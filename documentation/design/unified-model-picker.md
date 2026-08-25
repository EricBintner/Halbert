# Unified Model Picker — Implementation Strategy & Design

**Status:** Plan set (2026-08-23). Awaiting execution.
**Reads with:** [the-being.md](the-being.md) (the product vision this serves),
[explorations.md](explorations.md) (the catalog of design seams this lands into).

**Revision 2 (2026-08-23):** Added §11 (user invisibility), §12 (branding credit),
§13 (licensing model). Architecture shifted from "shared package, no daemon" to "shared
daemon, bundled by both products" after clarifying that the daemon must work standalone
for each product and that SourcePrep's free tier is generous enough to cover Halbert's
single-project use case.

---

## 0. TL;DR

Halbert and SourcePrep both need a model picker. SourcePrep already has a superior one
(7 providers, 5 slots, concurrency, plan tiers, compute nodes, cloud discovery, searchable
select, admin policy, mapped/structured assignment modes). Halbert has a simpler one
(3 roles, 3 providers, basic endpoint CRUD). Rather than rebuild, we unify on
SourcePrep's picker — but **without forcing either product to depend on the other being
installed.**

The strategy: **extract the shared LLM-config layer into a package boundary, then consume
it from both products.** Extraction is iterative — we vendor first, cut dependencies
later. The picker UI lands in Halbert's Settings page within days, not weeks, by linking
SourcePrep's existing `@prep/ui` component library and routing Halbert's backend to a
vendored copy of the LLM router.

This document is the full plan: the problem, the rejected alternatives, the chosen
architecture, the phased steps, the risks, and the verification gates.

---

## 1. The problem

### 1.1 Two products, one machine, one GPU

Halbert is a conversational OS custodian. SourcePrep is a code-awareness daemon + dashboard
for AI coding agents. Both talk to the same Ollama on `:11434`. Both maintain their own copy
of "what models exist on this machine." That duplication is the bug.

The model picker looks like an app feature, but it's actually **machine infrastructure.**
Every AI app on the box — Halbert, SourcePrep, Claude Code, OpenClaw — talks to the same
LLM endpoints. Having each app maintain its own copy of "what models exist, what their
concurrency limits are, what plan tier we're on" is redundant and drifts.

### 1.2 The current state of each picker

**Halbert's picker** (the simpler one):

- **Backend:** `dashboard/routes/settings.py` (~1100 lines). REST API over `config/models.yml`.
  Endpoints: `GET/POST /model`, `GET /model/status`, `POST /model/apply-recommended`,
  `POST /model/install`, `POST /model/test`, `GET/POST /endpoints`, `GET /endpoints/{id}/models`,
  `POST /endpoints/{id}/test`, `DELETE /endpoints/{id}`, `POST /assign/{guide|specialist|vision}`,
  `POST /specialist/test`, `POST /specialist/clear`, plus deprecated legacy routes.
- **Frontend:** inline in `Settings.tsx` (~3287 lines; model cards at lines 1395–1770).
  Three role cards (Guide/Orchestrator, Specialist, Vision). Endpoint → model two-step
  selection. Capability badges (thinking/vision/code). Hardware-tier recommendations.
- **Schema:** 3 roles + `saved_endpoints` (id, name, url, provider, api_key).
- **Providers supported:** ollama, openai, anthropic (3).
- **Missing vs. SourcePrep:** concurrency, compute nodes, plan tiers, cloud model discovery,
  searchable model select, model details (context window, rate limits, batch estimates),
  admin policy, mapped/structured assignment modes, HuggingFace embedding download,
  coordinator slot, always-on toggle, deep analysis settings.

**SourcePrep's picker** (the superior one):

- **UI:** `packages/ui/src/components/llm/` — 11 files, ~5756 lines:
  - `AIModelsSettings.tsx` (1173) — main panel, orchestrates everything
  - `EndpointManager.tsx` (746) — endpoint CRUD with 7 providers, autofill, concurrency, plan tiers
  - `ModelCard.tsx` (548) — searchable select, cloud discovery, HF download, always-on, model details
  - `LLMAssignmentBlockCard.tsx` (280) + `LLMAssignmentsPipeline.tsx` (188) — mapped mode (per-task model assignment)
  - `AdvancedLLMSettings.tsx` (82), `DeepAnalysisSettings.tsx` (310), `PlanDropdown.tsx` (138),
    `ProbeButton.tsx` (214), `llmConfigHelpers.ts`, `provider-utils.ts`, `index.ts`
- **Types:** `packages/ui/src/types.ts` — `LLMConfig`, `SavedEndpoint`, `LLMSlotConfig`,
  `ComputeNode`, `AdminPolicy`, `EmbeddingConfig`, `AdvancedLLMSettings`, `LLMAssignmentBlock`,
  `ModelStatusResult`, `EndpointTestResult`, `SchedulerStatus`, etc.
- **Hook:** `src/prep/dashboard/src/hooks/useLLMConfig.ts` — state management + debounced autosave.
- **Backend:** `src/prep/api/routers/llm.py` (~1600 lines) + `system.py` (`/global/config`).
  14 endpoints: `GET/PUT /global/config` (SQLite `llm_config`), `/llm/plan-limits`,
  `/llm/status`, `/llm/test`, `/llm/slots/status`, `/api/llm/proxy/models`,
  `/api/llm/proxy/cloud-models`, `/api/llm/proxy/test`, `/api/llm/proxy/test-model`,
  `/api/llm/model-status`, `/api/llm/mode-switch`, `/embedding/status`, `/embedding/download`.
