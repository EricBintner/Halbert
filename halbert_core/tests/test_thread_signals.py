# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for agents/thread_signals.py — decide() rules and build_hint() text."""

from datetime import datetime

import pytest

from halbert_core.agents.conversation_sqlite import SqliteConversationStore
from halbert_core.agents.thread_signals import (
    Candidate, ThreadDecision, build_hint, decide, format_date, relative_time,
)
from halbert_core.intake.signals import analyze_message

NOW = datetime(2026, 8, 26, 12, 0).timestamp()
SAMBA_TS = NOW - 43 * 86400  # Jul 14


@pytest.fixture
def store():
    s = SqliteConversationStore(":memory:")
    s.create_thread("samba", "Samba media share")
    s.update_thread("samba", status="closed", last_active=SAMBA_TS, topic_domains=["network", "config"],
                    entities_json=["samba", "share", "/etc/samba/smb.conf", "media"])
    s.upsert_receipt("samba", "Samba media share",
        "Title: Samba media share\nEntities: samba, share, /etc/samba/smb.conf, media\n"
        "Started with: add a samba share for the media folder\nLast said: Restarted smbd.\nOpen loop: none recorded")
    s.create_thread("nas", "NAS disk swap")
    s.update_thread("nas", status="paused", last_active=NOW - 600, paused_at=NOW - 600,
                    topic_domains=["storage"], entities_json=["zfs", "nvme", "/dev/nvme0n1"])
    s.upsert_receipt("nas", "NAS disk swap",
        "Title: NAS disk swap\nEntities: zfs, nvme, /dev/nvme0n1\nStarted with: swap the failing nvme in the zfs pool\n"
        "Last said: Resilver running.\nOpen loop: Check zpool status once the resilver finishes.")
    s.create_thread("open", "Nginx tuning")
    s.update_thread("open", status="open", last_active=NOW - 60, topic_domains=["service"], entities_json=["nginx"])
    yield s
    s.close()


def _open(store):
    return store.get_thread("open")


def _decide(store, text, now=NOW, open_thread="open"):
    ot = _open(store) if open_thread else None
    return decide(text, analyze_message(text), ot, store, now)


class TestDecide:
    def test_detour_stays(self, store):
        d = _decide(store, "check the disk space on /var")
        assert d.action == "stay" and d.stale is False and d.target_thread_id == "open" and d.strong is None

    def test_gap_only_is_stale_not_new(self, store):
        store.update_thread("open", last_active=NOW - 3 * 3600)
        d = _decide(store, "restart nginx")
        assert d.action == "stay" and d.stale is True

    def test_gap_and_shift_opens_new(self, store):
        store.update_thread("open", last_active=NOW - 3 * 3600)
        d = _decide(store, "check the disk space on /var")
        assert d.action == "open_new" and d.stale is True and d.target_thread_id is None

    def test_gap_and_shift_with_anaphora_stays(self, store):
        store.update_thread("open", last_active=NOW - 3 * 3600)
        d = _decide(store, "did that work? the ssd is full")
        assert d.action == "stay" and "anaphora" in d.cues

    def test_no_open_thread(self, store):
        d = _decide(store, "check the disk space on /var", open_thread=None)
        assert d.action == "open_new" and d.target_thread_id is None

    def test_anaphora_no_signals_strong_from_most_recent_closed(self, store):
        store.update_thread("nas", status="closed")
        store.update_thread("open", last_active=None)
        d = _decide(store, "did that work?")
        assert d.action == "stay" and d.strong is not None and d.strong.thread_id == "nas"
        assert d.strong.status == "closed" and d.strong.match_terms == ["anaphora"] and d.cues == ["anaphora"]

    def test_anaphora_ignored_when_open_thread_is_newer(self, store):
        d = _decide(store, "did that work?")
        assert d.action == "stay" and d.strong is None

    def test_strong_overlap_reopens_paused(self, store):
        d = _decide(store, "the zfs resilver on the nvme finished")
        assert d.action == "reopen" and d.target_thread_id == "nas"
        assert d.strong.strong is True and {"zfs", "nvme"} <= set(d.strong.match_terms)

    def test_cue_plus_fts_hit_recalls_closed(self, store):
        d = _decide(store, "add another share like we did for the media one")
        assert d.action == "stay" and d.strong is not None and d.strong.thread_id == "samba"
        assert d.strong.status == "closed" and {"share", "media"} <= set(d.strong.match_terms)
        assert d.cues == ["past_reference"]

    def test_weak_candidates_without_cue(self, store):
        d = _decide(store, "what about the media library")
        assert d.action == "stay" and d.strong is None
        assert d.candidates[0].thread_id == "samba" and d.candidates[0].strong is False and d.candidates[0].score == 0.5


