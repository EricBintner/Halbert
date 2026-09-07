# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Two-axis persona policy lattice.

security  = capability:   DENY < ALLOWLIST < FULL   (merged with min — strictest wins)
ask       = consultation: OFF < ON_MISS < ALWAYS   (merged with max — most prompting wins)

The load-bearing invariant, lifted from OpenClaw src/infra/exec-approvals-core.ts:
a persona defined as a security FLOOR (e.g. guest = DENY on the write plane) can
never be loosened by any other layer's generosity; "full and never ask" requires
every merged layer to agree. No layer merge may produce it otherwise.

This module is a pure mechanism layer for the permission-and-consent design
(documentation/design/PERMISSION-AND-CONSENT-SYSTEM-2026-09-06.md): it answers
*capability* (may this be executed) and *consultation* (must we ask first). It
does not answer *legitimacy* (by whose rule the voice acts) — that is the
warrant layer's question, and the two must never be folded together.
"""
from __future__ import annotations
from dataclasses import dataclass
from enum import IntEnum


class SecurityLevel(IntEnum):
    DENY = 0
    ALLOWLIST = 1
    FULL = 2


class AskPolicy(IntEnum):
    OFF = 0
    ON_MISS = 1
    ALWAYS = 2


@dataclass(frozen=True)
class PolicyPair:
    security: SecurityLevel
    ask: AskPolicy


def min_security(a: SecurityLevel, b: SecurityLevel) -> SecurityLevel:
    return SecurityLevel(min(a, b))


def max_ask(a: AskPolicy, b: AskPolicy) -> AskPolicy:
    return AskPolicy(max(a, b))


_DEFAULT_FAIL_CLOSED = PolicyPair(security=SecurityLevel.DENY, ask=AskPolicy.ALWAYS)


def merge_policies(layers) -> PolicyPair:
    """Merge policy layers left-to-right. Empty input fails closed to deny+ask."""
    if not layers:
        return _DEFAULT_FAIL_CLOSED
    security = SecurityLevel.FULL  # min-fold identity: only layers can lower it
    ask = AskPolicy.OFF
    for layer in layers:
        security = min_security(security, layer.security)
        ask = max_ask(ask, layer.ask)
    return PolicyPair(security=security, ask=ask)


# Named floors, derived from the existing guest allowlist (single source of truth stays guest_tools)
GUEST_WRITE_PLANE_FLOOR = PolicyPair(security=SecurityLevel.DENY, ask=AskPolicy.OFF)
OWNER_DEFAULT = PolicyPair(security=SecurityLevel.FULL, ask=AskPolicy.ON_MISS)