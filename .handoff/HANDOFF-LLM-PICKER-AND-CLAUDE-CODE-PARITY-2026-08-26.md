# Comprehensive Handoff: LLM Picker Redesign, Brand New Ollama/Claude Code Architecture, and Halbert Agent Parity

**Date:** 2026-08-26  
**Status:** Research Complete, Architecture & UI/UX Specifications Approved, Ready for Implementation  
**Audience:** Next engineering / agent session, founders, core contributors  
**Related Documents:**
* `.handoff/LLM-PICKER-DESIGN-REVIEW-2026-08-26.md` (Background on the vendoring regression)
* `documentation/design/model-picker-independent-2026-08-26.md` (Approved independent picker design)
* `.handoff/TERMINAL-AND-ORCHESTRATOR-REVIEW-2026-08-26.md` (Audit of terminal streaming and conversation orchestration)
* `config/prompts/v2/tiers/` (`guide.xml`, `specialist.xml`, `vision.xml`)

---

## Executive Summary

Halbert currently suffers from two interrelated issues:
1. **The Model Picker UI is Clumsy & Over-Engineered**: Halbert previously vendored a 1,223-line component from SourcePrep (`AIModelsSettings.tsx`) designed for batch indexing pipelines (6 slots: `small_model`, `large_model`, `code_model`, `coordinator_model`, `embedding`, etc., plus mapped task blocks and compute node clustering). Halbert only needs 3 conversational roles (`chat_model`, `specialist_model`, `vision_model`). Users are forced through an indirect two-step setup (create endpoint → select slot → wait for dropdown) with zero local auto-discovery and no in-chat model switching.
2. **Halbert Agent UI vs. Claude Code Behavior**: Halbert has built remarkable UI primitives (xterm terminal streaming, accordion dock, task checklists, code diff blocks, tool execution cards, collapsible thinking panels, and confirmation dialogs). However, it lacks mid-session model switching (`/model`), has a backend conversational memory gap (`conversation_history=[]` per turn), lacks interactive terminal input (`stdin`), and lacks context window budget gauges.

