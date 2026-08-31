# Implementation Plan: Singular Entity, Multi-Body

**Date:** 2026-08-31
**Parent handoff:** `HANDOFF-SINGULAR-ENTITY-MULTI-BODY-2026-08-31.md`
**Status:** Ready for implementation

---

## Overview

Add **singular entity mode** as an option on top of the existing independent-entity architecture. In singular mode, paired devices share one `persona_id`, one memory store, and one thread registry — they are one Halbert with multiple bodies. In independent mode (current behavior), each device is its own entity that shares compute.

The switch is config-driven: if `canonical_memory_url` is set, the device proxies memory to the canonical host (singular mode); if not, it uses local memory (independent mode). Zero migration risk.

---

## Phase 1 — Config foundation

**Goal:** Add the config fields that control entity mode. Zero behavior change — just plumbing.

### Changes

**`halbert_core/halbert_core/config/being_config.py`:**
- Add `body_name: Optional[str]` field to `BeingConfig` (default: `workstation` for sysadmin variant, `home` for home variant)
- Add `canonical_memory_url: Optional[str]` field (default: None = local memory)
- Add `canonical_thread_url: Optional[str]` field (default: None = local threads)
- Add validation: if `canonical_memory_url` is set, `persona_id_override` should match the canonical host's persona (warn if mismatched, don't error — the user might be mid-config)

**`halbert_core/halbert_core/integrations/cognition_wiring.py`:**
- `_get_body_name()` helper — reads `body_name` from `being.yml`, falls back to variant-based default
- Expose `body_name` to the prompt builder (via `AppSeam` or `StateContext`)

**Prompt builder (wherever identity/scene context is assembled):**
- In singular mode (when `canonical_memory_url` is set OR when `persona_id_override` is shared), include `body_name` in the identity prompt: "You are currently at your [body_name]."
- In independent mode, `body_name` is optional context, not an identity signal.

### Tests
- `test_being_config.py`: `body_name`, `canonical_memory_url`, `canonical_thread_url` fields parse correctly, defaults work, validation catches mismatched persona
- `test_cognition_wiring.py`: `_get_body_name()` returns correct values for both variants + override

### Acceptance
- Config fields exist and parse. No behavior change. Existing installs unaffected.

---

## Phase 2 — PeerMemoryBackend (the keystone)

**Goal:** Make singular mode real. The workstation reads/writes memory on the HA server over the peer link. Both cognitions share one autobiography.

### Changes

**Haloysius side — `haloysius/memory_v2/peer_backend.py` (new):**
- `PeerMemoryBackend` class implementing the same interface as the local `PersonaMemoryStore` backend
- `add(memory_entry)` → POST to `<canonical_memory_url>/add` with bearer auth
- `search(query, limit)` → GET `<canonical_memory_url>/search?q=...&limit=...` with bearer auth
- `get(id)` → GET `<canonical_memory_url>/get/<id>`
- Connection error handling: raise a `PeerMemoryUnavailable` exception (caller decides whether to fail gracefully or retry)
- Reuses the existing peer bearer auth pattern from `federation/peer_middleware.py`

**Halbert side — `halbert_core/halbert_core/dashboard/routes/memory.py` (new or extend):**
- `POST /api/memory/add` — accepts a `PersonaMemory` dict, reconstructs it, calls `store.smart_add()` (NOT raw insert — smart_add handles duplicate detection, contradiction detection, MERGE operations, embedding computation, and connection discovery)
- `GET /api/memory/search` — proxies to local `PersonaMemoryStore.search()`
- `GET /api/memory/get/{id}` — proxies to local `PersonaMemoryStore.get()`
- Protected by peer bearer auth (same middleware as compute endpoint)
- **No `mcp_response()` redaction** — this is internal entity communication, not external egress. Redacting would corrupt the shared autobiography.

