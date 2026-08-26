# Halbert Model Picker — Independent Design

**Date:** 2026-08-26
**Status:** Approved design, awaiting implementation plan
**Supersedes:** `documentation/design/unified-model-picker.md` (2026-08-23 shared-package
plan; never executed past vendoring) and the open questions in
`.handoff/LLM-PICKER-DESIGN-REVIEW-2026-08-26.md`.

## 1. Problem

Halbert's Settings → AI Models tab is in an in-between state after an attempt to unify
its model picker with SourcePrep's. What is true on 2026-08-26:

1. **Halbert runs on the legacy keys, not the unified ones.** The live user
   `models.yml` has `orchestrator.model` populated under the old top-level key and every
   `llm_config.*` slot `enabled: false`. The new picker reads and writes `llm_config`,
   so it shows an empty picker while chat works through the fallback in
   `model/client.py`. The unified slots have never held real data.
2. **Two endpoint lists in one file.** Top-level `saved_endpoints` (old picker, with API
   keys) and `llm_config.saved_endpoints` (new picker). They have already diverged.
3. **Two runtime readers.** `model/client.py` reads unified-then-legacy;
   `intake/pipeline.py` reads *only* `orchestrator/specialist/vision`, so intake routing
   never sees the new picker. `settings.py` status endpoints and `model/router.py` also
   read legacy keys; `settings.py` and the CLI `config_wizard.py` write them.
4. **Nothing is shared with SourcePrep.** Halbert never reads SourcePrep's LLM config
   and SourcePrep never reads Halbert's. The only coupling is the GPU advisory lock file
   and a copied schema shape. The banner claiming the config is "shared with SourcePrep"
   is false.
5. **Three of five vendored cards configure nothing.** Halbert's RAG and Chroma index use
   a hard-coded sentence-transformers embedder; no Halbert code reads
   `llm_config.embedding`, `code_model`, `coordinator_model`, `advanced`, `always_on`, or
   `model_context_cache`.
6. **The vendored `AIModelsSettings` is ~1,200 lines of SourcePrep-shaped UI** (mode
   toggle, mapped-mode blocks, Compute Profile, Pipeline Activity, Slot Guide in
   SourcePrep vocabulary, docs.sourceprep.io link, stub components).
7. **The picker offers providers chat cannot call.** `EndpointManager` lists seven
   providers; `call_llm_chat` handles only `ollama` and `openai`, sends no
   `Authorization` header, and routes `lm-studio` / `openai-compatible` into the Ollama
   branch. An endpoint can test green and then fail in chat.
8. The partial Vision card names specific models in its help text, which the legal pass
   forbids (Halbert never names or recommends AI models).

## 2. Decisions

