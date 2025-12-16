"""
Knowledge module for persistent self-understanding.

Implements the Genesis vision: "The system's data is its biography,
its configuration is its physiology."
"""
from .self_knowledge import (
    SelfKnowledge,
    KnowledgeEntry,
    KnowledgeType,
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
    'get_self_knowledge',
    'bootstrap_identity',
    'bootstrap_from_profile',
    'parse_config_comments',
    'learn_from_config',
]
