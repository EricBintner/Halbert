# REV-01 Review Results — Security Architecture & Trust Boundaries (2026-08-31)

Reviewer: GLM-5.3, adversarial pass with verification (worktree `central-todo-batches`, branch `worktree-central-todo-batches`, reviewed at commit `162f3965` + the U1 security commit `5a132654` already on the branch).

Method: every finding below was traced end-to-end in the current code and, where it claims a behavior, **reproduced by running the worktree's own code** through throwaway scripts (`/tmp/rev01_repro*.py`, sandboxed to temp dirs via `HALBERT_CONFIG_DIR` and patched canon/snapshot dirs — no production config was touched). Findings are marked CONFIRMED (full path traced and/or reproduced) or PLAUSIBLE (could not fully trace). Anything I could not substantiate was discarded.

Verification runs: `test_tier2_guarantee.py`, `test_security_roles.py`, `test_cli_security.py`, `test_config_queries.py`, `test_config_snapshot_redacted.py`, `test_secure_response.py` (92 passed); federation `test_peer_redaction.py`, `test_peer_tool_allowlist.py`, `test_token_revocation.py`, `test_secure_model_no_offload.py` (34 passed, 3 skipped).

---

## 1. Verdict per area

| Area | Verdict |
|---|---|
| **Tier 0/1/2 sensitivity gates** (`sensitivity.py`, `queries.py`) | Routing logic is sound and fails safe (invalid TTL → local_only; file floor placed after content checks). **But the canon DB it reads is redaction-incoherent — see F1**; in the default deployment the Tier-2 describe path emits garbage metadata and false correlations. |
| **Tier 2 recalibration** (`secure_response.py`, `cli/`) | Architectural guarantee **holds**: `describe_secret` has no network path, no value field; the network-calling credential tools live in `cli/` and are unwired from the describe path. **But its output is computed on the redaction placeholder in default deployments (F1-A).** |
| **Redaction backstop** (`ingestion/redaction.py`, `mcp/response.py`) | Strong. Line pass + substitutions + nested-JSON/base64/known-prefix/high-entropy passes; documented known gaps remain (short context-free secrets < 32 chars under neutral keys; sequence-item credentials; credentials with whitespace sharing a line). These are accepted, documented trade-offs — not new findings. |
| **MCP dispatch egress gate** (`mcp/server.py:930`, `:956`) | **Resolved from packet.** Every `tools/call` result wraps through `mcp_response()` at the choke point, notifications included; the dispatcher catch-all redacts the error text. Pinned by `test_tier2_guarantee.py` (all pass). |
| **`credentials_admin`** | **Resolved, refactored.** Lives as a role scope in `config/roles.py` + `tools/register_host_project.py` (staging boundary: credential files stage only under the credentials scope, key material never stages, default staging redacts). The packet's description (a `being_config.py`/`settings.py` field) is outdated. |
| **Security tab UI / unlock path** | UI is clean: phrase held in component state, reset on modal close, nothing persisted to localStorage; TTL choices (1h/restart/permanent) wire correctly to `secret_tier_expiry`/`volatile_unlock`. **Server-side friction is weaker than claimed — see F2.** |
| **Secure content routing** (assembler backstop → model gate) | Sound. Two-part detector (provenance + `redact_text` probe), latched per turn (`state_machine.py:1633-1639`), and `_resolve_turn_model` fails **closed** (`_SecureContentBlocked`) when a secure turn finds no local model. Pins do not override the boundary. |
| **Peer/compute boundary** (federation) | Allowlist is frozen with an import-time self-check; every peer compute response wraps `mcp_response()` (`compute_endpoint.py:194`). The inference path itself is still a stub (`_submit_to_broker` raises `NotImplementedError`) — see §5. |
| **MCP HTTP transport** | Bearer auth with constant-time compare, fail-closed on short tokens, per-IP rate limit, SSE cap, explicit-origin CORS only. One minor input-validation issue (F6). |

---

## 2. Findings (most severe first)

### F1 — CONFIRMED (High, correctness/architecture; Medium, disk): the canon DB's redaction state is incoherent across the pipeline, breaking the Tier-2 describe feature and the on-disk invariant

The tree contains **two contradictory designs for `~/.local/share/halbert/config/canon/`**:

- `config/snapshot.py:46-77` (+ the whole of `test_config_snapshot_redacted.py` and `watcher.py:34` calling `snapshot()` with the **default `redact=True`**) asserts the invariant: *the canon DB must carry no plaintext credential* — the module carries a 30-line comment calling unredacted canon "plaintext credentials written by the pipeline whose stated job includes removing them."
- `scripts/rebuild_sourceprep_unredacted.py` + `test_security_roles.py` (the Tier-2 recalibration follow-through) assert the opposite: *the canon DB is raw by design, and the egress boundaries (tier routing + the MCP choke point) are what protect it.*

