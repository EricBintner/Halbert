# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Context module for assembling and managing context for LLM calls.

Phase 36: Token budget management and multi-source context assembly.
"""

from .tokens import TokenCounter
from .assembler import ContextAssembler, AssembledContext
from .adapters import (
    RAGServiceAdapter,
    DiscoveryServiceAdapter,
    MemoryServiceAdapter,
    create_wired_context_assembler,
)
from .prioritizer import (
    ContextPrioritizer,
    ContextItem,
    ContextSource,
)
from .cache import (
    ContextCache,
    SemanticCache,
    CacheEntry,
    get_context_cache,
)
from .extra_adapters import (
    SystemIdentityAdapter,
    SelfKnowledgeAdapter,
    TelemetryAdapter,
    SafetyAdapter,
    create_extended_context_assembler,
)

__all__ = [
    'TokenCounter',
    'ContextAssembler',
    'AssembledContext',
    'RAGServiceAdapter',
    'DiscoveryServiceAdapter',
    'MemoryServiceAdapter',
    'create_wired_context_assembler',
    # Prioritizer
    'ContextPrioritizer',
    'ContextItem',
    'ContextSource',
    # Cache
    'ContextCache',
    'SemanticCache',
    'CacheEntry',
    'get_context_cache',
    # Extended adapters (Phase C)
    'SystemIdentityAdapter',
    'SelfKnowledgeAdapter',
    'TelemetryAdapter',
    'SafetyAdapter',
    'create_extended_context_assembler',
]
