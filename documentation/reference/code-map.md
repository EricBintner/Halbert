# Code Map

This document maps Cerebric's architecture to its implementation. Every major component is traced to its source file.

---

## Repository Structure

```
LinuxBrain/
├── Cerebric/                   # CLI entry point
│   └── main.py                 # Typer CLI, 50+ commands
├── cerebric_core/              # Core Python package
│   └── cerebric_core/          # Source code
│       ├── alerts/             # Alert management
│       ├── approval/           # Human-in-the-loop approvals
│       ├── autonomy/           # Guardrails and safety
│       ├── config/             # Configuration tracking
│       ├── dashboard/          # Web UI (FastAPI + React)
│       ├── discovery/          # System discovery
│       ├── index/              # Vector database
│       ├── ingestion/          # Telemetry collection
│       ├── memory/             # RAG retrieval
│       ├── model/              # LLM integration
│       ├── obs/                # Observability
│       ├── platform/           # Platform abstraction
│       ├── policy/             # Policy engine
│       ├── rag/                # RAG pipeline
│       ├── runtime/            # Orchestration
│       ├── scheduler/          # Task scheduling
│       ├── tools/              # Agent tools
│       └── utils/              # Utilities
├── config/                     # Configuration templates
├── documentation/              # This documentation
├── scripts/                    # Utility scripts
└── tests/                      # Test suite
```

---

## Component → File Mapping

### CLI Entry Point

| Component | File | Description |
|-----------|------|-------------|
| **Main CLI** | `Cerebric/main.py` | Typer-based CLI with all commands |

**Key Commands**:
- `info`, `roadmap` — System information
- `ingest-journald`, `ingest-hwmon` — Telemetry ingestion
- `snapshot-configs`, `watch-configs`, `diff-configs` — Config tracking
- `policy-show`, `policy-eval` — Policy engine
- `scheduler-add`, `scheduler-list`, `scheduler-cancel` — Task scheduling
- `model-status`, `model-test` — LLM management
- `memory-query`, `memory-stats` — RAG queries

---

### Runtime Engine (Orchestration)

| Component | File | Description |
|-----------|------|-------------|
| **Engine** | `runtime/engine.py` | LangGraph orchestrator, agent loop |
| **Graph** | `runtime/graph.py` | Node and edge definitions |
| **State** | `runtime/state.py` | Conversation and agent state management |

The runtime engine coordinates the agent loop:
1. Receive input → 2. Plan → 3. Execute tools → 4. Observe → 5. Respond

---

### Model System (LLM Integration)

| Component | File | Description |
|-----------|------|-------------|
| **Loader** | `model/loader.py` | LLM initialization, Ollama connection |
| **Prompt Manager** | `model/prompt_manager.py` | System prompt construction |
| **Router** | `model/router.py` | Task-based model selection |
| **Providers (base)** | `model/providers/base.py` | Abstract provider interface |
| **Ollama Provider** | `model/providers/ollama.py` | Ollama backend implementation |
| **Hardware Detector** | `model/hardware_detector.py` | Hardware capability detection |
| **Config Wizard** | `model/config_wizard.py` | Interactive configuration |
| **Context Handoff** | `model/context_handoff.py` | Context management between calls |
| **Performance Monitor** | `model/performance_monitor.py` | Inference metrics tracking |

**Key Insight**: The `prompt_manager.py` is where the self-identity prompts are constructed. It gathers system information and injects it into the LLM's context.

---

### Memory System (RAG)

| Component | File | Description |
|-----------|------|-------------|
| **Vector Index** | `index/chroma_index.py` | ChromaDB wrapper |
| **Retrieval Engine** | `memory/retrieval.py` | Query execution, relevance scoring |
| **Memory Writer** | `memory/writer.py` | Event persistence |
| **RAG Pipeline** | `rag/` | Full RAG implementation (14 files) |

The memory system stores system events as embeddings and retrieves relevant context during conversations.

---

### Ingestion Pipeline (Telemetry)

| Component | File | Description |
|-----------|------|-------------|
| **journald Collector** | `ingestion/journald.py` | systemd journal ingestion |
| **hwmon Collector** | `ingestion/hwmon.py` | Hardware sensor collection |
| **hwmon Runner** | `ingestion/hwmon_runner.py` | Continuous sensor polling |
| **JSONL Writer** | `ingestion/jsonl_writer.py` | Event persistence to JSONL |
| **Severity Mapper** | `ingestion/severity.py` | Log level normalization |
| **Redaction** | `ingestion/redaction.py` | Sensitive data removal |
| **Runner** | `ingestion/runner.py` | Ingestion orchestration |
| **Validator** | `ingestion/validate.py` | Schema validation |

**Data Flow**:
```
journald/hwmon → Collector → Severity Map → Redaction → Validate → JSONL → ChromaDB
```

---

### Configuration System

| Component | File | Description |
|-----------|------|-------------|
| **Manifest** | `config/manifest.py` | Config file registry |
| **Parser** | `config/parser.py` | Config file parsing |
| **Snapshot** | `config/snapshot.py` | Point-in-time snapshots |
| **Drift Detection** | `config/drift.py` | Change detection |
| **Watcher** | `config/watcher.py` | File system monitoring |
| **Indexer** | `config/indexer.py` | Config indexing for search |

The config system tracks system configuration files, detects changes, and stores snapshots for rollback.

---

### Policy Engine

| Component | File | Description |
|-----------|------|-------------|
| **Loader** | `policy/loader.py` | YAML policy parsing |
| **Engine** | `policy/engine.py` | Rule evaluation |

