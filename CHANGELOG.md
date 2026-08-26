# Changelog

All notable changes to Halbert.

Format based on [Keep a Changelog](https://keepachangelog.com/).

---

## [Unreleased]

### Added
- Legal hub under `documentation/legal/`: `LICENSE.md`, `THIRD-PARTY-LICENSES.md`,
  `PRIVACY.md`, `DISCLAIMER.md`, `TRADEMARKS.md`, and the compliance action plan.
- `halbert license` (`--full`, `--third-party`) and `halbert --version`; `halbert info`
  and the dashboard server now print the GPLv3 legal notice.
- Foundation-model licence and attribution notices (`halbert_core.model.attribution`)
  in `halbert model-list-all`, `/api/llm/proxy/models`, and the model picker UI.
- SPDX licence headers on all first-party source files, enforced by
  `scripts/add_spdx_headers.py --check`; DCO sign-off check for pull requests.

### Changed
- Licence declared as `GPL-3.0-or-later` consistently across source headers,
  `pyproject.toml`, `Cargo.toml`, `package.json`, and `tauri.conf.json`.

---

## [0.1.1] - 2025-12-15

### Removed
- All LoRA-related code and CLI commands (`lora-list`, `lora-info`, `lora-set`, `lora-import`, `mlx-train-lora`, `mlx-load-lora`, `mlx-lora-status`)
- LoRA adapter support from model providers (MLX, llama.cpp, base)
- LoRA adapter loading from model loader
- LoRA-related tests

### Changed
- Renamed `mlx-prepare-training-data` to `prepare-training-data`
- Simplified model provider interfaces

---

## [0.1.0-alpha.1] - 2025-12-11

First public alpha release.

### Added
- Initial public release
- CLI interface (`Halbert/main.py`)
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
