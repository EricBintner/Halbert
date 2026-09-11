# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
""""What I remember about you" -- the read model, and the tool that reads it.

`RQ-5`: a remembered fact is *data*, not a directive. It is governed by the
four-whys law -- inspectable, with who / when / how it was learned shown,
edited through the store, forgotten with a statement of reach -- rather than
by lenses invariant 5, which governs files where the file *is* the mechanism.

The same rows answer the Settings list and the conversational question, from
one deterministic function. Two readers of one store cannot disagree about
what is remembered; two implementations of the same list can, and would.
"""

import pytest

from halbert_core.continuity.about_you import (
    describe_learning,
    list_remembered,
)
from halbert_core.continuity.interests import Interest, InterestStatus, Origin


def _stated(topic="vintage thinkpads", **kw):
    kw.setdefault("reason", f"remember that I collect {topic}")
    kw.setdefault("actor", "user")
    return Interest(topic=topic, origin=Origin.STATED, **kw)


def _inferred(topic="samba tuning", **kw):
    kw.setdefault("reason", "appeared on 4 days in 30 across 5 threads")
    kw.setdefault("evidence", {"days": 4, "window_days": 30,
                               "threads": ["t1", "t2", "t3", "t4", "t5"]})
    return Interest(topic=topic, origin=Origin.INFERRED_CONFIRMED, **kw)


class _Store:
    def __init__(self, rows):
        self._rows = rows

    def list_memories(self):
        return [r.to_persona_memory("about-you") for r in self._rows]


class TestHowItWasLearned:
    """Plain words, and never a bare confidence number.

    The UI shows the origin and the evidence; a score would invite the reader
    to weigh a thing the system cannot justify numerically.
    """

    def test_a_stated_interest_says_you_told_me(self):
        assert "you" in describe_learning(_stated()).lower()

    def test_an_inferred_one_counts_its_evidence(self):
        text = describe_learning(_inferred())
        assert "5" in text and "30" in text, f"evidence not shown: {text!r}"

    def test_no_bare_confidence_number_appears(self):
        for interest in (_stated(), _inferred()):
            text = describe_learning(interest)
            assert "0.9" not in text and "0.7" not in text

    def test_it_never_raises_on_missing_evidence(self):
        assert describe_learning(_stated(evidence={}))


class TestTheList:

    def test_active_interests_are_listed(self):
        rows = list_remembered(_Store([_stated()]))
        assert len(rows) == 1
        assert rows[0]["topic"] == "vintage thinkpads"

    def test_each_row_carries_who_when_and_how(self):
        row = list_remembered(_Store([_stated()]))[0]
        for key in ("topic", "learned", "when", "reason", "status", "memory_id"):
            assert key in row, f"missing {key}"

    def test_the_row_shows_the_message_it_came_from(self):
        row = list_remembered(_Store([_stated()]))[0]
        assert row["reason"] == "remember that I collect vintage thinkpads"

    def test_forgotten_rows_are_hidden_by_default(self):
        rows = list_remembered(_Store([
            _stated("vintage thinkpads"),
            _stated("sailing", status=InterestStatus.FORGET_REQUESTED),
        ]))
        assert [r["topic"] for r in rows] == ["vintage thinkpads"]

    def test_show_forgotten_reveals_them(self):
        rows = list_remembered(_Store([
            _stated("vintage thinkpads"),
            _stated("sailing", status=InterestStatus.FORGET_REQUESTED),
        ]), include_forgotten=True)
        assert {r["topic"] for r in rows} == {"vintage thinkpads", "sailing"}

    def test_a_candidate_is_not_shown_as_something_remembered(self):
        # Nobody confirmed it. Listing it as remembered would make the list
        # claim more than the system is entitled to.
        rows = list_remembered(_Store([
            Interest(topic="samba", origin=Origin.INFERRED,
                     status=InterestStatus.CANDIDATE, reason="4 days in 30"),
        ]))
        assert rows == []

    def test_no_store_is_an_empty_list_not_an_error(self):
        assert list_remembered(None) == []

    def test_a_broken_store_is_an_empty_list(self):
        class _Broken:
            def list_memories(self):
                raise RuntimeError("gone")

        assert list_remembered(_Broken()) == []


class TestTheConversationalAnswer:
    """The same rows, deterministically -- no model, no ranking."""

    async def test_it_answers_from_the_list(self):
        from halbert_core.tools.about_you_tool import what_i_remember

        import halbert_core.integrations.cognition_wiring as cw
        cw.get_persona_memory_store = lambda: _Store([_stated()])
        out = await what_i_remember({})
        assert "vintage thinkpads" in out

    async def test_nothing_remembered_says_so_plainly(self):
        from halbert_core.tools.about_you_tool import what_i_remember

        import halbert_core.integrations.cognition_wiring as cw
        cw.get_persona_memory_store = lambda: _Store([])
        out = await what_i_remember({})
        assert "nothing" in out.lower()

    async def test_it_tells_the_model_not_to_add_to_the_list(self):
        # The failure mode: asked what it remembers, a model happily invents
        # a fifth thing. The answer text says the list is complete.
        from halbert_core.tools.about_you_tool import what_i_remember

        import halbert_core.integrations.cognition_wiring as cw
        cw.get_persona_memory_store = lambda: _Store([_stated()])
        out = await what_i_remember({})
        assert "nothing else" in out.lower() or "only" in out.lower()

    async def test_it_shows_how_each_was_learned(self):
        from halbert_core.tools.about_you_tool import what_i_remember

        import halbert_core.integrations.cognition_wiring as cw
        cw.get_persona_memory_store = lambda: _Store([_inferred()])
        out = await what_i_remember({})
        assert "5" in out, "the person should see the evidence, not just the claim"
