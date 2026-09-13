# Scoping & Architectural Recommendations for Halbert

**Location**: `.handoff/research/multi-node-systems/05-SCOPING-AND-RECOMMENDATIONS-FOR-HALBERT.md`  
**Date**: 2026-09-12  
**Focus**: Scoping cutting-edge distributed systems research back to Halbert's architectural invariants, design rules, hardware budgets, and concrete 4-phase implementation roadmap.

---

## 1. Grounding in Halbert's Non-Negotiable Invariants

Before adopting any cutting-edge distributed computing pattern, it must pass Halbert's core engineering constraints:

| Halbert Invariant | Source | Architectural Consequence for Multi-Node |
|---|---|---|
| **Haloysius Subtractive Contract** | `AGENTS.md` | **Exactly two hard dependencies** (`pyyaml>=6.0`, `requests>=2.31.0`). No heavy distributed daemons (no Consul, etcd, PostgreSQL, or Kubernetes). Every network or crypto enhancement must be written in standard library or lazy optional packages. |
| **Singular Entity Model** | `DECISIONS.md` (2026-08-31) | One identity, multiple bodies. Canonical host holds memory and conversation history; `body_name` is a location label. |
| **Tier 2 Deterministic Redaction** | `DECISIONS.md` (2026-08-27) | Tier 2 secrets are scrubbed before reaching any model or wire transport. Scrubbing must be deterministic. |
| **Apple Intelligence Local-Only** | `DECISIONS.md` (2026-08-30) | Apple Intelligence is local to the Mac's own slots; it is never offered as a peer backend. Peers get Ollama / vLLM only. |
| **Low-Power Edge Budgets** | `.handoff/` Low-Power Handoff | Satellites (Pi 5, N100) have **10–25 GB** storage budgets and **0.5–1.5 GB** RAM budgets. No 200 GB distributed indexes. |

---

## 2. The "What NOT to Build" Rejection List

Research into enterprise distributed systems reveals several attractive patterns that are **lethal traps** for Halbert's home-network architecture. We explicitly reject the following:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       REJECTED ARCHITECTURES & PATTERNS                     │
│                                                                             │
│  ❌ Consensus Clusters (Raft / rqlite / dqlite):                             │
│     Deadlocks on 2-node home setups (1 Pi + 1 Mac) whenever the Mac sleeps.  │
│                                                                             │
│  ❌ Tensor Parallelism over Home LAN / Wi-Fi:                               │
│     160 network roundtrips per token stalls the GPU to <1 token/sec.        │
│                                                                             │
│  ❌ FUSE-Based Filesystems (LiteFS):                                         │
│     Requires macFUSE (kernel extension / reduced SIP) on macOS workstations.│
│                                                                             │
│  ❌ Heavy Infrastructure Daemons (PostgreSQL, Consul, Ceph):                │
│     Violates the Haloysius 2-hard-dependency contract.                      │
│                                                                             │
│  ❌ Cleartext HTTP & Plaintext PIN Pairing:                                 │
│     Trivially intercepted by any rogue device on home Wi-Fi.                │
│                                                                             │
│  ❌ Offloading Cognitive Monologue Turns:                                   │
│     Floods the peer GPU with 60–120 requests/minute, starving user chat.    │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. What Halbert REALLY Needs: The Scoped Solution

By synthesizing the research literature against Halbert's invariants, we identify four tightly scoped, high-leverage architectural pillars:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      THE FOUR PILLARS OF HALBERT MULTI-NODE                 │
│                                                                             │
│  1. Zero-Trust PAKE & mTLS Transport                                        │
│     - SPAKE2+ (RFC 9383) 6-digit numeric PIN handshake                      │
│     - Mutual TLS 1.3 with internal Canonical Root CA                         │
│     - Ed25519 body.key DID pinning (did:key)                                │
│     - Attenuated capability tokens (scoped tool access, 30-day rotation)    │
│  ─────────────────────────────────────────────────────────────────────────  │
│  2. Request-Level Smart Compute Dispatch                                    │
│     - Whole-turn routing to unified-memory GPU hosts (32B/70B)              │
│     - Strict 1.5s Voice Deadline with instant local CPU template fallback   │
│     - Sliding-window lookahead redaction filter for real-time SSE streaming │
│     - Selective Wake-on-LAN for background batch consolidation only         │
│  ─────────────────────────────────────────────────────────────────────────  │
│  3. Hybrid State & Local Cache Replication                                  │
│     - Local read-through cache on satellites (zero-downtime voice turns)    │
│     - Optimistic offline write queue (stages turns during network drops)    │
│     - G-Set set-union sync for timeline.db and state_ledger.db              │
│     - DAG branch preservation for concurrent conversation turns             │
│  ─────────────────────────────────────────────────────────────────────────  │
│  4. Resilient Hybrid Discovery & Failure Hysteresis                         │
│     - mDNS/DNS-SD (zeroconf) with cached IP fallback for VLANs              │
│     - Rolling 3-consecutive-failure threshold to absorb Wi-Fi roaming blips │
│     - Dual-broadcast WoL (subnet directed + global broadcast)              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Concrete 4-Phase Implementation Roadmap

This roadmap builds directly on existing code units (`halbert_core/federation/`, `agents/peer_conversation_store.py`, `dashboard/routes/peers.py`) without introducing any new hard dependencies.

