# LLM Picker Design Review Request

**Date:** 2026-08-26
**Status:** Expanded — design exploration for external review
**Author:** Devin session, to be reviewed by external AI

## Purpose

This document started as a regression fix request for Halbert's LLM model
picker. It has since expanded into a broader design research effort with
three goals:

1. **Fix the immediate regression** in Halbert's picker (vendoring
   SourcePrep's component broke model selection and lost the Vision slot)
2. **Research how other AI tools manage model selection** — not to
   replicate, but to understand the design space and improve on it. Our
   tools are open to any API (BYOK) or local LLM, so we need to be
   cognizant of how others handle this and try to do better.
3. **Design a reusable component** that can be shared across all 4 of our
   forked apps, rather than each maintaining its own divergent picker

The core question for the reviewer is not "how do pickers currently
work" (though that's important context) but **"how SHOULD they work?"**
— what is the right design for an open, BYOK + local LLM model picker
that is simpler and more intuitive than what exists today?

The original regression analysis and slot-mapping investigation are
preserved below. The new research begins at **"UI/UX Research: How Other
Apps Do Model Pickers"**, the design proposal begins at **"Design
Exploration: How the Picker SHOULD Work"**, and the questions for the
reviewer are at the end.

---

## The four apps that need a shared picker

All four are Tauri + React + Python-backend apps forked from the same
lineage. They share ancestry but have diverged significantly in their
model picker implementations.

| App | Path | Purpose | Current picker |
|---|---|---|---|
| **Halbert** | `/Volumes/4TB-BAD/Halbert` | Sysadmin AI assistant | Vendored `@prep/ui` `AIModelsSettings` (1,222 lines, ~70% dead code) |
| **SourcePrep (CoDRAG)** | `/Volumes/4TB-BAD/HumanAI/CoDRAG` | Codebase intelligence | Original `@prep/ui` `AIModelsSettings` in `packages/ui` (the source of truth) |
| **LinuxBrain** | `/Volumes/4TB-BAD/HumanAI/LinuxBrain` | Persona/companion AI | Custom `SettingsTabs.tsx` with `ModelConfig` interface (orchestrator/specialist/vision/parser) — completely different schema from Halbert/SourcePrep |
| **BrightestMinds** | `/Volumes/4TB-BAD/BrightestMinds` | Persona/companion AI (LinuxBrain fork) | Custom `SettingsTabs.tsx` — forked from LinuxBrain, diverged further |

### Schema divergence across apps

| App | Config schema | Slots | Store |
|---|---|---|---|
| Halbert | `llm_config` (unified, YAML) | `small_model`, `large_model`, `code_model`, `vision_model`, `coordinator_model`, `embedding` | `models.yml` |
| SourcePrep | `llm_config` (unified, SQLite settings store) | Same 6 slots | `settings.get("llm_config")` |
| LinuxBrain | `ModelConfig` (custom, JSON via API) | `orchestrator`, `specialist`, `vision`, `parser`, `routing`, `saved_endpoints` | Backend-managed |
| BrightestMinds | `ModelConfig` (forked from LinuxBrain) | Similar but diverged | Backend-managed |

**Key observation:** Halbert and SourcePrep share a schema (6 slots)
but have different stores. LinuxBrain and BrightestMinds share a
*different* schema (orchestrator/specialist/vision/parser) and are
backend-managed. A reusable component must abstract over both schemas.

---

## UI/UX Research: How Other Apps Do Model Pickers

### 1. Ollama app + Claude Desktop (August 2026 — brand new)

**What happened:** Ollama shipped Claude Desktop integration in
v0.33.0 (Aug 21, 2026), with model mapping UI refined in PR #17979
(Aug 25, 2026 — one day before this research).

**How their picker works:**
- The Ollama macOS app has an "Apps" page with a Claude Desktop toggle
- When enabled, it shows a **mapping table**: each Claude model tier
  (Opus 5, Sonnet 5, Sonnet 4.6, Haiku 4.5, Fable 5) maps to an Ollama
  model via a dropdown
- **Account-aware defaults**: signed-out users get Sonnet 5 → Gemma 4;
  Pro users get Opus 5 → GLM 5.2, Sonnet 5 → DeepSeek V4 Flash, etc.
- Same Ollama model can be assigned to multiple Claude tiers
- Unavailable models show status in the picker (signed-out, plan-limited)
- Warns before discarding unapplied mapping changes
- "Start Claude" / "Restart Claude" button applies changes

**Design takeaways:**
- **Tier-to-model mapping** is the core UX pattern: "this role → this
  model" rather than "configure this slot"
- Account/plan-aware defaults reduce cold-start friction
- The mapping is explicit and visible — user sees all assignments at once
- Apply/restart is a deliberate action, not auto-save

**Relevant to us:** Halbert's "Chat Model / Specialist Model / Vision
Model" is the same pattern as Ollama's "Opus → GLM, Sonnet → DeepSeek".
The tier-mapping table is a cleaner mental model than separate cards.

### 2. Open WebUI (model selector)

**How their picker works:**
- **Searchable dropdown** in the chat input (not a settings page)
- Models grouped by **connection type**: Local (Ollama), External (API),
  Direct
- **Filter chips** by tag and connection type
- **Fuzzy search** (Fuse.js) across model names, tags, descriptions
- **Pin models** to keep favorites at top
- **Multi-model selection** for comparative responses
- Admins can pull models directly from the selector
- Each model shows metadata: parameter size, quantization, "Loaded"
  status for Ollama models

**Design takeaways:**
- The picker lives **where you use it** (chat input), not buried in
  settings — but this is for per-message model selection, not role
  assignment
- Filter chips + search is the standard for large model lists
- "Loaded" status indicator is useful for local models (shows what's
  in memory)
- Pinning reduces friction for frequently-used models

**Relevant to us:** Our apps need role-assignment (which model for
which task), not per-message selection. But the filter/search/pin
patterns are reusable for the model dropdowns within each role card.

### 3. Cherry Studio (model selector v2 + provider settings)

**How their picker works:**
- **Two surfaces**: (1) per-message model selector popup, (2) provider
  settings page
- Provider settings: list of 60+ built-in provider templates, each with
  API key, base URL, and model list management
