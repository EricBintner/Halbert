# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The channel a paired app hands a persona over — design §8, option 2.

Not the MCP surface: ``mcp/server.py`` is a standalone stdio/HTTP process,
so a process-local guest offered there would never reach the agent. These
routes live in the dashboard process that owns the agent singleton, and
reuse the pairing token (``require_peer_auth``) for the app's side and the
local-admin boundary for the user's side.

Every ending — withdrawn, handed back, ended by the user, heartbeat missed —
is announced on the proactive event bus so the bell and the conversation
see the face change (§7). The Presence Pill reads ``fronting`` from
``/api/instance/info`` (I4).
"""
from __future__ import annotations

import asyncio
import os
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from halbert_core.dashboard.routes import guest as guest_routes
from halbert_core.federation.peer_middleware import PeerContext, require_peer_auth
from halbert_core.federation.peers_config import PeerCredential
from halbert_core.persona import guest, private_sources, sibling
from halbert_core.proactive.events import get_event_bus, is_user_facing


@pytest.fixture(autouse=True)
def _fresh_state():
    guest.reset_for_tests()
    private_sources.reset_for_tests()
    get_event_bus().clear()
    yield
    guest.reset_for_tests()
    private_sources.reset_for_tests()
    get_event_bus().clear()


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


class TestOffer:

    def test_a_paired_app_can_offer_a_persona(self):
        client = TestClient(_app(_peer()))
        resp = client.post("/api/guest/offer", json=_offer_body())
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["session"]["name"] == "Marnie"
        assert body["session"]["offered_by"] == "h2-node"
        assert body["dropped"] == []
        live = guest.current_guest()
        assert live is not None and live.offered_by == "h2-node"

    def test_fields_that_are_not_the_guests_are_dropped_and_reported(self):
        client = TestClient(_app(_peer()))
        resp = client.post("/api/guest/offer", json=_offer_body(autonomy_level="act", ha_token="x"))
        assert resp.status_code == 200
        assert resp.json()["dropped"] == ["autonomy_level", "ha_token"]

    def test_without_a_pairing_token_the_offer_is_refused(self):
        client = TestClient(_app())
        resp = client.post("/api/guest/offer", json=_offer_body())
        assert resp.status_code == 401

    def test_a_persona_without_a_name_is_a_bad_request(self):
        client = TestClient(_app(_peer()))
        resp = client.post("/api/guest/offer", json={"persona": {"tone_descriptors": ["warm"]}})
        assert resp.status_code == 400
        assert guest.current_guest() is None

    def test_a_second_app_cannot_take_over(self):
        TestClient(_app(_peer("h2-node"))).post("/api/guest/offer", json=_offer_body())
        resp = TestClient(_app(_peer("other-app", "Other"))).post("/api/guest/offer", json=_offer_body(name="Rex"))
        assert resp.status_code == 409
        assert guest.current_guest().persona.name == "Marnie"

    def test_the_offer_is_announced(self):
        TestClient(_app(_peer())).post("/api/guest/offer", json=_offer_body())
        events = get_event_bus().get_recent()
        assert len(events) == 1
        event = events[0]
        assert event.type == "guest_session"
        assert is_user_facing(event)
        assert event.data["state"] == "fronting"
        assert "Marnie" in event.title


class TestLifetime:

    def _offered(self):
        client = TestClient(_app(_peer()))
        session_id = client.post("/api/guest/offer", json=_offer_body()).json()["session"]["session_id"]
        return client, session_id

    def test_heartbeat_keeps_the_session_alive(self):
        client, session_id = self._offered()
        resp = client.post("/api/guest/heartbeat", json={"session_id": session_id})
        assert resp.status_code == 200
        assert resp.json()["session"]["active"] is True

    def test_heartbeat_for_an_unknown_session_is_404(self):
        client, _ = self._offered()
        assert client.post("/api/guest/heartbeat", json={"session_id": "nope"}).status_code == 404

    def test_heartbeat_from_another_app_is_403(self):
        _, session_id = self._offered()
        other = TestClient(_app(_peer("other-app")))
        assert other.post("/api/guest/heartbeat", json={"session_id": session_id}).status_code == 403

    def test_the_app_can_withdraw_and_it_is_announced(self):
        client, _ = self._offered()
        resp = client.post("/api/guest/withdraw")
        assert resp.status_code == 200
        assert resp.json()["session"]["end_reason"] == "withdrawn"
        assert guest.current_guest() is None
        ended = [e for e in get_event_bus().get_recent() if e.data.get("state") == "ended"]
        assert len(ended) == 1 and ended[0].data["reason"] == "withdrawn"

    def test_another_app_cannot_withdraw_a_session_it_did_not_offer(self):
        self._offered()
        other = TestClient(_app(_peer("other-app")))
        assert other.post("/api/guest/withdraw").status_code == 403
        assert guest.current_guest() is not None

    def test_withdraw_when_idle_is_idle(self):
        client = TestClient(_app(_peer()))
        resp = client.post("/api/guest/withdraw")
        assert resp.status_code == 200 and resp.json()["status"] == "idle"

    def test_the_user_can_end_it_from_this_machine(self):
        self._offered()
        client = TestClient(_app())   # no peer token: the user's side
        resp = client.post("/api/guest/end")
        assert resp.status_code == 200
        assert resp.json()["session"]["end_reason"] == "ended_by_user"
        assert guest.current_guest() is None

    def test_a_missed_heartbeat_is_announced_when_noticed(self):
        client = TestClient(_app(_peer()))
        client.post("/api/guest/offer", json={"persona": {"name": "Marnie"}, "ttl_seconds": 1})
        session = guest.current_guest()
        assert guest.current_guest(now=session.deadline + 1) is None
        ended = [e for e in get_event_bus().get_recent() if e.data.get("state") == "ended"]
        assert len(ended) == 1 and ended[0].data["reason"] == "heartbeat_missed"

    def test_a_handback_from_the_tool_is_announced_too(self):
        self._offered()
        guest.handback()
        ended = [e for e in get_event_bus().get_recent() if e.data.get("state") == "ended"]
        assert len(ended) == 1 and ended[0].data["reason"] == "handback"


class TestWhatThePillSees:

    def test_status_route(self):
        client = TestClient(_app(_peer()))
        assert client.get("/api/guest").json() == {"fronting": None, "private_sources": {}}
        client.post("/api/guest/offer", json=_offer_body())
        fronting = client.get("/api/guest").json()["fronting"]
        assert fronting["name"] == "Marnie" and fronting["active"] is True

    def test_instance_info_carries_the_guest(self, tmp_path):
        from halbert_core.dashboard.routes.instance import get_instance_info

        env = {"HALBERT_PERSONA_ID": "halbert", "HALBERT_CONFIG_DIR": str(tmp_path)}
        with patch.dict(os.environ, env, clear=False):
            info = asyncio.run(get_instance_info())
            assert info["fronting"] is None
            persona, _ = guest.GuestPersona.from_payload({"name": "Marnie"})
            guest.offer(persona, offered_by="h2-node", offered_by_name="H2")
            info = asyncio.run(get_instance_info())
        assert info["fronting"]["name"] == "Marnie"
        assert info["fronting"]["offered_by_name"] == "H2"
        # I4: the machine's own name is still the machine's; the pill shows both.
        assert info["display_name"] != "Marnie"


class TestTheHome:

    def test_an_offer_can_name_the_guests_home_and_the_token_is_never_shown(self):
        client = TestClient(_app(_peer()))
        body = _offer_body()
        body["home"] = {"base_url": "http://127.0.0.1:8002/", "persona_id": "marnie-7", "token": "tkn", "label": "H2"}
        resp = client.post("/api/guest/offer", json=body)
        assert resp.status_code == 200, resp.text
        assert resp.json()["session"]["home"] == {"base_url": "http://127.0.0.1:8002", "persona_id": "marnie-7", "label": "H2"}
        assert "tkn" not in resp.text
        assert guest.current_guest().home.token == "tkn"

    def test_a_bad_home_is_a_bad_request_and_nothing_fronts(self):
        client = TestClient(_app(_peer()))
        body = _offer_body()
        body["home"] = {"base_url": "ftp://x", "persona_id": "p"}
        assert client.post("/api/guest/offer", json=body).status_code == 400
        assert guest.current_guest() is None


class TestPull:
    """"Halbert, be Marnie": the user's side fetches the persona from its home."""

    PERSONA = {"id": "marnie-7", "name": "Marnie", "traits": ["warm"], "directives": ["Keep it short."]}

    def test_pull_fetches_wears_and_announces(self, monkeypatch):
        calls = []

        def transport(method, url, body, headers):
            calls.append((method, url))
            return 200, self.PERSONA

        monkeypatch.setattr(sibling, "default_transport", transport)
        client = TestClient(_app())
        resp = client.post("/api/guest/pull", json={"base_url": "http://127.0.0.1:8002", "persona_id": "marnie-7", "label": "H2"})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["session"]["name"] == "Marnie"
        assert body["session"]["home"]["persona_id"] == "marnie-7"
        assert body["dropped"] == []
        live = guest.current_guest()
        assert live is not None and live.home is not None and live.keepalive is not None
        assert calls and calls[0][1].endswith("/api/personas/marnie-7")
        events = get_event_bus().get_recent()
        assert events and events[0].data["state"] == "fronting"

    def test_a_dead_home_is_a_bad_gateway_and_nothing_fronts(self, monkeypatch):
        def dead(method, url, body, headers):
            raise ConnectionError("down")

        monkeypatch.setattr(sibling, "default_transport", dead)
        client = TestClient(_app())
        resp = client.post("/api/guest/pull", json={"base_url": "http://127.0.0.1:8002", "persona_id": "marnie-7"})
        assert resp.status_code == 502
        assert guest.current_guest() is None

    def test_pull_while_another_app_fronts_is_a_conflict(self, monkeypatch):
        monkeypatch.setattr(sibling, "default_transport", lambda m, u, b, h: (200, self.PERSONA))
        TestClient(_app(_peer("other-app"))).post("/api/guest/offer", json=_offer_body(name="Rex"))
        resp = TestClient(_app()).post("/api/guest/pull", json={"base_url": "http://127.0.0.1:8002", "persona_id": "marnie-7"})
        assert resp.status_code == 409
        assert guest.current_guest().persona.name == "Rex"


