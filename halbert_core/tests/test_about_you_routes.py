# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The Settings surface: /api/memory/about-you.

The path deliberately does not say "observations" -- that word now means the
world stream (the event ledger), and a second meaning on a user-facing path
is how the two get confused by whoever reads it next.

This is where `forget_interest` and `resume_interest` finally get a caller.
Both were complete and tested and invoked by nothing, which is the shape this
workstream has had to correct three times.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from halbert_core.continuity.interests import Interest, InterestStatus, Origin


def _stated(topic="vintage thinkpads", **kw):
    kw.setdefault("reason", f"remember that I collect {topic}")
    kw.setdefault("actor", "user")
    return Interest(topic=topic, origin=Origin.STATED, **kw)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HALOYSIUS_DATA_HOME", str(tmp_path))
    from haloysius.memory_v2.observation_store import ObservationStore
    from haloysius.memory_v2.store import PersonaMemoryStore
    import halbert_core.integrations.cognition_wiring as cw
    from halbert_core.dashboard.routes import memory as memory_routes

    mem = PersonaMemoryStore("routes-test")
    obs = ObservationStore("routes-test")
    monkeypatch.setattr(cw, "get_persona_memory_store", lambda: mem)
    monkeypatch.setattr(cw, "get_observation_store", lambda: obs, raising=False)

    interest = _stated()
    _op, _r, memory_id = mem.smart_add(interest.to_persona_memory("routes-test"))
    obs.save(category="preference", content=interest.content,
             source_memory_id=memory_id)

    app = FastAPI()
    app.include_router(memory_routes.router, prefix="/api/memory")
    return TestClient(app), mem, obs, memory_id


class TestTheList:

    def test_it_lists_what_is_remembered(self, client):
        c, *_ = client
        body = c.get("/api/memory/about-you").json()
        assert [r["topic"] for r in body["items"]] == ["vintage thinkpads"]

    def test_each_row_says_how_it_was_learned(self, client):
        c, *_ = client
        row = c.get("/api/memory/about-you").json()["items"][0]
        assert row["learned"]
        assert row["reason"]

    def test_the_response_carries_the_reach_statement(self, client):
        # A person deciding whether to trust "Forget" needs to know what it
        # does not touch, on the same screen as the button.
        c, *_ = client
        body = c.get("/api/memory/about-you").json()
        assert body["limits"]


class TestStopUsing:

    def test_it_stops_the_interest_being_used(self, client):
        c, mem, obs, memory_id = client
        r = c.post(f"/api/memory/about-you/{memory_id}/stop-using")
        assert r.status_code == 200
        assert r.json()["complete"] is True
        assert c.get("/api/memory/about-you").json()["items"] == []

    def test_it_appears_under_show_forgotten(self, client):
        c, mem, obs, memory_id = client
        c.post(f"/api/memory/about-you/{memory_id}/stop-using")
        body = c.get("/api/memory/about-you?include_forgotten=true").json()
        assert [r["topic"] for r in body["items"]] == ["vintage thinkpads"]
        assert body["items"][0]["forgotten"] is True

    def test_remember_again_restores_it(self, client):
        c, mem, obs, memory_id = client
        c.post(f"/api/memory/about-you/{memory_id}/stop-using")
        r = c.post(f"/api/memory/about-you/{memory_id}/remember-again")
        assert r.status_code == 200
        assert [x["topic"] for x in c.get("/api/memory/about-you").json()["items"]] \
            == ["vintage thinkpads"]


class TestForget:

    def test_it_erases_and_reports_each_plane(self, client):
        c, mem, obs, memory_id = client
        body = c.post(f"/api/memory/about-you/{memory_id}/forget").json()
        assert body["memory"] is True
        assert body["observations"] == 1
        assert body["complete"] is True
        assert memory_id not in mem._memories

    def test_a_forgotten_row_does_not_come_back_under_show_forgotten(self, client):
        # "Forget" is not "stop using": there is nothing left to show.
        c, mem, obs, memory_id = client
        c.post(f"/api/memory/about-you/{memory_id}/forget")
        body = c.get("/api/memory/about-you?include_forgotten=true").json()
        assert body["items"] == []

    def test_an_unknown_id_reports_incomplete_rather_than_done(self, client):
        c, *_ = client
        body = c.post("/api/memory/about-you/no-such-memory/forget").json()
        assert body["complete"] is False

    def test_the_report_states_what_it_could_not_reach(self, client):
        c, mem, obs, memory_id = client
        body = c.post(f"/api/memory/about-you/{memory_id}/forget").json()
        assert body["limits"]


class TestThePathDoesNotSayObservations:

    def test_no_route_uses_the_word(self):
        from halbert_core.dashboard.routes import memory as memory_routes

        paths = [r.path for r in memory_routes.router.routes]
        about = [p for p in paths if "about-you" in p]
        assert about, "the surface must exist"
        assert not [p for p in about if "observation" in p.lower()]


# ===========================================================================
# The other door: confirming from the list rather than from the conversation.
# ===========================================================================


