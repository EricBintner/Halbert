# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""MCP get_findings / get_proposals / get_proactive_events / search_knowledge
against the REAL stores and a client stub with the REAL signature.

The previous tests mocked store methods that did not exist, so every live
call returned {'error': "'FindingStore' object has no attribute
'list_findings'"} and search_knowledge raised TypeError on the client's
signature (MCP-01, MCP-02, C2-05).
"""
from __future__ import annotations

import inspect
import json

import pytest

from halbert_core.findings.proposals import Proposal, ProposalStore
from halbert_core.findings.store import Finding, FindingStore
from halbert_core.mcp.server import MCPServer


@pytest.fixture
def server():
    return MCPServer(instance_name="test", hostname="test-host")


def _call(server, tool, args=None):
    req = {
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": tool, "arguments": args or {}},
    }
    resp = server.handle_request(req)
    assert "result" in resp, resp
    return json.loads(resp["result"]["content"][0]["text"])


@pytest.fixture
def stores(tmp_path, monkeypatch):
    from halbert_core.findings import proposals as proposals_mod
    from halbert_core.findings import store as store_mod

    db = str(tmp_path / "findings.db")
    fs = FindingStore(db_path=db)
    ps = ProposalStore(db_path=db)
    monkeypatch.setattr(store_mod, "FindingStore", lambda: fs)
    monkeypatch.setattr(proposals_mod, "ProposalStore", lambda: ps)
    return fs, ps


def _finding(title, severity="warning", detector="permissions_hygiene"):
    return Finding(
        id="", detector=detector, severity=severity, title=title,
        description="d", why_now="triggered by sweep",
        why_care="key readable by others", why_so="mode 0644 on id_rsa",
        why_trust=["~/.ssh/id_rsa:mode"], affected_paths=["~/.ssh/id_rsa"],
    )


class TestGetFindings:
    def test_open_findings_carry_the_four_whys(self, server, stores):
        fs, _ = stores
        fid = fs.add(_finding("Loose key"))
        result = _call(server, "get_findings")
        assert "error" not in result, result
        assert [f["id"] for f in result["findings"]] == [fid]
        f = result["findings"][0]
        assert f["why_now"] == "triggered by sweep"
        assert f["why_care"] == "key readable by others"
        assert f["why_so"] == "mode 0644 on id_rsa"
        assert f["why_trust"] == ["~/.ssh/id_rsa:mode"]

    def test_status_and_severity_filters(self, server, stores):
        fs, _ = stores
        crit = fs.add(_finding("crit", severity="critical"))
        fs.add(_finding("warn"))
        dismissed = fs.add(_finding("gone"))
        fs.dismiss(dismissed, "no")

        assert {f["id"] for f in _call(server, "get_findings", {"status": "all"})["findings"]} == {
            crit, fs.list_all()[1].id, dismissed
        }
        assert [f["id"] for f in _call(server, "get_findings", {"severity": "critical"})["findings"]] == [crit]
        assert [f["id"] for f in _call(server, "get_findings", {"status": "dismissed"})["findings"]] == [dismissed]

    def test_limit(self, server, stores):
        fs, _ = stores
        for i in range(3):
            fs.add(_finding(f"f{i}"))
        assert len(_call(server, "get_findings", {"limit": 2})["findings"]) == 2

    def test_unknown_status_is_an_error_not_a_crash(self, server, stores):
        result = _call(server, "get_findings", {"status": "bogus"})
        assert result["findings"] == []
        assert "bogus" in result["error"]


class TestGetProposals:
    def test_pending_proposals_carry_dry_run_and_blast_radius(self, server, stores):
        fs, ps = stores
        fid = fs.add(_finding("Loose key"))
        pid = ps.add(Proposal(
            id="", finding_id=fid, action="chmod 600 ~/.ssh/id_rsa",
            changes=[{"path": "~/.ssh/id_rsa", "action": "chmod", "mode": "600"}],
            dry_run_result={"ok": True}, blast_radius=["sshd.service"],
        ))
        rejected = ps.add(Proposal(id="", finding_id=fid, action="x"))
        ps.reject(rejected, "no")

        result = _call(server, "get_proposals")
        assert "error" not in result, result
        assert [p["id"] for p in result["proposals"]] == [pid]
        p = result["proposals"][0]
        assert p["dry_run_result"] == {"ok": True}
        assert p["blast_radius"] == ["sshd.service"]
        assert p["changes"][0]["action"] == "chmod"

    def test_status_all(self, server, stores):
        fs, ps = stores
        fid = fs.add(_finding("f"))
        a = ps.add(Proposal(id="", finding_id=fid, action="a"))
        b = ps.add(Proposal(id="", finding_id=fid, action="b"))
        ps.reject(b, "no")
        assert {p["id"] for p in _call(server, "get_proposals", {"status": "all"})["proposals"]} == {a, b}
        assert [p["id"] for p in _call(server, "get_proposals", {"status": "rejected"})["proposals"]] == [b]


class TestGetProactiveEvents:
    def test_reads_the_shared_bus_not_a_fresh_one(self, server, monkeypatch):
        import asyncio
        from halbert_core.proactive import events as events_mod

        bus = events_mod.ProactiveEventBus()
        monkeypatch.setattr(events_mod, "get_event_bus", lambda: bus)
        ev = events_mod.ProactiveEvent.create(
            type="finding", severity="warning", title="Loose key", body="b",
            why={"now": "n", "care": "c", "so": "s", "trust": []},
        )
        asyncio.run(bus.publish(ev))

        result = _call(server, "get_proactive_events")
        assert "error" not in result, result
        assert [e["id"] for e in result["events"]] == [ev.id]
        assert result["events"][0]["why"]["care"] == "c"


class _StubClient:
    """Same signature as SourcePrepClient.search / get_context."""

    instances: list = []

    def __init__(self, *args, **kwargs):
        self.calls = []
        _StubClient.instances.append(self)

    def search(self, query, k=8, min_score=0.15, project_id=None):
        self.calls.append(("search", query, k))
        return {"data": {"results": [
            {"source_path": "docs/arch-wiki/ssh.md", "score": 0.91,
             "text": "OpenSSH keys must be mode 600 " * 40},
            {"path": "host/etc/ssh/sshd_config", "score": 0.4,
             "content": "Port 22"},
        ]}}

    def get_context(self, query="", k=5, max_chars=60000, structured=True,
                    trace_expand=True, min_score=0.15, project_id=None,
                    scope=None, scope_mode="hard"):
        self.calls.append(("context", query, k, scope))
        return {"data": {"chunks": [
            {"source_path": "docs/macos/launchd.md", "score": 0.8,
             "text": "launchd plists live in ~/Library/LaunchAgents"},
        ], "context": "..."}}


@pytest.fixture
def client_stub(monkeypatch):
    from halbert_core.integrations import sourceprep_client as sp_mod
    from halbert_core.integrations.sourceprep_client import SourcePrepClient

    # Guard the stub against signature drift in the real client.
    def _shape(fn):
        return [(q.name, q.default) for q in inspect.signature(fn).parameters.values()]

    assert _shape(_StubClient.search) == _shape(SourcePrepClient.search)
    assert _shape(_StubClient.get_context) == _shape(SourcePrepClient.get_context)
    _StubClient.instances = []
    monkeypatch.setattr(sp_mod, "SourcePrepClient", _StubClient)
    return _StubClient


class TestSearchKnowledge:
    def test_unscoped_search_uses_k_and_normalises(self, server, client_stub):
        result = _call(server, "search_knowledge", {"query": "ssh key permissions", "limit": 3})
        assert "error" not in result, result
        assert client_stub.instances[0].calls == [("search", "ssh key permissions", 3)]
        assert result["query"] == "ssh key permissions"
        first, second = result["results"]
        assert set(first) == {"title", "source", "score", "snippet"}
        assert first["title"] == "ssh.md"
        assert first["source"] == "docs/arch-wiki/ssh.md"
        assert first["score"] == 0.91
        assert first["snippet"].startswith("OpenSSH keys must be mode 600")
        assert len(first["snippet"]) <= 500
        assert second["source"] == "host/etc/ssh/sshd_config"
        assert second["snippet"] == "Port 22"

    def test_scoped_search_routes_to_the_context_endpoint(self, server, client_stub):
        result = _call(server, "search_knowledge", {"query": "launch agents", "scope": "knowledge_macos"})
        assert "error" not in result, result
        assert client_stub.instances[0].calls == [("context", "launch agents", 5, "knowledge_macos")]
        assert result["results"] == [{
            "title": "launchd.md",
            "source": "docs/macos/launchd.md",
            "score": 0.8,
            "snippet": "launchd plists live in ~/Library/LaunchAgents",
        }]

    def test_daemon_failure_is_an_error_payload(self, server, monkeypatch):
        from halbert_core.integrations import sourceprep_client as sp_mod

        class _Down:
            def __init__(self, *a, **k):
                pass

            def search(self, query, k=8, min_score=0.15, project_id=None):
                raise ConnectionError("daemon down")

        monkeypatch.setattr(sp_mod, "SourcePrepClient", _Down)
        result = _call(server, "search_knowledge", {"query": "x"})
        assert result["results"] == []
        assert "daemon down" in result["error"]
