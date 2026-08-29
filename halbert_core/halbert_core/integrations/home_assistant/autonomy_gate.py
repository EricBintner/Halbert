# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Autonomy Gate — enforces the autonomy_level setting before HA actions.

The autonomy slider is the architectural keystone of the sentient home.
Every action the cognitive loop or chat agent wants to take must pass
through this gate before reaching the HA client.

Autonomy levels (from BeingConfig.autonomy_level):
    observe    — perceive and report only. No device commands ever.
    suggest    — create proposals but wait for approval. No device commands.
    act        — execute Level 0/1 governance actions autonomously.
                 Level 2+ become proposals requiring approval.
    orchestrate — coordinate multi-device sequences. Level 2 actions
                  execute with a 30-second cancel window. Level 3 always
                  forbidden.

Per-domain overrides (BeingConfig.autonomy_overrides) keyed by HA domain
take precedence over the global level. E.g. {"lock": "suggest"} means
locks always require a proposal even at orchestrate level.

This gate integrates with the existing HAGovernancePolicy (4-level
domain classification) to determine whether a specific action is
permitted at the current autonomy level.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, Optional

from .ha_governance import HAGovernancePolicy

logger = logging.getLogger("halbert.integrations.home_assistant.autonomy_gate")

# Autonomy level → max governance level allowed for auto-execution
# observe:    nothing auto-executes (max_level = -1)
# suggest:    nothing auto-executes, but proposals are created (max_level = -1)
# act:        Level 0 and 1 auto-execute (max_level = 1)
# orchestrate: Level 0, 1, 2 auto-execute (max_level = 2), Level 3 forbidden
_MAX_AUTO_LEVEL = {
    "observe": -1,
    "suggest": -1,
    "act": 1,
    "orchestrate": 2,
}


@dataclass
class AutonomyDecision:
    """Result of an autonomy gate check."""
    allowed: bool
    auto_execute: bool
    requires_proposal: bool
    cancel_window_seconds: int
    governance_level: int
    reason: str


class AutonomyGate:
    """Enforces autonomy_level before HA service calls.

    Wraps HAGovernancePolicy to add the autonomy slider layer.
    The governance policy classifies the risk; the autonomy gate
    decides whether to auto-execute, propose, or block.
    """

    def __init__(
        self,
        autonomy_level: str = "observe",
        autonomy_overrides: Optional[Dict[str, str]] = None,
        governance: Optional[HAGovernancePolicy] = None,
    ) -> None:
        self.autonomy_level = autonomy_level
        self.autonomy_overrides = autonomy_overrides or {}
        self.governance = governance or HAGovernancePolicy()

    def evaluate(
        self,
        domain: str,
        entity_id: str = "",
        service: str = "",
    ) -> AutonomyDecision:
        """Evaluate whether an action is permitted at the current autonomy level.

        Args:
            domain: HA domain (light, climate, lock, etc.)
            entity_id: Full entity ID (e.g. light.living_room)
            service: Service name (turn_on, turn_off, etc.)

        Returns:
            AutonomyDecision with allowed, auto_execute, requires_proposal
        """
        # Step 1: Classify via governance policy
        gov = self.governance.classify(domain, entity_id, service)
        gov_level = gov["level"]

        # Level 3 is always forbidden regardless of autonomy
        if gov_level == 3:
            return AutonomyDecision(
                allowed=False,
                auto_execute=False,
                requires_proposal=False,
                cancel_window_seconds=0,
                governance_level=3,
                reason=f"Forbidden by governance: {gov['reason']}",
            )

        # Step 2: Determine effective autonomy level (override takes precedence)
        effective_level = self.autonomy_overrides.get(domain, self.autonomy_level)

        # Step 3: observe — never auto-execute, never send commands
        if effective_level == "observe":
            return AutonomyDecision(
                allowed=False,
                auto_execute=False,
                requires_proposal=False,
                cancel_window_seconds=0,
                governance_level=gov_level,
                reason="Autonomy level is 'observe' — no device commands permitted",
            )

        # Step 4: suggest — create proposals, never auto-execute
        if effective_level == "suggest":
            return AutonomyDecision(
                allowed=True,
                auto_execute=False,
                requires_proposal=True,
                cancel_window_seconds=0,
                governance_level=gov_level,
                reason="Autonomy level is 'suggest' — proposal created for approval",
            )

        # Step 5: act — auto-execute Level 0/1, propose Level 2+
        if effective_level == "act":
            max_level = _MAX_AUTO_LEVEL["act"]  # 1
            if gov_level <= max_level:
                return AutonomyDecision(
                    allowed=True,
                    auto_execute=True,
                    requires_proposal=False,
                    cancel_window_seconds=0,
                    governance_level=gov_level,
                    reason=f"Auto-executed (governance Level {gov_level} <= {max_level})",
                )
            else:
                return AutonomyDecision(
                    allowed=True,
                    auto_execute=False,
                    requires_proposal=True,
                    cancel_window_seconds=0,
                    governance_level=gov_level,
                    reason=f"Requires proposal (governance Level {gov_level} > {max_level})",
                )

        # Step 6: orchestrate — auto-execute Level 0/1/2, propose nothing
        # Level 2 gets a 30-second cancel window
        if effective_level == "orchestrate":
            max_level = _MAX_AUTO_LEVEL["orchestrate"]  # 2
            if gov_level <= max_level:
                cancel_window = 30 if gov_level == 2 else 0
                return AutonomyDecision(
                    allowed=True,
                    auto_execute=True,
                    requires_proposal=False,
                    cancel_window_seconds=cancel_window,
                    governance_level=gov_level,
                    reason=(
                        f"Auto-executed (governance Level {gov_level} <= {max_level})"
                        + (f" with {cancel_window}s cancel window" if cancel_window else "")
                    ),
                )
            else:
                return AutonomyDecision(
                    allowed=False,
                    auto_execute=False,
                    requires_proposal=False,
                    cancel_window_seconds=0,
                    governance_level=gov_level,
                    reason=f"Forbidden at orchestrate level (governance Level {gov_level})",
                )

        # Fallback — should never reach here if config validated
        return AutonomyDecision(
            allowed=False,
            auto_execute=False,
            requires_proposal=False,
            cancel_window_seconds=0,
            governance_level=gov_level,
            reason=f"Unknown autonomy level '{effective_level}'",
        )

    def update_level(self, level: str, overrides: Optional[Dict[str, str]] = None) -> None:
        """Update the autonomy level at runtime (e.g. from UI slider)."""
        self.autonomy_level = level
        if overrides is not None:
            self.autonomy_overrides = overrides
        logger.info(f"Autonomy gate updated: level={level}, overrides={self.autonomy_overrides}")
