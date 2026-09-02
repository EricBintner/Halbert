# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for the MCP server — JSON-RPC protocol and tool dispatch."""
from __future__ import annotations

import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from halbert_core.mcp.server import MCPServer, TOOL_HANDLERS, TOOL_SCHEMAS


@pytest.fixture
def server():
    return MCPServer(instance_name="test", hostname="test-host")


class TestProtocol:
    """JSON-RPC 2.0 protocol handling."""

    def test_initialize(self, server):
        req = {"jsonrpc": "2.0", "id": 1, "method": "initialize"}
        resp = server.handle_request(req)
        assert resp["jsonrpc"] == "2.0"
        assert resp["id"] == 1
        assert "result" in resp
        assert "protocolVersion" in resp["result"]
        assert "serverInfo" in resp["result"]
        assert "halbert-test" in resp["result"]["serverInfo"]["name"]

    def test_ping(self, server):
        req = {"jsonrpc": "2.0", "id": 2, "method": "ping"}
        resp = server.handle_request(req)
        assert resp["id"] == 2
        assert "result" in resp

    def test_notification_no_response(self, server):
        """Notifications (no id) should return None."""
        req = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        resp = server.handle_request(req)
        assert resp is None

    def test_unknown_method(self, server):
        req = {"jsonrpc": "2.0", "id": 3, "method": "bogus"}
        resp = server.handle_request(req)
        assert "error" in resp
        assert resp["error"]["code"] == -32601

    def test_tools_list(self, server):
        req = {"jsonrpc": "2.0", "id": 4, "method": "tools/list"}
        resp = server.handle_request(req)
        assert "result" in resp
        tools = resp["result"]["tools"]
        assert len(tools) == 18
        # Instance name should be in descriptions
        assert "[test]" in tools[0]["description"]

    def test_tools_list_has_all_expected(self, server):
        req = {"jsonrpc": "2.0", "id": 5, "method": "tools/list"}
        resp = server.handle_request(req)
        tool_names = {t["name"] for t in resp["result"]["tools"]}
        expected = {
            "get_vitals", "get_discoveries", "get_findings", "get_proposals",
            "get_proactive_events", "get_being_config", "get_config_value",
            "get_config_structure", "get_config_diff", "get_config_dependencies",
            "search_knowledge", "run_scanner", "approve_proposal",
            # HA tools (Phase 1)
            "ha_get_entities", "ha_get_entity_state", "ha_call_service",
            "get_autonomy_level", "set_autonomy_level",
        }
        assert tool_names == expected


class TestToolCall:
    """Tool dispatch via tools/call."""

    def _call(self, server, tool_name, args=None):
        req = {
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": tool_name, "arguments": args or {}},
        }
        resp = server.handle_request(req)
        assert "result" in resp
        content = resp["result"]["content"][0]["text"]
        return json.loads(content)

    def test_unknown_tool(self, server):
        req = {
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "bogus", "arguments": {}},
        }
        resp = server.handle_request(req)
        assert "error" in resp
        assert resp["error"]["code"] == -32601

    def test_get_vitals(self, server):
        result = self._call(server, "get_vitals")
        # psutil may or may not be available
        assert "error" in result or "cpu_percent" in result

    def test_get_being_config(self, server):
        result = self._call(server, "get_being_config")
        # Should have voice, proactivity fields
        assert "voice" in result or "error" in result
        # Security config should be stripped
        assert "security" not in result

    def test_get_config_value_missing_params(self, server):
        result = self._call(server, "get_config_value")
        assert "error" in result

    def test_get_config_value_not_found(self, server):
        result = self._call(server, "get_config_value", {
            "path": "/nonexistent/path.conf", "key": "Port"
        })
        assert "error" in result

    def test_get_config_structure_missing_path(self, server):
        result = self._call(server, "get_config_structure")
        assert "error" in result

    def test_get_config_diff(self, server):
        result = self._call(server, "get_config_diff")
        assert "changes" in result

    def test_get_config_dependencies_missing_path(self, server):
        result = self._call(server, "get_config_dependencies")
        assert "error" in result

    def test_search_knowledge_missing_query(self, server):
        result = self._call(server, "search_knowledge")
        assert "error" in result

    def test_run_scanner_missing_type(self, server):
        result = self._call(server, "run_scanner")
        assert "error" in result

    def test_approve_proposal_missing_id(self, server):
        result = self._call(server, "approve_proposal")
        assert "error" in result
        assert "proposal_id" in result["error"]

    def test_approve_proposal_requires_confirm(self, server):
        result = self._call(server, "approve_proposal", {"proposal_id": "abc123"})
        assert "error" in result
        assert "confirm" in result["error"]

    def test_approve_proposal_not_found(self, server):
        result = self._call(server, "approve_proposal", {
            "proposal_id": "nonexistent-id",
            "confirm": True,
        })
        assert "error" in result
        assert "not found" in result["error"]


