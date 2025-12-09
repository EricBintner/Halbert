"""
End-to-end RAG pipeline for Cerebric.

Orchestrates retrieval, context building, and integration with LLM.
"""

import logging
from typing import List, Dict, Any, Optional
from pathlib import Path
from dataclasses import dataclass, asdict
import json

from .embeddings import EmbeddingManager
from .retriever import HybridRetriever

logger = logging.getLogger('cerebric')


@dataclass
class RAGResponse:
    """RAG pipeline response with answer and sources."""
    query: str
    answer: str
    sources: List[Dict[str, Any]]
    retrieved_count: int
    latency_ms: float
    metadata: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


class RAGPipeline:
    """
    End-to-end RAG pipeline.
    
    Handles document loading, indexing, retrieval, and context building
    for integration with LLM generation.
    """
    
    def __init__(
        self,
        data_dir: Path,
        embedding_model: str = "all-MiniLM-L6-v2",
        use_reranking: bool = True,
        top_k: int = 5,
        max_context_length: int = 4096
    ):
        """
        Initialize RAG pipeline.
        
        Args:
            data_dir: Directory containing document data
            embedding_model: Embedding model name
            use_reranking: Enable cross-encoder reranking
            top_k: Number of documents to retrieve
            max_context_length: Max tokens for context
        """
        self.data_dir = Path(data_dir)
        self.use_reranking = use_reranking
        self.top_k = top_k
        self.max_context_length = max_context_length
        
        # Initialize components
        self.embedding_manager = EmbeddingManager(
            embedding_model=embedding_model,
            cache_dir=self.data_dir / '.cache'
        )
        
        self.retriever = HybridRetriever(
            embedding_manager=self.embedding_manager,
            bm25_weight=0.5,
            dense_weight=0.5
        )
        
        self._indexed = False
        
        logger.info(f"Initialized RAGPipeline with data_dir={data_dir}")
    
    def load_and_index_documents(
        self,
        jsonl_path: Optional[Path] = None,
        documents: Optional[List[Dict[str, Any]]] = None
    ):
        """
        Load and index documents.
        
        Args:
            jsonl_path: Path to JSONL file with documents
            documents: Or provide documents directly as list of dicts
        """
        if documents is None:
            if jsonl_path is None:
                # Default to merged RAG corpus
                merged_path = self.data_dir / 'linux' / 'merged' / 'rag_corpus_merged.jsonl'
                if merged_path.exists():
                    jsonl_path = merged_path
                else:
                    # Fallback to old man pages
                    jsonl_path = self.data_dir / 'linux' / 'man-pages' / 'man_pages.jsonl'
            
            logger.info(f"Loading documents from {jsonl_path}")
            documents = self._load_jsonl(jsonl_path)
        
        logger.info(f"Indexing {len(documents)} documents")
        
        # Normalize documents (handle old schema)
        documents = self._normalize_documents(documents)
        
        # Prepare documents for indexing
        indexed_docs = []
        for doc in documents:
            # Create searchable content
            content = self._format_document_content(doc)
            
            indexed_docs.append({
                'id': doc.get('name', doc.get('id', 'unknown')),
                'content': content,
                'name': doc.get('name', ''),
                'section': doc.get('section', ''),
                'description': doc.get('description', ''),
                'full_text': doc.get('full_text', ''),
                'metadata': doc
            })
        
        # Index documents
        self.retriever.index_documents(
            indexed_docs,
            text_field='content',
            id_field='id'
        )
        
        self._indexed = True
        logger.info(f"Indexed {len(indexed_docs)} documents")
    
    def _load_jsonl(self, path: Path) -> List[Dict[str, Any]]:
        """Load documents from JSONL file."""
        documents = []
        
        if not path.exists():
            logger.warning(f"Document file not found: {path}")
            return documents
        
        with open(path, 'r') as f:
            for line in f:
                try:
                    doc = json.loads(line.strip())
                    documents.append(doc)
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse line: {e}")
                    continue
        
        logger.info(f"Loaded {len(documents)} documents from {path}")
        return documents
    
    def _normalize_documents(self, documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Normalize document schema.
        
        Handles old schema: {"text": "...", "metadata": {"man_page": "name(section)"}}
        Converts to: {"name": "...", "section": "...", "full_text": "..."}
        """
        normalized = []
        
        for doc in documents:
            # If already in new schema, keep as-is
            if 'name' in doc and 'full_text' in doc:
                normalized.append(doc)
                continue
            
            # Handle 'content' field (Phase 10 user-added docs)
            if 'name' in doc and 'content' in doc:
                doc['full_text'] = doc['content']
                normalized.append(doc)
                continue
            
            # Convert old schema
            if 'text' in doc and 'metadata' in doc:
                text = doc['text']
                metadata = doc['metadata']
                
                # Try to extract name from metadata.man_page (old man pages format)
                man_page = metadata.get('man_page', '')
                name = ''
                section = ''
                
                if '(' in man_page and ')' in man_page:
                    name = man_page.split('(')[0].strip()
                    section = man_page.split('(')[1].split(')')[0].strip()
                elif man_page:
                    name = man_page
                else:
                    # Vendor docs format: extract title from text or URL
                    lines = text.split('\n')
                    # Try first non-empty line as title
                    for line in lines[:5]:
                        line = line.strip()
                        if line and len(line) > 3 and len(line) < 200:
                            # Clean up common doc titles
                            name = line.replace('—', '-').replace('»', '').strip()
                            if name:
                                break
                    
                    # Fallback: use URL path
                    if not name:
                        url = metadata.get('attribution_url', '')
                        if url:
                            # Extract last part of URL as name
                            name = url.rstrip('/').split('/')[-1].replace('-', ' ')
                
                # Extract description from first few lines
                description = ''
                for line in text.split('\n')[:15]:
                    line = line.strip()
                    if line and len(line) > 20 and len(line) < 300:
                        # Skip lines that are just the title
                        if name and line.lower() != name.lower():
                            description = line[:200]
                            break
                
                normalized.append({
                    'name': name or 'Unknown',
                    'section': section,
                    'description': description,
                    'full_text': text,
                    'metadata': metadata
                })
            else:
                # Unknown schema, keep as-is
                normalized.append(doc)
        
        return normalized
    
    def _format_document_content(self, doc: Dict[str, Any]) -> str:
        """
        Format document for indexing.
        
        Combines name, description, and full text for better retrieval.
        """
        parts = []
        
        # Add name and section
        name = doc.get('name', '')
        section = doc.get('section', '')
        if name:
            if section:
                parts.append(f"{name}({section})")
            else:
                parts.append(name)
        
        # Add description
        description = doc.get('description', '')
        if description:
            parts.append(description)
        
        # Add full text (truncate if too long)
        full_text = doc.get('full_text', '')
        if full_text:
            # Limit to ~2000 chars for indexing
            if len(full_text) > 2000:
                full_text = full_text[:2000] + '...'
            parts.append(full_text)
        
        return '\n\n'.join(parts)
    
    def retrieve(self, query: str) -> List[Dict[str, Any]]:
        """
        Retrieve relevant documents for query.
        
        Args:
            query: User query
            
        Returns:
            List of retrieved documents with scores
        """
        if not self._indexed:
            logger.error("Documents not indexed. Call load_and_index_documents() first")
            return []
        
        import time
        start = time.time()
        
        # Retrieve with or without reranking
        if self.use_reranking:
            results = self.retriever.retrieve_and_rerank(
                query,
                top_k=self.top_k,
                retrieve_k=self.top_k * 4  # Cast wider net before reranking
            )
        else:
            results = self.retriever.retrieve_hybrid(
                query,
                top_k=self.top_k
            )
        
        latency = (time.time() - start) * 1000
        
        logger.info(
            f"Retrieved {len(results)} documents in {latency:.1f}ms "
            f"(reranking={'on' if self.use_reranking else 'off'})"
        )
        
        # Convert to dict format
        documents = []
        for result in results:
            doc = {
                'doc_id': result.doc_id,
                'score': result.score,
                'name': result.metadata.get('name', result.doc_id),
                'section': result.metadata.get('section', ''),
                'description': result.metadata.get('description', ''),
                'content': result.content,
                'full_text': result.metadata.get('full_text', ''),
                'source': result.source,
            }
            # Preserve original metadata for source attribution (Phase 10)
            if 'metadata' in result.metadata:
                doc['metadata'] = result.metadata['metadata']
            documents.append(doc)
        
        return documents
    
    def build_context(
        self,
        query: str,
        documents: List[Dict[str, Any]]
    ) -> str:
        """
        Build context string for LLM from retrieved documents.
        
        Args:
            query: User query
            documents: Retrieved documents
            
        Returns:
            Formatted context string
        """
        if not documents:
            return ""
        
        # Format context
        context_parts = [
            "# Relevant Documentation\n",
            f"Query: {query}\n"
        ]
        
        for i, doc in enumerate(documents, 1):
            name = doc.get('name', 'Unknown')
            section = doc.get('section', '')
            description = doc.get('description', '')
            
            # Header
            if section:
                context_parts.append(f"\n## {i}. {name}({section})")
            else:
                context_parts.append(f"\n## {i}. {name}")
            
            # Description
            if description:
                context_parts.append(f"{description}\n")
            
            # Content (truncate if needed)
            content = doc.get('full_text', doc.get('content', ''))
            if content:
                # Rough token estimate: 1 token ≈ 4 chars
                max_chars = (self.max_context_length // len(documents)) * 4
                if len(content) > max_chars:
                    content = content[:max_chars] + '...'
                context_parts.append(content)
        
        context = '\n'.join(context_parts)
        
        logger.debug(f"Built context with {len(documents)} documents (~{len(context)} chars)")
        return context
    
    def query(
        self,
        query: str,
        llm_generate_fn=None,
        return_sources: bool = True
    ) -> RAGResponse:
        """
        End-to-end RAG query.
        
        Args:
            query: User query
            llm_generate_fn: Optional LLM generation function (query, context) -> answer
            return_sources: Include source documents in response
            
        Returns:
            RAGResponse with answer and sources
        """
        import time
        start = time.time()
        
        # Retrieve documents
        documents = self.retrieve(query)
        
        # Build context
        context = self.build_context(query, documents)
        
        # Generate answer (if LLM function provided)
        answer = ""
        if llm_generate_fn:
            try:
                answer = llm_generate_fn(query, context)
            except Exception as e:
                logger.error(f"LLM generation failed: {e}")
                answer = f"Error generating answer: {e}"
        else:
            # Return context only if no LLM function
            answer = context
        
        latency = (time.time() - start) * 1000
        
        # Build response
        sources = []
        if return_sources:
            for doc in documents:
                sources.append({
                    'name': doc.get('name', ''),
                    'section': doc.get('section', ''),
                    'description': doc.get('description', ''),
                    'score': doc.get('score', 0.0),
                    'source': doc.get('source', 'unknown')
                })
        
        response = RAGResponse(
            query=query,
            answer=answer,
            sources=sources,
            retrieved_count=len(documents),
            latency_ms=latency,
            metadata={
                'use_reranking': self.use_reranking,
                'top_k': self.top_k,
                'context_length': len(context)
            }
        )
        
        logger.info(
            f"RAG query complete in {latency:.1f}ms "
            f"(retrieved={len(documents)}, sources={len(sources)})"
        )
        
        return response
    
    def format_citations(self, sources: List[Dict[str, Any]]) -> str:
        """
        Format source citations for display.
        
        Args:
            sources: List of source documents
            
        Returns:
            Formatted citation string
        """
        if not sources:
            return ""
        
        citations = ["Sources:"]
        for source in sources:
            name = source.get('name', 'Unknown')
            section = source.get('section', '')
            score = source.get('score', 0.0)
            
            if section:
                citations.append(f"  - {name}({section}) [score: {score:.3f}]")
            else:
                citations.append(f"  - {name} [score: {score:.3f}]")
        
        return '\n'.join(citations)
