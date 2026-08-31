# Handoff: Singular Entity, Multi-Body — One Halbert Across Devices

**To:** Implementation AI
**From:** Architecture / product planning
**Date:** 2026-08-31
**Status:** Design complete, implementation plan written (see `IMPL-PLAN-SINGULAR-ENTITY-2026-08-31.md`)

---

## 1. The goal in one sentence

A user with an HA server (N150) and a workstation (Mac Studio) should experience **one Halbert** — the same entity at the desk and in the kitchen — not two AIs that share a GPU. This is the **default** mode. But the existing "each device is its own entity that shares compute" mode remains a first-class option for users who want separate AIs.

---

## 2. Two entity modes (both first-class)

| | Singular Entity (default) | Independent Entities (option) |
|---|---|---|
| **persona_id** | Same on all paired devices | Different per device |
| **Memory** | One canonical store on the always-on node (HA server); others proxy via `PeerMemoryBackend` | Each device has its own local store (current behavior) |
| **Threads** | One canonical `ThreadManager` on the always-on node; others proxy via `PeerThreadBackend` | Each device has its own `ThreadManager` (current behavior) |
| **Compute** | Cloud primary for all; HA server falls back to any awake workstation's Ollama when offline | Same — compute sharing is independent of entity mode |
| **Cognition** | Each device runs its own `PersonaCognition` with the same `persona_id` + shared memory | Each device runs its own `PersonaCognition` with its own `persona_id` + local memory |
| **Switching** | Config: `canonical_memory_url` set → singular; unset → independent | Current behavior, zero changes needed |

**Key insight:** Independent mode IS the current architecture. Singular mode is added ON TOP, not replacing it. The switch is config-driven — if `canonical_memory_url` is set, the device proxies memory to the canonical host; if not, it uses local memory as-is. Zero migration risk for existing installs. New paired installs default to singular; a lone install with no peers is trivially "singular with one body" = same as standalone.

**Giving each device its own entity (opt-out from singular):** In settings, a user can split a paired device into its own entity by assigning it a different `persona_id`. This breaks the memory/thread sharing and makes it independent. The compute peer link still works — they share GPU but not identity. This should be a simple settings affordance, not a YAML edit.

---

## 3. Body names (singular mode UX)

In singular mode, the user may want to distinguish which body they're talking to: "I'm at my desk right now" vs "I'm in the kitchen." This is a **body_name**, not a `persona_id`. The `persona_id` stays the same (the entity); the `body_name` is a physical-location label.

- Add a `body_name` field to `being.yml` (e.g., `body_name: desk`, `body_name: home`).
- In singular mode, the prompt builder includes "You are currently speaking from your [body_name] body" so the entity knows where it is.
- In independent mode, `body_name` is optional — it's just a device label for logging/UI.
- Default `body_name` values: `workstation` for sysadmin variant, `home` for home variant. User can override.

---

## 4. Capability from hardware + context, not variant labels

**Principle:** A node's capability should emerge from what hardware and services are present, not from a variant label. If a node has a terminal and config files, it can do sysadmin. If it has HA connected, it can do home automation. If it has a GPU, it can do local LLM. The variant becomes a **preset/hint** (default config, UI emphasis), not a **hard gate**.

Today the variant system (`VALID_VARIANTS = {"sysadmin", "home"}`) hard-gates service registration: a `home` node cannot run ingestion, scheduler, config watcher, terminal, SourcePrep, or secure_model — period. This is wrong for the singular-entity vision. A Mac Studio that has HA configured should be able to do **both** sysadmin AND home things. An N150 with an A2000 GPU should be able to run local LLM inference. The body's hardware determines what the entity can **do**, not a label.

**This is a separate architectural change** from the singular-entity work. The singular-entity implementation plan assumes the current variant system as-is. The variant-as-hint refactor is a follow-on that should be tracked separately. But the singular-entity design is informed by this principle: in singular mode, the entity knows which body it's in and what that body can do — capability is per-body, driven by what's there.

**Example:** In singular mode with a Mac + N150:
- At the Mac body: "I can edit configs, run terminal commands, analyze my logs, and I can also see the front door camera and control the lights."
- At the N150 body (voice): "I can control the lights, see the cameras, and talk to you. I can't edit configs right now — my desk body is asleep."