class TestTierRouting:
    """Config value tier routing through the MCP server."""

    def test_password_is_redacted(self, server, tmp_path, monkeypatch):
        """A password value should come back redacted, not raw."""
        # Create a config file with a password
        config_file = tmp_path / "test.conf"
        config_file.write_text("[Service]\nPassword=hunter2\n")

        # Patch being config to use defaults (local_only for secrets)
        from halbert_core.config.being_config import BeingConfig, SecurityConfig
        from halbert_core.config import being_config as bc_module

        # Patch load_being_config to return a config with local_only
        def mock_load():
            bc = BeingConfig()
            bc.security = SecurityConfig(secret_tier="local_only")
            return bc

        monkeypatch.setattr("halbert_core.config.being_config.load_being_config", mock_load)

        # Patch the canon DB to have our file
        from halbert_core.config import queries as q_module
        from halbert_core.config.parser import parse as parse_config

        def mock_get_current_canon(path):
            if str(config_file) in path:
                return parse_config(str(config_file))
            return None

        monkeypatch.setattr(q_module, "_get_current_canon", mock_get_current_canon)
        # Allowlist: the path must appear in the snapshot manifest.
        monkeypatch.setattr(q_module, "_load_latest_snapshot",
                            lambda: [{"path": str(config_file), "hash": "x"}])

        req = {
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "get_config_value",
                       "arguments": {"path": str(config_file), "key": "Password"}},
        }
        resp = server.handle_request(req)
        content = json.loads(resp["result"]["content"][0]["text"])

        assert content["tier"] == 2
        assert "value" not in content
        assert content.get("redacted") is True
        assert "hunter2" not in json.dumps(content)


class TestEgressBoundary:
    """mcp_response() is applied to config tools."""

    def test_config_value_passes_through_mcp_response(self, server, tmp_path, monkeypatch):
        """The MCP response boundary should redact secrets in tool output."""
        config_file = tmp_path / "test.conf"
        config_file.write_text("[Service]\nPassword=hunter2\nPort=2222\n")

        from halbert_core.config import queries as q_module
        from halbert_core.config.parser import parse as parse_config

        def mock_get_current_canon(path):
            if str(config_file) in path:
                return parse_config(str(config_file))
            return None

        monkeypatch.setattr(q_module, "_get_current_canon", mock_get_current_canon)
        # Allowlist: the path must appear in the snapshot manifest.
        monkeypatch.setattr(q_module, "_load_latest_snapshot",
                            lambda: [{"path": str(config_file), "hash": "x"}])

        # Request with cloud_ok_acknowledged to get the raw value
        from halbert_core.config.being_config import BeingConfig, SecurityConfig
        def mock_load():
            bc = BeingConfig()
            bc.security = SecurityConfig(secret_tier="cloud_ok_acknowledged")
            return bc
        monkeypatch.setattr("halbert_core.config.being_config.load_being_config", mock_load)

        req = {
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "get_config_value",
                       "arguments": {"path": str(config_file), "key": "Password"}},
        }
        resp = server.handle_request(req)
        content_text = resp["result"]["content"][0]["text"]
        # Even with cloud_ok_acknowledged, the mcp_response boundary
        # should redact the password value in the output
        assert "hunter2" not in content_text


