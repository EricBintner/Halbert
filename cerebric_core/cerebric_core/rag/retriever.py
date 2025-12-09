"""
Hybrid retriever combining BM25 (sparse) and dense embeddings.

Uses Reciprocal Rank Fusion (RRF) to merge results from both retrievers.
"""

import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import numpy as np

logger = logging.getLogger('cerebric')


@dataclass
class RetrievalResult:
    """Single retrieval result."""
    doc_id: str
    score: float
    content: str
    metadata: Dict[str, Any]
    source: str  # 'bm25', 'dense', or 'hybrid'


class HybridRetriever:
    """
    Hybrid retriever combining BM25 (sparse) and dense embeddings.
    
    Uses Reciprocal Rank Fusion to merge results from both methods.
    """
    
    def __init__(
        self,
        embedding_manager,
        bm25_weight: float = 0.5,
        dense_weight: float = 0.5,
        rrf_k: int = 60
    ):
        """
        Initialize hybrid retriever.
        
        Args:
            embedding_manager: EmbeddingManager instance
            bm25_weight: Weight for BM25 scores (0-1)
            dense_weight: Weight for dense scores (0-1)
            rrf_k: RRF constant (typically 60)
        """
        self.embedding_manager = embedding_manager
        self.bm25_weight = bm25_weight
        self.dense_weight = dense_weight
        self.rrf_k = rrf_k
        
        self._bm25 = None
        self._documents = []
        self._doc_ids = []
        self._doc_metadata = []
        self._dense_index = None
        
        logger.info(
            f"Initialized HybridRetriever "
            f"(BM25:{bm25_weight}, Dense:{dense_weight}, RRF_k:{rrf_k})"
        )
    
    def index_documents(
        self,
        documents: List[Dict[str, Any]],
        text_field: str = 'content',
        id_field: str = 'id'
    ):
        """
        Index documents for retrieval.
        
        Args:
            documents: List of document dicts with text and metadata
            text_field: Field name for document text
            id_field: Field name for document ID
        """
        logger.info(f"Indexing {len(documents)} documents")
        
        # Extract text and metadata
        self._documents = []
        self._doc_ids = []
        self._doc_metadata = []
        
        for doc in documents:
            text = doc.get(text_field, '')
            if not text:
                continue
            
            doc_id = doc.get(id_field, f"doc_{len(self._documents)}")
            
            self._documents.append(text)
            self._doc_ids.append(doc_id)
            self._doc_metadata.append(doc)
        
        logger.info(f"Extracted {len(self._documents)} valid documents")
        
        # Build BM25 index
        self._build_bm25_index()
        
        # Build dense index
        self._build_dense_index()
        
        logger.info("Document indexing complete")
    
    def _build_bm25_index(self):
        """Build BM25 sparse index."""
        try:
            from rank_bm25 import BM25Okapi
            
            logger.info("Building BM25 index")
            
            # Tokenize documents (simple whitespace split)
            tokenized_docs = [doc.lower().split() for doc in self._documents]
            
            self._bm25 = BM25Okapi(tokenized_docs)
            
            logger.info(f"BM25 index built with {len(tokenized_docs)} documents")
            
        except ImportError:
            logger.error("rank-bm25 not installed. Run: pip install rank-bm25")
            raise
    
    def _build_dense_index(self):
        """Build dense embedding index."""
        logger.info("Building dense embedding index")
        
        # Encode all documents
        embeddings = self.embedding_manager.encode_documents(
            self._documents,
            show_progress=True
        )
        
        # Store embeddings (using simple numpy for now, can swap to FAISS later)
        self._dense_index = embeddings
        
        logger.info(f"Dense index built: {embeddings.shape}")
    
    def retrieve_bm25(self, query: str, top_k: int = 20) -> List[RetrievalResult]:
        """
        Retrieve using BM25 sparse retrieval.
        
        Args:
            query: Query string
            top_k: Number of results to return
            
        Returns:
            List of RetrievalResult objects
        """
        if self._bm25 is None:
            logger.warning("BM25 index not built")
            return []
        
        # Tokenize query
        tokenized_query = query.lower().split()
        
        # Get scores
        scores = self._bm25.get_scores(tokenized_query)
        
        # Get top-k indices
        top_indices = np.argsort(scores)[::-1][:top_k]
        
        results = []
        for idx in top_indices:
            if scores[idx] <= 0:
                break
            
            results.append(RetrievalResult(
                doc_id=self._doc_ids[idx],
                score=float(scores[idx]),
                content=self._documents[idx],
                metadata=self._doc_metadata[idx],
                source='bm25'
            ))
        
        logger.debug(f"BM25 retrieved {len(results)} results")
        return results
    
    def retrieve_dense(self, query: str, top_k: int = 20) -> List[RetrievalResult]:
        """
        Retrieve using dense embeddings.
        
        Args:
            query: Query string
            top_k: Number of results to return
            
        Returns:
            List of RetrievalResult objects
        """
        if self._dense_index is None:
            logger.warning("Dense index not built")
            return []
        
        # Encode query
        query_embedding = self.embedding_manager.encode_queries([query])[0]
        
        # Compute cosine similarity with all documents
        # Normalize embeddings for cosine similarity
        query_norm = query_embedding / np.linalg.norm(query_embedding)
        doc_norms = self._dense_index / np.linalg.norm(
            self._dense_index, axis=1, keepdims=True
        )
        
        similarities = np.dot(doc_norms, query_norm)
        
        # Get top-k indices
        top_indices = np.argsort(similarities)[::-1][:top_k]
        
        results = []
        for idx in top_indices:
            results.append(RetrievalResult(
                doc_id=self._doc_ids[idx],
                score=float(similarities[idx]),
                content=self._documents[idx],
                metadata=self._doc_metadata[idx],
                source='dense'
            ))
        
        logger.debug(f"Dense retrieved {len(results)} results")
        return results
    
    def retrieve_hybrid(
        self,
        query: str,
        top_k: int = 10,
        retrieve_k: int = 20
    ) -> List[RetrievalResult]:
        """
        Hybrid retrieval using RRF fusion.
        
        Args:
            query: Query string
            top_k: Final number of results to return
            retrieve_k: Number of results to retrieve from each method before fusion
            
        Returns:
            List of RetrievalResult objects, reranked
        """
        # Retrieve from both methods
        bm25_results = self.retrieve_bm25(query, top_k=retrieve_k)
        dense_results = self.retrieve_dense(query, top_k=retrieve_k)
        
        # Reciprocal Rank Fusion
        rrf_scores = {}
        
        # Add BM25 scores
        for rank, result in enumerate(bm25_results):
            doc_id = result.doc_id
            rrf_score = self.bm25_weight / (self.rrf_k + rank + 1)
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0) + rrf_score
        
        # Add dense scores
        for rank, result in enumerate(dense_results):
            doc_id = result.doc_id
            rrf_score = self.dense_weight / (self.rrf_k + rank + 1)
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0) + rrf_score
        
        # Sort by combined RRF score
        sorted_doc_ids = sorted(
            rrf_scores.keys(),
            key=lambda x: rrf_scores[x],
            reverse=True
        )[:top_k]
        
        # Build results
        doc_map = {}
        for result in bm25_results + dense_results:
            if result.doc_id not in doc_map:
                doc_map[result.doc_id] = result
        
        results = []
        for doc_id in sorted_doc_ids:
            result = doc_map[doc_id]
            results.append(RetrievalResult(
                doc_id=result.doc_id,
                score=rrf_scores[doc_id],
                content=result.content,
                metadata=result.metadata,
                source='hybrid'
            ))
        
        logger.debug(f"Hybrid retrieval returned {len(results)} results")
        return results
    
    def retrieve_and_rerank(
        self,
        query: str,
        top_k: int = 5,
        retrieve_k: int = 20
    ) -> List[RetrievalResult]:
        """
        Hybrid retrieval with cross-encoder reranking.
        
        Args:
            query: Query string
            top_k: Final number of results after reranking
            retrieve_k: Number of results to retrieve before reranking
            
        Returns:
            List of reranked RetrievalResult objects
        """
        # First-stage retrieval (hybrid)
        initial_results = self.retrieve_hybrid(
            query,
            top_k=retrieve_k,
            retrieve_k=retrieve_k * 2  # Cast wider net
        )
        
        if not initial_results:
            return []
        
        # Extract documents for reranking
        documents = [r.content for r in initial_results]
        
        # Rerank with cross-encoder
        reranked_indices = self.embedding_manager.rerank(
            query,
            documents,
            top_k=top_k
        )
        
        # Build final results
        results = []
        for idx, score in reranked_indices:
            original = initial_results[idx]
            results.append(RetrievalResult(
                doc_id=original.doc_id,
                score=float(score),
                content=original.content,
                metadata=original.metadata,
                source='reranked'
            ))
        
        logger.debug(f"Reranking returned top-{len(results)} results")
        return results
