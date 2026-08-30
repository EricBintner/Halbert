# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for the RoleGate safety wrapper."""

import pytest

from halbert_core.tools.safety import ToolSafetyFramework, RiskLevel
from halbert_core.tools.role_gate import RoleGate, ROLE_MAX_RISK


@pytest.fixture
def gate():
    return RoleGate(ToolSafetyFramework())


def test_admin_can_execute_safe(gate):
    """Admin can execute safe operations."""
    r = gate.classify("run_command", {"command": "ls -la"}, speaker_role="admin")
    assert r.allowed is True


def test_admin_can_execute_high_with_confirmation(gate):
    """Admin can execute high-risk ops (base requires confirmation)."""
    r = gate.classify("run_command", {"command": "rm -rf /tmp/test"}, speaker_role="admin")
    assert r.allowed is True
    assert r.requires_confirmation is True


def test_guest_blocked_from_high(gate):
    """Guest is blocked from HIGH-risk operations."""
    r = gate.classify("run_command", {"command": "rm -rf /tmp/test"}, speaker_role="guest")
    assert r.allowed is False
    assert r.matched_rule == "role_gate"


def test_unknown_high_requires_confirmation(gate):
    """Unknown speaker on HIGH-risk gets confirmation, not block."""
    r = gate.classify("run_command", {"command": "rm -rf /tmp/test"}, speaker_role="unknown")
    assert r.allowed is True
    assert r.requires_confirmation is True


def test_unknown_critical_blocked(gate):
    """Unknown speaker is blocked from CRITICAL operations."""
    r = gate.classify("run_command", {"command": "dd if=/dev/zero of=/dev/sda"}, speaker_role="unknown")
    assert r.allowed is False
    assert r.matched_rule == "role_gate"


def test_member_can_execute_high(gate):
    """Member can execute HIGH-risk ops (cap is HIGH)."""
    r = gate.classify("run_command", {"command": "rm -rf /tmp/test"}, speaker_role="member")
    assert r.allowed is True


def test_restricted_blocked_from_medium(gate):
    """Restricted role is blocked from MEDIUM and above."""
    # Find a medium-risk command
    r = gate.classify("run_command", {"command": "zpool scrub tank"}, speaker_role="restricted")
    # zpool scrub is classified as medium by the base framework
    if r.risk_level.value in ("medium", "high", "critical"):
        assert r.allowed is False
        assert r.matched_rule == "role_gate"


def test_role_permissions_admin(gate):
    """Admin permissions are correct."""
    perms = gate.get_role_permissions("admin")
    assert perms["max_risk"] == "critical"
    assert perms["can_execute_critical"] is True
    assert perms["can_execute_high"] is True


def test_role_permissions_guest(gate):
    """Guest permissions are correct."""
    perms = gate.get_role_permissions("guest")
    assert perms["max_risk"] == "medium"
    assert perms["can_execute_high"] is False
    assert perms["can_execute_medium"] is True


def test_role_permissions_unknown(gate):
    """Unknown permissions are correct."""
    perms = gate.get_role_permissions("unknown")
    assert perms["max_risk"] == "medium"
    assert perms["requires_confirmation_for_high"] is True


def test_gate_never_loosens(gate):
    """RoleGate can only tighten, never loosen the base classification."""
    # Safe operation should pass through unchanged for all roles
    for role in ("admin", "member", "guest", "restricted", "unknown"):
        r = gate.classify("run_command", {"command": "ls -la"}, speaker_role=role)
        base = ToolSafetyFramework().classify("run_command", {"command": "ls -la"})
        assert r.allowed == base.allowed
        assert r.risk_level == base.risk_level
