# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Secure content detector — determines if a turn's context has secrets.

Two-part detector (OR):

1. **Provenance:** set ``secure=True`` when any assembled chunk came from
   the unredacted ``host/`` scope.  Cheap, catches the common case.

2. **Content:** ``redact_text(ctx) != ctx`` → ``secure=True``.  Reuses the
   redactor as a detector — if it would have changed anything, the context
   holds something it considers a credential.  Provenance-independent,
   deterministic, catches secrets that arrived via terminal output,
   scanner results, file-read tools, or the user pasting a config.

Fail toward ``secure=True`` including on exceptions.  A false positive
costs a local-model answer; a false negative ships a secret to a cloud
vendor.
"""
from __future__ import annotations

import logging
from typing import Any, List, Optional

from ..ingestion.redaction import redact_text

logger = logging.getLogger(__name__)


def detect_secure_content(
    context_text: str,
    *,
    chunk_sources: Optional[List[str]] = None,
) -> bool:
    """Return True if the context appears to contain secure content.

    Args:
        context_text: The assembled context text that would be sent to the
            LLM.  This is the full prompt context, not just the user query.
        chunk_sources: Optional list of source identifiers for the chunks
            in the context.  If any source starts with ``host/``, the
            provenance check fires.

    Returns:
        True if secure content is detected (force local model).
        False if the context appears safe for cloud models.

    Fails toward True on exceptions — a false positive costs a
    local-model answer; a false negative ships a secret to a cloud vendor.
    """
    # Part 1: provenance — chunks from the host/ scope
    if chunk_sources:
        for source in chunk_sources:
            if isinstance(source, str) and source.startswith("host/"):
                return True

    # Part 2: content — redact_text as a detector
    if context_text:
        try:
            if redact_text(context_text) != context_text:
                return True
        except Exception as e:
            # Fail toward secure: if the detector itself breaks, assume
            # the worst rather than shipping potentially-sensitive content
            # to a cloud vendor.
            logger.warning(
                "Secure content detector raised %s; failing toward secure=True", e
            )
            return True

    return False