- **5 slots:** embedding, small, large, code, coordinator.
- **7 providers:** ollama, lm-studio, openai, openai-compatible, anthropic, google, azure-openai.
- **`@prep/ui` is a separate npm workspace** designed as a reusable shared library
  (has Storybook, its own `package.json`, typed props, primitives).

### 1.3 The constraint

The unified picker must work for:

- **Halbert-only users** — people who want a conversational OS custodian. They should never
  see "SourcePrep" in the UI, never be asked to install it.
- **SourcePrep-only users** — developers who want code-awareness for their existing AI tools
  (Claude Code, Cursor, Windsurf). They should never see "Halbert," never be asked to install it.
- **Both installed** — a power user who runs both. Config should be shareable, but not forced.
  The relationship between the two products should surface only as a machine-level convenience,
  not as "you must install X to use Y."

---

## 2. Rejected alternatives

### 2.1 "Halbert owns config, port the UI"

Duplicate SourcePrep's 14 backend endpoints in Halbert. Maintain two copies of model-fetching,
cloud-discovery, plan-limits, concurrency logic.

**Rejected.** The whole point of embedding SourcePrep's work is to *not* rebuild what it
already has. Two copies will drift; the drift will be silent; users on one product will get
features the other doesn't have, with no clear reason.

### 2.2 "Embed SourcePrep's dashboard route via iframe"

SourcePrep daemon serves its own model-picker page. Halbert's dashboard embeds it via iframe
or reverse-proxy at `/settings/models`.

**Rejected.** Cross-frame styling and communication is painful. The user would see two
different design languages in one app. The iframe can't easily participate in Halbert's
navigation, theming, or chat-context summoning (per the-being.md's "dual-container modules"
pattern). It's a hack that buys nothing over linking the component library.

### 2.3 "Copy the components into Halbert"

Copy the 11 LLM component files + relevant types into Halbert's frontend `src/`. Halbert owns
its copy, can adapt freely.

**Workable as a fallback**, but risks drift from SourcePrep upstream. Prefer linking the
package; fall back to copying only if the package boundary proves unworkable after a real
attempt. (See Step 0 — the 30-minute feasibility check.)

### 2.4 "SourcePrep daemon owns everything, Halbert is a thin client"

SourcePrep daemon is canonical. Halbert's chat path reads config via `SourcePrepClient`.
Requires SourcePrep daemon running for Halbert chat to work.

**Rejected.** This assumes users have both or want to install Halbert if they only want
SourcePrep. It also makes Halbert dependent on a separate process being up — a process
management burden and a failure mode (daemon down → Halbert chat broken) that doesn't exist
today. The daemon is the right *runtime* owner for concurrency arbitration (Phase 4), but
config storage belongs to a shared file that both apps can read/write independently.

---

## 3. The chosen architecture

### 3.1 Core principle: shared layer as a package, not a process

The LLM config layer — config store, REST router, model-fetch/test proxy logic, UI components
— becomes a **package boundary** consumed by both products. No subprocess management, no port
coordination, no singleton locking. Each product's process owns its own config store by
default. Sharing is opt-in (point both at the same config file/path).

This matches how the code is already structured: the LLM router in SourcePrep is a
self-contained FastAPI router file, and `@prep/ui` is already a separate npm workspace
designed for reuse.

### 3.2 The packaging split

| Layer | Owner | What it is | Consumed by |
|-------|-------|-----------|-------------|
| **LLM config store + router** (Python) | Shared package | YAML-backed config store (single file, file-locked) + FastAPI router (`/llm/*`, `/global/config`) + model-fetch/test proxy logic | Halbert (mounted at `/api/llm/*`), SourcePrep standalone (mounted at `/llm/*`) |
| **LLM UI components** (TypeScript) | `@prep/ui` (or extracted `@sourceprep/llm-ui`) | The 11 LLM component files + relevant types + `useLLMConfig` hook | Halbert's frontend, SourcePrep's dashboard |
| **Chat path / inference** | Each product's own code | Halbert's `model/client.py`, SourcePrep's `core/llm_client.py` — both read config from the shared store | Product-specific |
| **Concurrency arbitration** (future) | Optional shared daemon or lock file | AIMD backoff, compute nodes, plan tiers — the "brain" for GPU sharing | Both products, opt-in |

### 3.3 Config storage: one YAML file, one source of truth

SourcePrep currently stores `llm_config` in SQLite (via its settings store). Halbert uses
`config/models.yml`. For the unified layer, we choose **a single YAML file as the only
config store**, with a file-lock write protocol. No SQLite, no cache, no fallback copy.
One file. Always.

**The daemon reads and writes this file. Halbert's chat path reads this same file.** If
the daemon is down, Halbert reads the same file the daemon would have read — it's not a
"fallback," it's the same single store. The daemon is the preferred writer (richer
validation, concurrency checks, proxy endpoints), but Halbert can also write directly
if the daemon is down. A file lock (`fcntl` on POSIX, `msvcrt.locking` on Windows)
prevents write corruption when both are running.

This eliminates the silent-divergence risk: there is never a second copy of the config
that could go stale. The user always sees the same model list regardless of whether the
daemon is up or down, because there's only one list.

Reasons for YAML over SQLite:

- **Human-editable.** The design docs (the-being.md §2) emphasize provenance and
  rationale-persistence. A config file a user can read and diff in git fits that philosophy.
  SQLite is opaque.
- **Git-diffable.** Users who version their dotfiles can track model config changes.
- **Zero migration risk for Halbert.** Halbert already reads YAML. Extending the schema is
  additive. No one-time import script, no migration bugs.
- **Single source of truth.** One file means no sync, no cache invalidation, no stale
  copies. The daemon and Halbert both point at the same path.
