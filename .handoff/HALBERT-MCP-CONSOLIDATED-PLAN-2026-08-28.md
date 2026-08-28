# Halbert MCP — Consolidated Plan for Review

**Date:** 2026-08-28
**Status:** Ready for review
**Worktree:** `feat/halbert-mcp` at `~/.config/superpowers/worktrees/Halbert/halbert-mcp`
**Prior docs in this series:**
1. `HALBERT-MCP-DESIGN-RESEARCH-2026-08-28.md` — architecture and opportunities
2. `HALBERT-MCP-TRUST-BOUNDARY-RESULTS-2026-08-28.md` — trust boundary answers
3. `HALBERT-MCP-HARDEST-QUESTION-2026-08-28.md` — secret propagation through history

This document supersedes the three above as the single review-ready plan.
The prior docs remain as supporting detail.

---

## 1. The Goal

Expose Halbert as an MCP server so that any MCP client (WarpCLI, Claude Code,
Devin, Cursor) can query the machine's runtime state, config values, and
agent actions without opening the dashboard.

The architecture is two MCP servers that any client can call:

```
Client (WarpCLI / Claude Code / Devin)
    |
    +-- MCP: prep (SourcePrep, already exists)
    |       Structural intelligence: "what config files exist, how do they
    |       relate, what docs cover launchd" — semantic search, trace graph
    |
    +-- MCP: halbert (NEW)
            Runtime state + deterministic config + agent actions
```

---

## 2. The Key Insight: Deterministic Config DB

Halbert already has a config snapshot system (`config/snapshot.py`) that
parses real config files into structured canonical JSON:

- `config/parser.py` — parses ini, systemd, YAML, JSON, plist (binary + XML),
  text fallback. Each file becomes `{path, hash, kind, sections/tree, lines}`
  with line numbers for citation.
- `config/snapshot.py` — runs the parser over the manifest, stores canonical
  JSON at `~/.local/share/halbert/config/canon/{hash}.json` and raw text at
  `~/.local/share/halbert/config/raw/{hash}.txt`.
- `config/drift.py` — diffs two snapshots, loads canonical JSONs by hash,
  produces structured change reports (which keys changed, added, removed).
- `config/edge_extractor.py` — extracts dependency edges (systemd Requires,
  Include directives, fstab→mount units) and pushes to SourcePrep's trace
  graph.
- `config/indexer.py` — indexes canonical records into ChromaDB for vector
  search over config key/values.

**This is the deterministic side.** It's not LLM reasoning over raw text —
it's a parsed, structured, queryable database of the machine's actual
configuration. `get_config_value("/etc/ssh/sshd_config", "Port")` returns
`2222` without any LLM in the loop.

**This is what the MCP server should expose for config access.** Not raw
file reads, not SourcePrep semantic search, but structured queries against
the parsed config DB.

### Current state: built but not populated

The snapshot system exists and works, but:
- Only 1 file in the canon DB — a test WireGuard config from a test run
- Has never been run against the real host manifest
- Both raw and canon copies are redacted (`redact_text()` / `redact_parsed()`)
- The redaction is correct for a shared index but defeats the purpose for
  Halbert knowing its own config

---

## 3. Warp CLI and Data Privacy

Warp's AI architecture is **server-mediated**: prompts go from the client
through Warp's backend servers to cloud LLMs (Anthropic, OpenAI, Google).

**What Warp does right:**
- Zero Data Retention (ZDR) agreements with all contracted LLM providers —
  they do not store or train on your data. ZDR applies across all plans.
- Automatic secret redaction in all AI interactions (Warp's own redaction
  layer, not configurable by the user).
- Business/Enterprise: data collection disabled by default.
- Client source code is open (AGPL v3) at `warpdotdev/warp`.

**What Warp does not do:**
- Local LLM support (Ollama) is the #1 most requested feature (GitHub
  issue #4339) but is NOT officially supported. Community forks exist
  (`danieljohnmorris/warp-local`) but require bypassing auth.
