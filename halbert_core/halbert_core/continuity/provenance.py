# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""One call that records a change on both planes, so they cannot disagree.

LEDGER-1 wants every write path to record *path, before/after, actor, reason*.
Two stores hold different halves of that:

- the **audit log** (``obs.audit``) — a hash-chained, erasable record of what
  a tool did, with the content digests;
- the **state ledger** (``continuity.state_store``) — what is true of this
  host now, since when, and why, with supersession.

Writing to one and forgetting the other is the failure mode this module
exists to prevent, and the two are joined on ``request_id`` — never on an
event sequence number, which is not unique under a concurrent append and
would silently point a join at the wrong record.

Neither write is allowed to break the change it describes: a full disk must
not turn a successful config save into a failed one. Both halves fail soft
and log. The one thing that does raise is a missing ``reason`` or ``actor``,
because that is a programming error at the call site and there is no correct
value to substitute — see ``state_store``'s module docstring on why a
fabricated reason is worse than none.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("halbert.continuity.provenance")

__all__ = [
    "content_digest",
    "record_file_change",
    "record_file_mode_change",
    "FILE_CONTENT_PREDICATE",
    "FILE_MODE_PREDICATE",
    "normalise_mode",
    "DIGEST_UNREADABLE",
    "DIGEST_ABSENT",
    "unreadable_digest",
    "forget_request",
    "ERASURE_LIMITS",
]

#: Predicate under which a file's current content digest is held.
FILE_CONTENT_PREDICATE = "content_sha256"

#: Recorded as a file's digest when the write succeeded but the content could
#: not be read back -- a privileged file written through pkexec and read by an
#: unprivileged process. Distinct from any real digest (a sha256 is 64 hex
#: characters) so it can never be mistaken for one.
#:
#: Always qualified per write by :func:`unreadable_digest`. A bare constant
#: collided with itself: two consecutive unreadable writes produced the same
#: object, ``record_state`` took its unchanged-value no-op branch, and the
#: second write's reason was discarded on the rule that nothing had changed --
#: when in truth we had simply failed to look twice.
DIGEST_UNREADABLE = "unreadable"


def unreadable_digest(request_id: str) -> str:
    """A distinct unreadable marker per write, so two never collide."""
    return f"{DIGEST_UNREADABLE}:{request_id}" if request_id else DIGEST_UNREADABLE

#: Recorded as a file's digest when the file is gone. Without it the ledger
#: keeps asserting the last content as *current* for a path that no longer
#: exists, and answers "why is this configured this way" about a file nobody
#: can open.
DIGEST_ABSENT = "absent"

#: Predicate for a file's permission bits, as an octal string ("0644").
#:
#: A separate predicate, not a second use of the content one. A chmod does
#: not change content, so routing it through :func:`record_file_change` would
#: find the content digest unchanged, take ``record_state``'s no-op branch,
#: and discard the ledger row *and its reason* while the audit half still
#: landed. A test asserting "a record exists" would pass with half the
#: contract missing.
FILE_MODE_PREDICATE = "mode_octal"


def normalise_mode(mode: object) -> str:
    """One notation for permission bits: four octal digits, e.g. "0644".

    The write path had `"600"` (the string from a proposal) and the rollback
    path had `oct(0o644)` -> `"0o644"`, so the ledger held two spellings of
    the same concept and any comparison between them reported a permission
    change that never happened.
    """
    if isinstance(mode, int):
        return format(mode & 0o7777, "04o")
    text = str(mode).strip()
    if text.startswith(("0o", "0O")):
        text = text[2:]
    try:
        return format(int(text, 8) & 0o7777, "04o")
    except ValueError:
        return text


