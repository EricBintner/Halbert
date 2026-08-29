# Halbert MCP Implementation — Handoff

**Date:** 2026-08-28
**Worktree:** `~/.config/superpowers/worktrees/Halbert/halbert-mcp` on branch `feat/halbert-mcp`
**Plan:** `.handoff/HALBERT-MCP-PLAN-2026-08-28.md` (single consolidated plan, reviewed)
**Tests:** 57 passing across 5 test files
**Commits:** 6 implementation commits on top of the plan docs

---

## Starter Prompt (paste into next session)

> Continue implementing the Halbert MCP plan. Work in the worktree at
> `~/.config/superpowers/worktrees/Halbert/halbert-mcp` on branch
> `feat/halbert-mcp`. The plan is at `.handoff/HALBERT-MCP-PLAN-2026-08-28.md`.
> Tasks 7, 0, 1, 2, 3 are done (57 tests passing). Next up is Phase 2
> (config query layer + sensitivity classifier + deterministic secure
> responder), then Task 8 (redaction gaps), then Phase 4 (MCP server
> stdio), then Phase 4b (HTTP/SSE transport + multi-instance auth).
> Read this handoff file first: `.handoff/HALBERT-MCP-HANDOFF-2026-08-28.md`.
> Run tests with `PYTHONPATH=halbert_core python -m pytest halbert_core/tests/ -q`.

---

## What's Done (5 tasks, 6 commits)

### Task 7 — Harden exclude globs (commit `a6ad875`)

**File:** `halbert_core/halbert_core/tools/register_host_project.py`

Added key material patterns to `_COMMON_EXCLUDE_GLOBS`:
`*.key`, `*.pem`, `*.p12`, `*.pfx`, `id_rsa*`, `id_ecdsa*`, `id_ed25519*`,
`*.kdbx`, `.netrc`, `authorized_keys`.

Defence in depth — most match no include glob today (the include allowlist
is the primary gate), but the protection must not depend on that list
never widening. Task 1 lifts redaction from staging, which removes the
`PEM_RE` backstop inside `redact_text()`; these excludes replace it at the
staging gate.

### Task 0 — MCP response boundary (commit `eed2862`)

**Files:**
- NEW `halbert_core/halbert_core/mcp/__init__.py`
- NEW `halbert_core/halbert_core/mcp/response.py`
- NEW `halbert_core/tests/test_mcp_response_boundary.py`

`mcp_response()` is the single choke point every MCP tool returns through.
Two passes:

1. **Structural:** dict with a `"key"` field whose value is a secret key
   name (per `_is_secret_key`) has its `"value"` field replaced with
   `<secret>`. Catches the primary MCP payload shape
   `{"path": ..., "key": "password", "value": "hunter2"}` where
   `redact_text()` alone would miss the bare value (no `key=value`
   structure to match). Also handles secret dict keys in nested config
   structures, with an `_MCP_FIELD_NAMES` exemption so payload field names
   like `"key"`, `"value"`, `"path"` are not treated as credential keywords.

2. **Text:** `redact_text()` on every remaining string — catches
   `key=value` shapes, PEM blocks, JWTs, URL-embedded credentials,
   routable IPs, email addresses, MAC addresses.

**Known limit (Task 8):** bare context-free secrets under neutral keys
(`ghp_...` under `"location"`) are not caught — requires known-prefix
detection and entropy backstop.

17 tests. Non-mutation verified. Non-string scalars pass through.

### Task 1 — Unredacted staging mode (commit `4904c5a`)

**Files:**
- `halbert_core/halbert_core/tools/register_host_project.py`
- `halbert_core/halbert_core/config/snapshot.py`
- NEW `halbert_core/tests/test_host_staging_unredacted.py`

Added `redact: bool = True` keyword argument to:
- `_stage_one_file()` — writes raw text when `redact=False`
- `_stage_config_files()` — passes flag through to each file
- `stage_role_tree()` — passes flag through
- `HostProjectRegistrar.register()` — passes flag to staging
- `register_host_project()` convenience function
- `config/snapshot.py:snapshot()` — writes raw text and unredacted canon JSON

