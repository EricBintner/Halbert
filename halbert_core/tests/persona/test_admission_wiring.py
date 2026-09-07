# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Named-gate admission decisions wired onto the guest dashboard routes.

PACKET-02 C1: every guest route walks an ordered gate list and produces an
``IngressDecision`` (``persona/admission.py``); a deny answers with the
decision's ``reason_code`` in the error payload instead of an opaque
status. Each route gets one allow case and one deny case asserting the
reason_code string.

Halley's warning is pinned three ways:

- a route id with no gate list configured refuses admission
  (``no_gate_list_configured``) — the seam fails closed on unwritten
  policy, never silently allowing;
- the registry must cover every route the router serves, so a new route
  cannot land without a gate list;
- removing a route's entry turns its requests into refusals.

Warrant-layer composition rule (packet, 2026-09-07): these gates grade
ADMISSION — capability. The claims ladder (``persona/claims.py``) grades
identity claims and the warrant layer grades legitimacy; the ladder is
never chained behind these gates and these gates never behind the ladder.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from halbert_core.dashboard.routes import guest as guest_routes
from halbert_core.federation.peer_middleware import PeerContext, require_peer_auth
from halbert_core.federation.peers_config import PeerCredential
from halbert_core.persona import admission as admission_module
from halbert_core.persona import guest, private_sources, sibling
from halbert_core.persona.admission import ADMISSION_DISPATCH, ADMISSION_DROP
from halbert_core.proactive.events import get_event_bus


@pytest.fixture(autouse=True)
def _fresh_state():
    guest.reset_for_tests()
    private_sources.reset_for_tests()
    get_event_bus().clear()
    yield
    guest.reset_for_tests()
    private_sources.reset_for_tests()
    get_event_bus().clear()


@pytest.fixture
def _config_dir(tmp_path, monkeypatch):
    """Home records (and nothing else) stay inside the test's tmp dir."""
    import halbert_core.utils.platform as plat
    monkeypatch.setattr(plat, "get_config_dir", lambda: tmp_path)
    return tmp_path


@pytest.fixture
def _stores(tmp_path, monkeypatch):
    """The forget route's two halves, pointed at throwaway databases."""
    from halbert_core.agents import conversation_sqlite as cs
    from halbert_core.continuity import state_store as ss

    conv = cs.SqliteConversationStore(db_path=str(tmp_path / "conv.db"))
    ledger = ss.StateStore(db_path=str(tmp_path / "state.db"))
    monkeypatch.setattr(cs, "SqliteConversationStore", lambda *a, **k: conv)
    monkeypatch.setattr(ss, "StateStore", lambda *a, **k: ledger)
    return conv, ledger


def _peer(node_id="h2-node", name="H2"):
    cred = PeerCredential(
        node_id=node_id, node_name=name, role="body",
        token_hash="sha256:stub", paired_at="2026-01-01T00:00:00Z",
    )
    return PeerContext(node_id=node_id, node_name=name, role="body", capabilities=[], credential=cred)


def _app(peer=None):
    app = FastAPI()
    app.include_router(guest_routes.router)
    if peer is not None:
        app.dependency_overrides[require_peer_auth] = lambda: peer
    return app


def _offer_body(**extra):
    persona = {"name": "Marnie", "tone_descriptors": ["warm"], "directives": ["Keep it short."]}
    persona.update(extra)
    return {"persona": persona, "ttl_seconds": 30}


def _decisions(monkeypatch):
    """Capture the IngressDecision each admitted request produces."""
    seen = []
    real = admission_module.decide_ingress

    def spy(gates):
        decision = real(gates)
        seen.append(decision)
        return decision

    monkeypatch.setattr(guest_routes, "decide_ingress", spy)
    return seen


def _reason(resp):
    return resp.json()["detail"]["reason_code"]


def _fronting():
    """Offer a persona as a paired app, return the user's-side client."""
    TestClient(_app(_peer())).post("/api/guest/offer", json=_offer_body())
    return TestClient(_app())


