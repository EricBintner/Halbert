# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The halt state — axis 5 of five: is anything halted or expired?

PERMISSION-AND-CONSENT-SYSTEM-2026-09-06.md §4.1 ("Stop everything") and the
axis table of §1.2:

    Runtime — is anything halted or expired?  Unknown → DENY.

"Stop is also what failure does": the halt is not only the owner's action
but the machine's own response to a broken trust precondition — a consent
ledger it cannot read or verify, a missing integrity primitive, an audit log
it cannot write, a redaction-required capability with no working backend, or
repeated guardrail trips. Each has its own reason code, and the machine
names which one it stopped for.

This module is the **in-process state only**: the flag, the reason, and the
provenance of both directions. The persisted ``<data_dir>/runtime/halt.json``
(``0600``, atomic, ``flock``-guarded), the Phase-0 boot read, the six doors,
and the deliberately asymmetric resume (an authenticated owner, on a
first-party surface, with OS re-auth, shown what will restart) are the D3-P6
live controls. The pure state simply clears — the *authority* for a resume
lives in the wiring, never here.

Halt wins over everything: the evaluator checks this axis first, and a
halted state denies every capability regardless of the other four axes.
"""
from __future__ import annotations

import threading
from typing import Optional


class HaltReason:
    """Reason codes for entering the halted state.

    The design's §4.1 failure list, plus the owner's own stop. ``consent_chain_broken``
    is the projection-vs-log disagreement that §1.5 makes a Stop rather than
    a warning.
    """

    OWNER_STOP = "owner_stop"                  # the kill switch, any door
    CONSENT_UNREADABLE = "consent_unreadable"  # the ledger cannot be read
    CONSENT_CHAIN_BROKEN = "consent_chain_broken"  # projection disagrees with the chain
    INTEGRITY_MISSING = "integrity_missing"    # haloysius.integrity absent — broken install
    AUDIT_UNWRITABLE = "audit_unwritable"      # an action that cannot be accounted for is not performed
    REDACTION_UNAVAILABLE = "redaction_unavailable"  # a redaction-required capability with no backend
    GUARDRAIL_TRIPS = "guardrail_trips"        # three guardrail trips in a row


class HaltState:
    """The in-process halted flag with reason and provenance.

    Thread-safe (a lock guards every transition and read). Halting twice
    records the newer reason: a second failure detected while stopped is new
    information, and the machine should name the cause it would stop for
    now. Resuming a running state is a no-op.
    """

    __slots__ = ("_lock", "_reason_code", "_halted_by", "_halted_surface", "_halted_at",
                 "_resumed_by", "_resumed_surface", "_resumed_at")

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._reason_code: str = ""
        self._halted_by: str = ""
        self._halted_surface: str = ""
        self._halted_at: Optional[str] = None
        self._resumed_by: str = ""
        self._resumed_surface: str = ""
        self._resumed_at: Optional[str] = None

    def halt(self, reason_code: str, *, by: str = "", surface: str = "") -> None:
        """Enter the halted state, recording why and from where."""
        from datetime import datetime, timezone

        with self._lock:
            self._reason_code = reason_code
            self._halted_by = by
            self._halted_surface = surface
            self._halted_at = datetime.now(timezone.utc).isoformat()

    def resume(self, *, by: str = "", surface: str = "") -> None:
        """Clear the halted state, recording who resumed from where.

        No authority is checked here — the owner-re-auth asymmetry belongs
        to the D3-P6 live control that calls this. A resume of a running
        state records nothing.
        """
        from datetime import datetime, timezone

        with self._lock:
            if not self._reason_code and self._halted_at is None:
                return
            self._reason_code = ""
            self._halted_by = ""
            self._halted_surface = ""
            self._halted_at = None
            self._resumed_by = by
            self._resumed_surface = surface
            self._resumed_at = datetime.now(timezone.utc).isoformat()

    def is_halted(self) -> bool:
        with self._lock:
            return self._halted_at is not None

    @property
    def reason_code(self) -> str:
        with self._lock:
            return self._reason_code

    @property
    def halted_by(self) -> str:
        with self._lock:
            return self._halted_by

    @property
    def halted_surface(self) -> str:
        with self._lock:
            return self._halted_surface

    @property
    def halted_at(self) -> Optional[str]:
        with self._lock:
            return self._halted_at

    @property
    def resumed_by(self) -> str:
        with self._lock:
            return self._resumed_by

    @property
    def resumed_surface(self) -> str:
        with self._lock:
            return self._resumed_surface

    @property
    def resumed_at(self) -> Optional[str]:
        with self._lock:
            return self._resumed_at