Default remains `redact=True`. Halbert's private host project passes
`redact=False`. The exclude globs (Task 7) still strip key material
regardless of this flag. The MCP response boundary (Task 0) redacts on
egress to external clients.

4 new tests verify raw mode writes secrets, redacted mode still works,
directory walk passes the flag, and non-secret content is identical in
both modes.

### Task 2 — PREP_DAEMON_TOKEN (commit `3144d5b`)

**Files:**
- NEW `halbert_core/halbert_core/integrations/prep_token.py`
- `halbert_core/halbert_core/integrations/sourceprep_client.py`
- `halbert_core/halbert_core/tools/register_host_project.py`
- NEW `halbert_core/tests/test_prep_token.py`

`prep_token.py`:
- `ensure_token()` — generates a 32-byte hex token, writes to
  `~/.config/halbert/prep_token` with mode 0600. Returns existing token
  if file exists. Returns env var `PREP_DAEMON_TOKEN` if set (no file
  write in that case).
- `get_token()` — checks env var first, then token file. Returns None if
  nothing configured.
- `auth_headers()` — returns `{"Authorization": "Bearer <token>"}` dict
  or empty dict if no token.

Wired into all SourcePrep HTTP calls:
- `SourcePrepClient`: `_post()`, `_get()`, `health()`, `get_impact()`
- `HostProjectRegistrar`: `_list_projects()`, `_create_project()`,
  `_update_project_config()`, `_build_project()`, `verify()`

