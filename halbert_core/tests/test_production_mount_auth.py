# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The peer surface must work through the production mounts (F-A).

The security review of 2026-09-13 (``.handoff/research/halbert-backup/
security-review-response.md``) found that ``peers`` and ``conversations``
were mounted behind ``require_owner`` — a door that knows only the dashboard
token — while every peer-scoped suite mounted its router bare. Result: the
pairing handshake was unreachable for a real satellite, and a genuine peer
token 401'd on every peer route except compute. The suites proved the
handshake and production never ran it.

These tests drive the REAL app — ``create_app()`` with the production
``mount_api`` — with real client addresses, the way the probe did. Any test
in this file failing means the production door has diverged from the
per-route guards again, not that a unit is broken.
"""
from __future__ import annotations

import os
import uuid

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402


REMOTE = ("203.0.113.7", 4444)  # a satellite on the LAN
LOCAL = ("127.0.0.1", 4444)     # the operator at the machine


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    """The real app, production mounts, isolated state and peer store."""
    tmp = tmp_path_factory.mktemp("prod-mount-auth")
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("XDG_STATE_HOME", str(tmp))
        mp.setenv("HALBERT_CONFIG_DIR", str(tmp / "config"))
        mp.setenv("HALBERT_DATA_DIR", str(tmp / "data"))
        # The conftest autouse fixture pins a TEST_API_TOKEN for every client;
        # this suite manages its own credentials explicitly.
        prev = os.environ.pop("HALBERT_API_TOKEN", None)
        try:
            from halbert_core.dashboard.app import create_app
            yield create_app()
        finally:
            if prev is not None:
                os.environ["HALBERT_API_TOKEN"] = prev


@pytest.fixture
def dashboard_token(app):
    from halbert_core.dashboard import auth as dashboard_auth
    return dashboard_auth.load_or_create_token()


@pytest.fixture
def peers_store(app, tmp_path):
    """Point the process-wide PeersConfig singleton at an isolated file."""
    from pathlib import Path

    from halbert_core.federation.peers_config import PeersConfig
    import halbert_core.federation.peer_middleware as pm

    config = PeersConfig(config_path=Path(tmp_path) / "peers.json")
    prev, pm._peers_config = getattr(pm, "_peers_config", None), config
    yield config
    pm._peers_config = prev


@pytest.fixture
def peer_token(peers_store):
    """A genuine peer token: stored hashed, presented raw by a remote client."""
    raw = f"hbt_{uuid.uuid4().hex}"
    peers_store.add_peer(
        node_id="prod-mount-sat", node_name="Prod Mount Satellite",
        role="body", raw_token=raw,
    )
    return raw


class TestPairingIsReachableInProduction:
    """The handshake a satellite drives — through the production door."""

    def test_a_credential_less_satellite_can_request_pairing(self, app):
        sat = TestClient(app, client=REMOTE)
        res = sat.post("/api/peers/pair", json={
            "node_id": "want-in", "node_name": "New Satellite", "role": "body",
        })
        assert res.status_code == 200, res.text
        assert "pin" not in res.json()

    def test_verify_refuses_before_approval_unchanged(self, app):
        sat = TestClient(app, client=REMOTE)
        rid = sat.post("/api/peers/pair", json={
            "node_id": "want-in", "node_name": "New Satellite", "role": "body",
        }).json()["request_id"]
        # A correct PIN alone never issued a token (SE-16), and still must
        # not — the F-A fix opens the door, it does not lower the handshake.
        res = sat.post("/api/peers/verify", json={
            "request_id": rid, "pin": "0000", "node_id": "want-in",
        })
        assert res.status_code == 403

    def test_the_local_operator_can_approve_with_the_dashboard_token(
            self, app, dashboard_token):
        owner = TestClient(app, client=LOCAL,
                           headers={"Authorization": f"Bearer {dashboard_token}"})
        rid = TestClient(app, client=REMOTE).post("/api/peers/pair", json={
            "node_id": "want-in", "node_name": "New Satellite", "role": "body",
        }).json()["request_id"]
        res = owner.post(f"/api/peers/pending/{rid}/approve")
        assert res.status_code == 200, res.text


class TestPeerTokenAgainstTheProductionDoor:
    """What a paired satellite can and cannot do with its own token."""

    def test_peers_list(self, app, peer_token):
        sat = TestClient(app, client=REMOTE,
                         headers={"Authorization": f"Bearer {peer_token}"})
        assert sat.get("/api/peers/list").status_code == 200

    def test_conversations_health(self, app, peer_token):
        sat = TestClient(app, client=REMOTE,
                         headers={"Authorization": f"Bearer {peer_token}"})
        res = sat.get("/api/conversations/health")
        assert res.status_code == 200, res.text
        assert res.json() == {"healthy": True, "connected": True}

    def test_owner_surface_still_refuses_peer_tokens(self, app, peer_token):
        """The fix opens the peer door; it grants nothing else. A peer token
        on an owner route is still nobody (the pre-fix behaviour for every
        route, retained where it belongs). /api/approvals is the one
        exception by design: its pending list answers to
        require_trust_anchor, so a genuine peer is authenticated and then
        refused for its role — 403, not 401."""
        sat = TestClient(app, client=REMOTE,
                         headers={"Authorization": f"Bearer {peer_token}"})
        for path in ("/api/settings/policy", "/api/terminal/exec"):
            res = sat.get(path) if not path.endswith("exec") else \
                sat.post(path, json={"command": "id"})
            assert res.status_code == 401, f"{path} answered a peer token"
        assert sat.get("/api/approvals").status_code == 403


class TestPerPeerControlsStayPerPeer:
    """require_local_or_self_peer on revocation and WoL (F-E / R10-F5)."""

    def test_a_peer_cannot_revoke_another(self, app, peers_store, peer_token):
        peers_store.add_peer(
            node_id="other-sat", node_name="Other", role="body",
            raw_token=f"hbt_{uuid.uuid4().hex}",
        )
        sat = TestClient(app, client=REMOTE,
                         headers={"Authorization": f"Bearer {peer_token}"})
        assert sat.delete("/api/peers/other-sat").status_code == 403
        assert peers_store.get_peer("other-sat").revoked is False

    def test_a_peer_may_revoke_itself(self, app, peer_token):
        sat = TestClient(app, client=REMOTE,
                         headers={"Authorization": f"Bearer {peer_token}"})
        assert sat.delete("/api/peers/prod-mount-sat").status_code == 200

    def test_a_peer_cannot_retarget_another_peers_wol(
            self, app, peers_store, peer_token):
        peers_store.add_peer(
            node_id="other-sat", node_name="Other", role="body",
            raw_token=f"hbt_{uuid.uuid4().hex}",
        )
        sat = TestClient(app, client=REMOTE,
                         headers={"Authorization": f"Bearer {peer_token}"})
        res = sat.put("/api/peers/other-sat/wol",
                      json={"enabled": True, "mac": "AA:BB:CC:DD:EE:FF"})
        assert res.status_code == 403
        assert peers_store.get_peer("other-sat").wol_enabled is False

    def test_a_peer_may_retarget_its_own_wol(self, app, peer_token):
        sat = TestClient(app, client=REMOTE,
                         headers={"Authorization": f"Bearer {peer_token}"})
        res = sat.put("/api/peers/prod-mount-sat/wol",
                      json={"enabled": True, "mac": "AA:BB:CC:DD:EE:FF"})
        assert res.status_code == 200, res.text


class TestLocalAdminOnlyControlsStayLocal:
    """compute-peer link and discovered inventory (the two formerly unguarded
    routes on the peers router) — local-admin now, reachable by the owner."""

    def test_compute_peer_link_refuses_a_remote_peer(self, app, peer_token):
        sat = TestClient(app, client=REMOTE,
                         headers={"Authorization": f"Bearer {peer_token}"})
        res = sat.post("/api/peers/compute-peer",
                       json={"endpoint": "peer://x:8000", "token": ""})
        assert res.status_code == 403

    def test_compute_peer_link_refuses_a_remote_anon(self, app):
        sat = TestClient(app, client=REMOTE)
        res = sat.post("/api/peers/compute-peer",
                       json={"endpoint": "peer://x:8000", "token": ""})
        assert res.status_code == 403

    def test_discovered_refuses_a_remote_peer(self, app, peer_token):
        sat = TestClient(app, client=REMOTE,
                         headers={"Authorization": f"Bearer {peer_token}"})
        assert sat.get("/api/peers/discovered").status_code == 403


@pytest.fixture
def trust_anchor_token(peers_store):
    """A paired trust_anchor device (the phone-class peer)."""
    raw = f"hbt_{uuid.uuid4().hex}"
    peers_store.add_peer(
        node_id="prod-mount-phone", node_name="Prod Mount Phone",
        role="trust_anchor", raw_token=raw,
    )
    return raw


class TestTrustAnchorApproval:
    """The phone-class peer approves additions, never mints its own kind
    (security review 2026-09-13, Q1.1/Q2.2)."""

    def _request_pairing(self, app, role: str, node: str) -> str:
        res = TestClient(app, client=REMOTE).post("/api/peers/pair", json={
            "node_id": node, "node_name": node, "role": role,
        })
        assert res.status_code == 200, res.text
        return res.json()["request_id"]

    def test_trust_anchor_can_approve_a_body_pairing(
            self, app, trust_anchor_token):
        rid = self._request_pairing(app, "body", "incoming-body")
        phone = TestClient(app, client=REMOTE,
                           headers={"Authorization": f"Bearer {trust_anchor_token}"})
        res = phone.post(f"/api/peers/pending/{rid}/approve")
        assert res.status_code == 200, res.text

    def test_trust_anchor_can_list_pending_without_pins(
            self, app, trust_anchor_token):
        self._request_pairing(app, "body", "incoming-body-2")
        phone = TestClient(app, client=REMOTE,
                           headers={"Authorization": f"Bearer {trust_anchor_token}"})
        res = phone.get("/api/peers/pending")
        assert res.status_code == 200, res.text
        assert all(item["pin"] is None for item in res.json())

    def test_local_operator_sees_pins(self, app, dashboard_token):
        self._request_pairing(app, "body", "incoming-body-3")
        owner = TestClient(app, client=LOCAL,
                           headers={"Authorization": f"Bearer {dashboard_token}"})
        res = owner.get("/api/peers/pending")
        assert res.status_code == 200, res.text
        pending = [i for i in res.json() if i["node_id"] == "incoming-body-3"]
        assert pending and pending[0]["pin"]

    def test_a_body_peer_cannot_approve(self, app, peer_token):
        rid = self._request_pairing(app, "body", "incoming-body-4")
        sat = TestClient(app, client=REMOTE,
                         headers={"Authorization": f"Bearer {peer_token}"})
        res = sat.post(f"/api/peers/pending/{rid}/approve")
        assert res.status_code == 403

    def test_a_body_peer_cannot_list_pending(self, app, peer_token):
        sat = TestClient(app, client=REMOTE,
                         headers={"Authorization": f"Bearer {peer_token}"})
        assert sat.get("/api/peers/pending").status_code == 403

    def test_anonymous_remote_cannot_list_pending(self, app):
        res = TestClient(app, client=REMOTE).get("/api/peers/pending")
        assert res.status_code == 401

    def test_trust_anchor_cannot_mint_another_trust_anchor(
            self, app, trust_anchor_token):
        rid = self._request_pairing(app, "trust_anchor", "incoming-phone")
        phone = TestClient(app, client=REMOTE,
                           headers={"Authorization": f"Bearer {trust_anchor_token}"})
        res = phone.post(f"/api/peers/pending/{rid}/approve")
        assert res.status_code == 403

    def test_trust_anchor_pairing_approved_at_the_machine(
            self, app, dashboard_token, trust_anchor_token):
        rid = self._request_pairing(app, "trust_anchor", "incoming-phone-2")
        owner = TestClient(app, client=LOCAL,
                           headers={"Authorization": f"Bearer {dashboard_token}"})
        res = owner.post(f"/api/peers/pending/{rid}/approve")
        assert res.status_code == 200, res.text

    def test_remote_owner_credential_can_approve(
            self, app, dashboard_token):
        """The owner credential satisfies the door from anywhere — a router
        that leaves require_owner must not regress the remote owner."""
        rid = self._request_pairing(app, "body", "incoming-body-5")
        owner = TestClient(app, client=REMOTE,
                           headers={"Authorization": f"Bearer {dashboard_token}"})
        res = owner.post(f"/api/peers/pending/{rid}/approve")
        assert res.status_code == 200, res.text


class TestApprovalsTrustAnchorSurface:
    """The approvals router is self-authenticating now: the pending list,
    the detail read, and the two decision routes answer to
    require_trust_anchor; history and proposals stay owner-only (F-A
    restructure + Q1)."""

    def _queue_request(self) -> str:
        import uuid as _uuid
        from halbert_core.approval.engine import ApprovalEngine, ApprovalRequest
        rid = str(_uuid.uuid4())
        ApprovalEngine()._save_request(ApprovalRequest(
            id=rid, task="t", action="a", reasoning="r", confidence=0.5,
            risk_level="low", system_state={}, affected_resources=[],
        ))
        return rid

    def test_trust_anchor_lists_pending_approvals(self, app, trust_anchor_token):
        phone = TestClient(app, client=REMOTE,
                           headers={"Authorization": f"Bearer {trust_anchor_token}"})
        assert phone.get("/api/approvals").status_code == 200

    def test_trust_anchor_approves_a_staged_command(
            self, app, trust_anchor_token):
        rid = self._queue_request()
        phone = TestClient(app, client=REMOTE,
                           headers={"Authorization": f"Bearer {trust_anchor_token}"})
        res = phone.post(f"/api/approvals/{rid}/approve", json={"approved": True})
        assert res.status_code == 200, res.text
        assert res.json()["success"] is True

    def test_a_body_peer_cannot_approve_a_staged_command(
            self, app, peer_token):
        rid = self._queue_request()
        sat = TestClient(app, client=REMOTE,
                         headers={"Authorization": f"Bearer {peer_token}"})
        assert sat.post(f"/api/approvals/{rid}/approve",
                        json={"approved": True}).status_code == 403

    def test_history_and_proposals_stay_owner_only(
            self, app, trust_anchor_token, peer_token):
        phone = TestClient(app, client=REMOTE,
                           headers={"Authorization": f"Bearer {trust_anchor_token}"})
        assert phone.get("/api/approvals/history").status_code == 401
        assert phone.get("/api/approvals/proposals").status_code == 401
        sat = TestClient(app, client=REMOTE,
                         headers={"Authorization": f"Bearer {peer_token}"})
        assert sat.get("/api/approvals").status_code == 403


class TestWebSocketPeerCredential:
    """Q9: a paired peer opens the audio sockets with its own token —
    the companion voice MVP's prerequisite. Before this, the WS door knew
    only the dashboard token and the phone would have needed the owner
    credential (F-B)."""

    def test_peer_token_opens_the_audio_socket(self, app, peer_token):
        sat = TestClient(app, client=REMOTE)
        # Auth passed if the handshake completes; the pipeline may then
        # close 1013 (audio disabled in the test app) — that is after the
        # door, not at it.
        with sat.websocket_connect(f"/api/audio/stream?token={peer_token}"):
            pass

    def test_dashboard_token_still_opens_the_audio_socket(
            self, app, dashboard_token):
        sat = TestClient(app, client=REMOTE)
        with sat.websocket_connect(f"/api/audio/stream?token={dashboard_token}"):
            pass

    def test_garbage_token_is_refused(self, app):
        sat = TestClient(app, client=REMOTE)
        with pytest.raises(Exception):
            with sat.websocket_connect("/api/audio/stream?token=hbt_garbage"):
                pass