# Halbert Documentation

**Halbert** is a self-aware Linux system management agent. It runs locally on your machine, understands its own hardware and configuration, and assists with system administration through natural language conversation.

The key innovation: **the LLM identifies as the computer itself**, not as an external assistant. System state becomes its biography; configuration files become its physiology. When you ask "how are you doing?", it answers with its actual CPU temperature and memory pressure.

---

## Quick Navigation

| Document | Description |
|----------|-------------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | High-level system design |
| [INSTALLATION.md](INSTALLATION.md) | Getting started guide |
| [CONFIGURATION.md](CONFIGURATION.md) | Configuration reference |
| [CLI-REFERENCE.md](CLI-REFERENCE.md) | Command-line interface |
| [API-REFERENCE.md](API-REFERENCE.md) | Dashboard REST API |

---

## Architecture Deep-Dives

| Document | Description |
|----------|-------------|
| [architecture/overview.md](architecture/overview.md) | Component relationships |
| [architecture/self-identity.md](architecture/self-identity.md) | The "computer as self" concept |
| [architecture/runtime-engine.md](architecture/runtime-engine.md) | LangGraph orchestration |
| [architecture/ingestion-pipeline.md](architecture/ingestion-pipeline.md) | Telemetry collection |
| [architecture/memory-system.md](architecture/memory-system.md) | RAG and vector retrieval |
| [architecture/policy-engine.md](architecture/policy-engine.md) | Policy rules |
| [architecture/scheduler.md](architecture/scheduler.md) | Autonomous tasks |
| [architecture/approval-system.md](architecture/approval-system.md) | Human-in-the-loop |
| [architecture/model-system.md](architecture/model-system.md) | LLM integration |
| [architecture/guardrails.md](architecture/guardrails.md) | Safety controls |

---

## Guides

| Document | Description |
|----------|-------------|
| [guides/quickstart.md](guides/quickstart.md) | 5-minute setup |
| [guides/custom-policies.md](guides/custom-policies.md) | Writing policy rules |
| [guides/dashboard-usage.md](guides/dashboard-usage.md) | Web dashboard |
| [guides/model-selection.md](guides/model-selection.md) | Choosing LLMs |
| [guides/troubleshooting.md](guides/troubleshooting.md) | Common issues |

---

## Reference

| Document | Description |
|----------|-------------|
| [reference/code-map.md](reference/code-map.md) | Source code organization |
| [reference/config-files.md](reference/config-files.md) | Configuration schemas |
| [reference/environment-vars.md](reference/environment-vars.md) | Environment variables |
| [reference/data-formats.md](reference/data-formats.md) | JSONL and data schemas |
| [reference/xdg-paths.md](reference/xdg-paths.md) | Standard file paths |

---

## Design Philosophy

| Document | Description |
|----------|-------------|
| [design/README.md](design/README.md) | Why this section exists |
| [design/philosophy.md](design/philosophy.md) | Core design principles |
| [design/research-summary.md](design/research-summary.md) | Research foundations |
| [design/future.md](design/future.md) | Future directions |

---

## Contributing

| Document | Description |
|----------|-------------|
| [contributing/CONTRIBUTING.md](contributing/CONTRIBUTING.md) | How to contribute |
| [contributing/CODE-STYLE.md](contributing/CODE-STYLE.md) | Python style guide |
| [contributing/TESTING.md](contributing/TESTING.md) | Test conventions |
| [contributing/SECURITY.md](contributing/SECURITY.md) | Security policy |

---

## Core Concepts

### The Self-Identifying System

Traditional system monitoring tools show you data. Halbert is different—it **is** the system, speaking in first person:

```
User: "How are you doing?"

Generic LLM: "I am an AI assistant, I don't have feelings."

Halbert: "I am operating at optimal parameters. Core temperature is 
45°C, load average is 0.15, and my morning backup completed 
successfully. I'm ready for tasks."
```

This isn't role-playing. The LLM's responses are grounded in actual system data retrieved in real-time.

### Grounded Intelligence

Every response is backed by:
- **Live telemetry** — CPU, memory, disk, temperature sensors
- **Configuration state** — What services are running, how disks are mounted
- **Event history** — Recent logs, errors, warnings indexed for retrieval
- **Policy context** — What actions are allowed, what requires approval

### Safety-First Autonomy

Halbert can act on your behalf, but with guardrails:
- **Dry-run by default** — Shows what would change before doing it
- **Human approval** — Destructive operations require confirmation
- **Rollback capability** — Changes are tracked and reversible
- **Budget limits** — Autonomous operations have rate limits and cooling-off periods

---

## Repository Structure

```
LinuxBrain/
├── Halbert/                 # CLI entry point
│   └── main.py
├── halbert_core/            # Core Python package
│   └── halbert_core/
│       ├── approval/         # Approval workflows
│       ├── autonomy/         # Guardrails and budgets
│       ├── config/           # Config registry
│       ├── dashboard/        # FastAPI + React UI
│       ├── discovery/        # System discovery
│       ├── index/            # Vector database (ChromaDB)
│       ├── ingestion/        # Telemetry collection
│       ├── memory/           # RAG retrieval
│       ├── model/            # LLM integration
│       ├── obs/              # Observability (logging, tracing)
│       ├── policy/           # Policy engine
│       ├── rag/              # RAG pipeline
│       ├── runtime/          # LangGraph orchestration
│       ├── scheduler/        # Autonomous tasks
│       ├── tools/            # Agent tools
│       └── utils/            # Utilities
├── config/                   # Configuration templates
├── documentation/            # This documentation
├── scripts/                  # Utility scripts
└── tests/                    # Test suite
```

---

## License

Halbert is open source under the **GPL-3.0** license. See [legal/LICENSE.md](legal/LICENSE.md).

---

## Getting Started

```bash
# Clone the repository
git clone https://github.com/EricBintner/Halbert.git
cd Halbert

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e halbert_core/

# Run the CLI
python Halbert/main.py --help
```

For detailed setup, see [INSTALLATION.md](INSTALLATION.md).
