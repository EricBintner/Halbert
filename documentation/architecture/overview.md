# Architecture Overview

This document provides a comprehensive view of Halbert's architecture, explaining how components interact to create a self-aware Linux system agent.

---

## Design Goals

1. **Self-Identification** — The LLM identifies as the computer, not as an external assistant
2. **Grounded Responses** — Every claim about system state is backed by actual data
3. **Safe Autonomy** — The system can act, but with layered safety controls
4. **Local-First** — Everything runs on your machine, no external dependencies
5. **Extensibility** — New tools and capabilities can be added without restructuring

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              User Layer                                     │
│  ┌─────────────┐  ┌──────────────────┐  ┌────────────────────────────────┐  │
│  │    CLI      │  │    Dashboard     │  │         REST API               │  │
│  │  (Typer)    │  │ (React+FastAPI)  │  │        (FastAPI)               │  │
│  └──────┬──────┘  └────────┬─────────┘  └──────────────┬─────────────────┘  │
└─────────┼──────────────────┼───────────────────────────┼────────────────────┘
          │                  │                           │
          └──────────────────┴───────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            Chat Engine                                   │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                  Direct Ollama API (routes/chat.py)                 │   │
│  │                                                                      │   │
│  │  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────────┐   │   │
│  │  │ Context  │ →  │  Model   │ →  │  Ollama  │ →  │   Response   │   │   │
│  │  │Injection │    │ Selection│    │   API    │    │  + Actions   │   │   │
│  │  └──────────┘    └──────────┘    └──────────┘    └──────────────┘   │   │
│  │                        │              │                              │   │
│  │                        ▼              ▼                              │   │
│  │                 ┌──────────┐   ┌───────────┐                         │   │
│  │                 │  Policy  │   │ Guardrails│                         │   │
│  │                 │  Check   │   │ + Approval│                         │   │
│  │                 └──────────┘   └───────────┘                         │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└───────────────────────────────────────┴─────────────────────────────────────┘
                                     │
          ┌──────────────────────────┼──────────────────────────┐
          │                          │                          │
          ▼                          ▼                          ▼
┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────────┐
│    Model Layer      │  │    Memory Layer     │  │      Tool Layer         │
│                     │  │                     │  │                         │
│  ┌───────────────┐  │  │  ┌───────────────┐  │  │  ┌─────────────────┐    │
│  │    Ollama     │  │  │  │   ChromaDB    │  │  │  │   read_sensor   │    │
│  │   (Llama 3)   │  │  │  │ (Embeddings)  │  │  │  │   write_config  │    │
│  └───────────────┘  │  │  └───────────────┘  │  │  │   schedule_cron │    │
│  ┌───────────────┐  │  │  ┌───────────────┐  │  │  │   query_journal │    │
│  │    Prompt     │  │  │  │   Retrieval   │  │  │  │   ...           │    │
│  │   Manager     │  │  │  │    Engine     │  │  │  └─────────────────┘    │
│  └───────────────┘  │  │  └───────────────┘  │  │                         │
└─────────────────────┘  └─────────────────────┘  └─────────────────────────┘
          │                          │                          │
          └──────────────────────────┼──────────────────────────┘
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Data Layer                                     │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────────┐  │
│  │   Ingestion     │  │     Config      │  │        Scheduler            │  │
│  │  (journald,     │  │    Registry     │  │      (APScheduler)          │  │
│  │   hwmon)        │  │  (snapshots)    │  │                             │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────────────────┘  │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────────┐  │
│  │     Policy      │  │    Guardrails   │  │         Audit               │  │
│  │     Engine      │  │    (Budgets,    │  │         Trail               │  │
│  │                 │  │     Limits)     │  │                             │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Linux System                                      │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐ │
│  │ journald  │  │   /proc   │  │   /sys    │  │  systemd  │  │   /etc    │ │
│  └───────────┘  └───────────┘  └───────────┘  └───────────┘  └───────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Component Relationships

### Request Flow (User Query)

1. **User Input** → CLI, Dashboard, or API receives the query
2. **Context Injection** → Relevant discoveries, memory, docs injected
3. **Model Selection** → Complexity scoring routes to Guide or Specialist
4. **Ollama API** → Direct API call with system prompt + context
5. **Tool Authorization** → Policy + Guardrails check before tool execution
6. **Approval** → If required, queue for user confirmation
7. **Tool Execution** → Run the tool with audit logging
8. **Response** → Grounded response with suggested actions

### Background Flow (Autonomous)

1. **Scheduler** → APScheduler triggers a scheduled task
2. **Ingestion** → Collect fresh telemetry (journald, hwmon)
3. **Indexing** → Embed and store in ChromaDB
4. **Analysis** → Deep Thinker reviews trends
5. **Guardrails** → Check operation budgets
6. **Action** → Execute if within limits, queue for approval if not
7. **Logging** → Record all decisions in audit trail

