# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The interrupt algebra's decision core: stop / steer / redirect.

Three protocol verbs for a mid-turn arrival, with distinct safety
properties (Hermes review §2):

- ``STOP`` (interrupt) — hard stop. The abort itself is race-safe via
  ``TurnActivity`` generation claims (Hermes ``agent/interrupt_control.py``,
  ``require_generation``): an abort that loses the race to a finishing turn
  *declines* instead of double-firing.
- ``STEER`` — never interrupts. User text is appended to the **last tool
  result** once the current tool batch finishes; multiple steers
  concatenate (Hermes ``tui_gateway/session_auto_continue.py:234``).
- ``REDIRECT`` — the middle ground: cancels the current model request only
  (completed work kept, partial output becomes context, the correction
  appended as a real user message, loop retries); during a tool call it
  degrades to steer and asks the tool to **yield, never kill**.

This module is pure: ``decide_midturn`` takes predicates as arguments and
the state machine (Packet 07 Phase B) supplies them. No locks live here —
the one shared stop-vs-correction lock is the ``TurnActivity`` lock at the
integration edge, so a stop accepted at the same edge as a correction can
never produce a double-fire or a retry.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

STEER_MARKER = "\n[steered] "


class Verdict(enum.Enum):
    """Which protocol verb applies to a mid-turn arrival."""

    NORMAL_TURN = "normal_turn"
    STOP = "stop"
    STEER = "steer"
    REDIRECT = "redirect"


@dataclass
class Decision:
    """The verb plus why it was chosen (for the dashboard confirmation line)."""

    verb: Verdict
    reason: str
    text: str = ""
    tool_batch_in_flight: bool = False
    in_model_request: bool = False
    notes: List[str] = field(default_factory=list)


def decide_midturn(
    turn_active: bool,
    is_command: bool,
    text: str,
    tool_batch_in_flight: bool = False,
    in_model_request: bool = False,
) -> Decision:
    """Route one mid-turn arrival to its verb.

    Pure over its arguments. Phase B (state machine) wires the predicates;
    until then ``in_model_request`` defaults False and REDIRECT is only
    decided when the caller reports it.
    """
    # Rule 0 (Hermes gateway/run_inbound.py:599-651, idle branch): an
    # arrival while the agent is idle is just an ordinary turn.
    if not turn_active:
        return Decision(Verdict.NORMAL_TURN, "agent idle; ordinary turn", text)

    # Rule 1 (Hermes run_inbound.py busy branch, command bypass): explicit
    # commands bypass steering — they act, they don't append.
    if is_command:
        # Demotion rule (Hermes interrupt_control.py): interrupt demotes to
        # queue/steer when a turn-critical subsystem is mid-flight — never
        # kill a tool to deliver guidance.
        if tool_batch_in_flight:
            return Decision(
                Verdict.STEER,
                "interrupt demoted: tool batch in flight; steer instead of kill",
                text,
                tool_batch_in_flight=True,
                in_model_request=in_model_request,
                notes=["interrupt_demoted_to_steer"],
            )
        return Decision(Verdict.STOP, "command bypass; generation-claimed stop", text)

    # Rule 2 (redirect middle ground): plain text arriving while the state
    # machine is inside a model request cancels only that request —
    # completed tool work is kept. Only decided when the caller reports the
    # predicate (Phase B wires it).
    if in_model_request and not tool_batch_in_flight:
        return Decision(
            Verdict.REDIRECT,
            "inside model request; cancel request, keep completed work, retry",
            text,
            tool_batch_in_flight=False,
            in_model_request=True,
        )

    # Rule 3 (Hermes session_auto_continue.py:234): plain text while busy
    # never interrupts — it steers into the last tool result once the
    # current batch finishes.
    return Decision(Verdict.STEER, "busy; steer into last tool result", text)


def apply_steer_to_results(
    results: List[Dict[str, Any]], text: str
) -> Optional[str]:
    """Append a steer to the **last** tool result; steers concatenate.

    Appends ``\\n[steered] <text>`` to the last entry's ``output`` and
    returns the new output. Returns ``None`` (no-op) when there is no tool
    result to steer into — an arrival is never silently dropped in that
    case: the caller's single replace-not-grow pending slot (Packet 07
    Phase B) holds it for the next batch boundary instead.
    """
    if not results:
        return None
    last = results[-1]
    current = last.get("output") or ""
    appended = f"{current}{STEER_MARKER}{text}"
    last["output"] = appended
    return appended