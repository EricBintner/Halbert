# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The gates-before-judge verdict contract (Hermes ``judge_goal`` shape).

An evaluation turn asks "did the work finish?" The tempting shape is to hand
the transcript to an LLM judge and read its answer. That shape fails in three
ways at once: it spends model calls on turns a deterministic check already
settled, it invites the judge to congratulate the work into a DONE, and when
the judge misbehaves there is no difference between *the judge is broken* and
*the work is blocked*.

The contract here separates the layers:

**Gates first, and they short-circuit.** Deterministic gates run in order; the
first failing gate's *bounded output* becomes the continuation prompt and no
judge is ever called on that turn. A gate failure is not a judgment, it is a
measurement — the deliverable is missing, and the model is told exactly what
to go produce.

**A closed vocabulary.** The judge may answer exactly one of ``DONE``,
``BLOCKED``, ``CONTINUE``, ``WAIT``, optionally with a structured wait
directive (``wait_on_pid`` / ``wait_for_seconds``) carried as data, never as
prose. Anything else — lowercase, chatty, novel vocabularies — is a parse
failure, because a judge that cannot hold the vocabulary is a judge whose
other words cannot be trusted either.

**Failure modes are separated.** A *parse* failure means the judge's output
channel is broken: consecutive ones open a circuit and pause the judge (fail
closed — stop spending on a judge that will not speak the protocol). A
*transport* failure means the wire hiccuped: a single one fails open to
CONTINUE (do not stall the loop on a transient), but repeats open their own
circuit — a judge that cannot be reached is not a transient after the third
try. Both breakers reset on a clean verdict.

Nothing here calls a model. The judge is a callable the caller wires in; with
none wired (the default, flag-off), a gate-passing turn simply CONTINUEs —
nothing claims DONE without evidence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Optional, Sequence

__all__ = [
    "VerdictKind", "WaitDirective", "Verdict", "Gate",
    "VerdictParseError", "JudgeTransportError",
    "JudgeCircuit", "ParseCircuitOpen", "TransportCircuitOpen",
    "JUDGE_PROMPT", "MAX_GATE_OUTPUT_CHARS",
    "parse_verdict", "verdict",
]


class VerdictKind(Enum):
    """The closed vocabulary. There is no fifth answer."""

    DONE = "done"
    BLOCKED = "blocked"
    CONTINUE = "continue"
    WAIT = "wait"


@dataclass(frozen=True)
class WaitDirective:
    """A structured wait instruction — data, never prose."""

    wait_on_pid: Optional[int] = None
    wait_for_seconds: Optional[float] = None


@dataclass(frozen=True)
class Verdict:
    """One evaluation outcome, whatever layer produced it."""

    kind: VerdictKind
    #: why — a gate name, the judge's evidence line, or a breaker note
    reason: str
    #: only when ``kind is WAIT``
    wait: Optional[WaitDirective] = None
    #: which layer decided: "gate" | "judge" | "parse-failure" |
    #: "parse-circuit-breaker" | "transport-fail-open" |
    #: "transport-circuit-breaker" | "judge-disabled"
    source: str = "judge"
    #: the bounded continuation prompt, only on a gate failure
    continuation_prompt: Optional[str] = None


@dataclass(frozen=True)
class Gate:
    """A deterministic quality gate. ``check`` must not call a model."""

    name: str
    #: True means the gate passes
    check: Callable[[Any], bool]
    #: the bounded continuation prompt when the gate fails
    output: str


class VerdictParseError(ValueError):
    """The judge spoke outside the closed vocabulary or its directive schema."""


class JudgeTransportError(Exception):
    """The judge could not be reached — a wire problem, not an answer."""


#: Fitted by measurement, not taste: a continuation prompt is re-read by the
#: model next turn, so it must be bounded, but it must survive several
#: gate outputs stitched by upstream callers. 4000 chars is generous.
MAX_GATE_OUTPUT_CHARS = 4000


def _bound(text: str) -> str:
    if len(text) <= MAX_GATE_OUTPUT_CHARS:
        return text
    return text[:MAX_GATE_OUTPUT_CHARS] + "\n[gate output truncated]"


# -- parsing ------------------------------------------------------------------