- **SourcePrep migrates from SQLite to YAML.** SourcePrep standalone switches its LLM
  config backend from SQLite to YAML (the `ConfigStore` protocol supports both; we pick
  YAML as the default for the shared layer). Existing SourcePrep users get a one-time
  SQLite→YAML migration on first launch of the updated version.

The tradeoff: YAML lacks transactions. For a single-user desktop app where config changes
are rare and human-initiated, a file lock is sufficient. Concurrent-write safety (both
apps writing at once) is handled by the lock — acquire before write, release after. If
the daemon is writing, Halbert waits; if Halbert is writing, the daemon waits.

### 3.4 The user experience

**Halbert-only user:** Installs Halbert. Settings page shows the full model picker (powered
by the shared package + `@prep/ui` components). Config stored in `config/models.yml`
(extended schema). No mention of SourcePrep anywhere in the UI. The code-awareness features
(prep_search, trace graphs) are Halbert features, branded as Halbert.

**SourcePrep-only user:** Installs SourcePrep. Dashboard shows the same model picker. Config
stored in the same YAML file (SourcePrep migrates from SQLite to YAML as part of this work).
No mention of Halbert. This is the current state, basically unchanged except the storage
backend.

**Both installed:** Both apps read the same YAML file automatically — config is always
in sync because there is only one file. However, **Halbert's model picker becomes read-only
when the SourcePrep daemon is detected running.** Instead of a duplicate editable picker,
Halbert's Settings page shows the current model configuration (read from the shared YAML)
with editing disabled, plus a **"Manage SourcePrep models"** button that links to
SourcePrep's dashboard (`http://localhost:8400`). This avoids two identical editable pickers
competing for the same config file. The user manages models in one place (SourcePrep's
dashboard); Halbert reflects those changes immediately via the shared YAML. If the
SourcePrep daemon stops, Halbert's picker re-enables automatically. A small status indicator
shows which state Halbert is in: "Model config managed by SourcePrep" (daemon detected) or
"Model config managed here" (daemon not detected).

### 3.5 Slot mapping: Halbert's roles → SourcePrep's slots

Halbert's 3 roles map onto SourcePrep's 5 slots as follows:

| Halbert role | SourcePrep slot | Notes |
|---|---|---|
| orchestrator (guide) | `small_model` | Primary chat model. SourcePrep's "small" = fast, always-on. |
| specialist | `large_model` | Complex reasoning, code generation. SourcePrep's "large" = deep. |
| vision | (no direct equivalent) | Halbert-specific. Add as a 6th slot or keep as a Halbert-specific extension field. |
| (none) | `embedding` | SourcePrep needs this for indexing. Halbert doesn't currently configure embeddings separately (uses compression package's own embedder). Add to Halbert's schema but mark optional. |
| (none) | `code_model` | SourcePrep's code-specific slot. Halbert's specialist covers this. Map specialist → both `large_model` and `code_model`, or let Halbert ignore `code_model`. |
| (none) | `coordinator_model` | SourcePrep's swarm orchestrator. Halbert doesn't have a swarm. Ignore in Halbert. |

**Decision:** The shared schema has all 5 slots. Halbert's UI shows 3 (small/large/vision),
with embedding and coordinator hidden behind an "Advanced" toggle. This keeps the UI simple
for Halbert's audience while preserving schema compatibility.

---

## 4. Phased implementation

### Step 0 — Feasibility check (30 minutes, do first)

**Goal:** Validate the biggest risk (npm package boundary) before committing to anything.

**Actions:**

1. In Halbert's frontend (`halbert_core/halbert_core/dashboard/frontend/`), add `@prep/ui`
   as a `file:` dependency pointing at `/Volumes/4TB-BAD/HumanAI/CoDRAG/packages/ui`.
2. Run `npm install` and `npm run build`.
3. Import `AIModelsSettings` from `@prep/ui` in a throwaway test page. See if it renders.

**Pass criteria:**
- `@prep/ui` installs and builds without dragging in the entire SourcePrep monorepo.
- The component renders (even if unstyled or broken-looking — we just need it to mount).
- No unresolvable import chains that reach back into SourcePrep's daemon/dashboard code.

**Fail path:** If `@prep/ui` can't be linked cleanly (e.g., it imports from
`@prep/dashboard` or has peer deps that conflict), fall back to copying the 11 LLM component
files + types into Halbert's frontend. This is more work but unblocks the integration.
Document the failure reason — it informs whether `@sourceprep/llm-ui` extraction (Phase 3)
is worth doing.

**Why this step exists:** The entire plan hinges on being able to reuse SourcePrep's UI
components. If the package boundary doesn't work, every subsequent step changes. 30 minutes
of validation saves days of misdirected work.

---

### Step 1 — Vendor the LLM router into Halbert's backend

**Goal:** Get `/api/llm/*` serving from Halbert's FastAPI app, backed by `models.yml`
(extended schema).

**Actions:**

1. Copy `src/prep/api/routers/llm.py` from SourcePrep into Halbert at
   `halbert_core/halbert_core/dashboard/routes/llm.py`.
2. Copy `src/prep/api/routers/system.py`'s `/global/config` endpoint logic into the same
   file (or a new `global_config.py`).
3. Stub every import that reaches back into `prep.server` / `prep.core`:
   - `_load_ui_config` → read `models.yml` directly
   - `_save_ui_config` → write `models.yml` with file lock
   - `_deep_merge` → inline a simple dict-merge utility
   - `_index`, `_project_indexes` → not needed for LLM config; remove or stub
   - Settings store (SQLite) → replace with YAML read/write
