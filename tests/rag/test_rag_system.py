"""
Tests for RAG system.
"""

import pytest
from pathlib import Path
import json
import tempfile
import os

from halbert_core.rag import EmbeddingManager, HybridRetriever, RAGPipeline


@pytest.fixture
def sample_documents():
    """Sample documents for testing."""
    return [
        {
            'id': 'systemctl',
            'name': 'systemctl',
            'section': '1',
            'description': 'Control the systemd system and service manager',
            'full_text': 'systemctl - Control the systemd system and service manager. '
                        'Use systemctl restart to restart a service. '
                        'Use systemctl status to check service status.'
        },
        {
            'id': 'journalctl',
            'name': 'journalctl',
            'section': '1',
            'description': 'Query the systemd journal',
            'full_text': 'journalctl - Query the systemd journal. '
                        'View system logs with journalctl. '
                        'Use journalctl -u servicename to view logs for a specific service.'
        },
        {
            'id': 'chmod',
            'name': 'chmod',
            'section': '1',
            'description': 'Change file mode bits',
            'full_text': 'chmod - Change file mode bits. '
                        'Use chmod 755 to set permissions. '
                        'Use chmod +x to make a file executable.'
        },
        {
            'id': 'df',
            'name': 'df',
            'section': '1',
            'description': 'Report file system disk space usage',
            'full_text': 'df - Report file system disk space usage. '
                        'Use df -h for human-readable output. '
                        'Shows available disk space for all mounted filesystems.'
        }
    ]


