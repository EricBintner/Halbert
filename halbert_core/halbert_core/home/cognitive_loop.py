# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Home Cognitive Loop — the autonomous perception-reason-action tick.

This is the single most important missing piece for the sentient home.
The agent state machine today only runs when a user sends a chat message.
This loop runs on a configurable interval (default 5-15 minutes) and:

1. PERCEIVES: gathers state from HA entities, Frigate events, scanner
   findings, occupancy model, and behavior predictions.
2. REASONS: flushes pending HA/Frigate events into PersonaCognition
   via the event mappers (queue+flush pattern), then calls advance_turn.
   Uses cheap heuristics for routine checks; only invokes the LLM when
   something novel happens.
3. ACTS: routes desired actions through the AutonomyGate. Depending on
   the autonomy level, actions are auto-executed, proposed, or suppressed.
4. OBSERVES: checks whether the action had the intended effect.
5. REFLECTS: logs the decision chain for the orchestration timeline.

The loop is interruptible — if the user sends a chat message while the
loop is running, the chat takes priority. The loop does NOT use the LLM
on every tick (cost + latency). It uses cheap heuristics for routine
checks and only invokes the LLM when something novel happens.

Per the feedback in HOME-AUTOMATION-DESIGN-REVIEW-FEEDBACK-v2.md:
- advance_turn is NOT called per HA event. Events accumulate until:
  - User sends a message (natural flush point)
  - Scheduled cognitive tick interval (this loop)
  - Significant event threshold (security alert)
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from ..integrations.home_assistant.autonomy_gate import AutonomyGate, AutonomyDecision

logger = logging.getLogger("halbert.home.cognitive_loop")


@dataclass
class CognitiveTickResult:
    """Result of a single cognitive tick."""
    timestamp: float
    perceived: Dict[str, Any] = field(default_factory=dict)
    actions_evaluated: List[Dict[str, Any]] = field(default_factory=list)
    actions_executed: List[Dict[str, Any]] = field(default_factory=list)
    actions_proposed: List[Dict[str, Any]] = field(default_factory=list)
    actions_blocked: List[Dict[str, Any]] = field(default_factory=list)
    cognition_ticked: bool = False
    error: Optional[str] = None