**Scope note:** the token blocks unauthenticated localhost callers (other
users' processes, stray browser fetches, mis-scoped containers). It does
NOT provide same-user isolation — any process running as the same user can
read the token file and the index files directly off disk. Same-user
isolation requires OS-level controls (Task 5, deferred).

6 tests covering generation, persistence, env var precedence, auth_headers
with/without token, file permissions.

### Task 3 — Secure content routing (commit `fd0985`)

**Files:**
- NEW `halbert_core/halbert_core/integrations/secure_detector.py`
- `halbert_core/halbert_core/dashboard/routes/agent.py`
- NEW `halbert_core/tests/test_secure_detector.py`

`secure_detector.py` — `detect_secure_content(context_text, chunk_sources)`:
Two-part detector (OR):

1. **Provenance:** any chunk source starting with `host/` → secure=True.
   Cheap, catches the common case.
2. **Content:** `redact_text(ctx) != ctx` → secure=True. Reuses the
   redactor as a detector — if it would have changed anything, the context
   holds a credential. Provenance-independent, catches secrets from
   terminal output, scanner results, file-read tools, user pastes.

Fails toward `secure=True` on exceptions — a false positive costs a
local-model answer; a false negative ships a secret to a cloud vendor.

`_resolve_turn_model()` in `agent.py`:
- New `secure: bool = False` parameter
- When `secure=True` and the complexity router selects a cloud specialist
  (provider not in `LOCAL_GPU_PROVIDERS`), falls back to the guide model
  (local ollama). Logged with reason: `"Secure content — specialist was
  cloud, used local guide"`.
- `LOCAL_GPU_PROVIDERS` imported from `model/client.py`

13 tests covering provenance, content, fail-toward-secure, combined
detection.

---

## What's Left

### Phase 2: Config query layer + sensitivity classifier + secure responder

This is the deterministic foundation that the MCP server and the agent
both use. Three new files, one modification.

#### T2.1 — Config query functions (NEW `config/queries.py`, ~100 lines)

Deterministic functions that read from the canon DB
(`~/.local/share/halbert/config/canon/{hash}.json`):

- `get_config_value(path, key) -> dict` — returns `{"value": ..., "tier": ...}`.
  Tier 0/1 (cloud_ok): raw value. Tier 2 / Tier 1 (local_only): deterministic
  description via `describe_secret()`.
- `get_config_structure(path) -> dict` — returns parsed tree/sections. No
  values. Always cloud-safe.
- `get_config_diff(since) -> dict` — uses `config/drift.py` to return
  structured changes. Key names and change types only. No values. Always
  cloud-safe.
- `get_config_dependencies(path) -> dict` — uses `config/edge_extractor.py`
  to return edge relationships. No values. Always cloud-safe.

The canon DB is keyed by file hash. To look up by path, you need the
snapshot manifest (`~/.local/share/halbert/config/snapshots/latest.json`)
which maps path → hash. Then load `canon/{hash}.json` and navigate the
parsed structure (`sections` for ini, `tree` for yaml/json, `lines` for
text).

**Staleness check:** compare the live file's hash to the canon hash. If
they differ, re-parse via `config/parser.py` before returning. This
handles the "canon DB is a snapshot" problem.

**Existing building blocks:**
- `config/parser.py` — `parse(path) -> dict` with `{path, hash, kind, sections/tree, lines}`
- `config/snapshot.py` — `snapshot(manifest_path, redact=False) -> list`
- `config/drift.py` — `diff_snapshots(prev, curr) -> list[changes]`
- `config/edge_extractor.py` — extracts systemd deps, includes, fstab→mount
- `config/indexer.py` — indexes canon records into ChromaDB

#### T2.2 — Sensitivity classifier (NEW `config/sensitivity.py`, ~40 lines)

`classify_sensitivity(key, value, file_path) -> int` (0/1/2).

The corrected version from the reviewed plan (§4 of the plan doc):

```python
def classify_sensitivity(key, value, file_path) -> int:
    text = "" if value is None else str(value)
    # Tier 2 by key
    if _is_secret_key(key):
        return 2
    # Tier 2 by value content — redact_text as detector
    if text and redact_text(text) != text:
        return 2
    # Tier 0 by file — floor, not ceiling (AFTER content checks)
    if _host_path(file_path) in PUBLIC_FILES:
        return 0
    # Tier 0: structural values
    if isinstance(value, bool):
        return 0
    if key.lower() in {"include", "enabled", "type", "kind", "version"}:
        return 0
    # Tier 1: everything else
    return 1
```

Key details:
- `_is_secret_key` and `redact_text` imported from `ingestion/redaction.py`
- `_host_path()` maps staged paths
  (`~/.local/share/halbert/sourceprep/host/etc/hosts`) back to original
  host paths (`/etc/hosts`) before comparing against `PUBLIC_FILES`. This
  is needed because the exact-match test on staged paths never fires.
- `PUBLIC_FILES` is a set of host paths: `/etc/hosts`, `/etc/hostname`,
  `/etc/fstab`, `/etc/machine-id`, `/etc/os-release`. Also read from
  being config `security.public_files`.
- File-level Tier 0 is a FLOOR not a CEILING — placed after content
  checks so `/etc/hosts` with a routable IP still gets Tier 1 for that
  value, and `/etc/fstab` with cifs creds still gets Tier 2.
- `extra_secret_keys` from being config are added to the Tier 2 check.

**Known limit (shared with Task 8):** `redact_text()` is keyword-driven
with no entropy or known-prefix detection, so a bare context-free secret
(`ghp_...` under a neutral key) is classified Tier 1, not Tier 2. Closing
this in Task 8 closes it here too — both share one detector.

#### T2.3 — Deterministic secure responder (NEW `config/secure_response.py`, ~40 lines)

`describe_secret(key, value, file_path) -> dict`

Returns structured facts about the value WITHOUT the value:
- `key` — the config key name
- `file` — the file path
- `length` — character count of the value
- `charset` — character classes present (lowercase, uppercase, digits, symbols, base64)
- `entropy_bits` — estimated Shannon entropy
- `view_command` — the local command to view the value (e.g., `plutil -p <file>`
  for plists, `cat <file>` for text, `grep <key> <file>` for ini)

No model call. No LLM. A template cannot be talked into quoting a value,
cannot be injected, and does not vary with which model is loaded.

This replaces the "local secure LLM" that the original tiered sensitivity
plan proposed. The review (C2 in the plan) measured that local LLMs leak
secrets even with "describe, don't transcribe" system prompts —
`qwen3:4b` leaked 4/4, `qwen3.5:27b` leaked and obeyed injections,
`llama3.1:8b` refused 2/5. Posture is non-monotonic in model size.
Deterministic is the only guarantee.

#### T2.4 — Being config security section (`config/being_config.py`, ~40 lines)

Add `SecurityConfig` dataclass to `BeingConfig`:

```python
@dataclass
class SecurityConfig:
    operational_tier: str = "cloud_ok"  # cloud_ok | local_only | redact
    secret_tier: str = "local_only"     # local_only | cloud_ok_acknowledged
    public_files: List[str] = field(default_factory=lambda: [
        "/etc/hosts", "/etc/hostname", "/etc/fstab",
    ])
    extra_secret_keys: List[str] = field(default_factory=list)
```

No `secure_model` / `secure_endpoint` fields — the Tier 2 path is
deterministic, no model. If a local model is ever reintroduced for
open-ended questions about secrets, it must carry a fail-closed assertion:
reject any tag ending in `:cloud` (this host's Ollama serves
`deepseek-v4-*:cloud`, `gemini-3-flash-preview:cloud`, `kimi-*:cloud`
through `localhost:11434`), reject any provider outside
`LOCAL_GPU_PROVIDERS`, never infer locality from the endpoint URL.

Load/save from the `security:` section of `being.yml`. Add to
`BeingConfig.from_dict()` and `BeingConfig.to_dict()`.

#### T2.5 — Settings UI (`dashboard/frontend/src/pages/Settings.tsx`, ~80 lines)

Add a Security tab to the settings page:
- Tier 1 picker: `cloud_ok` / `local_only` / `redact` (radio or dropdown)
- Tier 2 display: `local_only` (default, show as locked) with an
  "acknowledge and allow cloud" escape hatch that requires explicit
  confirmation
- Public files list (editable)
- Extra secret keys list (editable)

This is frontend React/TypeScript work. The backend endpoint for saving
being config already exists (`PUT /api/being-config`).

#### T3.3 — Agent context assembler integration (`context/assembler.py`, ~30 lines)

When the agent assembles context, use tier-aware config queries instead of
pulling raw file text. Tier 0/1 (cloud_ok) values go into context directly.
Tier 2 / Tier 1 (local_only) values go through `describe_secret()`.

The assembler currently pulls from multiple sources (RAG, memory,
discovery, conversation). The config source is new — it calls
`get_config_value()` when the agent needs a config value, rather than
reading the raw file into the prompt.

This is the piece that keeps raw config text out of the conversation
history. The LLM calls `get_config_value` as a tool and gets back a
structured value or a safe description. The conversation history contains
the LLM's assertion ("your sshd port is 2222"), not a raw file dump.

#### T3.6 — Context-assembly backstop (`context/assembler.py`, ~20 lines)

Before a cloud call, run `detect_secure_content()` over the assembled
context. This catches secrets that arrived off the config path (terminal
watch, scanners, pastes). The detector already exists (Task 3); this wires
it into the assembler's output.

The integration point is after the assembler finishes building the context
but before it's passed to the model client. Set `secure=True` on the turn
if the detector fires.

---

### Task 8: Close redaction gaps at boundary (~60 lines + fixtures)

**Files:**
- `halbert_core/halbert_core/ingestion/redaction.py`
- NEW `halbert_core/tests/test_redaction_gaps.py`

Once `redact_text()` guards the MCP response boundary (Task 0) and the
secure content detector (Task 3), its misses become egress. Highest value
gaps:

1. **Known-prefix detection.** Add regex patterns for common API key
   prefixes: `ghp_` (GitHub), `sk-` (OpenAI/Anthropic), `AKIA` (AWS),
   `xox` (Slack), `AIza` (Google). These are well-known prefixes that
   unambiguously identify a credential regardless of context.

2. **High-entropy backstop.** A long unbroken run of base64/hex characters
   (e.g., 32+ chars, no spaces) is likely a token even without a known
   prefix. Add an entropy check: if a "word" in the text is longer than
   N characters and has entropy above a threshold, redact it.

Tune permissively — this layer only fires on what the format-aware passes
already declined. False positives here mean redacting a non-secret that
looked like a token, which costs information but not security.

The gaps to test (from the reviewed trust-boundary doc):
- Bare token in a file (`~/.config/foo/token` containing just `ghp_abc123`)
- netrc shape (`machine h login u password hunter2` — password is mid-line)
- YAML sequence items (`passwords:\n  - hunter2`)
- Hash material (`$6$salt$hash`, htpasswd lines)

---

### Task 4: Rebuild index unredacted (operational, needs daemon)

**Not a code task — an operational task.** Requires the SourcePrep daemon
to be running on `:8400`.

Steps:
1. Ensure `PREP_DAEMON_TOKEN` is set in the daemon's environment (run
   `ensure_token()` and export the result)
