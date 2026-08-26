# Triage Response: Scrutiny & Reverse-Engineering Audit

**Date:** 2026-08-26
**Status:** Verified and triaged — ready for engineering and design tracks
**Author:** Devin session
**Input:** `documentation/design/SCRUTINY-AND-REVERSE-ENGINEERING-MODEL-PICKER-2026-08-26.md`
**Related:** `documentation/design/UI-SPEC-REUSABLE-MODEL-PICKER-2026-08-26.md`, `.handoff/LLM-PICKER-DESIGN-REVIEW-2026-08-26.md`

---

## 1. Verification Results

All four claimed vulnerabilities were verified against the actual
codebase. Every claim is accurate, with one nuance noted below.

### Vuln 1&6: BYOK Authentication Blindspot — CONFIRMED

**Verified code:**
- `_resolve_endpoint()` (`model/client.py:169-184`) returns
  `Tuple[str, str]` (url, provider). `api_key` is discarded.
- `call_llm_chat()` (`model/client.py:324-333`) has no `api_key`
  parameter.
- `_do_llm_call()` (`model/client.py:455-480`):
  - OpenAI branch: `requests.post(url, json=payload, timeout=timeout)`
    — no `headers` parameter, no `Authorization: Bearer`.
  - Anthropic falls into the `else` branch and hits
    `{endpoint}/api/chat` (Ollama format) — would 404 on
    `api.anthropic.com`.
- A working `AnthropicClient` exists in `agents/llm_client.py:264-347`
  with proper `x-api-key` headers and correct `/v1/messages` endpoint —
  but `LLMClientAdapter.chat()` doesn't use it. It calls
  `call_llm_chat()` directly.
- The "Test" button in the UI uses a different code path (`routes/llm.py`
  proxy) which DOES send auth headers — creating the "green in settings,
  fails in chat" experience described in the scrutiny document.

**User decision:** This is a known limitation. Halbert was always
intended to be local-Ollama-first. BYOK wiring is something the user
wants to do once, as part of the unified UI framework. **Fix as part of
the picker redesign, not as a separate hotfix.**

### Vuln 2: In-Chat Runtime Disconnect — CONFIRMED

**Verified code:**
- `SendMessageRequest` (`routes/agent.py:37-47`) has no `model` or
  `tier` field.
- `useAgentStream.ts:586-591` sends `{ message, session_id,
  max_tokens, temperature }` — no model or tier.
- This is missing infrastructure needed to support the in-chat model
  pill, not a regression.

### Vuln 3: Multi-Turn Memory Illusion — CONFIRMED with nuance

**Verified code:**
- `agent.process()` is called at `routes/agent.py:686-690` without
  `conversation_history`.
- `state_machine.py:190-224` DOES accept `conversation_history` and
  stores it in `self.ctx`. It's even used in context assembly
  (line 634). The state machine is ready — the route just doesn't load
  it.
- Both LLM call sites use `messages=[{"role": "user", "content":
  prompt}]` — single message, no multi-turn history. Verified at
  `state_machine.py:659-663` (planning) and `state_machine.py:1276-1280`
  (response generation).
- A conversation store EXISTS (`conversation_sqlite.py`,
  `conversation.py`) with list/get/delete API endpoints — but
  `send_message()` never loads from it.

**Nuance:** The scrutiny document says "completely stateless between
turns." This is slightly overstated — the infrastructure exists
(conversation store, state machine parameter, context assembly
integration), it's just not wired together end-to-end. The end-user
effect is the same: no multi-turn memory.

### Vuln 4: Auto-Routing vs. User Override — CONFIRMED in principle

**Verified code:**
- `LLMClientAdapter.chat()` (`routes/agent.py:325-347`) auto-routes to
  specialist when `complexity_score >= 0.5`.
- Currently moot (no in-chat model selection exists), but becomes a
  real problem once the in-chat pill is implemented.
- The UI spec's Auto Mode vs. Locked Mode is the correct fix.

---

## 2. User Decisions on Open Questions

### Package strategy

**Decision:** Not `@prep/ui`, not `packages/design-system` as a
design-system-imposing package. The shared component should be a
**lightweight, style-agnostic utility** that provides structural and
behavioral logic (model discovery, endpoint management, role
assignment, capability filtering) while letting each app style it with
their own design tokens.

