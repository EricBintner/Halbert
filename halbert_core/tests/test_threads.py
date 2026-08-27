# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for agents/threads.py — the hidden-thread manager."""

from datetime import datetime

import pytest

from halbert_core.agents.conversation_sqlite import SqliteConversationStore
from halbert_core.agents.threads import ThreadManager
from halbert_core.intake.signals import analyze_message

NOW = datetime(2026, 8, 26, 12, 0).timestamp()


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


@pytest.fixture
def tm():
    s = SqliteConversationStore(":memory:")
    clock = Clock(NOW)
    m = ThreadManager(s, now=clock)
    m.clock = clock
    yield m
    s.close()


def _turn(tm, text, session="s", **end):
    turn = tm.begin_turn(text, analyze_message(text), session)
    tm.end_turn(turn, assistant_text=end.get("assistant", "ok"), blocks=end.get("blocks", []),
                terminal_session_ids=end.get("terminals", []), diff_proposals=end.get("diffs", []))
    return turn


class TestBeginEndTurn:
    def test_first_turn_opens_thread_and_persists_user_row(self, tm):
        text = "add a samba share for the media folder"
        turn = tm.begin_turn(text, analyze_message(text), "sess-1")
        assert turn.decision.action == "open_new" and turn.history == [] and turn.hint == "" and turn.recalled == []
        assert turn.previous_thread_id is None and turn.session_id == "sess-1"
        assert turn.domains == ["network"] and turn.entities == ["samba", "share"]
        t = tm.current()
        assert t["thread_id"] == turn.thread_id and t["title"] == text and t["title_source"] == "provisional"
        rows = tm.store.list_messages(turn.thread_id)
        assert len(rows) == 1 and rows[0]["status"] == "in_progress" and rows[0]["turn_id"] == turn.turn_id
        assert rows[0]["session_id"] == "sess-1" and rows[0]["message_id"] == turn.user_message_id

    def test_second_turn_sees_first_exchange(self, tm):
        t1 = _turn(tm, "add a samba share for the media folder", assistant="Added [media] to smb.conf.")
        text = "now restart smbd"
        turn2 = tm.begin_turn(text, analyze_message(text), "sess-2")
        assert turn2.thread_id == t1.thread_id and turn2.decision.action == "stay"
        assert turn2.history == [
            {"role": "user", "content": "add a samba share for the media folder"},
            {"role": "assistant", "content": "Added [media] to smb.conf."},
        ]
        assert turn2.hint == ('<continuity>\nThread: "add a samba share for the media folder" · 1 turns · '
                              'last active just now.\n</continuity>')

    def test_end_turn_updates_thread_and_receipt(self, tm):
        turn = _turn(tm, "add a samba share for the media folder",
                     assistant="Done. Next, check the mount from the laptop.",
                     blocks=[{"tool": "run_command", "args": {"command": "testparm"}, "exit": 0}],
                     terminals=["term-1"], diffs=[{"id": "d1", "path": "/etc/samba/smb.conf"}])
        t = tm.store.get_thread(turn.thread_id)
        assert t["last_active"] == NOW and t["turns_since_pause"] == 1
        assert t["topic_domains"] == ["network"] and t["entities_json"] == ["samba", "share"]
        assert "Commands: testparm (exit 0)" in t["receipt"]
        assert "Files written: /etc/samba/smb.conf" in t["receipt"]
        assert "Open loop: Next, check the mount from the laptop." in t["receipt"]
        rows = tm.store.list_messages(turn.thread_id)
        assert rows[0]["status"] == "complete"
        assert rows[1]["role"] == "assistant" and rows[1]["turn_id"] == turn.turn_id and rows[1]["session_id"] == "s"
        assert rows[1]["terminal_block_ids"] == ["term-1"] and rows[1]["diff_proposals"][0]["id"] == "d1"
        assert tm.store.search_receipts("testparm")[0]["thread_id"] == turn.thread_id

    def test_history_gets_receipt_row_when_older_turns_exist(self, tm):
        for i in range(8):
            _turn(tm, f"step {i} of the samba setup", assistant=f"did step {i}")
        turn = tm.begin_turn("continue", analyze_message("continue"), "s")
        assert len(turn.history) == 13
        assert turn.history[0]["role"] == "system"
        assert turn.history[0]["content"].startswith("[Earlier in this subject: Title: step 0 of the samba setup")
        assert turn.history[1] == {"role": "user", "content": "step 2 of the samba setup"}

    def test_gap_and_shift_opens_new_thread_and_pauses_old(self, tm):
        t1 = _turn(tm, "add a samba share for the media folder", assistant="Added it.")
        tm.clock.advance(3 * 3600)
        text = "check the disk space on /var"
        turn2 = tm.begin_turn(text, analyze_message(text), "s2")
        assert turn2.thread_id != t1.thread_id and turn2.decision.action == "open_new"
        assert turn2.previous_thread_id == t1.thread_id
        old = tm.store.get_thread(t1.thread_id)
        assert old["status"] == "paused" and old["paused_at"] == NOW + 3 * 3600 and old["metadata"]["successor"] == turn2.thread_id
        assert tm.current()["thread_id"] == turn2.thread_id
        assert turn2.history[0]["role"] == "system" and "kept for one turn only" in turn2.history[0]["content"]
        assert turn2.history[1]["content"] == "add a samba share for the media folder"

    def test_strong_recall_of_closed_thread_injects_receipt(self, tm):
        t1 = _turn(tm, "add a samba share for the media folder", assistant="Added [media] at /srv/media.")
        tm.clock.advance(3 * 3600)
        t2 = _turn(tm, "check the disk space on /var")
        assert tm.store.update_thread(t1.thread_id, status="closed") is True
        text = "add another share like we did for the media one"
        turn3 = tm.begin_turn(text, analyze_message(text), "s3")
        assert turn3.thread_id == t2.thread_id and turn3.decision.action == "stay"
        assert turn3.recalled[0]["thread_id"] == t1.thread_id and turn3.recalled[0]["status"] == "accepted"
        assert turn3.hint.startswith('<continuity>\nThread: "check the disk space on /var" · 1 turns · last active just now.\n')
        assert 'Pulled in: "Add samba" (Aug 26, 3 hours ago; matched' in turn3.hint
        assert "Started with: add a samba share for the media folder" in turn3.hint
        rec = tm.store.get_thread(t2.thread_id)["recalled_json"]
        assert len(rec) == 1 and rec[0]["thread_id"] == t1.thread_id and rec[0]["status"] == "accepted"

    def test_strong_match_reopens_paused(self, tm):
        t1 = _turn(tm, "swap the failing nvme in the zfs pool", assistant="Resilver running.")
        tm.clock.advance(3 * 3600)
        t2 = _turn(tm, "add a samba share for the media folder")
        text = "the zfs resilver on the nvme finished"
        turn3 = tm.begin_turn(text, analyze_message(text), "s3")
        assert turn3.decision.action == "reopen" and turn3.thread_id == t1.thread_id
        assert tm.store.get_thread(t2.thread_id)["status"] == "paused"
        assert tm.store.get_thread(t1.thread_id)["status"] == "open"
        assert turn3.history[0] == {"role": "user", "content": "swap the failing nvme in the zfs pool"}

    def test_resume_thread(self, tm):
        t1 = _turn(tm, "add a samba share for the media folder")
        tm.clock.advance(3 * 3600)
        t2 = _turn(tm, "check the disk space on /var")
        assert tm.resume_thread(t1.thread_id, from_thread_id=t2.thread_id) is True
        assert tm.current()["thread_id"] == t1.thread_id
        assert tm.store.get_thread(t2.thread_id)["status"] == "paused"
        reopened = tm.store.get_thread(t1.thread_id)
        assert reopened["paused_at"] is None and reopened["turns_since_pause"] == 0 and "successor" not in reopened["metadata"]
        assert tm.resume_thread("nope", from_thread_id=t1.thread_id) is False
        assert tm.resume_thread(t1.thread_id, from_thread_id=t2.thread_id) is False  # already open

    def test_mark_interrupted(self, tm):
        tm.begin_turn("add a samba share", analyze_message("add a samba share"), "s")
        assert tm.mark_interrupted() == 1
        assert tm.store.list_messages(tm.current()["thread_id"])[0]["status"] == "interrupted"
