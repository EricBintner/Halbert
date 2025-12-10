# Halbert_core — Phase 1 runtime skeleton

Python package scaffolding for Halbert Phase 1 (Observability Assistant): runtime graph, tools, ingestion, index, observability, evaluation.

This is a scaffold with interfaces and docstrings. Implementations will be filled during Phase 1 execution.

## Layout
- Halbert_core/runtime/ — agent graph and typed state
- Halbert_core/tools/ — OS-interacting tools (dry-run/confirm/audit)
- Halbert_core/ingestion/ — collectors and JSONL writer
- Halbert_core/index/ — vector index abstraction (ChromaDB)
- Halbert_core/obs/ — logging and tracing utilities
- Halbert_core/eval/ — evaluation harness and golden tasks

See docs under `docs/Phase1/` for detailed specifications.
