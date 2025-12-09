"""
Embedding manager for RAG system.

Handles loading and caching of embedding models (sentence-transformers)
and reranking models (cross-encoders).
"""

import logging
from typing import List, Optional
from pathlib import Path
import numpy as np

logger = logging.getLogger('cerebric')


class EmbeddingManager:
    """Manages embedding and reranking models for RAG."""
    
    def __init__(
        self,
        embedding_model: str = "all-MiniLM-L6-v2",
        reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
        cache_dir: Optional[Path] = None
    ):
        """
        Initialize embedding manager.
        
        Args:
            embedding_model: Sentence transformer model name
            reranker_model: Cross-encoder model name for reranking
            cache_dir: Directory to cache models (optional)
        """
        self.embedding_model_name = embedding_model
        self.reranker_model_name = reranker_model
        self.cache_dir = cache_dir
        
        self._embedder = None
        self._reranker = None
        
        logger.info(f"Initialized EmbeddingManager with {embedding_model}")
    
    @property
    def embedder(self):
        """Lazy load sentence transformer model."""
        if self._embedder is None:
            try:
                from sentence_transformers import SentenceTransformer
                
                logger.info(f"Loading embedding model: {self.embedding_model_name}")
                self._embedder = SentenceTransformer(
                    self.embedding_model_name,
                    cache_folder=str(self.cache_dir) if self.cache_dir else None
                )
                logger.info(f"Embedding model loaded: {self._embedder.get_sentence_embedding_dimension()}D")
                
            except ImportError:
                logger.error("sentence-transformers not installed. Run: pip install sentence-transformers")
                raise
            except Exception as e:
                logger.error(f"Failed to load embedding model: {e}")
                raise
        
        return self._embedder
    
    @property
    def reranker(self):
        """Lazy load cross-encoder reranker model."""
        if self._reranker is None:
            try:
                from sentence_transformers import CrossEncoder
                
                logger.info(f"Loading reranker model: {self.reranker_model_name}")
                self._reranker = CrossEncoder(
                    self.reranker_model_name,
                    max_length=512
                )
                logger.info("Reranker model loaded")
                
            except ImportError:
                logger.error("sentence-transformers not installed")
                raise
            except Exception as e:
                logger.error(f"Failed to load reranker model: {e}")
                raise
        
        return self._reranker
    
    def encode_queries(self, queries: List[str], batch_size: int = 32) -> np.ndarray:
        """
        Encode queries to embeddings.
        
        Args:
            queries: List of query strings
            batch_size: Batch size for encoding
            
        Returns:
            numpy array of embeddings (n_queries, embedding_dim)
        """
        logger.debug(f"Encoding {len(queries)} queries")
        embeddings = self.embedder.encode(
            queries,
            batch_size=batch_size,
            show_progress_bar=False,
            convert_to_numpy=True
        )
        return embeddings
    
    def encode_documents(
        self,
        documents: List[str],
        batch_size: int = 32,
        show_progress: bool = True
    ) -> np.ndarray:
        """
        Encode documents to embeddings.
        
        Args:
            documents: List of document strings
            batch_size: Batch size for encoding
            show_progress: Show progress bar
            
        Returns:
            numpy array of embeddings (n_docs, embedding_dim)
        """
        logger.info(f"Encoding {len(documents)} documents")
        embeddings = self.embedder.encode(
            documents,
            batch_size=batch_size,
            show_progress_bar=show_progress,
            convert_to_numpy=True
        )
        logger.info(f"Encoded {len(documents)} documents to {embeddings.shape}")
        return embeddings
    
    def rerank(
        self,
        query: str,
        documents: List[str],
        top_k: Optional[int] = None
    ) -> List[tuple]:
        """
        Rerank documents using cross-encoder.
        
        Args:
            query: Query string
            documents: List of document strings to rerank
            top_k: Return only top-k results (optional)
            
        Returns:
            List of (doc_index, score) tuples, sorted by score descending
        """
        if not documents:
            return []
        
        logger.debug(f"Reranking {len(documents)} documents for query")
        
        # Create query-document pairs
        pairs = [[query, doc] for doc in documents]
        
        # Score with cross-encoder
        scores = self.reranker.predict(pairs, show_progress_bar=False)
        
        # Sort by score descending
        ranked = sorted(
            enumerate(scores),
            key=lambda x: x[1],
            reverse=True
        )
        
        if top_k:
            ranked = ranked[:top_k]
        
        logger.debug(f"Reranked to top-{len(ranked)} documents")
        return ranked
    
    @property
    def embedding_dimension(self) -> int:
        """Get embedding dimension."""
        return self.embedder.get_sentence_embedding_dimension()
