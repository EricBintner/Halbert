# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for the one-time JSON -> SQLite thread migration (spec §8, Plan A).

Both legacy on-disk shapes must land as closed threads with receipts, exactly
once, and a bad file must never stop the others.
"""

import json
from datetime import datetime

import pytest

from halbert_core.agents.conversation_sqlite import SqliteConversationStore
from halbert_core.agents.migrations import migrate_legacy_conversations


AGENT_CONV = {
    "conversation_id": "agent-1",
    "user_id": "u1",
    "title": "Disk usage on /var",
    "messages": [
        {"role": "user", "content": "why is /var filling up on this box",
         "timestamp": 1720000000.0, "metadata": {}},
        {"role": "assistant",
         "content": "journald is the culprit. Next, run journalctl --vacuum-size=200M.",
         "timestamp": 1720000060.0, "metadata": {}},
    ],
    "created_at": 1720000000.0,
    "updated_at": 1720000060.0,
    "metadata": {},
}

LEGACY_CONV = {
    "id": "legacy-1",
    "name": "Chat Jul 14, 10:00 AM",
    "created_at": "2026-07-14T10:00:00",
    "updated_at": "2026-07-14T10:05:00",
    "persona": "guide",
    "messages": [
        {"id": "m0", "role": "assistant",
         "content": "Hi! I'm Halbert, your system assistant.",
         "timestamp": "2026-07-14T10:00:00", "mentions": [], "tool_calls": []},
        {"id": "m1", "role": "user",
         "content": "configure the samba share for the media folder",
         "timestamp": "2026-07-14T10:01:00", "mentions": [], "tool_calls": []},
        {"id": "m2", "role": "assistant",
         "content": "I added [media] to /etc/samba/smb.conf and restarted smbd.",
         "timestamp": "2026-07-14T10:05:00Z", "mentions": [], "tool_calls": [],
         "reasoning": None},
    ],
}


def _tid(thread):
    return thread.get("thread_id") or thread.get("id")


@pytest.fixture
def store(tmp_path):
    s = SqliteConversationStore(str(tmp_path / "threads.db"))
    yield s
    s.close()


@pytest.fixture
def dirs(tmp_path):
    agent_dir = tmp_path / "agent-json"
    legacy_dir = tmp_path / "legacy-json"
    agent_dir.mkdir()
    legacy_dir.mkdir()
    (agent_dir / "agent-1.json").write_text(json.dumps(AGENT_CONV))
    (legacy_dir / "legacy-1.json").write_text(json.dumps(LEGACY_CONV))
    return agent_dir, legacy_dir


class TestBothShapes:
    def test_both_shapes_become_closed_threads(self, store, dirs):
        agent_dir, legacy_dir = dirs
        counts = migrate_legacy_conversations(
            store, agent_dir=agent_dir, legacy_dir=legacy_dir
        )
        assert counts == {"agent_json": 1, "legacy_json": 1}

        a = store.get_thread("agent-1")
        assert a is not None
        assert a["status"] == "closed"
        assert a["title"] == "Disk usage on /var"
        assert a["last_active"] == 1720000060.0

        l = store.get_thread("legacy-1")
        assert l is not None
        assert l["status"] == "closed"
        assert l["title"] == "Chat Jul 14, 10:00 AM"

        # no thread was left open by the migration
        assert store.current_open_thread() is None

    def test_messages_keep_order_roles_and_origins(self, store, dirs):
        agent_dir, legacy_dir = dirs
        migrate_legacy_conversations(store, agent_dir=agent_dir, legacy_dir=legacy_dir)

        rows = store.recent_messages("legacy-1", limit=12)
        assert [r["role"] for r in rows] == ["assistant", "user", "assistant"]
        assert [r["origin"] for r in rows] == ["assistant", "human", "assistant"]
        assert rows[1]["content"] == "configure the samba share for the media folder"

        rows = store.recent_messages("agent-1", limit=12)
        assert [r["content"][:6] for r in rows] == ["why is", "journa"]

    def test_legacy_iso_timestamps_become_floats(self, store, dirs):
        agent_dir, legacy_dir = dirs
        migrate_legacy_conversations(store, agent_dir=agent_dir, legacy_dir=legacy_dir)
        rows = store.recent_messages("legacy-1", limit=12)
        assert rows[1]["timestamp"] == datetime(2026, 7, 14, 10, 1, 0).timestamp()
        # trailing 'Z' (UTC) parses on Python 3.10 too
        assert rows[2]["timestamp"] == datetime.fromisoformat(
            "2026-07-14T10:05:00+00:00"
        ).timestamp()
        assert store.get_thread("legacy-1")["last_active"] == rows[2]["timestamp"]

    def test_receipt_built_and_indexed_for_recall(self, store, dirs):
        agent_dir, legacy_dir = dirs
        migrate_legacy_conversations(store, agent_dir=agent_dir, legacy_dir=legacy_dir)

        l = store.get_thread("legacy-1")
        assert l["receipt"].startswith("Title:")
        assert "Started with:" in l["receipt"]
        assert "samba" in l["receipt"].lower()
        assert "samba" in l["entities_json"]
        assert "network" in l["topic_domains"]

        hits = store.search_receipts("samba")
        assert [h["thread_id"] for h in hits] == ["legacy-1"]
        hits = store.search_receipts("journalctl")
        assert [h["thread_id"] for h in hits] == ["agent-1"]


class TestIdempotence:
    def test_second_run_is_a_noop(self, store, dirs):
        agent_dir, legacy_dir = dirs
        first = migrate_legacy_conversations(store, agent_dir=agent_dir, legacy_dir=legacy_dir)
        assert first == {"agent_json": 1, "legacy_json": 1}
        again = migrate_legacy_conversations(store, agent_dir=agent_dir, legacy_dir=legacy_dir)
        assert again == {"agent_json": 0, "legacy_json": 0}
        assert len(store.recent_messages("legacy-1", limit=50)) == 3
        assert len(store.recent_messages("agent-1", limit=50)) == 2

    def test_existing_thread_id_is_not_reimported(self, store, dirs):
        agent_dir, legacy_dir = dirs
        # A live thread already uses this id: leave it alone, record the file as done.
        from halbert_core.agents.conversation import Conversation
        store.save(Conversation(conversation_id="agent-1", title="live thread"))
        store.append_message("agent-1", "user", "live row", origin="human")
        counts = migrate_legacy_conversations(store, agent_dir=agent_dir, legacy_dir=legacy_dir)
        assert counts == {"agent_json": 0, "legacy_json": 1}
        assert [r["content"] for r in store.recent_messages("agent-1", limit=50)] == ["live row"]
        assert store.get_thread("agent-1")["title"] == "live thread"
        # and it stays done on the next run
        assert migrate_legacy_conversations(
            store, agent_dir=agent_dir, legacy_dir=legacy_dir
        ) == {"agent_json": 0, "legacy_json": 0}


class TestRobustness:
    def test_missing_dirs_return_zero(self, store, tmp_path):
        counts = migrate_legacy_conversations(
            store, agent_dir=tmp_path / "nope-a", legacy_dir=tmp_path / "nope-b"
        )
        assert counts == {"agent_json": 0, "legacy_json": 0}

    def test_corrupt_file_is_skipped_and_retried_later(self, store, dirs):
        agent_dir, legacy_dir = dirs
        bad = agent_dir / "broken.json"
        bad.write_text("{not json")
        counts = migrate_legacy_conversations(store, agent_dir=agent_dir, legacy_dir=legacy_dir)
        assert counts == {"agent_json": 1, "legacy_json": 1}
        assert store.get_thread("agent-1") is not None

        # fix the file: it migrates on the next run, nothing else re-runs
        fixed = dict(AGENT_CONV, conversation_id="agent-2", title="second")
        bad.write_text(json.dumps(fixed))
        counts = migrate_legacy_conversations(store, agent_dir=agent_dir, legacy_dir=legacy_dir)
        assert counts == {"agent_json": 1, "legacy_json": 0}
        assert store.get_thread("agent-2")["status"] == "closed"

    def test_empty_conversation_is_marked_done_not_counted(self, store, tmp_path):
        agent_dir = tmp_path / "a"
        agent_dir.mkdir()
        (agent_dir / "empty.json").write_text(json.dumps(
            dict(AGENT_CONV, conversation_id="empty-1", messages=[])
        ))
        counts = migrate_legacy_conversations(store, agent_dir=agent_dir, legacy_dir=tmp_path / "none")
        assert counts == {"agent_json": 0, "legacy_json": 0}
        assert store.get_thread("empty-1") is None

    def test_title_falls_back_to_provisional_from_first_user_line(self, store, tmp_path):
        agent_dir = tmp_path / "a"
        agent_dir.mkdir()
        (agent_dir / "untitled.json").write_text(json.dumps(
            dict(AGENT_CONV, conversation_id="untitled-1", title=None)
        ))
        migrate_legacy_conversations(store, agent_dir=agent_dir, legacy_dir=tmp_path / "none")
        t = store.get_thread("untitled-1")
        assert t["title"] == "why is /var filling up on this box"
        assert t["title_source"] == "provisional"

    def test_store_without_connection_is_a_noop(self, dirs):
        agent_dir, legacy_dir = dirs
        dead = SqliteConversationStore(str(agent_dir / "x" / "y" / "z" / "not-creatable.db"))
        dead._conn = None
        assert migrate_legacy_conversations(
            dead, agent_dir=agent_dir, legacy_dir=legacy_dir
        ) == {"agent_json": 0, "legacy_json": 0}