- Model selector v2 (PR #14490): **popover-based** with virtualized
  grouped list, sticky headers, keyboard navigation, search, tag filter
  chips, pin toggle, and a provider-settings shortcut
- **Provider filter chips** in the selector (PR #15232): click a
  provider to toggle its models visible/hidden
- Provider types: OpenAI-compatible, Anthropic-compatible, Gemini,
  Bedrock, Azure, Local inference (Ollama, LM Studio)
- Each model has capability tags: vision, tool-calling, reasoning

**Design takeaways:**
- **Provider-first, model-second** is the dominant pattern for BYOK:
  configure the provider (endpoint + key), then pick models from it
- Capability tags (vision, tools, reasoning) help users pick the right
  model for a role without knowing model specs
- The v2 selector is **popover-based** (not a full page) — lighter
  weight, dismissable, doesn't navigate away
- Provider filter chips solve the "too many models" problem when
  multiple providers are configured

**Relevant to us:** Our `EndpointManager` is the provider-first layer.
Our `ModelCard` is the role-assignment layer. Cherry Studio's pattern
confirms this separation is correct. The capability-tag idea could help
users pick a vision model (show only vision-capable models in the
vision card dropdown).

### 4. Cursor IDE (BYOK)

**How their picker works:**
- Settings → Models page with provider sections (OpenAI, Anthropic,
  Google, Azure, Bedrock)
- Paste API key → toggle on → models appear in the picker
- **Override OpenAI Base URL** for OpenAI-compatible gateways
  (OpenRouter, custom endpoints)
- Custom model names can be added manually
- Model picker in chat shows available models; "Auto" mode lets Cursor
  choose
- Known bug: custom model names containing built-in model names get
  incorrectly rejected

**Design takeaways:**
- **Per-provider key fields** with toggle — simple, no nested config
- Base URL override is a power-user feature, not the default path
- "Auto" mode (let the app choose) reduces decision fatigue
- The model picker is separate from provider config — configure once,
  pick per-session

**Relevant to us:** The "Auto" concept is interesting — Halbert could
offer "Auto" for the specialist slot (auto-route based on complexity)
which it already does via `_score_query_complexity()`. The per-provider
key + toggle pattern is what our `EndpointManager` already does.

### 5. GitHub Copilot app (BYOK)

**How their picker works:**
- Onboarding: if no Copilot plan, choose "set up your own model
  provider"
- Settings → Model providers → Add provider → select from presets →
  enter details (display name, base URL, API key)
- Provider's models appear in the model picker alongside
  GitHub-hosted models
- **Credentials stored in system credential store** (not displayed in
  UI, not sent to server storage)

**Design takeaways:**
- **Onboarding-aware**: BYOK setup is offered during first-run, not
  hidden in settings
- System credential store for API keys (security best practice)
- Provider presets reduce configuration friction
- BYOK and hosted models coexist in the same picker

**Relevant to us:** The onboarding-aware BYOK is a good pattern for
Halbert's first-run experience. Credential store usage is a security
improvement over storing API keys in `models.yml` (currently plaintext).

### 6. LM Studio

**How their picker works:**
- Desktop app with model discovery, download, and loading
- Models grouped by: loaded (in memory), downloaded (load on first ask)
- `/api/v1/models` returns both LLMs and embedding models with
  capabilities (vision, tool_use, reasoning)
- Model variants (quantization levels) shown as sub-entries
- JIT loading: downloaded models load on first request

**Design takeaways:**
- **Loaded vs downloaded** distinction is useful for local model
  management
- Capability metadata (vision, tools, reasoning) comes from the model
  itself, not hardcoded
- JIT loading reduces memory pressure

**Relevant to us:** The loaded/downloaded distinction could surface in
our model dropdowns for Ollama endpoints (show which models are
currently loaded in memory). Capability metadata from `/api/show` is
already partially fetched in our `llm.py` proxy.

### 7. Msty Studio (Model Hub + Model Squad + Purpose Tags)

**How their picker works:**
Msty has the most sophisticated model management UX found in this
research. Three distinct concepts:

- **Model Hub** — central place to connect providers, install local
  models, compare options, tune parameters. Has a Model Matchmaker
  (guided recommendations), Cost Calculator, VRAM Calculator, and
  Context Explorer.
- **Model Squad** — assign preferred models to specific *internal
  tasks*: title generation, context summaries, RTD synthesis, persona
  memory extraction. These are background system tasks, separate from
  the user's conversation model. Falls back to conversation model if
  no Squad assignment exists.
- **Purpose Tags** — every model is tagged with capabilities: Text,
  Coding, Tools, Image, Vision, Embedding, Streaming, Thinking. These
  tags drive model filtering in selectors and feature availability
  (e.g., image attachments require a Vision-tagged model).

**Design takeaways:**
- **Model Squad is the exact pattern we need.** Our apps don't do
  per-conversation model selection — they assign models to *roles*
  (chat, specialist, vision, parser, embedding). Msty's "Model Squad"
  is the same concept: "which model handles this system task?"
- **Purpose tags solve the capability-filtering problem.** Instead of
  the user knowing that `kimi-k3` supports vision, the system tags it
  and the vision role card only shows vision-tagged models.
- **Hardware-fit indicators** ("Fits", "May be slow", "Won't fit") are
  crucial for local model selection — Jan has this too.
- **Model Matchmaker** (guided recommendations) reduces cold-start
  friction for users who don't know which model to pick.
- **VRAM Calculator** — estimates whether a local model fits your
  hardware before you download it.

**Relevant to us:** Model Squad is the conceptual model for our
role-assignment picker. Purpose tags are the capability filter layer.
The VRAM/hardware-fit indicators are a natural extension of Halbert's
existing `hardware/budget` endpoint (already in LinuxBrain's
`HardwareContextCard`).

### 8. AnythingLLM (Model Router)

**How their picker works:**
AnythingLLM introduced a **user-defined model router** (v1.13.0) that
goes beyond static role assignment:

- **Calculated rules**: match on keywords, token count, message count,
  time of day, image attachment — fast, free, no LLM call
- **LLM-classified rules**: plain-English description of when a rule
  should match; the fallback model evaluates each incoming message
- **Sticky routing**: keeps you on the same model during a conversation
  thread (configurable cache cooldown)
- **Fallback model**: used when no rule matches AND to evaluate
  LLM-classified rules
- Rules are evaluated top-to-bottom by priority; first match wins
- Drag-to-reorder rule priority

**Design takeaways:**
- **Rule-based routing is more powerful than static role assignment.**
  Our apps currently do static assignment ("specialist = model X").
  AnythingLLM lets you say "if the message contains 'debug' or has
  >500 tokens, use the specialist; otherwise use the chat model."
- **Calculated rules are free** (no LLM call) — keyword matching, token
  count, image attachment. This is a superset of Halbert's existing
  `_score_query_complexity()`.
- **Sticky routing prevents model-bouncing** within a conversation —
  important for context coherence.
- **LLM-classified rules** add intent understanding without requiring
  the user to enumerate every keyword.

**Relevant to us:** Halbert already has complexity-based routing
(`_score_query_complexity()` routes to specialist when complexity >
0.5). AnythingLLM's rule system is a generalization of this. We could
offer an optional "routing rules" panel that lets power users define
custom routing beyond the default complexity score. This is a Phase 3+
feature, not a blocker for the picker redesign.

### 9. LibreChat (Model Specs)

**How their picker works:**
- **Model Specs**: predefined model configurations that simplify the
  UI. Instead of showing all endpoints + all models, you show curated
  specs (e.g., "GPT-4o (fast)" or "Claude Opus (thinking)")
- Each spec has: label, description, endpoint, model, preset settings
- `enforce: true` mode hides the raw endpoint/model dropdowns entirely
  — users only see the curated specs
- `addedEndpoints` lets specific endpoints remain selectable alongside
  specs
- API keys are managed separately (Settings → Data controls → API keys)

**Design takeaways:**
- **Curated specs > raw model lists for most users.** A user shouldn't
  need to know that `deepseek-v4-flash:cloud` is the fast model — they
  should see "Fast Model" and pick it.
- **Enforce mode** is interesting for managed deployments — hide raw
  config, show only approved presets.
- **Separating key management from model selection** reduces cognitive
  load — configure your keys once, then just pick models.

**Relevant to us:** Our `ModelCard` already does this implicitly (the
card has a label like "Chat Model" and the user picks the model within
it). LibreChat's insight is that the *spec* (label + description +
preset) should be the primary unit, not the raw model name. Our
`SlotConfig` type in the reusable component strategy already captures
this.

### 10. Jan (hardware-fit + model hub)

**How their picker works:**
- **Model Hub** with curated catalog, filterable by capability (text,
  vision, code), size, provider
- **Hardware-fit pills**: "Fits", "May be slow", "Won't fit" — based
  on your system's RAM/VRAM, computed locally (no data sent)
- **Quantization tiers** grouped as Small, Balanced, Large with
  "Recommended" tag on the default
- **Gear icon** next to selected model opens model parameters (context
  size, GPU layers, temperature, etc.)
- **Capability toggles**: Vision, Tools, Embeddings, Reasoning — user
  can enable/disable per model
- **JIT loading**: downloaded models load on first request

**Design takeaways:**
- **Hardware-fit is essential for local model UX.** Users need to know
  if a model will work on their machine before they commit to it.
- **Quantization grouping** (Small/Balanced/Large) simplifies the
  choice — most users don't care about Q4_K_M vs Q5_K_S.
- **Capability toggles** let users override system-detected capabilities
  — useful when the system gets it wrong or a model has unofficial
  capabilities.
- **Parameters accessible via gear icon** — keeps the main picker clean
  while power-user settings are one click away.

**Relevant to us:** Halbert's `HardwareContextCard` (in LinuxBrain)
already queries `/api/hardware/budget` for GPU + context budgets. This
concept should be integrated into the model dropdown — show hardware-fit
next to each model option.

---

## Design Exploration: How the Picker SHOULD Work

This is the core question for the reviewer. The research above shows
how pickers *currently* work across the industry. Here we propose how
ours *should* work, informed by that research but not bound by it.

### The fundamental insight: role-assignment, not model-selection

Our apps are not chat apps where the user picks a model per
conversation. They are **agent systems** where models are assigned to
**functional roles** within the agent's architecture. This is closer to
Msty's "Model Squad" than to Open WebUI's per-message selector.

The user's mental model should be:

> "I'm configuring my AI assistant's brain. It needs a conversation
> model, a reasoning model, and a vision model. Let me assign each."

Not:

> "I'm picking which LLM to talk to."

This means the picker is a **settings page**, not a **chat input
dropdown**. The primary unit is the **role** (with a label,
description, and capability requirements), not the **model** (with a
raw model name).

### Proposed UX: The Role-Assignment Picker

#### Layout: Single page, top-to-bottom

```
┌─────────────────────────────────────────────────────────┐
│  AI Models                                               │
│  Configure the models that power your AI assistant       │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  Endpoints                                               │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────────┐    │
│  │ Ollama Local│ │ OpenRouter  │ │ + Add Endpoint  │    │
│  │ localhost   │ │ openrouter… │ │                 │    │
│  │ ● Connected │ │ ● Connected │ │                 │    │
│  └─────────────┘ └─────────────┘ └─────────────────┘    │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  Chat Model                                    [Test]    │
│  The primary model you interact with. Used for every    │
│  conversation, RAG query, and discovery scan.           │
│                                                         │
│  Endpoint: [Ollama Local      ▾]                       │
│  Model:    [deepseek-v4-flash ▾]  ● Connected           │
│            284B MoE · 256k ctx · tools · thinking       │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  Specialist Model (Optional)                  [Test]    │
│  A larger model for complex diagnostics. Routed         │
│  automatically when query complexity is high.           │
│  Falls back to Chat Model if not configured.            │
│                                                         │
│  Endpoint: [OpenRouter       ▾]                        │
│  Model:    [deepseek-v4-pro  ▾]  ● Connected           │
│            Frontier MoE · 3 reasoning modes             │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  Vision Model (Optional)                      [Test]    │
│  Multimodal model for screenshot interpretation.        │
│  Falls back to Chat Model if not configured.            │
│                                                         │
│  Endpoint: [OpenRouter       ▾]                        │
│  Model:    [kimi-k3:cloud    ▾]  ● Connected           │
│            Vision · tools · thinking                    │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  Advanced                                               │
│  Max thinking budget: [24576] tokens                    │
│  ☐ Cloud token safety enforcement                       │
└─────────────────────────────────────────────────────────┘
```

#### Key UX principles

**1. Endpoints first, roles second.**
The user configures their endpoints (providers) once at the top. Then
each role card picks from those endpoints. This follows the
provider-first pattern from Cherry Studio, Cursor, and GitHub Copilot.
Endpoints show connection status so the user knows what's available
before assigning models.

**2. Role cards are the primary unit, not model dropdowns.**
Each card has a clear label ("Chat Model"), a description in plain
English, and an optional/required indicator. The user understands
what *role* they're filling, not just what model they're picking.

**3. Capability metadata shown inline.**
Under each model dropdown, show what the model can do: parameter size,
context window, capabilities (tools, thinking, vision). This comes
from Ollama `/api/show` or provider model metadata. The user doesn't
need to know the model spec — the system surfaces it.

**4. Capability-aware filtering.**
The Vision Model card should only show vision-capable models in its
dropdown. The Chat Model card shows all models. This follows Msty's
purpose-tag pattern and reduces user error.

**5. Hardware-fit indicators for local models.**
When an Ollama endpoint is selected, show hardware-fit next to each
model: "Fits (16GB VRAM)", "May be slow", "Won't fit (needs 32GB)".
This follows Jan's pattern and Halbert's existing `hardware/budget`
endpoint.

**6. Test button per role.**
Each role card has a test button that sends a probe to the configured
endpoint+model and reports success/failure. This already exists in our
`ModelCard` — keep it.

**7. "Optional" + "Falls back to" messaging.**
Specialist and Vision cards are clearly marked optional with fallback
behavior stated. This reduces anxiety about leaving them unconfigured.

**8. No mode toggle, no compute nodes, no pipeline activity.**
These are SourcePrep-specific features that don't belong in a general-
purpose picker. They can be added as opt-in extensions by apps that
need them.

#### The model dropdown: searchable, not flat

When an endpoint has 50+ models (Ollama cloud, OpenRouter), a flat
`<select>` is unusable. The dropdown should be a **popover with
search** (following Cherry Studio v2 and Open WebUI):

```
┌────────────────────────────────────┐
│ 🔍 Search models...                │
│────────────────────────────────────│
│ Filter: [All] [Vision] [Tools] ... │
│────────────────────────────────────│
│ ★ deepseek-v4-flash    284B · 256k │  ← pinned
│   deepseek-v4-pro      Frontier    │
│   gemma-4              27B · 128k  │
│   kimi-k3:cloud        Vision · T  │
│   kimi-k2.7-code:cloud Code        │
│   qwen3.5              72B · 128k  │
│   ...                              │
└────────────────────────────────────┘
```

Features:
- **Search** — fuzzy match on model name
- **Filter chips** — capability filters (Vision, Tools, Thinking, Code)
- **Pin** — star icon to pin favorites to top
- **Metadata inline** — parameter size, context window, capabilities
- **Hardware-fit** — for local models, fit indicator
- **Loaded indicator** — for Ollama, show if model is in memory

#### Onboarding: first-run model setup

Following GitHub Copilot's pattern, the first-run experience should
include model configuration:

```
┌─────────────────────────────────────────────────────────┐
│  Welcome to Halbert                                     │
│                                                         │
│  To get started, connect a model provider:              │
│                                                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │
│  │ Ollama      │  │ OpenAI      │  │ Other       │     │
│  │ (Local)     │  │ (Cloud)     │  │ (BYOK)      │     │
│  │ Free · Fast │  │ $0.01/1k    │  │ Any API     │     │
│  └─────────────┘  └─────────────┘  └─────────────┘     │
│                                                         │
│  Or skip and configure later in Settings.               │
└─────────────────────────────────────────────────────────┘
```

If the user picks Ollama, auto-detect local Ollama instance and
suggest a default chat model. If cloud, ask for API key and fetch
model list. This eliminates the "No model configured" error that
currently surprises new users.

#### Optional: Routing rules (power-user feature)

Following AnythingLLM's pattern, offer an optional "Routing Rules"
panel for power users who want more control than static role
assignment:

```
┌─────────────────────────────────────────────────────────┐
│  Routing Rules (Optional)                    [Enable]   │
│                                                         │
│  When enabled, messages are routed to models based on   │
│  rules instead of static role assignment.               │
│                                                         │
│  Rule 1: If message contains "debug" or "error"         │
│          → Use Specialist Model                         │
│  Rule 2: If image attached                             │
│          → Use Vision Model                             │
│  Rule 3: If token count > 2000                         │
│          → Use Specialist Model                         │
│  Default: → Use Chat Model                              │
│                                                         │
│  [+ Add Rule]                                           │
└─────────────────────────────────────────────────────────┘
```

This is a Phase 3+ feature. The default experience is static role
assignment (which is what we have today, just with better UX). Routing
rules are an opt-in power-user feature that builds on Halbert's
existing `_score_query_complexity()` infrastructure.

### Design principles summary

1. **Role-assignment, not model-selection** — the user fills roles,
   not picks models
2. **Provider-first, model-second** — configure endpoints once, pick
   models from them
3. **Capability-aware** — filter models by what they can do, not by
   name
4. **Hardware-aware** — show fit indicators for local models
5. **Progressive disclosure** — simple by default, powerful when
   needed (routing rules, advanced settings)
6. **Onboarding-aware** — first-run surfaces model config, not hidden
   in settings
7. **Schema-agnostic** — the reusable component works across all 4
   apps with different slot definitions
8. **No dead UI** — every visible element maps to a runtime consumer

---

## Synthesis: Design Patterns for a Reusable LLM Picker

From the research, the dominant patterns are:

### Pattern 1: Provider-first, model-second
Every app separates "configure your endpoint/provider" from "pick a
model for this role." Our `EndpointManager` + `ModelCard` split already
follows this. **Keep it.**

### Pattern 2: Role-tier mapping (Ollama/Claude pattern)
Instead of abstract slot names ("small_model", "large_model"), show
**named roles** with a model dropdown each. Ollama's "Opus 5 → GLM
5.2" is the same UX as Halbert's "Chat Model → deepseek-v4-flash." The
role names should be **app-specific** (Halbert: Chat/Specialist/Vision;
SourcePrep: Fast/Thinking/Code/Coordinator; LinuxBrain:
Orchestrator/Specialist/Vision/Parser).

### Pattern 3: Capability tags
Models should be tagged with capabilities (vision, tools, reasoning,
embedding). The vision role card should filter to vision-capable
models. The code role should filter to code-tuned models. This reduces
user error (picking a text-only model for screenshots).

### Pattern 4: Searchable, filterable model dropdowns
When an endpoint has 50+ models (Ollama cloud, OpenRouter), a flat
dropdown is unusable. Cherry Studio and Open WebUI both use search +
filter chips. Our `ModelCard` currently has a flat dropdown — this
needs upgrading for large model lists.

### Pattern 5: Status indicators
- Connection status (connected/disconnected/not-configured)
- Model loaded in memory (for local Ollama)
- Test result (pass/fail from probe)
Our `ModelCard` already has status indicators. **Keep and refine.**

### Pattern 6: Onboarding-aware BYOK
First-run should offer "connect your model provider" before requiring
configuration. GitHub Copilot does this well. Currently Halbert's
first-run doesn't surface model config — the user discovers it's
missing when chat fails with "No model configured."

---

## Reusable Component Strategy

### The problem

We have 4 apps with 3 different picker implementations:

1. **SourcePrep** has the canonical `@prep/ui` package with
   `AIModelsSettings`, `ModelCard`, `EndpointManager`, etc. — the most
   mature, but tightly coupled to SourcePrep's pipeline vocabulary
2. **Halbert** vendored a copy of `@prep/ui` components — diverged,
   ~70% dead code, wrong vocabulary
3. **LinuxBrain + BrightestMinds** have a completely custom
   `SettingsTabs.tsx` with a different schema (orchestrator/specialist/
   vision/parser) and different UI patterns

### The opportunity

`@prep/ui` already exists as an npm package in the CoDRAG monorepo.
The primitives (`ModelCard`, `EndpointManager`, `AdvancedLLMSettings`)
are reusable. What's not reusable is the **composition layer**
(`AIModelsSettings`) which bakes in SourcePrep's pipeline vocabulary
and features (mapped mode, compute nodes, swarm coordinator, pipeline
activity).

### Proposed architecture: `@prep/ui` v2 — slot-driven composition

**Layer 1: Primitives (already exist, refine for reuse)**
- `ModelCard` — endpoint dropdown + model dropdown + test button +
  status indicator. **Add:** searchable model dropdown, capability
  filter chips, loaded-in-memory indicator
- `EndpointManager` — provider CRUD (add/edit/delete/test endpoints).
  **Already reusable.**
- `AdvancedLLMSettings` — max thinking budget, cloud safety. **Already
  reusable.**

**Layer 2: Slot configuration (new, schema-agnostic)**
A `SlotConfig` type that abstracts over both schemas:

```typescript
interface SlotConfig {
  id: string           // 'chat' | 'specialist' | 'vision' | 'fast' | 'thinking' | ...
  label: string        // App-specific: "Chat Model" or "Fast Model"
  description: string  // App-specific help text
  icon?: ReactNode     // App-specific icon
  required: boolean    // true for primary/chat, false for optional
  endpointId?: string
  model?: string
  enabled: boolean
  alwaysOn?: boolean
  // Capability filter: only show models matching these tags
  requiredCapabilities?: ('vision' | 'tools' | 'reasoning' | 'embedding')[]
}
```

**Layer 3: App-specific composition (new, one per app)**
Each app renders its own set of `ModelCard`s with its own labels:

```tsx
// Halbert
<LLMSettings
  slots={[
    { id: 'chat', label: 'Chat Model', description: '...', required: true },
    { id: 'specialist', label: 'Specialist Model', description: '...', required: false },
    { id: 'vision', label: 'Vision Model', description: '...', required: false, requiredCapabilities: ['vision'] },
  ]}
  config={llmConfig}
  onConfigChange={...}
  endpoints={...}
  ...
/>

// SourcePrep
<LLMSettings
  slots={[
    { id: 'small', label: 'Fast Model', description: '...', required: true },
    { id: 'large', label: 'Thinking Model', description: '...', required: false },
    { id: 'code', label: 'Code Model', description: '...', required: false, requiredCapabilities: ['tools'] },
    { id: 'coordinator', label: 'Swarm Coordinator', description: '...', required: false },
    { id: 'embedding', label: 'Embedding Model', description: '...', required: true, requiredCapabilities: ['embedding'] },
  ]}
  ...
/>

// LinuxBrain
<LLMSettings
  slots={[
    { id: 'orchestrator', label: 'Orchestrator', description: '...', required: true },
    { id: 'specialist', label: 'Specialist', description: '...', required: false },
    { id: 'vision', label: 'Vision', description: '...', required: false, requiredCapabilities: ['vision'] },
    { id: 'parser', label: 'Parser', description: '...', required: false },
  ]}
  ...
/>
```

The `LLMSettings` component:
- Renders one `ModelCard` per slot
- Maps slot IDs to the app's config schema (via a `slotMapper` prop or
  adapter)
