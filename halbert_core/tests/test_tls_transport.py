# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Multi-node Task 1 — self-signed TLS transport with fingerprint pinning.

Peer traffic rode cleartext HTTP + bearer token: the token, the pairing
PIN, and every conversation payload crossed the LAN readable. The fix is
per-node self-signed certificates and a pinned fingerprint per peer — no
CA, no new hard dependency. These tests pin down the properties:

- a node cert is generated once, with restrictive key permissions
- fingerprinting is deterministic and stdlib-only
- a pinned session accepts exactly one certificate and refuses every
  other (including "self-signed but different" and "no pin")
- the credential model round-trips the pin
- the pairing routes advertise the pin only when the listener is up
- the satellite-side client escalates verify to pinned HTTPS
"""
from __future__ import annotations

import http.server
import ssl
import threading

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from halbert_core.federation import tls
from halbert_core.federation.peers_config import PeersConfig

pytestmark = pytest.mark.skipif(
    not tls.tls_listener_enabled(), reason="HALBERT_PEER_TLS disabled"
)


@pytest.fixture(autouse=True)
def _isolated_state(monkeypatch, tmp_path):
    """Cert/key material lands under <state_dir>/peer-tls — point the state
    dir at tmp so no test writes to the real ~/.local/state/halbert."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    yield


@pytest.fixture
def cert_pair():
    return tls.ensure_node_cert("test-node")


@pytest.fixture
def https_server(cert_pair):
    """A real TLS server on loopback serving a canned verify response."""
    cert_path, key_path = cert_pair

    class Handler(http.server.BaseHTTPRequestHandler):
        def _json(self, body: bytes):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            self._json(b"{}")

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            self.rfile.read(length)
            self._json(b'{"token": "raw-token-abc", "desktop_node_id": "host-1"}')

        def log_message(self, *args):
            pass

    ctx = tls.make_server_ssl_context(cert_path, key_path)
    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    server.socket = ctx.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"https://127.0.0.1:{server.server_address[1]}", tls.cert_fingerprint(cert_path)
    server.shutdown()
    thread.join(timeout=5)


class TestNodeCert:
    def test_generates_cert_and_key_with_locked_permissions(self, cert_pair):
        import os

        cert_path, key_path = cert_pair
        assert cert_path.exists() and key_path.exists()
        assert os.stat(key_path).st_mode & 0o777 == 0o600
        assert b"BEGIN CERTIFICATE" in cert_path.read_bytes()
        assert b"PRIVATE KEY" in key_path.read_bytes()

    def test_idempotent_returns_the_same_cert(self, cert_pair):
        cert_path, _ = cert_pair
        again, _ = tls.ensure_node_cert("test-node")
        assert cert_path.read_bytes() == again.read_bytes()

    def test_cn_carries_the_node_id(self, cert_pair):
        from cryptography import x509

        cert_path, _ = cert_pair
        cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
        cn = cert.subject.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)
        assert cn[0].value == "test-node"


class TestFingerprint:
    def test_sha256_prefixed_hex(self, cert_pair):
        fp = tls.cert_fingerprint(cert_pair[0])
        assert fp.startswith("sha256:")
        assert len(fp) == len("sha256:") + 64

    def test_deterministic(self, cert_pair):
        assert tls.cert_fingerprint(cert_pair[0]) == tls.cert_fingerprint(cert_pair[0])

    def test_two_nodes_have_different_fingerprints(self, cert_pair, tmp_path, monkeypatch):
        # A second cert under a second state dir.
        first = tls.cert_fingerprint(cert_pair[0])
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "other-state"))
        other_cert, _ = tls.ensure_node_cert("other-node")
        assert tls.cert_fingerprint(other_cert) != first


class TestPinnedSession:
    def test_accepts_the_pinned_cert(self, https_server):
        url, fp = https_server
        session = tls.make_pinned_session(fp)
        assert session.get(url + "/", timeout=5).status_code == 200

    def test_rejects_a_different_cert(self, https_server):
        url, _ = https_server
        import requests.exceptions

        session = tls.make_pinned_session("sha256:" + "0" * 64)
        with pytest.raises(requests.exceptions.SSLError):
            session.get(url + "/", timeout=5)

    def test_plain_requests_reject_the_self_signed_cert(self, https_server):
        """The pin is load-bearing: without it, default verification fails."""
        import requests
        import requests.exceptions

        url, _ = https_server
        with pytest.raises(requests.exceptions.SSLError):
            requests.get(url + "/", timeout=5)


