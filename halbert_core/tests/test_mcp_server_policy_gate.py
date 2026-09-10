# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""R-09 Phase E: Halbert-as-MCP-server tools declare what gates them.

A17-G9, scoped as a finding inside the founder-ruled B6 audit -- one gate
function at the existing dispatch choke point, not a rebuild of
``TOOL_HANDLERS``.

What the audit found, stated precisely: the eighteen tools this server
exposes do not run through ``ToolSafetyFramework`` the way the agent's
own tools do, but the four that change something are not ungated --
``run_scanner`` requires ``confirm=True``, ``approve_proposal`` requires
``confirm`` plus a typed phrase for a critical proposal,
``ha_call_service`` runs through the AutonomyGate, and
``set_autonomy_level`` requires the escalation phrase. Each author wrote
their own ask.

What was missing is a PLACE where the question is asked at all: nothing
said which tools this door serves, nothing recorded what gates each one,
and a tool added tomorrow would dispatch with whatever gate its author
remembered -- or none. These tests pin the declaration and the refusal
of anything undeclared. They deliberately do not add a second ask on top
of the existing ones: two asks for one action is how a confirmation stops
meaning anything.
"""

import pytest

from halbert_core.mcp.server import (
    TOOL_HANDLERS,
    audit_mcp_tool_classifications,
    mcp_tool_policy,
)


def test_a_read_only_tool_is_served_with_no_gate():
    decision = mcp_tool_policy("get_vitals", {})
    assert decision.allowed is True
    assert decision.gated_by == ""


def test_a_state_changing_tool_names_the_gate_that_guards_it():
    decision = mcp_tool_policy("set_autonomy_level", {"level": "high"})
    assert decision.allowed is True
    assert "phrase" in decision.gated_by


def test_an_unclassified_tool_is_refused():
    decision = mcp_tool_policy("not_a_tool", {})
    assert decision.allowed is False
    assert decision.reason_code == "mcp_tool_unclassified"
    assert "not_a_tool" in decision.message


def test_every_registered_tool_is_classified():
    """A tool in TOOL_HANDLERS that nobody classified is a finding."""
    unclassified = [
        name for name in TOOL_HANDLERS
        if not mcp_tool_policy(name, {}).allowed
    ]
    assert unclassified == [], unclassified


def test_every_state_changing_tool_names_a_gate():
    audit = audit_mcp_tool_classifications()
    for name, disposition in audit.items():
        if "changes state" in disposition:
            assert "gated by" in disposition, name


def test_the_audit_record_covers_the_whole_registry():
    assert set(audit_mcp_tool_classifications()) == set(TOOL_HANDLERS)


def test_the_gate_is_wired_at_the_dispatch_choke_point():
    """The same discipline the camera gate uses: read from the dispatch
    source, so an edit that drops the gate is a loud failure rather than
    a silent bypass."""
    import inspect

    from halbert_core.mcp.server import MCPServer

    source = inspect.getsource(MCPServer.handle_request)
    assert "mcp_tool_policy(" in source


def test_an_unclassified_tool_answers_an_error_not_a_result(monkeypatch):
    import halbert_core.mcp.server as server_mod

    monkeypatch.setitem(
        server_mod.TOOL_HANDLERS, "brand_new_tool",
        lambda params: server_mod.mcp_response({"ok": True}),
    )
    server = server_mod.MCPServer()
    response = server.handle_request({
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "brand_new_tool", "arguments": {}},
    })
    assert "error" in response, response
    assert "brand_new_tool" in response["error"]["message"]


def test_a_classified_tool_still_reaches_its_handler(monkeypatch):
    import halbert_core.mcp.server as server_mod

    called = []

    def _fake(params):
        called.append(params)
        return server_mod.mcp_response({"ok": True})

    monkeypatch.setitem(server_mod.TOOL_HANDLERS, "get_vitals", _fake)
    server = server_mod.MCPServer()
    response = server.handle_request({
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "get_vitals", "arguments": {}},
    })
    assert called, "a classified tool must still run"
    assert "result" in response
