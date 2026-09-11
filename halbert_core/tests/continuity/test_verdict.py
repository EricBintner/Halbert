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

import time

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

        result = verdict(claims, gates=[Gate(name="g", check=lambda c: True, output="")],
                          judge=judge, circuit=verdict_module.JudgeCircuit())
        assert judge_calls == [claims]
        assert result.kind is VerdictKind.DONE
        assert result.source == "judge"

    def test_gate_failure_reason_names_the_gate(self):
        result = verdict({}, gates=[_gate(name="output-exists")], judge=_never_called)
        assert "output-exists" in result.reason

    def test_gate_output_truncation_keeps_the_tail_where_the_diagnostic_is(self):
        # A02-G4 + own-bug 2: the origin keeps the TAIL of gate output (that
        # is where a test runner's failure line lives), and the truncation
        # marker must survive gate_output_limit's own re-slicing.
        output = "ok\n" * 3000 + "FAILED test_x: AssertionError"
        result = verdict({}, gates=[Gate(name="g", check=lambda c: False, output=output)],
                          judge=_never_called)
        assert "FAILED test_x" in result.continuation_prompt
        assert len(result.continuation_prompt) <= verdict_module.MAX_GATE_OUTPUT_CHARS

    def test_a_raising_gate_is_a_failed_gate_not_a_crash(self):
        # A02-G5: the origin converts a raising gate into a failed gate with
        # a diagnostic; today it propagates and crashes verdict().
        gate = Gate(name="flaky", check=lambda c: 1 / 0, output="the deliverable is missing")
        result = verdict({}, gates=[gate], judge=_never_called)
        assert result.kind is VerdictKind.CONTINUE
        assert result.source == "gate"
        assert "flaky" in result.reason
        assert "ZeroDivisionError" in result.reason

    def test_gate_exhausts_after_max_retries_and_blocks(self):
        # A02-G6: a permanently failing gate must not CONTINUE forever once
        # it has a retry budget.
        circuit = verdict_module.JudgeCircuit()
        gate = Gate(name="never-passes", check=lambda c: False, output="still missing",
                    max_retries=2)
        first = verdict({}, gates=[gate], judge=_never_called, circuit=circuit)
        second = verdict({}, gates=[gate], judge=_never_called, circuit=circuit)
        third = verdict({}, gates=[gate], judge=_never_called, circuit=circuit)
        assert first.kind is VerdictKind.CONTINUE
        assert second.kind is VerdictKind.CONTINUE
        assert third.kind is VerdictKind.BLOCKED
        assert third.source == "gate-exhausted"

    def test_turn_budget_exhausted_blocks_without_calling_the_judge(self):
        # A02-G6: a turn counter caps the whole loop, independent of any one
        # gate's own retry budget.
        circuit = verdict_module.JudgeCircuit(max_turns=2)
        gate = Gate(name="g", check=lambda c: True, output="")
        verdict({}, gates=[gate], judge=lambda c: "CONTINUE ok", circuit=circuit)
        verdict({}, gates=[gate], judge=lambda c: "CONTINUE ok", circuit=circuit)
        result = verdict({}, gates=[gate], judge=_never_called, circuit=circuit)
        assert result.kind is VerdictKind.BLOCKED
        assert result.source == "turn-budget"


class TestFingerprintReplay:
    """A02-G15: a gate's ``check`` is deterministic by contract, so re-running
    it on byte-identical claims can never change the answer — an unchanged
    workspace between two turns should replay the cached result instead of
    re-running the check, without changing any observable outcome (the
    retry counter, exhaustion, and continuation prompt all behave exactly
    as if the check had actually run again)."""

    def test_an_unchanged_claims_blob_is_not_re_checked(self):
        circuit = verdict_module.JudgeCircuit()
        calls = []

        def check(c):
            calls.append(c)
            return False

        gate = Gate(name="g", check=check, output="still missing")
        claims = {"deliverable": "missing"}
        verdict(claims, gates=[gate], judge=_never_called, circuit=circuit)
        verdict(claims, gates=[gate], judge=_never_called, circuit=circuit)
        verdict(claims, gates=[gate], judge=_never_called, circuit=circuit)
        assert len(calls) == 1

    def test_a_changed_claims_blob_re_runs_the_check(self):
        circuit = verdict_module.JudgeCircuit()
        calls = []

        def check(c):
            calls.append(c)
            return False

        gate = Gate(name="g", check=check, output="still missing")
        verdict({"deliverable": "missing"}, gates=[gate], judge=_never_called, circuit=circuit)
        verdict({"deliverable": "still missing"}, gates=[gate], judge=_never_called, circuit=circuit)
        assert len(calls) == 2

    def test_a_replayed_failure_still_counts_toward_exhaustion(self):
        # Same fixture as test_gate_exhausts_after_max_retries_and_blocks,
        # but proving the replay path (identical claims every call) reaches
        # the exact same exhaustion outcome as a freshly re-run check would.
        circuit = verdict_module.JudgeCircuit()
        gate = Gate(name="never-passes", check=lambda c: False, output="still missing",
                    max_retries=2)
        first = verdict({}, gates=[gate], judge=_never_called, circuit=circuit)
        second = verdict({}, gates=[gate], judge=_never_called, circuit=circuit)
        third = verdict({}, gates=[gate], judge=_never_called, circuit=circuit)
        assert first.kind is VerdictKind.CONTINUE
        assert second.kind is VerdictKind.CONTINUE
        assert third.kind is VerdictKind.BLOCKED
        assert third.source == "gate-exhausted"

    def test_a_replayed_pass_still_resets_the_retry_counter(self):
        circuit = verdict_module.JudgeCircuit()
        calls = []

        def check(c):
            calls.append(c)
            return True

        gate = Gate(name="g", check=check, output="", max_retries=1)
        claims = {"deliverable": "present"}
        first = verdict(claims, gates=[gate],
                         judge=lambda c: "CONTINUE ok", circuit=circuit)
        second = verdict(claims, gates=[gate],
                          judge=lambda c: "CONTINUE ok", circuit=circuit)
        assert len(calls) == 1
        assert first.source == "judge"
        assert second.source == "judge"
        assert gate.name not in circuit.gate_attempts

    def test_a_raising_check_is_never_replayed(self):
        # Exceptions carry a diagnostic that may not be safe to cache
        # verbatim across turns; the fingerprint-skip is scoped to the
        # boolean pass/fail path only.
        circuit = verdict_module.JudgeCircuit()
        calls = []

        def check(c):
            calls.append(1)
            raise RuntimeError("boom")

        gate = Gate(name="flaky", check=check, output="the deliverable is missing")
        verdict({}, gates=[gate], judge=_never_called, circuit=circuit)
        verdict({}, gates=[gate], judge=_never_called, circuit=circuit)
        assert len(calls) == 2