class TestFailClosed:
    """Halley's warning, made mechanical: unwritten policy denies."""

    def test_a_route_with_no_gate_list_refuses_admission(self, monkeypatch):
        monkeypatch.setattr(guest_routes, "_ROUTE_GATES", {})
        client = TestClient(_app())
        resp = client.get("/api/guest")
        assert resp.status_code == 403
        assert _reason(resp) == "no_gate_list_configured"
        assert resp.json()["detail"]["decisive_gate"] == "route_registry"

    def test_dropping_one_routes_gate_list_turns_its_requests_into_refusals(self, monkeypatch):
        gates = dict(guest_routes._ROUTE_GATES)
        gates.pop("POST /api/guest/end")
        monkeypatch.setattr(guest_routes, "_ROUTE_GATES", gates)
        resp = TestClient(_app()).post("/api/guest/end")
        assert resp.status_code == 403
        assert _reason(resp) == "no_gate_list_configured"

    def test_every_route_on_the_router_has_a_gate_list(self):
        from fastapi.routing import APIRoute

        covered = 0
        for route in guest_routes.router.routes:
            if not isinstance(route, APIRoute):
                continue
            for method in route.methods:
                if method == "HEAD":
                    # Starlette adds HEAD to every GET route; no guest route
                    # registers HEAD itself.
                    continue
                assert f"{method} {route.path}" in guest_routes._ROUTE_GATES, (
                    f"{method} {route.path} has no gate list configured"
                )
                covered += 1
        assert covered == len(guest_routes._ROUTE_GATES)


class TestOffer:
    def test_allow(self, monkeypatch):
        seen = _decisions(monkeypatch)
        resp = TestClient(_app(_peer())).post("/api/guest/offer", json=_offer_body())
        assert resp.status_code == 200, resp.text
        decision = seen[-1]
        assert decision.admission == ADMISSION_DISPATCH
        assert decision.decisive_gate == "session_free"

    def test_deny_reason_code_when_another_peer_fronts(self):
        TestClient(_app(_peer("h2-node"))).post("/api/guest/offer", json=_offer_body())
        resp = TestClient(_app(_peer("other-app", "Other"))).post(
            "/api/guest/offer", json=_offer_body(name="Rex"))
        assert resp.status_code == 409
        assert _reason(resp) == "guest_already_fronting"
        assert resp.json()["detail"]["decisive_gate"] == "session_free"


class TestHeartbeat:
    def _offered(self):
        client = TestClient(_app(_peer()))
        session_id = client.post("/api/guest/offer", json=_offer_body()).json()["session"]["session_id"]
        return client, session_id

    def test_allow(self, monkeypatch):
        seen = _decisions(monkeypatch)
        client, session_id = self._offered()
        resp = client.post("/api/guest/heartbeat", json={"session_id": session_id})
        assert resp.status_code == 200
        decision = seen[-1]
        assert decision.admission == ADMISSION_DISPATCH
        assert decision.decisive_gate == "session_owned"

    def test_deny_reason_code_for_an_unknown_session(self):
        client, _ = self._offered()
        resp = client.post("/api/guest/heartbeat", json={"session_id": "nope"})
        assert resp.status_code == 404
        assert _reason(resp) == "no_such_session"

    def test_deny_reason_code_for_another_peers_session(self):
        _, session_id = self._offered()
        resp = TestClient(_app(_peer("other-app"))).post(
            "/api/guest/heartbeat", json={"session_id": session_id})
        assert resp.status_code == 403
        assert _reason(resp) == "session_owned_by_other_peer"


class TestWithdraw:
    def test_allow(self, monkeypatch):
        seen = _decisions(monkeypatch)
        client = TestClient(_app(_peer()))
        client.post("/api/guest/offer", json=_offer_body())
        resp = client.post("/api/guest/withdraw")
        assert resp.status_code == 200
        decision = seen[-1]
        assert decision.admission == ADMISSION_DISPATCH
        assert decision.decisive_gate == "session_owned"

    def test_deny_reason_code_for_another_peers_session(self):
        TestClient(_app(_peer("h2-node"))).post("/api/guest/offer", json=_offer_body())
        resp = TestClient(_app(_peer("other-app"))).post("/api/guest/withdraw")
        assert resp.status_code == 403
        assert _reason(resp) == "session_owned_by_other_peer"


