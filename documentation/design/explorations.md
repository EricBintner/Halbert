# Explorations — Design-to-Implementation Catalog

**Status:** Breadth-first catalog (2026-08-23). Every idea we could see, with the concrete code
seam it attaches to. **Curation is at §10** — nothing here is committed to until it lands there.
**Reads with:** [the-being.md](the-being.md) (the vision this serves) and
`.handoff/ROADMAP-2026-08-23.md` (the phased implementation plan — §A maps to Phases 0–4,
§B–E map to Phases 5–8, §F maps to Phase 0+2, §G is already wired, §H maps to Phase 6).

Convention: each exploration has an ID (`A1`, `B3`, …) for curation reference, the seam it
attaches to in the current codebase, and design options where they exist.

---

## A. The conversation core (the spine)

The product is the conversation. Two chat paths exist today and must become one.

### A1. Collapse to one conversation path
**Seam:** `dashboard/routes/chat.py` (3,914 lines — legacy, rich context injection, still has
live UI consumers) vs `dashboard/routes/agent.py` (736 lines — Phase 36 state machine, SSE,
**already wired to the Haloysius cognition tick** via `integrations/cognition_wiring.py`, and to
the wired context assembler via `context/`).
**Direction:** the agent path is the survivor — it's the one already holding the mind. Port the
legacy path's differentiating features (keyword→discovery injection, telemetry injection, failure
correlation, config-edit blocks, vision) into the state machine as handlers/context adapters,
then retire `chat.py` endpoint-by-endpoint. The old SidePanel chat tab swaps to the same SSE
backend as AgentPanel.
**Risk:** medium. The legacy path has live consumers; port features before cutting endpoints.

### A2. The message as a container
**Seam:** `components/agent/AgentChat.tsx`, `agents/events.py` (`StreamEvent.to_sse()`).
**Idea:** a message is not just text — it carries attachments: summoned modules (§B), evidence
links (§C4), proposed actions (approve/dismiss buttons), and the why affordance. Extend the SSE
event vocabulary rather than inventing a parallel channel: add `module_invoke`, `evidence_ref`,
`action_proposal` event types alongside the existing state/response events.
**Design option:** (a) LLM emits structured JSON actions in-band (like tool calls); (b) backend
post-processes the response and attaches payloads; (c) hybrid — LLM expresses intent, backend
validates/enriches with real data, frontend renders. **Leaning (c)** — the LLM should never be
trusted to fabricate a module's data or an evidence link.

### A3. One conversation, one store
**Seam:** `routes/conversations.py` (isolated per-conversation JSON files), Haloysius
`conversation/` + `memory_v2`, `conversation/summarization.py` (5-level hierarchical, already
built).
**Idea:** the user experiences *one ongoing conversation with their computer*, not a list of
chat sessions. History is one stream, summarized hierarchically as it grows (the summarization
cascade already exists). "New conversation" becomes "new day," not "new being."
**Open:** migration of existing per-file conversations; whether old threads remain addressable
("that thing we discussed last Tuesday" → retrieval, not a separate UI list).

### A4. Voice setting — implementation seam
**Seam:** `prompts/` (PromptBuilder, ContextInjector, AgentPromptBuilder — all wired in
`agent.py:95-102`), Haloysius continuity renderer.
**Idea:** voice = a prompt-layer + renderer-layer setting (`first_person` / `the_computer` /
`hybrid`). The self-model and ledger are voice-agnostic; only the render changes. Store in
`~/.config/halbert/being.yml` (new) alongside the proactivity dial.

---

## B. Module invocation — chat summons the dashboard

The signature mechanic of the physical design (the-being.md §3): as Halbert communicates, it
summons dashboard modules into a context region.

### B1. The module registry
**Seam:** `frontend/src/pages/*.tsx` (17 pages), `frontend/src/components/domain/`,
`frontend/src/components/agent/` (already modular: DiffBlock, ScanBlock, ToolExecutionCard,
PlanChecklist, ThinkingPanel).
**Idea:** a registry mapping `module_name → { component, data_fetcher, prop_contract,
standalone_route }`. Pages refactor into modules that render in two containers: standalone
(dashboard browsing) and summoned (context region in conversation). The agent/ components are
already shaped this way — the pattern exists.

