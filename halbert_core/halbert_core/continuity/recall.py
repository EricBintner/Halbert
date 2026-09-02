# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""One read of the change ledger, shared by the API route and the agent tool.

Both surfaces answer the same question — *why is this the way it is* — and
must answer it identically. Duplicating the query is how they drift.

Nothing here ranks, guesses or calls a model. A subject match is a
case-folded substring test over recorded subjects, so the answer to "which
of these did you mean" is a list, never a best guess. Authority is not
similarity: this module resolves or abstains.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from .provenance import FILE_CONTENT_PREDICATE
from .state_store import StateStore, default_state_db_path

logger = logging.getLogger("halbert.continuity.recall")

__all__ = [
    "subject_for_path",
    "recall_state",
    "predicates_for",
    "matching_subjects",
    "recorded_subjects",
    "LedgerUnavailable",
]


class LedgerUnavailable(RuntimeError):
    """The ledger could not be read.

    Distinct from "nothing recorded" on purpose: a caller that renders a read
    failure as an empty result turns "I could not look" into "there is
    nothing", which is the failure R06-O2 exists to prevent.
    """


def subject_for_path(path: str) -> str:
    """A file's subject key. The one place this shape is written down."""
    return f"file:{path}"


def _open(store: Any) -> Tuple[Any, Optional[StateStore]]:
    """Return (store_to_use, store_we_own). Never cache one: the path is
    resolved at call time so HALBERT_DATA_DIR is honoured per call."""
    if store is not None:
        return store, None
    owned = StateStore(db_path=str(default_state_db_path()))
    return owned, owned


def recall_state(
    *,
    subject: Optional[str] = None,
    path: Optional[str] = None,
    predicate: str = FILE_CONTENT_PREDICATE,
    include_history: bool = False,
    history_limit: int = 10,
    store: Any = None,
) -> Dict[str, Any]:
    """What is true, since when, who changed it, and why.

    Returns ``{subject, predicate, found, current, superseded, history}``.
    ``found`` is False when the ledger holds no record for the key — which
    means *nothing was recorded*, never *nothing changed*.

    Raises:
        LedgerUnavailable: the store could not be read.
    """
    if path and not subject:
        subject = subject_for_path(path)
    if not subject:
        return {"subject": "", "predicate": predicate, "found": False,
                "current": None, "superseded": None, "history": []}

    target, owned = _open(store)
    try:
        answer = target.why(subject, predicate)
        history: List[Dict[str, Any]] = []
        if include_history:
            rows = target.state_history(subject, predicate)
            history = [t.to_dict() for t in rows[-history_limit:]][::-1]
    except Exception as e:
        logger.warning(f"recall_state({subject}, {predicate}) failed: {e}")
        raise LedgerUnavailable(str(e)) from e
    finally:
        if owned is not None:
            owned.close()

    return {
        "subject": subject,
        "predicate": predicate,
        "found": answer.found,
        "current": answer.current.to_dict() if answer.current else None,
        "superseded": answer.superseded.to_dict() if answer.superseded else None,
        "history": history,
    }


def predicates_for(subject: str, *, store: Any = None) -> List[str]:
    """Which predicates this subject actually holds right now.

    Subjects are heterogeneous — ``file:`` holds a content digest,
    ``service:`` a status, ``system`` a load figure — so a default predicate
    that misses would otherwise abstain on a subject the ledger plainly
    knows about. That is technically honest and practically a lie.
    """
    target, owned = _open(store)
    try:
        return sorted({t.predicate for t in target.current_state(subject=subject)})
    except Exception as e:
        logger.warning(f"predicates_for({subject}) failed: {e}")
        raise LedgerUnavailable(str(e)) from e
    finally:
        if owned is not None:
            owned.close()


def recorded_subjects(*, limit: int = 12, store: Any = None) -> List[str]:
    """Subjects the ledger currently holds anything for."""
    target, owned = _open(store)
    try:
        return sorted({t.subject for t in target.current_state()})[:limit]
    except Exception as e:
        logger.warning(f"recorded_subjects() failed: {e}")
        raise LedgerUnavailable(str(e)) from e
    finally:
        if owned is not None:
            owned.close()


def matching_subjects(query: str, *, limit: int = 12,
                      store: Any = None) -> List[Tuple[str, str]]:
    """Recorded (subject, predicate) pairs whose subject contains ``query``.

    A case-folded substring test, deterministic and unranked. This is a
    disambiguation aid, not a search: it proposes candidates for a human or
    a model to choose between, and never picks one.
    """
    needle = (query or "").strip().casefold()
    if not needle:
        return []
    target, owned = _open(store)
    try:
        rows = target.current_state()
    except Exception as e:
        logger.warning(f"matching_subjects({query}) failed: {e}")
        raise LedgerUnavailable(str(e)) from e
    finally:
        if owned is not None:
            owned.close()
    seen: List[Tuple[str, str]] = []
    for t in rows:
        if needle in t.subject.casefold() and (t.subject, t.predicate) not in seen:
            seen.append((t.subject, t.predicate))
        if len(seen) >= limit:
            break
    return seen
