# Halbert as an MCP Server — Design Research & Opportunities

**Date:** 2026-08-28
**Status:** Blue-sky design research — initial planning
**Worktree:** `feat/halbert-mcp` at `~/.config/superpowers/worktrees/Halbert/halbert-mcp`
**Companion doc:** `HALBERT-MCP-TRUST-BOUNDARY-RESEARCH-2026-08-28.md` (small-scope, hardest-part research)

---

## 1. The Premise

Halbert currently lives behind a FastAPI dashboard (`dashboard/app.py`). The agent
state machine, discovery scanners, findings/proposals stores, being config, and
proactive event bus are all wired into that HTTP server. To reach Halbert, you
open the dashboard in a browser or hit its REST endpoints.

But the world is moving toward MCP (Model Context Protocol). WarpCLI, Claude
Code, Devin CLI, Cursor — they all speak MCP. If Halbert exposed itself as an
MCP server, any of these clients could ask "how are you doing?" and get a
grounded answer, or "approve proposal X" and have it applied, without opening
the dashboard.

The question is: **what does Halbert-as-MCP look like, and what are the
opportunities and risks?**

---

## 2. What Halbert Has Today (Building Blocks)

### 2.1 Discovery Engine — Runtime State

The discovery engine (`discovery/engine.py`) is a scanner registry that probes
the live system:

| Scanner | Type | What it produces |
|---------|------|-----------------|
| `BackupScanner` / `TimeMachineScanner` | BACKUP | Backup status, last backup time, destination |
| `ServiceScanner` / `LaunchdScanner` | SERVICE | Running services, loaded units, failed units |
| `StorageScanner` / `MacStorageScanner` | STORAGE | Filesystems, disk usage, mount points |
| `NetworkScanner` / `MacNetworkScanner` | NETWORK | Interfaces, routes, connections |
| `SecurityScanner` / `MacSecurityScanner` | SECURITY | Firewall, SSH, open ports, sudo config |
| `SharingScanner` | SHARING | File sharing, screen sharing, remote login |
| `HomebrewScanner` / `HomebrewAppScanner` / `MacAppStoreScanner` | PACKAGE | Installed packages, outdated |
| `MacThermalScanner` | HARDWARE | CPU temp, fan speed, thermal pressure |

Each scanner extends `BaseScanner` (`discovery/scanners/base.py`) and implements
`scan() -> List[Discovery]`. The engine aggregates results, stores them in
ChromaDB, and exposes query methods (`get_by_type`, `get_by_id`, `scan_all`).

**This is the runtime state layer.** It's what makes Halbert "the computer" —
it can see its own disk usage, running services, network state, thermal
pressure. No other tool in the stack does this.

### 2.2 SourcePrep — Structural Intelligence

Two SourcePrep projects on the daemon at `:8400`:

| Project | ID | Path | Scope |
|---------|-----|------|-------|
| `Halbert` (source code) | `aaa78a44-...` | `/Volumes/4TB-BAD/Halbert` | 886 files, 8175 nodes — the codebase |
| `halbert` (host + knowledge) | `735a592e-...` | `~/.local/share/halbert/sourceprep` | 282 files, 85288 nodes — config tree + RAG corpus |

The second project is the one relevant to MCP. It indexes:
- **`host/`** (40 files): redacted snapshots of `sshd_config`, `hosts`,
  `LaunchAgents/`, `LaunchDaemons/` — staged by `register_host_project.py`
- **`knowledge/`** (242 files): arch wiki, man pages, homebrew docs, tldr, etc.

Verified working: `prep_search` with `project_id: "735a592e-..."` returns real
results — both documentation and actual config files from this machine.

**This is the structural intelligence layer.** It knows what config files exist,
how they relate, what docs cover a topic. It's already exposed as an MCP server
(the `prep` MCP that WarpCLI/Claude Code/Devin can call).

### 2.3 Agent Infrastructure — The Being

Phases 5-8 built the "being" layer:
- **Findings/Proposals** (`findings/`): SQLite-backed stores for detected issues,
  proposed changes, approval/rollback lifecycle
