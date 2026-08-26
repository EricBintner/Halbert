# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Hierarchical Documentation Module

Sprint 4: RAPTOR-style hierarchical document organization.

Implements multi-tier knowledge organization:
- LEAF: Individual facts (CPU model, hostname)
- CLUSTER: Grouped related facts (Hardware summary)
- SUMMARY: High-level overviews (System identity)

This allows retrieval at different abstraction levels based on query needs.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from .self_knowledge import KnowledgeEntry, KnowledgeType, get_self_knowledge

logger = logging.getLogger(__name__)


class DocumentTier(str, Enum):
    """Hierarchical document tiers (RAPTOR-inspired)."""
    LEAF = "leaf"           # Individual facts, most specific
    CLUSTER = "cluster"     # Grouped related facts
    SUMMARY = "summary"     # High-level overview, most abstract


@dataclass
class HierarchicalDoc:
    """
    A document at a specific tier in the hierarchy.
    
    Can reference child documents (for clusters/summaries)
    or source knowledge entries (for leaves).
    """
    id: str
    tier: DocumentTier
    title: str
    content: str
    category: str                           # e.g., "hardware", "identity", "network"
    source_ids: List[str] = field(default_factory=list)  # IDs of source entries/docs
    parent_id: Optional[str] = None         # Parent cluster/summary
    created_at: str = ""
    updated_at: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        now = datetime.now().isoformat()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "tier": self.tier.value,
            "title": self.title,
            "content": self.content,
            "category": self.category,
            "source_ids": self.source_ids,
            "parent_id": self.parent_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'HierarchicalDoc':
        """Create from dictionary."""
        return cls(
            id=data["id"],
            tier=DocumentTier(data["tier"]),
            title=data["title"],
            content=data["content"],
            category=data["category"],
            source_ids=data.get("source_ids", []),
            parent_id=data.get("parent_id"),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            metadata=data.get("metadata", {}),
        )