4. Mount the router in `dashboard/app.py` at `/api/llm`.
5. Extend `models.yml` schema to include the richer fields:
   - `saved_endpoints` gains: `compute_node_id`, `local_concurrency`, `cloud_concurrency`,
     `plan_tier`
   - New top-level keys: `embedding`, `small_model`, `large_model`, `code_model`,
     `coordinator_model`, `compute_nodes`, `assignment_blocks`, `advanced`
   - Keep existing `orchestrator`/`specialist`/`vision` keys as aliases that read/write
     `small_model`/`large_model`/`vision` respectively (backward compat).
6. Write a `ConfigStore` protocol class with a YAML backend (the single backend for the
   shared layer). Both Halbert and SourcePrep use the same YAML store. The router speaks
   to the protocol, not the backend directly. SourcePrep's existing SQLite store gets a
   one-time migration to YAML on first launch of the updated version.

**Pass criteria:**
- `GET /api/llm/status` returns a valid response from Halbert's backend.
- `GET /api/global/config` returns the current `models.yml` content in the `LLMConfig` shape.
- `PUT /api/global/config` writes back to `models.yml` (with file lock).
- `POST /api/llm/proxy/models` fetches models from a configured Ollama endpoint.
- No imports from `prep.server` or `prep.core` remain.

**Known tangles to cut (from code review):**
- `llm.py` imports `from prep.server import _load_ui_config, _save_ui_config, _index, _project_indexes`
  (in `update_global_config_v2`). Replace with the `ConfigStore` protocol.
- `llm.py` imports `from prep.services.config_manager import _deep_merge` (moved in commit
  f3dbd219). Inline a 10-line deep-merge utility.
- `llm.py` references the settings store for `llm_config` key. Replace with YAML read.
- `system.py`'s `/global/config` uses `_load_ui_config` which reads from SQLite settings
  store. Replace with YAML read.
- Compute node CRUD (`/compute/nodes`) reads/writes `llm_config.compute_nodes`. Same YAML
  backend.
- Scheduler status (`/compute/scheduler-status`) references the live scheduler — Halbert
  doesn't have one. Stub to return empty/inactive status.

---

### Step 2 — Render `AIModelsSettings` in Halbert's Settings page

**Goal:** Replace Halbert's inline model cards with SourcePrep's `AIModelsSettings` component.

**Actions:**

1. In Halbert's `Settings.tsx`, remove the inline model card JSX (lines ~1395–1770).
2. Import `AIModelsSettings` from `@prep/ui` (or the copied components).
3. Import `useLLMConfig` from `@prep/ui` (or adapt it to Halbert's API client).
4. Wire the component's callbacks to Halbert's new `/api/llm/*` + `/api/global/config`
   endpoints:
   - `onAddEndpoint` → `POST /api/llm/endpoints` (or `PUT /api/global/config` with
     updated `saved_endpoints`)
   - `onFetchModels` → `POST /api/llm/proxy/models`
   - `onTestEndpoint` → `POST /api/llm/proxy/test`
   - `onTestModel` → `POST /api/llm/proxy/test-model`
   - `onConfigChange` → `PUT /api/global/config` (debounced autosave via `useLLMConfig`)
5. Adapt the `useLLMConfig` hook to Halbert's API base URL (`/api` prefix vs. SourcePrep's
   root). Either parameterize the hook or write a thin Halbert-specific wrapper.
6. Hide slots Halbert doesn't use (embedding, coordinator, code) behind an "Advanced"
   toggle. Show small_model (as "Chat"), large_model (as "Specialist"), and vision.
7. Preserve Halbert-specific UI elements that live near the model cards:
   - Hardware-tier recommendations ("Apply Recommended Config" button)
   - Compression settings card (already a separate component: `CompressionSettings.tsx`)
   - Model test results display
8. **Daemon detection — picker deferral.** Add a daemon-detection check (port probe to
   `http://localhost:8400/health`, polled every ~10s while the Settings page is
   open):
   - **Daemon detected:** Render `AIModelsSettings` in **read-only mode** (all inputs
     disabled, greyed out). Show a banner: "Model config managed by SourcePrep" with a
     **"Manage SourcePrep models"** button that opens `http://localhost:8400` in a new tab.
     The current config is still displayed (read from the shared YAML) so the user can see
     what's configured — they just can't edit it from Halbert.
   - **Daemon not detected:** Render `AIModelsSettings` in normal editable mode. Show a
     subtle status line: "Model config managed here."
   - The detection is client-side polling, not a one-time check — if the daemon starts or
     stops while the Settings page is open, the picker mode switches in real time.

**Pass criteria:**
- Settings page renders `AIModelsSettings` with the current `models.yml` config.
- User can add/edit/delete endpoints **when SourcePrep daemon is not running.**
- User can assign models to slots (small/large/vision) **when SourcePrep daemon is not running.**
- Model test works (clicks "Test" → gets a success/failure result).
- "Apply Recommended Config" still works (either as a Halbert-specific button outside the
  component, or as a custom prop injected into `AIModelsSettings`).
- **When SourcePrep daemon is running:** picker is read-only, "Manage SourcePrep models"
  button links to `http://localhost:8400`, current config is still visible.
- **When daemon transitions from running → stopped:** picker re-enables automatically
  within ~10s.
- No visual regression in the rest of the Settings page.

**Styling note:** `@prep/ui` uses Tailwind with a specific design-token system
(`text-text`, `bg-surface`, `border-border`, etc.). Halbert's frontend also uses Tailwind
but may have different token names. Either:
- (a) Map `@prep/ui`'s tokens to Halbert's tokens in a shared Tailwind config, or
- (b) Accept visual differences and adjust Halbert's tokens to match `@prep/ui`'s
  (since `@prep/ui` is the more mature design system).

This is a Step 2 concern, not a Step 0 blocker — the component rendering unstyled is enough
to validate the package boundary.

---

### Step 3 — Chat path reads the unified config shape

