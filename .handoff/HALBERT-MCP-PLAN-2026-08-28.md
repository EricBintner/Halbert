# Halbert MCP — Implementation Plan

**Date:** 2026-08-28 (reviewed)
**Worktree:** `feat/halbert-mcp`
**Status:** Ready for execution

---

## 1. Goal

Expose Halbert as an MCP server so any MCP client (WarpCLI, Claude Code,
Devin, Cursor) can query the machine's runtime state, config values, and
agent actions. Two MCP servers:

```
Client (WarpCLI / Claude Code / Devin)
    |
    +-- MCP: prep (SourcePrep, already exists, :8400)
    |       Structural intelligence: file relationships, trace graph,
    |       semantic search over docs
    |
    +-- MCP: halbert (NEW)
            Runtime state + deterministic config DB + agent actions
```

The key insight: Halbert already has a config snapshot system
(`config/snapshot.py`, `config/parser.py`, `config/drift.py`,
`config/edge_extractor.py`) that parses real config files into structured
canonical JSON. This deterministic DB is the primary config access path —
not raw file reads, not LLM reasoning over raw text.

---

## 2. The Two Egress Risks

Both must be closed before any unredacted content lands on disk.

### Risk A — MCP egress to a third-party vendor (primary)

An MCP client (WarpCLI, Claude Code, Cursor) reads a raw config value
through Halbert's tool surface and forwards it to its own cloud model.
This is not an escalation edge case — it is the feature working as
designed, on every call. The destination vendor is not Halbert's choice
and Halbert's model router cannot see it.

**Prevented by Task 0** — `redact_text()` on the MCP response boundary.

### Risk B — Cloud model escalation with secure content (secondary)

Halbert's complexity router escalates a secret-bearing turn to a cloud
specialist. The specialist sees raw config values in the prompt.

**Prevented by Task 3** — secure content routing with a two-part
detector (provenance + content).

### Ordering

```
Task 7 (harden excludes) → Task 0 (redact MCP boundary) → Task 1 (unredact)
                                    |
                                    +→ Task 3 (secure routing) → Task 4 (rebuild)
```

Task 1 puts real secrets on disk in a queryable index. Both egress paths
must be closed before it lands.

---

## 3. Tiered Sensitivity

Binary "force local when secure" throws away the cloud models' entire
value. The user plans DeepSeek V4 Flash (orchestrator) and DeepSeek V4 Pro
or GLM-5.2 (thinking) — powerful cloud models. Route by tier, not by a
binary flag.

### Tier 0 — Public (no restrictions)

Machine structure with no secrets and no exploitable identifying values.

- `/etc/hosts` structure, `/etc/hostname`, `fstab` mount points/types
- Service names, unit names, which services are loaded
- Package lists, disk partition layout, filesystem types
- Network interface names, routes (not routable IPs — those are Tier 1)
- Booleans, structural keys (`include`, `enabled`, `type`, `kind`, `version`)

**Routing:** Cloud models see this freely.

### Tier 1 — Operational (user-configurable)

Config values that could identify the machine or reveal security-relevant
settings, but are not credentials.

- SSH port, `PermitRootLogin`, `PasswordAuthentication`
- Routable network addresses, firewall rules
- Launchd program paths, KeepAlive settings
- TimeMachine destination, backup schedule
- Homebrew tap URLs, package sources

**Routing:** User choice via `being.yml`:
- `cloud_ok` (default) — cloud models see it. Cloud reasoning power
  outweighs privacy cost for most users.
- `local_only` — deterministic description, not raw value.
- `redact` — strip value, return only structure.

### Tier 2 — Secrets (deterministic response, no model)

Credentials, keys, tokens, passwords — anything `_is_secret_key()` or
`redact_text()` identifies.

- API keys, tokens, bearer tokens, passwords, passphrases, PSKs
- OAuth credentials, JWT tokens, PEM blocks
- URL-embedded credentials (`user:pass@host`)

**Routing:** The value never leaves the tool. A deterministic responder
returns structured facts *about* the value without the value itself: key
name, file, length, character classes, entropy estimate, local view
command. No model in the boundary — a template cannot be talked into
quoting a value, cannot be injected, and does not vary with which model
is loaded.

