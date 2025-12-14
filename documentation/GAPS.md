# Documentation vs Code Gap Analysis

**Generated**: December 14, 2025  
**Last Audit**: This document

---

## Summary

The public `documentation/` folder contains the original architecture vision from early development. Many features have been implemented that aren't documented, and some documented features don't exist or work differently.

**Status Key:**
- ✅ **Implemented & Documented** — Works and docs are accurate
- ⚠️ **Implemented, Undocumented** — Works but not in public docs
- ❌ **Documented, Not Implemented** — Docs claim it exists but it doesn't
- 🔄 **Partially Implemented** — Some aspects work, others don't

---

## Dashboard Pages (Frontend)

### Actual Pages vs Documentation

| Page | Status | Notes |
|------|--------|-------|
| **Dashboard** | ⚠️ | Exists, minimal docs |
| **Services** | ⚠️ | Full systemd service management, not documented |
| **Storage** | ⚠️ | bcachefs, ZFS, BTRFS, disk health - undocumented |
| **Backups** | ⚠️ | Timeshift, borg detection - undocumented |
| **Security** | ⚠️ | SSH, firewall, users - undocumented |
| **Network** | ⚠️ | Interfaces, bridges, bonds, VPN - undocumented |
| **Sharing** | ⚠️ | NFS, SMB, Tailscale, WireGuard - undocumented |
| **Containers** | ⚠️ | Docker/Podman management - undocumented |
| **GPU** | ⚠️ | NVIDIA/AMD monitoring, Ollama - undocumented |
| **Development** | ⚠️ | Git repos, dev environments - undocumented |
| **Approvals** | ⚠️ | Works, minimal docs |
| **Settings** | ⚠️ | Extensive settings, not documented |
| **Terminal** | ⚠️ | Integrated terminal - undocumented |
| **Memory** | 🔄 | Page exists but may be legacy |
| **Jobs** | 🔄 | Page exists but may be legacy |

---

## API Routes (Backend)

### Documented Routes

| Route | Doc Status | Actual Status |
|-------|------------|---------------|
| `GET /health` | ✅ | Works |
| `GET /api/status` | ✅ | Works |
| `POST /api/chat` | ⚠️ | Works but docs are incomplete |
| `GET /api/memory/*` | ❌ | May not exist as documented |
| `GET /api/approval/*` | ⚠️ | Works differently |
| `GET /api/autonomy/*` | ❌ | Not implemented |
| `ws://localhost:8000/ws` | ❌ | WebSocket not implemented |

### Undocumented Routes (Actually Exist)

| Route File | Key Endpoints | Status |
|------------|---------------|--------|
| `chat.py` | `/api/chat/send`, `/api/chat/config`, vision, history | ⚠️ Undocumented |
| `settings.py` | Endpoints, models, AI rules, personas | ⚠️ Undocumented |
| `discovery.py` | System discovery for all pages | ⚠️ Undocumented |
| `services.py` | Service management | ⚠️ Undocumented |
| `containers.py` | Docker/Podman | ⚠️ Undocumented |
| `gpu.py` | GPU monitoring | ⚠️ Undocumented |
| `editor.py` | Config file editing | ⚠️ Undocumented |
| `terminal.py` | Command execution | ⚠️ Undocumented |
| `conversations.py` | Chat history | ⚠️ Undocumented |
| `web_search.py` | Internet grounding | ⚠️ Undocumented |
| `rag.py` | RAG pipeline | ⚠️ Undocumented |
| `persona.py` | Persona switching | ⚠️ Undocumented |

---

## Core Features

### Implemented Features Not in Docs