**`halbert_core/halbert_core/integrations/cognition_wiring.py`:**
- `_create_memory_adapter()` — if `canonical_memory_url` is set, create `HaloysiusMemoryAdapter` backed by `PeerMemoryBackend` instead of local `PersonaMemoryStore`
- If not set, current behavior (local store)

**`halbert_core/halbert_core/integrations/haloysius_memory_adapter.py`:**
- `HaloysiusMemoryAdapter` already wraps a store; just needs to accept a `PeerMemoryBackend` instance instead of always creating a local `PersonaMemoryStore`

### Tests
- `test_peer_memory_backend.py`: mocked HTTP — add/search/get proxy correctly, auth header present, connection errors raise `PeerMemoryUnavailable`
- `test_memory_routes.py`: HA server memory endpoints work with bearer auth, reject without auth, redaction boundary applied
- `test_cognition_wiring.py`: `_create_memory_adapter()` picks `PeerMemoryBackend` when `canonical_memory_url` set, local store when not
- Integration test (mocked): workstation writes a memory via `PeerMemoryBackend` → HA server's local store has it → HA server's cognition retrieves it

### Acceptance
- Workstation configured with `canonical_memory_url` writes a memory → it appears in the HA server's `PersonaMemoryStore`
- HA server writes a memory → workstation's cognition can retrieve it via `PeerMemoryBackend`
- Connection failure raises `PeerMemoryUnavailable`, cognition handles gracefully (logged, not crashed)
- **This phase alone makes them one entity.**

---

## Phase 3 — Thread continuity (shared message history)

**Goal:** Cross-device conversation continuity. "Continue what we were saying" works from desk to kitchen.

**Design correction (from scrutiny):** The original plan proposed proxying the entire `ThreadManager` over HTTP. This is wrong — `ThreadManager.begin_turn()` is deeply stateful (thread decision logic, history building, hint building, open loops, terminal hints, recall management). Serializing a `TurnContext` over the wire on every turn would be a massive payload and terrible latency. Instead: share the underlying SQLite message history, not the ThreadManager logic.

### Changes

**Halbert side — `halbert_core/halbert_core/agents/peer_conversation_store.py` (new):**
- `PeerConversationStore` — a thin data-access proxy implementing the same interface as `SqliteConversationStore`
- Proxies only CRUD operations: `append_message()`, `get_thread()`, `current_open_thread()`, `update_thread()`, `list_open_loops()`, `search()`, etc.
- Does NOT proxy the thread decision logic — that runs locally on each node
- Connection error handling: raise `PeerConversationUnavailable`, caller degrades to local-only threads for the session
- Reuses peer bearer auth

**Halbert side — `halbert_core/halbert_core/dashboard/routes/conversations.py` (new or extend):**
- `POST /api/conversations/messages` — append message
- `GET /api/conversations/threads/{id}` — get thread
- `GET /api/conversations/threads/current` — current open thread
- `PUT /api/conversations/threads/{id}` — update thread
- `GET /api/conversations/threads/{id}/loops` — list open loops
- `GET /api/conversations/search` — search conversations
- Protected by peer bearer auth
- **No `mcp_response()` redaction** — this is internal entity communication

**`halbert_core/halbert_core/integrations/cognition_wiring.py` or agent setup:**
- If `canonical_thread_url` is set, the `ThreadManager`'s store is a `PeerConversationStore` instead of a local `SqliteConversationStore`
- If not, current behavior (local `SqliteConversationStore`)
- **No changes to `ThreadManager` itself** — it uses whatever store it's given. The thread decision logic, history building, hint building all run locally.

### How it works

- The HA server hosts the canonical SQLite conversation database (always on).
- The workstation's `ThreadManager` reads/writes to the HA server's database via `PeerConversationStore`.
- Each node runs its own `ThreadManager` with its own thread decision logic, but against the same shared data.
- SQLite WAL mode handles concurrent access. The store is already thread-safe with `busy_timeout`.
- Tradeoff: each node may independently open/close threads. Both nodes see the full conversation history.

