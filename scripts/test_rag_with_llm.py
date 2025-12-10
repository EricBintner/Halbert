#!/usr/bin/env python3
"""
Test RAG system with LLM integration.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'halbert_core'))

from halbert_core.rag import RAGPipeline
from halbert_core.rag.llm import OllamaLLM, LLMConfig


def test_rag_with_llm():
    print("="*70)
    print("Halbert RAG + LLM DEMO")
    print("="*70)
    
    # Initialize RAG
    print("\n1. Initializing RAG pipeline...")
    pipeline = RAGPipeline(
        data_dir=Path('data'),
        use_reranking=True,
        top_k=3
    )
    
    print("2. Loading documents...")
    pipeline.load_and_index_documents()
    print(f"   ✓ Indexed {len(pipeline.retriever._documents)} documents")
    
    # Initialize LLM
    print("\n3. Initializing LLM...")
    llm_config = LLMConfig(
        model="llama3.2:3b",  # Fast, good quality
        temperature=0.3,  # Lower for more factual responses
        max_tokens=512
    )
    llm = OllamaLLM(config=llm_config)
    
    if not llm.check_available():
        print("✗ Ollama is not available!")
        print("  Start with: ollama serve")
        return
    
    print(f"   ✓ Using model: {llm_config.model}")
    
    # Test queries
    test_queries = [
        "How do I check GPU memory usage?",
        "What command shows disk space?",
        "How do I restart a systemd service?",
    ]
    
    print("\n4. Testing RAG + LLM...\n")
    
    for i, query in enumerate(test_queries, 1):
        print("="*70)
        print(f"Query {i}: {query}")
        print("="*70)
        
        # Retrieve relevant docs
        print("\nRetrieving documents...", flush=True)
        docs = pipeline.retrieve(query)
        
        if docs:
            print(f"Found {len(docs)} relevant documents:")
            for j, doc in enumerate(docs, 1):
                print(f"  {j}. {doc['name']} (score: {doc['score']:.3f})")
            
            # Generate answer
            print("\nGenerating answer...", flush=True)
            answer = llm.generate_with_context(query, docs, max_context_docs=3)
            
            print(f"\n📖 Answer:\n{answer}")
        else:
            print("  No relevant documents found")
        
        print()


def test_interactive():
    """Interactive mode with LLM."""
    print("="*70)
    print("Halbert RAG + LLM: Interactive Mode")
    print("="*70)
    print("\nType your questions (or 'quit' to exit)\n")
    
    # Initialize
    pipeline = RAGPipeline(data_dir=Path('data'), use_reranking=True, top_k=3)
    pipeline.load_and_index_documents()
    
    llm = OllamaLLM(config=LLMConfig(model="llama3.2:3b", temperature=0.3))
    
    if not llm.check_available():
        print("✗ Ollama not available. Start with: ollama serve")
        return
    
    print(f"✓ Ready! Using {llm.config.model}\n")
    
    while True:
        try:
            query = input("❓ Question> ").strip()
            
            if query.lower() in ['quit', 'exit', 'q']:
                print("Goodbye!")
                break
            
            if not query:
                continue
            
            # Retrieve + Generate
            docs = pipeline.retrieve(query)
            
            if docs:
                print(f"\n📚 Found {len(docs)} relevant docs: {', '.join(d['name'] for d in docs[:3])}")
                print("💭 Thinking...", flush=True)
                answer = llm.generate_with_context(query, docs)
                print(f"\n✨ {answer}\n")
            else:
                print("  No relevant documentation found.\n")
                
        except KeyboardInterrupt:
            print("\nGoodbye!")
            break
        except Exception as e:
            print(f"\n⚠ Error: {e}\n")


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description="Test RAG with LLM")
    parser.add_argument('--mode', choices=['test', 'interactive'], default='test',
                       help='Run mode: test examples or interactive')
    
    args = parser.parse_args()
    
    if args.mode == 'test':
        test_rag_with_llm()
    else:
        test_interactive()
