# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The push loop: the right peers, the right credential, a report per peer."""
import io
import json
import sqlite3
import tarfile
import uuid
from pathlib import Path

import pytest

from halbert_core.federation.peers_config import PeersConfig
from halbert_core.replica.push import (
    pack_snapshot_tar,
    push_snapshot_to_peers,
    unpack_snapshot_tar,
)
from halbert_core.replica.snapshot import SnapshotTarget, create_snapshot


def _memories(path: Path) -> Path:
    path.write_text(json.dumps({"version": 2, "memories": [{"id": "m1"}]}))
    return path


def _db(path: Path) -> Path:
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("CREATE TABLE conversations (id TEXT)")
        conn.commit()
    finally:
        conn.close()
    return path


def _snapshot(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir(exist_ok=True)
    return create_snapshot([
        SnapshotTarget(_memories(src / "memories.json"), "file_copy", "memories.json"),
        SnapshotTarget(_db(src / "conversations.db"), "sqlite_backup", "conversations.db"),
    ])


def test_tar_roundtrip(tmp_path):
    snap = _snapshot(tmp_path)
    body = pack_snapshot_tar(snap, source_node_id="canonical-1")
    dest = tmp_path / "rx"
    manifest = unpack_snapshot_tar(body, dest)

    assert manifest["source_node_id"] == "canonical-1"
    assert set(manifest["files"]) == {"memories.json", "conversations.db"}
    assert (dest / "memories.json").is_file()
    assert (dest / "conversations.db").is_file()


def test_tar_refuses_hostile_members(tmp_path):
    """A member outside the allowlist is skipped unread — extractfile,
    never extractall, so a name can never steer a write."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        payload = b"evil"
        info = tarfile.TarInfo("../../etc/evil.txt")
        info.size = len(payload)
        tar.addfile(info, io.BytesIO(payload))
        good = b'{"files": {}}'
        info = tarfile.TarInfo("manifest.json")
        info.size = len(good)
        tar.addfile(info, io.BytesIO(good))
    dest = tmp_path / "rx"
    unpack_snapshot_tar(buf.getvalue(), dest)
    assert not (tmp_path / "etc").exists()
    assert not (dest / ".." / "etc" ).exists()


def test_unpack_requires_a_manifest(tmp_path):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        data = b"x"
        info = tarfile.TarInfo("memories.json")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    with pytest.raises(ValueError):
        unpack_snapshot_tar(buf.getvalue(), tmp_path / "rx")


class TestPushToPeers:
    @pytest.fixture
    def config(self, tmp_path, monkeypatch):
        c = PeersConfig(config_path=tmp_path / "peers.json")
        monkeypatch.setattr(
            "halbert_core.federation.peer_middleware.get_peers_config", lambda: c)
        return c

    def _peer(self, config, node_id, role="body", endpoint="http://sat:8000",
              outbound="hbt_push"):
        config.add_peer(node_id=node_id, node_name=node_id, role=role,
                        raw_token=f"hbt_{uuid.uuid4().hex}", endpoint=endpoint)
        if outbound:
            config.set_outbound_token(node_id, outbound)

    def test_pushes_to_body_peers_with_their_outbound_token(
            self, config, tmp_path):
        self._peer(config, "sat-1")
        self._peer(config, "sat-2", endpoint="http://sat2:8000", outbound="hbt_p2")
        self._peer(config, "compute-1", role="compute_provider")  # skipped
        calls = []

        class Resp:
            status_code = 200
            text = "{}"

        def http_post(url, data=None, headers=None, timeout=None):
            calls.append((url, headers))
            return Resp()

        reports = push_snapshot_to_peers(_snapshot(tmp_path), http_post=http_post)

        assert {r.peer_id for r in reports if r.success} == {"sat-1", "sat-2"}
        assert all(r.success for r in reports)
        assert calls[0][0] == "http://sat:8000/api/peers/sync-replica"
        assert calls[0][1]["Authorization"] == "Bearer hbt_push"
        assert calls[1][1]["Authorization"] == "Bearer hbt_p2"

    def test_peer_without_outbound_token_is_reported_not_pushed(
            self, config, tmp_path):
        self._peer(config, "sat-1", outbound=None)
        calls = []

        def http_post(url, **kw):
            calls.append(url)

        reports = push_snapshot_to_peers(_snapshot(tmp_path), http_post=http_post)

        assert calls == []
        assert reports[0].success is False
        assert "re-pair" in reports[0].error

    def test_revoked_peers_are_skipped(self, config, tmp_path):
        self._peer(config, "sat-1")
        config.revoke_peer("sat-1")
        calls = []

        def http_post(url, **kw):
            calls.append(url)

        reports = push_snapshot_to_peers(_snapshot(tmp_path), http_post=http_post)
        assert calls == []
        assert reports == []

    def test_http_failure_is_a_report_not_an_exception(self, config, tmp_path):
        self._peer(config, "sat-1")

        class Resp:
            status_code = 409
            text = "promoted"

        def http_post(url, **kw):
            return Resp()

        reports = push_snapshot_to_peers(_snapshot(tmp_path), http_post=http_post)
        assert reports[0].success is False
        assert reports[0].status_code == 409

    def test_network_error_is_a_report(self, config, tmp_path):
        self._peer(config, "sat-1")

        def http_post(url, **kw):
            raise OSError("connection refused")

        reports = push_snapshot_to_peers(_snapshot(tmp_path), http_post=http_post)
        assert reports[0].success is False
        assert "connection refused" in reports[0].error
