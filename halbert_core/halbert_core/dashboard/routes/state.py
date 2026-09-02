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

from ...continuity.provenance import FILE_CONTENT_PREDICATE
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
    if path and not subject:
        subject = f"file:{path}"
    if not subject:
        return WhyResponse(subject="", predicate=predicate, found=False)

    store = _store()
    try:
        answer = store.why(subject, predicate)
        return WhyResponse(**answer.to_dict(), found=answer.found)
    except Exception as e:
        logger.warning(f"why({subject}, {predicate}) failed: {e}")
        return WhyResponse(subject=subject, predicate=predicate, found=False)
    finally:
        store.close()


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
