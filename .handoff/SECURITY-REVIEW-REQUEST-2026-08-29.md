# Halbert MCP Trust Boundary — External Review Request

**Date:** 2026-08-29
**Worktree:** `~/.config/superpowers/worktrees/Halbert/halbert-mcp` on branch `feat/halbert-mcp`
**Reviewer ask:** UX advice on the Settings security tab + architectural review of the trust boundary system

---

## What This Is

Halbert is a home-automation agent that reads the host's config files
(SSH config, LaunchDaemons, fstab, credentials, etc.) and exposes them
to an LLM via MCP tools. The LLM might be local (Ollama) or cloud
(Claude, GPT, Gemini). The trust boundary system controls what the LLM
sees — specifically, how secrets in config files are described to the
LLM without being revealed to it.

The system has two egress paths that must never leak a secret:

1. **MCP response boundary** — when an external MCP client (WarpCLI,
   Claude Code, Cursor) calls a Halbert tool, the response passes
   through `mcp_response()` which redacts secrets structurally and
   textually before the response leaves the process.

2. **Secure content routing** — when Halbert's own agent assembles
   context for a model call, `detect_secure_content()` checks whether
   the context contains secrets. If it does, the turn is routed to a
   local model instead of a cloud model.

The config query path (`get_config_value`) is the primary way the LLM
asks about config values. It applies a three-tier sensitivity
classifier and routes Tier 2 (secrets) through `describe_secret()`,
which returns metadata about the value (length, charset, entropy,
credential type, breach risk, last changed, view command) without the
value itself.

---

## The Three Tiers

| Tier | Name | Examples | Default routing |
|------|------|----------|----------------|
| 0 | Public | Service names, booleans, structural keys | Raw value to any model |
| 1 | Operational | SSH port, routable IPs, firewall rules | User-configurable (cloud_ok / local_only / redact) |
| 2 | Secrets | Passwords, tokens, API keys, private keys | Deterministic description only (describe_secret) |

Tier 2's default is `local_only` — the LLM gets a description, never
the raw value. There is an escape hatch (`cloud_ok_acknowledged`) that
requires explicit confirmation in the UI, and a per-key escape hatch
(`cloud_ok_keys`) that allows specific key names to bypass the Tier 2
boundary while the global setting stays locked.

---

## Key Design Decisions

### 1. No LLM in the Tier 2 boundary

The original plan proposed a "local secure LLM" that would describe
secrets to the main LLM. This was measured to leak: qwen3:4b leaked
4/4 secrets, qwen3.5:27b leaked and obeyed injections, llama3.1:8b
refused 2/5 requests. Posture is non-monotonic in model size. The
deterministic `describe_secret()` replaces it — a template cannot be
talked into quoting a value.

### 2. Architectural guarantee, not policy

Research into AWS `describe-secret`, Snowflake `DESCRIBE SECRET`, and
AgentSecrets zero-knowledge architecture found that the guarantee must
be architectural (no code path exists), not policy-based (code path
exists but is disabled). `describe_secret()` has no code path that
sends the secret value to any external service. There is no config
option that enables sending the value, because the code path does not
exist. This is enforced by 7 architectural guarantee tests that mock
all network calls and assert `describe_secret` triggers none.

### 3. File-level Tier 0 is a floor, not a ceiling

`/etc/hosts` is Tier 0 by file, but if it contains a routable IP, that
value gets Tier 1. `/etc/fstab` is Tier 0 by file, but if it contains
CIFS credentials, those values get Tier 2. The file-level tier is
applied AFTER content checks, not before.

### 4. The MCP client is itself a cloud pipeline

WarpCLI/Claude Code/Cursor forward tool results to their own cloud
vendors. The MCP response boundary (`mcp_response()`) is what makes it
safe for the LLM to call Halbert tools. Internal reads (Halbert's own
agent) keep the raw path.

### 5. Two standalone human-run tools are NOT in the Tier 2 path

