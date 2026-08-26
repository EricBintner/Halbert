# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
RAPTOR: Recursive Abstractive Processing for Tree-Organized Retrieval

Implementation based on Stanford NLP research (2024):
- Paper: https://arxiv.org/abs/2401.18059
- Builds hierarchical tree of summaries from bottom up
- Enables retrieval at different levels of abstraction
- 20% improvement on QuALITY benchmark

Architecture:
    Level 0: Original document chunks
    Level 1: Summaries of chunk clusters
    Level 2: Summaries of Level 1 summaries
    ...
    Level N: Root summary (single document summary)
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class RaptorNode:
    """A node in the RAPTOR tree."""
    id: str
    level: int                          # 0 = leaf (original chunk), higher = more abstract
    text: str                           # Content (original or summary)
    embedding: Optional[List[float]] = None
    children: List[str] = field(default_factory=list)  # Child node IDs
    parent: Optional[str] = None        # Parent node ID
    source_doc: Optional[str] = None    # Original document ID
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "level": self.level,
            "text": self.text,
            "embedding": self.embedding,
            "children": self.children,
            "parent": self.parent,
            "source_doc": self.source_doc,
            "metadata": self.metadata,
            "created_at": self.created_at,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RaptorNode':
        return cls(**data)


class RaptorIndex:
    """
    RAPTOR hierarchical index for documents.
    
    Enables multi-level retrieval:
    - Query at level 0 for specific details
    - Query at higher levels for broader context
    - Combine levels for comprehensive answers
    
    Example:
        raptor = RaptorIndex()
        raptor.build_tree(doc_chunks, doc_id="arch-wiki-systemd")
        
        # Get specific details
        results = raptor.query("systemd timer syntax", level=0)
        
        # Get overview
        results = raptor.query("what is systemd", level=2)
        
        # Get both (default)
        results = raptor.query("systemd services", levels=[0, 1, 2])
    """
    
    def __init__(
        self,
        cluster_size: int = 5,
        max_levels: int = 4,
        summary_model: Optional[str] = None,
    ):
        """
        Initialize RAPTOR index.
        
        Args:
            cluster_size: Number of nodes to cluster at each level
            max_levels: Maximum tree depth
            summary_model: LLM for generating summaries; None means the
                configured guide model (resolved at call time)
        """
        self.cluster_size = cluster_size
        self.max_levels = max_levels
        self.summary_model = summary_model
        
        self._nodes: Dict[str, RaptorNode] = {}
        self._level_index: Dict[int, List[str]] = {}  # level -> node IDs
        self._doc_trees: Dict[str, str] = {}  # doc_id -> root node ID
        
        self._data_path = self._get_data_path()
        self._load_from_disk()
        
        logger.info(f"RaptorIndex initialized with {len(self._nodes)} nodes")
    
    def _get_data_path(self) -> Path:
        """Get path to RAPTOR store."""
        data_dir = Path.home() / ".local" / "share" / "halbert" / "raptor"
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir / "raptor_index.json"
    
    def _load_from_disk(self):
        """Load index from disk."""
        if not self._data_path.exists():
            return
        
        try:
            with open(self._data_path, 'r') as f:
                data = json.load(f)
            
            for node_data in data.get('nodes', []):
                node = RaptorNode.from_dict(node_data)
                self._nodes[node.id] = node
                
                if node.level not in self._level_index:
                    self._level_index[node.level] = []
                self._level_index[node.level].append(node.id)
            
            self._doc_trees = data.get('doc_trees', {})
            logger.info(f"Loaded {len(self._nodes)} RAPTOR nodes")
        except Exception as e:
            logger.error(f"Failed to load RAPTOR index: {e}")
    
    def _save_to_disk(self):
        """Persist index to disk."""
        try:
            data = {
                'version': 1,
                'updated_at': datetime.now().isoformat(),
                'nodes': [n.to_dict() for n in self._nodes.values()],
                'doc_trees': self._doc_trees,
            }
            with open(self._data_path, 'w') as f:
                json.dump(data, f)
        except Exception as e:
            logger.error(f"Failed to save RAPTOR index: {e}")
    
    def _generate_node_id(self, text: str, level: int, doc_id: str) -> str:
        """Generate unique node ID."""
        content = f"{doc_id}:{level}:{text[:100]}"
        return f"raptor:{hashlib.md5(content.encode()).hexdigest()[:12]}"
    
    def _get_embedding(self, text: str) -> List[float]:
        """Get embedding for text."""
        try:
            from ..rag.embeddings import EmbeddingManager
            em = EmbeddingManager()
            return em.embed(text)
        except Exception as e:
            logger.warning(f"Failed to get embedding: {e}")
            return []
    
    def _generate_summary(self, texts: List[str]) -> str:
        """Generate summary of multiple texts using LLM."""
        combined = "\n\n---\n\n".join(texts)
        
        # Truncate if too long
        max_chars = 8000
        if len(combined) > max_chars:
            combined = combined[:max_chars] + "..."
        
        prompt = f"""Summarize the following related content into a concise, comprehensive summary.
Focus on key concepts, commands, and important details.
Keep the summary informative but under 500 words.

Content:
{combined}

Summary:"""
        
        try:
            import requests
            from ..model.client import get_configured_model, get_ollama_endpoint
            
            model = self.summary_model or get_configured_model()
            if not model:
                raise ValueError(
                    "No model configured — choose one in Settings → AI Models"
                )
            endpoint = get_ollama_endpoint()
            response = requests.post(
                f"{endpoint}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                },
                timeout=60
            )
            response.raise_for_status()
            return response.json().get("response", "").strip()
        except Exception as e:
            logger.warning(f"Failed to generate summary: {e}")
            # Fallback: just concatenate first parts
            return " ".join(t[:200] for t in texts[:3])
    
    def _cluster_nodes(self, node_ids: List[str]) -> List[List[str]]:
        """
        Cluster nodes by embedding similarity.
        
        Uses simple k-means style clustering based on embeddings.
        """
        if len(node_ids) <= self.cluster_size:
            return [node_ids]
        
        # Get embeddings
        embeddings = []
        valid_ids = []
        for nid in node_ids:
            node = self._nodes.get(nid)
            if node and node.embedding:
                embeddings.append(node.embedding)
                valid_ids.append(nid)
        
        if not embeddings:
            # No embeddings, just chunk by position
            clusters = []
            for i in range(0, len(node_ids), self.cluster_size):
                clusters.append(node_ids[i:i+self.cluster_size])
            return clusters
        
        # Simple clustering: group by similarity
        try:
            embeddings_arr = np.array(embeddings)
            n_clusters = max(1, len(valid_ids) // self.cluster_size)
            
            # K-means clustering
            from sklearn.cluster import KMeans
            kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
            labels = kmeans.fit_predict(embeddings_arr)
            
            clusters = [[] for _ in range(n_clusters)]
            for idx, label in enumerate(labels):
                clusters[label].append(valid_ids[idx])
            
            # Remove empty clusters
            clusters = [c for c in clusters if c]
            return clusters
            
        except ImportError:
            # sklearn not available, fall back to simple chunking
            logger.warning("sklearn not available for clustering, using simple chunking")
            clusters = []
            for i in range(0, len(node_ids), self.cluster_size):
                clusters.append(node_ids[i:i+self.cluster_size])
            return clusters
    
    def build_tree(
        self,
        chunks: List[str],
        doc_id: str,
        metadata: Optional[Dict] = None
    ) -> str:
        """
        Build RAPTOR tree from document chunks.
        
        Args:
            chunks: List of text chunks (level 0 nodes)
            doc_id: Document identifier
            metadata: Optional metadata for all nodes
        
        Returns:
            Root node ID
        """
        if not chunks:
            logger.warning(f"No chunks provided for {doc_id}")
            return ""
        
        logger.info(f"Building RAPTOR tree for {doc_id} with {len(chunks)} chunks")
        
        # Create level 0 nodes (original chunks)
        current_level_ids = []
        for i, chunk in enumerate(chunks):
            node_id = self._generate_node_id(chunk, 0, doc_id)
            
            node = RaptorNode(
                id=node_id,
                level=0,
                text=chunk,
                embedding=self._get_embedding(chunk),
                source_doc=doc_id,
                metadata={**(metadata or {}), "chunk_index": i}
            )
            
            self._nodes[node_id] = node
            current_level_ids.append(node_id)
            
            if 0 not in self._level_index:
                self._level_index[0] = []
            self._level_index[0].append(node_id)
        
        logger.info(f"Created {len(current_level_ids)} level 0 nodes")
        
        # Build higher levels until we have a single root or hit max
        current_level = 0
        while len(current_level_ids) > 1 and current_level < self.max_levels - 1:
            current_level += 1
            
            # Cluster current level nodes
            clusters = self._cluster_nodes(current_level_ids)
            logger.info(f"Level {current_level}: {len(clusters)} clusters from {len(current_level_ids)} nodes")
            
            # Create summary nodes for each cluster
            next_level_ids = []
            for cluster in clusters:
                # Get texts of children
                child_texts = [self._nodes[cid].text for cid in cluster]
                
                # Generate summary
                summary = self._generate_summary(child_texts)
                
                # Create parent node
                node_id = self._generate_node_id(summary, current_level, doc_id)
                
                node = RaptorNode(
                    id=node_id,
                    level=current_level,
                    text=summary,
                    embedding=self._get_embedding(summary),
                    children=cluster,
                    source_doc=doc_id,
                    metadata=metadata or {}
                )
                
                self._nodes[node_id] = node
                next_level_ids.append(node_id)
                
                # Update children's parent pointer
                for cid in cluster:
                    self._nodes[cid].parent = node_id
                
                if current_level not in self._level_index:
                    self._level_index[current_level] = []
                self._level_index[current_level].append(node_id)
            
            current_level_ids = next_level_ids
        
        # Store root
        root_id = current_level_ids[0] if current_level_ids else ""
        self._doc_trees[doc_id] = root_id
        
        self._save_to_disk()
        logger.info(f"Built RAPTOR tree for {doc_id}: {len(self._nodes)} total nodes, root={root_id}")
        
        return root_id
    
    def query(
        self,
        query: str,
        levels: Optional[List[int]] = None,
        k: int = 5,
        doc_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Query RAPTOR index at specified levels.
        
        Args:
            query: Search query
            levels: Levels to search (None = all levels)
            k: Number of results per level
            doc_id: Optional filter by document
        
        Returns:
            List of results with node info and similarity scores
        """
        query_embedding = self._get_embedding(query)
        if not query_embedding:
            logger.warning("Failed to get query embedding")
            return []
        
        # Determine levels to search
        if levels is None:
            levels = list(self._level_index.keys())
        
        results = []
        
        for level in levels:
            level_nodes = self._level_index.get(level, [])
            
            # Filter by doc_id if specified
            if doc_id:
                level_nodes = [
                    nid for nid in level_nodes 
                    if self._nodes[nid].source_doc == doc_id
                ]
            
            # Score nodes by similarity
            scored = []
            for nid in level_nodes:
                node = self._nodes[nid]
                if not node.embedding:
                    continue
                
                # Cosine similarity
                similarity = self._cosine_similarity(query_embedding, node.embedding)
                scored.append((similarity, node))
            
            # Sort by score and take top k
            scored.sort(key=lambda x: x[0], reverse=True)
            
            for score, node in scored[:k]:
                results.append({
                    "id": node.id,
                    "level": node.level,
                    "text": node.text,
                    "score": score,
                    "source_doc": node.source_doc,
                    "has_children": len(node.children) > 0,
                    "has_parent": node.parent is not None,
                })
        
        # Sort all results by score
        results.sort(key=lambda x: x["score"], reverse=True)
        
        return results
    
    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        try:
            a_arr = np.array(a)
            b_arr = np.array(b)
            return float(np.dot(a_arr, b_arr) / (np.linalg.norm(a_arr) * np.linalg.norm(b_arr)))
        except:
            return 0.0
    
    def get_context_with_hierarchy(
        self,
        query: str,
        k_per_level: int = 2
    ) -> str:
        """
        Get context combining multiple abstraction levels.
        
        Returns context formatted with level indicators.
        """
        results = self.query(query, k=k_per_level)
        
        if not results:
            return ""
        
        # Group by level
        by_level = {}
        for r in results:
            level = r["level"]
            if level not in by_level:
                by_level[level] = []
            by_level[level].append(r)
        
        # Build context
        context_parts = []
        
        # Start with highest level (overview)
        for level in sorted(by_level.keys(), reverse=True):
            level_name = "Overview" if level > 1 else "Summary" if level == 1 else "Detail"
            context_parts.append(f"=== {level_name} (Level {level}) ===")
            
            for r in by_level[level][:k_per_level]:
                context_parts.append(r["text"])
            
            context_parts.append("")
        
        return "\n".join(context_parts)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get index statistics."""
        level_counts = {level: len(ids) for level, ids in self._level_index.items()}
        
        return {
            "total_nodes": len(self._nodes),
            "documents": len(self._doc_trees),
            "levels": level_counts,
            "max_level": max(self._level_index.keys()) if self._level_index else 0,
        }


# Singleton accessor
_raptor_instance: Optional[RaptorIndex] = None

def get_raptor_index() -> RaptorIndex:
    """Get singleton RAPTOR index."""
    global _raptor_instance
    if _raptor_instance is None:
        _raptor_instance = RaptorIndex()
    return _raptor_instance


def build_raptor_for_collection(
    collection_name: str = "linux_docs",
    max_docs: int = 100
) -> Dict[str, Any]:
    """
    Build RAPTOR trees for documents in a ChromaDB collection.
    
    Args:
        collection_name: ChromaDB collection to process
        max_docs: Maximum documents to process
    
    Returns:
        Stats about the build process
    """
    from ..index.chroma_index import get_index
    
    raptor = get_raptor_index()
    idx = get_index()
    
    # Get documents from collection
    try:
        col = idx.client.get_collection(collection_name)
        results = col.peek(max_docs)
    except Exception as e:
        logger.error(f"Failed to access collection {collection_name}: {e}")
        return {"error": str(e)}
    
    docs_processed = 0
    trees_built = 0
    
    if results and results.get("documents"):
        documents = results["documents"]
        metadatas = results.get("metadatas", [{}] * len(documents))
        ids = results.get("ids", [f"doc_{i}" for i in range(len(documents))])
        
        # Group chunks by source document
        doc_chunks: Dict[str, List[str]] = {}
        for i, (doc, meta, doc_id) in enumerate(zip(documents, metadatas, ids)):
            source = meta.get("source", meta.get("title", doc_id))
            if source not in doc_chunks:
                doc_chunks[source] = []
            doc_chunks[source].append(doc)
        
        # Build tree for each document
        for doc_id, chunks in doc_chunks.items():
            if len(chunks) >= 3:  # Only build tree if enough chunks
                raptor.build_tree(chunks, doc_id)
                trees_built += 1
            docs_processed += len(chunks)
    
    return {
        "collection": collection_name,
        "docs_processed": docs_processed,
        "trees_built": trees_built,
        "total_nodes": len(raptor._nodes),
    }
