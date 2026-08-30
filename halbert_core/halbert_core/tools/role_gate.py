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


class RoleGate:
    """Wraps ToolSafetyFramework to enforce speaker-role-based access.

    Can only TIGHTEN (never loosen) the base classification.
    """

    def __init__(self, safety_framework: ToolSafetyFramework):
        self._safety = safety_framework

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