def content_digest(text: Optional[str]) -> Optional[str]:
    """SHA-256 of file content, or None when there was no file.

    The digest is what gets recorded, not the content: a record should be
    able to say *what changed* without becoming a second copy of the data
    that ``EventLog.erase`` would then have to reach.
    """
    if text is None:
        return None
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def record_file_change(
    *,
    path: str,
    reason: str,
    actor: str,
    request_id: str,
    tool: str,
    before_text: Optional[str] = None,
    after_text: Optional[str] = None,
    mode: str = "apply",
    ok: bool = True,
    summary: str = "",
    thread_id: Optional[str] = None,
    store: Any = None,
) -> None:
    """Record one file change in the audit log and the state ledger.

    Args:
        path: the file that changed.
        reason: **why**, from the turn that caused it — a human utterance, a
            deterministic rule that names itself, or ``UNRECORDED``. A model
            may state its own reason *for the write it is making now*; what
            is forbidden is inventing one for a write that already happened.
        actor: **who** — ``ACTOR_USER``, ``ACTOR_AGENT``, ``ACTOR_SYSTEM``.
        request_id: the join key between the two planes.
        tool: the mechanism, for the audit record and the ledger's ``source``.
        before_text/after_text: content before and after, used only to
            compute digests.
        store: an open ``StateStore`` to use instead of the default one.
            The caller keeps ownership of anything it passes.

    Raises:
        ValueError: if ``reason`` or ``actor`` is empty.
    """
    from .state_store import StateStore, default_state_db_path, _require

    reason = _require(reason, "reason")
    actor = _require(actor, "actor")

    before_sha = content_digest(before_text)
    after_sha = content_digest(after_text)

    # --- audit plane -------------------------------------------------
    try:
        from ..obs.audit import write_audit

        write_audit(
            tool=tool,
            mode=mode,
            request_id=request_id,
            ok=ok,
            summary=summary or f"{mode} {path}",
            reason=reason,
            actor=actor,
            before_sha256=before_sha,
            after_sha256=after_sha,
            path=path,
        )
    except Exception as e:  # pragma: no cover - write_audit already swallows
        logger.warning(f"audit record for {path} could not be written: {e}")

    # --- ledger plane ------------------------------------------------
    # Only a real apply changes what is true. A dry run is a thing the tool
    # did (audited), not a thing that became true (not recorded).
    if mode != "apply" or not ok:
        return
    if after_sha is None:
        # The write succeeded but we could not read back what landed -- a
        # root-owned config saved through pkexec, say. Recording nothing
        # would leave the ledger asserting the OLD digest as current, which
        # is worse than admitting the gap: a later drift check would then
        # report a change nobody made. Record the fact with an explicit
        # unknown, and say so out loud rather than returning in silence.
        logger.warning(
            "content of %s could not be read back after the write; recording "
            "its digest as unknown rather than leaving a stale one current",
            path,
        )
        after_sha = unreadable_digest(request_id)
    owned = None
    try:
        target = store
        if target is None:
            owned = StateStore(db_path=str(default_state_db_path()))
            target = owned
        target.record_state(
            f"file:{path}", FILE_CONTENT_PREDICATE, after_sha, tool,
            reason=reason, actor=actor, request_id=request_id,
            thread_id=thread_id,
        )
    except Exception as e:
        logger.warning(f"state ledger row for {path} could not be written: {e}")
    finally:
        if owned is not None:
            owned.close()


def record_file_mode_change(
    *,
    path: str,
    mode_octal: str,
    reason: str,
    actor: str,
    request_id: str,
    tool: str,
    before_mode: Optional[str] = None,
    ok: bool = True,
    summary: str = "",
    thread_id: Optional[str] = None,
    store: Any = None,
    strict: bool = False,
) -> None:
    """Record a permission change on both planes.

    The mode's own predicate (:data:`FILE_MODE_PREDICATE`) rather than the
    content digest, for the reason given on that constant.

    Args:
        strict: let a failure of the **audit** half propagate instead of
            being logged. Default False, because recording must not break
            the change it describes. An approved chmod passes True: a
            privileged change that cannot be accounted for must not stand,
            and its caller rolls the mode back (R06-F4). The ledger half
            stays fail-soft either way -- it is not part of that contract,
            and losing it must not undo a mode the caller was told held.

    Raises:
        ValueError: if ``reason`` or ``actor`` is empty.
        Exception: from the audit write, when ``strict`` is set.
    """
    from .state_store import StateStore, default_state_db_path, _require

    reason = _require(reason, "reason")
    actor = _require(actor, "actor")
    mode_octal = normalise_mode(mode_octal)
    if before_mode is not None:
        before_mode = normalise_mode(before_mode)

    try:
        from ..obs.audit import write_audit

        write_audit(
            tool=tool,
            mode="apply",
            request_id=request_id,
            ok=ok,
            summary=summary or f"chmod {mode_octal} {path}",
            reason=reason,
            actor=actor,
            path=path,
            mode_octal=mode_octal,
            before_mode=before_mode,
            strict=strict,
        )
    except Exception as e:
        if strict:
            raise
        logger.warning(f"audit record for chmod {path} could not be written: {e}")

    if not ok:
        return
    owned = None
    try:
        target = store
        if target is None:
            owned = StateStore(db_path=str(default_state_db_path()))
            target = owned
        target.record_state(
            f"file:{path}", FILE_MODE_PREDICATE, mode_octal, tool,
            reason=reason, actor=actor, request_id=request_id,
            thread_id=thread_id,
        )
    except Exception as e:
        logger.warning(f"state ledger row for chmod {path} could not be written: {e}")
    finally:
        if owned is not None:
            owned.close()