Policies define what the LLM can do:
- Which actions require approval
- Which are allowed automatically
- Which are prohibited

---

### Scheduler

| Component | File | Description |
|-----------|------|-------------|
| **Job Definition** | `scheduler/job.py` | Job schema |
| **Scheduler Engine** | `scheduler/engine.py` | APScheduler wrapper |
| **Executor** | `scheduler/executor.py` | Job execution with guardrails |
| **Autonomous Tasks** | `scheduler/autonomous_tasks.py` | LLM-driven scheduled tasks |

The scheduler runs background tasks:
- Health checks
- Trend analysis
- Proactive maintenance
- Log rotation

---

### Approval System

| Component | File | Description |
|-----------|------|-------------|
| **Approval Engine** | `approval/engine.py` | Approval workflow management |
| **Simulator** | `approval/simulator.py` | Dry-run execution |

The approval system implements human-in-the-loop:
1. Tool requests action
2. Simulator shows what would happen
3. User approves or rejects
4. Action executes (or doesn't)
5. Decision is logged

---

### Guardrails (Safety)

| Component | File | Description |
|-----------|------|-------------|
| **Guardrails** | `autonomy/guardrails.py` | Safety check framework |
| **Budgets** | `autonomy/budgets.py` | Rate limiting |
| **Anomaly Detector** | `autonomy/anomaly_detector.py` | Unusual pattern detection |
| **Recovery** | `autonomy/recovery.py` | Rollback procedures |

Guardrails prevent runaway automation:
- Operation budgets (max N per hour)
- Cooling-off periods
- Emergency stop
- Anomaly alerts

---

### Dashboard (Web UI)

| Component | File | Description |
|-----------|------|-------------|
| **FastAPI App** | `dashboard/app.py` | Main web application |
| **Routes** | `dashboard/routes/` | API endpoints (6 modules) |
| **Frontend** | `dashboard/frontend/` | React + shadcn/ui |

The dashboard provides:
- Real-time system metrics (WebSocket)
- Chat interface
- Configuration management
- Task scheduling UI

---

### Tools (Agent Actions)

| Component | File | Description |
|-----------|------|-------------|
| **Base Tool** | `tools/base.py` | Tool interface contract |
| **read_sensor** | `tools/read_sensor.py` | Hardware sensor access |
| **write_config** | `tools/write_config.py` | Configuration modification |
| **schedule_cron** | `tools/schedule_cron.py` | Cron job management |

All tools implement:
- Dry-run mode (show what would change)
- Audit logging (record all actions)
- Approval integration (request confirmation for destructive ops)

---

### Observability

| Component | File | Description |
|-----------|------|-------------|
| **Logging** | `obs/logging.py` | Structured logging (cerebric logger) |
| **Audit** | `obs/audit.py` | Action audit trail |
| **Dashboard** | `obs/dashboard.py` | Metrics for dashboard |
| **Tracing** | `obs/tracing.py` | Distributed tracing |
| **Span Exporter** | `obs/span_exporter.py` | OpenTelemetry export |

---

### Platform Abstraction

| Component | File | Description |
|-----------|------|-------------|
| **Base** | `platform/base.py` | Abstract platform interface |
| **Linux** | `platform/linux.py` | Linux-specific implementations |
| **Detection** | `platform/detection.py` | Platform detection |

The platform layer abstracts OS-specific operations (journald, systemd, /proc, etc.).

---

### Utilities

| Component | File | Description |
|-----------|------|-------------|
| **Paths** | `utils/paths.py` | XDG-compliant path resolution |
| **Retry** | `utils/retry.py` | Exponential backoff with jitter |
| **Platform** | `utils/platform.py` | Cross-platform utilities |

---

## Test Coverage

| Test File | Coverage |
|-----------|----------|
| `tests/test_persona_switching.py` | Persona system |
| `tests/test_model_router.py` | Model routing |
| `tests/test_context_handoff.py` | Context management |
| `tests/test_hardware_detection.py` | Hardware detection |
| `tests/test_scheduler_guardrails.py` | Scheduler safety |
| `tests/test_persona_api.py` | Dashboard API |
| `tests/test_phase4_integration.py` | Integration tests |
| `tests/platform/test_linux_adapters.py` | Linux platform |
| `tests/platform/test_platform_detection.py` | Platform detection |
| `tests/rag/test_rag_system.py` | RAG pipeline |

---

## Configuration Files

| File | Location | Purpose |
|------|----------|---------|
| `ingestion.yml` | `~/.config/cerebric/` | Telemetry settings |
| `config-registry.yml` | `~/.config/cerebric/` | Tracked config files |
| `policy.yml` | `~/.config/cerebric/` | Policy rules |
| `autonomy.yml` | `config/` | Guardrail settings |
| `model-catalog.yml` | `config/` | Model recommendations |
| `prompts/*.txt` | `config/prompts/` | System prompts |

---

## Entry Points

| Purpose | Entry Point |
|---------|-------------|
| CLI usage | `python Cerebric/main.py [command]` |
| Dashboard | `python -m cerebric_core.dashboard.app` |
| Ingestion | `python Cerebric/main.py ingest-journald` |
| Tests | `pytest tests/` |

---

## Adding New Features

When adding a new feature:

1. **Tool**: Add to `cerebric_core/tools/` following `base.py` interface
2. **CLI Command**: Add to `Cerebric/main.py` with Typer
3. **API Endpoint**: Add to `cerebric_core/dashboard/routes/`
4. **Tests**: Add to `tests/`
5. **Documentation**: Update this code map
