# Implementation Plan: Singular Entity, Multi-Body — Task Breakdown with Model Assignments

**Date:** 2026-08-31
**Parent handoff:** `HANDOFF-SINGULAR-ENTITY-MULTI-BODY-2026-08-31.md`
**Worktree:** `feat/singular-entity` at `~/.config/superpowers/worktrees/Halbert/singular-entity`
**Status:** COMPLETE — all Fable/Opus/GLM tasks implemented and green
(2026-08-31 wrap-up).

## Completion record

Full-suite verification at the final HEAD: backend 71 failures,
byte-for-byte the known pre-existing environmental set on base
`ffe74bdd` (zero regressions, +416 passing tests vs base); frontend 469
passed, tsc+vite build clean; haloysius memory_v2 93 passed.

| Task | Where | Notes |
|---|---|---|
| P2a/F1 PeerMemoryBackend | Haloysius repo `fd5e962` | Drop-in PersonaMemoryStore proxy; duplicate detection runs on the canonical host; no client-side embeddings. |
| P2b/G1 memory API routes | `8f1243eb` | + remediation `27fcfb95`. |
| P2c/G2 memory wiring | `e30f9f4b` | `_create_memory_store` picks PeerMemoryBackend when canonical_memory_url + peer_token set; local fallback. |
| P2d/G3 peer memory tests | `e30f9f4b` | Cross-repo loop vs real routes + real store; caught the get-route envelope bug pre-ship. |
| P3a/O1 PeerConversationStore | `330f641b` | Single dispatch endpoint wire contract; RedactionFailed propagates; allowlist parity tests. |
| P3b/G4 conversation routes | `3bbcc4d4` | Answers the P3a contract. |
| P3c/G5 ThreadManager injection | `5f9737a3` | Falls back to local when peer_token missing. |
| P3d/O2 shared-thread tests | `330f641b` | Cross-node visibility, 5-body concurrency, two-process WAL, bounded begin_turn race. |
| P4a/G6 connectivity probe | `908169b4` | Pre-session. |
| P4b/O3 compute chain reorder | `e04ad14e` + `27fcfb95` | Cloud primary for ALL turn types; no-AI terminal tier. |
| P4c/G7 degraded marker | `28df5910` | "[no thinking power]" marker. |
| P4d/G8 direction fields | `99cc5df5` | Pre-session. |
| P4e/G9 fallback tests | `9fca4f22` + `27fcfb95` | test_connectivity, test_compute_fallback, test_wake_on_lan. |
| P5a/F2 PeerToolProxy | pre-session | With P5d/F4 security tests at `ffe74bdd`; executor routing fixed by `27fcfb95` remediation. |
| P5b/F3 state-machine routing | `ffe74bdd` + `27fcfb95` | TestExecutorPeerFallback suite green. |
| P5c/O4 capability tracking | `e04ad14e` | KNOWN_PEER_CAPABILITIES, lookups, set_capabilities. |
| P5d/F4 tool-proxy security tests | `ffe74bdd` | 24 tests. |
| P6a/G10 WoL sender | `20c27231` | Pre-session. |
| P6b/O5 router WoL tier | `e04ad14e` | WAKE_ELIGIBLE_TURN_TYPES gating. |
| P6c/G11 WoL fields | `c7e047b8` | Pre-session. |
| P6d/G11 WoL tests | `27fcfb95` | test_wake_on_lan, test_wol_config. |
| P7a/O6 devices API | `922122b2` | Routes + entity mode + capability discovery. |
| P7b-d/G12 Devices page + pairing | `de74e18a`, `5ab70760` | All five binding review decisions; 18 component tests. |
| F5 variant-as-hint | `330f641b` + review `09ec6eb7` | Reviewed: probes are presence checks now (3 defects fixed); test fallout repaired in `4f8c171b`; see HANDOFF-F5-REVIEW-2026-08-31.md. |

Open items (future work, none blocking): server-side atomic get-or-open
for the cross-node begin_turn race (P3d note); CAP_LOCAL_LLM has no
consumer yet (natural home: ComputeRouter's local tier); no capability
re-probe path in a running process; frontend capabilities endpoint;
ManualPairingForm's pre-existing TODO(federation-9.1) gap (out of G12
scope by review decision); `test_cognition_tick_once` is order-sensitive
(fails solo, passes in the full suite — pre-existing on base).

