# LLM Picker Design Review Request

**Date:** 2026-08-26
**Status:** Seeking alternate perspective before implementation
**Author:** Devin session, to be reviewed by external AI

## Purpose

We discovered a regression in Halbert's LLM model picker UI and have been
working through the redesign. We've reached a point where the design
decisions need an independent review before we commit to implementation.
This document lays out the full context, the regression, the proposed
plan, and the open questions we want challenged.

---

## Background: The three codebases

Halbert is a sysadmin AI assistant with a chat interface. It integrates
two other projects:

- **Haloysius** (`/Volumes/4TB-BAD/Haloysius`) — a cognitive core library
  that gives Halbert a "self-model" (thoughts, worries, drives, emotions).
  It has a `ModelBackend` protocol (BYOK) but no model picker UI of its
  own. Halbert provides the model backend via an `AppSeam` adapter.

- **SourcePrep** (`/Volumes/4TB-BAD/HumanAI/CoDRAG`) — a codebase
  intelligence platform. It has its own daemon (`prep serve` on :8400),
  its own dashboard, its own LLM config, and its own model picker UI
  (`AIModelsSettings` component in `@prep/ui`). Halbert vendored a copy
  of this component.

All three run on the same machine. SourcePrep's daemon may or may not be
running at any given time.

---

## The regression

### What existed before

Halbert's Settings page had an "AI Models" tab with three model picker
cards, each with an endpoint dropdown and model dropdown:

1. **Chat Model** (orchestrator) — the primary model the user talks to
2. **Specialist Model** — a larger model for complex reasoning, routed
   by a complexity score
3. **Vision Model** — for screenshot interpretation

Plus a "Saved Endpoints" card where users could add/edit/delete LLM
endpoints (Ollama, OpenAI, Anthropic, etc.) with API keys and connection
testing.

### What happened

Commit `bff3ce5` vendored SourcePrep's `@prep/ui` LLM picker components
into Halbert's frontend. Commit `01633fe` rendered the vendored
`AIModelsSettings` component in the Settings page, wrapped in a new
`UnifiedLLMSettings` component. Commit `83b9f7f` then deleted the old
3-target picker (Chat/Specialist/Vision cards) and the old backend
endpoints, declaring them "superseded."

### What broke

`UnifiedLLMSettings` had a daemon-detection hook (`useSourcePrepDaemon`)
that polled `http://localhost:8400/health`. When the SourcePrep daemon
was running, it **hid the entire LLM picker** and showed a banner saying
"SourcePrep daemon is managing LLM models" with a link to SourcePrep's
dashboard. When the daemon was down, it showed the vendored
`AIModelsSettings` — which has SourcePrep's slot layout (Fast, Thinking,
Code, Coordinator, Embedding) but **no Vision slot**.

So the user lost:
1. The ability to pick models when SourcePrep was running (entire picker
   hidden)
