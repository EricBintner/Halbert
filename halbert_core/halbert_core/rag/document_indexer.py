"""
Document Indexer for RAG

Indexes Linux documentation (man pages, Arch Wiki, vendor docs) into ChromaDB
for semantic search during chat.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class IndexStats:
    """Statistics for indexing operation."""
    total_docs: int = 0
    indexed_docs: int = 0
    skipped_docs: int = 0
    errors: int = 0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    collection: str = ""


def chunk_text(text: str, max_chars: int = 1200, overlap: int = 150) -> List[str]:
    """
    Split text into overlapping chunks with semantic boundary awareness.
    
    Research-aligned chunking strategy (DataCamp/RAPTOR):
    - Target ~300-400 tokens (1200 chars ≈ 300 tokens)
    - 10-15% overlap for context continuity
    - Respect semantic boundaries (headers, code blocks, lists)
    
    Args:
        text: Full document text
        max_chars: Maximum characters per chunk (~300 tokens)
        overlap: Overlap between chunks (~10% of max_chars)
    
    Returns:
        List of text chunks
    """
    if len(text) <= max_chars:
        return [text]
    
    chunks = []
    start = 0
    
    # Semantic boundary markers (priority order)
    HEADER_MARKERS = ['## ', '### ', '#### ', '# ', '\n---', '\n===']
    CODE_MARKERS = ['```', '~~~']
    
    while start < len(text):
        end = start + max_chars
        
        # Don't split past end of text
        if end >= len(text):
            chunk = text[start:].strip()
            if chunk:
                chunks.append(chunk)
            break
        
        # Try to find best break point (priority order)
        best_break = None
        min_pos = start + max_chars // 3  # Don't break too early
        
        # 1. Try header boundaries (strongest semantic break)
        for marker in HEADER_MARKERS:
            pos = text.rfind(marker, min_pos, end)
            if pos > min_pos:
                best_break = pos
                break
        
        # 2. Try paragraph break
        if best_break is None:
            para_break = text.rfind('\n\n', min_pos, end)
            if para_break > min_pos:
                best_break = para_break + 2
        
        # 3. Try list item break
        if best_break is None:
            for list_marker in ['\n- ', '\n* ', '\n• ', '\n1. ', '\n2. ']:
                pos = text.rfind(list_marker, min_pos, end)
                if pos > min_pos:
                    best_break = pos + 1  # Keep newline with next chunk
                    break
        
        # 4. Try sentence break
        if best_break is None:
            for sep in ['. ', '.\n', '! ', '? ', ':\n']:
                pos = text.rfind(sep, min_pos, end)
                if pos > min_pos:
                    best_break = pos + len(sep)
                    break
        
        # 5. Fallback to word boundary
        if best_break is None:
            space_pos = text.rfind(' ', min_pos, end)
            if space_pos > min_pos:
                best_break = space_pos + 1
            else:
                best_break = end  # Hard cut as last resort
        
        chunk = text[start:best_break].strip()
        if chunk:
            chunks.append(chunk)
        
        # Move start with overlap, but not past the break point
        start = max(best_break - overlap, start + 1)
    
    return chunks


def load_jsonl(filepath: Path) -> Iterator[Dict[str, Any]]:
    """Load documents from JSONL file."""
    with open(filepath, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as e:
                logger.warning(f"Invalid JSON at line {line_num}: {e}")
                continue


def index_documents(
    data_dir: Path,
    collection_name: str = "linux_docs",
    batch_size: int = 100,
    max_docs: Optional[int] = None,
    sources: Optional[List[str]] = None
) -> IndexStats:
    """
    Index Linux documentation into ChromaDB.
    
    Args:
        data_dir: Path to data/linux directory
        collection_name: ChromaDB collection name
        batch_size: Documents per batch insert
        max_docs: Maximum documents to index (None = all)
        sources: List of source directories to index (None = all)
    
    Returns:
        IndexStats with indexing results
    """
    from ..index.chroma_index import get_index
    
    stats = IndexStats(collection=collection_name)
    stats.started_at = datetime.now()
    
    index = get_index()
    col = index._collection(collection_name)
    
    if col is None:
        logger.error(f"Failed to get collection {collection_name}")
        return stats
    
    # Find all JSONL files
    data_path = Path(data_dir)
    if not data_path.exists():
        logger.error(f"Data directory not found: {data_path}")
        return stats
    
    jsonl_files = []
    for subdir in data_path.iterdir():
        if subdir.is_dir():
            if sources and subdir.name not in sources:
                continue
            for jsonl in subdir.glob("*.jsonl"):
                jsonl_files.append(jsonl)
    
    logger.info(f"Found {len(jsonl_files)} JSONL files to index")
    
    # Batch indexing
    batch_ids: List[str] = []
    batch_docs: List[str] = []
    batch_metas: List[Dict[str, str]] = []
    
    def flush_batch():
        """Flush current batch to ChromaDB."""
        if not batch_ids:
            return
        try:
            col.upsert(ids=batch_ids, documents=batch_docs, metadatas=batch_metas)
            stats.indexed_docs += len(batch_ids)
            logger.debug(f"Indexed batch of {len(batch_ids)} docs (total: {stats.indexed_docs})")
        except Exception as e:
            logger.error(f"Batch insert failed: {e}")
            stats.errors += len(batch_ids)
        batch_ids.clear()
        batch_docs.clear()
        batch_metas.clear()
    
    for jsonl_file in jsonl_files:
        source_name = jsonl_file.parent.name
        logger.info(f"Indexing {source_name}...")
        
        for doc in load_jsonl(jsonl_file):
            if max_docs and stats.total_docs >= max_docs:
                break
            
            stats.total_docs += 1
            
            # Handle both old schema (text/metadata) and new schema (content/title/source)
            text = doc.get("text") or doc.get("content", "")
            metadata = doc.get("metadata", {})
            
            if not text or len(text) < 50:
                stats.skipped_docs += 1
                continue
            
            # Extract key metadata - support both schemas
            source_type = metadata.get("source_type") or doc.get("source", source_name)
            title = (
                metadata.get("man_page") or 
                metadata.get("title") or 
                metadata.get("name") or
                doc.get("title", "")
            )
            
            # Extract freshness info
            scraped_at = doc.get("scraped_at") or metadata.get("scraped_at", "")
            
            # Chunk long documents (using improved semantic chunking)
            chunks = chunk_text(text, max_chars=1200)
            
            for i, chunk in enumerate(chunks):
                # Use content hash for deduplication - same content = same ID = upsert
                content_hash = hashlib.md5(chunk.encode()).hexdigest()[:12]
                doc_id = f"{source_name}:{title[:30]}:{i}:{content_hash}"
                
                # Include freshness metadata for retrieval scoring
                meta = {
                    "source": source_name,
                    "source_type": str(source_type),
                    "title": str(title)[:100],
                    "chunk": str(i),
                    "total_chunks": str(len(chunks)),
                    "indexed_at": datetime.now().isoformat(),
                    "scraped_at": str(scraped_at)[:25] if scraped_at else "",
                }
                
                batch_ids.append(doc_id)
                batch_docs.append(chunk)
                batch_metas.append(meta)
                
                if len(batch_ids) >= batch_size:
                    flush_batch()
        
        if max_docs and stats.total_docs >= max_docs:
            break
    
    # Flush remaining
    flush_batch()
    
    stats.completed_at = datetime.now()
    duration = (stats.completed_at - stats.started_at).total_seconds()
    
    logger.info(
        f"Indexing complete: {stats.indexed_docs} docs indexed, "
        f"{stats.skipped_docs} skipped, {stats.errors} errors "
        f"({duration:.1f}s)"
    )
    
    return stats


def get_default_data_dir() -> Path:
    """Get default data directory."""
    # Check common locations
    candidates = [
        Path(__file__).parent.parent.parent.parent / "data" / "linux",
        Path.home() / "LinuxBrain" / "data" / "linux",
        Path("/opt/halbert/data/linux"),
    ]
    for p in candidates:
        if p.exists():
            return p
    return candidates[0]


def index_all_docs(max_docs: Optional[int] = None) -> IndexStats:
    """
    Index all available Linux documentation.
    
    Convenience function to index everything.
    """
    data_dir = get_default_data_dir()
    return index_documents(
        data_dir=data_dir,
        collection_name="linux_docs",
        max_docs=max_docs
    )


def index_priority_docs(max_per_source: int = 500) -> Dict[str, IndexStats]:
    """
    Index priority documentation sources.
    
    Indexes the most useful sources first with limits.
    """
    data_dir = get_default_data_dir()
    
    # Priority sources for system administration
    priority_sources = [
        # Core documentation
        "man-pages",
        "arch-wiki-ext",
        # Phase 27 comprehensive guides
        "systemd-docs",
        "ubuntu-docs",
        "networking-docs",
        "filesystem-docs",
        "shell-docs",
        "security-docs",
        "containers-docs",
        "git-docs",
        "scheduling-docs",
        "logging-docs",
        "performance-docs",
        # Phase 26 app formats
        "flatpak-docs",
        "snap-docs",
        "appimage-docs",
        # Legacy sources
        "network-docs",
        "docker-docs",
        "backup-docs",
    ]
    
    results = {}
    for source in priority_sources:
        source_path = data_dir / source
        if source_path.exists():
            logger.info(f"Indexing priority source: {source}")
            stats = index_documents(
                data_dir=data_dir,
                collection_name="linux_docs",
                max_docs=max_per_source,
                sources=[source]
            )
            results[source] = stats
    
    return results


def expand_query(query: str) -> List[str]:
    """
    Expand query with synonyms and related terms for better recall.
    
    Research-aligned (HyDE-lite, multi-query retrieval):
    - Add common Linux command synonyms
    - Include related concepts
    """
    expansions = [query]  # Original query first
    query_lower = query.lower()
    
    # Common Linux synonyms and related terms
    SYNONYMS = {
        'folder': ['directory', 'dir'],
        'directory': ['folder', 'dir'],
        'delete': ['remove', 'rm'],
        'remove': ['delete', 'rm'],
        'copy': ['cp'],
        'move': ['mv'],
        'list': ['ls'],
        'permission': ['chmod', 'access rights'],
        'owner': ['chown', 'ownership'],
        'process': ['pid', 'task'],
        'service': ['systemd', 'daemon', 'unit'],
        'package': ['apt', 'dnf', 'pacman'],
        'network': ['ip', 'interface', 'connection'],
        'disk': ['storage', 'drive', 'partition'],
        'memory': ['ram', 'swap'],
        'cpu': ['processor', 'core'],
    }
    
    # Add synonyms if found
    for term, syns in SYNONYMS.items():
        if term in query_lower:
            for syn in syns[:2]:  # Limit expansions
                expanded = query_lower.replace(term, syn)
                if expanded != query_lower:
                    expansions.append(expanded)
    
    return expansions[:3]  # Max 3 query variants


def query_docs(
    query: str, 
    k: int = 5, 
    use_reranking: bool = True,
    use_expansion: bool = True
) -> List[Dict[str, Any]]:
    """
    Query indexed documents with optional reranking and query expansion.
    
    Research-aligned retrieval (Self-RAG, CRAG):
    - Query expansion for better recall
    - Cross-encoder reranking for better precision
    
    Args:
        query: Search query
        k: Number of results
        use_reranking: Enable cross-encoder reranking (slower but better)
        use_expansion: Enable query expansion
    
    Returns:
        List of relevant document chunks with metadata
    """
    from ..index.chroma_index import get_index
    
    index = get_index()
    
    # Expand query if enabled
    queries = expand_query(query) if use_expansion else [query]
    
    # Retrieve more candidates if reranking
    retrieve_k = k * 3 if use_reranking else k
    
    # Collect results from all query variants
    all_results = []
    seen_ids = set()
    
    for q in queries:
        results = index.query(text=q, k=retrieve_k, collection="linux_docs")
        for r in results:
            # Deduplicate by content hash
            content_key = r.get('content', '')[:100]
            if content_key not in seen_ids:
                seen_ids.add(content_key)
                all_results.append(r)
    
    # Rerank if enabled and we have results
    if use_reranking and len(all_results) > k:
        try:
            from .embeddings import EmbeddingManager
            em = EmbeddingManager()
            
            # Extract content for reranking
            contents = [r.get('content', '') for r in all_results]
            
            # Rerank
            reranked = em.rerank(query, contents, top_k=k)
            
            # Rebuild results in new order with rerank scores
            final_results = []
            for idx, score in reranked:
                result = all_results[idx].copy()
                result['rerank_score'] = float(score)
                final_results.append(result)
            
            return final_results
        except Exception as e:
            logger.warning(f"Reranking failed, returning unranked: {e}")
    
    return all_results[:k]


def get_index_stats() -> Dict[str, Any]:
    """Get statistics about the document index."""
    from ..index.chroma_index import get_index
    
    index = get_index()
    stats = index.get_stats()
    
    # Get linux_docs count
    linux_docs = stats.get("collections", {}).get("linux_docs", 0)
    if linux_docs == "error":
        linux_docs = 0
    
    # Build collections dict with only numeric values
    collections = {}
    for name, count in stats.get("collections", {}).items():
        if isinstance(count, int):
            collections[name] = count
    
    return {
        "linux_docs_count": linux_docs,
        "total_docs": sum(v for v in collections.values() if isinstance(v, int)),
        "collections": collections,
    }