---

## Model tiers

| Tier | Model | Context | When to use |
|---|---|---|---|
| **Fable** | Kimi-k3 [1M] | 1M | Architecturally novel, security-sensitive, needs to reason across many files, first-of-kind patterns |
| **Opus** | GLM-5.3 [1M] | 1M | Strong multi-file capability, well-defined interfaces, established patterns to follow |
| **GLM** | GLM-5.2 [200k] | 200k | Well-scoped, single-file or few-file changes, clear inputs/outputs, mechanical work |

---

## Completed

### P1 — Config foundation ✓ DONE

**Commit:** `cb565199` on `feat/singular-entity`

- Added `body_name`, `canonical_memory_url`, `canonical_thread_url` to `BeingConfig` with validation
- Added `_get_body_name()`, `_get_canonical_memory_url()`, `_get_canonical_thread_url()`, `is_singular_entity_mode()` to `cognition_wiring.py`
- 10 new tests, 24/24 passing

---

## P2 — PeerMemoryBackend (the keystone)

Makes singular mode real. The workstation reads/writes memory on the HA server over the peer link. Both cognitions share one autobiography.

### P2a — Haloysius `PeerMemoryBackend` class [Fable]

**What:** A `PersonaMemoryStore` backend that proxies `smart_add` / `search` / `get` to the HA server's memory API over the peer HTTP link.

**Why Fable:** This is architecturally novel — it's a new backend pattern for the Haloysius engine. It needs to understand the `PersonaMemoryStore` interface deeply (smart_add semantics, PersonaMemory serialization via `to_dict()`/`from_dict()`, the return tuple `(MemoryOperation, reason, memory_id)`). It also needs to handle the subtractive contract (lazy imports, no new hard dependencies — use `requests` which is already a hard dep).

**Files:**
- New: `haloysius/src/haloysius/memory_v2/peer_backend.py`
- Reference: `haloysius/src/haloysius/memory_v2/store.py` (the interface to proxy)
- Reference: `haloysius/src/haloysius/memory_v2/types.py` (PersonaMemory dataclass)

**Key design decisions:**
- The backend wraps a remote URL + bearer token. It does NOT instantiate a local `PersonaMemoryStore`.
- `smart_add(memory)` → POST `/api/memory/add` with the memory serialized via `to_dict()`. Returns the `(operation, reason, memory_id)` tuple from the response.
- `search(query, k, ...)` → GET `/api/memory/search?q=...&k=...`. Returns `List[PersonaMemory]` reconstructed via `from_dict()`.
- `get(memory_id)` → GET `/api/memory/get/{id}`.
- `delete(memory_id)` → DELETE `/api/memory/{id}`.
- Connection errors raise `PeerMemoryUnavailable` (new exception). Callers catch this and degrade gracefully.
- No embedding computation on the client side — the HA server computes embeddings on write and search.
- No `mcp_response()` redaction — this is internal entity communication.

**Acceptance:** The backend passes a mock-server test: write a memory, search for it, get it by ID, delete it. Connection failure raises `PeerMemoryUnavailable`.

### P2b — Halbert memory API endpoint [GLM]

**What:** FastAPI routes on the HA server that expose the local `PersonaMemoryStore` over HTTP.

**Why GLM:** Straightforward FastAPI routes with a well-defined interface. The heavy lifting (smart_add, search, embedding) is in the store — the endpoint just proxies to it.

**Files:**
- New or extend: `halbert_core/halbert_core/dashboard/routes/memory.py`
- Reference: `halbert_core/halbert_core/dashboard/routes/persona.py` (existing persona/memory routes pattern)
- Reference: `halbert_core/halbert_core/federation/peer_middleware.py` (bearer auth pattern)

**Endpoints:**
- `POST /api/memory/add` — accepts a PersonaMemory dict, reconstructs via `PersonaMemory.from_dict()`, calls `store.smart_add()`. Returns `{operation, reason, memory_id}`.
- `GET /api/memory/search?q=...&k=...&memory_type=...` — calls `store.search()`. Returns list of memory dicts.
- `GET /api/memory/get/{id}` — returns a single memory dict or 404.
- `DELETE /api/memory/{id}` — soft delete.
- All protected by peer bearer auth. No `mcp_response()` redaction.