#: The closed vocabulary, uppercase-only.
_VOCABULARY = frozenset(v.name for v in VerdictKind)
#: WAIT may carry only these directive keys, as data.
_DIRECTIVE_KEYS = {"wait_on_pid", "wait_for_seconds"}
_INT = re.compile(r"^-?\d+$")
_FLOAT = re.compile(r"^-?\d+(?:\.\d+)?$")


def parse_verdict(raw: str) -> Verdict:
    """Parse one judge response against the closed vocabulary.

    The first token must be exactly one of the four uppercase verdict words;
    the rest of the line is the judge's evidence and is carried as ``reason``
    (for WAIT, the tokens must all be directive pairs instead). Everything
    else — lowercase, novel vocabularies, chatter before the word — raises
    :class:`VerdictParseError`, because a judge that cannot hold the verdict
    token cannot be trusted with the evidence either.
    """
    tokens = raw.split()
    if not tokens:
        raise VerdictParseError("empty response")
    word = tokens[0]
    if word not in _VOCABULARY:
        raise VerdictParseError(f"unknown verdict: {word!r}")
    kind = VerdictKind[word]
    wait: Optional[WaitDirective] = None
    reason = " ".join(tokens[1:])
    if word == "WAIT":
        kwargs = {}
        for token in tokens[1:]:
            key, sep, value = token.partition("=")
            if not sep or key not in _DIRECTIVE_KEYS or "=" in value:
                raise VerdictParseError(f"unknown directive: {token!r}")
            if key == "wait_on_pid":
                if not _INT.match(value):
                    raise VerdictParseError(f"wait_on_pid must be an integer: {value!r}")
                kwargs["wait_on_pid"] = int(value)
            else:
                if not _FLOAT.match(value) or float(value) < 0:
                    raise VerdictParseError(
                        f"wait_for_seconds must be a non-negative number: {value!r}")
                kwargs["wait_for_seconds"] = float(value)
        wait = WaitDirective(**kwargs) if kwargs else None
        reason = ""
    elif any(t.partition("=")[0] in _DIRECTIVE_KEYS for t in tokens[1:]):
        raise VerdictParseError("only WAIT carries a directive")
    return Verdict(kind=kind, reason=reason, wait=wait, source="judge")


# -- the flag-off judge prompt -------------------------------------------------

#: The prompt for the judge hook, kept here so the language is versioned with
#: the contract even while the hook is flag-off (no model calls until a caller
#: wires a judge through the model-picker's slots).
#:
#: The language is anti-self-congratulation on purpose. Left alone, a judge
#: drifts toward agreement: it reads a confident summary and calls it DONE.
#: The counterweight is to demand *evidence* — DONE requires the deliverable
#: to actually exist, and BLOCKED is a refusal, not a completion.
JUDGE_PROMPT = """\
You are evaluating whether a unit of work is finished. You are a measurement, \
not a cheerleader.

Require specific evidence for every claim. A confident description of work is \
not work. DONE requires the deliverable to actually exist — name the file, \
the pid, the row, the output that proves it. If you cannot point at it, the \
verdict is CONTINUE. BLOCKED is a refusal, not a completion: use it only when \
a genuine external dependency cannot be met, and say exactly which.

Answer with exactly one verdict word — DONE, BLOCKED, CONTINUE, or WAIT — as \
the first token, then one short line of the specific evidence behind it (on a \
WAIT, directive pairs instead: wait_on_pid=<int>, wait_for_seconds=<seconds>).\
"""


# -- circuit breakers ----------------------------------------------------------

#: Consecutive parse failures before the judge is paused. Three means the
#: protocol is broken, not that one response was noisy.
PARSE_BREAKER_LIMIT = 3
#: Repeated transport failures before the judge is paused. A single one is a
#: transient; this many means the judge cannot be reached.
TRANSPORT_BREAKER_LIMIT = 3


class ParseCircuitOpen(RuntimeError):
    """The parse breaker is open — the judge is paused."""


class TransportCircuitOpen(RuntimeError):
    """The transport breaker is open — the judge is paused."""