The entity doesn't say "I'm a home variant so I can't do sysadmin." It says "my desk body has those tools but it's asleep right now." Capability is real and physical, not label-gated.

---

## 5. What we are NOT building

- **Not "federated" or "multi-node" in user-facing language.** The node-based architecture is the implementation; the product is one entity. Users pair devices in a setup flow ("add this Mac as part of Halbert") and never see the word "node" or "peer."
- **Not a thin client + brain.** Both nodes are full Halbert instances. They differ in what hardware they have and how you interact with them, not in whether they're a "real" Halbert.
- **Not a replicated-mind CRDT.** There is no merge problem because there is only one memory store, hosted on the always-on node.
- **Not a hardcoded "HA nodes can't have local LLMs" assumption.** An N150 can have an A2000 GPU added and run a local LLM. The fallback chain includes "local model on this node if configured." The HA server is a thin client by default, but a user can upgrade it.
- **Not a dead "tiny 3B model on the HA node" plan.** That specific plan (mandatory 3B on every HA node) is dead. But a user-installed GPU with a proper local model on the HA node is absolutely supported — it's just not assumed or required.

---

## 6. The two bodies (common case: 1 HA + 1 workstation)

| | Workstation (Mac Studio) | HA Server (N150) |
|---|---|---|
| **Variant (preset)** | `sysadmin` | `home` |
| **body_name** | `desk` (default: `workstation`) | `home` |
| **Always on?** | No — sleeps when user is away | Yes — always-on appliance |
| **Interface** | Keyboard / screen (desk) | Voice / Wyoming (kitchen, bedroom) |
| **Capabilities** | Emerges from hardware: terminal, config files, GPU, SourcePrep index → sysadmin tools. HA configured → also home tools. | Emerges from hardware: HA connected → home tools. GPU installed (e.g. A2000) → local LLM. No terminal by default. |
| **LLM** | Cloud (normal) or local Ollama/LMStudio (offline) | Cloud (normal) or local Ollama (if GPU installed) or offload to any awake peer's Ollama (if no internet) |
| **Cognition** | Runs its own `PersonaCognition` with shared `persona_id` | Runs its own `PersonaCognition` with shared `persona_id` |
| **Memory (singular mode)** | Reads/writes to the HA server's store via `PeerMemoryBackend` | Local `PersonaMemoryStore` (canonical, always on) |
| **Memory (independent mode)** | Local `PersonaMemoryStore` (own persona) | Local `PersonaMemoryStore` (own persona) |
| **Perception** | System events (sysadmin observations) → shared memory | HA entities, Frigate cameras, voice → shared memory |
| **Threads (singular mode)** | Proxies thread operations to HA server via `PeerThreadBackend` | Local `ThreadManager` (canonical, always on) |
| **Threads (independent mode)** | Local `ThreadManager` (own persona) | Local `ThreadManager` (own persona) |

In singular mode, both are the same entity because they share **persona_id + memory + threads**. They differ in what they can do and how you talk to them — like a person who's focused at their desk and relaxed in the kitchen. In independent mode, they're two separate AIs that share compute.

---

## 7. Why memory is the identity (not a shared cognition singleton)

The clean architectural insight: **memory is what makes them one person, not a shared cognition process.**

Two nodes with the same `persona_id` and the same memory store ARE the same entity — even if their in-the-moment emotional/scene state diverges. That's like a person who's focused at their desk and relaxed in the kitchen. The autobiography is shared; that's the identity.

Each node runs its **own** `PersonaCognition` with the same `persona_id`, reading from and writing to **one** memory store (hosted on the HA server, the always-on node). No cognition delegation RPC. No round-trip latency on the cognition tick. The workstation's cognition does sysadmin work against shared memory; the HA server's cognition does home/voice work against the same shared memory. Both "know" about both bodies because the memories are shared — "I noticed my workstation's disk was failing" (written by the Mac) is retrievable when you ask the HA speaker "how's your workstation doing?"

This avoids the entire distributed-database / split-brain problem. There is one store, on one always-on node. The workstation is a read-write client of it, not a replica.

---

## 8. LLM routing (corrected)

