"""
RAG (Retrieval-Augmented Generation) system for Halbert.

Provides hybrid retrieval (BM25 + dense embeddings) with reranking
for accurate document retrieval from man pages and knowledge base.
"""

from .retriever import HybridRetriever
from .embeddings import EmbeddingManager
from .pipeline import RAGPipeline

__all__ = [
    'HybridRetriever',
    'EmbeddingManager',
    'RAGPipeline',
]
