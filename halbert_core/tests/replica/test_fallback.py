# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Read-fallback: recall survives the canonical going dark; writes don't."""
import json
import sqlite3
import uuid
from pathlib import Path

import pytest

from halbert_core.agents.peer_conversation_store import (
    PeerConversationStore,
    PeerConversationUnavailable,
)
from halbert_core.replica.fallback import (
    FallbackConversationStore,
    ReplicaMemoryStore,
    ReplicaReadOnly,
    probe_canonical_reachable,
)
from halbert_core.replica.snapshot import SnapshotTarget, create_snapshot
from halbert_core.replica.store import ReplicaStore


def _memories(path: Path, count: int = 2) -> Path:
    path.write_text(json.dumps({
        "version": 2,
        "memories": [
            {"id": f"m{i}", "persona_id": "halbert",
             "content": f"memory {i} about tea",
             "memory_type": "episodic", "created_at": f"2026-01-0{i}"}
            for i in range(count)
        ],
    }))
    return path


def _threads_db(path: Path) -> Path:
    conn = sqlite3.connect(str(path))
    try:
        conn.executescript("""
            CREATE TABLE conversations (
                id TEXT PRIMARY KEY, title TEXT, user_id TEXT,
                created_at TEXT, updated_at TEXT);
            CREATE TABLE messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT, role TEXT, content TEXT, created_at TEXT);
            INSERT INTO conversations VALUES ('c1','t','u','2026-01-01','2026-01-01');
        """)
        conn.commit()
    finally:
        conn.close()
    return path