2. The Vision model picker (not in SourcePrep's component)
3. The 3-target mental model (Chat/Specialist/Vision) replaced by
   SourcePrep's pipeline-oriented slots (Fast/Thinking/Code/Coordinator)

### What we've done so far (partial, needs rework)

We made `UnifiedLLMSettings` always show the picker (non-blocking
banner instead of hiding it), and added a `vision_model` slot to the
vendored `AIModelsSettings` component. This compiles and passes tests,
but we now believe this approach is wrong — see "Why the current
approach is wrong" below.

---

## The slot mapping problem

### SourcePrep's LLM slots

SourcePrep's pipeline has these LLM slots, defined in
`STAGE_MODEL_SLOT` (`stages.py:266`):

| Slot | Stages that use it | Purpose |
|---|---|---|
| `small_model` | CATALOGUE | Fast summarization pass |
| `large_model` | ENRICHMENT, GROUP_REASONING, CLUSTERING, ATLAS, DEEPENING, CONCEPTS, AUDIT | Deep reasoning |
| `code_model` | INFERRED_EDGES | Code-aware edge discovery |
| `coordinator_model` | Swarm planning + synthesis | Routes work to workers (large_model), merges results. Inherits large_model by default. |
| `embedding` | (not an LLM) | Vector encoding via ONNX nomic-embed-text-v1.5 |

SourcePrep has **no orchestrator slot**. Its "orchestrator" is Python
code (`orchestrator.py`), not a model. The pipeline stages are
dispatched by code, not by an LLM.

### Halbert's runtime model consumers

Halbert's `model/client.py` exposes four functions. We traced every
call site:

| Function | Slot read | Call sites | Purpose |
|---|---|---|---|
| `get_configured_model()` | `small_model` (falls back to legacy `orchestrator` key) | 17 in `agent.py`, 8 in `discovery.py`, 4 in `rag/*`, 2 in `settings.py`, 1 in `gpu.py`, 1 in `agents/llm_client.py`, 1 in `app_seam.py` | **The primary chat model.** Every user message, every RAG query, every discovery scan, every cognitive tick. The workhorse. |
| `get_specialist_model()` | `large_model` (falls back to legacy `specialist` key) | 5 in `agent.py`, 1 in `settings.py`, 1 in `discovery.py` | Complex reasoning, routed by `score_query_complexity()` when complexity > 0.5 |
| `get_vision_model()` | `vision_model` (falls back to legacy `vision` key) | 2 in `agent.py` | Screenshot interpretation only |
| `get_ollama_endpoint()` | `small_model` endpoint (falls back to `orchestrator` endpoint) | 10+ call sites | Resolves the endpoint URL for the orchestrator |

### The mismatch

Halbert's `get_configured_model()` reads `small_model` as the
orchestrator (primary chat model). But in SourcePrep, `small_model` is
just the catalogue summarization pass — a fast, cheap model for
summarizing files. These are semantically different roles:

- **Halbert orchestrator** = the AI the user talks to. Needs to be
  good at conversation, instruction following, tool use. Typically a
  strong 14B+ model.
- **SourcePrep small_model** = catalogue summarization. Needs to be
  fast and cheap. Typically a 7-12B model.

If Halbert defers its orchestrator to SourcePrep's `small_model`, the
user might get a cheap catalogue model as their primary chat model — a
silent downgrade.

### The one slot where deferral makes sense

`large_model` is the one slot where both systems want the same thing: a
big, capable reasoning model. SourcePrep uses it for deep enrichment and
thinking stages. Halbert uses it for complex diagnostics. Deferring
Halbert's specialist to SourcePrep's `large_model` is semantically
correct.

### Summary of overlap

| Halbert role | Halbert reads | SourcePrep's use | Deferral makes sense? |
|---|---|---|---|
| Orchestrator (chat) | `small_model` | Catalogue summarization | **No** — different purposes, same slot name |
| Specialist (reasoning) | `large_model` | Deep enrichment, thinking | **Yes** — both want a big reasoning model |
| Vision | `vision_model` | Doesn't exist | **No** — Halbert-only |
| (not used by Halbert) | — | `code_model` | N/A — SourcePrep-only |
| (not used by Halbert) | — | `coordinator_model` | N/A — SourcePrep-only |
| (not used by Halbert) | — | `embedding` | N/A — SourcePrep-only |

---

## Why the current approach is wrong

We added `vision_model` to the vendored `AIModelsSettings` component
(SourcePrep's component). This pollutes a SourcePrep-derived component
with a Halbert-specific slot. The component also shows SourcePrep-only
slots (embedding, code, coordinator) that Halbert's runtime never reads.
The slot labels ("Single / Fast Model", "Thinking Model", "Swarm
Coordinator") are SourcePrep's pipeline vocabulary, not Halbert's
user-facing vocabulary ("Chat Model", "Specialist Model", "Vision
Model").

The fundamental issue: **Halbert and SourcePrep have different slot
semantics, and sharing one component forces one to adopt the other's
vocabulary.**

---

## Proposed plan (for review)

### Config storage

Halbert's `models.yml` stores its own `llm_config` with:

```yaml
llm_config:
  defer_specialist_to_sourceprep: false  # new field
  saved_endpoints: [...]                 # Halbert's own endpoint list
  small_model:                           # Halbert's orchestrator
    enabled: true
    endpoint_id: "ep_local"
    model: "deepseek-v4-flash:cloud"
  large_model:                           # Halbert's specialist
    enabled: true
    endpoint_id: "ep_remote"
    model: "deepseek-v4-pro:cloud"
  vision_model:                          # Halbert's vision (always own)
    enabled: true
    endpoint_id: "ep_remote"
    model: "kimi-k3:cloud"
```

SourcePrep's config stays in its own store. Halbert never writes to it.

When `defer_specialist_to_sourceprep: true` and the daemon is running,
Halbert reads the specialist model from SourcePrep's `/global/config`
API at runtime (in `get_specialist_model()`). The orchestrator and
vision always come from Halbert's own `models.yml`.

### UI: New `HalbertLLMSettings` component

Instead of reusing SourcePrep's `AIModelsSettings`, create a separate
`HalbertLLMSettings` component that renders only the 3 slots Halbert
needs, with Halbert's labels:

1. **Chat Model** (small_model) — always editable
2. **Specialist Model** (large_model) — editable unless "Use SourcePrep's
   Thinking Model" checkbox is checked and daemon is running
3. **Vision Model** (vision_model) — always editable

Reuses `ModelCard` and `EndpointManager` primitives from the vendored
components, but with its own layout and labels.

### The checkbox

Only appears when SourcePrep daemon is detected. Label: "Use SourcePrep's
Thinking Model for specialist tasks."

**When checked:**
- Specialist Model card shows SourcePrep's current `large_model` value,
  disabled (read-only)
- A note: "Specialist model is managed by SourcePrep. Uncheck to
  override."
- Chat and Vision remain fully editable

**When unchecked (or daemon not running):**
- Specialist Model card is editable, values from Halbert's `models.yml`
- All 3 slots are editable

### Backend changes

1. Add `defer_specialist_to_sourceprep: bool` to `_default_llm_config()`
   in `llm.py`
2. Add `GET /llm/sourceprep-config` endpoint that proxies to SourcePrep's
   `/global/config` to fetch the shared slot value for display
3. `model/client.py`:
   - `get_configured_model()` — always reads from Halbert's `models.yml`
   - `get_specialist_model()` — when `defer_specialist_to_sourceprep` is
     true and daemon is running, reads from SourcePrep's config. Falls
     back to local if daemon is unreachable.
   - `get_vision_model()` — always reads from Halbert's `models.yml`

### What to revert from the partial work done

- Revert the `vision_model` ModelCard addition to `AIModelsSettings.tsx`
  (it doesn't belong in SourcePrep's component)
- Keep `vision_model` in `types/llm.ts`, `useLLMConfig.ts`, `llm.py`
  default config, and `model/client.py` (all still needed)
- Replace `UnifiedLLMSettings.tsx` to render the new
  `HalbertLLMSettings` instead of `AIModelsSettings`

---

## Open questions for the reviewer

1. **Is the slot mapping correct?** We claim Halbert's orchestrator
   reads `small_model` and that this is semantically different from
   SourcePrep's `small_model` (catalogue). Is this the right read of the
   code? Should we instead add a dedicated `orchestrator_model` slot to
   avoid the name collision entirely?

2. **Is deferring only the specialist the right call?** We argue that
   `large_model` is the only slot where deferral makes sense because
   both systems want a big reasoning model. The orchestrator can't
   defer because SourcePrep's `small_model` is a catalogue model, not a
   chat model. Is this correct, or is there a better deferral strategy?

3. **Separate component vs. prop-driven filtering?** We propose creating
   a new `HalbertLLMSettings` component instead of adding
   `visibleSlots`/`disabledSlots` props to the existing
   `AIModelsSettings`. Is the code duplication worth the cleaner
   separation? Or would prop-driven filtering be more maintainable?

4. **Should the endpoint list be shared?** Currently Halbert and
   SourcePrep have separate `saved_endpoints` arrays. If the user
   configures an endpoint in SourcePrep, Halbert doesn't see it (and
   vice versa). Should we share endpoints when deferring, or keep them
   separate?

5. **What about the legacy `orchestrator`/`specialist`/`vision` keys?**
   `model/client.py` falls back to the old top-level keys
   (`orchestrator`, `specialist`, `vision`) in `models.yml` when the
   unified `llm_config` slots aren't set. Should we keep this fallback
   for backward compatibility, or remove it and require the unified
   schema?

6. **Is there a simpler design we're missing?** The current proposal
   involves a new component, a new backend endpoint, a new config field,
   and conditional runtime model resolution. Is there a simpler approach
   that achieves the same goals (always-visible picker, Halbert-specific
   slots, optional deferral for the one slot where it makes sense)?

---

## Relevant files

### Halbert (`/Volumes/4TB-BAD/Halbert`)

- `config/models.yml` — the LLM config file (unified schema + legacy keys)
- `halbert_core/halbert_core/model/client.py` — runtime model resolution
  (`get_configured_model`, `get_specialist_model`, `get_vision_model`)
- `halbert_core/halbert_core/dashboard/routes/llm.py` — backend API for
  the model picker (`/global/config`, `/api/llm/proxy/*`)
- `halbert_core/halbert_core/dashboard/frontend/src/components/llm/UnifiedLLMSettings.tsx`
  — wrapper that currently renders `AIModelsSettings` with daemon
  detection
- `halbert_core/halbert_core/dashboard/frontend/src/components/llm/AIModelsSettings.tsx`
  — vendored SourcePrep component (Fast/Thinking/Code/Coordinator/Embed)
- `halbert_core/halbert_core/dashboard/frontend/src/components/llm/EndpointManager.tsx`
  — vendored endpoint CRUD component (reusable)
- `halbert_core/halbert_core/dashboard/frontend/src/components/llm/ModelCard.tsx`
  — vendored model picker card (reusable)
- `halbert_core/halbert_core/dashboard/frontend/src/hooks/useLLMConfig.ts`
  — Halbert's LLM config hook (endpoint CRUD, model fetch/test, autosave)
- `halbert_core/halbert_core/dashboard/frontend/src/hooks/useSourcePrepDaemon.ts`
  — daemon health probe
- `halbert_core/halbert_core/dashboard/frontend/src/types/llm.ts` —
  shared type definitions
- `halbert_core/halbert_core/dashboard/frontend/src/pages/Settings.tsx`
  — Settings page that mounts `UnifiedLLMSettings` in the AI Models tab

### SourcePrep (`/Volumes/4TB-BAD/HumanAI/CoDRAG`)

- `src/prep/services/pipeline/stages.py:266` — `STAGE_MODEL_SLOT` mapping
  (which slot each pipeline stage uses)
- `src/prep/services/config_manager.py:320-373` — default `llm_config`
  schema with all 5 slots
- `packages/ui/src/components/llm/AIModelsSettings.tsx` — the original
  SourcePrep component (Halbert vendored a copy)
- `src/prep/dashboard/src/hooks/useLLMConfig.ts` — SourcePrep's LLM
  config hook (Halbert adapted a copy)

### Haloysius (`/Volumes/4TB-BAD/Haloysius`)

- `src/haloysius/seam.py` — `ModelBackend` protocol (BYOK, Halbert
  provides the implementation via `app_seam.py`)
- `src/haloysius/persona/thought_generator.py` — `ThoughtGenerator`
  takes an `llm_generate` callback (currently not wired — falls back to
  templates)

### Git history of the regression

- `bff3ce5` — "feat(ui): vendor @prep/ui LLM picker components into
  Halbert frontend"
- `01633fe` — "feat(ui): render AIModelsSettings in Settings with
  daemon-detection deferral (Steps 2 + 2b)"
- `83b9f7f` — "refactor: remove legacy model picker endpoints and UI
  (Step 4)" — **the regression commit, removed 1833 lines**
