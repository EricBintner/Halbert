# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for terminal hint extension in build_hint (Plan B: B22)."""

import pytest

from halbert_core.agents.thread_signals import build_hint, ThreadDecision


def _make_thread(turns=1, title="test thread", last_active=1000.0):
    return {
        "thread_id": "t1",
        "title": title,
        "turn_count": turns,
        "last_active": last_active,
    }


def _make_decision():
    return ThreadDecision(
        action="stay",
        target_thread_id="t1",
        stale=False,
        strong=None,
        candidates=[],
    )


class TestTerminalHint:
    def test_terminal_hint_included(self):
        thread = _make_thread()
        decision = _make_decision()
        hint = build_hint(
            thread, decision, recalled=[], notifications=[],
            terminal_hint="[Since your last message you ran 2 commands in your shell (last: ls /tmp, exit 0)]",
        )
        assert "2 commands" in hint
        assert "ls /tmp" in hint
        assert "<continuity>" in hint
        assert "</continuity>" in hint

    def test_terminal_hint_none_omitted(self):
        thread = _make_thread()
        decision = _make_decision()
        hint = build_hint(
            thread, decision, recalled=[], notifications=[],
            terminal_hint=None,
        )
        assert "commands in your shell" not in hint

    def test_terminal_hint_after_notes_before_notifications(self):
        thread = _make_thread()
        decision = _make_decision()
        hint = build_hint(
            thread, decision, recalled=[], notifications=[
                {"text": "build failed"},
            ],
            notes=["retracted recall of old thread"],
            terminal_hint="[Since your last message you ran 1 command in your shell (last: make, exit 1)]",
        )
        # Order: head, notes, terminal, notification
        note_pos = hint.index("Note:")
        terminal_pos = hint.index("1 command")
        notif_pos = hint.index("Waiting for you:")
        assert note_pos < terminal_pos < notif_pos

    def test_terminal_hint_clipped(self):
        thread = _make_thread()
        decision = _make_decision()
        long_hint = "[Since your last message you ran 1 command in your shell (last: " + "x" * 500 + ", exit 0)]"
        hint = build_hint(
            thread, decision, recalled=[], notifications=[],
            terminal_hint=long_hint,
        )
        # The hint should be clipped to TERMINAL_HINT_MAX
        # Just verify it doesn't blow the budget
        assert len(hint) <= 1100  # HINT_MAX_CHARS + some slack for delimiters

    def test_terminal_hint_empty_string_omitted(self):
        thread = _make_thread()
        decision = _make_decision()
        hint = build_hint(
            thread, decision, recalled=[], notifications=[],
            terminal_hint="",
        )
        assert "commands in your shell" not in hint
