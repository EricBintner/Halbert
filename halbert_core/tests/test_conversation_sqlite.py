# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for SqliteConversationStore + migration (F1)."""

import pytest

from halbert_core.agents.conversation import Conversation, Message
from halbert_core.agents.conversation_sqlite import SqliteConversationStore


@pytest.fixture
def store():
    s = SqliteConversationStore(":memory:")
    yield s
    s.close()


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

class TestCRUD:
    def test_create_and_get(self, store):
        store.create("c1", user_id="u1")
        store.append_message("c1", "user", "hello there")
        store.append_message("c1", "assistant", "hi!", origin="assistant")

        got = store.get("c1")
        assert got is not None
        assert got.conversation_id == "c1"
        assert got.user_id == "u1"
        assert len(got.messages) == 2
        assert got.messages[0].content == "hello there"
        assert got.messages[1].content == "hi!"

    def test_get_missing_returns_none(self, store):
        assert store.get("nope") is None

    def test_get_or_create(self, store):
        c = store.get_or_create("c2", "u2")
        assert c.conversation_id == "c2"
        c2 = store.get_or_create("c2", "u2")
        assert c2.conversation_id == "c2"

    def test_save_never_touches_messages(self, store):
        conv = store.create("c3")
        store.append_message("c3", "user", "first")
        # Re-saving with a different in-memory message list changes nothing on disk
        conv.messages = [Message(role="user", content="replaced")]
        store.save(conv)
        got = store.get("c3")
        assert len(got.messages) == 1
        assert got.messages[0].content == "first"

    def test_delete(self, store):
        store.create("c4")
        store.append_message("c4", "user", "x")
        assert store.delete("c4") is True
        assert store.get("c4") is None

    def test_title_auto_from_first_user_message(self, store):
        conv = store.create("c5")
        conv.add_message("user", "A very long question about systemd configuration details")
        store.save(conv)
        got = store.get("c5")
        assert got.title is not None
        assert "systemd" in got.title or got.title.startswith("A very long")


# ---------------------------------------------------------------------------
# list_conversations
# ---------------------------------------------------------------------------

class TestList:
    def test_list_returns_summaries(self, store):
        for i in range(3):
            store.create(f"c{i}", user_id="u1")
            store.append_message(f"c{i}", "user", f"msg {i}")
        listed = store.list_conversations(user_id="u1")
        assert len(listed) == 3
        assert "conversation_id" in listed[0]
        assert listed[0]["message_count"] == 1

    def test_list_filters_by_user(self, store):
        store.create("a", "u1")
        store.create("b", "u2")
        assert len(store.list_conversations(user_id="u1")) == 1
        assert len(store.list_conversations(user_id="u2")) == 1

    def test_list_pagination(self, store):
        for i in range(5):
            store.create(f"p{i}", "u")
        assert len(store.list_conversations(limit=2)) == 2
        assert len(store.list_conversations(limit=2, offset=4)) == 1


# ---------------------------------------------------------------------------
# FTS5 search
# ---------------------------------------------------------------------------

class TestSearch:
    def test_search_finds_by_message_content(self, store):
        store.create("s1")
        store.append_message("s1", "user", "how do I configure the nginx firewall")
        store.append_message("s1", "assistant", "you can use ufw to manage the firewall", origin="assistant")
        results = store.search("firewall")
        assert "s1" in results

    def test_search_finds_by_title(self, store):
        c = store.create("s2")
        c.title = "disk usage report"
        store.save(c)
        results = store.search("disk")
        assert "s2" in results

    def test_search_no_match(self, store):
        store.create("s3")
        store.append_message("s3", "user", "nothing relevant here")
        assert store.search("zzzznonexistent") == []

    def test_search_empty_query(self, store):
        assert store.search("") == []

    def test_search_multiple_matches_distinct(self, store):
        store.create("m1"); store.append_message("m1", "user", "fix the network")
        store.create("m2"); store.append_message("m2", "user", "network is down")
        results = store.search("network")
        assert set(results) >= {"m1", "m2"}


# ---------------------------------------------------------------------------
# session_somatic_blocks
# ---------------------------------------------------------------------------

class TestSomaticBlocks:
    def test_add_and_list(self, store):
        store.add_somatic_block("sess-1", "blk-1", block_type="SENSORY", status="detected")
        store.add_somatic_block("sess-1", "blk-2", block_type="ACTION", status="executing",
                                metadata={"k": "v"})
        blocks = store.list_somatic_blocks("sess-1")
        assert len(blocks) == 2
        assert blocks[0]["block_id"] == "blk-1"
        assert blocks[1]["metadata"] == {"k": "v"}

    def test_list_empty(self, store):
        assert store.list_somatic_blocks("nope") == []

    def test_remove(self, store):
        store.add_somatic_block("sess-1", "blk-1")
        assert store.remove_somatic_block("sess-1", "blk-1") is True
        assert store.list_somatic_blocks("sess-1") == []

    def test_isolated_per_session(self, store):
        store.add_somatic_block("s1", "b1")
        store.add_somatic_block("s2", "b2")
        assert len(store.list_somatic_blocks("s1")) == 1
        assert len(store.list_somatic_blocks("s2")) == 1
