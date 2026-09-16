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

import hashlib
import re
import threading
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, Optional, Sequence, Tuple

__all__ = [
    "VerdictKind", "WaitDirective", "Verdict", "Gate",
    "VerdictParseError", "JudgeTransportError",
    "JudgeCircuit", "ParseCircuitOpen", "TransportCircuitOpen",
    "JUDGE_PROMPT", "MAX_GATE_OUTPUT_CHARS", "JUDGE_INPUT_CHARS",
    "MAX_BARRIER_WAIT_S",
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
    #: consecutive failures allowed before this gate BLOCKs instead of
    #: CONTINUE-ing forever; ``None`` (default) is unlimited, unchanged
    #: from before this field existed.
    max_retries: Optional[int] = None


class VerdictParseError(ValueError):
    """The judge spoke outside the closed vocabulary or its directive schema."""


class JudgeTransportError(Exception):
    """The judge could not be reached — a wire problem, not an answer."""


#: Fitted by measurement, not taste: a continuation prompt is re-read by the
#: model next turn, so it must be bounded, but it must survive several
#: gate outputs stitched by upstream callers. 4000 chars is generous.
MAX_GATE_OUTPUT_CHARS = 4000

#: The judge sees claims, not the whole transcript; bounded next to the gate
#: output cap so a single call site can't blow the same budget the gates do.
JUDGE_INPUT_CHARS = 8000

#: A WAIT barrier expires after this long — an unbounded wait target is a
#: stuck loop by another name.
MAX_BARRIER_WAIT_S = 1800.0

_TRUNCATION_MARKER = "[gate output truncated]\n"


def _fingerprint(claims: Any) -> str:
    """A stable content hash of ``claims`` (A02-G15).

    A gate's ``check`` must not call a model (documented contract) — it is
    deterministic, so re-running it on byte-identical claims can never
    produce a different answer. The fingerprint lets ``verdict()`` skip the
    redundant re-run on an unchanged workspace between turns and replay the
    cached pass/fail instead, with no change to any observable outcome.
    """
    return hashlib.sha256(repr(claims).encode("utf-8", "replace")).hexdigest()



def _bound(text: str, limit: int = MAX_GATE_OUTPUT_CHARS) -> str:
    """Keep the TAIL of ``text`` — that is where a failure's diagnostic
    line lives — prefixed with a marker that survives the bound itself."""
    if len(text) <= limit:
        return text
    kept = max(limit - len(_TRUNCATION_MARKER), 0)
    return _TRUNCATION_MARKER + text[len(text) - kept:]


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
                if not _INT.match(value) or int(value) < 1:
                    raise VerdictParseError(f"wait_on_pid must be a positive integer: {value!r}")
                kwargs["wait_on_pid"] = int(value)
            else:
                if not _FLOAT.match(value) or float(value) <= 0:
                    raise VerdictParseError(
                        f"wait_for_seconds must be a positive number: {value!r}")
                kwargs["wait_for_seconds"] = min(float(value), MAX_BARRIER_WAIT_S)
        if not kwargs:
            raise VerdictParseError("WAIT with no target (wait_on_pid or wait_for_seconds)")
        wait = WaitDirective(**kwargs)
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
    """Consecutive-failure counters for one judge, separating the two modes,
    plus the per-gate retry counters and turn counter for the same turn loop.

    Parse failures and transport failures count independently, and each
    resets the *other* (a flaky transport interleaved with parse failures
    must not trip the parse breaker on non-consecutive failures); a clean
    verdict resets both. This object is deliberately the only mutable state
    in the contract, so ``verdict`` itself stays a pure decision.
    """

    def __init__(self,
                 parse_limit: int = PARSE_BREAKER_LIMIT,
                 transport_limit: int = TRANSPORT_BREAKER_LIMIT,
                 max_turns: Optional[int] = None) -> None:
        self.parse_limit = parse_limit
        self.transport_limit = transport_limit
        self.max_turns = max_turns
        self.parse_failures = 0
        self.transport_failures = 0
        self.turns = 0
        self.gate_attempts: Dict[str, int] = {}
        #: A02-G15: (fingerprint, passed) of the last real check per gate,
        #: for fingerprint-skip replay — never populated for a raising check.
        self.gate_fingerprints: Dict[str, Tuple[str, bool]] = {}

    def _reset(self) -> None:
        self.parse_failures = 0
        self.transport_failures = 0

    def record_parse_failure(self) -> bool:
        """Count one parse failure; True when the breaker trips."""
        self.parse_failures += 1
        self.transport_failures = 0
        return self.parse_failures >= self.parse_limit

    def record_transport_failure(self) -> bool:
        """Count one transport failure; True when the breaker trips."""
        self.transport_failures += 1
        self.parse_failures = 0
        return self.transport_failures >= self.transport_limit

    def parse_open(self) -> bool:
        return self.parse_failures >= self.parse_limit

    def transport_open(self) -> bool:
        return self.transport_failures >= self.transport_limit

    def record_gate_failure(self, gate_name: str) -> int:
        """Count one failure of ``gate_name``; returns the new attempt count."""
        self.gate_attempts[gate_name] = self.gate_attempts.get(gate_name, 0) + 1
        return self.gate_attempts[gate_name]

    def reset_gate(self, gate_name: str) -> None:
        self.gate_attempts.pop(gate_name, None)

    def gate_replay(self, gate_name: str, fingerprint: str) -> Optional[bool]:
        """The cached pass/fail for ``gate_name`` at this exact fingerprint,
        or ``None`` when nothing is cached (a fresh gate, or the workspace
        changed since the last real check)."""
        cached = self.gate_fingerprints.get(gate_name)
        if cached is not None and cached[0] == fingerprint:
            return cached[1]
        return None

    def record_gate_result(self, gate_name: str, fingerprint: str, passed: bool) -> None:
        self.gate_fingerprints[gate_name] = (fingerprint, passed)


def _call_judge(judge: Callable[[Any], str], claims: Any,
                 timeout: Optional[float]) -> str:
    """Call ``judge(claims)``, treating a hang past ``timeout`` as a
    transport failure like an unreachable judge. The worker thread is
    abandoned (daemon) on timeout, not killed — Python cannot force that —
    but the caller stops waiting on it."""
    if timeout is None:
        return judge(claims)

    outcome: Dict[str, Any] = {}

    def _run() -> None:
        try:
            outcome["value"] = judge(claims)
        except BaseException as exc:  # noqa: BLE001 - re-raised on the caller's thread
            outcome["error"] = exc

    worker = threading.Thread(target=_run, daemon=True)
    worker.start()
    worker.join(timeout)
    if worker.is_alive():
        raise JudgeTransportError(f"judge did not respond within {timeout}s")
    if "error" in outcome:
        raise outcome["error"]
    return outcome["value"]


# -- the decision --------------------------------------------------------------

def verdict(claims: Any,
            gates: Sequence[Gate],
            judge: Optional[Callable[[Any], str]] = None,
            circuit: Optional[JudgeCircuit] = None,
            gate_output_limit: int = MAX_GATE_OUTPUT_CHARS,
            judge_timeout: Optional[float] = None) -> Verdict:
    """Decide one evaluation turn: gates first, judge second, breakers last.

    Args:
        claims: what the turn produced — passed through to gates; the judge
            sees it too, bounded to ``JUDGE_INPUT_CHARS`` when it is text.
        gates: deterministic checks, run in order. The first failure
            short-circuits: its bounded ``output`` becomes the continuation
            prompt and the judge is never called. A gate whose ``check``
            raises is a failed gate with a diagnostic, not a crash. A gate
            with ``max_retries`` set BLOCKs once its own attempts on
            ``circuit`` exceed that budget, instead of CONTINUE-ing forever.
        judge: the model hook, flag-off by default (``None``). Must return a
            string in the closed vocabulary; raise :class:`JudgeTransportError`
            when unreachable. A call exceeding ``judge_timeout`` counts as a
            transport failure the same way.
        circuit: the breaker state, gate-attempt counters and turn counter,
            all in the one mutable object. Required once a live judge is
            about to be consulted (i.e. gates already passed) — a circuit
            created on demand cannot persist breaker state across calls,
            which previously left the breakers silently inert.
        judge_timeout: seconds to wait for the judge before treating the
            call as unreachable.

    A gate failure is a CONTINUE carrying the gate's prompt — the work is not
    done, and the model is told what to produce. With no judge wired, a
    gate-passing turn also CONTINUEs: nothing claims DONE without evidence.
    """
    circuit_given = circuit is not None
    if circuit is None:
        circuit = JudgeCircuit()

    circuit.turns += 1
    if circuit.max_turns is not None and circuit.turns > circuit.max_turns:
        return Verdict(
            kind=VerdictKind.BLOCKED,
            reason=f"turn budget exhausted ({circuit.max_turns} turns)",
            source="turn-budget",
        )

    for gate in gates:
        fingerprint = _fingerprint(claims)
        replay = circuit.gate_replay(gate.name, fingerprint)
        if replay is not None:
            passed = replay
        else:
            try:
                passed = gate.check(claims)
            except Exception as exc:  # noqa: BLE001 - a raising gate is a failed gate
                return Verdict(
                    kind=VerdictKind.CONTINUE,
                    reason=f"gate {gate.name} raised {type(exc).__name__}: {exc}",
                    source="gate",
                    continuation_prompt=_bound(
                        f"{gate.output}\n[gate could not run: {type(exc).__name__}: {exc}]",
                        gate_output_limit,
                    ),
                )
            circuit.record_gate_result(gate.name, fingerprint, passed)
        if passed:
            circuit.reset_gate(gate.name)
            continue
        attempts = circuit.record_gate_failure(gate.name)
        if gate.max_retries is not None and attempts > gate.max_retries:
            return Verdict(
                kind=VerdictKind.BLOCKED,
                reason=f"gate {gate.name} exhausted after {attempts} attempts",
                source="gate-exhausted",
                continuation_prompt=_bound(gate.output, gate_output_limit),
            )
        return Verdict(
            kind=VerdictKind.CONTINUE,
            reason=f"gate {gate.name} failed",
            source="gate",
            continuation_prompt=_bound(gate.output, gate_output_limit),
        )

    if judge is None:
        return Verdict(
            kind=VerdictKind.CONTINUE,
            reason="gates passed; no judge wired (flag-off)",
            source="judge-disabled",
        )

    if not circuit_given:
        raise TypeError(
            "verdict(): a JudgeCircuit must be passed explicitly once a judge "
            "is about to be consulted — a circuit created on demand is "
            "discarded after the call and cannot persist breaker state "
            "across turns, which leaves the breakers silently inert."
        )

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

    judge_claims = claims
    if isinstance(claims, str) and len(claims) > JUDGE_INPUT_CHARS:
        judge_claims = _bound(claims, JUDGE_INPUT_CHARS)

    try:
        raw = _call_judge(judge, judge_claims, judge_timeout)
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