`credential_validation.py` (checks if a credential is still active by
calling the issuing service's API) and `compromise_detection.py`
(checks HIBP and GitHub secret scanning) send the secret to external
services. They are documented as standalone human-run CLI tools, not
part of the `describe_secret` path. Their docstrings say this
explicitly. They are not wired into any agent-facing code path.

---

## File Inventory

### Core trust boundary

| File | Purpose | Lines |
|------|---------|-------|
| `config/sensitivity.py` | Three-tier classifier (0/1/2) | 147 |
| `config/secure_response.py` | `describe_secret()` — deterministic metadata-only responder | 176 |
| `config/queries.py` | `get_config_value()` — tier-routed config query API | 470 |
| `config/being_config.py` | `SecurityConfig` dataclass (operational_tier, secret_tier, public_files, extra_secret_keys, cloud_ok_keys) | 265 |
| `mcp/response.py` | `mcp_response()` — egress redaction boundary for MCP tool responses | 162 |
| `integrations/secure_detector.py` | `detect_secure_content()` — two-part detector (provenance + content) | 71 |
| `ingestion/redaction.py` | `redact_text()` — the redactor used by all paths (keyword, prefix, entropy, PEM, JWT, URL creds) | ~1500 |
| `config/credential_formats.py` | Credential format database — 30+ known formats with breach_risk levels | ~340 |
| `config/dynamic_prefixes.py` | Fetches updated credential format patterns from a remote source, caches locally | ~200 |
| `config/secret_correlation.py` | Cross-file secret correlation by SHA-256 hash — "this password also appears in 3 other files" | 204 |

### MCP server

| File | Purpose |
|------|---------|
| `mcp/server.py` | 12-tool MCP server (stdio + HTTP/SSE), tier-routed `get_config_value`, `mcp_response()` on every tool |
| `mcp/auth.py` | Bearer token auth for HTTP/SSE transport |

### Standalone human-run tools (NOT in the Tier 2 path)

| File | Purpose |
|------|---------|
| `config/credential_validation.py` | Validates credentials against issuing service APIs. Human-run only. |
| `config/compromise_detection.py` | Checks HIBP and GitHub secret scanning. Human-run only. |

### Frontend

| File | Purpose |
|------|---------|
| `dashboard/frontend/src/pages/Settings.tsx` | Settings page with Security tab (tier pickers, escape hatches, lists) |

### Tests

| File | Tests | What it covers |
|------|-------|----------------|
| `tests/test_secure_response.py` | 39 | describe_secret output, architectural guarantee (no network calls), breach_risk, last_changed |
| `tests/test_config_queries.py` | ~30 | Tier routing in get_config_value, staleness, structure/diff/dependencies |
| `tests/test_sensitivity.py` | ~20 | Three-tier classification, floor-not-ceiling, extra_secret_keys |
| `tests/test_mcp_response_boundary.py` | 17 | Egress redaction (config-value-pair, secret dict keys, text) |
| `tests/test_mcp_server.py` | ~20 | Tool dispatch, tier routing through server, mcp_response on output |
| `tests/test_mcp_http.py` | ~15 | HTTP/SSE transport, bearer auth, rate limiting, CORS |
| `tests/test_secret_correlation.py` | ~20 | Hash-based correlation, describe_with_correlations |
| `tests/test_implementation_gaps.py` | ~15 | cloud_ok_keys escape hatch, staleness, base64/nested JSON detection |
| `tests/test_being_config_security.py` | ~10 | SecurityConfig load/save/validate |
| `tests/test_secure_detector.py` | 13 | Provenance + content detection, fail-toward-secure |
| `tests/test_redaction_gaps.py` | ~15 | Known-prefix, high-entropy backstop, netrc, YAML sequences, hashes |
| `tests/test_credential_formats.py` | ~20 | Format identification, breach_risk, confidence levels |
| `tests/test_dynamic_prefixes.py` | ~10 | Remote fetch, cache, fallback to bundled |
| `tests/test_credentials_scope.py` | ~10 | Credentials scope manifest (~/.aws, ~/.kube, ~/.netrc, .env, ~/.docker, ~/.ssh/config) |

**Total: 350 tests passing across 17 test files.**

---

## What We're Asking The Reviewer

### UX review (primary ask)

The Security tab in `Settings.tsx` (lines 432-730) has these cards:

1. **MCP Trust Boundary overview** — static text explaining the three tiers
2. **Tier 1 — Operational Values** — three-button picker (Cloud OK / Local Only / Redact)
3. **Tier 2 — Secrets** — locked badge + escape hatch with two-step confirmation
4. **Public Files** — textarea, one path per line
5. **Extra Secret Keys** — textarea, one key per line
6. **Per-Key Cloud Escape Hatch** — textarea, one key per line, with yellow warning

Questions for the UX reviewer:

- **Is the three-tier model comprehensible to a non-security-expert user?**
  The overview card explains it in three paragraphs. Is that enough, or
  does it need a visual diagram / interactive example?

- **Is the escape hatch flow safe?** The Tier 2 escape hatch has a
  two-step confirmation ("I understand the risk" -> "Confirm: allow
  cloud access to secrets"). Is two steps enough for an action that
  sends all secrets to a cloud vendor? Should it require typing a
  confirmation phrase?

- **Is the per-key escape hatch understandable?** The `cloud_ok_keys`
  card lets users list specific key names that bypass the Tier 2
  boundary. The warning says "raw values will appear in your cloud LLM
  vendor's inference logs." Is this clear enough? Should there be
  per-key confirmation rather than a blanket textarea?

- **Are the textareas the right UX for managing lists?** Public files,
  extra secret keys, and cloud_ok_keys are all textareas with
  one-item-per-line. Should these be tag inputs with autocomplete
  (e.g. suggesting known config key names for extra_secret_keys)?

- **Should the tier pickers show impact?** When the user selects
  "Cloud OK" for Tier 1, should the UI show a live count of how many
  config values would be exposed? When they select "Local Only",
  should it show how many would be described instead of revealed?

- **Is the "Locked" badge on Tier 2 sufficient?** It's a small badge
  that says "Locked" or "Acknowledged". Should the entire card change
  appearance (border color, background) when the escape hatch is
  active?

### Architectural review (secondary ask)

- **Is the two-egress-path model sound?** MCP response boundary for
  external clients, secure content routing for internal agent. Both
  use `redact_text()` as the underlying detector. Is there a gap
  between them?

- **Is the staleness handling in queries.py correct?** When a config
  file changes between snapshots, `get_config_value` re-parses the
  live file and writes the new canon record. This means the canon DB
  is updated as a side effect of a read query. Is this surprising? Is
  there a race condition if two queries hit the same changed file
  simultaneously?

- **Is the correlation index safe?** `secret_correlation.py` stores
  SHA-256 hashes (truncated to 16 hex chars) of secret values. The
  hash is one-way. Could an attacker who reads the correlation index
  file recover any secrets? (The truncation is to 64 bits, which is
  not enough for a rainbow table over the full value space, but is
  enough for collision resistance across one machine's config files.)

- **Should `describe_secret` return the file path?** It currently
  returns `file_path` in the result. The LLM sees the path where the
  secret lives. Is this a leak? (The path is needed for the
  `view_command` field, which tells the user how to view the value
  locally. But the LLM also sees it, and could use it to instruct a
  file-read tool to bypass the boundary.)

- **Is the `_view_command` field safe to show to an LLM?** It returns
  a shell command like `grep password /etc/myapp.conf`. The LLM could
  instruct the user to run it, or could use a shell-execution tool to
  run it and get the raw value. Is this an unacceptable bypass risk,
  or is it acceptable because the command runs locally and the user
  is in control?

---

## How To Run

```bash
cd ~/.config/superpowers/worktrees/Halbert/halbert-mcp
PYTHONPATH=halbert_core python -m pytest halbert_core/tests/ -q
```

To start the dashboard and see the Settings UI:
```bash
cd halbert_core/halbert_core/dashboard/frontend
npm install && npm run dev
```

The Security tab is at `/settings?tab=security`.

---

## Known Gaps (documented, not yet addressed)

1. **Short context-free secrets under neutral keys.** A 7-character
   password under a key like `"location"` is not caught by any
   detector — no known prefix, below the 32-char entropy threshold,
   and the key name doesn't match `_is_secret_key`. The entropy
   threshold is set high to avoid over-redacting UUIDs and SHA-256
   hashes. This is the same gap documented in `sensitivity.py` and
   `mcp/response.py`.

2. **`_view_command` as a bypass vector.** The view command tells the
   LLM how to read the raw value locally. If the LLM has access to a
   shell-execution tool, it could run the command and get the raw
   value, bypassing the entire boundary. This is a design trade-off:
   the command is useful for the human user, but it's also a roadmap
   for the LLM.

3. **File path in describe_secret output.** The LLM sees the file path
   where the secret lives. Combined with a file-read tool, this could
   be used to bypass the boundary. The path is needed for the view
   command and for the `last_changed` timestamp.

4. **Canon DB updated as side effect of read queries.**
   `_get_current_canon()` in `queries.py` re-parses changed files and
   writes new canon records during what is nominally a read
   operation. This keeps the canon DB current but means reads have
   write side effects.

5. **Standalone modules still in `config/`.**
   `credential_validation.py` and `compromise_detection.py` have
   corrected docstrings but still live in `config/` rather than a
   `cli/` directory. Follow-up todo exists.

---

## Research References

- AWS describe-secret: https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_DescribeSecret.html
- Snowflake DESCRIBE SECRET: https://docs.snowflake.com/en/sql-reference/sql/desc-secret
- AgentSecrets zero-knowledge: https://agentsecrets.theseventeen.co/docs/concepts/zero-knowledge
- AgentSecrets architecture: https://github.com/The-17/agentsecrets/blob/main/docs/ARCHITECTURE.md
- Infisical Agent Vault: https://github.com/Infisical/agent-vault
- Keys on the Wire: https://github.com/inflightsec/agent-vault-proxy
- TruffleHog: https://github.com/trufflesecurity/trufflehog
- Tier 2 recalibration research: `.handoff/TIER2-RECALIBRATION-2026-08-29.md`
- Original MCP plan: `.handoff/HALBERT-MCP-PLAN-2026-08-28.md`
- Original MCP handoff: `.handoff/HALBERT-MCP-HANDOFF-2026-08-28.md`
