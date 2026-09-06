# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The guest's home — where its words go and where its face comes from.

``persona/sibling.py`` is Halbert's client for a paired sibling's per-persona
API: fetch a persona in the engine's ``PersonaConfig`` shape and wear it
(the pull channel, design §7), forward a guest turn to the persona's own
memory (§4.2, so the guest's words never live on Halbert's disk), and
search that memory for the guest's ``recall_guest_memory`` tool (§4.3,
I6: the guest reads what it wrote).

Nothing here talks to a real network: a transport is injected.
"""
from __future__ import annotations

import pytest

from halbert_core.persona import guest, sibling
from halbert_core.persona.guest import GuestHome


@pytest.fixture(autouse=True)
def _fresh():
    guest.reset_for_tests()
    yield
    guest.reset_for_tests()


class FakeTransport:
    """Records every call; answers from a route table."""

    def __init__(self, routes=None, fail=False):
        self.calls = []
        self.routes = routes or {}
        self.fail = fail

    def __call__(self, method, url, body, headers):
        self.calls.append((method, url, body, headers))
        if self.fail:
            raise ConnectionError("home down")
        for (m, suffix), answer in self.routes.items():
            if m == method and url.endswith(suffix):
                return answer
        return 404, {"error": "no route"}


HOME = GuestHome(base_url="http://127.0.0.1:8002", persona_id="marnie-7", token="tkn", label="H2")

FLAT_PERSONA = {
    "id": "marnie-7", "name": "Marnie", "age": 34, "occupation": "gardener",
    "traits": ["warm", "dry"], "communication_style": "short sentences",
    "quirks": ["hums"], "speech_patterns": ["never says 'basically'"],
    "directives": ["Keep it short."], "personality_profile": {"openness": 0.8},
    "archetype_id": None, "background": "Grew up by the sea.", "context": "Evenings.",
    "summary": "Company for the evening.", "lora_enabled": True, "context_window": 50,
}


class TestGuestHome:

    def test_from_payload_keeps_the_address_and_not_much_else(self):
        home = GuestHome.from_payload({"base_url": "http://127.0.0.1:8002/", "persona_id": "marnie-7",
                                       "token": "t", "label": "H2", "extra": 1})
        assert home.base_url == "http://127.0.0.1:8002"      # trailing slash gone
        assert home.persona_id == "marnie-7"
        assert home.token == "t"
        assert home.to_dict() == {"base_url": "http://127.0.0.1:8002", "persona_id": "marnie-7", "label": "H2"}

    def test_only_http_and_https(self):
        for bad in ("ftp://x", "file:///etc/passwd", "127.0.0.1:8002", ""):
            with pytest.raises(guest.GuestValidationError):
                GuestHome.from_payload({"base_url": bad, "persona_id": "p"})

    def test_persona_id_is_required_and_one_line(self):
        with pytest.raises(guest.GuestValidationError):
            GuestHome.from_payload({"base_url": "http://h", "persona_id": ""})
        with pytest.raises(guest.GuestValidationError):
            GuestHome.from_payload({"base_url": "http://h", "persona_id": "a\nb"})


class TestPersonaMapping:

    def test_flat_engine_shape_maps_to_guest_fields_only(self):
        payload = sibling.persona_payload_from_config(FLAT_PERSONA)
        assert set(payload) <= guest.GUEST_PERSONA_FIELDS
        assert payload["name"] == "Marnie"
        assert payload["tone_descriptors"] == ["warm", "dry"]
        assert "short sentences" in payload["speech_patterns"]
        assert "hums" in payload["speech_patterns"]
        assert "never says 'basically'" in payload["speech_patterns"]
        assert payload["directives"] == ["Keep it short."]
        assert payload["personality_profile"] == {"openness": 0.8}
        assert "Grew up by the sea." in payload["scene_context"]
        assert "Evenings." in payload["scene_context"]
        assert payload["purpose"] == "Company for the evening."
        persona, dropped = guest.GuestPersona.from_payload(payload)
        assert dropped == []

    def test_nested_persona_shape_maps_too(self):
        nested = {
            "name": "Marnie",
            "personality": {"traits": ["warm"], "communication_style": "", "quirks": [],
                            "speech_patterns": ["short"], "personality_profile": {}},
            "directives": ["x"], "background": "", "context": "", "custom_prompt": "Be Marnie.",
        }
        payload = sibling.persona_payload_from_config(nested)
        assert payload["tone_descriptors"] == ["warm"]
        assert payload["speech_patterns"] == ["short"]
        assert payload["custom_personality_prompt"] == "Be Marnie."


class TestSiblingClient:

    def test_list_and_fetch(self):
        t = FakeTransport({
            ("GET", "/api/personas"): (200, {"personas": [{"id": "marnie-7", "name": "Marnie"}]}),
            ("GET", "/api/personas/marnie-7"): (200, FLAT_PERSONA),
        })
        client = sibling.SiblingClient(HOME, transport=t)
        assert client.list_personas() == [{"id": "marnie-7", "name": "Marnie"}]
        assert client.fetch_persona()["name"] == "Marnie"
        assert t.calls[0][3].get("Authorization") == "Bearer tkn"

    def test_memory_add_posts_the_v2_shape(self):
        t = FakeTransport({("POST", "/api/personas/marnie-7/memory-v2/memories"): (200, {"success": True})})
        client = sibling.SiblingClient(HOME, transport=t)
        assert client.memory_add("They showed me the garden.", tags=["a", "b"]) is True
        method, url, body, _ = t.calls[0]
        assert body["content"] == "They showed me the garden."
        assert body["type"] == "episodic"
        assert body["tags"] == ["a", "b"]

    def test_memory_search_returns_the_memories(self):
        t = FakeTransport({("POST", "/api/personas/marnie-7/memory/search"): (200, {"memories": [{"content": "garden"}]})})
        client = sibling.SiblingClient(HOME, transport=t)
        assert client.memory_search("garden", k=3) == [{"content": "garden"}]
        assert t.calls[0][2] == {"query": "garden", "k": 3}

    def test_a_dead_home_answers_false_and_empty_never_raises(self):
        client = sibling.SiblingClient(HOME, transport=FakeTransport(fail=True))
        assert client.ping() is False
        assert client.memory_add("x", tags=[]) is False
        assert client.memory_search("x") == []

    def test_ping_is_the_persona_fetch(self):
        t = FakeTransport({("GET", "/api/personas/marnie-7"): (200, FLAT_PERSONA)})
        assert sibling.SiblingClient(HOME, transport=t).ping() is True


class TestForwardTheTurn:

    def _session(self, home=HOME):
        persona, _ = guest.GuestPersona.from_payload({"name": "Marnie"})
        return guest.offer(persona, offered_by="h2-node", offered_by_name="H2", home=home)

    def test_a_turn_becomes_one_memory_at_the_home_tagged_with_the_session(self):
        t = FakeTransport({("POST", "/api/personas/marnie-7/memory-v2/memories"): (200, {"success": True})})
        session = self._session()
        assert sibling.forward_turn(session, "Is the garage shut?", "It is.", transport=t) is True
        body = t.calls[0][2]
        assert "Is the garage shut?" in body["content"] and "It is." in body["content"]
        assert body["content"].startswith("User:")
        assert "Marnie:" in body["content"]
        assert set(body["tags"]) >= {"halbert-guest-session", session.id, "turn"}

    def test_the_content_fits_the_homes_limit(self):
        t = FakeTransport({("POST", "/api/personas/marnie-7/memory-v2/memories"): (200, {})})
        session = self._session()
        sibling.forward_turn(session, "x" * 3000, "y" * 3000, transport=t)
        assert len(t.calls[0][2]["content"]) <= sibling.HOME_MEMORY_CHARS

    def test_no_home_means_nothing_is_forwarded_and_the_caller_is_told(self):
        session = self._session(home=None)
        t = FakeTransport()
        assert sibling.forward_turn(session, "a", "b", transport=t) is False
        assert t.calls == []

    def test_a_dead_home_is_false_not_an_exception(self):
        session = self._session()
        assert sibling.forward_turn(session, "a", "b", transport=FakeTransport(fail=True)) is False

    def test_an_observation_is_tagged_with_its_source(self):
        t = FakeTransport({("POST", "/api/personas/marnie-7/memory-v2/memories"): (200, {})})
        session = self._session()
        assert sibling.forward_observation(session, "A person on the patio.", "frigate:patio", transport=t) is True
        assert set(t.calls[0][2]["tags"]) >= {"halbert-guest-session", session.id, "observation", "frigate:patio"}


class TestInstallFromHome:

    def test_fetches_maps_and_wears(self):
        t = FakeTransport({("GET", "/api/personas/marnie-7"): (200, FLAT_PERSONA)})
        session, dropped = sibling.install_from_home(HOME, offered_by="h2-node", offered_by_name="H2", transport=t)
        assert guest.current_guest() is session
        assert session.persona.name == "Marnie"
        assert session.home == HOME
        assert dropped == []

    def test_an_unreachable_home_installs_nothing(self):
        with pytest.raises(sibling.HomeUnreachable):
            sibling.install_from_home(HOME, offered_by="h2-node", transport=FakeTransport(fail=True))
        assert guest.current_guest() is None

    def test_a_pulled_session_is_kept_alive_by_the_home_not_a_heartbeat(self):
        """Nobody on the other side is beating: the deadline is renewed by a
        successful ping, and a dead home ends the session."""
        t = FakeTransport({("GET", "/api/personas/marnie-7"): (200, FLAT_PERSONA)})
        session, _ = sibling.install_from_home(HOME, offered_by="h2-node", transport=t, ttl_seconds=30.0)
        pings_before = len(t.calls)
        assert guest.current_guest(now=session.deadline + 1.0) is session      # renewed by a ping
        assert len(t.calls) == pings_before + 1
        t.fail = True
        assert guest.current_guest(now=session.deadline + 1.0) is None         # home gone
        assert session.end_reason == "home_unreachable"


class TestKeepalive:

    def test_keepalive_renews_and_is_asked_once_per_window(self):
        asks = []
        persona, _ = guest.GuestPersona.from_payload({"name": "Marnie"})
        session = guest.offer(persona, offered_by="h2-node", ttl_seconds=10.0, now=0.0,
                              keepalive=lambda: asks.append(1) or True)
        assert guest.current_guest(now=5.0) is session
        assert asks == []
        assert guest.current_guest(now=11.0) is session
        assert len(asks) == 1
        assert guest.current_guest(now=12.0) is session      # inside the renewed window
        assert len(asks) == 1
        assert guest.current_guest(now=22.0) is session
        assert len(asks) == 2

    def test_a_failing_keepalive_ends_the_session(self):
        heard = []
        guest.on_session_end(lambda s: heard.append(s.end_reason))
        persona, _ = guest.GuestPersona.from_payload({"name": "Marnie"})
        session = guest.offer(persona, offered_by="h2-node", ttl_seconds=10.0, now=0.0, keepalive=lambda: False)
        assert guest.current_guest(now=11.0) is None
        assert session.end_reason == "home_unreachable"
        assert heard == ["home_unreachable"]

    def test_a_keepalive_that_raises_counts_as_failed(self):
        def boom():
            raise RuntimeError("no")
        persona, _ = guest.GuestPersona.from_payload({"name": "Marnie"})
        session = guest.offer(persona, offered_by="h2-node", ttl_seconds=10.0, now=0.0, keepalive=boom)
        assert guest.current_guest(now=11.0) is None
        assert session.end_reason == "home_unreachable"

    def test_the_home_is_shown_without_its_token(self):
        persona, _ = guest.GuestPersona.from_payload({"name": "Marnie"})
        session = guest.offer(persona, offered_by="h2-node", home=HOME)
        d = session.to_dict()
        assert d["home"] == {"base_url": "http://127.0.0.1:8002", "persona_id": "marnie-7", "label": "H2"}
        assert "tkn" not in str(d)
