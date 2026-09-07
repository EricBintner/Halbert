# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Run receipts — packet 03 A3 + Hermes addendum items 2 and 3.

A receipt is a *pre-execution marker*, not an outcome ledger: the
file-backed outcome writer was deliberately removed once (audit F1) and
must not come back through the side door. ``mark_started`` writes and
fsyncs BEFORE returning, so the marker outlives any crash that happens
after the side effects begin.

On boot, ``recover_on_boot`` marks every still-``running`` receipt whose
owner pid is dead as ``interrupted`` — the simplified single-instance rule
(directly NOT OpenClaw's multi-instance invariant matrix).

Occurrence-level idempotency (Hermes ``cron/occurrences.py``): a completed
scheduled instant is recorded and can never fire again, even if
``next_run_at`` was left stale by a crash. This is stronger than any claim
TTL and is the real at-most-once primitive.

Terminal statuses are the closed Hermes set ``ok / error /
delivery_failed / blocked_config`` — run success is not user delivery, and
``blocked_config`` (refused in preflight, before any LLM spend) is distinct
from ``error``. Consumers must ask ``delivered_to_user(status)``, never
test ``status == "ok"``, for "the user got it".

Storage is one JSON file (``receipts.json``) in the scheduler data dir,
matching SchedulerEngine's per-job-file convention, written atomically
(temp + rename + fsync). Loaded records are validated and a malformed file
is rejected loudly (Hermes anti-pattern: silent repair passes breed
hand-edited stores). Deliberately not SQLite — see the packet's A3 and the
SchedulerEngine convention; the file is small and append-mostly.
"""
from __future__ import annotations

import json
import os
import tempfile
import time
from typing import Callable, Dict, List, Optional, Union

# Terminal statuses (Hermes jobs.py closed set). "running" and "interrupted"
# are lifecycle states, not outcomes.
CLOSED_STATUSES = frozenset({"ok", "error", "delivery_failed", "blocked_config"})

_RUNNING = "running"
_INTERRUPTED = "interrupted"

ReceiptInstant = Union[float, int, str]


def delivered_to_user(status: str) -> bool:
    """Did the user actually receive the result? (run success != delivery)."""
    return status == "ok"


def _default_pid_alive(pid: int) -> bool:
    """POSIX liveness probe: signal 0 checks existence without delivery."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # The pid exists but belongs to someone we cannot signal: alive.
        return True


def _occurrence_key(job_id: str, scheduled_instant) -> str:
    return f"{job_id}@{scheduled_instant}"


class RunReceiptStore:
    def __init__(self, path):
        self.path = os.fspath(path)
        self._receipts: Dict[str, dict] = {}
        self._occurrences: Dict[str, dict] = {}
        self._load()

    # -- loading ---------------------------------------------------------

    def _load(self) -> None:
        if not os.path.exists(self.path):
            return
        with open(self.path, "r", encoding="utf-8") as f:
            raw = json.load(f)  # malformed file raises: validate-and-reject
        self._receipts = {
            rid: rec
            for rid, rec in raw.get("receipts", {}).items()
            if isinstance(rec, dict)
            and rec.get("id") == rid
            and rec.get("status") in (_RUNNING, _INTERRUPTED, *CLOSED_STATUSES)
        }
        self._occurrences = {
            key: rec
            for key, rec in raw.get("occurrences", {}).items()
            if isinstance(rec, dict)
        }

    # -- persistence -----------------------------------------------------

    def _flush(self) -> None:
        """Atomic write: tmp file + fsync + rename, so a crash mid-write
        leaves either the old or the new full state, never a torn file."""
        directory = os.path.dirname(self.path) or "."
        os.makedirs(directory, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            dir=directory, prefix=os.path.basename(self.path) + ".", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(
                    {"receipts": self._receipts, "occurrences": self._occurrences},
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, self.path)
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
        # fsync the directory so the rename itself is durable
        dir_fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)

    # -- receipts --------------------------------------------------------

    def mark_started(
        self,
        job_id: str,
        owner_pid: int,
        scheduled_instant: ReceiptInstant = None,
    ) -> str:
        """Persist a running receipt BEFORE any side effect. Writes and
        fsyncs before returning; the caller runs its task only after this."""
        rid = f"{job_id}:{os.urandom(8).hex()}"
        self._receipts[rid] = {
            "id": rid,
            "job_id": job_id,
            "owner_pid": int(owner_pid),
            "scheduled_instant": scheduled_instant,
            "status": _RUNNING,
            "started_at_epoch": time.time(),
        }
        self._flush()
        return rid

    def mark_finished(self, rid: str, status: str, error: Optional[str] = None) -> None:
        """Terminal outcome from the CLOSED status set; records the receipt's
        scheduled instant (if any) as a completed occurrence."""
        if status not in CLOSED_STATUSES:
            raise ValueError(
                f"status {status!r} is not in the closed set {sorted(CLOSED_STATUSES)}"
            )
        receipt = self._receipts[rid]  # KeyError on an unknown rid: loud, not silent
        receipt["status"] = status
        if error is not None:
            receipt["error"] = error
        receipt["finished_at_epoch"] = time.time()
        scheduled = receipt.get("scheduled_instant")
        if scheduled is not None:
            self.completed_occurrence(receipt["job_id"], scheduled)
        self._flush()

    def status(self, rid: str) -> str:
        return self._receipts[rid]["status"]

    def receipt(self, rid: str) -> dict:
        return dict(self._receipts[rid])

    def recover_on_boot(self, owner_alive: Callable[[int], bool] = None) -> List[str]:
        """Mark running receipts with dead owners as ``interrupted``.

        An interrupted run proves nothing about its side effects — no
        occurrence is recorded for it; the re-run decision (and its budget)
        belongs to the wiring layer.
        """
        alive = owner_alive or _default_pid_alive
        recovered: List[str] = []
        for rid, receipt in sorted(self._receipts.items()):
            if receipt.get("status") != _RUNNING:
                continue
            if not alive(int(receipt.get("owner_pid", -1))):
                receipt["status"] = _INTERRUPTED
                receipt["recovered_at_epoch"] = time.time()
                recovered.append(rid)
        if recovered:
            self._flush()
        return recovered

    # -- occurrence idempotency -------------------------------------------

    def completed_occurrence(self, job_id: str, scheduled_instant) -> None:
        """Record a scheduled instant as consumed. Idempotent: repeating the
        call for the same (job_id, instant) is a no-op."""
        key = _occurrence_key(job_id, scheduled_instant)
        if key not in self._occurrences:
            self._occurrences[key] = {
                "job_id": job_id,
                "scheduled_instant": scheduled_instant,
                "completed_at_epoch": time.time(),
            }
            self._flush()

    def occurrence_completed(self, job_id: str, scheduled_instant) -> bool:
        """Has this scheduled instant already run to a terminal outcome?"""
        return _occurrence_key(job_id, scheduled_instant) in self._occurrences