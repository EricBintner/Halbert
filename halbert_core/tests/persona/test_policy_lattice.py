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