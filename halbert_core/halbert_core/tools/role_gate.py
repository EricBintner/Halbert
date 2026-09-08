# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""RoleGate — speaker-role-based access control wrapper for ToolSafetyFramework.

Wraps ``ToolSafetyFramework.classify()`` to enforce that only authorized
speakers can execute high-risk tools. Can only TIGHTEN (never loosen) the
base classification — mirrors how ``_check_skill_safety`` composes with
``_classify_builtin`` in safety.py.

DO NOT modify ``ToolSafetyFramework`` itself — it is a high-blast-radius
component called on every tool execution. This wrapper is a separate layer
that composes with it.

Role hierarchy:
    admin      -> can do anything the base framework allows
    member     -> capped at HIGH risk
    guest      -> capped at MEDIUM risk
    restricted -> capped at LOW risk
    unknown    -> capped at MEDIUM, HIGH requires confirmation (PIN prompt)

Usage:
    from halbert_core.tools.role_gate import RoleGate
    gate = RoleGate(safety_framework)
    result = gate.classify("run_command", {"command": "zpool scrub tank"},
                           speaker_role="member")
    if not result.allowed:
        return "You don't have permission to do that."
"""

from __future__ import annotations

import logging
from typing import Dict, Optional

from .safety import ToolSafetyFramework, RiskLevel, SafetyCheckResult, _RISK_ORDER
from ..persona.claims import ClaimStrength
from ..persona.guest_tools import WRITE_PLANE_TOOLS
from ..persona.policy import (
    AskPolicy,
    GUEST_WRITE_PLANE_FLOOR,
    OWNER_DEFAULT,
    PolicyPair,
    SecurityLevel,
    merge_policies,
)

logger = logging.getLogger("halbert.tools.role_gate")


# Maximum risk level allowed per speaker role.
# A role can never execute above its cap, even if the base framework
# classifies the operation as lower risk.
ROLE_MAX_RISK: Dict[str, str] = {
    "admin": "critical",    # admin can do anything the base allows
    "member": "high",       # member capped at HIGH
    "guest": "medium",      # guest capped at MEDIUM
    "restricted": "low",    # restricted capped at LOW
    "unknown": "medium",    # unknown speaker treated as guest
}

# For unknown speakers, HIGH-risk ops require confirmation (PIN prompt)
# rather than outright blocking — this allows a guest to perform a
# privileged action if an admin confirms it.
UNKNOWN_CONFIRM_RISK = "high"


# ---------------------------------------------------------------------------
# Lattice policy view (PACKET-02 C2)
# ---------------------------------------------------------------------------

# The two-axis lattice (persona/policy.py) projected onto this module's
# role table. This is the POLICY VIEW for the audit line — the guest
# allowlist (persona/guest_tools.py) and the role risk caps above remain
# the actual filters; the view records capability (security) and
# consultation (ask) and must never loosen either.
#
# Unwritten policy fails closed (Halley's warning): a role with no
# written floor reads as DENY + ALWAYS ask, never as owner-default, so
# the audit line says "no policy was written for this" rather than
# silently granting the owner's default.

# Guest-class speakers run inside the allowlist; "unknown" is treated as
# guest everywhere else in this module, so it reads as guest here too.
GUEST_CLASS_ROLES = frozenset({"guest", "unknown"})
# The owner's own voice: dashboard text turns are session-authenticated
# and process-internal calls default to admin.
OWNER_CLASS_ROLES = frozenset({"admin"})

# The guest role floor: ALLOWLIST security — the allowlist still does the
# actual filtering; this records the view — with ask ON_MISS, because an
# allowlist is exactly "asked for by name or refused on the miss".
GUEST_ROLE_FLOOR = PolicyPair(security=SecurityLevel.ALLOWLIST, ask=AskPolicy.ON_MISS)


def role_floor(role: str) -> PolicyPair:
    """The persona-policy floor a speaker role brings to every call.

    Only two floors are written: the owner's default and the guest's
    allowlist. Any other role has no written floor and reads as the
    lattice's fail-closed default (DENY + ALWAYS ask) — conservative in
    the view, and never permissive.
    """
    if role in OWNER_CLASS_ROLES:
        return OWNER_DEFAULT
    if role in GUEST_CLASS_ROLES:
        return GUEST_ROLE_FLOOR
    return merge_policies([])


def tool_plane_policy(tool_name: str) -> PolicyPair:
    """The policy a tool's plane contributes.

    Write-plane tools (``WRITE_PLANE_TOOLS`` — their handlers write the
    hash-chained audit log) carry the guest write-plane floor; everything
    else contributes the owner default, which never tightens a merge.
    """
    if tool_name in WRITE_PLANE_TOOLS:
        return GUEST_WRITE_PLANE_FLOOR
    return OWNER_DEFAULT


def effective_policy(
    speaker_role: str,
    tool_name: str,
    session: Optional[PolicyPair] = None,
) -> PolicyPair:
    """The merged policy view for one call: role floor, then plane, then
    any session layer, folded with the lattice (min security, max ask).

    The write-plane floor is a floor for GUEST-CLASS speakers only — it
    is the guest's floor for the machine's own audit record, and the
    owner's audit tools are the owner's. Merging it for every role would
    deny the owner the very tools that keep the record, which is not the
    view the lattice is meant to record.
    """
    layers = [role_floor(speaker_role)]
    if speaker_role in GUEST_CLASS_ROLES:
        layers.append(tool_plane_policy(tool_name))
    if session is not None:
        layers.append(session)
    return merge_policies(layers)


# ---------------------------------------------------------------------------
# Voice claim ceiling (D-6 wave 3 — enforcement, not just recording)
# ---------------------------------------------------------------------------

def voice_role_ceiling(claim_strength: ClaimStrength) -> str:
    """The strongest role-class a voice turn's claim can earn.

    Packet 04 A2 recorded the turn's identifier claim; this is the
    enforcement half. ASSERTED or stronger (speaker verification matched,
    or a credential the server validates): the stated role stands — the
    current behavior. Below ASSERTED (UNVERIFIED — claimed but
    uncorroborated; MUTABLE — a free-text name the speaker chose
    themselves): member is the strongest class the claim can earn, so an
    unverified voice claiming to be the owner never wields owner-class
    tools.

    Typed turns never consult this — the executor only applies the
    ceiling when a voice turn's claim is bound on its context, so text
    behavior is byte-identical to before.
    """
    if claim_strength >= ClaimStrength.ASSERTED:
        return "admin"
    return "member"


def effective_voice_role(speaker_role: str, claim_strength: ClaimStrength) -> str:
    """The role RoleGate should hear for a voice turn with this claim.

    Applies ``voice_role_ceiling`` to the stated role. The ceiling caps,
    never grants: a stated role already at or below member (member,
    guest, unknown, restricted) stands as stated — the claim axis never
    lifts a speaker out of its own class. Composition rule: this cap is
    about the *voice identity claim*, a different axis from persona
    fronting — a guest persona's own gate list (persona/guest_tools.py)
    stays authoritative for guests whether or not a claim is bound.

    When the cap downgrades the stated role, one structured line
    (``voice_role_capped``) records old role, capped role, and claim
    strength, so the audit surface shows why a tool was gated.
    """
    ceiling = voice_role_ceiling(claim_strength)
    # "Stronger role" = the higher risk cap ROLE_MAX_RISK allows it; the
    # effective role is the weaker of the two, by that order.
    stated_order = _RISK_ORDER[ROLE_MAX_RISK.get(speaker_role, "medium")]
    ceiling_order = _RISK_ORDER[ROLE_MAX_RISK.get(ceiling, "medium")]
    if ceiling_order < stated_order:
        logger.warning(
            "voice_role_capped: stated_role=%s capped_role=%s claim_strength=%s",
            speaker_role,
            ceiling,
            ClaimStrength(claim_strength).name.lower(),
        )
        return ceiling
    return speaker_role


class RoleGate:
    """Wraps ToolSafetyFramework to enforce speaker-role-based access.

    Can only TIGHTEN (never loosen) the base classification.
    """

    def __init__(self, safety_framework: ToolSafetyFramework):
        self._safety = safety_framework

    def policy_view(
        self,
        tool_name: str,
        speaker_role: str = "unknown",
    ) -> PolicyPair:
        """The lattice policy view for this call — the audit line's
        capability/consultation record.

        The allowlist and the role risk caps in ``classify()`` remain the
        actual filters; this records what the two-axis lattice sees, so an
        audit line can say "DENY, ask OFF" (a guest on the write plane)
        instead of only what the risk cap did. Unwritten policy fails
        closed: a role with no written floor reads as DENY + ALWAYS ask.
        """
        view = effective_policy(speaker_role, tool_name)
        logger.info(
            "RoleGate policy view: role=%s tool=%s security=%s ask=%s",
            speaker_role, tool_name, view.security.name, view.ask.name,
        )
        return view

    def classify(
        self,
        tool_name: str,
        args: Dict,
        speaker_role: str = "unknown",
    ) -> SafetyCheckResult:
        """Classify a tool call with speaker-role enforcement.

        Args:
            tool_name: Name of the tool being called.
            args: Tool arguments.
            speaker_role: The verified role of the speaker
                ('admin', 'member', 'guest', 'restricted', 'unknown').

        Returns:
            SafetyCheckResult — may be tighter than the base classification
            but never looser.
        """
        # The audit line's policy view: capability and consultation as the
        # lattice sees them. Recorded, never enforced here — the caps
        # below and the guest allowlist remain the filters.
        self.policy_view(tool_name, speaker_role)

        base = self._safety.classify(tool_name, args)

        max_risk_name = ROLE_MAX_RISK.get(speaker_role, "medium")
        max_risk_order = _RISK_ORDER.get(max_risk_name, 1)
        base_risk_order = _RISK_ORDER[base.risk_level.value]

        # For unknown speakers on HIGH-risk ops, allow with confirmation (PIN prompt).
        # This check comes BEFORE the cap check so unknown speakers can still
        # perform HIGH ops if an admin confirms — they're not outright blocked.
        # If the base already requires confirmation, that's sufficient.
        if (
            speaker_role == "unknown"
            and base.risk_level == RiskLevel.HIGH
        ):
            if base.requires_confirmation:
                # Base already requires confirmation — pass through
                return base
            logger.info(
                f"Role gate: unknown speaker — confirmation required for "
                f"HIGH-risk operation ({tool_name})"
            )
            return SafetyCheckResult(
                risk_level=base.risk_level,
                allowed=True,
                requires_confirmation=True,
                reason=(
                    f"Unknown speaker — confirmation required for "
                    f"{base.risk_level.value} operation ({base.reason})"
                ),
                matched_rule="role_gate.unknown_confirm",
            )

        # If the base classification exceeds the role's cap, block it
        if base_risk_order > max_risk_order:
            logger.warning(
                f"Role gate BLOCKED: speaker_role='{speaker_role}' "
                f"cannot execute {base.risk_level.value} operation "
                f"({tool_name}: {base.reason})"
            )
            return SafetyCheckResult(
                risk_level=base.risk_level,
                allowed=False,
                requires_confirmation=False,
                reason=(
                    f"Blocked: speaker role '{speaker_role}' cannot execute "
                    f"{base.risk_level.value} operations ({base.reason})"
                ),
                matched_rule="role_gate",
            )

        return base

    def get_role_permissions(self, speaker_role: str) -> Dict:
        """Get a summary of what a role can do (for UI display).

        Returns:
            Dict with max_risk, can_execute_high, requires_pin_for_high, etc.
        """
        max_risk_name = ROLE_MAX_RISK.get(speaker_role, "medium")
        return {
            "role": speaker_role,
            "max_risk": max_risk_name,
            "can_execute_critical": max_risk_name == "critical",
            "can_execute_high": _RISK_ORDER[max_risk_name] >= _RISK_ORDER["high"],
            "can_execute_medium": _RISK_ORDER[max_risk_name] >= _RISK_ORDER["medium"],
            "requires_confirmation_for_high": speaker_role == "unknown",
            "description": _ROLE_DESCRIPTIONS.get(speaker_role, ""),
        }


_ROLE_DESCRIPTIONS = {
    "admin": "Full system access (ZFS, SSH, deadbolts, alarms, shell commands)",
    "member": "Standard home access (lights, thermostat, media, vacuum)",
    "guest": "Advisory queries and safe lighting only",
    "restricted": "Read-only info. PIN required for any privileged action.",
    "unknown": "Unidentified speaker. Treated as guest. Confirmation required for high-risk ops.",
}
