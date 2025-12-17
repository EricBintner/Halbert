"""
Knowledge module for persistent self-understanding.

Implements the Genesis vision: "The system's data is its biography,
its configuration is its physiology."

Sprint 1: Mem0-style memory operations (ADD/UPDATE/DELETE/NOOP)
Sprint 2: Graph-based relationship modeling for system components
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
from .graph import (
    KnowledgeGraph,
    KnowledgeRelation,
    RelationType,
    get_knowledge_graph,
    discover_relations_from_profile,
)
from .reflection import (
    SelfReflector,
    ReflectionResult,
    RetrievalDecision,
    ConfidenceLevel,
    RetrievedContext,
    ReflectionToken,
    CRAGAction,
    get_reflector,
    reflect_before_answer,
)
from .hierarchical import (
    HierarchicalKnowledge,
    HierarchicalDoc,
    DocumentTier,
    get_hierarchical_knowledge,
)

__all__ = [
    # Self-Knowledge (Sprint 1)
    'SelfKnowledge',
    'KnowledgeEntry', 
    'KnowledgeType',
    'MemoryOperation',
    'get_self_knowledge',
    'bootstrap_identity',
    'bootstrap_from_profile',
    'parse_config_comments',
    'learn_from_config',
    # Knowledge Graph (Sprint 2)
    'KnowledgeGraph',
    'KnowledgeRelation',
    'RelationType',
    'get_knowledge_graph',
    'discover_relations_from_profile',
    # Self-Reflection (Sprint 3) - Enhanced with Self-RAG + CRAG
    'SelfReflector',
    'ReflectionResult',
    'RetrievalDecision',
    'ConfidenceLevel',
    'RetrievedContext',
    'ReflectionToken',
    'CRAGAction',
    'get_reflector',
    'reflect_before_answer',
    # Hierarchical Knowledge (Sprint 4)
    'HierarchicalKnowledge',
    'HierarchicalDoc',
    'DocumentTier',
    'get_hierarchical_knowledge',
]
