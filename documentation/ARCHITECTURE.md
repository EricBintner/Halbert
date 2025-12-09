# Cerebric Architecture

This document provides a high-level overview of Cerebric's architecture. For detailed component documentation, see the [architecture/](architecture/) directory.

---

## System Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              User Interface                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────────────┐  │
│  │   CLI       │  │  Dashboard  │  │        REST API                 │  │
│  │ (main.py)   │  │  (React)    │  │       (FastAPI)                 │  │
│  └──────┬──────┘  └──────┬──────┘  └────────────────┬────────────────┘  │
└─────────┼────────────────┼──────────────────────────┼───────────────────┘
          │                │                          │
          ▼                ▼                          ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           Runtime Engine                                │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                    LangGraph Orchestrator                        │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  │   │
│  │  │ Planner  │→ │ Executor │→ │ Observer │→ │ Response Builder │  │   │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────────────┘  │   │
│  └──────────────────────────────────────────────────────────────────┘   │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
          ┌──────────────────────┼──────────────────────┐
          ▼                      ▼                      ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────────┐
│  Model System   │  │  Memory System  │  │        Tool System          │
│  ┌───────────┐  │  │  ┌───────────┐  │  │  ┌─────────┐ ┌───────────┐  │
│  │  Ollama   │  │  │  │ ChromaDB  │  │  │  │read_    │ │write_     │  │
│  │  Backend  │  │  │  │ (Vector)  │  │  │  │sensor   │ │config     │  │
│  └───────────┘  │  │  └───────────┘  │  │  └─────────┘ └───────────┘  │
│  ┌───────────┐  │  │  ┌───────────┐  │  │  ┌─────────┐ ┌───────────┐  │
│  │  Prompt   │  │  │  │ Retrieval │  │  │  │schedule │ │query_     │  │
│  │  Manager  │  │  │  │  Engine   │  │  │  │cron     │ │journal    │  │
│  └───────────┘  │  │  └───────────┘  │  │  └─────────┘ └───────────┘  │
└─────────────────┘  └─────────────────┘  └─────────────────────────────┘
          │                      │                      │
          └──────────────────────┼──────────────────────┘
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         Data Layer                                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌───────────────┐   │
│  │  journald   │  │   hwmon     │  │   Config    │  │  Policy       │   │
│  │  Ingestion  │  │  Ingestion  │  │  Registry   │  │  Engine       │   │
│  └─────────────┘  └─────────────┘  └─────────────┘  └───────────────┘   │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────────────┐  │
│  │  Scheduler  │  │  Approval   │  │          Guardrails             │  │
│  │  (APScheduler) │  │  Engine    │  │  (Budgets, Limits, Controls)   │  │
│  └─────────────┘  └─────────────┘  └─────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Core Components

### 1. User Interface Layer

| Component | Location | Purpose |
|-----------|----------|---------|
| **CLI** | `Cerebric/main.py` | Command-line interface with 50+ commands |
| **Dashboard** | `cerebric_core/dashboard/` | React + FastAPI web interface |
| **REST API** | `cerebric_core/dashboard/routes/` | Programmatic access |

The CLI is the primary interface for power users. The dashboard provides a web-based GUI with real-time updates via WebSocket.

### 2. Runtime Engine

| Component | Location | Purpose |
|-----------|----------|---------|
| **Orchestrator** | `cerebric_core/runtime/engine.py` | LangGraph-based agent loop |
| **State Management** | `cerebric_core/runtime/state.py` | Conversation and agent state |
| **Graph Definition** | `cerebric_core/runtime/graph.py` | Node and edge definitions |

