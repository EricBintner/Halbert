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
    assert all(p["bank_digest"] for p in parsed)