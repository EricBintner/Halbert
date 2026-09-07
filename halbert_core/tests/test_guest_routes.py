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


class TestTheVerb:
    """N5. "Be Marnie" — a name, not a URL, a persona id and a token."""

    @pytest.fixture(autouse=True)
    def _homes(self, tmp_path, monkeypatch):
        import halbert_core.utils.platform as plat
        monkeypatch.setattr(plat, "get_config_dir", lambda: tmp_path)
        yield tmp_path

    @staticmethod
    def _catalogue(monkeypatch, personas, unreachable=()):
        from halbert_core.persona import guest_homes
        monkeypatch.setattr(
            guest_homes, "available_personas",
            lambda *a, **k: {"personas": list(personas), "unreachable": list(unreachable)})

    def test_a_home_is_remembered_without_its_token(self):
        client = TestClient(_app())
        r = client.post("/api/guest/homes",
                        json={"base_url": "http://h2.lan:8002", "label": "H2", "token": "secret"})
        assert r.status_code == 200
        homes = client.get("/api/guest/homes").json()["homes"]
        assert homes == [{"base_url": "http://h2.lan:8002", "label": "H2", "profile": "default"}]
        assert "secret" not in str(homes)

    def test_a_home_that_is_not_an_http_url_is_refused(self):
        client = TestClient(_app())
        assert client.post("/api/guest/homes", json={"base_url": "h2.lan"}).status_code == 400

    def test_re_adding_a_home_replaces_it_rather_than_duplicating(self):
        client = TestClient(_app())
        client.post("/api/guest/homes", json={"base_url": "http://h2.lan:8002", "label": "old"})
        client.post("/api/guest/homes", json={"base_url": "http://h2.lan:8002/", "label": "new"})
        homes = client.get("/api/guest/homes").json()["homes"]
        assert [h["label"] for h in homes] == ["new"]

    def test_being_a_name_wears_it(self, monkeypatch):
        self._catalogue(monkeypatch, [
            {"persona_id": "marnie-7", "name": "Marnie", "home_label": "H2",
             "base_url": "http://h2.lan:8002"},
        ])
        monkeypatch.setattr(
            sibling, "default_transport",
            lambda method, url, body, headers: (200, {"id": "marnie-7", "name": "Marnie"}))

        resp = TestClient(_app()).post("/api/guest/become", json={"name": "marnie"})
        assert resp.status_code == 200, resp.text
        assert resp.json()["session"]["name"] == "Marnie"

    def test_a_name_nobody_has_says_so_and_names_the_homes_that_did_not_answer(self, monkeypatch):
        self._catalogue(monkeypatch, [], [{"home": "H2", "error": "timeout"}])
        resp = TestClient(_app()).post("/api/guest/become", json={"name": "Marnie"})
        assert resp.status_code == 404
        assert "H2" in resp.json()["detail"]

    def test_a_name_in_two_homes_asks_which_rather_than_guessing(self, monkeypatch):
        self._catalogue(monkeypatch, [
            {"persona_id": "a", "name": "Marnie", "home_label": "H2", "base_url": "http://a:1"},
            {"persona_id": "b", "name": "Marnie", "home_label": "The study", "base_url": "http://b:1"},
        ])
        resp = TestClient(_app()).post("/api/guest/become", json={"name": "Marnie"})
        assert resp.status_code == 409
        assert "The study" in resp.json()["detail"]

    def test_naming_the_home_settles_it(self, monkeypatch):
        self._catalogue(monkeypatch, [
            {"persona_id": "a", "name": "Marnie", "home_label": "H2", "base_url": "http://a:1"},
            {"persona_id": "b", "name": "Marnie", "home_label": "The study", "base_url": "http://b:1"},
        ])
        monkeypatch.setattr(
            sibling, "default_transport",
            lambda method, url, body, headers: (200, {"id": "b", "name": "Marnie"}))
        resp = TestClient(_app()).post(
            "/api/guest/become", json={"name": "Marnie", "base_url": "http://b:1"})
        assert resp.status_code == 200, resp.text

    def test_one_sleeping_home_does_not_hide_the_others(self, tmp_path, monkeypatch):
        """Reported per home, not raised: "be Marnie" should still work when
        the other house is asleep."""
        from halbert_core.persona import guest_homes

        guest_homes.add_home("http://awake:1", "Awake", "t1")
        guest_homes.add_home("http://asleep:1", "Asleep", "t2")

        def transport(method, url, body, headers):
            if "asleep" in url:
                raise OSError("connection refused")
            return 200, {"personas": [{"id": "m", "name": "Marnie"}]}

        out = guest_homes.available_personas(transport)
        assert [p["name"] for p in out["personas"]] == ["Marnie"]
        assert [u["home"] for u in out["unreachable"]] == ["Asleep"]

    def test_the_verb_is_local_only(self, monkeypatch):
        self._catalogue(monkeypatch, [
            {"persona_id": "a", "name": "Marnie", "home_label": "H2", "base_url": "http://a:1"}])
        with patch(
            "halbert_core.federation.peer_middleware._is_local_client", return_value=False,
        ):
            resp = TestClient(_app()).post("/api/guest/become", json={"name": "Marnie"})
        assert resp.status_code == 403