class TestCredentialTlsFields:
    def test_round_trip(self, tmp_path):
        config = PeersConfig(config_path=tmp_path / "peers.json")
        cred = config.add_peer(
            node_id="sat-1",
            node_name="Satellite",
            role="satellite",
            raw_token="tok",
            tls_enabled=True,
            tls_pin="sha256:abc",
        )
        assert cred.tls_enabled is True
        assert cred.tls_pin == "sha256:abc"

        reloaded = PeersConfig(config_path=tmp_path / "peers.json")
        cred2 = reloaded.get_peer("sat-1")
        assert cred2.tls_enabled is True
        assert cred2.tls_pin == "sha256:abc"

    def test_old_records_default_to_plaintext(self):
        from halbert_core.federation.peers_config import PeerCredential

        cred = PeerCredential.from_dict({
            "node_id": "old-peer",
            "token_hash": "sha256:x",
            "paired_at": "2026-01-01",
        })
        assert cred.tls_enabled is False
        assert cred.tls_pin is None

    def test_set_tls_pin(self, tmp_path):
        config = PeersConfig(config_path=tmp_path / "peers.json")
        config.add_peer("sat-1", "Sat", "satellite", "tok")
        assert config.set_tls_pin("sat-1", "sha256:dead" * 1) is True
        cred = config.get_peer("sat-1")
        assert cred.tls_enabled and cred.tls_pin
        assert config.set_tls_pin("sat-1", None) is True
        assert config.get_peer("sat-1").tls_enabled is False
        assert config.set_tls_pin("nobody", "sha256:x") is False


class TestFindPeerByEndpoint:
    def test_matches_across_schemes(self, tmp_path):
        config = PeersConfig(config_path=tmp_path / "peers.json")
        config.add_peer("sat-1", "Sat", "satellite", "tok",
                        endpoint="peer://desktop.lan:8001")
        assert config.find_peer_by_endpoint("https://desktop.lan:8001") is not None
        assert config.find_peer_by_endpoint("http://desktop.lan:8001/api") is not None
        assert config.find_peer_by_endpoint("http://other.lan:8001") is None

    def test_same_host_fallback_when_ports_differ(self, tmp_path):
        config = PeersConfig(config_path=tmp_path / "peers.json")
        config.add_peer("sat-1", "Sat", "satellite", "tok",
                        endpoint="https://desktop.lan:8001")
        # canonical_thread_url may still say :8000 — host match wins.
        assert config.find_peer_by_endpoint("http://desktop.lan:8000") is not None


class TestPairingAdvertisement:
    """The pin is advertised only when the TLS listener is actually up."""

    @pytest.fixture
    def client(self, monkeypatch, tmp_path):
        from halbert_core.dashboard.routes import peers as peers_routes
        import halbert_core.federation.peer_middleware as pm

        monkeypatch.setattr(pm, "_is_local_client", lambda request: True)
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

    def test_no_listener_means_no_advertisement(self, client):
        http, _ = client
        body = http.post("/api/peers/pair", json={
            "node_id": "sat-1", "node_name": "S", "role": "satellite",
        }).json()
        assert body["tls_pin"] is None
        assert body["tls_port"] is None

    def test_listener_up_advertises_the_pin(self, client, monkeypatch):
        monkeypatch.setattr(
            "halbert_core.federation.tls.peer_tls_advertisement",
            lambda: ("sha256:abcd", 8001),
        )
        http, _ = client
        body = http.post("/api/peers/pair", json={
            "node_id": "sat-1", "node_name": "S", "role": "satellite",
            "tls_pin": "sha256:satcert",
        }).json()
        assert body["tls_pin"] == "sha256:abcd"
        assert body["tls_port"] == 8001

    def test_verify_stores_the_satellites_pin(self, client, monkeypatch):
        monkeypatch.setattr(
            "halbert_core.federation.tls.peer_tls_advertisement",
            lambda: ("sha256:abcd", 8001),
        )
        http, config = client
        rid = http.post("/api/peers/pair", json={
            "node_id": "sat-1", "node_name": "S", "role": "satellite",
            "tls_pin": "sha256:satcert",
        }).json()["request_id"]
        pin = http.get("/api/peers/pending").json()[0]["pin"]
        http.post(f"/api/peers/pending/{rid}/approve")
        body = http.post("/api/peers/verify", json={
            "request_id": rid, "pin": pin, "node_id": "sat-1",
        }).json()
        assert body["tls_pin"] == "sha256:abcd"
        assert body["tls_port"] == 8001
        cred = config.get_peer("sat-1")
        assert cred.tls_enabled and cred.tls_pin == "sha256:satcert"

    def test_pending_view_shows_the_satellites_pin(self, client):
        http, _ = client
        rid = http.post("/api/peers/pair", json={
            "node_id": "sat-1", "node_name": "S", "role": "satellite",
            "tls_pin": "sha256:satcert",
        }).json()["request_id"]
        pending = http.get("/api/peers/pending").json()
        assert pending[0]["request_id"] == rid
        assert pending[0]["tls_pin"] == "sha256:satcert"