| Feature | Phase | Location | Description |
|---------|-------|----------|-------------|
| **Multi-Model Architecture** | 21 | `chat.py` | Guide (8B) + Specialist (70B) + Vision routing |
| **Smart Model Routing** | 21 | `chat.py` | Complexity-based routing between models |
| **Vision Model Support** | 21 | `chat.py`, `SidePanel.tsx` | Image paste/drop, screenshot analysis |
| **Config Editor** | 18 | `ConfigEditor.tsx`, `editor.py` | AI-assisted config file editing with diff |
| **Custom AI Rules** | - | `settings.py` | User-defined guardrails per category |
| **Debug Mode** | - | `DebugContext.tsx` | Verbose debugging for chat |
| **Conversation History** | - | `conversations.py` | Persistent chat with context |
| **Context Injection** | 21 | `chat.py` | Auto-inject discoveries based on keywords |
| **Failure Correlation** | 21 | `chat.py` | Correlate related failures (disk → service) |
| **Tool Calling** | 12d | `chat.py` | LLM can call system tools |
| **RAG Pipeline** | 12c | `rag.py` | Documentation retrieval |
| **Command Execution** | - | `terminal.py` | Run commands from chat |
| **Auto-Analyze** | 21 | `SidePanel.tsx` | AI analyzes command output automatically |
| **Sharing Tab** | 17 | `Sharing.tsx` | NFS, SMB, Tailscale, WireGuard |
| **Screenshot Capture** | - | `Layout.tsx` | Capture window for vision model |

### Documented Features Not Implemented

| Feature | Documentation Claim | Actual Status |
|---------|---------------------|---------------|
| **LangGraph Orchestrator** | `runtime/engine.py` | ❌ Not used, direct Ollama calls |
| **Policy Engine** | `policy/loader.py`, `engine.py` | ❌ Files may exist but not integrated |
| **Scheduler/APScheduler** | `scheduler/*.py` | ❌ Not actively used |
| **Guardrails/Budgets** | `autonomy/*.py` | ❌ Files exist but not integrated |
| **Anomaly Detector** | `autonomy/anomaly_detector.py` | ❌ Not implemented |
| **Recovery Playbooks** | `autonomy/recovery.py` | ❌ Not implemented |
| **journald Ingestion** | `ingestion/journald.py` | 🔄 May be partial |
| **hwmon Ingestion** | `ingestion/hwmon.py` | 🔄 May be partial |
| **ChromaDB Vector Index** | `index/chroma_index.py` | 🔄 Exists, unclear if used |
| **WebSocket Real-time** | `ws://localhost:8000/ws` | ❌ Not implemented |
| **Dry-run Mode** | "Shows what would change" | 🔄 Not consistent |

---

## Architecture Claims vs Reality

### ARCHITECTURE.md Claims

| Claim | Reality |
|-------|---------|
| "LangGraph orchestrator with Planner → Executor → Observer" | ❌ Direct API calls to Ollama, no LangGraph loop |
| "ChromaDB for RAG" | ✅ ChromaDB now enabled by default, memory system integrated |
| "APScheduler for background tasks" | ❌ No scheduled tasks running |
| "Approval workflows with dry-run" | 🔄 Approval page exists but workflow minimal |
| "Guardrails prevent runaway automation" | ❌ Guardrails not enforced |
| "Telemetry collection from journald/hwmon" | 🔄 Discovery scanners exist, ingestion unclear |

### What Actually Happens

1. **Chat Flow**: User message → keyword context injection → Ollama API → response
2. **Discovery**: Scanners run on-demand per page, not continuous ingestion
3. **Model Selection**: Complexity scoring routes to guide vs specialist
4. **Config Editing**: SEARCH/REPLACE blocks parsed and applied

---

## Settings Features

### Undocumented Settings Tabs

| Tab | Features |
|-----|----------|
| **AI Models** | Guide/Specialist/Vision model assignment, endpoint management |
| **AI Rules** | Custom guardrails with priority, category, enabled toggle |
| **Personas** | Persona selection (not LoRA, system prompts only) |
| **Data Scan** | Trigger system discovery |
| **Autonomy** | (may be placeholder) |

---

