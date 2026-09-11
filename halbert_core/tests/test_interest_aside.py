# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The one confirmation aside, and every fence around it.

This is the single exception to "never volunteer a fact about the person",
so the tests that matter are the ones about when it does NOT happen: at the
wrong dial, twice, on a diagnostic turn, on a turn that already recalled
something, and for a candidate nobody proposed.
"""

import pytest

from halbert_core.continuity.interest_aside import (
    ASIDE_COOLDOWN_SECONDS,
    DIALS_THAT_ASK,
    OFFERED_KEY,
    render_aside,
    select_candidate,
    was_offered,
)
from halbert_core.continuity.interests import Interest, InterestStatus, Origin

NOW = 1_780_000_000.0


class _Signals:
    def __init__(self, **kw):
        self.intent = kw.get("intent", "question")
        self.is_troubleshooting = kw.get("is_troubleshooting", False)
        self.has_error_indicators = kw.get("has_error_indicators", False)
        self.entities = kw.get("entities", set())
        self.detected_domains = kw.get("detected_domains", [])


def _candidate(topic="samba", days=4, threads=5, offered=False):
    evidence = {
        "days": days,
        "threads": [f"t{n}" for n in range(threads)],
        "window_days": 30,
    }
    if offered:
        evidence[OFFERED_KEY] = NOW - 3600
    return Interest(
        topic=topic, origin=Origin.INFERRED, status=InterestStatus.CANDIDATE,
        reason=f"appeared on {days} days in 30 across {threads} threads",
        evidence=evidence,
    )


class TestWhenItAsks:

    def test_a_pending_candidate_on_a_quiet_turn(self):
        chosen = select_candidate([_candidate()], _Signals(), now=NOW)
        assert chosen is not None and chosen.topic == "samba"

    def test_relevance_to_the_turn_is_not_required(self):
        """Unlike recall. The question is about a month of conversations,
        not about this sentence -- and waiting for the subject to come up
        would mean asking exactly when the person is busy with it."""
        chosen = select_candidate([_candidate()], _Signals(entities={"printers"}), now=NOW)
        assert chosen is not None

    def test_the_strongest_evidence_is_chosen(self):
        weak = _candidate("printers", days=3, threads=3)
        strong = _candidate("samba", days=6, threads=4)
        chosen = select_candidate([weak, strong], _Signals(), now=NOW)
        assert chosen.topic == "samba"


class TestWhenItDoesNot:

    def test_never_at_the_dial_off(self):
        assert select_candidate([_candidate()], _Signals(), dial="off", now=NOW) is None

    def test_never_at_quiet(self):
        """Quiet is list-only. A person who turned the dial down asked for
        fewer interruptions, and an aside is an interruption however short."""
        assert select_candidate([_candidate()], _Signals(), dial="quiet", now=NOW) is None
        assert "quiet" not in DIALS_THAT_ASK

    def test_it_does_ask_at_balanced_and_assertive(self):
        for dial in ("balanced", "assertive"):
            assert select_candidate([_candidate()], _Signals(), dial=dial, now=NOW)

    def test_not_on_a_diagnostic_turn(self):
        signals = _Signals(intent="troubleshooting")
        assert select_candidate([_candidate()], signals, now=NOW) is None

    def test_not_while_a_confirmation_is_pending(self):
        assert select_candidate(
            [_candidate()], _Signals(), required_confirmation=True, now=NOW
        ) is None

    def test_not_twice_on_the_same_thread_in_a_day(self):
        assert select_candidate(
            [_candidate()], _Signals(), last_aside_at=NOW - 60, now=NOW
        ) is None
        assert select_candidate(
            [_candidate()], _Signals(),
            last_aside_at=NOW - ASIDE_COOLDOWN_SECONDS - 60, now=NOW,
        ) is not None

    def test_never_twice_for_the_same_candidate(self):
        """Once, ever. A second ask is the machine disagreeing with a
        person's silence, and silence is an answer."""
        assert select_candidate([_candidate(offered=True)], _Signals(), now=NOW) is None

    def test_not_for_something_already_active(self):
        active = Interest(topic="zfs", origin=Origin.STATED, actor="user",
                          reason="remember that I work on zfs")
        assert select_candidate([active], _Signals(), now=NOW) is None

    def test_not_for_something_retracted(self):
        stopped = _candidate()
        stopped.status = InterestStatus.FORGET_REQUESTED
        assert select_candidate([stopped], _Signals(), now=NOW) is None

    def test_unreadable_evidence_counts_as_already_asked(self):
        # Not asking is the recoverable error. Asking twice is not.
        class _Broken:
            status = InterestStatus.CANDIDATE
            origin = Origin.INFERRED
            topic = "samba"

            @property
            def evidence(self):
                raise RuntimeError("no")

        assert was_offered(_Broken()) is True
        assert select_candidate([_Broken()], _Signals(), now=NOW) is None

    def test_no_rows_and_no_signals_are_both_fine(self):
        assert select_candidate([], _Signals(), now=NOW) is None
        assert select_candidate(None, None, now=NOW) is None