- **Being Config** (`config/being_config.py`): voice, proactivity dial, quiet
  hours, morning report, purpose
- **Proactive Channel** (`proactive/`): event bus, gate, morning report
  generator, detector runner
- **Reactive Slice** (`agents/state_machine.py`): "how are you?" flow with
  grounded responses, provenance citations, module invocation
- **Module Registry** (`modules/registry.py`): 4 context modules (config-diff,
  vitals, drive-health, evidence) with data fetchers behind `dashboard/routes/modules.py`

**This is the cognition layer.** It's what makes Halbert "a being" rather than a
monitoring dashboard.

### 2.4 Module Data Fetchers — Already an API Surface

`dashboard/routes/modules.py` already exposes module data via REST:
- `GET /api/modules` — list available modules
- `GET /api/modules/{name}/data?...` — fetch module data (vitals = psutil,
  drive-health = partitions, config-diff = file read with allowlist,
  evidence = log/journald search)

These are the same data an MCP server would expose. The allowlist enforcement
(`_resolve_allowed_path` in `modules.py:52-70`) is already built — paths outside
`/etc`, `~/.config`, and the host staging dir are rejected with 403.

---

## 3. The Two-Server Architecture

```
WarpCLI / Claude Code / Devin CLI
    |
    +-- MCP: prep (SourcePrep)          <-- structural intelligence over files
    |       queries project 735a592e for config/docs/knowledge
    |
    +-- MCP: halbert (NEW)              <-- runtime state + agent actions
            |
            +-- tools:
            |     get_vitals            -> psutil (CPU, mem, disk, net)
            |     get_discoveries       -> DiscoveryEngine.scan_type()
            |     get_findings          -> FindingStore.list_open()
            |     get_proposals         -> ProposalStore.list_pending()
            |     approve_proposal      -> ProposalStore.approve() + apply
            |     get_config_file       -> direct read (with allowlist)
            |     run_scanner           -> DiscoveryEngine.scan_type()
            |     get_being_config      -> BeingConfig
            |     get_proactive_events  -> ProactiveEventBus.recent()
            |
            +-- internally calls SourcePrep HTTP API (:8400)
                when it needs structural context
                (does NOT chain MCP-to-MCP)
```

### Key design principle: Server-to-server is HTTP, not MCP

Halbert-as-MCP does NOT call SourcePrep through the MCP protocol. It calls
`http://localhost:8400` directly — exactly like `register_host_project.py`
already does. MCP is a client-to-server protocol. Server-to-server is just
normal API calls.

This means:
- **WarpCLI** sees two MCP servers: `prep` and `halbert`
- **Halbert MCP** sees one HTTP API: SourcePrep at `:8400`
- **No MCP chaining, no weird recursion**

### What each MCP server owns

| Concern | prep MCP | halbert MCP |
|---------|----------|-------------|
| "What config files exist?" | YES (semantic search over host/ scope) | no |
| "How do these files relate?" | YES (trace graph, edges) | no |
| "What docs cover launchd?" | YES (knowledge/ scope) | no |
| "What's my CPU load right now?" | no | YES (psutil) |
| "What services are running?" | no | YES (DiscoveryEngine) |
| "What findings are open?" | no | YES (FindingStore) |
| "Approve proposal X" | no | YES (ProposalStore) |
| "What does sshd_config say?" | structure only (redacted) | YES (direct read, allowlisted) |
| "Read this log file" | no | YES (evidence module fetcher) |

---

## 4. Opportunities

### O1. Any MCP client becomes a Halbert interface

WarpCLI, Claude Code, Cursor, Devin — they all get Halbert as a tool. You could
ask Claude Code "how's the system doing?" and it would call `halbert.get_vitals`
and `halbert.get_findings`, then answer in Halbert's voice (if we expose being
config). No dashboard needed.

### O2. Halbert becomes composable with other MCP servers

A client could combine `prep` (codebase structure), `halbert` (runtime state),
and `github` (issues/PRs) in a single conversation. "Is there a config issue
that correlates with the failing CI test?" — the client queries prep for the
config, halbert for the runtime state, and github for the failing test.

### O3. The dashboard becomes optional, not required

