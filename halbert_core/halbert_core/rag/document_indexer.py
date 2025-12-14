"""
Document Indexer for RAG

Indexes Linux documentation (man pages, Arch Wiki, vendor docs) into ChromaDB
for semantic search during chat.
"""
from __future__ import annotations

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


def chunk_text(text: str, max_chars: int = 1500, overlap: int = 200) -> List[str]:
    """
    Split text into overlapping chunks for better retrieval.
    
    Args:
        text: Full document text
        max_chars: Maximum characters per chunk
        overlap: Overlap between chunks
    
    Returns:
        List of text chunks
    """
    if len(text) <= max_chars:
        return [text]
    
    chunks = []
    start = 0
    
    while start < len(text):
        end = start + max_chars
        
        # Try to break at paragraph or sentence boundary
        if end < len(text):
            # Look for paragraph break
            para_break = text.rfind('\n\n', start, end)
            if para_break > start + max_chars // 2:
                end = para_break + 2
            else:
                # Look for sentence break
                for sep in ['. ', '.\n', '! ', '? ']:
                    sent_break = text.rfind(sep, start, end)
                    if sent_break > start + max_chars // 2:
                        end = sent_break + len(sep)
                        break
        
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        
        start = end - overlap
        if start >= len(text):
            break
    
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
            
            text = doc.get("text", "")
            metadata = doc.get("metadata", {})
            
            if not text or len(text) < 50:
                stats.skipped_docs += 1
                continue
            
            # Extract key metadata
            source_type = metadata.get("source_type", source_name)
            title = metadata.get("man_page") or metadata.get("title") or metadata.get("name", "")
            
            # Chunk long documents
            chunks = chunk_text(text, max_chars=1500)
            
            for i, chunk in enumerate(chunks):
                doc_id = f"{source_type}:{title}:{i}" if title else f"{source_name}:{stats.total_docs}:{i}"
                
                meta = {
                    "source": source_name,
                    "source_type": str(source_type),
                    "title": str(title)[:100],
                    "chunk": str(i),
                    "total_chunks": str(len(chunks)),
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
        "man-pages",
        "systemd-docs",
        "arch-wiki-ext",
        "network-docs",
        "filesystem-docs",
        "security-docs",
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


def query_docs(query: str, k: int = 5) -> List[Dict[str, Any]]:
    """
    Query indexed documents.
    
    Args:
        query: Search query
        k: Number of results
    
    Returns:
        List of relevant document chunks with metadata
    """
    from ..index.chroma_index import get_index
    
    index = get_index()
    results = index.query(text=query, k=k, collection="linux_docs")
    return results


def get_index_stats() -> Dict[str, Any]:
    """Get statistics about the document index."""
    from ..index.chroma_index import get_index
    
    index = get_index()
    stats = index.stats()
    
    linux_docs = stats.get("collections", {}).get("linux_docs", 0)
    
    return {
        "linux_docs_count": linux_docs,
        "total_docs": sum(stats.get("collections", {}).values()),
        "collections": stats.get("collections", {}),
    }