- BYOLLM (custom endpoints) is also not officially supported (issue #7936).
- Data still transits Warp's servers even with ZDR. ZDR means no
  storage/training, but the cloud LLM processes the data in real-time.
  The values are in the prompt, even if they're not saved.

**What this means for Halbert:**

If WarpCLI's AI calls `halbert.get_config_value` as an MCP tool, the result
goes back into Warp's AI pipeline → Warp's servers → cloud LLM. The config
value leaves the machine for inference, even though it's not stored.

This is the same problem as Halbert's own complexity router escalating to a
cloud specialist. The fix is the same: **don't let secure content reach
cloud models, regardless of which client is asking.**

The deterministic config DB helps here too: if the MCP tool returns a
structured value (not raw file text), the client can use it directly without
feeding it to an LLM. `get_config_value` returns `{"port": 2222}` — the
client can display that without an AI round-trip. The AI is only needed for
*reasoning about* config, not for *reading* it.

---

## 4. The Trust Boundary

### The real threat model

Same machine, same user. The user is the sysadmin. The user and Halbert both
can know system secrets. There is no untrusted caller.

The threat is **cloud models seeing secrets**. Two paths:
1. Halbert's own complexity router escalates to a cloud specialist
2. WarpCLI's AI pipeline sends tool results to cloud LLMs

Both have the same fix: keep secure content on local models.

### What SourcePrep already provides

- `PREP_DAEMON_TOKEN` — bearer token auth (constant-time comparison,
  `hmac.compare_digest`). Already implemented in `src/prep/server.py:223-236`.
- CORS locked to localhost (`127.0.0.1` / `localhost` only). Already
  implemented in `src/prep/server.py:199-218`.
- No per-project access control (any token-bearing client can query any
  project). Acceptable for single-machine use.

### The redaction layer

`halbert_core/halbert_core/ingestion/redaction.py` is 1377 lines of
credential stripping. Covers: secret keys (password, token, api, key,
passphrase, etc. — two-tier keyword matching with exemptions), plist XML
values, YAML block scalars, ini/systemd keyfiles, JWTs, PEM blocks, routable
IPs (RFC1918 exempted), MAC addresses, email addresses, URL credentials,
home paths, macOS LKDC realms.

It is not configurable — `redact_text()` always runs all passes. To get
unredacted content, skip the call.

### What needs to change

1. **Lift redaction for Halbert's private copies.** The canon DB
   (`~/.local/share/halbert/config/canon/`) and the SourcePrep host staging
   dir (`~/.local/share/halbert/sourceprep/host/`) are user-owned, not
   shared. Skip `redact_text()` / `redact_parsed()` when writing to these.
   The exclude_globs already strip `*.key`, `*.pem`, `shadow`, `gshadow`,
   `ssl/`, `letsencrypt/` — private keys and system secrets are still
   excluded.

2. **Set `PREP_DAEMON_TOKEN`.** Generate a token on first run, store in
   Halbert config, pass as `Authorization: Bearer <token>` on all SourcePrep
   API calls. Prevents other local processes from querying the unredacted
   index.

3. **Secure content routing in the model layer.** When the context being
   sent to an LLM contains content from the config DB (canon records) or
   the unredacted host/ scope, force the model to a local provider
   (`LOCAL_GPU_PROVIDERS = {"ollama", "llamacpp", "mlx", "lm-studio"}`).
   The infrastructure for this classification already exists in
   `model/client.py:76`.

---

## 5. The Hardest Problem: Secret Propagation Through History

### The scenario

```
Turn 1: "What port is sshd on?"
  → Config DB query: Port = 2222
  → Local model answers: "sshd is on port 2222..."
  → Answer stored in conversation history

Turn 2: "Why did SSH stop working after the update?"
  → Complexity router sees diagnostic keywords, escalates to cloud specialist
  → No new config DB query this turn
  → Cloud specialist receives full message array including turn 1's history
  → "port 2222" is on a cloud server
```

### Why the deterministic config DB changes the calculus

With the config DB, the LLM doesn't need raw config text in its context.
It calls `get_config_value` as a tool and gets back a structured value.
The conversation history contains the LLM's *assertion* ("your sshd port
is 2222"), not a raw file dump. This is a smaller blast radius than the
raw-file-in-prompt approach.

But the assertion still contains the secret. The hardest problem is not
fully solved by the config DB — it's *reduced* but not *eliminated*.

### The decision that determines the fix

**Is the local model good enough for config analysis?**

- If 7B+ can correctly analyze multi-file configs with drop-in overrides →
  **Session-level secure flag.** Once any turn touches config DB content,
  lock the thread to local models. Simple. One boolean. The UX cost is
  small because the local model is capable.
- If 7B can't handle it but 13B+ can → **Two-channel history.** Store a
  "safe" version of each response (secrets replaced with references like
  `[config:/etc/ssh/sshd_config:Port]`) for cloud-visible history, and a
  "full" version for local model history and UI display. More complex but
  preserves cloud capability for non-secure turns.
- If the user doesn't configure a cloud specialist → **No problem.** The
  escalation path doesn't exist. Default config should have specialist =
  local or unset.

### Proposed test

Take the real `sshd_config` + `sshd_config.d/100-macos.conf` from this
machine. Ask 4B, 7B, and 13B models: "What port is sshd on, and which file
takes precedence?" Score: correct port, correct precedence understanding,
correct Include directive interpretation.

This is a model capability test, not an architecture test. The architecture
is the same either way — the test determines which option to build.

---

## 6. The Implementation Plan

### Phase 1: Populate the config DB (deterministic foundation)

| Task | File | Change | Effort |
|------|------|--------|--------|
| T1.1 Run snapshot on real manifest | `config/snapshot.py` | Execute `snapshot()` against the macOS host manifest, not a test temp file | 1 command |
| T1.2 Lift redaction for local canon DB | `config/snapshot.py:85-90` | Add `redact: bool = True` param. When False, write raw text and unredacted canon JSON | ~20 lines |
| T1.3 Lift redaction for SourcePrep staging | `tools/register_host_project.py:165` | Add `redact: bool = True` param. When False, write raw text | ~10 lines |
| T1.4 Rebuild both with unredacted content | — | Re-run snapshot + re-register host project with `redact=False` | 2 commands |
| T1.5 Set PREP_DAEMON_TOKEN | Halbert config + SourcePrep client | Generate token, store, pass on all API calls | ~30 lines |

### Phase 2: Config DB query layer (deterministic API)

| Task | File | Change | Effort |
|------|------|--------|--------|
| T2.1 Config query functions | NEW `config/queries.py` | `get_config_value(path, key)`, `get_config_structure(path)`, `get_config_diff(since)`, `get_config_dependencies(path)` — all read from canon DB, no LLM | ~100 lines |
| T2.2 Wire into agent context assembler | `context/assembler.py` | When the agent needs a config value, call `get_config_value` instead of pulling raw file text into the prompt | ~30 lines |
| T2.3 Wire into module data fetchers | `dashboard/routes/modules.py` | `config-diff` module uses `get_config_diff` instead of raw file reads | ~20 lines |

### Phase 3: Secure content routing (trust boundary)

| Task | File | Change | Effort |
|------|------|--------|--------|
| T3.1 Secure flag on context | `context/assembler.py` | Set `secure=True` when assembled context includes config DB values or host/ scope chunks | ~15 lines |
| T3.2 Force local model for secure turns | `dashboard/routes/agent.py:_resolve_turn_model` | When `secure=True` and provider not in `LOCAL_GPU_PROVIDERS`, fall back to guide model (local ollama) | ~20 lines |
| T3.3 Session-level secure flag | `agents/threads.py` or `agents/state_machine.py` | Once any turn in a thread touches secure content, set thread-level flag. All subsequent turns use local models. | ~25 lines |
| T3.4 Model capability test | — | Test 4B/7B/13B on real sshd_config scenario. Determines whether T3.3 is sufficient or T3.5 is needed. | research |
| T3.5 (conditional) Two-channel history | `agents/conversation_sqlite.py` | If 7B can't handle config analysis, store safe + full versions of responses. Safe version replaces secrets with references. | ~80 lines |

### Phase 4: MCP server (expose to external clients)

| Task | File | Change | Effort |
|------|------|--------|--------|
| T4.1 MCP server skeleton | NEW `mcp/server.py` | stdio-based MCP server using Python MCP SDK. Tool definitions, request handling. | ~150 lines |
| T4.2 Read-only tools | `mcp/server.py` | `get_vitals` (psutil), `get_discoveries` (DiscoveryEngine), `get_findings` (FindingStore), `get_proposals` (ProposalStore), `get_being_config`, `get_config_value` (config DB), `get_config_structure`, `get_config_diff`, `search_knowledge` (SourcePrep HTTP) | ~200 lines |
| T4.3 Test with WarpCLI | — | Verify WarpCLI can call `halbert.get_config_value` and get real data | manual |
| T4.4 Write actions (Phase 4b, gated) | `mcp/server.py` | `approve_proposal`, `reject_proposal`, `snooze_finding`, `run_scanner`. Gated on secure routing being proven. | ~100 lines |

### Phase 5: Remote deployment hardening (deferred)

| Task | Scope | Change |
|------|-------|--------|
| T5.1 Encryption at rest | Home automation / remote | OS-level (LUKS / FileVault). Not application code. |
| T5.2 Cloud disallowance policy | Advanced config | `allow_cloud_for_secure_content: false` in being config. Default false. |
| T5.3 Per-project SourcePrep access | Multi-machine | Token-scoped project access. Not needed for single-machine. |

---

## 7. Tool Surface (12 tools, curated)

| Tool | Input | Output | Phase | Risk |
|------|-------|--------|-------|------|
| `get_vitals` | `{timeframe?}` | CPU, mem, disk, net, temp | P4 | low |
| `get_discoveries` | `{type?, scanner?}` | Discovery objects | P4 | low |
| `get_findings` | `{status?, severity?}` | Open/snoozed findings | P4 | low |
| `get_proposals` | `{status?}` | Pending proposals | P4 | low |
| `get_proactive_events` | `{limit?}` | Recent events | P4 | low |
| `get_being_config` | `{}` | Voice, proactivity, quiet hours | P4 | low |
| `get_config_value` | `{path, key}` | Parsed value from canon DB | P4 | low (deterministic) |
| `get_config_structure` | `{path}` | Parsed tree/sections | P4 | low (deterministic) |
| `get_config_diff` | `{since}` | Structured changes | P4 | low (deterministic) |
| `search_knowledge` | `{query, scope?}` | SourcePrep semantic search | P4 | low (localhost) |
| `run_scanner` | `{type}` | Fresh scan results | P4b | medium |
| `approve_proposal` | `{proposal_id}` | Applied change | P4b | high (write) |

The three `get_config_*` tools are deterministic — no LLM, no cloud, no
redaction concern. They read from the local canon DB. This is the
"deterministic side" that simplifies everything.

---

## 8. What We Are NOT Doing

- **Not replacing the dashboard.** The dashboard stays as one consumer.
  MCP is another consumer.
- **Not replacing the agent.** The agent state machine is the brain. MCP
  tools are data providers.
- **Not chaining MCP servers.** Halbert MCP calls SourcePrep's HTTP API
  directly (`:8400`), not through MCP protocol.
- **Not building an LLM summarization gate.** The config DB makes this
  unnecessary — structured queries replace raw file reads.
- **Not building per-client permissions.** Single machine = trusted.
  Per-client is for the multi-machine case.
- **Not modifying SourcePrep's redaction for shared indexes.** The
  redaction layer stays as-is for any project that's not Halbert's private
  one.

---

## 9. Open Questions for Review

1. **Is the session-level secure flag (T3.3) acceptable UX?** One config
   question locks the thread to local models. If the local model is 7B+,
   this is fine. If it's 4B, it's not. The model capability test (T3.4)
   answers this.

2. **Should the MCP server be stdio or HTTP/SSE?** stdio is simpler and
   matches how WarpCLI/Claude Code launch MCP servers. HTTP/SSE shares
   state with the dashboard. Proposal: start with stdio (Phase 4), evaluate
   HTTP/SSE if state sharing becomes painful.

3. **Should `get_config_value` return raw values or references?** Raw
   values are more useful but leak secrets to the client's AI pipeline
   (WarpCLI → cloud). References (`[config:/etc/ssh/sshd_config:Port]`)
   are safe but less useful. Proposal: return raw values (the client is on
   the same machine), but document that the client's AI pipeline may send
   them to cloud models. The secure routing rule is Halbert's defense, not
   the client's.

4. **Should we block MCP tool results from reaching cloud models?** This
   is a WarpCLI concern, not a Halbert concern. Halbert can't control what
   WarpCLI does with tool results. But we could add a `sensitive: true`
   flag to tool results that clients can respect. Proposal: add the flag,
   document it, don't enforce it (Halbert can't enforce client behavior).

