# UI/UX Specification: Reusable Local + BYOK Model Picker & Runtime Controls

**Document Version:** 1.0.0  
**Date:** 2026-08-26  
**Status:** Approved Design Specification — For Technical Team Review & Implementation  
**Track:** UI / UX Design & Interaction Architecture  
**Author:** Design & Architecture Workstream  
**Target Codebases:** Halbert (`halbert_core`), SourcePrep (`@prep/ui`), Shared Design System (`packages/design-system`)  
**Directly Resolves / Supersedes:**
* Open questions in `.handoff/LLM-PICKER-DESIGN-REVIEW-2026-08-26.md`
* Findings in `.handoff/HANDOFF-LLM-PICKER-AND-CLAUDE-CODE-PARITY-2026-08-26.md`
* Supersedes `documentation/design/unified-model-picker.md`

---

## 1. Design Mission & The Core Problem

### 1.1 The Fundamental Flaw of Existing Pickers
Most local-first and BYOK AI developer tools (including Halbert’s vendored `AIModelsSettings.tsx`) suffer from a severe mental-model mismatch:
* **The Engineer's Internal Model:** *"I have local Ollama running with Qwen-Coder for fast diagnostic commands, and an Anthropic API key for deep reasoning refactors. I want to talk to my machine, see what model is answering, and easily switch if a task gets complicated."*
* **The Current UI Reality:** A 1,223-line monolithic administrative page buried 3 levels deep in Settings. Users must first understand abstract infrastructure concepts ("Endpoints"), create an endpoint, assign concurrency profiles, scroll past batch-indexing pipeline stages (`small_model`, `large_model`, `coordinator_model`, `code_model`, `embedding`), configure 6 separate cards, wait on loading spinners, and guess whether `:latest` is breaking the dropdown. Worst of all, **inside the chat interface, there is zero indication of what model is answering and zero ability to switch mid-stream.**

### 1.2 The Three Design Pillars
1. **Understandable & Zero-Friction:** If Ollama or LM Studio is running on `localhost`, the user does not configure anything. The app auto-discovers it, selects the best installed model, and presents a ready state.
2. **Intuitive Dual-Surface Interaction:**
   * **Surface 1 (Ambient Runtime):** A compact, responsive pill directly inside the Chat composer/header for 95% of daily usage (switching models, viewing active tier, seeing context limits).
   * **Surface 2 (System Configuration):** A clean, 1-row-per-role setup drawer for the 5% of time users add API keys or modify role mappings.
3. **Predictable & Transparent:** Never quietly degrade or switch models in the background. If a prompt triggers an escalation from Guide to Specialist, show the handoff clearly. Badges explicitly clarify whether a model is **Local (Offline)** or **Cloud (BYOK)**.

---

## 2. User Mental Models & Primary User Journeys

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                             PRIMARY USER JOURNEYS                           │
├───────────────────┬─────────────────────────┬───────────────────────────────┤
│ Persona           │ Starting Context        │ Desired Experience            │
├───────────────────┼─────────────────────────┼───────────────────────────────┤
│ 1. The Local      │ Has Ollama running with │ Opens Halbert. Chat says:     │
│    Sysadmin       │ qwen2.5-coder:14b. No   │ "🟢 Ollama · qwen2.5-coder:14b"│
│    (Zero Cloud)   │ cloud keys.             │ Works immediately. 0 clicks.  │
├───────────────────┼─────────────────────────┼───────────────────────────────┤
│ 2. The Hybrid     │ Runs Ollama locally,    │ Uses Guide (Ollama) for fast  │
│    Power User     │ has Anthropic BYOK key  │ checks. When a complex issue  │
│    (Local + BYOK) │ for deep coding tasks.  │ arises, clicks [⚡ Guide] to  │
│                   │                         │ flip to [🧠 Specialist], or   │
│                   │                         │ lets auto-routing handle it.  │
├───────────────────┼─────────────────────────┼───────────────────────────────┤
│ 3. The Explorer   │ Wants to test a newly   │ In chat, types `/model deep-  │
│    (In-Session)   │ pulled Ollama model     │ seek-r1` or clicks the pill.  │
│                   │ mid-investigation.      │ Switches instantly without    │
│                   │                         │ leaving the terminal/chat view│
└───────────────────┴─────────────────────────┴───────────────────────────────┘
```

---

## 3. Surface 1: Ambient In-Chat Controls (Runtime Interface)

The primary interaction happens in the chat stream, not in Settings.

### 3.1 The Model Selector Pill
Positioned in the header of [`AgentChat.tsx`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/components/agent/AgentChat.tsx) (and mirrored in the bottom toolbar of the composer alongside the screenshot/camera button).

```
[Chat Header Wireframe]
┌─────────────────────────────────────────────────────────────────────────────┐
│ 💬 Disk Cleanup Session #3                     [🟢 Ollama · qwen2.5-coder:14b ▾] [⚡ Auto: Guide ▾] ⚙️ │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### Pill Elements & States:
1. **Health Dot:**
   * 🟢 Green: Endpoint reachable, model loaded or ready.
   * 🟡 Amber: Loading/pulling model into VRAM.
   * 🔴 Red: Endpoint unreachable (clicking gives 1-click diagnostic).