class TestPrivateSources:
    """N4. Handing one source to the guest, and being told what that means."""

    @staticmethod
    def _fronting():
        client = TestClient(_app(_peer()))
        client.post("/api/guest/offer", json={"persona": {"name": "Marnie"}, "ttl_seconds": 30})
        return TestClient(_app())   # the user's side: no peer token

    def test_the_user_can_hand_over_a_source(self):
        client = self._fronting()
        resp = client.post("/api/guest/private/assign", json={"source_id": "webcam:desk"})
        assert resp.status_code == 200, resp.text
        assert resp.json()["private_sources"] == {"webcam:desk": "guest"}
        assert private_sources.active() is True

    def test_a_caller_that_is_not_at_this_machine_cannot_hand_over_a_camera(self):
        """require_local_admin, not require_peer_auth: the app that lent the
        persona must not be able to award itself the user's camera. The
        boundary is the client's address, so that is what this drives — a
        TestClient always looks local, which is exactly why asserting on a
        bearer token here would have proved nothing."""
        client = self._fronting()
        with patch(
            "halbert_core.federation.peer_middleware._is_local_client",
            return_value=False,
        ):
            resp = client.post("/api/guest/private/assign", json={"source_id": "webcam:desk"})
        assert resp.status_code == 403, resp.text
        assert private_sources.active() is False

    def test_releasing_is_local_only_too(self):
        client = self._fronting()
        client.post("/api/guest/private/assign", json={"source_id": "webcam:desk"})
        with patch(
            "halbert_core.federation.peer_middleware._is_local_client",
            return_value=False,
        ):
            assert client.post(
                "/api/guest/private/release", json={"source_id": "webcam:desk"}
            ).status_code == 403
        assert private_sources.active() is True

    def test_nothing_can_be_handed_over_with_no_guest_fronting(self):
        client = TestClient(_app())
        resp = client.post("/api/guest/private/assign", json={"source_id": "webcam:desk"})
        assert resp.status_code == 409
        assert private_sources.active() is False

    def test_a_malformed_source_id_is_a_bad_request(self):
        client = self._fronting()
        resp = client.post("/api/guest/private/assign", json={"source_id": "not an id"})
        assert resp.status_code == 400

    def test_the_first_handover_carries_the_statement(self):
        """The private-mode review's P6: the line has to be in the interface,
        not only in a design document."""
        client = self._fronting()
        client.post("/api/guest/private/assign", json={"source_id": "webcam:desk"})

        said = [e for e in get_event_bus().get_recent() if e.data.get("state") == "private"]
        assert len(said) == 1
        assert said[0].data["first"] is True
        body = said[0].body
        assert "stops recording what you say" in body
        assert "keeps recording what the machine and the rest of the house" in body
        assert "Life safety still reaches" in body

    def test_the_second_handover_does_not_repeat_the_statement(self):
        client = self._fronting()
        client.post("/api/guest/private/assign", json={"source_id": "webcam:desk"})
        client.post("/api/guest/private/assign", json={"source_id": "mic:local:study"})

        said = [e for e in get_event_bus().get_recent() if e.data.get("state") == "private"]
        assert [e.data["first"] for e in said] == [True, False]

    def test_taking_a_source_back_leaves_the_guest_fronting(self):
        client = self._fronting()
        client.post("/api/guest/private/assign", json={"source_id": "webcam:desk"})
        resp = client.post("/api/guest/private/release", json={"source_id": "webcam:desk"})
        assert resp.status_code == 200
        assert resp.json()["private_sources"] == {}
        assert private_sources.active() is False
        assert guest.current_guest() is not None

    def test_the_status_route_reports_what_is_handed_over(self):
        client = self._fronting()
        client.post("/api/guest/private/assign", json={"source_id": "webcam:desk"})
        body = client.get("/api/guest").json()
        assert body["private_sources"] == {"webcam:desk": "guest"}

    def test_with_no_guest_there_are_never_private_sources(self):
        body = TestClient(_app()).get("/api/guest").json()
        assert body["fronting"] is None
        assert body["private_sources"] == {}

    def test_the_catalogue_lists_sources_across_the_senses(self, monkeypatch):
        """One list, because a private mode that gates one sense and not
        another is worse than none."""
        from halbert_core.vision import sources as vs

        monkeypatch.setattr(vs, "list_sources", lambda **k: [
            vs.VisionSource(id="webcam:desk", label="Desk", kind="webcam", native="0", enabled=True),
            vs.VisionSource(id="webcam:off", label="Off", kind="webcam", native="1", enabled=False),
        ])
        client = self._fronting()
        client.post("/api/guest/private/assign", json={"source_id": "webcam:desk"})

        entries = {e["id"]: e for e in client.get("/api/guest/private/sources").json()["sources"]}
        assert entries["webcam:desk"]["owner"] == "guest"
        assert "webcam:off" not in entries          # disabled is not offerable
        assert "screen:active_window" in entries    # the watcher's own id is
