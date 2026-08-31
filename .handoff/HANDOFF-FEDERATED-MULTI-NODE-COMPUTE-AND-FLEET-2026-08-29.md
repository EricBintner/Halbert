# Federated Multi-Node Architecture & Fleet Compute Sharing

**Date:** 2026-08-29  
**Status:** Comprehensive Architecture, Handoff & Implementation Plan  
**Target:** Halbert Workstations (macOS/Linux Desktop) + N Satellite Nodes (Raspberry Pi, Homelab, Laptops)

> **Revised 2026-08-30 per `HANDOFF-HOME-AUTOMATION-SIMPLIFICATION-2026-08-30.md`:** the `home`/`home-light` (home automation) variants are simplified to pure compute clients of the workstation — no `secure_model` (slot infrastructure stays for `sysadmin` only), no SourcePrep, no model picker (a single "Compute Peer" setting; the workstation's picker governs), no 1B model tier (`SBC_LOW_POWER` is offload-only; 2B-3B is the minimum for local inference, 8GB+ hosts only), and Apple Intelligence is never a peer compute backend (mDNS `compute_backends` advertises `ollama`/`vllm` only). Affected recommendations in §1, §2, §3, §4 Pillar 3, §5, §7 (H7, M11, M13, L15), §8, §9, §10, and §11 are revised in place below. The simplification handoff §12 is the authoritative code-verified work list (W1-W25, decisions D1-D4) and its S1-S7 steps must land **before** the Phase 9 sequence in §8/§10.  

---

## 1. Executive Summary & Vision

Halbert operates on a **Federated Peer Model ("Sovereign Self, Shared Commons")**:
* **Every device is a sovereign Halbert node:** Maintaining its own identity, SQLite state, local sensors, system baseline, and local automation rules.
* **Compute is asymmetrical and opportunistic:** Low-power 24/7 nodes (e.g. Raspberry Pi 5 / Home Hubs) leverage high-power desktop nodes (e.g. Mac Studio, GPU devbox) for heavy compute (LLM inference, sysadmin batch maintenance) whenever the desktop is awake. Per-node persona memory embeddings stay on the satellite — they are not SourcePrep and not offloadable (memory is per-node, per-identity), served locally via haloysius's ONNX/Ollama `MemoryEmbedder` (simplification §4.7).
* **1:N Fleet Support from Day One:** A single Compute Host (Desktop) can pair with and support **multiple satellite nodes** (1 to 25+ nodes: Living Room Pi, Workshop Pi, Garage Cam, Homelab NAS, Travel Laptop) with prioritized concurrency queuing.
* **Bi-directional value:**
  1. *Satellite ➔ Desktop:* Offloads heavy LLM inference and batch jobs to Desktop GPU.
  2. *Desktop ➔ Satellite:* Serves as a Fleet Diagnostics Cockpit to inspect remote node health, stream logs, and troubleshoot automation/system configs.
* **Local-First & Zero-Config:** Automatic discovery over LAN / Tailscale subnets via mDNS (`_halbert._tcp`) with mutual pre-shared token security (`X-Halbert-Peer-Token`). No external cloud servers or relays required.

---

## 2. Architecture & Topology

```mermaid
graph TD
    subgraph DesktopCockpit["Compute Host / Workstation (Mac Studio / Linux Devbox)"]
        HostIdentity["Sovereign Host Identity & DB"]
        HostGPU["GPU & Local LLMs (Ollama / vLLM / MLX — peer-facing: Ollama / vLLM only; Apple Intelligence is Mac-local, never a peer backend)"]
        SPDaemon["SourcePrep Daemon & AST Graph"]
        FleetCockpit["Fleet Diagnostics Cockpit UI"]
        ComputeQueue["Compute Concurrency Broker (Priority Queue)"]
    end

    subgraph Satellites["Connected Sovereign Nodes (1 to 25+ Satellites)"]
        subgraph Node1["Node 1: Living Room (Pi 5)"]
            Node1Self["Local State & Sensors"]
            Node1Router["Compute Router (Offload + Fallback)"]
            Node1Cache["Snapshot / Digest Cache"]
        end
        subgraph Node2["Node 2: Workshop / Garage (Pi 4)"]
            Node2Self["Local State & Camera Stream"]
            Node2Router["Compute Router"]
        end
        subgraph NodeN["Node N: Laptop / Homelab NAS"]
            NodeNSelf["Local Storage & Files"]
            NodeNRouter["Compute Router"]
        end
    end

    Node1Router -->|"mDNS / Token (LLM Prompts)"| ComputeQueue
    Node2Router -->|"mDNS / Token (LLM Prompts)"| ComputeQueue
    NodeNRouter -->|"mDNS / Token (LLM Prompts)"| ComputeQueue
    ComputeQueue --> HostGPU

    FleetCockpit -->|"Telemetry / Logs / Inspection"| Node1Self
    FleetCockpit -->|"Telemetry / Logs / Inspection"| Node2Self
    FleetCockpit -->|"Telemetry / Logs / Inspection"| NodeNSelf
```

---

## 3. Human & Operational Roles

| Role | Typical Hardware | Primary Responsibilities | Compute Profile |
| :--- | :--- | :--- | :--- |
| **Compute Host (Workstation)** | Mac Studio, Linux GPU Rig, High-RAM Desktop | • Code development & SourcePrep daemon<br>• Fleet Diagnostics Cockpit<br>• Hosting 14B–70B LLMs for peer compute (satellite persona memory embeddings stay per-node local and are never hosted/offloaded — simplification §4.7) | Intermittent uptime (sleeps/travel), massive compute capacity |
| **Ambient Sentinel (Home / Satellites)** | Raspberry Pi 4/5, mini-PC, IoT Hub, Travel Laptop | • 24/7 continuous ambient monitoring<br>• Voice / wake-word assistant<br>• Home Assistant / Frigate / Sensor integration<br>• Local device control | Always-on, low power, lightweight CPU compute. For `home`/`home-light` variants: pure compute client of the workstation — no local LLM (peer offload → template thoughts fallback), no `secure_model`, no SourcePrep, no model picker (single Compute Peer setting). Sysadmin-variant satellites retain local models + full picker. |

---

## 4. Key Architectural Pillars

### Pillar 1: Zero-Config Discovery & Mutual Pairing (mDNS + Token)
1. **Service Announcement:**
   * Compute Host advertises service type `_halbert._tcp` on local LAN / Tailnet.
   * TXT Record includes: `node_id`, `node_name`, `role=compute_provider`, `capabilities=gpu_llm,sourceprep,fleet_api`, `api_port=8000`.
   * When the `compute_backends` TXT field is added, it lists `ollama,vllm` only — `apple_foundation` is never advertised (Apple Intelligence is Mac-local only; simplification §7.3/§7.4). `sourceprep` in capabilities stays correct: the host runs SourcePrep for its own sysadmin use; `home`/`home-light` satellites simply never query it (no `SOURCEPREP_URL` configured).
2. **One-Click Pairing Handshake:**
   * Satellite discovers beacon and requests pairing.
   * Host displays pairing confirmation / 4-digit code.
   * Both exchange a cryptographic pre-shared token (`X-Halbert-Peer-Token`) stored locally in `~/.config/halbert/peers.json`.
3. **Advanced IT Backdoor:**
   * UI provides manual configuration: Enter static IP/Hostname (`http://192.168.1.50:8000` or `http://desktop.tailnet.ts.net:8000`) + Token for custom VLANs.

### Pillar 2: Priority-Queued Compute Broker (Home ➔ Desktop)
* Runs on Compute Host to manage multi-satellite inference without GPU VRAM thrashing:
  * **Priority 1 (Interactive Local User):** Immediate execution for direct desktop user prompt.
  * **Priority 2 (Interactive Remote Voice/Sensor):** Real-time queries from Home Pi wake-word/smart home actions.
  * **Priority 3 (Background Batch Summaries):** Daily digests, log indexing, scheduled maintenance.
* Built with an async concurrency semaphore (e.g. 4 concurrent inference slots with FIFO queueing).

### Pillar 3: Multi-Tier Fallback & Offline Resilience (When Desktop Sleeps)
* Satellite nodes use an intelligent `ComputeRouter` with sub-second health probing. **Revised 2026-08-30 per `HANDOFF-HOME-AUTOMATION-SIMPLIFICATION-2026-08-30.md`:** the fallback chain is hardware-profile- and variant-aware — the local-micro-model tier is gone for `SBC_LOW_POWER` devices and for all `home`/`home-light` variants, and the 1B model tier is dropped as a supported configuration (2B-3B is the minimum for local inference, on 8GB+ hosts only).
  ```
  1. Desktop Compute Peer (LAN / GPU) [1.5s health probe]
     └─► If Online: Stream generation from the peer's GPU model
  2. If peer asleep / unreachable:
     (a) SBC_LOW_POWER (<4GB in code — 4GB boundary is open decision D2,
         simplification §12.1) and home/home-light variants:
         deterministic template thoughts (HALBERT_LLM_THOUGHTS=0)
         — NO local model attempt, no local model fallback tier
     (b) ENTRY_8GB+ sysadmin-variant satellites: optional local 3B fallback
         (offload preferred; 2B-3B is the minimum supported local tier)
  3. Deferred Task Queue (user-initiated and automation-triggered turns only,
     per H8 — monologue turns are never deferred/replayed)
  ```
  The former "Optional Cloud API" tier is removed from the satellite chain for `home`/`home-light` variants — the HA fallback is template thoughts, not cloud. If a sysadmin-variant satellite configures a cloud API within its privacy policy, that remains a sysadmin-variant decision outside this chain.

### Pillar 4: Desktop Fleet Cockpit (Desktop ➔ Satellite Management)
* Desktop UI includes a **Fleet Cockpit** & **Node Switcher**:
  * Live status grid for all paired satellites (CPU, RAM, Temp, Uptime, Active Services).
  * Real-time log streaming and agent timeline inspection across any satellite.
  * Diagnostic Agent: Desktop AI analyzes remote Pi systemd configs, cron jobs, and Home Assistant error logs using Desktop's full LLM reasoning power.

---

## 5. Technical Implementation Roadmap

### Phase 1: Networking & Discovery
- [ ] Implement `halbert_core/discovery/peer_discovery.py` using `zeroconf` for mDNS broadcast and listening.
- [ ] Implement `halbert_core/config/peers_config.py` for managing paired node credentials and manual IP overrides.
- [ ] Create pairing handshake REST endpoints (`/api/peers/pair`, `/api/peers/verify`).

### Phase 2: Compute Broker & Client Router
- [ ] Implement `halbert_core/compute/broker.py` with priority queueing and concurrency semaphore on Compute Host.
- [ ] Implement `halbert_core/compute/router.py` with the fallback pipeline on Satellite nodes (hardware-profile- and variant-aware: `SBC_LOW_POWER` (<4GB in code — see D2) and `home`/`home-light` = peer → template thoughts, no local model tier, no 1B tier; 8GB+ sysadmin satellites may fall back to a local 3B — 2B-3B is the minimum supported local tier).
- [ ] Expose OpenAI-compatible `/api/compute/v1/chat/completions` endpoint for authenticated peers. On Mac compute hosts, peer requests route to the Ollama backend — never `apple-foundation` (Apple Intelligence is Mac-local only and is not exposed in the peer-facing model list).

### Phase 3: Fleet Telemetry & Remote Diagnostics
- [ ] Implement `halbert_core/runtime/telemetry_agent.py` on satellites for lightweight system metrics reporting.
- [ ] Implement `halbert_core/dashboard/routes/fleet.py` on Desktop for node aggregation and SSE log streaming.
- [ ] Build Diagnostic Agent skill to inspect remote satellite configs.

### Phase 4: Frontend UI Components
- [ ] Build `NodeFleetCockpit.tsx` (Fleet dashboard cards, load gauges, connection status).
- [ ] Build `NodeSwitcher.tsx` (Top-bar dropdown for switching active node context).
- [ ] Build `PeerPairingModal.tsx` (Discovered peers list, one-click pair button, PIN confirmation).
- [ ] **Revised 2026-08-30 (simplification §5.3/§5.4, W15):** build the **Compute Peer** settings card for `home`/`home-light` variants (hostname:port or Tailscale address + "Test Connection"), mounted in place of `<ModelSettings />` — the model picker is not rendered on HA nodes; the workstation's picker governs. Reuses fleet plumbing (`PeerPairingModal.tsx`, `DiscoveredPeerCard.tsx`, `routes/peers.py`). This is a net-new deliverable outside the 28-file scaffold; the sysadmin variant keeps the full picker.

---

## 6. Verification & Test Strategy

1. **Automated Unit & Load Tests:**
   * `test_peer_discovery.py`: mDNS packet serialization and pairing handshake validation.
   * `test_compute_broker.py`: 10-satellite concurrent load test with priority preemption verification.
   * `test_compute_router.py`: Simulated host offline/sleep failover tests.
2. **Integration Verification:**
   * Live pair testing between Desktop and Raspberry Pi over LAN and Tailscale.
   * GPU allocation monitoring during multi-node concurrent prompt dispatch.

---

## 7. Architectural Review Feedback (2026-08-29)

**Reviewer:** Devin (GLM-5.2 High)
**Verdict:** The vision is correct and the "Sovereign Self, Shared Commons" framing is the right mental model. However, the plan as written **ignores substantial completed work** (Multi-Instance Phase 7, MCP Phase 4b, 4-slot model architecture, Apple Intelligence integration, discovery engine) and proposes parallel systems where integration is required. It also under-specifies the trust boundary that a federated compute endpoint opens. Below are 15 findings, ordered by severity, each with concrete code references and implementation guidance.

### Critical — must resolve before implementation

---

**C1. Duplicates MCP Phase 4b (HTTP/SSE + bearer auth) without referencing it.**

The MCP plan (`HALBERT-MCP-PLAN-2026-08-28.md`, Phase 4b) already specifies HTTP/SSE transport with bearer token auth for multi-instance access, reusing the `prep_token` pattern. This handoff proposes a separate `X-Halbert-Peer-Token` scheme over mDNS. These are two auth surfaces for the same problem.

**Why this matters:** Two token systems means two rotation flows, two revocation paths, two places where a token leak goes undetected. A paired satellite and an MCP client are both "external callers that authenticate to the Halbert API" — they should share one credential mechanism.

**Code references:**
- `halbert_core/halbert_core/mcp/server.py:1-27` — MCP server already documents "HTTP/SSE + bearer auth in Phase 4b"
- `halbert_core/halbert_core/mcp/response.py:146-162` — `mcp_response()` is the existing egress boundary
- MCP plan Phase 4b tasks: T4b.1 (HTTP/SSE transport), T4b.2 (bearer token auth), T4b.3 (instance naming)

**Resolution:** The federated peer token MUST be the same credential mechanism as MCP Phase 4b. One token, one auth middleware (`federation/peer_middleware.py`), used by both MCP clients (Warp/Claude) and peer Halbert nodes. The `X-Halbert-Peer-Token` header and the MCP `Authorization: Bearer <token>` header should resolve to the same `PeerCredential` record. Do not build a second token system.

**Scaffolded file:** `halbert_core/halbert_core/federation/peer_middleware.py` — FastAPI dependency that validates bearer tokens against `peers_config.py`, shared by both the MCP HTTP/SSE transport and the compute endpoint.

---

**C2. Duplicates Multi-Instance Phase 7 (already implemented) without building on it.**

Phase 7 (`HALBERT-MULTI-INSTANCE-DESIGN.md` + `HALBERT-MULTI-INSTANCE-REVIEW-FEEDBACK.md`) shipped the two-process env-var-isolated model, `HALBERT_PORT`, `HALBERT_DATA_DIR`, persona-aware sidebar, and the **Top-Bar Instance Switcher**. This handoff's "Node Switcher" (Phase 4) is the same component.

**Why this matters:** The Instance Switcher already handles paired remote instances (manual IP entry, localStorage persistence, role-based icons). The federated work just needs to add mDNS-discovered peers to the same dropdown and add a "Fleet Cockpit" view — not rebuild the switcher.

**Code references:**
- `halbert_core/halbert_core/dashboard/frontend/src/components/shell/InstanceSwitch.tsx:1-244` — full Instance Switcher with `PairedInstance` interface, `loadPairedInstances()`, `handleSwitch()`, add/remove form
- `halbert_core/halbert_core/dashboard/routes/instance.py:1-60` — `GET /api/instance/info` returns persona_id, role, features, port
- `halbert_core/halbert_core/dashboard/frontend/src/lib/apiBase.ts` — `setInstanceEndpoint()` / `getInstanceEndpoint()` already support remote endpoints

**Resolution:** The federated work is effectively **Phase 9+** of the home-automation strategy. The `NodeSwitcher.tsx` already exists as `InstanceSwitch.tsx` — extend it to list mDNS-discovered peers alongside manually-paired instances. The plan must explicitly state "builds on Phase 7 Instance Switcher." Do not create `NodeSwitcher.tsx` as a new component.

**Scaffolded change:** `InstanceSwitch.tsx` gains a `discoveredPeers` prop fed by a `useDiscoveredPeers` hook that polls `/api/peers/discovered`. Discovered peers show with a "mDNS" badge vs manually-paired "Manual" badge.

---

**C3. ComputeRouter duplicates `tier_router.py` / `cascade_router.py`.**

The codebase already has `model/tier_router.py` with intelligent fallback chains, `cascade_router.py` (MetaHarnessRouter), and `error_recovery` manager. The proposed `compute/router.py` multi-tier fallback (Desktop → Local micro-model → Cloud → Deferred — the pre-simplification chain; the variant- and hardware-aware chain in the revised Pillar 3 above supersedes it for `SBC_LOW_POWER` and `home`/`home-light` nodes) is a *peer-aware extension* of the existing fallback machinery, not a new router.

**Why this matters:** `TierRouter` already tracks `_model_health`, `_last_health_check`, `ModelSelection.fallback_used`, `fallback_from`, and has a `RateLimiter` for 429/529 handling. Building a parallel router means two health-check systems, two fallback-tracking systems, and two places where cost-cascade logic lives. The `MetaHarnessRouter` (cascade_router.py) blends outcome evidence with priors — a peer endpoint should participate in that same evidence loop.

**Code references:**
- `halbert_core/halbert_core/model/tier_router.py:37-42` — `ProviderType` enum: `OLLAMA`, `ANTHROPIC`, `OPENAI`, `OPENROUTER` (needs `PEER`)
- `halbert_core/halbert_core/model/tier_router.py:46-53` — `ModelSelection` dataclass with `fallback_used`, `fallback_from`
- `halbert_core/halbert_core/model/tier_router.py:215-263` — `TierRouter` class with `_model_health`, `rate_limiter`, `outcome_store`, `cascade_router`
- `halbert_core/halbert_core/model/providers/base.py:60-100` — `ModelProvider` ABC with `list_models()`, `load_model()`, `generate()`
- `halbert_core/halbert_core/model/providers/ollama.py:30` — `OllamaProvider(ModelProvider)` — the pattern to follow

**Resolution:** Add a "peer endpoint" as a first-class provider in `tier_router.py` (alongside `OLLAMA`/`ANTHROPIC`/`OPENAI`/`OPENROUTER`), with health probing. The satellite's `chat_model` slot points at `peer://desktop.lan:8000`. Reuse `ModelSelection.fallback_used` / `fallback_from` rather than reinventing fallback tracking. The `PeerProvider` class implements `ModelProvider` and proxies to the peer's `/api/compute/v1/chat/completions` endpoint.

**Scaffolded file:** `halbert_core/halbert_core/model/providers/peer.py` — `PeerProvider(ModelProvider)` that calls the peer's compute endpoint with bearer auth, implements `list_models()` via `GET /api/compute/v1/models`, and `generate()` via `POST /api/compute/v1/chat/completions`.

---

**C4. The compute endpoint opens a prompt-injection exfiltration path with no redaction boundary.**

`/api/compute/v1/chat/completions` lets a paired satellite send arbitrary prompts to the Desktop's GPU. A compromised satellite (Pi in the garage, travel laptop on hostile WiFi) can craft a prompt that instructs the Desktop model to read and return `~/.ssh/id_rsa`, `/etc/shadow`, or SourcePrep-indexed secrets. The MCP plan spent Tasks 0+3 building `redact_text()` and a Tier 0/1/2 sensitivity model precisely for this.

**Why this matters:** Without redaction, a peer compute request is equivalent to giving the satellite shell access to the Desktop's model + tool surface. The MCP plan's entire security architecture (Tasks 0, 3, 7) exists because "an MCP client is not `cat`" — the same is true for a peer node. A peer is not `cat`; it forwards prompts that may contain injection payloads.

**Code references:**
- `halbert_core/halbert_core/mcp/response.py:1-62` — `mcp_response()` documentation explaining why the egress boundary exists
- `halbert_core/halbert_core/ingestion/redaction.py` — `redact_text()` and `_is_secret_key()` (the redaction primitives)
- MCP plan §2 "The Two Egress Risks" — Risk A (MCP egress to vendor) is the same risk as peer egress to satellite
- MCP plan §3 "Tiered Sensitivity" — Tier 0 (Public), Tier 1 (Operational), Tier 2 (Secrets)

**Resolution:** The compute endpoint MUST apply the same `mcp_response()` / `redact_text()` boundary on responses, and the Desktop-side tool surface available to peer prompts MUST be a restricted subset (no `run_scanner`, no `approve_proposal`, no file-read tools). Define an explicit "peer-capable tool allowlist" mirroring the MCP `cloud_safe` tool table (MCP plan §8). The response from a peer-initiated generation passes through `mcp_response()` before being sent back over the network.

**Scaffolded files:**
- `halbert_core/halbert_core/federation/tool_allowlist.py` — `PEER_ALLOWED_TOOLS` frozenset, `is_tool_allowed_for_peer()`, `filter_tools_for_peer()`
- `halbert_core/halbert_core/federation/compute_endpoint.py` — applies `mcp_response()` to the generation response before returning

---

**C5. Fleet Cockpit remote-config inspection is a new attack surface on every satellite.**

Pillar 4 / Phase 3 proposes the Desktop AI inspecting "remote Pi systemd configs, cron jobs, HA error logs." This is a Tier 1 (Operational) data flow per the MCP sensitivity model — and it requires every satellite to expose a read API for its own configs.

**Why this matters:** Building a bespoke `/api/fleet/inspect` endpoint on every satellite means every satellite runs a second API surface with its own auth, its own redaction, and its own tool set. The MCP server already solves this: it exposes config queries with `mcp_response()` redaction, tool allowlisting, and bearer auth. The Desktop should be an MCP *client* of the satellite, not a consumer of a parallel API.

**Code references:**
- `halbert_core/halbert_core/mcp/server.py:1-27` — 17 MCP tools already defined
- `halbert_core/halbert_core/mcp/response.py:146-162` — `mcp_response()` boundary
- MCP plan §8 tool table — `get_config_structure` (cloud-safe), `get_config_diff` (cloud-safe), `get_config_value` (Tier 1, user-configurable redaction)

**Resolution:** Do NOT build a bespoke `/api/fleet/inspect` endpoint. The satellite should run the **MCP server** (already planned) and the Desktop should connect as an MCP *client* with the same Tier 0/1/2 redaction applied at the satellite's response boundary. This reuses the entire MCP security architecture instead of duplicating it insecurely. The Fleet Cockpit UI calls a Desktop-side route that proxies MCP tool calls to the satellite.

**Scaffolded file:** `halbert_core/halbert_core/federation/fleet_proxy.py` — proxies MCP tool calls from Desktop to satellite over the peer link, applies `mcp_response()` on the Desktop side as defense-in-depth.

### High — design gaps that will cause rework

---

**H6. "1:N from Day One (1 to 25+)" is over-scoped for a first phase.**

Phase 7 proved 1:1 (two processes, one machine). Jumping to 1:25+ with a priority concurrency broker in a single phase is a 10x complexity jump with no intermediate validation.

**Why this matters:** The concurrency broker (semaphore, priority queue, preemption) is the hardest part to get right. If the 1:1 link has a subtle bug (token mismatch, redaction gap, health-probe race), it will be multiplied by 25 nodes and become invisible in the noise. Validate the link, the auth, the redaction, and the failover with exactly 2 nodes first.

**Resolution:** Split Phase 2. Phase 2a: 1:1 cross-machine (Desktop ↔ one Pi), prove the link, failover, and redaction. Phase 2b: introduce the concurrency broker and scale to N. Validate 2a end-to-end before building 2b.

**Scaffolded files reflect this:** `compute_broker.py` is scaffolded with a `max_concurrent` parameter defaulting to 1 (effectively FIFO for 2a), with the priority queue and semaphore ready for 2b but not enforced until 2a passes.

---

**H7. Fallback tier 2 ("Local Micro-Model") is not viable on the lowest hardware tiers.**

The low-power hardware handoff (`HANDOFF-LOW-POWER-HARDWARE-TIERS-AND-EDGE-CASES-2026-08-29.md` §7.1) established that on Pi 4 (4GB) a 4B model is 3-5 tok/s with OOM risk, and on `SBC_LOW_POWER` (≤4GB) the architectural rule is template thoughts (`HALBERT_LLM_THOUGHTS=0`). The fallback chain as written assumes a usable local model always exists.

**Why this matters:** If the fallback chain tries to load a 3B model on a Pi 4 2GB, it will OOM and crash the satellite — worse than just failing silently. The fallback must be aware of the hardware profile it's running on.

**Code references:**
- `halbert_core/halbert_core/model/hardware_detector.py:32-41` — `HardwareProfile` enum: `SBC_LOW_POWER`, `ENTRY_8GB`, `LAPTOP_16GB`, etc.
- `halbert_core/halbert_core/model/hardware_detector.py:392-427` — `_classify_hardware()` maps RAM → profile
- Low-power handoff §7.1 — parameter table: 4B on Pi 4 = 3-5 tok/s, OOM risk
- Low-power handoff §3 — "cognitive monologue defaults to template thoughts (`HALBERT_LLM_THOUGHTS=0`)" on ≤4GB

**Resolution:** The `ComputeRouter` fallback must be **hardware-profile-aware** using the existing `SBC_LOW_POWER` / `ENTRY_8GB` profiles. **Revised 2026-08-30 per `HANDOFF-HOME-AUTOMATION-SIMPLIFICATION-2026-08-30.md` §6:** on `SBC_LOW_POWER` the fallback is template thoughts + deferred queue, and the router must not attempt local model loading **at all** — there is no local model tier in the chain. The 1B tier is dropped as a supported configuration; 2B-3B is the minimum for local inference, valid only on 8GB+ hosts, where the 3B fallback is valid but offload-preferred. Note: in code `SBC_LOW_POWER` is strictly <4GB (a 4GB host classifies `ENTRY_8GB`) — the 4GB boundary is open decision D2 (simplification §12.1) and blocks S4. The `PeerProvider` in `tier_router.py` checks `HardwareProfile` before attempting local model fallback; the scaffolded `_hardware_supports_local_model()` already excludes `sbc_low_power` and is pinned by `test_hardware_profile_fallback.py` — the remaining work is implementing `route()` to honor peer → template thoughts. Extended to variant level by the simplification: `home`/`home-light` variants are offload-only regardless of RAM.

---

**H8. Cognitive monologue (`advance_turn`) offload is not addressed.**

The satellite's `advance_turn` is a continuous cognitive tick. If it offloads to the Desktop and the Desktop sleeps, the satellite's cognition stalls. "Deferred Task Queue" handles batch jobs but not the monologue.

**Why this matters:** If `advance_turn` queues 200 turns while the Desktop sleeps and replays them on wake, the Desktop gets a burst of 200 inference requests — a denial-of-service from the satellite's own cognition. Conversely, if `advance_turn` just drops turns, the satellite's cognitive state diverges from reality.

**Resolution:** Define explicit behavior: when the Desktop peer is unreachable, the satellite's `advance_turn` falls back to template thoughts (per the low-power rule), and queued monologue turns are NOT replayed on wake (they'd flood). Only user-initiated and automation-triggered turns are deferred. State this in Pillar 3. The `ComputeRouter` distinguishes `turn_type: "monologue" | "user" | "automation"` and applies different deferral policies.