### B2. Invocation protocol
Three options, complementary:
- **LLM-initiated:** model emits `show_module("storage", focus="/dev/sda1")` intent (A2 hybrid —
  backend validates against the registry, fetches data, streams `module_invoke` with payload).
- **Backend-initiated:** proactive findings (§D) always carry the module that explains them.
- **User-initiated:** the `modules ▾` palette — any module summonable on demand.
**Leaning:** all three, same registry, same rendering path.

### B3. Modules are live, not screenshots
**Seam:** existing discovery API (`routes/discovery.py`), editor (`routes/editor.py`).
Summoned modules are interactive: drill in, approve the proposed action, edit the config inline.
A summoned module is the dashboard page *in context*, not a static card. This is what makes
"demote the dashboard" lossless — nothing is removed, only re-containered.

### B4. Minimal module set for the slices
Don't refactor all 17 pages up front. The slices need only: **config-diff module** (exists:
ConfigEditor + DiffBlock), **drive-health module** (storage page subset), **vitals module**
(dashboard metrics subset), **evidence module** (log excerpt viewer — new, small). Curate the
rest later (§10).

---

## C. The why data model

The design law (the-being.md §2) needs schemas and stores.

### C1. Finding
```yaml
finding:
  id: f_<ulid>
  what: str                    # "two sshd drop-ins set PasswordAuthentication"
  category: config|storage|service|security|network|…
  severity: info|notice|important|critical
  consequence: str             # what happens if ignored — required, never empty
  evidence: [provenance_ref]   # §C4
  detected_by: watcher|sweep|scanner|user
  detected_at: timestamp
  status: open|snoozed|resolved|dismissed
```
**Seam:** new `findings` store — SQLite alongside the approval engine's storage, or a ChromaDB
collection. Leaning SQLite: findings are relational (status transitions, proposals link to them),
not semantic-search-first.

### C2. Proposal
```yaml
proposal:
  id: p_<ulid>
  finding_id: f_<ulid>
  action: str                  # human sentence: "remove PasswordAuthentication yes from 60-cloudimg.conf"
  tool_call: {tool: write_config, inputs: {…}}   # the executable form
  reasoning: str               # why this fix
  blast_radius: [str]          # what depends on the target (config edges, §E3)
  rollback_plan: str           # write_config gives backup+rollback for free
  status: pending|approved|rejected|applied|rolled_back
```
**Seam:** `approval/engine.py` already stores requests + decisions; proposals extend it rather
than parallel it.

### C3. Rationale store (why-so)
**Seam:** SourcePrep concepts (file-anchored, stale-flagged, status lifecycle) — via
`integrations/sourceprep_client.py`. The dead WhyBrain UI (`saveWhy` → nonexistent `/api/why`)
gets revived against this: every discovery card / config entry / module can carry "why does this
exist," persisted as a concept anchored to the path.
**Fallback:** if SourcePrep isn't running, a local YAML/JSON store with the same shape, synced
when it comes up.

### C4. Provenance references (why-trust)
```yaml
provenance_ref:
  type: log|snapshot|metric|config|memory
  locator: str   # journald cursor | snapshot id | metric window | path:lines | memory id
  summary: str   # one line, shown on hover
```
Every claim in a message can carry refs; the UI renders them as the why affordance (click →
evidence module §B4). This is the mechanical enforcement of the philosophy's "no hallucination
about system state."

### C5. The why affordance in UI
A consistent micro-affordance on every message/module/proposal: hover or click expands the four
whys. One component (`WhyChip.tsx`), fed by C1/C2/C3/C4. Small component, huge meaning-per-pixel.

---

## D. The proactive channel — plumbing

The sidebar that opens on its own. All the pieces exist in rough form; none are connected.

### D1. Event flow
```
trigger (watcher event | scheduled sweep | scanner | ingestion anomaly)
  → detector rule (§E1) 
  → finding (C1, with four whys)
  → gate: severity × category × dial (§D3) × quiet hours
  → if pass: push to surface (§D2) + record in ledger (worries_about / conflicted_about)
  → conversation opens with the finding + its module + its proposal
```

