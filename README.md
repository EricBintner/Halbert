# Cerebric

**Local-first AI assistant for Linux system administration.**

Cerebric runs entirely on your machine using local LLMs. It ingests system logs, tracks configuration changes, and answers questions grounded in real system data.

---

## Features

- **Local LLM** — No cloud APIs, runs on Ollama
- **System-aware** — Ingests journald logs and hardware sensors
- **RAG-powered** — Answers grounded in Linux documentation
- **Safe by default** — Dry-run mode, approval system, policy engine
- **Self-identifying** — The LLM identifies as your computer

---

## Quick Start

```bash
# 1. Install Ollama
curl -fsSL https://ollama.ai/install.sh | sh
ollama pull llama3.2:3b

# 2. Clone and install
git clone https://github.com/yourusername/cerebric.git
cd cerebric
python3 -m venv .venv
source .venv/bin/activate
pip install -e cerebric_core/

# 3. Ask a question
python Cerebric/main.py ask "Why did my docker service fail?"
```

---

## Requirements

- Linux (Ubuntu 22.04+, Fedora 38+, Arch)
- Python 3.11+
- 8 GB RAM minimum
- [Ollama](https://ollama.ai/)

---

## Documentation

| Document | Description |
|----------|-------------|
| [Installation](documentation/INSTALLATION.md) | Full setup guide |
| [CLI Reference](documentation/CLI-REFERENCE.md) | All commands |
| [Configuration](documentation/CONFIGURATION.md) | Config files |
| [Architecture](documentation/ARCHITECTURE.md) | System design |
| [API Reference](documentation/API-REFERENCE.md) | Dashboard API |

See [documentation/](documentation/) for full docs.

---

## Example Usage

```bash
# Ask questions
python Cerebric/main.py ask "How do I free up disk space?"

# Start dashboard
python Cerebric/main.py dashboard

# Ingest system logs
python Cerebric/main.py ingest-journald

# Track config changes
python Cerebric/main.py snapshot-configs
```

---

## Architecture

```
┌─────────────────────────────────────────────┐
│                  Cerebric                    │
├─────────────────────────────────────────────┤
│  CLI / Dashboard                            │
├─────────────────────────────────────────────┤
│  Runtime Engine (LangGraph)                 │
├──────────────┬──────────────┬───────────────┤
│   Memory     │     RAG      │    Tools      │
│  (ChromaDB)  │  (Docs + KB) │  (System)     │
├──────────────┴──────────────┴───────────────┤
│  Ollama (Local LLM)                         │
└─────────────────────────────────────────────┘
```

---

## Contributing

See [CONTRIBUTING.md](documentation/contributing/CONTRIBUTING.md).

---

## License

GPL-3.0. See [LICENSE](LICENSE).