Right now the dashboard is the only interface. With an MCP server, the
dashboard becomes one consumer among many. The agent infrastructure (state
machine, findings, proposals) is already client-agnostic — it's behind FastAPI
routes, but the underlying stores and engines don't depend on HTTP.

### O4. Proactive push via MCP resource subscriptions

MCP supports resource subscriptions. Halbert could expose its proactive event
bus as a subscribable resource — clients get notified when a new finding is
detected, without polling. (This depends on MCP client support for
subscriptions, which is still evolving.)

### O5. Cross-machine Halbert

If Halbert MCP runs on multiple machines (your Mac, the N150 home server, a
remote Pi), a single MCP client could talk to all of them. "How's every machine
doing?" would fan out to multiple Halbert MCP servers. This aligns with the
home-automation multi-instance design (`HOME-AUTOMATION-DESIGN-2026-08-27.md`).

### O6. Scoped access for different clients

Different MCP clients could get different tool sets. WarpCLI gets read-only
tools (get_vitals, get_findings). The Halbert dashboard (if it becomes an MCP
client) gets write tools (approve_proposal, run_scanner). A CI bot gets only
health-check tools. This is MCP's permission model, not something we build.

---

## 5. Risks & Open Questions

### R1. The redaction trust boundary (THE HARD PART)

SourcePrep indexes redacted config files. Halbert-as-MCP would need unredacted
access to be useful ("what port is sshd on?" requires reading the actual value).
But if Halbert MCP exposes raw config reads, any MCP client can read secrets.

**This is the most challenging part of the entire MCP effort.** It has its own
research document: `HALBERT-MCP-TRUST-BOUNDARY-RESEARCH-2026-08-28.md`.

### R2. MCP protocol maturity

MCP is still evolving. Tool definitions, resource subscriptions, streaming —
the spec is moving. We'd need to pick a server implementation (Python SDK?
TypeScript SDK? Raw stdio?) and accept that the protocol may shift under us.

### R3. Process model

The dashboard is a long-running FastAPI server. An MCP server can be:
- **stdio-based** (launched by the client, short-lived) — simplest, but can't
  share state with the dashboard
- **HTTP/SSE-based** (long-running daemon) — shares state with dashboard, but
  needs a port and lifecycle management
- **Hybrid** (stdio wrapper that proxies to the HTTP daemon) — best of both?

### R4. State sharing with the dashboard

If the MCP server and the dashboard are separate processes, they need to share:
- DiscoveryEngine state (in-memory, ChromaDB-backed)
- FindingStore / ProposalStore (SQLite — file-based, shareable)
- ProactiveEventBus (in-memory ring buffer — NOT shareable across processes)
- BeingConfig (file-based — shareable)

The SQLite stores are fine. The in-memory state (event bus, discovery cache) is
not. Options: (a) MCP server is a thin client of the dashboard's REST API,
(b) MCP server shares the same process as the dashboard, (c) move in-memory
state to a shared store (Redis, SQLite).

### R5. Tool surface bloat

How many tools does Halbert MCP expose? Too few and it's useless; too many and
clients get confused (MCP clients have token budgets for tool descriptions).
Need to curate the tool set carefully — maybe 8-12 tools, not 50.

### R6. Authentication

MCP doesn't have a built-in auth model for stdio servers. HTTP/SSE servers can
use bearer tokens. If Halbert MCP exposes write actions (approve_proposal,
run_scanner), we need auth. Who authenticates? How are tokens issued?

---

## 6. Proposed Tool Surface (Draft)

