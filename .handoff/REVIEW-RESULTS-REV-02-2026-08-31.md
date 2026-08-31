# REV-02 Review Results — MCP Server & Client Boundary

**Date:** 2026-08-31
**Reviewer pass:** GLM-5.3 adversarial review with verification
**Packet:** `.handoff/REVIEW-PACKET-02-MCP-SERVER-AND-BOUNDARY.md`
**Code reviewed:** worktree `central-todo-batches` @ `fbfb5614` (includes U1 batch `5a132654` and the `feat/security-review-01` merge `297ceb67`)
**Method:** full read of the current MCP surface, adversarial trace of each suspected defect end-to-end, dynamic probes for the two HTTP transport defects, test suite run. No production code modified.

---

## 1. Scope reality check (packet vs. current code)

The packet (2026-08-29) describes `mcp/tools.py`, `mcp/transport.py`, `mcp/auth.py`, and `dashboard/routes/mcp.py`. **None of these exist.** The current surface is:

- `halbert_core/halbert_core/mcp/server.py` — JSON-RPC dispatcher, 18 tools (not 12), stdio + HTTP/SSE transports, bearer auth, rate limiter, SSE tracker (1353 lines)
- `halbert_core/halbert_core/mcp/response.py` — `mcp_response()` egress choke point
- `halbert_core/halbert_core/mcp/camera_gate.py` — camera/vision gate (dead code, see §5)
- `halbert_core/halbert_core/federation/peer_middleware.py` + `peers_config.py` — the FastAPI-side bearer surface (`require_peer_auth`, hashed per-peer tokens)
- `halbert_core/halbert_core/federation/compute_endpoint.py`, `fleet_proxy.py` — peer compute/proxy surfaces (stubs)
- No MCP client module exists in `integrations/` (packet's client-side scope has no code to review)

The review was done against this current layout, as directed.

---

## 2. Verdicts per area

| Area | Verdict |
|---|---|
| JSON-RPC 2.0 protocol handling | **PASS with minor notes.** Batch arrays rejected with -32600 instead of crashing; notification semantics correct (no `id` → no response, not even an error, including the internal-error path; explicit `"id": null` treated as an id); error codes -32700/-32600/-32601/-32602/-32603 all present and correctly applied. Minor: invalid notifications get HTTP 202 (acceptable); `initialize` before `tools/call` is not enforced. |
| Egress boundary (`mcp_response()`) | **PASS.** The dispatch-level choke point (`server.py:930`) wraps every `tools/call` result; the catch-all `-32603` error path now runs through `redact_text()` (commit `5a132654` — verified, this was the packet-era leak); `get_being_config` strips `ha_token`/`ha_url`/`security` as suspenders; Tier 2 routing goes through `describe_secret()`/`describe_with_correlations()`, which have no code path that emits the value (verified by reading `secure_response.py:95-176`); 18 boundary tests + 2 dispatch-level guarantee tests cover the seams. |
| Tier routing (`get_config_value`) | **PASS.** Tier 2 under `local_only` returns description-only (test-verified); TTL expiry fails safe to `local_only` (`queries.py:263-271`); `cloud_ok_acknowledged` raw values are still caught by the structural redaction at dispatch (test-verified). Documented residual gap: short context-free secrets under neutral key names remain unclassified — known and documented in `response.py`. |
| Bearer auth (HTTP transport) | **PASS with defects.** Constant-time compare, always executed (no format-based timing branch); 32-char minimum enforced, fail-closed; token never echoed to stderr/logs. Defects F2, F3, F5 below. |
| Peer auth (FastAPI side) | **PASS with defects.** SHA-256-hashed per-peer tokens, constant-time verify, surgical revocation, raw token never persisted or logged. Defects P1, P2 below. |
| CORS | **PASS.** Default-deny (no headers at all when unconfigured — browser blocks every cross-origin read); explicit-origin echo with `Vary: Origin`; `*` warned against; preflight carries no data. |
| SSE transport | **PASS with defect.** Connection cap (10), rate limit, heartbeat, threaded server so one stream cannot stall others. Defect F4 (slot leak) below. |
| Autonomy / destructive-tool gating | **FAIL — top finding F1.** The AutonomyGate properly enforces `ha_call_service`, but `set_autonomy_level` and `approve_proposal` are gated only by a client-supplied boolean. |
| Fleet proxy / compute endpoint | **NOT TESTABLE — stubs.** Every method raises `NotImplementedError`. Design contradiction F6 noted. |

---

## 3. Findings (most severe first)

### F1 — CONFIRMED (high): self-supplied `confirm` gates allow a one-call autonomy escalation to `orchestrate`

**Files:** `halbert_core/halbert_core/mcp/server.py:532-564` (`set_autonomy_level`), `:308-376` (`approve_proposal`), `:459-515` (`ha_call_service`)

**Trace.** `ha_call_service` is correctly gated server-side: it loads the current `BeingConfig` and consults `AutonomyGate.evaluate()`, so at `observe` every action is blocked. But `set_autonomy_level` has **no** gate: its only server-side checks are `cfg.validate()` (the level string must be in `VALID_AUTONOMY_LEVELS`, verified at `being_config.py:311`) and `params.get("confirm")` — a boolean **supplied by the same client making the request**. The Tier 2 unlock phrase enforced in `dashboard/routes/settings.py:3069-3086` is not applied anywhere in the MCP path (grep-verified: no phrase reference under `mcp/` or `findings/`).

**Failure scenario.** Any bearer-token holder over HTTP — which per the C1 design (`peer_middleware.py:11-22`) includes every paired satellite, so one compromised Raspberry Pi is enough — sends:
1. `tools/call set_autonomy_level {"level": "orchestrate", "confirm": true}` → persisted, no human involved.
2. `tools/call ha_call_service {"domain": "lock", "service": "unlock", "entity_id": "lock.front_door"}` → `AutonomyGate` now auto-executes.

The house's physical-action control is defeated in two requests. `approve_proposal` has the same shape: it applies real config changes to the host filesystem gated only by the client's own `confirm=true`, with no autonomy check anywhere in `ProposalGenerator`/`ProposalStore` (grep-verified). The docstrings claim the gate "prevents an LLM from applying changes without user awareness" — server-side, nothing enforces that; the only enforcement point is the MCP client UI, which the server cannot assume (and a paired satellite has no UI at all).

**Suggested fix.** Server-side, not client-side: require a human-in-the-loop token for the two escalation tools — either the same confirmation phrase used for the Tier 2 unlock, or an out-of-band approval (dashboard notification + approval record) that `set_autonomy_level`/`approve_proposal` must reference. At minimum: forbid *raising* autonomy above the current level via MCP (allow only decrease), and route `approve_proposal` through the existing `ApprovalEngine` approval-request flow rather than the self-supplied boolean.

---

### F2 — CONFIRMED (medium): unvalidated `Content-Length` — negative value hangs a handler thread indefinitely

**File:** `halbert_core/halbert_core/mcp/server.py:1080-1085`

**Trace.** `content_length = int(self.headers.get("Content-Length", 0))`. A header of `Content-Length: -1` parses to `-1`, passes the `> _MAX_REQUEST_SIZE` check, and reaches `self.rfile.read(-1)` — which for a buffered reader means *read until EOF* (dynamically verified). The read blocks until the client closes the connection. The rate limiter is never consulted because the request never completes. Production uses `ThreadingHTTPServer` with unbounded thread spawn, so each open socket with a negative Content-Length permanently pins one thread — no body ever needs to be sent. A secondary robustness bug in the same line: a non-numeric Content-Length raises `ValueError`, unhandled → per-request traceback to stderr.

**Failure scenario.** Over HTTP (or LAN if bound beyond loopback), `for i in {1..500}: open socket → "POST / HTTP/1.1\r\nContent-Length: -1\r\n\r\n" → keep socket open` pins 500 threads and 500 FDs with ~1 KB each; the 60/min rate limit never fires. Server becomes unusable for real clients while the sockets stay open.

**Suggested fix.** Validate before reading: `if not (0 <= content_length <= _MAX_REQUEST_SIZE): return 413/400` (reject negatives and non-numeric explicitly — parse inside try/except). Also consider a socket timeout (`handler.timeout`) so a silent client cannot hold a thread forever even with a valid small Content-Length.

---

### F3 — CONFIRMED (medium): auth check precedes rate limiting — the unauthenticated surface is unthrottled

**File:** `halbert_core/halbert_core/mcp/server.py:1070-1078` (`do_POST`), `:1101-1109` (`do_GET`)

**Trace.** `do_POST` runs `_check_auth()` first and returns 401 without ever calling `_check_rate_limit()`; same ordering in `do_GET`. So every unauthenticated request — including token guess attempts — bypasses the rate limiter entirely. The enforced 32-character minimum makes brute force of the token itself infeasible, but the limiter's stated purpose ("max 60 requests per minute per client IP", `server.py:1014-1015`) simply does not apply to the unauthenticated path: connection-flood and request-flood abuse of the 401 path is unthrottled.

**Failure scenario.** An unauthenticated client on the network sends unlimited POSTs; each performs a `hmac.compare_digest` and a JSON-less 401 write. No bucket fills; the process sees full request rate. Combined with F2 this is a clean DoS lane that never touches any defense.

**Suggested fix.** Swap the order (rate limit, then auth), or make the 401 path consume a cheaper, smaller bucket (e.g. one-tenth the normal allowance) so unauthenticated floods are still bounded.

---

### F4 — CONFIRMED (medium-low): SSE connection slot leaks if the client resets during header write

**File:** `halbert_core/halbert_core/mcp/server.py:1117-1147`

**Trace.** `do_GET` acquires an SSE slot at line 1118, then writes the response status and headers (1122-1127) and the initial `endpoint` SSE event (1130-1134) — **all outside the `try:`** that begins at line 1138. `BaseHTTPRequestHandler` flushes the header buffer at `end_headers`, so a client that has already RST the connection makes `wfile.write` raise `BrokenPipeError` before the try block is entered → the `finally: release()` never runs → the slot is lost until process restart. The cap is 10, so ten successful races permanently 503 the SSE endpoint.

**Failure scenario.** An authenticated client (or any client in open mode) opens `GET /sse` and immediately RSTs, repeatedly. After 10 successful races, all SSE slots are leaked and every legitimate SSE client receives 503 until the server restarts. The heartbeat loop's own `finally` covers only the post-header phase.

**Suggested fix.** Move the `acquire()` inside the guarded region — wrap everything from `send_response` through the heartbeat loop in the `try/finally` that releases the slot, or release in an `except` for the header-write block.

---

### F5 — CONFIRMED (low): non-ASCII bearer token crashes the request thread

**File:** `halbert_core/halbert_core/mcp/server.py:1025-1026`

**Trace.** `hmac.compare_digest(token, self._bearer_token)` is called on `str`. `compare_digest` raises `TypeError: comparing strings with non-ASCII characters is not supported` for non-ASCII input (dynamically verified). `BaseHTTPRequestHandler` decodes headers as latin-1, so a raw non-ASCII byte sequence after `Bearer ` survives into `token` as a non-ASCII `str`. The exception is unhandled in `do_POST`/`do_GET` → connection aborted with a traceback to stderr, per request, with no rate-limit consumption (the request never completes). An attacker can spam stderr/log volume and crash-loop request threads at zero cost.

**Failure scenario.** `Authorization: Bearer <0xC3 0xB6>x` repeated — each request produces an unhandled-exception traceback and a dropped connection; no rate-limit bucket is touched.

**Suggested fix.** Compare bytes: `hmac.compare_digest(token.encode("utf-8"), self._bearer_token.encode("utf-8"))` — `compare_digest` on bytes is safe for arbitrary input and remains constant-time. (The `verify_bearer_token` helper in `camera_gate.py:437` correctly uses bytes — but is itself dead code, see §5.)

---

### F6 — CONFIRMED (medium, latent): FleetProxy spec requires the raw peer token, but PeersConfig stores only hashes

**Files:** `halbert_core/halbert_core/federation/fleet_proxy.py:150-164`, `halbert_core/halbert_core/federation/peers_config.py:112-129`

**Trace.** `get_fleet_proxy()` documents: "Looks up the peer's endpoint and token from PeersConfig" — but `PeersConfig` deliberately persists only `sha256:<hex>` token hashes (M14: "the raw token is never persisted to disk"). The Desktop therefore **cannot** obtain a credential to authenticate to the satellite as spec'd; the C5 "Desktop as MCP client of satellite" data flow is unimplementable with the current credential model. Everything in `fleet_proxy.py` is currently `NotImplementedError` stubs, so this is latent — but whoever implements federation-9.9 will hit a wall or, worse, will "fix" it by storing raw outbound tokens in `peers.json`, silently downgrading M14.

**Suggested fix.** Decide the credential model now, before implementation: peer pairing is bidirectional (each side holds a raw token for the *other*); store the Desktop's outbound satellite credentials in a separate store (or a `token_hash` for inbound plus a keychain/OS-keyring reference for outbound) — never as plaintext in `peers.json`.

---

### P1 — PLAUSIBLE (low): `verify_token` iterates the peer dict without the lock

**File:** `halbert_core/halbert_core/federation/peers_config.py:206-223`

`verify_token` scans `self._peers.values()` lock-free "because the dict is only replaced atomically" (module docstring) — but `add_peer` (`:255`) mutates the **same dict in place** rather than replacing it. A `tools/call`-bearing peer request arriving concurrently with a pairing operation can raise `RuntimeError: dictionary changed size during iteration` → 500 on an otherwise valid request. Rare (pairing is infrequent), but real. Fix: iterate over `list(self._peers.values())`, or actually implement the copy-on-write replacement the docstring promises.

### P2 — PLAUSIBLE (low): blocking disk write on every authenticated peer request, inside the async event loop

**Files:** `halbert_core/halbert_core/federation/peer_middleware.py:161`, `peers_config.py:275-287`

`require_peer_auth` (an async FastAPI dependency) calls `update_last_seen`, which takes a threading lock, mutates the record, and performs a synchronous atomic file write — on **every** authenticated request. Under concurrent peer traffic this serializes all peer requests on a lock + disk I/O and blocks the event loop. The code itself flags it (TODO federation-9.1: "throttle — don't save on every request"). This is live code on the hot path today, not just a TODO-idea. Fix: throttle (write at most once per N seconds, e.g. via a monotonic timestamp check) and/or move the write to a worker.

### P3 — PLAUSIBLE (low): notifications execute side-effectful tools with no acknowledgment

**File:** `halbert_core/halbert_core/mcp/server.py:912-935`

A `tools/call` without `id` runs the handler fully — including `approve_proposal` and `set_autonomy_level` — then discards the result and returns None (HTTP 202). JSON-RPC permits processing notifications, but for tools with host-side effects this means an execution path with no response and no client-visible outcome. Combined with F1 this is a second no-ack lane for the same escalation. Consider rejecting `tools/call` notifications outright (`-32600`), which MCP clients would tolerate and which removes the lane.

### P4 — PLAUSIBLE (low): stdio has no line-size limit

**File:** `halbert_core/halbert_core/mcp/server.py:964-981`

`for line in sys.stdin` followed by `json.loads(line)` — a local client can send a multi-gigabyte single line and exhaust memory before any parse. Local same-user trust boundary, so this is a robustness note, not a security boundary. A `maxlen` guard would be cheap.

### P5 — Interop nit: `Authorization` scheme match is case-sensitive

**File:** `halbert_core/halbert_core/mcp/server.py:1025`

`auth.startswith("Bearer ")` rejects `bearer x`. RFC 7235 auth-schemes are case-insensitive; a spec-correct client gets a spurious 401. Fails closed, so security-neutral.

---

## 4. Packet claims now resolved (one line each)

- **Packet §3/§4 file inventory** (`mcp/tools.py`, `mcp/transport.py`, `mcp/auth.py`, `dashboard/routes/mcp.py`): obsolete — surface consolidated into `mcp/server.py` (18 tools) + `federation/peer_middleware.py`; reviewed the current layout.
- **Packet §1.3 / "12 core tools"**: now 18 tools; gating params (`confirm`) added to `run_scanner`, `approve_proposal`, `set_autonomy_level`.
- **Packet §1.4 Tier 2 interception**: implemented and stronger than described — tier routing in `config/queries.py` plus a dispatch-level `mcp_response()` choke point that covers every tool (commit `5a132654`), not per-handler convention.
- **Packet §6 "Specification adherence" error codes**: all five codes present and correctly used; batch-array crash fixed (now -32600), notification handling spec-correct, `id` echoed verbatim including `null`.
- **Packet §6 "Security Boundary Gate" (`get_config_value` Tier 2)**: confirmed — requesting a Tier 2 key under `local_only` returns `describe_secret` metadata with the value absent from every field; even `cloud_ok_acknowledged` raw values are re-redacted at dispatch (test-verified).
- **Packet §6 "Autonomy Validation"**: **partially resolved** — `ha_call_service` is properly AutonomyGate-enforced, but `approve_proposal` and `set_autonomy_level` are not (finding F1).
- **Packet §5.1 SSE resiliency**: partially addressed server-side (10-connection cap, rate limit, heartbeat, threaded serving) — but the slot leak (F4) and the unbounded heartbeat loop remain; no client-reconnect-loop test exists.
- **Packet §5.2 client config snippets** (`documentation/guides/mcp-setup.md`): **not done** — the file does not exist.
- **Packet §5.3 concurrency pressure testing**: **not done** — no concurrent tool-execution tests; see P1/P2.
- **`feat/security-review-01` follow-ups in scope**: default-deny CORS, bearer hygiene, 32-char minimum, rate limiter monotonic clock + bounded client map, and the `5a132654` redacted catch-all all verified present and correct.

---

## 5. Other observations (no action forced)

- **`mcp/camera_gate.py` is dead code.** Its frigate/vision tool handlers (`:243-421`) are registered in no `TOOL_HANDLERS` and `gate_response()` (`:423`) has zero call sites — the module docstring's claim that it is "a defense-in-depth layer on top of `mcp_response()`" is false as wired. There is no exposure today (the tools simply don't exist on the MCP surface), but either wire the gate into dispatch or delete the module so the stated guarantee matches reality. Its `verify_bearer_token` also duplicates `_check_auth` (and is the byte-safe variant — see F5).
- The egress choke point's residual gaps are honestly documented in `response.py` (short context-free secrets under neutral key names). No new gap found: every tool result path — handler returns, per-tool `{"error": ...}` returns, and the dispatch catch-all — now passes through redaction.
- Test suite: `test_mcp_server.py` + `test_mcp_http.py` → **48 passed** (via the worktree `wt_pytest.py` wrapper). Boundary tests (`test_mcp_response_boundary.py`, 18 cases) present and passing as part of prior runs.

## 6. Untestable here

- Live multi-instance HTTP/SSE operation and the pairing handshake (no second instance or network peers available in this environment).
- Behavior against real MCP clients (Claude Desktop / Cursor): `initialize`-ordering enforcement, SSE reconnection loops (packet open item 1's client side).
- SQLite lock behavior under concurrent MCP tool executions (packet open item 3) — no concurrent-execution harness exists to run.
- `compute_endpoint.py` and `fleet_proxy.py` runtime behavior — every code path raises `NotImplementedError`.
- The dashboard `peers.py` route end-to-end (requires a running FastAPI app with a paired peer).