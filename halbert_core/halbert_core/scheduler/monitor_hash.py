# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Monitor-hash gate — packet 03 Phase A addendum item 4 (Hermes cron/monitor.py).

For jobs whose purpose is "check on X": a cheap deterministic script/URL
probe runs each tick and its output is hashed. Unchanged -> the agent run
is suppressed entirely; changed -> a capped unified diff is injected. The
hash is persisted BEFORE the agent runs, so a failed agent run does not
re-alert forever. A source failure is an error, never a "change".

The gated job set is NAMED EXPLICITLY (detector_sweep-class jobs) — the
gate is never applied to the scheduler wholesale, or morning_report would
be silently suppressed. Anything not in the named set comes back
``NOT_GATED`` and runs normally.

Pure policy plus a tiny hash store; the probe itself (script/URL, timeout,
redaction) belongs to the wiring layer.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional

# The explicitly named, hash-gated job set. detector_sweep is a check-on-X
# job; morning_report and timeline_retention are deliberately NOT here —
# they must never be suppressed by an unchanged source. New monitor-shaped
# jobs are added by NAME, one deliberate line at a time.
DEFAULT_MONITOR_HASH_JOBS = frozenset({"detector_sweep"})

DEFAULT_HASH = hashlib.sha256


class MonitorDecision(Enum):
    NOT_GATED = "not_gated"  # job not in the named set: run normally
    BASELINE = "baseline"  # first observation: establish the baseline, suppress
    SUPPRESS = "suppress"  # source unchanged: the agent run is suppressed entirely
    ALERT_DIFF = "alert_diff"  # source changed: inject the capped diff
    SOURCE_ERROR = "source_error"  # probe failed: an error, never a "change"


@dataclass(frozen=True)
class MonitorOutcome:
    decision: MonitorDecision
    job_id: str
    diff: Optional[str] = None  # ALERT_DIFF only, capped
    source_hash: Optional[str] = None
    previous_hash: Optional[str] = None


def capped_unified_diff(old_text: str, new_text: str, max_bytes: int) -> str:
    """Unified diff of two probe outputs, capped (the cap is an OOM/scroll
    defense, not a courtesy). A truncation marker is appended when cut."""
    diff = "".join(
        difflib.unified_diff(
            old_text.splitlines(keepends=True),
            new_text.splitlines(keepends=True),
            fromfile="previous",
            tofile="current",
        )
    )
    encoded = diff.encode("utf-8")
    if len(encoded) <= max_bytes:
        return diff
    marker = "\n... [diff truncated]"
    # Reserve the marker's own bytes so the cap is respected, marker included.
    budget = max(0, max_bytes - len(marker.encode("utf-8")))
    truncated = encoded[:budget].decode("utf-8", errors="ignore")
    return truncated + marker


class MonitorHashGate:
    """Suppress/diff policy for named check-on-X jobs.

    ``evaluate(job_id, probe_result)`` is the whole policy. ``probe_result``
    is ``(ok, output_text)`` from the cheap deterministic probe. The new
    hash is persisted BEFORE the decision is returned — i.e. before the
    caller can run the agent — so a failed agent run cannot re-alert
    forever. A probe failure mutates nothing.
    """

    def __init__(
        self,
        store_path,
        *,
        jobs: frozenset = DEFAULT_MONITOR_HASH_JOBS,
        max_diff_bytes: int = 4096,
        max_stored_bytes: int = 65536,
        hash_fn: Callable[[bytes], "hashlib._Hash"] = None,
    ):
        self.store_path = os.fspath(store_path)
        self.jobs = frozenset(jobs)
        self.max_diff_bytes = max_diff_bytes
        self.max_stored_bytes = max_stored_bytes
        self.hash_fn = hash_fn or DEFAULT_HASH
        self._hashes: dict = {}
        self._outputs: dict = {}
        self._load()

    # -- named-set guard ---------------------------------------------------

    def is_gated(self, job_id: str) -> bool:
        return job_id in self.jobs

    # -- store ---------------------------------------------------------------

    def _load(self) -> None:
        if not os.path.exists(self.store_path):
            return
        with open(self.store_path, "r", encoding="utf-8") as f:
            raw = json.load(f)  # malformed file raises: validate-and-reject
        hashes = raw.get("hashes", {})
        if isinstance(hashes, dict):
            self._hashes = {k: v for k, v in hashes.items() if isinstance(v, str)}
        outputs = raw.get("outputs", {})
        if isinstance(outputs, dict):
            self._outputs = {
                k: v for k, v in outputs.items() if isinstance(v, str)
            }

    def _flush(self) -> None:
        """Atomic write (tmp + fsync + rename): the hash must survive the
        crash it exists to protect against."""
        directory = os.path.dirname(self.store_path) or "."
        os.makedirs(directory, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            dir=directory,
            prefix=os.path.basename(self.store_path) + ".",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(
                    {"hashes": self._hashes, "outputs": self._outputs},
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, self.store_path)
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
        dir_fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)

    # -- policy ---------------------------------------------------------------

    def evaluate(self, job_id: str, probe_result) -> MonitorOutcome:
        ok, output_text = probe_result
        if not self.is_gated(job_id):
            # NOT gated -> never suppressed. This is the branch
            # morning_report always takes.
            return MonitorOutcome(MonitorDecision.NOT_GATED, job_id)
        if not ok:
            # Source failure is an error, never a "change": persist nothing.
            return MonitorOutcome(MonitorDecision.SOURCE_ERROR, job_id)

        digest = self.hash_fn(output_text.encode("utf-8")).hexdigest()
        previous_hash = self._hashes.get(job_id)
        previous_output = self._outputs.get(job_id)

        # Persist BEFORE returning the decision, so the agent run that the
        # caller performs on ALERT_DIFF cannot re-alert on the next tick if
        # it fails.
        self._hashes[job_id] = digest
        self._outputs[job_id] = output_text[: self.max_stored_bytes]
        self._flush()

        if previous_hash is None:
            return MonitorOutcome(
                MonitorDecision.BASELINE, job_id, source_hash=digest
            )
        if previous_hash == digest:
            return MonitorOutcome(
                MonitorDecision.SUPPRESS, job_id, source_hash=digest,
                previous_hash=previous_hash,
            )
        diff = capped_unified_diff(previous_output or "", output_text, self.max_diff_bytes)
        return MonitorOutcome(
            MonitorDecision.ALERT_DIFF,
            job_id,
            diff=diff,
            source_hash=digest,
            previous_hash=previous_hash,
        )