### Tests
- `test_peer_conversation_store.py`: mocked HTTP — all CRUD operations proxy correctly, auth present, errors handled
- `test_conversation_routes.py`: HA server conversation endpoints work with auth
- Integration test (mocked): start a thread on the workstation → append to it from the HA server → both see the full history
- `test_shared_threads.py`: two ThreadManagers operating on the same shared store don't corrupt data (concurrent access via WAL)

### Acceptance
- Thread started on workstation is visible and continuable on the HA server
- Thread started on HA server is visible and continuable on the workstation
- Thread decision logic runs locally on each node (no network round trip per turn)
- Connection failure degrades gracefully (local-only threads for the session)

---

## Phase 4 — Compute fallback chain correction

**Goal:** Cloud is primary for all nodes. The fallback chain is: cloud → any available local or peer Ollama → template (degraded) → no AI.

### The corrected fallback chain

1. **Cloud LLM** (primary — all nodes, when internet is up)
2. **This node's own local Ollama** (if a GPU is installed — e.g., N150 with A2000, Mac with Apple Intelligence)
3. **Any awake peer's Ollama/LMStudio** (via peer link — automated fallback when cloud is unreachable)
4. **Template thoughts** (degraded — clearly marked as "no thinking power," not pretending to be real AI)
5. **No response** (unconscious — rare, acceptable)

### Changes

**`halbert_core/halbert_core/federation/compute_router.py`:**
- Re-order the fallback chain: cloud primary, local model second, peer third, template fourth, no-AI last
- The current scaffold assumes peer is the primary path. Correct this so cloud is primary.
- The HA server's `ComputeRouter` activates the peer path only when cloud fails AND no local model is configured.
- Template fallback must be clearly marked as degraded — the response should indicate "I have no thinking power right now" so the user is never confused.
- The workstation does NOT need a `ComputeRouter` — it uses cloud or its own local Ollama directly.

**`halbert_core/halbert_core/federation/peers_config.py`:**
- Support HA-server-as-issuer direction: the HA server is the client (offloads TO the workstation), the workstation is the compute provider.
- This is the reverse of the current scaffold's assumption (workstation offloads to HA server).
- Both directions should be supported (the peer link is symmetric in principle), but the default pairing direction for compute is HA → workstation.

**`halbert_core/halbert_core/federation/compute_endpoint.py`:**
- The workstation's compute endpoint serves the HA server's offload requests.
- Already scaffolded — just needs the direction confirmed and tested.

**`halbert_core/halbert_core/federation/connectivity.py` (new, small):**
- `check_internet_connectivity()` — probes the cloud LLM provider's health endpoint (or a generic connectivity check like `https://api.openai.com/v1/models` HEAD request). Returns True/False.
- Cached for a configurable interval (e.g., 30s) so a burst of turns probes once, not once per turn.
- Used by `ComputeRouter` to decide whether to try cloud or fall through to local/peer.

### Important: what actually needs the workstation

**Simple HA commands do NOT need the workstation.** "Turn on the lights" is a direct `ha_call_service` tool call from the HA server's own agent. The cloud LLM generates the tool call, the HA server executes it against HA's API. No workstation involvement. The fallback chain above is about **LLM inference**, not tool execution.

**The workstation is needed when the task requires sysadmin capabilities:** config editing, SourcePrep documentation, terminal commands. For those, see Phase 5 (cross-node tool proxy) — a separate path from compute-offload.

### Ollama endpoints across devices (zero new code — document only)

Ollama/LMStudio already support remote endpoints. A user can manually configure any node's `models.yml` to point at any other node's Ollama URL. This is already supported by the existing model config. No code changes needed — just document it as a config pattern:

```yaml
# Workstation pointing at HA server's A2000 Ollama
specialist_model:
  provider: ollama
  url: http://n150.tailnet.ts.net:11434
```

