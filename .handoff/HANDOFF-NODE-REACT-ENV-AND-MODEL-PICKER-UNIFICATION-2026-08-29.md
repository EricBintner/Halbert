# Handoff: Node & React Environment, Haloysius Integration, and Model Picker UI Unification

**Document Version:** 1.0.0  
**Date:** 2026-08-29  
**Status:** Ready for Agent Allocation  
**Domain:** Node.js, React, Tauri 2 Shell, Haloysius Cognitive Core, Headless Model Picker (`@halbert/model-picker`), and Olivetti Design System (`@halbert/design-system`)  
**Directly Implements / Governed By:**
- [`.handoff/HANDOFF-LLM-PICKER-AND-CLAUDE-CODE-PARITY-2026-08-26.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/HANDOFF-LLM-PICKER-AND-CLAUDE-CODE-PARITY-2026-08-26.md)
- [`documentation/design/UI-SPEC-REUSABLE-MODEL-PICKER-2026-08-26.md`](file:///Volumes/4TB-BAD/Halbert/documentation/design/UI-SPEC-REUSABLE-MODEL-PICKER-2026-08-26.md)
- [`documentation/design/BRAND-AESTHETIC-STYLEGUIDE-AND-STORYBOOK-PLAN.md`](file:///Volumes/4TB-BAD/Halbert/documentation/design/BRAND-AESTHETIC-STYLEGUIDE-AND-STORYBOOK-PLAN.md)
- [`/Volumes/4TB-BAD/Haloysius/CHARTER.md`](file:///Volumes/4TB-BAD/Haloysius/CHARTER.md)

---

## 1. Executive Summary & Objective

Following a comprehensive audit of the core Halbert desktop app, Haloysius cognitive core, and the newly extracted `@halbert/model-picker` and `@halbert/design-system` packages, this document partitions all required unification, hygiene, and documentation tasks into self-contained, model-calibrated packets.

### Target Stack Invariants
1. **Node.js:** Standardized on **Node.js 22 LTS** (`.nvmrc: 22`).
2. **React Ecosystem:**
   - Libraries ([`@halbert/model-picker`](file:///Volumes/4TB-BAD/Halbert/packages/model-picker), [`@halbert/design-system`](file:///Volumes/4TB-BAD/Halbert/packages/design-system)): Strict dual peer-dependency support (`^18.2.0 || ^19.0.0`).
   - Desktop App ([`halbert_core/dashboard/frontend`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend)): React 18.2 ➔ planned path to React 19.
3. **Workspace Model:** Standard npm/pnpm workspace linking replacing relative filesystem Vite aliases.
4. **Haloysius Contract:** Pure Python subtractive contract preserved with function-level lazy imports and isolated data directories.

---

## 2. Agent Allocation Matrix

| Packet ID | Workstream / Domain | Target Model Tier | Effort Level | Key Target Files |
|:---|:---|:---:|:---:|:---|
| **Packet 01** | Root Workspace Architecture & Package Resolution | **Sonnet + UltraCode** | **High** | Root `package.json`, `vite.config.ts`, `tsconfig.json` |
| **Packet 02** | Frontend Dependency Hygiene & Primitives Consolidation | **Sonnet + UltraCode** | **Med** | `dashboard/frontend/package.json`, `prep-primitives/*` |
| **Packet 03** | Haloysius ↔ Halbert Integration & Python Harmonization | **Opus** | **High** | `pyproject.toml`, `cognition_wiring.py`, `haloysius_memory_adapter.py` |
| **Packet 04** | Model Picker Transport & Desktop In-Chat Seam Hardening | **Fable / Opus** | **XHigh / Max** | `modelPickerTransport.ts`, `ChatModelPill.tsx`, `AgentChat.tsx` |
| **Packet 05** | Documentation Overhaul & Developer Experience Alignment | **Sonnet + UltraCode** | **Med** | `frontend/README.md`, `INSTALLATION.md`, `ARCHITECTURE.md` |

---

## 3. Detailed Task Packets

```
┌─────────────────────────────────────────────────────────────────────────────┐
│             PACKET 01: ROOT WORKSPACE ARCHITECTURE & RESOLUTION             │
│             Model: Sonnet + UltraCode  |  Effort: High                      │
└─────────────────────────────────────────────────────────────────────────────┘
```
### Objective
Eliminate fragile relative path aliases (`../../../../packages/model-picker/src`) and `server.fs.allow` overrides in the dashboard frontend by establishing a formal root workspace.

### Tasks
1. **Task 1.1: Create Halbert Root Workspace Manifest**
   - **Target File:** [`package.json`](file:///Volumes/4TB-BAD/Halbert/package.json) (New at repo root)
   - Declare npm workspaces:
     ```json
     {
       "name": "halbert-monorepo",
       "private": true,
       "packageManager": "npm@10.9.3",
       "workspaces": [
         "packages/*",
         "halbert_core/halbert_core/dashboard/frontend"
       ],
       "scripts": {
         "dev": "npm --workspace=halbert-dashboard run dev",
         "build": "npm run --workspaces --if-present build",
         "test": "npm run --workspaces --if-present test",
         "typecheck": "npm run --workspaces --if-present typecheck"
       }
     }
     ```
2. **Task 1.2: Standardize Workspace Dependencies in Dashboard**
   - **Target File:** [`halbert_core/halbert_core/dashboard/frontend/package.json`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/package.json)
   - Add explicit workspace references:
     ```json
     "dependencies": {
       "@halbert/design-system": "*",
       "@halbert/model-picker": "*"
     }
     ```
3. **Task 1.3: Clean Up Frontend `vite.config.ts` and `tsconfig.json`**
   - **Target File:** [`halbert_core/halbert_core/dashboard/frontend/vite.config.ts`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/vite.config.ts)
   - Remove hardcoded `MODEL_PICKER_SRC` and relative file path aliases; rely on Node workspace module resolution.
   - Remove `fs: { allow: ['..', MODEL_PICKER_SRC] }` workaround.
   - **Target File:** [`halbert_core/halbert_core/dashboard/frontend/tsconfig.json`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/tsconfig.json)
   - Update `paths` mapping to reflect standard package names.
4. **Task 1.4: Add Unified `.nvmrc`**
   - **Target Files:** [`/Volumes/4TB-BAD/Halbert/.nvmrc`](file:///Volumes/4TB-BAD/Halbert/.nvmrc) & [`/Volumes/4TB-BAD/Haloysius/.nvmrc`](file:///Volumes/4TB-BAD/Haloysius/.nvmrc)
   - Write `22` in both files.

---

```
┌─────────────────────────────────────────────────────────────────────────────┐
│        PACKET 02: FRONTEND DEPENDENCY HYGIENE & PRIMITIVES CONSOLIDATION     │
│        Model: Sonnet + UltraCode  |  Effort: Med                            │
└─────────────────────────────────────────────────────────────────────────────┘
```
### Objective
Deduplicate packages, upgrade outdated icon dependencies, align TypeScript/Vite versions, and route duplicate UI primitives through `@halbert/design-system`.

### Tasks
1. **Task 2.1: Purge Deprecated Unscoped Xterm Packages**
   - **Target File:** [`halbert_core/halbert_core/dashboard/frontend/package.json`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/package.json)
   - Remove: `"xterm": "^5.3.0"`, `"xterm-addon-fit": "^0.8.0"`, `"xterm-addon-web-links": "^0.9.0"`.
   - Preserve and verify: `"@xterm/xterm": "^5.5.0"`, `"@xterm/addon-fit": "^0.10.0"`, `"@xterm/addon-web-links": "^0.11.0"`.
2. **Task 2.2: Upgrade `lucide-react` to Modern Standard**
   - **Target File:** [`halbert_core/halbert_core/dashboard/frontend/package.json`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/package.json)
   - Bump `"lucide-react"` from `^0.294.0` to `^0.475.0` (or `^1.x` aligned with other components).
   - Verify icon imports across `src/components/agent/` and `src/components/shell/`.
3. **Task 2.3: Align TypeScript and Vite Compiler Toolchains**
   - Align `typescript` to `^5.6.3` (matching `packages/model-picker` and `packages/design-system`).
   - Align `vite` to `^5.4.14` and `@vitejs/plugin-react` to `^4.3.4`.
4. **Task 2.4: Consolidate Redundant Primitives**
   - **Target Directory:** [`halbert_core/halbert_core/dashboard/frontend/src/components/prep-primitives/`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/components/prep-primitives)
   - Replace redundant local `Button.tsx`, `Select.tsx` with re-exports or direct imports from `@halbert/design-system`.

---

```
┌─────────────────────────────────────────────────────────────────────────────┐
│          PACKET 03: HALOYSIUS ↔ HALBERT INTEGRATION & PYTHON HARMONY         │
│          Model: Opus  |  Effort: High                                       │
└─────────────────────────────────────────────────────────────────────────────┘
```
### Objective
Ensure seamless inter-repo operation between Halbert Core and Haloysius, preserving the subtractive dependency contract, lazy import safety, and data directory isolation.

### Tasks
1. **Task 3.1: Verify & Lock Haloysius Dependency Definition**
   - **Target File:** [`halbert_core/pyproject.toml`](file:///Volumes/4TB-BAD/Halbert/halbert_core/pyproject.toml)
   - Update optional cognition extra to reflect Haloysius v0.2.0+:
     ```toml
     cognition = [
       "haloysius>=0.2.0",
     ]
     ```
2. **Task 3.2: Verify Subtractive Contract & Lazy Import Guards**
   - **Target Files:**
     - [`halbert_core/halbert_core/integrations/cognition_wiring.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/integrations/cognition_wiring.py)
     - [`halbert_core/halbert_core/integrations/haloysius_memory_adapter.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/integrations/haloysius_memory_adapter.py)
   - Audit all top-level imports: verify that no `haloysius.*` modules are imported eagerly at module evaluation time.
   - Verify fallback graceful degradation: when Haloysius is not installed in the active virtualenv, `halbert_core` must boot cleanly without raising `ImportError`.
3. **Task 3.3: Validate Multi-Instance Memory Isolation**
   - Ensure `HALOYSIUS_DATA_HOME` environment mapping correctly binds to `HALBERT_DATA_DIR` so persona memory files (`self_knowledge`, `conversations`) never collide between multiple daemon instances.

---

```
┌─────────────────────────────────────────────────────────────────────────────┐
│       PACKET 04: MODEL PICKER TRANSPORT & IN-CHAT SEAM HARDENING            │
│       Model: Fable / Opus  |  Effort: XHigh / Max                           │
└─────────────────────────────────────────────────────────────────────────────┘
```
### Objective
Harden the single communication seam between `@halbert/model-picker` and Halbert's backend, verify `/model` slash command synchronization in Agent Chat, and maintain zero boundary violations.

### Tasks
1. **Task 4.1: Harden `modelPickerTransport.ts` Error Handling**
   - **Target File:** [`halbert_core/halbert_core/dashboard/frontend/src/lib/modelPickerTransport.ts`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/lib/modelPickerTransport.ts)
   - Ensure `discoverLocal()` handles offline daemons (`localhost:11434` or `localhost:1234`) with polite failure envelopes instead of unhandled Promise rejections.
   - Ensure masked API key handling (`apiKey: undefined` vs `apiKey: ''`) preserves stored keys on partial PUT saves.
2. **Task 4.2: Verify Agent Chat Slash Command & Pill Synchronization**
   - **Target Files:**
     - [`halbert_core/halbert_core/dashboard/frontend/src/components/agent/AgentChat.tsx`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/components/agent/AgentChat.tsx)
     - [`halbert_core/halbert_core/dashboard/frontend/src/components/llm/ChatModelPill.tsx`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/components/llm/ChatModelPill.tsx)
   - Ensure typing `/model <name>` updates the exact same state instance displayed by `ChatModelPill` in the chat header and composer tray.
   - Verify that model switches inject the proper ephemeral notice into the stream and preserve context in `routes/agent.py`.
3. **Task 4.3: Maintain Extraction Boundary Invariants**
   - **Target Directory:** [`packages/model-picker`](file:///Volumes/4TB-BAD/Halbert/packages/model-picker)
   - Run `npm run check:boundary` and ensure 0 violations across all 16 source files (zero I/O, zero hardcoded classes, zero slot names).
   - Run `npm test` and verify all 103 tests pass.

---

```
┌─────────────────────────────────────────────────────────────────────────────┐
│          PACKET 05: DOCUMENTATION OVERHAUL & DX ALIGNMENT                   │
│          Model: Sonnet + UltraCode  |  Effort: Med                          │
└─────────────────────────────────────────────────────────────────────────────┘
```
### Objective
Bring all project documentation into 100% alignment with the implemented Tauri 2 shell, design tokens, model picker package, and cognitive architecture.

### Tasks
1. **Task 5.1: Overhaul Frontend Dashboard README**
   - **Target File:** [`halbert_core/halbert_core/dashboard/frontend/README.md`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/README.md)
   - Document:
     - Tauri 2 desktop shell architecture and dev commands (`npm run tauri:dev`, `npm run build`).
     - Consumption of `@halbert/model-picker` and `@halbert/design-system`.
     - In-chat `/model` slash command usage and keyboard navigation.
     - Live terminals (`@xterm/xterm`) and WebSocket/SSE streaming.
2. **Task 5.2: Update System Installation Guide**
   - **Target File:** [`documentation/INSTALLATION.md`](file:///Volumes/4TB-BAD/Halbert/documentation/INSTALLATION.md)
   - Add "Desktop UI & Frontend Prerequisites" section:
     - Node.js 22 LTS (`nvm use 22`).
     - Rust / Cargo toolchain for Tauri desktop builds.
     - Editable installation instructions for sibling repos (`Haloysius`).
3. **Task 5.3: Update Architecture Overview Document**
   - **Target File:** [`documentation/ARCHITECTURE.md`](file:///Volumes/4TB-BAD/Halbert/documentation/ARCHITECTURE.md)
   - Update Section 1 (User Interface Layer) to incorporate the decoupled package diagram showing `@halbert/model-picker`, `@halbert/design-system`, and Tauri 2 sidecar IPC.

---

## 4. Verification & Gate Conditions

Every allocated agent must satisfy these pass criteria before marking a packet complete:

```bash
# 1. Root & Package Typechecking
npm run typecheck

# 2. Package Boundary Compliance
cd packages/model-picker && npm run check:boundary

# 3. Complete Test Suites
cd packages/model-picker && npm test             # 103 passed tests
cd packages/design-system && npm test            # 29 passed tests
cd halbert_core/halbert_core/dashboard/frontend && npm test # 401 passed tests

# 4. Backend & Haloysius Integration
pytest halbert_core/tests/test_client.py halbert_core/tests/test_being_config.py -v
```