**Goal:** Halbert's chat inference reads config from the new `LLMConfig` schema instead of
the old `orchestrator`/`specialist`/`vision` keys directly.

**Actions:**

1. Update `model/client.py` to read from the `LLMConfig` shape:
   - `orchestrator` → `small_model` (with fallback to `orchestrator` for backward compat)
   - `specialist` → `large_model` (with fallback to `specialist`)
   - `vision` → `vision` (unchanged)
2. Update `context/assembler.py` if it reads model config for context-budget sizing (per
  the LinuxBrain analysis session: Halbert's budget is model-agnostic; this is a chance to
  make it model-aware using the new `model_context_cache` field).
3. Update `dashboard/routes/chat.py` if it reads model config for routing decisions
  (complexity scoring, specialist routing).
4. `models.yml` is the single config store (not a fallback, not a cache — the store).
  The daemon reads/writes it; Halbert's chat path reads/writes it; both use the same
  file lock. The old `orchestrator`/`specialist`/`vision` keys remain as aliases for
  backward compat with any code that hasn't been updated yet.
5. **No migration script.** The first time the new code reads `models.yml`, it normalizes
  the old shape into the new shape in memory. The first time the user saves via the new UI,
  it writes the new shape to disk. Self-healing, zero-downtime.

**Pass criteria:**
- Chat works end-to-end with the new config shape.
- Specialist routing still works (complexity threshold → large_model).
- Vision model still works (if configured).
- A `models.yml` in the old shape still loads correctly (backward compat).
- Saving via the new UI writes the new shape; old code reading old keys still works
  (via aliases).

---

### Step 4 — Remove old endpoints and inline UI (cleanup)

**Goal:** Remove the duplicated code now that the unified picker is working.

**Actions:**

1. Remove the old inline model cards from `Settings.tsx` (already done in Step 2, but
  verify no remnants).
2. Remove or deprecate the old `/api/settings/model*` endpoints in `settings.py`:
   - `GET/POST /model` → replaced by `GET/PUT /api/global/config`
   - `GET /model/status` → replaced by `GET /api/llm/status`
   - `POST /model/apply-recommended` → keep as Halbert-specific (not in SourcePrep's router)
   - `POST /model/install` → keep as Halbert-specific (Ollama pull)
   - `POST /model/test` → replaced by `POST /api/llm/proxy/test`
   - `GET/POST /endpoints` → replaced by `PUT /api/global/config` with `saved_endpoints`
   - `GET /endpoints/{id}/models` → replaced by `POST /api/llm/proxy/models`
   - `POST /endpoints/{id}/test` → replaced by `POST /api/llm/proxy/test`
   - `DELETE /endpoints/{id}` → replaced by `PUT /api/global/config` with updated list
   - `POST /assign/{guide|specialist|vision}` → replaced by `PUT /api/global/config` with
     updated slot config
   - `POST /specialist/test` → replaced by `POST /api/llm/proxy/test-model`
   - `POST /specialist/clear` → replaced by `PUT /api/global/config` with `large_model.enabled = false`
   - Legacy deprecated routes (`/endpoints/use-as-guide`, `/endpoints/use-as-specialist`) → remove
3. Keep `settings.py` for non-model settings (computer name, system scan, compression
  config, etc.). Just remove the model-specific routes.
4. Update `AGENTS.md` / `CLAUDE.md` if they reference the old endpoints.

**Pass criteria:**
- No 404s in the browser console when using the Settings page.
- All model-related operations work through the new endpoints.
- `grep -r "settings/model" halbert_core/` returns only the Halbert-specific routes
  (`apply-recommended`, `install`) that we intentionally kept.

---

### Step 5 — Minimal concurrency guard (cheap, prevents worst UX failure)

**Goal:** Prevent Halbert chat and SourcePrep pipeline from simultaneously slamming the GPU.

**Actions:**

1. Implement a simple advisory lock file (`~/.local/share/halbert/llm.lock` or similar):
   - Before an LLM call, acquire a shared lock.
   - SourcePrep's pipeline (if running) acquires the same lock.
   - If both try to call the same endpoint simultaneously, the second one waits (or fails
     fast with a "GPU busy" message).
2. This is NOT the full AIMD concurrency arbitration from SourcePrep — that's Phase 4.
   This is a 50-line file lock that prevents the worst case.
3. Wire it into `model/client.py`'s call path.

**Pass criteria:**
- When SourcePrep pipeline is running a large batch, Halbert chat either waits or shows
  "LLM busy, retrying..." instead of timing out.
- No deadlock (shared locks, not exclusive; timeout on acquire).

**Why this step exists:** The moment both apps run on the same machine, you'll feel the
contention. This is cheap insurance. Full arbitration (compute nodes, plan tiers, AIMD
backoff) is Phase 4 and doesn't need to block the picker unification.

---

## 5. Deferred work (future phases)

### Phase 3 — Package extraction

Extract the vendored LLM router into a standalone Python package
(`sourceprep-llm-config` or similar) that both Halbert and SourcePrep can depend on.
Extract `@prep/ui`'s LLM components into `@sourceprep/llm-ui`.

This is only worth doing once:
- The vendored router has stabilized in Halbert (no more frequent edits).
- The `ConfigStore` protocol is proven (YAML + SQLite both work).
- We've identified the minimal dependency surface (what the router truly needs vs. what
  it inherited from `prep.server`).

Until then, vendoring is cheaper than maintaining a published package.

### Phase 4 — Concurrency arbitration

Route Halbert's LLM calls through a shared concurrency manager (either the SourcePrep
daemon's `/api/llm/proxy/*` or a standalone lock service). The daemon's compute-node +
plan-tier + AIMD backoff system manages the whole machine's LLM throughput.

