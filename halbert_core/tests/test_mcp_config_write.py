# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for the MCP config write path and B5 dashboard edit endpoints.

Two layers:

1. The write path itself (``mcp.config.edit_servers`` /
   ``add_server_entry`` / ``remove_server_entry`` /
   ``set_risk_overrides``) — the loader-validated, round-trip-gated,
   atomic-replace foundation the dashboard edits land through.
2. The B5 routes (``POST /api/mcp/servers``, ``DELETE /api/mcp/servers/
   {name}``, ``PUT /api/mcp/servers/{name}/risk``) — thin, capability-
   gated wraps that map the write path's exceptions to 4xx with
   redacted detail and refuse to introduce a literal token.
"""
from __future__ import annotations

import os

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

from halbert_core.dashboard.routes import mcp as mcp_routes
from halbert_core.mcp import config as cfg_mod


# ---------------------------------------------------------------------------
# Fixtures: an isolated config dir + MCP capability on
# ---------------------------------------------------------------------------

@pytest.fixture
def cfg_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("HALBERT_CONFIG_DIR", str(tmp_path))
    # The config memo keys on file identity per path; a fresh process
    # slot is already empty, but be explicit so a prior test's slot
    # can't leak if the env var was reused.
    cfg_mod.reset_config_memo()
    return tmp_path


@pytest.fixture
def client(cfg_dir, capability_registry):
    capability_registry.set_capability("mcp_client", True)
    app = FastAPI()
    app.include_router(mcp_routes.router, prefix="/api")
    return TestClient(app)


# ---------------------------------------------------------------------------
# Write path (mcp.config)
# ---------------------------------------------------------------------------

class TestAddServerEntry:
    def test_appends_a_valid_server(self, cfg_dir):
        cfg = cfg_mod.add_server_entry({
            "name": "fs", "transport": "stdio",
            "command": "npx", "args": ["-y", "server-filesystem", "/tmp"],
        })
        assert [s.name for s in cfg.servers] == ["fs"]
        # The file was written, and loads back to the same server.
        raw = yaml.safe_load((cfg_dir / "mcp_config.yml").read_text())
        assert raw["servers"][0]["name"] == "fs"
        assert raw["servers"][0]["command"] == "npx"

    def test_duplicate_exact_name_refused(self, cfg_dir):
        cfg_mod.add_server_entry({"name": "x", "transport": "stdio",
                                  "command": "a"})
        with pytest.raises(ValueError):
            cfg_mod.add_server_entry({"name": "x", "transport": "stdio",
                                      "command": "b"})

    def test_duplicate_sanitized_name_refused(self, cfg_dir):
        # A name that sanitizes to a collision is refused (the loader's
        # own collision rule), so the dashboard answers 400 instead of
        # writing an entry the loader would skip.
        cfg_mod.add_server_entry({"name": "my-server", "transport": "stdio",
                                  "command": "a"})
        with pytest.raises(ValueError):
            cfg_mod.add_server_entry({"name": "my_server", "transport": "stdio",
                                      "command": "b"})

    def test_invalid_entry_refused(self, cfg_dir):
        # No transport and no command/url — the loader skips this; the
        # write path surfaces it as a ValueError instead of writing a
        # server that would never connect.
        with pytest.raises(ValueError):
            cfg_mod.add_server_entry({"name": "broken"})

    def test_no_file_is_created_by_a_failed_add(self, cfg_dir):
        with pytest.raises(ValueError):
            cfg_mod.add_server_entry({"name": "broken"})
        assert not (cfg_dir / "mcp_config.yml").exists()


class TestRemoveServerEntry:
    def test_removes_by_exact_name(self, cfg_dir):
        cfg_mod.add_server_entry({"name": "fs", "transport": "stdio",
                                  "command": "npx"})
        cfg = cfg_mod.remove_server_entry("fs")
        assert cfg.servers == ()

    def test_missing_name_refused(self, cfg_dir):
        with pytest.raises(ValueError):
            cfg_mod.remove_server_entry("nope")

    def test_preserves_other_servers(self, cfg_dir):
        cfg_mod.add_server_entry({"name": "a", "transport": "stdio",
                                  "command": "x"})
        cfg_mod.add_server_entry({"name": "b", "transport": "stdio",
                                  "command": "y"})
        cfg = cfg_mod.remove_server_entry("a")
        assert [s.name for s in cfg.servers] == ["b"]


class TestSetRiskOverrides:
    def test_sets_override_and_tool_risk(self, cfg_dir):
        cfg_mod.add_server_entry({"name": "fs", "transport": "stdio",
                                  "command": "npx"})
        cfg = cfg_mod.set_risk_overrides("fs", "high",
                                         {"delete": "critical", "read": "safe"})
        srv = cfg.server("fs")
        assert srv.risk_override.value == "high"
        assert {t: l.value for t, l in srv.tool_risk.items()} == {
            "delete": "critical", "read": "safe"}

    def test_clears_with_none(self, cfg_dir):
        cfg_mod.add_server_entry({"name": "fs", "transport": "stdio",
                                  "command": "npx"})
        cfg_mod.set_risk_overrides("fs", "high", {"delete": "critical"})
        cfg = cfg_mod.set_risk_overrides("fs", None, None)
        srv = cfg.server("fs")
        assert srv.risk_override is None
        assert dict(srv.tool_risk) == {}

    def test_preserves_connection_fields(self, cfg_dir):
        # A risk edit must not touch command/args/url/auth — the user's
        # connection is preserved (and a literal hand-written token with
        # it, though the API never introduces one).
        cfg_mod.add_server_entry({"name": "fs", "transport": "stdio",
                                  "command": "npx", "args": ["-y", "pkg"]})
        cfg = cfg_mod.set_risk_overrides("fs", "high", None)
        srv = cfg.server("fs")
        assert srv.command == "npx"
        assert tuple(srv.args) == ("-y", "pkg")

    def test_invalid_level_refused(self, cfg_dir):
        cfg_mod.add_server_entry({"name": "fs", "transport": "stdio",
                                  "command": "npx"})
        with pytest.raises(ValueError):
            cfg_mod.set_risk_overrides("fs", "nonsense", None)

    def test_missing_server_refused(self, cfg_dir):
        with pytest.raises(ValueError):
            cfg_mod.set_risk_overrides("nope", "high", None)


class TestAtomicityAndRoundTrip:
    def test_existing_file_preserved_on_failed_write(self, cfg_dir):
        cfg_mod.add_server_entry({"name": "fs", "transport": "stdio",
                                  "command": "npx"})
        before = (cfg_dir / "mcp_config.yml").read_text()
        with pytest.raises(ValueError):
            cfg_mod.add_server_entry({"name": "broken"})  # invalid
        after = (cfg_dir / "mcp_config.yml").read_text()
        assert before == after  # unchanged on a refused write

    def test_hand_broken_entry_elsewhere_is_not_clobbered(self, cfg_dir):
        # The operator's own broken entry stays where it is; the write
        # path neither fixes nor removes it (the loader keeps skipping
        # it exactly as before).
        (cfg_dir / "mcp_config.yml").write_text(yaml.safe_dump({"servers": [
            {"name": "broken", "transport": "wat"},  # invalid transport
            {"name": "good", "transport": "stdio", "command": "x"},
        ]}))
        cfg = cfg_mod.add_server_entry({"name": "new", "transport": "stdio",
                                         "command": "y"})
        names = [s.name for s in cfg.servers]
        assert "good" in names and "new" in names
        # The broken entry is still in the raw file (preserved, skipped).
        raw = yaml.safe_load((cfg_dir / "mcp_config.yml").read_text())
        raw_names = [e.get("name") for e in raw["servers"]]
        assert "broken" in raw_names


# ---------------------------------------------------------------------------
# B5 routes
# ---------------------------------------------------------------------------

class TestAddServerRoute:
    def test_add_returns_snapshot(self, client, cfg_dir):
        r = client.post("/api/mcp/servers", json={
            "name": "fs", "transport": "stdio",
            "command": "npx", "args": ["-y", "pkg"],
        })
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["enabled"] is True
        assert any(s["name"] == "fs" for s in body["servers"])

    def test_duplicate_is_400(self, client, cfg_dir):
        client.post("/api/mcp/servers", json={
            "name": "fs", "transport": "stdio", "command": "npx"})
        r = client.post("/api/mcp/servers", json={
            "name": "fs", "transport": "stdio", "command": "other"})
        assert r.status_code == 400

    def test_literal_token_refused(self, client, cfg_dir):
        r = client.post("/api/mcp/servers", json={
            "name": "linear", "transport": "http", "url": "https://x",
            "auth": {"type": "bearer", "token": "secret-value"},
        })
        assert r.status_code == 400
        assert "token_env" in r.text
        # And nothing was written.
        assert not (cfg_dir / "mcp_config.yml").exists()

    def test_token_env_accepted(self, client, cfg_dir):
        r = client.post("/api/mcp/servers", json={
            "name": "linear", "transport": "http", "url": "https://x",
            "auth": {"type": "bearer", "token_env": "LINEAR_TOKEN"},
        })
        assert r.status_code == 200, r.text
        raw = yaml.safe_load((cfg_dir / "mcp_config.yml").read_text())
        assert raw["servers"][0]["auth"]["token_env"] == "LINEAR_TOKEN"
        assert "token" not in raw["servers"][0]["auth"]

    def test_malformed_json_is_400(self, client):
        r = client.post("/api/mcp/servers",
                        data="{not json",
                        headers={"Content-Type": "application/json"})
        assert r.status_code == 400


class TestRemoveServerRoute:
    def test_remove_returns_snapshot(self, client, cfg_dir):
        client.post("/api/mcp/servers", json={
            "name": "fs", "transport": "stdio", "command": "npx"})
        r = client.delete("/api/mcp/servers/fs")
        assert r.status_code == 200, r.text
        assert all(s["name"] != "fs" for s in r.json()["servers"])

    def test_missing_is_400(self, client):
        r = client.delete("/api/mcp/servers/nope")
        assert r.status_code == 400


class TestSetRiskRoute:
    def test_set_override(self, client, cfg_dir):
        client.post("/api/mcp/servers", json={
            "name": "fs", "transport": "stdio", "command": "npx"})
        r = client.put("/api/mcp/servers/fs/risk", json={
            "risk_override": "high", "tool_risk": {"delete": "critical"},
        })
        assert r.status_code == 200, r.text
        srv = next(s for s in r.json()["servers"] if s["name"] == "fs")
        assert srv["risk_override"] == "high"
        assert srv["tool_risk"]["delete"] == "critical"

    def test_clear_with_null(self, client, cfg_dir):
        client.post("/api/mcp/servers", json={
            "name": "fs", "transport": "stdio", "command": "npx"})
        client.put("/api/mcp/servers/fs/risk", json={
            "risk_override": "high", "tool_risk": {"delete": "critical"}})
        r = client.put("/api/mcp/servers/fs/risk", json={
            "risk_override": None, "tool_risk": None})
        assert r.status_code == 200, r.text
        srv = next(s for s in r.json()["servers"] if s["name"] == "fs")
        assert srv["risk_override"] is None
        assert srv["tool_risk"] == {}

    def test_invalid_level_is_400(self, client, cfg_dir):
        client.post("/api/mcp/servers", json={
            "name": "fs", "transport": "stdio", "command": "npx"})
        r = client.put("/api/mcp/servers/fs/risk", json={
            "risk_override": "nonsense"})
        assert r.status_code == 400

    def test_missing_server_is_400(self, client):
        r = client.put("/api/mcp/servers/nope/risk", json={
            "risk_override": "high"})
        assert r.status_code == 400


class TestCapabilityGate:
    def test_status_off_when_capability_disabled(self, cfg_dir, capability_registry):
        capability_registry.set_capability("mcp_client", False)
        app = FastAPI()
        app.include_router(mcp_routes.router, prefix="/api")
        c = TestClient(app)
        body = c.get("/api/mcp/status").json()
        assert body["enabled"] is False
        assert body["servers"] == []

    def test_edit_refused_when_capability_disabled(self, cfg_dir, capability_registry):
        capability_registry.set_capability("mcp_client", False)
        app = FastAPI()
        app.include_router(mcp_routes.router, prefix="/api")
        c = TestClient(app)
        r = c.post("/api/mcp/servers", json={
            "name": "fs", "transport": "stdio", "command": "npx"})
        assert r.status_code == 409
        assert not (cfg_dir / "mcp_config.yml").exists()