The fallback chain, from best to worst:

1. **Cloud LLM** — both nodes use cloud when internet is up (normal case)
2. **Any available local or peer Ollama/LMStudio** — if no internet, try in order:
   - This node's own local Ollama (if a GPU is installed — e.g., N150 with A2000, or Mac with Apple Intelligence)
   - Any awake peer's Ollama/LMStudio (via the peer link — just a URL endpoint, zero new code)
3. **Template thoughts (degraded mode)** — clearly marked as "no thinking power." The entity says something like "I can't think right now, but here's what I last knew..." This is NOT pretending to be real AI. It's an honest degraded state.
4. **No response** — the entity is "unconscious." Rare (no internet, no local GPU, no awake peers). Acceptable.

### Ollama endpoints across devices (zero new code)

Ollama and LMStudio already support remote endpoints. A user can:
- Install Ollama on the HA server with an A2000 GPU → point the workstation's `specialist_model` at `http://n150:11434`
- Install Ollama on the workstation → point the HA server's fallback model at `http://mac-studio:11434`
- Install Ollama on a Linux box → point both other nodes at it

This is just URL configuration in `being.yml` / `models.yml`. The existing model config already accepts arbitrary URLs. **Zero new code.** The peer link's compute-offload is for the automated fallback case (HA server detects no internet → automatically tries peer Ollama). Manual endpoint configuration is already supported.

### Privacy note: remote Ollama and private data

If private data (secrets, configs, HA tokens) is processed by a remote Ollama instance, the data transits the network. For Tailscale/LAN this is relatively safe, but it's a user decision. The `secure_model` slot (local-only endpoint enforcement) exists for when the user wants private data to stay local:

- **HA server with A2000 GPU**: `secure_model` points at `localhost:11434` — private data never leaves the node. Best case.
- **HA server without GPU, Mac with Apple Intelligence**: `secure_model` on the Mac points at the local Apple Intelligence endpoint. Private data stays on the Mac. The HA server doesn't process private data — HA credentials are handled by tool calls that abstract them away.
- **HA server without GPU, workstation with Ollama, user accepts network transit**: `secure_model` can point at the workstation's Ollama over Tailscale. The user explicitly accepts this risk.

The Mac's Apple Intelligence is always local and always available (on Apple Silicon), so a Mac body always has a local private-data option without any GPU installation.

### Template fallbacks are allowed but must be obviously degraded

Template thoughts are a real fallback tier, not just setup mode. But they must be **clearly marked** as degraded — the entity should say "I have no thinking power right now" or equivalent, not pretend to be reasoning. The user should never be confused about whether they're talking to real AI or a template response. This is an honesty/UX requirement, not just a technical one.

### Direction correction