@pytest.fixture
def temp_data_dir(sample_documents):
    """Create temporary data directory with sample docs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        data_dir = Path(tmpdir) / 'data'
        data_dir.mkdir()
        
        # Create man pages directory
        man_dir = data_dir / 'linux' / 'man-pages'
        man_dir.mkdir(parents=True)
        
        # Write JSONL file
        jsonl_path = man_dir / 'man_pages.jsonl'
        with open(jsonl_path, 'w') as f:
            for doc in sample_documents:
                f.write(json.dumps(doc) + '\n')
        
        yield data_dir


class TestEmbeddingManager:
    """Test EmbeddingManager."""
    
    def test_init(self):
        """Test initialization."""
        manager = EmbeddingManager()
        assert manager.embedding_model_name == "all-MiniLM-L6-v2"
    
    def test_encode_queries(self):
        """Test query encoding."""
        manager = EmbeddingManager()
        queries = ["How do I restart systemd?", "Check disk space"]
        
        embeddings = manager.encode_queries(queries)
        
        assert embeddings.shape[0] == 2
        assert embeddings.shape[1] == manager.embedding_dimension
    
    def test_encode_documents(self):
        """Test document encoding."""
        manager = EmbeddingManager()
        docs = [
            "systemctl is used to control systemd",
            "df shows disk space usage"
        ]
        
        embeddings = manager.encode_documents(docs, show_progress=False)
        
        assert embeddings.shape[0] == 2
        assert embeddings.shape[1] == manager.embedding_dimension


class TestHybridRetriever:
    """Test HybridRetriever."""
    
    def test_index_documents(self, sample_documents):
        """Test document indexing."""
        manager = EmbeddingManager()
        retriever = HybridRetriever(manager)
        
        # Prepare docs
        docs = []
        for doc in sample_documents:
            docs.append({
                'id': doc['id'],
                'content': f"{doc['name']} - {doc['description']} {doc['full_text']}"
            })
        
        retriever.index_documents(docs)
        
        assert len(retriever._documents) == len(sample_documents)
        assert retriever._bm25 is not None
        assert retriever._dense_index is not None
    
    def test_retrieve_bm25(self, sample_documents):
        """Test BM25 retrieval."""
        manager = EmbeddingManager()
        retriever = HybridRetriever(manager)
        
        # Index
        docs = []
        for doc in sample_documents:
            docs.append({
                'id': doc['id'],
                'content': f"{doc['name']} - {doc['description']} {doc['full_text']}"
            })
        retriever.index_documents(docs)
        
        # Retrieve
        results = retriever.retrieve_bm25("systemctl restart service", top_k=3)
        
        assert len(results) > 0
        assert results[0].doc_id == 'systemctl'  # Should match systemctl
        assert results[0].source == 'bm25'
    
    def test_retrieve_dense(self, sample_documents):
        """Test dense retrieval."""
        manager = EmbeddingManager()
        retriever = HybridRetriever(manager)
        
        # Index
        docs = []
        for doc in sample_documents:
            docs.append({
                'id': doc['id'],
                'content': f"{doc['name']} - {doc['description']} {doc['full_text']}"
            })
        retriever.index_documents(docs)
        
        # Retrieve with semantic query
        results = retriever.retrieve_dense("check disk space", top_k=3)
        
        assert len(results) > 0
        # Should retrieve df (disk space) doc
        doc_ids = [r.doc_id for r in results]
        assert 'df' in doc_ids
    
    def test_retrieve_hybrid(self, sample_documents):
        """Test hybrid retrieval."""
        manager = EmbeddingManager()
        retriever = HybridRetriever(manager)
        
        # Index
        docs = []
        for doc in sample_documents:
            docs.append({
                'id': doc['id'],
                'content': f"{doc['name']} - {doc['description']} {doc['full_text']}"
            })
        retriever.index_documents(docs)
        
        # Retrieve
        results = retriever.retrieve_hybrid("restart service", top_k=3)
        
        assert len(results) > 0
        assert results[0].source == 'hybrid'


class TestRAGPipeline:
    """Test RAGPipeline."""
    
    def test_init(self, temp_data_dir):
        """Test pipeline initialization."""
        pipeline = RAGPipeline(temp_data_dir)
        
        assert pipeline.data_dir == temp_data_dir
        assert pipeline.embedding_manager is not None
        assert pipeline.retriever is not None
        assert not pipeline._indexed
    
    def test_load_and_index(self, temp_data_dir):
        """Test document loading and indexing."""
        pipeline = RAGPipeline(temp_data_dir)
        pipeline.load_and_index_documents()
        
        assert pipeline._indexed
        assert len(pipeline.retriever._documents) == 4
    
    def test_retrieve(self, temp_data_dir):
        """Test retrieval."""
        pipeline = RAGPipeline(temp_data_dir, use_reranking=False)
        pipeline.load_and_index_documents()
        
        results = pipeline.retrieve("How do I restart systemd?")
        
        assert len(results) > 0
        assert 'doc_id' in results[0]
        assert 'score' in results[0]
        assert 'name' in results[0]
    
    def test_build_context(self, temp_data_dir):
        """Test context building."""
        pipeline = RAGPipeline(temp_data_dir, use_reranking=False)
        pipeline.load_and_index_documents()
        
        docs = pipeline.retrieve("restart service")
        context = pipeline.build_context("restart service", docs)
        
        assert len(context) > 0
        assert "Relevant Documentation" in context
        assert "systemctl" in context.lower()
    
    def test_query_without_llm(self, temp_data_dir):
        """Test query without LLM generation."""
        pipeline = RAGPipeline(temp_data_dir, use_reranking=False)
        pipeline.load_and_index_documents()
        
        response = pipeline.query("How do I check disk space?")
        
        assert response.query == "How do I check disk space?"
        assert len(response.sources) > 0
        assert response.retrieved_count > 0
        assert response.latency_ms > 0
    
    def test_query_with_llm(self, temp_data_dir):
        """Test query with mock LLM."""
        pipeline = RAGPipeline(temp_data_dir, use_reranking=False)
        pipeline.load_and_index_documents()
        
        # Mock LLM function
        def mock_llm(query, context):
            return f"Mock answer for: {query}"
        
        response = pipeline.query(
            "How do I restart systemd?",
            llm_generate_fn=mock_llm
        )
        
        assert "Mock answer" in response.answer
        assert len(response.sources) > 0
    
    def test_format_citations(self, temp_data_dir):
        """Test citation formatting."""
        pipeline = RAGPipeline(temp_data_dir)
        
        sources = [
            {'name': 'systemctl', 'section': '1', 'score': 0.95},
            {'name': 'journalctl', 'section': '1', 'score': 0.75}
        ]
        
        citations = pipeline.format_citations(sources)
        
        assert "Sources:" in citations
        assert "systemctl(1)" in citations
        assert "journalctl(1)" in citations


# Integration test
@pytest.mark.skipif(
    not os.path.exists('data/linux/man-pages/man_pages.jsonl'),
    reason="Real man pages data not available"
)
def test_real_man_pages():
    """Integration test with real man pages."""
    pipeline = RAGPipeline(
        data_dir=Path('data'),
        use_reranking=True,
        top_k=5
    )
    
    # Load real man pages
    pipeline.load_and_index_documents()
    
    # Test queries
    test_queries = [
        "How do I restart systemd?",
        "Check disk usage",
        "Change file permissions"
    ]
    
    for query in test_queries:
        response = pipeline.query(query)
        
        assert len(response.sources) > 0
        assert response.latency_ms > 0
        print(f"\nQuery: {query}")
        print(f"Retrieved: {response.retrieved_count} docs")
        print(f"Top result: {response.sources[0]['name']}")


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
