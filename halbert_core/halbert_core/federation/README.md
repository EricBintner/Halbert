# Federated Multi-Node Compute & Fleet Diagnostics

This package implements the "Sovereign Self, Shared Commons" federation
architecture for Halbert. It is **not** a greenfield system — it extends
three existing foundations.

## Architecture

```
Satellite (Pi 5)                      Compute Host (Mac Studio)
┌────────────────────┐                ┌──────────────────────────┐
│ ComputeRouter      │  1. mDNS       │ PeerBeacon (_halbert._tcp)│
│  ├─ PeerProvider   │     discover   │                          │
│  │  (tier_router)  │  2. Pair       │ PeersConfig (peers.json) │
│  └─ Fallback chain │     (PIN)      │  └─ per-peer token hash  │
│     (H7: hw-aware) │                │                          │
│                    │  3. Compute    │ ComputeBroker            │
│ DiscoveryEngine    │     (bearer)   │  └─ priority queue       │
│  + TelemetryAgent  │                │     + semaphore          │
│                    │  4. Telemetry  │                          │
│ MCP Server ◄───────│────────────────│── FleetProxy (MCP client)│
│  (mcp_response)    │  5. Inspect    │  └─ mcp_response() x2    │
└────────────────────┘     (MCP)      └──────────────────────────┘
```

## Foundations (do not duplicate)

| Foundation | Package | What it provides | Finding |
|-----------|---------|------------------|---------|
| MCP Phase 4b | `mcp/` | HTTP/SSE transport, bearer auth, `mcp_response()` redaction, Tier 0/1/2 sensitivity | C1, C4, C5 |
| Multi-Instance Phase 7 | `dashboard/routes/instance.py`, `InstanceSwitch.tsx` | Env-var isolation, Instance Switcher, persona-aware sidebar | C2 |
| 4-slot model | `model/llm_config.py`, `model/tier_router.py` | `chat_model`, `specialist_model`, `vision_model`, `secure_model` slots, fallback chains | C3, M11 |
| Discovery engine | `discovery/` | Platform-aware scanners, structured `Discovery` objects | M12 |
| Hardware profiles | `model/hardware_detector.py` | `SBC_LOW_POWER`, `ENTRY_8GB`, `LAPTOP_16GB`, etc. | H7 |
| Apple Intelligence | `model/capabilities.py`, `model/auto_provision.py` | `apple-foundation` provider, Metal GPU detection | M13 |

## Files

### Backend (`federation/`)

| File | Step | Purpose |
|------|------|---------|
| `__init__.py` | — | Package init, lazy public API |
| `peers_config.py` | 9.1 | Per-peer credential store (SHA-256 token hashes, revocation) |
| `peer_middleware.py` | 9.1 | FastAPI bearer token dependency (shared with MCP 4b) |
| `peer_discovery.py` | 9.7 | mDNS beacon/listener (lazy `zeroconf`, LAN-only) |
| `compute_endpoint.py` | 9.4 | OpenAI-compatible `/api/compute/v1/chat/completions` with `mcp_response()` |
| `compute_broker.py` | 9.8 | Priority queue + concurrency semaphore |
| `compute_router.py` | 9.6 | Hardware-profile-aware fallback chain (extends `tier_router`) |
| `tool_allowlist.py` | 9.4 | `PEER_ALLOWED_TOOLS` frozenset, `filter_tools_for_peer()` |
| `telemetry_agent.py` | 9.5 | Discovery snapshot + vitals deltas (reuses `discovery/`) |
| `fleet_proxy.py` | 9.9 | Desktop-as-MCP-client proxy to satellite |

### Backend (`model/providers/`)

| File | Step | Purpose |
|------|------|---------|
| `peer.py` | 9.3 | `PeerProvider(ModelProvider)` — calls peer compute endpoint |

### Backend (`dashboard/routes/`)

| File | Step | Purpose |
|------|------|---------|
| `peers.py` | 9.1 | Pairing handshake (`/api/peers/pair`, `/api/peers/verify`), list, revoke |
| `fleet.py` | 9.9 | Fleet Cockpit aggregation (proxies to satellite MCP) |

### Frontend

| File | Step | Purpose |
|------|------|---------|
| `lib/peerApi.ts` | 9.2 | Typed API client for peers/fleet endpoints |
| `hooks/useDiscoveredPeers.ts` | 9.7 | Polls `/api/peers/discovered` for mDNS peers |
| `components/fleet/NodeFleetCockpit.tsx` | 9.9 | Fleet status grid (CPU/RAM/temp per node) |
| `components/fleet/PeerPairingModal.tsx` | 9.1 | Discovered peers list + manual pairing + PIN |

### Tests (`tests/federation/`)

| File | Finding | Purpose |
|------|---------|---------|
| `test_peer_redaction.py` | C4, L15 | Peer prompt requesting secrets returns redacted |
| `test_peer_tool_allowlist.py` | C4, L15 | Peer prompts cannot invoke restricted tools |
| `test_token_revocation.py` | M14, L15 | Revoked token rejected within one request cycle |
| `test_split_brain.py` | L15 | Deferred task conflict resolution |
| `test_secure_model_no_offload.py` | M11, L15 | `secure_model` never routes to peer |
| `test_hardware_profile_fallback.py` | H7, L15 | SBC_LOW_POWER uses template thoughts |
| `test_compute_broker.py` | H6, L15 | Concurrency + priority preemption |
| `test_peer_discovery.py` | H9, H10, L15 | mDNS TXT record serialization |

## Implementation Order (Phase 9+)

See `.handoff/HANDOFF-FEDERATED-MULTI-NODE-COMPUTE-AND-FLEET-2026-08-29.md` §8
for the full re-sequencing with finding references.

| Step | Builds On | Deliverable |
|------|-----------|-------------|
| 9.1 | MCP Phase 4b | Peer auth = MCP token, one middleware, per-peer tokens |
| 9.2 | Multi-Instance Phase 7 | Extend Instance Switcher with remote peers |
| 9.3 | `tier_router.py` | `peer://` provider, 1:1 cross-machine link |
| 9.4 | MCP Tier 0/1/2 | `redact_text()` + tool allowlist on compute endpoint |
| 9.5 | Discovery engine | Satellite telemetry = discovery snapshot + vitals |
| 9.6 | Hardware profiles | Hardware-profile-aware fallback |
| 9.7 | — | mDNS auto-discovery (lazy `zeroconf`, LAN-only) |
| 9.8 | 9.1-9.4 | Concurrency broker, scale to N |
| 9.9 | MCP server on satellite | Fleet Cockpit = Desktop as MCP client |
| 9.10 | Apple Intelligence | `apple-foundation` as advertised peer capability |

## Security Boundary

Every response that leaves a Halbert node toward a peer passes through
`mcp_response()` (`halbert_core/mcp/response.py`), the same redaction
boundary used by the MCP server. Peer prompts cannot invoke tools
outside `PEER_ALLOWED_TOOLS`. Fleet inspection is proxied through the
satellite's MCP server, not a bespoke API.

## Dependencies

- `zeroconf>=0.131.0` — **optional** (lazy import, `[federation]` extra)
- `psutil` — already a dependency (used by telemetry_agent)
- `requests` — already a hard dependency (used by fleet_proxy)
- No new hard dependencies (Haloysius subtractive contract preserved)