def _thread(store, thread_id):
    from halbert_core.agents.conversation import Conversation

    store.save(Conversation(conversation_id=thread_id, title="thread"))


class TestForgetSession:
    """N6. D2 keeps the transcript in normal mode and tags it so one call can
    take it back out; the tag is worth nothing unless something calls this."""

    @pytest.fixture
    def stores(self, tmp_path, monkeypatch):
        from halbert_core.agents import conversation_sqlite as cs
        from halbert_core.continuity import state_store as ss

        conv = cs.SqliteConversationStore(db_path=str(tmp_path / "conv.db"))
        ledger = ss.StateStore(db_path=str(tmp_path / "state.db"))
        monkeypatch.setattr(cs, "SqliteConversationStore", lambda *a, **k: conv)
        monkeypatch.setattr(ss, "StateStore", lambda *a, **k: ledger)
        return conv, ledger

    def _front(self):
        TestClient(_app(_peer())).post(
            "/api/guest/offer", json={"persona": {"name": "Marnie"}, "ttl_seconds": 30})
        return guest.current_guest()

    def test_the_transcript_and_the_ledger_are_both_cleared(self, stores):
        from halbert_core.continuity.ownership import guest_request_id
        from halbert_core.continuity.state_store import ACTOR_AGENT

        conv, ledger = stores
        session = self._front()
        rid = guest_request_id(session)

        _thread(conv, "t1")
        # No metadata passed: append_message applies the guest tag itself
        # while a guest fronts, which is the mechanism D2 relies on.
        conv.append_message("t1", "user", "the thing that was said")
        ledger.record_state("thread:t1", "ran_command:x", "ls",
                            "thread_close", reason="the thing that was said",
                            actor=ACTOR_AGENT, request_id=rid)

        resp = TestClient(_app()).post("/api/guest/forget", json={})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["request_id"] == rid
        assert body["messages_removed"] == 1
        assert body["ledger_rows_redacted"] >= 1

        assert conv.forget_request(rid) == 0            # nothing left to remove
        # The words go; the fact and its timeline stay. What was true and when
        # is not the thing being forgotten.
        current = ledger.why("thread:t1", "ran_command:x").to_dict()["current"]
        assert current["reason"] == "unrecorded"
        assert current["object"] == "ls"

    def test_a_session_that_has_ended_can_still_be_forgotten(self, stores):
        """The session most worth forgetting is usually one that has ended."""
        conv, _ = stores
        session = self._front()
        guest.withdraw(reason="ended_by_user", by="user")

        resp = TestClient(_app()).post(
            "/api/guest/forget", json={"session_id": session.id})
        assert resp.status_code == 200
        assert resp.json()["session_id"] == session.id

    def test_forgetting_nothing_in_particular_with_no_guest_asks_which(self, stores):
        resp = TestClient(_app()).post("/api/guest/forget", json={})
        assert resp.status_code == 409

    def test_forgetting_is_local_only(self, stores):
        self._front()
        with patch(
            "halbert_core.federation.peer_middleware._is_local_client", return_value=False,
        ):
            assert TestClient(_app()).post("/api/guest/forget", json={}).status_code == 403

    def test_a_second_call_removes_nothing_more(self, stores):
        conv, _ = stores
        self._front()
        _thread(conv, "t1")
        conv.append_message("t1", "user", "x")

        client = TestClient(_app())
        assert client.post("/api/guest/forget", json={}).json()["messages_removed"] == 1
        assert client.post("/api/guest/forget", json={}).json()["messages_removed"] == 0

    def test_forget_also_takes_the_title_and_the_receipt(self, stores):
        """The transcript is not the only copy. The thread title is the first
        sixty characters of what the user said, and the stored receipt is a
        searchable summary of it — neither reached by forget_request."""
        conv, _ = stores
        self._front()
        _thread(conv, "t1")
        conv.append_message("t1", "user", "the thing that was said")
        conv.upsert_receipt("t1", "the thing that was said", "a summary of it")

        resp = TestClient(_app()).post("/api/guest/forget", json={})
        assert resp.status_code == 200, resp.text
        assert resp.json()["threads_blanked"] == 1

        thread = conv.get_thread("t1")
        assert thread is not None                    # the thread stays
        assert "the thing that was said" not in (thread.get("title") or "")
        assert (thread.get("receipt") or "") == ""

    def test_a_half_done_erasure_does_not_report_success(self, stores, monkeypatch):
        """"ok" on a partial erase is the worst possible answer: the user
        believes the words are gone and stops looking."""
        from halbert_core.continuity import state_store as ss

        self._front()

        class _Broken:
            def redact_request(self, *a, **k):
                raise RuntimeError("database is locked")

        monkeypatch.setattr(ss, "StateStore", lambda *a, **k: _Broken())
        resp = TestClient(_app()).post("/api/guest/forget", json={})
        assert resp.status_code == 500
        assert "ledger" in resp.json()["detail"]


