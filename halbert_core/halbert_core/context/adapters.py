# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Service Adapters for Context Assembler

Adapters to connect existing Halbert services with the context assembler.
Based on research5.md Part 20.4.
"""

from __future__ import annotations
import asyncio
import inspect
import logging
import warnings
from typing import List, Dict, Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger('halbert.context.adapters')


class RAGServiceAdapter:
    """
    Adapter for the existing ChromaDB-backed RAG service.

    .. deprecated::
        RAGServiceAdapter is deprecated on the chat path — use
        :class:`SourcePrepAdapter` instead. Kept for CLI eval tooling
        and non-chat producers only.
    
    Provides async interface expected by ContextAssembler.
    """
    
    def __init__(self, chroma_index=None):
        """
        Initialize with optional ChromaDB index.
        
        Args:
            chroma_index: ChromaDB index instance
        """
        warnings.warn(
            "RAGServiceAdapter is deprecated on the chat path. "
            "Use SourcePrepAdapter instead. Kept for CLI eval only.",
            DeprecationWarning,
            stacklevel=2,
        )
        self._index = chroma_index
        self._initialized = False
    
    def _ensure_initialized(self):
        """Lazy initialization of the index."""
        if self._initialized:
            return
        
        if self._index is None:
            try:
                from ..index.chroma_index import get_index
                self._index = get_index()
                if self._index:
                    logger.info(f"RAG adapter initialized with ChromaDB index: {type(self._index).__name__}")
                else:
                    logger.warning("RAG adapter: get_index() returned None")
            except Exception as e:
                logger.warning(f"Could not initialize ChromaDB index: {e}", exc_info=True)
        
        self._initialized = True
    
    async def search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Search the RAG index.
        
        Args:
            query: Search query
            limit: Maximum results
            
        Returns:
            List of documents with content and metadata
        """
        self._ensure_initialized()
        
        if self._index is None:
            logger.warning("RAG index not available - returning empty results")
            return []
        
        try:
            logger.info(f"RAG searching for: {query[:50]}...")
            # Index.query returns list of dicts with 'content', 'distance', and metadata
            results = self._index.query(query, k=limit)
            logger.info(f"RAG search returned {len(results)} results")
            
            documents = []
            for item in results:
                documents.append({
                    'content': item.get('content', ''),
                    'metadata': {k: v for k, v in item.items() if k not in ('content', 'distance')},
                    'source': item.get('source', 'rag'),
                    'score': 1.0 - (item.get('distance', 0.5) or 0.5)
                })
            
            return documents
            
        except Exception as e:
            logger.error(f"RAG search error: {e}")
            return []


