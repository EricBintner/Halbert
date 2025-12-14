# Halbert Architecture

This document provides a high-level overview of Halbert's architecture. For detailed component documentation, see the [architecture/](architecture/) directory.

**Legend**: ✅ Implemented | 🔄 Partial | 📋 Planned

---

## System Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         User Interface  ✅                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────────────┐  │
│  │   CLI       │  │  Dashboard  │  │        REST API                 │  │
│  │ (main.py)   │  │  (React)    │  │       (FastAPI)                 │  │
│  └──────┬──────┘  └──────┬──────┘  └────────────────┬────────────────┘  │
└─────────┼────────────────┼──────────────────────────┼───────────────────┘
          │                │                          │
          ▼                ▼                          ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         Chat Engine  ✅                                 │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │              Smart Model Router (Guide ↔ Specialist)             │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  │   │
│  │  │ Context  │→ │  Model   │→ │  Ollama  │→ │    Response      │  │   │
│  │  │ Injection│  │ Selection│  │   API    │  │    + Actions     │  │   │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────────────┘  │   │
│  └──────────────────────────────────────────────────────────────────┘   │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
          ┌──────────────────────┼──────────────────────┐
          ▼                      ▼                      ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────────┐
│  Model System ✅ │  │ Memory System ✅│  │    Discovery System  ✅     │
│  ┌───────────┐  │  │  ┌───────────┐  │  │  ┌─────────┐ ┌───────────┐  │
│  │  Ollama   │  │  │  │ ChromaDB  │  │  │  │Storage  │ │Network    │  │
│  │  Backend  │  │  │  │ (Vector)  │  │  │  │Scanner  │ │Scanner    │  │
│  └───────────┘  │  │  └───────────┘  │  │  └─────────┘ └───────────┘  │
│  ┌───────────┐  │  │  ┌───────────┐  │  │  ┌─────────┐ ┌───────────┐  │
│  │  Vision   │  │  │  │Conversation│ │  │  │Service  │ │Security   │  │
│  │  Model    │  │  │  │ Retrieval │  │  │  │Scanner  │ │Scanner    │  │
│  └───────────┘  │  │  └───────────┘  │  │  └─────────┘ └───────────┘  │
└─────────────────┘  └─────────────────┘  └─────────────────────────────┘
          │                      │                      │
          └──────────────────────┼──────────────────────┘
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         Data Layer                                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌───────────────┐   │
│  │ RAG Pipeline│  │   Config    │  │  Approval   │  │  AI Rules     │   │
│  │  ✅ Hybrid  │  │   Editor ✅ │  │  System 🔄  │  │     ✅        │   │
│  └─────────────┘  └─────────────┘  └─────────────┘  └───────────────┘   │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────────────┐  │
│  │  Scheduler  │  │ Ingestion   │  │        Guardrails               │  │
│  │    📋      │  │    📋       │  │          📋                     │  │
│  └─────────────┘  └─────────────┘  └─────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Core Components

### 1. User Interface Layer ✅

| Component | Location | Purpose | Status |
|-----------|----------|---------|--------|
| **Dashboard** | `halbert_core/dashboard/` | React + FastAPI web interface | ✅ |
| **REST API** | `halbert_core/dashboard/routes/` | Programmatic access | ✅ |
| **CLI** | `Halbert/main.py` | Command-line interface | 🔄 |

The dashboard is the primary interface with 16 pages covering system management. The REST API provides full programmatic access.

### 2. Chat Engine ✅

| Component | Location | Purpose | Status |
|-----------|----------|---------|--------|
| **Chat Routes** | `dashboard/routes/chat.py` | Main chat processing | ✅ |
| **Model Router** | `model/router.py` | Complexity-based model selection | ✅ |
| **Context Injection** | `routes/chat.py` | Auto-inject relevant discoveries | ✅ |

The chat engine processes user queries through:
1. **Context injection** — Keywords trigger relevant discovery injection
2. **Memory retrieval** — ChromaDB semantic search for past conversations  
3. **Model selection** — Complexity scoring routes to Guide (8B) or Specialist (70B)
4. **Ollama API** — Direct API calls to local LLM
5. **Response + actions** — Response with suggested actions and tool calling

### 3. Model System ✅

| Component | Location | Purpose | Status |
|-----------|----------|---------|--------|
| **Guide Model** | Configurable | Fast 8B model for simple queries | ✅ |
| **Specialist Model** | Configurable | Large 70B model for complex reasoning | ✅ |
| **Vision Model** | Configurable | Multimodal for image analysis | ✅ |
| **Model Config** | `~/.config/halbert/models.yml` | Endpoint + model assignments | ✅ |

