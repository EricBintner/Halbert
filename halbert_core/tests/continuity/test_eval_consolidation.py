# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Arms: (1) NO_CONSOLIDATION — the ceiling; (2) current deterministic
Consolidator; (3) TRUNCATE_OLDEST — a cheap baseline any LLM arm must beat.
Scores are recall@retained, never recall alone. Region scoping is pinned by a
sentinel test (Hermes test_region_scoping.py)."""

import pytest

from halbert_core.continuity import corpus
from halbert_core.continuity import eval_consolidation


def _matrix(tmp_path, **kw):
    return eval_consolidation.run_matrix(cache_dir=tmp_path / "cache", **kw)


def test_arms_answer_identical_exam(tmp_path):
    report = _matrix(tmp_path, seeds=(7, 8), turns=40)
    rows = [r for r in report.rows if r.status == "OK"]
    assert rows
    # every arm that ran answered the same bank per thread: one digest per thread
    by_thread = {}
    for r in rows:
        by_thread.setdefault(r.thread_id, set()).add(r.bank_digest)
    assert all(len(digests) == 1 for digests in by_thread.values())
    # and the bank was generated exactly once per thread: one cache file each
    digests = {r.bank_digest for r in rows}
    cache_files = {p.name for p in (tmp_path / "cache").iterdir()}
    assert cache_files == {f"questions-{d[:10]}.json" for d in digests}


def test_ceiling_arm_defined(tmp_path):
    report = _matrix(tmp_path, seeds=(7,), turns=40)
    aggregates = report.aggregates()
    assert aggregates[0].arm == "NO_CONSOLIDATION"
    assert aggregates[0].ceiling is True
    rendered = report.render()
    # the ceiling is printed first in the report
    assert rendered.index("NO_CONSOLIDATION") < rendered.index("TRUNCATE_OLDEST")
    assert rendered.index("NO_CONSOLIDATION") < rendered.index("CONSOLIDATOR_DETERMINISTIC")


def test_region_scoping_sentinel(tmp_path):
    """Plant sentinels head/middle/tail; a policy must receive ONLY the
    expected region — never the whole thread (Hermes test_region_scoping)."""
    thread = corpus.synthetic_thread(seed=7, turns=30)
    thread.messages[0].content += " SENTINEL-HEAD"
    thread.messages[15].content += " SENTINEL-MIDDLE"
    thread.messages[29].content += " SENTINEL-TAIL"

    seen = []

    def spy(thread_, region):
        seen.append(list(region))
        return eval_consolidation.Retained(text="nothing")

    arm = eval_consolidation.Arm(name="SPY", policy=spy)
    _matrix(tmp_path, threads=[thread], arms=[arm], region=(0, 10))

    assert len(seen) == 1
    assert len(seen[0]) == 10
    contents = " | ".join(m.content for m in seen[0])
    assert "SENTINEL-HEAD" in contents
    assert "SENTINEL-MIDDLE" not in contents
    assert "SENTINEL-TAIL" not in contents


def test_truncated_summary_is_a_failure_not_a_result(tmp_path):
    """A summarizer that returns finish_reason=length-style truncation is a
    retryable failure, never stored (Hermes _finish_summary rule)."""
    thread = corpus.synthetic_thread(seed=7, turns=40)

    def truncated_summarizer(text):
        return {"text": text[:20], "finish_reason": "length"}

    arm = eval_consolidation.Arm(
        name="LLM_SUMMARY",
        policy=eval_consolidation.llm_summary_policy(truncated_summarizer),
    )
    report = _matrix(tmp_path, threads=[thread], arms=[arm], region=(0, 20))
    rows = [r for r in report.rows if r.arm == "LLM_SUMMARY"]
    assert rows and all(r.status == "FAILED-RETRYABLE" for r in rows)
    assert all(r.retryable for r in rows)
    # nothing was stored: no retained text, no scores
    assert all(r.retained_tokens is None for r in rows)
    assert all(r.recall is None for r in rows)

    # and a clean stop result IS a result
    clean = eval_consolidation.Arm(
        name="LLM_SUMMARY",
        policy=eval_consolidation.llm_summary_policy(
            lambda text: {"text": "summary", "finish_reason": "stop"}),
    )
    report2 = _matrix(tmp_path, threads=[thread], arms=[clean], region=(0, 20))
    assert all(r.status == "OK" for r in report2.rows)


def test_llm_arm_is_skipped_gate_closed(tmp_path):
    """The LLM arm is present in the matrix definition but the R5 gate is
    closed: it is printed SKIPPED-GATE-CLOSED, and nothing model-shaped runs."""
    report = _matrix(tmp_path, seeds=(7, 8, 9), turns=40)
    llm_rows = [r for r in report.rows if r.arm == "LLM_SUMMARY"]
    assert llm_rows and all(r.status == "SKIPPED-GATE-CLOSED" for r in llm_rows)
    assert {a.arm: a for a in report.aggregates()}["LLM_SUMMARY"].status == \
        "SKIPPED-GATE-CLOSED"
    rendered = report.render()
    assert "SKIPPED-GATE-CLOSED" in rendered


def test_deterministic_arms_recall_at_retained(tmp_path):
    """Pin the synthetic-corpus story: ceiling answers everything; the
    deterministic Consolidator retains durable structure, not episodic facts;
    TRUNCATE_OLDEST keeps only the newest planted fact. Scores are always
    reported alongside retained tokens — recall alone is not a score."""
    report = _matrix(tmp_path, seeds=tuple(range(1, 10)), turns=40, region=(0, 20))
    agg = {a.arm: a for a in report.aggregates()}
    assert agg["NO_CONSOLIDATION"].recall == 1.0
    assert agg["CONSOLIDATOR_DETERMINISTIC"].recall == 0.0
    assert agg["TRUNCATE_OLDEST"].recall == pytest.approx(0.5)
    assert (agg["NO_CONSOLIDATION"].mean_retained_tokens
            > agg["TRUNCATE_OLDEST"].mean_retained_tokens
            > agg["CONSOLIDATOR_DETERMINISTIC"].mean_retained_tokens)


def test_report_jsonl_round_trips_every_row(tmp_path):
    import json

    report = _matrix(tmp_path, seeds=(7,), turns=40)
    parsed = [json.loads(line) for line in report.jsonl().splitlines()]
    assert len(parsed) == len(report.rows)
    assert {p["arm"] for p in parsed} == {r.arm for r in report.rows}


def test_a_region_with_no_planted_fact_renders_instead_of_crashing(tmp_path):
    # own-bug: a region containing no planted fact (facts sit at turns
    # 0/10/20/30) scores zero questions; recall stays None but the arm
    # otherwise ran cleanly, so it must not be reported as OK-with-None.
    report = _matrix(tmp_path, seeds=(7,), turns=40, region=(1, 9))
    agg = {a.arm: a for a in report.aggregates()}
    assert agg["NO_CONSOLIDATION"].status == "NO-QUESTIONS"
    assert agg["NO_CONSOLIDATION"].recall is None
    rendered = report.render()  # must not raise
    assert "NO-QUESTIONS" in rendered


def test_a_policy_that_raises_an_unexpected_exception_yields_a_failed_row(tmp_path):
    # own-bug: _run_arm caught only PolicyFailed; any other exception
    # aborted the whole matrix and discarded rows already computed.
    def bad_policy(thread, region):
        raise RuntimeError("boom")

    arm = eval_consolidation.Arm(name="BAD", policy=bad_policy)
    ceiling = eval_consolidation.Arm(
        name="NO_CONSOLIDATION", policy=eval_consolidation.verbatim_policy())
    report = _matrix(tmp_path, seeds=(7,), turns=40, arms=[ceiling, arm])
    assert any(r.status == "OK" for r in report.rows if r.arm == "NO_CONSOLIDATION")
    bad_rows = [r for r in report.rows if r.arm == "BAD"]
    assert bad_rows and all(r.status == "FAILED" for r in bad_rows)
    assert all(not r.retryable for r in bad_rows)
    assert "RuntimeError" in bad_rows[0].failure


def test_mixed_length_threads_refuse_an_ambiguous_default_region(tmp_path):
    # own-bug: the default region and reported turn count were derived from
    # threads[0] only; a caller passing mixed-length threads silently got a
    # region sized for the first thread and a scorecard header that lies
    # about the second.
    short_thread = corpus.synthetic_thread(seed=7, turns=40)
    long_thread = corpus.synthetic_thread(seed=8, turns=60)
    with pytest.raises(ValueError, match="turn counts"):
        _matrix(tmp_path, threads=[short_thread, long_thread])


def test_verdicts_are_attached_to_committed_rows(tmp_path):
    # A02-G11: per-question verdicts were computed then discarded — the
    # committed rows could not show which planted fact an arm lost.
    report = _matrix(tmp_path, seeds=(7,), turns=40, region=(0, 20))
    ok_rows = [r for r in report.rows if r.status == "OK"]
    assert ok_rows
    for row in ok_rows:
        assert row.verdicts
        assert len(row.verdicts) == row.n_questions
        for v in row.verdicts:
            assert set(v) == {"question", "gold", "answer", "score"}
    # and they round-trip through jsonl with the rest of the row
    parsed_line = report.jsonl().splitlines()[report.rows.index(ok_rows[0])]
    import json
    assert json.loads(parsed_line)["verdicts"] == ok_rows[0].verdicts


def test_region_messages_are_not_shared_mutable_state_across_arms(tmp_path):
    # A02-G12: a policy that mutates its region argument must not corrupt a
    # later arm's retained context for the same thread.
    def mutating_policy(thread, region):
        region[0].content = "MUTATED"
        return eval_consolidation.Retained(text=eval_consolidation._region_text(region))

    mutator = eval_consolidation.Arm(name="MUTATOR", policy=mutating_policy)
    verbatim = eval_consolidation.Arm(
        name="NO_CONSOLIDATION", policy=eval_consolidation.verbatim_policy())
    # mutator runs first; verbatim must still see the untouched region
    report = _matrix(tmp_path, seeds=(7,), turns=40, region=(0, 20),
                     arms=[mutator, verbatim])
    verbatim_row = next(r for r in report.rows if r.arm == "NO_CONSOLIDATION")
    assert verbatim_row.recall == 1.0


def test_region_tokens_and_kept_fraction_are_reported(tmp_path):
    # A02-G13: retained-fraction ("kept %") is not derivable from committed
    # evidence without the region's own token count alongside it.
    report = _matrix(tmp_path, seeds=(7,), turns=40, region=(0, 20))
    ok_rows = [r for r in report.rows if r.status == "OK"]
    assert ok_rows and all(r.region_tokens for r in ok_rows)
    agg = {a.arm: a for a in report.aggregates()}["NO_CONSOLIDATION"]
    assert agg.mean_region_tokens == pytest.approx(
        sum(r.region_tokens for r in ok_rows if r.arm == "NO_CONSOLIDATION")
        / len([r for r in ok_rows if r.arm == "NO_CONSOLIDATION"]))
    rendered = report.render()
    assert "kept" in rendered.lower()


def test_truncated_summary_retries_before_giving_up(tmp_path):
    # A02-G14: the origin retries a truncated summary before giving up; one
    # attempt was the whole budget.
    thread = corpus.synthetic_thread(seed=7, turns=40)
    calls = []

    def flaky_once(text):
        calls.append(1)
        if len(calls) == 1:
            return {"text": text[:20], "finish_reason": "length"}
        return {"text": "summary", "finish_reason": "stop"}

    arm = eval_consolidation.Arm(
        name="LLM_SUMMARY", policy=eval_consolidation.llm_summary_policy(flaky_once))
    report = _matrix(tmp_path, threads=[thread], arms=[arm], region=(0, 20))
    rows = [r for r in report.rows if r.arm == "LLM_SUMMARY"]
    assert rows and all(r.status == "OK" for r in rows)
    assert all(r.attempts == 2 for r in rows)
    assert len(calls) == 2  # one thread: truncated once, then succeeded

    calls_always = []

    def always_truncated(text):
        calls_always.append(1)
        return {"text": text[:20], "finish_reason": "length"}

    arm2 = eval_consolidation.Arm(
        name="LLM_SUMMARY", policy=eval_consolidation.llm_summary_policy(always_truncated))
    report2 = _matrix(tmp_path, threads=[thread], arms=[arm2], region=(0, 20))
    rows2 = [r for r in report2.rows if r.arm == "LLM_SUMMARY"]
    assert rows2 and all(r.status == "FAILED-RETRYABLE" for r in rows2)
    assert all(r.attempts == 2 for r in rows2)  # default budget, then gave up


def test_region_scoping_sentinel_proves_head_and_tail_survive_verbatim(tmp_path):
    # A02-G17: the existing sentinel only proved the arm received the
    # expected slice; it never proved the thread's own messages outside the
    # region come through run_matrix unmodified.
    thread = corpus.synthetic_thread(seed=7, turns=30)
    thread.messages[0].content += " SENTINEL-HEAD"
    thread.messages[29].content += " SENTINEL-TAIL"
    before_head = thread.messages[0].content
    before_tail = thread.messages[29].content

    arm = eval_consolidation.Arm(
        name="SPY", policy=lambda t, r: eval_consolidation.Retained(text="nothing"))
    _matrix(tmp_path, threads=[thread], arms=[arm], region=(0, 10))

    assert thread.messages[0].content == before_head
    assert thread.messages[29].content == before_tail