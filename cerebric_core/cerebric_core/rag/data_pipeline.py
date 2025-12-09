"""
Unified data pipeline for RAG system.

Orchestrates scraping, validation, deduplication, and indexing.
"""

import logging
from typing import List, Dict, Any, Optional
from pathlib import Path
from dataclasses import dataclass
import json
from datetime import datetime

from .scrapers import ScrapedDocument

logger = logging.getLogger('cerebric')


@dataclass
class PipelineStats:
    """Statistics from pipeline run."""
    total_scraped: int = 0
    duplicates_removed: int = 0
    invalid_removed: int = 0
    final_count: int = 0
    sources: Dict[str, int] = None
    categories: Dict[str, int] = None
    
    def __post_init__(self):
        if self.sources is None:
            self.sources = {}
        if self.categories is None:
            self.categories = {}


class DataPipeline:
    """
    Unified data pipeline for RAG.
    
    Handles:
    - Data ingestion from multiple sources
    - Validation and quality checks
    - Deduplication
    - Format normalization
    - Output management
    """
    
    def __init__(self, data_dir: Path):
        """
        Initialize data pipeline.
        
        Args:
            data_dir: Base data directory
        """
        self.data_dir = Path(data_dir)
        self.raw_dir = self.data_dir / 'raw'
        self.processed_dir = self.data_dir / 'processed'
        
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Initialized DataPipeline with data_dir={data_dir}")
    
    def load_documents_from_source(self, source: str) -> List[ScrapedDocument]:
        """
        Load documents from a source JSONL file.
        
        Args:
            source: Source name (e.g., 'arch_wiki', 'stackoverflow')
            
        Returns:
            List of loaded documents
        """
        input_path = self.raw_dir / f"{source}.jsonl"
        
        if not input_path.exists():
            logger.warning(f"Source file not found: {input_path}")
            return []
        
        documents = []
        with open(input_path, 'r') as f:
            for line_num, line in enumerate(f, 1):
                try:
                    data = json.loads(line.strip())
                    doc = ScrapedDocument.from_dict(data)
                    documents.append(doc)
                except json.JSONDecodeError as e:
                    logger.warning(f"Line {line_num}: Failed to parse JSON: {e}")
                except Exception as e:
                    logger.warning(f"Line {line_num}: Failed to create document: {e}")
        
        logger.info(f"Loaded {len(documents)} documents from {source}")
        return documents
    
    def validate_documents(self, documents: List[ScrapedDocument]) -> List[ScrapedDocument]:
        """
        Validate documents and filter out invalid ones.
        
        Args:
            documents: List of documents to validate
            
        Returns:
            List of valid documents
        """
        valid_docs = []
        
        for doc in documents:
            if self._validate_document(doc):
                valid_docs.append(doc)
        
        invalid_count = len(documents) - len(valid_docs)
        if invalid_count > 0:
            logger.info(f"Filtered out {invalid_count} invalid documents")
        
        return valid_docs
    
    def _validate_document(self, doc: ScrapedDocument) -> bool:
        """Validate a single document."""
        # Must have ID
        if not doc.id:
            logger.debug("Document missing ID")
            return False
        
        # Must have URL
        if not doc.url:
            logger.debug(f"Document {doc.id} missing URL")
            return False
        
        # Must have title
        if not doc.title or len(doc.title) < 3:
            logger.debug(f"Document {doc.id} has invalid title")
            return False
        
        # Must have content
        if not doc.content:
            logger.debug(f"Document {doc.id} has no content")
            return False
        
        # Content must be substantial (at least 200 chars)
        if len(doc.content) < 200:
            logger.debug(f"Document {doc.id} has insufficient content ({len(doc.content)} chars)")
            return False
        
        # Must have source
        if not doc.source:
            logger.debug(f"Document {doc.id} missing source")
            return False
        
        return True
    
    def deduplicate_documents(
        self,
        documents: List[ScrapedDocument],
        by: str = 'url'
    ) -> List[ScrapedDocument]:
        """
        Remove duplicate documents.
        
        Args:
            documents: List of documents
            by: Deduplication key ('url' or 'id')
            
        Returns:
            Deduplicated list
        """
        seen = set()
        unique_docs = []
        
        for doc in documents:
            key = doc.url if by == 'url' else doc.id
            
            if key not in seen:
                seen.add(key)
                unique_docs.append(doc)
        
        dup_count = len(documents) - len(unique_docs)
        if dup_count > 0:
            logger.info(f"Removed {dup_count} duplicates")
        
        return unique_docs
    
    def merge_sources(self, sources: List[str]) -> List[ScrapedDocument]:
        """
        Merge documents from multiple sources.
        
        Args:
            sources: List of source names
            
        Returns:
            Merged and deduplicated document list
        """
        logger.info(f"Merging {len(sources)} sources: {sources}")
        
        all_docs = []
        for source in sources:
            docs = self.load_documents_from_source(source)
            all_docs.extend(docs)
        
        logger.info(f"Loaded {len(all_docs)} total documents before deduplication")
        
        # Deduplicate across sources
        unique_docs = self.deduplicate_documents(all_docs, by='url')
        
        logger.info(f"After deduplication: {len(unique_docs)} documents")
        
        return unique_docs
    
    def process_pipeline(
        self,
        sources: List[str],
        output_name: str = 'all_sources'
    ) -> PipelineStats:
        """
        Run full data pipeline.
        
        Args:
            sources: List of source names to process
            output_name: Output file name (without extension)
            
        Returns:
            Pipeline statistics
        """
        logger.info(f"Running data pipeline for sources: {sources}")
        
        stats = PipelineStats()
        
        # 1. Load documents from all sources
        documents = self.merge_sources(sources)
        stats.total_scraped = len(documents)
        
        # 2. Validate documents
        initial_count = len(documents)
        documents = self.validate_documents(documents)
        stats.invalid_removed = initial_count - len(documents)
        
        # 3. Deduplicate (in case merge didn't catch everything)
        initial_count = len(documents)
        documents = self.deduplicate_documents(documents)
        stats.duplicates_removed = initial_count - len(documents)
        
        stats.final_count = len(documents)
        
        # 4. Collect statistics
        stats.sources = self._count_by_field(documents, 'source')
        stats.categories = self._count_by_field(documents, 'category')
        
        # 5. Save processed documents
        output_path = self.processed_dir / f"{output_name}.jsonl"
        self._save_documents(documents, output_path)
        
        # 6. Save statistics
        self._save_stats(stats, output_name)
        
        logger.info(f"Pipeline complete: {stats.final_count} documents processed")
        
        return stats
    
    def _count_by_field(self, documents: List[ScrapedDocument], field: str) -> Dict[str, int]:
        """Count documents by field value."""
        counts = {}
        for doc in documents:
            value = getattr(doc, field, 'unknown')
            counts[value] = counts.get(value, 0) + 1
        return counts
    
    def _save_documents(self, documents: List[ScrapedDocument], output_path: Path):
        """Save documents to JSONL."""
        logger.info(f"Saving {len(documents)} documents to {output_path}")
        
        with open(output_path, 'w') as f:
            for doc in documents:
                f.write(json.dumps(doc.to_dict()) + '\n')
        
        logger.info(f"Saved to {output_path}")
    
    def _save_stats(self, stats: PipelineStats, name: str):
        """Save pipeline statistics."""
        stats_path = self.processed_dir / f"{name}_stats.json"
        
        stats_dict = {
            'timestamp': datetime.now().isoformat(),
            'total_scraped': stats.total_scraped,
            'duplicates_removed': stats.duplicates_removed,
            'invalid_removed': stats.invalid_removed,
            'final_count': stats.final_count,
            'sources': stats.sources,
            'categories': stats.categories
        }
        
        with open(stats_path, 'w') as f:
            json.dumps(stats_dict, f, indent=2)
        
        logger.info(f"Stats saved to {stats_path}")