Models are configured per-role with separate endpoints. Complexity scoring routes queries automatically.

```yaml
# ~/.config/halbert/models.yml
orchestrator:
  endpoint: http://localhost:11434
  model: llama3.1:8b
specialist:
  enabled: true
  endpoint: http://remote:11434
  model: llama3.1:70b
vision:
  endpoint: http://localhost:11434
  model: llava:34b
```

### 4. Memory System ✅

| Component | Location | Purpose | Status |
|-----------|----------|---------|--------|
| **ChromaDB Index** | `index/chroma_index.py` | Persistent vector storage | ✅ |
| **Conversation Memory** | `self_conversations` collection | Chat history for retrieval | ✅ |
| **Knowledge Index** | `self_knowledge_all` collection | Global knowledge base | ✅ |
| **Memory API** | `/api/chat/memory/*` | Stats and query endpoints | ✅ |

The memory system provides semantic search over past conversations:
- Conversations stored with embeddings in ChromaDB
- Relevant past context auto-injected into new queries
- Persisted to `~/.local/share/halbert/chromadb/`

### 5. Discovery System ✅

| Component | Location | Purpose | Status |
|-----------|----------|---------|--------|
| **Discovery Engine** | `discovery/engine.py` | Scanner orchestration | ✅ |
| **Storage Scanner** | `discovery/scanners/disk_usage.py` | Disks, filesystems, SMART | ✅ |
| **Service Scanner** | `discovery/scanners/services.py` | Systemd services | ✅ |
| **Network Scanner** | `discovery/scanners/network.py` | Interfaces, bridges, VPN | ✅ |
| **Security Scanner** | `discovery/scanners/security.py` | SSH, firewall, users | ✅ |
| **Sharing Scanner** | `discovery/scanners/sharing.py` | NFS, SMB, Tailscale | ✅ |
| **Backup Scanner** | `discovery/scanners/backup.py` | Timeshift, Borg | ✅ |

Scanners run on-demand per page and store results in ChromaDB for context injection.

### 6. RAG Pipeline ✅

| Component | Location | Purpose | Status |
|-----------|----------|---------|--------|
| **RAG Pipeline** | `rag/pipeline.py` | End-to-end retrieval | ✅ |
| **Hybrid Retriever** | `rag/retriever.py` | BM25 + dense embeddings | ✅ |
| **Embedding Manager** | `rag/embeddings.py` | Sentence transformers | ✅ |
| **Index Builder** | `rag/index_builder.py` | Document indexing | ✅ |

Hybrid retrieval combines:
- **BM25** sparse retrieval for keyword matching
- **Dense embeddings** for semantic similarity
- **RRF fusion** to merge results
- **Cross-encoder reranking** for precision

### 7. Config Editor ✅

| Component | Location | Purpose | Status |
|-----------|----------|---------|--------|
| **Editor Routes** | `routes/editor.py` | File read/write API | ✅ |
| **Config Chat** | `routes/chat.py` | AI-assisted editing | ✅ |
| **ConfigEditor UI** | `frontend/components/ConfigEditor.tsx` | Monaco editor + diff | ✅ |

AI-assisted config editing with SEARCH/REPLACE blocks and inline diff view.

### 8. Ingestion Pipeline 📋

| Component | Location | Purpose | Status |
|-----------|----------|---------|--------|
| **journald** | `ingestion/journald.py` | System log collection | 📋 |
| **hwmon** | `ingestion/hwmon.py` | Hardware sensor collection | 📋 |
| **JSONL Writer** | `ingestion/jsonl_writer.py` | Event persistence | 📋 |

**Planned**: Continuous telemetry collection and indexing. Currently, discoveries are on-demand.

### 9. Scheduler 📋

| Component | Location | Purpose | Status |
|-----------|----------|---------|--------|
| **Scheduler Engine** | `scheduler/engine.py` | APScheduler wrapper | 📋 |
| **Autonomous Tasks** | `scheduler/autonomous_tasks.py` | LLM-driven tasks | 📋 |

**Planned**: Background tasks for health checks, trend analysis, proactive maintenance.

### 10. Guardrails 📋

| Component | Location | Purpose | Status |
|-----------|----------|---------|--------|
| **Guardrails** | `autonomy/guardrails.py` | Safety checks | 📋 |
| **Budgets** | `autonomy/budgets.py` | Rate limiting | 📋 |
| **AI Rules** | `settings/ai_rules.yml` | User-defined rules | ✅ |

**Partial**: AI Rules implemented for user-defined guardrails. Full budget/rate-limiting planned.

