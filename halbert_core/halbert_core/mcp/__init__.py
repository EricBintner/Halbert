# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""MCP server subsystem for external LLM client integration.

Security boundary: the camera_gate module strips image data from
any response that touches camera/vision data. No raw frames, snapshots,
or base64 images ever leave the local host through MCP.
"""
