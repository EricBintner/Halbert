# Cerebric_core — Phase 1 runtime skeleton

Python package scaffolding for Cerebric Phase 1 (Observability Assistant): runtime graph, tools, ingestion, index, observability, evaluation.

This is a scaffold with interfaces and docstrings. Implementations will be filled during Phase 1 execution.

## Layout
- Cerebric_core/runtime/ — agent graph and typed state
- Cerebric_core/tools/ — OS-interacting tools (dry-run/confirm/audit)
- Cerebric_core/ingestion/ — collectors and JSONL writer
- Cerebric_core/index/ — vector index abstraction (ChromaDB)
- Cerebric_core/obs/ — logging and tracing utilities
- Cerebric_core/eval/ — evaluation harness and golden tasks

See docs under `docs/Phase1/` for detailed specifications.