### 11. Approval System 🔄

| Component | Location | Purpose | Status |
|-----------|----------|---------|--------|
| **Approval Routes** | `routes/approvals.py` | Approval workflow API | 🔄 |
| **Approval Page** | `pages/Approvals.tsx` | Pending approvals UI | 🔄 |

**Partial**: UI exists, workflow integration minimal.

---

## Data Flow

### Chat Query Flow (Current Implementation)

```
User Message
    │
    ▼
┌───────────────────────────────────────┐
│ 1. Parse message and @mentions        │
└───────────────────────────────────────┘
    │
    ▼
┌───────────────────────────────────────┐
│ 2. Context Injection                  │
│    - Page context (current view)      │
│    - Memory retrieval (ChromaDB)      │
│    - Keyword → discovery mapping      │
│    - Failure correlation              │
└───────────────────────────────────────┘
    │
    ▼
┌───────────────────────────────────────┐
│ 3. Model Selection                    │
│    - Complexity scoring               │
│    - Route to Guide or Specialist     │
└───────────────────────────────────────┘
    │
    ▼
┌───────────────────────────────────────┐
│ 4. Ollama API Call                    │
│    - System prompt + context          │
│    - Conversation history             │
│    - Vision model if images present   │
└───────────────────────────────────────┘
    │
    ▼
┌───────────────────────────────────────┐
│ 5. Response Processing                │
│    - Store in conversation memory     │
│    - Parse tool calls if present      │
│    - Generate suggested actions       │
└───────────────────────────────────────┘
    │
    ▼
Response to User
```

### Discovery Flow

```
Page Load (e.g., Storage)
    │
    ▼
┌───────────────────────────────────────┐
│ 1. Frontend requests /api/discovery   │
└───────────────────────────────────────┘
    │
    ▼
┌───────────────────────────────────────┐
│ 2. Discovery Engine runs scanner      │
│    - StorageScanner for Storage page  │
│    - Detects disks, filesystems, etc. │
└───────────────────────────────────────┘
    │
    ▼
┌───────────────────────────────────────┐
│ 3. Store in ChromaDB                  │
│    - discoveries collection           │
│    - With embedding for search        │
└───────────────────────────────────────┘
    │
    ▼
┌───────────────────────────────────────┐
│ 4. Return to frontend                 │
│    - Display in page UI               │
│    - Available for @mentions          │
└───────────────────────────────────────┘
```

---

## Configuration

### File Locations (XDG-Compliant)

| Type | Path | Purpose |
|------|------|---------|
| **Config** | `~/.config/halbert/` | User configuration |
| **Data** | `~/.local/share/halbert/` | Persistent data |
| **ChromaDB** | `~/.local/share/halbert/chromadb/` | Vector database |
| **Conversations** | `~/.local/share/halbert/conversations/` | Chat history |

### Key Configuration Files

| File | Purpose | Status |
|------|---------|--------|
| `models.yml` | Model/endpoint configuration | ✅ |
| `ai_rules.yml` | Custom AI guardrails | ✅ |
| `personas/` | Persona definitions | ✅ |
| `ingestion.yml` | Telemetry settings | 📋 |
| `policy.yml` | Policy rules | 📋 |
| `autonomy.yml` | Guardrail settings | 📋 |

---

## Dependencies

### Python Packages

| Package | Purpose | Status |
|---------|---------|--------|
| `pydantic` | Data validation | ✅ |
| `fastapi` | REST API | ✅ |
| `chromadb` | Vector database | ✅ |
| `sentence-transformers` | Embeddings | ✅ |
| `rank-bm25` | Sparse retrieval | ✅ |
| `pyyaml` | Config parsing | ✅ |
| `requests` | HTTP client | ✅ |

### External Services

| Service | Purpose |
|---------|---------|
| **Ollama** | Local LLM inference |

Halbert runs entirely locally. No external API calls required.

---

## Next Steps

Priority items from gap analysis:

1. **Ingestion Pipeline** — Continuous journald/hwmon collection
2. **Scheduler** — Background autonomous tasks  
3. **Guardrails** — Budget/rate limiting enforcement
4. **Approval Workflow** — Full dry-run + approval flow

See [GAPS.md](GAPS.md) for detailed gap analysis.

---

## Related Documentation

- [FEATURES.md](FEATURES.md) — Complete feature list
- [API-REFERENCE.md](API-REFERENCE.md) — REST API documentation  
- [architecture/](architecture/) — Component deep-dives
- [CONFIGURATION.md](CONFIGURATION.md) — Configuration reference