The peer link's automated compute-offload (this phase) is for the **fallback** case — when cloud is down and the node needs to automatically find a peer with compute. Manual endpoint configuration is already supported and is the primary way users share GPU resources across devices.

### Privacy note

If private data goes to a remote Ollama over the network, that's a user decision. The `secure_model` slot enforces local-only endpoints. Best cases:
- HA server with A2000 GPU: `secure_model` → `localhost:11434` (private data never leaves)
- Mac with Apple Intelligence: `secure_model` → local Apple Intelligence endpoint (always local on Apple Silicon)

### Tests
- `test_compute_router_route.py`: cloud primary, local model second, peer third, template fourth, no-AI last
- `test_compute_fallback.py`: HA server with no internet + local GPU → uses own Ollama; HA server with no internet + no GPU + workstation awake → offloads to workstation; HA server with no internet + no GPU + workstation asleep → template degraded
- `test_template_degraded.py`: template fallback response includes "no thinking power" indicator
- `test_peer_direction.py`: HA server as compute client, workstation as compute provider

### Acceptance
- HA server with internet: uses cloud directly, never touches peer compute
- HA server without internet + local GPU: uses own Ollama
- HA server without internet + no GPU + workstation awake: offloads to workstation's Ollama
- HA server without internet + no GPU + workstation asleep: template degraded (clearly marked)
- Template fallback is obviously degraded — user is never confused about whether they're talking to real AI

---

## Phase 5 — Cross-node tool proxy

**Goal:** The HA server's agent can call workstation tools via the peer link. In singular mode, the entity at the kitchen can use the workstation's sysadmin capabilities (config editing, SourcePrep, terminal) without the user walking to the desk.

**Why this exists:** The HA server's cloud LLM can generate any tool call, but the HA server only has home-variant tools locally. When the LLM generates a tool call that needs a workstation capability (e.g., `search_knowledge` for HA documentation, `get_config_value` for HA config files, `edit_system_config` for config changes), the HA server currently fails. The tool proxy routes these calls to the workstation's MCP server for execution.

**Example:** User in the kitchen says "can we edit the lighting in this room so it uses warm colors after 8pm in the summer?" The entity needs to:
1. Look up HA documentation → `search_knowledge` on workstation's SourcePrep
2. Find the current lighting config → `get_config_value` on workstation's config watcher
3. Propose the change → `edit_system_config` proposal on workstation
4. The user reviews and approves the proposal (from either body)

Simple commands like "turn on the lights" do NOT use this path — they use the HA server's own `ha_call_service` tool directly.

### Changes

**Halbert side — `halbert_core/halbert_core/agents/peer_tool_proxy.py` (new):**
- `PeerToolProxy` — sends a specific, structured tool call to a peer's MCP server for execution
- Uses the `fleet_proxy.py` pattern (MCP JSON-RPC over HTTP) but reversed direction: HA server is the MCP client, workstation is the MCP server
- Bearer auth from `peers_config.py`
- The workstation applies its existing safety gating (agent state machine, proposal approval) before executing

**Halbert side — `halbert_core/halbert_core/agents/state_machine.py` (modified):**
- In the `_handle_executing()` state, when a tool call targets a capability that doesn't exist locally, check if a paired peer has that capability
- If so, route the tool call via `PeerToolProxy` instead of executing locally
- The response from the peer is treated as a normal tool result

**`halbert_core/halbert_core/federation/peers_config.py`:**
- Track which capabilities each peer has (sysadmin tools, SourcePrep, terminal, etc.)
- The HA server knows "my workstation peer has sysadmin tools" and can route accordingly

