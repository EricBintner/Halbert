"""
Knowledge module for persistent self-understanding.
"""
from .self_knowledge import (
    SelfKnowledge,
    KnowledgeEntry,
    KnowledgeType,
    get_self_knowledge,
    bootstrap_identity,
)

__all__ = [
    'SelfKnowledge',
    'KnowledgeEntry', 
    'KnowledgeType',
    'get_self_knowledge',
    'bootstrap_identity',
]
