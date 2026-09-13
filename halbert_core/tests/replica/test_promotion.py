# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Promotion: the replica becomes the live mind, divergence quarantined."""
import json
import os
import sqlite3
import stat
import uuid
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from halbert_core.dashboard.routes import replica as replica_routes  # noqa: E402
from halbert_core.federation.peers_config import PeersConfig  # noqa: E402
from halbert_core.replica.promotion import promote_to_canonical  # noqa: E402
from halbert_core.replica.snapshot import SnapshotTarget, create_snapshot  # noqa: E402
from halbert_core.replica.store import ReplicaStore  # noqa: E402


def _memories(path: Path, count: int = 3) -> Path:
    path.write_text(json.dumps({
        "version": 2,
        "persona_id": "halbert",
        "memories": [{"id": f"m{i}", "persona_id": "halbert",
                      "content": f"m{i}", "memory_type": "episodic"}
                     for i in range(count)],
    }))
    return path


def _db(path: Path) -> Path:
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("CREATE TABLE conversations (id TEXT)")
        conn.executemany("INSERT INTO conversations VALUES (?)",
                         [("c1",), ("c2",)])
        conn.commit()
    finally:
        conn.close()
    return path


@pytest.fixture
def promoted_env(tmp_path, monkeypatch):
    """A satellite with a valid replica, a being.yml pointing at a dead
    canonical, and the local data tree the promotion will write into."""
    # Replica
    src = tmp_path / "src"
    src.mkdir()
    snap = create_snapshot([
        SnapshotTarget(_memories(src / "memories.json"), "file_copy", "memories.json"),
        SnapshotTarget(_db(src / "conversations.db"), "sqlite_backup", "conversations.db"),
    ])
    data = tmp_path / "data"
    store = ReplicaStore(replica_dir=data / "canonical_replica")
    store.receive(snap.staging_dir, {
        "files": snap.manifest, "created_at": snap.created_at,
        "source_node_id": "canonical-1",
    })
    monkeypatch.setenv("HALBERT_DATA_DIR", str(data))
    monkeypatch.setenv("HALOYSIUS_DATA_HOME", str(tmp_path / "halo"))

    # being.yml on a tmp path: this node is a body of a dead canonical.
    being = tmp_path / "being.yml"
    being.write_text(
        "canonical_memory_url: http://dead:8000/api/memory\n"
        "canonical_thread_url: http://dead:8000/api/conversations\n"
        "peer_token: hbt_x\n"
        "persona_id_override: halbert\n"
    )
    monkeypatch.setattr(
        "halbert_core.config.being_config._default_path", lambda: being)
    return store, data


class TestPromoteFunction:
    def test_valid_replica_promotes(self, promoted_env):
        store, data = promoted_env
        result = promote_to_canonical(store)
        assert result.success, result.error
        assert result.old_canonical_url == "http://dead:8000/api/memory"
        assert result.memory_count == 3
        assert result.thread_count == 2
        assert (data / "conversations.db").is_file()

    def test_promotion_clears_both_canonical_urls(self, promoted_env):
        store, _ = promoted_env
        promote_to_canonical(store)
        from halbert_core.config.being_config import load_being_config
        cfg = load_being_config()
        assert cfg.canonical_memory_url == ""
        assert cfg.canonical_thread_url == ""
        assert cfg.peer_token == ""

    def test_no_replica_fails(self, tmp_path):
        store = ReplicaStore(replica_dir=tmp_path / "nothing")
        result = promote_to_canonical(store)
        assert not result.success
        assert "replica" in result.error

    def test_corrupt_replica_fails(self, promoted_env):
        store, _ = promoted_env
        (store.path() / "memories.json").write_text("{torn")
        result = promote_to_canonical(store)
        assert not result.success

    def test_divergent_local_state_is_quarantined(self, promoted_env):
        """A memory written while the canonical was down must not be
        silently overwritten — it moves aside, preserved for the operator."""
        store, data = promoted_env
        data.mkdir(exist_ok=True)
        diverged = data / "conversations.db"
        _db(diverged)
        # Make it genuinely different content.
        conn = sqlite3.connect(str(diverged))
        conn.execute("INSERT INTO conversations VALUES ('local-only')")
        conn.commit()
        conn.close()

        result = promote_to_canonical(store)
        assert result.success
        assert len(result.quarantined) == 1
        assert Path(result.quarantined[0]).is_file()
        # And the live file is now the replica's.
        conn = sqlite3.connect(str(data / "conversations.db"))
        assert conn.execute(
            "SELECT COUNT(*) FROM conversations").fetchone()[0] == 2
        conn.close()

    def test_promotion_is_idempotent(self, promoted_env):
        store, _ = promoted_env
        first = promote_to_canonical(store)
        assert first.success
        second = promote_to_canonical(store)
        assert second.success  # same replica installs again cleanly


class TestPromoteRoute:
    """The route's door: trust_anchor or local operator — a recovery
    action taken from the phone, at arm's length."""

    @pytest.fixture
    def app(self, tmp_path, monkeypatch):
        import halbert_core.federation.peer_middleware as pm

        def _looks_local(request):
            client = getattr(request, "client", None)
            host = getattr(client, "host", None) if client else None
            return host == "testclient" or pm._is_loopback_host(host)

        monkeypatch.setattr(pm, "_is_local_client", _looks_local)
        config = PeersConfig(config_path=tmp_path / "peers.json")
        monkeypatch.setattr(
            "halbert_core.federation.peer_middleware.get_peers_config",
            lambda: config)
        app = FastAPI()
        app.include_router(replica_routes.router)
        return app, config

    def test_status_route_answers_any_principal(self, app):
        fast_app, _ = app
        res = TestClient(fast_app).get("/api/replica/status")
        assert res.status_code == 200
        assert res.json()["has_replica"] is False

    def test_promote_requires_trust_anchor(self, app):
        fast_app, config = app
        raw = f"hbt_{uuid.uuid4().hex}"
        config.add_peer(node_id="body-1", node_name="b", role="body",
                        raw_token=raw)
        remote = TestClient(fast_app, client=("203.0.113.7", 4444))
        res = remote.post("/api/replica/promote",
                          headers={"Authorization": f"Bearer {raw}"})
        assert res.status_code == 403

    def test_trust_anchor_may_promote(self, app, tmp_path, monkeypatch):
        fast_app, config = app
        raw = f"hbt_{uuid.uuid4().hex}"
        config.add_peer(node_id="phone", node_name="p", role="trust_anchor",
                        raw_token=raw)
        remote = TestClient(fast_app, client=("203.0.113.7", 4444))
        res = remote.post("/api/replica/promote",
                          headers={"Authorization": f"Bearer {raw}"})
        # No replica in this env → a clean 400, not an auth failure.
        assert res.status_code == 400

    def test_anonymous_cannot_promote(self, app):
        fast_app, _ = app
        remote = TestClient(fast_app, client=("203.0.113.7", 4444))
        remote.headers.pop("Authorization", None)
        assert remote.post("/api/replica/promote").status_code == 401