2. **Provider Icon + Label:**
   * Ollama / LM Studio logo + Model Name (`qwen2.5-coder:14b`).
   * Cloud BYOK shows provider icon (Anthropic, OpenAI, Google) + Model Name (`claude-3-7-sonnet`).
3. **Context Meter Pill (Optional / Hover):**
   * Displays token usage against model context ceiling (e.g., `18k / 32k`).
4. **Active Tier Badge:**
   * `[⚡ Auto: Guide]` — Fast model active, will auto-escalate if prompt complexity > 0.5.
   * `[🔒 Pin: Specialist]` — Forced deep reasoning model for all turns.
   * `[👁️ Vision]` — Multimodal model handling attached screenshots.

---

### 3.2 The Quick-Switch Popover
Clicking the Model Selector Pill (or typing `/model` in the composer) renders an accessible, floating popover directly anchored to the trigger.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         QUICK-SWITCH POPOVER                                │
├─────────────────────────────────────────────────────────────────────────────┤
│  🔍  Search models or providers...                             [Esc to exit]│
├─────────────────────────────────────────────────────────────────────────────┤
│  TIER OVERRIDE                                                              │
│  [  ⚡ Fast (Guide)  ]   [  🧠 Reasoning (Specialist)  ]   [  ⚙️ Auto-Route  ]│
├─────────────────────────────────────────────────────────────────────────────┤
│  LOCAL MODELS (Ollama @ localhost:11434)                       [↻ Refresh]  │
│  ✓ qwen2.5-coder:14b       [32k ctx] [Tools] [Coding]           ● Ready     │
│    deepseek-r1:14b         [32k ctx] [Reasoning]                ○ Offline   │
│    llama3.2-vision:11b     [128k ctx][Vision] [Multimodal]      ○ Offline   │
│                                                                             │
│  CLOUD MODELS (BYOK)                                                        │
│    claude-3-7-sonnet       [200k ctx][Anthropic] [Reasoning]    ● Connected │
│    gpt-4o                  [128k ctx][OpenAI]    [Tools]        ● Connected │
├─────────────────────────────────────────────────────────────────────────────┤
│  ⚙️  Configure Providers & Keys...                   ⌨️ Press /model anytime │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### Behavioral Details:
* **Keyboard Navigation:** Arrow Up/Down navigates models. `Enter` selects and closes. `Esc` cancels.
* **Instant Model Switching:** Selecting a model takes effect on the *very next turn*. No full-page reload or session teardown.
* **Capability Tags:**
  * `[Tools]`: Verified native tool calling support (vital for agent bash/file operations).
  * `[Vision]`: Multimodal image processing support.
  * `[Reasoning]`: Chain-of-thought model (DeepSeek-R1, o3, Claude 3.7 Thinking).
  * `[32k ctx]`: Context window indicator. Warns with amber text if < 16k for agent tasks.
* **Direct Shortcut:** A footer link cleanly transitions to the full Configuration Drawer.

---

### 3.3 The In-Chat `/model` Command (Claude Code Parity)
To match Claude Code's terminal ergonomics, the composer in [`AgentChat.tsx`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/components/agent/AgentChat.tsx) intercepts slash commands:
1. **`/model`**: Opens the Quick-Switch Popover anchored above the input bar with focus immediately in the search field.
2. **`/model <search-string>`**: Fuzzy matches installed/configured models. For example, typing `/model qwen` and hitting Enter immediately switches the active chat model to `qwen2.5-coder:14b` and inserts an ephemeral system notification in chat:
   > *Active model switched to **qwen2.5-coder:14b** (Local Ollama).*
