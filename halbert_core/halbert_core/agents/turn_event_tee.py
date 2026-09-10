# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The turn-event tee (D-4 design §6, packet C4) — observe-only
fan-out of a turn's REDUCED event set.

Today a turn's events reach exactly one HTTP response: the SSE of whoever
posted it. Everything else that should be able to *see* a turn — the
voice HUD reflecting a dashboard turn, a second screen in the room, the
future terminal client — cannot. The tee is the thin fix: one
process-wide hub the state machine publishes to, subscribers receive.

The reduced set (never the token stream — that is bandwidth and privacy
tee consumers do not need; the full stream stays behind a future opt-in,
design §8 Q4):

    turn_started, turn_queued, turn_ended, state_change,
    conversation_status, somatic_block, tool_start, tool_complete,
    steer_accepted, stop_outcome

Three hard rules, from existing seams:

  * **Through the echo-guard seam** (packet-05 B2): every string value in
    a payload is scanned with the global echo guard and redacted through
    the ingestion variant registry before fan-out — the same two calls
    ``_echo_guard_egress`` makes — so a subscriber in the room sees only
    what the answer stream was cleared to show. (The reduced payloads
    carry no content by construction; the seam is the belt to that
    braces.)
  * **Observe-only**: subscribing confers no steer/stop rights. The hub
    has no verb — the busy verbs stay behind the channel declarations
    (C3) — and a subscriber that raises costs the turn nothing.
  * **Single event loop, no lock**: publishers and subscribers share the
    dashboard's loop (the turn runs inside the SSE generator), like the
    TTS egress hub. A slow subscriber is a bug in the subscriber; the
    tee itself never blocks, and its callbacks are sync — a bridge that
    needs to await schedules its own task.

Module singleton via ``get_turn_event_tee()`` (the get_event_bus
pattern): the publisher (the agent state machine, built without an app
reference) and the subscribers (app.py's /ws bridge) meet here without
either holding the FastAPI app.
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Callable, Dict, List

logger = logging.getLogger("halbert.agents.turn_event_tee")

#: A subscriber's return handle: call to unsubscribe.
Unsubscribe = Callable[[], None]


def _scrub_text(text: str) -> str:
    """The tee's call into the one scrub seam (A05-G4).

    This used to be a copy of ``AgentStateMachine._echo_guard_egress``,
    with a comment saying it mirrored it "so the tee does not import the
    state machine to reach a staticmethod". Two copies of a security
    seam drift, and the one that drifts is the one nobody is looking at.
    The seam lives in ``security/scrub.py`` now; this is the call.
    """
    from ..security.scrub import scrub_for_egress
    return scrub_for_egress(text, surface="tee")


class TurnEventTee:
    """Observe-only fan-out of reduced turn events."""

    def __init__(self) -> None:
        self._subscribers: List[Callable[[Dict[str, Any]], None]] = []

    def reset(self) -> None:
        """Test seam: drop every subscriber."""
        self._subscribers = []

    def subscribe(
        self, callback: Callable[[Dict[str, Any]], None]
    ) -> Unsubscribe:
        """Register a sync callback receiving payload dicts.

        Observe-only: the callback gets no handle that acts on the turn,
        and a callback that raises is swallowed (logged once per
        occurrence, debug level — a broken consumer is diagnosable
        without ever costing the turn).
        """
        self._subscribers.append(callback)
        return lambda: self.unsubscribe(callback)

    def unsubscribe(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        try:
            self._subscribers.remove(callback)
        except ValueError:
            pass

    def publish(self, payload: Dict[str, Any]) -> None:
        """Fan one reduced payload out to every subscriber.

        String values pass the echo-guard seam first (the design's first
        hard rule); a subscriber exception is swallowed so observation
        can never break the turn it observes.
        """
        if not self._subscribers:
            return
        cleaned = {
            key: (_scrub_text(value) if isinstance(value, str) else value)
            for key, value in payload.items()
        }
        for callback in list(self._subscribers):
            try:
                callback(cleaned)
            except Exception as e:
                logger.debug(f"tee subscriber failed (non-fatal): {e}")


_TEE: TurnEventTee | None = None


def get_turn_event_tee() -> TurnEventTee:
    global _TEE
    if _TEE is None:
        _TEE = TurnEventTee()
    return _TEE