---

## Key Architectural Decisions

### Why Direct Ollama API? (DEPRECATED LangGraph)

**Original plan**: Use LangGraph for state machine orchestration.

**Actual implementation**: Direct Ollama API calls in `routes/chat.py`.

Why we changed:
- **Simplicity** — Direct API calls are easier to debug and maintain
- **Performance** — No LangGraph overhead, faster responses
- **Flexibility** — Custom context injection works better without framework constraints
- **Local-first** — No dependency on external orchestration libraries

LangGraph would add complexity without clear benefit for our use case (single-turn Q&A with context).

### Why ChromaDB?

ChromaDB provides:
- **Local-first** — No external service required
- **Embedding storage** — Semantic search over events
- **Metadata filtering** — Query by time, severity, source
- **Persistence** — Survives restarts

Alternative considered: Pinecone. Rejected because it requires cloud connectivity.

### Why Ollama?

Ollama provides:
- **Local inference** — No API costs, no data leaving the machine
- **Model management** — Easy model downloads and switching
- **API compatibility** — OpenAI-compatible interface
- **GPU acceleration** — Uses available hardware

Alternative considered: Direct llama.cpp. Rejected because Ollama handles model management better.

### Why APScheduler?

APScheduler provides:
- **Cron-like scheduling** — Familiar syntax
- **Persistent jobs** — Survive restarts
- **Job stores** — SQLite, memory, etc.
- **Executor pools** — Thread/process pools

Alternative considered: Celery. Rejected because it requires a message broker (Redis/RabbitMQ).

---

## Data Storage

### XDG-Compliant Paths

| Type | Path | Contents |
|------|------|----------|
| **Config** | `~/.config/halbert/` | User configuration files |
| **Data** | `~/.local/share/halbert/` | Persistent data (vector DB, snapshots) |
| **State** | `~/.local/state/halbert/` | Runtime state (logs, cursors) |

### Storage Layout

```
~/.local/share/halbert/
├── raw/                    # Raw telemetry JSONL
│   ├── journal_events.jsonl
│   └── hwmon_events.jsonl
├── config/                 # Config snapshots
│   ├── raw/                # Redacted raw configs
│   ├── canon/              # Canonical JSON
│   └── snapshots/          # Point-in-time snapshots
├── index/                  # ChromaDB
│   └── chroma.sqlite3
└── audit/                  # Audit trail
    └── actions.jsonl
```

---

## Security Model

### Principle of Least Privilege

- Runs as user (not root) by default
- Escalates only when necessary (sudo prompt)
- Tools declare their privilege requirements
- Audit trail records all escalations

### Approval Workflow

1. Tool requests action
2. Policy engine checks if approval required
3. If yes: show diff, wait for confirmation
4. User approves or rejects
5. Decision logged regardless of outcome

### Guardrails

| Control | Purpose |
|---------|---------|
| **Operation Budget** | Max N operations per hour |
| **Cooling-Off Period** | Wait between high-risk actions |
| **Anomaly Detection** | Alert on unusual patterns |
| **Emergency Stop** | Kill switch for all automation |

---

## Extensibility

### Adding a New Tool

1. Create `halbert_core/tools/my_tool.py`
2. Implement the `BaseTool` interface
3. Add dry-run support
4. Add audit logging
5. Register in tool catalog
6. Add CLI command in `Halbert/main.py`

### Adding a New Data Source

1. Create `halbert_core/ingestion/my_source.py`
2. Implement collection logic
3. Transform to standard event schema
4. Add to ingestion runner
5. Update identity prompt if relevant

### Adding a Dashboard Feature

1. Add API route in `halbert_core/dashboard/routes/`
2. Create React component in `dashboard/frontend/src/`
3. Add WebSocket handler if real-time needed
4. Update API documentation

---

## Performance Considerations

### Memory Usage

| Component | Typical Memory |
|-----------|----------------|
| ChromaDB | 200-500 MB (depends on corpus size) |
| Ollama (8B model) | 4-8 GB |
| Dashboard | 50-100 MB |
| Ingestion | 20-50 MB |

### Latency

| Operation | Typical Latency |
|-----------|-----------------|
| Memory retrieval | 50-200 ms |
| LLM inference | 500-5000 ms (depends on model/hardware) |
| Tool execution | 100-1000 ms (depends on tool) |
| End-to-end query | 1-10 seconds |

---

## Next Steps

- [self-identity.md](self-identity.md) — Deep dive on identity construction
- [runtime-engine.md](runtime-engine.md) — LangGraph orchestration details
- [memory-system.md](memory-system.md) — RAG and retrieval
- [guardrails.md](guardrails.md) — Safety controls