The existing `federation/compute_router.py` and `HANDOFF-N150-PEER-OFFLOAD.md` assume the **workstation is the compute host** and the **HA server offloads to it**. That direction is correct for the no-internet fallback case (HA server → workstation's Ollama). But it is NOT the primary compute path — the primary path for both nodes is **cloud LLM directly**. The peer link's compute-offload is only for the offline-fallback case, not the normal case.

This means the peer compute link is **less central** than the current scaffold assumes. The primary new use of the peer link is **memory + thread federation**, not compute offload. Compute offload is a secondary feature for the offline edge case.

---

## 9. What's already built (the 95%)

| Piece | Status |
|---|---|
| Same `persona_id` on both nodes | Already supported via `being.yml` `persona_id_override` |
| HA server runs cognition tick locally | Already works (`cognition_wiring.get_cognition_tick()`) |
| HA server perception (HA events, Frigate, voice) | Already wired (`HAEventMapper`, `FrigateEventMapper`, `CompositeEventMapper`) |
| Variant system (sysadmin vs home tool surface) | Already done (`VALID_VARIANTS`, `is_home_variant()`, per-variant service skips in `app.py`) |
| Peer link (bearer auth, health probes, redaction boundary) | Already scaffolded (`federation/`) |
| Home variant skip list (no ingestion, no scheduler, no config watcher, no terminal, no SourcePrep, no secure_model) | Already done |

---

## 10. What's genuinely new (the 5%)

Three modules, all reusing the existing peer link:

### M1 — `PeerMemoryBackend` (the keystone)

A `PersonaMemoryStore` backend that proxies `add` / `search` to the HA server's store over the peer HTTP link.

- **HA server**: uses its local `PersonaMemoryStore` as-is (canonical, always on).
- **Workstation**: configured with `canonical_memory_url: http://n150.tailnet.ts.net:8001/api/memory` in `being.yml`. Its `PersonaMemoryStore` is backed by `PeerMemoryBackend`, which proxies all reads/writes to the HA server.
- **Both cognitions** read the same autobiography. The workstation writes sysadmin observations ("I noticed my workstation's disk was failing"); the HA server writes home observations ("the front door opened"). Both retrieve from the union.
- **Reuses**: peer bearer auth, existing peer HTTP transport. **No `mcp_response()` redaction** — this is internal entity communication, not external egress.

**Where it lives:** Haloysius side (`haloysius/memory_v2/peer_backend.py` or similar), so the engine supports a remote-backed memory store as a first-class option. Halbert's `cognition_wiring._create_memory_adapter()` picks the peer backend when `canonical_memory_url` is set.

### M2 — Thread continuity (shared message history, NOT full proxy)

The original plan proposed proxying the entire `ThreadManager` over HTTP. Scrutiny revealed this is wrong: `ThreadManager.begin_turn()` is deeply stateful (thread decision logic, history building, hint building, open loops, terminal hints, recall management — all against a local `SqliteConversationStore` with re-entrant locks). Serializing a `TurnContext` over the wire on every turn would be a massive payload and significant latency.

**Corrected approach:** Share the underlying SQLite message history, not the ThreadManager logic.

- **HA server**: hosts the canonical `SqliteConversationStore` (SQLite database file, always on).
- **Workstation**: its `ThreadManager` reads/writes to the HA server's SQLite database via a thin data-access proxy (`PeerConversationStore`) — just the CRUD operations (`append_message`, `get_thread`, `current_open_thread`, etc.), not the thread decision logic.
- **Each node runs its own `ThreadManager`** against the shared store. Thread decisions (which thread does this turn belong to?) run locally — fast, no network round trip. The conversation data is shared — the entity's conversation history is continuous across devices.
- SQLite WAL mode handles concurrent access. The store is already thread-safe with `busy_timeout`.
- **Tradeoff:** each node may independently open/close threads (they share the data but have their own thread state machine). This is fine — the shared message history means both nodes see the full conversation.

**Where it lives:** Halbert side — `PeerConversationStore` (thin data-access proxy for `SqliteConversationStore`) + a conversation API endpoint on the HA server. Each node's `ThreadManager` uses the store as-is — no changes to thread decision logic.

### M3 — Reversed compute fallback direction

When the HA server has no internet, it offloads LLM inference to the workstation's Ollama/LMStudio via the peer link.

- The existing `ComputeRouter` + `PeerProvider` scaffold already supports this — it just needs the **direction corrected**. The current scaffold assumes workstation = compute host, HA = satellite. For the offline fallback case that's actually correct (HA offloads TO the workstation). But the framing in the handoff docs assumes the workstation is the primary compute source, which is wrong — cloud is primary for both.
- **What changes:** the compute-offload path becomes a **secondary fallback**, only activated when the HA server detects no internet. The `ComputeRouter`'s primary path is cloud; the peer path is the offline fallback. The workstation's own LLM calls go to cloud directly (or its own local Ollama if the user prefers).
- **New infrastructure needed:** internet connectivity detection. Nothing in the codebase currently detects "no internet." The `ComputeRouter` needs a connectivity probe (check the cloud LLM provider's health endpoint or a generic connectivity check) before deciding to fall back. This is a new piece of infrastructure not in the current plan.

**Where it lives:** `federation/compute_router.py` — re-order the fallback chain so cloud is primary, peer is secondary (offline only). Add an internet connectivity probe. The workstation does not need a `ComputeRouter` at all — it uses cloud or its own local model directly.

### M4 — Cross-node tool proxy (new, identified during scrutiny)

**The gap:** In singular mode, the entity at the kitchen (HA server) may need workstation capabilities — config editing, SourcePrep documentation, terminal commands. Today there is no path for the HA server's agent to call workstation tools. The cloud LLM generates a tool call, the HA server tries to execute it locally, and it fails because home variant skips those services.

**Example:** User in the kitchen says "can we edit the lighting in this room so it uses warm colors after 8pm in the summer?" The entity needs to: (1) look up HA documentation (SourcePrep on workstation), (2) find and edit the HA config (config editing on workstation), (3) verify the change. Simple commands like "turn on the lights" do NOT need this — they use the HA server's own `ha_call_service` tool directly.

**The fix:** A cross-node tool proxy path — the HA server's agent recognizes when a tool call needs a workstation capability and routes it to the workstation's MCP server for execution. This is NOT the compute-offload path (which is about GPU inference with a restricted toolset). This is about **tool execution on the other body**.

**Security model:** Different from compute-offload. The HA server isn't sending an arbitrary prompt for the workstation's GPU to process (prompt injection concern). It's sending a specific, structured tool call for the workstation to execute. The workstation applies its existing safety gating (agent state machine, proposal approval) before executing. The existing `fleet_proxy.py` pattern (MCP client over HTTP) is the right template — just reversed direction.

**Where it lives:** Halbert side — a `PeerToolProxy` in the agent layer + tool proxy endpoint on the workstation's MCP server. The HA server's agent state machine gains a "route to peer" step when a tool call targets a capability that doesn't exist locally.

### Redaction boundary correction

The original plan said memory/thread endpoints should pass through `mcp_response()`. **This is wrong.** `mcp_response()` redacts for **external** egress (what leaves a node toward cloud services or untrusted callers). Memory/thread/tool federation between two Halbert nodes is **internal entity communication** — like memory staying within the entity. Redacting it would corrupt the shared autobiography. Bearer auth + TLS is the right protection for inter-node federation.

Redaction **does** apply to the compute-offload response path (where the workstation processes a request and returns tokens that could contain sensitive data). The existing `mcp_response()` on the compute endpoint is correct and should stay.

### Memory endpoint must use `smart_add()`

The HA server's memory endpoint must call `PersonaMemoryStore.smart_add()`, not raw insert. `smart_add` does duplicate detection, contradiction detection, MERGE operations, embedding computation, and connection discovery. If the endpoint just inserts raw JSON, none of this happens — the memory graph is incomplete and the embedding index is stale.

---

## 11. Disconnect cases

| Scenario | What happens |
|---|---|
| **Workstation sleeps** (normal, every night) | HA server continues normally: cloud LLM + home perception + voice. Sysadmin tools unavailable. Entity says "my workstation is asleep." No data loss — memory is on the HA server. |
| **No internet, workstation awake** | HA server offloads to workstation's Ollama/LMStudio via peer link. Slower but functional. Workstation uses its own Ollama/LMStudio directly. |
| **No internet, workstation asleep, HA has GPU** | HA server uses its own local Ollama (A2000). Full functionality, no network needed. |
| **No internet, workstation asleep, no GPU** | Template thoughts (degraded — entity says "I can't think right now"). If WoL enabled, HA server may wake the workstation first. |
| **Workstation wakes** | Starts running its own cognition again, reads shared memory (via `PeerMemoryBackend`), streams sysadmin perception to shared memory. Entity "wakes up at the desk." |
| **HA server reboots** | Workstation's `PeerMemoryBackend` gets connection errors; writes buffer or fail gracefully. When HA server returns, workstation reconnects. No data loss on the HA server (persistent store). Workstation may lose perception writes during the gap — acceptable. |
| **Both up, user moves desk → kitchen** | Thread continuity: user starts a conversation at the desk, walks to the kitchen, says "continue what we were saying." HA server's voice session picks up the same thread_id from the canonical `ThreadManager`. |

---

## 12. Config sketch

### HA server (N150) — `being.yml`

```yaml
persona_id_override: halbert          # same on both nodes (singular mode)
variant: home
body_name: home                        # how the entity refers to this body

# Memory: local (canonical, always on)
# No canonical_memory_url — this node IS the memory host

# Threads: local (canonical, always on)
# No canonical_thread_url — this node IS the thread host

# LLM: cloud primary, local Ollama if GPU installed, workstation fallback when offline
chat_model:
  provider: openai                     # or whatever cloud provider
  # ...cloud config...
# If the user installed an A2000 GPU on this N150:
# specialist_model:
#   provider: ollama
#   url: http://localhost:11434        # local GPU — also serves as secure_model endpoint
# Offline fallback (configured in federation, not being.yml):
# peers:
#   - url: http://mac-studio.tailnet.ts.net:8000
#     role: compute_fallback
#     token_env: HALBERT_WORKSTATION_TOKEN
```

### Workstation (Mac Studio) — `being.yml`

```yaml
persona_id_override: halbert          # same on both nodes (singular mode)
variant: sysadmin
body_name: desk                        # how the entity refers to this body

# Memory: proxy to HA server (canonical, always on)
canonical_memory_url: http://n150.tailnet.ts.net:8001/api/memory

# Threads: proxy to HA server (canonical, always on)
canonical_thread_url: http://n150.tailnet.ts.net:8001/api/threads

# LLM: cloud primary, local Ollama secondary (also serves HA server when it's offline)
chat_model:
  provider: openai                     # cloud primary
  # ...cloud config...
specialist_model:
  provider: ollama                     # local, also serves as HA's offline fallback
  url: http://localhost:11434
```

### Independent entities (opt-out from singular)

To give each device its own entity, simply use a different `persona_id` and omit the canonical URLs:

```yaml
# Workstation — being.yml
persona_id_override: halbert-desk      # different persona = different entity
variant: sysadmin
body_name: desk
# No canonical_memory_url — local memory (independent)
# No canonical_thread_url — local threads (independent)
# Compute peer link still works — they share GPU, just not identity
```

```yaml
# HA server — being.yml
persona_id_override: halbert-home      # different persona = different entity
variant: home
body_name: home
# No canonical_memory_url — local memory (independent)
```

This should be exposed in settings as a simple "separate this device into its own entity" affordance — the user picks a name, and the device gets its own `persona_id` + drops the canonical URLs. No YAML editing required.

### Pairing

The workstation is paired to the HA server (not the other way around). The HA server issues a per-workstation bearer token. The workstation uses it for memory + thread + compute-fallback calls. This reuses the existing `federation/peers_config.py` bearer auth — just with the HA server as the token issuer and the workstation as the client.

### Sharing Ollama endpoints across devices (zero new code)

Ollama and LMStudio already support remote endpoints. Any node can point its model config at any other node's Ollama URL. This is just `models.yml` / `being.yml` configuration — the existing model config already accepts arbitrary URLs. No code changes needed.

```yaml
# Any node pointing at the HA server's A2000 Ollama
specialist_model:
  provider: ollama
  url: http://n150.tailnet.ts.net:11434

# Any node pointing at the Mac's Apple Intelligence (local-only, Mac itself only)
# This is configured via the apple-foundation provider, not a remote URL
```

The peer link's automated compute-offload (Phase 4 of the implementation plan) is for the **fallback** case — when cloud is down and a node needs to automatically find a peer with compute. Manual endpoint configuration (above) is the primary way users share GPU resources across devices and is already fully supported.

---

## 13. Files that matter

**New:**
- `haloysius/memory_v2/peer_backend.py` (or similar) — `PeerMemoryBackend` for Haloysius `PersonaMemoryStore`
- `halbert_core/halbert_core/agents/peer_conversation_store.py` (new) — thin data-access proxy for `SqliteConversationStore` (shared message history, NOT full ThreadManager proxy)
- `halbert_core/halbert_core/agents/peer_tool_proxy.py` (new) — cross-node tool proxy (HA agent → workstation MCP server)
- `halbert_core/halbert_core/dashboard/routes/memory.py` (new or extend) — memory API endpoint on the HA server (calls `smart_add()`, not raw insert)
- `halbert_core/halbert_core/dashboard/routes/conversations.py` (new or extend) — conversation data API endpoint on the HA server (thin CRUD proxy for `SqliteConversationStore`)
- `halbert_core/halbert_core/federation/connectivity.py` (new) — internet connectivity detection probe
- `halbert_core/halbert_core/federation/wake_on_lan.py` (new) — WoL magic packet sender (LAN-only)

**Modified:**
- `halbert_core/halbert_core/integrations/cognition_wiring.py` — `_create_memory_adapter()` picks `PeerMemoryBackend` when `canonical_memory_url` is set; thread store picks `PeerConversationStore` when `canonical_thread_url` is set
- `halbert_core/halbert_core/config/being_config.py` — add `canonical_memory_url`, `canonical_thread_url`, `body_name` fields
- `halbert_core/halbert_core/federation/compute_router.py` — re-order fallback chain: cloud primary, local model second, peer third, template fourth (degraded), no-AI last. Add internet connectivity probe.
- `halbert_core/halbert_core/federation/peers_config.py` — support HA-server-as-issuer direction; add `wake_on_lan` per-peer config
- `halbert_core/halbert_core/agents/state_machine.py` — add "route to peer" step for tool calls that need workstation capabilities

**Already correct (no changes):**
- `halbert_core/halbert_core/integrations/cognition_wiring.py` — `_get_persona_id()` already reads `being.yml` `persona_id_override`
- `halbert_core/halbert_core/config/being_config.py` — `VALID_VARIANTS`, variant gating
- `halbert_core/halbert_core/dashboard/app.py` — per-variant service skips
- `halbert_core/halbert_core/federation/peer_middleware.py` — bearer auth (reused as-is)
- `halbert_core/halbert_core/federation/compute_endpoint.py` — compute endpoint (reused for the offline-fallback direction)

---

## 14. Implementation order

See `IMPL-PLAN-SINGULAR-ENTITY-2026-08-31.md` for the detailed phased implementation plan.

Summary:
1. **P1 — Config foundation** — `entity_mode`, `body_name`, `canonical_memory_url`, `canonical_thread_url` fields. Zero behavior change.
2. **P2 — `PeerMemoryBackend`** (keystone) — makes singular mode real.
3. **P3 — Thread continuity** — shared message history via `PeerConversationStore`.
4. **P4 — Compute fallback direction** — cloud primary, peer secondary (offline only). Includes internet connectivity detection.
5. **P5 — Cross-node tool proxy** — HA server's agent can call workstation tools via peer link.
6. **P6 — Wake-on-LAN** — HA server can wake a sleeping workstation for compute fallback. LAN-only.
7. **P7 — Setup/pairing UI** — users don't hand-edit YAML.

P1+P2 alone deliver the core singular-entity experience.

---

## 15. Marketing / product framing

This is NOT "federated" or "multi-node" in user-facing language. The node-based architecture is the implementation; the product is one entity.

- **User-facing language:** "Halbert lives in your home. Your powerful computer is part of him; your home-automation hub is another part. He's the same Halbert at the desk and in the kitchen."
- **Setup flow:** "Add this Mac as part of Halbert" (pairing). Not "configure a peer node."
- **The node option stays available** for power users who genuinely want two separate AIs (rare). It's an advanced config, not the default story.

The `HANDOFF-MARKETING-WEBSITE-UPDATE-2026-08-31.md` "One Halbert, many bodies" messaging option (Q1 option A) is the correct product framing for this architecture. This handoff makes that framing technically true.

---

## 16. Wake-on-LAN (optional, default off)

**Use case:** The HA server needs compute fallback (no internet), the workstation is asleep. Instead of falling back to "no AI," the HA server sends a Wake-on-LAN magic packet to the workstation, waits for it to come up, then offloads.

- **Mac:** easy — `pmset wakeonnetaccess` or the HA server sends a `wakeonlan <mac>` magic packet. Macs reliably wake on network access when configured.
- **Linux:** depends on motherboard BIOS WoL support + `ethtool -s eth0 wol g`. Some motherboards (the user noted theirs is challenging) don't support WoL reliably. This is a per-device capability, not a guarantee.
- **Implementation:** per-peer config in `peers.json` with `wake_on_lan: { enabled: false, mac_address: null, broadcast_address: null }`. Default off — it's surprising to have your Mac wake at 3am.
- **Flow:** the HA server's `ComputeRouter`, before declaring "no AI," checks if any paired workstation has WoL enabled. If so, sends the magic packet, waits with a timeout (e.g. 90s), then retries the peer health probe. If the workstation comes up, offload proceeds. If not, falls through to "no AI."
- **Constraints:** WoL magic packets are broadcast on the local subnet. **WoL works on the same physical LAN only.** Tailscale creates point-to-point encrypted tunnels with no broadcast domain — WoL does NOT work over Tailscale. We are local-network-oriented by design; Tailscale is scoped for later research as a remote-access feature, not a local pairing mechanism. If the user needs remote access, that's a separate scope.
- **Settings UI:** per-peer toggle ("Allow Halbert to wake this device for compute") + MAC address field. Only shown when the peer is a workstation variant.

**Where it lives:** `federation/compute_router.py` — a pre-fallback step in the routing chain. `federation/peers_config.py` — WoL config fields. Settings UI — per-peer toggle.

---

## 17. Multi-workstation compute sharing (research needed)

**Scenario:** A user has a Mac + a Linux workstation + an HA server. Can the HA server offload to either workstation? Can workstations offload to each other?

This is a separate scope of work from the singular-entity implementation. The singular-entity plan assumes 1 HA + 1 workstation (the common case). Multi-workstation is a follow-on that needs research.

**Questions for research (see `RESEARCH-MULTI-WORKSTATION-COMPUTE-2026-08-31.md`):**
- Can the `ComputeRouter` support multiple peer endpoints with health probes and a selection strategy (round-robin, least-latency, first-available)?
- Can workstations offload to each other (Mac → Linux, Linux → Mac), or only HA → workstation?
- How does mDNS discovery work with 3+ nodes? The current scaffold assumes 1:1 pairing.
- Does the `ComputeBroker` on each workstation need to become multi-peer aware (accept requests from multiple satellites, track which peer is sending)?
- In singular mode, does the memory/thread canonical host change? (No — still the HA server, always on. Both workstations proxy to it.)
- What happens when both workstations are awake — does the HA server load-balance, or prefer one? User-configurable?

**What does NOT change with multi-workstation:**
- Singular entity mode: still one `persona_id`, one memory store (HA server), one thread registry (HA server). Both workstations are bodies of the same entity.
- Independent entity mode: each workstation has its own `persona_id`. Compute sharing is separate from identity.

---

## 18. Open questions

1. **Memory write buffering on the workstation when HA server is rebooting.** Does the workstation buffer writes locally and flush on reconnect, or does it fail gracefully and accept the gap? Buffering is nicer but introduces a temporary local store that must be reconciled. Recommend: fail gracefully for v1, buffer for v2.
2. **Thread ownership when both nodes are up.** If a user starts a voice conversation on the HA server and a chat on the workstation simultaneously, do they share a thread or get separate threads? Recommend: separate threads by default (one per session), with an explicit "continue from [other device]" affordance. The canonical `ThreadManager` handles both.
3. **Workstation cognition when HA server is down.** The workstation's `PersonaCognition` can still run (it has its own process), but its memory reads/writes will fail. Does it fall back to a local read-only cache, or does cognition pause? Recommend: local read-only cache of last-known memory for reads, writes fail gracefully (logged but not lost if buffering is implemented in v2). Cognition continues against the stale cache — degraded but not dead.
4. **Should the workstation also stream its perception to the HA server's cognition in real-time, or only write to shared memory?** Streaming to cognition (via a remote secondary mapper) would let the HA server's cognition react to workstation events in real-time ("my workstation's CPU is hot"). Writing to memory only means the entity knows about it retroactively. Recommend: memory-only for v1 (simpler), real-time perception streaming for v2.
5. **Body name in prompt builder.** How exactly should `body_name` appear in the system prompt? "You are currently speaking from your desk body" vs "You are at your desk" vs "You are speaking from the workstation." Needs prompt engineering + testing to find the phrasing that makes the entity feel embodied without being clunky. Recommend: "You are currently at your [body_name]" — simple, natural.
6. **WoL timeout.** How long should the HA server wait after sending a WoL packet before giving up? Macs wake in ~5-15s; Linux varies. Recommend: 90s default, user-configurable per peer.
7. **Multi-workstation priority.** If the user has a Mac + Linux and both are awake, which does the HA server prefer for compute fallback? Recommend: user-configurable priority order in `peers.json`, default = first-paired-first.
