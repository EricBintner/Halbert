# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Branch summaries: the two sentences a topic switch leaves behind (A16-G7).

Design §2.3. When the leaf moves from one subject to another, the crossing
mints two rows — one into the thread being left ("this was set aside for
X"), one into the thread being returned to ("Y was explored in between") —
so the transcript can answer *why did we change the share path?* six turns
later. Before this, the switch left a one-turn ephemeral note that stored
nothing (``agents/threads.py::_soft_landing``) and a recall chip carrying
``{thread_id, title, date, status, at}``: a pointer, not a sentence.

Both rows are built here, by template. That is the tiered-sensitivity rule
and FD-3's: never a model where a template suffices. There is nothing here
for a summariser to do — the two facts a crossing produces are the two
titles, and both are already stored.

The writer is ``SqliteConversationStore.move_leaf``, which mints inside its
own transaction: a leaf that moved without a divider, and a divider without
a move, are both records that lie.
"""
from __future__ import annotations

from typing import Any

# The row's brackets are the delimiter, and these titles are untrusted: a
# title is the first line a person typed, a ``new_thread`` argument, or a
# migrated JSON title. ``_fence`` is the neutraliser the sibling system-row
# builders already use -- it substitutes the brackets with their fullwidth
# lookalikes rather than deleting them (a deleted bracket silently rewrites
# a command quoted out of the row), collapses ``<continuity>`` tags to a
# fixpoint, and caps. Importing the private name is deliberate: the audit's
# standing complaint about this tree is that the same sanitiser exists three
# times with three different rule sets, and a fourth copy here would be that
# defect, not a fix for it.
#
# Import direction: ``agents.threads`` imports ``conversation_sqlite`` at
# module level, so this module must never be imported from
# ``conversation_sqlite`` at module level -- ``move_leaf`` imports it inside
# the call, the same way ``append_message`` reaches ``continuity.ownership``.
from ..agents.threads import PREV_TITLE_MAX, _fence

#: ``metadata.kind`` on both rows: what a reader filters on.
BRANCH_SUMMARY_KIND = "branch_summary"

#: ``origin`` on both rows. Separate from ``system`` so the soft-landing
#: reader (``recent_messages``, which selects ``human``/``assistant``) and
#: the boundary walk below can both tell a divider from a turn without
#: decoding JSON for every row in the thread.
BRANCH_ORIGIN = "branch"

#: ``metadata.side`` -- which half of the crossing this row is.
SIDE_DEPARTED = "departed"
SIDE_RETURNED = "returned"

#: What an unnamed subject is called. A thread can be crossed away from
#: before anything has titled it, and "" reads as a bug in the sentence.
UNTITLED = "an untitled subject"


def crossing_key(from_thread: str, to_thread: str, boundary_message_id: Any) -> str:
    """Identity of one edge crossing (design §2.3).

    ``boundary_message_id`` is the last *turn* in the thread being left --
    not the last row, because the last row may be a divider this scheme
    wrote itself. That is what makes the key do double duty:

    - **Crash retry.** The two inserts are in one transaction, but a caller
      that retries a crossing recomputes the same key, finds whichever row
      already landed, and writes only the missing one.
    - **Anti-thrash.** Cross away and back with nobody saying anything in
      between and the boundary has not moved, so the key repeats and
      nothing is written. A topic-switch loop cannot paper a thread with
      dividers, which is design §2.3's "a thread that has turns since its
      last branch-summary entry" stated as an identity instead of a counter
      somebody has to remember to reset.
    """
    return f"{from_thread}->{to_thread}@{boundary_message_id}"


def _title(text: Any) -> str:
    fenced = _fence(text, PREV_TITLE_MAX)
    return fenced or UNTITLED


def build_departure_summary(*, to_title: Any) -> str:
    """The row that lands in the thread being LEFT.

    It names where the conversation went, so a replay of this subject can
    say what interrupted it. It is written with ``context_included=0``: the
    departed thread's own prompt does not need to be told it was departed.
    """
    return f'[This subject was set aside here; the conversation moved to "{_title(to_title)}"]'


def build_return_summary(*, from_title: Any, to_title: Any) -> str:
    """The row that lands in the thread being RETURNED TO.

    This is the sentence the gap is about, and it carries ``context_included=1``:
    without it the reopened thread's history is its last twelve rows and the
    detour is invisible to the model that has to answer for it.
    """
    return (f'[Back on "{_title(to_title)}"; '
            f'"{_title(from_title)}" was explored in between]')
