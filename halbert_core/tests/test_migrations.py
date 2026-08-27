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

    def test_unrecognised_shapes_are_skipped(self, store, tmp_path):
        agent_dir = tmp_path / "a"
        agent_dir.mkdir()
        # a bare list, and a dict with neither `conversation_id` nor `id`
        (agent_dir / "a-list.json").write_text(json.dumps([{"role": "user", "content": "hi"}]))
        (agent_dir / "b-stray.json").write_text(json.dumps({"foo": "bar", "messages": []}))
        counts = migrate_legacy_conversations(
            store, agent_dir=agent_dir, legacy_dir=tmp_path / "none"
        )
        assert counts == {"agent_json": 0, "legacy_json": 0}
        assert store.list_conversations() == []

    def test_block_list_content_is_flattened_to_text(self, store, tmp_path):
        agent_dir = tmp_path / "a"
        agent_dir.mkdir()
        (agent_dir / "blocks.json").write_text(json.dumps(dict(
            AGENT_CONV,
            conversation_id="blocks-1",
            messages=[
                {"role": "user", "content": "restart the samba share",
                 "timestamp": 1720000000.0},
                {"role": "assistant", "timestamp": 1720000060.0, "content": [
                    {"type": "text", "text": "Restarting smbd."},
                    {"type": "tool_use", "name": "run_command",
                     "input": {"command": "systemctl restart smbd"}},
                ]},
            ],
        )))
        migrate_legacy_conversations(store, agent_dir=agent_dir, legacy_dir=tmp_path / "none")
        rows = store.recent_messages("blocks-1", limit=12)
        assert rows[1]["content"].startswith("Restarting smbd.")
        assert "run_command" in rows[1]["content"]
        # ...and the structure behind that text survives as blocks, not only
        # as a rendering of it (review round 2, finding 4)
        stored = store.list_messages("blocks-1")
        assert [b.get("type") for b in stored[1]["blocks"]] == ["text", "tool_use"]
        assert stored[1]["blocks"][1]["input"] == {"command": "systemctl restart smbd"}

    def test_iso_timestamps_with_an_offset_are_converted(self, store, tmp_path):
        legacy_dir = tmp_path / "l"
        legacy_dir.mkdir()
        (legacy_dir / "offset.json").write_text(json.dumps(dict(
            LEGACY_CONV,
            id="offset-1",
            messages=[dict(LEGACY_CONV["messages"][1],
                           timestamp="2026-07-14T12:01:00+02:00")],
        )))
        migrate_legacy_conversations(store, agent_dir=tmp_path / "none", legacy_dir=legacy_dir)
        rows = store.recent_messages("offset-1", limit=12)
        assert rows[0]["timestamp"] == datetime.fromisoformat(
            "2026-07-14T10:01:00+00:00"
        ).timestamp()

    def test_store_without_connection_is_a_noop(self, dirs):
        agent_dir, legacy_dir = dirs
        dead = SqliteConversationStore(str(agent_dir / "x" / "y" / "z" / "not-creatable.db"))
        dead._conn = None
        assert migrate_legacy_conversations(
            dead, agent_dir=agent_dir, legacy_dir=legacy_dir
        ) == {"agent_json": 0, "legacy_json": 0}