| # | Decision | Rationale |
|---|---|---|
| D1 | **Halbert's model config is fully independent of SourcePrep.** No deferral, no daemon probe, no proxy to SourcePrep, no "SourcePrep" in Halbert's UI. | Halbert must work with the daemon down; the slot semantics differ (`small_model` is SourcePrep's catalogue summariser, not a chat model; SourcePrep has no vision slot); any secondary source means precedence rules and a network call in the chat path. The one thing worth sharing — the endpoint list — is a one-shot import, deferred to a follow-up (§11). |
| D2 | **Keep the robust picker primitives, drop the SourcePrep page.** Reuse the vendored `ModelCard` and `EndpointManager`; delete `AIModelsSettings` and everything only it needed. | The primitives (endpoint → model two-step select, model details with licence annotation, test buttons) are the upgrade the user wanted; the page around them is SourcePrep's product. |
| D3 | **Three slots in Halbert vocabulary:** `chat_model`, `specialist_model`, `vision_model`. | "small_model = the primary chat model" was the trap. The unified slots have never held real data, so renaming costs nothing now and never will again. |
| D4 | **One schema, one store module, one migration.** Every reader and writer goes through `model/llm_config.py`; legacy keys are migrated once and removed. | Ends the two-readers / two-endpoint-lists problem at the root. |
| D5 | **All seven providers stay in `EndpointManager`.** Providers the chat runtime cannot call are badged and excluded from slot dropdowns. `lm-studio` / `openai-compatible` / `openai` become callable with bearer auth. | User choice; the badge prevents "test green, chat fails". Anthropic / Google / Azure chat adapters are a follow-up (§11). |
| D6 | **The legacy Connection Status card is folded into a Quick-setup strip** inside the new picker, shown only while Chat is unconfigured. | The card's status rows duplicate `ModelCard`; only "Apply hardware defaults" and the "Ollama not running" hint are distinct. The fresh-install endpoint auto-create moves out of a `GET` handler. |

## 3. Scope

**In scope:** schema + migration; the store module; rewiring every legacy reader and
writer; the HTTP API; the new `ModelSettings` + `QuickSetup` components and trimmed
hook/types; `EndpointManager` trimming; provider mapping and bearer auth in
`call_llm_chat`; tests; doc supersession.

**Out of scope (see §11):** Import-from-SourcePrep; Vision-provided-by-Chat capability
hint; Anthropic / Google / Azure chat adapters; streaming; deeper `EndpointManager`
refactor.

**Untouched:** SourcePrep (`/Volumes/4TB-BAD/HumanAI/CoDRAG`) in its entirety; Haloysius;
`CompressionSettings`; Performance Tweaks; `routing`, `compression`, `handoff`,
`persona_names`, `providers` keys in `models.yml`; the GPU advisory lock.

## 4. Schema

`models.yml` (user config dir, located by `model/config_locator.py`) gains exactly this
under `llm_config`; nothing else in the file is owned by the picker.

```yaml
llm_config:
  saved_endpoints:
    - id: ep_3f9a2c1b          # opaque, stable; existing ids preserved on migration
      name: Local Ollama
      provider: ollama           # ollama | lm-studio | openai | openai-compatible | anthropic | google | azure-openai
      url: http://localhost:11434
      api_key: ""                # stored as-is; never returned masked (single-user local app)
  chat_model:       { enabled: true,  endpoint_id: ep_3f9a2c1b, model: "<name>" }
  specialist_model: { enabled: false, endpoint_id: "",          model: "" }
  vision_model:     { enabled: false, endpoint_id: "",          model: "" }
```

Slot rules: `enabled` is true only when `model` is non-empty and `endpoint_id` names an
existing endpoint. The store normalises on load (an enabled slot whose endpoint is
missing becomes disabled with a warning log).

Removed from Halbert's schema (dropped silently on load, never written back):
`embedding`, `small_model`, `large_model`, `code_model`, `coordinator_model`,
`assignment_mode`, `assignment_blocks`, `advanced`, `compute_nodes`,
`model_context_cache`. `small_model` / `large_model` are dropped rather than migrated
because on every known install they are `enabled: false`; if one *is* enabled and has a
model, it migrates to `chat_model` / `specialist_model` respectively, only when the target
slot is empty.

The repo template `config/models.yml` is rewritten to the new shape with empty slots and
the comment block updated; its legacy `orchestrator` / `specialist` / `vision` sections go.

### 4.1 Legacy migration (once, in the store)

Triggered by `load()` when any of top-level `orchestrator`, `specialist`, `vision`,
`saved_endpoints` is present.

1. Copy the file to `models.yml.bak` (overwrite; migration runs at most once per file
   because step 6 removes the trigger keys).
2. **Endpoints:** union of top-level `saved_endpoints` and `llm_config.saved_endpoints`,
   de-duplicated by `(provider, url)`; on a duplicate keep the `llm_config` entry's id and
   fill any empty `api_key` from the legacy entry. Legacy entries without an `id` get one.
3. **chat_model** ← `orchestrator` when `chat_model` is not enabled: model from
   `orchestrator.model`; endpoint resolved by `orchestrator.endpoint_id` if it exists in
   the merged list, else by `(provider, url)` match on `orchestrator.endpoint`, else a new
   endpoint `{name: "Migrated endpoint", provider: orchestrator.provider or ollama, url}`.
   Enabled iff model non-empty.
4. **specialist_model** ← `specialist` the same way; enabled iff `specialist.enabled`
   and model non-empty.
5. **vision_model** ← `vision` the same way; enabled iff model non-empty.
6. Delete top-level `orchestrator`, `specialist`, `vision`, `saved_endpoints`; write the
   file. Log one INFO line summarising what was migrated.

Idempotent: a second `load()` finds no trigger keys and does nothing.

## 5. Backend

### 5.1 Store module — `halbert_core/model/llm_config.py`

The only code that reads or writes `llm_config`.

```python
CHAT_CAPABLE_PROVIDERS = frozenset({"ollama", "lm-studio", "openai", "openai-compatible"})

@dataclass
class ResolvedModel:
    model: str
    url: str
    provider: str
    api_key: str            # "" when none

def load() -> dict                       # llm_config: defaults ← file ← migration ← normalise
def load_file() -> dict                  # the whole models.yml dict, post-migration (for readers that also need routing/compression)
def save(llm_config: dict) -> None       # rewrites only the llm_config key, preserves the rest
def update(partial: dict) -> dict        # deep-merge then save; returns full config
def resolve(slot: str) -> ResolvedModel | None   # None when slot disabled/unset
def api_key_for(url: str) -> str         # first endpoint whose url matches, else ""
def ensure_local_ollama_endpoint() -> bool       # adds "Local Ollama" if list empty and :11434 answers /api/tags; True if added
```

Writes go to a temp file in the same directory followed by an atomic rename (new; today
`yaml.dump` writes in place), and keep every non-`llm_config` key intact in meaning (YAML
re-serialised; comments in the user file are already lost today, so no regression).

### 5.2 Readers and writers (all via the store)

| Site | Today | After |
|---|---|---|
| `model/client.py` `get_configured_model()` | `small_model` → `large_model` → legacy `orchestrator` | `resolve("chat_model").model` or `""` |
| `get_ollama_endpoint()` | small/large endpoint → legacy → default | chat endpoint url, else `http://localhost:11434` |
| `get_specialist_model()` | `large_model` → legacy `specialist` | `resolve("specialist_model")` → `(model, url, provider)` or `(None, None, None)` |
| `get_vision_model()` | `vision_model` → legacy `vision` | `resolve("vision_model")` → `(model, url)` or `(None, chat url)` |
| `call_llm_chat(..., api_key=None)` | no auth; `provider == "openai"` else Ollama | provider mapping (§5.4); when `api_key` is None it is looked up with `api_key_for(endpoint)` |
| `intake/pipeline.py` | legacy dict keys | reads `llm_config.chat_model / specialist_model / vision_model` from the `model_config` dict it is given; `routes/agent.py` builds that dict with `load_file()` so it is post-migration; `routing.complexity_threshold` unchanged |
| `settings.py GET /model/status` | legacy keys; **writes** an endpoint on fresh install | reads via store; no writes; new response shape (§5.3) |
| `settings.py POST /model/apply-recommended` | writes `orchestrator.model` | writes `chat_model` with the local Ollama endpoint's id (calls `ensure_local_ollama_endpoint()` first); compression write unchanged |
| `settings.py POST /model/install` | writes `orchestrator.*` | writes `chat_model` the same way |
| `settings.py GET /model/loaded` | legacy | via `get_configured_model()` / `get_ollama_endpoint()` |
| `model/router.py` (`services/{name}/explain`) | own loader with legacy defaults | `resolve("chat_model")` / `resolve("specialist_model")`; its default-config block for these keys is removed |
| `model/config_wizard.py` (CLI) | writes legacy schema | writes `llm_config` via `update()`; creates the endpoint it chose |
| `dashboard/routes/llm.py` | `/global/config` on its own loader | thin HTTP layer over the store |

Call sites of the four `client.py` getters (30+) are untouched.

### 5.3 HTTP API (`dashboard/routes/llm.py`, `settings.py`)

| Method & path | Body / response | Notes |
|---|---|---|
| `GET /llm/config` | `{data: {llm_config, chat_capable_providers: [...]}}` | Calls `ensure_local_ollama_endpoint()` first so a fresh install sees its local Ollama without a write inside `/model/status`. |
| `PUT /llm/config` | body `{llm_config: <partial>}` → same shape as GET | Deep-merge via `update()`. Replaces `/global/config`. |
| `POST /api/llm/proxy/models` | unchanged | Model list with details + licence annotation. |
| `POST /api/llm/proxy/test` | unchanged | Endpoint reachability. |
| `POST /api/llm/proxy/test-model` | unchanged minus the `kind: embedding` branch | Slot-level completion test. |
| `GET /settings/model/status` | `{chat: {configured, model, endpoint_url, provider, reachable, model_available}, local_ollama: {reachable, url, model_count}, hardware: {tier, total_vram_gb}}` | Read-only. Drives the Quick-setup strip. |
| `POST /settings/model/apply-recommended` | unchanged response shape | Writes new schema. |
| **Deleted** | `GET/PUT /global/config`, `GET /llm/plan-limits`, `GET /embedding/status`, `POST /embedding/download`, `GET /llm/slots/status`, `POST /api/llm/proxy/cloud-models` | All stubs or SourcePrep-only. The Ollama-cloud candidate list is empty by design, so cloud-models was inert. |

### 5.4 Provider mapping in `call_llm_chat`

| `provider` | Request | Auth |
|---|---|---|
| `ollama` | `POST {url}/api/chat` | none |
| `openai`, `openai-compatible`, `lm-studio` | `POST {url}/v1/chat/completions` (url already ends in `/v1` → not doubled) | `Authorization: Bearer <key>` when key non-empty |
| `anthropic`, `google`, `azure-openai` | raise `UnsupportedProviderError("<provider> endpoints can list and test models but are not yet usable for chat")` | — |

The advisory GPU lock keeps its current rule (local providers only; `lm-studio` joins
`ollama`, `llamacpp`, `mlx`).

## 6. Frontend

### 6.1 Components

`components/llm/ModelSettings.tsx` (new, mounted in Settings → AI Models in place of
`UnifiedLLMSettings`):

```
┌ AI Models ───────────────────────────────────────────────┐
│ [QuickSetup strip — only while chat_model is not enabled] │
│ ┌ Chat model ──────────┐ ┌ Specialist model ───┐ ┌ Vision model ──┐
│ │ endpoint ▾  model ▾  │ │ endpoint ▾  model ▾ │ │ endpoint ▾ … │
│ │ status · Test        │ │ status · Test       │ │ status · Test│
│ └──────────────────────┘ └─────────────────────┘ └──────────────┘
│ ┌ Endpoints (EndpointManager) ─────────────────────────────┐
│ │ Local Ollama  ollama  http://localhost:11434   Test Edit │
│ │ Claude        anthropic  …  [Listing & testing only]     │
│ │ + Add endpoint                                           │
│ └──────────────────────────────────────────────────────────┘
└───────────────────────────────────────────────────────────┘
```

Card copy (final; no model names; no product names):

- **Chat model** — *The model you talk to. Required.*
- **Specialist model** — *Complex diagnostics and multi-step reasoning. Optional —
  routed by complexity; leave empty to use the Chat model.*
- **Vision model** — *Screenshots and images. Optional — leave empty to send images to
  the Chat model.*

`ModelCard` props used: `title`, `description`, `endpoint`, `model`, `endpoints`
(filtered to `chat_capable_providers`), `availableModels`, `modelDetails`,
`onEndpointChange`, `onModelChange`, `onRefreshModels`, `loadingModels`, `status`,
`onTest`, `testResult`, `testingConnection`. Not used: always-on, HuggingFace, cloud
discovery, source toggle.

`components/llm/QuickSetup.tsx` (new). Input: `GET /settings/model/status`. States:

| Condition | Content |
|---|---|
| `local_ollama.reachable && model_count > 0` | "Local Ollama detected with N models." + button **Use the largest model that fits my hardware** → `POST /settings/model/apply-recommended` → reload config; shows the response `message`. |
| `local_ollama.reachable && model_count == 0` | "Local Ollama is running but has no models yet. Pull one, then refresh." + Refresh. |
| not reachable | "No LLM endpoint is reachable. Start Ollama with `ollama serve` [Run in terminal] or add an endpoint below." (reuses the existing `halbert:run-command` event) |

Unmounted as soon as `chat_model.enabled` is true.

`EndpointManager.tsx` (trimmed in place): remove `PlanDropdown`, local/cloud concurrency
fields, compute-node select, `adminPolicy` gating and their props/state; keep provider
select (all seven), name, URL, API key, autofill hints, `ProbeButton` test. New prop
`chatCapableProviders: string[]`; rows whose provider is not in it show the badge
**Listing & testing only — not yet usable for chat**.

### 6.2 Hook and types

`hooks/useLLMConfig.ts` rewritten: state `{llmConfig, availableModels, modelDetails,
loadingModels, testingSlot: 'chat'|'specialist'|'vision'|null, testResults,
chatCapableProviders}`; handlers for endpoint add/edit/delete/test, fetch models, test
slot, slot change; debounced `PUT /llm/config` autosave (existing 800 ms pattern) plus
`flushPendingSave()`. Removed: HF download, mode switch, slots status, cloud models,
`model_context_cache` merging, `stripModeFields`.

`types/llm.ts` trimmed to: `LLMProvider`, `SavedEndpoint` (id, name, provider, url,
api_key), `LLMSlotConfig` (enabled, endpoint_id, model), `LLMConfig` (saved_endpoints +
three slots), `EndpointTestResult`, `ModelDetail`, and whatever `ModelCard` /
`EndpointManager` / `ProbeButton` still reference after trimming.

### 6.3 Deleted files

`components/llm/AIModelsSettings.tsx`, `UnifiedLLMSettings.tsx`,
`AdvancedLLMSettings.tsx`, `PlanDropdown.tsx`, `llmConfigHelpers.ts`, `stubs/*`,
`hooks/useSourcePrepDaemon.ts` (git history keeps it for the import follow-up).
`components/llm/index.ts` exports only what remains.

`Settings.tsx`: the Connection Status card, its `modelStatus` / `loadingStatus` /
`hardwareDefaultsMessage` state and fetch, and the static "Context Compression: Active"
badge are removed. `CompressionSettings` and Performance Tweaks remain where they are.
`documentation/legal/THIRD-PARTY-LICENSES.md` already attributes `components/llm/*`
generically and needs no change.

## 7. Runtime behaviour

- Chat: `chat_model` or an empty model name; callers already surface "choose one in
  Settings → AI Models" on empty.
- Specialist: used when `resolve("specialist_model")` is non-None and the complexity
  score crosses `routing.complexity_threshold`; otherwise chat. Unchanged logic, new
  source.
- Vision: used for image messages when set; otherwise images go to the chat model
  (existing behaviour in `routes/agent.py`).
- A slot pointing at an endpoint whose provider is not chat-capable cannot be saved from
  the UI (filtered dropdown) and is rejected by `PUT /llm/config` with a 422-style error
  `{error: {code: "PROVIDER_NOT_CHAT_CAPABLE", slot, provider}}` — hand-edited YAML gets
  the same treatment on `load()` (slot disabled, warning logged).

## 8. Error handling

- Migration failure (unreadable YAML, write error): log ERROR, leave the file untouched,
  serve defaults for the session; `.bak` is written before any rewrite so nothing is lost.
- `ensure_local_ollama_endpoint()` uses a 2 s timeout and never raises.
- `UnsupportedProviderError` surfaces in chat as the standard model-error message
  including the provider name and the badge wording.
- `PUT /llm/config` validates shape (unknown top-level keys under `llm_config` are
  dropped, not errors) so an older frontend build cannot corrupt the file.

## 9. Testing and gates

Backend (`pytest halbert_core/tests`, pathspec-style imports per the namespace gotcha):

- `test_llm_config_store.py`: defaults; migration from legacy-only, mixed, and
  none; idempotence; endpoint de-dupe and key back-fill; `.bak` written; endpoint
  creation when URL matches nothing; `small/large` dropped vs migrated; non-chat-capable
  slot disabled on load; `resolve()` / `api_key_for()`.
- `test_model_client.py`: the four getters on the new schema only (no legacy fallback);
  `call_llm_chat` provider → URL mapping and bearer header (mock `requests`);
  `UnsupportedProviderError`.
- `test_intake_pipeline.py`: fixtures moved to the new dict shape; routing assertions
  unchanged.
- `test_settings_model_routes.py`: `/model/status` read-only and new shape;
  `apply-recommended` writes `chat_model` + endpoint id.
- Existing `test_app_seam_model_backend.py`, `test_compute_probe.py`,
  `test_phase_d_integration.py` still pass.

Frontend (`npm run test`, `npm run build`):

- `ModelSettings.test.tsx`: renders exactly three cards with the specified titles; no
  text matching /embedding|sourceprep|coordinator|swarm/i; non-chat-capable endpoints are
  absent from slot dropdowns and badged in the endpoint list.
- `QuickSetup.test.tsx`: the three states; unmounted when chat is enabled.
- `test_frontend_no_relative_urls.py` continues to pass.

Live check before calling it done: start the dashboard against the real user
`models.yml`; confirm the migration produced `models.yml.bak`, the Chat card shows the
model that was in `orchestrator.model`, both legacy endpoints appear once each, and a
chat message answers.

## 10. Housekeeping

- `documentation/design/unified-model-picker.md`: add a "Superseded 2026-08-26" header
  linking here; body left intact as history.
- `.handoff/LLM-PICKER-DESIGN-REVIEW-2026-08-26.md`: append a "Resolution" section
  answering its six questions by reference to §2.
- Working tree: `AIAnalysisPanel.tsx`, `Apps.tsx`, `scripts/corpus_quality_gate.py`,
  `data/quality_gate_report*.json`, `.handoff/HANDOFF-SCOPE-FILTER-REVIEW-*` belong to a
  concurrent session — never staged by this work. All commits use explicit pathspecs.
  The in-progress hunks in the six LLM files are replaced by this work.
- Copy rule for every string added: no AI model names, no "SourcePrep".

## 11. Follow-ups (explicitly not in this pass)

1. **Import from SourcePrep** — button visible only when `:8400/health` answers; copies
   SourcePrep's saved endpoints into Halbert's list (de-dupe by provider+url) and offers to
   pre-fill Specialist from SourcePrep's Thinking model. One-shot copy, no runtime coupling.
   Resurrect `useSourcePrepDaemon.ts` from git.
2. **Vision provided by Chat** — badge the Vision card when `model/capabilities.py`
   (vendor-neutral tokens + Ollama `/api/show` capabilities) reports the chat model has
   vision.
3. **Anthropic / Google / Azure chat adapters** — generalise `_do_llm_call` onto the
   request shapes already present in `proxy_test_model`; then drop them from the badge.
4. **Streaming** — `_do_llm_call` ignores `stream`; out of scope here.
5. **EndpointManager** deeper trim (it remains ~700 lines after §6.1).
