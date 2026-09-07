# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for the deterministic echo guard (Packet 05 Phase B).

Lifted from OpenClaw src/gateway/boot-echo-guard.ts: a rolling-window chunk
match of recently injected sensitive material against outbound deliveries —
the second, independent layer over the redaction choke point. Catches the
model reproducing a long verbatim chunk even after paraphrasing around
markers.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from halbert_core.security import echo_guard as _eg
from halbert_core.security.echo_guard import EchoGuard


@pytest.fixture(autouse=True)
def _fresh_global_echo_guard():
    """Isolate the process-global guard around every test here."""
    saved = _eg._GLOBAL
    _eg._GLOBAL = None
    try:
        yield
    finally:
        _eg._GLOBAL = saved


def test_exact_chunk_detected():
    guard = EchoGuard(window=40, threshold=40)
    guard.note_injected(
        "api key abc123def456ghi789jkl012mno345pqr678stu901 use it for calls"
    )
    flagged = guard.scan_outbound(
        "so the key is abc123def456ghi789jkl012mno345pqr678stu901 fyi"
    )
    assert flagged


def test_short_overlap_not_flagged():
    guard = EchoGuard(window=40, threshold=40)
    guard.note_injected("api key abc123def456 use it")
    assert not guard.scan_outbound("the key starts with abc123")


def test_paraphrase_not_flagged():
    guard = EchoGuard(window=40, threshold=40)
    guard.note_injected("api key abc123def456ghi789jkl012mno345pqr678stu901")
    assert not guard.scan_outbound(
        "I've confirmed the key is configured correctly and won't repeat it."
    )


def test_session_scoped_clear():
    guard = EchoGuard(window=40, threshold=40)
    guard.note_injected("x" * 60)
    guard.clear_session("default")
    assert not guard.scan_outbound("x" * 60)


def test_whitespace_normalized():
    guard = EchoGuard(window=20, threshold=20)
    guard.note_injected("alpha beta gamma delta epsilon zeta")
    # newlines and doubled spaces collapse to the same normalized form
    assert guard.scan_outbound("alpha\nbeta  gamma   delta epsilon\tzeta")


def test_find_match_returns_the_matched_material():
    guard = EchoGuard(window=40, threshold=40)
    guard.note_injected("api key abc123def456ghi789jkl012mno345pqr678stu901")
    match = guard.find_match(
        "the key is abc123def456ghi789jkl012mno345pqr678stu901 fyi"
    )
    assert match is not None
    assert len(match) == 40
    assert guard.find_match("nothing relevant here") is None


def test_bounded_chunk_store():
    """The chunk set is bounded FIFO: an unbounded one would grow with every
    acked value for the life of the process.

    Each note is a distinct letter run so no window-sized substring is
    shared between notes — a shared substring would be refreshed by every
    later note (move_to_end on re-note) and never evict, which is correct
    guard behaviour but would make "oldest evicted" unobservable here.
    """
    guard = EchoGuard(window=8, threshold=8, max_chunks=16)
    for i in range(20):
        guard.note_injected(chr(ord("a") + i) * 30)
    assert len(guard) == 16
    # oldest evicted: the first note's chunks are gone
    assert not guard.scan_outbound("a" * 30)
    # newest still present
    assert guard.scan_outbound("t" * 30)


def test_empty_note_is_ignored():
    guard = EchoGuard(window=40, threshold=40)
    guard.note_injected("")
    guard.note_injected("   ")
    assert len(guard) == 0
    assert not guard.scan_outbound("anything at all")


def test_global_singleton():
    a = _eg.get_global_echo_guard()
    b = _eg.get_global_echo_guard()
    assert a is b
    assert isinstance(a, EchoGuard)