This is the "brain" for GPU sharing. It's hard and doesn't need to be solved for the picker
unification. Step 5's advisory lock is the placeholder.

### Phase 5 — Cross-product config discovery (already solved, future polish)

With the single-file architecture (§3.3), config sharing is automatic when both apps are
installed — they read/write the same YAML file. No setting needed. Future polish: a
machine-wide notification when config changes (so an open app refreshes its UI when the
other app writes), via file-watch or a lightweight signal between processes.

### Phase 6 — Multi-client daemon discovery

Daemon advertises itself via mDNS or a well-known port file. Standalone SourcePrep (or any
future client) auto-discovers and connects. The daemon becomes the machine's "AI compute
daemon." This is the far-future vision — not needed for any current use case.

---

## 6. Risks and mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| `@prep/ui` can't be linked into Halbert's frontend build | Medium | High (changes the whole approach) | Step 0 validates this in 30 minutes. Fallback: copy components. |
| `@prep/ui`'s Tailwind tokens don't match Halbert's | High | Medium (visual ugliness) | Map tokens in shared Tailwind config, or adopt `@prep/ui`'s tokens. |
| Vendored router has hidden dependencies on `prep.server`/`prep.core` | High | Medium (stubbing work) | Cut iteratively. List every import; stub or inline. Don't aim for clean extraction in Step 1. |
| Chat path breaks when reading new config shape | Medium | High (chat is the core feature) | Backward-compat aliases in Step 3. Old `models.yml` still loads. Test with old-format file. |
| SourcePrep's UI is too complex for Halbert's audience | Medium | Medium (UX confusion) | Hide advanced slots (embedding, coordinator, code) behind "Advanced" toggle. Show 3 slots by default. |
| Concurrency contention when both apps run | High (once both exist) | Medium (slow responses, timeouts) | Step 5's advisory lock. Full arbitration in Phase 4. |
| Drift between vendored router and SourcePrep upstream | High (over time) | Low (vendored copy works; just misses upstream fixes) | Phase 3 extraction resolves this. Until then, periodic re-vendor. |
| `useLLMConfig` hook assumes SourcePrep's API client shape | Medium | Medium (wiring work) | Write a thin Halbert-specific wrapper or parameterize the hook's API base. |

---

## 7. Verification gates

Each step has pass criteria (above). Additionally, after all steps are complete:

1. **Functional:** Chat works end-to-end. Specialist routing works. Vision works. Model
   test works. Endpoint CRUD works. "Apply Recommended Config" works.
2. **Backward compat:** A `models.yml` in the old shape loads correctly. Old code reading
   old keys (via aliases) still works.
3. **No duplication:** `grep -r "settings/model" halbert_core/` returns only intentionally
   kept routes. No inline model cards in `Settings.tsx`.
4. **UI consistency:** The picker looks like it belongs in Halbert (tokens match, layout
   fits the Settings page).
5. **Concurrency:** Step 5's lock prevents simultaneous GPU slam.

---

## 8. File inventory

### Files to create (Halbert)