### Phase 1: Cryptographic Zero-Trust Pairing & mTLS Channel
**Target**: Eliminate all cleartext secrets on the wire during pairing and communication.
1. **SPAKE2+ Handshake**:
   - Implement `crypto_pake.py` using Python's standard `cryptography` library.
   - Replace cleartext PIN in `routes/peers.py` with the 2-step SPAKE2+ exchange.
   - Derive 256-bit session key with zero risk of offline dictionary attacks.
2. **Internal CA & mTLS 1.3**:
   - Canonical Host initializes an internal ECDSA/Ed25519 Root CA.
   - Satellite exchanges CSR during pairing; Host signs a 90-day Node Certificate.
   - Configure Uvicorn/FastAPI with `ssl_context` requiring client certificates.
3. **DID Pinning**:
   - Pin the satellite's `did:key` in `peers.json`. Reject any connection where the TLS client certificate public key does not match the pinned DID.

### Phase 2: Streaming Redaction & Deadline-Aware Compute Broker
**Target**: Enable low-latency streaming chat/voice offloading without secret leakage.
1. **Sliding-Window Redaction Filter**:
   - Implement `SlidingWindowRedactor` in `halbert_core/mcp/response.py`.
   - Hold a 32-character buffer to inspect token boundaries for secret prefixes (`sk-`, `ghp_`, `BEGIN PRIVATE KEY`).
   - Wire into `/api/compute/v1/chat/completions` for SSE streaming responses (`stream: true`).
2. **Voice Deadline Enforcement**:
   - Enforce `ComputeBroker.VOICE_QUEUE_TIMEOUT_S = 1.5` for Priority 2 (`interactive_user`).
   - If workstation GPU is busy, satellite aborts offload and speaks fast local template (<100ms).
3. **Selective Wake-on-LAN**:
   - Only trigger `send_wol_packet_dual` for asynchronous background turns (`sleep_consolidation`, deep indexing).

### Phase 3: Satellite Read Cache & Offline Write Queue
**Target**: Prevent satellite crashes when the workstation reboots or Wi-Fi blips.
1. **Local Read-Through Replica**:
   - Satellite keeps a local read-only SQLite mirror of active conversation threads and core memories.
   - Queries (`get_thread`, `list_messages`, `recall_memory`) hit local SQLite first (0ms latency).
2. **Optimistic Offline Staging Queue**:
   - If network drops during `append_message` or `add_event`, the write is appended to `local_staging.db`.
   - A background synchronization worker flushes pending writes via mTLS upon link recovery.
3. **DAG Branch Reconciliation**:
   - If both nodes generated turns concurrently, `ThreadManager` grafts them as sibling branches in the conversation tree without clobbering either.

### Phase 4: Active-Passive Replication & Warm Standby Failover
**Target**: Eliminate the Canonical Host as a single point of failure (disaster recovery).
1. **Encrypted Snapshot Streaming**:
   - Canonical Host takes daily/hourly SQLite online snapshots (`VACUUM INTO`) and pushes encrypted archives to paired satellites.
2. **Warm Standby Promotion**:
   - Satellite maintains a warm replica of `conversation.db` and `memories.db`.
   - If the Canonical Host experiences hardware failure, the operator can click **"Promote to Canonical"** on the satellite dashboard.
   - The satellite assumes the canonical role and begins serving memory and conversation history.

---

## 5. Hardware Tier Budgets & Allocation Matrix

To prevent memory or disk exhaustion on edge nodes, Halbert multi-node components adhere to these strict limits:

| Hardware Tier | Target Device | RAM Allocation | Storage Allocation | Max Model Size | Permitted Multi-Node Roles |
|---|---|:---:|:---:|:---:|---|
| **Micro Satellite** | Raspberry Pi 4/5 (2–4GB) | < 512 MB | < 10 GB | Template Thoughts Only | Voice Pod, Sensor Ingestion, Read Cache. |
| **Coordinator / Edge** | Intel N100 / Pi 5 (8GB) | < 1.5 GB | < 25 GB | 3B Q4 (10–14 tok/s) | Canonical Coordinator, Home Tools, Offline Fallback. |
| **Compute Workstation** | Mac Studio / PC (64–128GB) | Full RAM | > 100 GB | 32B–70B Q4 (25–60 tok/s) | Compute Host, RAG Indexing, Deep Reflection. |

---

## 6. Summary: The Singular Entity Experience

When these recommendations are implemented, Halbert achieves the ultimate vision of a **Singular Entity with Multiple Bodies**:

1. **Effortless & Bulletproof Pairing**: The user installs Halbert on a new Raspberry Pi. The Mac Studio UI displays a 6-digit PIN. The user enters it on the Pi. Within 2 seconds, SPAKE2+ negotiates a zero-trust encrypted channel, exchanges pinned DIDs, and issues an mTLS certificate.
2. **Zero-Lag Voice Turns**: The user speaks in the kitchen. The Pi offloads the query to the Mac Studio's 70B model over mTLS. Tokens stream back with zero secret leakage in <1.2 seconds.
3. **Immunity to Sleep & Network Blips**: If the Mac Studio enters sleep, the Pi continues managing smart home automations, records sensor events into its local timeline, and answers kitchen questions with fast local templates. When the Mac Studio wakes, all staged events and conversation turns sync seamlessly.
4. **Permanent Memory Safety**: If the Mac Studio's SSD fails, the entity's autobiography, memory graph, and conversation history are safe in the Pi's encrypted warm standby replica.
