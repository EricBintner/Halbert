# Halbert Features

A feature list corrected against the code on 2026-09-02 (SONNET-05 dispatch,
`RAG-*`/doc-resync task). The previous version of this document described
the system as it stood in December 2025 — a ChromaDB-backed sidebar
assistant with a three-tab Settings page. Most of that architecture has
since been replaced; this pass rewrites each section against what is
actually in the tree today, and marks anything backend-only or unwired
explicitly rather than presenting it as a working feature.

---

## Platform Support

| Platform | Status | Notes |
|----------|--------|-------|
| **Linux** | Full support | Primary sysadmin variant, all discovery scanners and route modules |
| **macOS** | Full support | Home and sysadmin variants both ship; App Store (sandboxed) and direct-distribution (Pro) channels — see `documentation/legal/APP-STORE-DISTRIBUTION-STRATEGY.md` |
| **Windows** | Not supported | No Windows-specific code anywhere in the tree; WSL was never implemented |

---

## Dashboard Pages

The pages below are still, broadly, what the December-2025 doc described —
system inventory pages backed by discovery scanners, each with an
AI-assisted troubleshooting affordance via the chat surface (see "Chat
System"). This section is not re-verified route-by-route in this pass;
what changed materially is the Settings page (rewritten below) and the
overall shell around these pages (also below), not each individual
page's own content.

### Dashboard, Services, Storage, Backups, Security, Network, Sharing, Containers, GPU, Apps, Development, Approvals
Per-page system inventory and control surfaces, each reading from the
discovery scanner for its domain (see "Discovery System" below) and
exposing controls gated behind the approval workflow for anything
destructive.

### Settings
**Application configuration**, reorganized into five sections and eleven
tabs (`pages/Settings.tsx`, lazy-mounted — each tab's code and data load
only on first visit):

| Section | Tabs |
|---|---|
| Personality & Identity | Identity & Voice, Devices |
| Intelligence | Models & Providers, Knowledge |
| System & Security | Tool Permissions, Alert Rules, Trust Boundary, Vision, Audio & Voice |
| General | System Info, About |
| Developer | Debug |

- **Models & Providers**: configures four model slots — `chat_model`,
  `specialist_model`, `vision_model`, `secure_model` — each an endpoint +
  model pair, resolved per turn by `TierRouter` (`model/tier_router.py`)
  against the active variant's capabilities, not the three-slot
  Guide/Specialist/Vision scheme the December-2025 doc described.
- **Knowledge**: the corpus/retrieval status tab — see "Document
  Retrieval" below for what it actually indexes today.
- **Tool Permissions** / **Alert Rules** / **Trust Boundary**: the policy
  engine, alert rule editor, and MCP/redaction boundary controls (see
  "Autonomy & Safety").
- **Debug**: a toggle (`Switch`, not a footer button) exposing request
  counts, token usage, response times, and model-routing decisions in the
  console.

### AI Rules
Custom guardrails with priority levels and categories, editable from the
Trust Boundary / Tool Permissions tabs — unchanged in substance from the
December-2025 description, moved into the new tab structure above.

---

## Chat System

The chat surface is no longer a dismissible sidebar. The current shell
(`components/shell/HostShell.tsx`) is a panel layout — the agent chat
(`components/agent/AgentChat.tsx`) as one panel, a context stage, and a
domain rail for navigating between dashboard pages — with a presence
indicator (`PresencePill`) rather than the old instance switcher. Terminal
sessions the agent opens appear inline in the chat as terminal tiles
(`components/agent/TerminalTile.tsx`, `InlineTerminals.tsx`), in addition
to the standalone Terminal page (below).

### AI Assistant
- **Contextual awareness**: the agent knows the current dashboard page and
  visible items.
- **@Mentions**: reference specific discovered items in a message.
- **Conversation history**: persisted turns (SQLite — `threads`, `turns`,
  `receipts` — not the December-2025 doc's ChromaDB-backed conversation
  store, which is gone).
- Inline terminal tiles for commands the agent runs during a turn.

### Model Routing
Automatic selection across the four model slots above, scored by query
complexity (`intake/pipeline.py`) and gated by which capabilities the
running variant/hardware actually has (`capabilities.py`) — for example,
`secure_model` is only ever used on variants where a secure model
capability is both allowed and configured; Apple Intelligence-backed
endpoints are only offered where the on-device bridge is actually running.
Debug mode surfaces the routing decision for each turn.

### Vision Model Support
Image analysis via the `vision_model` slot — paste, drag-and-drop, or
screen-capture an image into a turn for the agent to analyze.

### Document Retrieval
**Corrected from the December-2025 "ChromaDB Document RAG" section.**
Two retrieval systems exist in the tree today, and only one still feeds
the agent:

- **Current**: SourcePrep/CodeIndex — a hybrid BM25 + embedding retrieval
  backend over a staged corpus (system docs, man pages, Arch Wiki, BSD
  handbook, vendor docs — see `documentation/RAG-DATA-SOURCES-2026-08-24.md`
  for the full source list and licensing). This is what the agent actually
  queries (`integrations/sourceprep_retrieval_backend.py`).
- **Legacy, backend-only, not reachable from the UI**: the ChromaDB-based
  `linux_docs` collection and its `/api/settings/docs/*` endpoints
  (stats/index/query) still exist in `routes/settings.py`, and the
  `pages/Memory.tsx` page that displayed it is not routed anywhere in
  `App.tsx` — it is dead code, not a reachable feature. Nothing in
  `agents/` reads from `linux_docs`. This is `RAG-21`, an open decision
  (retire the legacy indexer, per the state-of-work audit's default) —
  see `.handoff/DISPATCH-2026-09-01-FOUNDER-DECISIONS.md`.

### Self-Knowledge System (Why Brain)
**Still live**, unlike the retrieval system above. `components/ui/why-brain.tsx`
is wired into several discovery pages (GPU, Services, Storage, Containers,
Network) as a clickable brain icon; clicking it records or shows a
user-authored explanation for why an item is configured a certain way,
served by `get_self_knowledge()` (`routes/settings.py`) and injected into
future chat context. The December-2025 doc's separate "Self-Knowledge
System (Ontology)" and "Why Brain UI" sections described the same feature
twice with slightly different framing; merged here.

### Telemetry Ingestion
journald and hwmon collection, injected into chat context on relevant
keywords — the mechanism is unchanged from the December-2025 description;
its storage backend (formerly "indexed in ChromaDB") was not
independently re-verified in this pass.

### Command Execution
Inline "Run" button on AI-suggested code blocks in chat; output displayed
inline and saved to conversation history.

---

## Config Editor

### AI-Assisted Editing
Edit system configuration files with AI help — Monaco editor, SEARCH/REPLACE
diff proposals, accept/reject, automatic backup before save
(`routes/editor.py`, `/api/editor/file`).

### Supported Config Types
Netplan, Samba, NFS exports, SSH config, systemd units, or any text config
file.

---

## Terminal

### Terminal Access
A dedicated Terminal page (`pages/Terminal.tsx`) plus inline terminal
tiles the agent opens during a chat turn — not the December-2025 doc's
"tab switching between Chat and Terminal" (that toggle no longer exists;
chat and terminal are simultaneously visible panels/tiles, not exclusive
tabs).

---

## Debug Mode

See "Settings" above — Debug is now a Settings tab (a `Switch` toggle),
not a sidebar-footer control. It shows request counts, token usage,
response times, and model-routing decisions, and persists across reloads.

---

## Discovery System

### Automatic System Scanning
Discovery scanners (`halbert_core/halbert_core/discovery/`) collect and
catalog system components — disks, network interfaces, services, backups,
security posture, packages — independently of the dashboard route modules
that expose GPU, Containers, and Development data. The December-2025 doc's
scanner table listed `gpu.py`, `containers.py`, and `development.py`
alongside genuine discovery scanners; those three are **dashboard route
modules** (`dashboard/routes/gpu.py`, `routes/containers.py`,
`routes/development.py` — API surfaces with their own live probes, e.g.
`nvidia-smi`/`rocm-smi` for GPU), not entries in the scanner registry. The
full current scanner and route-module lists were not each individually
re-enumerated in this pass; anyone updating this section should read
`halbert_core/halbert_core/discovery/` for the scanner registry and
`dashboard/routes/` for the route modules directly, since both are large
enough to drift again quickly.

---

## Backend API

**Corrected from the December-2025 "Core Endpoints" table**, which listed
eight paths that do not exist on the current API surface (`/api/chat/send`,
`/api/chat/config`, `/api/discovery/{type}`, `/api/settings/endpoints`,
`/api/settings/assign/{role}`, and others). A non-exhaustive list of the
actual current core endpoints, verified against `dashboard/routes/*.py`
and their mount prefixes in `dashboard/app.py`:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/agent/message` | POST | Send a chat/agent turn |
| `/api/agent/timeline` | GET | Chat history, one page of turns |
| `/api/agent/state/{session_id}` | GET | Current turn/session state |
| `/api/discoveries/` | GET | List discoveries (note: `/discoveries`, plural — not `/discovery`) |
| `/api/discoveries/{type}` is not a route — discoveries are queried via `/api/discoveries/` with filters, and `/api/discoveries/search` | | |
| `/api/settings/ai-rules` | GET/POST/PUT/DELETE | Custom AI rules |
| `/api/settings/docs/*` | GET/POST | Legacy ChromaDB doc index — backend-only, see "Document Retrieval" |
| `/api/terminal/exec` | POST | Run a one-shot command |
| `/api/terminal/sessions` | GET/POST | Terminal session management |
| `/api/editor/file` | GET/POST | Read/write config files |
| `/api/services/{service_name}/control` | POST | Service start/stop/restart |
| `/api/llm/config` | GET/PUT | Model/endpoint configuration |

This table is illustrative, not exhaustive — the route modules under
`dashboard/routes/` (40+ files) each own their own path space; consult
them directly rather than trusting a hand-maintained list to stay current.

---

## Configuration

### File Locations
| Path | Purpose |
|------|---------|
| `~/.config/halbert/models.yml` (or `~/Library/Application Support/Halbert/` on macOS) | Model/endpoint configuration |
| `~/.config/halbert/being.yml` | Identity, voice, variant, and persona configuration |
| `~/.config/halbert/ai_rules.yml` | Custom AI rules |
| `~/.halbert/conversations.db` | Chat history (SQLite: threads, turns, receipts) |

The December-2025 doc's `models.yml` example (`orchestrator`/`specialist`/
`vision` top-level keys) is stale — the current schema uses the four
`SLOTS` named above (`chat_model`, `specialist_model`, `vision_model`,
`secure_model`) under a `saved_endpoints` + per-slot structure; see
`model/llm_config.py` for the authoritative shape rather than a
hand-copied example here.

---

## Autonomy & Safety

### Policy Engine
Tool execution permissions — default allow/deny, per-tool overrides,
editable from Settings › Tool Permissions.

### Guardrails
Confidence thresholds, resource budgets, and a safe mode that pauses
autonomous operations, editable from Settings › Trust Boundary.

### Anomaly Detection, Recovery Playbooks, Dry-run Simulation
**Backend-only — no UI calls any of these endpoints.** Verified by
grepping the frontend `src/` tree for every one of these routes'
paths: zero matches. The backend logic is real and exists
(`dashboard/routes/settings.py`):
- Anomaly detection: `GET /api/settings/anomaly/status`, `POST /api/settings/anomaly/check` — CPU spikes, memory growth, repeated failures, error-rate tracking.
- Recovery playbooks: `GET /api/settings/recovery/status`, `POST /api/settings/recovery/rollback`, `/restart-service`, `/alert` — config rollback, service restart, alerting, audit-logged.
- Dry-run simulation: `POST /api/settings/simulate/file-write`, `/command`, `/service-restart`, `/tool` — preview an action's effect before running it.

None of these are reachable from the dashboard today. Treat this section
as a backend capability inventory, not a shipped feature, until a
frontend surface calls them.

### Approval Workflow
Human-in-the-loop for risky operations — approval requests for tool calls
below a confidence threshold, dashboard approval page, approve/reject with
reason.

---

## Real-time Features

### WebSocket Streaming
Live updates without polling — system status broadcasts, approval
notifications, scheduler job status, chat token streaming, auto-reconnect.

### Scheduler
Background job scheduling via APScheduler with SQLAlchemy persistence.

---

## Running Halbert

### Development Mode
```bash
make dev
```
Starts the FastAPI backend and Vite dev server with hot reload.

### Production Build
```bash
make build
make serve
```

### Access
- Dashboard: http://localhost:8000
- API Docs: http://localhost:8000/docs

---

## Planned / Partial

The three sections below describe work that is partially real and
partially still aspirational, unchanged in kind from the December-2025
doc's framing — kept as directional statements, not verified feature
lists.

### Multi-Session & Remote Host Management
The underlying primitive is real: `dashboard/routes/instance.py` and the
`HALBERT_PERSONA_ID`/variant system distinguish which machine an instance
identifies as, and peer pairing (`routes/peers.py`) exists for
machine-to-machine connections. The multi-tab session-switcher UI this
section describes, and remote tool-execution streaming across that UI, are
not built.

### Configuration as Physiology & Hidden Rules Discovery
Not built as a distinct engine. Config file discovery and editing exist
(see "Config Editor" and "Discovery System" above); the deeper
hygiene/conflict-audit and impact-analysis framing this section describes
does not exist as shipped functionality.

### macOS Editions (Pro & Free)
Real distinction, described in `documentation/legal/APP-STORE-DISTRIBUTION-STRATEGY.md`
— the licensing/distribution strategy is drafted; some elements (bundle
identifiers, the exact feature gate between editions) are still open
founder decisions (`FDR-02`/`FDR-03` in
`.handoff/DISPATCH-2026-09-01-FOUNDER-DECISIONS.md`), not yet fully
implemented as two shipping builds.
