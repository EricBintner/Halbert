# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Standalone human-run CLI tools.

These modules are NOT part of the agent or MCP tool surface. They are
deliberate-use tools a human runs to check their own credentials. The
secret value is sent to the issuing service's API (not an LLM), which
breaks the Tier 2 architectural guarantee — so they live here, outside
the config/ package, to make the boundary physically visible.
"""