**Security model:**
- Different from compute-offload (which sends arbitrary prompts to the peer's GPU with a restricted toolset — prompt injection concern)
- This is a specific, structured tool call — the workstation applies its own safety gating before executing
- Write actions (config editing, proposals) still go through the proposal approval flow — the HA server can't unilaterally change the workstation's configs
- The existing `fleet_proxy.py` defense-in-depth pattern (satellite applies `mcp_response()`, workstation applies it again) applies here too

### Tests
- `test_peer_tool_proxy.py`: tool calls route correctly to peer MCP server, auth present, safety gating applied on the peer side
- `test_state_machine_tool_routing.py`: state machine routes non-local tool calls to peer when a capable peer is available
- `test_tool_proxy_security.py`: write actions require proposal approval even when proxied

### Acceptance
- HA server's agent can call `search_knowledge` on the workstation's SourcePrep via the peer link
- HA server's agent can call `get_config_value` on the workstation's config watcher via the peer link
- Write actions (config editing) go through proposal approval regardless of which body initiated them
- Simple HA commands (`ha_call_service`) do NOT use the tool proxy — they execute locally on the HA server

---

## Phase 6 — Wake-on-LAN (optional, default off, LAN-only)

**Goal:** The HA server can wake a sleeping workstation for compute fallback or tool proxy instead of falling through to template degraded mode. LAN-only — WoL magic packets are broadcast UDP and do not cross Tailscale tunnels.

**WoL is for non-interactive turns only.** Interactive voice turns should never wait 90s for a workstation to wake. Voice gets template thoughts immediately (clearly marked as degraded). WoL fires in the background for the next high_value_event or sleep_consolidation turn.

### Changes

**`halbert_core/halbert_core/federation/peers_config.py`:**
- Add `wake_on_lan` section to per-peer config:
  ```python
  wake_on_lan: {
      enabled: bool = False,
      mac_address: Optional[str] = None,
      broadcast_address: Optional[str] = None,  # default: 255.255.255.255
      timeout_seconds: int = 90,
  }
  ```

**`halbert_core/halbert_core/federation/compute_router.py`:**
- Before falling through to template degraded mode, check if any paired workstation has WoL enabled
- If so, send a magic packet (`wakeonlan <mac>` or raw UDP broadcast), wait up to `timeout_seconds`, poll peer health
- If peer comes up, offload. If not, fall through to template degraded mode.
- Log: "Attempting to wake workstation [body_name] for compute fallback..."

**`halbert_core/halbert_core/federation/wake_on_lan.py` (new, small):**
- `send_wol_packet(mac_address, broadcast_address)` — constructs and sends the WoL magic packet (6x 0xFF + 16x MAC)
- Pure stdlib (socket), no new dependency

**Settings UI:**
- Per-peer toggle: "Allow Halbert to wake this device for compute"
- MAC address field (auto-detected if possible, manual entry fallback)
- Timeout slider (30-180s, default 90s)
- Only shown for workstation-variant peers

### Tests
- `test_wake_on_lan.py`: magic packet construction correct, broadcast sent, connection errors handled
- `test_compute_router_wol.py`: router attempts WoL before template degraded mode, respects timeout, falls through if workstation doesn't wake

### Acceptance
- HA server with no internet + workstation asleep + WoL enabled: sends magic packet, waits, offloads if workstation wakes
- HA server with no internet + workstation asleep + WoL disabled: falls through to template degraded mode (clearly marked as no thinking power)
- WoL disabled by default — no surprise wake-ups

### Limitations (documented)
- WoL magic packets are broadcast on the local subnet. **LAN-only.** WoL does NOT work over Tailscale (point-to-point tunnels have no broadcast domain). We are local-network-oriented by design. Tailscale is scoped for later research as a remote-access feature.
- Both devices must be on the same L2 network (same physical LAN, no router between them).
- Linux WoL depends on motherboard BIOS support — not guaranteed (user noted theirs is challenging).
- Mac WoL is reliable when `pmset wakeonnetaccess` is enabled.
- WoL only fires for non-interactive turns (high_value_event, sleep_consolidation). Interactive voice gets template immediately; WoL fires in background for the next turn.

---

## Phase 7 — Setup / pairing UI

**Goal:** Users configure singular entity mode through a UI, not YAML editing.

### Changes

**Pairing flow (dashboard frontend):**
1. User opens Halbert on the workstation, goes to Settings → Devices
2. "Add a device to Halbert" → enters HA server URL (or scans mDNS)
3. HA server confirms pairing, issues a bearer token
4. User chooses: "This device is part of Halbert" (singular) or "This is a separate Halbert" (independent)
5. If singular: workstation auto-configures `canonical_memory_url`, `canonical_thread_url`, same `persona_id`
6. If independent: workstation gets its own `persona_id`, no canonical URLs

**Settings → Devices page:**
- List of paired devices with: body name, variant, status (online/asleep), entity mode
- Per-device: rename body, toggle entity mode (split into own entity / rejoin singular), toggle WoL, remove device

**"Separate this device" affordance:**
- One click: assigns a new `persona_id`, drops `canonical_memory_url` / `canonical_thread_url`
- The device becomes its own entity but keeps the compute peer link
- Reversible: "Rejoin Halbert" re-links to the canonical host

### Tests
- Frontend component tests for the pairing flow and devices page
- Backend tests for the pairing API endpoints

### Acceptance
- User can pair a workstation to an HA server through the UI
- User can switch between singular and independent mode through the UI
- User can toggle WoL per device through the UI
- No YAML editing required for any of the above

---

## Dependency graph

```
P1 (config) ──► P2 (memory) ──► P3 (threads)
                    │
                    ├──► P4 (compute fallback) ──► P6 (WoL)
                    │
                    └──► P5 (tool proxy)
                              │
                    P7 (UI) ──┘ (depends on all config fields existing)
```

- P1 is prerequisite for all others (config fields must exist)
- P2 is the keystone — delivers the core singular-entity experience
- P3 can proceed in parallel with P4 (no dependency between them)
- P5 depends on P1 (config) but is independent of P2/P3/P4 — it can proceed in parallel
- P6 depends on P4 (WoL is a pre-fallback step in the compute router)
- P7 depends on P1 (config fields) but can mock P2-P6 for UI development

**Minimum viable singular entity:** P1 + P2. Everything else is refinement.

---

## Risk register

| Risk | Mitigation |
|---|---|
| Memory proxy adds latency to every cognition tick | `PeerMemoryBackend` caches recent reads; writes are async-fire-and-forget with retry |
| HA server reboot loses workstation perception writes | v1: fail gracefully (logged). v2: local write buffer with flush-on-reconnect |
| User accidentally splits entity and loses shared memory | Settings UI shows a confirmation dialog with clear consequences; memory is NOT deleted, just not shared |
| WoL wakes the Mac at 3am unexpectedly | Default off; user must explicitly enable per device; log all WoL attempts |
| Peer link auth token compromise | Reuse existing `peers_config.py` revocation; per-peer tokens, surgical revocation |
| Cloud LLM is primary but user has no cloud account | Detect on first boot; if no cloud LLM configured, local/peer Ollama becomes primary (graceful degradation) |

---

## Follow-on: Variant as hint, not hard gate

**Not part of this implementation plan.** Tracked separately, but informed by this work.

Today the variant system (`VALID_VARIANTS = {"sysadmin", "home"}`) hard-gates service registration. A `home` node cannot run ingestion, scheduler, config watcher, terminal, SourcePrep, or secure_model — period.

The principle from the singular-entity handoff (Section 4): **capability should emerge from what hardware and services are present, not from a variant label.** A Mac Studio with HA configured should do both sysadmin AND home. An N150 with an A2000 GPU should run local LLM. The variant becomes a preset/hint (default config, UI emphasis), not a hard gate.

This is a significant refactor of `dashboard/app.py` (service registration), `cognition_wiring.py` (variant-gated skips), and the tool registry. It should be scoped as a separate workstream after the singular-entity work is stable. The singular-entity implementation plan assumes the current variant system as-is — this follow-on changes how capabilities are determined, but doesn't change how identity/memory/threads are shared.
