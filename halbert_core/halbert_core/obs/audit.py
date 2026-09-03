# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tamper-evident audit log for tool executions.

Backed by :class:`haloysius.integrity.EventLog` (integrity handoff §3.3).

The log this replaced kept a SHA-256 chain *per file* under
``audit/YYYY/MM/DD/<tool>.jsonl``, restarting at ``prev_hash = None`` for
every new day and every new tool.  A chain that starts fresh in each file
can only see an edit made *inside* a file: deleting a day's file, or
trimming records off the end of one, left a log that still verified
perfectly.  That is the failure mode an audit log exists to catch, so the
chain is now continuous across every boundary and anchored by a persisted
head pointer -- the head is what makes a *short* log detectable, since a
truncated chain is otherwise still a valid chain.

Signing is opt-in and comes second, deliberately.  Signing a truncatable
log misrepresents its integrity, so continuity had to land first; and
resolving a signer *creates a private key on this machine*, which is not
something a tool call should do behind the user's back.  Call
:func:`set_audit_signer`, or set ``HALBERT_AUDIT_SIGNING=1`` to have the
custody ladder resolve one.  Unsigned, the log still appends, still
verifies, and honestly reports ``signed: 0``.
"""
from __future__ import annotations

import logging
import os
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

try:  # POSIX only; Halbert targets macOS and Linux, but do not hard-require it
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None  # type: ignore[assignment]

try:  # halbert_core's core is required to import without haloysius present
    from haloysius.integrity import EventLog, VerifyResult
except ImportError:  # pragma: no cover - exercised in a subprocess
    EventLog = None  # type: ignore[assignment,misc]
    VerifyResult = None  # type: ignore[assignment,misc]

from ..utils.paths import log_subdir

__all__ = [
    "AuditUnavailable",
    "write_audit",
    "audit_log",
    "verify_audit",
    "render_verify_report",
    "verify_result_as_dict",
    "set_audit_signer",
    "erase_audit_by_request",
    "get_audit_signer",
    "reset_audit_signer",
    "AUDIT_EVENT_KIND",
]

log = logging.getLogger(__name__)

#: Every audit record is an event of this kind in the log.
AUDIT_EVENT_KIND = "tool_execution"

#: Payload keys the audit record owns. A caller's keyword argument may not
#: land on any of them -- see write_audit.
#:
#: ``reason``, ``actor``, ``before_sha256`` and ``after_sha256`` are here
#: rather than in ``**extra`` on purpose. Provenance is what the record
#: exists to state, and an extra is whatever a tool result or a
#: model-supplied string happened to contain: leaving them shadowable would
#: let the audited event decide what the audit says about who changed
#: something and why. They are also the fields ``StateStore`` records on the
#: same write, so the two planes state the same thing about it.
AUDITED_FIELDS = frozenset(
    {
        "ts", "tool", "mode", "request_id", "ok", "summary", "shadowed",
        "reason", "actor", "before_sha256", "after_sha256",
    }
)

#: Set to 1/true/yes to have the audit log resolve a signing key from the
#: custody ladder on first use. Off by default -- see the module docstring.
SIGNING_ENV_VAR = "HALBERT_AUDIT_SIGNING"

_UNSET = object()
_signer: Any = _UNSET

_MISSING_INTEGRITY = (
    "the audit log needs haloysius.integrity, which is not installed. "
    "Install it from the sibling checkout: "
    "pip install -e /path/to/Haloysius. Halbert deliberately does not fall "
    "back to a hand-rolled chain here -- an audit log that cannot be "
    "verified but looks as though it can is worse than none."
)


class AuditUnavailable(RuntimeError):
    """The integrity layer the audit log is built on is not installed."""


# ---------------------------------------------------------------------------
# Signer registration.
# ---------------------------------------------------------------------------


def set_audit_signer(signer: Optional[Any]) -> None:
    """Register the ``SigningBackend`` that authors audit records.

    Passing ``None`` pins the log to unsigned rather than re-resolving.
    """
    global _signer
    _signer = signer


def reset_audit_signer() -> None:
    """Forget the registered signer, so the next write resolves again."""
    global _signer
    _signer = _UNSET


def get_audit_signer() -> Optional[Any]:
    """The active signer, resolving one from custody on first use if enabled."""
    global _signer
    if _signer is _UNSET:
        _signer = _resolve_signer_from_env()
    return _signer


def _resolve_signer_from_env() -> Optional[Any]:
    if os.environ.get(SIGNING_ENV_VAR, "").strip().lower() not in {"1", "true", "yes", "on"}:
        return None
    try:
        from ..crypto.storage import resolve_signer

        return resolve_signer()
    except Exception as exc:  # custody must never block an audit write
        log.warning("audit signing requested but no key could be resolved: %s", exc)
        return None


# ---------------------------------------------------------------------------
# The log.
# ---------------------------------------------------------------------------


def audit_log() -> EventLog:
    """The append-only log, rooted under ``<log_dir>/audit``.

    Rebuilt per call rather than cached: ``log_dir()`` is resolved from the
    environment, and a cached instance would keep writing to whichever
    directory happened to be configured first.
    """
    if EventLog is None:
        raise AuditUnavailable(_MISSING_INTEGRITY)
    return EventLog(log_subdir("audit"), signer=get_audit_signer())


#: Serializes appends within one process. The file lock below covers the
#: cross-process case; this covers threads, and covers everything on a
#: platform with no ``fcntl``.
_local_append_lock = threading.Lock()

#: Name of the lock file. Not ``*.jsonl``, so ``EventLog`` never reads it
#: as a shard.
LOCK_FILE = ".append.lock"


@contextmanager
def _append_lock(directory: Any):
    """Serialize the append's read-modify-write of the head pointer.

    ``EventLog.append`` reads the head, writes a record, then writes the
    head back, with nothing holding the three together.  Halbert runs tool
    calls concurrently -- async request handlers, the scheduler, the
    guardrail and recovery paths -- and two appends that interleave take
    the same ``seq`` and the same ``prev_hash``.  The log is then *reported
    as tampered with* even though nobody touched it, and an audit check
    that cries wolf is one people learn to ignore.

    The lock has to be a file lock rather than only an in-process one: the
    daemon, a tool subprocess and ``halbert audit-verify`` are separate
    processes writing the same log.  Where ``fcntl`` is unavailable the
    in-process lock still applies, and the failure mode is the pre-existing
    one rather than a new one.
    """
    with _local_append_lock:
        if fcntl is None:
            yield
            return
        path = os.path.join(str(directory), LOCK_FILE)
        try:
            handle = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
        except OSError as exc:
            # An unwritable log directory is the append's problem to report,
            # not the lock's; let the append fail with the real reason.
            log.debug("audit append lock unavailable (%s); appending unlocked", exc)
            yield
            return
        try:
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)
        finally:
            os.close(handle)


def write_audit(
    tool: str,
    mode: str,
    request_id: str,
    ok: bool,
    summary: str = "",
    *,
    reason: Optional[str] = None,
    actor: Optional[str] = None,
    before_sha256: Optional[str] = None,
    after_sha256: Optional[str] = None,
    **extra: Any,
) -> str:
    """Append one tool execution to the audit log; return the shard path.

    Never raises.  An audit record is a side effect of a tool call, not its
    purpose, and a full disk should not turn a successful ``write_config``
    into a failed one -- the failure is logged instead.

    Args:
        reason: why this happened -- a human utterance from the causing turn,
            a deterministic rule that names itself, or
            ``state_store.UNRECORDED``. Never a generated rationale: a
            plausible invented reason is unfalsifiable and everything
            downstream then reads it as evidence.
        actor: who caused it (``ACTOR_USER`` / ``ACTOR_AGENT`` /
            ``ACTOR_SYSTEM``, or a specific identifier).
        before_sha256/after_sha256: content digests for a mutation, so a
            record states what changed without carrying the content.

    These four are named parameters rather than ``**extra`` entries so they
    cannot be shadowed by a caller's keyword, and they are omitted from the
    payload entirely when not supplied -- an absent field says "not stated",
    which a null or an empty string would not.
    """
    try:
        payload: Dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "tool": tool,
            "mode": mode,
            "request_id": request_id,
            "ok": ok,
            "summary": summary,
        }
        for key, value in (
            ("reason", reason),
            ("actor", actor),
            ("before_sha256", before_sha256),
            ("after_sha256", after_sha256),
        ):
            if value is not None:
                payload[key] = value
        extras = _canonical_safe(extra or {})
        # A keyword argument must never land on top of an audited field.
        # `ok`, `tool` and `ts` are what the record exists to state, and
        # extras carry whatever a tool result or a model-supplied string
        # happened to contain -- letting one overwrite `ok` would let the
        # audited event decide what the audit says about it. Collisions are
        # kept under `shadowed` so nothing is lost and the attempt is visible.
        shadowed = {k: extras.pop(k) for k in list(extras) if k in AUDITED_FIELDS}
        payload.update(extras)
        if shadowed:
            payload["shadowed"] = shadowed
            log.warning(
                "audit call for %s passed %s, which would have overwritten an "
                "audited field; kept under 'shadowed'",
                tool, ", ".join(sorted(shadowed)),
            )
        events = audit_log()
        with _append_lock(events.directory):
            event = events.append(AUDIT_EVENT_KIND, payload)
        # _shard_path is the only way to name the file a given event landed
        # in; EventLog exposes no public equivalent, and callers of
        # write_audit have always been handed back a path.
        return str(events._shard_path(event.seq, event.ts_ms))
    except Exception as exc:
        log.error("audit record for %s/%s could not be written: %s", tool, mode, exc)
        return ""


def erase_audit_by_request(request_id: str) -> int:
    """Erase every audit record written under one request; return the count.

    Drops the payload and the salt, so the content is unrecoverable from the
    log and unbrute-forceable from the commitment, while every downstream
    hash and signature still verifies. The chain is not broken by this - that
    is the whole point of the salted-commitment design.

    Returns 0 rather than raising when nothing matches. An already-erased
    record has no payload and so cannot be found a second time: that is the
    idempotent path, not a failure.

    Never raises. Forgetting must not fail loudly at the one moment a person
    is asking for privacy; the count says what happened.
    """
    if not request_id:
        return 0
    try:
        events = audit_log()
    except Exception as exc:
        log.warning("audit erase for %s unavailable: %s", request_id, exc)
        return 0
    try:
        with _append_lock(events.directory):
            seqs = events.seqs_where(
                lambda payload: payload.get("request_id") == request_id
            )
            if not seqs:
                return 0
            return int(events.erase_many(seqs))
    except Exception as exc:
        log.error("audit erase for %s failed: %s", request_id, exc)
        return 0


def verify_audit(directory: Optional[Any] = None) -> "VerifyResult":
    """Walk the whole audit log and report every integrity failure found.

    Detects in-place edits, records trimmed off the end, and whole shard
    files deleted -- the last two being exactly what the per-file chain
    this replaced could not see.

    Takes the append lock for the duration. ``EventLog.append`` writes the
    record and *then* the head, so a verify landing between the two sees a
    log one record ahead of its head and calls it truncated -- 288 false
    tamper reports in a three-second race, before this lock. A check that
    cries wolf on a busy machine is one people learn to ignore.

    Raises:
        AuditUnavailable: haloysius.integrity is not installed, so there is
            nothing to verify *with*; or ``directory`` does not exist, so
            there is nothing to verify. Both are raised rather than returned
            as a clean result, which would read as "checked and fine" -- a
            typo in ``--dir`` must not print "no tampering detected".
    """
    if EventLog is None:
        raise AuditUnavailable(_MISSING_INTEGRITY)
    if directory is None:
        events = audit_log()
    else:
        path = Path(directory)
        if not path.is_dir():
            raise AuditUnavailable(
                f"no audit log directory at {path}. Nothing was checked -- "
                f"this is not the same as finding nothing wrong."
            )
        events = EventLog(path)
    with _append_lock(events.directory):
        return events.verify()


def render_verify_report(
    result: VerifyResult, peer: Optional[str] = None
) -> str:
    """Render a :class:`VerifyResult` as text for a person to read.

    The wording is a correctness requirement, not presentation (§3.5).
    This check cannot say the log is *verified*: on a single machine the
    signing key and the log share a disk, so whoever can rewrite the log
    can re-sign it, and a "verified" badge would assert something the
    system has no basis for.  What it can say is that nothing has been
    altered since the last independent point of comparison -- a peer sync,
    where one exists -- and that is what it says.
    """
    lines: list[str] = []
    against = f"since last sync with {peer}" if peer else "since this log began"

    if result.checked == 0 and not result.problems:
        lines.append("No records in the audit log -- nothing to check.")
        lines.append(
            "An empty log is not a clean log: it is a log that has not been "
            "written to yet."
        )
        return "\n".join(lines)

    if result.ok:
        lines.append(f"No tampering detected {against}.")
    else:
        lines.append(f"TAMPERING DETECTED {against}.")

    if result.checked == 0:
        # Empty *and* faulted: the head pointer says records should be here
        # and they are not. Reporting this as "nothing to check" would hide
        # the most complete tampering there is -- deleting the whole log.
        lines.append(
            "  The log holds no readable records, but its head pointer says "
            "it should. Every record has been removed."
        )
    else:
        unsigned = result.checked - result.signed
        lines.append(
            f"  records checked: {result.checked}    "
            f"signed: {result.signed}    unsigned: {unsigned}"
        )
        if result.signed == 0 and result.ok:
            lines.append(
                "  All records are unsigned: this check confirms the chain is "
                "internally consistent, not who wrote it."
            )
        elif result.signed == 0:
            lines.append(
                "  All records are unsigned, so there is no signature to say "
                "who wrote them either."
            )

    if result.problems:
        lines.append("")
        lines.append(f"{len(result.problems)} problem(s):")
        lines.extend(f"  {problem}" for problem in result.problems)
        return "\n".join(lines)

    lines.append("")
    if peer:
        lines.append(
            f"  Checked against the head last agreed with {peer}. Records "
            f"written since then are attested only by this machine."
        )
    else:
        lines.append(
            "  Both the log and the key that would sign it live on the same "
            "machine, so this cannot prove the log was never rewritten -- only "
            "that nothing has been altered underneath the running system. An "
            "off-machine comparison (a peer sync) is what would strengthen it."
        )
    return "\n".join(lines)


def verify_result_as_dict(result: VerifyResult) -> Dict[str, Any]:
    """The same outcome as JSON, for scripts and the dashboard."""
    return {
        "ok": result.ok,
        "checked": result.checked,
        "signed": result.signed,
        "unsigned": result.checked - result.signed,
        "problems": [
            {"kind": p.kind, "seq": p.seq, "detail": p.detail}
            for p in result.problems
        ],
    }


# ---------------------------------------------------------------------------
# Payload hygiene.
# ---------------------------------------------------------------------------


def _canonical_safe(value: Any) -> Any:
    """Coerce a value into something :func:`canonicalize` accepts.

    Canonical form admits ``None``, bool, int, str, list and str-keyed dict,
    and rejects floats outright (RFC 8785's number rules are not portable).
    Callers pass arbitrary keyword arguments, so anything outside that set
    is rendered as text here rather than being allowed to fail the write:
    an audit record that records a duration as ``"1.5"`` is worth more than
    no audit record at all.

    Never raises. Rendering an arbitrary object runs *its* ``__str__``, and
    a value that throws there must cost that one field, not the whole audit
    record -- write_audit is called on tool failure paths, where the object
    in hand is exactly the kind most likely to be half-constructed.
    """
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, dict):
        return {_as_text(k): _canonical_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical_safe(v) for v in value]
    if isinstance(value, set):
        # Sorted so two bodies recording the same set record the same bytes.
        return sorted(_as_text(v) for v in value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return _as_text(value)


def _as_text(value: Any) -> str:
    """``str(value)``, substituting a placeholder if the object fights back."""
    if isinstance(value, datetime):
        try:
            return value.isoformat()
        except Exception:
            pass
    try:
        return str(value)
    except Exception:
        try:
            return f"<unrenderable {type(value).__name__}>"
        except Exception:
            return "<unrenderable>"
