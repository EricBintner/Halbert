"""
Knowledge module for persistent self-understanding.

Implements the Genesis vision: "The system's data is its biography,
its configuration is its physiology."

Sprint 1 Enhancement: Mem0-style memory operations (ADD/UPDATE/DELETE/NOOP)
for intelligent duplicate/contradiction detection.
"""
from .self_knowledge import (
    SelfKnowledge,
    KnowledgeEntry,
    KnowledgeType,
    MemoryOperation,
    get_self_knowledge,
    bootstrap_identity,
    bootstrap_from_profile,
    parse_config_comments,
    learn_from_config,
)

__all__ = [
    'SelfKnowledge',
    'KnowledgeEntry', 
    'KnowledgeType',
    'MemoryOperation',
    'get_self_knowledge',
    'bootstrap_identity',
    'bootstrap_from_profile',
    'parse_config_comments',
    'learn_from_config',
]