The component should pull in styles for a few form elements (dropdowns,
buttons, cards) but not impose a full design system. Apps that already
have their own design systems (Halbert's `packages/design-system`,
LinuxBrain's styles, SourcePrep's `@prep/ui` tokens) should be able to
wrap the shared component with their own styling.

**Implication:** The shared package should export unstyled or
minimally-styled components with clear className/style prop seams, not
opinionated CSS. Think "headless UI" pattern (like Radix UI or downshift)
rather than "component library" (like MUI or Ant Design).

### BYOK priority

**Decision:** Known limitation. Fix as part of the picker redesign.
The user wants to wire up all endpoints once, through the unified UI
framework, rather than patching the broken path incrementally.

### Scope: dual-surface design

**Decision:** Commit to the full dual-surface design (in-chat pill +
settings drawer). The user also wants to build a **tiered config
system** inspired by Claude Code's config file and the
`claude-ollama` CLI command — meaning model configuration should be
expressible as a tiered config (global defaults → project overrides →
session overrides), not just a flat settings file.

---

## 3. Engineering Track (blocking)

These are backend fixes that must be completed before or alongside the
picker UI. They are verified bugs / missing infrastructure, not design
questions.

### E-1: Fix BYOK auth in `model/client.py`

**Files:** `halbert_core/halbert_core/model/client.py`

1. `_resolve_endpoint()` must return `Tuple[str, str, Optional[str]]`
   (url, provider, api_key)
2. `call_llm_chat()` must accept `api_key: Optional[str] = None` and
   forward it to `_do_llm_call()`
3. `_do_llm_call()` must accept `api_key: Optional[str] = None`:
   - For `provider in ("openai", "openai-compatible")`: add
     `headers["Authorization"] = f"Bearer {api_key}"` when api_key is
     present
   - For `provider == "anthropic"`: route through `AnthropicClient`
     (already exists in `agents/llm_client.py:264`) instead of raw
     `requests.post`
4. `LLMClientAdapter.chat()` must pass `api_key` through to
   `call_llm_chat()` — this means `get_configured_model()` and
   `get_specialist_model()` must also return the api_key from the
   resolved endpoint

### E-2: Add model/tier override to the agent request path

**Files:** `halbert_core/halbert_core/dashboard/routes/agent.py`,
`halbert_core/halbert_core/dashboard/frontend/src/hooks/useAgentStream.ts`

1. Add `model: Optional[str]` and `tier: Optional[str]` to
   `SendMessageRequest`
2. In `send_message()`, pass `model_override` and `tier_override` to
   `agent.process()` (or to the LLMClientAdapter)
3. In `LLMClientAdapter.chat()`: if `model_override` is provided,
   bypass the complexity router and use the specified model
4. In `useAgentStream.ts`: forward the currently selected model and
   tier from the in-chat picker in the request body

### E-3: Wire conversation history into the agent loop

**Files:** `halbert_core/halbert_core/dashboard/routes/agent.py`,
`halbert_core/halbert_core/agents/state_machine.py`

1. In `send_message()`: if `request.conversation_id` is provided (or
   derive from `session_id`), load recent turns from the existing
   `conversation_store`
2. Pass `conversation_history=history` to `agent.process()`
3. In `state_machine.py` planning and response states: construct
   `messages` from `self.ctx.conversation_history` + current turn,
   not just `[{"role": "user", "content": prompt}]`
4. After response completes, persist the new turn to the conversation
   store

### E-4: Implement server-side local discovery route

**Files:** `halbert_core/halbert_core/dashboard/routes/llm.py`

1. Add `GET /api/llm/discover` that probes `localhost:11434` (Ollama)
   and `localhost:1234` (LM Studio) with 500ms timeout
2. Returns `{ ollama: { running, version, models }, lm_studio: {
   running, models } }`
3. Runs on the server loopback interface (bypasses browser CORS)
4. Frontend calls this on mount to auto-discover local engines

### E-5: Tiered config system (Claude Code parity)

**Files:** New `halbert_core/halbert_core/model/tiered_config.py`

Inspired by Claude Code's config file and `claude-ollama` CLI:

1. **Global defaults** (`~/.config/halbert/models.yml`) — base config
2. **Project overrides** (`<project>/.halbert/models.yml`) — per-project
   model assignments (e.g., a project that needs a code-specialist model)
3. **Session overrides** (in-memory, set via `/model` command) —
   per-session model pinning

Resolution order: session > project > global > auto-discovered defaults.