| Tool | Input | Output | Risk |
|------|-------|--------|------|
| `get_vitals` | `{timeframe?}` | CPU, mem, disk, net, temp | low (read-only) |
| `get_discoveries` | `{type?, scanner?}` | List of Discovery objects | low (read-only) |
| `get_findings` | `{status?, severity?}` | Open/snoozed findings | low (read-only) |
| `get_proposals` | `{status?}` | Pending proposals | low (read-only) |
| `get_proactive_events` | `{limit?}` | Recent proactive events | low (read-only) |
| `get_being_config` | `{}` | Voice, proactivity, quiet hours | low (read-only) |
| `get_config_file` | `{path}` | Raw file contents | **HIGH** (trust boundary) |
| `run_scanner` | `{type}` | Fresh scan results | medium (triggers work) |
| `approve_proposal` | `{proposal_id}` | Applied change result | **HIGH** (write action) |
| `reject_proposal` | `{proposal_id, reason}` | Rejection confirmation | medium (write action) |
| `snooze_finding` | `{finding_id, duration}` | Snooze confirmation | medium (write action) |
| `search_knowledge` | `{query, scope?}` | Semantic search results | low (delegates to SourcePrep) |

12 tools. The two HIGH-risk ones (`get_config_file`, `approve_proposal`) are
where the trust boundary research matters.

---

## 7. Implementation Path (High-Level)

### Phase 1: Read-only MCP server (safe, no trust boundary issues)
- Expose `get_vitals`, `get_discoveries`, `get_findings`, `get_proposals`,
  `get_proactive_events`, `get_being_config`, `search_knowledge`
- stdio-based, launched by the client
- Thin wrapper: calls the dashboard's existing REST API internally
- No raw file access, no write actions
- **This is safe to build first.** It proves the architecture without touching
  the trust boundary.

### Phase 2: Scanner trigger + finding lifecycle
- Add `run_scanner`, `snooze_finding`, `reject_proposal`
- Still no raw config reads, no proposal approval
- Medium risk — these trigger work but don't modify config files

### Phase 3: Trust boundary + write actions
- Add `get_config_file` (raw reads) and `approve_proposal` (config changes)
- This requires the trust boundary research to be resolved
- See companion doc: `HALBERT-MCP-TRUST-BOUNDARY-RESEARCH-2026-08-28.md`

### Phase 4: Proactive push (optional)
- Expose proactive event bus as subscribable MCP resource
- Depends on MCP client support for subscriptions

---

## 8. What This Is NOT

- **Not a replacement for the dashboard.** The dashboard stays. It's one
  consumer of the same underlying stores and engines. The MCP server is another
  consumer.
- **Not a replacement for the agent.** The agent state machine
  (`agents/state_machine.py`) is the conversational brain. The MCP server is a
  tool provider — it doesn't think, it answers. (Though a client like Claude
  Code could use Halbert MCP tools to power its own thinking.)
- **Not a way to bypass SourcePrep.** SourcePrep stays as a separate MCP server
  (`prep`). Halbert MCP calls SourcePrep's HTTP API internally when it needs
  structural context, but they remain independent servers.

---

## 9. Next Steps

1. **Resolve the trust boundary question** (companion research doc)
2. **Prototype Phase 1** (read-only stdio MCP server, 7 tools, thin REST proxy)
3. **Test with WarpCLI** — can it call `halbert.get_vitals` and get real data?
4. **Decide process model** (stdio vs HTTP/SSE vs hybrid) based on Phase 1
   experience
5. **Design auth model** before Phase 3

---

## 10. References

- Discovery engine: `halbert_core/halbert_core/discovery/engine.py`
- Scanner base class: `halbert_core/halbert_core/discovery/scanners/base.py`
- Module registry: `halbert_core/halbert_core/modules/registry.py`
- Module routes (data fetchers + allowlist): `halbert_core/halbert_core/dashboard/routes/modules.py`
- Host project registrar: `halbert_core/halbert_core/tools/register_host_project.py`
- Being config: `halbert_core/halbert_core/config/being_config.py`
- Findings store: `halbert_core/halbert_core/findings/store.py`
- Proposals store: `halbert_core/halbert_core/findings/proposals.py`
- Proactive event bus: `halbert_core/halbert_core/proactive/events.py`
- Agent state machine: `halbert_core/halbert_core/agents/state_machine.py`
- SourcePrep host project ID: `735a592e-a2da-499b-a614-854a5fc461f5`
- SourcePrep daemon: `http://localhost:8400`
- Home automation multi-instance design: `.handoff/HOME-AUTOMATION-DESIGN-2026-08-27.md`
- The being vision: `documentation/design/the-being.md`
