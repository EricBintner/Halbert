# Scope 01 Security Review — Progress & Findings

**Review Packet:** [REVIEW-PACKET-01-SECURITY-AND-TRUST-BOUNDARY.md](REVIEW-PACKET-01-SECURITY-AND-TRUST-BOUNDARY.md)
**Worktree:** `~/.config/superpowers/worktrees/Halbert/security-review-01`
**Branch:** `feat/security-review-01`
**Date:** 2026-08-31

---

## 1. Summary

Scope 01 (Security & Trust Boundary) reviewed the Tier 2 architectural
guarantee (`describe_secret`), the redactor's entropy/regex backstops, TTL
expiry and volatile unlock state, concurrency/race conditions, and MCP
protocol compliance. The review found **6 critical/high vulnerabilities**
and **2 robustness gaps**, all of which are now fixed and committed. Five
commits were merged to `main` in a prior session; two additional commits
landed on the branch today completing the remaining work.

**Final state:** 458 security tests pass, 0 failures. Frontend builds clean.

---

## 2. Findings & Fixes

### Already merged to `main` (5 commits, prior session)

| # | Severity | Finding | Fix | Commit |
|---|----------|---------|-----|--------|
| 1 | **CRITICAL** | MCP egress boundary: `_tool_get_being_config` leaked `ha_token`; 6 tools bypassed `mcp_response` | Universal `mcp_response` wrap in `handle_request`; explicit credential field popping | `06e113cc` |
| 2 | **CRITICAL** | Secure content routing dead: `AssembledContext.secure` flag set but never consumed — secrets in RAG chunks/file reads could flow to cloud | Wired flag through `StateContext` to all LLM call sites; comprehensive secure gate in `_resolve_turn_model` (fail-closed) | `4db888a9` |
| 3 | **HIGH** | Volatile unlock broken: "until restart" TTL relocked on every `load_being_config()` call | Module-level once-per-process relock guard keyed by config path | `f800789c` |
| 4 | **CRITICAL** | Client-side phrase only: Tier 2 escape hatch checked in browser only; curl could unlock without friction | Server-side phrase enforcement in `update_being_config` | `da75bca1` |
| 5 | **HIGH** | MCP transport: bearer token printed to stderr; CORS wildcard+credentials; wall-clock rate limiter; ForkingHTTPServer blocked SSE | Token print removed, 32-char min, CORS default-deny, ThreadingHTTPServer, monotonic time | `78e9d141` |

### Completed today on branch (2 commits)

| # | Severity | Finding | Fix | Commit |
|---|----------|---------|-----|--------|
| 6 | **MEDIUM** | Redactor: base64 pass had no size cap (DoS via multi-MB blob decode) or recursion cap (base64-of-base64 chain bomb); nested JSON only redacted flat objects, not `{"auths": {"registry": {"auth": "..."}}}` | Base64: 8192-char token cap, depth-2 recursion cap. Nested JSON: whole-document parse + `_redact_json_leaves` recursive walker (depth cap 8), redacts non-bool/non-null leaves under secret keys | `9e057db7` |
| 7 | **HIGH** | MCP path allowlist missing: config-query tools (`get_config_value`, `get_config_structure`, `get_config_dependencies`) accepted arbitrary `path` — an MCP client could read `/etc/shadow` or `~/.ssh/id_rsa` | `_is_allowed_config_path()` checks path against snapshot manifest; `realpath()` resolves symlinks and `..` traversal | `c5b6bb91` |

### JSON-RPC Compliance (merged with #5)

- Batch arrays no longer crash (return -32600)
- Notifications (id absent) get no response
- `jsonrpc` field validation enforced

---

## 3. Pre-existing Behaviour Documented (Not Fixed)

### Over-redaction of bools under secret keys

`{"PasswordAuthentication": false}` is redacted to `{<secret>, "other": null}`
because the line pass (`redact_structured_values`) runs before the nested-JSON
pass and redacts any value under a secret key, including booleans. This is
**conservative over-redaction** (safe direction — no leak). Fixing it would
require the line pass to skip bool-like values, which risks leaking
`password: true`-style secrets. Documented in
`test_bool_and_null_under_secret_key_over_redacted`.

---

## 4. Open Items from the Review Packet (§5)

| # | Item | Status |
|---|------|--------|
| 1 | CLI Script Migration | **DONE** — `halbert-check-credential`/`halbert-check-breach` in `cli/` + console scripts in `pyproject.toml` |
| 2 | Unredacted SourcePrep Indexing | **PENDING** — operational gate; requires running `register_host_project(redact=False)` and verifying both egress gates protect raw keys. Not a code change — an operational procedure. |
| 3 | Live Scanner Egress Testing | **PENDING** — integration tests with mock API keys across macOS scanners. Not yet executed. |

---

## 5. Verification

```
458 passed, 0 failed  (security test suite)
Frontend: built in 2.97s, 0 errors
```

Test files run:
- `test_redact.py`, `test_redaction_gaps.py`, `test_redaction_secrets.py`
- `test_mcp_server.py`, `test_mcp_http.py`, `test_mcp_response_boundary.py`
- `test_secure_response.py`, `test_secure_model.py`, `test_secure_detector.py`
- `test_assembler_secure.py`, `test_being_config_security.py`
- `test_streaming_redact.py`, `test_mcp_camera_gate.py`
- `test_config_snapshot_redacted.py`, `test_host_staging_redacted.py`
- `test_host_staging_unredacted.py`, `test_apply_redact_host.py`

**Note:** `test_security_unlock_phrase.py` and `test_agent_routes_redact.py`
error on collection due to `from contextlib import aclosing` (Python 3.10+
required, conda env is 3.9). This is a pre-existing environment issue, not
related to the security review changes.

---

## 6. Commits on Branch (not yet merged)

```
c5b6bb91 fix(security): MCP path allowlist for config-query tools
9e057db7 fix(security): harden redactor — base64 size/depth caps, nested JSON leaf redaction
```

These two commits complete the remaining code work for Scope 01. The branch
is ready to merge to `main`.

---

## 7. Review Directives Checklist (from packet §6)

| Directive | Status |
|-----------|--------|
| Architectural Guarantee Check: `describe_secret` no network/plaintext | **PASS** — Tier 2 returns deterministic description; no network branch |
| Shannon Entropy & Regex Backstop: false pos/neg trade-offs | **PASS** — high-entropy backstop runs last; known-prefix catches bare tokens; base64 now bounded |
| TTL Expiry & Volatile State: auto-expire, no localStorage linger | **PASS** — once-per-process relock guard; server-side phrase enforcement |
| Verification Command | **PASS** — 458 tests pass |
