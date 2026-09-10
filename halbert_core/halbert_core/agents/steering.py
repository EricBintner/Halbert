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

#: The steered block's open and close markers (A07-G4). A bare
#: ``[steered] `` prefix left the model to infer where the user's words
#: ended and the tool's output resumed -- and told it nothing about whose
#: words they were. A labelled wrapper with a matching closer is the
#: vocabulary the rest of the prompt already uses, and the prompt-side
#: contract (``prompts.agent_prompts.STEER_CONTRACT``) says what it means.
STEER_MARKER = "\n[steered]\n"
STEER_MARKER_CLOSE = "\n[/steered]\n"

#: The refusal codes the algebra emits. A closed set, the way the
#: admission module's ``reason_code`` is a closed set: the caller renders
#: it, it never renders a free-text reason at a user.
REASON_BELOW_TURN_ROLE_FLOOR = "below_turn_role_floor"
REASON_EMPTY_ARRIVAL = "empty_arrival"
REASON_TURN_ALREADY_STOPPED = "turn_already_stopped"
REASON_ANSWER_ALREADY_COMMITTED = "answer_already_committed"


#: The sentence each refusal code renders as. One message per code --
#: the closed-set rule the admission module holds to.
_REFUSAL_REASONS = {
    "below_turn_role_floor":
        "arrival stands below the running turn's role floor",
    "empty_arrival": "an empty arrival is not a steer",
    "turn_already_stopped":
        "the turn was stopped; send this as the next turn",
    "answer_already_committed":
        "the answer is already committed; send this as the next turn",
}


class Verdict(enum.Enum):
    """Which protocol verb applies to a mid-turn arrival."""

    NORMAL_TURN = "normal_turn"
    STOP = "stop"
    STEER = "steer"
    REDIRECT = "redirect"
    #: The arrival may not act on the running turn at all (R-01 Phase A):
    #: its speaker stands below the floor the running turn was admitted
    #: at. A refusal is a verb, not an error -- the arrival's own stream
    #: carries it, the same way an accepted steer carries its receipt.
    REFUSED = "refused"


@dataclass
class Decision:
    """The verb plus why it was chosen (for the dashboard confirmation line)."""

    verb: Verdict
    reason: str
    text: str = ""
    tool_batch_in_flight: bool = False
    in_model_request: bool = False
    notes: List[str] = field(default_factory=list)
    #: Closed-set code for a REFUSED verdict; empty for every other verb.
    reason_code: str = ""


def decide_midturn(
    turn_active: bool,
    is_command: bool,
    text: str,
    tool_batch_in_flight: bool = False,
    in_model_request: bool = False,
    below_role_floor: bool = False,
    refusal: str = "",
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

    # Rule 0.5 (R-01 Phase A, the OSS pass's #1 finding): authority
    # first. Every verb below acts ON the running turn -- a steer joins
    # its context, a stop ends it -- so a speaker who stands below the
    # floor that turn was admitted at may use none of them. Ordered
    # ahead of the command bypass on purpose: "/stop" is the strongest
    # verb, not an exemption from the check.
    if below_role_floor:
        return Decision(
            Verdict.REFUSED,
            "arrival stands below the running turn's role floor",
            text,
            tool_batch_in_flight=tool_batch_in_flight,
            in_model_request=in_model_request,
            reason_code=REASON_BELOW_TURN_ROLE_FLOOR,
        )

    # Rule 0.6 (A07-G3, A07 bug 1): the verdict must be the truth. A
    # steer accepted after the turn was stopped, or after its answer was
    # already committed, used to be confirmed and then dropped at a batch
    # boundary that never came -- and an empty arrival joined the turn as
    # a blank line. Refuse them here, so the surface can send the text as
    # the next turn instead of believing it landed in this one.
    if refusal:
        return Decision(
            Verdict.REFUSED,
            _REFUSAL_REASONS.get(refusal, "arrival refused"),
            text,
            tool_batch_in_flight=tool_batch_in_flight,
            in_model_request=in_model_request,
            reason_code=refusal,
        )

    # Rule 1 (Hermes run_inbound.py busy branch, command bypass): explicit
    # commands bypass steering — they act, they don't append.
    #
    # A07-G2: this branch used to demote a ``/stop`` arriving during a
    # tool batch to a steer, citing the interrupt-demotion rule. That
    # rule is "never kill a tool to deliver *guidance*" -- it belongs to
    # Rule 3's plain text, which steers anyway. Transcribed onto the stop
    # verb it meant the one verb the algebra names "stop" could not stop
    # the one thing a user actually wants stopped: a running command.
    # Rule 1 is unconditional; the redirect verb keeps yield-never-kill.
    if is_command:
        return Decision(
            Verdict.STOP,
            "command bypass; generation-claimed stop",
            text,
            tool_batch_in_flight=tool_batch_in_flight,
            in_model_request=in_model_request,
        )

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

    Wraps ``text`` in the ``[steered]`` / ``[/steered]`` pair (A07-G4) and
    appends it to the last entry's ``output``, returning the new output.
    Returns ``None`` (no-op) when there is no tool result to steer into —
    an arrival is never silently dropped in that case: the caller holds it
    for the next batch boundary instead.
    """
    if not results:
        return None
    last = results[-1]
    current = last.get("output") or ""
    appended = f"{current}{STEER_MARKER}{text}{STEER_MARKER_CLOSE}"
    last["output"] = appended
    return appended