**Acceptance:** curl tests against a running HA server show add/search/get/delete working with bearer auth, 401 without.

### P2c — `cognition_wiring` integration [GLM]

**What:** When `canonical_memory_url` is set, `_create_memory_adapter()` creates a `HaloysiusMemoryAdapter` backed by `PeerMemoryBackend` instead of a local `PersonaMemoryStore`.

**Why GLM:** Small, well-defined change. The adapter already accepts any store — just needs to pick the right one.

**Files:**
- Modified: `halbert_core/halbert_core/integrations/cognition_wiring.py` — `_create_memory_adapter()`

**Acceptance:** With `canonical_memory_url` set, the cognition tick writes memories to the remote store. Without it, current behavior (local store).

### P2d — Tests [GLM]

**What:** Mocked HTTP tests for the backend, endpoint tests, integration test.

**Files:**
- New: `halbert_core/tests/test_peer_memory_backend.py`
- New: `halbert_core/tests/test_memory_routes.py`

**Acceptance:** All tests pass. Workstation writes a memory via `PeerMemoryBackend` → HA server's local store has it → HA server's cognition retrieves it (mocked HTTP).

---

## P3 — Thread continuity (shared message history)

Cross-device conversation continuity. Each node runs its own `ThreadManager` against the same shared SQLite database on the HA server.

### P3a — `PeerConversationStore` [Opus]

**What:** A thin data-access proxy implementing the same interface as `SqliteConversationStore`, proxying CRUD operations to the HA server over HTTP.

**Why Opus:** The `SqliteConversationStore` interface is large (many methods: `append_message`, `get_thread`, `current_open_thread`, `update_thread`, `list_open_loops`, `search`, `get_history`, `redact_message`, etc.). The proxy is mechanical but needs to faithfully replicate the interface. It also needs to handle the `RedactionFailed` exception that `redact_message` raises (this must propagate, not be swallowed).

**Files:**
- New: `halbert_core/halbert_core/agents/peer_conversation_store.py`
- Reference: `halbert_core/halbert_core/agents/conversation_sqlite.py` (the interface to proxy)

**Key design decisions:**
- Implements the same public interface as `SqliteConversationStore`
- Each method maps to an HTTP call with bearer auth
- `redact_message` must propagate `RedactionFailed` on failure (deliberate exception in the interface)
- Connection errors raise `PeerConversationUnavailable`
- No `mcp_response()` redaction — internal entity communication

**Acceptance:** The proxy passes a mock-server test for all public methods. `ThreadManager` can use it as a drop-in replacement for `SqliteConversationStore`.

### P3b — Conversation API endpoint [GLM]

**What:** FastAPI routes on the HA server that expose the local `SqliteConversationStore` over HTTP.

**Files:**
- New or extend: `halbert_core/halbert_core/dashboard/routes/conversations.py`
- Reference: `halbert_core/halbert_core/agents/conversation_sqlite.py` (methods to expose)

**Endpoints:** Implemented per the **P3a wire contract** (P3a has landed — see
`halbert_core/halbert_core/agents/peer_conversation_store.py` module docstring
for the authoritative version):

- `POST /api/conversations/invoke` with `{"method": <name>, "args": [...], "kwargs": {...}}`,
  peer bearer auth. Server allowlists `method` against `PEER_CONVERSATION_METHODS`
  (exported from `peer_conversation_store.py`), calls the same-named method on the
  local `SqliteConversationStore`, and answers `200 {"value": <return value>}`
  (including `null`/`false`/`[]`, which are ordinary answers, not errors).
  A failed redaction answers `500 {"error": {"type": "RedactionFailed", "message": ...}}`.
  No `mcp_response()` redaction — internal entity communication.
- `GET /api/conversations/health` → `{"healthy": bool, "connected": bool}`.
- `Conversation`-carrying methods (`get`/`create`/`get_or_create` return, `save`
  accepts) pass `Conversation.to_dict()` at the wire.

A single dispatch endpoint (not one route per method) is deliberate: the proxy's
41 public methods share one envelope, so neither side can drift per-method.
`tests/test_peer_conversation_store.py` contains an executable reference
implementation (`FakeConversationServer`) backed by the real store — P3b's
routes must answer the same envelope, and its tests can reuse that fixture.