Three consequences, all reproduced against this worktree's code (production path: `snapshot(redact=True)` → `get_config_value`):

**(a) `_write_canon` persists plaintext credentials to disk** — `config/queries.py:127-144`. On every stale-or-never-snapshotted file (live hash ≠ snapshot hash — the common case for any changing config), `_get_current_canon` (`queries.py:101-124`) re-parses the live file and writes the canon record **unredacted**. Reproduced: after one query on a modified file, the canon record on disk contained the plaintext `Password=hunter2same`. This violates exactly the invariant `test_config_snapshot_redacted.py` pins, and the readers the snapshot comment names (`drift.py`, `edge_extractor.py`) read the result.

**(b) `describe_secret` describes the placeholder, not the secret** — for snapshot-fresh files, `get_config_value` extracts values from the **redacted** canon, so the Tier-2 path calls `describe_secret(key, "<secret>")`. Reproduced: description reports `length: 8, entropy: 2.75` (the properties of the string `<secret>`) for every secret; `credential_type`/`breach_risk` are always absent (the placeholder matches no format). The flagship Tier-2 deliverable — useful metadata about a secret — is **inert** in the default deployment, and silently so.

**(c) The correlation index collapses all secrets into one hash** — `snapshot.py:117-135` builds the index from the canon it just wrote (redacted in the default path), so every secret hashes the same placeholder `"<secret>"`. Reproduced: querying `Token=zzz-different-secret-42` (a *different* secret) reported correlations with both `Password` locations — false positives that misdirect rotation advice. When the canon is raw (rebuilt via the unredacted script), the same index works as designed.

Worst property: behavior flips **file-by-file** depending on which writer last touched the record (watcher → redacted; stale re-parse / unredacted rebuild → raw). Tier-2 behavior is nondeterministic in production.

**Failure scenario (b):** user asks the agent about a password → MCP `get_config_value` → file unchanged since last watcher snapshot → canon value is `"<secret>"` → LLM is told the credential is 8 chars, symbols-only, entropy 2.75, unknown type → wrong security advice, no breach risk, garbage correlations.

**Suggested fix:** pick one invariant and make every writer follow it. The Tier-2 recalibration direction (raw canon + egress boundaries) is the coherent choice: default `snapshot()` to `redact=False` (keeping the RAW_DIR text sink redacted), retire the redacted-canon invariant and its pinning test, and add an assertion-level test that `describe_secret` receives real values. If redacted canon must stay, then `_write_canon` must redact like `_redact_canon` does, the correlation index must be built from a raw in-memory parse (never from disk), and `describe_secret` must be fed from a live re-read rather than the canon.

### F2 — CONFIRMED (Medium): the unlock route's friction defeats itself, and the phrase is public

`dashboard/routes/settings.py:3076-3091`:

- The 403 on a wrong phrase **contains the phrase**: `"Unlocking secrets requires the confirmation phrase: EXPOSE SECRETS"` (`:3085-3086`). The threat the comment names — "a bare curl to POST /settings/being could unlock all secrets" — is handed the answer to its own challenge. Against an *agent-driven* unlock (the realistic threat: a prompt-injected agent with dashboard access), the error message teaches the model exactly what to type.
- The phrase is hardcoded in an open-source repo (`UNLOCK_PHRASE = "EXPOSE SECRETS"`, `settings.py:35`; also rendered verbatim in the UI, which is fine for UX). It is friction, not a secret — acceptable, but only if it is not also disclosed on failure.
- Any exposure-increasing change other than a fresh `local_only → cloud_ok_acknowledged` transition needs **no phrase at all**: extending an existing unlock with a later expiry (or `expiry=None`, i.e. making it permanent) and editing `cloud_ok_keys` both bypass the check (`transitioning_to_unlock` only fires on the transition).

**Failure scenario:** agent (or script) POSTs `{"security": {"cloud_ok_keys": ["serial", "location"]}}` with no phrase → 200 OK, persisted. No error message needed, no phrase needed. See F3 for what that hatch then does.

**Suggested fix:** never echo the phrase in an error response; require the phrase for *any* security change that increases exposure (hatch additions, expiry extension, unlock); consider a per-install random phrase generated at unlock-time and stored 0600 next to `being.yml`, shown once in the UI.

