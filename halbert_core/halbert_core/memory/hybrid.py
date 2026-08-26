"""
Hybrid Memory System

Unified memory interface integrating vector store, knowledge graph, and self-knowledge.
Based on research5.md Part 15.
"""

from __future__ import annotations
import asyncio
import time
import uuid
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from enum import Enum

logger = logging.getLogger('halbert.memory.hybrid')


class MemoryType(Enum):
    """Types of memories."""
    FACT = "fact"              # Factual information
    PREFERENCE = "preference"  # User preferences
    INTERACTION = "interaction"  # Q&A interactions
    PATTERN = "pattern"        # Learned patterns
    SEMANTIC = "semantic"      # Semantic knowledge
    EPISODIC = "episodic"      # Episode/event memory
    SUMMARY = "summary"        # A-MEM: Hierarchical summary of other memories


@dataclass
class Memory:
    """A single memory entry."""
    id: str
    content: str
    memory_type: MemoryType
    created_at: float
    last_accessed: float
    access_count: int
    importance: float
    metadata: Dict[str, Any]
    embedding: Optional[List[float]] = None
    # A-MEM: Edit history and relationships
    edit_history: List[Dict] = field(default_factory=list)
    parent_ids: List[str] = field(default_factory=list)  # For merged/summary memories
    contradiction_ids: List[str] = field(default_factory=list)  # Conflicting memories
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "content": self.content,
            "type": self.memory_type.value,
            "created_at": self.created_at,
            "last_accessed": self.last_accessed,
            "access_count": self.access_count,
            "importance": self.importance,
            "metadata": self.metadata,
            "edit_count": len(self.edit_history),
            "has_contradictions": len(self.contradiction_ids) > 0,
        }


