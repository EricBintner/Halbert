# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""SE-16 / R10-F1 / R10-F5: pairing must be a handshake, not self-service.

``POST /api/peers/pair`` returned the 4-digit PIN to the requester, and
``POST /api/peers/verify`` minted a bearer token on a PIN match alone — so
anyone who could reach the port could pair itself in two calls and walk away
with a peer credential. The PIN was theatre: the caller was handed the secret
it was then asked to prove. There was no expiry, no attempt limit and no cap
on pending requests, and the "desktop confirmation" was a TODO comment.

Nothing tested any of this; these are the properties, not the plumbing.
"""
from __future__ import annotations

import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from halbert_core.dashboard.routes import peers as peers_routes
from halbert_core.federation.peers_config import PeersConfig


@pytest.fixture
def client(monkeypatch, tmp_path):
    config = PeersConfig(config_path=tmp_path / "peers.json")
    monkeypatch.setattr(
        "halbert_core.federation.peer_middleware.get_peers_config", lambda: config)
    monkeypatch.setattr(
        "halbert_core.dashboard.routes.peers.get_peers_config", lambda: config)
    peers_routes._pending_pairings.clear()
    app = FastAPI()
    app.include_router(peers_routes.router)
    yield TestClient(app), config
    peers_routes._pending_pairings.clear()


PAIR_BODY = {
    "node_id": "satellite-1",
    "node_name": "Kitchen Panel",
    "role": "satellite",
}


def _pair(http, body=None):
    resp = http.post("/api/peers/pair", json=body or PAIR_BODY)
    assert resp.status_code == 200, resp.text
    return resp.json()


class TestThePinIsNotHandedToTheRequester:

    def test_the_pairing_response_carries_no_pin(self, client):
        http, _ = client
        body = _pair(http)
        assert "pin" not in body, "the requester was handed the secret it must prove"
        assert body["request_id"]

    def test_the_pin_is_readable_only_from_this_machine(self, client):
        http, _ = client
        rid = _pair(http)["request_id"]

        pending = http.get("/api/peers/pending").json()
        assert [p["request_id"] for p in pending] == [rid]
        assert len(pending[0]["pin"]) == 4

        remote = TestClient(http.app, client=("203.0.113.7", 4444))
        assert remote.get("/api/peers/pending").status_code == 403


class TestNoTokenWithoutApproval:

    def test_a_correct_pin_alone_issues_nothing(self, client):
        http, config = client
        rid = _pair(http)["request_id"]
        pin = http.get("/api/peers/pending").json()[0]["pin"]

        resp = http.post("/api/peers/verify", json={
            "request_id": rid, "pin": pin, "node_id": "satellite-1",
        })
        assert resp.status_code == 403
        assert config.get_peer("satellite-1") is None

    def test_approval_then_the_pin_completes_the_pairing(self, client):
        http, config = client
        rid = _pair(http)["request_id"]
        pin = http.get("/api/peers/pending").json()[0]["pin"]

        assert http.post(f"/api/peers/pending/{rid}/approve").status_code == 200

        resp = http.post("/api/peers/verify", json={
            "request_id": rid, "pin": pin, "node_id": "satellite-1",
        })
        assert resp.status_code == 200, resp.text
        assert resp.json()["token"]
        assert config.get_peer("satellite-1") is not None

    def test_approval_is_local_admin_only(self, client):
        http, _ = client
        rid = _pair(http)["request_id"]
        remote = TestClient(http.app, client=("203.0.113.7", 4444))
        assert remote.post(f"/api/peers/pending/{rid}/approve").status_code == 403


class TestGuessingThePin:

    def test_three_wrong_pins_end_the_attempt(self, client):
        http, config = client
        rid = _pair(http)["request_id"]
        real = http.get("/api/peers/pending").json()[0]["pin"]
        http.post(f"/api/peers/pending/{rid}/approve")

        wrong = "0000" if real != "0000" else "1111"
        for _ in range(2):
            assert http.post("/api/peers/verify", json={
                "request_id": rid, "pin": wrong, "node_id": "satellite-1",
            }).status_code == 400

        third = http.post("/api/peers/verify", json={
            "request_id": rid, "pin": wrong, "node_id": "satellite-1",
        })
        assert third.status_code == 400
        assert "again" in third.json()["detail"]

        # The request is gone, so the real PIN no longer works either.
        assert http.post("/api/peers/verify", json={
            "request_id": rid, "pin": real, "node_id": "satellite-1",
        }).status_code == 400
        assert config.get_peer("satellite-1") is None

    def test_a_request_for_another_node_is_refused(self, client):
        http, _ = client
        rid = _pair(http)["request_id"]
        pin = http.get("/api/peers/pending").json()[0]["pin"]
        http.post(f"/api/peers/pending/{rid}/approve")

        resp = http.post("/api/peers/verify", json={
            "request_id": rid, "pin": pin, "node_id": "someone-else",
        })
        assert resp.status_code == 400


class TestPendingRequestsAreBounded:

    def test_a_lapsed_request_cannot_be_completed(self, client, monkeypatch):
        http, config = client
        rid = _pair(http)["request_id"]
        pin = http.get("/api/peers/pending").json()[0]["pin"]
        http.post(f"/api/peers/pending/{rid}/approve")

        # Age it past the window.
        peers_routes._pending_pairings[rid].created_at = (
            time.time() - peers_routes.PAIRING_TTL_S - 1
        )

        resp = http.post("/api/peers/verify", json={
            "request_id": rid, "pin": pin, "node_id": "satellite-1",
        })
        assert resp.status_code == 400
        assert config.get_peer("satellite-1") is None
        assert http.get("/api/peers/pending").json() == []

    def test_pending_requests_do_not_pile_up_without_limit(self, client):
        http, _ = client
        for i in range(peers_routes.PAIRING_MAX_PENDING):
            assert http.post("/api/peers/pair", json={
                **PAIR_BODY, "node_id": f"sat-{i}",
            }).status_code == 200

        overflow = http.post("/api/peers/pair", json={**PAIR_BODY, "node_id": "sat-x"})
        assert overflow.status_code == 429

    def test_the_operator_can_refuse_outright(self, client):
        http, _ = client
        rid = _pair(http)["request_id"]
        assert http.delete(f"/api/peers/pending/{rid}").status_code == 200
        assert http.get("/api/peers/pending").json() == []


class TestRevocationIsNotAPeerPrivilege:
    """R10-F5. Any authenticated peer could revoke any other — the file's own
    TODO called it a privilege-escalation risk, and one compromised satellite
    could cut every other node off from the host."""

    def _paired(self, http, config, node_id):
        rid = http.post("/api/peers/pair", json={**PAIR_BODY, "node_id": node_id}).json()["request_id"]
        pin = next(p["pin"] for p in http.get("/api/peers/pending").json()
                   if p["request_id"] == rid)
        http.post(f"/api/peers/pending/{rid}/approve")
        return http.post("/api/peers/verify", json={
            "request_id": rid, "pin": pin, "node_id": node_id,
        }).json()["token"]

    def test_a_peer_cannot_revoke_another_peer(self, client):
        http, config = client
        token_a = self._paired(http, config, "sat-a")
        self._paired(http, config, "sat-b")

        remote = TestClient(http.app, client=("203.0.113.7", 4444))
        resp = remote.delete(
            "/api/peers/sat-b", headers={"Authorization": f"Bearer {token_a}"},
        )
        assert resp.status_code == 403
        assert config.get_peer("sat-b").revoked is False

    def test_a_peer_may_revoke_itself(self, client):
        http, config = client
        token_a = self._paired(http, config, "sat-a")

        remote = TestClient(http.app, client=("203.0.113.7", 4444))
        resp = remote.delete(
            "/api/peers/sat-a", headers={"Authorization": f"Bearer {token_a}"},
        )
        assert resp.status_code == 200
        assert config.get_peer("sat-a").revoked is True

    def test_the_operator_may_revoke_anyone(self, client):
        http, config = client
        self._paired(http, config, "sat-b")
        assert http.delete("/api/peers/sat-b").status_code == 200
        assert config.get_peer("sat-b").revoked is True