This replaces the current flat `models.yml` with a layered system. The
UI reads the merged config but writes to the appropriate layer (settings
drawer writes to global, `/model` command writes to session).

---

## 4. Design Track (Specifications & Review Resolutions)

The UI spec (`UI-SPEC-REUSABLE-MODEL-PICKER-2026-08-26.md`) proposed a
dual-surface design (in-chat pill + settings drawer). The user committed
to this scope. Below are the definitive design resolutions for D-1
through D-6, refined to deliver maximum simplicity, clarity, and
predictability.

### D-1: Shared component architecture (headless pattern)

Per the user's decision, the shared component is a **style-agnostic
utility** (headless UI pattern), not an opinionated design system. Each
host application wraps it with their own styling.

**Package Structure (`packages/model-picker/`):**
```
packages/model-picker/
├── src/
│   ├── types.ts               # AppRoleDefinition, DiscoveredModel, etc.
│   ├── useModelPicker.ts      # Core headless state: selection, discovery, tests
│   ├── useLocalDiscovery.ts   # Port probing via /api/llm/discover
│   ├── primitives/
│   │   ├── ModelSelectorPill.tsx   # Headless combobox trigger & pill
│   │   ├── QuickSwitchPopover.tsx  # Floating searchable menu
│   │   ├── ModelSettingsDrawer.tsx # Role assignment grid + provider manager
│   │   ├── RoleAssignmentRow.tsx   # 1-row mapping: role -> provider -> model
│   │   └── ProviderCard.tsx        # Zero-config local & BYOK key inputs
│   └── index.ts
├── package.json               # peerDeps: react, react-dom (ZERO CSS frameworks)
└── README.md
```

**Integration Pattern:**
The headless primitives render standard semantic HTML elements (`<button>`,
`<input>`, `<select>`) with clean `className` and `style` passthrough,
plus full ARIA accessibility (`role="combobox"`, `aria-expanded`). Host
apps simply provide their own Tailwind tokens or CSS modules:
```tsx
// In Halbert (using Daylight design tokens):
import { ModelSelectorPill as HeadlessPill } from '@halbert/model-picker';
export function HalbertModelPill(props) {
  return (
    <HeadlessPill 
      {...props} 
      className="bg-surface border border-border hover:border-primary/50 text-text rounded-full px-2.5 py-1 text-xs font-mono" 
    />
  );
}
```

### D-2: Auto Mode vs. Locked Mode (Vuln 4 Resolution)

To guarantee predictability and prevent silent cloud token spend:

1. **Failure Behavior When a Pinned Model is Unavailable:**
   * **Graceful fallback with notification:** If a pinned model is offline
     (e.g., local Ollama daemon killed, model not pulled, or cloud API key
     expired), the system **never crashes or fails silently**.
   * **Behavior:**
     1. The engine falls back to the default `chat_model` (Guide) for this
        turn so the user is never stranded.
     2. An inline alert chip renders in the chat stream:
        `⚠️ Pinned model 'qwen2.5-coder:32b' unavailable (Ollama offline). Temporarily using 'qwen2.5-coder:14b'. [Reconnect] [Change Model]`.
     3. The pill indicator shifts to amber warning state:
        `[ ⚠️ Pin: qwen2.5-coder:32b (Offline) ]`.

2. **Per-Session vs. Persistent Pinning:**
   * **In-Chat Selection / `/model` command:** Sets an **in-memory session
     override** (`session.model` / `session.tier`). This affects only the
     current conversation thread.
   * **Settings Drawer:** Sets the **persistent global default**
     (`~/.config/halbert/models.yml`), applied to all future new sessions.

3. **Interaction with Tiered Config (E-5):**
   * Precedence hierarchy:
     `Session Override (/model)` > `Project Override (.halbert/models.yml)` > `Global Default (~/.config/halbert/models.yml)` > `Auto-Discovered Default`.
   * When in **Auto Mode**, the resolution hierarchy resolves both the Guide
     and Specialist models; the complexity router dynamically routes between
     them. When in **Locked Mode**, the pin forces the specified model for
     every turn, completely bypassing the complexity router.

### D-3: Visible Tier Handoff Banner

When the complexity router escalates a turn to the Specialist model:

1. **Dismissible & Subtle:**
   * The banner is a compact, single-line inline divider:
     `🔀 Escalated to Specialist (claude-3-7-sonnet) · [Why?] ▾`
   * It carries a subtle `(x)` dismiss button and auto-fades to 60% opacity
     after the assistant response finishes streaming.