3. **`/model status`**: Injects a compact diagnostic card into the stream showing active models for all three roles, loaded VRAM status, and token usage.

---

### 3.4 Visible Tier Handoffs in the Conversation
One of the most frustrating aspects of multi-tier systems is silent model switching. When Halbert’s complexity router determines a query requires the Specialist model, the chat stream renders a clean **Handoff Banner**:

```
[Chat Stream Inline Progression]
┌─────────────────────────────────────────────────────────────────────────────┐
│ 👤 User: "Diagnose why nginx failed after the certbot renew hook yesterday" │
├─────────────────────────────────────────────────────────────────────────────┤
│ 🔀 Escalated to Specialist (claude-3-7-sonnet) · Complexity Score: 0.78    │
│                                                                             │
│ 🧠 Thinking (12.4s) ▾                                                       │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ Checking renewal logs in /var/log/letsencrypt and systemd service state │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│ 📋 Plan:                                                                    │
│ [x] 1. Inspect certbot renewal log                                          │
│ [ ] 2. Test nginx syntax with renewed certificate                           │
│ [ ] 3. Verify socket binding on port 443                                    │
└─────────────────────────────────────────────────────────────────────────────┘
```
This gives the user complete predictability: they know *why* a more powerful model was summoned and *what* it is doing.

---

## 4. Surface 2: Foundational Configuration (Settings Drawer / Modal)

When users need to add API keys, configure remote endpoints, or customize role defaults, they access the Configuration Drawer.

### 4.1 Layout: Two Clean Tabs Instead of Six Cards
Instead of SourcePrep's 6 sprawling cards, the UI is organized into two tabs:
1. **Tab 1: Model Roles (What model does what?)**
2. **Tab 2: Providers & BYOK Keys (Where do models come from?)**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         AI MODEL CONFIGURATION                              │
├─────────────────────────────────────────────────────────────────────────────┤
│  [ 🎯 Model Roles (3) ]          [ 🔌 Providers & BYOK Keys (2 Active) ]    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Assign models to Halbert's 3 runtime roles.                                │
│                                                                             │
│  ROLE             ENDPOINT / PROVIDER       MODEL SELECTION        STATUS   │
│  ─────────────────────────────────────────────────────────────────────────  │
│  💬 Chat (Guide)  [ 🟢 Local Ollama     ▾ ] [ qwen2.5-coder:14b ▾] [ Test ] │
│     Primary conversational interface for routine commands & quick answers.  │
│                                                                             │
│  🧠 Specialist    [ 🟣 Anthropic (BYOK) ▾ ] [ claude-3-7-sonnet ▾] [ Test ] │
│     Deep reasoning engine for multi-step diagnosis and complex plans.       │
│     ☑️ Enable automatic routing for complex queries (>0.5 score)            │
│                                                                             │
│  👁️ Vision        [ 🟢 Local Ollama     ▾ ] [ llama3.2-vision:11b▾][ Test ] │
│     Interprets screenshots, terminal snapshots, and architectural diagrams. │
│     💡 Chat model supports vision natively; separate slot optional.         │
│                                                                             │
│  ─────────────────────────────────────────────────────────────────────────  │
│  [ Save Changes ]                                          [ Reset to Auto ]│
└─────────────────────────────────────────────────────────────────────────────┘
```

### 4.2 Tab 2: Providers & Zero-Config Local Auto-Discovery

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  [ 🎯 Model Roles (3) ]          [ 🔌 Providers & BYOK Keys (2 Active) ]    │
├─────────────────────────────────────────────────────────────────────────────┤
│  LOCAL ENGINES (Auto-Discovered)                                            │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │ 🟢 Local Ollama               http://localhost:11434       [ ↻ Rescan ]│  │
│  │    8 models found · Running v0.14.2 · GPU acceleration active         │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │ ⚪ Local LM Studio            http://localhost:1234        [ Connect ] │  │
│  │    Not detected on standard port · Click to start or specify port     │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│  CLOUD PROVIDERS (BYOK)                                                     │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │ 🟣 Anthropic (Claude)                                    [ Connected ]│  │
│  │    API Key: [ sk-ant-api03-••••••••••••••••••••••• 👁️ ]    [ Test Key ] │  │
│  │    Models available: claude-3-7-sonnet, claude-3-5-haiku, claude-3-opus │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │ 🟢 OpenAI                                                [ Not Set ]  │  │
│  │    API Key: [ sk-proj-•••••••••••••••••••••••••••• 👁️ ]    [ Test Key ] │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │ 🌐 Custom OpenAI-Compatible Endpoint                      [ + Add ]   │  │
│  │    For vLLM, OpenRouter, TGI, LocalAI, or custom corporate gateways    │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### Clarity & Simplicity Enhancements:
1. **Auto-Discovery eliminates endpoint setup:** The app probes `http://localhost:11434` and `http://localhost:1234` on mount. If detected, they appear pre-configured. The user never types `http://localhost:11434`.
2. **Inline Key Verification:** When a user pastes an API key, clicking **[ Test Key ]** makes a lightweight models request. A green checkmark confirms validity immediately.
3. **No Hidden Secrets:** Keys are stored strictly in the local app configuration directory (`/etc/halbert` or `~/.config/halbert`), never synced to any remote service.