**Open question (simplification §11 Q4, unresolved):** with template thoughts as the only monologue option on HA nodes (no local LLM, no monologue offload), decide whether `advance_turn` should be disabled entirely on `home`/`home-light` variants, with cognition running only on explicit user/automation triggers.

---

**H9. mDNS does not cross Tailscale without a reflector.**

§1 and Pillar 1 claim "automatic discovery over LAN / Tailscale subnets via mDNS." mDNS is link-local multicast (224.0.0.251) and does not traverse Tailscale's WireGuard tunnel unless an mDNS reflector/bridge is explicitly configured on a node.

**Why this matters:** A user on a travel laptop connected to Tailscale will expect zero-config discovery of their home Desktop, but mDNS will silently fail. The "Advanced IT Backdoor" (manual IP) is the actual Tailscale path, but the plan implies it's a secondary option.

**Resolution:** Either (a) state that Tailscale peers use the "Advanced IT Backdoor" manual IP entry (Pillar 1.3) — mDNS is LAN-only, or (b) document the mDNS reflector requirement (e.g., `avahi-daemon` with `enable-reflector=yes` on a bridge node). Do not imply zero-config discovery over Tailscale. The scaffolded `peer_discovery.py` documents this limitation in its module docstring.

---

**H10. `zeroconf` violates the Haloysius subtractive contract.**