class TestBuildHint:
    def _stay(self, **kw):
        base = dict(action="stay", target_thread_id="open", stale=False, strong=None, candidates=[], cues=[])
        base.update(kw)
        return ThreadDecision(**base)

    def test_empty_for_fresh_thread(self):
        assert build_hint({"title": "x", "turn_count": 0}, self._stay(action="open_new"), [], [], now=NOW) == ""

    def test_thread_line_and_stale(self):
        ot = {"title": "Nginx tuning", "turn_count": 3, "last_active": NOW - 3 * 3600}
        assert build_hint(ot, self._stay(stale=True), [], [], now=NOW) == (
            '<continuity>\nThread: "Nginx tuning" · 3 turns · last active 3 hours ago. (resuming after a gap)\n</continuity>')

    def test_fresh_thread_with_recall(self):
        recalled = [{"thread_id": "samba", "title": "Samba media share", "date": "Jul 14", "last_active": SAMBA_TS,
                     "match_terms": ["share", "media"],
                     "receipt": "Title: Samba media share\nStarted with: add a samba share\nLast said: Restarted smbd.\nOpen loop: none recorded"}]
        hint = build_hint({"title": "Scanner share", "turn_count": 0}, self._stay(), recalled, [], now=NOW)
        assert hint == ('<continuity>\nThread: "Scanner share" · opened just now.\n'
                        'Pulled in: "Samba media share" (Jul 14, 6 weeks ago; matched share, media) — '
                        'Started with: add a samba share Last said: Restarted smbd. Open loop: none recorded\n</continuity>')

    def test_weak_candidates_line_and_omitted_when_strong(self):
        c = Candidate("samba", "Samba media share", SAMBA_TS, 0.5, ["media"], False, "closed")
        ot = {"title": "Nginx tuning", "turn_count": 1, "last_active": NOW - 60}
        hint = build_hint(ot, self._stay(candidates=[c]), [], [], now=NOW)
        assert hint.splitlines()[2] == 'Earlier work that may matter: "Samba media share" (Jul 14; matched media)'
        strong = Candidate("nas", "NAS", NOW - 600, 1.0, ["zfs"], True, "closed")
        hint2 = build_hint(ot, self._stay(strong=strong, candidates=[strong, c]), [], [], now=NOW)
        assert "Earlier work" not in hint2

    def test_notifications_and_cap(self):
        ot = {"title": "Nginx tuning", "turn_count": 1, "last_active": NOW - 60}
        hint = build_hint(ot, self._stay(), [], [{"text": "backup finished, exit 0"}], now=NOW)
        assert hint.splitlines()[2] == "Waiting for you: backup finished, exit 0"
        recalled = [{"title": "Big", "date": "Jul 14", "last_active": SAMBA_TS, "match_terms": ["x"],
                     "receipt": "Started with: " + "w" * 2000}]
        capped = build_hint(ot, self._stay(), recalled, [], now=NOW)
        assert len(capped) <= 900 and capped.endswith("…\n</continuity>")

    def test_time_helpers(self):
        assert relative_time(NOW - 30, NOW) == "just now"
        assert relative_time(NOW - 120, NOW) == "2 minutes ago"
        assert relative_time(NOW - 86400 - 10, NOW) == "yesterday"
        assert relative_time(NOW - 3 * 86400, NOW) == "3 days ago"
        assert relative_time(SAMBA_TS, NOW) == "6 weeks ago"
        assert relative_time(NOW - 100 * 86400, NOW) == "3 months ago"
        assert relative_time(None, NOW) == "unknown"
        assert format_date(SAMBA_TS, NOW) == "Jul 14"
        assert format_date(SAMBA_TS - 400 * 86400, NOW) == "Jun 9, 2025"