class TestProtocolHardening:
    """JSON-RPC robustness: batch arrays, notifications, validation."""

    def test_batch_array_rejected_not_crash(self, server):
        """A JSON-RPC batch (array) returns -32600 instead of raising."""
        resp = server.handle_request([{"jsonrpc": "2.0", "id": 1, "method": "ping"}])
        assert resp is not None
        assert resp["error"]["code"] == -32600
        assert resp["id"] is None

    def test_notification_unknown_method_no_response(self, server):
        """A notification (no id) never gets a response, not even an error."""
        resp = server.handle_request({"jsonrpc": "2.0", "method": "bogus"})
        assert resp is None

    def test_notification_tools_call_no_response(self, server):
        resp = server.handle_request({
            "jsonrpc": "2.0", "method": "tools/call",
            "params": {"name": "get_vitals", "arguments": {}},
        })
        assert resp is None

    def test_notification_error_path_no_response(self, server):
        """Even an internal error on a notification produces no response."""
        resp = server.handle_request({
            "jsonrpc": "2.0", "method": "tools/call",
            "params": {"name": "get_config_value", "arguments": {"path": None}},
        })
        assert resp is None

    def test_missing_jsonrpc_version_rejected(self, server):
        resp = server.handle_request({"id": 1, "method": "ping"})
        assert resp["error"]["code"] == -32600

    def test_wrong_jsonrpc_version_rejected(self, server):
        resp = server.handle_request({"jsonrpc": "1.0", "id": 1, "method": "ping"})
        assert resp["error"]["code"] == -32600

    def test_missing_method_rejected(self, server):
        resp = server.handle_request({"jsonrpc": "2.0", "id": 1})
        assert resp["error"]["code"] == -32600

    def test_explicit_null_id_gets_response(self, server):
        """An explicit "id": null is an id, not a notification."""
        resp = server.handle_request({"jsonrpc": "2.0", "id": None, "method": "ping"})
        assert resp is not None
        assert resp["id"] is None
        assert "result" in resp


class TestUniversalEgressBoundary:
    """The dispatch layer wraps EVERY tool result in mcp_response()."""

    def test_being_config_strips_ha_credentials(self, server, monkeypatch):
        """get_being_config must never emit the Home Assistant token."""
        from halbert_core.config.being_config import BeingConfig

        def mock_load():
            bc = BeingConfig()
            bc.ha_url = "http://homeassistant.local:8123"
            bc.ha_token = "ha-secret-token-value-123"
            return bc

        monkeypatch.setattr(
            "halbert_core.config.being_config.load_being_config", mock_load)

        req = {
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "get_being_config", "arguments": {}},
        }
        resp = server.handle_request(req)
        content_text = resp["result"]["content"][0]["text"]
        assert "ha-secret-token-value-123" not in content_text
        assert "ha_token" not in content_text
        assert "ha_url" not in content_text

    def test_dispatch_wraps_unwrapped_handler(self, server, monkeypatch):
        """A handler that forgets mcp_response is still redacted at dispatch."""
        monkeypatch.setitem(
            TOOL_HANDLERS, "get_vitals",
            lambda params: {"password": "hunter2", "note": "nothing to see"},
        )
        req = {
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "get_vitals", "arguments": {}},
        }
        resp = server.handle_request(req)
        content_text = resp["result"]["content"][0]["text"]
        assert "hunter2" not in content_text
        assert "<secret>" in content_text