- `halbert_core/halbert_core/dashboard/routes/llm.py` — vendored LLM router (from SourcePrep)
- `halbert_core/halbert_core/dashboard/routes/global_config.py` — vendored `/global/config` endpoint
- `halbert_core/halbert_core/config/llm_config_store.py` — `ConfigStore` protocol + YAML backend
- `halbert_core/halbert_core/dashboard/frontend/src/hooks/useSourcePrepDaemon.ts` — daemon detection hook (port probe to `:8400`, polls every ~10s, returns `{ detected: boolean, dashboardUrl: string }`)
- (If `@prep/ui` can't be linked) `halbert_core/halbert_core/dashboard/frontend/src/components/llm/` — copied components

### Files to modify (Halbert)

- `halbert_core/halbert_core/dashboard/app.py` — mount new routers
- `halbert_core/halbert_core/dashboard/frontend/src/pages/Settings.tsx` — replace inline model cards with `AIModelsSettings`
- `halbert_core/halbert_core/dashboard/frontend/package.json` — add `@prep/ui` dependency (or copied-component imports)
- `halbert_core/halbert_core/dashboard/routes/settings.py` — remove model-specific routes (Step 4)
- `halbert_core/halbert_core/model/client.py` — read new config shape (Step 3)
- `halbert_core/halbert_core/context/assembler.py` — optional: model-aware context budget (Step 3)
- `halbert_core/halbert_core/dashboard/routes/chat.py` — optional: read new config for routing (Step 3)
- `config/models.yml` — extended schema (additive, backward-compatible)

### Files to reference (SourcePrep, not modified)

- `packages/ui/src/components/llm/*` — the 11 LLM UI components
- `packages/ui/src/types.ts` — `LLMConfig`, `SavedEndpoint`, etc.
- `src/prep/dashboard/src/hooks/useLLMConfig.ts` — state management hook
- `src/prep/api/routers/llm.py` — the router to vendor
- `src/prep/api/routers/system.py` — `/global/config` endpoint to vendor

---

## 9. Decision log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-08-23 | YAML over SQLite for shared config store | Human-editable, git-diffable, zero migration risk for Halbert, fits the-being.md's provenance philosophy. |
| 2026-08-23 | Vendor first, extract later | Clean package extraction is expensive and risky. Vendoring gets the picker working in days. Extraction (Phase 3) waits until the vendored copy stabilizes. |
| 2026-08-23 | Link `@prep/ui` over copying components | Keeps components in sync with SourcePrep upstream. Copying is the fallback if linking fails (Step 0). |
| 2026-08-23 | 5-slot schema, 3-slot default UI | Schema compatibility with SourcePrep. Halbert's audience sees 3 slots (chat/specialist/vision); advanced slots hidden. |
| 2026-08-23 | Advisory lock for concurrency (Step 5) | Full AIMD arbitration is Phase 4. A file lock is 50 lines and prevents the worst UX failure. |
| 2026-08-23 | No migration script | Self-healing: new code normalizes old shape in memory; first save writes new shape. Zero-downtime. |
| 2026-08-23 | Keep `apply-recommended` and `install` as Halbert-specific routes | These are Halbert features (hardware-tier detection, Ollama pull) not in SourcePrep's router. |
| 2026-08-23 | Single YAML file, no fallback cache | A fallback cache creates silent divergence — user sees stale model list without knowing daemon is down. One file, one source of truth. Both apps read/write the same path. File lock prevents corruption. |
| 2026-08-24 | Halbert picker defers to SourcePrep when daemon detected | Avoids two identical editable pickers competing for the same YAML. When SourcePrep daemon is running, Halbert's picker becomes read-only with a "Manage SourcePrep models" link to the SP dashboard. Halbert's picker re-enables when the daemon goes down. Config still syncs via the shared YAML in both directions. |

---

## 10. Open questions

1. **Should `vision` be a 6th slot in the shared schema, or a Halbert-specific extension?**
   SourcePrep doesn't have a vision slot. Adding it to the shared schema means SourcePrep
   ignores it. Keeping it Halbert-specific means the schema diverges. **Recommendation: add
   it to the shared schema as an optional field. SourcePrep ignores it; Halbert uses it.**

2. **Should Halbert's "Apply Recommended Config" (hardware-tier detection) be ported into
   the shared router?** It's Halbert-specific (torch CUDA/MPS detection), but the logic is
   generic enough to benefit SourcePrep users too. **Recommendation: keep in Halbert for
   now. If SourcePrep wants it later, port it into the shared package.**

3. **How should the `useLLMConfig` hook be parameterized?** It currently assumes
   SourcePrep's API client (`useApiClient` from `@prep/ui`). Halbert has its own API
   client shape. **Recommendation: write a thin Halbert wrapper that adapts Halbert's
   fetch calls to the hook's expected interface. Don't fork the hook.**

4. **Should the compression settings (`CompressionSettings.tsx`) move into the shared
   package?** Compression is Halbert-specific (ported from LinuxBrain Phase 72). SourcePrep
   doesn't have context compression. **Recommendation: keep in Halbert. It's not part of
   the LLM config layer.**

---

## 11. User invisibility — how frictionless is this?

The core requirement: a user can install either product alone and feel zero extra friction.
No dependency prompts, no "please also install X," no confusing second app appearing.

### 11.1 Halbert-only user

1. User installs Halbert (eventually via signed installer / app store / pip).
2. Halbert bundles a minimal SourcePrep daemon (headless, no CLI advertised, no dashboard
   served unless explicitly enabled). The daemon starts automatically as a subprocess or
   in-process thread when Halbert starts.
3. The user sees: a chat interface, a settings page with an AI model picker, and system
   awareness features. None of these are labeled "SourcePrep." They're Halbert features.
4. The model picker is "AI Settings." The code-awareness is "Halbert's knowledge of your
   system." The daemon is invisible plumbing.
5. **Zero friction. Zero mention of SourcePrep** (except the credit line — see §12).

### 11.2 SourcePrep-only user

1. User installs SourcePrep (pip, brew, signed installer, or build from source).
2. SourcePrep daemon runs as it does today. Dashboard at `:8400` or `:5174`.
3. The user sees: a code-awareness dashboard, MCP tools for their AI agent, a model picker.
4. **Zero friction. Zero mention of Halbert.** This is the current state, unchanged.

### 11.3 Both installed

1. Whichever app starts first launches the daemon (acquires a singleton lock via port
   probe on `:8400` + a well-known lock file at `~/.sourceprep/daemon.lock`).
2. The second app detects the running daemon (port probe) and connects to it instead of
   spawning a second one. No user action required. No prompt. It just works.
3. If the first app closes, the daemon may stay alive (if the second app is still connected)
   or shut down gracefully (reference-counted lifecycle, or the second app takes over
   ownership).
4. Both apps share the same LLM config (since they're reading the same YAML file). Config
   is always in sync — there is only one file.
5. **Halbert's model picker is read-only when the SourcePrep daemon is detected.** Instead
   of a duplicate editable picker, Halbert shows the current config with editing disabled
   and a **"Manage SourcePrep models"** button linking to SourcePrep's dashboard
   (`http://localhost:8400`). The user manages models in one place; Halbert reflects
   changes via the shared YAML. If the daemon stops, Halbert's picker re-enables
   automatically. A status indicator reads: "Model config managed by SourcePrep" (daemon
   detected) or "Model config managed here" (daemon not detected).
6. **The user doesn't need to understand this.** They just notice that both apps agree on
   which models are configured. If they only ever use one at a time, they never even notice
   the other exists.

### 11.4 What if the daemon crashes or won't start?

- **Halbert:** Chat still works. Halbert reads `models.yml` directly (the same file the
  daemon reads — not a fallback copy, the actual store). **The model picker re-enables**
  (since the SourcePrep daemon is no longer detected, Halbert takes over as the config
  editor). Code-awareness features (prep_search, trace) are degraded — a non-blocking
  notification suggests restarting. The user never sees a different model list because
  there is only one list.
- **SourcePrep:** MCP tools and dashboard are degraded. The daemon restarts on next app
  launch. Config is preserved in the same YAML file.

The daemon is an enhancement layer for Halbert (code-awareness, concurrency arbitration,
cloud model discovery), not a dependency for chat or model config. Halbert's chat path and
model picker work without it because they read the same single config file.

---

## 12. Branding — "Epistemology powered by SourcePrep"

The user wants Halbert to credit SourcePrep somewhere tasteful. This is both honest
(Halbert's code-awareness IS SourcePrep) and a discovery path for power users.

### 12.1 Placement

- **Settings page footer** — a small, subtle line at the bottom of the Settings page:
  > *Epistemology powered by [SourcePrep](https://sourceprep.io)*

- **About / version info** — if Halbert has an "About" dialog or version info page, the
  same line appears there, possibly with the SourcePrep daemon version number:
  > *Epistemology powered by SourcePrep v0.x.x*

- **Not in the main chat UI.** The chat interface is Halbert's voice. The credit belongs
  in settings/about, not in the conversation.

### 12.2 Discovery path

If a user clicks the SourcePrep link, they land on sourceprep.io and discover it as a
standalone tool for AI coding agents. The positioning writes itself: "Halbert uses
SourcePrep for code awareness. You can also use SourcePrep directly with Claude Code,
Cursor, Windsurf, or any MCP-compatible AI tool."

This is the only place the relationship surfaces for Halbert users. It's a credit line,
not a feature explanation. Users who don't care will ignore it. Users who do care will
click through and understand.

### 12.3 What SourcePrep's UI says about Halbert

**Nothing, by default.** SourcePrep's dashboard doesn't mention Halbert. If both are
installed and sharing a daemon, SourcePrep's dashboard might show a small "Connected
clients: 2" indicator in a status bar (alongside Halbert's connection). This is
informational, not promotional.

---

## 13. Licensing — how this works with SourcePrep Pro

### 13.1 Current SourcePrep pricing (from sourceprep.io/pricing, 2026-08-23)

| Tier | Price | What you get |
|------|-------|-------------|
| **Open Source** | $0 forever | Full product, Apache 2.0, unlimited projects, all capabilities. pip/brew/build from source. |
| **Pro** | $29 one-time | Signed+notarized installers, auto-updates (12mo included, ~$15/yr optional after), email support. "Convenience, not capability" — no feature gates. |
| **Teams** | $9/seat/mo (3-seat min) | Shared always-fresh index, SSO, RBAC, audit logs, priority support. |
| **Enterprise** | $24/seat/mo (15-seat min) | Air-gapped deployment, named contact, monthly office hours. |

**Critical detail:** the pricing page explicitly states *"Paid tiers add convenience —
signed installers, hosted team infrastructure, support — never capabilities."* The
open-source tier is the full product with all features. Pro is about installers and
updates, not feature gates.

Note: `feature_gate.py` in the SourcePrep codebase has a stale docstring ($7/mo, $79
perpetual, 3-project free limit) that doesn't match the current pricing page. The
marketing page is authoritative — open source is unlimited. The gate file should be
updated separately (not our concern here).

### 13.2 What this means for Halbert

**Halbert bundling the SourcePrep daemon is zero-cost and zero-friction:**

- The daemon is Apache 2.0. Halbert can bundle it, vendor it, or depend on it freely.
- The free/open-source tier is the full product. No feature gates on capabilities.
- Halbert needs one "project" (the host OS itself). Even if a project limit existed,
  one project is well within any tier.
- **No "Halbert Pro" license is needed.** Halbert users get the full SourcePrep engine
  for free, bundled inside Halbert.

### 13.3 If a user buys SourcePrep Pro

- Pro buys signed installers and auto-updates for the **SourcePrep app** (standalone).
  It doesn't change what the daemon does — the daemon is already full-featured on free.
- If a user has both Halbert and SourcePrep installed, and buys Pro for SourcePrep,
  they get signed SourcePrep updates. Halbert benefits indirectly (the shared daemon
  is the same binary), but there's no separate "Halbert Pro" transaction.
- **The license is tied to the SourcePrep product, not to the daemon process.** The
  daemon reads `~/.sourceprep/license.json` regardless of which app launched it. A Pro
  license unlocks Pro conveniences (signed updates) for the SourcePrep app; the daemon
  itself runs identically on free or Pro.

### 13.4 Teams / Enterprise

These are about shared infrastructure (SSO, hosted index, audit logs, centralized policy).
They're relevant if a team deploys Halbert across multiple machines and wants shared
config-awareness. For personal use (Halbert's primary audience), they're not needed.

If a team uses Halbert + SourcePrep Teams:
- The shared daemon connects to the team's hosted index infrastructure.
- SSO applies to the SourcePrep dashboard (if exposed).
- Audit logs cover daemon operations (indexing, searches, config changes).
- Halbert's chat path is unaffected — it just talks to the daemon as usual.

### 13.5 The singleton daemon and licensing

The daemon is a single process per machine (singleton lock). Its license tier is
determined by `~/.sourceprep/license.json`, not by which app launched it. So:

- **Halbert only, no license file:** Free tier. Full features. Daemon runs.
- **SourcePrep only, no license file:** Free tier. Full features. Daemon runs.
- **Both installed, no license file:** Free tier. Full features. One daemon, shared.
- **SourcePrep Pro license present:** Daemon reads it. SourcePrep app gets signed updates.
  Halbert benefits from the shared daemon. No extra cost.
- **No license file, both apps trying to start daemon:** Singleton lock prevents two
  daemons. First app wins; second app connects. License is irrelevant to this — it's
  process management, not licensing.

### 13.6 Summary: licensing is a non-issue for this integration

The pricing model makes this simple. The daemon is free and full-featured. Pro is about
installer convenience. Halbert bundles the free daemon. No licensing friction, no
feature gates, no "upgrade to use this." If users want SourcePrep's signed installer and
auto-updates, they buy Pro — and both apps benefit from the shared daemon.

---

*End of document.*