The runtime engine uses [LangGraph](https://github.com/langchain-ai/langgraph) to orchestrate multi-step reasoning. It:
1. Receives user input
2. Plans required tool calls
3. Executes tools with approval checks
4. Observes results
5. Builds grounded responses

### 3. Model System

| Component | Location | Purpose |
|-----------|----------|---------|
| **Model Loader** | `cerebric_core/model/loader.py` | LLM initialization and management |
| **Prompt Manager** | `cerebric_core/model/prompt_manager.py` | System prompt construction |
| **Model Router** | `cerebric_core/model/router.py` | Task-based model selection |
| **Providers** | `cerebric_core/model/providers/` | Backend integrations (Ollama, etc.) |

The model system handles LLM integration. The **Prompt Manager** is critical—it injects the system's self-identity into every conversation:

```python
# Simplified example
system_prompt = f"""
You are {hostname}. You run {os_version}. 
Your primary storage is {disk_info}.
Your current temperature is {cpu_temp}°C.
All your responses must be grounded in this reality.
"""
```

### 4. Memory System

| Component | Location | Purpose |
|-----------|----------|---------|
| **Vector Index** | `cerebric_core/index/chroma_index.py` | ChromaDB wrapper |
| **Retrieval Engine** | `cerebric_core/memory/retrieval.py` | RAG query execution |
| **Memory Writer** | `cerebric_core/memory/writer.py` | Event persistence |

The memory system stores and retrieves system events. When the user asks a question, relevant past events are retrieved and included in the prompt context.

### 5. Tool System

| Component | Location | Purpose |
|-----------|----------|---------|
| **Base Tool** | `cerebric_core/tools/base.py` | Tool interface contract |
| **read_sensor** | `cerebric_core/tools/read_sensor.py` | Hardware sensor access |
| **write_config** | `cerebric_core/tools/write_config.py` | Configuration modification |
| **schedule_cron** | `cerebric_core/tools/schedule_cron.py` | Cron job management |

Tools are the LLM's "hands"—functions it can call to interact with the system. All tools:
- Support dry-run mode
- Emit audit logs
- Require approval for destructive operations

### 6. Ingestion Pipeline

| Component | Location | Purpose |
|-----------|----------|---------|
| **journald** | `cerebric_core/ingestion/journald.py` | System log collection |
| **hwmon** | `cerebric_core/ingestion/hwmon.py` | Hardware sensor collection |
| **JSONL Writer** | `cerebric_core/ingestion/jsonl_writer.py` | Event persistence |
| **Severity Mapper** | `cerebric_core/ingestion/severity.py` | Log level normalization |
| **Redaction** | `cerebric_core/ingestion/redaction.py` | Sensitive data removal |

Ingestion continuously collects telemetry and logs, transforms them into structured events, and indexes them for retrieval.

### 7. Policy Engine

| Component | Location | Purpose |
|-----------|----------|---------|
| **Policy Loader** | `cerebric_core/policy/loader.py` | YAML policy parsing |
| **Policy Engine** | `cerebric_core/policy/engine.py` | Rule evaluation |

Policies define what the LLM can and cannot do:

```yaml
# Example policy
rules:
  - action: restart_service
    requires_approval: true
    
  - action: read_logs
    requires_approval: false
```

### 8. Scheduler

| Component | Location | Purpose |
|-----------|----------|---------|
| **Job Definitions** | `cerebric_core/scheduler/job.py` | Scheduled task schema |
| **Scheduler Engine** | `cerebric_core/scheduler/engine.py` | APScheduler wrapper |
| **Executor** | `cerebric_core/scheduler/executor.py` | Job execution with guardrails |
| **Autonomous Tasks** | `cerebric_core/scheduler/autonomous_tasks.py` | LLM-driven tasks |

The scheduler runs background tasks:
- Health checks
- Log rotation
- Trend analysis
- Proactive maintenance

### 9. Approval System

| Component | Location | Purpose |
|-----------|----------|---------|
| **Approval Engine** | `cerebric_core/approval/engine.py` | Approval workflow management |
| **Simulator** | `cerebric_core/approval/simulator.py` | Dry-run simulation |

When a tool requires approval, the workflow:
1. Displays what would change (dry-run)
2. Waits for user confirmation
3. Executes if approved
4. Logs the decision either way

### 10. Guardrails

| Component | Location | Purpose |
|-----------|----------|---------|
| **Guardrails** | `cerebric_core/autonomy/guardrails.py` | Safety checks |
| **Budgets** | `cerebric_core/autonomy/budgets.py` | Rate limiting |
| **Anomaly Detector** | `cerebric_core/autonomy/anomaly_detector.py` | Unusual behavior detection |
| **Recovery** | `cerebric_core/autonomy/recovery.py` | Rollback procedures |

Guardrails prevent runaway automation:
- Operation budgets (max N operations per hour)
- Cooling-off periods between high-risk actions
- Emergency stop capability
- Anomaly detection for unusual patterns

---

## Data Flow

### Query Flow

```
User Input
    │
    ▼
┌───────────────────────────────────────┐
│ 1. Runtime Engine receives query      │
└───────────────────────────────────────┘
    │
    ▼
┌───────────────────────────────────────┐
│ 2. Memory retrieval (ChromaDB query)  │
│    - Find relevant past events        │
│    - Find relevant config state       │
└───────────────────────────────────────┘
    │
    ▼
┌───────────────────────────────────────┐
│ 3. Prompt construction                │
│    - System identity                  │
│    - Retrieved context                │
│    - User query                       │
└───────────────────────────────────────┘
    │
    ▼
┌───────────────────────────────────────┐
│ 4. LLM inference (Ollama)             │
│    - Plan tool calls if needed        │
│    - Generate response                │
└───────────────────────────────────────┘
    │
    ▼
┌───────────────────────────────────────┐
│ 5. Tool execution (if planned)        │
│    - Policy check                     │
│    - Approval if required             │
│    - Execute with audit logging       │
└───────────────────────────────────────┘
    │
    ▼
Response to User
```

### Ingestion Flow

```
System Events (journald, hwmon, configs)
    │
    ▼
┌───────────────────────────────────────┐
│ 1. Ingestion adapters collect data    │
└───────────────────────────────────────┘
    │
    ▼
┌───────────────────────────────────────┐
│ 2. Normalize and structure            │
│    - Severity mapping                 │
│    - Schema validation                │
│    - Redaction                        │
└───────────────────────────────────────┘
    │
    ▼
┌───────────────────────────────────────┐
│ 3. Write to JSONL (raw storage)       │
└───────────────────────────────────────┘
    │
    ▼
┌───────────────────────────────────────┐
│ 4. Embed and index (ChromaDB)         │
│    - Generate embeddings              │
│    - Store with metadata              │
└───────────────────────────────────────┘
```

---

## Configuration

### File Locations (XDG-Compliant)

| Type | Path | Purpose |
|------|------|---------|
| **Config** | `~/.config/cerebric/` | User configuration |
| **Data** | `~/.local/share/cerebric/` | Persistent data |
| **State** | `~/.local/state/cerebric/` | Runtime state |
| **Logs** | `~/.local/state/cerebric/log/` | Application logs |

### Key Configuration Files

| File | Purpose |
|------|---------|
| `ingestion.yml` | Telemetry collection settings |
| `config-registry.yml` | Tracked system configs |
| `policy.yml` | Policy rules |
| `autonomy.yml` | Guardrail settings |

---

## Dependencies

### Python Packages

| Package | Purpose |
|---------|---------|
| `langchain` / `langgraph` | LLM orchestration |
| `chromadb` | Vector database |
| `pydantic` | Data validation |
| `fastapi` | REST API |
| `apscheduler` | Task scheduling |
| `watchdog` | File monitoring |
| `systemd-python` | journald access |

### External Services

| Service | Purpose |
|---------|---------|
| **Ollama** | Local LLM inference |

Cerebric runs entirely locally. No external API calls are required for core functionality.

---

## Next Steps

- [architecture/self-identity.md](architecture/self-identity.md) — The self-identifying LLM concept
- [architecture/runtime-engine.md](architecture/runtime-engine.md) — LangGraph orchestration details
- [architecture/memory-system.md](architecture/memory-system.md) — RAG and retrieval
- [INSTALLATION.md](INSTALLATION.md) — Getting started
