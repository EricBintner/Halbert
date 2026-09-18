# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The operator's own rationale for one thing on a surface — "why is this here".

Distinct from ``routes/state.py``, which answers the same words from the
*change ledger*: that one reports what the machine recorded when a config
changed. This one holds what a person wrote down about an item they were
looking at — a GPU, an interface, a service — so the next reader (them, six
months later) gets the reason rather than re-deriving it.

The discipline is state.py's, and it is the reason this module exists as its
own file rather than a pair of handlers bolted onto a settings route:

*Resolve or abstain.* ``found`` is False only when the store was read and
holds nothing for that id. A store that could not be read at all is a 503,
never a 200 that reads as "nothing recorded" — conflating the two tells an
operator their note is gone when it is merely unreachable, and the reasonable
next thing they do is write it again over the top of the file that still has
it.

*A write that did not land is not a save.* ``saved`` is True only after the
bytes reached the disk. ``SelfKnowledge.add`` raises when they did not.

*Exact keys, never similar ones.* Notes are fetched by exact id. The store
also offers ``get_by_subject`` (a substring match, so ``network:eth0`` would
return ``network:eth0.100``'s note) and ``smart_add`` (which treats two items
with the same name as duplicates and silently keeps only the first — two
identical GPUs lose the second note). Neither is used here. Authority is not
similarity.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ...knowledge.self_knowledge import (
    KnowledgeEntry,
    KnowledgeType,
    KnowledgeUnavailable,
    SelfKnowledge,
    get_self_knowledge,
)

logger = logging.getLogger(__name__)

router = APIRouter()

#: Every note this surface writes is keyed ``rationale:<item_id>`` and tagged
#: ``rationale``. The prefix is what separates an operator's note from the
#: ``config:*`` rationales the profile bootstrap writes into the same store,
#: which are the machine's own inferences and not a person's words.
_ID_PREFIX = "rationale:"
_TAG = "rationale"

#: Said the same way on every path that could not reach the store: what
#: failed, what it means, what to do.
_UNREADABLE = (
    "The rationale store could not be read, so this cannot be answered. That "
    "is a failure to look, not an absence of notes — anything recorded is "
    "still on disk. Check the knowledge store file, then try again."
)
_UNWRITABLE = (
    "The rationale store could not be written, so this was not recorded. "
    "Nothing already recorded was changed. Check that the knowledge store "
    "file exists and is writable, then try again."
)


class SaveRationaleRequest(BaseModel):
    """One item, and what a person wants remembered about it."""

    item_id: str
    item_name: str
    item_type: str
    why: str


class SaveRationaleResponse(BaseModel):
    """What was recorded. ``saved`` is only ever True after a durable write."""

    item_id: str
    saved: bool
    updated_at: str


class RationaleResponse(BaseModel):
    """What the store holds for one item."""

    item_id: str
    #: False means the store was read and holds no note for this id. It never
    #: means "the store could not be read" — that answer is a 503.
    found: bool
    why: Optional[str] = None
    item_name: Optional[str] = None
    item_type: Optional[str] = None
    updated_at: Optional[str] = None


class RationaleSummary(BaseModel):
    """One note, as it appears in a by-type listing."""

    why: str
    item_name: str
    updated_at: str


class RationalesByTypeResponse(BaseModel):
    """Every note recorded against one kind of item, keyed by item id.

    A caller renders a whole list of items in one pass, so it asks once for
    the type rather than once per row.
    """

    item_type: str
    count: int
    rationales: Dict[str, RationaleSummary]


class DeleteRationaleResponse(BaseModel):
    """``deleted`` is False when there was nothing to delete.

    That is not an error and not a 404: removing a note that is already gone
    is the outcome the caller asked for, so a second DELETE is a no-op.
    """

    item_id: str
    deleted: bool


def _note_id(item_id: str) -> str:
    """The one place the key shape is written down."""
    return f"{_ID_PREFIX}{item_id}"


def _store() -> SelfKnowledge:
    """The knowledge store, or raise :class:`KnowledgeUnavailable`.

    Resolved per request, never cached here: the store resolves its path at
    construction from ``HALBERT_DATA_DIR``, and a module-level handle would
    outlive the answer to that question.

    ``readable`` is checked explicitly. The store loads once per process, so
    a read failure is not something the next request retries into truth — it
    would answer "nothing recorded" for the life of the process.
    """
    try:
        sk = get_self_knowledge()
    except Exception as e:  # constructing it is itself a read of the disk
        logger.warning(f"rationale store could not be opened: {e}")
        raise KnowledgeUnavailable(str(e)) from e
    if not sk.readable:
        raise KnowledgeUnavailable(sk.load_error or "the store could not be read")
    return sk


def _item_type_of(entry: KnowledgeEntry) -> Optional[str]:
    """The item type a note was filed under.

    It is ``tags[0]`` by construction (``[item_type, "rationale"]``). Read
    positionally rather than as "the tag that is not 'rationale'", so an item
    whose type genuinely *is* ``rationale`` still resolves to itself.
    """
    return entry.tags[0] if entry.tags else None


def _our_notes(sk: SelfKnowledge) -> List[KnowledgeEntry]:
    """Only the notes this surface wrote, never the bootstrap's inferences."""
    return [
        e for e in sk.get_by_type(KnowledgeType.CONFIG_RATIONALE)
        if e.id.startswith(_ID_PREFIX) and _TAG in e.tags
    ]


