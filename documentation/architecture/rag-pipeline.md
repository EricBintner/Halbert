# RAG Pipeline

Retrieval-Augmented Generation (RAG) grounds Halbert's responses in documentation and system knowledge.

---

## Overview

RAG retrieves relevant documents before LLM generation, ensuring responses are accurate and grounded in real information.

**Code**: `halbert_core/halbert_core/rag/`

---

## Pipeline Architecture

```
User Query
    │
    ▼
┌──────────────────┐
│     Embed        │  Convert query to vector
└──────────────────┘
    │
    ▼
┌──────────────────┐
│    Retrieve      │  Find similar documents
└──────────────────┘
    │
    ▼
┌──────────────────┐
│    Rerank        │  Score by relevance
└──────────────────┘
    │
    ▼
┌──────────────────┐
│    Generate      │  LLM with context
└──────────────────┘
    │
    ▼
Response
```

---

## Components

### Document Loader

Loads and chunks documentation.

```python
from halbert_core.halbert_core.rag import RAGPipeline

pipeline = RAGPipeline(data_dir=Path("data/"))
pipeline.load_and_index_documents()
```

Supported formats:
- Markdown (`.md`)
- Plain text (`.txt`)
- JSON (`.json`, `.jsonl`)

### Embedding Model

Default: `sentence-transformers/all-MiniLM-L6-v2`

- 384-dimensional vectors
- Fast inference
- Good semantic similarity

### Vector Store

ChromaDB for persistent storage.

```python
# Query the index
docs = pipeline.retrieve(query="systemd service failures", k=5)
```

### Reranker

Optional cross-encoder reranking for better precision.

```python
pipeline = RAGPipeline(
    data_dir=data_dir,
    use_reranking=True,  # Enable reranking
    top_k=3
)
```

### LLM Integration

```python
from halbert_core.halbert_core.rag.llm import OllamaLLM

llm = OllamaLLM(model="llama3.2:3b")
response = pipeline.generate(query="Why did docker fail?", llm=llm)
```

---

## Data Sources

### Trust Tiers

| Tier | Source | Trust Level |
|------|--------|-------------|
| 1 | Official docs (Arch Wiki, man pages) | High |
| 2 | Verified community (Stack Overflow accepted) | Medium |
| 3 | Community content | Lower |

### Data Directory Structure

```
data/linux/
├── arch-wiki/           # Arch Wiki articles
├── man-pages/           # Man page extracts
├── stack-overflow/      # Q&A pairs
├── ubuntu-docs/         # Ubuntu documentation
└── ...
```

---

## CLI Usage

```bash
# Ask a question with RAG
python Halbert/main.py ask "How do I fix broken apt packages?"

# Retrieve without LLM generation
python Halbert/main.py ask "systemd timers" --no-llm

# Use different model
python Halbert/main.py ask "docker networking" --model llama3.1:70b

# Retrieve more documents
python Halbert/main.py ask "nginx config" --top-k 10
```

---

## Retrieval Process

### 1. Query Embedding

```python
query_vector = embedder.encode(query)
```

### 2. Similarity Search

```python
# Find k most similar documents
results = collection.query(
    query_embeddings=[query_vector],
    n_results=k
)
```

### 3. Reranking (Optional)

```python
# Cross-encoder scoring
reranked = reranker.rerank(query, results)
```

### 4. Context Assembly

```python
context = "\n\n".join([doc["content"] for doc in reranked[:3]])
```

---

## Prompt Template

```python
PROMPT_TEMPLATE = """You are Halbert, a Linux system assistant.

Use the following documentation to answer the question:

{context}

Question: {query}

Answer based on the documentation above. If the documentation doesn't contain the answer, say so.
"""
```

---

## Configuration

### Pipeline Options

```python
pipeline = RAGPipeline(
    data_dir=Path("data/"),
    
    # Retrieval settings
    top_k=5,
    use_reranking=True,
    
    # Embedding model
    embedding_model="sentence-transformers/all-MiniLM-L6-v2",
    
    # Chunking
    chunk_size=512,
    chunk_overlap=50,
)
```

---

## Performance

### Benchmarks

| Operation | Time |
|-----------|------|
| Query embedding | ~10ms |
| Vector search (10k docs) | ~20ms |
| Reranking (5 docs) | ~100ms |
| Total retrieval | ~130ms |

### Optimization Tips

1. **Pre-index documents** - Don't reload on every query
2. **Use appropriate top_k** - Higher k = more context but slower
3. **Enable reranking** - Better precision at small cost
4. **Batch queries** - When processing multiple queries

---

## Extending

### Adding New Data Sources

1. Add documents to `data/linux/your-source/`
2. Include metadata in each document:

```json
{
  "content": "Document text...",
  "metadata": {
    "source": "your-source",
    "source_url": "https://...",
    "trust_tier": 2
  }
}
```

3. Re-index:

```python
pipeline.load_and_index_documents()
```

### Custom Embeddings

```python
from sentence_transformers import SentenceTransformer

custom_model = SentenceTransformer("your-model")
pipeline = RAGPipeline(embedding_model=custom_model)
```

---

## Related

- [architecture/memory-system.md](memory-system.md) - Memory integration
- [ARCHITECTURE.md](../ARCHITECTURE.md) - System overview
- [reference/code-map.md](../reference/code-map.md) - File locations