class TestAutonomyEscalationPhrase:
    """REV-02 F1 — raising autonomy via MCP requires the confirmation phrase.

    A client-supplied ``confirm`` boolean is not consent: every paired
    satellite holds a bearer token, so a one-call observe→orchestrate
    escalation must need the same high-friction phrase the dashboard's
    Tier 2 unlock enforces. Decreasing autonomy stays frictionless.
    """

    def _call_set(self, server, args):
        req = {
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "set_autonomy_level", "arguments": args},
        }
        resp = server.handle_request(req)
        return json.loads(resp["result"]["content"][0]["text"])

    def _patch_being(self, monkeypatch, level="observe", overrides=None):
        # _tool_set_autonomy_level goes through update_being_config (R1-F4:
        # one exclusive lock across the whole load-modify-save cycle), not
        # a separate load_being_config/save_being_config pair — so the
        # fake here plays update_being_config's role: run the mutator
        # against the fixture cfg and record what would have been saved.
        from halbert_core.config import being_config as bc
        from halbert_core.config.being_config import BeingConfig

        cfg = BeingConfig()
        cfg.autonomy_level = level
        cfg.autonomy_overrides = dict(overrides or {})
        saved = []

        def fake_update_being_config(mutator, path=None):
            mutator(cfg)
            cfg.validate()
            saved.append(cfg)
            return cfg

        monkeypatch.setattr(bc, "update_being_config", fake_update_being_config)
        return saved

    def test_escalation_without_phrase_rejected(self, server, monkeypatch):
        saved = self._patch_being(monkeypatch, level="observe")
        result = self._call_set(server, {"level": "orchestrate", "confirm": True})
        assert "error" in result
        assert "phrase" in result["error"]
        assert saved == []  # nothing persisted

    def test_escalation_rejection_does_not_echo_phrase(self, server, monkeypatch):
        self._patch_being(monkeypatch, level="observe")
        result = self._call_set(server, {"level": "act", "confirm": True})
        assert "EXPOSE SECRETS" not in json.dumps(result)

    def test_escalation_with_wrong_phrase_rejected(self, server, monkeypatch):
        saved = self._patch_being(monkeypatch, level="observe")
        result = self._call_set(server, {
            "level": "orchestrate", "confirm": True, "phrase": "let me in"})
        assert "error" in result
        assert saved == []

    def test_escalation_with_phrase_accepted(self, server, monkeypatch):
        from halbert_core.config.security_constants import UNLOCK_PHRASE
        saved = self._patch_being(monkeypatch, level="observe")
        result = self._call_set(server, {
            "level": "orchestrate", "confirm": True, "phrase": UNLOCK_PHRASE})
        assert "error" not in result, result
        assert saved and saved[0].autonomy_level == "orchestrate"

    def test_phrase_is_whitespace_and_case_normalised(self, server, monkeypatch):
        saved = self._patch_being(monkeypatch, level="observe")
        result = self._call_set(server, {
            "level": "suggest", "confirm": True, "phrase": "  expose   secrets "})
        assert "error" not in result, result
        assert saved and saved[0].autonomy_level == "suggest"

    def test_decrease_without_phrase_allowed(self, server, monkeypatch):
        saved = self._patch_being(monkeypatch, level="act")
        result = self._call_set(server, {"level": "observe", "confirm": True})
        assert "error" not in result, result
        assert saved and saved[0].autonomy_level == "observe"

    def test_override_escalation_requires_phrase(self, server, monkeypatch):
        saved = self._patch_being(monkeypatch, level="observe")
        result = self._call_set(server, {
            "level": "observe", "confirm": True,
            "overrides": {"lock": "orchestrate"}})
        assert "error" in result
        assert saved == []

    def test_override_escalation_with_phrase_accepted(self, server, monkeypatch):
        from halbert_core.config.security_constants import UNLOCK_PHRASE
        saved = self._patch_being(monkeypatch, level="observe")
        result = self._call_set(server, {
            "level": "observe", "confirm": True,
            "overrides": {"lock": "act"}, "phrase": UNLOCK_PHRASE})
        assert "error" not in result, result
        assert saved and saved[0].autonomy_overrides == {"lock": "act"}

    def test_override_decrease_without_phrase_allowed(self, server, monkeypatch):
        saved = self._patch_being(
            monkeypatch, level="orchestrate", overrides={"lock": "orchestrate"})
        result = self._call_set(server, {
            "level": "orchestrate", "confirm": True,
            "overrides": {"lock": "observe"}})
        assert "error" not in result, result


