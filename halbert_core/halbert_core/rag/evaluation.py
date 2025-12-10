"""
RAG evaluation framework.

Implements RAGAS-style metrics and custom evaluation for Halbert RAG.
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from pathlib import Path
import json
import time

logger = logging.getLogger('halbert')


@dataclass
class EvaluationMetrics:
    """RAG evaluation metrics."""
    # Retrieval metrics
    hit_at_1: float = 0.0
    hit_at_3: float = 0.0
    hit_at_5: float = 0.0
    mrr: float = 0.0  # Mean Reciprocal Rank
    
    # Answer quality metrics (if LLM available)
    answer_relevancy: float = 0.0
    faithfulness: float = 0.0
    
    # Performance metrics
    avg_retrieval_time_ms: float = 0.0
    avg_total_time_ms: float = 0.0
    
    # Metadata
    num_queries: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


@dataclass
class TestQuery:
    """Test query with ground truth."""
    query: str
    expected_docs: List[str]  # Doc IDs or names that should be retrieved
    category: str = "general"
    ground_truth_answer: Optional[str] = None


class RAGEvaluator:
    """
    Evaluate RAG system performance.
    
    Implements retrieval accuracy metrics (Hit@k, MRR) and
    optional answer quality metrics.
    """
    
    def __init__(self, pipeline):
        """
        Initialize evaluator.
        
        Args:
            pipeline: RAGPipeline instance to evaluate
        """
        self.pipeline = pipeline
        logger.info("Initialized RAGEvaluator")
    
    def evaluate(
        self,
        test_queries: List[TestQuery],
        top_k: int = 5
    ) -> EvaluationMetrics:
        """
        Evaluate RAG pipeline on test queries.
        
        Args:
            test_queries: List of test queries with ground truth
            top_k: Number of documents to retrieve
            
        Returns:
            Evaluation metrics
        """
        logger.info(f"Evaluating on {len(test_queries)} test queries")
        
        hit_1_count = 0
        hit_3_count = 0
        hit_5_count = 0
        mrr_sum = 0.0
        retrieval_times = []
        
        for i, test_query in enumerate(test_queries, 1):
            logger.debug(f"Evaluating query {i}/{len(test_queries)}: {test_query.query}")
            
            # Retrieve documents
            start_time = time.time()
            results = self.pipeline.retrieve(test_query.query)
            retrieval_time = (time.time() - start_time) * 1000
            retrieval_times.append(retrieval_time)
            
            # Extract retrieved doc IDs
            retrieved_ids = [doc['doc_id'] for doc in results[:top_k]]
            retrieved_names = [doc['name'] for doc in results[:top_k]]
            
            # Check if any expected doc was retrieved
            found_at_rank = None
            for expected_doc in test_query.expected_docs:
                for rank, (doc_id, doc_name) in enumerate(zip(retrieved_ids, retrieved_names), 1):
                    # Match by ID or name
                    if expected_doc in [doc_id, doc_name]:
                        found_at_rank = rank
                        break
                if found_at_rank:
                    break
            
            # Update metrics
            if found_at_rank:
                if found_at_rank <= 1:
                    hit_1_count += 1
                if found_at_rank <= 3:
                    hit_3_count += 1
                if found_at_rank <= 5:
                    hit_5_count += 1
                
                # MRR: 1/rank
                mrr_sum += 1.0 / found_at_rank
            
            # Log result
            if found_at_rank:
                logger.debug(f"  ✓ Found at rank {found_at_rank}")
            else:
                logger.debug(f"  ✗ Not found in top-{top_k}")
        
        # Calculate metrics
        num_queries = len(test_queries)
        metrics = EvaluationMetrics(
            hit_at_1=hit_1_count / num_queries,
            hit_at_3=hit_3_count / num_queries,
            hit_at_5=hit_5_count / num_queries,
            mrr=mrr_sum / num_queries,
            avg_retrieval_time_ms=sum(retrieval_times) / len(retrieval_times),
            num_queries=num_queries
        )
        
        logger.info(
            f"Evaluation complete: "
            f"Hit@1={metrics.hit_at_1:.2%}, "
            f"Hit@5={metrics.hit_at_5:.2%}, "
            f"MRR={metrics.mrr:.3f}"
        )
        
        return metrics
    
    def save_results(self, metrics: EvaluationMetrics, output_path: Path):
        """
        Save evaluation results.
        
        Args:
            metrics: Evaluation metrics
            output_path: Output file path
        """
        results = {
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'metrics': metrics.to_dict(),
            'thresholds': {
                'hit_at_5': {'target': 0.90, 'achieved': metrics.hit_at_5 >= 0.90},
                'mrr': {'target': 0.80, 'achieved': metrics.mrr >= 0.80},
            }
        }
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w') as f:
            json.dump(results, f, indent=2)
        
        logger.info(f"Results saved to {output_path}")


class TestDatasetGenerator:
    """Generate test datasets for evaluation."""
    
    # Sample test queries for Linux system administration
    SAMPLE_QUERIES = [
        TestQuery(
            query="How do I restart a systemd service?",
            expected_docs=["systemctl", "systemd"],
            category="system_admin"
        ),
        TestQuery(
            query="Check disk space usage",
            expected_docs=["df", "du"],
            category="file_system"
        ),
        TestQuery(
            query="Change file permissions to executable",
            expected_docs=["chmod"],
            category="security"
        ),
        TestQuery(
            query="View system logs",
            expected_docs=["journalctl", "syslog"],
            category="system_admin"
        ),
        TestQuery(
            query="Configure network interface",
            expected_docs=["ifconfig", "ip", "network"],
            category="networking"
        ),
        TestQuery(
            query="Add a new user to the system",
            expected_docs=["useradd", "adduser"],
            category="system_admin"
        ),
        TestQuery(
            query="List running processes",
            expected_docs=["ps", "top"],
            category="system_admin"
        ),
        TestQuery(
            query="Create a cron job",
            expected_docs=["crontab", "cron"],
            category="system_admin"
        ),
        TestQuery(
            query="Find files by name",
            expected_docs=["find", "locate"],
            category="file_system"
        ),
        TestQuery(
            query="Connect to remote server via SSH",
            expected_docs=["ssh", "openssh"],
            category="networking"
        ),
        TestQuery(
            query="Mount a filesystem",
            expected_docs=["mount", "fstab"],
            category="file_system"
        ),
        TestQuery(
            query="Check network connectivity",
            expected_docs=["ping", "traceroute"],
            category="networking"
        ),
        TestQuery(
            query="Install a package",
            expected_docs=["apt", "yum", "pacman"],
            category="package_mgmt"
        ),
        TestQuery(
            query="Change user password",
            expected_docs=["passwd"],
            category="security"
        ),
        TestQuery(
            query="Kill a process",
            expected_docs=["kill", "killall"],
            category="system_admin"
        ),
        TestQuery(
            query="Compress a file",
            expected_docs=["tar", "gzip", "zip"],
            category="file_system"
        ),
        TestQuery(
            query="Configure firewall rules",
            expected_docs=["iptables", "firewall", "ufw"],
            category="security"
        ),
        TestQuery(
            query="Check memory usage",
            expected_docs=["free", "vmstat"],
            category="system_admin"
        ),
        TestQuery(
            query="Search text in files",
            expected_docs=["grep", "ack"],
            category="file_system"
        ),
        TestQuery(
            query="Change ownership of a file",
            expected_docs=["chown"],
            category="security"
        ),
    ]
    
    @classmethod
    def get_sample_dataset(cls) -> List[TestQuery]:
        """Get sample test dataset."""
        return cls.SAMPLE_QUERIES.copy()
    
    @classmethod
    def save_dataset(cls, queries: List[TestQuery], output_path: Path):
        """Save test dataset to JSON."""
        data = [
            {
                'query': q.query,
                'expected_docs': q.expected_docs,
                'category': q.category,
                'ground_truth_answer': q.ground_truth_answer
            }
            for q in queries
        ]
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w') as f:
            json.dump(data, f, indent=2)
        
        logger.info(f"Saved {len(queries)} test queries to {output_path}")
    
    @classmethod
    def load_dataset(cls, input_path: Path) -> List[TestQuery]:
        """Load test dataset from JSON."""
        with open(input_path, 'r') as f:
            data = json.load(f)
        
        queries = [
            TestQuery(
                query=item['query'],
                expected_docs=item['expected_docs'],
                category=item.get('category', 'general'),
                ground_truth_answer=item.get('ground_truth_answer')
            )
            for item in data
        ]
        
        logger.info(f"Loaded {len(queries)} test queries from {input_path}")
        return queries


def run_evaluation_cli():
    """CLI entry point for evaluation."""
    import argparse
    from ..pipeline import RAGPipeline
    
    parser = argparse.ArgumentParser(
        description='Evaluate RAG system'
    )
    parser.add_argument(
        '--data-dir',
        type=Path,
        default=Path('data'),
        help='Data directory'
    )
    parser.add_argument(
        '--test-dataset',
        type=Path,
        help='Test dataset JSON file (optional, uses sample dataset if not provided)'
    )
    parser.add_argument(
        '--output',
        type=Path,
        default=Path('tests/rag/evaluation_results.json'),
        help='Output file for results'
    )
    parser.add_argument(
        '--top-k',
        type=int,
        default=5,
        help='Number of documents to retrieve'
    )
    parser.add_argument(
        '--use-reranking',
        action='store_true',
        help='Enable reranking'
    )
    
    args = parser.parse_args()
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Initialize pipeline
    logger.info("Initializing RAG pipeline...")
    pipeline = RAGPipeline(
        data_dir=args.data_dir,
        use_reranking=args.use_reranking,
        top_k=args.top_k
    )
    pipeline.load_and_index_documents()
    
    # Load test dataset
    if args.test_dataset and args.test_dataset.exists():
        test_queries = TestDatasetGenerator.load_dataset(args.test_dataset)
    else:
        logger.info("Using sample test dataset")
        test_queries = TestDatasetGenerator.get_sample_dataset()
    
    # Run evaluation
    evaluator = RAGEvaluator(pipeline)
    metrics = evaluator.evaluate(test_queries, top_k=args.top_k)
    
    # Print results
    print("\n" + "=" * 60)
    print("EVALUATION RESULTS")
    print("=" * 60)
    print(f"Test queries:        {metrics.num_queries}")
    print(f"Hit@1:               {metrics.hit_at_1:.2%}")
    print(f"Hit@3:               {metrics.hit_at_3:.2%}")
    print(f"Hit@5:               {metrics.hit_at_5:.2%}")
    print(f"MRR:                 {metrics.mrr:.3f}")
    print(f"Avg retrieval time:  {metrics.avg_retrieval_time_ms:.1f}ms")
    print("=" * 60)
    print()
    
    # Check if targets met
    targets_met = []
    targets_missed = []
    
    if metrics.hit_at_5 >= 0.90:
        targets_met.append("Hit@5 >= 90%")
    else:
        targets_missed.append(f"Hit@5 >= 90% (got {metrics.hit_at_5:.2%})")
    
    if metrics.mrr >= 0.80:
        targets_met.append("MRR >= 0.80")
    else:
        targets_missed.append(f"MRR >= 0.80 (got {metrics.mrr:.3f})")
    
    if targets_met:
        print("✓ Targets met:")
        for target in targets_met:
            print(f"  - {target}")
    
    if targets_missed:
        print("\n✗ Targets missed:")
        for target in targets_missed:
            print(f"  - {target}")
    
    # Save results
    evaluator.save_results(metrics, args.output)
    print(f"\nResults saved to: {args.output}")


if __name__ == '__main__':
    run_evaluation_cli()
