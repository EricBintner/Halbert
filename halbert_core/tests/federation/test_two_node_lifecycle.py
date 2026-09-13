# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Multi-node Task 4 — two-node lifecycle integration test.

One process stands in for two: a host FastAPI app (pairing + compute +
conversation routes over a real TestClient) and a satellite side built
from the client halves (pairing_client, PeerConversationStore,
ResilientPeerConversationStore). Transport between them is an ASGI shim,
so every call crosses the real route stack — peer auth, allowlists,
response envelopes — just not a real socket (test_tls_transport.py owns
the real-socket TLS verification; here the cert material is real and the
PIN PROPAGATION is what is under test).

Lifecycle covered:

1. Both nodes mint self-signed certs (distinct scratch dirs).
2. Satellite requests pairing, advertises its fingerprint; the host
   advertises its own back.
3. Operator approval on the host; verify issues the bearer token.
4. Both peers.json files carry the other node's cert pin.
5. A streamed compute turn is redacted through the SSE window.
6. Conversation writes land on the host while it is up.
7. Host "sleeps" (every request raises ConnectionError): writes succeed
   locally and stage; reads serve the mirror.
8. Host wakes: flush_pending() replays the queue in order.
"""
from __future__ import annotations

import json
from urllib.parse import urlsplit

import pytest
import requests
from fastapi import FastAPI
from fastapi.testclient import TestClient

from halbert_core.agents.conversation_sqlite import SqliteConversationStore
from halbert_core.agents.peer_conversation_store import PeerConversationStore
from halbert_core.agents.resilient_peer_store import ResilientPeerConversationStore
from halbert_core.dashboard.routes import conversations as conv_routes
from halbert_core.dashboard.routes import peers as peers_routes
from halbert_core.federation import compute_endpoint, pairing_client, peer_middleware, tls
from halbert_core.federation.peers_config import PeersConfig

pytest.importorskip("cryptography", reason="TLS cert generation needs it")


# ---------------------------------------------------------------------------
# Transport shim — requests-shaped calls onto the host's TestClient
# ---------------------------------------------------------------------------

class _ShimResp:
    def __init__(self, resp):
        self._resp = resp
        self.status_code = resp.status_code
        self.text = resp.text

    def json(self):
        return self._resp.json()

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}: {self.text[:200]}")


class _AsgiSession:
    """A requests.Session lookalike that lands calls on the host app."""

    def __init__(self, client: TestClient):
        self.client = client

    def _call(self, method, url, **kwargs):
        path = urlsplit(url).path
        return _ShimResp(self.client.request(method, path, **kwargs))

    def post(self, url, json=None, headers=None, timeout=None):
        return self._call("POST", url, json=json, headers=headers)

    def get(self, url, headers=None, timeout=None):
        return self._call("GET", url, headers=headers)


class _DownSession:
    def post(self, *args, **kwargs):
        raise requests.ConnectionError("host is asleep")

    def get(self, *args, **kwargs):
        raise requests.ConnectionError("host is asleep")


# ---------------------------------------------------------------------------
# The two nodes
# ---------------------------------------------------------------------------

class TestTwoNodeLifecycle:
    @pytest.fixture
    def nodes(self, tmp_path, monkeypatch):
        host_dir = tmp_path / "host"
        sat_dir = tmp_path / "sat"
        host_tls_dir = host_dir / "peer_tls"
        sat_tls_dir = sat_dir / "peer_tls"
        host_tls_dir.mkdir(parents=True)
        sat_tls_dir.mkdir(parents=True)

        # -- TLS material, one pair per node (peer_tls_dir is per-process;
        #    repoint it while each node's cert is minted).
        monkeypatch.setattr(tls, "peer_tls_dir", lambda: host_tls_dir)
        host_cert, _ = tls.ensure_node_cert("host-node")
        host_pin = tls.cert_fingerprint(host_cert)
        monkeypatch.setattr(tls, "peer_tls_dir", lambda: sat_tls_dir)
        sat_cert, _ = tls.ensure_node_cert("sat-node")
        sat_pin = tls.cert_fingerprint(sat_cert)

        # -- Host app + its singletons.
        host_config = PeersConfig(config_path=host_dir / "peers.json")
        monkeypatch.setattr(
            peer_middleware, "get_peers_config", lambda: host_config)
        monkeypatch.setattr(
            peers_routes, "get_peers_config", lambda: host_config)
        monkeypatch.setattr(
            peer_middleware, "_is_local_client", lambda request: True)
        monkeypatch.setattr(
            tls, "peer_tls_advertisement", lambda: (host_pin, 18443))

        host_store = SqliteConversationStore(str(host_dir / "conv.db"))
        conv_routes._conversation_store = host_store

        async def fake_submit(request, tools, peer):
            return {
                "content": "intro\npassword=hunter2\noutro\n",
                "finish_reason": "stop",
                "usage": {"prompt_tokens": 4, "completion_tokens": 9,
                          "total_tokens": 13},
            }

        monkeypatch.setattr(
            compute_endpoint, "_submit_to_broker", fake_submit)

        app = FastAPI()
        app.include_router(peers_routes.router)
        app.include_router(conv_routes.router, prefix="/api/conversations")
        app.include_router(compute_endpoint.router)
        host_client = TestClient(app)

        sat_config = PeersConfig(config_path=sat_dir / "peers.json")

        yield type("Nodes", (), {
            "host_dir": host_dir, "sat_dir": sat_dir,
            "host_client": host_client, "host_store": host_store,
            "host_config": host_config, "sat_config": sat_config,
            "host_pin": host_pin, "sat_pin": sat_pin,
            "session": _AsgiSession(host_client),
        })()

        conv_routes._conversation_store = None

    # ------------------------------------------------------------------
    # The lifecycle
    # ------------------------------------------------------------------

    def test_full_lifecycle(self, nodes):
        host = nodes

        # ── 1-3: pairing handshake ─────────────────────────────────────
        pair = pairing_client.request_pairing(
            "http://host.test",
            node_id="sat-node",
            node_name="Satellite",
            role="satellite",
            endpoint="https://sat.test:18444",
            tls_pin=host.sat_pin,
            session=host.session,
        )
        assert pair["request_id"]
        # The host advertised its fingerprint + TLS port.
        assert pair["tls_pin"] == host.host_pin
        assert pair["tls_port"] == 18443

        # Operator at the host reads the PIN and approves.
        pending = host.host_client.get("/api/peers/pending").json()
        pin = next(p["pin"] for p in pending
                   if p["request_id"] == pair["request_id"])
        ok = host.host_client.post(
            f"/api/peers/pending/{pair['request_id']}/approve")
        assert ok.status_code == 200

        verify = pairing_client.verify_pairing(
            "http://host.test",
            request_id=pair["request_id"],
            pin=pin,
            node_id="sat-node",
            session=host.session,
        )
        token = verify["token"]
        assert verify["tls_pin"] == host.host_pin

        # ── 4: both peers.json files carry the other's cert pin ────────
        host_cred = host.host_config.get_peer("sat-node")
        assert host_cred is not None and host_cred.tls_pin == host.sat_pin
        assert host_cred.tls_enabled is True

        host.sat_config.add_peer(
            "host-node", "Host", "host", token,
            endpoint="https://host.test:18443",
            tls_enabled=True, tls_pin=host.host_pin,
        )
        raw = json.loads((host.sat_dir / "peers.json").read_text())
        sat_cred = next(p for p in raw["peers"] if p["node_id"] == "host-node")
        assert sat_cred["tls_pin"] == host.host_pin
        assert sat_cred["tls_enabled"] is True

        # ── 5: streamed compute turn, redacted through the SSE window ──
        resp = host.host_client.post(
            "/api/compute/v1/chat/completions",
            json={"model": "m",
                  "messages": [{"role": "user", "content": "hi"}],
                  "stream": True},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.text
        assert "hunter2" not in body
        assert "data: [DONE]" in body
        deltas = "".join(
            f["choices"][0]["delta"].get("content", "")
            for f in (
                json.loads(b[5:])
                for b in body.split("\n\n")
                if b.strip().startswith("data:") and "[DONE]" not in b
            )
        )
        assert "intro" in deltas and "outro" in deltas
        assert "<secret>" in deltas

        # ── 6: conversation writes reach the host while it is up ───────
        peer = PeerConversationStore(
            "http://host.test", token, session=host.session)
        store = ResilientPeerConversationStore(
            peer, str(host.sat_dir / "cache.db"), autostart_flush=False)
        assert store.create_thread("t1", "Lifecycle") is True
        online_mid = store.append_message("t1", "user", "hello while up")
        assert online_mid is not None
        host_msgs = host.host_store.list_messages("t1")
        assert host_msgs[0]["content"] == "hello while up"

        # ── 7: host sleeps — writes stage, reads serve the mirror ──────
        peer._session = _DownSession()
        local_mid = store.append_message("t1", "user", "written while down")
        assert isinstance(local_mid, int)
        assert store.staged_count() == 1
        offline = store.list_messages("t1")
        assert [m["content"] for m in offline] == [
            "hello while up", "written while down"]

        # ── 8: host wakes — the staged write replays in order ──────────
        peer._session = host.session
        assert store.flush_pending() == 1
        assert store.staged_count() == 0
        contents = [m["content"] for m in host.host_store.list_messages("t1")]
        assert contents == ["hello while up", "written while down"]
        # The locally-minted id resolved to the host's id.
        host_mid = host.host_store.list_messages("t1")[1]["message_id"]
        assert store._peer_id_for(local_mid, "message") == host_mid

        store.close()