def run_pipeline_cli():
    """CLI entry point for running data pipeline."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Run RAG data pipeline'
    )
    parser.add_argument(
        '--data-dir',
        type=Path,
        default=Path('data'),
        help='Base data directory'
    )
    parser.add_argument(
        '--sources',
        nargs='+',
        required=True,
        help='Source names to process (e.g., arch_wiki stackoverflow)'
    )
    parser.add_argument(
        '--output-name',
        type=str,
        default='all_sources',
        help='Output file name'
    )
    
    args = parser.parse_args()
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Run pipeline
    pipeline = DataPipeline(args.data_dir)
    stats = pipeline.process_pipeline(args.sources, args.output_name)
    
    # Print summary
    print("\n" + "=" * 60)
    print("PIPELINE SUMMARY")
    print("=" * 60)
    print(f"Total scraped:       {stats.total_scraped}")
    print(f"Invalid removed:     {stats.invalid_removed}")
    print(f"Duplicates removed:  {stats.duplicates_removed}")
    print(f"Final count:         {stats.final_count}")
    print("\nBy source:")
    for source, count in stats.sources.items():
        print(f"  {source:20s} {count:5d}")
    print("\nBy category:")
    for category, count in stats.categories.items():
        print(f"  {category:20s} {count:5d}")
    print("=" * 60)


if __name__ == '__main__':
    run_pipeline_cli()
