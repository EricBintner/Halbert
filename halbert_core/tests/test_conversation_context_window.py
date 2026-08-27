# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""``Conversation.get_context_window``: the summary stands in for what it drops.

This method has no caller in the shipping tree. Its last one was
``context/assembler.py::build_conversation_window``, which called it from the
compaction branch on main (fd9d7fd); the merged feature branch rewrote that
function to hard-trim instead, on the grounds that the thread receipt is a
better summary than anything built from whatever happens to be overflowing.

It is kept, and pinned here, because the same merge carried a real main-side
bugfix into it that nothing was left to exercise:

    remaining_older = older_messages[:-included_older_count] ...

``[:-0]`` is ``[:0]``, so on the ordinary tight-budget path — nothing older
fits — every older turn was dropped *and* the summary that is supposed to
stand in for them was skipped, silently. The pre-fix body returns five rows
and no summary where the fixed one returns six; without this file nothing in
the repository can tell those two apart, so a future edit could revert the fix
with the suite still green.
"""

import pytest

from halbert_core.agents.conversation import Conversation


OLDER = 3
RECENT = 5  # get_context_window's own `keep_recent` ceiling


def _conversation() -> Conversation:
    conv = Conversation(conversation_id="c1")
    for i in range(OLDER):
        conv.add_message("user", f"older turn {i} about the samba share")
    for i in range(RECENT):
        conv.add_message("assistant", f"recent turn {i} about the samba share")
    return conv


def _cost(messages) -> int:
    """The method's own char accounting: content plus 20 of overhead."""
    return sum(len(m.content) + 20 for m in messages)


class TestOlderTurnsAreNeverDroppedSilently:
    def test_nothing_older_fits_so_all_of_it_is_summarised(self):
        # The `[:-0]` case, and the usual one once the budget is tight: the
        # recent turns plus one older turn plus the 500-char summary reserve
        # overrun the budget, so no older turn is included.
        conv = _conversation()
        window = conv.get_context_window(max_tokens=200)

        assert window[0]["role"] == "system"
        assert window[0]["content"].startswith("Previous conversation summary:")
        # Every older turn is accounted for in the summary, not just gone.
        for i in range(OLDER):
            assert f"older turn {i}" in window[0]["content"]
        # ...and the recent turns follow it, verbatim and in order.
        assert [m["content"] for m in window[1:]] == [
            f"recent turn {i} about the samba share" for i in range(RECENT)
        ]

    def test_a_summary_is_emitted_even_when_the_recent_turns_already_overflow(self):
        # The second half of the same fix: the summary used to be withheld
        # when it did not fit alongside the turns, which is exactly when turns
        # get dropped. The caller trims to its own ceiling instead.
        conv = Conversation(conversation_id="c2")
        for i in range(OLDER):
            conv.add_message("user", f"older turn {i}")
        for i in range(RECENT):
            conv.add_message("assistant", "x" * 400)

        window = conv.get_context_window(max_tokens=10)  # 40 chars of budget

        assert window[0]["role"] == "system"
        assert "older turn 0" in window[0]["content"]

    def test_partial_fit_summarises_only_the_turns_it_left_out(self):
        # The non-degenerate branch of the same line: with one older turn
        # included, `older_messages[:-1]` must be the two it did NOT include —
        # the oldest ones — and never the other way round.
        conv = _conversation()
        older, recent = conv.messages[:OLDER], conv.messages[OLDER:]
        # Room for the recent turns, the summary reserve, and exactly one
        # older turn (each older turn costs at least 21 chars, so rounding the
        # budget up to whole tokens cannot buy a second one).
        chars = _cost(recent) + (len(older[-1].content) + 20) + 500
        window = conv.get_context_window(max_tokens=(chars + 3) // 4)

        assert window[0]["role"] == "system"
        summary = window[0]["content"]
        assert "older turn 0" in summary and "older turn 1" in summary
        assert "older turn 2" not in summary
        # The one that fitted is carried whole, ahead of the recent turns.
        assert window[1]["content"] == "older turn 2 about the samba share"
        assert len(window) == 1 + 1 + RECENT

    def test_everything_fits_so_there_is_nothing_to_summarise(self):
        conv = _conversation()
        window = conv.get_context_window(max_tokens=4000)

        assert not any(m["role"] == "system" for m in window)
        assert [m["content"] for m in window] == [m.content for m in conv.messages]


class TestNoOlderTurns:
    def test_a_short_conversation_is_returned_as_is(self):
        conv = Conversation(conversation_id="c3")
        for i in range(RECENT):
            conv.add_message("user", f"turn {i}")

        window = conv.get_context_window(max_tokens=4000)

        assert [m["content"] for m in window] == [f"turn {i}" for i in range(RECENT)]
        assert not any(m["role"] == "system" for m in window)

    def test_an_empty_conversation_returns_nothing(self):
        assert Conversation(conversation_id="c4").get_context_window() == []


class TestSummariseMessages:
    def test_a_multi_line_turn_is_reduced_to_its_first_line(self):
        conv = Conversation(conversation_id="c5")
        conv.add_message("user", "restart smbd\nthen check testparm")

        summary = conv._summarize_messages(conv.messages)

        assert summary == "- user: restart smbd..."

    def test_a_summary_is_capped(self):
        conv = Conversation(conversation_id="c6")
        for i in range(40):
            conv.add_message("user", f"turn {i} " + "pad " * 20)

        summary = conv._summarize_messages(conv.messages)

        assert len(summary) == 503 and summary.endswith("...")

    def test_no_messages_says_so(self):
        assert Conversation(conversation_id="c7")._summarize_messages([]) == (
            "No previous messages."
        )


@pytest.mark.parametrize("name", ["get_context_window", "_summarize_messages"])
def test_the_window_helpers_are_still_on_the_record(name):
    # A deliberate tripwire: if either is deleted, this file goes with it and
    # the deletion is a decision someone made on purpose, not a silent drift.
    assert callable(getattr(Conversation, name))