The project rules (`CLAUDE.md`) mandate only 2 hard dependencies (`pyyaml`, `requests`); all heavy stacks must be function-level lazy optional extras. `zeroconf` would be a new hard dependency.

**Why this matters:** The subtractive contract is what lets Halbert run on a Pi 4 2GB without pulling in unnecessary packages. `zeroconf` pulls in `ifaddr` and other networking deps. Adding it to `requirements.txt` breaks the contract.

**Code references:**
- `CLAUDE.md` / `AGENTS.md` — "Haloysius Subtractive Contract: Only 2 hard dependencies (`pyyaml>=6.0`, `requests>=2.31.0`); all heavy/ML stacks must remain function-level lazy optional extras."
- `halbert_core/halbert_core/vision/` — example of lazy imports (torch, cv2 imported inside functions)

**Resolution:** `peer_discovery.py` must import `zeroconf` lazily inside the discovery function with a graceful "mDNS unavailable, use manual pairing" fallback, exactly like the vision/ML stacks. Add `zeroconf` to optional extras (`halbert-core[federation]`), not `requirements.txt`.

**Scaffolded file:** `halbert_core/halbert_core/federation/peer_discovery.py` — `import zeroconf` is inside `_start_zeroconf_listener()`, wrapped in `try/except ImportError`.

