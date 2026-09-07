# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Monitor-hash gate (Hermes cron/monitor.py, packet 03 Phase A addendum).

For jobs whose purpose is "check on X": a cheap deterministic probe is
hashed each tick; unchanged -> the agent run is suppressed entirely;
changed -> a capped unified diff is injected. The hash is persisted BEFORE
the agent runs, so a failed agent run does not re-alert forever. A source
failure is an error, never a "change".

The job set is NAMED EXPLICITLY (detector_sweep-class jobs) — the gate is
never applied to the scheduler wholesale, or morning_report would be
silently suppressed."""
import json
import pathlib

import pytest

from halbert_core.scheduler.monitor_hash import (
    DEFAULT_MONITOR_HASH_JOBS,
    MonitorDecision,
    MonitorHashGate,
    capped_unified_diff,
)


@pytest.fixture
def gate(tmp_path):
    return MonitorHashGate(tmp_path / "monitor_hashes.json")


def test_job_set_is_named_explicitly():
    # Guard the founder-facing invariant: only check-on-X jobs are gated.
    assert DEFAULT_MONITOR_HASH_JOBS == frozenset({"detector_sweep"})
    assert "morning_report" not in DEFAULT_MONITOR_HASH_JOBS


def test_ungated_jobs_are_never_suppressed(tmp_path):
    gate = MonitorHashGate(tmp_path / "h.json", jobs={"detector_sweep"})
    outcome = gate.evaluate("morning_report", (True, "same output"))
    assert outcome.decision is MonitorDecision.NOT_GATED


def test_first_observation_establishes_baseline_and_suppresses(gate):
    outcome = gate.evaluate("detector_sweep", (True, "baseline output"))
    assert outcome.decision is MonitorDecision.BASELINE
    # hash persisted before the agent could run
    on_disk = json.loads(pathlib.Path(gate.store_path).read_text(encoding="utf-8"))
    assert "detector_sweep" in on_disk["hashes"]


def test_unchanged_source_suppresses(gate):
    gate.evaluate("detector_sweep", (True, "snapshot"))
    outcome = gate.evaluate("detector_sweep", (True, "snapshot"))
    assert outcome.decision is MonitorDecision.SUPPRESS


def test_changed_source_alerts_with_capped_diff(gate):
    gate.evaluate("detector_sweep", (True, "line one\nline two\n"))
    outcome = gate.evaluate("detector_sweep", (True, "line one\nline two changed\n"))
    assert outcome.decision is MonitorDecision.ALERT_DIFF
    assert outcome.diff is not None and "-line two" in outcome.diff and "+line two changed" in outcome.diff


def test_source_failure_is_error_never_change(gate):
    gate.evaluate("detector_sweep", (True, "snapshot"))
    outcome = gate.evaluate("detector_sweep", (False, ""))
    assert outcome.decision is MonitorDecision.SOURCE_ERROR
    # and a failing probe must not poison the baseline
    again = gate.evaluate("detector_sweep", (True, "snapshot"))
    assert again.decision is MonitorDecision.SUPPRESS


def test_hash_persisted_before_the_run_decision(gate):
    # A failed agent run after ALERT_DIFF must not re-alert forever: the
    # next tick with the same source is SUPPRESS, not another alert.
    gate.evaluate("detector_sweep", (True, "v1"))
    outcome = gate.evaluate("detector_sweep", (True, "v2"))
    assert outcome.decision is MonitorDecision.ALERT_DIFF
    assert gate.evaluate("detector_sweep", (True, "v2")).decision is MonitorDecision.SUPPRESS


def test_diff_cap(tmp_path):
    gate = MonitorHashGate(tmp_path / "h.json", max_diff_bytes=120)
    gate.evaluate("detector_sweep", (True, "a\n"))
    outcome = gate.evaluate("detector_sweep", (True, "\n".join(f"changed-{i}" for i in range(40)) + "\n"))
    assert outcome.decision is MonitorDecision.ALERT_DIFF
    assert len(outcome.diff.encode("utf-8")) <= 120
    assert "truncated" in outcome.diff.lower()


def test_capped_unified_diff_cap_is_respected():
    big = "\n".join(f"row {i}" for i in range(500))
    diff = capped_unified_diff(big, big.replace("row 0", "ROW 0"), max_bytes=200)
    assert len(diff.encode("utf-8")) <= 200


def test_store_survives_reopen(tmp_path):
    path = tmp_path / "h.json"
    MonitorHashGate(path).evaluate("detector_sweep", (True, "v1"))
    reopened = MonitorHashGate(path)
    assert reopened.evaluate("detector_sweep", (True, "v1")).decision is MonitorDecision.SUPPRESS