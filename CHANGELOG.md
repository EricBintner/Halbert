# Changelog

All notable changes to Cerebric.

Format based on [Keep a Changelog](https://keepachangelog.com/).

---

## [Unreleased]

### Added
- Initial public release
- CLI interface (`Cerebric/main.py`)
- RAG pipeline with Linux documentation
- journald and hwmon ingestion
- Configuration tracking and diff
- ChromaDB memory system
- Policy engine for action control
- Approval system for human-in-the-loop
- Autonomy guardrails (safe mode, budgets)
- Web dashboard (FastAPI)
- LangGraph runtime engine

### Architecture
- Local-first design (no cloud dependencies)
- Ollama integration for LLM inference
- XDG-compliant paths
- Modular tool system

---

## Versioning

This project uses [Semantic Versioning](https://semver.org/).

- MAJOR: Breaking changes
- MINOR: New features (backward compatible)
- PATCH: Bug fixes
