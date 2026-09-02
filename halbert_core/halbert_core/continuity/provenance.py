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
from typing import Any, Optional

logger = logging.getLogger("halbert.continuity.provenance")

__all__ = ["content_digest", "record_file_change", "FILE_CONTENT_PREDICATE"]

#: Predicate under which a file's current content digest is held.
FILE_CONTENT_PREDICATE = "content_sha256"


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
    if mode != "apply" or not ok or after_sha is None:
        return
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
