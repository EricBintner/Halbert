# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The vault's doors: every route is local-admin, and the CLI works."""
import json
import sqlite3
import uuid
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from halbert_core.dashboard.routes import backup as backup_routes  # noqa: E402
from halbert_core.federation.peers_config import PeersConfig  # noqa: E402


@pytest.fixture
def entity(tmp_path, monkeypatch):
    """A small entity on disk, behind the routes."""
    config = tmp_path / "config"
    data = tmp_path / "data"
    halo = tmp_path / "halo"
    for d in (config, data, halo):
        d.mkdir(parents=True)
    (config / "being.yml").write_text("voice: null\n")
    (halo / "personas" / "halbert").mkdir(parents=True)
    (halo / "personas" / "halbert" / "memories.json").write_text(json.dumps({
        "version": 2, "persona_id": "halbert", "memories": []}))
    conn = sqlite3.connect(str(data / "conversations.db"))
    conn.execute("CREATE TABLE conversations (id TEXT)")
    conn.commit()
    conn.close()
    monkeypatch.setattr(
        "halbert_core.utils.platform.get_config_dir", lambda: config)
    monkeypatch.setenv("HALBERT_DATA_DIR", str(data))
    monkeypatch.setenv("HALOYSIUS_DATA_HOME", str(halo))
    monkeypatch.setattr(
        "halbert_core.crypto.storage.resolve_signer", lambda *a, **kw: None)
    return tmp_path


@pytest.fixture
def app(tmp_path, monkeypatch):
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
    app.include_router(backup_routes.router)
    return app, config


class TestBackupRoutes:
    def test_backup_now_creates_archive(self, app, entity, tmp_path):
        fast_app, _ = app
        out = tmp_path / "exports"
        res = TestClient(fast_app).post("/api/backup/now", json={
            "passphrase": "pw", "export_path": str(out)})
        assert res.status_code == 200
        archive = Path(res.json()["archive"])
        assert archive.is_file()
        assert archive.name.endswith(".halbert-backup")

    def test_history_lists_archives(self, app, entity, tmp_path):
        fast_app, _ = app
        out = tmp_path / "exports"
        TestClient(fast_app).post("/api/backup/now", json={
            "passphrase": "pw", "export_path": str(out)})
        res = TestClient(fast_app).get(
            "/api/backup/history", params={"export_path": str(out)})
        assert res.status_code == 200
        assert len(res.json()) == 1
        assert res.json()[0]["schema_version"] == 1

    def test_restore_round_trip(self, app, entity, tmp_path):
        fast_app, _ = app
        out = tmp_path / "exports"
        created = TestClient(fast_app).post("/api/backup/now", json={
            "passphrase": "pw", "export_path": str(out)}).json()
        res = TestClient(fast_app).post("/api/backup/restore", json={
            "archive_path": created["archive"], "passphrase": "pw"})
        assert res.status_code == 200
        assert res.json()["status"] == "restored"

    def test_restore_wrong_passphrase_is_400(self, app, entity, tmp_path):
        fast_app, _ = app
        out = tmp_path / "exports"
        created = TestClient(fast_app).post("/api/backup/now", json={
            "passphrase": "pw", "export_path": str(out)}).json()
        res = TestClient(fast_app).post("/api/backup/restore", json={
            "archive_path": created["archive"], "passphrase": "nope"})
        assert res.status_code == 400

    def test_remote_caller_is_refused(self, app, entity, tmp_path):
        """A backup exports the body's private key — never remote."""
        fast_app, config = app
        raw = f"hbt_{uuid.uuid4().hex}"
        config.add_peer(node_id="phone", node_name="p",
                        role="trust_anchor", raw_token=raw)
        remote = TestClient(fast_app, client=("203.0.113.7", 4444))
        for method, url in (
            ("post", "/api/backup/now"),
            ("get", "/api/backup/history"),
            ("post", "/api/backup/restore"),
            ("get", "/api/backup/config"),
        ):
            res = getattr(remote, method)(
                url, headers={"Authorization": f"Bearer {raw}"})
            assert res.status_code in (401, 403), (url, res.status_code)


class TestCli:
    """The terminal path — same engines, operator at a shell."""

    def test_backup_and_restore_round_trip(self, entity, tmp_path, monkeypatch):
        from halbert_core.cli.backup import backup_main, restore_main
        monkeypatch.setattr("sys.argv", [
            "halbert-backup", "--path", str(tmp_path / "out"),
            "--passphrase", "pw"])
        backup_main()
        archives = list((tmp_path / "out").glob("*.halbert-backup"))
        assert len(archives) == 1

        monkeypatch.setattr("sys.argv", [
            "halbert-restore", "--path", str(archives[0]),
            "--passphrase", "pw"])
        restore_main()  # exits cleanly — anything else raises SystemExit

    def test_restore_wrong_passphrase_exits(self, entity, tmp_path, monkeypatch):
        from halbert_core.cli.backup import backup_main, restore_main
        monkeypatch.setattr("sys.argv", [
            "halbert-backup", "--path", str(tmp_path / "out"),
            "--passphrase", "pw"])
        backup_main()
        archive = next((tmp_path / "out").glob("*.halbert-backup"))
        monkeypatch.setattr("sys.argv", [
            "halbert-restore", "--path", str(archive),
            "--passphrase", "wrong"])
        with pytest.raises(SystemExit):
            restore_main()