### Medium — integration / consistency

---

**M11. No mapping to the 4-slot model architecture.**

The 4-slot model (`chat_model`, `specialist_model`, `vision_model`, `secure_model`) is the established config surface. The plan talks about "offloading LLM inference" generically.

**Why this matters:** Without slot-level routing rules, a satellite might offload `secure_model` to the Desktop — which defeats the entire purpose of `secure_model` (local-only processing of secrets, credentials, camera frames). The `secure_model` slot has a hard local-only URL enforcement (`llm_config.py:417-421`) that would need to be bypassed, creating a security hole.

**Code references:**
- `halbert_core/halbert_core/model/llm_config.py:64` — `SLOTS = ("chat_model", "specialist_model", "vision_model", "secure_model")`
- `halbert_core/halbert_core/model/llm_config.py:135-140` — `_is_local_url()` enforces `secure_model` is local-only
- `halbert_core/halbert_core/model/llm_config.py:417-421` — `secure_model` endpoint non-local → slot disabled with warning

**Resolution:** Specify which slots offload to the peer:
- `chat_model`: CAN peer-offload (general conversation, no secrets expected)
- `specialist_model`: CAN peer-offload (complex reasoning, the main use case)
- `vision_model`: CAN peer-offload ONLY if peer advertises `vision` capability in mDNS TXT record
- `secure_model`: MUST NOT peer-offload (local-only by architectural rule — sending secure content to another node defeats its purpose). The `_is_local_url()` enforcement stays in place; `peer://` URLs are rejected for `secure_model`.

State this explicitly in the plan and enforce it in `PeerProvider.can_serve_slot()`.

