# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The consent ledger — the store, its projection, and its one writer.

PERMISSION-AND-CONSENT-SYSTEM-2026-09-06.md §1.5:

    Store. ``<data_dir>/consent`` — an append-only
    ``haloysius.integrity.EventLog``, the same primitive ``obs/audit.py``
    was rebuilt on: hash chain continuous across day and tool boundaries,
    a persisted head pointer so truncation is detectable, salted
    commitments so a record can be erased without breaking the chain.
    Files ``0600`` in a ``0700`` directory. Plus a derived, ``0600``,
    ``flock``-guarded projection at ``<config_dir>/consent-state.json``
    for fast reads.

    The log is authoritative; the projection is rebuildable. ... A
    projection that disagrees with the chain is not a warning — it is a
    Stop (§4.1), and the machine says which.

Ruling on the optional dependency (§1.5, recorded in the design): if
``haloysius.integrity`` is absent, the machine boots halted and says so.
It is a broken install, not a supported configuration — this module
raises ``ConsentUnavailable(halt_reason=INTEGRITY_MISSING)`` rather than
falling back to a hand-rolled chain.

``record_decision`` is the **one writer** and enforces the §1.5 asymmetry
at the function: narrowing (``denied``/``revoked``/``expired``) is
writable by an ``owner``, an ``os`` (a revocation we detected) or
``system`` (halt, expiry, a new-capability default); a ``granted`` record
is refused unless the principal is an owner on an authenticated
first-party surface with a live OS re-auth — everything else raises
``GrantRefused`` with the reason code that says which leg failed, and
nothing is written. There is no argument that makes the agent an owner;
it cannot mint a grant, it can only ask.

