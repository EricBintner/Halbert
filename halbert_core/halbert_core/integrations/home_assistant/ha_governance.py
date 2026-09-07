# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""HA Governance Policy — 4-level safety for HA service calls.

Levels:
    0 — No confirmation needed (light, fan, media_player, vacuum)
    1 — Low risk, log only (climate, humidifier, switch)
    2 — Confirmation required (lock, alarm, cover, valve, and anything unknown)
    3 — Forbidden (arbitrary code execution, host control, medical devices)

Governance is enforced via the ToolExecutor safety framework; classify()
returns a risk level the executor checks before allowing execution.

**SEC-9 — two criticals, both of which made most of this file decorative.**

1. *The confirm and forbid tiers keyed on domains Home Assistant does not
   have.* There is no ``garage_door`` domain — a garage door is a ``cover``
   with ``device_class: garage`` — and no ``water_valve`` domain; HA calls it
   ``valve``. So Level 2 and Level 3 matched nothing, ever, while ``cover``
   sat in Level 1 and opened the garage with no confirmation.

2. *An unknown domain returned Level 1: act, log only.* Thirteen device
   domains were classified and everything else auto-executed — including
   ``shell_command``, ``python_script``, ``hassio`` and ``homeassistant``,
   which is arbitrary code execution and host control on the hub. A default
   that runs what it does not recognise is not a policy.
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
    "switch",
    "input_boolean",
    "input_number",
    "input_select",
    "select",
    "number",
    "scene",
    "text",
    "button",
    "siren",
    "remote",
    "water_heater",
}

# Level 2: Confirmation required — security-critical or physically consequential.
#
# `cover` and `valve` are whole-domain entries on purpose: the domain cannot
# tell a bedroom blind from a garage door, or a radiator valve from a mains
# stopcock, and classify() is not always given the device_class. Confirming a
# blind is a small tax; opening a garage without asking is not.
LEVEL_2_CONFIRM_REQUIRED: Set[str] = {
    "lock",
    "alarm_control_panel",
    "cover",
    "valve",
    "camera",
    "person",
    "device_tracker",
    "notify",
    "tts",
    "conversation",
}

# Level 3: Forbidden — arbitrary code execution, host control, or physical
# safety. These are not device domains; they are the ones that turn "Halbert
# may adjust the lights" into "Halbert may run anything on the hub".
LEVEL_3_FORBIDDEN: Set[str] = {
    "shell_command",
    "python_script",
    "hassio",
    "homeassistant",   # restart, stop, reload_core_config
    "automation",      # rewriting the automations is rewriting the rules
    "script",
    "rest_command",
    "command_line",
    "recorder",        # purge deletes the history that would show what happened
    "backup",
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

        # Unknown domain — ask, do not guess.
        #
        # This returned Level 1 ("cautious but not blocking") and auto-executed.
        # An allowlist whose default is "run it" is not an allowlist: every
        # domain the author had not thought of — including the ones that execute
        # arbitrary code on the hub — went straight through (SEC-9).
        return {
            "level": 2,
            "allowed": True,
            "requires_confirmation": True,
            "reason": (
                f"Domain '{domain}' is not one I have been told how to judge, "
                f"so I will ask before acting on it"
            ),
        }