### F3 — CONFIRMED (Medium): the per-key escape hatch and the dispatch choke point disagree — the hatch is inert for vocabulary keys and silently leaks for `extra_secret_keys` keys

The UI (`pages/Settings.tsx` per-key card) promises: "Keys listed here bypass the Tier 2 boundary. Their raw values will appear in your cloud LLM vendor's inference logs." Actual behavior splits on `_is_secret_key`:

- **Key matches the built-in secret vocabulary** (password, token, api_key… including the card's own placeholder example `WEATHER_API_KEY` — `weatherapikey` contains `api`): `get_config_value` returns the raw value (queries.py:320-322), but `mcp_response` rule 1 (`mcp/response.py:121-133`) re-redacts the `value` sibling. The hatch is **inert** — the UI promise is false for exactly the keys a user is most likely to list.
- **Key is Tier-2 only via `extra_secret_keys`** (e.g. `serial`): not a `_is_secret_key` name, so neither structural rule fires, and a short low-entropy value has no `redact_text` pattern. Reproduced end-to-end: `get_config_value(..., extra_secret_keys=["serial"], cloud_ok_keys=["serial"])` returned the raw value **through `mcp_response`** unchanged: `{'key': 'serial', 'tier': 2, 'value': 'XK-9827-4415-B2', 'acknowledged': True}` crosses the MCP boundary.

The same asymmetry applies to the **global** unlock (`cloud_ok_acknowledged`): raw vocabulary keys are still re-redacted at the choke point; `extra_secret_keys`-classified values cross. So the Tier-2 unlock's blast radius is both smaller than the UI claims (for password/token/api-key-class values) and larger in a subtler way (for user-classified keys).

**Failure scenario:** user adds `serial` (their device serial, classified Tier 2 via `extra_secret_keys`) to the hatch believing only that key is affected; any MCP client (cloud-forwarding) receives the raw serial on `get_config_value` — and, per F2, an agent can add keys to the hatch without any confirmation.

**Suggested fix:** make the choke point *aware* of the acknowledgment: `mcp_response` (or the `get_config_value` handler) should consult the effective tier + `cloud_ok_keys` and annotate/allow deliberately, so the hatch behaves identically for all key classes — or drop the hatch and document that the MCP boundary always redacts vocabulary keys.

### F4 — CONFIRMED (Medium-Low): cross-process lost-update race on `being.yml` can silently revert a relock

`save_being_config` uses an atomic temp-file rename (good against corruption) but there is **no file lock** across processes, and `load_being_config` also *writes* (persisting relocks, `being_config.py:474-478`). The dashboard's `_being_config_lock` serializes only within the dashboard process. The MCP server process writes too (`set_autonomy_level` → load-modify-save, `mcp/server.py:550-557`).

**Failure scenario:** user relocks secrets in the UI (persisted `local_only`); concurrently the MCP server handles `set_autonomy_level` using a config loaded a moment earlier, when the tier was still `cloud_ok_acknowledged` — its save persists the whole stale object, restoring the unlock. Window is request-lifetime (small), but the unsafe direction (relock reverted) exists, and it compounds F2's frictionless paths. Volatile-unlock state can be lost the same way.

**Suggested fix:** `fcntl`/`flock` around every load-modify-save of `being.yml` (the lock file living beside it), or route all security-state writes through a single owner.

### F5 — CONFIRMED (Low): the correlation index is an offline dictionary target and a secret-location map

`config/secret_correlation.py:40-42` stores `sha256(secret)[:16]` keyed to `{path, key, section}` at `~/.local/share/halbert/config/secret_correlations.json`. The docstring argues truncation makes it unusable as a lookup table — true for high-entropy tokens, **not** for human passwords: a 64-bit truncation does not slow a dictionary/guess attack at all (any candidate is hashed and compared), and the file additionally enumerates *where every secret on the machine lives*. In the raw-canon deployment (per F1's likely fix) this covers every harvested credential. Same-local-user attackers can read secrets directly, so severity is low, but backup/sync exfiltration of this one file is meaningful.

**Suggested fix:** key the hash with a locally-generated random HMAC key stored separately (pepper) so the file alone verifies nothing; and/or build the index on demand, never persisting it.

### F6 — CONFIRMED (Low): MCP HTTP `do_POST` does not validate Content-Length bounds

`mcp/server.py:1080-1085`: `content_length = int(header)`; only `> 1MB` is rejected. A negative value reaches `self.rfile.read(negative)` → read-until-EOF (unbounded memory, held thread); a non-integer raises unhandled. Local-DoS only (default bind 127.0.0.1, bearer auth, per-IP rate limit), hence Low.

**Suggested fix:** `if content_length < 0 or content_length > MAX: 413`, and wrap the `int()` in try/except.

### Verified negative (no action needed)

- **Browser CSRF against `/api/settings/being` is blocked**: a cross-site simple request cannot carry `application/json`, and FastAPI rejects `text/plain` JSON bodies with 422 (reproduced); cross-origin JSON requires a preflight that the explicit-origin CORS policy denies. The F2 threat is local processes/agents, not web pages.
- **Exception-path egress**: the dispatcher catch-all redacts error text (pinned by `test_tier2_guarantee.py::test_exception_message_cannot_smuggle_a_secret`).
- **Numeric PINs under secret keys** are caught by `mcp_response` rule 2 (int, non-bool → `<secret>`).
- Python 3.10's `fromisoformat` not accepting the UI's `Z`-suffixed ISO timestamps fails **closed** (tier downgrades to local_only) — availability quirk, not a leak.

---

## 3. Resolved from the packet (fixed since 2026-08-29; one line each)

- **Dispatch-level egress gate** — landed (`5a132654`): every `tools/call` result wraps through `mcp_response()` at `mcp/server.py:930`, notifications included; the catch-all error message is redacted (`:956`). Pinned by `test_tier2_guarantee.py`.
- **Tier 2 recalibration** — complete: `describe_secret` is metadata-only with no network path; the network-calling credential tools moved to `cli/` as standalone human-run tools (`check_credential.py`, `check_breach.py`), unwired from the describe path (pinned by `test_cli_security.py`).
- **CLI script migration** — done (packet already noted 2026-08-30).
- **TTL expiry** — runtime re-check at the single decision point (`effective_secret_tier()`) plus the `queries.py:263-271` backstop; expired unlocks downgrade at query time without a reload.
- **Volatile unlock ("until restart")** — implemented with once-per-process relock guard (`being_config.py:414-481`); persisted flag consumed by the next fresh process; UI TTL wiring correct.
- **`credentials_admin` scope** — exists, refactored into the role-scope registry (`config/roles.py:103-112`) + `register_host_project` staging, with behavior pinned by `test_security_roles.py` (scope isolation, default redaction, raw-by-design flag, key-material exclusion, tier routing on raw content). The packet's file references (`being_config.py`, `settings.py`) are stale.
- **`get_being_config` secret strip** — `ha_token`, `ha_url`, and the whole `security` block popped (`mcp/server.py:163-183`).
- **Security tab UI polish** (TTL wiring, null guards, list validation, ARIA, polling) — present and coherent; no localStorage persistence of the phrase or unlock state.
- **HTTP transport hardening** — rate limit (monotonic clock, bounded), SSE cap, constant-time bearer compare, fail-closed short-token refusal, no-token-echo, explicit-origin-only CORS.
- **Peer compute redaction** — `mcp_response` applied to every peer response (`compute_endpoint.py:194`), tool allowlist frozen with import-time overlap self-check; federation boundary tests pass.

---

## 4. Open packet items still requiring live work

- **Packet §5.2 (unredacted SourcePrep indexing, operational gate):** `scripts/rebuild_sourceprep_unredacted.py` now exists with a built-in egress self-check (stages raw, rebuilds, probes both boundaries, exit 2 = EGREGIOUS). Running it requires the live daemon + `PREP_DAEMON_TOKEN`. Note it hard-codes the raw-canon decision that F1 says must be reconciled with `snapshot()`'s default — run it *after* F1's invariant is settled.
- **Packet §5.3 (live scanner egress testing with mock API keys):** not done; needs a live macOS host run across the discovery scanners.

## 5. Untestable without a live deployment

- Whether the deployed canon DB on a real host is currently raw or redacted (F1's in-situ behavior depends on which writer last ran — watcher vs. unredacted rebuild vs. stale re-parse).
- The SourcePrep daemon's index build with raw staged files: whether `search_knowledge` results can surface raw credential fragments beyond what `mcp_response` catches (the backstop redacts strings, but chunked retrieval across scopes is only provable live).
- Live scanner egress (mock API keys through every macOS discovery scanner).
- The compute endpoint end-to-end (`federation-9.4`): `_submit_to_broker` is a `NotImplementedError` stub, so the peer inference + redaction path, and its planned SSE streaming (which will need a buffering redaction filter), cannot be exercised yet.
- Anything depending on a real `being.yml` unlock/relock cycle across *multiple* long-lived processes (F4's race window is real but requires process orchestration to observe).