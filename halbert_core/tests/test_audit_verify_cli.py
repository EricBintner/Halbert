# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""``halbert audit-verify`` -- and the words it is allowed to use.

§3.5 of the integrity handoff makes copy a correctness requirement, not a
polish item: on a single machine the signing key and the log it signs share
a disk, so anyone who can rewrite the log can re-sign it.  "Verified" would
assert something this system cannot back.  What it *can* back is narrower
and is what the report says: no tampering detected since the last point of
comparison.  Several tests below exist only to keep that wording honest.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from halbert_core.obs.audit import (
    render_verify_report,
    set_audit_signer,
    verify_audit,
    write_audit,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _isolated_audit_log(tmp_path, monkeypatch):
    monkeypatch.setenv("HALBERT_LOG_DIR", str(tmp_path / "logs"))
    set_audit_signer(None)
    yield
    set_audit_signer(None)


def _write(n=3):
    for i in range(n):
        write_audit(tool="write_config", mode="apply", request_id=f"r{i}", ok=True)


# ---------------------------------------------------------------------------
# The report's claims.
# ---------------------------------------------------------------------------


def test_a_clean_report_claims_no_tampering_detected_not_verification():
    _write()

    report = render_verify_report(verify_audit())

    assert "no tampering detected" in report.lower()


def test_a_clean_report_never_calls_the_log_verified():
    """The badge §3.5 forbids, in its command-line form."""
    _write()

    report = render_verify_report(verify_audit()).lower()

    for forbidden in ("log verified", "memory verified", "integrity verified"):
        assert forbidden not in report


def test_a_clean_report_says_what_it_cannot_vouch_for():
    """A reader must not walk away thinking this proves more than it does."""
    _write()

    report = render_verify_report(verify_audit()).lower()

    assert "same machine" in report or "this machine" in report


def test_the_report_does_not_claim_a_comparison_nobody_performed():
    """The peer wording asserted the log had been "checked against the head
    last agreed with <peer>". No code performs that comparison, and claiming
    a stronger guarantee than the mechanism provides is what INTEG-05
    forbids. It returns when peer root co-signing does."""
    _write()

    report = render_verify_report(verify_audit())

    assert "last agreed with" not in report
    assert "since this log began" in report
    assert "none is performed today" in report


def test_an_unsigned_report_says_so_rather_than_staying_quiet():
    _write()

    report = render_verify_report(verify_audit()).lower()

    assert "unsigned" in report


def test_a_failed_report_renders_every_problem():
    _write()
    shard = sorted((Path(os.environ["HALBERT_LOG_DIR"]) / "audit").glob("*.jsonl"))[0]
    lines = shard.read_text().splitlines()
    shard.write_text("\n".join(lines[:-1]) + "\n")

    result = verify_audit()
    report = render_verify_report(result)

    assert "no tampering detected" not in report.lower()
    for problem in result.problems:
        assert str(problem) in report


def test_an_empty_log_is_reported_as_empty_not_as_clean():
    """Nothing to find is not the same as having looked and found nothing."""
    report = render_verify_report(verify_audit()).lower()

    assert "no records" in report or "empty" in report


# ---------------------------------------------------------------------------
# The command.
# ---------------------------------------------------------------------------


def _run_cli(*args, env_extra=None):
    env = os.environ.copy()
    env.update(env_extra or {})
    return subprocess.run(
        [sys.executable, "Halbert/main.py", "audit-verify", *args],
        capture_output=True, text=True, cwd=REPO_ROOT, env=env,
    )


def test_the_command_exits_zero_on_a_clean_log():
    _write()

    result = _run_cli()

    assert result.returncode == 0, result.stderr
    assert "no tampering detected" in result.stdout.lower()


def test_the_command_exits_nonzero_on_a_tampered_log():
    """An audit check that cannot fail the build is not a check."""
    _write()
    shard = sorted((Path(os.environ["HALBERT_LOG_DIR"]) / "audit").glob("*.jsonl"))[0]
    shard.write_text(shard.read_text().replace('"ok": true', '"ok": false'))

    result = _run_cli()

    assert result.returncode == 1
    assert "commitment_mismatch" in result.stdout


def test_the_command_exits_nonzero_when_a_shard_is_deleted():
    _write()
    for shard in (Path(os.environ["HALBERT_LOG_DIR"]) / "audit").glob("*.jsonl"):
        shard.unlink()

    result = _run_cli()

    assert result.returncode == 1
    assert "truncated" in result.stdout


def test_the_command_emits_machine_readable_json_on_request():
    _write()

    result = _run_cli("--json")

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["checked"] == 3
    assert payload["signed"] == 0
    assert payload["problems"] == []


def test_the_json_output_carries_the_problems_too():
    _write()
    shard = sorted((Path(os.environ["HALBERT_LOG_DIR"]) / "audit").glob("*.jsonl"))[0]
    lines = shard.read_text().splitlines()
    shard.write_text("\n".join(lines[:-1]) + "\n")

    result = _run_cli("--json")

    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["problems"][0]["kind"] == "truncated"
    assert payload["problems"][0]["detail"]


def test_the_command_accepts_an_explicit_directory(tmp_path):
    _write()
    directory = Path(os.environ["HALBERT_LOG_DIR"]) / "audit"

    result = _run_cli("--dir", str(directory), env_extra={"HALBERT_LOG_DIR": str(tmp_path / "elsewhere")})

    assert result.returncode == 0
    assert "3" in result.stdout


def test_a_failed_report_does_not_also_claim_the_chain_is_consistent():
    """The unsigned caveat must not contradict the failure above it."""
    _write()
    shard = sorted((Path(os.environ["HALBERT_LOG_DIR"]) / "audit").glob("*.jsonl"))[0]
    lines = shard.read_text().splitlines()
    shard.write_text("\n".join(lines[:-1]) + "\n")

    report = render_verify_report(verify_audit())

    assert "internally consistent" not in report
    assert "unsigned" in report.lower()


def test_the_command_exits_two_when_the_integrity_layer_is_missing(tmp_path):
    """Exit 2, not 1: "cannot check" is a different answer from "tampered"."""
    shim = tmp_path / "shim"
    (shim / "haloysius").mkdir(parents=True)
    (shim / "haloysius" / "__init__.py").write_text('raise ImportError("blocked")')
    _write()

    result = _run_cli(env_extra={"PYTHONPATH": str(shim)})

    assert result.returncode == 2, (result.stdout, result.stderr)
    assert "haloysius" in result.stdout


def test_a_mistyped_directory_exits_two_not_zero(tmp_path):
    """`--dir /typo` printing "no tampering detected" would be a lie."""
    _write()

    result = _run_cli("--dir", str(tmp_path / "typo"))

    assert result.returncode == 2, (result.stdout, result.stderr)
    assert "no tampering detected" not in result.stdout.lower()
    assert not (tmp_path / "typo").exists()