@pytest.fixture
def replica(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    snap = create_snapshot([
        SnapshotTarget(_memories(src / "memories.json"), "file_copy", "memories.json"),
        SnapshotTarget(_threads_db(src / "conversations.db"),
                       "sqlite_backup", "conversations.db"),
    ])
    store = ReplicaStore(replica_dir=tmp_path / "canonical_replica")
    store.receive(snap.staging_dir, {
        "files": snap.manifest,
        "created_at": snap.created_at,
        "source_node_id": "canonical-1",
    })
    return store


class _DownPeer(PeerConversationStore):
    """A peer store whose every call fails like the canonical is dead."""
    def _invoke(self, method, args, kwargs):
        raise PeerConversationUnavailable("connection refused")


class _UpPeer(PeerConversationStore):
    def _invoke(self, method, args, kwargs):
        return {"conversation_id": "from-peer", "messages": []}


class TestConversationFallback:
    def test_peer_reachable_serves_from_peer(self, replica):
        store = FallbackConversationStore(_UpPeer("http://x"), replica)
        assert store.get("c1").conversation_id == "from-peer"

    def test_peer_down_read_served_from_replica(self, replica):
        store = FallbackConversationStore(_DownPeer("http://x"), replica)
        conv = store.get("c1")
        assert conv is not None
        assert conv.conversation_id == "c1"

    def test_peer_down_write_raises(self, replica):
        store = FallbackConversationStore(_DownPeer("http://x"), replica)
        with pytest.raises(PeerConversationUnavailable):
            store.create("new-1")
        with pytest.raises(PeerConversationUnavailable):
            store.append_message("c1", "user", "hi")

    def test_peer_down_no_replica_read_raises(self, tmp_path):
        store = FallbackConversationStore(
            _DownPeer("http://x"),
            ReplicaStore(replica_dir=tmp_path / "empty_replica"),
        )
        with pytest.raises(PeerConversationUnavailable):
            store.get("c1")

    def test_healthy_true_when_only_replica(self, replica):
        store = FallbackConversationStore(_DownPeer("http://x"), replica)
        assert store.healthy is True


class TestReplicaMemoryStore:
    def test_reads_served(self, replica):
        store = ReplicaMemoryStore(replica.path() / "memories.json")
        assert store.get("m0") is not None
        assert len(store.list_memories()) == 2
        assert store.get_recent(1)[0].id == "m1"

    def test_search_is_keyword_recall(self, replica):
        store = ReplicaMemoryStore(replica.path() / "memories.json")
        results = store.search("tea", k=5)
        assert results  # degraded recall still recalls

    def test_writes_raise(self, replica):
        store = ReplicaMemoryStore(replica.path() / "memories.json")
        with pytest.raises(ReplicaReadOnly):
            store.smart_add(object())
        with pytest.raises(ReplicaReadOnly):
            store.delete("m0")
        with pytest.raises(ReplicaReadOnly):
            store.teach("x")

    def test_missing_file_yields_empty_store(self, tmp_path):
        store = ReplicaMemoryStore(tmp_path / "nope.json")
        assert store.list_memories() == []


class TestProbe:
    def test_200_is_reachable(self):
        class R:
            status_code = 200
        assert probe_canonical_reachable(
            "http://x:8000/api/memory", "hbt",
            http_get=lambda *a, **k: R()) is True

    def test_error_is_unreachable(self):
        def boom(*a, **kw):
            raise OSError("refused")
        assert probe_canonical_reachable(
            "http://x:8000", "hbt", http_get=boom) is False


class TestMemoryStoreWiring:
    """_create_memory_store picks the right backend by reachability."""

    @pytest.fixture
    def wiring(self, tmp_path, monkeypatch):
        import halbert_core.integrations.cognition_wiring as cw
        monkeypatch.setattr(cw, "_get_canonical_memory_url",
                            lambda: "http://c:8000/api/memory")
        monkeypatch.setattr(cw, "_get_peer_token", lambda: "hbt_t")
        return cw

    def test_reachable_uses_peer_backend(self, wiring, monkeypatch):
        monkeypatch.setattr(
            "halbert_core.replica.fallback.probe_canonical_reachable",
            lambda *a, **kw: True)
        store = wiring._create_memory_store()
        from haloysius.memory_v2.peer_backend import PeerMemoryBackend
        assert isinstance(store, PeerMemoryBackend)

    def test_unreachable_with_replica_uses_replica(
            self, wiring, replica, monkeypatch):
        monkeypatch.setattr(
            "halbert_core.replica.fallback.probe_canonical_reachable",
            lambda *a, **kw: False)
        # The wiring constructs ReplicaStore() with the default dir —
        # point HALBERT_DATA_DIR at the fixture's parent so it finds it.
        monkeypatch.setenv("HALBERT_DATA_DIR",
                           str(Path(replica.path()).parent))
        store = wiring._create_memory_store()
        assert isinstance(store, ReplicaMemoryStore)

    def test_unreachable_no_replica_uses_local(
            self, wiring, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "halbert_core.replica.fallback.probe_canonical_reachable",
            lambda *a, **kw: False)
        monkeypatch.setattr(
            "halbert_core.replica.store.ReplicaStore.is_valid",
            lambda self: False)
        monkeypatch.setenv("HALBERT_DATA_DIR", str(tmp_path / "empty"))
        store = wiring._create_memory_store()
        from haloysius.memory_v2.store import PersonaMemoryStore
        assert isinstance(store, PersonaMemoryStore)


class TestConversationStoreWiring:
    """_create_conversation_store wraps the peer in the fallback — the
    Step 1.6 wiring the plan's per-call recover story needs."""

    def test_peer_store_is_wrapped(self, tmp_path, monkeypatch):
        from halbert_core.integrations import cognition_wiring as cw
        monkeypatch.setattr(
            cw, "_get_canonical_thread_url",
            lambda: "http://canonical:8000/api/conversations")
        monkeypatch.setattr(cw, "_get_peer_token", lambda: "hbt_x")
        monkeypatch.setenv("HALBERT_DATA_DIR", str(tmp_path / "data"))

        from halbert_core.agents.threads import _create_conversation_store
        store = _create_conversation_store()
        assert isinstance(store, FallbackConversationStore)
        assert isinstance(store._peer, PeerConversationStore)
        assert store._peer.peer_url == "http://canonical:8000/api/conversations"

    def test_no_thread_url_stays_local(self, tmp_path, monkeypatch):
        from halbert_core.integrations import cognition_wiring as cw
        monkeypatch.setattr(cw, "_get_canonical_thread_url", lambda: "")
        monkeypatch.setenv("HALBERT_DATA_DIR", str(tmp_path / "data"))

        from halbert_core.agents.threads import _create_conversation_store
        from halbert_core.agents.conversation_sqlite import (
            SqliteConversationStore)
        store = _create_conversation_store()
        assert isinstance(store, SqliteConversationStore)
        assert not isinstance(store, FallbackConversationStore)