class TestPartialWrites:
    """A thread is several store calls; a failure between them must not leave
    a truncated, still-open thread behind (review finding 1)."""

    @staticmethod
    def _fail_second_append(store, monkeypatch):
        real = store.append_message
        calls = {"n": 0}

        def flaky(*args, **kwargs):
            calls["n"] += 1
            return None if calls["n"] == 2 else real(*args, **kwargs)

        monkeypatch.setattr(store, "append_message", flaky)

    def test_failed_write_leaves_no_open_truncated_thread(self, store, dirs, monkeypatch):
        agent_dir, legacy_dir = dirs
        self._fail_second_append(store, monkeypatch)

        counts = migrate_legacy_conversations(
            store, agent_dir=agent_dir, legacy_dir=legacy_dir
        )
        # agent-1 refused half way; the other file still migrated
        assert counts == {"agent_json": 0, "legacy_json": 1}
        assert store.get_thread("agent-1") is None
        assert store.current_open_thread() is None

        # and the retry really happens on the next run
        monkeypatch.undo()
        counts = migrate_legacy_conversations(
            store, agent_dir=agent_dir, legacy_dir=legacy_dir
        )
        assert counts == {"agent_json": 1, "legacy_json": 0}
        assert store.get_thread("agent-1")["status"] == "closed"
        assert len(store.recent_messages("agent-1", limit=50)) == 2
        assert [h["thread_id"] for h in store.search_receipts("journalctl")] == ["agent-1"]

    def test_interrupted_run_repairs_the_half_written_thread(self, store, dirs, monkeypatch):
        agent_dir, legacy_dir = dirs
        self._fail_second_append(store, monkeypatch)
        # the run dies before it can clean up after itself (kill -9, power cut)
        monkeypatch.setattr(store, "delete", lambda *a, **k: False)

        migrate_legacy_conversations(store, agent_dir=agent_dir, legacy_dir=legacy_dir)
        half = store.get_thread("agent-1")
        assert half is not None and half["status"] == "open"
        assert len(store.recent_messages("agent-1", limit=50)) == 1

        monkeypatch.undo()
        counts = migrate_legacy_conversations(
            store, agent_dir=agent_dir, legacy_dir=legacy_dir
        )
        assert counts == {"agent_json": 1, "legacy_json": 0}
        assert store.get_thread("agent-1")["status"] == "closed"
        assert [r["content"][:6] for r in store.recent_messages("agent-1", limit=50)] == [
            "why is", "journa"
        ]
        assert store.current_open_thread() is None

    def test_a_live_thread_that_claimed_the_id_is_never_discarded(
        self, store, dirs, monkeypatch
    ):
        """The repair path must prove a leftover thread is its own before it
        deletes anything (review round 2, finding 1)."""
        agent_dir, legacy_dir = dirs
        self._fail_second_append(store, monkeypatch)
        migrate_legacy_conversations(store, agent_dir=agent_dir, legacy_dir=legacy_dir)
        assert store.get_thread("agent-1") is None  # cleaned up, row still partial
        monkeypatch.undo()

        # Something else now owns that id — the store takes any id a caller
        # hands it, and A12b/A12c wire legacy ids through it.
        from halbert_core.agents.conversation import Conversation
        store.save(Conversation(conversation_id="agent-1", title="live thread"))
        store.append_message("agent-1", "user", "a real question", origin="human")

        counts = migrate_legacy_conversations(
            store, agent_dir=agent_dir, legacy_dir=legacy_dir
        )
        assert counts == {"agent_json": 0, "legacy_json": 0}
        assert store.get_thread("agent-1")["title"] == "live thread"
        assert [r["content"] for r in store.recent_messages("agent-1", limit=50)] == [
            "a real question"
        ]

    def test_orphaned_partial_is_swept_when_its_source_is_gone(
        self, store, dirs, monkeypatch
    ):
        """A12c/A12d delete both legacy stores, so "interrupted, then the file
        went away" is a state to expect (review round 2, finding 2)."""
        agent_dir, legacy_dir = dirs
        self._fail_second_append(store, monkeypatch)
        monkeypatch.setattr(store, "delete", lambda *a, **k: False)  # kill -9
        migrate_legacy_conversations(store, agent_dir=agent_dir, legacy_dir=legacy_dir)
        assert store.get_thread("agent-1")["status"] == "open"
        monkeypatch.undo()

        (agent_dir / "agent-1.json").unlink()
        counts = migrate_legacy_conversations(
            store, agent_dir=agent_dir, legacy_dir=legacy_dir
        )
        assert counts == {"agent_json": 0, "legacy_json": 0}
        assert store.get_thread("agent-1") is None
        assert store.current_open_thread() is None
        # the bookkeeping row went with it
        assert store._conn.execute(
            "SELECT COUNT(*) FROM migrations_done WHERE state = 'partial'"
        ).fetchone()[0] == 0

    def test_sweep_keeps_finished_threads_whose_sources_were_deleted(self, store, dirs):
        """The normal end state of A12c/A12d: both stores are removed once the
        migration has run. Nothing may be swept then."""
        agent_dir, legacy_dir = dirs
        migrate_legacy_conversations(store, agent_dir=agent_dir, legacy_dir=legacy_dir)
        (agent_dir / "agent-1.json").unlink()
        (legacy_dir / "legacy-1.json").unlink()
        assert migrate_legacy_conversations(
            store, agent_dir=agent_dir, legacy_dir=legacy_dir
        ) == {"agent_json": 0, "legacy_json": 0}
        assert store.get_thread("agent-1")["status"] == "closed"
        assert store.get_thread("legacy-1")["status"] == "closed"
        assert [h["thread_id"] for h in store.search_receipts("samba")] == ["legacy-1"]


class TestTopicSets:
    """Entities are harvested per message, not from one giant string
    (review round 2, finding 3)."""

    def test_entities_past_the_scan_limit_are_still_harvested(self, store, tmp_path):
        agent_dir = tmp_path / "a"
        agent_dir.mkdir()
        filler = "the disk was fine yesterday and the disk is fine today. " * 400
        assert len(filler) > 16 * 1024  # past intake's _ENTITY_SCAN_LIMIT
        (agent_dir / "long.json").write_text(json.dumps(dict(
            AGENT_CONV,
            conversation_id="long-1",
            messages=[
                {"role": "user", "content": filler, "timestamp": 1720000000.0},
                {"role": "user", "timestamp": 1720000060.0,
                 "content": "now configure the samba share on /srv/media and restart smbd"},
            ],
        )))
        migrate_legacy_conversations(store, agent_dir=agent_dir, legacy_dir=tmp_path / "none")
        entities = store.get_thread("long-1")["entities_json"]
        assert "samba" in entities and "/srv/media" in entities
        assert "disk" in entities  # the early message still counts too
        assert [h["thread_id"] for h in store.search_receipts("samba")] == ["long-1"]

    def test_entities_are_capped_like_a_live_thread(self, store, tmp_path):
        from halbert_core.agents.threads import MAX_THREAD_ENTITIES

        agent_dir = tmp_path / "a"
        agent_dir.mkdir()
        (agent_dir / "wide.json").write_text(json.dumps(dict(
            AGENT_CONV,
            conversation_id="wide-1",
            messages=[
                {"role": "user", "content": f"check /srv/vol{i:02d} please",
                 "timestamp": 1720000000.0 + i}
                for i in range(30)
            ],
        )))
        migrate_legacy_conversations(store, agent_dir=agent_dir, legacy_dir=tmp_path / "none")
        entities = store.get_thread("wide-1")["entities_json"]
        assert len(entities) == MAX_THREAD_ENTITIES
        # newest kept, oldest dropped — the same tie-break threads._age_topics uses
        assert "/srv/vol29" in entities
        assert "/srv/vol00" not in entities


