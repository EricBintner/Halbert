# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The gates-before-judge verdict contract (Hermes ``judge_goal`` shape).

Four rules, one test each minimum:

(1) deterministic gates run FIRST and short-circuit — a failing gate's bounded
output becomes the continuation prompt and no judge is spent on the turn;
(2) the judge speaks a closed vocabulary (DONE / BLOCKED / CONTINUE / WAIT)
with an optional structured wait directive — anything else is a parse failure;
(3) the (flag-off) judge prompt demands specific evidence — anti-self-
congratulation language, because a verdict is a measurement, not a mood;
(4) failure modes are separated: consecutive PARSE failures auto-pause the
judge (its output channel is broken — fail closed), while TRANSPORT failures
fail open to CONTINUE on singles and only circuit-break on repeats.
"""

import pytest

from halbert_core.continuity import verdict as verdict_module
from halbert_core.continuity.verdict import (
    Gate,
    JUDGE_PROMPT,
    JudgeTransportError,
    ParseCircuitOpen,
    TransportCircuitOpen,
    Verdict,
    VerdictKind,
    VerdictParseError,
    WaitDirective,
    parse_verdict,
    verdict,
)


def _gate(name="output-exists", ok=False, output="the deliverable is missing"):
    return Gate(name=name, check=lambda claims: ok, output=output)


def _never_called(claims):
    raise AssertionError("judge must not be called when a gate already failed")


class TestGatesBeforeJudge:
    def test_failing_gate_short_circuits_judge(self):
        """No judge is spent on a turn whose gate already failed."""
        result = verdict({}, gates=[_gate()], judge=_never_called)
        assert result.kind is VerdictKind.CONTINUE
        assert result.source == "gate"
        assert result.continuation_prompt == "the deliverable is missing"

    def test_first_failing_gate_wins(self):
        gates = [
            Gate(name="g1", check=lambda c: False, output="first gate output"),
            Gate(name="g2", check=lambda c: False, output="second gate output"),
        ]
        result = verdict({}, gates=gates, judge=_never_called)
        assert result.continuation_prompt == "first gate output"

    def test_gate_output_is_bounded(self):
        gates = [Gate(name="g", check=lambda c: False, output="x" * 10_000)]
        result = verdict({}, gates=gates, judge=_never_called)
        assert len(result.continuation_prompt) <= verdict_module.MAX_GATE_OUTPUT_CHARS

    def test_passing_gates_reach_the_judge(self):
        claims = {"deliverable": "present"}
        judge_calls = []

        def judge(c):
            judge_calls.append(c)
            return "DONE the file exists at /tmp/out with 40 lines"

        result = verdict(claims, gates=[Gate(name="g", check=lambda c: True, output="")], judge=judge)
        assert judge_calls == [claims]
        assert result.kind is VerdictKind.DONE
        assert result.source == "judge"

    def test_gate_failure_reason_names_the_gate(self):
        result = verdict({}, gates=[_gate(name="output-exists")], judge=_never_called)
        assert "output-exists" in result.reason


class TestClosedVocabulary:
    def test_parse_accepts_each_closed_term(self):
        for word, kind in [
            ("DONE", VerdictKind.DONE),
            ("BLOCKED", VerdictKind.BLOCKED),
            ("CONTINUE", VerdictKind.CONTINUE),
            ("WAIT", VerdictKind.WAIT),
        ]:
            parsed = parse_verdict(word)
            assert parsed.kind is kind

    def test_parse_rejects_unknown_verdict(self):
        with pytest.raises(VerdictParseError):
            parse_verdict("FANCY")

    def test_parse_rejects_lowercase_and_padding(self):
        """The vocabulary is closed, not forgiving — a chatty judge is a
        broken judge."""
        with pytest.raises(VerdictParseError):
            parse_verdict("  done ")

    def test_parse_rejects_empty(self):
        with pytest.raises(VerdictParseError):
            parse_verdict("")

    def test_wait_directive_carried_structured(self):
        parsed = parse_verdict("WAIT wait_on_pid=1234")
        assert parsed.kind is VerdictKind.WAIT
        assert parsed.wait == WaitDirective(wait_on_pid=1234)

    def test_wait_for_seconds_carried_structured(self):
        parsed = parse_verdict("WAIT wait_for_seconds=30")
        assert parsed.wait == WaitDirective(wait_for_seconds=30.0)

    def test_wait_directive_is_optional(self):
        assert parse_verdict("WAIT").wait is None

    def test_wait_rejects_unknown_directive_key(self):
        with pytest.raises(VerdictParseError):
            parse_verdict("WAIT wait_on_process=init")

    def test_wait_rejects_non_integer_pid(self):
        with pytest.raises(VerdictParseError):
            parse_verdict("WAIT wait_on_pid=systemd")

    def test_non_wait_verdict_cannot_carry_directive(self):
        with pytest.raises(VerdictParseError):
            parse_verdict("DONE wait_on_pid=1")


class TestFailureModeSeparation:
    def test_single_parse_failure_continues_but_counts(self):
        calls = []
        judge = _parse_then_ok(1, calls)
        circuit = verdict_module.JudgeCircuit()
        result = verdict({}, gates=[], judge=judge, circuit=circuit)
        assert result.kind is VerdictKind.CONTINUE
        assert result.source == "parse-failure"
        assert circuit.parse_failures == 1

    def test_consecutive_parse_failures_auto_pause(self):
        """Three consecutive unparseable outputs mean the judge's output
        channel is broken: fail closed, stop spending on it."""
        circuit = verdict_module.JudgeCircuit()
        calls = []
        judge = _parse_then_ok(3, calls)
        for _ in range(2):
            assert verdict({}, gates=[], judge=judge, circuit=circuit).kind is VerdictKind.CONTINUE
        result = verdict({}, gates=[], judge=judge, circuit=circuit)
        assert result.kind is VerdictKind.BLOCKED
        assert result.source == "parse-circuit-breaker"
        # and the judge is not called again while the breaker is open
        n = len(calls)
        assert verdict({}, gates=[], judge=judge, circuit=circuit).kind is VerdictKind.BLOCKED
        assert len(calls) == n

    def test_parse_breaker_resets_on_success(self):
        circuit = verdict_module.JudgeCircuit()
        calls = []
        judge = _parse_then_ok(1, calls)
        verdict({}, gates=[], judge=judge, circuit=circuit)
        assert verdict({}, gates=[], judge=judge, circuit=circuit).source == "judge"
        assert circuit.parse_failures == 0

    def test_single_transport_failure_fails_open_to_continue(self):
        calls = []
        judge = _transport_then_ok(1, calls)
        circuit = verdict_module.JudgeCircuit()
        result = verdict({}, gates=[], judge=judge, circuit=circuit)
        assert result.kind is VerdictKind.CONTINUE
        assert result.source == "transport-fail-open"

    def test_repeated_transport_failures_circuit_break(self):
        """Repeats are not transients: stop calling a judge that cannot be
        reached."""
        circuit = verdict_module.JudgeCircuit()
        calls = []
        judge = _transport_then_ok(99, calls)
        for _ in range(verdict_module.TRANSPORT_BREAKER_LIMIT - 1):
            assert verdict({}, gates=[], judge=judge, circuit=circuit).kind is VerdictKind.CONTINUE
        result = verdict({}, gates=[], judge=judge, circuit=circuit)
        assert result.kind is VerdictKind.BLOCKED
        assert result.source == "transport-circuit-breaker"
        n = len(calls)
        assert verdict({}, gates=[], judge=judge, circuit=circuit).kind is VerdictKind.BLOCKED
        assert len(calls) == n

    def test_transport_breaker_resets_on_success(self):
        circuit = verdict_module.JudgeCircuit()
        calls = []
        judge = _transport_then_ok(1, calls)
        verdict({}, gates=[], judge=judge, circuit=circuit)
        assert verdict({}, gates=[], judge=judge, circuit=circuit).source == "judge"
        assert circuit.transport_failures == 0

    def test_parse_and_transport_counters_are_independent(self):
        circuit = verdict_module.JudgeCircuit()
        calls = []
        judge = _parse_then_ok(1, calls)
        verdict({}, gates=[], judge=judge, circuit=circuit)
        assert circuit.parse_failures == 1
        assert circuit.transport_failures == 0


class TestFlagOff:
    def test_no_judge_wired_returns_continue_without_model_calls(self):
        """The judge hook is flag-off: gates pass, no judge exists, the loop
        keeps moving — nothing claims DONE without evidence."""
        result = verdict({}, gates=[])
        assert result.kind is VerdictKind.CONTINUE
        assert result.source == "judge-disabled"

    def test_judge_prompt_requires_specific_evidence(self):
        assert "specific evidence" in JUDGE_PROMPT

    def test_judge_prompt_done_requires_the_deliverable_to_exist(self):
        assert "actually exist" in JUDGE_PROMPT

    def test_judge_prompt_blocked_is_a_refusal(self):
        assert "refusal, not a completion" in JUDGE_PROMPT


# -- helpers -----------------------------------------------------------------

def _parse_then_ok(failures, calls):
    def judge(claims):
        calls.append(1)
        if len(calls) <= failures:
            return "not a verdict at all"
        return "CONTINUE more work remains"
    return judge


def _transport_then_ok(failures, calls):
    def judge(claims):
        calls.append(1)
        if len(calls) <= failures:
            raise JudgeTransportError("connection reset")
        return "CONTINUE more work remains"
    return judge