class TestPull:
    PERSONA = {"id": "marnie-7", "name": "Marnie", "traits": ["warm"], "directives": ["Keep it short."]}

    def test_allow(self, monkeypatch):
        monkeypatch.setattr(
            sibling, "default_transport",
            lambda method, url, body, headers: (200, self.PERSONA))
        seen = _decisions(monkeypatch)
        resp = TestClient(_app()).post(
            "/api/guest/pull",
            json={"base_url": "http://127.0.0.1:8002", "persona_id": "marnie-7"})
        assert resp.status_code == 200, resp.text
        decision = seen[-1]
        assert decision.admission == ADMISSION_DISPATCH
        assert decision.decisive_gate == "local_admin"

    def test_deny_reason_code_off_machine(self):
        with patch(
            "halbert_core.federation.peer_middleware._is_local_client",
            return_value=False,
        ):
            resp = TestClient(_app()).post(
                "/api/guest/pull",
                json={"base_url": "http://127.0.0.1:8002", "persona_id": "marnie-7"})
        assert resp.status_code == 403
        assert _reason(resp) == "not_local_admin"
        assert guest.current_guest() is None


# The user's side: every one of these routes sits behind the same
# local-admin boundary gate, and every deny below drives the boundary the
# way it actually fails — the client's address, not a token.
_LOCAL_ADMIN_ROUTES = [
    ("post", "/api/guest/end", None),
    ("get", "/api/guest/homes", None),
    ("post", "/api/guest/homes", {"base_url": "http://h2.lan:8002", "label": "H2"}),
    ("delete", "/api/guest/homes?base_url=http%3A%2F%2Fh2.lan%3A8002", None),
    ("get", "/api/guest/available", None),
    ("post", "/api/guest/become", {"name": "Marnie"}),
    ("get", "/api/guest/private/sources", None),
    ("post", "/api/guest/private/release", {"source_id": "webcam:desk"}),
    ("post", "/api/guest/forget", {"session_id": "anything"}),
    ("get", "/api/guest", None),
]


class TestLocalAdminBoundary:
    @pytest.mark.parametrize("method,path,body", _LOCAL_ADMIN_ROUTES)
    def test_deny_reason_code_off_machine(self, method, path, body):
        client = TestClient(_app())
        with patch(
            "halbert_core.federation.peer_middleware._is_local_client",
            return_value=False,
        ):
            if body is None:
                resp = getattr(client, method)(path)
            else:
                resp = getattr(client, method)(path, json=body)
        assert resp.status_code == 403, resp.text
        assert _reason(resp) == "not_local_admin"
        assert resp.json()["detail"]["decisive_gate"] == "local_admin"


class TestEnd:
    def test_allow(self, monkeypatch):
        seen = _decisions(monkeypatch)
        TestClient(_app(_peer())).post("/api/guest/offer", json=_offer_body())
        resp = TestClient(_app()).post("/api/guest/end")
        assert resp.status_code == 200
        assert seen[-1].admission == ADMISSION_DISPATCH
        assert seen[-1].decisive_gate == "local_admin"


class TestHomes:
    def test_list_allow(self, monkeypatch, _config_dir):
        seen = _decisions(monkeypatch)
        resp = TestClient(_app()).get("/api/guest/homes")
        assert resp.status_code == 200
        assert seen[-1].admission == ADMISSION_DISPATCH

    def test_add_allow(self, monkeypatch, _config_dir):
        seen = _decisions(monkeypatch)
        resp = TestClient(_app()).post(
            "/api/guest/homes", json={"base_url": "http://h2.lan:8002", "label": "H2"})
        assert resp.status_code == 200, resp.text
        assert seen[-1].admission == ADMISSION_DISPATCH

    def test_forget_allow(self, monkeypatch, _config_dir):
        seen = _decisions(monkeypatch)
        resp = TestClient(_app()).delete(
            "/api/guest/homes?base_url=http%3A%2F%2Fh2.lan%3A8002")
        assert resp.status_code == 200
        assert seen[-1].admission == ADMISSION_DISPATCH