#: What erasure does not reach. Stated positively next to what it does, per
#: INTEG-05's rule against a badge that claims more than it can show.
ERASURE_LIMITS = (
    "This removes the recorded reason from the change ledger and the content "
    "of the matching audit records, and rewrites the ledger's own pages so the "
    "old text is not left in the file (secure_delete, then a WAL checkpoint). "
    "It does NOT reach: an approval's own copy of the reason, kept in "
    "findings.db under proposals.execution_result; conversation messages, "
    "which are redacted separately; Haloysius memory_v2's plaintext store; "
    "blocks of a rewritten log shard the filesystem has not yet reused; or any "
    "backup, snapshot or replica taken before now."
)


def forget_request(request_id: str, *, actor: str = "forget",
                   reproject: bool = True) -> Dict[str, Any]:
    """Remove one request's recorded words from the ledger and the audit log.

    Not from *every* plane that holds them -- see :data:`ERASURE_LIMITS` for
    the ones it cannot reach. Saying "everywhere" when it is two of several
    is the overclaim this project keeps having to correct.

    Keyed on ``request_id`` because that is the join between the planes, and
    never on an event sequence number, which is not unique under a concurrent
    append.

    What this removes is the **words** — a reason is where a human utterance
    lives. The facts and their timeline stay: what was true and when is not
    the thing being forgotten, and deleting those rows would make the history
    lie about itself.

    Returns a per-plane report. Nothing raises: forgetting must not fail
    loudly at the one moment a person is asking for privacy, and a partial
    result is still worth reporting honestly. ``complete`` is False when a
    plane could not be reached, so a caller can say so rather than showing a
    clean tick over a job half done.
    """
    from .state_store import StateStore, default_state_db_path

    report: Dict[str, Any] = {
        "request_id": request_id,
        "ledger_rows": 0,
        "audit_records": 0,
        "vault_rebuilt": False,
        "errors": [],
        "limits": ERASURE_LIMITS,
    }
    if not request_id:
        report["errors"].append("no request_id given")
        report["complete"] = False
        return report

    # Both planes raise on a real failure now, so an error here is a genuine
    # "the words are still there" and lands in report["errors"], which is what
    # `complete` is computed from.
    store = None
    try:
        store = StateStore(db_path=str(default_state_db_path()))
        report["ledger_rows"] = store.redact_request(request_id, actor=actor)
    except Exception as e:
        logger.warning(f"forget_request({request_id}): ledger: {e}")
        report["errors"].append(f"ledger: {e}")
    finally:
        if store is not None:
            store.close()

    try:
        from ..obs.audit import erase_audit_by_request

        report["audit_records"] = erase_audit_by_request(request_id)
    except Exception as e:
        logger.warning(f"forget_request({request_id}): audit: {e}")
        report["errors"].append(f"audit: {e}")

    if reproject:
        try:
            from .vault import VaultProjector, vault_root

            # Only reproject a vault that already exists. Rebuilding one into
            # being during a forget would write fresh plaintext copies of
            # every OTHER reason to disk -- publishing on the way to erasing,
            # which is the opposite of what was asked for.
            notes = vault_root() / "notes"
            if notes.exists() and any(notes.glob("*.md")):
                VaultProjector().rebuild()
                report["vault_rebuilt"] = True
            else:
                report["vault_rebuilt"] = False
        except Exception as e:
            logger.warning(f"forget_request({request_id}): vault: {e}")
            report["errors"].append(f"vault: {e}")

    report["complete"] = not report["errors"]
    return report