class DiscoveryServiceAdapter:
    """
    Adapter for the existing discovery service.
    
    Provides async interface expected by ContextAssembler.
    """
    
    def __init__(self, discovery_engine=None):
        """
        Initialize with optional discovery engine.
        
        Args:
            discovery_engine: Discovery engine instance
        """
        self._engine = discovery_engine
        self._initialized = False
    
    def _ensure_initialized(self):
        """Lazy initialization of the engine."""
        if self._initialized:
            return
        
        if self._engine is None:
            try:
                from ..discovery.engine import get_engine
                self._engine = get_engine()
                logger.info("Discovery adapter initialized")
            except Exception as e:
                logger.warning(f"Could not initialize discovery engine: {e}")
        
        self._initialized = True
    
    async def search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Search discoveries.
        
        Args:
            query: Search query
            limit: Maximum results
            
        Returns:
            List of discoveries with content and metadata
        """
        self._ensure_initialized()
        
        if self._engine is None:
            logger.debug("Discovery engine not available")
            return []
        
        try:
            results = self._engine.search(query, limit=limit)
            
            discoveries = []
            for disc in results:
                # Discovery is a dataclass, access attributes directly
                discoveries.append({
                    'content': disc.description or disc.title or '',
                    'category': str(disc.type.value) if hasattr(disc.type, 'value') else str(disc.type),
                    'metadata': {
                        'id': disc.id,
                        'name': disc.name,
                        'source': disc.source or 'discovery'
                    }
                })
            
            return discoveries
            
        except Exception as e:
            logger.error(f"Discovery search error: {e}")
            return []


class MemoryServiceAdapter:
    """
    Adapter for memory/self-knowledge service.
    
    Provides async interface expected by ContextAssembler.
    """
    
    def __init__(self, memory_service=None):
        """
        Initialize with optional memory service.
        
        Args:
            memory_service: Memory service instance
        """
        self._service = memory_service
        self._initialized = False
    
    def _ensure_initialized(self):
        """Lazy initialization of the service."""
        if self._initialized:
            return
        
        if self._service is None:
            try:
                from ..memory.hybrid import get_hybrid_memory
                self._service = get_hybrid_memory()
                logger.info("Memory adapter initialized")
            except Exception as e:
                logger.warning(f"Could not initialize memory service: {e}")
        
        self._initialized = True
    
    async def recall(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Recall relevant memories.
        
        Args:
            query: Search query
            limit: Maximum results
            
        Returns:
            List of memories with content and metadata
        """
        self._ensure_initialized()
        
        if self._service is None:
            logger.debug("Memory service not available")
            return []
        
        try:
            # Try different methods the memory service might have.
            # HybridMemorySystem.recall is preferred (returns content/type/metadata dicts).
            if hasattr(self._service, 'recall'):
                results = self._service.recall(query, limit=limit)
            elif hasattr(self._service, 'search'):
                results = self._service.search(query, limit=limit)
            elif hasattr(self._service, 'get_relevant'):
                results = self._service.get_relevant(query, limit=limit)
            else:
                logger.warning("Memory service has no search method")
                return []
            if inspect.isawaitable(results):
                results = await results
            
            memories = []
            for mem in results:
                if isinstance(mem, dict):
                    memories.append({
                        'content': mem.get('content', str(mem)),
                        'type': mem.get('type', 'memory'),
                        'metadata': mem.get('metadata', {})
                    })
                else:
                    memories.append({
                        'content': str(mem),
                        'type': 'memory',
                        'metadata': {}
                    })
            
            return memories
            
        except Exception as e:
            logger.error(f"Memory recall error: {e}")
            return []
    
    async def store_interaction(
        self,
        query: str,
        response: str,
        session_id: str = None
    ):
        """
        Store an interaction in memory.
        
        Args:
            query: User query
            response: Agent response
            session_id: Optional session ID
        """
        self._ensure_initialized()
        
        if self._service is None:
            return
        
        try:
            if hasattr(self._service, 'store_interaction'):
                # HybridMemorySystem truncates/filters itself; pass the full response
                res = self._service.store_interaction(
                    query=query, response=response, session_id=session_id
                )
            elif hasattr(self._service, 'store'):
                res = self._service.store({
                    'query': query,
                    'response': response[:500],  # Truncate long responses
                    'session_id': session_id,
                    'type': 'interaction'
                })
            elif hasattr(self._service, 'add'):
                res = self._service.add(f"Q: {query}\nA: {response[:500]}")
            else:
                return
            if inspect.isawaitable(res):
                await res
        except Exception as e:
            logger.error(f"Memory store error: {e}")


