# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
ChromaDB-backed index for Halbert memory and knowledge storage.

Uses persistent ChromaDB with separate collections for:
- self_hwmon: Hardware sensor events
- self_journald: System log events
- self_dbus: D-Bus events
- self_conversations: Chat history for context retrieval (migrated to
  HybridMemorySystem in Phase 2 — kept for backward compat)
- self_knowledge_all: Global knowledge index (migrated to SourcePrep
  observations in Phase 2 — kept for backward compat)

Phase 2 RAG Consolidation:
    The chat path now uses SourcePrep as the sole retrieval backend.
    ChromaDB is retired from the chat path but kept for non-chat
    producers and eval tooling. The following 4 collections stay on
    ChromaDB until their producers are rewired to SourcePrep:

    1. self_hwmon      — hardware sensor events (producer: obs loop)
    2. self_journald   — system log events (producer: journald reader)
    3. self_dbus       — D-Bus events (producer: dbus monitor)
    4. discoveries     — system discovery results (producer: discovery engine)

    The following 2 collections have been migrated and are kept only
    for backward compatibility / eval:

    5. self_conversations  — migrated to HybridMemorySystem (Phase 2)
    6. self_knowledge_all  — migrated to SourcePrep observations (Phase 2)

    Migration scripts:
        python -m halbert_core.tools.migrate_self_knowledge --apply
        python -m halbert_core.tools.migrate_conversations --apply

