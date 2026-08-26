<p align="left">
  <img src="Halbert.png" alt="Halbert" width="120">
</p>

# Halbert

**Local-first AI assistant for Linux system administration.**

Halbert runs on your machine using local LLMs by default—no cloud required. Optionally connect a cloud provider's API if you prefer. It ingests system logs, tracks configuration changes, and answers questions grounded in real system data.

---

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="./assets/screenshots/hero/dashboard-overview-dark.png">
    <source media="(prefers-color-scheme: light)" srcset="./assets/screenshots/hero/dashboard-overview-light.png">
    <img alt="Halbert Dashboard" src="./assets/screenshots/hero/dashboard-overview-light.png" width="800">
  </picture>
</p>

## Features

- **Local LLM** — Runs on Ollama by default, no cloud required
- **Cloud optional** — Connect a cloud provider's API if you prefer
- **System-aware** — Ingests journald logs and hardware sensors
- **RAG-powered** — Answers grounded in Linux documentation
- **Safe by default** — Dry-run mode, approval system, policy engine
- **Self-identifying** — The LLM identifies as your computer

---

## Quick Start

```bash
# 1. Install Ollama and pull a chat model sized for your hardware
curl -fsSL https://ollama.ai/install.sh | sh
ollama pull <model>

# 2. Clone and install
git clone https://github.com/EricBintner/Halbert.git
cd Halbert
python3 -m venv .venv
source .venv/bin/activate
pip install -e halbert_core/

# 3. Start the web dashboard
make dev-web
# Open http://localhost:8000
# or for Tauri build
make dev  
```

### Choosing a Model

Halbert works with whatever chat model your endpoint serves — it does not ship with or endorse a particular one. Pick a model sized for your RAM/VRAM: as a rule of thumb, a ~8B-parameter model at 4-bit quantization needs ~5 GB, a ~14B model ~10 GB, and a ~70B model ~40 GB. A single model that supports vision and tool calling can cover the Guide, Specialist, and Vision roles by itself. Assign models in **Settings → AI Models**.

See the [Quick Start Guide](documentation/guides/quickstart.md) for full setup and the [Model Selection guide](documentation/guides/model-selection.md) for hardware sizing and cloud provider setup.

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
| [**Visual Walkthrough**](documentation/WALKTHROUGH.md) | **Screenshot tour of every feature** |
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
python Halbert/main.py ask "How do I free up disk space?"

# Start dashboard
python Halbert/main.py dashboard

# Ingest system logs
python Halbert/main.py ingest-journald

# Track config changes
python Halbert/main.py snapshot-configs
```

---

## Architecture

```
┌────────────────────────────────────────┐
│                 Halbert                │
├────────────────────────────────────────┤
│ CLI / Dashboard                        │
├────────────────────────────────────────┤
│ Runtime Engine                         │
├────────────┬──────────────┬────────────┤
│   Memory   │      RAG     │   Tools    │
│ (ChromaDB) │  (Docs + KB) │  (System)  │
├────────────┴──────────────┴────────────┤
│ Ollama (Local) or Cloud API (Optional) │
└────────────────────────────────────────┘
```

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="./assets/screenshots/hero/chat-conversation-dark.png">
    <source media="(prefers-color-scheme: light)" srcset="./assets/screenshots/hero/chat-conversation-light.png">
    <img alt="AI Chat Assistant" src="./assets/screenshots/hero/chat-conversation-light.png" width="800">
  </picture>
</p>

<p align="center">
  <em>Ask questions in natural language — Halbert knows your system</em>
</p>

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="./assets/screenshots/hero/storage-overview-dark.png">
    <source media="(prefers-color-scheme: light)" srcset="./assets/screenshots/hero/storage-overview-light.png">
    <img alt="Storage Management" src="./assets/screenshots/hero/storage-overview-light.png" width="48%">
  </picture>
  &nbsp;
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="./assets/screenshots/hero/gpu-overview-dark.png">
    <source media="(prefers-color-scheme: light)" srcset="./assets/screenshots/hero/gpu-overview-light.png">
    <img alt="GPU Monitoring" src="./assets/screenshots/hero/gpu-overview-light.png" width="48%">
  </picture>
</p>

---

## Contributing

See [CONTRIBUTING.md](documentation/contributing/CONTRIBUTING.md).

---

## License

Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors.

Halbert is free software under the **GNU General Public License v3.0 or later**
(`GPL-3.0-or-later`). See [LICENSE](LICENSE) for the full text, and
[documentation/legal/](documentation/legal/README.md) for the licence summary,
[third-party notices](documentation/legal/THIRD-PARTY-LICENSES.md) (RAG corpus
sources, dependencies, foundation models), the [privacy policy](documentation/legal/PRIVACY.md),
[trademarks](documentation/legal/TRADEMARKS.md), and the
[autonomous-action disclaimer](documentation/legal/DISCLAIMER.md).
`halbert license` prints the same information from the CLI.