2. **De-escalation (Specialist → Guide):**
   * **Silent by default:** De-escalation back to the Guide model does not
     render a loud banner (avoiding conversational noise). The turn footer
     simply displays `Model: qwen2.5-coder:14b (Guide)`.
3. **Complexity Score Visibility:**
   * By default, shows only human rationale: *"Escalated to Specialist for
     multi-step diagnosis"*.
   * Clicking `[Why?]` (or having Settings > Developer Mode enabled) expands
     the exact routing metrics: *"(Complexity score: 0.78, Threshold: 0.50,
     Intent: MultiStepTroubleshooting)"*.

### D-4: Auto-Inherit Vision from Chat Model

To eliminate confusing redundant slots:

1. **Capability Detection for Cloud & Local Models:**
   * **Local Ollama:** Checked via `/api/show` for `mllama` or `clip`
     families, or parameter definitions.
   * **Cloud BYOK:** Standardized prefix matching against a static capability
     table:
     * Anthropic: `claude-3-*` (all Claude 3, 3.5, 3.7 models support vision).
     * OpenAI: `gpt-4o`, `gpt-4o-mini`, `gpt-4-turbo`, `o1` support vision.
     * Google: `gemini-1.5-*`, `gemini-2.0-*` support vision.
     * Local: names containing `vision`, `vl`, `llava`, `minicpm-v`.
2. **User Override:**
   * The Vision slot in Settings defaults to `[ 🟢 Auto: Inherit from Chat Model (llama3.2-vision) ▾ ]`.
   * The dropdown allows explicit overrides: users can pick a different
     endpoint/model or select `Disabled`.
3. **When Chat Model Loses Vision:**
   * If Vision was set to "Inherit" and the user switches Chat to a
     text-only model (e.g. `deepseek-r1:14b`), the Vision slot shows:
     `[ ⚠️ Chat model lacks vision — Click to assign dedicated Vision model ]`.
   * Dropping an image into chat while text-only chat is active surfaces a
     helpful tip: *"Attached image requires a vision model. Please assign a
     vision model in Settings or switch to a multimodal chat model."*

### D-5: `/model` Slash Command Interaction

For full parity with Claude Code:

1. **Fuzzy vs. Exact Matching:**
   * **Smart Fuzzy Match:** Typing `/model qwen` matches `qwen2.5-coder:14b`;
     `/model sonnet` matches `claude-3-7-sonnet`.
   * **Ambiguity Handling:** If multiple models match (e.g. `/model qwen`
     when both `qwen2.5:7b` and `qwen2.5-coder:14b` are installed), it opens
     the Quick-Switch Popover with the search box pre-filled to `"qwen"`,
     allowing arrow-key selection.
2. **`/model status` Output:**
   * Prints an ephemeral system diagnostic card into the chat stream:
     ```
     ── Active Model Status ────────────────────────────────────
     • Active Turn Model : qwen2.5-coder:14b (Local Ollama)
     • Mode              : Auto (Guide: qwen2.5:14b, Specialist: claude-3-7-sonnet)
     • Context Window    : 32,768 tokens (~4,120 used in session)
     • Hardware Offload  : 100% GPU VRAM (Ollama @ localhost:11434)
     ───────────────────────────────────────────────────────────
     ```
3. **Dedicated Subcommands:**
   * `/model` — Opens the quick-switch popover menu.
   * `/model auto` — Resets session to Auto Mode (Guide + Specialist).
   * `/model pin <name>` or `/model lock <name>` — Locks the session to a specific model.
   * `/model guide <name>` — Overrides Guide model for this session.
   * `/model specialist <name>` — Overrides Specialist model for this session.

### D-6: Two-Tab Settings Drawer vs. Single Unified Surface

**The Ideal Compromise: Single Cohesive Surface with Collapsible Providers Accordion:**
* Having separate tabs for "Roles" and "Endpoints" creates friction when
  adding a new key and immediately assigning it.