## File Structure Discrepancies

### Documented but Potentially Stale

```
halbert_core/
├── approval/         # Exists but minimal use
├── autonomy/         # Exists but not integrated
├── ingestion/        # Exists but unclear use
├── memory/           # Exists but unclear use
├── policy/           # Exists but not integrated
├── runtime/          # Exists but not LangGraph-based
├── scheduler/        # Exists but not running
```

### Active Code Not in Docs

```
halbert_core/
├── dashboard/
│   ├── routes/       # 18 route files, only 5 documented
│   └── frontend/
│       ├── pages/    # 16 pages, 0 documented
│       └── components/
│           ├── ConfigEditor.tsx    # Undocumented
│           ├── SidePanel.tsx       # Undocumented (chat/terminal)
│           └── AIAnalysisPanel.tsx # Undocumented
├── discovery/
│   └── scanners/     # ~15 scanners, undocumented
```

---

## Priority Actions

### 🔴 P0: RAG/Memory Enhancement (Self-Understanding)

These features directly improve the system's understanding of itself:

| Item | Description | Status |
|------|-------------|--------|
| **Ingestion Pipeline** | journald/hwmon → ChromaDB | ✅ Done |
| **Conversation Memory** | Store/retrieve past conversations | ✅ Done |
| **Telemetry Context** | Inject relevant logs into chat | ✅ Done |
| **Document Indexing** | Man pages, Arch Wiki → ChromaDB | ✅ Done |
| **Discovery Search** | Semantic search over discoveries | ✅ Done |
| **Self-Knowledge** | Persistent ontology + teachable knowledge | ✅ Done |

### 🟠 P1: Documentation Updates (Completed This Session)

| Item | Status | Notes |
|------|--------|-------|
| **ARCHITECTURE.md** | ✅ Updated | Reflects actual implementation with status indicators |
| **FEATURES.md** | ✅ Created | Comprehensive feature list |
| **API-REFERENCE.md** | ✅ Updated | All actual endpoints documented |
| **GAPS.md** | ✅ Updated | This document, actionable priorities |

### 🟡 P2: Missing Core Features

| Item | Description | Location |
|------|-------------|----------|
| **Scheduler** | Background autonomous tasks | `scheduler/engine.py` |
| **Approval Workflow** | Dry-run + approval flow | `approval/engine.py` |
| **Guardrails** | Budget/rate limiting | `autonomy/guardrails.py` |
| **Policy Engine** | Action authorization | `policy/engine.py` |

### 🟢 P3: Developer Documentation

| Item | Description |
|------|-------------|
| **Scanner Guide** | How to add new discovery scanners |
| **Context Injection** | Keyword → discovery mapping logic |
| **Model Routing** | Complexity scoring algorithm |
| **Frontend Components** | Component library usage |

---

## Implementation Backlog (RAG/Memory Focus)

### Phase 22A: Ingestion Pipeline ✅ COMPLETE

**Goal**: Continuous telemetry collection into ChromaDB

```
journald → Events → Embeddings → ChromaDB (self_journald)
hwmon → Metrics → Embeddings → ChromaDB (self_hwmon)
```

**Implemented**:
- `ingestion/service.py` — Background service manager (singleton)
- `ingestion/journald.py` — Collect systemd journal ✅
- `ingestion/hwmon.py` — Collect hardware sensors ✅
- `index/chroma_index.py` — Upsert events ✅
- `dashboard/app.py` — Auto-start on app startup ✅
- `routes/settings.py` — API endpoints for start/stop/status ✅
- `routes/chat.py` — Telemetry context injection ✅

### Phase 22B: Discovery Persistence ✅ COMPLETE

**Goal**: Store discoveries with semantic embeddings

**Implemented**:
- `discovery/engine.py` — ChromaDB enabled by default ✅
- `discovery/engine.py` — `search()` uses ChromaDB semantic search ✅
- `routes/chat.py` — `get_discovery_context()` for semantic retrieval ✅
- Discoveries stored in `discoveries` collection with embeddings