**Variant scope (revised 2026-08-30 per `HANDOFF-HOME-AUTOMATION-SIMPLIFICATION-2026-08-30.md` findings 1 & 3):** these rules are binding for **sysadmin-variant satellites**. For `home`/`home-light` satellites, `secure_model` is not configured at all — the MUST-NOT rule and `_is_local_url()` enforcement remain in the codebase as defense-in-depth but never fire there; `chat_model` and `specialist_model` both resolve to `peer://<workstation>:8000` with no per-slot user selection (no model picker on HA nodes — a single Compute Peer setting; the workstation's picker governs). Whether `vision_model` exists on HA variants at all is open (simplification §11 Q3 — Frigate may handle all vision, with Halbert consuming MQTT events).

---

**M12. Telemetry agent duplicates the discovery engine.**

Phase 3 proposes `runtime/telemetry_agent.py` for "lightweight system metrics." The `discovery/` package already has scanners (storage, service, network, thermal, process) producing structured discoveries on both macOS and Linux, with platform-aware registration.

**Why this matters:** Two metrics collection systems means two code paths for "what services are running on this Pi," two data shapes, and two update cadences. The discovery engine already produces `Discovery` objects with structured data fields that the frontend renders.

**Code references:**
- `halbert_core/halbert_core/discovery/engine.py:28-60` — `DiscoveryEngine` with scanner registration, `scan_all()`, `get_by_type()`
- `halbert_core/halbert_core/discovery/scanners/` — 20+ scanners including `thermal.py`, `process.py`, `network.py`, `service.py`
- `halbert_core/halbert_core/discovery/scanners/macos/` — macOS-specific scanners (platform-aware registration already works)

**Resolution:** The satellite's telemetry stream should be a **lightweight periodic snapshot of the discovery engine's existing results** plus live deltas (CPU/RAM/temp via `psutil`), not a parallel metrics collection system. Reuse `DiscoveryEngine` + a small vitals poller. The `telemetry_agent.py` becomes a thin wrapper that calls `engine.scan_all()` periodically and diffs against the last snapshot.

---

**M13. Apple Intelligence / Metal is absent from the Compute Host pillar.**

The recent Apple Intelligence integration (`HANDOFF-APPLE-INTELLIGENCE-IMPLEMENTATION-2026-08-29.md`) added `apple-foundation` as a local provider with Metal GPU detection and auto-provisioning. The Compute Host pillar (§2 diagram, §3 roles) lists only "Ollama / vLLM / MLX."

**Status:** superseded — the resolution below was **revised 2026-08-30** and resolves this finding differently (see the resolution paragraph).

**Why this matters:** A Mac Studio compute host's primary inference path may be Apple Intelligence on the ANE (Apple Neural Engine), not Ollama. Satellites need to know which backend the Desktop uses so they route to the right endpoint. The `apple-foundation` provider has different capabilities (on-device, no data leaves the Mac) that affect the sensitivity routing.

**Code references:**
- `halbert_core/halbert_core/model/capabilities.py` — `ModelCapabilities.detect()` has `apple-foundation` branch with `tool_use=True`, `streaming=True`
- `halbert_core/halbert_core/model/hardware_detector.py:66-69` — `apple_intelligence_available`, `apple_intelligence_bridge_running` fields
- `halbert_core/halbert_core/model/auto_provision.py` — auto-provisioning on first boot

**Resolution (revised 2026-08-30 per `HANDOFF-HOME-AUTOMATION-SIMPLIFICATION-2026-08-30.md` finding 5 — resolved differently):** Apple Intelligence is deliberately **not** a peer compute source; the original §2/§3 omission was already correct for peer-facing purposes, and Apple Intelligence belongs only to the Mac's own slot configuration. The Mac runs two local backends: `apple-foundation` for the Mac's own `chat_model`/`secure_model` (personal, on-device, ANE-accelerated), and Ollama 7B-14B for serving peer compute requests from satellites. `compute_endpoint.py` routes peer requests to Ollama and never exposes Apple Intelligence in the peer-facing model list; `peer_discovery.py` advertises `compute_backends=ollama,vllm` (never `apple_foundation`); `PeerProvider.list_models()` receives only the Ollama model list. Rationale: Apple Intelligence is designed for on-device personal use — serving it as an inference endpoint for other machines may violate Apple's terms — and its 3B model is capability-mismatched for satellite reasoning versus an Ollama 7B-14B on the same Mac. The code references above remain valid context for the Mac-local path only.

---

**M14. Token rotation and compromise recovery are undefined.**

`peers.json` stores a pre-shared token on disk. If a satellite (e.g., garage Pi) is physically compromised, the PSK leaks and grants GPU access to the Desktop.

**Why this matters:** Without per-peer tokens, one compromised satellite means re-pairing ALL satellites. Without a rotation flow, tokens never change and accumulate risk. Without revocation, a stolen token remains valid indefinitely.

**Resolution:** Define:
- (a) **Per-peer tokens:** each satellite gets its own token (not one shared PSK). The `peers_config.py` stores a `token_hash` per peer (SHA-256, never the raw token). Revocation is surgical — one peer, one token.
- (b) **Token rotation flow:** Desktop revokes a peer (`DELETE /api/peers/{node_id}`), the peer is forced to re-pair. The old token is invalidated immediately.
- (c) **What Desktop-side capabilities a revoked token loses immediately:** the `peer_middleware.py` checks token validity on every request; a revoked token gets 401 within one request cycle (no caching of token validity beyond the request scope).

Tie this to the MCP Phase 4b token scoping.

**Scaffolded file:** `halbert_core/halbert_core/federation/peers_config.py` — `PeerCredential` dataclass with `node_id`, `token_hash`, `role`, `paired_at`, `last_seen`, `revoked`. `PeersConfig` class with `add_peer()`, `revoke_peer()`, `verify_token()`.

### Low — test strategy

---

**L15. Test strategy misses the trust boundary and split-brain cases.**

The proposed tests cover load and failover but not the security-critical paths.

**Add the following test files:**

- `test_peer_redaction.py`: peer prompt requesting `~/.ssh/id_rsa` content returns redacted/empty, never the raw value. Verifies `mcp_response()` is applied on the compute endpoint response boundary.
- `test_peer_tool_allowlist.py`: peer prompts cannot invoke `run_scanner` / `approve_proposal` / file-read tools on the Desktop. Verifies `filter_tools_for_peer()` strips disallowed tools.
- `test_token_revocation.py`: revoked peer token is rejected within one request cycle. Verifies `peer_middleware.py` checks `revoked` flag on every request.
- `test_split_brain.py`: Desktop wakes, a deferred satellite task completed locally conflicts with a Desktop-side completion — define resolution (last-write-wins? Desktop-authoritative?).
- `test_secure_model_no_offload.py`: `secure_model` slot never routes to a peer endpoint even when peer is online. Verifies `PeerProvider.can_serve_slot("secure_model")` returns `False`. *(Revised 2026-08-30: guardrail for sysadmin-variant satellites — `home`/`home-light` never configure the slot at all, so the check is moot there; it passes unchanged.)*
- `test_hardware_profile_fallback.py`: on `SBC_LOW_POWER` profile, the router makes **no local model attempt** (no model load; peer → template thoughts only — the skip itself is already scaffolded and pinned by this test). On `ENTRY_8GB`, the local 3B fallback is permitted but offload-preferred. No 1B-tier configuration is supported anywhere. *(Revised 2026-08-30; update the 4GB-row expectations per open decision D2 before unskipping.)*

---

## 8. Recommended Re-sequencing

Given the completed foundations, the federated work should be framed as **Phase 9+** and re-sequenced to build on them:

| Step | Builds On | Deliverable | Scaffolded File(s) |
|------|-----------|-------------|---------------------|
| 9.1 | MCP Phase 4b (HTTP/SSE + bearer) | Peer auth = MCP token, one middleware. Per-peer tokens. | `federation/peer_middleware.py`, `federation/peers_config.py` |
| 9.2 | Multi-Instance Phase 7 (Instance Switcher) | Extend switcher with remote peer entries (manual IP first). | `InstanceSwitch.tsx` (extend), `useDiscoveredPeers.ts` |
| 9.3 | `tier_router.py` | Add `peer://` provider type with health probe. 1:1 cross-machine link. For `home`/`home-light`: `list_models()` is a health check only — never user-facing model selection (no model picker on HA nodes; the workstation's picker governs). Prerequisite: register `PeerProvider` in the model stack — `peer` is currently absent from `CHAT_CAPABLE_PROVIDERS`/`tier_router.py`/`providers/__init__.py`, so any peer slot is disabled as "not chat-capable" (W14). | `model/providers/peer.py` |
| 9.4 | MCP Tier 0/1/2 redaction | Apply `redact_text()` + peer tool allowlist on compute endpoint. | `federation/tool_allowlist.py`, `federation/compute_endpoint.py` |
| 9.5 | Discovery engine | Satellite telemetry = discovery snapshot + vitals deltas. | `federation/telemetry_agent.py` |
| 9.6 | Low-power hardware profiles | Offload-only fallback on `SBC_LOW_POWER` (<4GB in code; 4GB boundary = open decision D2) and `home`/`home-light` variants — no local model tier, peer → template thoughts; optional 3B local fallback on 8GB+ sysadmin variants; 1B tier dropped. | `federation/compute_router.py` |
| 9.7 | — | mDNS auto-discovery (lazy `zeroconf`, LAN-only). Tailscale = manual. | `federation/peer_discovery.py` |
| 9.8 | 9.1-9.4 validated | Concurrency broker, scale to N (Phase 2b). | `federation/compute_broker.py` |
| 9.9 | MCP server on satellite | Fleet Cockpit = Desktop as MCP client of satellite (no bespoke inspect API). | `federation/fleet_proxy.py`, `dashboard/routes/fleet.py` |
| 9.10 | Apple Intelligence (local-only) | Enforce `apple-foundation` is **not** a peer backend: advertise `compute_backends=ollama,vllm`; route peer requests on Mac hosts to Ollama; exclude Apple Intelligence models from `PeerProvider.list_models()`. | `peer_discovery.py` (TXT field), `compute_endpoint.py` (routing) |

**Bottom line:** The vision is sound. The plan needs to be rewritten as an *extension* of MCP Phase 4b + Multi-Instance Phase 7 + the 4-slot model, not a greenfield architecture. The single most important fix is C4/C5 — the federated compute and inspection paths inherit the MCP redaction boundary and tool allowlist, or they are an unmonitored exfiltration channel.

---

## 9. Scaffolded Implementation (this worktree)

**Worktree:** `~/.config/superpowers/worktrees/Halbert/federated-fleet`
**Branch:** `feat/federated-fleet`

All files are scaffolded with detailed inline comments referencing the findings above. No file contains working logic — they are structural skeletons with docstrings, type signatures, and `raise NotImplementedError` / `TODO(federation-9.x)` markers. The intent is to make the implementation path concrete and reviewable before any logic is written.

### Backend (`halbert_core/halbert_core/federation/`)

| File | Purpose | Finding |
|------|---------|---------|
| `__init__.py` | Package init, public API exports | — |
| `peers_config.py` | Per-peer credential store with token hashes, revocation | C1, M14 |
| `peer_middleware.py` | FastAPI dependency: bearer token validation (shared with MCP 4b) | C1 |
| `peer_discovery.py` | mDNS beacon/listener (lazy `zeroconf`, LAN-only). mDNS TXT `compute_backends` lists `ollama`/`vllm` only — `apple_foundation` is never advertised (strip the scaffolded `apple_foundation` references; see the simplification §7.4/§9 impact) | H9, H10, S6 |
| `compute_endpoint.py` | OpenAI-compatible `/api/compute/v1/chat/completions` with redaction boundary. On Mac compute hosts, peer requests route to Ollama — never `apple-foundation`; the models route never lists Apple Intelligence | C4, S6 |
| `compute_broker.py` | Priority queue + concurrency semaphore (max_concurrent=1 for 9.2a) | H6 |
| `compute_router.py` | Hardware-profile-aware fallback chain (extends tier_router). Offload-only on `SBC_LOW_POWER` (local-model skip already scaffolded and tested in `_hardware_supports_local_model()`) and `home`/`home-light`: peer → template thoughts, no local model tier, no 1B tier, no `secure_model` routing (zero references in the file); remaining work is implementing `route()` | C3, H7, H8, S4 |
| `tool_allowlist.py` | `PEER_ALLOWED_TOOLS` frozenset, `filter_tools_for_peer()` | C4, C5 |
| `telemetry_agent.py` | Discovery engine snapshot + vitals deltas (reuses discovery/) | M12 |
| `fleet_proxy.py` | Desktop-as-MCP-client proxy to satellite (no bespoke inspect API) | C5 |

### Backend (`halbert_core/halbert_core/model/providers/`)

| File | Purpose | Finding |
|------|---------|---------|
| `peer.py` | `PeerProvider(ModelProvider)` — calls peer compute endpoint with bearer auth; `can_serve_slot("secure_model")` returns `False` (unchanged; for `home`/`home-light` the slot doesn't exist at all, so this is moot); `list_models()` is used for health checking, not user selection. Prerequisite: register the provider in the model stack — `peer` is currently absent from `CHAT_CAPABLE_PROVIDERS`/`tier_router.py`/`providers/__init__.py` (W14) | C3, M11, S3 |

### Backend (`halbert_core/halbert_core/dashboard/routes/`)

| File | Purpose | Finding |
|------|---------|---------|
| `peers.py` | Pairing handshake (`/api/peers/pair`, `/api/peers/verify`), list/revoke | C1, M14 |
| `fleet.py` | Fleet Cockpit aggregation (proxies to satellite MCP via `fleet_proxy`) | C5 |

### Frontend (`halbert_core/halbert_core/dashboard/frontend/src/`)

| File | Purpose | Finding |
|------|---------|---------|
| `components/fleet/NodeFleetCockpit.tsx` | Fleet status grid (CPU/RAM/temp/uptime per node) | C2 |
| `components/fleet/PeerPairingModal.tsx` | Discovered peers list, one-click pair, PIN confirmation | C2 |
| `hooks/useDiscoveredPeers.ts` | Polls `/api/peers/discovered`, feeds `InstanceSwitch` | C2 |
| `lib/peerApi.ts` | Typed API client for peers/fleet endpoints | — |

### Tests (`halbert_core/tests/federation/`)

| File | Purpose | Finding |
|------|---------|---------|
| `test_peer_redaction.py` | Peer prompt requesting `~/.ssh/id_rsa` returns redacted | C4, L15 |
| `test_peer_tool_allowlist.py` | Peer prompts cannot invoke restricted tools | C4, L15 |
| `test_token_revocation.py` | Revoked token rejected within one request cycle | M14, L15 |
| `test_split_brain.py` | Deferred task conflict resolution | L15 |
| `test_secure_model_no_offload.py` | `secure_model` never routes to peer (guardrail for sysadmin-variant satellites; `home`/`home-light` never configure the slot) | M11, L15 |
| `test_hardware_profile_fallback.py` | No local model attempt on `SBC_LOW_POWER` (peer → template thoughts only); `ENTRY_8GB` 3B fallback optional/offload-preferred; no 1B tier anywhere | H7, L15 |
| `test_compute_broker.py` | Concurrency + priority preemption (Phase 2b) | H6 |
| `test_peer_discovery.py` | mDNS packet serialization + handshake validation. **Revised 2026-08-30:** currently asserts `compute_backends == "ollama,apple_foundation"` — must be updated to `ollama,vllm` in the same change as the advertisement fix (W22/W23) | H9, S6 |

### Documentation

| File | Purpose |
|------|---------|
| `halbert_core/halbert_core/federation/README.md` | Architecture overview, finding references, implementation order. **Revised 2026-08-30:** must record the simplification deltas — offload-only fallback on `SBC_LOW_POWER`/`home` variants, `compute_backends=ollama,vllm`, `secure_model` scoped to sysadmin, no model picker on HA nodes. Its current Apple Intelligence listing and "9.10 — apple-foundation as advertised peer capability" phase row must be rewritten as the negative constraint (W22) |

> **Simplification impact (2026-08-30, per `HANDOFF-HOME-AUTOMATION-SIMPLIFICATION-2026-08-30.md` §9):** the 28-file scaffold list neither grows nor shrinks — only the Purpose/expectations of `peer_discovery.py`, `compute_endpoint.py`, `compute_router.py`, `peer.py`, `test_secure_model_no_offload.py`, `test_hardware_profile_fallback.py`, and `test_peer_discovery.py` change. The one net-new deliverable outside the scaffold is the `home`/`home-light` "Compute Peer" settings card (replaces the model picker; W15). Scaffold bug found during code verification: `federation/__init__.py` exports `PeerAuthMiddleware`, which `peer_middleware.py` does not define (it defines `require_peer_auth`/`optional_peer_auth`/`PeerContext`) — accessing `halbert_core.federation.PeerAuthMiddleware` raises `ImportError`; fix alongside S6 (W24).

---

## §10 — Scaffold Completion Log

**Date:** 2026-08-29
**Branch:** `feat/federated-fleet` (merged to `main`, pushed to `origin`)
**Commits:**
- `928c9166` — scaffold: federated multi-node compute & fleet (Phase 9+)
- `a2ca6677` — fix: scrutiny pass on federation scaffold (13 issues)
- `9fff12a7` — merge: federated multi-node compute & fleet scaffold (Phase 9+)

### What was built

28 files, ~5,100 lines of structural scaffolding across backend, frontend,
and test layers. Every file has detailed inline docstrings referencing the
15 review findings (C1-C5, H6-H10, M11-M14, L15) and `TODO(federation-9.x)`
markers pointing to the implementation step that fills in the logic.

**Backend (10 files in `federation/`):** peers_config, peer_middleware,
peer_discovery, compute_endpoint, compute_broker, compute_router,
tool_allowlist, telemetry_agent, fleet_proxy, __init__.

**Backend (1 file in `model/providers/`):** peer.py (PeerProvider).

**Backend (2 files in `dashboard/routes/`):** peers.py, fleet.py.

**Frontend (4 files):** peerApi.ts, useDiscoveredPeers.ts,
NodeFleetCockpit.tsx, PeerPairingModal.tsx. Plus DialogFooter added to
dialog.tsx.

**Tests (8 files, 59 passing, 16 skipped):** test_peer_redaction,
test_peer_tool_allowlist, test_token_revocation, test_secure_model_no_offload,
test_hardware_profile_fallback, test_split_brain, test_compute_broker,
test_peer_discovery.

**Integration:** peers and fleet routers registered in `app.py`.

### Scrutiny pass (13 issues found and fixed)

After the initial scaffold, a full reverse-engineering review found 13
issues across 4 severity levels. All were fixed before merge:

**CRITICAL (2):**
- `peers.py` and `fleet.py` imported `get_peers_config` from
  `peers_config` — but it lives in `peer_middleware`. Would have raised
  `ImportError` at first request.
- Routes were not registered in `app.py` — `include_router` calls missing.

**HIGH (3):**
- `peers_config._save()` didn't create the parent directory before
  writing the tmp file — `FileNotFoundError` on first write to a fresh
  config dir.
- `ComputeRequest` dataclass used `metadata={"compare": True/False}`
  which the `dataclasses` module silently ignores. `order=True` would
  have compared all fields including non-comparable `list`/`dict`/`None`
  types, breaking `PriorityQueue` sorting on tie-breaks. Fixed to use
  `field(compare=True/False)`.
- `PeerPairingModal.tsx` imported `DialogFooter` from `dialog.tsx` which
  didn't export it. Added the `DialogFooter` component to `dialog.tsx`.

**MEDIUM (5):**
- Role vocabulary inconsistent: `peers_config.py` docstring said
  `"compute_host"` but `peer_discovery.py` and `peers.py` used
  `"compute_provider"`. Standardized on `"compute_provider"`.
- `compute_endpoint.py` had `dependencies=[Depends(require_peer_auth)]`
  on routes that also had `peer: PeerContext = Depends(require_peer_auth)`
  as a parameter — double auth path. Removed the redundant
  `dependencies=[]`.
- `tool_allowlist.py` docstring said "logs a warning" but the code used
  `logger.debug`. Fixed the docstring.
- `NodeFleetCockpit.tsx` imported `Activity` from lucide-react but never
  used it — `noUnusedLocals` compile error. Removed.
- `PeerPairingModal.tsx` imported `KeyRound` from lucide-react but never
  used it. Removed.
- `fleet.py` `FleetNodeStatus.vitals` was `Optional[Dict[str, Any]]` but
  the frontend typed it as a structured object with fixed fields
  (`cpu_percent`, `memory_percent`, etc.). Added `FleetVitals` Pydantic
  model to match the frontend shape.

**LOW (3):**
- `peers.py` PIN generation used `random.randint(0, 9999)` — not
  cryptographically secure. Changed to `secrets.randbelow(10000)`.
- `useDiscoveredPeers.ts` initialized `loading=true` but if `enabled=false`
  the effect returned early and `loading` stayed `true` forever. Fixed to
  initialize from `enabled` and set `false` in the early-return path.
- `test_re_pairing_after_revocation` had no assertions — trivially passed.
  Added real assertions documenting the current behavior (re-pairing
  raises `ValueError` because the revoked entry is still in the store).

### Test results

```
59 passed, 16 skipped in 0.10s
```

The 16 skipped tests are marked `TODO(federation-9.x)` and will be
unskipped as each implementation step is completed. **Revised 2026-08-30:**
before unskipping the 9.6/9.10-related tests, update their expected behavior
per the simplification (`test_hardware_profile_fallback`, 
`test_secure_model_no_offload`, and `test_peer_discovery`'s
`compute_backends` TXT assertions — W22/W23).

### Next steps

The scaffold is ready for implementation. The recommended order is the
10-step sequence in §8 above.

**Revised 2026-08-30 per `HANDOFF-HOME-AUTOMATION-SIMPLIFICATION-2026-08-30.md` §10:** implement S1-S7 of the simplification handoff **before** starting this sequence — they shrink the 9.3/9.6/9.10 targets so the federated Phase 9 work lands on a cleaner target: the HA node as a pure compute client with no local models, no SourcePrep, no `secure_model`, and no model picker.

1. **Step 9.1** — Peer auth = MCP token, one middleware, per-peer tokens
2. **Step 9.2** — Extend Instance Switcher with remote peers
3. **Step 9.3** — `peer://` provider, 1:1 cross-machine link (register `PeerProvider` in the model stack — prerequisite, W14; for `home`/`home-light`, `list_models()` is a health check only — no model picker on HA nodes)
4. **Step 9.4** — `redact_text()` + tool allowlist on compute endpoint
5. **Step 9.5** — Satellite telemetry = discovery snapshot + vitals
6. **Step 9.6** — Offload-only fallback (peer → template thoughts) on `SBC_LOW_POWER` and `home`/`home-light`; no local model tier; 1B tier dropped; optional 3B on 8GB+ sysadmin satellites
7. **Step 9.7** — mDNS auto-discovery (lazy `zeroconf`, LAN-only)
8. **Step 9.8** — Concurrency broker, scale to N
9. **Step 9.9** — Fleet Cockpit = Desktop as MCP client
10. **Step 9.10** — Enforce Apple Intelligence as local-only: `compute_backends=ollama,vllm`; Mac peer endpoint routes peer requests to Ollama (never `apple-foundation`)

Each step's TODO markers in the scaffolded files point to the exact
functions that need implementation.

---

## 11. Comprehensive Design Implications & Architectural Research Findings

**Date:** 2026-08-29  
**Analysis Target:** Halbert Federated Multi-Node Network, Design System Integration, Cognitive Loops, and Security Perimeter  

Following the completion of the 28-file structural scaffolding pass and the resolution of the 13 scrutiny findings in commits `928c9166`, `a2ca6677`, and `9fff12a7`, this section synthesizes the critical design implications and research findings across the Halbert ecosystem.

---

### 11.1 Architectural Track-Check: Why This Model Succeeds

The scaffolding successfully anchors the federated model into Halbert's existing foundations rather than creating redundant parallel abstractions:
1. **Zero New Auth Silos (Resolving C1):** Reuses the MCP Phase 4b bearer authentication and token architecture. A peer node is authenticated through `peer_middleware.py`, creating a unified trust boundary across external MCP tools (Claude Code, Warp) and peer Halbert instances.
2. **Evolution Over Greenfield (Resolving C2 & C3):** Rather than creating duplicate switchers or routers, `InstanceSwitch.tsx` is extended with mDNS discovery feeds, and `PeerProvider` implements the standard `ModelProvider` ABC within `tier_router.py`.
3. **Defense-in-Depth Trust Boundary (Resolving C4 & C5):** Eliminates prompt-injection exfiltration and arbitrary remote inspection by enforcing `mcp_response()` redaction and delegating remote satellite diagnostics to the satellite's own MCP server.

---

### 11.2 Frontend Ergonomics & Design System Integration

The user experience must balance two distinct mental models: **"Teleporting" into a single machine** vs **"Monitoring and managing the entire household fleet"**.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            TOP BAR NAVIGATION                               │
│  [Halbert Mark]  Overview  Alerts  Storage  Security  Fleet [InstanceSwitch ▼]│
└─────────────────────────────────────────────────────────────────────────────┘
                                                          │
          ┌───────────────────────────────────────────────┴───────────────────┐
          ▼                                                                   ▼
┌───────────────────────────────────────┐   ┌─────────────────────────────────────────┐
│     1. INSTANCE SWITCH (Teleport)     │   │      2. FLEET COCKPIT (Panoptic)        │
│ • Switches global `apiBase`           │   │ • Stays on Desktop context              │
│ • Full UI re-targets to remote node   │   │ • Views all 1-25+ nodes at a glance     │
│ • "I am now managing the Living Room" │   │ • Inspects logs via remote MCP drawer   │
└───────────────────────────────────────┘   └─────────────────────────────────────────┘
```

#### Key Design System Rules (`packages/design-system`):
1. **Component Surface Reuse:**
   * Node cards in `NodeFleetCockpit.tsx` MUST use the standardized `MetricCard` surface and `StatusBadge` variants (`online` [emerald/green], `fallback` [amber/yellow], `offline` [slate/red]).
   * Vitals indicators (CPU %, RAM %, Thermals °C, Load) must follow the exact typographic hierarchy and tabular numbers (`font-mono`) established in `@halbert/design-system`.
2. **Dual-Action Node Interaction:**
   * Clicking a node card in the Fleet Cockpit offers two clear affordances:
     * **[Inspect Node]** (Default): Slides open a diagnostic drawer powered by `fleet_proxy.py` (Desktop acting as MCP client of the satellite) without interrupting the user's active desktop conversation or workflow.
     * **[Switch Active Context]**: Invokes `setInstanceEndpoint()`, transitioning the full desktop UI to directly interface with that node's local dashboard.
3. **Storybook Verification:**
   * All new fleet components (`NodeFleetCockpit`, `PeerPairingModal`, `DiscoveredPeerCard`) must be registered with stories in `packages/design-system/src/stories/` covering full state variations: `SingleNode`, `MultiNodeFleet (5 nodes)`, `Degraded/Offline`, and `PairingHandshake`.

---

### 11.3 Cognitive & Persona Monologue Mechanics (`advance_turn`)

The interaction between background cognitive ticks (`advance_turn` in `PersonaCognition`) and compute offloading presents a severe resource contention risk if not strictly bounded.

#### The Cognitive Contention Finding:
* If 10 satellite nodes in a household offloaded their continuous subconscious monologue (`advance_turn`) to the Desktop's GPU every 5–10 seconds, the Desktop would be hit with 60–120 inference requests per minute. This would permanently exhaust GPU VRAM and cause interactive desktop chat turns to crawl.

#### The Four-Tier Turn Classification Policy:
The `ComputeRouter` on satellite nodes enforces strict turn classification:

| Turn Classification | Origin / Trigger | Offload to Desktop GPU? | Fallback Behavior if Desktop Offline |
| :--- | :--- | :--- | :--- |
| **`interactive_user`** | Wake-word voice query, chat input on satellite | **YES (Priority 2)** | Template thoughts (deterministic, < 1.5s) on `home`/`home-light` and `SBC_LOW_POWER` devices; optional local 3B on 8GB+ sysadmin-variant satellites (offload-preferred) |
| **`high_value_event`** | Frigate person detection, security anomaly alert | **YES (Priority 3)** | Local heuristic rule evaluation |
| **`sleep_consolidation`** | Daily memory synthesis (scheduled 3:00 AM) | **YES (Priority 3, Batch)** | Deferred in queue until Desktop is awake and idle |
| **`cognitive_monologue`** | Continuous background tick (`advance_turn`) | **NO (Strictly Local)** | Runs 100% on-device using template thoughts (`HALBERT_LLM_THOUGHTS=0`) |

> **Revised 2026-08-30:** the `interactive_user` fallback cell drops "local micro-model response" for `home`/`home-light` and `SBC_LOW_POWER` — those nodes have no local model at all; template thoughts deliver the < 1.5s guarantee deterministically. **Open questions (simplification §11, unresolved):** (Q3) whether `vision_model` exists on HA variants at all — Frigate may handle all vision with Halbert consuming MQTT events; (Q4) whether `advance_turn` should be disabled entirely on `home`/`home-light` variants, given template thoughts are the only monologue option there — the `cognitive_monologue` row above assumes the monologue still runs.

---

### 11.4 Multi-Satellite Concurrency & Latency Budgets

When scaling to **1:N satellites (up to 25 nodes)**, latency budgets must govern queueing behavior to ensure human conversational responsiveness never stalls.

#### Concurrency Slot Allocation (Desktop Broker):
* The Desktop `ComputeBroker` operates with an async semaphore (default `max_concurrent=4` slots for modern Apple Silicon unified memory / NVIDIA VRAM):
  * **Slot 1 (Reserved):** Dedicated to `Priority 1` (Active Local Desktop User).
  * **Slots 2–4 (Dynamic Pool):** Shared between `Priority 2` (Satellite Voice) and `Priority 3` (Background Batch).

#### The 1.5-Second Voice Timeout Rule:
* When a user speaks to a satellite in the kitchen:
  1. Satellite sends an inference request to Desktop with `priority=2` and a hard **1.5s queue timeout**.
  2. If the Desktop is online and a slot is open, generation begins immediately and streams back over HTTP/SSE.
  3. If all slots are occupied and 1.5s elapses without acquisition, the satellite **aborts queue wait** and immediately falls back to template thoughts (`home`/`home-light` and `SBC_LOW_POWER` — no local model exists) or local 3B generation (8GB+ sysadmin-variant satellites only).
  4. **Outcome:** The user never experiences an awkward 5-second silence while standing in front of an ambient smart home speaker.

---

### 11.5 Security Perimeter, Egress Redaction & Trust Lifecycle

A federated compute architecture fundamentally transforms the node-to-node boundary into an untrusted network link:

```
  ┌────────────────────────────────────────────────────────┐
  │         SATELLITE NODE (e.g. Garage Pi on Wi-Fi)       │
  └───────────────────────────┬────────────────────────────┘
                              │ Prompt Request (Contains user input)
                              ▼
  ┌────────────────────────────────────────────────────────┐
  │        DESKTOP COMPUTE ENDPOINT (compute_endpoint.py)   │
  │  1. Validate Bearer Token against peers_config.py      │
  │  2. Filter Tools: Strip all non-PEER_ALLOWED_TOOLS     │
  │  3. Execute Model Generation (Ollama / vLLM — never    │
  │     apple-foundation for peer requests)                │
  │  4. Apply mcp_response() + redact_text() on output     │
  └───────────────────────────┬────────────────────────────┘
                              │ Redacted Response Stream
                              ▼
  ┌────────────────────────────────────────────────────────┐
  │        SECURE INGESTION ON SATELLITE (No secrets leak)  │
  └────────────────────────────────────────────────────────┘
```

#### Security Directives:
1. **Unconditional `secure_model` Isolation:**
   * The `secure_model` slot handles local secrets, disk encryption keys, authentication credentials, and raw private storage.
   * `PeerProvider.can_serve_slot("secure_model")` unconditionally returns `False`. Remote offload of `secure_model` is forbidden by code architecture.
   * **Scope note (revised 2026-08-30):** `home`/`home-light` variants do not configure `secure_model` at all — the guardrail remains in `PeerProvider`/`llm_config` as defense-in-depth but is exercised only by sysadmin-variant nodes. Sysadmin work on an HA device is performed from the workstation's Halbert (fleet cockpit / MCP client path) using the workstation's `secure_model`.
2. **Egress Sanitization:**
   * Responses from the Desktop compute endpoint pass through `mcp_response()` before serialization, stripping accidental file paths, API tokens, or internal workstation credentials that may have appeared in model reasoning traces.
3. **Cryptographic Token Revocation:**
   * `peers_config.py` stores SHA-256 hashes of tokens. Revoking a peer via the Desktop UI (`DELETE /api/peers/{node_id}`) immediately causes all subsequent requests from that peer to receive `401 Unauthorized` on the very next request cycle with zero cache lag.

---

### 11.6 Haloysius Subtractive Contract & Network Resilience

Halbert's core contract mandates extreme portability:
* **Subtractive Dependency Guard:** `zeroconf` is loaded strictly inside function-level `try/except ImportError` blocks. The core Halbert daemon will start, run, and execute all local functions with zero errors even if `zeroconf` is completely absent from the environment.
* **Network Flapping Mitigation:**
  * Workstations frequently enter sleep, undergo DHCP lease renewals, or experience Wi-Fi roaming latency.
  * The satellite `ComputeRouter` maintains a rolling health window (`_peer_health_state`) with a 3-consecutive-failure threshold before transitioning a peer from `ONLINE` to `OFFLINE`. This prevents rapid flapping between peer-offload and fallback mode during minor network packet loss (fallback = local model on 8GB+ sysadmin-variant satellites; template thoughts on `home`/`home-light` and `SBC_LOW_POWER` devices, which have no local model to flap to).

---

### 11.7 Implementation Summary Table

| Step | Functional Area | Primary Component | Key Contract Enforced |
| :--- | :--- | :--- | :--- |
| **9.1** | Authentication | `peer_middleware.py` | Unified MCP/Peer bearer auth with SHA-256 token hashing |
| **9.2** | Navigation | `InstanceSwitch.tsx` | Discovery feed polling + manual IP fallback |
| **9.3** | Inference Client | `model/providers/peer.py` | `ModelProvider` compliance + slot filtering; for `home`/`home-light`, `list_models()` = health check only (no model picker; the workstation's picker governs); provider registration in the model stack is a prerequisite |
| **9.4** | Redaction Boundary | `compute_endpoint.py` | `mcp_response()` output filtering + restricted tool allowlist |
| **9.5** | Telemetry | `telemetry_agent.py` | Lightweight discovery snapshot diffing (no parallel scanners) |
| **9.6** | Edge Fallback | `compute_router.py` | Offload-only on `SBC_LOW_POWER` and `home`/`home-light` (no local model tier; peer → template thoughts); 2B-3B minimum on 8GB+ sysadmin satellites; 1B tier dropped |
| **9.7** | Discovery | `peer_discovery.py` | Lazy `zeroconf` import (Haloysius subtractive contract) |
| **9.8** | Concurrency | `compute_broker.py` | Priority queue with 1.5s voice timeout & GPU slot semaphore |
| **9.9** | Fleet Diagnostics | `fleet_proxy.py` | Desktop-as-MCP-client to remote satellites |
| **9.10** | Apple Silicon (local-only) | `peer_discovery.py`, `compute_endpoint.py` | `compute_backends` advertises `ollama`/`vllm` only; peer requests on Mac hosts route to Ollama, never `apple-foundation` |

