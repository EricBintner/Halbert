# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Memory for Halbert.

Conversation memory belongs to the thread store (``agents/conversation_sqlite.py``);
identity and semantic memory belong to Haloysius ``memory_v2``; durable machine state
belongs to the state ledger, ``continuity.state_store.StateStore`` (``MEM-02``; the
trackers in ``integrations/state_trackers.py`` write to it). What
remains here is the ChromaDB-backed HybridMemorySystem, which is eval- and browser-only
(``documentation/design/the-being.md`` §9) and is deliberately not on the agent path.

The file-backed MemoryWriter/MemoryRetrieval pair was removed 2026-08-26: the writer
imposed no schema and the reader scored only on ``text``/``summary``, so nothing ever
written could be read back. See
``documentation/research/CONTINUITY-MECHANISM-AUDIT-2026-08-26.md`` finding F1.
"""

from .hybrid import (
    HybridMemorySystem,
    Memory,
    MemoryType,
    get_hybrid_memory,
)

__all__ = [
    'HybridMemorySystem',
    'Memory',
    'MemoryType',
    'get_hybrid_memory',
]