- Renders `EndpointManager` below the slots
- Renders `AdvancedLLMSettings` if any app needs it
- Does NOT render: mode toggle, compute nodes, pipeline activity,
  assignment blocks, slot guide (those are SourcePrep-specific and stay
  in SourcePrep's own wrapper)

**Layer 4: Schema adapter (new, one per app)**
Each app has a thin adapter that translates between `SlotConfig[]` and
its native config shape:

```typescript
// Halbert adapter
function halbertAdapter(config: LLMConfig): SlotConfig[] {
  return [
    { id: 'chat', ..., endpointId: config.small_model.endpoint_id, model: config.small_model.model, ... },
    { id: 'specialist', ..., endpointId: config.large_model.endpoint_id, model: config.large_model.model, ... },
    { id: 'vision', ..., endpointId: config.vision_model?.endpoint_id, model: config.vision_model?.model, ... },
  ]
}
```

This keeps the component schema-agnostic while each app owns its
config mapping.

### Migration path

1. **Build `LLMSettings` in `@prep/ui`** (the slot-driven composition
   component). It replaces `AIModelsSettings` as the recommended entry
   point for new consumers.
2. **Halbert adopts `LLMSettings`** first (smallest scope, fixes the
   regression). Delete the vendored `AIModelsSettings` copy. Add a
   Halbert schema adapter.
3. **SourcePrep migrates** `AIModelsSettings` to use `LLMSettings`
   internally (keeping its own slots + the SourcePrep-specific features
   like mode toggle and compute nodes as opt-in props or wrapper
   components).
4. **LinuxBrain + BrightestMinds** adopt `@prep/ui` and `LLMSettings`
   with their own schema adapter, replacing their custom
   `SettingsTabs.tsx` model section.

### What stays app-specific

- Config storage (YAML vs SQLite vs backend API)
- Slot definitions (which roles exist, what they're called)
- Backend model resolution (`get_configured_model()` etc.)
- SourcePrep-only features (mapped mode, compute nodes, pipeline
  activity, concurrency reset)

### What becomes shared

- `ModelCard` (with upgraded searchable dropdown + capability filters)
- `EndpointManager` (already shared via `@prep/ui`)
- `AdvancedLLMSettings` (already shared)
- `LLMSettings` (new slot-driven composition)
- Type definitions (`SavedEndpoint`, `EndpointTestResult`, etc.)

---

## Implementation Strategy (revised)

### Phase 1: Fix Halbert's regression (immediate, no shared package)

**Goal:** Replace the dead-code-heavy vendored picker with a clean
3-card picker. No new dependencies, no shared package yet.

1. Create `HalbertLLMSettings.tsx` in Halbert's frontend (~250 lines):
   - 3 `ModelCard`s (Chat / Specialist / Vision) with Halbert labels
   - `EndpointManager` (reuse vendored copy)
   - `AdvancedLLMSettings` (reuse vendored copy)
   - Daemon banner (informational only, reworded — see below)
   - No mode toggle, no compute nodes, no pipeline activity, no slot
     guide, no deferral checkbox

2. Revert the `vision_model` ModelCard from `AIModelsSettings.tsx`
   (remove the vision card + handlers we added — they pollute the
   SourcePrep-derived component)

3. Replace `UnifiedLLMSettings.tsx` to render `HalbertLLMSettings`
   instead of `AIModelsSettings`

4. Keep `vision_model` in: `types/llm.ts`, `useLLMConfig.ts`,
   `llm.py` default config, `model/client.py` (all still needed)

**Banner rewording** (the current banner falsely claims "shared with
SourcePrep via the same config"):
> SourcePrep daemon is running on port 8400. SourcePrep has its own
> separate model settings for its pipeline. [Open SourcePrep dashboard ↗]

**Files touched:** 3 frontend files (1 new, 1 replaced, 1 reverted)
**Risk:** Low — UI-only, no backend changes

### Phase 2: Build `LLMSettings` in `@prep/ui` (shared component)

**Goal:** Create the slot-driven composition component that will
replace both Halbert's `HalbertLLMSettings` and eventually SourcePrep's
`AIModelsSettings`.

1. Define `SlotConfig` type in `@prep/ui/types`
2. Build `LLMSettings` component in `@prep/ui/components/llm/`:
   - Accepts `slots: SlotConfig[]`, `endpoints`, `onConfigChange`
   - Renders `ModelCard` per slot
   - Renders `EndpointManager` + optional `AdvancedLLMSettings`
   - No app-specific features (no mode toggle, no compute nodes)
3. Upgrade `ModelCard` with:
   - **Searchable model dropdown** (for endpoints with 50+ models)
   - **Capability filter chips** (vision, tools, reasoning — filters
     the model list when `requiredCapabilities` is set on the slot)
   - **Loaded-in-memory indicator** for Ollama models (query `/api/ps`)
4. Add Storybook stories for `LLMSettings` with different slot configs
   (Halbert 3-slot, SourcePrep 5-slot, LinuxBrain 4-slot)

**Files touched:** `@prep/ui` package (CoDRAG monorepo)
**Risk:** Medium — new component, but doesn't change existing apps yet

### Phase 3: Halbert adopts `@prep/ui` `LLMSettings`

**Goal:** Replace Halbert's Phase 1 `HalbertLLMSettings` with the
shared `LLMSettings` from `@prep/ui`.

1. Add `@prep/ui` as a dependency in Halbert's frontend `package.json`
   (either npm link, local path, or published package)
2. Write Halbert schema adapter (`halbertSlots(config): SlotConfig[]`)
3. Replace `HalbertLLMSettings` with `<LLMSettings slots={halbertSlots(config)} ... />`
4. Remove vendored `AIModelsSettings.tsx`, `ModelCard.tsx`,
   `EndpointManager.tsx` from Halbert (now imported from `@prep/ui`)
5. Verify TypeScript compiles, all 3 slots work, endpoints CRUD works

**Files touched:** Halbert frontend `package.json`, 1 new adapter, ~5
deleted vendored files
**Risk:** Medium — dependency wiring, but behavior unchanged

### Phase 4: SourcePrep migrates `AIModelsSettings` to `LLMSettings`

**Goal:** SourcePrep's `AIModelsSettings` becomes a thin wrapper around
`LLMSettings` that adds SourcePrep-specific features.

1. Refactor `AIModelsSettings` to render `LLMSettings` for the slot
   cards, then add SourcePrep-specific sections (mode toggle, compute
   nodes, pipeline activity) as siblings
2. SourcePrep's slot config includes all 5 slots + embedding
3. Verify SourcePrep dashboard still works end-to-end

**Files touched:** `@prep/ui` `AIModelsSettings.tsx`
**Risk:** Medium — SourcePrep is the most complex consumer

### Phase 5: LinuxBrain + BrightestMinds adopt `@prep/ui`

**Goal:** Replace the custom model section in `SettingsTabs.tsx` with
`LLMSettings`.

1. Add `@prep/ui` dependency to both apps
2. Write schema adapters for the `orchestrator/specialist/vision/parser`
   schema
3. Replace the model section of `SettingsTabs.tsx` with `<LLMSettings>`
4. Both apps get the upgraded ModelCard (searchable dropdown,
   capability filters) for free

**Files touched:** LinuxBrain + BrightestMinds frontend
**Risk:** Medium — different schema, different backend, but the adapter
pattern handles this

---

## Original Regression Analysis (preserved for context)

### Background: The three codebases

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

### The regression

#### What existed before

Halbert's Settings page had an "AI Models" tab with three model picker
cards, each with an endpoint dropdown and model dropdown:

1. **Chat Model** (orchestrator) — the primary model the user talks to
2. **Specialist Model** — a larger model for complex reasoning, routed
   by a complexity score
3. **Vision Model** — for screenshot interpretation

Plus a "Saved Endpoints" card where users could add/edit/delete LLM
endpoints (Ollama, OpenAI, Anthropic, etc.) with API keys and connection
testing.

#### What happened

Commit `bff3ce5` vendored SourcePrep's `@prep/ui` LLM picker components
into Halbert's frontend. Commit `01633fe` rendered the vendored
`AIModelsSettings` component in the Settings page, wrapped in a new
`UnifiedLLMSettings` component. Commit `83b9f7f` then deleted the old
3-target picker (Chat/Specialist/Vision cards) and the old backend
endpoints, declaring them "superseded."

#### What broke

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

#### What we've done so far (partial, needs rework)

We made `UnifiedLLMSettings` always show the picker (non-blocking
banner instead of hiding it), and added a `vision_model` slot to the
vendored `AIModelsSettings` component. This compiles and passes tests,
but we now believe this approach is wrong — see "Why the current
approach is wrong" below.

### The slot mapping problem

#### SourcePrep's LLM slots

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

#### Halbert's runtime model consumers

Halbert's `model/client.py` exposes four functions. We traced every
call site:

| Function | Slot read | Call sites | Purpose |
|---|---|---|---|
| `get_configured_model()` | `small_model` (falls back to legacy `orchestrator` key) | 17 in `agent.py`, 8 in `discovery.py`, 4 in `rag/*`, 2 in `settings.py`, 1 in `gpu.py`, 1 in `agents/llm_client.py`, 1 in `app_seam.py` | **The primary chat model.** Every user message, every RAG query, every discovery scan, every cognitive tick. The workhorse. |
| `get_specialist_model()` | `large_model` (falls back to legacy `specialist` key) | 5 in `agent.py`, 1 in `settings.py`, 1 in `discovery.py` | Complex reasoning, routed by `score_query_complexity()` when complexity > 0.5 |
| `get_vision_model()` | `vision_model` (falls back to legacy `vision` key) | 2 in `agent.py` | Screenshot interpretation only |
| `get_ollama_endpoint()` | `small_model` endpoint (falls back to `orchestrator` endpoint) | 10+ call sites | Resolves the endpoint URL for the orchestrator |

#### The mismatch

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

#### The one slot where deferral makes sense

`large_model` is the one slot where both systems want the same thing: a
big, capable reasoning model. SourcePrep uses it for deep enrichment and
thinking stages. Halbert uses it for complex diagnostics. Deferring
Halbert's specialist to SourcePrep's `large_model` is semantically
correct.

#### Summary of overlap

| Halbert role | Halbert reads | SourcePrep's use | Deferral makes sense? |
|---|---|---|---|
| Orchestrator (chat) | `small_model` | Catalogue summarization | **No** — different purposes, same slot name |
| Specialist (reasoning) | `large_model` | Deep enrichment, thinking | **Yes** — both want a big reasoning model |
| Vision | `vision_model` | Doesn't exist | **No** — Halbert-only |
| (not used by Halbert) | — | `code_model` | N/A — SourcePrep-only |
| (not used by Halbert) | — | `coordinator_model` | N/A — SourcePrep-only |
| (not used by Halbert) | — | `embedding` | N/A — SourcePrep-only |

### Why the current approach is wrong

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

This is why the slot-driven `LLMSettings` component (Phase 2 above) is
the right long-term solution: it lets each app define its own slots
with its own vocabulary while sharing the underlying primitives.

### Additional findings from code verification

1. **The embedding card is dead UI in Halbert.** Halbert's RAG uses a
   hardcoded `all-MiniLM-L6-v2` via `sentence-transformers`
   (`rag/embeddings.py:22-23`), completely ignoring
   `llm_config.embedding`. The embedding ModelCard lets users pick an
   embedding endpoint/model that nothing reads.

2. **The config stores are separate, not shared.** The
   `UnifiedLLMSettings` banner says "Halbert's model settings below are
   shared with SourcePrep via the same config" — this is factually
   wrong. Halbert writes to `models.yml` via `get_config_dir() /
   "models.yml"`. SourcePrep reads from
   `prep.services.settings_store.settings.get("llm_config")`. They use
   the same JSON shape but different stores.

3. **The Structured/Assigned mode toggle is dead UI.** Halbert's
   `useLLMConfig` explicitly documents: "No assignment blocks / mapped
   mode (Halbert uses structured mode only)." The toggle renders,
   `handleModeSwitch` is a near-no-op, and the entire mapped-mode branch
   is dead code.

4. **The "Slot Guide" info card describes SourcePrep's pipeline.** It
   references "Swarm Coordinator", "LOD extracts", and "Compression" —
   none of which exist in Halbert's runtime.

---

## Open questions for the reviewer

These questions are the core of what we want challenged. They are
ordered from most fundamental (design philosophy) to most tactical
(implementation detail). We want the reviewer to push back on any
assumptions that feel wrong.

### Design philosophy questions

1. **Is role-assignment the right mental model for our users?**
   We propose that the picker is a settings page where users assign
   models to functional roles (Chat, Specialist, Vision), not a
   per-conversation model selector. This follows Msty's "Model Squad"
   pattern. But our apps are interactive AI assistants — should the
   user be able to override the chat model mid-conversation? Is there
   a hybrid: role-assignment as the default, with a per-conversation
   override for power users? What's the right balance between "set it
   once and forget" and "pick per message"?

2. **How many roles should we expose by default?**
   Halbert has 3 (Chat/Specialist/Vision). SourcePrep has 5
   (Fast/Thinking/Code/Coordinator/Embedding). LinuxBrain has 4
   (Orchestrator/Specialist/Vision/Parser). Msty's Model Squad has ~5
   internal tasks. Is there a "right" number? Should we show all roles
   by default, or progressive-disclosure (show Chat + Vision, hide
   Specialist/Code/Coordinator under "Advanced")? The risk of too many
   roles is decision fatigue; the risk of too few is hidden capability.

3. **Should "Specialist" be an explicit role or a routing behavior?**
   Currently Halbert routes to the specialist model when
   `_score_query_complexity()` > 0.5. The user doesn't see this
   routing — it's invisible. AnythingLLM's Model Router makes routing
   explicit and user-configurable. Should we:
   - (a) Keep specialist as an invisible auto-route (current behavior)
   - (b) Make it a visible "Routing Rules" panel (AnythingLLM pattern)
   - (c) Make it a per-conversation toggle ("Use specialist for this
     message")
   - (d) Some combination
   The tradeoff is transparency vs. simplicity. Most users don't want
   to configure routing rules; power users do.

4. **Should the picker be schema-agnostic or schema-opinionated?**
   Our reusable component strategy proposes a `SlotConfig[]` type that
   abstracts over each app's native config schema. But maybe the
   *schema itself* should be unified — all 4 apps adopt the same slot
   names (`chat`, `specialist`, `vision`, `code`, `coordinator`,
   `embedding`) and the component is opinionated about which exist.
   This would simplify the component but require LinuxBrain to migrate
   from `orchestrator/specialist/vision/parser` to the unified schema.
   Is unification worth the migration cost, or is the adapter pattern
   good enough?

5. **Should we separate "model registry" from "role assignment"?**
   Msty separates Model Hub (where models live) from Model Squad (where
   models are assigned to tasks). Currently our apps conflate these:
   the endpoint+model is configured *inside* the role card. Should we
   split this into two steps: (1) register your models (connect
   endpoints, browse/fetch models, tag capabilities), then (2) assign
   models to roles? This would let users build a "model library" once
   and assign from it across all roles. The tradeoff is more setup
   steps upfront vs. cleaner long-term UX.

### Capability & metadata questions

6. **How do we handle capability metadata?** The vision card should
   only show vision-capable models. Options: (a) fetch from Ollama
   `/api/show` (already partially done), (b) maintain a capability
   database, (c) let the user tag models manually (Msty/Jan pattern),
   (d) filter by model name patterns (e.g. `llava`, `qwen-vl`,
   `kimi-k3`), (e) some combination. Msty and Jan both let users
   override system-detected capabilities — is that worth the
   complexity?

7. **Should we show hardware-fit indicators?** Jan shows "Fits / May
   be slow / Won't fit" based on RAM/VRAM. Halbert's LinuxBrain fork
   already has a `HardwareContextCard` that queries
   `/api/hardware/budget`. Should this be integrated into the model
   dropdown (show fit next to each model option)? Or is it a separate
   concern that belongs in a "System" tab? For cloud models, fit is
   irrelevant — does showing it only for local models create
   inconsistency?

8. **Should we show cost estimates for cloud models?** Msty has a Cost
   Calculator. OpenRouter returns cost-per-token in its model metadata.
   Should the model dropdown show "$0.01/1k tokens" for cloud models?
   This helps users understand the cost implications of assigning an
   expensive model to the chat role (which runs on every message).

### UX & interaction questions

9. **Should the model dropdown be a popover or a select?** Cherry
   Studio v2 uses a popover with virtualized list + search + filter
   chips. Our current `ModelCard` uses a flat `<select>`. For endpoints
   with 50+ models (Ollama cloud, OpenRouter), the popover is clearly
   better. But it's more code. Is this a Phase 2 or Phase 3 concern?
   Should we ship the simple `<select>` first and upgrade later, or
   build the popover from the start?

10. **Should we add an "Auto" option to role dropdowns?** Cursor has
    "Auto" (let the app choose the model). For the specialist role,
    "Auto" could mean "use the chat model unless complexity is high,
    then use the specialist." For the vision role, "Auto" could mean
    "use the chat model if it has vision capability, otherwise use the
    configured vision model." Does this reduce decision fatigue, or
    add confusion by making "Auto" a pseudo-model?

11. **How do we handle onboarding-aware BYOK?** GitHub Copilot offers
    "set up your own model provider" during first-run. Currently
    Halbert's first-run doesn't surface model config — the user
    discovers it's missing when chat fails with "No model configured."
    Should the reusable component include an onboarding variant? Or
    should onboarding be a separate flow that writes the same config?
    What's the minimum viable first-run: just ask for an Ollama URL,
    or walk through endpoint + model + role assignment?

12. **Should configuration be auto-save or explicit apply?** Ollama's
    Claude Desktop mapping requires a "Restart Claude" action to apply
    changes. Our current `useLLMConfig` auto-saves on every change.
    Auto-save is lower friction but means partial/broken configs are
    persisted. Explicit apply is safer but adds a step. Which is right
    for our users? Should it be configurable?

### Implementation & architecture questions

13. **Is the slot-driven `LLMSettings` component the right
    abstraction?** We propose a single component that takes
    `SlotConfig[]` and renders one `ModelCard` per slot. Each app
    defines its own slots. Is this the right granularity, or should we
    go finer (composable card-by-card) or coarser (full-page presets
    like LibreChat's Model Specs)?

14. **Should `@prep/ui` be the shared package, or should we create a
    new package?** `@prep/ui` is currently inside the CoDRAG monorepo.
    Halbert and LinuxBrain would need to depend on it. Options: (a)
    publish to npm, (b) git submodule, (c) local path dependency, (d)
    extract to a new standalone repo/package. The choice affects
    versioning, CI, and how changes propagate across apps.

15. **What about the legacy `orchestrator`/`specialist`/`vision` keys?**
    `model/client.py` falls back to the old top-level keys in
    `models.yml` when the unified `llm_config` slots aren't set.
    Should we keep this fallback for backward compatibility, or remove
    it and require the unified schema? Keeping it means two code paths
    forever; removing it means existing users' configs break on
    upgrade.

16. **Should API keys move to the system credential store?** GitHub
    Copilot stores BYOK keys in the OS credential store, not in config
    files. Currently Halbert stores API keys in plaintext in
    `models.yml`. This is a security improvement but adds platform
    complexity (Tauri has a keychain plugin). Is this worth doing as
    part of the picker redesign, or is it a separate security
    initiative?

17. **Should the embedding model be in the picker or separate?**
    Halbert's RAG uses a hardcoded `all-MiniLM-L6-v2` via
    `sentence-transformers`, ignoring `llm_config.embedding`. The
    embedding ModelCard in the current picker is dead UI. Should we:
    (a) remove the embedding card entirely (it's not wired), (b) wire
    it up so RAG reads from the config, (c) move embedding config to a
    separate "RAG Settings" section since it's a different concern
    (vector embeddings, not LLM inference). SourcePrep needs the
    embedding card; Halbert and LinuxBrain may not.

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
  — vendored model picker card (reusable, needs upgrade)
- `halbert_core/halbert_core/dashboard/frontend/src/hooks/useLLMConfig.ts`
  — Halbert's LLM config hook (endpoint CRUD, model fetch/test, autosave)
- `halbert_core/halbert_core/dashboard/frontend/src/hooks/useSourcePrepDaemon.ts`
  — daemon health probe
- `halbert_core/halbert_core/dashboard/frontend/src/types/llm.ts` —
  shared type definitions
- `halbert_core/halbert_core/dashboard/frontend/src/pages/Settings.tsx`
  — Settings page that mounts `UnifiedLLMSettings` in the AI Models tab
- `halbert_core/halbert_core/rag/embeddings.py` — hardcoded embedding
  model (ignores `llm_config.embedding`)

### SourcePrep (`/Volumes/4TB-BAD/HumanAI/CoDRAG`)

- `src/prep/services/pipeline/stages.py:266` — `STAGE_MODEL_SLOT` mapping
  (which slot each pipeline stage uses)
- `src/prep/services/config_manager.py:320-373` — default `llm_config`
  schema with all 5 slots
- `packages/ui/src/components/llm/AIModelsSettings.tsx` — the original
  SourcePrep component (Halbert vendored a copy)
- `packages/ui/src/components/llm/` — the `@prep/ui` LLM component
  directory (ModelCard, EndpointManager, etc.)
- `packages/ui/package.json` — `@prep/ui` package definition
- `src/prep/dashboard/src/hooks/useLLMConfig.ts` — SourcePrep's LLM
  config hook (Halbert adapted a copy)

### LinuxBrain (`/Volumes/4TB-BAD/HumanAI/LinuxBrain`)

- `halley_core/frontend/src/components/SettingsTabs.tsx` — custom
  settings with `ModelConfig` interface (orchestrator/specialist/vision/
  parser) — completely different schema from Halbert/SourcePrep
- `halley_core/frontend/src/components/image-settings/ModelSelector.tsx`
  — image generation model selector (separate from LLM picker)
- `halley_core/frontend/src/stores/chatStore.ts` — chat store (no model
  config — handled in SettingsTabs)

### BrightestMinds (`/Volumes/4TB-BAD/BrightestMinds`)

- `brightestminds_core/frontend/src/components/SettingsTabs.tsx` —
  forked from LinuxBrain, diverged further (different imports, different
  tab structure)

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

### Research sources

**Model picker UX (existing apps):**
- Ollama PR #17979 (Aug 25, 2026): Claude Desktop model mappings —
  https://github.com/ollama/ollama/pull/17979
- Ollama PR #17915 (Aug 21, 2026): Claude model management —
  https://github.com/ollama/ollama/pull/17915
- The New Stack: Claude Desktop + Ollama integration —
  https://thenewstack.io/ollama-claude-desktop-integration/
- Open WebUI ModelSelector (Svelte) —
  https://github.com/open-webui/open-webui/blob/main/src/lib/components/chat/ModelSelector.svelte
- Cherry Studio PR #14490: Model selector v2 —
  https://github.com/CherryHQ/cherry-studio/pull/14490
- Cherry Studio PR #16858: Provider settings redesign —
  https://github.com/CherryHQ/cherry-studio/pull/16858
- Cherry Studio issue #15232: Provider filter in model selector —
  https://github.com/CherryHQ/cherry-studio/issues/15232
- GitHub Copilot BYOK docs —
  https://docs.github.com/en/copilot/how-tos/github-copilot-app/use-byok-models
- Cursor BYOK docs — https://cursor.com/help/models-and-usage/api-keys
- LM Studio REST API (model capabilities) —
  https://lmstudio.ai/docs/developer/rest/list
- local-llm-ui (model selector with backend filter chips) —
  https://github.com/praveenc/local-llm-ui
- LocalMode Model Selector docs —
  https://localmode.ai/docs/local-first/model-selector

**Model squad / role-assignment pattern:**
- Msty Studio: Model Hub + Model Squad —
  https://docs.msty.ai/studio/managing-models
- Msty Studio: Model Squad (DeepWiki) —
  https://deepwiki.com/cloudstack-llc/msty-studio-docs/4.5-model-squad
- Msty Studio: Model Purposes & Tags —
  https://deepwiki.com/cloudstack-llc/msty-studio-docs/4.3-model-purposes-and-tags
- Msty Studio: Local Models (Ollama/MLX/Llama.cpp) —
  https://docs.msty.ai/studio/managing-models/local-models
- Msty (original): Model Selector docs —
  https://docs.msty.app/features/model-selector

**Model routing (dynamic):**
- AnythingLLM: Model Router overview —
  https://docs.anythingllm.com/model-router/overview
- AnythingLLM: Model Router setup (rules) —
  https://docs.anythingllm.com/model-router/setup
- AnythingLLM v1.13.0 release (hybrid AI) —
  https://github.com/Mintplex-Labs/anything-llm/releases/tag/v1.13.0
- AnythingLLM Model Router (DeepWiki) —
  https://deepwiki.com/Mintplex-Labs/anything-llm/5.4-model-router

**Model specs / curated presets:**
- LibreChat: Model Specs object structure —
  https://www.librechat.ai/docs/configuration/librechat_yaml/object_structure/model_specs
- LibreChat: Custom endpoint configuration —
  https://www.librechat.ai/docs/configuration/librechat_yaml/object_structure/custom_endpoint
- LibreChat: Custom endpoints guide —
  https://www.librechat.ai/docs/quick_start/custom_endpoints

**Hardware-fit & local model management:**
- Jan: Model Settings (parameters, GPU layers) —
  https://github.com/janhq/jan/blob/dev/docs/src/pages/docs/desktop/model-parameters.mdx
- Jan: Managing Models (hub, import, capabilities) —
  https://github.com/janhq/jan/blob/dev/docs/src/pages/docs/desktop/manage-models.mdx
- Jan: Settings (downloaded models, provider settings) —
  https://janhq-jan-19.mintlify.app/desktop/settings
- Jan: Running Local LLMs (hardware fit) —
  https://mintlify.wiki/janhq/jan/features/local-models

**Model routing architecture (research/theory):**
- Zylos Research: AI Agent Model Routing strategies —
  https://zylos.ai/research/2026-03-02-ai-agent-model-routing/
- Agent Patterns Catalog: Complexity-Based Routing —
  https://www.agentpatternscatalog.org/patterns/complexity-based-routing/
- Ginger Labs: Signal-Driven Routing for Mixture-of-Models —
  https://gingerlabs.ai/blog/signal-driven-mixture-of-models
- CallSphere: Multi-Model Agent Architectures —
  https://callsphere.ai/blog/multi-model-agent-architectures-different-llms-reasoning-steps.md
- aiarch.dev: Role-Based Model Routing —
  https://aiarch.dev/patterns/model-router