This handoff details:
1. The **brand new Ollama + Claude Code integration features** announced recently (Ollama's native Anthropic Messages API support, the desktop GUI "Apps" toggle, `ollama launch claude` interactive TUI, `/model` in-session switching, and tiered model mapping).
2. **Competitive analysis** of how leading agentic tools (Cursor, Cline/Roo Code, Continue.dev, Zed, Open WebUI, Aider) handle local models and BYOK.
3. A **deep audit** of Halbert's agent UI against Claude Code capabilities.
4. An **architectural blueprint** for a universal, reusable local + BYOK model picker package (`packages/design-system`) that can serve Halbert, SourcePrep, and any future application cleanly.

---

## Part 1: Fresh Research on Ollama & Claude Code Integration

### 1.1 Native Anthropic Messages API Compatibility in Ollama (v0.14.0+)
Ollama introduced native wire-compatibility with the Anthropic Messages API (`/v1/messages`). Previously, running Claude-compatible tools against local models required LiteLLM proxies, OpenRouter proxies, or custom translation middleware. With native support:
* Ollama parses Anthropic-formatted requests directly.
* Ollama emits Anthropic-compliant Server-Sent Events (SSE) streaming chunks, including `message_start`, `content_block_start`, `content_block_delta`, and `message_delta`.
* Ollama translates Anthropic's tool-use definitions (`tool_choice`, `tools: [{name, description, input_schema}]`) into the underlying model's tool calling format (e.g. Qwen2.5 function calling tokens, Hermes format, or Llama 3 format).

### 1.2 The New Ollama Desktop GUI "Apps" Toggle
In the official Ollama desktop application (macOS/Windows):
* A dedicated **Apps** section exists within Ollama Settings.
* Users find a **Claude** toggle switch.
* When switched to **On**, the user selects which local model they wish to bind to Claude.
* A single click on **"Restart Claude"** automatically configures the local runtime and environment for the user, bridging local weights directly to desktop agent tools without manual config hacking.

### 1.3 The Interactive Terminal Picker (`ollama launch claude`)
For command-line terminal agents:
1. **Interactive TUI Selection**: Running `ollama launch claude` automatically probes the local Ollama daemon and displays an interactive terminal menu where the user navigates locally pulled models with the arrow keys.
2. **Direct CLI Flags**: Users can bypass the menu via `ollama launch claude --model <model-name>`.
3. **Mid-Session Switching via `/model`**: Once inside Claude Code, typing `/model` opens the model selection prompt mid-session. Users can switch between a smaller model (for fast file reading) and a larger model (for complex refactors) without killing their session or losing context.
4. **Model Verification via `/status`**: Displays the active model, current context tokens used, and backend endpoint.

### 1.4 The "Tiered Model Set" Mechanics & Session Configurations
Claude Code's internal agent loop does not treat the LLM as a single monolith. Instead, it partitions tasks across **three distinct model tiers**:

| Tier | Role in Claude Code | Typical Local Model Equivalent | Token / Resource Profile |
| :--- | :--- | :--- | :--- |
| **Haiku Tier** | Fast classification, intent routing, terminal output summarization, memory compaction | `qwen2.5:7b`, `gemma2:9b`, `ministral:8b` | Very low latency, small context, cheap |
| **Sonnet Tier** | The primary agent workhorse: file reading, diff generation, tool dispatch, bash orchestration | `qwen2.5-coder:14b` or `32b`, `deepseek-coder` | High tool-calling precision, strong coding ability |
| **Opus Tier** | Architectural synthesis, multi-file refactor planning, ambiguous root-cause reasoning | `qwen2.5-coder:32b`, `deepseek-r1:32b+` | Heavy reasoning, chain-of-thought, highest param size |

#### Why the Session Config / `claude-ollama` Wrapper is Required
When Claude Code connects to an Anthropic endpoint, it makes API calls requesting specific tiers depending on the operation. If pointed at a raw Ollama instance without tier mapping, requests for secondary tiers fail or default unpredictably.

To get the full tiered tooling working with local Ollama, developers use environment variables or a session config wrapper script (such as `claude-ollama`):
```bash
#!/usr/bin/env bash
# claude-ollama: Session configuration wrapper for tiered local execution
export ANTHROPIC_BASE_URL="http://localhost:11434"
export ANTHROPIC_API_KEY="ollama" # placeholder token

# Map Claude Code's internal tiers to specific local models
export ANTHROPIC_DEFAULT_HAIKU_MODEL="qwen2.5:7b"
export ANTHROPIC_DEFAULT_SONNET_MODEL="qwen2.5-coder:14b"
export ANTHROPIC_DEFAULT_OPUS_MODEL="qwen2.5-coder:32b"

# Launch Claude Code
exec claude "$@"
```

#### Hardware & Context Requirements for Agentic Local Models
* **Tool Calling Capability**: Agentic workflows will break if a model fails to emit clean JSON tool calls. Community consensus highlights **Qwen2.5-Coder (14B or 32B)** as the gold standard for local coding agents.
* **Context Window Budget**: Coding agents routinely ingest multiple files and terminal outputs. A 4k or 8k context window results in immediate truncation. Local models must be run with a context window of at least **32k** (or 64k+ if unified memory permits), configured in the Ollama Modelfile via `PARAMETER num_ctx 32768`.

---

## Part 2: Competitive Research on Local Model & BYOK UI/UX Patterns

We analyzed how the top AI development environments and agent interfaces handle local models (Ollama, LM Studio) and BYOK (Bring Your Own Key):

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     COMPETITIVE UI/UX PATTERN MATRIX                        │
├─────────────────┬───────────────────┬──────────────────┬────────────────────┤
│ Application     │ Primary UI Surface│ Local Discovery  │ BYOK Management    │
├─────────────────┼───────────────────┼──────────────────┼────────────────────┤
│ Cursor          │ Composer Toolbar  │ Manual URL field │ API Key inputs     │
│                 │ Pill Selector     │ (override URL)   │ per provider       │
├─────────────────┼───────────────────┼──────────────────┼────────────────────┤
│ Cline/Roo Code  │ Chat Header Badge │ Refresh button   │ Full provider tab, │
│                 │ + Mini Popover    │ hits /api/tags   │ context/temp slider│
├─────────────────┼───────────────────┼──────────────────┼────────────────────┤
│ Continue.dev    │ Status Bar Pill + │ Port Prober      │ Role-based slots   │
│                 │ Onboarding Wizard │ (11434, 1234)    │ (Chat, Edit, Embed)│
├─────────────────┼───────────────────┼──────────────────┼────────────────────┤
│ Zed             │ Assistant Header  │ Auto-detected    │ Minimalist inline  │
│                 │ Dropdown Menu     │ grouped items    │ key prompts        │
├─────────────────┼───────────────────┼──────────────────┼────────────────────┤
│ Open WebUI      │ Top Bar Dropdown  │ Connection test  │ Global admin keys, │
│                 │ with Badges       │ button           │ capability tags    │
├─────────────────┼───────────────────┼──────────────────┼────────────────────┤
│ Aider           │ CLI flags &       │ Base URL flag    │ Env vars + split   │
│                 │ In-Chat /model    │                  │ Architect/Editor   │
└─────────────────┴───────────────────┴──────────────────┴────────────────────┘
```

### Deep Dive into Specific Implementations

#### 1. Cursor
* **UX Placement**: Placed directly inside the prompt composer footer next to the submit button (`[Claude 3.7 Sonnet ▾]`).
* **Interaction**: Clicking the pill opens a quick-pick modal. Users can switch models for the next prompt without navigating to Settings.
* **BYOK**: Settings → Models. Offers standard provider keys (OpenAI, Anthropic, Google) and an "Override OpenAI Base URL" input pointing to local ports (`http://localhost:11434/v1`).

#### 2. Cline / Roo Code (VS Code Extension)
* **UX Placement**: Chat header features an active badge showing `[Ollama] qwen2.5-coder:14b`. Clicking it opens a focused popover.
* **Local Discovery**: When "Ollama" is chosen from the provider dropdown, it provides a **"Refresh Models"** button that immediately hits `http://localhost:11434/api/tags` and populates the model list.
* **Context & Parameters**: Exposes a slider for context window limit (auto-populated by model) and thinking token budget directly in the popover.

#### 3. Continue.dev
* **Zero-Config Port Probing**: On launch or setup, Continue scans standard localhost ports (`11434` for Ollama, `1234` for LM Studio). If detected, it displays a green card: *"Ollama running locally with 6 models found — click to use."*
* **Role-Based Slot Separation**: Recognizes that different tasks need different models:
  * *Chat Model* (interactive assistant)
  * *Autocomplete Model* (fast tab completion, e.g. StarCoder / Qwen-0.5B)
  * *Embeddings Model* (local nomic-embed-text)
  * *Reranker Model*

#### 4. Zed
* **Unified Assistant Header**: The model selector is in the top-right of the Assistant panel.
* **Categorized Dropdown**: Dropdown groups models clearly:
  * *Anthropic* (Claude 3.7 Sonnet, Claude 3.5 Haiku)
  * *OpenAI* (GPT-4o, o3-mini)
  * *Ollama* (Local models listed automatically)
* If an API key is missing for a cloud model, an inline "Add API Key" badge appears next to the provider name.

#### 5. Aider
* **The Architect/Editor Paradigm**: Aider popularized splitting agent work into two models:
  * `--model <reasoning-model>` (Architect: plans the change, produces reasoning)
  * `--editor-model <coding-model>` (Editor: applies diffs accurately)
* **In-Chat Command**: Users switch models dynamically via `/model <name>` or `/architect`.

---

## Part 3: Halbert Agent UI Audit vs. Claude Code Behavior

Halbert is a local-first AI assistant for Linux system administration. We audited its frontend ([`halbert_core/dashboard/frontend/src/components/agent/`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/components/agent/)) against Claude Code's agentic loop.

### 3.1 What Halbert Already Has (Strong Parity)
1. **Interactive Bash & Terminal Pipeline**:
   * [`InlineTerminals.tsx`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/components/agent/InlineTerminals.tsx): Renders xterm.js terminal instances inline inside the assistant's turn.
   * [`TerminalAccordionDock.tsx`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/components/agent/TerminalAccordionDock.tsx): Automatically docks terminal sessions into the right-hand `ContextStage` when scrolled off-screen, with a `TetherChip` jump button.
2. **Structured Plan Tracking**:
   * [`PlanChecklist.tsx`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/components/agent/PlanChecklist.tsx): Parses `<plan>` blocks and renders live task lists (pending, in_progress, completed, failed) matching Claude Code’s task queue.
3. **Tool Call Inspection**:
   * [`ToolExecutionCard.tsx`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/components/agent/ToolExecutionCard.tsx): Displays running tools with duration, parameters, and output foldouts.
4. **Unified Code Diffs**:
   * [`DiffBlock.tsx`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/components/agent/DiffBlock.tsx): Renders green/red syntax-highlighted diffs for file modifications.
5. **Human-in-the-Loop Safety**:
   * [`ConfirmationDialog.tsx`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/components/agent/ConfirmationDialog.tsx): Pauses execution for sensitive system commands, presenting Approve/Reject options.
6. **Thinking & Reasoning Panels**:
   * [`ThinkingPanel.tsx`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/components/agent/ThinkingPanel.tsx): Renders chain-of-thought folding with real-time token streaming.
7. **System Grounding & Provenance**:
   * [`WhyChip.tsx`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/components/WhyChip.tsx): Interactive provenance chips that expand into log inspection modules (`journalctl`, `systemctl`, `hwmon`).
8. **Prompt Tier Specialization**:
   * [`config/prompts/v2/tiers/guide.xml`](file:///Volumes/4TB-BAD/Halbert/config/prompts/v2/tiers/guide.xml): Fast tier, concise 1-3 sentences, 500 token budget, 1 diagnostic command at a time.
   * [`config/prompts/v2/tiers/specialist.xml`](file:///Volumes/4TB-BAD/Halbert/config/prompts/v2/tiers/specialist.xml): Reasoning tier, 4,000 token budget, `<plan>` first, step-by-step troubleshooting.

### 3.2 The 5 Critical Gaps to Achieve Claude Code Parity

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                   THE 5 GAPS TO CLAUDE CODE BEHAVIOR                        │
├───────────────────────┬─────────────────────────────────────────────────────┤
│ 1. In-Chat Switching  │ No model badge, no tier toggle, and no /model       │
│                       │ command in AgentChat. Model selection is buried in  │
│                       │ a 1,200-line settings page.                         │
├───────────────────────┼─────────────────────────────────────────────────────┤
│ 2. Multi-Turn Memory  │ Backend resets conversation_history=[] every turn.  │
│                       │ The agent cannot reference prior tool output or chat│
│                       │ history.                                            │
├───────────────────────┼─────────────────────────────────────────────────────┤
│ 3. PTY Stdin Support  │ Agent commands run via asyncio.create_subprocess_   │
│                       │ shell (pipe mirror). Interactive CLI prompts (y/N,  │
│                       │ passwords) cannot receive user keystrokes.          │
├───────────────────────┼─────────────────────────────────────────────────────┤
│ 4. Context Meter      │ ContextBar shows items and token sums, but lacks a  │
│                       │ visual progress gauge against model max context.    │
├───────────────────────┼─────────────────────────────────────────────────────┤
│ 5. Autonomy Policies  │ Binary per-command confirmation dialog only. Lacks  │
│                       │ "Auto-approve read-only", "Plan mode", or           │
│                       │ "Autonomous" mode toggles.                          │
└───────────────────────┴─────────────────────────────────────────────────────┘
```

---

## Part 4: Root Cause Diagnosis of the Current Model Picker

Halbert's current picker ([`AIModelsSettings.tsx`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/components/llm/AIModelsSettings.tsx)) feels clumsy for four architectural reasons:

1. **Vendoring a Pipeline Indexer into a Conversational Assistant**:
   * SourcePrep is an indexing pipeline: it runs catalogue passes, AST edge extraction, and concept clustering. Its slots are `small_model`, `large_model`, `code_model`, `coordinator_model`, `embedding`.
   * Halbert is an interactive sysadmin assistant: it has a **Guide (Chat)**, a **Specialist (Reasoning)**, and **Vision**.
   * Vendoring `AIModelsSettings.tsx` introduced 1,223 lines of code including Mapped Mode task assignment blocks, Concurrency reset buttons, compute cluster nodes, and Swarm coordinator inheritance that Halbert's runtime never executes.
2. **Two-Step Indirection Barrier**:
   * Users cannot simply choose "Ollama → Qwen2.5-Coder".
   * Instead, they must create a named endpoint in `EndpointManager`, assign it a plan tier, then go to a slot card, pick the endpoint, wait for a network fetch, and pick the model from a dropdown.
3. **Absence of Local Auto-Discovery**:
   * 90% of Halbert users run Ollama locally on `localhost:11434`. Halbert does not probe this port automatically on first start; it requires manual configuration.
4. **Disconnected from the Chat Surface**:
   * The user cannot see what model is currently answering in `AgentChat.tsx` or change it on the fly.

---

## Part 5: Complete Architecture & Design for a Universal Reusable Model Picker

To solve this across Halbert, SourcePrep, and future apps, we design a modular, reusable picker component in [`packages/design-system`](file:///Volumes/4TB-BAD/Halbert/packages/design-system).

### 5.1 Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    REUSABLE MODEL PICKER ARCHITECTURE                       │
│                        (packages/design-system)                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  [Surface 1: In-Chat Quick Switcher]                                        │
│  Mounted in AgentChat header or composer footer                             │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │  [ 🟢 Ollama: qwen2.5-coder:14b ▾ ]   [ ⚡ Fast / Guide Mode ▾ ]       │  │
│  └───────────────────────────────────┬───────────────────────────────────┘  │
│                                      │ Click                                │
│                                      ▼                                      │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │  Quick-Switch Popover                                                 │  │
│  │  🔍 Search models...                                                  │  │
│  │  Local (Ollama):                                                      │  │
│  │    • qwen2.5-coder:14b  [Tools, 32k]  ✓ Active                        │  │
│  │    • deepseek-r1:14b    [Reasoning, 32k]                              │  │
│  │    • llama3.2-vision:11b[Vision, 128k]                                │  │
│  │  Cloud (BYOK):                                                        │  │
│  │    • claude-3-7-sonnet  [Anthropic, 200k]                             │  │
│  │  ───────────────────────────────────────────────────────────────────  │  │
│  │  ⚙️ Manage Endpoints & API Keys...                                    │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│  [Surface 2: Model & Provider Management Modal / Drawer]                    │
│  Mounted via Settings page or popover shortcut                              │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │  Tabs: [ 🎯 Model Roles ]   [ 🔌 Endpoints & BYOK Keys ]              │  │
│  ├───────────────────────────────────────────────────────────────────────┤  │
│  │  Tab 1: App Role Grid (Clean 1-row-per-role)                          │  │
│  │  • Chat Model       : [ Ollama (Local) ▾ ] [ qwen2.5-coder:14b ▾ ] [Test]│
│  │  • Specialist Model : [ Anthropic (BYOK)▾] [ claude-3-7-sonnet  ▾ ] [Test]│
│  │  • Vision Model     : [ Ollama (Local) ▾ ] [ llama3.2-vision:11b▾ ] [Test]│
│  ├───────────────────────────────────────────────────────────────────────┤  │
│  │  Tab 2: Endpoints & BYOK Keys                                         │  │
│  │  🟢 Local Ollama (http://localhost:11434)  [Auto-Detected]            │  │
│  │  ⚪ Local LM Studio (http://localhost:1234) [Offline]                 │  │
│  │  ── Cloud Providers (BYOK) ─────────────────────────────────────────  │  │
│  │  [ Anthropic ]  Key: [ sk-ant-••••••••••••• 👁️ ]   [Save & Verify]     │  │
│  │  [ OpenAI    ]  Key: [ sk-proj-•••••••••••• 👁️ ]   [Save & Verify]     │  │
│  │  [ + Add Custom OpenAI-Compatible / vLLM Endpoint ]                   │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 5.2 Decoupled Data Schema (`models.yml`)
Halbert's model configuration becomes fully independent from SourcePrep:
```yaml
llm_config:
  saved_endpoints:
    - id: ep_local_ollama
      name: Local Ollama
      provider: ollama
      url: http://localhost:11434
      api_key: ""
      is_auto_discovered: true
    - id: ep_byok_anthropic
      name: Anthropic Claude
      provider: anthropic
      url: https://api.anthropic.com
      api_key: "sk-ant-api03-..."
      is_auto_discovered: false

  # The 3 conversational roles Halbert actually consumes:
  chat_model:
    enabled: true
    endpoint_id: ep_local_ollama
    model: "qwen2.5-coder:14b"
  specialist_model:
    enabled: true
    endpoint_id: ep_byok_anthropic
    model: "claude-3-7-sonnet-20250219"
  vision_model:
    enabled: true
    endpoint_id: ep_local_ollama
    model: "llama3.2-vision:11b"
```

### 5.3 Core Component Specifications

#### Component 1: `<ModelSelectorPill />`
* **Props**:
  * `currentModel`: string
  * `currentProvider`: string
  * `currentRole`: `'chat' | 'specialist'`
  * `onSelectModel`: `(model: string, endpointId: string) => void`
  * `onOpenSettings`: `() => void`
* **Behavior**: Renders a compact badge in the chat header or composer footer. Clicking displays the Quick-Switch Popover with fuzzy search, local vs. cloud grouping, and capability chips.

#### Component 2: `useLocalDiscovery()` Hook
* Automatically issues background `fetch` requests with a 1-second timeout:
  * `http://localhost:11434/api/version` (Ollama)
  * `http://localhost:1234/v1/models` (LM Studio)
* If Ollama responds, it calls `/api/tags` and populates the local model cache without user intervention.

#### Component 3: In-Chat `/model` Command Parser
* In [`AgentChat.tsx`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/components/agent/AgentChat.tsx), intercept user input starting with `/`:
  * `/model`: Opens the `<ModelSelectorPill />` popover directly above the composer.
  * `/model <name>`: Fuzzy matches local and BYOK models and switches active model immediately, posting a subtle system notification in chat: *"Active model switched to `qwen2.5-coder:14b`."*
  * `/status`: Displays current model, backend endpoint, and context window metrics.

---

## Part 6: Phased Implementation Roadmap for Halbert

### Phase 1: In-Chat Model Switcher & Slash Commands
* [ ] Add `<ModelSelectorPill />` to [`AgentChat.tsx`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/components/agent/AgentChat.tsx) header.
* [ ] Implement in-chat `/model` and `/status` command interceptors.
* [ ] Surface active tier badge (`⚡ Guide` vs `🧠 Specialist`) based on query complexity routing.

### Phase 2: Independent Settings & Deletion of Vendored Monolith
* [ ] Implement `halbert_core/model/llm_config.py` as the single store module for `models.yml`.
* [ ] Migrate legacy `orchestrator`, `specialist`, `vision` keys to `chat_model`, `specialist_model`, `vision_model`.
* [ ] Build clean, lightweight `ModelSettings.tsx` (1 row per role + Auto-discovery + BYOK cards).
* [ ] Delete `AIModelsSettings.tsx`, `UnifiedLLMSettings.tsx`, and SourcePrep stubs.

### Phase 3: Agent Multi-Turn Continuity & PTY Terminal Input
* [ ] Fix `routes/agent.py` to persist `conversation_history` across turns for the active conversation session.
* [ ] Connect agent tool execution to `streaming/pty.py` WebSocket bridge for interactive terminal stdin (so the user can answer `y/N` or enter sudo passwords).
* [ ] Add visual context window budget gauge to [`ContextBar.tsx`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/components/agent/ContextBar.tsx).

### Phase 4: Shared Package Extraction
* [ ] Move the headless model registry hook and UI components to [`packages/design-system`](file:///Volumes/4TB-BAD/Halbert/packages/design-system).
* [ ] Update SourcePrep to consume the shared package with its pipeline schema (`small_model`, `large_model`, `embedding`), achieving zero duplicated picker code across the two projects.