class TestPairingClient:
    def test_host_tls_url_rewrites_scheme_and_port(self):
        from halbert_core.federation.pairing_client import host_tls_url

        assert host_tls_url("http://desktop.lan:8000", 8001) == "https://desktop.lan:8001"
        assert host_tls_url("http://192.168.1.5:8000", 8443) == "https://192.168.1.5:8443"

    def test_verify_uses_pinned_https_when_advertised(self, https_server):
        from halbert_core.federation.pairing_client import verify_pairing

        url, fp = https_server
        port = int(url.rsplit(":", 1)[1])
        # base_url deliberately wrong port — the pin+port must route us to
        # the TLS server regardless.
        body = verify_pairing(
            "http://127.0.0.1:8000",
            request_id="r1", pin="1234", node_id="sat-1",
            tls_pin=fp, tls_port=port,
        )
        assert body["token"] == "raw-token-abc"

    def test_verify_falls_back_to_plaintext_without_a_pin(self, monkeypatch):
        import requests

        from halbert_core.federation import pairing_client

        calls = {}

        class Resp:
            def raise_for_status(self): pass
            def json(self): return {"token": "t", "desktop_node_id": "h"}

        def fake_post(url, **kwargs):
            calls["url"] = url
            return Resp()

        monkeypatch.setattr(requests, "post", fake_post)
        body = pairing_client.verify_pairing(
            "http://desktop.lan:8000",
            request_id="r1", pin="1234", node_id="sat-1",
        )
        assert body["token"] == "t"
        assert calls["url"] == "http://desktop.lan:8000/api/peers/verify"


class TestPeerApp:
    """The dedicated TLS-listener app mounts exactly the peer surface."""

    def test_mounts_peer_routes(self, monkeypatch, tmp_path):
        import halbert_core.federation.peer_middleware as pm

        monkeypatch.setattr(pm, "_is_local_client", lambda request: True)
        config = PeersConfig(config_path=tmp_path / "peers.json")
        monkeypatch.setattr(
            "halbert_core.federation.peer_middleware.get_peers_config", lambda: config)
        monkeypatch.setattr(
            "halbert_core.dashboard.routes.peers.get_peers_config", lambda: config)
        app = tls.build_peer_app()
        http = TestClient(app)
        # Pairing is open (PIN + approval is the boundary).
        resp = http.post("/api/peers/pair", json={
            "node_id": "s1", "node_name": "S", "role": "satellite"})
        assert resp.status_code == 200
        # The conversation mesh requires a peer token.
        assert http.get("/api/conversations/health").status_code == 401
        # Owner routes are not on this app at all.
        assert http.get("/api/settings/").status_code == 404


class TestPeerProviderTls:
    def test_pinned_credential_switches_to_https(self, monkeypatch, tmp_path):
        from halbert_core.model.providers.peer import PeerProvider

        config = PeersConfig(config_path=tmp_path / "peers.json")
        config.add_peer(
            "desktop-1", "Desktop", "compute_provider", "tok",
            endpoint="https://desktop.lan:8001",
            tls_enabled=True, tls_pin="sha256:" + "ab" * 32,
        )
        monkeypatch.setattr(
            "halbert_core.federation.peer_middleware.get_peers_config", lambda: config)
        provider = PeerProvider(
            endpoint="peer://desktop.lan:8001",
            peer_token="tok",
            peer_node_id="desktop-1",
        )
        assert provider._endpoint == "https://desktop.lan:8001"

    def test_unpinned_credential_stays_http(self, monkeypatch, tmp_path):
        from halbert_core.model.providers.peer import PeerProvider

        config = PeersConfig(config_path=tmp_path / "peers.json")
        config.add_peer("desktop-1", "Desktop", "compute_provider", "tok")
        monkeypatch.setattr(
            "halbert_core.federation.peer_middleware.get_peers_config", lambda: config)
        provider = PeerProvider(
            endpoint="peer://desktop.lan:8000",
            peer_token="tok",
            peer_node_id="desktop-1",
        )
        assert provider._endpoint == "http://desktop.lan:8000"
