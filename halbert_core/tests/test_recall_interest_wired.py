# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""RECALL-v1 has to reach an actual prompt, and record that it did.

`select_interest` and `render_interest_block` are pure and fully tested, and
until this file they had no caller -- the same shape as A4 shipping dead in
the observation workstream, and as `remember`'s writer reaching for an
accessor that did not exist. Both of those passed their own suites. These
tests assert the wiring.

The injection is recorded to the **event ledger**, which is what makes the
"one per thread per 24 h" rule survive a restart and what gives the
`memory_recalled` chip something to cite. An injection is an event: it
happened, at a time, on a thread.
"""

import time

import pytest

from halbert_core.continuity.interests import Interest, InterestStatus, Origin


def _interest(topic="vintage thinkpads"):
    return Interest(topic=topic, origin=Origin.STATED,
                    reason=f"remember that I collect {topic}",
                    actor="user", status=InterestStatus.ACTIVE)


class _Intake:
    def __init__(self, entities=(), domains=()):
        self.entities = set(entities)
        self.detected_domains = list(domains)
        self.intent = "question"
        self.is_troubleshooting = False
        self.has_error_indicators = False


@pytest.fixture
def machine(tmp_path, monkeypatch):
    """A state machine stub with a real ledger and a stubbed memory store."""
    monkeypatch.setenv("HALOYSIUS_DATA_HOME", str(tmp_path))
    from halbert_core.agents.state_machine import AgentStateMachine
    from halbert_core.continuity.timeline import TimelineStore
    import halbert_core.integrations.cognition_wiring as cw

    timeline = TimelineStore(db_path=str(tmp_path / "t.db"))
    rows = []

    class _Store:
        def list_memories(self):
            return [r.to_persona_memory("halbert") for r in rows]

    monkeypatch.setattr(cw, "get_timeline_store", lambda: timeline)
    monkeypatch.setattr(cw, "get_persona_memory_store", lambda: _Store())

    m = AgentStateMachine.__new__(AgentStateMachine)
    m._identity_block = lambda modality: "I am this machine."
    m._composed_prompt_block = lambda: ""
    m._continuity_tail = lambda: ""
    m._world_observations = lambda: []
    m.ctx = type("C", (), {
        "conversation_history": [], "thread_receipt_block": "",
        "defanged_query": None, "user_query": "", "model_override": None,
        "tier_override": None, "intake": _Intake(entities={"thinkpads"}),
        "thread_id": "thread-1", "session_id": "s1",
    })()
    return m, rows, timeline


class TestTheBlockReachesThePrompt:

    def test_an_on_topic_turn_carries_the_interest(self, machine):
        m, rows, _ = machine
        rows.append(_interest())
        head = m._build_messages("what laptop should I buy?")[0]["content"]
        assert "interested in vintage thinkpads" in head

    def test_an_off_topic_turn_carries_nothing(self, machine):
        m, rows, _ = machine
        rows.append(_interest("sailing"))
        head = m._build_messages("what laptop should I buy?")[0]["content"]
        assert "sailing" not in head

    def test_no_interests_leaves_the_prompt_unchanged(self, machine):
        m, rows, _ = machine
        # Asserted as "no interest block", not as an exact string: the head
        # also carries the SK-2 cache boundary marker, which belongs there.
        head = m._build_messages("hello")[0]["content"]
        assert "interested in" not in head
        assert head.endswith("hello")

    def test_both_llm_calls_of_a_turn_see_the_same_block(self, machine):
        # _build_messages runs once per call site, twice in a normal turn.
        # A second selection could differ, and a model that planned with a
        # fact and answered without it has no way to notice.
        m, rows, _ = machine
        rows.append(_interest())
        first = m._build_messages("q")[0]["content"]
        rows.append(_interest("thinkpad batteries"))
        assert m._build_messages("q")[0]["content"] == first


class TestTheInjectionIsRecorded:

    def test_it_lands_in_the_event_ledger(self, machine):
        m, rows, timeline = machine
        rows.append(_interest())
        m._build_messages("q")
        recorded = timeline.query(event_type="interest_recalled")
        assert len(recorded) == 1
        assert recorded[0]["entity_id"] == "thread-1"

    def test_it_is_recorded_once_per_turn_not_once_per_call(self, machine):
        m, rows, timeline = machine
        rows.append(_interest())
        m._build_messages("q")
        m._build_messages("q")
        assert len(timeline.query(event_type="interest_recalled")) == 1

    def test_nothing_is_recorded_when_nothing_was_injected(self, machine):
        m, rows, timeline = machine
        rows.append(_interest("sailing"))
        m._build_messages("q")
        assert timeline.query(event_type="interest_recalled") == []


class TestTheCooldownSurvivesARestart:
    """The 24 h rule is read from the ledger, not from process memory."""

    def test_a_recent_injection_on_this_thread_suppresses(self, machine):
        m, rows, timeline = machine
        rows.append(_interest())
        from halbert_core.continuity.timeline import TimelineEvent
        timeline.record(TimelineEvent(timestamp=time.time() - 60,
                                      event_type="interest_recalled",
                                      source="recall", entity_id="thread-1",
                                      title="earlier injection"))
        head = m._build_messages("q")[0]["content"]
        assert "thinkpads" not in head

    def test_an_injection_on_another_thread_does_not(self, machine):
        m, rows, timeline = machine
        rows.append(_interest())
        from halbert_core.continuity.timeline import TimelineEvent
        timeline.record(TimelineEvent(timestamp=time.time() - 60,
                                      event_type="interest_recalled",
                                      source="recall", entity_id="another-thread",
                                      title="elsewhere"))
        assert "thinkpads" in m._build_messages("q")[0]["content"]

    def test_an_old_injection_does_not(self, machine):
        m, rows, timeline = machine
        rows.append(_interest())
        from halbert_core.continuity.timeline import TimelineEvent
        timeline.record(TimelineEvent(timestamp=time.time() - 25 * 3600,
                                      event_type="interest_recalled",
                                      source="recall", entity_id="thread-1",
                                      title="yesterday"))
        assert "thinkpads" in m._build_messages("q")[0]["content"]


class TestItNeverBreaksATurn:

    def test_a_broken_memory_store_costs_the_colour_not_the_answer(self, machine, monkeypatch):
        m, rows, _ = machine
        import halbert_core.integrations.cognition_wiring as cw

        class _Broken:
            def list_memories(self):
                raise RuntimeError("gone")

        monkeypatch.setattr(cw, "get_persona_memory_store", lambda: _Broken())
        head = m._build_messages("q")[0]["content"]
        assert "interested in" not in head
        assert head.endswith("q"), "the turn still gets its prompt"

    def test_no_memory_store_at_all_is_fine(self, machine, monkeypatch):
        m, rows, _ = machine
        import halbert_core.integrations.cognition_wiring as cw
        monkeypatch.setattr(cw, "get_persona_memory_store", lambda: None)
        assert "thinkpads" not in m._build_messages("q")[0]["content"]
