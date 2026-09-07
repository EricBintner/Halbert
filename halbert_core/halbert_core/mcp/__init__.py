# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Halbert MCP server package.

Exposes Halbert's runtime state, deterministic config DB, and agent actions
to external MCP clients (WarpCLI, Claude Code, Devin, Cursor).

Security boundary: every tool response passes through ``_mcp_response()``
in ``response.py`` before returning to the client.  That helper runs
``redact_text()`` over the payload so that no credential in the host's
config tree reaches an external AI client's cloud model.  Internal reads
(Halbert's own agent) keep the raw path — the boundary is the MCP response,
not Halbert's internal data flow.

The camera_gate module strips image data from any response that touches
camera/vision data. It IS wired into server.py's dispatch (VIS-1,
2026-09-06): every tools/call returns through
``mcp_response(gate_response(tool_name, handler(tool_args)))`` at the
single choke point — the gate is universal, not per-tool. And the
wiring is enforced, not documented (R2-OBS-1, Packet 05 C2): a tool
whose name marks it camera/vision (frigate/vision/camera) cannot be
registered in TOOL_HANDLERS — or dispatched, if added after import —
unless the dispatch source still routes handlers through the gate
(``server._assert_camera_gate_wired``). An edit that drops the gate
fails loudly at registration/dispatch instead of reopening a silent
image-data egress path.
"""