class HierarchicalKnowledge:
    """
    RAPTOR-style hierarchical knowledge organization.
    
    Organizes knowledge into tiers:
    1. LEAF: Raw facts from self-knowledge
    2. CLUSTER: Grouped facts by category
    3. SUMMARY: High-level system overviews
    
    Enables retrieval at appropriate abstraction level.
    """
    
    # Category definitions for clustering
    CATEGORIES = {
        "identity": {
            "types": [KnowledgeType.IDENTITY],
            "keywords": ["hostname", "os", "kernel", "user", "distribution"],
            "summary_template": "System Identity: {hostname} running {os}"
        },
        "hardware": {
            "types": [KnowledgeType.HARDWARE],
            "keywords": ["cpu", "memory", "disk", "gpu", "storage"],
            "summary_template": "Hardware: {cpu}, {memory} RAM"
        },
        "storage": {
            "types": [KnowledgeType.HARDWARE, KnowledgeType.OBSERVATION],
            "keywords": ["disk", "filesystem", "mount", "bcachefs", "nvme", "ssd"],
            "summary_template": "Storage Configuration: {summary}"
        },
        "network": {
            "types": [KnowledgeType.HARDWARE, KnowledgeType.OBSERVATION],
            "keywords": ["network", "interface", "ip", "dns", "port"],
            "summary_template": "Network: {summary}"
        },
        "config": {
            "types": [KnowledgeType.CONFIG_RATIONALE],
            "keywords": ["config", "setting", "rationale", "choice"],
            "summary_template": "Configuration Decisions: {summary}"
        },
        "roles": {
            "types": [KnowledgeType.ROLE],
            "keywords": ["role", "purpose", "function"],
            "summary_template": "Component Roles: {summary}"
        },
        "relationships": {
            "types": [KnowledgeType.RELATIONSHIP],
            "keywords": ["depends", "uses", "connects", "related"],
            "summary_template": "System Relationships: {summary}"
        },
        "user_knowledge": {
            "types": [KnowledgeType.USER_TAUGHT],
            "keywords": [],
            "summary_template": "User-Taught Knowledge: {summary}"
        },
    }
    
    _instance: Optional['HierarchicalKnowledge'] = None
    
    def __new__(cls) -> 'HierarchicalKnowledge':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        self._documents: Dict[str, HierarchicalDoc] = {}
        self._data_path = self._get_data_path()
        
        # Indices
        self._by_tier: Dict[DocumentTier, Set[str]] = {
            tier: set() for tier in DocumentTier
        }
        self._by_category: Dict[str, Set[str]] = {}
        self._children: Dict[str, Set[str]] = {}  # parent_id -> child_ids
        
        # Load existing
        self._load_from_disk()
        self._rebuild_indices()
        
        logger.info(f"HierarchicalKnowledge initialized with {len(self._documents)} documents")
    
    def _get_data_path(self) -> Path:
        """Get path to hierarchical store."""
        data_dir = Path.home() / ".local" / "share" / "halbert" / "knowledge"
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir / "hierarchical_docs.json"
    
    def _load_from_disk(self):
        """Load documents from JSON file."""
        if not self._data_path.exists():
            return
        
        try:
            with open(self._data_path, 'r') as f:
                data = json.load(f)
            
            for doc_data in data.get('documents', []):
                doc = HierarchicalDoc.from_dict(doc_data)
                self._documents[doc.id] = doc
            
            logger.info(f"Loaded {len(self._documents)} hierarchical documents")
        except Exception as e:
            logger.error(f"Failed to load hierarchical docs: {e}")
    
    def _save_to_disk(self):
        """Persist documents to JSON file."""
        try:
            data = {
                'version': 1,
                'updated_at': datetime.now().isoformat(),
                'documents': [d.to_dict() for d in self._documents.values()]
            }
            with open(self._data_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save hierarchical docs: {e}")
    
    def _rebuild_indices(self):
        """Rebuild lookup indices."""
        for tier in DocumentTier:
            self._by_tier[tier] = set()
        self._by_category.clear()
        self._children.clear()
        
        for doc_id, doc in self._documents.items():
            self._by_tier[doc.tier].add(doc_id)
            
            if doc.category not in self._by_category:
                self._by_category[doc.category] = set()
            self._by_category[doc.category].add(doc_id)
            
            if doc.parent_id:
                if doc.parent_id not in self._children:
                    self._children[doc.parent_id] = set()
                self._children[doc.parent_id].add(doc_id)
    
    def _generate_id(self, tier: DocumentTier, category: str, title: str) -> str:
        """Generate a unique document ID."""
        content = f"{tier.value}:{category}:{title}"
        hash_suffix = hashlib.md5(content.encode()).hexdigest()[:8]
        return f"hdoc:{tier.value}:{category}:{hash_suffix}"
    
    # ─────────────────────────────────────────────────────────────
    # Document Management
    # ─────────────────────────────────────────────────────────────
    
    def add_document(self, doc: HierarchicalDoc) -> str:
        """Add or update a hierarchical document."""
        if doc.id in self._documents:
            doc.updated_at = datetime.now().isoformat()
        
        self._documents[doc.id] = doc
        
        # Update indices
        self._by_tier[doc.tier].add(doc.id)
        if doc.category not in self._by_category:
            self._by_category[doc.category] = set()
        self._by_category[doc.category].add(doc.id)
        
        if doc.parent_id:
            if doc.parent_id not in self._children:
                self._children[doc.parent_id] = set()
            self._children[doc.parent_id].add(doc.id)
        
        self._save_to_disk()
        return doc.id
    
    def get_document(self, doc_id: str) -> Optional[HierarchicalDoc]:
        """Get a document by ID."""
        return self._documents.get(doc_id)
    
    def get_by_tier(self, tier: DocumentTier) -> List[HierarchicalDoc]:
        """Get all documents at a tier."""
        return [self._documents[did] for did in self._by_tier.get(tier, set())]
    
    def get_by_category(self, category: str) -> List[HierarchicalDoc]:
        """Get all documents in a category."""
        return [self._documents[did] for did in self._by_category.get(category, set())]
    
    def get_children(self, parent_id: str) -> List[HierarchicalDoc]:
        """Get child documents of a parent."""
        return [self._documents[did] for did in self._children.get(parent_id, set())]
    
    # ─────────────────────────────────────────────────────────────
    # RAPTOR-style Building
    # ─────────────────────────────────────────────────────────────
    
    def build_from_knowledge(self) -> Dict[str, int]:
        """
        Build hierarchical documents from self-knowledge.
        
        Creates:
        1. LEAF docs from individual knowledge entries
        2. CLUSTER docs grouping related leaves
        3. SUMMARY docs providing category overviews
        
        Returns counts of documents created per tier.
        """
        sk = get_self_knowledge()
        counts = {tier.value: 0 for tier in DocumentTier}
        
        # Step 1: Create LEAF documents
        leaves_by_category: Dict[str, List[str]] = {}
        
        for entry in sk._knowledge.values():
            category = self._categorize_entry(entry)
            
            leaf = HierarchicalDoc(
                id=f"hdoc:leaf:{entry.id}",
                tier=DocumentTier.LEAF,
                title=entry.subject,
                content=entry.content,
                category=category,
                source_ids=[entry.id],
                metadata={"type": entry.type.value, "source": entry.source},
            )
            self.add_document(leaf)
            counts["leaf"] += 1
            
            if category not in leaves_by_category:
                leaves_by_category[category] = []
            leaves_by_category[category].append(leaf.id)
        
        # Step 2: Create CLUSTER documents
        for category, leaf_ids in leaves_by_category.items():
            if len(leaf_ids) < 1:
                continue
            
            # Get leaf contents
            leaves = [self._documents[lid] for lid in leaf_ids if lid in self._documents]
            
            # Generate cluster content
            cluster_content = self._generate_cluster_content(category, leaves)
            
            cluster = HierarchicalDoc(
                id=self._generate_id(DocumentTier.CLUSTER, category, "cluster"),
                tier=DocumentTier.CLUSTER,
                title=f"{category.title()} Overview",
                content=cluster_content,
                category=category,
                source_ids=leaf_ids,
                metadata={"leaf_count": len(leaf_ids)},
            )
            self.add_document(cluster)
            counts["cluster"] += 1
            
            # Update leaves to point to cluster
            for lid in leaf_ids:
                if lid in self._documents:
                    self._documents[lid].parent_id = cluster.id
        
        # Step 3: Create top-level SUMMARY
        cluster_ids = list(self._by_tier[DocumentTier.CLUSTER])
        if cluster_ids:
            summary_content = self._generate_summary_content()
            
            summary = HierarchicalDoc(
                id=self._generate_id(DocumentTier.SUMMARY, "system", "overview"),
                tier=DocumentTier.SUMMARY,
                title="System Overview",
                content=summary_content,
                category="system",
                source_ids=cluster_ids,
                metadata={"cluster_count": len(cluster_ids)},
            )
            self.add_document(summary)
            counts["summary"] += 1
        
        self._save_to_disk()
        logger.info(f"Built hierarchy: {counts}")
        return counts
    
    def _categorize_entry(self, entry: KnowledgeEntry) -> str:
        """Determine category for a knowledge entry."""
        # Check by type first
        for cat_name, cat_def in self.CATEGORIES.items():
            if entry.type in cat_def["types"]:
                # Also check keywords for better matching
                entry_text = f"{entry.subject} {entry.content}".lower()
                if any(kw in entry_text for kw in cat_def["keywords"]):
                    return cat_name
        
        # Fallback to type-based categorization
        type_to_category = {
            KnowledgeType.IDENTITY: "identity",
            KnowledgeType.HARDWARE: "hardware",
            KnowledgeType.CONFIG_RATIONALE: "config",
            KnowledgeType.ROLE: "roles",
            KnowledgeType.RELATIONSHIP: "relationships",
            KnowledgeType.USER_TAUGHT: "user_knowledge",
            KnowledgeType.OBSERVATION: "identity",
        }
        return type_to_category.get(entry.type, "identity")
    
    def _generate_cluster_content(
        self, 
        category: str, 
        leaves: List[HierarchicalDoc]
    ) -> str:
        """Generate summarized content for a cluster."""
        lines = [f"## {category.title()} Information\n"]
        
        for leaf in leaves[:20]:  # Limit to avoid huge clusters
            lines.append(f"- **{leaf.title}**: {leaf.content[:100]}")
        
        if len(leaves) > 20:
            lines.append(f"\n... and {len(leaves) - 20} more entries")
        
        return "\n".join(lines)
    
    def _generate_summary_content(self) -> str:
        """Generate top-level system summary."""
        sk = get_self_knowledge()
        
        # Gather key facts
        facts = {}
        for entry in sk._knowledge.values():
            if entry.subject in ['hostname', 'os', 'distribution', 'kernel']:
                facts[entry.subject] = entry.content
            elif entry.type == KnowledgeType.HARDWARE:
                facts[entry.subject] = entry.content
        
        lines = ["# System Overview\n"]
        lines.append(f"**Hostname**: {facts.get('hostname', 'Unknown')}")
        lines.append(f"**OS**: {facts.get('os', 'Unknown')} - {facts.get('distribution', '')}")
        lines.append(f"**Kernel**: {facts.get('kernel', 'Unknown')}")
        
        if 'cpu' in facts:
            lines.append(f"\n**CPU**: {facts['cpu']}")
        if 'memory' in facts:
            lines.append(f"**Memory**: {facts['memory']}")
        
        # Add category summaries
        lines.append("\n## Knowledge Categories")
        for category, doc_ids in self._by_category.items():
            leaf_count = len([d for d in doc_ids if self._documents.get(d, HierarchicalDoc("","","","","")).tier == DocumentTier.LEAF])
            if leaf_count > 0:
                lines.append(f"- **{category.title()}**: {leaf_count} entries")
        
        return "\n".join(lines)
    
    # ─────────────────────────────────────────────────────────────
    # Retrieval Methods
    # ─────────────────────────────────────────────────────────────
    
    def retrieve(
        self,
        query: str,
        preferred_tier: Optional[DocumentTier] = None,
        max_results: int = 5
    ) -> List[HierarchicalDoc]:
        """
        Retrieve documents matching a query.
        
        If preferred_tier is set, prioritizes that tier.
        Otherwise, auto-selects based on query specificity.
        """
        query_lower = query.lower()
        
        # Determine best tier if not specified
        if preferred_tier is None:
            preferred_tier = self._determine_best_tier(query_lower)
        
        # Score documents at preferred tier
        scored = []
        for doc in self.get_by_tier(preferred_tier):
            score = self._score_document(query_lower, doc)
            if score > 0:
                scored.append((doc, score))
        
        # If not enough results, check adjacent tiers
        if len(scored) < max_results:
            adjacent_tiers = self._get_adjacent_tiers(preferred_tier)
            for tier in adjacent_tiers:
                for doc in self.get_by_tier(tier):
                    score = self._score_document(query_lower, doc) * 0.8  # Slight penalty
                    if score > 0:
                        scored.append((doc, score))
        
        # Sort by score and return
        scored.sort(key=lambda x: x[1], reverse=True)
        return [doc for doc, _ in scored[:max_results]]
    
    def _determine_best_tier(self, query: str) -> DocumentTier:
        """Determine the best tier for a query."""
        # Specific queries → LEAF
        specific_keywords = ['what is', 'show me', 'exact', 'specific', 'value of']
        if any(kw in query for kw in specific_keywords):
            return DocumentTier.LEAF
        
        # Overview queries → SUMMARY
        overview_keywords = ['overview', 'summary', 'tell me about', 'describe', 'explain']
        if any(kw in query for kw in overview_keywords):
            return DocumentTier.SUMMARY
        
        # Default to CLUSTER for balanced detail
        return DocumentTier.CLUSTER
    
    def _get_adjacent_tiers(self, tier: DocumentTier) -> List[DocumentTier]:
        """Get adjacent tiers for fallback retrieval."""
        if tier == DocumentTier.LEAF:
            return [DocumentTier.CLUSTER]
        elif tier == DocumentTier.SUMMARY:
            return [DocumentTier.CLUSTER]
        else:
            return [DocumentTier.LEAF, DocumentTier.SUMMARY]
    
    def _score_document(self, query: str, doc: HierarchicalDoc) -> float:
        """Score how well a document matches a query."""
        score = 0.0
        query_words = set(query.split())
        
        # Title match
        title_words = set(doc.title.lower().split())
        if query_words & title_words:
            score += 0.4 * len(query_words & title_words) / len(query_words)
        
        # Content match
        content_words = set(doc.content.lower().split())
        if query_words & content_words:
            score += 0.3 * len(query_words & content_words) / len(query_words)
        
        # Category match
        if doc.category.lower() in query:
            score += 0.2
        
        # Exact phrase bonus
        if doc.title.lower() in query or query in doc.title.lower():
            score += 0.3
        
        return min(score, 1.0)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get hierarchical knowledge statistics."""
        return {
            "total_documents": len(self._documents),
            "by_tier": {tier.value: len(ids) for tier, ids in self._by_tier.items()},
            "by_category": {cat: len(ids) for cat, ids in self._by_category.items()},
        }


# ─────────────────────────────────────────────────────────────────────────────
# Singleton accessor
# ─────────────────────────────────────────────────────────────────────────────

_hierarchical_instance: Optional[HierarchicalKnowledge] = None

def get_hierarchical_knowledge() -> HierarchicalKnowledge:
    """Get the singleton HierarchicalKnowledge instance."""
    global _hierarchical_instance
    if _hierarchical_instance is None:
        _hierarchical_instance = HierarchicalKnowledge()
    return _hierarchical_instance