* **The Unified Layout:**
  1. **Top Section (Always Visible): Role Assignments**
     * 3 clean, compact rows: `Chat / Guide`, `Specialist`, `Vision`.
     * 1 row = `[Role Name] → [Provider Dropdown] → [Model Dropdown] → [Test Button]`.
  2. **Bottom Section (Collapsible Accordion): Connected Providers & BYOK Keys**
     * Shows auto-discovered local engines (Ollama, LM Studio) with live status.
     * Shows configured cloud cards (Anthropic, OpenAI, OpenRouter).
     * Has `[ + Add Provider / Key ]` button.
  3. **Contextual Action Link:**
     * When a user adds an endpoint in the bottom section, a subtle highlight
       appears above: *"Anthropic endpoint connected! Assign to Specialist?"*
       with a 1-click **[ Assign ]** button.
     * Zero tab switching, zero context loss.

---

## 5. What's NOT being pursued

Based on the user's decisions and the scrutiny feedback:

- **NOT using `@prep/ui` as the shared package** — the shared component
  will be a lightweight headless utility, not coupled to SourcePrep's
  design system
- **NOT fixing BYOK as a separate hotfix** — it will be fixed as part
  of the picker redesign since the picker is what surfaces BYOK
- **NOT shipping settings-only first** — the full dual-surface design
  (in-chat pill + settings drawer) is the committed scope
- **NOT keeping the vendored `AIModelsSettings.tsx`** — it will be
  deleted and replaced with the new shared component

---

## 6. Recommended execution order

1. **E-1 (BYOK auth fix)** — unblocks all cloud model usage
2. **E-3 (conversation history)** — unblocks multi-turn conversations
3. **E-2 (model/tier override)** — unblocks the in-chat pill
4. **D-1 (shared component architecture)** — scaffold the headless
   package
5. **E-4 (local discovery route)** — unblocks auto-discovery
6. **D-2 through D-6** — design review and refinement of UI spec items
7. **E-5 (tiered config)** — implement after the basic picker works
8. **Integration** — wire the shared component into Halbert, then
   SourcePrep, then LinuxBrain, then BrightestMinds

---

## 7. Verification matrix acknowledgment

The scrutiny document's V-01 through V-07 test cases are accepted as
the verification criteria. They should be turned into automated tests
where possible (V-01, V-02, V-07) and manual QA checklists where not
(V-03, V-04, V-05, V-06).

---

## 8. Engineering Handoff Clarifications & Open Alignments

The following technical alignments and trade-offs are documented for
the engineering team as implementation begins:

### Q1: Tiered Config Hierarchy & Project File Location (E-5)
* **Question:** What is the exact path and resolution strategy for
  project-level model configs?
* **Recommendation:**
  * Global: `~/.config/halbert/models.yml` (user-wide defaults)
  * Project: `<project_root>/.halbert/models.yml` (per-repo model pins,
    mirroring `.claude/` or `.cursor/` conventions)
  * Session: In-memory dictionary in `session_manager.py` keyed by
    `session_id` (ephemeral per conversation)
* **Resolution Rule:** Merged on read: session overrides project;
  project overrides global. Writes from the Settings Drawer target
  global; writes from `/model pin` target the active session.

### Q2: Context Window Budgeting & Compaction Strategy
* **Question:** When a conversation with local models (e.g. 32k context)
  approaches capacity (>80% full), how should Halbert handle overflow?
* **Recommendation:**
  * Phase 1: In-chat indicator on `<ContextBar />` turns amber at 80%
    and red at 90%, with an inline action button:
    `[ 🧹 Compact Conversation Memory ]`.
  * Phase 2: Implement `/compact` command that invokes the fast Guide
    model to summarize earlier turns into a compact context block,
    matching Claude Code's memory compression.

### Q3: API Key Security in Single-User vs. Desktop Tauri Builds
* **Question:** Is plaintext storage in `models.yml` with `chmod 0600`
  acceptable for the initial release?
* **Recommendation:** **Yes.** For the CLI and local web daemon
  (`make dev-web`), `models.yml` with restricted POSIX permissions
  (`0600`) is the standard practice for single-user dev tools. In the
  UI, keys are always masked with reveal protection. The Tauri OS
  Keyring plugin is scheduled for the Desktop Packaging milestone,
  abstracted cleanly under the `useModelPicker` hook without altering
  the UI components.

### Q4: Shared Package Directory
* **Question:** Where should the new headless model picker live in the repo?
* **Recommendation:** `packages/model-picker/` (a standalone peer to
  `packages/design-system/`). It has zero CSS dependencies, zero Tailwind
  classes, and exports headless hooks and unstyled Radix-style primitives
  ready to be consumed by Halbert, SourcePrep, LinuxBrain, and BrightestMinds.
