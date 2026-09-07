# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Lattice semantics: security merges with min (strictest wins), ask merges with max (most prompting wins)."""
import pytest
from halbert_core.persona.policy import (
    SecurityLevel, AskPolicy, min_security, max_ask, PolicyPair, merge_policies,
    GUEST_WRITE_PLANE_FLOOR,
)

def test_security_order_and_min():
    assert min_security(SecurityLevel.FULL, SecurityLevel.DENY) is SecurityLevel.DENY
    assert min_security(SecurityLevel.FULL, SecurityLevel.ALLOWLIST) is SecurityLevel.ALLOWLIST
    assert min_security(SecurityLevel.DENY, SecurityLevel.DENY) is SecurityLevel.DENY

def test_ask_order_and_max():
    assert max_ask(AskPolicy.OFF, AskPolicy.ALWAYS) is AskPolicy.ALWAYS
    assert max_ask(AskPolicy.ON_MISS, AskPolicy.OFF) is AskPolicy.ON_MISS

def test_deny_cannot_be_loosened_by_any_layer():
    # the load-bearing property: guest floor + generous session override still deny
    floor = PolicyPair(security=SecurityLevel.DENY, ask=AskPolicy.OFF)
    session = PolicyPair(security=SecurityLevel.FULL, ask=AskPolicy.OFF)
    assert merge_policies([floor, session]).security is SecurityLevel.DENY

def test_yolo_requires_every_layer_to_agree():
    layers = [PolicyPair(SecurityLevel.FULL, AskPolicy.OFF)] * 3
    assert merge_policies(layers).security is SecurityLevel.FULL
    assert merge_policies(
        layers + [PolicyPair(SecurityLevel.ALLOWLIST, AskPolicy.OFF)]
    ).security is SecurityLevel.ALLOWLIST

def test_merge_empty_is_deny_and_ask():
    # fail closed: no policy expressed at all is deny + ask
    merged = merge_policies([])
    assert merged.security is SecurityLevel.DENY
    assert merged.ask is AskPolicy.ALWAYS


from halbert_core.persona import guest_tools  # noqa: E402


def test_guest_floor_agrees_with_existing_allowlist():
    """The lattice's guest write-plane floor must agree with guest_tools' self-checked invariant:
    GUEST_ALLOWED_TOOLS ∩ WRITE_PLANE_TOOLS = ∅. Lattice is a projection of the allowlist,
    not a second authority."""
    assert not (set(guest_tools.GUEST_ALLOWED_TOOLS) & set(guest_tools.WRITE_PLANE_TOOLS))
    # and the floor the lattice would assign to those tools is DENY
    assert GUEST_WRITE_PLANE_FLOOR.security is SecurityLevel.DENY

# ---------------------------------------------------------------------------
# PACKET-02 C2 — the lattice policy view in RoleGate
# ---------------------------------------------------------------------------

from halbert_core.tools.role_gate import (  # noqa: E402
    GUEST_ROLE_FLOOR,
    RoleGate,
    effective_policy,
    role_floor,
    tool_plane_policy,
)
from halbert_core.persona.policy import OWNER_DEFAULT  # noqa: E402


def test_role_gate_guest_write_plane_is_deny_regardless_of_session_generosity():
    """The A1 invariant, now at the integration seam: no session layer,
    however generous, lifts a guest-class speaker over the write-plane
    floor."""
    generous = PolicyPair(security=SecurityLevel.FULL, ask=AskPolicy.OFF)
    for tool in ("run_command", "write_file", "write_config", "schedule_cron", "terminal_blocks"):
        assert effective_policy("guest", tool).security is SecurityLevel.DENY
        assert effective_policy("guest", tool, session=generous).security is SecurityLevel.DENY
        # "unknown" is treated as guest everywhere in RoleGate; so here.
        assert effective_policy("unknown", tool, session=generous).security is SecurityLevel.DENY
    # and a tool off the write plane keeps the guest role floor
    assert effective_policy("guest", "get_status").security is SecurityLevel.ALLOWLIST
    assert effective_policy("guest", "get_status") == GUEST_ROLE_FLOOR


def test_role_gate_owner_write_plane_is_full_on_miss():
    """The owner's audit tools are the owner's: the write-plane floor is a
    guest floor, not an owner floor."""
    view = effective_policy("admin", "run_command")
    assert view.security is SecurityLevel.FULL
    assert view.ask is AskPolicy.ON_MISS
    assert view == OWNER_DEFAULT


def test_role_gate_plane_policy_is_pure_per_tool():
    assert tool_plane_policy("run_command") == GUEST_WRITE_PLANE_FLOOR
    assert tool_plane_policy("get_status") == OWNER_DEFAULT


def test_role_gate_unwritten_role_floor_fails_closed():
    """Halley's warning at this seam: only the owner and guest floors are
    written; every other role reads as DENY + ALWAYS ask — conservative in
    the recorded view, never permissive."""
    for role in ("member", "restricted", "nobody-wrote-this-floor"):
        view = role_floor(role)
        assert view.security is SecurityLevel.DENY
        assert view.ask is AskPolicy.ALWAYS


def test_role_gate_policy_view_method_records_the_lattice_answer():
    # policy_view never touches the safety framework; None keeps the test
    # about the view, not the framework.
    gate = RoleGate(None)
    assert gate.policy_view("run_command", speaker_role="guest").security is SecurityLevel.DENY
    assert gate.policy_view("run_command", speaker_role="admin") == OWNER_DEFAULT
    assert gate.policy_view("get_status", speaker_role="guest") == GUEST_ROLE_FLOOR
