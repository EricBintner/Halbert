# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""P7a: Devices & entity-mode route tests.

The Devices page (P7b) API surface: device list joined with this node's
entity identity, entity-mode and body-name toggles (being.yml via the
locked composite), capability set/discover (P5c), and the WoL/remove
aliases over the peer store.  Pairing itself stays in routes/peers.py.
"""
from __future__ import annotations

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from halbert_core.agents.peer_tool_proxy import PeerToolUnavailable
from halbert_core.dashboard.routes.devices import router
from halbert_core.federation.peers_config import PeersConfig


@pytest.fixture
def client(monkeypatch, tmp_path):
    """App with only the devices router, isolated being.yml + peers.json."""
    monkeypatch.setattr(
        "halbert_core.config.being_config.get_config_dir", lambda: tmp_path)
    peers = PeersConfig(config_path=tmp_path / "peers.json")
    monkeypatch.setattr(
        "halbert_core.dashboard.routes.devices.get_peers_config", lambda: peers)
    # Never read the developer's real models.yml during token lookup.
    monkeypatch.setattr(
        "halbert_core.model.llm_config.load_global",
        lambda use_cache=True: {"saved_endpoints": []})
    app = FastAPI()
    app.include_router(router, prefix="/api")
    return TestClient(app), peers, tmp_path


class TestTheRoutesAreMountedWhereTheFrontendLooks:
    """ROUTE-01. The fixture above builds its own FastAPI() with
    prefix="/api", which is exactly how this went unnoticed: every test
    passed against a router mounted the way the app did NOT mount it. These
    go through create_app()."""

    def test_the_real_app_serves_the_devices_path(self):
        from halbert_core.dashboard.app import create_app

        client = TestClient(create_app())
        resp = client.get("/api/devices")
        assert resp.status_code != 404, (
            "Settings > Devices calls /api/devices; the app serves nothing there"
        )

    def test_the_unprefixed_path_is_not_the_contract(self):
        from halbert_core.dashboard.app import create_app

        client = TestClient(create_app())
        assert client.get("/devices").status_code == 404


class TestOnlyThisMachineMayReconfigureIt:
    """R10-F5. Every mutating device route shipped with no auth dependency
    at all: any caller that could reach the dashboard could rewrite this
    node's entity mode, rename its body, replace the peer token it trusts,
    or revoke another peer. The dashboard binds loopback by default, but
    HALBERT_HOST opens it — and the compute-peer feature gives operators a
    reason to."""

    def test_the_gate_refuses_a_non_loopback_client(self):
        from fastapi import FastAPI
        from halbert_core.federation.peer_middleware import require_local_admin

        app = FastAPI()

        @app.get("/probe", dependencies=[Depends(require_local_admin)])
        async def probe():
            return {"ok": True}

        remote = TestClient(app, client=("203.0.113.7", 51234))
        assert remote.get("/probe").status_code == 403

        local = TestClient(app, client=("127.0.0.1", 51234))
        assert local.get("/probe").status_code == 200

    def test_every_mutating_device_route_carries_the_gate(self):
        """Named individually rather than spot-checked: a route added later
        without the dependency is the same bug again."""
        from halbert_core.dashboard.routes.devices import router
        from halbert_core.federation.peer_middleware import require_local_admin

        mutating = [
            r for r in router.routes
            if set(getattr(r, "methods", set())) & {"PUT", "POST", "DELETE"}
        ]
        assert mutating, "no mutating device routes found"

        for route in mutating:
            gates = [d.call for d in route.dependant.dependencies]
            assert require_local_admin in gates, (
                f"{sorted(route.methods)} {route.path} has no local-admin gate"
            )


def _pair(peers, node_id="desk", **kwargs):
    return peers.add_peer(
        node_id=node_id, node_name=kwargs.pop("node_name", "Mac Studio"),
        role=kwargs.pop("role", "compute_provider"),
        raw_token=kwargs.pop("raw_token", "t"),
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Read model
# ---------------------------------------------------------------------------

class TestListDevices:
    def test_empty_fresh_node_is_independent(self, client):
        c, peers, _ = client
        body = c.get("/api/devices").json()
        assert body["status"] == "ok"
        assert body["entity_mode"] == "independent"
        assert body["entity_role"] == "independent"
        assert body["canonical_memory_url"] == ""
        assert body["devices"] == []

    def test_a_paired_body_makes_this_node_the_canonical_host(self, client):
        """W4-05: 'singular' used to be defined only on the proxying body;
        the host that IS the memory reported Independent Node."""
        c, peers, _ = client
        _pair(peers, "mac", role="body")
        body = c.get("/api/devices").json()
        assert body["entity_role"] == "canonical"
        assert body["entity_mode"] == "singular"
        assert body["canonical_memory_url"] == ""

    def test_a_revoked_body_no_longer_makes_a_canonical_host(self, client):
        c, peers, _ = client
        _pair(peers, "mac", role="body")
        peers.revoke_peer("mac")
        body = c.get("/api/devices").json()
        assert body["entity_role"] == "independent"
        assert body["entity_mode"] == "independent"

    def test_a_node_proxying_to_a_canonical_host_is_a_body(self, client):
        c, _, _ = client
        c.put("/api/devices/entity-mode",
              json={"mode": "singular", "base_url": "http://n150.lan:8001"})
        body = c.get("/api/devices").json()
        assert body["entity_role"] == "body"
        assert body["entity_mode"] == "singular"

    def test_devices_include_capabilities_wol_and_revoked(self, client):
        c, peers, _ = client
        _pair(peers, "desk", endpoint="http://desktop.lan:8000",
              capabilities=["gpu_llm", "terminal"],
              wol_enabled=True, wol_mac="AA:BB:CC:DD:EE:FF")
        _pair(peers, "old", node_name="Old Pi")
        peers.revoke_peer("old")
        devices = {d["node_id"]: d for d in c.get("/api/devices").json()["devices"]}
        assert devices["desk"]["capabilities"] == ["gpu_llm", "terminal"]
        assert devices["desk"]["wol_enabled"] is True
        assert devices["desk"]["revoked"] is False
        assert devices["old"]["revoked"] is True
        # No token material ever leaves the store.
        assert "token_hash" not in devices["desk"]


# ---------------------------------------------------------------------------
# Entity mode & body name
# ---------------------------------------------------------------------------

class TestEntityMode:
    def test_singular_with_base_url_derives_canonical_urls(self, client):
        c, _, tmp = client
        r = c.put("/api/devices/entity-mode",
                  json={"mode": "singular", "base_url": "http://n150.lan:8001"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["entity_mode"] == "singular"
        assert body["canonical_memory_url"] == "http://n150.lan:8001/api/memory"
        assert body["canonical_thread_url"] == "http://n150.lan:8001/api/conversations"
        # Persisted through the locked composite — a fresh load sees it.
        state = c.get("/api/devices").json()
        assert state["entity_mode"] == "singular"

    def test_singular_explicit_urls_override_derivation(self, client):
        c, _, _ = client
        r = c.put("/api/devices/entity-mode", json={
            "mode": "singular",
            "memory_url": "http://n150.lan:8001/api/memory",
            "thread_url": "http://n150.lan:8001/api/conversations",
        })
        assert r.status_code == 200
        assert r.json()["canonical_thread_url"].endswith("/api/conversations")

    def test_singular_without_any_url_is_400(self, client):
        c, _, _ = client
        r = c.put("/api/devices/entity-mode", json={"mode": "singular"})
        assert r.status_code == 400

    def test_singular_with_invalid_url_is_400(self, client):
        """being.yml's own validator (P1) rejects non-http(s) canonical URLs."""
        c, _, _ = client
        r = c.put("/api/devices/entity-mode",
                  json={"mode": "singular", "base_url": "ftp://n150.lan"})
        assert r.status_code == 400

    def test_independent_clears_canonical_urls(self, client):
        c, _, _ = client
        c.put("/api/devices/entity-mode",
              json={"mode": "singular", "base_url": "http://n150.lan:8001"})
        r = c.put("/api/devices/entity-mode", json={"mode": "independent"})
        assert r.status_code == 200
        body = r.json()
        assert body["entity_mode"] == "independent"
        assert body["canonical_memory_url"] == ""
        assert body["canonical_thread_url"] == ""

    def test_unknown_mode_is_400(self, client):
        c, _, _ = client
        assert c.put("/api/devices/entity-mode",
                     json={"mode": "hive"}).status_code == 400


