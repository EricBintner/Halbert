# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Test: peer prompts cannot invoke restricted tools on the Desktop.

Implements finding C4 / L15 from the federated multi-node review.

C4 — The peer tool allowlist restricts what tools a peer-initiated
generation can call. This test verifies that:
1. Allowed tools (search_knowledge, get_config_structure, etc.) pass through.
2. Denied tools (get_config_value, run_scanner, approve_proposal, etc.)
   are filtered out.
3. The allowlist and denylist do not overlap (self-check).
4. An empty tool list returns empty (no false positives).
"""
import pytest

from halbert_core.federation.tool_allowlist import (
    PEER_ALLOWED_TOOLS,
    PEER_DENIED_TOOLS,
    is_tool_allowed_for_peer,
    filter_tools_for_peer,
)


class TestPeerToolAllowlist:
    """Verify the peer tool allowlist filters correctly."""

    def test_allowed_tools_pass_through(self):
        """Tools in the allowlist are permitted."""
        for tool in PEER_ALLOWED_TOOLS:
            assert is_tool_allowed_for_peer(tool), f"{tool} should be allowed"

    def test_denied_tools_are_filtered(self):
        """Tools in the denylist are rejected."""
        for tool in PEER_DENIED_TOOLS:
            assert not is_tool_allowed_for_peer(tool), f"{tool} should be denied"

    def test_unknown_tool_is_denied(self):
        """A tool not in the allowlist is denied (default-deny)."""
        assert not is_tool_allowed_for_peer("some_random_tool")
        assert not is_tool_allowed_for_peer("file_read")
        assert not is_tool_allowed_for_peer("shell_exec")

    def test_allowlist_and_denylist_do_not_overlap(self):
        """No tool is in both allowlist and denylist (security invariant)."""
        overlap = PEER_ALLOWED_TOOLS & PEER_DENIED_TOOLS
        assert not overlap, f"Overlap found: {overlap}"

    def test_filter_tools_for_peer_removes_denied(self):
        """filter_tools_for_peer removes denied tools from a list."""
        tools = ["search_knowledge", "get_config_value", "get_config_structure", "run_scanner"]
        filtered = filter_tools_for_peer(tools)
        assert "search_knowledge" in filtered
        assert "get_config_structure" in filtered
        assert "get_config_value" not in filtered
        assert "run_scanner" not in filtered
        assert len(filtered) == 2

    def test_filter_empty_list_returns_empty(self):
        """Filtering an empty list returns an empty list."""
        assert filter_tools_for_peer([]) == []

    def test_filter_all_allowed_returns_unchanged(self):
        """A list of all-allowed tools is returned unchanged."""
        tools = list(PEER_ALLOWED_TOOLS)
        filtered = filter_tools_for_peer(tools)
        assert set(filtered) == set(tools)

    def test_filter_all_denied_returns_empty(self):
        """A list of all-denied tools returns an empty list."""
        tools = list(PEER_DENIED_TOOLS)
        filtered = filter_tools_for_peer(tools)
        assert filtered == []

    def test_critical_tools_are_in_denylist(self):
        """The most dangerous tools are explicitly in the denylist."""
        critical = {"get_config_value", "run_scanner", "approve_proposal", "ha_call_service"}
        assert critical.issubset(PEER_DENIED_TOOLS)

    def test_secure_model_related_tools_denied(self):
        """Tools that could expose secure_model config are denied."""
        # get_being_config may contain the secure_model endpoint URL
        assert "get_being_config" in PEER_DENIED_TOOLS