class TestClosedVocabulary:
    def test_parse_accepts_each_closed_term(self):
        for word, kind in [
            ("DONE", VerdictKind.DONE),
            ("BLOCKED", VerdictKind.BLOCKED),
            ("CONTINUE", VerdictKind.CONTINUE),
        ]:
            parsed = parse_verdict(word)
            assert parsed.kind is kind
        # WAIT is exercised with a target elsewhere (test_wait_directive_carried_structured);
        # a bare WAIT has no target and is a parse failure (test_bare_wait_with_no_target_is_a_parse_failure).
        assert parse_verdict("WAIT wait_on_pid=1").kind is VerdictKind.WAIT

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

    def test_bare_wait_with_no_target_is_a_parse_failure(self):
        # A02-G8: a WAIT with nothing to wait on is not a valid barrier —
        # the origin downgrades it to CONTINUE; Halbert's closed vocabulary
        # is stricter everywhere else, so a targetless WAIT raises too.
        with pytest.raises(VerdictParseError):
            parse_verdict("WAIT")

    def test_wait_rejects_unknown_directive_key(self):
        with pytest.raises(VerdictParseError):
            parse_verdict("WAIT wait_on_process=init")

    def test_wait_rejects_non_integer_pid(self):
        with pytest.raises(VerdictParseError):
            parse_verdict("WAIT wait_on_pid=systemd")

    def test_wait_rejects_non_positive_pid(self):
        # A02-G8: pid 0 and negative pids are not real targets.
        with pytest.raises(VerdictParseError):
            parse_verdict("WAIT wait_on_pid=0")
        with pytest.raises(VerdictParseError):
            parse_verdict("WAIT wait_on_pid=-4")

    def test_wait_rejects_zero_seconds(self):
        # A02-G8: a zero-second wait is not a wait.
        with pytest.raises(VerdictParseError):
            parse_verdict("WAIT wait_for_seconds=0")

    def test_wait_for_seconds_is_clamped_to_the_barrier_ceiling(self):
        # A02-G18: an unbounded wait target is a stuck loop by another name.
        parsed = parse_verdict(
            f"WAIT wait_for_seconds={verdict_module.MAX_BARRIER_WAIT_S + 500}")
        assert parsed.wait.wait_for_seconds == verdict_module.MAX_BARRIER_WAIT_S

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

    def test_a_transport_failure_resets_the_parse_counter(self):
        # A02-G9: a flaky transport interleaved with parse failures must not
        # trip the parse breaker on non-consecutive failures.
        circuit = verdict_module.JudgeCircuit()
        calls = []

        def judge(claims):
            calls.append(1)
            n = len(calls)
            if n in (1, 3, 5):
                return "not a verdict at all"  # parse failure
            if n in (2, 4):
                raise JudgeTransportError("connection reset")  # transport failure
            return "CONTINUE more work remains"

        for _ in range(5):
            result = verdict({}, gates=[], judge=judge, circuit=circuit)
            assert result.kind is not VerdictKind.BLOCKED
        assert circuit.parse_failures == 1  # reset by each intervening transport failure

    def test_judge_call_exceeding_timeout_counts_as_transport_failure(self):
        # A02-G7: a hung judge must not stall the turn — it counts as a
        # transport failure like an unreachable one.
        circuit = verdict_module.JudgeCircuit()

        def slow_judge(claims):
            time.sleep(0.3)
            return "CONTINUE more work remains"

        result = verdict({}, gates=[], judge=slow_judge, circuit=circuit, judge_timeout=0.05)
        assert result.kind is VerdictKind.CONTINUE
        assert result.source == "transport-fail-open"
        assert circuit.transport_failures == 1

    def test_judge_wired_without_an_explicit_circuit_raises(self):
        # A02-G10: a circuit created on demand and discarded cannot persist
        # breaker state across calls — the origin persists counters in
        # session state, so a caller that skips this silently loses the
        # breakers entirely. Fail loudly instead.
        with pytest.raises(TypeError):
            verdict({}, gates=[], judge=lambda c: "CONTINUE ok")

    def test_judge_input_is_bounded(self):
        # A02-G16: the origin caps judge input; today it is unbounded.
        received = []

        def judge(claims):
            received.append(claims)
            return "CONTINUE ok"

        big_claims = "x" * 100_000
        verdict(big_claims, gates=[], judge=judge, circuit=verdict_module.JudgeCircuit())
        assert len(received[0]) <= verdict_module.JUDGE_INPUT_CHARS


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