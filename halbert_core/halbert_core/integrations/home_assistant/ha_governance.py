# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""HA Governance Policy — 4-level safety for HA service calls.

Levels:
    0 — No confirmation needed (light, fan, media_player, vacuum)
    1 — Low risk, log only (climate, humidifier, cover)
    2 — Confirmation required (lock, alarm, garage_door)
    3 — Forbidden (water_valve, freezer, medical devices)

Phase 2: governance is enforced via the ToolExecutor safety framework.
The classify() method returns a risk level that the executor checks
before allowing execution.
"""

from __future__ import annotations

import logging
from typing import Set

logger = logging.getLogger("halbert.integrations.home_assistant.governance")

# Level 0: No confirmation — safe to toggle
LEVEL_0_NO_CONFIRM: Set[str] = {
    "light",
    "fan",
    "media_player",
    "vacuum",
}

# Level 1: Low risk — log but don't block
LEVEL_1_LOW_RISK: Set[str] = {
    "climate",
    "humidifier",
    "cover",
    "switch",
    "input_boolean",
}

# Level 2: Confirmation required — security-critical
LEVEL_2_CONFIRM_REQUIRED: Set[str] = {
    "lock",
    "alarm_control_panel",
    "garage_door",
}

# Level 3: Forbidden — physical safety risk
LEVEL_3_FORBIDDEN: Set[str] = {
    "water_valve",
}

# Entity IDs that are always forbidden regardless of domain
FORBIDDEN_ENTITY_PATTERNS: Set[str] = {
    "switch.freezer",
    "switch.medical",
    "switch.life_support",
}


class HAGovernancePolicy:
    """4-level governance policy for HA service calls.

    Use classify(domain, entity_id, service) to get the risk level
    and whether confirmation is required.
    """

    def classify(
        self,
        domain: str,
        entity_id: str = "",
        service: str = "",
    ) -> dict:
        """Classify a HA service call.

        Returns:
            Dict with:
                level: 0-3
                allowed: bool
                requires_confirmation: bool
                reason: str
        """
        # Check forbidden entity patterns first
        for pattern in FORBIDDEN_ENTITY_PATTERNS:
            if entity_id.startswith(pattern):
                return {
                    "level": 3,
                    "allowed": False,
                    "requires_confirmation": False,
                    "reason": f"Entity {entity_id} is on the forbidden list (physical safety)",
                }

        # Check domain-based levels
        if domain in LEVEL_3_FORBIDDEN:
            return {
                "level": 3,
                "allowed": False,
                "requires_confirmation": False,
                "reason": f"Domain '{domain}' is forbidden (physical safety risk)",
            }

        if domain in LEVEL_2_CONFIRM_REQUIRED:
            return {
                "level": 2,
                "allowed": True,
                "requires_confirmation": True,
                "reason": f"Domain '{domain}' requires confirmation (security-critical)",
            }

        if domain in LEVEL_1_LOW_RISK:
            return {
                "level": 1,
                "allowed": True,
                "requires_confirmation": False,
                "reason": f"Domain '{domain}' is low risk",
            }

        if domain in LEVEL_0_NO_CONFIRM:
            return {
                "level": 0,
                "allowed": True,
                "requires_confirmation": False,
                "reason": f"Domain '{domain}' is safe (no confirmation needed)",
            }

        # Unknown domain — default to Level 1 (cautious but not blocking)
        return {
            "level": 1,
            "allowed": True,
            "requires_confirmation": False,
            "reason": f"Domain '{domain}' is unknown — treating as low risk",
        }