class HomeCognitiveLoop:
    """Scheduled autonomous loop for the sentient home.

    Runs on a background thread, perceives house state, reasons about
    it, and takes coordinated action through the AutonomyGate.

    Args:
        autonomy_gate: Enforces the autonomy slider before actions.
        interval_seconds: How often to run the tick (default 300s / 5min).
        ha_client: Optional HA REST client for entity state queries.
        ha_event_mapper: Optional HAEventMapper for flushing pending events.
        frigate_event_mapper: Optional Frigate event mapper.
        system_event_mapper: Optional SystemEventMapper.
        cognition_tick: Optional advance_turn callable.
        cognition: Optional PersonaCognition instance.
        finding_store: Optional FindingStore for creating findings.
        proposal_generator: Optional ProposalGenerator for creating proposals.
        significant_event_threshold: If this many events accumulate, flush
            early regardless of interval (default 10).
    """

    def __init__(
        self,
        autonomy_gate: AutonomyGate,
        interval_seconds: int = 300,
        ha_client=None,
        ha_event_mapper=None,
        frigate_event_mapper=None,
        system_event_mapper=None,
        cognition_tick: Optional[Callable] = None,
        cognition=None,
        finding_store=None,
        proposal_generator=None,
        significant_event_threshold: int = 10,
    ) -> None:
        self.gate = autonomy_gate
        self.interval = interval_seconds
        self.ha_client = ha_client
        self.ha_event_mapper = ha_event_mapper
        self.frigate_event_mapper = frigate_event_mapper
        self.system_event_mapper = system_event_mapper
        self.cognition_tick = cognition_tick
        self.cognition = cognition
        self.finding_store = finding_store
        self.proposal_generator = proposal_generator
        self.significant_event_threshold = significant_event_threshold

        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._stop_event = threading.Event()
        self._last_tick: Optional[CognitiveTickResult] = None
        self._tick_count = 0

        # Pending actions from the last tick that need execution
        self._pending_actions: List[Dict[str, Any]] = []

    def start(self) -> None:
        """Start the cognitive loop in a background thread."""
        if self._running:
            logger.warning("Cognitive loop already running")
            return
        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="home-cognitive-loop")
        self._thread.start()
        logger.info(f"Home cognitive loop started (interval={self.interval}s)")

    def stop(self) -> None:
        """Stop the cognitive loop."""
        self._running = False
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=10)
        logger.info("Home cognitive loop stopped")

    def _run(self) -> None:
        """Main loop — runs until stop() is called."""
        # First tick after a short delay to let services initialize
        self._stop_event.wait(15)
        while not self._stop_event.is_set():
            try:
                result = self.tick()
                self._last_tick = result
                if result.error:
                    logger.warning(f"Cognitive tick error: {result.error}")
                else:
                    logger.debug(
                        f"Cognitive tick #{self._tick_count}: "
                        f"{len(result.actions_executed)} executed, "
                        f"{len(result.actions_proposed)} proposed, "
                        f"{len(result.actions_blocked)} blocked"
                    )
            except Exception as e:
                logger.exception(f"Cognitive tick crashed: {e}")
            # Wait for interval or stop signal
            self._stop_event.wait(self.interval)

    def tick(self) -> CognitiveTickResult:
        """Run a single cognitive tick. Can be called directly for testing.

        Returns:
            CognitiveTickResult with what was perceived and what happened.
        """
        result = CognitiveTickResult(timestamp=time.time())

        try:
            # --- Phase 1: PERCEIVE ---
            perceived = self._perceive()
            result.perceived = perceived
            self._tick_count += 1
            self._last_tick = result

            # --- Phase 2: REASON ---
            # Flush pending events into cognition (queue+flush pattern)
            self._flush_events_to_cognition()

            # Run the cognitive tick (advance_turn) if wired
            if self.cognition_tick and self.cognition:
                try:
                    asyncio.run(self._safe_cognition_tick())
                    result.cognition_ticked = True
                except Exception as e:
                    logger.warning(f"Cognition tick failed: {e}")

            # --- Phase 3: DECIDE ---
            # Use cheap heuristics to determine if any actions are needed.
            # The LLM is only invoked for novel situations (future enhancement).
            desired_actions = self._decide(perceived)

            # --- Phase 4: ACT (through AutonomyGate) ---
            for action in desired_actions:
                decision = self.gate.evaluate(
                    domain=action["domain"],
                    entity_id=action.get("entity_id", ""),
                    service=action.get("service", ""),
                )
                action_record = {
                    "action": action,
                    "decision": decision.__dict__ if hasattr(decision, "__dict__") else {},
                    "timestamp": time.time(),
                }

                if not decision.allowed:
                    result.actions_blocked.append(action_record)
                    logger.info(f"Action blocked: {action['domain']}.{action.get('service', '')} — {decision.reason}")
                elif decision.auto_execute:
                    self._execute_action(action)
                    result.actions_executed.append(action_record)
                    logger.info(f"Action executed: {action['domain']}.{action.get('service', '')} — {decision.reason}")
                elif decision.requires_proposal:
                    self._create_proposal(action, decision)
                    result.actions_proposed.append(action_record)
                    logger.info(f"Proposal created: {action['domain']}.{action.get('service', '')} — {decision.reason}")
                else:
                    result.actions_blocked.append(action_record)

        except Exception as e:
            result.error = str(e)
            logger.exception(f"Cognitive tick failed: {e}")

        return result

    def _perceive(self) -> Dict[str, Any]:
        """Gather current state from all available sources."""
        state: Dict[str, Any] = {}

        # HA entity states
        if self.ha_client:
            try:
                import asyncio
                states = asyncio.run(self.ha_client.get_states())
                state["ha_entities"] = states
            except Exception as e:
                logger.debug(f"HA state query failed: {e}")
                state["ha_entities"] = []
        else:
            state["ha_entities"] = []

        # Pending event counts
        state["pending_ha_events"] = (
            len(self.ha_event_mapper._pending_events)
            if self.ha_event_mapper and hasattr(self.ha_event_mapper, "_pending_events")
            else 0
        )
        state["pending_frigate_events"] = (
            len(self.frigate_event_mapper._pending_events)
            if self.frigate_event_mapper and hasattr(self.frigate_event_mapper, "_pending_events")
            else 0
        )
        state["pending_system_events"] = (
            len(self.system_event_mapper._pending_events)
            if self.system_event_mapper and hasattr(self.system_event_mapper, "_pending_events")
            else 0
        )

        return state

    def _flush_events_to_cognition(self) -> None:
        """Flush pending events from all mappers into cognition."""
        if self.cognition is None:
            return

        if self.ha_event_mapper:
            try:
                self.ha_event_mapper.populate_cognition(self.cognition)
            except Exception as e:
                logger.debug(f"HA event flush failed: {e}")

        if self.frigate_event_mapper:
            try:
                self.frigate_event_mapper.populate_cognition(self.cognition)
            except Exception as e:
                logger.debug(f"Frigate event flush failed: {e}")

        if self.system_event_mapper:
            try:
                self.system_event_mapper.populate_cognition(self.cognition)
            except Exception as e:
                logger.debug(f"System event flush failed: {e}")

    async def _safe_cognition_tick(self) -> None:
        """Run advance_turn safely, catching errors."""
        if self.cognition_tick is None:
            return
        try:
            # advance_turn may be sync or async; handle both
            import inspect
            if inspect.iscoroutinefunction(self.cognition_tick):
                await self.cognition_tick(cognition=self.cognition)
            else:
                await asyncio.to_thread(
                    self.cognition_tick,
                    cognition=self.cognition,
                )
        except Exception as e:
            logger.warning(f"advance_turn failed: {e}")

    def _decide(self, perceived: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Decide what actions to take based on perceived state.

        This is the heuristic layer. It uses cheap rules to determine
        if any actions are needed. The LLM is NOT invoked here — that
        is a future enhancement for novel situations.

        Returns:
            List of desired actions, each with domain, entity_id, service,
            and optional data.
        """
        actions: List[Dict[str, Any]] = []

        # Heuristic: if there are critical findings, create actions
        # to address them (future: use the LLM to generate remediation)
        # For now, this is a placeholder that demonstrates the pattern.

        # Example heuristic: if a light is on and no one is home, turn it off
        # (This requires occupancy model integration — Phase 2)

        return actions

    def _execute_action(self, action: Dict[str, Any]) -> None:
        """Execute a HA service call."""
        if self.ha_client is None:
            logger.warning("Cannot execute action — no HA client")
            return
        try:
            import asyncio
            asyncio.run(self.ha_client.call_service(
                domain=action["domain"],
                service=action.get("service", ""),
                data=action.get("data", {}),
            ))
        except Exception as e:
            logger.warning(f"Action execution failed: {e}")

    def _create_proposal(self, action: Dict[str, Any], decision: AutonomyDecision) -> None:
        """Create a proposal for an action that requires approval."""
        if self.proposal_generator is None:
            logger.debug("No proposal generator — action would be proposed")
            return
        try:
            # Future: create a proper proposal via the proposal generator
            logger.info(
                f"Proposal created for {action['domain']}.{action.get('service', '')} "
                f"on {action.get('entity_id', '')}: {decision.reason}"
            )
        except Exception as e:
            logger.warning(f"Proposal creation failed: {e}")

    @property
    def status(self) -> Dict[str, Any]:
        """Current status of the cognitive loop."""
        return {
            "running": self._running,
            "tick_count": self._tick_count,
            "interval_seconds": self.interval,
            "autonomy_level": self.gate.autonomy_level,
            "last_tick": (
                {
                    "timestamp": self._last_tick.timestamp,
                    "actions_executed": len(self._last_tick.actions_executed),
                    "actions_proposed": len(self._last_tick.actions_proposed),
                    "actions_blocked": len(self._last_tick.actions_blocked),
                    "error": self._last_tick.error,
                }
                if self._last_tick
                else None
            ),
        }