### D2. Transport
**Seam:** `routes/websocket.py` is a 37-line stub over a `ws_manager` broadcast; SSE already
works for agent streaming (`agent.py`); `hooks/useWebSocket.ts` exists.
**Options:** (a) flesh out the WebSocket manager for server→client push (findings, approvals);
(b) a dedicated SSE `/api/being/events` stream (simpler, one-directional, matches existing
streaming infra); (c) poll a `/api/findings?status=open` endpoint (ugly, works everywhere).
**Leaning (b)** — SSE for push, POST for actions (approve/snooze/dismiss). Tauri tray events ride
the same stream.

### D3. The gate
**Seam:** `autonomy/guardrails.py` (confidence thresholds, budgets, safe mode — already checked
on tool calls), `config/models.yml`-style YAML for settings.
Settings schema (new `being.yml`): `proactivity: off|quiet|balanced|assertive`,
`category_overrides: {security: assertive, storage: quiet}`, `quiet_hours: "23:00-08:00"`,
plus per-finding snooze. Severity mapping is a property of each detector rule (§E1).

### D4. The morning report (the first ritual)
**Seam:** `scheduler/autonomous_tasks.py` (health check every 6h exists), summarization cascade.
A scheduled job: consolidate the last 24h (findings, changes, telemetry anomalies, approvals
awaiting) into a digest message delivered at a configured time — the user's first ENGAGED moment
of the day. This is the Deep Thinker made visible, and the cheapest "alive" behavior to build.

