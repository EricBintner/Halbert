# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Forgetting an interest -- two verbs, and an honest report of each one's reach.

`RQ-6`, decided 2026-09-10: **"Stop using" and "Forget" are two verbs, named
apart.** "Stop using" marks the row stale with the engine's
``forgotten_by_user:`` tombstone -- reversible, auditable, and no longer
resurrectable by re-extraction. "Forget" deletes.

The report is the point, not a courtesy. ``forget_request`` already
establishes the shape this mirrors: per-plane counts, ``errors``, and
``complete`` False when a plane could not be reached, so a caller can say so
rather than showing a clean tick over a job half done. A person asking for
privacy is the worst possible moment to overclaim.

**The known gap, asserted rather than hidden.** ``ObservationStore`` has
``mark_stale_by_memory`` but no ``delete_by_memory``, and no getter returns a
row by ``source_memory_id``. So a hard forget enumerates the mirror through
FTS and matches on ``source_memory_id`` exactly -- and when that enumeration
comes up empty for a memory that had a mirror, the report says the plane was
not reached instead of claiming it was.
"""

import pytest

from halbert_core.continuity.interests import Interest, InterestStatus, Origin
from halbert_core.continuity.forget_interest import (
    STALE_REASON_LAPSED,
    STALE_REASON_USER,
    forget_interest,
    stop_using_interest,
)


@pytest.fixture
def stores(tmp_path, monkeypatch):
    """A real memory store and observation store, mirrored as production does."""
    monkeypatch.setenv("HALOYSIUS_DATA_HOME", str(tmp_path))
    from haloysius.memory_v2.observation_store import ObservationStore
    from haloysius.memory_v2.store import PersonaMemoryStore

    mem = PersonaMemoryStore("forget-test")
    obs = ObservationStore("forget-test")

    def _plant(topic="vintage thinkpads"):
        interest = Interest(topic=topic, origin=Origin.STATED,
                            reason=f"remember that I collect {topic}",
                            actor="user", speaker_role="admin",
                            status=InterestStatus.ACTIVE)
        _op, _r, memory_id = mem.smart_add(interest.to_persona_memory("forget-test"))
        obs_id = obs.save(category=interest.observation_category,
                          content=interest.content, source_memory_id=memory_id)
        return interest, memory_id, obs_id

    return mem, obs, _plant


class TestStopUsing:
    """Reversible, auditable, and never resurrected."""

    def test_the_observation_is_marked_with_the_engine_tombstone(self, stores):
        mem, obs, plant = stores
        interest, memory_id, obs_id = plant()
        report = stop_using_interest(interest, memory_id, turn="turn-7",
                                     memory_store=mem, observation_store=obs)
        assert report["complete"] is True
        stale = [o for o in obs.search(interest.topic, include_stale=True)
                 if o.id == obs_id]
        assert stale and stale[0].is_stale
        assert stale[0].stale_reason.startswith(STALE_REASON_USER)

    def test_the_tombstone_carries_the_turn(self, stores):
        mem, obs, plant = stores
        interest, memory_id, obs_id = plant()
        stop_using_interest(interest, memory_id, turn="turn-7",
                            memory_store=mem, observation_store=obs)
        row = [o for o in obs.search(interest.topic, include_stale=True) if o.id == obs_id][0]
        assert "turn-7" in row.stale_reason

    def test_nothing_is_destroyed(self, stores):
        mem, obs, plant = stores
        interest, memory_id, _ = plant()
        stop_using_interest(interest, memory_id, turn="t",
                            memory_store=mem, observation_store=obs)
        assert memory_id in mem._memories, "stop using keeps the memory"

    def test_the_engine_refuses_to_resurrect_it(self, stores):
        # The whole point of the tombstone: the next consolidation pass that
        # re-derives this observation must not clear the person's request.
        mem, obs, plant = stores
        interest, memory_id, obs_id = plant()
        stop_using_interest(interest, memory_id, turn="t",
                            memory_store=mem, observation_store=obs)
        again = obs.save(category="preference", content=interest.content,
                         source_memory_id=memory_id)
        assert again is None, "a tombstoned duplicate must not re-enter"
        row = [o for o in obs.search(interest.topic, include_stale=True) if o.id == obs_id][0]
        assert row.is_stale, "and must not be un-staled"


class TestForget:
    """Gone, and each plane reported."""

    def test_the_memory_is_hard_deleted(self, stores):
        mem, obs, plant = stores
        interest, memory_id, _ = plant()
        report = forget_interest(interest, memory_id,
                                 memory_store=mem, observation_store=obs)
        assert memory_id not in mem._memories
        assert report["memory"] is True

    def test_the_mirrored_observation_goes_too(self, stores):
        mem, obs, plant = stores
        interest, memory_id, obs_id = plant()
        report = forget_interest(interest, memory_id,
                                 memory_store=mem, observation_store=obs)
        assert report["observations"] == 1
        assert [o for o in obs.search(interest.topic, include_stale=True)
                if o.id == obs_id] == []

    def test_it_reports_every_plane_and_its_limits(self, stores):
        mem, obs, plant = stores
        interest, memory_id, _ = plant()
        report = forget_interest(interest, memory_id,
                                 memory_store=mem, observation_store=obs)
        assert set(report) >= {"memory", "observations", "errors", "complete", "limits"}
        assert report["limits"], "what it cannot reach must be stated"

    def test_a_row_that_merely_matches_the_text_is_untouched(self, stores):
        """The filter is on source_memory_id, and this is why.

        The mirror is enumerated through FTS, so the search returns anything
        whose text matches -- including observations the Consolidator wrote
        from ordinary conversation, which share the topic's words and belong
        to a different memory entirely. Deleting those would make "forget my
        interest in thinkpads" quietly erase unrelated things the person said
        about thinkpads.

        Two interests cannot be used to show this: the engine's semantic
        dedup collapses "thinkpads" into "vintage thinkpads" at smart_add, so
        there is only ever one memory for a near-miss pair. That is worth
        knowing on its own -- our topic slug keeps them apart and the engine
        joins them anyway.
        """
        mem, obs, plant = stores
        interest, memory_id, _ = plant("vintage thinkpads")
        bystander = obs.save(
            category="preference",
            content="User mentioned repairing vintage thinkpads at work",
            source_memory_id="some-other-memory",
        )
        assert bystander, "the bystander row must exist for this to mean anything"

        hits = obs.search("vintage thinkpads", include_stale=True)
        assert any(o.id == bystander for o in hits), (
            "this test is only meaningful if FTS returns the bystander"
        )

        report = forget_interest(interest, memory_id,
                                 memory_store=mem, observation_store=obs)
        assert report["observations"] == 1, "only the mirror was ours to delete"
        assert [o for o in obs.search("vintage thinkpads", include_stale=True)
                if o.id == bystander], "an unrelated row was collateral"


class TestTheReportIsHonest:

    def test_a_missing_memory_is_not_reported_as_erased(self, stores):
        mem, obs, _ = stores
        interest = Interest(topic="never stored", origin=Origin.STATED,
                            reason="remember that never stored", actor="user")
        report = forget_interest(interest, "no-such-memory",
                                 memory_store=mem, observation_store=obs)
        assert report["memory"] is False
        assert report["complete"] is False, (
            "nothing was found to erase; saying 'done' would be a lie"
        )

    def test_an_unreachable_plane_lands_in_errors(self, stores, monkeypatch):
        mem, obs, plant = stores
        interest, memory_id, _ = plant()

        def _boom(*a, **k):
            raise RuntimeError("disk gone")

        monkeypatch.setattr(obs, "search", _boom)
        report = forget_interest(interest, memory_id,
                                 memory_store=mem, observation_store=obs)
        assert report["errors"]
        assert report["complete"] is False

    def test_forgetting_never_raises(self, stores, monkeypatch):
        # Forgetting must not fail loudly at the one moment a person is
        # asking for privacy.
        mem, obs, plant = stores
        interest, memory_id, _ = plant()
        monkeypatch.setattr(mem, "delete", lambda *a, **k: (_ for _ in ()).throw(OSError("x")))
        report = forget_interest(interest, memory_id,
                                 memory_store=mem, observation_store=obs)
        assert report["complete"] is False


class TestTheStaleReasonConvention:

    def test_the_three_forms_are_distinguishable(self):
        # `forgotten_by_user:<turn>` / `lapsed:<date>` / `superseded_by:<id>`
        assert STALE_REASON_USER.endswith(":")
        assert STALE_REASON_LAPSED.endswith(":")
        assert STALE_REASON_USER != STALE_REASON_LAPSED

    def test_the_user_tombstone_is_the_engine_constant(self):
        from haloysius.memory_v2.observation_store import USER_TOMBSTONE_PREFIX
        assert STALE_REASON_USER == USER_TOMBSTONE_PREFIX, (
            "if these drift the engine stops recognising our tombstone and "
            "silently resurrects what a person asked to drop"
        )