Text for embedding: f"{message} {compact(data)}"; metadata filters per docs.
"""
from __future__ import annotations
from typing import Dict, Any, List, Optional
from pathlib import Path
import logging

logger = logging.getLogger('halbert.index')

try:
    import chromadb
    CHROMADB_AVAILABLE = True
except ImportError:
    chromadb = None  # type: ignore
    CHROMADB_AVAILABLE = False


def _compact_text(event: Dict[str, Any]) -> str:
    """Create searchable text from event."""
    msg = str(event.get("message", ""))
    data = event.get("data")
    if isinstance(data, dict):
        parts = [f"{k}={v}" for k, v in data.items()]
        return (msg + " " + " ".join(parts)).strip()
    return msg


class _MemoryIndex:
    """In-memory fallback when ChromaDB is unavailable."""
    
    def __init__(self, max_events: int = 10000) -> None:
        self.events: List[Dict[str, Any]] = []
        self.max_events = max_events

    def upsert(self, *events: Dict[str, Any]) -> None:
        self.events.extend(events)
        # Trim to max size
        if len(self.events) > self.max_events:
            self.events = self.events[-self.max_events:]

    def query(self, text: str, k: int = 5) -> List[Dict[str, Any]]:
        """Simple recency-based retrieval."""
        return list(reversed(self.events))[:k]
    
    def search(self, text: str, k: int = 5) -> List[Dict[str, Any]]:
        """Basic text matching search."""
        text_lower = text.lower()
        matches = []
        for event in reversed(self.events):
            event_text = _compact_text(event).lower()
            if text_lower in event_text:
                matches.append(event)
                if len(matches) >= k:
                    break
        return matches if matches else self.query(text, k)


class Index:
    """
    ChromaDB-backed persistent index with in-memory fallback.
    
    Provides semantic search over system events and conversations.
    """
    
    def __init__(self, persist_path: Optional[str] = None) -> None:
        self.mem = _MemoryIndex()
        self.client = None
        self.collections: Dict[str, Any] = {}
        self._persist_path = persist_path
        
        if CHROMADB_AVAILABLE:
            self._init_chromadb()
    
    def _init_chromadb(self) -> None:
        """Initialize ChromaDB client."""
        try:
            if self._persist_path:
                # Persistent storage
                Path(self._persist_path).mkdir(parents=True, exist_ok=True)
                self.client = chromadb.PersistentClient(path=self._persist_path)
            else:
                # Default persistent location
                default_path = Path.home() / ".local" / "share" / "halbert" / "chromadb"
                default_path.mkdir(parents=True, exist_ok=True)
                self.client = chromadb.PersistentClient(path=str(default_path))
            
            logger.info(f"ChromaDB initialized at {self._persist_path or default_path}")
        except Exception as e:
            logger.warning(f"ChromaDB init failed ({e}), using in-memory fallback")
            self.client = None

    def _get_embedding_function(self):
        """Get ChromaDB embedding function for consistent embeddings."""
        if not hasattr(self, '_embedding_fn'):
            try:
                from chromadb.utils import embedding_functions
                # Use same model as EmbeddingManager for consistency
                self._embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
                    model_name="all-MiniLM-L6-v2"
                )
            except Exception as e:
                logger.warning(f"Could not load embedding function: {e}")
                self._embedding_fn = None
        return self._embedding_fn
    
    def _collection(self, name: str, use_custom_embedding: bool = False):
        """
        Get or create a collection.
        
        Args:
            name: Collection name
            use_custom_embedding: If True and creating new collection, use custom embedding.
                                  Existing collections keep their original embedding function.
        """
        if self.client is None:
            return None
        if name in self.collections:
            return self.collections[name]
        try:
            # First try to get existing collection (preserves its embedding function)
            try:
                col = self.client.get_collection(name=name)
                self.collections[name] = col
                return col
            except Exception:
                pass  # Collection doesn't exist, create it
            
            # Create new collection - use custom embedding for new linux_docs collections
            if use_custom_embedding:
                embedding_fn = self._get_embedding_function()
                if embedding_fn:
                    col = self.client.create_collection(
                        name=name,
                        embedding_function=embedding_fn
                    )
                else:
                    col = self.client.create_collection(name=name)
            else:
                col = self.client.create_collection(name=name)
            
            self.collections[name] = col
            return col
        except Exception as e:
            logger.warning(f"Failed to get collection {name}: {e}")
            return None

    def upsert_event(self, event: Dict[str, Any]) -> None:
        """Store an event in the index."""
        text = _compact_text(event)
        meta = {k: str(event.get(k, "")) for k in 
                ("source", "host", "ts", "type", "subsystem", "severity", "tags", "hash")
                if event.get(k) is not None}
        doc_id = event.get("hash") or f"{event.get('source','evt')}:{event.get('ts','')}:{len(text)}"
        src = str(event.get("source", "misc"))
        col_name = {
            "hwmon": "self_hwmon",
            "journald": "self_journald",
            "dbus": "self_dbus",
            "ebpf": "self_ebpf",
            "conversation": "self_conversations",
        }.get(src, f"self_{src}")

        # Memory fallback
        self.mem.upsert(event)

        # Chroma collections
        for name in (col_name, "self_knowledge_all"):
            col = self._collection(name)
            if col is not None:
                try:
                    col.upsert(ids=[doc_id], documents=[text], metadatas=[meta])
                except Exception as e:
                    logger.debug(f"Failed to upsert to {name}: {e}")

    def upsert_conversation(
        self, 
        conversation_id: str,
        message: str,
        role: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Store a conversation message for context retrieval.
        
        Args:
            conversation_id: Unique conversation identifier
            message: Message content
            role: 'user' or 'assistant'
            metadata: Additional metadata (page, mentions, etc.)
        """
        import time
        
        doc_id = f"conv:{conversation_id}:{int(time.time() * 1000)}"
        meta = {
            "conversation_id": conversation_id,
            "role": role,
            "timestamp": str(int(time.time())),
            **(metadata or {})
        }
        
        # Store in conversations collection
        col = self._collection("self_conversations")
        if col is not None:
            try:
                col.upsert(ids=[doc_id], documents=[message], metadatas=[meta])
            except Exception as e:
                logger.debug(f"Failed to store conversation: {e}")
        
        # Also store in global knowledge for cross-conversation retrieval
        col = self._collection("self_knowledge_all")
        if col is not None:
            try:
                col.upsert(ids=[doc_id], documents=[message], metadatas=[meta])
            except Exception as e:
                logger.debug(f"Failed to store in knowledge: {e}")

    def query(
        self, 
        text: str, 
        k: int = 5, 
        collection: Optional[str] = None,
        where: Optional[Dict[str, Any]] = None,
        where_document: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Query the index for relevant events with optional metadata filtering.
        
        Args:
            text: Query text
            k: Number of results
            collection: Specific collection to query (default: self_knowledge_all)
            where: Metadata filter (e.g., {"source": "arch-wiki"})
            where_document: Document content filter (e.g., {"$contains": "systemd"})
            
        Returns:
            List of matching events with metadata
        """
        col_name = collection or "self_knowledge_all"
        col = self._collection(col_name)
        
        if col is not None:
            try:
                # Build query kwargs
                query_kwargs = {"query_texts": [text], "n_results": k}
                if where:
                    query_kwargs["where"] = where
                if where_document:
                    query_kwargs["where_document"] = where_document
                
                res = col.query(**query_kwargs)
                if res and res.get("metadatas") and res.get("documents"):
                    results = []
                    for i, meta in enumerate(res["metadatas"][0]):
                        results.append({
                            **meta,
                            "content": res["documents"][0][i] if res["documents"][0] else "",
                            "distance": res.get("distances", [[]])[0][i] if res.get("distances") else None
                        })
                    return results
            except Exception as e:
                logger.warning(f"ChromaDB query failed: {e}")
        
        return self.mem.search(text, k)
    
    def query_conversations(
        self, 
        query: str, 
        k: int = 5,
        conversation_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Query past conversations for relevant context.
        
        Args:
            query: Query text
            k: Number of results
            conversation_id: Filter to specific conversation
            
        Returns:
            List of relevant conversation snippets
        """
        col = self._collection("self_conversations")
        if col is None:
            return []
        
        try:
            if conversation_id:
                # Filter by conversation ID
                res = col.query(
                    query_texts=[query],
                    n_results=k,
                    where={"conversation_id": conversation_id}
                )
            else:
                res = col.query(query_texts=[query], n_results=k)
            
            if res and res.get("metadatas") and res.get("documents"):
                results = []
                for i, meta in enumerate(res["metadatas"][0]):
                    results.append({
                        **meta,
                        "content": res["documents"][0][i] if res["documents"][0] else "",
                        "distance": res.get("distances", [[]])[0][i] if res.get("distances") else None
                    })
                return results
        except Exception as e:
            logger.warning(f"Conversation query failed: {e}")
        
        return []
    
    def get_stats(self) -> Dict[str, Any]:
        """Get index statistics."""
        import sys
        collections = {}
        
        logger.info("get_stats: starting...")
        logger.info(f"get_stats: client={self.client is not None}")
        
        if self.client is not None:
            try:
                logger.info("get_stats: calling list_collections...")
                sys.stdout.flush()
                all_cols = self.client.list_collections()
                logger.info(f"get_stats: found {len(all_cols)} collections")
                
                for i, col in enumerate(all_cols):
                    col_name = col.name
                    logger.info(f"get_stats: [{i+1}/{len(all_cols)}] processing '{col_name}'...")
                    sys.stdout.flush()
                    try:
                        logger.info(f"get_stats: [{i+1}] calling count() on '{col_name}'...")
                        sys.stdout.flush()
                        count = col.count()
                        logger.info(f"get_stats: [{i+1}] '{col_name}' count = {count}")
                        collections[col_name] = count
                    except Exception as e:
                        logger.warning(f"get_stats: [{i+1}] FAILED to count '{col_name}': {e}")
                        collections[col_name] = "error"
                        
                logger.info(f"get_stats: finished all collections, total={sum(v for v in collections.values() if isinstance(v, int))}")
            except Exception as e:
                logger.error(f"get_stats: FAILED to list collections: {e}")
        else:
            logger.info("get_stats: no client available")
        
        default_path = Path.home() / ".local" / "share" / "halbert" / "chromadb"
        result = {
            "chromadb_available": self.client is not None,
            "persist_path": self._persist_path or str(default_path),
            "memory_events": len(self.mem.events),
            "collections": collections
        }
        logger.info(f"get_stats: returning result with {len(collections)} collections")
        return result
    
    def list_collections(self) -> List[Dict[str, Any]]:
        """List all collections with their counts."""
        collections = []
        known_names = ["self_knowledge_all", "self_conversations", "self_hwmon", "self_journald", "self_dbus", "linux_docs", "discoveries"]
        
        if self.client is not None:
            try:
                # Get all collections from ChromaDB
                all_cols = self.client.list_collections()
                for col in all_cols:
                    try:
                        count = col.count()
                        collections.append({
                            "name": col.name,
                            "count": count,
                            "known": col.name in known_names
                        })
                    except Exception:
                        collections.append({"name": col.name, "count": 0, "known": col.name in known_names})
            except Exception as e:
                logger.warning(f"Failed to list collections: {e}")
        
        return sorted(collections, key=lambda c: (-c.get("count", 0), c["name"]))
    
    def list_entries(
        self, 
        collection: str, 
        limit: int = 50, 
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        List entries in a collection with pagination.
        
        Args:
            collection: Collection name
            limit: Max entries to return
            offset: Skip this many entries
            
        Returns:
            List of entries with id, content, metadata
        """
        col = self._collection(collection)
        if col is None:
            return []
        
        try:
            # Get all entries (ChromaDB doesn't have great pagination)
            result = col.get(limit=limit + offset, include=["documents", "metadatas"])
            
            entries = []
            ids = result.get("ids", [])
            docs = result.get("documents", [])
            metas = result.get("metadatas", [])
            
            # Apply offset
            for i in range(offset, min(len(ids), offset + limit)):
                entries.append({
                    "id": ids[i],
                    "content": docs[i] if docs and i < len(docs) else "",
                    "metadata": metas[i] if metas and i < len(metas) else {}
                })
            
            return entries
        except Exception as e:
            logger.warning(f"Failed to list entries: {e}")
            return []
    
    def get_entry(self, collection: str, entry_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific entry by ID."""
        col = self._collection(collection)
        if col is None:
            return None
        
        try:
            result = col.get(ids=[entry_id], include=["documents", "metadatas"])
            if result and result.get("ids"):
                return {
                    "id": result["ids"][0],
                    "content": result["documents"][0] if result.get("documents") else "",
                    "metadata": result["metadatas"][0] if result.get("metadatas") else {}
                }
        except Exception as e:
            logger.warning(f"Failed to get entry: {e}")
        
        return None
    
    def delete_entry(self, collection: str, entry_id: str) -> bool:
        """Delete a specific entry."""
        col = self._collection(collection)
        if col is None:
            return False
        
        try:
            col.delete(ids=[entry_id])
            logger.info(f"Deleted entry {entry_id} from {collection}")
            return True
        except Exception as e:
            logger.warning(f"Failed to delete entry: {e}")
            return False
    
    def delete_entries(self, collection: str, entry_ids: List[str]) -> int:
        """Delete multiple entries. Returns count deleted."""
        col = self._collection(collection)
        if col is None:
            return 0
        
        try:
            col.delete(ids=entry_ids)
            logger.info(f"Deleted {len(entry_ids)} entries from {collection}")
            return len(entry_ids)
        except Exception as e:
            logger.warning(f"Failed to delete entries: {e}")
            return 0
    
    def clear_collection(self, collection: str) -> bool:
        """Clear all entries from a collection."""
        if self.client is None:
            return False
        
        try:
            # Delete and recreate the collection
            self.client.delete_collection(name=collection)
            if collection in self.collections:
                del self.collections[collection]
            logger.info(f"Cleared collection {collection}")
            return True
        except Exception as e:
            logger.warning(f"Failed to clear collection: {e}")
            return False


# Singleton instance
_index: Optional[Index] = None


def get_index(persist_path: Optional[str] = None) -> Index:
    """Get the global index instance."""
    global _index
    if _index is None:
        _index = Index(persist_path=persist_path)
    return _index