**Note**: Discoveries are ephemeral (represent current state), so full persistence 
isn't needed. The semantic search over current discoveries is the key feature.

### Phase 22C: Document Indexing ✅ COMPLETE

**Goal**: Index Linux documentation for RAG

**Sources** (7,400+ documents):
- Man pages (7,359 pages)
- Arch Wiki (43 articles)
- Systemd, network, filesystem, security docs

**Implemented**:
- `rag/document_indexer.py` — Chunking, indexing, querying ✅
- `routes/settings.py` — API endpoints for index/query ✅
- `routes/chat.py` — Auto-inject docs context ✅
- Collection: `linux_docs`

### Phase 22D: Self-Knowledge System ✅ COMPLETE

**Goal**: Persistent ontology for system self-understanding

**Implemented**:
- `knowledge/self_knowledge.py` — Core knowledge store ✅
- Knowledge types: identity, hardware, config_rationale, relationships, roles ✅
- `bootstrap_identity()` — Auto-detect hostname, OS, CPU, RAM ✅
- `routes/settings.py` — API endpoints (teach, search, explain-config) ✅
- `routes/chat.py` — Self-knowledge is FIRST context injected ✅
- Collection: `self_knowledge`
- Backup: `~/.local/share/halbert/knowledge/self_knowledge.json`

### Phase 22E: WhyBrain UI ✅ COMPLETE

**Goal**: Universal UI for capturing rationale ("WHY" things exist)

**Implemented**:
- `ui/why-brain.tsx` — Brain icon with two states (grey=undefined, pink=defined) ✅
- `ui/why-overlay.tsx` — Full-screen overlay for editing explanations ✅
- `lib/api.ts` — `saveWhy()`, `getWhy()` API functions ✅

**Integrated into pages**:
- DiscoveryCard.tsx (all discovery types)
- Services.tsx (service rows)
- Storage.tsx (storage group headers)
- Network.tsx (interface rows)
- Containers.tsx (container cards)
- GPU.tsx (GPU cards)

---

## Phase History (from private docs)

| Phase | Status | Summary |
|-------|--------|---------|
| 1-3 | 📄 Planned | Original vision, partially implemented |
| 4 | 📄 Planned | Persona system (simplified to prompts) |
| 5 | 📄 Planned | Multi-model (implemented as Phase 21) |
| 6 | 📄 Planned | macOS port (not started) |
| 17 | ✅ Complete | Sharing tab |
| 18 | ✅ Complete | Config editor |
| 19 | 📄 Planned | Enhancement backlog |
| 20 | ✅ Complete | Component library |
| 21 | ✅ Complete | ReAct architecture, model routing |
| 22 | ✅ Complete | RAG/Memory enhancement |

---

## Next Steps

### Completed (Phase 22)
- ✅ ChromaDB memory system (conversations)
- ✅ Ingestion pipeline (journald/hwmon)
- ✅ Document indexer (man pages, Arch Wiki)
- ✅ Context injection (memory, telemetry, docs, self-knowledge)
- ✅ Self-Knowledge system (persistent ontology)
- ✅ WhyBrain UI (universal rationale capture)
- ✅ Documentation: Phase 22 docs in `docs/Phase22/`

### Next Priority (P2: Missing Core Features)
1. **Scheduler** — Background autonomous tasks (`scheduler/engine.py`)
2. **Approval Workflow** — Dry-run + approval flow (`approval/engine.py`)
3. **Guardrails** — Budget/rate limiting (`autonomy/guardrails.py`)
4. **Policy Engine** — Action authorization (`policy/engine.py`)

### Cycle Checklist
- [ ] Audit: Re-check codebase vs documentation
- [ ] Document: Update public docs for any gaps
- [ ] Build: Implement P2 features
- [ ] Repeat
