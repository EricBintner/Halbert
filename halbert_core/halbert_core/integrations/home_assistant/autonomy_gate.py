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
from typing import Any, Dict, List, Optional

from .ha_governance import HAGovernancePolicy

logger = logging.getLogger("halbert.integrations.home_assistant.autonomy_gate")


def effective_entity_ids(entity_id: Any = "", data: Optional[Dict[str, Any]] = None) -> List[str]:
    """Every entity a service call will actually touch.

    SEC-9: Home Assistant takes its target from ``data["entity_id"]`` as
    readily as from a separate argument, and accepts a list as well as a
    string. Callers evaluated the gate on the *argument* and then merged the
    caller's ``data`` on top, so

        entity_id="switch.lamp", data={"entity_id": "switch.life_support"}

    was judged as the lamp and executed against the life-support switch. The
    only entity-level check in the whole policy was one dict key away from
    being decorative.

    Gate on the union, and let a caller name a target in whichever place they
    like — just not in a place the gate does not read.
    """
    found: List[str] = []

    def _add(value: Any) -> None:
        if isinstance(value, str):
            if value.strip():
                found.append(value.strip())
        elif isinstance(value, (list, tuple, set)):
            for item in value:
                _add(item)

    _add(entity_id)
    if isinstance(data, dict):
        _add(data.get("entity_id"))
        # `target` is the modern HA spelling and carries the same weight.
        target = data.get("target")
        if isinstance(target, dict):
            _add(target.get("entity_id"))

    seen, unique = set(), []
    for e in found:
        # HA matches entity ids case-insensitively; so must we, or `Switch.Freezer`
        # walks past a forbidden-entity rule written in lower case.
        lowered = e.lower()
        if lowered not in seen:
            seen.add(lowered)
            unique.append(lowered)
    return unique


#: Ways a service call can name a target that the gate cannot resolve to entity
#: ids without the Home Assistant device, area, floor and label registries.
#:
#: ``cv.make_entity_service_schema`` merges all of these into every entity
#: service schema, and ``ha_client`` POSTs ``data`` verbatim as the service body
#: — so all of them are live on this path. A gate that reads only ``entity_id``
#: judges a call that will act on something else entirely.
_UNRESOLVABLE_TARGET_KEYS = ("device_id", "area_id", "floor_id", "label_id")

#: ``ENTITY_MATCH_ALL``. HA accepts the literal string "all" as a target and
#: expands it to every entity of the platform. It starts with none of the
#: forbidden entity prefixes, so it walked straight past them:
#: ``switch.turn_off`` with ``{"entity_id": "all"}`` at ``act`` autonomy turned
#: off every switch in the house, including ``switch.life_support``.
_ENTITY_MATCH_ALL = "all"


def unresolvable_target(entity_id: Any = "", data: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """How this call names a target the gate cannot check, or None.

    The entity-level rules — the forbidden list above all — can only speak about
    entity ids. When a call names its target some other way, the honest answer is
    not to guess: it is to say the gate cannot vouch for this one.
    """
    blocks = [data if isinstance(data, dict) else {}]
    target = (data or {}).get("target") if isinstance(data, dict) else None
    if isinstance(target, dict):
        blocks.append(target)

    for block in blocks:
        for key in _UNRESOLVABLE_TARGET_KEYS:
            if block.get(key):
                return key

    for candidate in effective_entity_ids(entity_id, data):
        if candidate == _ENTITY_MATCH_ALL:
            return "entity_id: all"
    return None

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

        # An unknown domain never auto-executes, at any autonomy level.
        #
        # Classifying it Level 2 was not enough: `orchestrate` auto-executes
        # Level 2 with a 30-second cancel window, so "unknown domains now
        # confirm" was false exactly where autonomy was highest. Not knowing what
        # something does is not a reason to do it quickly.
        if gov.get("unknown_domain"):
            return AutonomyDecision(
                allowed=True,
                auto_execute=False,
                requires_proposal=True,
                cancel_window_seconds=0,
                governance_level=gov_level,
                reason=gov["reason"],
            )

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

    def evaluate_call(
        self,
        domain: str,
        entity_id: Any = "",
        service: str = "",
        data: Optional[Dict[str, Any]] = None,
    ) -> AutonomyDecision:
        """Evaluate a whole service call, including targets hidden in ``data``.

        Prefer this over :meth:`evaluate` at any call site that forwards a
        caller-supplied ``data`` dict to Home Assistant. ``evaluate`` judges one
        named entity; HA will act on every entity the payload names, and before
        SEC-9 those were not the same set (see :func:`effective_entity_ids`).

        The most restrictive verdict across all targets wins, and a call naming
        no entity at all is still judged on its domain — ``shell_command`` needs
        no target to be dangerous.
        """
        # A target the gate cannot resolve is not a target it may wave through.
        # `entity_id: "all"` expands to every entity of the platform, and a
        # device_id / area_id / floor_id / label_id names entities only the HA
        # registries can enumerate — so the entity-level rules, including the
        # forbidden list, cannot speak about this call at all.
        unresolved = unresolvable_target(entity_id, data)
        if unresolved:
            base = self.evaluate(domain, "", service)
            return AutonomyDecision(
                allowed=False,
                auto_execute=False,
                requires_proposal=False,
                cancel_window_seconds=0,
                governance_level=max(base.governance_level, 2),
                reason=(
                    f"This call targets '{unresolved}', which I cannot resolve to "
                    f"specific entities, so I cannot tell whether it touches "
                    f"something you have forbidden. Name the entities instead."
                ),
            )

        targets = effective_entity_ids(entity_id, data)
        if not targets:
            return self.evaluate(domain, "", service)

        decisions = [self.evaluate(domain, target, service) for target in targets]

        # Rank by how much they permit: a denial beats a proposal beats an
        # auto-execute. Ties keep the highest governance level, so the reason
        # the operator reads names the worst thing in the payload, not the first.
        def permissiveness(d: AutonomyDecision) -> tuple:
            return (d.allowed, d.auto_execute, -d.governance_level)

        worst = min(decisions, key=permissiveness)
        if len(targets) > 1 and worst.governance_level >= 2:
            logger.info(
                "HA call names %d entities; judged on the most restrictive (%s)",
                len(targets), worst.reason,
            )
        return worst

    def update_level(self, level: str, overrides: Optional[Dict[str, str]] = None) -> None:
        """Update the autonomy level at runtime (e.g. from UI slider)."""
        self.autonomy_level = level
        if overrides is not None:
            self.autonomy_overrides = overrides
        logger.info(f"Autonomy gate updated: level={level}, overrides={self.autonomy_overrides}")
