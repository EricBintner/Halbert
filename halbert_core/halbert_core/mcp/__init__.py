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
camera/vision data. No raw frames, snapshots, or base64 images ever leave
the local host through MCP.
"""