class TestHowItIsPhrased:

    def test_it_names_the_evidence(self):
        block = render_aside(_candidate(days=4, threads=5))
        assert "4 separate days" in block
        assert "5 conversations" in block

    def test_it_asks_about_the_work_and_forbids_the_other_phrasing(self):
        """"samba has come up on four days" is checkable. "you seem to be
        into samba" is a claim about who someone is -- the surveillance
        reading in a friendly voice."""
        block = render_aside(_candidate())
        assert "about the work" in block
        assert "never" in block and "about them" in block

    def test_it_tells_the_model_to_answer_first(self):
        assert "Answer the person's actual question first" in render_aside(_candidate())

    def test_it_says_to_drop_it_on_bad_news(self):
        assert "bad news" in render_aside(_candidate())

    def test_it_forbids_rephrasing(self):
        assert "never rephrase" in render_aside(_candidate())

    def test_the_topic_is_redacted_and_flattened(self):
        messy = _candidate("samba\n\n   shares")
        assert "samba shares" in render_aside(messy)


# ===========================================================================
# The inferred loop, end to end, with nothing stubbed between tool and disk.
# ===========================================================================


SAID_YES = "yes, remember that"


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setenv("HALOYSIUS_DATA_HOME", str(tmp_path))

    from haloysius.memory_v2.observation_store import ObservationStore
    from haloysius.memory_v2.store import PersonaMemoryStore
    import halbert_core.integrations.cognition_wiring as cw
    from halbert_core.continuity.provenance import current_user_message
    from halbert_core.tools.executor import current_speaker_role

    memory = PersonaMemoryStore("aside")
    observations = ObservationStore("aside")
    monkeypatch.setattr(cw, "get_persona_memory_store", lambda: memory)
    monkeypatch.setattr(cw, "get_observation_store", lambda: observations)

    tokens = [
        (current_user_message, current_user_message.set(SAID_YES)),
        (current_speaker_role, current_speaker_role.set("admin")),
    ]

    class World:
        pass

    World.memory = memory
    World.observations = observations

    def rows():
        return [
            i for i in (Interest.from_persona_memory(m)
                        for m in memory.list_memories()) if i is not None
        ]

    World.rows = staticmethod(rows)
    yield World

    for var, token in reversed(tokens):
        try:
            var.reset(token)
        except ValueError:
            var.set(None)


def _propose(world, topic="samba"):
    DAY = 24 * 3600
    threads = [
        {"thread_id": f"t{n}", "updated_at": NOW - n * 3 * DAY,
         "entities_json": [topic], "topic_domains": [], "turn_count": 4}
        for n in (1, 2, 3)
    ]

    class _Threads:
        def list_threads(self, **kw):
            return threads

    from halbert_core.continuity.consolidation import Consolidator

    return Consolidator(_Threads(), None, world.memory).propose_interests(now=NOW)