**Acceptance:** curl tests against a running HA server show all CRUD operations working.

### P3c — ThreadManager store injection [GLM]

**What:** When `canonical_thread_url` is set, the `ThreadManager` uses `PeerConversationStore` instead of a local `SqliteConversationStore`.

**Files:**
- Modified: wherever `ThreadManager` is instantiated (likely in agent setup or state machine)

**Acceptance:** With `canonical_thread_url` set, the `ThreadManager` uses the peer store. Without it, current behavior.

### P3d — Tests [Opus]

**Why Opus:** Concurrent access testing is subtle — two ThreadManagers operating on the same shared store via WAL. Needs to verify no data corruption.

**Files:**
- New: `halbert_core/tests/test_peer_conversation_store.py`
- New: `halbert_core/tests/test_shared_threads.py`

**Acceptance:** All tests pass. Two ThreadManagers on the same shared store don't corrupt data. Thread started on workstation is visible on HA server and vice versa.

---

## P4 — Compute fallback chain correction

Cloud primary, local model second, peer third, template (degraded) fourth, no-AI last.

### P4a — Internet connectivity detection [GLM]

**What:** A small module that probes internet connectivity (check the cloud LLM provider's health endpoint or a generic connectivity check). Cached for a configurable interval.

**Files:**
- New: `halbert_core/halbert_core/federation/connectivity.py`

**Acceptance:** Returns True when internet is reachable, False when not. Cached for 30s to avoid probing on every turn.

### P4b — ComputeRouter chain reorder [Opus]

**What:** Re-order the fallback chain in `ComputeRouter` so cloud is primary, local model second, peer third, template fourth, no-AI last. Add the connectivity probe.

**Why Opus:** Needs to understand the full `ComputeRouter` (turn types, health probing, deferred queue, hardware profile) and integrate the connectivity probe. The reordering is straightforward but needs to be correct for all 4 turn types.

**Files:**
- Modified: `halbert_core/halbert_core/federation/compute_router.py`
- Reference: `halbert_core/halbert_core/federation/connectivity.py` (P4a)

**Acceptance:** Cloud is tried first. If cloud fails (no internet), local model is tried (if GPU). If no local model, peer is tried. If no peer, template (degraded). If template fails, no-AI.

### P4c — Template degraded marker [GLM]

**What:** When template thoughts are served as a fallback, the response includes a clear "no thinking power" indicator so the user knows it's degraded.

**Files:**
- Modified: wherever template thoughts are rendered (likely in the thought generator or response formatting)

**Acceptance:** Template fallback response includes "I have no thinking power right now" or equivalent. User is never confused about whether they're talking to real AI.

### P4d — `peers_config` direction correction [GLM]

**What:** Support HA-server-as-issuer direction (HA server is the compute client, workstation is the compute provider). Both directions supported but default is HA → workstation.

**Files:**
- Modified: `halbert_core/halbert_core/federation/peers_config.py`

**Acceptance:** Config can express both directions. Default pairing direction is HA → workstation.

### P4e — Tests [GLM]

**Files:**
- Modified: `halbert_core/tests/federation/test_compute_router_route.py`
- New: `halbert_core/tests/federation/test_connectivity.py`
- New: `halbert_core/tests/federation/test_compute_fallback.py`

**Acceptance:** All fallback chain scenarios tested. Connectivity detection tested.

---

## P5 — Cross-node tool proxy

The HA server's agent can call workstation tools via the peer link. Security-sensitive.

### P5a — `PeerToolProxy` class [Fable]

**What:** Sends a specific, structured tool call to a peer's MCP server for execution. Uses the `fleet_proxy.py` pattern (MCP JSON-RPC over HTTP) but reversed direction.

**Why Fable:** Security-sensitive. Needs to understand the MCP protocol, the tool allowlist security model, the fleet proxy pattern, and the agent state machine's tool execution flow. Getting the security boundary wrong here could allow a compromised HA server to execute arbitrary tools on the workstation.

**Files:**
- New: `halbert_core/halbert_core/agents/peer_tool_proxy.py`
- Reference: `halbert_core/halbert_core/federation/fleet_proxy.py` (MCP client pattern)
- Reference: `halbert_core/halbert_core/mcp/server.py` (MCP protocol)
- Reference: `halbert_core/halbert_core/federation/tool_allowlist.py` (security model)

**Key design decisions:**
- The HA server sends a specific tool name + params, not an arbitrary prompt
- The workstation applies its existing safety gating (agent state machine, proposal approval) before executing
- Write actions (config editing, proposals) go through proposal approval regardless of which body initiated them
- The response from the peer is treated as a normal tool result in the HA server's agent loop

### P5b — State machine tool routing [Fable]

**What:** In `_handle_executing()`, when a tool call targets a capability that doesn't exist locally, check if a paired peer has that capability and route via `PeerToolProxy`.

**Why Fable:** Needs to understand the agent state machine's tool execution flow, the tool registry, and the capability model. This is where the "which body has this tool" decision is made.

**Files:**
- Modified: `halbert_core/halbert_core/agents/state_machine.py`
- Reference: `halbert_core/halbert_core/agents/peer_tool_proxy.py` (P5a)

### P5c — `peers_config` capability tracking [Opus]

**What:** Track which capabilities each peer has (sysadmin tools, SourcePrep, terminal, etc.). The HA server knows "my workstation peer has sysadmin tools" and can route accordingly.

**Files:**
- Modified: `halbert_core/halbert_core/federation/peers_config.py`

**Acceptance:** Config can express per-peer capabilities. The HA server can look up which peer has a given capability.

### P5d — Tests [Fable]

**Why Fable:** Security-sensitive. Write actions must require proposal approval even when proxied. A compromised HA server must not be able to execute arbitrary tools on the workstation.

**Files:**
- New: `halbert_core/tests/test_peer_tool_proxy.py`
- New: `halbert_core/tests/test_state_machine_tool_routing.py`
- New: `halbert_core/tests/test_tool_proxy_security.py`

---

## P6 — Wake-on-LAN (LAN-only, default off)

### P6a — WoL magic packet [GLM]

**What:** `send_wol_packet(mac_address, broadcast_address)` — constructs and sends the WoL magic packet. Pure stdlib (socket), no new dependency.

**Files:**
- New: `halbert_core/halbert_core/federation/wake_on_lan.py`

**Acceptance:** Magic packet construction is correct (6x 0xFF + 16x MAC). Broadcast sent. Connection errors handled.

### P6b — ComputeRouter WoL integration [Opus]

**What:** Before falling through to template degraded mode, check if any paired workstation has WoL enabled. If so, send the packet, wait up to timeout, poll peer health. Only for non-interactive turns (high_value_event, sleep_consolidation). Interactive voice gets template immediately.

**Files:**
- Modified: `halbert_core/halbert_core/federation/compute_router.py`
- Reference: `halbert_core/halbert_core/federation/wake_on_lan.py` (P6a)

### P6c — `peers_config` WoL fields [GLM]

**Files:**
- Modified: `halbert_core/halbert_core/federation/peers_config.py`

### P6d — Tests [GLM]

**Files:**
- New: `halbert_core/tests/federation/test_wake_on_lan.py`
- Modified: `halbert_core/tests/federation/test_compute_router_route.py`

---

## P7 — Setup / pairing UI

### P7a — Backend API endpoints [Opus]

**What:** Pairing API endpoints (pair, list devices, toggle entity mode, toggle WoL, remove device). Device capability discovery.

**Files:**
- New or extend: `halbert_core/halbert_core/dashboard/routes/devices.py` (or extend `peers.py`)

### P7b — Frontend Devices page [GLM]

**What:** Settings → Devices page with paired device list, body names, entity mode toggle, WoL toggle, remove device. Pairing flow modal.

**Files:**
- New: `halbert_core/halbert_core/dashboard/frontend/src/components/settings/DevicesSection.tsx` (or similar)
- Modified: `halbert_core/halbert_core/dashboard/frontend/src/pages/Settings.tsx`

### P7c — Frontend pairing flow [GLM]

**What:** "Add a device to Halbert" flow — enter HA server URL (or mDNS scan), confirm pairing, choose singular or independent mode.

**Files:**
- New: `halbert_core/halbert_core/dashboard/frontend/src/components/settings/PairingModal.tsx` (or similar)

### P7d — Tests [GLM]

**Files:**
- New: frontend component tests
- New: backend API tests

---

## Task list grouped by model

### Fable (Kimi-k3 [1M context]) — 5 tasks

| # | Task | Phase | Why |
|---|---|---|---|
| F1 | Haloysius `PeerMemoryBackend` class | P2a | New backend pattern, needs deep understanding of PersonaMemoryStore interface, smart_add semantics, subtractive contract |
| F2 | `PeerToolProxy` class | P5a | Security-sensitive, MCP protocol, tool allowlist security model, fleet proxy pattern |
| F3 | State machine tool routing | P5b | Needs agent state machine understanding, tool registry, capability model, "which body has this tool" decision |
| F4 | Tool proxy security tests | P5d | Security-sensitive — write actions must require proposal approval, compromised HA server must not execute arbitrary tools |
| F5 | Variant-as-hint refactor (follow-on) | Post-P7 | Significant refactor of variant gating → capability probing. Not part of this plan but flagged as follow-on |

### Opus (GLM-5.3 [1M context]) — 6 tasks

| # | Task | Phase | Why |
|---|---|---|---|
| O1 | `PeerConversationStore` | P3a | Large interface (many methods), mechanical but needs faithful replication, RedactionFailed propagation |
| O2 | Shared threads concurrent access tests | P3d | Concurrent access via WAL is subtle, needs to verify no data corruption |
| O3 | ComputeRouter chain reorder | P4b | Full router understanding (turn types, health probing, deferred queue, hardware profile), connectivity probe integration |
| O4 | `peers_config` capability tracking | P5c | Config change, per-peer capability model |
| O5 | ComputeRouter WoL integration | P6b | Pre-fallback step, non-interactive turn gating |
| O6 | Backend API endpoints (pairing, devices) | P7a | Multi-endpoint API, device capability discovery |

### GLM (GLM-5.2 [200k context]) — 12 tasks

| # | Task | Phase | Why |
|---|---|---|---|
| G1 | Halbert memory API endpoint | P2b | Straightforward FastAPI routes, well-defined interface |
| G2 | `cognition_wiring` memory integration | P2c | Small change, adapter already accepts any store |
| G3 | PeerMemoryBackend tests | P2d | Mocked HTTP, well-scoped |
| G4 | Conversation API endpoint | P3b | Straightforward FastAPI routes |
| G5 | ThreadManager store injection | P3c | Small change — pick store based on config |
| G6 | Internet connectivity detection | P4a | Small module, well-defined |
| G7 | Template degraded marker | P4c | Small change to response formatting |
| G8 | `peers_config` direction correction | P4d | Config change, small |
| G9 | Compute fallback tests | P4e | Well-scoped test scenarios |
| G10 | WoL magic packet | P6a | Self-contained, pure stdlib |
| G11 | `peers_config` WoL fields | P6c | Config change, small |
| G12 | Frontend Devices page + pairing flow | P7b, P7c | Well-defined UI components, existing patterns to follow |

---

## Execution order

```
P1 (done) ──► P2a (Fable) ──► P2b (GLM) ──► P2c (GLM) ──► P2d (GLM)
                    │
                    ├──► P3a (Opus) ──► P3b (GLM) ──► P3c (GLM) ──► P3d (Opus)
                    │
                    ├──► P4a (GLM) ──► P4b (Opus) ──► P4c (GLM) ──► P4d (GLM) ──► P4e (GLM)
                    │
                    ├──► P5a (Fable) ──► P5b (Fable) ──► P5c (Opus) ──► P5d (Fable)
                    │
                    ├──► P6a (GLM) ──► P6b (Opus) ──► P6c (GLM) ──► P6d (GLM)
                    │
                    └──► P7a (Opus) ──► P7b (GLM) ──► P7c (GLM) ──► P7d (GLM)
```

- P2 (F1, G1, G2, G3) is the keystone — delivers the core singular-entity experience
- P3, P4, P5 can proceed in parallel after P1 (no cross-dependencies)
- P6 depends on P4 (WoL is a pre-fallback step in the compute router)
- P7 depends on P1 (config fields) but can mock P2-P6 for UI development

**Minimum viable singular entity:** P1 (done) + P2 (F1, G1, G2, G3).
