# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The interest row: one shape, written and read back at the boundary.

`RQ-1`: an interest is a memory_v2 ``PersonaMemory``, mirrored as an
``ObservationStore`` ``preference`` row. ``StateStore`` never holds a user
fact (`MEM-02`: one subject, the machine).

`PersonaMemory.metadata` is a free dict, which is why this file exists. The
removed `MemoryWriter` failed because nothing it wrote could be read back --
a dataclass and a round-trip test at the boundary are the whole difference.

The confidence calibration is pinned here deliberately. Haloysius's handoff
told Halbert that a writer building its own ``PersonaMemory`` "must set
``source="user"`` itself"; measured on the engine as it stands, that alone
yields **0.7**, and the 0.9 a stated fact is supposed to carry needs the
``user_stated`` tag as well. A stated interest silently landing at the
inferred confidence is the exact defect the engine's fix was for, so it is
asserted rather than assumed.
"""

import pytest

from halbert_core.continuity.interests import (
    Interest,
    InterestStatus,
    Origin,
    topic_slug,
)


def _stated(topic="vintage thinkpads", **kw):
    kw.setdefault("reason", "remember that I collect vintage thinkpads")
    kw.setdefault("actor", "user")
    kw.setdefault("speaker_role", "admin")
    return Interest(topic=topic, origin=Origin.STATED, **kw)


def _inferred(topic="samba tuning", **kw):
    kw.setdefault("reason", "appeared on 4 days in 30 across 5 threads")
    kw.setdefault("evidence", {"days": 4, "window_days": 30, "threads": ["t1", "t2", "t3"]})
    return Interest(topic=topic, origin=Origin.INFERRED,
                    status=InterestStatus.CANDIDATE, **kw)


class TestTheTopicSlug:
    """The slug is the dedup key, in place of a content hash."""

    @pytest.mark.parametrize("a, b", [
        ("ThinkPads", "thinkpads"),
        ("Vintage ThinkPads", "vintage thinkpads"),
        ("  samba   tuning ", "samba tuning"),
        ("Samba-tuning", "samba tuning"),
        ("ZFS!", "zfs"),
    ])
    def test_the_same_topic_written_differently_is_one_slug(self, a, b):
        assert topic_slug(a) == topic_slug(b)

    def test_different_topics_stay_apart(self):
        assert topic_slug("zfs") != topic_slug("btrfs")

    def test_a_near_miss_still_fragments_and_that_is_recorded(self):
        # "ThinkPads" and "vintage ThinkPads" are documented as topics that
        # should not fragment, and under a deterministic slug they do. Joining
        # them is fuzzy *correspondence* -- rung 0 of the disagreement meter --
        # and is a separate decision, not something to fake here with a
        # substring rule that would also join "zfs" and "zfs send".
        assert topic_slug("thinkpads") != topic_slug("vintage thinkpads")

    def test_it_is_stable_and_url_safe(self):
        assert topic_slug("Vintage ThinkPads!") == "vintage-thinkpads"


class TestTheStatedRow:

    def test_it_carries_the_canonical_content(self):
        m = _stated().to_persona_memory("halbert")
        assert m.content == "User is interested in: vintage thinkpads"

    def test_a_stated_interest_is_calibrated_at_the_stated_confidence(self):
        # source alone is not enough -- see the module docstring.
        m = _stated().to_persona_memory("halbert")
        from haloysius.memory_v2.types import Provenance
        assert m.source == Provenance.USER_ORGANIC
        assert "user_stated" in m.tags, (
            "without this tag the engine calibrates a stated fact at 0.7, "
            "the inferred confidence"
        )

    def test_the_slug_is_a_tag_so_the_topic_is_the_dedup_key(self):
        m = _stated().to_persona_memory("halbert")
        assert topic_slug("vintage thinkpads") in m.tags
        assert "interest" in m.tags

    def test_the_topic_terms_are_keyword_anchors(self):
        # Keywords are the deterministic retrieval anchor: recall must not
        # depend on an embedder agreeing with itself.
        m = _stated().to_persona_memory("halbert")
        assert "thinkpads" in m.keywords

    def test_the_reason_is_the_utterance_never_model_text(self):
        m = _stated().to_persona_memory("halbert")
        assert m.metadata["reason"] == "remember that I collect vintage thinkpads"


class TestTheInferredRow:

    def test_an_inferred_candidate_is_not_user_sourced(self):
        from haloysius.memory_v2.types import Provenance
        m = _inferred().to_persona_memory("halbert")
        assert m.source == Provenance.CONSOLIDATION
        assert "user_stated" not in m.tags, (
            "an inferred candidate must not claim the confidence of a stated one"
        )

    def test_the_evidence_is_carried_as_arithmetic(self):
        m = _inferred().to_persona_memory("halbert")
        assert m.metadata["evidence"]["days"] == 4
        assert m.metadata["evidence"]["threads"] == ["t1", "t2", "t3"]

    def test_the_reason_names_the_rule_that_produced_it(self):
        m = _inferred().to_persona_memory("halbert")
        assert "4 days in 30" in m.metadata["reason"]


class TestTheRoundTrip:
    """`metadata` is a free dict; this is the boundary that makes it a shape."""

    @pytest.mark.parametrize("make", [_stated, _inferred])
    def test_what_is_written_reads_back_identical(self, make):
        original = make()
        assert Interest.from_persona_memory(original.to_persona_memory("halbert")) == original

    def test_a_memory_that_is_not_an_interest_reads_back_as_none(self):
        from haloysius.memory_v2.types import MemoryType, PersonaMemory
        other = PersonaMemory(id="x", persona_id="halbert",
                              memory_type=MemoryType.SEMANTIC,
                              content="User's name: Alex", tags=["taught"])
        assert Interest.from_persona_memory(other) is None

    def test_a_malformed_metadata_dict_does_not_raise(self):
        # The dict is free, so another writer can put anything in it. A
        # reader that raises here takes down whatever was iterating rows.
        from haloysius.memory_v2.types import MemoryType, PersonaMemory
        broken = PersonaMemory(id="x", persona_id="halbert",
                               memory_type=MemoryType.SEMANTIC,
                               content="User is interested in: x",
                               tags=["interest"], metadata={"topic": None})
        assert Interest.from_persona_memory(broken) is None


class TestTheMirrorRule:
    """The observation row is the index, not the record."""

    def test_an_active_interest_mirrors(self):
        assert _stated(status=InterestStatus.ACTIVE).should_mirror is True

    @pytest.mark.parametrize("status", [
        InterestStatus.CANDIDATE,
        InterestStatus.LAPSED,
        InterestStatus.FORGET_REQUESTED,
    ])
    def test_nothing_else_mirrors(self, status):
        # A candidate is never injected into a prompt until a person
        # confirms it, so it must not reach the index recall reads.
        assert _stated(status=status).should_mirror is False

    def test_the_mirror_category_is_preference_not_fact(self):
        # The keyword classifier files "interested in" as `fact`; the
        # category is set explicitly so it does not.
        assert _stated().observation_category == "preference"


class TestTheWriterRefusals:

    def test_an_empty_topic_is_refused(self):
        with pytest.raises(ValueError):
            Interest(topic="   ", origin=Origin.STATED, reason="r")

    def test_a_reason_is_mandatory(self):
        # MEM-06: a stored fact about a person needs a reason that is a human
        # utterance or a self-naming rule.
        with pytest.raises(ValueError):
            Interest(topic="zfs", origin=Origin.STATED, reason="")

    def test_a_stated_interest_needs_an_actor(self):
        with pytest.raises(ValueError):
            Interest(topic="zfs", origin=Origin.STATED, reason="remember zfs",
                     actor="")


class TestTheConfidenceCalibrationEndToEnd:
    """Through the real store, because this is the claim the engine's own
    handoff states incorrectly for our case.

    Not a unit test of our tags: a test that asserted `"user_stated" in tags`
    would pass forever while the engine changed the gate underneath it. This
    drives a real `PersonaMemoryStore` and reads the confidence back.
    """

    @pytest.fixture
    def store(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HALOYSIUS_DATA_HOME", str(tmp_path))
        from haloysius.memory_v2.store import PersonaMemoryStore
        return PersonaMemoryStore("test-interests")

    def _confidence(self, store, interest):
        _op, _reason, mid = store.smart_add(interest.to_persona_memory("test-interests"))
        stored = store._memories.get(mid)
        return getattr(getattr(stored, "epistemic", None), "confidence", None)

    def test_a_stated_interest_lands_at_the_stated_confidence(self, store):
        assert self._confidence(store, _stated("vintage thinkpads")) == 0.9

    def test_an_inferred_candidate_lands_lower(self, store):
        # It must not arrive claiming what a person said out loud.
        assert self._confidence(store, _inferred("samba tuning")) == 0.6

    def test_dropping_the_stated_tag_costs_the_calibration(self, store, monkeypatch):
        # Pins *why* the tag is there. If the engine ever calibrates on
        # provenance alone, this fails and the tag can go.
        import halbert_core.continuity.interests as mod
        monkeypatch.setattr(mod, "_USER_STATED_TAG", "not-the-tag")
        assert self._confidence(store, _stated("roman aqueducts")) == 0.7
