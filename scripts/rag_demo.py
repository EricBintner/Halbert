#!/usr/bin/env python3
"""
Demo script for Halbert RAG system.

Shows how to use the RAG pipeline for man page retrieval.
"""

import sys
from pathlib import Path

# Add halbert_core to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'halbert_core'))

from halbert_core.rag import RAGPipeline


def demo_basic_retrieval():
    """Demo basic retrieval without LLM."""
    print("=" * 70)
    print("Halbert RAG DEMO: Basic Retrieval")
    print("=" * 70)
    
    # Initialize pipeline
    print("\n1. Initializing RAG pipeline...")
    pipeline = RAGPipeline(
        data_dir=Path('data'),
        use_reranking=True,
        top_k=5
    )
    
    # Load and index man pages
    print("2. Loading and indexing man pages...")
    pipeline.load_and_index_documents()
    print(f"   ✓ Indexed {len(pipeline.retriever._documents)} documents")
    
    # Test queries
    queries = [
        "How do I restart a systemd service?",
        "Check disk space usage",
        "Change file permissions to executable",
        "View system logs",
        "Network interface configuration"
    ]
    
    print("\n3. Testing retrieval with sample queries...\n")
    
    for i, query in enumerate(queries, 1):
        print(f"\n{'─' * 70}")
        print(f"Query {i}: {query}")
        print('─' * 70)
        
        # Retrieve
        results = pipeline.retrieve(query)
        
        print(f"Retrieved {len(results)} documents:\n")
        
        for j, doc in enumerate(results, 1):
            name = doc['name']
            section = doc['section']
            score = doc['score']
            desc = doc['description'][:80] + '...' if len(doc['description']) > 80 else doc['description']
            
            print(f"  {j}. {name}({section}) - Score: {score:.3f}")
            print(f"     {desc}")


def demo_with_context():
    """Demo context building for LLM."""
    print("\n" + "=" * 70)
    print("Halbert RAG DEMO: Context Building")
    print("=" * 70)
    
    # Initialize pipeline
    pipeline = RAGPipeline(
        data_dir=Path('data'),
        use_reranking=True,
        top_k=3
    )
    
    pipeline.load_and_index_documents()
    
    query = "How do I restart a systemd service?"
    
    print(f"\nQuery: {query}\n")
    
    # Retrieve
    docs = pipeline.retrieve(query)
    
    # Build context
    context = pipeline.build_context(query, docs)
    
    print("Built context for LLM:")
    print("─" * 70)
    print(context[:1000] + "\n..." if len(context) > 1000 else context)
    print("─" * 70)
    print(f"\nContext length: {len(context)} characters")


def demo_full_pipeline():
    """Demo full pipeline with mock LLM."""
    print("\n" + "=" * 70)
    print("Halbert RAG DEMO: Full Pipeline")
    print("=" * 70)
    
    # Initialize pipeline
    pipeline = RAGPipeline(
        data_dir=Path('data'),
        use_reranking=True,
        top_k=5
    )
    
    pipeline.load_and_index_documents()
    
    # Mock LLM function
    def mock_llm(query, context):
        """Mock LLM that just returns context summary."""
        lines = context.split('\n')
        doc_names = [line for line in lines if line.startswith('## ')]
        
        answer = f"Based on the following documentation:\n"
        for doc in doc_names[:3]:
            answer += f"  - {doc.replace('## ', '').strip()}\n"
        answer += f"\n[Mock LLM would generate detailed answer here based on context]"
        
        return answer
    
    query = "How do I check system logs?"
    
    print(f"\nQuery: {query}\n")
    
    # Full RAG query
    response = pipeline.query(query, llm_generate_fn=mock_llm)
    
    print("Answer:")
    print("─" * 70)
    print(response.answer)
    print("─" * 70)
    
    print(f"\n{pipeline.format_citations(response.sources)}")
    
    print(f"\nMetadata:")
    print(f"  - Retrieved: {response.retrieved_count} documents")
    print(f"  - Latency: {response.latency_ms:.1f}ms")
    print(f"  - Reranking: {response.metadata['use_reranking']}")


def interactive_mode():
    """Interactive query mode."""
    print("\n" + "=" * 70)
    print("Halbert RAG: Interactive Mode")
    print("=" * 70)
    print("\nType your queries (or 'quit' to exit)\n")
    
    # Initialize pipeline
    print("Loading RAG pipeline...")
    pipeline = RAGPipeline(
        data_dir=Path('data'),
        use_reranking=True,
        top_k=5
    )
    
    pipeline.load_and_index_documents()
    print("✓ Ready!\n")
    
    while True:
        try:
            query = input("Query> ").strip()
            
            if query.lower() in ['quit', 'exit', 'q']:
                print("Goodbye!")
                break
            
            if not query:
                continue
            
            # Retrieve
            results = pipeline.retrieve(query)
            
            print(f"\nRetrieved {len(results)} documents:\n")
            
            for i, doc in enumerate(results, 1):
                name = doc['name']
                section = doc['section']
                score = doc['score']
                desc = doc['description'][:60] + '...' if len(doc['description']) > 60 else doc['description']
                
                print(f"  {i}. {name}({section}) - {score:.3f}")
                print(f"     {desc}\n")
        
        except KeyboardInterrupt:
            print("\n\nGoodbye!")
            break
        except Exception as e:
            print(f"Error: {e}")


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Halbert RAG System Demo'
    )
    parser.add_argument(
        '--mode',
        choices=['basic', 'context', 'full', 'interactive'],
        default='basic',
        help='Demo mode to run'
    )
    
    args = parser.parse_args()
    
    try:
        if args.mode == 'basic':
            demo_basic_retrieval()
        elif args.mode == 'context':
            demo_with_context()
        elif args.mode == 'full':
            demo_full_pipeline()
        elif args.mode == 'interactive':
            interactive_mode()
    
    except FileNotFoundError as e:
        print(f"\nError: {e}")
        print("\nMake sure man pages data exists at: data/linux/man-pages/man_pages.jsonl")
        print("Run this from the LinuxBrain root directory.")
        sys.exit(1)
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