### D5. Ignore semantics
Snoozed findings decay back to open after N days if the underlying condition persists (re-check
on sweep). Dismissed = user said "not a problem" → becomes a rationale entry ("user knows;
intentional") via C3. The being learns what's noise *for this user*.

---

## E. The config physiology brain — v1 detector catalog

The differentiator. Each detector is a small rule over the parsed config tree (`config/parser.py`
already canonicalizes ini/systemd/yaml/json; `config/snapshot.py` + `config/watcher.py` give
freshness; `config/edge_extractor.py` gives dependency edges for blast-radius).

### E1. Detector shortlist (pick 3–5 for v1)
| Detector | What it catches | Severity | Data needed |
|---|---|---|---|
| **Drop-in conflict** | `sshd_config.d/*.conf` disagreeing with each other / main file | important | parser + precedence rules (E2) |
| **fstab phantom** | fstab entry references UUID/device that no longer exists | critical | snapshot + discovery (disks) |
| **Dangling reference** | nginx/apache/unit file references missing cert/script/path | important | parser + fs existence check |
| **Duplicate knob** | same setting in 2+ files with different values (PATH, aliases, sysctl) | notice | parser + cross-file index |
| **Permissions hygiene** | world-readable private keys, `.ssh` perms, secrets in configs | critical | fs stat (+ SourcePrep `detect_secrets`) |
| **Orphan config** | config for uninstalled package | info | parser + package list (dpkg/brew) |
| **Cron/unit phantom** | scheduled job calls missing script | notice | parser + fs check |

### E2. Precedence resolution engine
The sleeper capability — "what is *actually* set?" systemd drop-in ordering, `sshd_config.d/`
glob order, shell rc ordering (`.zshenv` → `.zprofile` → `.zshrc`), `/etc/paths.d`, sysctl.d.
Without this, drop-in conflict detection produces false positives. Build as a library over
`config/parser.py` output; it also directly powers the conversation ("what's my effective SSH
config?" is a one-call answer).

### E3. Blast-radius
**Seam:** `config/edge_extractor.py` (Phase 3: 6 extractors, feeds SourcePrep external edges) +
`integrations/sourceprep_client.py`. For a proposed change: which services/units/configs depend
on the target path. v1 can be shallow (direct edges only); deep traversal comes with SourcePrep's
graph.

### E4. Propose-through-approval (already built)
**Seam:** `tools/write_config.py` — backup, unified-diff dry-run, rollback, policy gate, audit
trail all exist. `approval/engine.py` + Approvals page exist. The brain's job is only to produce
good proposals (C2); the action machinery is done.

### E5. When detectors run
- **On watch event:** `config/watcher.py` fires → re-snapshot → detectors for affected domain.
- **Scheduled sweep:** all detectors, daily (morning report input) + on dashboard startup.
- **On ask:** user queries config state → run relevant detectors live for freshness.

---

## F. Awareness substrate — the SourcePrep adapter

Verified feasible with a thin adapter (foundational research RQ2). Concretely:

### F1. The synthesized system tree
A directory Halbert maintains: `~/.local/share/halbert/system-tree/` containing
`config/` (snapshots as canonical text), `services/` (unit manifests), `logs/` (recent excerpts),
`discovery/` (scanner JSON), `identity.md` (self-knowledge bootstrap). Registered as one
SourcePrep project with custom `include_globs` (`.conf, .service, .timer, .yml, .yaml, .json,
.ini, .cfg, .plist, no-extension`).
**Refresh:** `config/watcher.py` events → re-snapshot → touch tree → SourcePrep file watcher
picks it up. Log excerpts refresh on a timer.

### F2. What we use vs. what we skip
**Use:** embeddings + semantic search over the tree (replaces the tangled dual-RAG for system
context), FTS5, concepts (rationale store C3), observations (cross-session ops memory).
**Skip:** symbol graph, `prep_impact` (code-centric), LOD compression, role projection.

### F3. Isolated instance vs. shared daemon
**Options:** (a) Halbert runs its own embedded SourcePrep (library mode, no daemon); (b) talks
to the user's daemon over MCP/HTTP if present, else embedded. **Leaning (a) for v1** — fewer
moving parts, no port conflicts; (b) becomes the power-user path later.

### F4. What this replaces
`rag/pipeline.py` (deprecated but alive in CLI eval tooling — keep for eval, off the chat path),
the self-knowledge ChromaDB collections (`self_knowledge`, `self_conversations` migrate to
memory_v2 + observations), keyword→injection heuristics in `chat.py` (replaced by semantic
retrieval over the system tree).

---

## G. Mind spine — Haloysius wiring status

Mostly built in Phases A–E; what's left is depth.

### G1. Already wired
`integrations/app_seam.py` (AppSeam registration), `cognition_wiring.py` (tick + event mapper),
`haloysius_memory_adapter.py`, `sourceprep_retrieval_backend.py`, `state_trackers.py`,
`system_event_mapper.py`. The agent path calls `advance_turn` (REFLECTING state).
**Verify on the target host:** the full stack booting with Haloysius installed (never yet
boot-tested end-to-end on the Ubuntu host — the foundational research flagged this).

### G2. The missing predicates (WP-8)
`believes, wants, worries_about, conflicted_about` don't exist in the continuity ledger yet.
These are exactly what the being needs for worry-as-state. **Options:** (a) contribute upstream
to Haloysius (they're planned as WP-8 there); (b) implement in Halbert's app-seam layer as
custom predicates. **Leaning (a)** — they belong in the core's ledger vocabulary; we co-design.

### G3. The unprompted tick (inner life, cheap version)
**Seam:** `scheduler/` + `cognition_wiring.py`. A scheduled job calls the tick with no user
message: decay, consolidate, review findings, update worry states, prepare the morning report.
The being keeps living between conversations. v1: hourly tick + daily report. This is the
highest meaning-per-line change in the whole program.

### G4. Memory consolidation
memory_v2 has consolidation/decay; the summarization cascade handles conversation growth.
One question to resolve: conversation history (memory_v2) vs. ops findings (SQLite C1) vs.
rationale (concepts C3) — three stores, clear ownership: *what happened to us* (memory_v2),
*what needs attention* (findings), *why things are* (concepts).

---

## H. Settings surface for the being

### H1. New `being.yml` config
```yaml
voice: first_person            # first_person | the_computer | hybrid
proactivity: balanced          # off | quiet | balanced | assertive
category_overrides: {}         # {security: assertive}
quiet_hours: "23:00-08:00"
morning_report: "08:30"        # or off
purpose: ""                    # free text v1; starter set later
```
**Seam:** `config/models.yml` pattern; `routes/settings.py` gains a `being` section;
Settings UI gains a "Being" tab (voice picker, proactivity dial, quiet hours, purpose).

### H2. The Settings split
Settings today mixes *app* configuration (models, endpoints) and *machine* configuration. The
being's preferences (voice, proactivity, purpose) are a third kind: **relationship settings**.
They get their own tab — the user is configuring how they live with their computer, not the app.

---

## I. The ambient surface

### I1. Tray indicator
**Seam:** Tauri v2 tray APIs (the app already ships a Tauri shell). States: calm / needs-attention
/ urgent — driven by open findings' max severity. Click → ENGAGED. Badge count optional.
Web fallback: a persistent header chip in the dashboard.

### I2. Engage surfaces
- Desktop panel (the SidePanel evolved: conversation spine + context region)
- CLI: `halbert` opens a terminal conversation against the same backend (thin client)
- Hotkey via Tauri global shortcut

### I3. The layout refactor
**Seam:** `Layout.tsx` (nav sidebar + SidePanel + global ConfigEditor today). Target: the
conversation spine becomes the persistent element (replacing SidePanel's chat tab), the main
region becomes the context region (summoned modules) or the dashboard grid (browsing mode
toggle). The 17-route nav collapses behind the dashboard toggle + module palette.

---

## J. Time & rituals

### J1. Sessions as days
Continuity segments per day; "new conversation" = new segment, same being. The conversation
list UI becomes a timeline, not a session picker.

### J2. Ritual schedule (all optional, all configurable)
morning report (daily), backup review (weekly), storage audit (monthly), config hygiene sweep
(daily, feeds findings). Each is a scheduled proactive message with its module attached.

### J3. Anniversaries & milestones
"I've been running 400 days." "We migrated to bcachefs six months ago — zero issues since."
Cheap (temporal layer), high warmth. Post-MVP but keep in view.

---

## 10. Curation — what lands, in what order

### Slice 1 (proactive config worry) needs:
| ID | What | Status |
|---|---|---|
| E1 (3 detectors) | drop-in conflict, fstab phantom, permissions hygiene | build |
| E2 | precedence resolution (minimal: sshd + systemd) | build |
| C1/C2 | findings + proposals stores | build (extend approval engine) |
| D1/D2/D3 | event flow + SSE push + gate | build (flesh out ws stub → SSE) |
| B1/B2 | module registry + invoke protocol (config-diff module only) | build |
| E4 | propose-through-approval | **exists** (write_config + approval engine) |
| E3 shallow | direct dependency edges | **exists** (Phase 3 edge_extractor) |
| A2 | message attachments (module_invoke, action_proposal events) | build |

### Slice 2 (reactive "how are you") needs:
| ID | What | Status |
|---|---|---|
| F1/F2/F3a | system tree + SourcePrep embedded + retrieval | build (thin) |
| G3 | scheduled tick (hourly) | build (small) |
| C4 | provenance refs on claims | build (format + renderer) |
| B4 | vitals + evidence modules | build (small) |
| A4/H1 | voice setting + being.yml | build (small) |

### Immediately after (the "make it feel whole" batch):
A1 (collapse chat paths), D4 (morning report), C3 (rationale store + revive WhyBrain), C5
(WhyChip), G2 (predicates upstream), D5 (ignore semantics).

### Later / keep in view:
B3 full interactivity for all modules, I3 full layout refactor, F4 completion (dual-RAG fully
retired), J3, society of beings, migration/death, attention-learning loop.

### Explicitly cut / don't build:
- No new dashboard pages. No new chat backends. No third memory store beyond the G4 ownership
  split. No bespoke `/api/why` (concepts replace it). No WebSocket investment (SSE suffices).
- `rag/pipeline.py` stays only for CLI eval; never returns to the chat path.

---

*This catalog is the menu. Slice planning (task-level breakdowns with acceptance checks) happens
per-slice in `.handoff/` when a slice is picked up.*