2. Run `register_host_project(redact=False)` to re-stage files with raw
   content
3. Run `snapshot(manifest_path, redact=False)` to populate the canon DB
   with unredacted canonical JSON
4. Trigger a SourcePrep index rebuild via the API
5. Verify: query the index for a known config value and confirm it returns
   the real value (not `<secret>`)

This is the one irreversible-ish step — it puts real secrets on disk in
the index. Both egress paths (Task 0 MCP boundary, Task 3 secure routing)
must be verified working before running this.

---

### Phase 4: MCP server (NEW `mcp/server.py`, ~350 lines)

The actual MCP server that external clients connect to. Ships stdio-only
in Phase 4 (local machine). Phase 4b adds HTTP/SSE transport + bearer auth
for remote/multi-instance access.

#### Tool surface (12 tools)

| Tool | Input | Output | Phase | Risk |
|------|-------|--------|-------|------|
| `get_vitals` | `{timeframe?}` | CPU, mem, disk, net, temp | P4 | low |
| `get_discoveries` | `{type?, scanner?}` | Discovery objects | P4 | low |
| `get_findings` | `{status?, severity?}` | Open/snoozed findings | P4 | low |
| `get_proposals` | `{status?}` | Pending proposals | P4 | low |
| `get_proactive_events` | `{limit?}` | Recent events | P4 | low |
| `get_being_config` | `{}` | Voice, proactivity, quiet hours | P4 | low |
| `get_config_value` | `{path, key}` | `{value, tier}` — Tier 2 → deterministic description | P4 | low |
| `get_config_structure` | `{path}` | Parsed tree/sections (no values) | P4 | low |
| `get_config_diff` | `{since}` | Change types (no values) | P4 | low |
| `get_config_dependencies` | `{path}` | Edge relationships (no values) | P4 | low |
| `search_knowledge` | `{query, scope?}` | SourcePrep semantic search | P4 | low |
| `run_scanner` | `{type}` | Fresh scan results | P4b | medium |
| `approve_proposal` | `{proposal_id}` | Applied change | P4b | high |

