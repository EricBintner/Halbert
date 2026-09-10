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

import errno
import json
import logging
import os
import secrets
import threading
from pathlib import Path
from typing import Any, Dict, Optional

try:  # POSIX only; Halbert is a single-host macOS/Linux steward.
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None

logger = logging.getLogger("halbert.permission.halt")

#: Where the halt state lives on disk (D3-P6 task 1, FD-5).
HALT_FILENAME = "halt.json"
HALT_SUBDIR = "runtime"


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


class PersistedHalt:
    """The halt state on disk: ``<data_dir>/runtime/halt.json``.

    A11-G6 under FD-5. The in-process flag lasted exactly as long as the
    process, and the conditions that halt the machine -- a consent ledger
    it cannot read, a missing integrity primitive, an audit log it cannot
    write -- are precisely the ones a restart does not fix. So the daemon
    came back up running with the same broken precondition.

    0600, written atomically through a temp file and ``os.replace``,
    flock-guarded so two writers cannot interleave, in the same shape the
    consent projection uses one module over.
    """

    def __init__(self, *, data_dir: Optional[str] = None) -> None:
        if data_dir is None:
            from ...utils.paths import data_dir as _default_data_dir
            data_dir = _default_data_dir()
        self.path = Path(str(data_dir)) / HALT_SUBDIR / HALT_FILENAME

    def _lock(self):
        if fcntl is None:  # pragma: no cover - Windows
            return None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self.path.parent / ("." + HALT_FILENAME + ".lock")
        fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)
        return fd

    @staticmethod
    def _unlock(handle) -> None:
        if handle is None:
            return
        fcntl.flock(handle, fcntl.LOCK_UN)
        os.close(handle)

    def write(self, payload: Optional[Dict[str, Any]]) -> None:
        """Persist the halt, or clear it. Never raises into the caller:
        a machine that cannot record its own Stop still has to STOP."""
        handle = None
        try:
            handle = self._lock()
            if payload is None:
                try:
                    self.path.unlink()
                except FileNotFoundError:
                    pass
                return
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_name(HALT_FILENAME + ".tmp")
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(payload, stream, indent=2, sort_keys=True)
                stream.write("\n")
            os.replace(tmp, self.path)
            os.chmod(self.path, 0o600)
        except OSError as e:
            logger.error(
                "could not persist the halt state to %s (%s); the "
                "in-process stop still stands", self.path, e)
        finally:
            self._unlock(handle)

    def read(self) -> Optional[Dict[str, Any]]:
        """The persisted halt, ``None`` when there is none.

        Raises ``ValueError`` when the file exists and cannot be read:
        a halt state nobody can read is not evidence of a running
        machine, and the caller fails closed on it.
        """
        handle = None
        try:
            handle = self._lock()
            try:
                text = self.path.read_text(encoding="utf-8")
            except FileNotFoundError:
                return None
            except OSError as e:
                raise ValueError(f"halt state unreadable: {e}") from e
            try:
                payload = json.loads(text)
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                raise ValueError(f"halt state is not readable JSON: {e}") from e
            if not isinstance(payload, dict):
                raise ValueError("halt state is not an object")
            return payload
        finally:
            self._unlock(handle)


