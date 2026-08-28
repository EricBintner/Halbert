# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for R8: consolidation at idle."""

import time

import pytest

from halbert_core.agents.conversation_sqlite import SqliteConversationStore
from halbert_core.continuity.consolidation import Consolidator
from halbert_core.continuity.state_store import StateStore


@pytest.fixture
def store():
    s = SqliteConversationStore(":memory:")
    yield s
    s.close()


@pytest.fixture
def state_store(tmp_path):
    s = StateStore(db_path=str(tmp_path / "state.db"))
    yield s
    s.close()


def _make_thread(store, thread_id, *, domains, entities, status="closed", updated_at=None):
    ts = updated_at or time.time()
    store.create_thread(thread_id, f"Thread {thread_id}", created_at=ts)
    store.update_thread(
        thread_id,
        topic_domains=domains,
        entities_json=entities,
        status=status,
        updated_at=ts,
    )


class TestConsolidation:
    def test_no_facts_below_min_batch(self, store, state_store):
        now = time.time()
        for i in range(2):
            _make_thread(store, f"t{i}", domains=["network"], entities=["samba"], updated_at=now)
        c = Consolidator(store, state_store)
        assert c.consolidate(now=now) == 0

    def test_records_durable_facts(self, store, state_store):
        now = time.time()
        for i in range(5):
            _make_thread(
                store, f"t{i}",
                domains=["network"],
                entities=["samba", "nfs", f"unique{i}"],
                updated_at=now,
            )
        c = Consolidator(store, state_store)
        facts = c.consolidate(now=now)
        # samba and nfs appear in all 5 threads (>= threshold of 2)
        # plus the domain thread_count fact
        assert facts >= 3

    def test_skips_old_threads(self, store, state_store):
        now = time.time()
        old = now - 8 * 24 * 3600  # 8 days ago
        for i in range(5):
            _make_thread(
                store, f"t{i}",
                domains=["network"],
                entities=["samba"],
                updated_at=old,
            )
        c = Consolidator(store, state_store)
        assert c.consolidate(now=now) == 0

    def test_fail_soft_on_store_error(self, state_store):
        # A store that raises on list_threads
        class BadStore:
            def list_threads(self, **kwargs):
                raise RuntimeError("db gone")
        c = Consolidator(BadStore(), state_store)
        assert c.consolidate() == 0

    def test_domain_isolation(self, store, state_store):
        now = time.time()
        # 3 threads in "network", 2 in "config" — only network consolidates
        for i in range(3):
            _make_thread(store, f"net{i}", domains=["network"], entities=["samba"], updated_at=now)
        for i in range(2):
            _make_thread(store, f"cfg{i}", domains=["config"], entities=["vim"], updated_at=now)
        c = Consolidator(store, state_store)
        facts = c.consolidate(now=now)
        # network: samba (3/3 >= 2) + thread_count = 2 facts
        # config: below MIN_BATCH, skipped
        assert facts >= 2