class TestSetAutonomyLevelRace:
    """R1-F4: set_autonomy_level must not clobber a concurrent relock.

    The old implementation did ``cfg = load_being_config(); ...;
    save_being_config(cfg)`` — two separate lock cycles with an
    unprotected window between them. If another process (e.g. a TTL
    expiry relock) completes its own load-modify-save inside that
    window, this tool's stale ``cfg`` object reverts it on save.

    The fix is to route through ``update_being_config``, which holds
    ONE exclusive lock across the whole load-modify-save cycle. To
    prove it, this test hooks the shared primitive both old and new
    code call — ``being_config_lock`` — so that a genuine concurrent
    actor's own complete, correctly locked load-modify-save cycle (the
    same shape a TTL expiry relock takes) fires the FIRST time any
    lock cycle here releases:

    - Old code's first lock cycle is ``load_being_config``'s own
      (read-only) one — it releases before ``save_being_config``'s
      separate cycle even starts, so the concurrent write lands
      squarely in the gap and gets overwritten by the tool's stale
      object.
    - New code's only lock cycle is ``update_being_config``'s single
      read-modify-write one — it doesn't release until the tool's own
      change is already persisted, so the concurrent write always
      lands after, and a proper load-modify-save (not a stale
      overwrite) can never lose it either way.
    """

    def _call_set(self, server, args):
        req = {
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "set_autonomy_level", "arguments": args},
        }
        resp = server.handle_request(req)
        return json.loads(resp["result"]["content"][0]["text"])

    def test_relock_persisted_between_load_and_save_is_not_clobbered(
            self, server, monkeypatch, tmp_path):
        from contextlib import contextmanager
        from pathlib import Path
        from halbert_core.config import being_config as bc

        path = str(tmp_path / "being.yml")
        cfg = bc.BeingConfig()
        cfg.autonomy_level = "act"
        cfg.security.secret_tier = "cloud_ok_acknowledged"
        bc.save_being_config(cfg, path)

        monkeypatch.setattr(bc, "_default_path", lambda: Path(path))

        real_lock = bc.being_config_lock
        fired = []

        @contextmanager
        def lock_then_maybe_inject_concurrent_relock(*args, **kwargs):
            with real_lock(*args, **kwargs) as acquired:
                yield acquired
            # Runs immediately after THIS lock cycle releases. Guarded so
            # the concurrent actor's own lock use (below) doesn't re-fire.
            if not fired:
                fired.append(True)
                bc.update_being_config(
                    lambda c: setattr(c.security, "secret_tier", "local_only"),
                    path,
                )

        monkeypatch.setattr(bc, "being_config_lock", lock_then_maybe_inject_concurrent_relock)

        result = self._call_set(server, {"level": "suggest", "confirm": True})
        assert "error" not in result, result

        final = bc.load_being_config(path)
        assert final.autonomy_level == "suggest"
        # The concurrent relock must survive — not reverted by a stale,
        # pre-relock config object saved separately from the load.
        assert final.security.secret_tier == "local_only"


class TestHighRiskProposalPhrase:
    """REV-02 F1 — approving a high-risk proposal requires the phrase.

    High-risk = the linked finding is critical, or cannot be loaded
    (fail closed). A proposal from a warning/info finding stays on the
    plain confirm=true gate.
    """

    def _call_approve(self, server, args):
        req = {
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "approve_proposal", "arguments": args},
        }
        resp = server.handle_request(req)
        return json.loads(resp["result"]["content"][0]["text"])

    def _patch_stores(self, monkeypatch, tmp_path, severity="critical",
                      proposal_finding_id="f-crit"):
        from halbert_core.findings import proposals as proposals_mod
        from halbert_core.findings import store as store_mod
        from halbert_core.findings import proposal_generator as gen_mod
        from halbert_core.findings.proposals import ProposalStore, Proposal
        from halbert_core.findings.store import FindingStore, Finding

        fs = FindingStore(db_path=str(tmp_path / "findings.db"))
        ps = ProposalStore(db_path=str(tmp_path / "proposals.db"))
        fs.add(Finding(
            id="f-crit", detector="test", severity=severity,
            title="t", description="d",
            why_now="now", why_care="care", why_so="so"))
        pid = ps.add(Proposal(
            id="", finding_id=proposal_finding_id, action="change something"))

        class _StubGenerator:
            def __init__(self, **kwargs):
                pass

            def execute_proposal(self, proposal_id, reason=""):
                return {"proposal_id": proposal_id, "status": "applied"}

        monkeypatch.setattr(proposals_mod, "ProposalStore", lambda: ps)
        monkeypatch.setattr(store_mod, "FindingStore", lambda: fs)
        monkeypatch.setattr(gen_mod, "ProposalGenerator", _StubGenerator)
        # The handler also constructs these as generator kwargs; stub them
        # so the test touches no real storage.
        from halbert_core.approval import engine as approval_mod
        from halbert_core.tools import write_config as write_mod
        from halbert_core.findings import blast_radius as blast_mod
        monkeypatch.setattr(approval_mod, "ApprovalEngine", lambda: None)
        monkeypatch.setattr(write_mod, "WriteConfig", lambda: None)
        monkeypatch.setattr(blast_mod, "BlastRadiusCalculator", lambda: None)
        return ps, pid

    def test_critical_proposal_requires_phrase(self, server, tmp_path, monkeypatch):
        ps, pid = self._patch_stores(monkeypatch, tmp_path, severity="critical")
        result = self._call_approve(server, {"proposal_id": pid, "confirm": True})
        assert "error" in result
        assert "phrase" in result["error"]
        assert ps.get(pid).status == "pending"  # nothing executed

    def test_critical_proposal_rejection_does_not_echo_phrase(
            self, server, tmp_path, monkeypatch):
        ps, pid = self._patch_stores(monkeypatch, tmp_path, severity="critical")
        result = self._call_approve(server, {"proposal_id": pid, "confirm": True})
        assert "EXPOSE SECRETS" not in json.dumps(result)

    def test_critical_proposal_with_phrase_proceeds(
            self, server, tmp_path, monkeypatch):
        from halbert_core.config.security_constants import UNLOCK_PHRASE
        ps, pid = self._patch_stores(monkeypatch, tmp_path, severity="critical")
        result = self._call_approve(server, {
            "proposal_id": pid, "confirm": True, "phrase": UNLOCK_PHRASE})
        assert "error" not in result, result
        assert result.get("status") == "applied"

    def test_low_risk_proposal_without_phrase_allowed(
            self, server, tmp_path, monkeypatch):
        ps, pid = self._patch_stores(monkeypatch, tmp_path, severity="warning")
        result = self._call_approve(server, {"proposal_id": pid, "confirm": True})
        assert "error" not in result, result
        assert result.get("status") == "applied"

    def test_missing_finding_treated_high_risk(
            self, server, tmp_path, monkeypatch):
        ps, pid = self._patch_stores(
            monkeypatch, tmp_path, severity="warning",
            proposal_finding_id="f-gone")  # not in the FindingStore
        result = self._call_approve(server, {"proposal_id": pid, "confirm": True})
        assert "error" in result
        assert "phrase" in result["error"]