class TestBodyName:
    def test_body_name_round_trips(self, client):
        c, _, _ = client
        r = c.put("/api/devices/body-name", json={"body_name": "desk"})
        assert r.status_code == 200
        assert r.json()["body_name"] == "desk"
        assert c.get("/api/devices").json()["body_name"] == "desk"

    def test_empty_body_name_is_422(self, client):
        c, _, _ = client
        assert c.put("/api/devices/body-name",
                     json={"body_name": ""}).status_code == 422


# ---------------------------------------------------------------------------
# Capabilities
# ---------------------------------------------------------------------------

class TestCapabilities:
    def test_set_capabilities_reports_unknown_but_keeps_them(self, client):
        c, peers, _ = client
        _pair(peers)
        r = c.put("/api/devices/desk/capabilities",
                  json={"capabilities": ["terminal", "quantum_router"]})
        assert r.status_code == 200
        body = r.json()
        assert body["capabilities"] == ["terminal", "quantum_router"]
        assert body["unknown"] == ["quantum_router"]

    def test_set_capabilities_on_missing_device_is_404(self, client):
        c, _, _ = client
        assert c.put("/api/devices/ghost/capabilities",
                     json={"capabilities": []}).status_code == 404


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

class TestDiscover:
    def _proxy(self, monkeypatch, tools=None, error=None):
        class _FakeProxy:
            def __init__(self, peer_url, bearer_token, timeout):
                self.seen = (peer_url, bearer_token)

            def list_tools(self):
                if error is not None:
                    raise error
                return tools or []

        monkeypatch.setattr(
            "halbert_core.agents.peer_tool_proxy.PeerToolProxy", _FakeProxy)
        return _FakeProxy

    def test_discover_maps_tools_to_capabilities(self, client, monkeypatch):
        c, peers, _ = client
        _pair(peers, endpoint="http://desktop.lan:8000")
        self._proxy(monkeypatch, tools=[
            "search_knowledge", "run_terminal_command", "read_config_file",
        ])
        r = c.post("/api/devices/desk/discover", json={"token": "tok"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "discovered"
        assert "mcp" in body["capabilities"]        # tools/list answered
        assert "sourceprep" in body["capabilities"]  # search_knowledge
        assert "terminal" in body["capabilities"]    # run_terminal_command
        assert "sysadmin_tools" in body["capabilities"]  # read_config_file
        # Persisted to the peer record.
        assert "mcp" in peers.get_peer("desk").capabilities

    def test_discover_unreachable_leaves_capabilities_untouched(self, client, monkeypatch):
        c, peers, _ = client
        _pair(peers, endpoint="http://desktop.lan:8000", capabilities=["terminal"])
        self._proxy(monkeypatch, error=PeerToolUnavailable("asleep"))
        r = c.post("/api/devices/desk/discover", json={"token": "tok"})
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "unreachable"
        assert body["capabilities"] == ["terminal"]
        assert peers.get_peer("desk").capabilities == ["terminal"]

    def test_discover_without_endpoint(self, client):
        c, peers, _ = client
        _pair(peers)  # no endpoint
        r = c.post("/api/devices/desk/discover", json={"token": "tok"})
        assert r.json()["status"] == "no-endpoint"

    def test_discover_without_token(self, client):
        c, peers, _ = client
        _pair(peers, endpoint="http://desktop.lan:8000")
        r = c.post("/api/devices/desk/discover", json={})
        assert r.json()["status"] == "no-token"

    def test_discover_on_missing_device_is_404(self, client):
        c, _, _ = client
        assert c.post("/api/devices/ghost/discover",
                      json={}).status_code == 404


# ---------------------------------------------------------------------------
# WoL toggle & remove (aliases over the peer store)
# ---------------------------------------------------------------------------

class TestDeviceLifecycle:
    def test_wol_toggle_round_trips(self, client):
        c, peers, _ = client
        _pair(peers)
        r = c.put("/api/devices/desk/wol",
                  json={"enabled": True, "mac": "AA:BB:CC:DD:EE:FF"})
        assert r.status_code == 200
        assert r.json()["wol_enabled"] is True
        assert peers.get_peer("desk").wol_enabled is True

    def test_remove_device_revokes(self, client):
        c, peers, _ = client
        _pair(peers)
        r = c.delete("/api/devices/desk")
        assert r.status_code == 200
        assert r.json()["status"] == "removed"
        assert peers.get_peer("desk").revoked is True

    def test_missing_device_operations_are_404(self, client):
        c, _, _ = client
        assert c.delete("/api/devices/ghost").status_code == 404
        assert c.put("/api/devices/ghost/wol",
                     json={"enabled": True}).status_code == 404

class TestPeerToken:
    def test_token_stored_when_canonical_host_set(self, client):
        c, _, _ = client
        c.put("/api/devices/entity-mode",
              json={"mode": "singular", "base_url": "http://n150.lan:8001"})
        r = c.put("/api/devices/peer-token", json={"token": "hbt_abc123"})
        assert r.status_code == 200, r.text
        assert r.json()["peer_token_set"] is True
        # Written through the locked composite; a fresh load sees it.
        state = c.get("/api/devices").json()
        assert state["entity_mode"] == "singular"

    def test_token_rejected_without_canonical_host(self, client):
        """A token with no canonical host is a config mistake waiting to
        happen — singular mode needs both."""
        c, _, _ = client
        r = c.put("/api/devices/peer-token", json={"token": "hbt_abc123"})
        assert r.status_code == 400

    def test_clearing_is_always_allowed(self, client):
        c, _, _ = client
        assert c.put("/api/devices/peer-token",
                     json={"token": ""}).status_code == 200


class TestForgetDevice:
    def test_forget_erases_the_record(self, client):
        c, peers, _ = client
        _pair(peers, "desk")
        r = c.delete("/api/devices/desk?forget=true")
        assert r.status_code == 200
        assert r.json()["status"] == "forgotten"
        assert peers.get_peer("desk") is None  # gone, not revoked

    def test_plain_remove_revokes_but_retains(self, client):
        c, peers, _ = client
        _pair(peers, "desk")
        r = c.delete("/api/devices/desk")
        assert r.json()["status"] == "removed"
        assert peers.get_peer("desk").revoked is True
        assert peers.get_peer("desk") is not None

    def test_repair_after_forget_starts_clean(self, client):
        """Q5's rationale: no ghost record colliding with a re-pair."""
        c, peers, _ = client
        _pair(peers, "desk")
        c.delete("/api/devices/desk?forget=true")
        # add_peer raises on an existing node_id — after forget it must not.
        peers.add_peer("desk", "Mac Studio", "compute_provider", raw_token="t2")
        assert peers.get_peer("desk").revoked is False

    def test_forget_missing_device_is_404(self, client):
        c, _, _ = client
        assert c.delete("/api/devices/ghost?forget=true").status_code == 404