class JudgeCircuit:
    """Consecutive-failure counters for one judge, separating the two modes.

    Parse failures and transport failures count independently; a clean verdict
    resets both. This object is deliberately the only mutable state in the
    contract, so ``verdict`` itself stays a pure decision.
    """

    def __init__(self,
                 parse_limit: int = PARSE_BREAKER_LIMIT,
                 transport_limit: int = TRANSPORT_BREAKER_LIMIT) -> None:
        self.parse_limit = parse_limit
        self.transport_limit = transport_limit
        self.parse_failures = 0
        self.transport_failures = 0

    def _reset(self) -> None:
        self.parse_failures = 0
        self.transport_failures = 0

    def record_parse_failure(self) -> bool:
        """Count one parse failure; True when the breaker trips."""
        self.parse_failures += 1
        return self.parse_failures >= self.parse_limit

    def record_transport_failure(self) -> bool:
        """Count one transport failure; True when the breaker trips."""
        self.transport_failures += 1
        return self.transport_failures >= self.transport_limit

    def parse_open(self) -> bool:
        return self.parse_failures >= self.parse_limit

    def transport_open(self) -> bool:
        return self.transport_failures >= self.transport_limit


# -- the decision --------------------------------------------------------------

def verdict(claims: Any,
            gates: Sequence[Gate],
            judge: Optional[Callable[[Any], str]] = None,
            circuit: Optional[JudgeCircuit] = None,
            gate_output_limit: int = MAX_GATE_OUTPUT_CHARS) -> Verdict:
    """Decide one evaluation turn: gates first, judge second, breakers last.

    Args:
        claims: what the turn produced — passed through to gates and judge.
        gates: deterministic checks, run in order. The first failure
            short-circuits: its bounded ``output`` becomes the continuation
            prompt and the judge is never called.
        judge: the model hook, flag-off by default (``None``). Must return a
            string in the closed vocabulary; raise :class:`JudgeTransportError`
            when unreachable.
        circuit: the breaker state; one per judge, created on demand.

    A gate failure is a CONTINUE carrying the gate's prompt — the work is not
    done, and the model is told what to produce. With no judge wired, a
    gate-passing turn also CONTINUEs: nothing claims DONE without evidence.
    """
    for gate in gates:
        if not gate.check(claims):
            return Verdict(
                kind=VerdictKind.CONTINUE,
                reason=f"gate {gate.name} failed",
                source="gate",
                continuation_prompt=_bound(gate.output)[:gate_output_limit],
            )

    if judge is None:
        return Verdict(
            kind=VerdictKind.CONTINUE,
            reason="gates passed; no judge wired (flag-off)",
            source="judge-disabled",
        )

    if circuit is None:
        circuit = JudgeCircuit()

    # An already-open breaker pauses the judge without spending a call.
    if circuit.parse_open():
        return Verdict(
            kind=VerdictKind.BLOCKED,
            reason=(f"parse circuit open after {circuit.parse_failures} "
                    "consecutive unparseable responses; judge paused"),
            source="parse-circuit-breaker",
        )
    if circuit.transport_open():
        return Verdict(
            kind=VerdictKind.BLOCKED,
            reason=(f"transport circuit open after {circuit.transport_failures} "
                    "consecutive unreachable calls; judge paused"),
            source="transport-circuit-breaker",
        )

    try:
        raw = judge(claims)
    except JudgeTransportError as exc:
        trips = circuit.record_transport_failure()
        if trips:
            return Verdict(
                kind=VerdictKind.BLOCKED,
                reason=f"judge unreachable {circuit.transport_failures} times in a row ({exc})",
                source="transport-circuit-breaker",
            )
        # fail open: one wire hiccup must not stall the loop
        return Verdict(
            kind=VerdictKind.CONTINUE,
            reason=f"judge transport failure ({exc}); failing open to continue",
            source="transport-fail-open",
        )

    try:
        parsed = parse_verdict(raw)
    except VerdictParseError as exc:
        trips = circuit.record_parse_failure()
        if trips:
            return Verdict(
                kind=VerdictKind.BLOCKED,
                reason=f"judge paused: {circuit.parse_failures} consecutive parse failures ({exc})",
                source="parse-circuit-breaker",
            )
        return Verdict(
            kind=VerdictKind.CONTINUE,
            reason=f"unparseable judge response ({exc}); continuing without it",
            source="parse-failure",
        )

    circuit._reset()
    return Verdict(
        kind=parsed.kind,
        reason=parsed.reason or raw.strip(),
        wait=parsed.wait,
        source="judge",
    )