Every tool that returns host config content passes its result through
`mcp_response()` (Task 0) before returning. The `get_config_value` tool
also applies tier routing internally — Tier 2 values go through
`describe_secret()` (T2.3) instead of returning the raw value.

**Existing building blocks:**
- `mcp/response.py` — `mcp_response()` boundary (Task 0, done)
- `config/queries.py` — config query functions (T2.1, to build)
- `config/sensitivity.py` — classifier (T2.2, to build)
- `config/secure_response.py` — deterministic responder (T2.3, to build)
- `discovery/engine.py` — scanner registry
- `findings/store.py` — FindingStore
- `findings/proposals.py` — ProposalStore
- `proactive/events.py` — ProactiveEventBus
- `integrations/sourceprep_client.py` — SourcePrep HTTP client (Task 2, done)
- `config/being_config.py` — BeingConfig

**MCP SDK:** Check if the project already has an MCP dependency. If not,
use `mcp` (the official Python MCP SDK) or implement the stdio protocol
directly (it's JSON-RPC over stdin/stdout, not complex).

#### Test with WarpCLI (local, stdio)

After the server is built, test with WarpCLI:
1. Configure WarpCLI to use Halbert as an MCP server (stdio)
2. Call `halbert.get_config_value` with a known path/key
3. Verify the response is tier-routed (Tier 2 → safe description, not raw value)
4. Verify the response passes through `mcp_response()` (no secrets in output)

---

### Phase 4b: HTTP/SSE transport + multi-instance auth (~220 lines)

Phase 4 ships stdio-only (local machine). Phase 4b adds remote capability
so a user with Halbert on multiple machines (laptop + home server) can
reach any instance from a single MCP client. See plan §7 Phase 4b for
full details.

#### T4b.1 — HTTP/SSE transport (`mcp/server.py`, ~150 lines)

- `--transport stdio|http` flag (default stdio)
- `--port` (default `:8401`) and `--bind` flags for HTTP mode
- Bind to localhost by default; user sets `--bind <LAN IP>` for remote
- Same tool handlers — transport is a thin wrapper
- Check if `mcp` Python SDK provides SSE transport; if not, implement
  minimal SSE framing (JSON-RPC over `text/event-stream`)
- SSH stdio alternative documented: `ssh <host> halbert-mcp-serve` works
  with zero server changes (SSH keys = auth + encryption)

#### T4b.2 — MCP bearer token auth (NEW `mcp/auth.py`, ~40 lines)

Reuses `prep_token.py` pattern (Task 2):
- `ensure_mcp_token()` — 32-byte hex token, `~/.config/halbert/mcp_token`,
  mode 0600. Env var `HALBERT_MCP_TOKEN` overrides.
- `get_mcp_token()` — env var first, then token file.
- `auth_middleware(handler)` — checks `Authorization: Bearer <token>`.
  Rejects with 401 if missing/mismatched. Disabled in stdio mode.
- Same scope note as PREP_DAEMON_TOKEN: blocks network callers, not
  same-user processes. OS-level controls (Task 5) for same-user isolation.
- Network hardening recommendations documented (LAN bind, reverse proxy
  with mTLS, Tailscale/WireGuard mesh) — not enforced in code.

#### T4b.3 — Instance naming (`mcp/server.py`, ~10 lines)

`--instance-name <name>` and `--hostname <hostname>` flags. Instance name
appears in tool descriptions so the LLM can disambiguate multiple
Halbert instances. Defaults to machine hostname. No behavior change for
single-instance users.

#### T4b.4 — SourcePrep token scoping (documentation, ~0 lines)

Each machine has its own `PREP_DAEMON_TOKEN`. No cross-machine token
sharing. The MCP client never sees SourcePrep tokens — only the MCP
bearer token, which is separate. Document as correct setup.

#### Client configuration (two Halbert instances)

HTTP/SSE (primary remote path):
```json
{
  "mcpServers": {
    "halbert-laptop": {
      "command": "halbert-mcp-serve",
      "args": ["--instance-name", "laptop"]
    },
    "halbert-home": {
      "url": "http://home-server.local:8401",
      "headers": { "Authorization": "Bearer <mcp_token>" }
    }
  }
}
```

SSH stdio (fallback, zero server code):
```json
{
  "mcpServers": {
    "halbert-home": {
      "command": "ssh",
      "args": ["home-server", "halbert-mcp-serve", "--instance-name", "home"]
    }
  }
}
```

#### Test with WarpCLI (remote, HTTP/SSE)

1. Start `halbert-mcp-serve --transport http --port 8401 --bind <LAN IP>`
   on the home server
2. Configure WarpCLI on laptop with the URL + bearer token
3. Call `halbert-home.get_config_value` with a known path/key
4. Verify tier routing + `mcp_response()` boundary work over HTTP
5. Verify unauthorized requests (no token, wrong token) get 401

---

### Phase 5: Remote hardening (deferred)

| Task | Scope | Change |
|------|-------|--------|
| T5.1 Encryption at rest | Home automation / remote | OS-level (LUKS / FileVault) |
| T5.2 Cloud disallowance policy | Advanced config | `allow_cloud_for_secure_content` in being config |
| T5.3 Per-user access scoping | Multi-user | Different users, different access levels to same instance |

Deferred to the home-automation deployment work. Not needed for the
single-machine or single-user multi-instance case (Phase 4b covers that).

---

## Dependency Order

```
DONE: Task 7 → Task 0 → Task 1 → Task 2 → Task 3
NEXT: Phase 2 (T2.1, T2.2, T2.3, T2.4, T2.5, T3.3, T3.6)
THEN: Task 8 (redaction gaps — closes known limits in Task 0 and T2.2)
THEN: Task 4 (rebuild index — operational, needs daemon)
THEN: Phase 4 (MCP server stdio — needs Phase 2 query layer)
THEN: Phase 4b (HTTP/SSE transport + multi-instance auth)
DEFERRED: Phase 5 (remote hardening — encryption at rest, per-user scoping)
```

Phase 2 tasks can be parallelized:
- T2.1 (queries), T2.2 (sensitivity), T2.3 (secure responder) are
  independent of each other
- T2.4 (being config) is independent
- T2.5 (settings UI) depends on T2.4
- T3.3 (assembler integration) depends on T2.1 and T2.2
- T3.6 (context backstop) depends on Task 3 (done)

---

## File Inventory

### Created in this branch

| File | Task | Lines | Purpose |
|------|------|-------|---------|
| `mcp/__init__.py` | T0 | 14 | MCP package init |
| `mcp/response.py` | T0 | 160 | `mcp_response()` — egress redaction boundary |
| `integrations/prep_token.py` | T2 | 118 | PREP_DAEMON_TOKEN management |
| `integrations/secure_detector.py` | T3 | 71 | Two-part secure content detector |
| `tests/test_mcp_response_boundary.py` | T0 | 191 | 17 tests for egress boundary |
| `tests/test_host_staging_unredacted.py` | T1 | 80 | 4 tests for raw staging mode |
| `tests/test_prep_token.py` | T2 | 72 | 6 tests for token management |
| `tests/test_secure_detector.py` | T3 | 81 | 13 tests for detector |

### Modified in this branch

| File | Task | Change |
|------|------|--------|
| `tools/register_host_project.py` | T7, T1, T2 | Hardened excludes; `redact=False` param; bearer auth |
| `config/snapshot.py` | T1 | `redact=False` param |
| `integrations/sourceprep_client.py` | T2 | Bearer auth on all HTTP calls |
| `dashboard/routes/agent.py` | T3 | `secure` param on `_resolve_turn_model`, cloud fallback |

### To create (remaining)

| File | Task | Est. lines | Purpose |
|------|------|-----------|---------|
| `config/sensitivity.py` | T2.2 | ~40 | 3-tier classifier |
| `config/queries.py` | T2.1 | ~100 | Deterministic config query functions |
| `config/secure_response.py` | T2.3 | ~40 | `describe_secret()` deterministic responder |
| `mcp/server.py` | P4/P4b | ~500 | MCP server (stdio + HTTP/SSE, 12 tools, instance naming) |
| `mcp/auth.py` | P4b | ~40 | MCP bearer token auth (reuses prep_token pattern) |
| `tests/test_sensitivity.py` | T2.2 | ~80 | Classifier tests |
| `tests/test_config_queries.py` | T2.1 | ~100 | Query function tests |
| `tests/test_secure_response.py` | T2.3 | ~60 | Responder tests |
| `tests/test_redaction_gaps.py` | T8 | ~80 | Known-prefix + entropy tests |

### To modify (remaining)

| File | Task | Change |
|------|------|--------|
| `config/being_config.py` | T2.4 | Add `SecurityConfig` dataclass |
| `context/assembler.py` | T3.3, T3.6 | Tier-aware config queries + content backstop |
| `ingestion/redaction.py` | T8 | Known-prefix + entropy patterns |
| `dashboard/frontend/src/pages/Settings.tsx` | T2.5 | Security tab |

---

## How to Run Tests

```bash
cd ~/.config/superpowers/worktrees/Halbert/halbert-mcp
PYTHONPATH=halbert_core python -m pytest halbert_core/tests/ -q
```

Current: 57 tests passing across 5 test files:
- `test_host_staging_redacted.py` (17, existing — still passes)
- `test_host_staging_unredacted.py` (4, new)
- `test_mcp_response_boundary.py` (17, new)
- `test_prep_token.py` (6, new)
- `test_secure_detector.py` (13, new)

---

## Key Design Decisions (from the reviewed plan)

1. **No local LLM in the Tier 2 boundary.** Measured to leak (qwen3:4b
   leaked 4/4, qwen3.5:27b leaked + obeyed injections, llama3.1:8b
   refused 2/5). Posture is non-monotonic in model size. Deterministic
   templates replace it — a template cannot be talked into quoting a
   value.

2. **No `secure_model` / `secure_endpoint` config fields.** This host's
   Ollama serves `deepseek-v4-*:cloud`, `gemini-3-flash-preview:cloud`,
   `kimi-*:cloud` through `localhost:11434`. A user who sets
   `secure_model: deepseek-v4-flash:cloud` turns the secure path into the
   exfiltration path while every label reads "local." If a local model is
   ever reintroduced, it must fail closed on `:cloud` suffix and
   `LOCAL_GPU_PROVIDERS` membership.

3. **File-level Tier 0 is a floor, not a ceiling.** Placed after content
   checks so `/etc/hosts` with a routable IP still gets Tier 1 for that
   value, and `/etc/fstab` with cifs creds still gets Tier 2.

4. **The MCP client is itself a cloud pipeline.** WarpCLI/Claude
   Code/Cursor forward tool results to their own cloud vendors. The MCP
   response boundary (`mcp_response()`) is the control that makes the
   unredacted index safe to build. Internal reads (Halbert's own agent)
   keep the raw path.

5. **Tier routing solves the hardest problem by construction.** Secrets
   never enter conversation history via the config query path. The
   content detector (Task 3) is the backstop for other paths (terminal,
   scanners, pastes).

6. **Multi-instance via HTTP/SSE + bearer token, not shared secrets.**
   Each Halbert instance has its own `mcp_token` (bearer auth) and its own
   `PREP_DAEMON_TOKEN` (SourcePrep auth). The MCP client (Warp, Claude
   Code) holds the MCP bearer token for each remote instance but never
   sees SourcePrep tokens. SSH stdio is a zero-code fallback where SSH
   keys replace bearer auth. Per-user access scoping (different users,
   different access levels to the same instance) remains deferred to
   Phase 5 — Phase 4b solves single-user multi-instance, not multi-user.

---

## References

- Plan: `.handoff/HALBERT-MCP-PLAN-2026-08-28.md`
- Redaction layer: `halbert_core/halbert_core/ingestion/redaction.py:126` (`_is_secret_key`), `:1221` (`redact_text`)
- Model client: `halbert_core/halbert_core/model/client.py:76` (`LOCAL_GPU_PROVIDERS`)
- Model resolution: `halbert_core/halbert_core/dashboard/routes/agent.py:363` (`_resolve_turn_model`)
- Config parser: `halbert_core/halbert_core/config/parser.py`
- Config snapshot: `halbert_core/halbert_core/config/snapshot.py`
- Config drift: `halbert_core/halbert_core/config/drift.py`
- Being config: `halbert_core/halbert_core/config/being_config.py`
- Context assembler: `halbert_core/halbert_core/context/assembler.py`
- SourcePrep daemon auth: `src/prep/server.py:223-236` (PREP_DAEMON_TOKEN)
- Warp ZDR: https://docs.warp.dev/enterprise/security-and-compliance/security-overview/
