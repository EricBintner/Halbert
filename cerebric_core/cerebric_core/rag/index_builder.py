"""
Build and manage RAG indices for Cerebric.

Utility for building vector indices from man pages and other documents.
"""

import logging
from pathlib import Path
from typing import Optional
import json
import time

from .pipeline import RAGPipeline

logger = logging.getLogger('cerebric')


class IndexBuilder:
    """Build and manage RAG indices."""
    
    def __init__(self, data_dir: Path):
        """
        Initialize index builder.
        
        Args:
            data_dir: Data directory
        """
        self.data_dir = Path(data_dir)
        logger.info(f"Initialized IndexBuilder with data_dir={data_dir}")
    
    def build_man_pages_index(
        self,
        jsonl_path: Optional[Path] = None,
        output_dir: Optional[Path] = None
    ):
        """
        Build index for man pages.
        
        Args:
            jsonl_path: Path to man pages JSONL file
            output_dir: Output directory for index
        """
        if jsonl_path is None:
            jsonl_path = self.data_dir / 'linux' / 'man-pages' / 'man_pages.jsonl'
        
        if output_dir is None:
            output_dir = self.data_dir / '.rag_indices' / 'man_pages'
        
        output_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Building man pages index from {jsonl_path}")
        start_time = time.time()
        
        # Create pipeline
        pipeline = RAGPipeline(
            data_dir=self.data_dir,
            use_reranking=True,
            top_k=5
        )
        
        # Load and index documents
        pipeline.load_and_index_documents(jsonl_path=jsonl_path)
        
        elapsed = time.time() - start_time
        
        # Save index metadata
        metadata = {
            'source': str(jsonl_path),
            'indexed_at': time.strftime('%Y-%m-%d %H:%M:%S'),
            'build_time_seconds': elapsed,
            'embedding_model': pipeline.embedding_manager.embedding_model_name,
            'reranker_model': pipeline.embedding_manager.reranker_model_name
        }
        
        metadata_path = output_dir / 'index_metadata.json'
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        logger.info(
            f"Index built in {elapsed:.1f}s. "
            f"Metadata saved to {metadata_path}"
        )
        
        return pipeline
    
    def test_index(self, pipeline: RAGPipeline, num_queries: int = 5):
        """
        Test index with sample queries.
        
        Args:
            pipeline: RAGPipeline instance
            num_queries: Number of test queries
        """
        test_queries = [
            "How do I restart systemd?",
            "How to check disk usage?",
            "What is chmod command?",
            "How to view system logs?",
            "Network configuration commands"
        ][:num_queries]
        
        logger.info(f"Testing index with {len(test_queries)} queries")
        
        for i, query in enumerate(test_queries, 1):
            logger.info(f"\nTest {i}/{len(test_queries)}: {query}")
            
            start = time.time()
            results = pipeline.retrieve(query)
            latency = (time.time() - start) * 1000
            
            logger.info(f"  Retrieved {len(results)} docs in {latency:.1f}ms")
            
            for j, doc in enumerate(results[:3], 1):
                name = doc.get('name', 'Unknown')
                section = doc.get('section', '')
                score = doc.get('score', 0.0)
                logger.info(f"    {j}. {name}({section}) - score: {score:.3f}")


def build_index_cli():
    """CLI entry point for building indices."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Build RAG index for Cerebric'
    )
    parser.add_argument(
        '--data-dir',
        type=Path,
        default=Path('data'),
        help='Data directory'
    )
    parser.add_argument(
        '--input',
        type=Path,
        help='Input JSONL file (default: data/linux/man-pages/man_pages.jsonl)'
    )
    parser.add_argument(
        '--output',
        type=Path,
        help='Output directory (default: data/.rag_indices/man_pages)'
    )
    parser.add_argument(
        '--test',
        action='store_true',
        help='Run test queries after building'
    )
    
    args = parser.parse_args()
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Build index
    builder = IndexBuilder(args.data_dir)
    pipeline = builder.build_man_pages_index(
        jsonl_path=args.input,
        output_dir=args.output
    )
    
    # Test if requested
    if args.test:
        builder.test_index(pipeline)
    
    logger.info("Index building complete!")


if __name__ == '__main__':
    build_index_cli()