class TestTheInferredLoop:

    @pytest.mark.asyncio
    async def test_propose_ask_confirm_recall(self, world):
        from halbert_core.continuity.recall_interest import select_interest
        from halbert_core.tools.confirm_interest import confirm_interest

        # -- 1. the arithmetic proposes ---------------------------------
        assert _propose(world) == 1
        row = world.rows()[0]
        assert row.status is InterestStatus.CANDIDATE

        # -- 2. nothing about it reaches a turn yet ---------------------
        signals = _Signals(entities={"samba"})
        assert select_interest(world.rows(), signals) is None
        assert world.observations.search("samba", limit=5) == []

        # -- 3. but it may be asked about, once -------------------------
        assert select_candidate(world.rows(), signals, now=NOW) is not None

        # -- 4. the person says yes -------------------------------------
        answer = await confirm_interest({"topic": "samba"})
        assert answer == 'Recorded: "User is interested in samba"'

        confirmed = world.rows()[0]
        assert confirmed.status is InterestStatus.ACTIVE
        assert confirmed.origin is Origin.INFERRED_CONFIRMED

        # -- 5. their words are the reason, the arithmetic is the evidence
        assert confirmed.reason == SAID_YES
        assert confirmed.evidence["proposed_reason"] == (
            "appeared on 3 days in 30 across 3 threads"
        )

        # -- 6. now it colours turns, and is in the index ---------------
        assert select_interest(world.rows(), signals) is not None
        assert world.observations.search("samba", limit=5)

        # -- 7. and it is listed as something remembered ----------------
        from halbert_core.continuity.about_you import list_remembered

        listed = list_remembered(world.memory)
        assert [r["topic"] for r in listed] == ["samba"]
        assert listed[0]["learned"].startswith("Noticed across 3 conversations")

        # -- 8. it is not asked about again -----------------------------
        assert select_candidate(world.rows(), signals, now=NOW) is None

    @pytest.mark.asyncio
    async def test_a_yes_the_model_invented_is_refused(self, world, monkeypatch):
        """The failure this tool exists to prevent."""
        from halbert_core.continuity.provenance import current_user_message
        from halbert_core.tools.confirm_interest import confirm_interest

        _propose(world)
        token = current_user_message.set("what's the weather")
        try:
            answer = await confirm_interest({"topic": "samba"})
        finally:
            try:
                current_user_message.reset(token)
            except ValueError:
                current_user_message.set(SAID_YES)
        assert "did not agree" in answer
        assert world.rows()[0].status is InterestStatus.CANDIDATE

    @pytest.mark.asyncio
    async def test_a_topic_nobody_proposed_is_refused(self, world):
        from halbert_core.tools.confirm_interest import confirm_interest

        _propose(world)
        answer = await confirm_interest({"topic": "underwater basket weaving"})
        assert "nothing was asked about" in answer
        assert len(world.rows()) == 1

    @pytest.mark.asyncio
    async def test_confirming_twice_is_refused(self, world):
        from halbert_core.tools.confirm_interest import confirm_interest

        _propose(world)
        assert "Recorded" in await confirm_interest({"topic": "samba"})
        assert "not an outstanding question" in await confirm_interest({"topic": "samba"})

    @pytest.mark.asyncio
    async def test_a_guest_speaker_may_not_confirm(self, world):
        from halbert_core.tools.executor import current_speaker_role
        from halbert_core.tools.confirm_interest import confirm_interest

        _propose(world)
        token = current_speaker_role.set("guest")
        try:
            answer = await confirm_interest({"topic": "samba"})
        finally:
            try:
                current_speaker_role.reset(token)
            except ValueError:
                current_speaker_role.set("admin")
        assert "may not record a fact about the household" in answer
        assert world.rows()[0].status is InterestStatus.CANDIDATE

    @pytest.mark.asyncio
    async def test_there_is_no_way_to_record_a_no(self, world):
        """A person who declines has said nothing that needs storing. A tool
        that recorded refusals would be a second list of things someone said
        no to, which is a record nobody asked for."""
        from halbert_core.tools import confirm_interest as mod

        assert not [n for n in dir(mod) if "decline" in n or "reject" in n]