5. **Is the config DB the right place for config access, or should we
   query live files?** The canon DB is a snapshot — it can be stale. Live
   file reads are always current but bypass the structured parsing.
   Proposal: canon DB for structure and history, live read for "what is
   the value right now?" The `get_config_value` tool can check staleness
   (compare file hash to canon hash) and re-parse if stale.

---

## 10. Dependency Order

```
Phase 1 (populate config DB)
    |
    v
Phase 2 (query layer)          Phase 3 (secure routing)
    |                              |
    +--------- both needed ------+
                |
                v
         Phase 4 (MCP server)
                |
                v
         Phase 5 (remote hardening, deferred)
```

Phase 2 and 3 can proceed in parallel after Phase 1. Phase 4 requires
both. Phase 5 is deferred to the home-automation deployment work.

---

## 11. File Inventory

### Already exists (building blocks)

| File | What it does |
|------|-------------|
| `config/parser.py` | Parses ini/systemd/YAML/JSON/plist/text into canonical JSON |
| `config/snapshot.py` | Runs parser over manifest, stores canon + raw + snapshot summary |
| `config/drift.py` | Diffs two snapshots, structured change reports |
| `config/edge_extractor.py` | Extracts dependency edges, pushes to SourcePrep trace graph |
| `config/indexer.py` | Indexes canon records into ChromaDB |
| `config/manifest.py` | Manifest system — which files to harvest per OS/role |
| `config/roles.py` | Role definitions, manifest paths, staging subdirs |
| `config/watcher.py` | File watcher with reindex/detector callbacks |
| `config/being_config.py` | Being config (voice, proactivity, quiet hours, purpose) |
| `ingestion/redaction.py` | 1377-line credential redaction layer |
| `tools/register_host_project.py` | Stages host config into SourcePrep project |
| `discovery/engine.py` | Scanner registry, runs all scanners, stores discoveries |
| `discovery/scanners/base.py` | BaseScanner abstract class |
| `findings/store.py` | SQLite-backed FindingStore |
| `findings/proposals.py` | ProposalStore with approve/reject/apply/rollback |
| `proactive/events.py` | ProactiveEventBus (async pub/sub) |
| `model/client.py` | Model client with LOCAL_GPU_PROVIDERS classification |
| `dashboard/routes/agent.py` | Model resolution, complexity routing, Locked Mode |
| `dashboard/routes/modules.py` | Module data fetchers with path allowlist |
| `modules/registry.py` | Module registry (config-diff, vitals, drive-health, evidence) |
| `agents/state_machine.py` | Agent state machine with conversation history windowing |
| `agents/conversation_sqlite.py` | SQLite conversation store with redaction support |