class HaltState:
    """The in-process halted flag with reason and provenance.

    Thread-safe (a lock guards every transition and read). Halting twice
    records the newer reason: a second failure detected while stopped is new
    information, and the machine should name the cause it would stop for
    now. Resuming a running state is a no-op.
    """

    __slots__ = ("_lock", "_reason_code", "_halted_by", "_halted_surface", "_halted_at",
                 "_resumed_by", "_resumed_surface", "_resumed_at",
                 "_persisted", "_resume_token")

    def __init__(self, *, persisted: Optional["PersistedHalt"] = None) -> None:
        self._lock = threading.Lock()
        self._reason_code: str = ""
        self._halted_by: str = ""
        self._halted_surface: str = ""
        self._halted_at: Optional[str] = None
        self._resumed_by: str = ""
        self._resumed_surface: str = ""
        self._resumed_at: Optional[str] = None
        #: Where this state is mirrored on disk. ``None`` keeps the pure
        #: in-process object every existing caller and test builds.
        self._persisted = persisted
        #: The outstanding resume token, minted by the authorised path
        #: and redeemable once.
        self._resume_token: Optional[str] = None

    def halt(self, reason_code: str, *, by: str = "", surface: str = "") -> None:
        """Enter the halted state, recording why and from where."""
        from datetime import datetime, timezone

        with self._lock:
            self._reason_code = reason_code
            self._halted_by = by
            self._halted_surface = surface
            self._halted_at = datetime.now(timezone.utc).isoformat()
            # A halt that is not the one that was minted for cannot be
            # resumed by an old token.
            self._resume_token = None
            payload = self._payload()
        if self._persisted is not None:
            self._persisted.write(payload)

    def _payload(self) -> Dict[str, Any]:
        """The persisted shape. Called with the lock held."""
        return {
            "reason_code": self._reason_code,
            "halted_by": self._halted_by,
            "halted_surface": self._halted_surface,
            "halted_at": self._halted_at,
        }

    def load(self) -> None:
        """Read the persisted halt at boot (D3-P6 task 1, FD-5).

        Fail-closed on an unreadable file: a halt state nobody can read
        is not evidence of a running machine. The machine halts for
        ``CONSENT_UNREADABLE`` -- the reason code that already means "a
        trust precondition could not be verified" -- rather than starting
        up and finding out later.
        """
        if self._persisted is None:
            return
        try:
            payload = self._persisted.read()
        except ValueError as e:
            logger.error(
                "the persisted halt state could not be read (%s); "
                "halting rather than assuming the machine may run", e)
            self.halt(
                HaltReason.CONSENT_UNREADABLE,
                by="boot", surface="halt-state",
            )
            return
        if not payload or not payload.get("halted_at"):
            return
        with self._lock:
            self._reason_code = str(payload.get("reason_code", ""))
            self._halted_by = str(payload.get("halted_by", ""))
            self._halted_surface = str(payload.get("halted_surface", ""))
            self._halted_at = str(payload.get("halted_at"))
            self._resume_token = None
        logger.error(
            "boot: the machine is halted (%s, recorded %s); nothing runs "
            "until it is resumed", self._reason_code, self._halted_at)

    def mint_resume_token(self) -> str:
        """Mint the single-use token a resume must present.

        The asymmetry the design calls for (§4.1): halting is easy and
        anyone's to do; resuming is the authorised path's alone. The
        wiring that owns that path -- an owner, on a first-party surface,
        with OS re-auth, shown what will restart -- calls this and hands
        the token to ``resume``. The authority lives in that wiring; what
        this guarantees is that "clear the flag" is not something a
        caller can do by simply calling it.
        """
        with self._lock:
            self._resume_token = secrets.token_urlsafe(24)
            return self._resume_token

    def resume(
        self, *, by: str = "", surface: str = "", token: Optional[str] = None,
    ) -> None:
        """Clear the halted state, recording who resumed from where.

        Requires a token minted by :meth:`mint_resume_token` (A11-G6,
        FD-5). The owner-re-auth asymmetry itself still belongs to the
        D3-P6 live control -- what is enforced HERE is that a resume
        cannot happen by simply calling this method, which is what made
        the stop something the machine could lift on its own behalf.

        A resume of a running state records nothing.
        """
        from datetime import datetime, timezone

        with self._lock:
            if not self._reason_code and self._halted_at is None:
                return
            expected = self._resume_token
            if not expected or not token or not secrets.compare_digest(
                str(token), str(expected)
            ):
                raise PermissionError(
                    "a resume needs a token minted for this halt; clearing "
                    "the stop is the authorised path's to do, not the "
                    "caller's"
                )
            self._resume_token = None
            self._reason_code = ""
            self._halted_by = ""
            self._halted_surface = ""
            self._halted_at = None
            self._resumed_by = by
            self._resumed_surface = surface
            self._resumed_at = datetime.now(timezone.utc).isoformat()
        if self._persisted is not None:
            self._persisted.write(None)

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