@router.post("/why", response_model=SaveRationaleResponse)
async def save_rationale(body: SaveRationaleRequest) -> SaveRationaleResponse:
    """Record why this item is the way it is.

    Re-saving the same ``item_id`` replaces the note and moves
    ``updated_at``; the original ``created_at`` is preserved, because when a
    person first wrote something down is a fact about them, not about the
    last edit.
    """
    item_id = body.item_id.strip()
    why = body.why.strip()
    if not item_id:
        raise HTTPException(
            400,
            "No item was named, so there is nothing to record this against. "
            "Send the item's id with the note.",
        )
    if not why:
        raise HTTPException(
            400,
            "The note is empty, so there is nothing to record. An empty note "
            "would be indistinguishable from never having written one. Write "
            "the reason, or delete the note instead.",
        )

    try:
        sk = _store()
    except KnowledgeUnavailable as e:
        logger.warning(f"save_rationale({item_id}) could not read the store: {e}")
        raise HTTPException(503, _UNREADABLE)

    existing = sk.get(_note_id(item_id))
    entry = KnowledgeEntry(
        id=_note_id(item_id),
        type=KnowledgeType.CONFIG_RATIONALE,
        subject=item_id,
        content=body.item_name,
        rationale=why,
        source="user",
        confidence=1.0,
        # Positional: [item_type, "rationale"]. _item_type_of reads it back.
        tags=[body.item_type.strip(), _TAG],
        created_at=existing.created_at if existing else "",
    )
    try:
        # add(), not smart_add(): smart_add compares CONTENT, and content here
        # is the item's display name. Two same-model GPUs would look like a
        # duplicate and the second note would be dropped without a word.
        sk.add(entry)
    except KnowledgeUnavailable as e:
        # 503, not a 200 with saved=true. The whole point of this response is
        # that the operator can stop holding the reason in their head.
        logger.warning(f"save_rationale({item_id}) could not write: {e}")
        raise HTTPException(503, _UNWRITABLE)

    # Read back rather than trusting the object we built: updated_at is
    # stamped inside add() on a replace.
    stored = sk.get(_note_id(item_id))
    return SaveRationaleResponse(
        item_id=item_id,
        saved=True,
        updated_at=(stored or entry).updated_at,
    )


@router.get("/why", response_model=RationaleResponse)
async def get_rationale(
    item_id: str = Query(..., description="the item a note was filed against"),
) -> RationaleResponse:
    """What was written down about this item, if anything.

    Looked up by exact id. ``get_by_subject`` would have matched by
    substring, which is how ``network:eth0`` gets handed ``network:eth0.100``'s
    reasoning and never knows.
    """
    try:
        sk = _store()
    except KnowledgeUnavailable as e:
        logger.warning(f"get_rationale({item_id}) could not read the store: {e}")
        raise HTTPException(503, _UNREADABLE)

    entry = sk.get(_note_id(item_id))
    if entry is None:
        return RationaleResponse(item_id=item_id, found=False)
    return RationaleResponse(
        item_id=item_id,
        found=True,
        why=entry.rationale,
        item_name=entry.content,
        item_type=_item_type_of(entry),
        updated_at=entry.updated_at,
    )


@router.get("/why/by-type", response_model=RationalesByTypeResponse)
async def get_rationales_by_type(
    item_type: str = Query(..., description="e.g. gpu, network, service"),
) -> RationalesByTypeResponse:
    """Every note filed under one kind of item, keyed by item id.

    ``count`` is the number of notes returned, not the number of items of
    that type the machine has — this store knows only what someone wrote
    about.
    """
    try:
        sk = _store()
    except KnowledgeUnavailable as e:
        logger.warning(f"get_rationales_by_type({item_type}) could not read the store: {e}")
        raise HTTPException(503, _UNREADABLE)

    wanted = item_type.strip()
    rationales: Dict[str, RationaleSummary] = {}
    for entry in _our_notes(sk):
        if _item_type_of(entry) != wanted:
            continue
        rationales[entry.subject] = RationaleSummary(
            why=entry.rationale or "",
            item_name=entry.content,
            updated_at=entry.updated_at,
        )

    return RationalesByTypeResponse(
        item_type=wanted, count=len(rationales), rationales=rationales,
    )


@router.delete("/why", response_model=DeleteRationaleResponse)
async def delete_rationale(
    item_id: str = Query(..., description="the item whose note to remove"),
) -> DeleteRationaleResponse:
    """Remove the note for this item.

    Idempotent: deleting a note that is not there returns ``deleted: false``
    and a 200. A failure to *reach* the store is still a 503 — an operator
    who asked for a note to be gone must not be told it is when it is not.
    """
    try:
        sk = _store()
    except KnowledgeUnavailable as e:
        logger.warning(f"delete_rationale({item_id}) could not read the store: {e}")
        raise HTTPException(503, _UNREADABLE)

    try:
        deleted = sk.delete(_note_id(item_id))
    except KnowledgeUnavailable as e:
        logger.warning(f"delete_rationale({item_id}) could not write: {e}")
        raise HTTPException(503, _UNWRITABLE)

    return DeleteRationaleResponse(item_id=item_id, deleted=deleted)