class TestHomeProfiles:
    """N7. The engine is the same in every sibling; only the mount differs, so
    a home records which shape its house speaks rather than getting a second
    client."""

    @pytest.fixture(autouse=True)
    def _homes(self, tmp_path, monkeypatch):
        import halbert_core.utils.platform as plat
        monkeypatch.setattr(plat, "get_config_dir", lambda: tmp_path)

    def test_a_home_behind_a_prefix_asks_the_prefixed_paths(self):
        from halbert_core.persona.guest import GuestHome
        from halbert_core.persona.sibling import SiblingClient

        seen = []

        def transport(method, url, body, headers):
            seen.append(url)
            return 200, {"results": []}

        home = GuestHome(base_url="http://h3:8003", persona_id="franklin")
        SiblingClient(home, transport, profile="h3").memory_search("kites")
        assert seen == ["http://h3:8003/api/blueprint/personas/franklin/memory/search"]

    def test_the_default_profile_is_unchanged(self):
        from halbert_core.persona.guest import GuestHome
        from halbert_core.persona.sibling import SiblingClient

        seen = []

        def transport(method, url, body, headers):
            seen.append(url)
            return 200, {"results": []}

        home = GuestHome(base_url="http://h2:8002", persona_id="marnie-7")
        SiblingClient(home, transport).memory_search("kites")
        assert seen == ["http://h2:8002/api/personas/marnie-7/memory/search"]

    def test_one_prefixed_home_does_not_move_another_homes_paths(self):
        """Per-instance, not class-level: the paths used to be class
        attributes, and assigning to them would have moved every home."""
        from halbert_core.persona.guest import GuestHome
        from halbert_core.persona.sibling import SiblingClient

        SiblingClient(GuestHome(base_url="http://h3:1", persona_id="x"), profile="h3")
        assert SiblingClient.PATH_MEMORY_SEARCH == "/api/personas/{pid}/memory/search"

    def test_an_unknown_profile_is_refused_when_the_home_is_remembered(self):
        client = TestClient(_app())
        resp = client.post("/api/guest/homes",
                           json={"base_url": "http://h3:8003", "profile": "nonsense"})
        assert resp.status_code == 400

    def test_the_profile_survives_the_round_trip(self):
        client = TestClient(_app())
        client.post("/api/guest/homes",
                    json={"base_url": "http://h3:8003", "label": "H3", "profile": "h3"})
        assert client.get("/api/guest/homes").json()["homes"][0]["profile"] == "h3"
