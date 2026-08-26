# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Memory management for Halbert (Phase 3 M2)

Provides memory storage, retrieval, and context building for LLM.
Phase 36: Adds HybridMemorySystem for unified memory interface.
"""

from .retrieval import MemoryRetrieval
from .writer import MemoryWriter
from .hybrid import (
    HybridMemorySystem,
    Memory,
    MemoryType,
    get_hybrid_memory,
)

__all__ = [
    'MemoryRetrieval',
    'MemoryWriter',
    # Phase 36: Hybrid Memory
    'HybridMemorySystem',
    'Memory',
    'MemoryType',
    'get_hybrid_memory',
]