### New files to create

| File | Phase | What it does |
|------|-------|-------------|
| `config/queries.py` | P2 | Deterministic config query functions |
| `mcp/server.py` | P4 | MCP server (stdio, 12 tools) |
| `mcp/__init__.py` | P4 | Package init |

### Files to modify

| File | Phase | Change |
|------|-------|--------|
| `config/snapshot.py` | P1 | Add `redact: bool` param, skip redaction when False |
| `tools/register_host_project.py` | P1 | Add `redact: bool` param |
| `context/assembler.py` | P2/P3 | Use config queries instead of raw file reads; set secure flag |
| `dashboard/routes/agent.py` | P3 | Force local model when secure flag is True |
| `agents/state_machine.py` | P3 | Thread-level secure flag propagation |
| `dashboard/routes/modules.py` | P2 | Use config queries for config-diff module |

---

## 12. References

- SourcePrep host project: ID `735a592e-a2da-499b-a614-854a5fc461f5`
- SourcePrep daemon: `http://localhost:8400` (localhost-only, PREP_DAEMON_TOKEN)
- Config DB: `~/.local/share/halbert/config/canon/` (1 file currently, needs real population)
- SourcePrep staging: `~/.local/share/halbert/sourceprep/host/` (40 files, redacted)
- Warp privacy: ZDR with LLM providers (no storage/training), but data transits servers
- Warp local LLM: not officially supported (GitHub #4339, #7936), community forks exist
- `LOCAL_GPU_PROVIDERS`: `{"ollama", "llamacpp", "mlx", "lm-studio"}` (`model/client.py:76`)
- Redaction layer: `ingestion/redaction.py` (1377 lines, not configurable, always runs)
- Complexity router: scores prompt only, not history (`model/client.py:1257`)
- History window: 12 rows, token-budgeted (`state_machine.py:728`)
