# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Read surface for the machine-state ledger — "why is X the way it is".

LEDGER-1's definition of done asks the ledger to answer, for any config the
machine has touched: what is it now, what was it before, who changed it, when,
and why. ``StateStore.why`` returns exactly that pair; these routes expose it.

The ledger resolves or abstains. When a key is unknown the response says so
rather than offering a near miss: authority is not similarity, and a plausible
wrong answer about a config change is worse than "I have no record of that".
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from ...continuity.provenance import FILE_CONTENT_PREDICATE, forget_request
from ...continuity.recall import LedgerUnavailable, recall_state
from ...continuity.state_store import StateStore, default_state_db_path

logger = logging.getLogger(__name__)

router = APIRouter()


class WhyResponse(BaseModel):
    """What the ledger knows about one (subject, predicate)."""

    subject: str
    predicate: str
    #: False when the ledger holds no record. The caller must not treat an
    #: empty answer as "nothing changed" -- it means "not recorded here".
    found: bool
    current: Optional[Dict[str, Any]] = None
    superseded: Optional[Dict[str, Any]] = None


def _store() -> StateStore:
    return StateStore(db_path=str(default_state_db_path()))


@router.get("/why", response_model=WhyResponse)
async def why(
    subject: Optional[str] = Query(None, description="e.g. service:nginx"),
    predicate: str = Query(FILE_CONTENT_PREDICATE),
    path: Optional[str] = Query(None, description="a file, as a shorthand for subject"),
) -> WhyResponse:
    """Why is this the way it is?

    Pass either ``path`` (a file, the common case) or an explicit ``subject``.
    Returns the open triple with the value it replaced, so a caller has
    before and after without a second request.
    """
    try:
        result = recall_state(subject=subject, path=path, predicate=predicate)
    except LedgerUnavailable as e:
        logger.warning(f"why({subject or path}, {predicate}) failed: {e}")
        return WhyResponse(subject=subject or "", predicate=predicate, found=False)
    # ``result`` already carries ``found``; passing it again alongside
    # ``**result`` would raise TypeError, which this route's own except
    # would then swallow into found=False for every request.
    return WhyResponse(
        subject=result["subject"], predicate=result["predicate"],
        found=result["found"], current=result["current"],
        superseded=result["superseded"],
    )


@router.get("/history")
async def history(
    subject: str = Query(...),
    predicate: str = Query(FILE_CONTENT_PREDICATE),
) -> List[Dict[str, Any]]:
    """Every value this key has held, oldest first, each with its reason."""
    store = _store()
    try:
        return [t.to_dict() for t in store.state_history(subject, predicate)]
    except Exception as e:
        logger.warning(f"history({subject}, {predicate}) failed: {e}")
        return []
    finally:
        store.close()


@router.get("/by-request")
async def by_request(request_id: str = Query(...)) -> List[Dict[str, Any]]:
    """Every triple written under one request.

    ``request_id`` is the join key to the audit log, and never an event
    sequence number: a seq is not unique under a concurrent append, so a
    seq-keyed join can silently point at the wrong record.
    """
    store = _store()
    try:
        return [t.to_dict() for t in store.by_request(request_id)]
    except Exception as e:
        logger.warning(f"by_request({request_id}) failed: {e}")
        return []
    finally:
        store.close()


class ForgetResponse(BaseModel):
    """What forgetting actually reached, and what it did not."""

    request_id: str
    ledger_rows: int
    audit_records: int
    vault_rebuilt: bool
    complete: bool
    #: Stated explicitly rather than implied. INTEG-05's rule: a surface must
    #: not claim more than it can show.
    limits: str
    errors: List[str] = []


@router.post("/forget", response_model=ForgetResponse)
async def forget(request_id: str = Query(..., description="The join key across both planes")) -> ForgetResponse:
    """Remove one request's recorded words from the ledger and the audit log.

    A POST, not a GET: this is destructive and must not be reachable by a
    prefetch or a link crawler.

    It removes the *words*. The facts and their timeline stay — what was true
    and when is not the thing being forgotten.
    """
    report = forget_request(request_id)
    return ForgetResponse(
        request_id=report["request_id"],
        ledger_rows=report["ledger_rows"],
        audit_records=report["audit_records"],
        vault_rebuilt=report["vault_rebuilt"],
        complete=report["complete"],
        limits=report["limits"],
        errors=report["errors"],
    )