This module never reads the legacy consent flags (``being.yml
senses.*``, ``vision_config.yml``, ...) — per the standing no-users
directive those keys stay on disk, unread, never deleted, and are never
read as grants.
"""
from __future__ import annotations

import fcntl
import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

try:  # halbert_core's core imports without haloysius present; using it halts
    from haloysius.integrity import EventLog, VerifyResult
except ImportError:  # pragma: no cover - exercised via monkeypatch in tests
    EventLog = None  # type: ignore[assignment,misc]
    VerifyResult = None  # type: ignore[assignment,misc]

from ..persona.permission.consent import (
    ConsentDecision,
    ConsentRecord,
    Principal,
    FIRST_PARTY_SURFACES,
    consent_state,
    is_valid_grant_record,
    latest_for,
    may_record_grant,
)
from ..persona.permission.ceiling import NEVER_CEILING_IDS, VOCABULARY, takes_consent_records
from ..persona.permission.halt import HaltReason, HaltState
from .denials import ConsentUnavailable

__all__ = [
    "CONSENT_EVENT_KIND",
    "ConsentStore",
    "GrantRefused",
    "record_from_payload",
    "record_to_payload",
]

log = logging.getLogger(__name__)

#: Every consent decision is an event of this kind in the ledger.
CONSENT_EVENT_KIND = "consent_decision"

#: The ledger directory, under the resolved data dir.
LEDGER_DIRNAME = "consent"

#: The projection file, under the resolved config dir.
PROJECTION_FILENAME = "consent-state.json"

_PROJECTION_VERSION = 1


class GrantRefused(Exception):
    """A widening (or unauthorized narrowing) attempt the writer refused.

    The reason code names which leg of the §1.5 bar failed, so Gate 4's
    proof half ("four refusals, each with a reason") is testable at this
    one function. Nothing is written when this is raised.
    """

    #: The capability does not take consent records (unknown, or sys.*).
    NOT_A_CONSENT_CAPABILITY = "not_a_consent_capability"
    #: The capability is declared absent (egress.telemetry) — the ledger
    #: never carries a grant for it; the ceiling proves the absence.
    DECLARED_ABSENT_CAPABILITY = "declared_absent_capability"
    #: The principal is not the owner. There is no argument that makes the
    #: agent an owner.
    NOT_OWNER = "not_owner"
    #: The surface is not an authenticated first-party surface (§3.4: no
    #: dangerous grant may be made from a remote surface).
    NOT_FIRST_PARTY_SURFACE = "not_first_party_surface"
    #: The decision arrived over a wire — at_machine is False.
    NOT_AT_MACHINE = "not_at_machine"
    #: A session credential is not a widening path; only a live OS
    #: re-auth (os_reauth:...) is.
    NO_LIVE_OS_REAUTH = "no_live_os_reauth"
    #: Gate 4: text_shown_sha256 is the field that turns a record into
    #: evidence. A grant without it is a boolean anyone could assert.
    NO_TEXT_SHOWN = "no_text_shown"
    #: Narrowing is owner/os/system only — an agent, peer or guest may not
    #: write a denial (it could narrow the owner's grants and blame them).
    UNAUTHORIZED_NARROWER = "unauthorized_narrower"
    #: Absence is the absence of a record, never a recorded answer.
    ABSENT_IS_NOT_AN_EVENT = "absent_is_not_an_event"

    def __init__(self, reason_code: str, detail: str = "") -> None:
        self.reason_code = reason_code
        self.detail = detail
        super().__init__(f"refused: {reason_code}" + (f" ({detail})" if detail else ""))


#: Who may write a narrowing record (§1.5): the owner, the OS (a
#: revocation we detected), or the system (halt, expiry, a
#: new-capability default).
NARROWING_WRITERS = frozenset({"owner", "os", "system"})

#: The decisions that narrow. GRANTED is the only widening.
_NARROWING_DECISIONS = frozenset({
    ConsentDecision.DENIED,
    ConsentDecision.REVOKED,
    ConsentDecision.EXPIRED,
})


# ---------------------------------------------------------------------------
# Payload serialization — the record as one JSON event.
# ---------------------------------------------------------------------------

_PRINCIPAL_FIELDS = ("kind", "id", "name", "authn", "at_machine")
_RECORD_FIELDS = (
    "capability", "decision", "ts", "surface", "text_shown_sha256", "via",
    "scope", "channel", "body", "os_grant_at_time", "session_type",
    "other_login_accounts", "build_version", "build_commit", "signing_subject",
    "policy_version", "expires_at", "cause", "prior",
)


def record_to_payload(record: ConsentRecord) -> Dict[str, Any]:
    """Flatten one record into the payload its ledger event carries."""
    payload: Dict[str, Any] = {
        "capability": record.capability,
        "decision": record.decision.value,
        "ts": record.ts,
        "principal": {
            "kind": record.principal.kind,
            "id": record.principal.id,
            "name": record.principal.name,
            "authn": record.principal.authn,
            "at_machine": record.principal.at_machine,
        },
        "surface": record.surface,
        "text_shown_sha256": record.text_shown_sha256,
        "via": record.via,
        "scope": dict(record.scope or {}),
        "channel": record.channel,
        "body": record.body,
        "os_grant_at_time": record.os_grant_at_time,
        "session_type": record.session_type,
        "other_login_accounts": record.other_login_accounts,
        "build_version": record.build_version,
        "build_commit": record.build_commit,
        "signing_subject": record.signing_subject,
        "policy_version": record.policy_version,
        "expires_at": record.expires_at,
        "cause": record.cause,
        "prior": record.prior.value if record.prior is not None else "",
    }
    return payload


def record_from_payload(payload: Mapping[str, Any]) -> ConsentRecord:
    """Rebuild the record from its event payload (fail-closed on shape)."""
    try:
        return ConsentRecord(
            capability=payload["capability"],
            decision=ConsentDecision(payload["decision"]),
            ts=payload["ts"],
            principal=Principal(
                kind=payload["principal"]["kind"],
                id=payload["principal"].get("id", ""),
                name=payload["principal"].get("name", ""),
                authn=payload["principal"].get("authn", ""),
                at_machine=bool(payload["principal"].get("at_machine", False)),
            ),
            surface=payload.get("surface", ""),
            text_shown_sha256=payload.get("text_shown_sha256", ""),
            via=payload.get("via", ""),
            scope=dict(payload.get("scope") or {}),
            channel=payload.get("channel", ""),
            body=payload.get("body", ""),
            os_grant_at_time=payload.get("os_grant_at_time", ""),
            session_type=payload.get("session_type", ""),
            other_login_accounts=int(payload.get("other_login_accounts", 0)),
            build_version=payload.get("build_version", ""),
            build_commit=payload.get("build_commit", ""),
            signing_subject=payload.get("signing_subject"),
            policy_version=payload.get("policy_version", "consent-schema/1"),
            expires_at=payload.get("expires_at"),
            cause=payload.get("cause", ""),
            prior=(
                ConsentDecision(payload["prior"])
                if payload.get("prior") else None
            ),
        )
    except (KeyError, ValueError) as exc:
        raise ConsentUnavailable(
            f"a consent record in the ledger is not shaped like one ({exc})",
            halt_reason=HaltReason.CONSENT_UNREADABLE,
        ) from exc


# ---------------------------------------------------------------------------
# Locking — the obs/audit.py pattern, restated for this ledger.
# ---------------------------------------------------------------------------

#: Serializes appends within one process; the file lock below covers the
#: cross-process case (the daemon, and ``halbert consent-verify``).
_local_lock = threading.Lock()

#: Name of the lock file. Not ``*.jsonl`` so EventLog never reads it as a shard.
_LOCK_FILENAME = ".append.lock"


def _flock_file(directory: Path, name: str):
    path = directory / name
    handle = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(handle, fcntl.LOCK_EX)
    except OSError:  # pragma: no cover - platforms without flock support
        os.close(handle)
        return None
    return handle


def _append_locked(log, payload: Dict[str, Any]):
    """Append one event under the cross-process lock, mirroring
    ``obs/audit.py::_append_lock``: ``EventLog.append`` reads the head,
    writes the record, then writes the head back, and two interleaving
    appends take the same ``seq`` and ``prev_hash`` — a log that then
    *reports* tampering nobody caused.
    """
    with _local_lock:
        handle = _flock_file(log.directory, _LOCK_FILENAME)
        try:
            return log.append(CONSENT_EVENT_KIND, payload)
        finally:
            if handle is not None:
                fcntl.flock(handle, fcntl.LOCK_UN)
                os.close(handle)


def _enforce_perms(directory: Path) -> None:
    """The ledger is ``0600`` files in a ``0700`` directory (§1.5).

    ``EventLog`` creates its shards and head with the process umask, so
    the store tightens them after every append — a consent ledger that a
    second login account could read is a household notice that lied.
    """
    try:
        os.chmod(directory, 0o700)
        for entry in directory.iterdir():
            if entry.is_file():
                os.chmod(entry, 0o600)
    except OSError as exc:  # pragma: no cover - unwritable ledger surfaces
        log.warning("consent ledger permissions could not be enforced: %s", exc)


# ---------------------------------------------------------------------------
# The store.
# ---------------------------------------------------------------------------


class ConsentStore:
    """The append-only consent ledger and its derived projection.

    The log at ``<data_dir>/consent`` is authoritative; the projection at
    ``<config_dir>/consent-state.json`` is derived and rebuildable; a
    disagreement between them is a **Stop** (§1.5/§4.1) —
    :meth:`check_or_halt` writes the halt reason into P1's ``HaltState``
    and raises ``ConsentUnavailable``, never returning a fallback value.

    Dirs are injectable for tests; the defaults resolve from
    ``utils.paths`` (``HALBERT_DATA_DIR`` / the platform config dir), so
    importing this module never touches the host.
    """

    def __init__(
        self,
        *,
        data_dir: Optional[str] = None,
        config_dir: Optional[str] = None,
    ) -> None:
        if data_dir is None or config_dir is None:
            from ..utils.paths import config_dir as _default_config_dir
            from ..utils.paths import data_dir as _default_data_dir
            data_dir = data_dir or _default_data_dir()
            config_dir = config_dir or _default_config_dir()
        self.data_dir = str(data_dir)
        self.config_dir = str(config_dir)

    # -- locations ------------------------------------------------------

    @property
    def ledger_dir(self) -> Path:
        return Path(self.data_dir) / LEDGER_DIRNAME

    @property
    def projection_path(self) -> Path:
        return Path(self.config_dir) / PROJECTION_FILENAME

    def _log(self) -> "EventLog":
        if EventLog is None:
            raise ConsentUnavailable(
                "the consent ledger needs haloysius.integrity, which is not "
                "installed. This is a broken install, not a supported "
                "configuration — the machine boots halted. (halbert_core "
                "imports without it; using the ledger does not.)",
                halt_reason=HaltReason.INTEGRITY_MISSING,
            )
        directory = self.ledger_dir
        directory.mkdir(parents=True, exist_ok=True)
        _enforce_perms(directory)
        return EventLog(directory)

    # -- the one writer ---------------------------------------------------

    def record_decision(
        self,
        capability: str,
        decision: ConsentDecision,
        *,
        principal: Principal,
        surface: str,
        text_shown_sha256: str = "",
        via: str = "",
        scope: Optional[Mapping[str, Any]] = None,
        channel: str = "",
        body: str = "",
        os_grant_at_time: str = "",
        session_type: str = "",
        other_login_accounts: int = 0,
        build_version: str = "",
        build_commit: str = "",
        signing_subject: Optional[str] = None,
        expires_at: Optional[str] = None,
        cause: str = "",
        ts: Optional[str] = None,
    ) -> ConsentRecord:
        """Append one decision event — the only writer (§1.5).

        Enforces, at this function:

        - the capability takes consent records (unknown or ``sys.*`` ids
          have no consent surface) and a ``granted`` for a declared-absent
          id is refused outright;
        - the widening asymmetry — narrowing is writable by
          ``owner``/``os``/``system`` only, a grant needs
          ``may_record_grant`` (owner, first-party surface, live OS
          re-auth, at the machine) **and** the digest of the copy shown;
        - absence is not an event.

        Raises ``GrantRefused`` (nothing written) or ``ConsentUnavailable``
        (the integrity primitive is missing). A failed append propagates
        the underlying error after writing nothing: an action that cannot
        be recorded is not performed.
        """
        if not takes_consent_records(capability):
            raise GrantRefused(
                GrantRefused.NOT_A_CONSENT_CAPABILITY,
                f"'{capability}' does not take consent records; only "
                f"sensor/reach/egress/auto ids do",
            )
        if (
            decision is ConsentDecision.GRANTED
            and capability in NEVER_CEILING_IDS
        ):
            raise GrantRefused(
                GrantRefused.DECLARED_ABSENT_CAPABILITY,
                f"'{capability}' is declared absent; the ledger never "
                f"carries a grant for it",
            )

        if decision is ConsentDecision.ABSENT:
            raise GrantRefused(
                GrantRefused.ABSENT_IS_NOT_AN_EVENT,
                "absence is the absence of a record, never an answer that "
                "was given",
            )

        if decision is ConsentDecision.GRANTED:
            self._refuse_unless_widening_is_authorized(principal, surface)
            if not text_shown_sha256:
                raise GrantRefused(
                    GrantRefused.NO_TEXT_SHOWN,
                    "a grant without the digest of the copy the owner saw "
                    "is a boolean anyone could have asserted",
                )
        else:
            if principal.kind not in NARROWING_WRITERS:
                raise GrantRefused(
                    GrantRefused.UNAUTHORIZED_NARROWER,
                    f"narrowing is written by owner/os/system; "
                    f"'{principal.kind}' may not record a {decision.value}",
                )

        events = self._log()
        prior_records = self._records_from(events)
        prior_decision = latest_for(prior_records, capability)
        record = ConsentRecord(
            capability=capability,
            decision=decision,
            ts=ts or datetime.now(timezone.utc).isoformat(),
            principal=principal,
            surface=surface,
            text_shown_sha256=text_shown_sha256,
            via=via,
            scope=dict(scope or {}),
            channel=channel,
            body=body,
            os_grant_at_time=os_grant_at_time,
            session_type=session_type,
            other_login_accounts=other_login_accounts,
            build_version=build_version,
            build_commit=build_commit,
            signing_subject=signing_subject,
            expires_at=expires_at,
            cause=cause,
            prior=prior_decision.decision if prior_decision else None,
        )
        if decision is ConsentDecision.GRANTED and not is_valid_grant_record(record):
            # Belt and braces: may_record_grant and the text check above
            # already cover this; a record that could not be evidenced must
            # never reach the chain even if a future caller reorders them.
            raise GrantRefused(GrantRefused.NO_TEXT_SHOWN)

        event = _append_locked(events, record_to_payload(record))
        _enforce_perms(self.ledger_dir)
        self._write_projection(events)
        log.info(
            "consent decision recorded: %s %s (seq %d)",
            capability, decision.value, event.seq,
        )
        return record

    @staticmethod
    def _refuse_unless_widening_is_authorized(principal: Principal, surface: str) -> None:
        """The §1.5 bar, each leg named so the refusal says which failed."""
        if principal.kind != "owner":
            raise GrantRefused(
                GrantRefused.NOT_OWNER,
                f"the agent is never an owner; a '{principal.kind}' "
                f"principal cannot mint a grant, it can only ask",
            )
        if surface not in FIRST_PARTY_SURFACES:
            raise GrantRefused(
                GrantRefused.NOT_FIRST_PARTY_SURFACE,
                f"'{surface}' is not an authenticated first-party surface; "
                f"no dangerous grant may be made from a remote surface",
            )
        if not principal.at_machine:
            raise GrantRefused(
                GrantRefused.NOT_AT_MACHINE,
                "the decision arrived over a wire",
            )
        if not principal.authn.startswith("os_reauth"):
            raise GrantRefused(
                GrantRefused.NO_LIVE_OS_REAUTH,
                f"authn '{principal.authn or 'none'}' is not a live OS "
                f"re-auth; a session credential is not a widening path",
            )

    # -- reads -----------------------------------------------------------

    @staticmethod
    def _records_from(events: "EventLog") -> List[ConsentRecord]:
        records: List[ConsentRecord] = []
        for event in events.read_all():
            if event.kind != CONSENT_EVENT_KIND or event.payload is None:
                continue
            records.append(record_from_payload(event.payload))
        return records

    def records(self) -> List[ConsentRecord]:
        """Every recorded decision, in append order (the log is
        authoritative). No ledger directory yet is the first-boot state:
        absence means never asked, never allowed."""
        if not self.ledger_dir.is_dir():
            return []
        return self._records_from(self._log())

    def state_for(
        self, capability: str, *, now: Optional[str] = None
    ) -> ConsentDecision:
        """The current folded decision for one capability."""
        return consent_state(self.records(), capability, now=now)

    # -- verification ----------------------------------------------------

    def verify(self) -> "VerifyResult":
        """Walk the whole chain and report every integrity failure.

        The integrity primitive is checked **first**: §1.5's ruling is
        that its absence is a broken install that boots halted, so a
        machine that cannot even instantiate the log never reports "no
        records, nothing to check" — there is nothing to check *with*.
        A missing ledger directory past that is the empty first-boot log
        (checked 0, ok).
        """
        if EventLog is None:
            raise ConsentUnavailable(
                "the consent ledger needs haloysius.integrity, which is "
                "not installed. This is a broken install, not a supported "
                "configuration — the machine boots halted.",
                halt_reason=HaltReason.INTEGRITY_MISSING,
            )
        if not self.ledger_dir.is_dir():
            return VerifyResult(ok=True, checked=0, signed=0)
        events = self._log()
        handle = _flock_file(events.directory, _LOCK_FILENAME)
        try:
            return events.verify()
        finally:
            if handle is not None:
                fcntl.flock(handle, fcntl.LOCK_UN)
                os.close(handle)

    def _projection_content(self, events: "EventLog") -> Dict[str, Any]:
        """The expected projection derived from the authoritative log."""
        records = self._records_from(events)
        state: Dict[str, Any] = {}
        for record in records:
            state[record.capability] = {
                "decision": record.decision.value,
                "ts": record.ts,
                "expires_at": record.expires_at or "",
            }
        last = None
        all_events = [e for e in events.read_all() if e.kind == CONSENT_EVENT_KIND]
        if all_events:
            last = all_events[-1]
        return {
            "version": _PROJECTION_VERSION,
            "head_seq": last.seq if last else -1,
            "head_hash": last.hash if last else "",
            "records": len(records),
            "state": dict(sorted(state.items())),
        }

    def _write_projection(self, events: "EventLog") -> Path:
        """Write the derived projection atomically (0600, flock-guarded)."""
        content = self._projection_content(events)
        path = self.projection_path
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = _flock_file(path.parent, "." + PROJECTION_FILENAME + ".lock")
        try:
            tmp = path.with_name(PROJECTION_FILENAME + ".tmp")
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(content, stream, indent=2, sort_keys=True)
                stream.write("\n")
            os.replace(tmp, path)
            os.chmod(path, 0o600)
        finally:
            if handle is not None:
                fcntl.flock(handle, fcntl.LOCK_UN)
                os.close(handle)
        return path

    def read_projection(self) -> Optional[Dict[str, Any]]:
        """The projection's contents, or None when it does not exist."""
        path = self.projection_path
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ConsentUnavailable(
                f"the consent projection at {path} cannot be read: {exc}",
                halt_reason=HaltReason.CONSENT_UNREADABLE,
            ) from exc

    def projection_status(self) -> str:
        """``"absent"`` | ``"agrees"`` | ``"disagrees"``.

        The log is authoritative; the projection is derived. A projection
        that disagrees with the chain is tampering or corruption — §1.5
        makes it a Stop, and the boot check halts on it.
        """
        events = self._log() if self.ledger_dir.is_dir() else None
        expected = (
            self._projection_content(events) if events is not None
            else {"version": _PROJECTION_VERSION, "head_seq": -1, "head_hash": "",
                  "records": 0, "state": {}}
        )
        actual = self.read_projection()
        if actual is None:
            return "absent"
        if actual == expected:
            return "agrees"
        return "disagrees"

    def check_or_halt(self, halt: HaltState) -> None:
        """The boot-time Stop (§1.5, §4.1): verify the chain, then the
        projection. Any failure halts the machine with the reason that
        says which trust precondition broke, and raises — never a
        fallback value. A merely missing projection is rebuildable and
        is rebuilt, not a Stop."""
        try:
            result = self.verify()
        except ConsentUnavailable as exc:
            # verify() could not even run (integrity missing, unreadable
            # ledger): the machine halts for the reason the exception
            # carries, then the exception propagates — a Stop, never a
            # fallback value.
            halt.halt(exc.halt_reason, by="consent-store", surface="boot")
            raise
        if not result.ok:
            halt.halt(
                HaltReason.CONSENT_CHAIN_BROKEN,
                by="consent-store", surface="boot",
            )
            raise ConsentUnavailable(
                "the consent ledger's chain does not verify — "
                f"{len(result.problems)} problem(s); the machine is stopped",
                halt_reason=HaltReason.CONSENT_CHAIN_BROKEN,
            )
        status = self.projection_status()
        if status == "disagrees":
            halt.halt(
                HaltReason.CONSENT_CHAIN_BROKEN,
                by="consent-store", surface="boot",
            )
            raise ConsentUnavailable(
                f"the consent projection at {self.projection_path} "
                f"disagrees with the chain — the machine is stopped",
                halt_reason=HaltReason.CONSENT_CHAIN_BROKEN,
            )
        if status == "absent":
            # Derived data: rebuildable, so a fresh or deleted projection
            # is rebuilt rather than treated as tampering.
            self.rebuild()

    def rebuild(self) -> Dict[str, Any]:
        """Reproject from the authoritative log (``halbert consent-rebuild``).

        Refuses to run on a chain that does not verify — a rebuild from a
        tampered log would launder the tampering into a "clean"
        projection, which is the one thing this command must never do.
        """
        result = self.verify()
        if not result.ok:
            raise ConsentUnavailable(
                "the consent chain does not verify; refusing to project a "
                "tampered log into a clean-looking state",
                halt_reason=HaltReason.CONSENT_CHAIN_BROKEN,
            )
        events = self._log() if self.ledger_dir.is_dir() else None
        if events is None:
            content = {"records": 0, "capabilities": 0, "path": str(self.projection_path)}
            # An empty log still writes its (empty) projection.
            self._write_projection(_EmptyLog(self.ledger_dir))
            return content
        path = self._write_projection(events)
        content = self._projection_content(events)
        return {
            "records": content["records"],
            "capabilities": len(content["state"]),
            "path": str(path),
        }


class _EmptyLog:
    """A stand-in EventLog for an absent ledger directory: the projection
    of an empty chain (head_seq -1, no state), so a first-boot rebuild
    writes an honest empty projection rather than none."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def read_all(self):  # pragma: no cover - exercised via rebuild()
        return []