---

## 5. Direct Resolution of Open Questions in Past Handoffs

Here we directly critique, resolve, and close the tensions raised in `.handoff/LLM-PICKER-DESIGN-REVIEW-2026-08-26.md` and `.handoff/HANDOFF-LLM-PICKER-AND-CLAUDE-CODE-PARITY-2026-08-26.md`:

### Question 1: Should Halbert share SourcePrep's LLM config or remain independent?
* **Previous State:** An attempt was made to share `models.yml` and `llm_config`. When SourcePrep daemon was running, Halbert locked its own settings and hid the picker.
* **Resolution:** **Strictly Independent Configuration.** Halbert's config is owned 100% by Halbert. It must work with zero dependence on whether SourcePrep is installed or running.
* **What IS Shared:** The UI components in [`packages/design-system`](file:///Volumes/4TB-BAD/Halbert/packages/design-system). Both Halbert and SourcePrep will import the *same reusable picker component*, passing their own role definitions.

### Question 2: Why did `small_model` map to the chat orchestrator?
* **Previous State:** SourcePrep’s `small_model` (cheap catalogue summarizer) was wired to Halbert’s primary chat model in `model/client.py`.
* **Resolution:** **Eliminate `small_model` and `large_model` nomenclature in Halbert.** Adopt the 3 user-facing conversational roles:
  * `chat_model` (The primary interactive Guide)
  * `specialist_model` (The deep reasoning engine)
  * `vision_model` (The multimodal interpreter)
  Legacy keys are migrated cleanly once by `model/llm_config.py`.

### Question 3: How should we handle the Vision slot when the Chat model already has vision?
* **Previous State:** Users were confused why they had to pick a Vision model when their chat model was already multimodal (e.g. `llama3.2-vision` or `claude-3-7-sonnet`).
* **Resolution:** **Auto-Inherit Capability Hint.** If the active `chat_model` has vision capabilities (verified via Ollama `/api/show` or model registry), the Vision slot defaults to `Inherit from Chat Model (Auto)`. Users only configure a separate Vision slot if their chat model is pure text.

### Question 4: How do we prevent "Test Green in Settings, Fails in Chat"?
* **Previous State:** `EndpointManager` offered 7 providers, but `call_llm_chat` only supported Ollama and OpenAI without proper auth headers.
* **Resolution:** Provider capability gating. Providers that chat cannot call are badged with `[Requires Chat Adapter]` or excluded from the chat slot until the adapter is implemented. `call_llm_chat` adds Bearer auth and Anthropic Messages format support.

### Question 5: How does this bridge with Claude Code parity?
* **Previous State:** Claude Code provides `/model` in terminal, while Halbert had no runtime switching and reset conversation history every turn.
* **Resolution:**
  1. Add `/model` command and header pill to [`AgentChat.tsx`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/components/agent/AgentChat.tsx).
  2. Implement continuous conversation memory in `routes/agent.py` so model switches preserve the context thread.

### Question 6: What happens to the legacy `orchestrator`, `specialist`, and `vision` keys?
* **Previous State:** `model/client.py` fell back to top-level legacy keys when `llm_config` was empty. Two endpoint lists existed in `models.yml`.
* **Resolution:** **One-Time Transparent Migration.** The backend store `model/llm_config.py` migrates legacy keys on first load, saves a timestamped `models.yml.bak`, and writes the clean unified schema. This eliminates dual code paths permanently while ensuring zero user configuration loss.

### Question 7: Should API keys move to the system credential store (Keyring / Keychain)?
* **Previous State:** API keys are stored in plaintext in `models.yml`.
* **Resolution:** **Pragmatic Staged Security.** For Linux/macOS single-user local daemons, storing in `models.yml` with restricted file permissions (`chmod 0600`) remains the most predictable and inspectable for developers. The UI masks keys (`sk-ant-•••••••••• 👁️`) with copy/reveal protection. For the desktop packaging track (Tauri), the `useModelRegistry` contract isolates key persistence so a Tauri Keychain plugin can be swapped in under the hood without changing a single line of picker UI.

### Question 8: Should the embedding model be inside the LLM picker?
* **Previous State:** Halbert's RAG hardcodes `all-MiniLM-L6-v2` via `sentence-transformers`. The vendored `AIModelsSettings.tsx` showed an Embedding Model Card that configured nothing in Halbert—pure dead UI that confused users.
* **Resolution:** **Role-Decoupled UI (Eliminate Dead Cards).** Embeddings are an indexing concern, not a conversational LLM. In Halbert, the embedding card is **completely removed** from the model picker. In SourcePrep (where vector embedding *is* user-configurable), SourcePrep simply passes `{ id: 'embedding', label: 'Vector Embedder' }` to the reusable component. The UI cleanly adapts to whatever roles an app actually supports.

### Question 9: Cross-App Ecosystem Strategy (Halbert, SourcePrep, LinuxBrain, BrightestMinds)
* **The Reality:**
  * **Halbert (`/Volumes/4TB-BAD/Halbert`):** Needs 3 roles (`chat_model`, `specialist_model`, `vision_model`).
  * **SourcePrep (`/Volumes/4TB-BAD/HumanAI/CoDRAG`):** Needs 4 pipeline slots (`small_model`, `large_model`, `code_model`, `embedding`).
  * **LinuxBrain (`/Volumes/4TB-BAD/HumanAI/LinuxBrain`):** Uses custom `SettingsTabs.tsx` (`orchestrator`, `specialist`, `vision`, `parser`, plus image generation models).
  * **BrightestMinds (`/Volumes/4TB-BAD/BrightestMinds`):** Forked from LinuxBrain with diverged tab structure.
* **The Solution:** A **Role-Agnostic Component Library**. By building the dual-surface picker in `packages/design-system`, every app in the ecosystem consumes the exact same auto-discovery, BYOK cards, and in-chat pill without any app being forced to adopt another app's internal pipeline naming.

---

## 6. Architecture of the Reusable Package (`packages/design-system`)

To prevent code duplication across Halbert, SourcePrep, and future apps, the picker is structured as a headless core with swappable surfaces.

```
packages/design-system/src/components/model-picker/
├── index.ts                     # Public package exports
├── types.ts                     # Universal schema & interfaces
├── useModelRegistry.ts          # Headless state, discovery & persistence hook
├── useLocalDiscovery.ts         # Port prober (Ollama :11434, LM Studio :1234)
├── ModelSelectorPill.tsx        # Surface 1: In-chat header & composer trigger
├── QuickSwitchPopover.tsx       # Surface 1: Searchable floating model switcher
├── ModelSettingsDrawer.tsx      # Surface 2: Full role grid & BYOK management
├── RoleAssignmentRow.tsx        # 1-row role assignment component
└── ProviderCard.tsx             # BYOK & local provider connection card
```

### 6.1 Universal Data Contract (`types.ts`)

```typescript
export type ProviderType = 
  | 'ollama' 
  | 'lm-studio' 
  | 'anthropic' 
  | 'openai' 
  | 'google' 
  | 'openai-compatible';

export interface ModelCapability {
  supportsTools: boolean;
  supportsVision: boolean;
  isReasoning: boolean;
  contextWindow: number; // e.g. 32768
}

export interface DiscoveredModel {
  id: string;              // e.g. "qwen2.5-coder:14b"
  name: string;
  provider: ProviderType;
  endpointId: string;
  isLocal: boolean;
  capabilities: ModelCapability;
}

export interface AppRoleDefinition {
  id: string;              // e.g. "chat_model" or "specialist_model"
  label: string;           // e.g. "Chat / Guide"
  description: string;
  recommendedTag?: string; // e.g. "Fast 8B-14B"
  requiresVision?: boolean;
  requiresTools?: boolean;
}

export interface ModelPickerProps {
  roles: AppRoleDefinition[];
  activeAssignments: Record<string, { endpointId: string; model: string }>;
  onSaveAssignment: (roleId: string, endpointId: string, model: string) => Promise<void>;
  endpoints: SavedEndpoint[];
  onSaveEndpoint: (endpoint: SavedEndpoint) => Promise<void>;
  onDeleteEndpoint: (endpointId: string) => Promise<void>;
  onProbeEndpoint: (endpoint: SavedEndpoint) => Promise<EndpointTestResult>;
}
```

### 6.2 How Halbert Consumes the Component:
```tsx
import { ModelSelectorPill, ModelSettingsDrawer } from '@halbert/design-system';

const HALBERT_ROLES: AppRoleDefinition[] = [
  { id: 'chat_model', label: 'Chat (Guide)', description: 'Quick system commands & diagnostics', requiresTools: true },
  { id: 'specialist_model', label: 'Specialist', description: 'Deep reasoning & multi-step plans' },
  { id: 'vision_model', label: 'Vision', description: 'Screenshot & hardware sensor analysis', requiresVision: true },
];

export function HalbertSettings() {
  return (
    <ModelSettingsDrawer 
      roles={HALBERT_ROLES}
      // wired to Halbert's /api/llm backend
    />
  );
}
```

### 6.3 How SourcePrep Consumes the Same Component:
```tsx
const SOURCEPREP_ROLES: AppRoleDefinition[] = [
  { id: 'small_model', label: 'Catalogue', description: 'Fast file summarization pass' },
  { id: 'large_model', label: 'Reasoning', description: 'Enrichment & concept clustering' },
  { id: 'embedding', label: 'Embeddings', description: 'Vector indexing model' },
];

export function SourcePrepSettings() {
  return (
    <ModelSettingsDrawer 
      roles={SOURCEPREP_ROLES}
      // wired to SourcePrep's :8400/global/config backend
    />
  );
}
```

---

## 7. Accessibility, Micro-Interactions & Visual Affordances

1. **Color & Contrast Token Compliance:**
   * Uses Daylight design tokens exclusively (`surface`, `surface-raised`, `border`, `text`, `text-muted`, `primary`, `success`, `warning`, `error`).
   * No raw Tailwind gray or custom hex codes.
2. **Keyboard Ergonomics:**
   * `Cmd + /` or typing `/model` focuses model selection immediately.
   * `ArrowDown` / `ArrowUp` cycles options; `Enter` commits; `Esc` dismisses.
   * Focus trap enabled when the popover is active.
3. **Screen Reader (ARIA) Specifications:**
   * Selector pill carries `role="combobox"`, `aria-expanded="false"`, and `aria-haspopup="listbox"`.
   * Live region (`aria-live="polite"`) announces model switches: *"Switched to Qwen 2.5 Coder 14B."*
4. **Privacy Transparency:**
   * Models that send data off-machine carry a permanent subtle badge: `[Cloud · External API]`.
   * Local models carry: `[Local · Machine Offline]`.

---

## 8. Technical Team Review Checklist & Next Steps

When the technical engineering team reviews this specification, here are the required code seams to execute:

* [ ] **Frontend Deletion:** Delete the 1,223-line [`AIModelsSettings.tsx`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/components/llm/AIModelsSettings.tsx), `UnifiedLLMSettings.tsx`, `AdvancedLLMSettings.tsx`, and stubs from `halbert_core`.
* [ ] **Design System Package:** Scaffold `packages/design-system/src/components/model-picker/` with the shared contracts and dual-surface components.
* [ ] **Chat Mount:** Mount `<ModelSelectorPill />` into [`AgentChat.tsx`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/components/agent/AgentChat.tsx) and wire `/model` slash command.
* [ ] **Backend Store:** Implement `halbert_core/model/llm_config.py` with one-time migration of `orchestrator/specialist/vision` legacy keys to `chat_model/specialist_model/vision_model`.
* [ ] **Chat Adapter Auth:** Add Bearer token support to `call_llm_chat` in `routes/agent.py` to enable Anthropic/OpenAI BYOK endpoints.
* [ ] **Local Discovery Route:** Ensure `/api/llm/discover` probes localhost ports `11434` and `1234` asynchronously without blocking backend startup.
