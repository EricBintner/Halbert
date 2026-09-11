# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
""""What do you remember about me" -- answered from the store, not the model.

Deterministic by construction: it reads the same rows the Settings list shows
and renders them. No model, no ranking, no search -- the same discipline
``recall_memory`` applies to the change ledger.

The question is one a model is unusually bad at. Asked what it remembers, it
will round a list of three up to a plausible four, and an *invented* memory of
a person is the worst output this whole mechanism could produce. So the answer
text ends by saying the list is complete, in the returned string rather than
only in the schema -- the schema is read before the call, the string is what
is present when the reply is composed.

Forgetting is **not** available here. "Forget that" in conversation is staged
and confirmed on a surface, never executed from a reply: a model that can
erase a person's memories on its own reading of a sentence is a worse failure
than one that cannot erase them at all.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger("halbert.tools.about_you")

__all__ = ["WHAT_I_REMEMBER_SCHEMA", "what_i_remember"]

WHAT_I_REMEMBER_SCHEMA = {
    "name": "what_i_remember",
    "description": (
        "List everything recorded about the user — their interests and "
        "preferences, how each was learned, and when. "
        "Call this whenever they ask what you know or remember about them. "
        "The answer is the complete list: never add to it, never infer a "
        "further preference from it, and never describe them beyond it. "
        "This cannot forget anything; if they ask you to forget something, "
        "tell them it is in Settings under 'What I remember about you'."
    ),
    "parameters": {"type": "object", "properties": {}},
}


async def what_i_remember(args: Dict[str, Any]) -> str:
    """The stored rows, rendered. Never raises."""
    try:
        from ..continuity.about_you import list_remembered, remembered_lines
        from ..integrations.cognition_wiring import get_persona_memory_store

        rows = list_remembered(get_persona_memory_store())
        return remembered_lines(rows)
    except Exception:
        logger.warning("what_i_remember failed", exc_info=True)
        return (
            "I could not read what I have recorded about you just now. That "
            "means the store could not be reached — not that there is nothing "
            "recorded. Settings → 'What I remember about you' is the reliable view."
        )