class TestAvailable:
    def test_allow(self, monkeypatch, _config_dir):
        seen = _decisions(monkeypatch)
        resp = TestClient(_app()).get("/api/guest/available")
        assert resp.status_code == 200, resp.text
        assert seen[-1].admission == ADMISSION_DISPATCH


class TestBecome:
    def test_allow(self, monkeypatch, _config_dir):
        from halbert_core.persona import guest_homes
        monkeypatch.setattr(
            guest_homes, "available_personas",
            lambda *a, **k: {"personas": [
                {"persona_id": "marnie-7", "name": "Marnie", "home_label": "H2",
                 "base_url": "http://h2.lan:8002"}], "unreachable": []})
        monkeypatch.setattr(
            sibling, "default_transport",
            lambda method, url, body, headers: (200, {"id": "marnie-7", "name": "Marnie"}))
        seen = _decisions(monkeypatch)
        resp = TestClient(_app()).post("/api/guest/become", json={"name": "marnie"})
        assert resp.status_code == 200, resp.text
        assert seen[-1].admission == ADMISSION_DISPATCH
        assert seen[-1].decisive_gate == "local_admin"


class TestPrivateSourcesRoutes:
    def test_assign_allow(self, monkeypatch):
        seen = _decisions(monkeypatch)
        client = _fronting()
        resp = client.post("/api/guest/private/assign", json={"source_id": "webcam:desk"})
        assert resp.status_code == 200, resp.text
        assert seen[-1].admission == ADMISSION_DISPATCH
        assert seen[-1].decisive_gate == "guest_fronting"

    def test_assign_deny_reason_code_with_no_guest_fronting(self):
        resp = TestClient(_app()).post(
            "/api/guest/private/assign", json={"source_id": "webcam:desk"})
        assert resp.status_code == 409
        assert _reason(resp) == "no_guest_fronting"
        assert resp.json()["detail"]["decisive_gate"] == "guest_fronting"

    def test_release_allow(self, monkeypatch):
        seen = _decisions(monkeypatch)
        client = _fronting()
        client.post("/api/guest/private/assign", json={"source_id": "webcam:desk"})
        resp = client.post("/api/guest/private/release", json={"source_id": "webcam:desk"})
        assert resp.status_code == 200
        assert seen[-1].admission == ADMISSION_DISPATCH

    def test_sources_allow(self, monkeypatch):
        monkeypatch.setattr(guest_routes.private_sources, "catalogue", lambda: [])
        seen = _decisions(monkeypatch)
        resp = TestClient(_app()).get("/api/guest/private/sources")
        assert resp.status_code == 200
        assert seen[-1].admission == ADMISSION_DISPATCH


class TestForgetSessionRoute:
    def test_allow(self, monkeypatch, _stores):
        seen = _decisions(monkeypatch)
        _fronting()
        resp = TestClient(_app()).post("/api/guest/forget", json={})
        assert resp.status_code == 200, resp.text
        assert seen[-1].admission == ADMISSION_DISPATCH
        assert seen[-1].decisive_gate == "forget_target"

    def test_deny_reason_code_with_nothing_named_and_nothing_fronting(self, _stores):
        resp = TestClient(_app()).post("/api/guest/forget", json={})
        assert resp.status_code == 409
        assert _reason(resp) == "no_session_to_forget"
        assert resp.json()["detail"]["decisive_gate"] == "forget_target"


class TestGuestStatus:
    def test_allow(self, monkeypatch):
        seen = _decisions(monkeypatch)
        resp = TestClient(_app()).get("/api/guest")
        assert resp.status_code == 200
        assert seen[-1].admission == ADMISSION_DISPATCH
        assert seen[-1].decisive_gate == "local_admin"