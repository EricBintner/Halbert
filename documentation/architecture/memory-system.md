# Memory System

Cerebric's memory system provides persistent, queryable knowledge storage using ChromaDB as a vector database.

---

## Overview

The memory system serves as the LLM's "biography" - its accumulated knowledge about the system it manages.

**Code**: `cerebric_core/cerebric_core/memory/`

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│                 Memory System                    │
├─────────────────────────────────────────────────┤
│                                                  │
│  ┌─────────────┐    ┌─────────────┐            │
│  │   Writer    │    │  Retrieval  │            │
│  │             │    │             │            │
│  │ write_core  │    │ retrieve_   │            │
│  │ write_action│    │    from()   │            │
│  └──────┬──────┘    └──────┬──────┘            │
│         │                  │                    │
│         ▼                  ▼                    │
│  ┌─────────────────────────────────────┐       │
│  │           ChromaDB Index            │       │
│  │                                     │       │
│  │  ┌─────────┐  ┌─────────┐          │       │
│  │  │  core   │  │ runtime │  ...     │       │
│  │  └─────────┘  └─────────┘          │       │
│  └─────────────────────────────────────┘       │
│                                                  │
└─────────────────────────────────────────────────┘
```

---

## Memory Subdirectories

| Directory | Purpose | Retention |
|-----------|---------|-----------|
| `core/` | System knowledge, documentation | Permanent |
| `runtime/` | Action outcomes, events | Rolling window |

---

## Writing to Memory

### Core Knowledge

Static knowledge about the system.

```python
from cerebric_core.cerebric_core.memory.writer import MemoryWriter

writer = MemoryWriter()

# Write system knowledge
writer.write_core_knowledge({
    "type": "system_info",
    "content": "This system runs Ubuntu 24.04 LTS",
    "source": "os-release",
    "timestamp": "2024-01-15T10:30:00Z"
})
```

### Action Outcomes

Results of executed actions.

```python
# Write action result
writer.write_action_outcome({
    "action": "restart_service",
    "target": "docker.service",
    "success": True,
    "output": "Service restarted successfully",
    "timestamp": "2024-01-15T10:31:00Z",
    "duration_ms": 2340
})
```

---

## Querying Memory

```python
from cerebric_core.cerebric_core.memory.retrieval import MemoryRetrieval

mem = MemoryRetrieval()

# Query core knowledge
results = mem.retrieve_from(
    subdir="core",
    query="docker configuration",
    k=5
)

for result in results:
    print(f"Score: {result['_score']:.2f}")
    print(f"Text: {result['text'][:100]}...")
```

---

## CLI Commands

```bash
# Query memory
python Cerebric/main.py memory-query \
  --subdir core \
  --query "docker errors" \
  --limit 10

# Show statistics
python Cerebric/main.py memory-stats

# Write test entry
python Cerebric/main.py memory-write \
  --subdir core \
  --entry '{"type": "test", "content": "Test entry"}'
```

---

## Storage Location

```
~/.local/share/cerebric/
├── index/                  # ChromaDB database
│   ├── chroma.sqlite3
│   └── ...
└── memory/
    ├── core/               # Core knowledge collection
    └── runtime/            # Runtime events collection
```

---

## Embedding Model

Memory uses sentence-transformers for embeddings:

```python
# Default: all-MiniLM-L6-v2
# Small, fast, good quality for semantic search
model = SentenceTransformer('all-MiniLM-L6-v2')
```

Model is cached at `~/.cache/cerebric/models/`.

---

## Integration with RAG

The memory system integrates with the RAG pipeline:

```
User Query
    │
    ▼
┌─────────────┐
│  Retrieval  │
│             │
│ ┌─────────┐ │
│ │ Memory  │ │  Local knowledge
│ └─────────┘ │
│ ┌─────────┐ │
│ │  RAG    │ │  Documentation corpus
│ └─────────┘ │
└─────────────┘
    │
    ▼
Combined Context
    │
    ▼
LLM Generation
```

---

## Configuration

No explicit configuration required. Memory uses XDG paths by default.

To override:

```bash
export Cerebric_DATA_DIR=/custom/path
```

---

## Implementation Details

### Index Class

**Code**: `cerebric_core/cerebric_core/index/chroma_index.py`

```python
class Index:
    def __init__(self, data_dir: str = None):
        self.client = chromadb.PersistentClient(path=data_dir)
    
    def add(self, documents: list[str], metadata: list[dict]):
        collection = self.client.get_or_create_collection("default")
        collection.add(
            documents=documents,
            metadatas=metadata,
            ids=[str(uuid4()) for _ in documents]
        )
    
    def query(self, text: str, k: int = 5) -> list[dict]:
        collection = self.client.get_collection("default")
        results = collection.query(query_texts=[text], n_results=k)
        return results
```

---

## Related

- [architecture/rag-pipeline.md](rag-pipeline.md) - RAG system
- [ARCHITECTURE.md](../ARCHITECTURE.md) - System overview
- [reference/code-map.md](../reference/code-map.md) - File locations