class TestPathAllowlist:
    """Config-query tools may only read paths in the snapshot manifest."""

    def _call(self, server, name, args):
        req = {
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": name, "arguments": args},
        }
        resp = server.handle_request(req)
        return json.loads(resp["result"]["content"][0]["text"])

    def test_arbitrary_path_rejected(self, server, monkeypatch, tmp_path):
        """A path not in the manifest is refused, even if the file exists."""
        secret_file = tmp_path / "shadow"
        secret_file.write_text("root:$6$...")

        from halbert_core.config import queries as q_module
        monkeypatch.setattr(q_module, "_load_latest_snapshot", lambda: [])

        result = self._call(server, "get_config_value",
                            {"path": str(secret_file), "key": "root"})
        assert "not in snapshot manifest" in result.get("error", "")

    def test_manifest_path_allowed(self, server, monkeypatch, tmp_path):
        """A path that IS in the manifest passes the gate."""
        config_file = tmp_path / "test.conf"
        config_file.write_text("[Service]\nPort=2222\n")

        from halbert_core.config import queries as q_module
        from halbert_core.config.parser import parse as parse_config

        monkeypatch.setattr(q_module, "_load_latest_snapshot",
                            lambda: [{"path": str(config_file), "hash": "x"}])
        monkeypatch.setattr(q_module, "_get_current_canon",
                            lambda p: parse_config(str(config_file)) if str(config_file) in p else None)

        result = self._call(server, "get_config_structure",
                            {"path": str(config_file)})
        assert "error" not in result or "not in snapshot" not in result.get("error", "")

    def test_dotdot_traversal_blocked(self, server, monkeypatch, tmp_path):
        """A path with ``..`` that resolves outside the manifest is caught."""
        allowed = tmp_path / "allowed.conf"
        allowed.write_text("[Service]\nPort=2222\n")
        secret = tmp_path / "secret.conf"
        secret.write_text("password=hunter2")

        from halbert_core.config import queries as q_module
        monkeypatch.setattr(q_module, "_load_latest_snapshot",
                            lambda: [{"path": str(allowed), "hash": "x"}])

        # Construct a traversal path that textually starts under allowed
        # but resolves to the secret file.
        traversal = str(allowed.parent / "allowed.conf" / ".." / "secret.conf")
        result = self._call(server, "get_config_structure",
                            {"path": traversal})
        assert "not in snapshot manifest" in result.get("error", "")
