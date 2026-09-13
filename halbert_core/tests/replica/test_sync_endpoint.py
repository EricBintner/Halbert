# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The sync-replica door: only the canonical pushes, only a body accepts.

F-D: the receiver authenticates the pusher as the peer it recorded with
role="canonical" — any other live peer token is refused for its role.
The promotion fence: a node that no longer follows a canonical answers
409 rather than letting a stale canonical overwrite the mind it now owns.
"""
import json
import sqlite3
import uuid
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from halbert_core.dashboard.routes import peers as peers_routes  # noqa: E402
from halbert_core.federation.peers_config import PeersConfig  # noqa: E402
from halbert_core.replica.push import pack_snapshot_tar  # noqa: E402
from halbert_core.replica.snapshot import SnapshotTarget, create_snapshot  # noqa: E402
from halbert_core.replica.store import ReplicaStore  # noqa: E402


def _memories(path: Path, count: int = 2) -> Path:
    path.write_text(json.dumps({
        "version": 2,
        "memories": [{"id": f"m{i}"} for i in range(count)],
    }))
    return path


def _db(path: Path) -> Path:
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("CREATE TABLE conversations (id TEXT)")
        conn.execute("INSERT INTO conversations VALUES ('c1')")
        conn.commit()
    finally:
        conn.close()
    return path


def _tar(tmp_path: Path) -> bytes:
    src = tmp_path / "src"
    src.mkdir(exist_ok=True)
    snap = create_snapshot([
        SnapshotTarget(_memories(src / "memories.json"), "file_copy", "memories.json"),
        SnapshotTarget(_db(src / "conversations.db"), "sqlite_backup", "conversations.db"),
    ])
    return pack_snapshot_tar(snap, source_node_id="canonical-1")


@pytest.fixture(autouse=True)
def _local_client(monkeypatch):
    import halbert_core.federation.peer_middleware as pm

    def _looks_local(request):
        client = getattr(request, "client", None)
        host = getattr(client, "host", None) if client else None
        return host == "testclient" or pm._is_loopback_host(host)

    monkeypatch.setattr(pm, "_is_local_client", _looks_local)
    yield


@pytest.fixture
def env(tmp_path, monkeypatch):
    """A bare app, an isolated peer store, an isolated replica dir, and a
    node that thinks it is a body (canonical_memory_url set)."""
    config = PeersConfig(config_path=tmp_path / "peers.json")
    monkeypatch.setattr(
        "halbert_core.federation.peer_middleware.get_peers_config", lambda: config)
    monkeypatch.setattr(
        "halbert_core.dashboard.routes.peers.get_peers_config", lambda: config)
    monkeypatch.setenv("HALBERT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(
        "halbert_core.integrations.cognition_wiring._get_canonical_memory_url",
        lambda: "http://canonical-1:8000/api/memory")
    app = FastAPI()
    app.include_router(peers_routes.router)
    yield app, config


def _token(config: PeersConfig, node_id: str, role: str) -> str:
    raw = f"hbt_{uuid.uuid4().hex}"
    config.add_peer(node_id=node_id, node_name=node_id, role=role, raw_token=raw)
    return raw


def test_canonical_push_is_stored(env, tmp_path):
    app, config = env
    canonical = _token(config, "canonical-1", "canonical")
    res = TestClient(app).post(
        "/api/peers/sync-replica",
        content=_tar(tmp_path),
        headers={"Authorization": f"Bearer {canonical}",
                 "Content-Type": "application/x-tar"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "stored"
    assert body["memory_count"] == 2
    assert ReplicaStore().meta() is not None


def test_a_body_peer_cannot_push(env, tmp_path):
    app, config = env
    body = _token(config, "body-1", "body")
    res = TestClient(app).post(
        "/api/peers/sync-replica",
        content=_tar(tmp_path),
        headers={"Authorization": f"Bearer {body}"},
    )
    assert res.status_code == 403


def test_anonymous_push_is_refused(env, tmp_path):
    app, _ = env
    anon = TestClient(app)
    anon.headers.pop("Authorization", None)
    res = anon.post("/api/peers/sync-replica", content=_tar(tmp_path))
    assert res.status_code == 401


def test_promoted_node_refuses_the_push(env, tmp_path, monkeypatch):
    """The receiver-side split-brain fence: no canonical URL means this
    node is promoted or independent — the mind it owns is not a satellite
    of anything, and a stale push must not overwrite it."""
    app, config = env
    monkeypatch.setattr(
        "halbert_core.integrations.cognition_wiring._get_canonical_memory_url",
        lambda: "")
    canonical = _token(config, "canonical-1", "canonical")
    res = TestClient(app).post(
        "/api/peers/sync-replica",
        content=_tar(tmp_path),
        headers={"Authorization": f"Bearer {canonical}"},
    )
    assert res.status_code == 409


def test_corrupt_payload_is_rejected(env, tmp_path):
    app, config = env
    canonical = _token(config, "canonical-1", "canonical")
    res = TestClient(app).post(
        "/api/peers/sync-replica",
        content=b"not a tar at all",
        headers={"Authorization": f"Bearer {canonical}"},
    )
    assert res.status_code == 400


def test_manifest_digest_mismatch_is_rejected(env, tmp_path):
    app, config = env
    canonical = _token(config, "canonical-1", "canonical")
    tar = bytearray(_tar(tmp_path))
    # Flip one byte inside the tar — the stored digest won't match.
    tar[len(tar) // 2] ^= 0xFF
    res = TestClient(app).post(
        "/api/peers/sync-replica",
        content=bytes(tar),
        headers={"Authorization": f"Bearer {canonical}"},
    )
    assert res.status_code in (400, 422)


class TestRegisterCanonical:
    """The satellite's half of the F-D handshake, local-admin only."""

    def test_remote_peer_cannot_register(self, env):
        app, config = env
        peer = _token(config, "body-1", "body")
        remote = TestClient(app, client=("203.0.113.7", 4444))
        res = remote.post(
            "/api/peers/register-canonical",
            json={"canonical_node_id": "c1", "canonical_url": "http://c1:8000",
                  "peer_token": "hbt_x", "push_token": "hbt_y"},
            headers={"Authorization": f"Bearer {peer}"},
        )
        assert res.status_code == 403

    def test_register_stores_canonical_record_and_being(
            self, env, tmp_path, monkeypatch):
        app, config = env
        being = tmp_path / "being.yml"
        monkeypatch.setattr(
            "halbert_core.config.being_config._default_path", lambda: being)
        res = TestClient(app).post("/api/peers/register-canonical", json={
            "canonical_node_id": "halbert-mac",
            "canonical_url": "http://mac.local:8000",
            "peer_token": "hbt_satellite",
            "push_token": "hbt_push",
            "persona_id": "halbert",
        })
        assert res.status_code == 200, res.text
        record = config.get_peer("halbert-mac")
        assert record is not None
        assert record.role == "canonical"
        # The stored hash verifies the raw push token — the canonical's
        # pushes will authenticate against exactly this record.
        assert config.verify_token("hbt_push").node_id == "halbert-mac"

        from halbert_core.config.being_config import load_being_config
        cfg = load_being_config()
        assert cfg.canonical_memory_url == "http://mac.local:8000/api/memory"
        assert cfg.canonical_thread_url == "http://mac.local:8000/api/conversations"
        assert cfg.peer_token == "hbt_satellite"

    def test_register_requires_http_url(self, env):
        app, _ = env
        res = TestClient(app).post("/api/peers/register-canonical", json={
            "canonical_node_id": "c1", "canonical_url": "ftp://nope",
            "peer_token": "hbt_x", "push_token": "hbt_y",
        })
        assert res.status_code == 400
