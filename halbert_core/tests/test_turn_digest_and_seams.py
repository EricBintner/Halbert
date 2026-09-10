# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""R-06 Phases B and D: the digest is bounded, honest, and scrubbed.

- **A05 bug 7** -- the spoken tail and the audit rollup were built from
  the digest and spoken/written directly, bypassing both the echo guard
  and the registry. The digest redacts its TARGETS by shape, which is not
  the same as passing the finished line through the egress seam every
  other user-visible string goes through.
- **A05-G8** -- the digest was unbounded: a turn that wrote forty files
  spoke forty lines. Twelve plus "and N more".
- **A05-G9 + bug 6** -- only SUCCESSES were recorded, and ``run_command``
  returning a non-zero exit code counts as a success at the executor's
  seam. So "I restarted sshd" was spoken for a command that failed. The
  digest records started / failed / cancelled, and a non-zero exit is a
  failure.
- **A05-G10** -- a binary payload became its own length in characters of
  noise; it becomes a size fact.
"""

import pytest

from halbert_core.security.turn_digest import (
    MAX_DIGEST_LINES,
    TurnDigest,
    spoken_tail,
)


def test_a_successful_effect_reads_as_done():
    digest = TurnDigest()
    digest.record("write_file", target="/etc/hosts")
    assert "write_file" in digest.summary()


def test_a_failed_effect_says_so():
    """A05-G9: 'I restarted sshd' for a command that failed."""
    digest = TurnDigest()
    digest.record("run_command", target="systemctl restart sshd", status="failed")
    summary = digest.summary()
    assert "failed" in summary.lower()


def test_a_cancelled_effect_says_so():
    digest = TurnDigest()
    digest.record("run_command", target="rsync -a /a /b", status="cancelled")
    assert "cancelled" in digest.summary().lower()


def test_the_count_line_separates_the_statuses():
    digest = TurnDigest()
    digest.record("write_file", target="/a")
    digest.record("write_file", target="/b", status="failed")
    head = digest.summary().splitlines()[0]
    assert "1" in head
    assert "failed" in head.lower()


def test_a_non_zero_exit_is_not_a_success():
    """A05 bug 6: the executor's ExecutionResult.success is True for a
    command that ran and returned 1."""
    from halbert_core.security.turn_digest import status_for_result

    assert status_for_result(True, "Exit code 1\nno such unit") == "failed"
    assert status_for_result(True, "all good") == "done"
    assert status_for_result(False, None) == "failed"


def test_exit_code_zero_is_a_success():
    from halbert_core.security.turn_digest import status_for_result

    assert status_for_result(True, "Exit code 0\nfine") == "done"


# ---------------------------------------------------------------------------
# A05-G8: the digest is bounded
# ---------------------------------------------------------------------------

def test_a_long_digest_is_capped_and_says_how_many_more():
    digest = TurnDigest()
    for i in range(40):
        digest.record("write_file", target=f"/tmp/file-{i:03d}")
    lines = digest.summary().splitlines()
    assert len(lines) <= MAX_DIGEST_LINES + 2
    assert "and 28 more" in digest.summary()


def test_a_short_digest_is_not_capped():
    digest = TurnDigest()
    digest.record("write_file", target="/a")
    assert "more" not in digest.summary()


def test_the_cap_still_counts_everything():
    digest = TurnDigest()
    for i in range(40):
        digest.record("write_file", target=f"/tmp/{i}")
    assert digest.summary().splitlines()[0].startswith("40 effects")


# ---------------------------------------------------------------------------
# A05-G10: a binary target is a size fact
# ---------------------------------------------------------------------------

def test_a_binary_target_becomes_a_size_fact():
    digest = TurnDigest()
    digest.record("write_file", target=b"\x00\x01\x02" * 5000)
    summary = digest.summary()
    assert "\x00" not in summary
    assert "bytes" in summary


# ---------------------------------------------------------------------------
# A05 bug 7: the tail goes through the egress seam
# ---------------------------------------------------------------------------

def test_the_spoken_tail_goes_through_the_scrub_seam():
    from halbert_core.ingestion.redaction_registry import get_global_registry

    get_global_registry().register("tail-secret-value-99")
    digest = TurnDigest()
    digest.record("write_file", target="tail-secret-value-99")
    tail = spoken_tail(digest, "voice")
    assert tail is not None
    assert "tail-secret-value-99" not in tail


def test_a_typed_turn_has_no_spoken_tail():
    digest = TurnDigest()
    digest.record("write_file", target="/a")
    assert spoken_tail(digest, "text") is None


def test_an_empty_digest_has_no_tail():
    assert spoken_tail(TurnDigest(), "voice") is None


def test_the_audit_rollup_line_is_the_scrubbed_one():
    """The same string is spoken and written; scrubbing one and not the
    other would put the raw value in the log instead of the room."""
    from halbert_core.security.turn_digest import audit_rollup

    from halbert_core.ingestion.redaction_registry import get_global_registry

    get_global_registry().register("rollup-secret-value-7")
    digest = TurnDigest()
    digest.record("run_command", target="echo rollup-secret-value-7")
    assert "rollup-secret-value-7" not in (audit_rollup(digest) or "")
