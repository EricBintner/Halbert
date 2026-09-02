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
camera/vision data — but it is NOT currently wired into server.py's
dispatch (R2-OBS-1): TOOL_HANDLERS registers no frigate/vision/camera
tool today, so the gate protects nothing yet. This is not presently a
gap in practice (there is no camera-data-returning tool surface to leak
through), but it is a landmine for whoever adds one: read camera_gate.py
and call ``gate_response()`` around the new handler(s) before assuming
this protection is already active.
"""
