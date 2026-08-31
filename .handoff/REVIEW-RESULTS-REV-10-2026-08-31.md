# Review Results — REV-10: Federated Fleet & Multi-Persona System

**Date:** 2026-08-31
**Reviewer:** GLM-5.3 (adversarial pass with end-to-end verification)
**Packet:** `.handoff/REVIEW-PACKET-10-FEDERATED-FLEET-AND-MULTI-PERSONA.md` (2026-08-29) + the 2026-08-30 simplification addendum
**Scope reviewed (current code on `worktree-central-todo-batches`):** `halbert_core/halbert_core/federation/` (peers_config, peer_discovery, peer_middleware, compute_router, compute_endpoint, compute_broker, tool_allowlist, fleet_proxy, telemetry_agent), `dashboard/routes/peers.py`, `dashboard/routes/fleet.py`, `dashboard/routes/persona.py`, `persona/store.py`, `persona/manager.py`, `model/providers/peer.py`, `model/client.py` (`_call_peer`), `model/config_wizard.py` (`_test_compute_peer`), `mcp/server.py` (auth surface), `dashboard/app.py` (router mounting), `components/llm/ComputePeerCard.tsx`.
**Verification run:** `arch -arm64 ... wt_pytest.py halbert_core/tests/federation/ halbert_core/tests/test_persona_store.py -q` → **158 passed, 15 skipped** (all 6 split-brain tests skipped; no `test_fleet_*.py` exists despite the packet's verification command referencing it).

---

## 1. Verdict per area

| Area | Verdict |
|---|---|
| Peer token handling (hashing, constant-time compare, revocation) | **PASS** — implemented and well tested (`test_token_revocation.py`) |
| Pairing handshake (token issuance) | **FAIL** — self-service token issuance, no user confirmation, no rate limiting (F1) |
| Peer compute endpoint (workstation side) | **FAIL** — router never mounted; broker is `NotImplementedError` stubs (F2) |
| ComputeRouter decision matrix + health probe | **PARTIAL** — logic implemented and unit-tested, but probes a route that does not exist anywhere, so the peer can never be marked online in production (F3); unwired (no production instantiation) |
| Split-brain / deferred-queue policy | **FAIL** — replay unimplemented, queue unbounded, all split-brain tests skipped (F4) |
| Tool allowlist (C4 ingress filter) | **PASS** — frozen set, import-time self-check, endpoint filtering, tested |
| Egress redaction (C4) | **PASS at unit level** (`mcp_response` applied in the endpoint; `test_peer_redaction.py` green) — but the endpoint that applies it is not mounted, so there is no live egress boundary yet |
| mDNS discovery (beacon/listener) | **SCAFFOLD** — raises `NotImplementedError` when zeroconf *is* installed; advertises empty `compute_backends`; no production caller (F11) |
| Fleet Cockpit / fleet proxy / telemetry | **SCAFFOLD** — every method raises `NotImplementedError`; routes 500 instead of 404 (F10) |
| Persona store (atomic symlink swap, reserved IDs) | **PASS** — `os.replace` swap is atomic and leaves no missing-`being.yml` window in-process; reserved IDs match the actual route segments; 20 tests pass. One cross-process race on the fixed temp-link name (F8) |
| Multi-persona isolation | **FAIL** — two parallel persona systems with no reconciliation; per-persona SQLite (`memory_{persona_id}.db`, packet open item 3) exists nowhere (F7) |
| C1 "one token, one validation path" (MCP + peers) | **CLAIM NOT IMPLEMENTED** — MCP transport uses its own static token, `PeersConfig` is never imported by `mcp/` (F6) |

**Overall:** the satellite half of the federated compute story (PeerProvider, `_call_peer`, provider registration, ComputeRouter logic, ComputePeerCard) is real and tested. The workstation half (compute endpoint, broker, health route) and the trust machinery (pairing confirmation, MCP token unification) are not. An HA node that follows the 2026-08-30 flow — link a compute peer, point both slots at it — gets a total inference outage today (F2), and a LAN-bound workstation hands out peer credentials to anyone who asks (F1).

---

## 2. Findings (most severe first)

### F1 — CONFIRMED (High, security): pairing is self-service token issuance; the PIN confirmation step does not exist
`halbert_core/halbert_core/dashboard/routes/peers.py:151-185` (`request_pairing`), `:188-235` (`verify_pairing`)

**Scenario:** the workstation must bind non-localhost for peers to connect at all (`dashboard/__main__.py:122`, `--host`, default `127.0.0.1`; the feature requires `HALBERT_HOST=0.0.0.0`), and the dashboard has no auth middleware beyond CORS. Any LAN host then does: (1) `POST /api/peers/pair {"node_id": "attacker"}` → the 4-digit PIN is returned **in the same response** (line 185); (2) `POST /api/peers/verify {"pin": ..., "node_id": "attacker"}` → a full raw bearer token is returned (line 235). There is no desktop-user confirmation state anywhere — the docstring's "User confirms pairing on the Desktop UI" is a `TODO(federation-9.1)` comment, not code. The PIN is not out-of-band (the requester receives it directly), so it gates nothing. Combined with F5, the attacker can then revoke the legitimate satellite's credential (fleet-wide DoS). Secondary issues in the same flow: `_pending_pairings` (line 76) never expires, has no attempt counter, and is keyed by PIN — 10k entries of unauthenticated write amplification, and a colliding `/pair` request silently overwrites a legitimate pending entry so the real satellite's `verify` fails with "PIN does not match".

**Fix:** make the PIN out-of-band — display it on the workstation UI only, and gate `/verify` on an explicit desktop-side approval action (or have the user type the PIN into the workstation rather than the satellite sending it back). Add PIN expiry (60s), attempt limiting, and an authenticated/local-admin-only requirement on `/pair`.

### F2 — CONFIRMED (High, functional): the workstation never serves the compute contract — the entire peer offload path is a dead end
`halbert_core/halbert_core/dashboard/app.py:298-306` (router mounting — `federation.compute_endpoint.router` is absent; `routes/compute.py` is a different module, the capacity probe), `federation/compute_endpoint.py:265` (`_submit_to_broker` raises `NotImplementedError`), `federation/compute_broker.py:166, 202` (`start`/`submit` stubs), `:220-241` (models route returns an empty list)

**Scenario:** an HA node pairs per the 2026-08-30 flow: `POST /api/peers/compute-peer` points `chat_model` and `specialist_model` at `peer://desktop:8000`. Every LLM call goes through `client._call_peer` → `POST /api/compute/v1/chat/completions` on the workstation → **404** (route not mounted; and even if mounted, `_submit_to_broker` 500s). `PeerProvider.health_check()` (`model/providers/peer.py:367-384`) and the ComputePeerCard's "Test Connection" (`POST /compute/peer-probe`, `routes/compute.py:296`) also hit the unmounted models route → always report the peer down. With no local models on an HA node and no other endpoints, TierRouter has nothing to fall back to: **every conversational turn fails**. The addendum's "the peer provider is registered in the model stack" is true on the satellite side only.

**Fix:** mount `compute_endpoint.router` in `app.py`, implement `_submit_to_broker` → `ComputeBroker.submit()`, and populate `/api/compute/v1/models`. Until then the ComputePeerCard should refuse to save a link or must clearly label the feature as not yet serving.

### F3 — CONFIRMED (Medium-High, functional): three components disagree on the peer health route, and the one ComputeRouter uses does not exist anywhere
`federation/compute_router.py:389` (probes `/api/compute/v1/health`), `model/config_wizard.py:424` (same), `model/providers/peer.py:106, 377` (probes `/api/compute/v1/models`); no `v1/health` route exists in the codebase (grep-verified)

**Scenario:** even once F2 is fixed by mounting the endpoint, `ComputeRouter._http_health_probe` gets a 404 → after 3 consecutive failures the peer is marked offline and `route()` **never returns `source="peer"`** — the decision matrix the addendum calls "implemented" can never select the peer in production. Separately, `config_wizard._test_compute_peer` reports every healthy workstation as unreachable ("HTTP 404"), so the wizard flow misleads the user on every attempt. The unit tests pass only because they monkeypatch the probe (`test_compute_router_route.py:103-138`).

**Fix:** add `GET /api/compute/v1/health` to `compute_endpoint.py` (auth'd, no GPU cost), or align all three probes on the models route. Pick one and encode it as a shared constant.

### F4 — CONFIRMED (Medium): deferred queue is unbounded and can never drain; the split-brain policy (L15/§11.3) is entirely unimplemented
`federation/compute_router.py:194` (plain list), `:298` (append on every template fallback for non-monologue turns), `:431-441` (`replay_deferred` raises `NotImplementedError`); `halbert_core/tests/federation/test_split_brain.py:25-60` (all 6 tests skipped)

**Scenario:** an HA node (`sbc_low_power`/`unknown` profile) with the peer offline appends the full `messages` payload of every `interactive_user`/`high_value_event`/`sleep_consolidation` turn to an in-memory list that nothing ever reads or drains — unbounded growth on a Pi over days of peer downtime, and the turns are silently lost (no replay, no persistence). Nothing detects or resolves the Desktop-wakes-with-conflicting-completions case; the packet's split-brain directive is answered by skipped tests. Mitigating: no production code instantiates `ComputeRouter` yet (grep-verified — only tests do), so this is latent until the router is wired into the agent loop.

**Fix:** cap the queue (bounded ring with drop-oldest + a dropped counter), persist deferrals, and implement `replay_deferred` with the §11.3 conflict policy *before* wiring `ComputeRouter.route()` into the tick.

### F5 — CONFIRMED (Medium, security): any authenticated peer can revoke any other peer
`halbert_core/halbert_core/dashboard/routes/peers.py:264-286`

**Scenario:** `DELETE /api/peers/{node_id}` requires only `require_peer_auth` — any token holder can revoke the credentials of every other node in the fleet (permanent DoS until manual re-pairing on the workstation). The code's own TODO acknowledges the privilege escalation; F1 makes it remotely triggerable by a fresh attacker token. A peer token should never be a fleet-admin credential.

**Fix:** restrict to local-admin (or allow a peer to revoke only itself: `node_id == ctx.node_id`).

### F6 — CONFIRMED (Medium, claim-vs-code): C1 "one token, one validation, one revocation path" is not wired — MCP uses a separate static token
`halbert_core/halbert_core/mcp/server.py:1006, 1017-1026` (`_bearer_token` + `_check_auth`), no `PeersConfig`/`peers_config` import anywhere under `mcp/` (grep-verified); contradicted by `federation/peer_middleware.py:5-23` and `federation/__init__.py` docstrings

**Scenario:** the federation docs claim MCP HTTP/SSE clients and peer nodes share one credential surface with one revocation path. In reality the MCP transport compares against a single process-static `_bearer_token` (no per-node identity, no revocation short of restart/reconfigure), while peer traffic validates against `PeersConfig`. Revoking a compromised satellite's peer token does not affect any MCP session credential, and vice versa. Anyone relying on the documented C1 property (e.g., "revoke once, kills everywhere") is wrong.

**Fix:** either wire `mcp/server.py`'s `_check_auth` through `PeersConfig.verify_token` or correct the C1 documentation to describe two separate surfaces until Phase 4b unifies them.

### F7 — CONFIRMED (Medium): two persona systems, two sources of truth for "active persona", zero reconciliation
`halbert_core/halbert_core/persona/manager.py:133-203` (`PersonaManager`, `persona_state.json`, enum `it_admin`/`friend`, decorative `memory_dir`), `persona/store.py:258` (`PersonaStore`, `being.yml` symlink), `dashboard/routes/persona.py:102` (`POST /api/persona/switch`) vs `:230` (`POST /api/persona/{id}/activate`)

**Scenario:** `POST /api/persona/switch` updates `persona_state.json` only; `POST /api/persona/{id}/activate` swaps `being.yml` only. `GET /api/persona/status` reports the PersonaManager view; `GET /api/persona/list` reports the PersonaStore view. A user who switches via one surface sees no change in the other, and the agent reads `being.yml` — so `/status` can claim a persona that is not the one actually serving prompts. Further: per-persona memory isolation (packet open item 3, `memory_{persona_id}.db`) exists nowhere — `PersonaManager.memory_dir` has no consumers outside its own module, and `persona/memory_purge.py` builds `personas/{name}` paths from its own root. The packet's "SQLite isolation across personas" review directive has nothing to inspect: it was never built.

**Fix:** pick one system (PersonaStore, per the multi-persona milestone) and route `/switch` through it, or delete the old PersonaManager surface. Implement per-persona memory paths before advertising persona isolation.

### F8 — PLAUSIBLE (Low-Medium): fixed-name temp symlink makes the atomic swap racy across processes
`halbert_core/halbert_core/persona/store.py:150-161` (`_set_symlink`)

**Scenario:** the temp link is always `.being.yml.tmp-link`. Two processes sharing a config dir (e.g., dashboard plus a CLI/second Halbert process; the in-process routes are serialized by `_being_config_lock` and event-loop atomicity, so this needs a second process) interleave: A creates the temp link → B unlinks it and creates its own → A's `os.replace` publishes **B's target** — A's activate returns success while `being.yml` points at the wrong persona — or A's replace raises `FileNotFoundError` → 500. The `os.replace` itself is atomic (the packet's zero-window directive holds for the swap proper); the flaw is the shared staging name.

**Fix:** unique staging name per call (`.being.yml.{os.getpid()}.{uuid4()}.tmp`) — one line; `os.replace` already handles the rest.

### F9 — PLAUSIBLE (Low): PeersConfig singleton has no cross-process coherence and rewrites the file per request
`halbert_core/halbert_core/federation/peers_config.py:182-189` (`_save`), `:206-223` (`verify_token`), `:275-287` (`update_last_seen`)

**Scenario:** each process caches `peers.json` at startup and `_save()` rewrites it wholesale. Two processes sharing a config dir (multi-instance deployment) lose updates: process A pairs a peer; process B (loaded earlier) later saves on any `update_last_seen` and silently **deletes A's new credential** — the satellite's token stops working with no audit trail. Within one process, `update_last_seen` persists the entire file on *every* authenticated request (acknowledged TODO) — lock contention and write amplification under satellite load. Related latent issue: `verify_token` iterates `self._peers.values()` lock-free while `add_peer` mutates the same dict in place (the docstring claims the dict is "only replaced atomically" — it is not); safe today only because every caller is an async handler on one event loop. Also `self._path.with_suffix(".tmp")` turns `peers.json` into `peers.tmp`, a more collision-prone name than intended.

**Fix:** re-read/mtime-check before save (or file-lock), throttle `last_seen` writes, and snapshot-iterate (`list(self._peers.values())`) in `verify_token`.

### F10 — CONFIRMED (Low): fleet routes 500 with `NotImplementedError` where they promise 404; the entire Fleet Cockpit is stubs
`halbert_core/halbert_core/dashboard/routes/fleet.py:138-142, 145-154, 157-176, 179-186, 189-199`; `federation/fleet_proxy.py:150-164`; `federation/telemetry_agent.py:220-228`

**Scenario:** `GET /api/fleet/{id}/info` and `POST /api/fleet/{id}/inspect` call `get_fleet_proxy(node_id)` before the 404 check — but `get_fleet_proxy` itself raises `NotImplementedError`, so every call 500s with an unhandled exception regardless of peer state. The packet's "remote instance telemetry aggregation and multi-node task delegation protocol" milestones are not present in current code: telemetry `_publish`, every `FleetProxy` method, and every fleet route body are `TODO(federation-9.x)` stubs.

**Fix:** have `get_fleet_proxy` return `None` until implemented (the routes already handle that), or mount the fleet router only when Phase 9.9 lands.

### F11 — CONFIRMED (Low): mDNS beacon/listener crash when zeroconf IS installed; advertisement data is empty
`halbert_core/halbert_core/federation/peer_discovery.py:191, 250` (`raise NotImplementedError` after the lazy import succeeds), `:285-291` (`get_node_identity` returns `compute_backends: []` with a TODO)

**Scenario:** the graceful-degradation path (H10) handles the *missing* zeroconf case, but the *present* case — an operator who installs `halbert-core[federation]` and calls `PeerBeacon.start()` — gets an unhandled `NotImplementedError`. And even once implemented, `get_node_identity` advertises an empty `compute_backends` list, so satellites would see a compute host with no backends. No production caller exists yet (grep-verified), so this is latent. The M13 property itself (Apple Intelligence never a peer backend) is correctly encoded in the TXT builder, docstrings, and tests — resolved.

**Fix:** log-and-return (like the ImportError path) until 9.7 is implemented, and populate `compute_backends` from the running Ollama/vLLM probes.

### Minor notes (no scenario needed)
- `parse_txt_record` (`peer_discovery.py:137`) raises `ValueError` on a malformed `api_port` TXT value — will kill a future listener callback; wrap in try/except with default.
- `GET /api/peers/discovered` (`routes/peers.py:366-380`) is a hardcoded `[]` — the UI's discovery list will always be empty (consistent with 9.7 being unimplemented, but worth a UI label).
- `PersonaManager._save_state` (`manager.py:115-131`) writes JSON non-atomically (no temp+rename) — inconsistent with the store's atomic discipline.
- Peer compute streaming deliberately raises `NotImplementedError` (`client.py:503-510`, `compute_endpoint.py` docstring) — correct fail-loud behavior, documented.
- `PeerProvider` trusts the peer to redact (`peer.py:157-161`) and the satellite is the destination — acceptable per the trust model, but note the Desktop-side second pass promised for fleet inspection does not exist yet (fleet_proxy stub).

---

## 3. Packet claims — resolved vs. still open

**Resolved since the packet (verified in current code):**
1. Phantom `PeerAuthMiddleware` export — replaced by the real auth surface: `require_peer_auth`/`optional_peer_auth`/`PeerContext` in `peer_middleware.py`; `federation/__init__.py` exports are accurate and `test_package_exports.py` passes.
2. Peer provider registered in the model stack — `ProviderType.PEER` in `tier_router.py:59, 378-390`, `CHAT_CAPABLE_PROVIDERS` in `client.py:76`, `_call_peer` transport (`client.py:485-540`), provider package export; registration tests green.
3. ComputePeerCard settings surface exists (`components/llm/ComputePeerCard.tsx`), gated to home variants, with `POST /compute/peer-probe` reusing `PeerProvider.health_check` — though the probe itself always fails today (F2/F3).
4. Token hygiene — SHA-256 hashed storage (raw never persisted), `hmac.compare_digest`, per-peer tokens, surgical revocation, re-pair flow — implemented and tested.
5. mDNS `compute_backends` advertises `ollama`/`vllm` only; Apple Intelligence never a peer backend (M13) — correctly encoded at the data-model level (runtime advertisement is still a stub, F11).
6. Tool allowlist (C4 ingress) — frozen allowlist + denylist self-check + endpoint tool filtering, tested.
7. Persona store scrutiny items — atomic `os.replace` swap, reserved IDs matching the actual route segments (`status`/`list`/`switch`/`memory` vs `/api/persona/*`), `_write_persona_file` temp+rename+0600; `test_persona_store.py` fully green.
8. `secure_model` never peer-offloaded (M11) — enforced at two layers (`llm_config._is_local_url` + `can_serve_slot`), `test_secure_model_no_offload.py` green.

**Still open from the packet (unresolved):**
1. Peer heartbeat reaper (90s OFFLINE) — does not exist; the only health machinery is ComputeRouter's probe cache (and it is broken, F3).
2. mTLS peer transport — not present (bearer tokens only; acceptable for LAN per the design, but the pairing weakness in F1 is the actual exposure).
3. Multi-persona database defensive naming (`memory_{persona_id}.db`) — no per-persona SQLite anywhere (F7).
4. Peer Heartbeat/mDNS beacon+listener implementation (9.7), fleet proxy/cockpit (9.9), compute broker/endpoint (9.3), replay (9.6), streaming redaction (9.4) — all still `NotImplementedError` stubs.

---

## 4. Bottom line

The security-sensitive pieces that exist (token hashing/revocation, tool allowlist, redaction boundary, secure-model pinning, persona symlink swap) are built to a good standard and well tested. The system's real defects are at the seams the tests don't cross: the pairing handshake issues credentials with no human in the loop (F1), the workstation never mounts the endpoint the whole design routes to (F2), and three components disagree about which health route exists (F3). Until F1-F3 are fixed, the federated fleet is simultaneously insecure to expose on a LAN (F1) and nonfunctional end to end (F2/F3) — which at least means the insecure surface currently leads only to 404s, but the moment F2 is fixed, F1 becomes the live risk. Fix F1 before or together with F2.