class SourcePrepAdapter:
    """Async adapter wrapping SourcePrepRetrievalBackend for ContextAssembler.

    SourcePrepRetrievalBackend.search() is synchronous (uses requests).
    This adapter wraps it with asyncio.to_thread() so the assembler can
    call it concurrently with other async sources.

    The adapter maps the assembler's expected interface (async search)
    to SourcePrep's sync interface, and normalizes result shape:
    SourcePrep returns dicts with 'text'/'source_path'/'score', while
    the assembler expects 'content'/'metadata'/'source'/'score'.
    """

    def __init__(
        self,
        backend=None,
        project_id: Optional[str] = None,
        base_url: Optional[str] = None,
        default_k: int = 5,
    ):
        """Args:
            backend: Optional pre-built SourcePrepRetrievalBackend instance.
                If None, one is created with project_id/base_url.
            project_id: SourcePrep project ID (for auto-creating backend).
            base_url: SourcePrep daemon URL (for auto-creating backend).
            default_k: Default number of results to retrieve.
        """
        if backend is not None:
            self._backend = backend
        else:
            from ..integrations.sourceprep_retrieval_backend import (
                SourcePrepRetrievalBackend,
            )
            self._backend = SourcePrepRetrievalBackend(
                project_id=project_id,
                base_url=base_url,
                default_k=default_k,
            )
        self._default_k = default_k

    def _route(self, query: str, *, scope: Optional[str] = None,
               role: Optional[str] = None) -> Optional[str]:
        """Decide the scope for this query: skill role, skill scope, heuristic.

        A skill that named a role wins, because it is the most specific thing
        anyone has said about the query. Only when no skill is active does the
        T-H1.3 keyword heuristic pick between the host config tree and the
        per-platform knowledge corpus; ambiguous stays unscoped.
        """
        if role:
            try:
                resolved = self._backend.resolve_role(role)
            except Exception:  # pragma: no cover - routing must never block
                resolved = None
            if resolved:
                return resolved
            logger.debug("role %r resolved to no scope; falling back", role)

        if scope:
            return scope

        try:
            from ..integrations.sourceprep_retrieval_backend import scope_for_query
            return scope_for_query(query)
        except Exception:  # pragma: no cover - routing must never block retrieval
            return None

    async def search(self, query: str, limit: int = 5, *,
                     scope: Optional[str] = None,
                     role: Optional[str] = None) -> List[Dict[str, Any]]:
        """Search SourcePrep asynchronously.

        Args:
            query: Natural language search query.
            limit: Maximum results (mapped to SourcePrep's k parameter).
            scope: Explicit scope id, from an active skill. Overrides the
                keyword heuristic below.
            role: Skill role, resolved locally to whichever scope carries it.
                Takes precedence over `scope`, and is why the role scopes
                (storage_admin, network_admin, service_admin) are reachable at
                all — scope_for_query() can only ever return None, "host", or
                "knowledge_<platform>".

        Returns:
            List of documents with 'content', 'metadata', 'source', 'score'.
            Empty list on error or if daemon is unreachable.
        """
        if not query.strip():
            return []

        k = limit or self._default_k
        scope = self._route(query, scope=scope, role=role)
        try:
            results = await asyncio.to_thread(
                self._backend.search, query, k=k, figure_id=scope
            )
        except Exception as e:
            logger.warning(f"SourcePrep adapter search failed: {e}")
            return []

        documents = []
        for item in results:
            text = item.get("text", "")
            if not text:
                continue
            documents.append({
                "content": text,
                "metadata": item.get("metadata", {}),
                "source": item.get("source_path", "sourceprep"),
                "score": item.get("score", 0.0),
            })
        return documents


def create_wired_context_assembler():
    """
    Create a ContextAssembler wired up with real services.

    Uses SourcePrepAdapter as the retrieval backend (Phase 2).
    RAGServiceAdapter is deprecated on the chat path.

    Returns:
        ContextAssembler with SourcePrep retrieval, discovery, and memory
    """
    from .assembler import ContextAssembler
    from .tokens import TokenCounter

    token_counter = TokenCounter()
    retrieval_adapter = SourcePrepAdapter()
    discovery_adapter = DiscoveryServiceAdapter()
    memory_adapter = MemoryServiceAdapter()

    return ContextAssembler(
        retrieval_service=retrieval_adapter,
        memory_service=memory_adapter,
        discovery_service=discovery_adapter,
        token_counter=token_counter,
    )