class TestStructureSurvives:
    """A migrated thread must still be able to answer "what did we run last
    time?" — the receipt line a sysadmin agent needs most (review round 2,
    finding 4). This migration is a one-way door: A12c/A12d delete the
    sources, so anything dropped here is gone for good."""

    def test_agent_shape_tool_use_blocks_reach_the_receipt(self, store, tmp_path):
        agent_dir = tmp_path / "a"
        agent_dir.mkdir()
        (agent_dir / "tools.json").write_text(json.dumps(dict(
            AGENT_CONV,
            conversation_id="tools-1",
            title="Samba share",
            messages=[
                {"role": "user", "content": "add a media share to samba",
                 "timestamp": 1720000000.0},
                {"role": "assistant", "timestamp": 1720000060.0, "content": [
                    {"type": "text", "text": "Added the share and restarted the service."},
                    {"type": "tool_use", "name": "write_file",
                     "input": {"path": "/etc/samba/smb.conf", "content": "[media]"}},
                    {"type": "tool_use", "name": "run_command",
                     "input": {"command": "systemctl restart smbd"}},
                ]},
            ],
        )))
        migrate_legacy_conversations(store, agent_dir=agent_dir, legacy_dir=tmp_path / "none")
        receipt = store.get_thread("tools-1")["receipt"]
        assert "systemctl restart smbd" in receipt
        assert "/etc/samba/smb.conf" in receipt
        assert "Commands: none" not in receipt
        assert "Files written: none" not in receipt
        assert [h["thread_id"] for h in store.search_receipts("smbd")] == ["tools-1"]

    def test_dashboard_shape_tool_calls_reach_the_receipt(self, store, tmp_path):
        legacy_dir = tmp_path / "l"
        legacy_dir.mkdir()
        (legacy_dir / "calls.json").write_text(json.dumps(dict(
            LEGACY_CONV,
            id="calls-1",
            messages=[
                {"id": "m0", "role": "user", "content": "free some space on /var",
                 "timestamp": "2026-07-14T10:00:00", "tool_calls": []},
                {"id": "m1", "role": "assistant", "content": "Vacuumed the journal.",
                 "timestamp": "2026-07-14T10:01:00", "tool_calls": [
                     # the field was only ever typed List[Dict[str, Any]]:
                     # accept an OpenAI function entry as well as a plain one
                     {"id": "c0", "type": "function", "function": {
                         "name": "run_command",
                         "arguments": "{\"command\": \"journalctl --vacuum-size=200M\"}"}},
                     {"tool": "edit_file", "args": {"path": "/etc/logrotate.conf"},
                      "exit": 0},
                 ]},
            ],
        )))
        migrate_legacy_conversations(store, agent_dir=tmp_path / "none", legacy_dir=legacy_dir)
        receipt = store.get_thread("calls-1")["receipt"]
        assert "journalctl --vacuum-size=200M" in receipt
        assert "/etc/logrotate.conf" in receipt
        stored = store.list_messages("calls-1")
        assert [b["tool"] for b in stored[1]["blocks"]] == ["run_command", "edit_file"]

    def test_a_message_that_is_only_a_tool_call_is_kept(self, store, tmp_path):
        legacy_dir = tmp_path / "l"
        legacy_dir.mkdir()
        (legacy_dir / "silent.json").write_text(json.dumps(dict(
            LEGACY_CONV,
            id="silent-1",
            messages=[
                {"id": "m0", "role": "user", "content": "restart smbd",
                 "timestamp": "2026-07-14T10:00:00"},
                {"id": "m1", "role": "assistant", "content": "",
                 "timestamp": "2026-07-14T10:01:00", "tool_calls": [
                     {"tool": "run_command", "args": {"command": "systemctl restart smbd"},
                      "exit": 0}]},
            ],
        )))
        migrate_legacy_conversations(store, agent_dir=tmp_path / "none", legacy_dir=legacy_dir)
        assert "systemctl restart smbd (exit 0)" in store.get_thread("silent-1")["receipt"]
