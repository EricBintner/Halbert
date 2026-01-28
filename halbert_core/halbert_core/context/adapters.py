"""
Service Adapters for Context Assembler

Adapters to connect existing Halbert services with the context assembler.
Based on research5.md Part 20.4.
"""

from __future__ import annotations
import logging
from typing import List, Dict, Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger('halbert.context.adapters')


class RAGServiceAdapter:
    """
    Adapter for the existing RAG service.
    
    Provides async interface expected by ContextAssembler.
    """
    
    def __init__(self, chroma_index=None):
        """
        Initialize with optional ChromaDB index.
        
        Args:
            chroma_index: ChromaDB index instance
        """
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
                from ..memory.store import get_memory_store
                self._service = get_memory_store()
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
            # Try different methods the memory service might have
            if hasattr(self._service, 'search'):
                results = self._service.search(query, limit=limit)
            elif hasattr(self._service, 'recall'):
                results = self._service.recall(query, limit=limit)
            elif hasattr(self._service, 'get_relevant'):
                results = self._service.get_relevant(query, limit=limit)
            else:
                logger.warning("Memory service has no search method")
                return []
            
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
            if hasattr(self._service, 'store'):
                self._service.store({
                    'query': query,
                    'response': response[:500],  # Truncate long responses
                    'session_id': session_id,
                    'type': 'interaction'
                })
            elif hasattr(self._service, 'add'):
                self._service.add(f"Q: {query}\nA: {response[:500]}")
        except Exception as e:
            logger.error(f"Memory store error: {e}")


def create_wired_context_assembler():
    """
    Create a ContextAssembler wired up with real services.
    
    Returns:
        ContextAssembler with RAG, discovery, and memory adapters
    """
    from .assembler import ContextAssembler
    from .tokens import TokenCounter
    
    token_counter = TokenCounter()
    rag_adapter = RAGServiceAdapter()
    discovery_adapter = DiscoveryServiceAdapter()
    memory_adapter = MemoryServiceAdapter()
    
    return ContextAssembler(
        rag_service=rag_adapter,
        memory_service=memory_adapter,
        discovery_service=discovery_adapter,
        token_counter=token_counter
    )