class HybridMemorySystem:
    """
    Unified memory interface for the agent.
    
    Integrates with existing Halbert memory systems:
    - Vector store (ChromaDB) for semantic search
    - Knowledge graph for relational queries
    - Self-knowledge for learned facts
    
    Based on research5.md Part 15.
    """
    
    def __init__(
        self,
        vector_store=None,
        knowledge_graph=None,
        self_knowledge=None,
        embedding_service=None,
        cache_max_size: int = 100
    ):
        """
        Initialize hybrid memory system.
        
        Args:
            vector_store: ChromaDB or similar vector store
            knowledge_graph: Knowledge graph service
            self_knowledge: Self-knowledge store
            embedding_service: Service for generating embeddings
            cache_max_size: Maximum items in hot cache
        """
        self.vectors = vector_store
        self.graph = knowledge_graph
        self.self_knowledge = self_knowledge
        self.embeddings = embedding_service
        
        # In-memory cache for hot data
        self.cache: Dict[str, Memory] = {}
        self.cache_max_size = cache_max_size
        
        # Track if services are available
        self._initialized = False
    
    def _ensure_initialized(self):
        """Lazy initialization of services."""
        if self._initialized:
            return
        
        # Try to connect to existing services
        if self.vectors is None:
            try:
                from ..index.chroma_index import get_index
                self.vectors = get_index()
                logger.info("Connected to ChromaDB vector store")
            except Exception as e:
                logger.warning(f"Vector store not available: {e}")
        
        if self.self_knowledge is None:
            try:
                from ..knowledge.self_knowledge import get_self_knowledge
                self.self_knowledge = get_self_knowledge()
                logger.info("Connected to self-knowledge store")
            except Exception as e:
                logger.warning(f"Self-knowledge not available: {e}")
        
        if self.embeddings is None:
            # The RAG EmbeddingManager (sentence-transformers) is the only
            # embedder in the codebase. It loads its model lazily, so wiring it
            # here is cheap; the model is only pulled on the first embed call.
            try:
                from ..rag.embeddings import EmbeddingManager
                self.embeddings = _EmbeddingManagerAdapter(EmbeddingManager())
                logger.info("Connected to embedding service (rag.embeddings.EmbeddingManager)")
            except Exception as e:
                logger.debug(f"Embedding service not available: {e}")
        
        self._initialized = True
    
    async def store(
        self,
        content: str,
        memory_type: MemoryType = MemoryType.FACT,
        metadata: Dict = None,
        importance: float = 0.5
    ) -> str:
        """
        Store a new memory.
        
        Args:
            content: Memory content
            memory_type: Type of memory
            metadata: Additional metadata
            importance: Importance score (0-1)
            
        Returns:
            Memory ID
        """
        self._ensure_initialized()
        
        memory_id = str(uuid.uuid4())
        now = time.time()
        
        # Get embedding if service available
        embedding = None
        if self.embeddings:
            try:
                embedding = await self._get_embedding(content)
            except Exception as e:
                logger.warning(f"Failed to get embedding: {e}")
        
        memory = Memory(
            id=memory_id,
            content=content,
            memory_type=memory_type,
            created_at=now,
            last_accessed=now,
            access_count=0,
            importance=importance,
            metadata=metadata or {},
            embedding=embedding
        )
        
        # Store in appropriate backends
        try:
            if memory_type == MemoryType.SEMANTIC and self.self_knowledge:
                await self._store_self_knowledge(content, metadata)
            
            if memory_type in [MemoryType.FACT, MemoryType.PATTERN] and self.graph:
                await self._store_graph(content, memory_type, metadata)
            
            # Always try to store in vector store for retrieval
            if self.vectors and embedding:
                await self._store_vector(memory_id, embedding, memory)
        except Exception as e:
            logger.error(f"Failed to store memory: {e}")
        
        # Cache in memory
        self._cache_memory(memory)
        
        logger.debug(f"Stored memory {memory_id}: {content[:50]}...")
        return memory_id
    
    async def recall(
        self,
        query: str,
        memory_types: List[MemoryType] = None,
        limit: int = 5,
        min_relevance: float = 0.3
    ) -> List[Dict]:
        """
        Recall relevant memories.
        
        Args:
            query: Search query
            memory_types: Filter by memory types
            limit: Maximum memories to return
            min_relevance: Minimum relevance threshold
            
        Returns:
            List of relevant memories
        """
        self._ensure_initialized()
        
        memories = []
        
        # Try vector search first
        if self.vectors:
            try:
                vector_results = await self._search_vectors(query, limit * 2)
                memories.extend(vector_results)
            except Exception as e:
                logger.warning(f"Vector search failed: {e}")
        
        # Also search self-knowledge
        if self.self_knowledge:
            try:
                sk_results = await self._search_self_knowledge(query, limit)
                for result in sk_results:
                    if not any(m.get("content") == result.get("content") for m in memories):
                        memories.append(result)
            except Exception as e:
                logger.warning(f"Self-knowledge search failed: {e}")
        
        # Also check cache
        cache_results = self._search_cache(query, limit)
        for result in cache_results:
            if not any(m.get("id") == result.get("id") for m in memories):
                memories.append(result)
        
        # Filter by type if specified
        if memory_types:
            type_values = [t.value for t in memory_types]
            memories = [m for m in memories if m.get("type") in type_values]
        
        # Filter by relevance
        memories = [m for m in memories if m.get("relevance", 0.5) >= min_relevance]
        
        # Sort by combined score (relevance + importance)
        memories.sort(
            key=lambda m: m.get("relevance", 0.5) * 0.7 + m.get("importance", 0.5) * 0.3,
            reverse=True
        )
        
        # Update access stats for returned memories
        for mem in memories[:limit]:
            await self._update_access(mem.get("id"))
        
        return memories[:limit]
    
    async def store_interaction(
        self,
        query: str,
        response: str,
        session_id: str = None,
        success: bool = True
    ):
        """
        Store an interaction for learning.
        
        Args:
            query: User query
            response: Agent response
            session_id: Session identifier
            success: Whether interaction was successful
        """
        # Only store successful, substantive interactions
        if success and len(response) > 50:
            await self.store(
                content=f"Q: {query[:200]}\nA: {response[:500]}",
                memory_type=MemoryType.INTERACTION,
                metadata={
                    "session_id": session_id,
                    "success": success,
                    "query_length": len(query),
                    "response_length": len(response),
                    "timestamp": time.time()
                },
                importance=0.3  # Low importance initially
            )
    
    async def reinforce(self, memory_id: str, amount: float = 0.1):
        """
        Reinforce a memory (increase importance).
        
        Called when a memory is useful.
        """
        if memory_id in self.cache:
            mem = self.cache[memory_id]
            mem.importance = min(1.0, mem.importance + amount)
            mem.last_accessed = time.time()
            mem.access_count += 1
        
        # Also update in vector store if available
        if self.vectors:
            try:
                await self._update_vector_importance(memory_id, amount)
            except Exception as e:
                logger.warning(f"Failed to update vector store: {e}")
    
    async def forget(self, memory_id: str):
        """Remove a memory."""
        # Remove from cache
        if memory_id in self.cache:
            del self.cache[memory_id]
        
        # Remove from vector store
        if self.vectors:
            try:
                self.vectors.delete(memory_id)
            except Exception as e:
                logger.warning(f"Failed to delete from vector store: {e}")
    
    async def consolidate(self):
        """
        Consolidate memories - decay old, low-access memories.
        
        Should be called periodically (e.g., daily).
        """
        now = time.time()
        to_forget = []
        
        # Check cache entries
        for memory_id, mem in self.cache.items():
            age_days = (now - mem.created_at) / 86400
            
            # Decay formula: old + rarely accessed = low importance
            if age_days > 30 and mem.access_count < 3:
                mem.importance *= 0.9
                
                if mem.importance < 0.1:
                    to_forget.append(memory_id)
        
        # Remove forgotten memories
        for memory_id in to_forget:
            await self.forget(memory_id)
            logger.info(f"Consolidated (forgot) memory: {memory_id}")
        
        logger.info(f"Consolidation complete: forgot {len(to_forget)} memories")
    
    async def get_preferences(self, user_id: str = None) -> List[Dict]:
        """Get user preferences."""
        return await self.recall(
            query="user preference setting",
            memory_types=[MemoryType.PREFERENCE],
            limit=10,
            min_relevance=0.2
        )
    
    async def store_preference(self, key: str, value: Any, user_id: str = None):
        """Store a user preference."""
        await self.store(
            content=f"Preference: {key} = {value}",
            memory_type=MemoryType.PREFERENCE,
            metadata={"key": key, "value": value, "user_id": user_id},
            importance=0.8  # Preferences are important
        )
    
    # =========================================================================
    # A-MEM: Agentic Memory Methods
    # Based on arxiv.org/abs/2502.12110
    # =========================================================================
    
    async def edit(
        self,
        memory_id: str,
        new_content: str,
        reason: str = ""
    ) -> bool:
        """
        Edit an existing memory with audit trail.
        
        A-MEM pattern: Agent can self-edit memories when it learns
        new information that updates or corrects previous knowledge.
        
        Args:
            memory_id: ID of memory to edit
            new_content: Updated content
            reason: Reason for the edit
            
        Returns:
            True if edit successful
        """
        if memory_id not in self.cache:
            logger.warning(f"Cannot edit memory {memory_id}: not in cache")
            return False
        
        memory = self.cache[memory_id]
        old_content = memory.content
        
        # Record edit history
        memory.edit_history.append({
            "timestamp": time.time(),
            "old_content": old_content,
            "new_content": new_content,
            "reason": reason,
        })
        
        # Update content
        memory.content = new_content
        memory.last_accessed = time.time()
        
        # Update embedding if service available
        if self.embeddings:
            try:
                memory.embedding = await self._get_embedding(new_content)
            except Exception as e:
                logger.warning(f"Failed to update embedding: {e}")
        
        # Update in vector store
        if self.vectors and memory.embedding:
            try:
                # Delete old and add new (most vector stores don't support update)
                if hasattr(self.vectors, 'delete'):
                    self.vectors.delete(ids=[memory_id])
                await self._store_vector(memory_id, memory.embedding, memory)
            except Exception as e:
                logger.warning(f"Failed to update vector store: {e}")
        
        logger.info(f"Edited memory {memory_id}: '{old_content[:30]}...' -> '{new_content[:30]}...'")
        return True
    
    async def merge(
        self,
        memory_ids: List[str],
        merged_content: str,
        importance: float = None
    ) -> Optional[str]:
        """
        Merge multiple memories into one.
        
        A-MEM pattern: Consolidate related memories to reduce
        redundancy and improve retrieval quality.
        
        Args:
            memory_ids: IDs of memories to merge
            merged_content: Combined content
            importance: Override importance (default: max of merged)
            
        Returns:
            ID of new merged memory, or None if failed
        """
        # Gather memories to merge
        memories_to_merge = []
        max_importance = 0.5
        
        for mid in memory_ids:
            if mid in self.cache:
                memories_to_merge.append(self.cache[mid])
                max_importance = max(max_importance, self.cache[mid].importance)
        
        if len(memories_to_merge) < 2:
            logger.warning(f"Cannot merge: need at least 2 memories, found {len(memories_to_merge)}")
            return None
        
        # Create merged memory
        new_id = await self.store(
            content=merged_content,
            memory_type=MemoryType.FACT,  # Merged memories become facts
            metadata={
                "merged_from": memory_ids,
                "merge_timestamp": time.time(),
            },
            importance=importance if importance is not None else max_importance
        )
        
        # Update parent_ids on new memory
        if new_id in self.cache:
            self.cache[new_id].parent_ids = memory_ids
        
        # Reduce importance of original memories (soft delete)
        for mid in memory_ids:
            if mid in self.cache:
                self.cache[mid].importance *= 0.3  # Demote but keep
        
        logger.info(f"Merged {len(memory_ids)} memories into {new_id}")
        return new_id
    
    async def flag_contradiction(
        self,
        memory_id_1: str,
        memory_id_2: str,
        notes: str = ""
    ) -> bool:
        """
        Flag two memories as potentially conflicting.
        
        A-MEM pattern: Track contradictions for resolution.
        
        Args:
            memory_id_1: First memory ID
            memory_id_2: Second memory ID
            notes: Optional notes about the contradiction
            
        Returns:
            True if flagged successfully
        """
        mem1 = self.cache.get(memory_id_1)
        mem2 = self.cache.get(memory_id_2)
        
        if not mem1 or not mem2:
            logger.warning(f"Cannot flag contradiction: memory not found")
            return False
        
        # Cross-reference contradictions
        if memory_id_2 not in mem1.contradiction_ids:
            mem1.contradiction_ids.append(memory_id_2)
        if memory_id_1 not in mem2.contradiction_ids:
            mem2.contradiction_ids.append(memory_id_1)
        
        # Store contradiction metadata
        mem1.metadata["contradiction_notes"] = mem1.metadata.get("contradiction_notes", [])
        mem1.metadata["contradiction_notes"].append({
            "with": memory_id_2,
            "notes": notes,
            "timestamp": time.time(),
        })
        
        logger.info(f"Flagged contradiction between {memory_id_1} and {memory_id_2}")
        return True
    
    async def get_contradictions(self) -> List[Dict]:
        """Get all memories with contradictions."""
        contradictions = []
        seen_pairs = set()
        
        for memory_id, mem in self.cache.items():
            if mem.contradiction_ids:
                for contra_id in mem.contradiction_ids:
                    pair = tuple(sorted([memory_id, contra_id]))
                    if pair not in seen_pairs:
                        seen_pairs.add(pair)
                        contradictions.append({
                            "memory_1": mem.to_dict(),
                            "memory_2": self.cache[contra_id].to_dict() if contra_id in self.cache else {"id": contra_id},
                        })
        
        return contradictions
    
    async def summarize_cluster(
        self,
        memory_ids: List[str],
        summary: str
    ) -> Optional[str]:
        """
        Create a hierarchical summary of related memories.
        
        A-MEM pattern: Build abstraction hierarchy for efficient retrieval.
        
        Args:
            memory_ids: IDs of memories to summarize
            summary: Summary content
            
        Returns:
            ID of summary memory
        """
        # Create summary memory
        summary_id = await self.store(
            content=summary,
            memory_type=MemoryType.SUMMARY,
            metadata={
                "summarizes": memory_ids,
                "summary_timestamp": time.time(),
            },
            importance=0.7  # Summaries are fairly important
        )
        
        # Link parent IDs
        if summary_id in self.cache:
            self.cache[summary_id].parent_ids = memory_ids
        
        logger.info(f"Created summary {summary_id} for {len(memory_ids)} memories")
        return summary_id
    
    async def get_edit_history(self, memory_id: str) -> List[Dict]:
        """Get edit history for a memory."""
        if memory_id in self.cache:
            return self.cache[memory_id].edit_history
        return []
    
    # Internal helper methods
    
    async def _get_embedding(self, text: str) -> List[float]:
        """Get embedding for text."""
        if hasattr(self.embeddings, 'embed'):
            return await self.embeddings.embed(text)
        elif hasattr(self.embeddings, 'encode'):
            return self.embeddings.encode(text).tolist()
        else:
            raise ValueError("Embedding service has no embed/encode method")
    
    async def _store_vector(self, memory_id: str, embedding: List[float], memory: Memory):
        """Store in vector database."""
        if hasattr(self.vectors, 'add'):
            self.vectors.add(
                ids=[memory_id],
                embeddings=[embedding],
                metadatas=[{
                    "content": memory.content[:1000],
                    "type": memory.memory_type.value,
                    "importance": memory.importance,
                    "created_at": memory.created_at,
                    **memory.metadata
                }]
            )
    
    async def _search_vectors(self, query: str, limit: int) -> List[Dict]:
        """Search vector database."""
        results = []
        
        if hasattr(self.vectors, 'search'):
            search_results = self.vectors.search(query, n_results=limit)
            
            for doc, metadata, distance in zip(
                search_results.get('documents', [[]])[0],
                search_results.get('metadatas', [[]])[0],
                search_results.get('distances', [[]])[0]
            ):
                results.append({
                    "id": metadata.get("id", str(uuid.uuid4())),
                    "content": doc or metadata.get("content", ""),
                    "type": metadata.get("type", "fact"),
                    "relevance": 1.0 - distance,  # Convert distance to similarity
                    "importance": metadata.get("importance", 0.5),
                    "metadata": metadata
                })
        
        return results
    
    async def _search_self_knowledge(self, query: str, limit: int) -> List[Dict]:
        """Search self-knowledge store.

        ``SelfKnowledge.search(query, k)`` returns ``KnowledgeEntry`` dataclasses;
        dict-shaped stores are still accepted for compatibility.
        """
        results = []
        
        if hasattr(self.self_knowledge, 'search'):
            sk_results = self.self_knowledge.search(query, k=limit)
            for item in sk_results:
                if isinstance(item, dict):
                    results.append({
                        "id": item.get("id", str(uuid.uuid4())),
                        "content": item.get("content", str(item)),
                        "type": "semantic",
                        "relevance": item.get("score", 0.5),
                        "importance": 0.6,
                        "metadata": item
                    })
                    continue
                # KnowledgeEntry (or duck-typed object with the same fields)
                entry_meta = dict(getattr(item, "metadata", None) or {})
                entry_meta.setdefault("subject", getattr(item, "subject", ""))
                entry_type = getattr(item, "type", None)
                if entry_type is not None:
                    entry_meta.setdefault(
                        "knowledge_type", getattr(entry_type, "value", str(entry_type))
                    )
                results.append({
                    "id": getattr(item, "id", None) or str(uuid.uuid4()),
                    "content": getattr(item, "content", str(item)),
                    "type": "semantic",
                    "relevance": 0.5,
                    "importance": 0.6,
                    "metadata": entry_meta
                })
        
        return results
    
    async def _store_self_knowledge(self, content: str, metadata: Dict):
        """Store in self-knowledge.

        ``SelfKnowledge.add`` takes a ``KnowledgeEntry``; build one from the
        memory content. Stores without a compatible ``add`` are skipped quietly.
        """
        metadata = dict(metadata or {})
        if hasattr(self.self_knowledge, 'store'):
            self.self_knowledge.store(content, metadata)
            return
        if not hasattr(self.self_knowledge, 'add'):
            logger.debug("Self-knowledge store has no add(); skipping semantic store")
            return
        
        try:
            from ..knowledge.self_knowledge import KnowledgeEntry, KnowledgeType
        except Exception as e:
            logger.debug(f"KnowledgeEntry unavailable; skipping semantic store: {e}")
            return
        
        raw_type = metadata.pop("knowledge_type", None) or metadata.pop("type", None)
        try:
            k_type = KnowledgeType(raw_type) if raw_type else KnowledgeType.OBSERVATION
        except ValueError:
            k_type = KnowledgeType.OBSERVATION
        subject = metadata.pop("subject", None) or content[:60]
        tags = metadata.pop("tags", None) or []
        entry = KnowledgeEntry(
            id=str(uuid.uuid4()),
            type=k_type,
            subject=subject,
            content=content,
            rationale=metadata.pop("rationale", None),
            source=metadata.pop("source", "system"),
            confidence=float(metadata.pop("confidence", 1.0)),
            tags=list(tags),
            metadata=metadata,
        )
        self.self_knowledge.add(entry)
    
    async def _store_graph(self, content: str, memory_type: MemoryType, metadata: Dict):
        """Store in knowledge graph."""
        if hasattr(self.graph, 'add_node'):
            self.graph.add_node(content, memory_type.value, metadata)
    
    async def _update_access(self, memory_id: str):
        """Update access statistics."""
        if memory_id and memory_id in self.cache:
            self.cache[memory_id].last_accessed = time.time()
            self.cache[memory_id].access_count += 1
    
    async def _update_vector_importance(self, memory_id: str, amount: float):
        """Update importance in vector store."""
        # Implementation depends on vector store capabilities
        pass
    
    def _search_cache(self, query: str, limit: int) -> List[Dict]:
        """Simple cache search using substring matching."""
        results = []
        query_lower = query.lower()
        
        for memory_id, mem in self.cache.items():
            if query_lower in mem.content.lower():
                results.append({
                    "id": memory_id,
                    "content": mem.content,
                    "type": mem.memory_type.value,
                    "relevance": 0.6,  # Basic relevance for cache hits
                    "importance": mem.importance,
                    "metadata": mem.metadata
                })
        
        return results[:limit]
    
    def _cache_memory(self, memory: Memory):
        """Add memory to cache with LRU eviction."""
        if len(self.cache) >= self.cache_max_size:
            # Evict least recently accessed
            oldest = min(self.cache.values(), key=lambda m: m.last_accessed)
            del self.cache[oldest.id]
        
        self.cache[memory.id] = memory


class _EmbeddingManagerAdapter:
    """Adapt ``rag.embeddings.EmbeddingManager`` to the ``encode(text)`` shape
    expected by ``HybridMemorySystem._get_embedding``."""

    def __init__(self, manager):
        self.manager = manager

    def encode(self, text: str):
        return self.manager.encode_queries([text])[0]


# Global instance
_hybrid_memory: Optional[HybridMemorySystem] = None


def get_hybrid_memory() -> HybridMemorySystem:
    """Get global hybrid memory instance."""
    global _hybrid_memory
    if _hybrid_memory is None:
        _hybrid_memory = HybridMemorySystem()
    return _hybrid_memory