User can override to `cloud_ok_acknowledged` with an explicit setting
change (escape hatch for users who trust ZDR and want maximum power).

### Why no local LLM in the boundary

Measured, not assumed: probed across 3 local models with planted
sentinels using the exact "describe, don't transcribe" system prompt.

| Model | Result |
|---|---|
| `qwen3:4b-instruct` | leaked 4/4 secrets from an env file; echoed a bare token verbatim |
| `qwen3.5:27b` | leaked on both adversarial fixtures and obeyed the injection |
| `llama3.1:8b` | leaked nothing, but refused 2/5 requests |

Posture is non-monotonic in model size — the 27B was the worst. "Use a
bigger local model" does not fix it. The task being narrow is not the
property that matters; being deterministic is. By the time
`classify_sensitivity()` has flagged a value as Tier 2, there is no
judgement left for a model to make. Every job the secure LLM would do is
template-able or computable.

---

## 4. Sensitivity Classifier

```python
def classify_sensitivity(key, value, file_path) -> int:
    """Return sensitivity tier: 0 (public), 1 (operational), 2 (secret)."""
    text = "" if value is None else str(value)

    # Tier 2, by KEY
    if _is_secret_key(key):
        return 2

    # Tier 2, by VALUE CONTENT — _is_secret_key inspects key names only,
    # so it misses JWTs, PEM blocks, URL-embedded credentials that have
    # no telltale key. Reuse the redactor as a DETECTOR: if it would have
    # changed the value, the value contains a credential.
    if text and redact_text(text) != text:
        return 2

    # Tier 0 by file — MUST be a floor, not a ceiling. Placed AFTER
    # content checks. A path can confirm clean content is public; it
    # can never certify content it has not looked at. /etc/hosts with a
    # routable IP, or /etc/fstab with cifs creds in options, must not
    # be whitelisted by filename.
    if _host_path(file_path) in PUBLIC_FILES:
        return 0

    # Tier 0: structural values
    if isinstance(value, bool):
        return 0
    if key.lower() in {"include", "enabled", "type", "kind", "version"}:
        return 0

    # Tier 1: everything else with a real value
    return 1
```

`_host_path()` maps staged paths
(`~/.local/share/halbert/sourceprep/host/etc/hosts`) back to original
host paths (`/etc/hosts`) before comparing against `PUBLIC_FILES`.

**Known limit, inherited:** `redact_text()` is keyword-driven with no
entropy or known-prefix detection, so a bare context-free secret (`ghp_…`
under a neutral key) is classified Tier 1, not Tier 2. Same gap as the
MCP boundary — closing it in Task 8 closes it here too, because both
share one detector.

---

## 5. User Settings

Add a `security` section to `being.yml`:

```yaml
security:
  operational_tier: cloud_ok  # cloud_ok | local_only | redact
  secret_tier: local_only     # local_only | cloud_ok_acknowledged

  public_files:
    - "/etc/hosts"
    - "/etc/hostname"
    - "/etc/fstab"

  extra_secret_keys:
    - "serial"
    - "license"
    - "activation"
```

No `secure_model` / `secure_endpoint` fields — the Tier 2 path is
deterministic, no model. If a local model is ever reintroduced for
open-ended questions about secrets, it must carry a fail-closed
assertion: reject any tag ending in `:cloud` (this host's Ollama serves
`deepseek-v4-*:cloud`, `gemini-3-flash-preview:cloud`, `kimi-*:cloud`
through `localhost:11434`), reject any provider outside
`LOCAL_GPU_PROVIDERS`, never infer locality from the endpoint URL.

---

## 6. How This Solves the Hardest Problem

"Once a secret enters conversation history, how do you prevent it from
reaching a cloud model on a subsequent turn?"

**Secrets never enter conversation history via the config query path.**
Tier routing happens at the tool level, before the value reaches any LLM.
No session lock, no two-channel history, no provenance redaction of
stored messages.

