# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for the R2-OBS-1 camera-gate registration guard (Packet 05 C2).

gate_response() is wired at the single dispatch choke point (VIS-1); the
guard exists so that wiring cannot be silently dropped: a camera/vision
tool cannot be registered or dispatched unless the dispatch source still
routes handlers through the gate.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from halbert_core.mcp import server as mcp_server


@pytest.fixture(autouse=True)
def _reset_wiring_cache():
    """Each test re-evaluates the wiring verdict from scratch — the
    module-level cache must not leak one test's verdict into the next."""
    saved = mcp_server._CAMERA_GATE_WIRED
    mcp_server._CAMERA_GATE_WIRED = None
    try:
        yield
    finally:
        mcp_server._CAMERA_GATE_WIRED = saved


@pytest.fixture
def unwired(monkeypatch):
    """Simulate the gate wiring having been dropped from dispatch."""
    monkeypatch.setattr(
        mcp_server, "_camera_gate_wired_at_dispatch", lambda: False
    )


def test_camera_tool_without_gate_raises(unwired):
    with pytest.raises(RuntimeError, match="camera gate"):
        mcp_server._assert_camera_gate_wired("frigate_snapshot")


@pytest.mark.parametrize(
    "tool_id",
    ["frigate_snapshot", "vision_describe", "camera_list", "Frigate_Events"],
)
def test_camera_tool_with_gate_passes(tool_id):
    # Current main wiring: the dispatch choke point routes every handler
    # through gate_response() inside mcp_response().
    mcp_server._assert_camera_gate_wired(tool_id)


def test_non_camera_tool_never_raises_even_when_unwired(unwired):
    mcp_server._assert_camera_gate_wired("get_vitals")
    mcp_server._assert_camera_gate_wired("run_scanner")


def test_static_registry_passes_registration_check():
    """The import-time registration check over TOOL_HANDLERS passes with
    today's registry (no camera tools) and the real wiring."""
    for tool_id in list(mcp_server.TOOL_HANDLERS):
        mcp_server._assert_camera_gate_wired(tool_id)


def test_runtime_registration_check_covers_late_entries(unwired):
    """A camera tool added to TOOL_HANDLERS after import is caught by the
    dispatch-loop guard, not just the import-time one."""
    mcp_server.TOOL_HANDLERS["frigate_snapshot"] = lambda params: {}
    try:
        with pytest.raises(RuntimeError, match="frigate_snapshot"):
            mcp_server._assert_camera_gate_wired("frigate_snapshot")
    finally:
        del mcp_server.TOOL_HANDLERS["frigate_snapshot"]


def test_dispatch_rejects_camera_tool_when_gate_unwired(monkeypatch, unwired):
    """End to end: with the gate unwired, a tools/call for a camera tool
    fails loudly (redacted catch-all error) rather than egressing."""
    mcp_server.TOOL_HANDLERS["frigate_snapshot"] = (
        lambda params: {"snapshot": "jpeg"}
    )
    try:
        out = mcp_server.MCPServer().handle_request({
            "jsonrpc": "2.0", "id": 1,
            "method": "tools/call",
            "params": {"name": "frigate_snapshot", "arguments": {}},
        })
    finally:
        del mcp_server.TOOL_HANDLERS["frigate_snapshot"]
    assert "camera gate" in out["error"]["message"]


def test_wiring_detection_is_real_not_stubbed():
    """The guard's source-level detection returns True against today's
    dispatch — pins that the guard verifies the real wiring."""
    assert mcp_server._camera_gate_wired_at_dispatch() is True


def test_wiring_detection_fails_closed_when_source_unavailable(monkeypatch):
    """If the dispatch source cannot be inspected, the guard treats the
    gate as unwired (fail closed) rather than trusting silence."""
    def _stub(self, request):
        return None  # not defined in a real source file

    monkeypatch.setattr(mcp_server.MCPServer, "handle_request", _stub)
    assert mcp_server._camera_gate_wired_at_dispatch() is False