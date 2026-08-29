# Review Packet 05: Unified Model Picker, LLM Router & GPU Concurrency

**Review Level:** **Fable Level Review**  
**Domain:** LLM Router Vendoring, Multi-Provider Endpoint Management, Advisory GPU Locking, and Dynamic Token Management  
**Target Date:** 2026-08-29  
**Status:** Ready for Multi-Provider Routing & Hardware Contention Review  

---

## 1. Executive Summary & Review Scope

Halbert transitioned from a fragmented, hardcoded model configuration to a vendored **SourcePrep LLM Router architecture**. This unification allows users to configure local Ollama/vLLM instances, cloud providers (OpenAI, Anthropic, Gemini, DeepSeek), and hybrid fallbacks through a single, schema-validated configuration system.

Key milestones delivered:
1. **SourcePrep Router Vendoring:** Integrated the `@prep/ui` LLM picker components into the frontend and backported the `/api/llm/*` proxy router into the Halbert backend.
2. **Unified Schema Adoption:** Refactored `client.py` to ingest `LLMConfig` dataclasses rather than relying on legacy platform yml files.
3. **GPU Contention & Advisory Locking:** Implemented cross-process advisory file locking (`ModelLockManager`) to prevent concurrent model loading from exhausting shared VRAM on local GPUs.
4. **Daemon Detection Deferral:** Built frontend hooks (`useSourcePrepDaemon.ts`, `useLLMConfig.ts`) that smoothly gracefully degrade when the external SourcePrep daemon is offline.

The reviewing model (**Fable**) must verify that model routing fallbacks operate reliably, examine GPU lock release edge-cases on unexpected process termination, and audit tool-calling payload translations across diverse LLM backends.

---

## 2. Planning & Design Documents (Past 2 Weeks)

| Document | Purpose | Key Themes |
|---|---|---|
| [`.handoff/MODEL-PICKER-PLAN-2026-08-26.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/MODEL-PICKER-PLAN-2026-08-26.md) | Comprehensive 5-step integration plan | Vendoring steps, UI replacement, schema alignment, GPU file locking |
| [`.handoff/LLM-PICKER-DESIGN-REVIEW-2026-08-26.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/LLM-PICKER-DESIGN-REVIEW-2026-08-26.md) | Architectural critique & security analysis | API key storage in keyring vs config files, fallback chains |
| [`.handoff/HANDOFF-LLM-PICKER-AND-CLAUDE-CODE-PARITY-2026-08-26.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/HANDOFF-LLM-PICKER-AND-CLAUDE-CODE-PARITY-2026-08-26.md) | Parity requirements with Claude Code | Tool definition schemas, streaming token delimiters, cost accounting |
| [`documentation/design/unified-model-picker.md`](file:///Volumes/4TB-BAD/Halbert/documentation/design/unified-model-picker.md) | SourcePrep LLM architecture overview | Endpoint abstraction, tier resolution, concurrency discovery |

---

## 3. Git History & Code Commits (Past Week: Aug 22 – Aug 29)

| Commit | Date | Summary | Key Files Changed |
|---|---|---|---|
| `bff3ce50` | 2026-08-24 | Feat(ui): vendor @prep/ui LLM picker components into Halbert frontend | `dashboard/frontend/src/components/llm/*`, `types/llm.ts` |
| `9a6b168f` | 2026-08-24 | Feat(llm): vendor SourcePrep LLM router into Halbert backend | `dashboard/routes/llm.py`, `dashboard/app.py` |
| `01633fe8` | 2026-08-24 | Feat(ui): render AIModelsSettings with daemon-detection deferral | `components/llm/UnifiedLLMSettings.tsx`, `pages/Settings.tsx` |
| `c4f57d75` | 2026-08-24 | Feat(model): update client.py to read unified LLMConfig schema | `model/client.py`, `model/__init__.py` |
| `83b9f7ff` | 2026-08-24 | Refactor: remove legacy model picker endpoints and UI | `dashboard/routes/settings.py`, `pages/Settings.tsx` |
| `232adf4f` | 2026-08-24 | Feat(model): advisory file lock for GPU contention | `model/lock_manager.py`, `tests/test_model_lock.py` |

---

## 4. Key Files & Architectural Components

- **Backend Router & Schema:**
  - [`halbert_core/halbert_core/dashboard/routes/llm.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/routes/llm.py)
  - [`halbert_core/halbert_core/model/client.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/model/client.py)
  - [`halbert_core/halbert_core/model/lock_manager.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/model/lock_manager.py)
- **Frontend Components & State:**
  - [`halbert_core/halbert_core/dashboard/frontend/src/components/llm/AIModelsSettings.tsx`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/components/llm/AIModelsSettings.tsx)
  - [`halbert_core/halbert_core/dashboard/frontend/src/components/llm/UnifiedLLMSettings.tsx`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/components/llm/UnifiedLLMSettings.tsx)
  - [`halbert_core/halbert_core/dashboard/frontend/src/hooks/useLLMConfig.ts`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/hooks/useLLMConfig.ts)

---

## 5. Incomplete Work & Open Items

1. **GPU Page Deep-Scan Refactor:** `dashboard/routes/gpu.py` and `pages/GPU.tsx` still contain a legacy route (`POST /api/gpu/analyze`) using raw Ollama endpoints. This must be rolled into the agent tool framework as specified in `.handoff/MASTER-TODO.md`.
2. **Tool-Calling Payload Adaptation:** Ensure that non-standard OpenAI-compatible endpoints properly serialize and deserialize JSON schema function calls without throwing format validation exceptions.

---

## 6. Review Directives for Fable

- **GPU File Lock Deadlock Protection:** Verify that `ModelLockManager` uses non-blocking advisory locks or robust timeout wrappers with automatic `finally` cleanups so stale lockfiles do not hang future LLM queries after a crash.
- **Credential Storage Scrutiny:** Ensure provider API keys entered in `UnifiedLLMSettings` are saved securely (via system keyring or encrypted storage) and are never exposed in plaintext frontend state dumps.
- **Verification Command:** Run `pytest halbert_core/tests/test_model_lock.py halbert_core/tests/test_client.py -v`.