**Scope correction:** this holds only for the config query path. Other
paths into context are not tier-routed: terminal output (Halbert watches
the user's shells), scanner results, file-read tools, the user pasting a
config. The backstop is the same detector the classifier uses: run
`redact_text()` over assembled context before a cloud call (Task 3,
content detector). A non-identity result means a secret is present
regardless of how it arrived.

---

## 7. Implementation Tasks

Execution order: **Task 7 → Task 0 → Task 1 → Task 3 → Task 4**.
Tasks 2 and 8 are parallel-safe. Tasks 5 and 6 are deferred.

### Task 7 (BLOCKING for Task 1): Harden the exclude globs

`_COMMON_EXCLUDE_GLOBS` (`register_host_project.py:89`) has no `*.key`/
`*.pem`. Key material is currently kept out by the include allowlist
plus `PEM_RE` inside `redact_text()`. Task 1 removes the second layer.

Add to `_COMMON_EXCLUDE_GLOBS`:
`**/*.key`, `**/*.pem`, `**/*.p12`, `**/*.pfx`, `**/id_rsa*`,
`**/id_ecdsa*`, `**/id_ed25519*`, `**/*.kdbx`, `**/.netrc`,
`**/authorized_keys`.

Defence in depth — most match no include glob today. The protection
should not depend on the include list never widening.

- **Risk:** None. Pure subtraction.
- **Effort:** ~10 lines.

### Task 0 (BLOCKING, do first): Redact the MCP response boundary

Every Halbert MCP tool that returns host config content passes its
result through `redact_text()` before returning. Single choke point:
one `_mcp_response(payload)` helper that every tool returns through, so
a new tool cannot forget it. Internal reads (Halbert's own agent) keep
the raw path.

- **Risk:** Low. Reuses existing, trusted code.
- **Effort:** ~30 lines + a test asserting a planted sentinel never
  appears in any MCP tool response.

### Task 1: Unredacted staging for Halbert's host project

Add `redact: bool = True` parameter to `register()` and
`_stage_one_file()` in `register_host_project.py`. When `redact=False`,
write raw text. Halbert's own registration call passes `redact=False`;
any shared/multi-machine use keeps `redact=True`.

Also applies to `config/snapshot.py:85-90` — add `redact: bool = True`
param, skip `redact_text()` / `redact_parsed()` when False for the
local canon DB at `~/.local/share/halbert/config/canon/`.

- **Risk:** Low. Staging dir is user-owned, daemon is localhost-only.
- **Effort:** ~30 lines across 2 files.

### Task 2: Set PREP_DAEMON_TOKEN

Generate a token on first run, store in Halbert config, pass as
`Authorization: Bearer <token>` on all SourcePrep API calls.

**Scope note:** the token blocks unauthenticated localhost callers
(other users' processes, stray browser fetches, mis-scoped containers).
It does NOT provide same-user isolation — any process running as the
same user can read the token file and the index files directly off disk.
Same-user isolation requires OS-level controls (encryption at rest,
Task 5).

- **Risk:** Low. Daemon already supports this.
- **Effort:** ~30 lines + config plumbing.

### Task 3: Secure content routing in model layer

Add a `secure: bool` flag to the turn context. When true and the
resolved provider is not in `LOCAL_GPU_PROVIDERS`, fall back to the
guide model (local ollama). Log the fallback.

Two-part detector (OR):

1. **Provenance:** `secure=True` when any assembled chunk came from the
   unredacted `host/` scope. Cheap, catches the common case.
2. **Content:** `redact_text(ctx) != ctx` → `secure=True`. Reuses the
   redactor as a detector — if it would have changed anything, the
   context holds a credential. Provenance-independent, deterministic.

Fail toward `secure=True` including on exceptions. A false positive
costs a local-model answer; a false negative ships a secret to a cloud
vendor.

- **Risk:** Medium. Flag must propagate through intake → assembler →
  model resolution.
- **Effort:** ~50 lines across 2-3 files.

### Task 4: Rebuild the host SourcePrep index unredacted

Run `register_host_project(redact=False)` to re-stage files, then
trigger a SourcePrep index rebuild. Also run `snapshot()` on the real
host manifest to populate the canon DB.

- **Risk:** Low. Overwrites the currently-redacted staging dir.
- **Effort:** Two commands.

### Task 8 (follow-up): Close redaction gaps at the boundary

Once `redact_text()` guards the MCP boundary, its misses become egress.
Highest value: known-prefix detection (`AKIA`, `ghp_`, `sk-`, `xox`)
and a high-entropy-token backstop for long unbroken base64/hex runs.
Covers bare-token and netrc cases. Tune permissively — this layer only
fires on what the format-aware passes already declined.

- **Risk:** Low.
- **Effort:** ~60 lines + fixtures.

### Task 5 (deferred): Encryption at rest for remote deployments

Home automation / multi-machine case only. OS-level (LUKS / FileVault),
not application code.

### Task 6 (deferred): Cloud disallowance policy

Add `allow_cloud_for_secure_content` to being config or models.yml.
Defer until after Task 3 proves the routing rule works.

---

## 8. Config Query Layer + MCP Tool Surface

### Config query functions (NEW `config/queries.py`)

- `get_config_value(path, key)` → `{value, tier}`. Tier 0/1 (cloud_ok):
  raw value. Tier 2 / Tier 1 (local_only): deterministic description via
  `describe_secret()`.
- `get_config_structure(path)` → parsed tree/sections. No values. Always
  cloud-safe.
- `get_config_diff(since)` → key names and change types. No values.
  Always cloud-safe.
- `get_config_dependencies(path)` → edge relationships. No values.
  Always cloud-safe.

### Deterministic secure responder (NEW `config/secure_response.py`)

`describe_secret(key, value, file) -> dict` returns facts about the
value without the value: key name, file, length, character classes,
entropy estimate, local view command. No model call.

### Sensitivity classifier (NEW `config/sensitivity.py`)

`classify_sensitivity(key, value, file_path) -> int` (0/1/2). Reuses
`_is_secret_key()` and `redact_text()` as a detector. ~40 lines.

### Being config security section (`config/being_config.py`)

Add `SecurityConfig` dataclass: `operational_tier`, `secret_tier`,
`public_files`, `extra_secret_keys`. No `secure_model`/`secure_endpoint`.

### MCP server (NEW `mcp/server.py`)

stdio-based, 12 tools:

| Tool | Tier handling |
|------|---------------|
| `get_vitals` | Runtime state (psutil). No config. |
| `get_discoveries` | Discovery objects. No config values. |
| `get_findings` | Open/snoozed findings. No config values. |
| `get_proposals` | Pending proposals. No config values. |
| `get_proactive_events` | Recent events. No config values. |
| `get_being_config` | Voice, proactivity, quiet hours. No secrets. |
| `get_config_value` | Returns `{value, tier}`. Tier 2 → deterministic description. Tier 1 → checks user setting. All results pass through `_mcp_response()` (Task 0). |
| `get_config_structure` | Structure only. Always cloud-safe. |
| `get_config_diff` | Change types only. Always cloud-safe. |
| `get_config_dependencies` | Edges only. Always cloud-safe. |
| `search_knowledge` | SourcePrep semantic search (localhost :8400). |
| `run_scanner` | Fresh scan results. Phase 4b, gated. |
| `approve_proposal` | Write action. Phase 4b, gated. |

---

## 9. The Model Setup This Enables

```
Orchestrator: DeepSeek V4 Flash (cloud) — fast, cheap, conversation
Thinking:     DeepSeek V4 Pro or GLM-5.2 (cloud) — complex reasoning
Secure:       NONE — Tier 2 is a deterministic template, not a model

Data flow:
  User asks question
    → DeepSeek V4 Flash orchestrates
    → Calls halbert.get_config_value for needed values
    → Tier 0/1 values come back directly → Flash reasons about them
    → Tier 2 values never leave the tool → deterministic description
      ("APIKey is set in <file>, 39 chars, alphanumeric; view: plutil -p <file>")
    → Flash combines everything, responds to user
    → If Flash needs deeper reasoning, escalates to V4 Pro / GLM-5.2
    → V4 Pro sees only safe content (Tier 0/1 + safe descriptions)
    → Full cloud power for reasoning, zero secrets on cloud servers
```

"Zero secrets on cloud servers" is a claim the deterministic path can
actually keep — a template cannot be talked into quoting a value, cannot
be injected, and does not vary with which model is loaded.

---

## 10. What We Are NOT Doing

- **No LLM summarization gate.** Measured to leak on benign prompts;
  posture is non-monotonic in model size. The deterministic responder
  replaces it.
- **No session-level secure flag.** Tier routing at tool level means
  secrets never enter history via the config path. No conversation
  locking.
- **No two-channel history.** Not needed — history is safe by
  construction for the config path, and the content detector (Task 3)
  is the backstop for other paths.
- **No per-MCP-client permissions.** Single machine = trusted. Per-client
  is for the multi-machine case.
- **No `secure_model` / `secure_endpoint` config fields.** The Tier 2
  path has no model. If reintroduced, must carry fail-closed assertion
  on `:cloud` suffix and `LOCAL_GPU_PROVIDERS` membership.
- **Not replacing the dashboard or the agent.** MCP is another consumer.
  The agent state machine is the brain; MCP tools are data providers.
- **Not chaining MCP servers.** Halbert MCP calls SourcePrep's HTTP API
  directly (`:8400`), not through MCP protocol.

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
| `ingestion/redaction.py` | 1377-line credential redaction layer (`_is_secret_key`, `redact_text`) |
| `tools/register_host_project.py` | Stages host config into SourcePrep project |
| `model/client.py` | Model client with `LOCAL_GPU_PROVIDERS` classification |
| `dashboard/routes/agent.py` | Model resolution, complexity routing, Locked Mode |
| `context/assembler.py` | Context assembler (RAG, memory, discovery, conversation) |

### New files

| File | Phase | What it does |
|------|-------|-------------|
| `config/sensitivity.py` | P2 | `classify_sensitivity()` — 3-tier classifier |
| `config/queries.py` | P2 | Deterministic config query functions |
| `config/secure_response.py` | P3 | `describe_secret()` — deterministic Tier 2 responder |
| `mcp/server.py` | P4 | MCP server (stdio, 12 tools) |
| `mcp/__init__.py` | P4 | Package init |

### Files to modify

| File | Task | Change |
|------|------|--------|
| `tools/register_host_project.py` | T7, T1 | Harden excludes; add `redact: bool` param |
| `config/snapshot.py` | T1 | Add `redact: bool` param, skip redaction when False |
| `config/being_config.py` | T2 | Add `SecurityConfig` dataclass |
| `context/assembler.py` | T3 | Content detector backstop; tier-aware config queries |
| `dashboard/routes/agent.py` | T3 | Force local model when `secure=True` |

---

## 12. References

- Redaction layer: `halbert_core/halbert_core/ingestion/redaction.py:126` (`_is_secret_key`), `:1221` (`redact_text`)
- Host project registrar: `halbert_core/halbert_core/tools/register_host_project.py:89` (excludes), `:73-87` (includes), `:165` (redaction call site)
- SourcePrep daemon auth: `src/prep/server.py:223-236` (PREP_DAEMON_TOKEN)
- SourcePrep CORS: `src/prep/server.py:199-218` (localhost-only)
- Model provider classification: `halbert_core/halbert_core/model/client.py:76` (LOCAL_GPU_PROVIDERS)
- Complexity router: `halbert_core/halbert_core/model/client.py:1257` (scores prompt only)
- Model resolution: `halbert_core/halbert_core/dashboard/routes/agent.py:363-449`
- Config parser: `halbert_core/halbert_core/config/parser.py`
- Config snapshot: `halbert_core/halbert_core/config/snapshot.py`
- Config drift: `halbert_core/halbert_core/config/drift.py`
- Config edge extractor: `halbert_core/halbert_core/config/edge_extractor.py`
- Being config: `halbert_core/halbert_core/config/being_config.py`
- SourcePrep host project: ID `735a592e-a2da-499b-a614-854a5fc461f5`, path `~/.local/share/halbert/sourceprep`
- Config canon DB: `~/.local/share/halbert/config/canon/` (1 test file currently, needs real population)
- LLM gate probe harness + results: `gate_probe.py`, `gate_probe_results.json` (session `b21d21d6`)
- Warp ZDR: https://docs.warp.dev/enterprise/security-and-compliance/security-overview/
- Warp local LLM (not supported): https://github.com/warpdotdev/warp/issues/4339