@pytest.fixture
def noticed(tmp_path, monkeypatch):
    """One candidate nobody has answered yet."""
    monkeypatch.setenv("HALOYSIUS_DATA_HOME", str(tmp_path))
    from haloysius.memory_v2.observation_store import ObservationStore
    from haloysius.memory_v2.store import PersonaMemoryStore
    import halbert_core.integrations.cognition_wiring as cw
    from halbert_core.dashboard.routes import memory as memory_routes

    mem = PersonaMemoryStore("noticed-test")
    obs = ObservationStore("noticed-test")
    monkeypatch.setattr(cw, "get_persona_memory_store", lambda: mem)
    monkeypatch.setattr(cw, "get_observation_store", lambda: obs)

    candidate = Interest(
        topic="samba", origin=Origin.INFERRED, status=InterestStatus.CANDIDATE,
        reason="appeared on 4 days in 30 across 5 threads",
        evidence={"days": 4, "threads": ["t1", "t2", "t3", "t4", "t5"],
                  "window_days": 30},
    )
    _op, _r, memory_id = mem.smart_add(candidate.to_persona_memory("noticed-test"))

    app = FastAPI()
    app.include_router(memory_routes.router, prefix="/api/memory")
    return TestClient(app), mem, obs, memory_id


class TestWhatWasNoticed:

    def test_it_is_not_on_the_remembered_list(self, noticed):
        # Nobody confirmed it, so calling it "something I remember about
        # you" would claim more than the system is entitled to.
        c, *_ = noticed
        assert c.get("/api/memory/about-you").json()["items"] == []

    def test_it_is_on_its_own_list(self, noticed):
        c, *_ = noticed
        body = c.get("/api/memory/about-you/noticed").json()
        assert [r["topic"] for r in body["items"]] == ["samba"]

    def test_the_row_carries_the_arithmetic_that_produced_it(self, noticed):
        # "Why do you think that?" has an exact answer here.
        c, *_ = noticed
        row = c.get("/api/memory/about-you/noticed").json()["items"][0]
        assert row["days"] == 4
        assert row["conversations"] == 5
        assert row["noticed"] == "appeared on 4 days in 30 across 5 threads"


class TestConfirmingFromTheList:

    def test_yes_moves_it_to_the_remembered_list(self, noticed):
        c, mem, obs, memory_id = noticed
        report = c.post(f"/api/memory/about-you/{memory_id}/remember-this").json()
        assert report["complete"] is True, report["errors"]
        assert [r["topic"] for r in c.get("/api/memory/about-you").json()["items"]] == ["samba"]
        assert c.get("/api/memory/about-you/noticed").json()["items"] == []

    def test_yes_is_what_gives_it_an_index_row(self, noticed):
        # A candidate never mirrors. This is the moment the index gains it,
        # and it is the moment a person said yes.
        c, mem, obs, memory_id = noticed
        assert obs.search("samba", limit=5) == []
        c.post(f"/api/memory/about-you/{memory_id}/remember-this")
        assert [o.source_memory_id for o in obs.search("samba", limit=5)] == [memory_id]

    def test_the_reason_names_the_door_it_came_through(self, noticed):
        """MEM-06 takes a human utterance or a self-naming rule. A button in
        a surface that says what it does is the second kind."""
        c, mem, obs, memory_id = noticed
        c.post(f"/api/memory/about-you/{memory_id}/remember-this")
        row = c.get("/api/memory/about-you").json()["items"][0]
        assert "Settings" in row["reason"]

    def test_the_arithmetic_is_kept_beside_it(self, noticed):
        # "How did you know to ask?" is a question the person is entitled to
        # an answer to, after they have said yes as much as before.
        c, mem, obs, memory_id = noticed
        c.post(f"/api/memory/about-you/{memory_id}/remember-this")
        stored = Interest.from_persona_memory(mem.get(memory_id))
        assert stored.evidence["proposed_reason"] == (
            "appeared on 4 days in 30 across 5 threads"
        )

    def test_it_cannot_be_confirmed_twice(self, noticed):
        c, mem, obs, memory_id = noticed
        c.post(f"/api/memory/about-you/{memory_id}/remember-this")
        again = c.post(f"/api/memory/about-you/{memory_id}/remember-this").json()
        assert again["complete"] is False
        assert "not an outstanding question" in " ".join(again["errors"])

    def test_something_already_remembered_cannot_be_confirmed(self, noticed):
        c, mem, obs, _cand = noticed
        stated = Interest(topic="thinkpads", origin=Origin.STATED, actor="user",
                          reason="remember that I collect thinkpads")
        _op, _r, mid = mem.smart_add(stated.to_persona_memory("noticed-test"))
        body = c.post(f"/api/memory/about-you/{mid}/remember-this").json()
        assert body["complete"] is False


class TestDecliningFromTheList:

    def test_no_takes_it_off_both_lists(self, noticed):
        c, mem, obs, memory_id = noticed
        assert c.post(f"/api/memory/about-you/{memory_id}/not-interested").json()["complete"] is True
        assert c.get("/api/memory/about-you/noticed").json()["items"] == []
        assert c.get("/api/memory/about-you").json()["items"] == []

    def test_no_records_no_refusal_of_its_own(self, noticed):
        """A person who declines has said nothing that needs storing. What
        changes is the candidate's status, not a new row about them."""
        c, mem, obs, memory_id = noticed
        c.post(f"/api/memory/about-you/{memory_id}/not-interested")
        assert len(mem.list_memories(include_deleted=True)) == 1

    def test_declining_is_not_erasing(self, noticed):
        # Retired, not deleted, so the arithmetic cannot immediately
        # re-propose it off the same threads.
        c, mem, obs, memory_id = noticed
        c.post(f"/api/memory/about-you/{memory_id}/not-interested")
        assert mem.get(memory_id) is not None
