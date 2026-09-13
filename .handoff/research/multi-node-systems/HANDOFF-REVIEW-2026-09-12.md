# Handoff: Multi-Node Research Sanity Check

**Location**: `.handoff/research/multi-node-systems/HANDOFF-REVIEW-2026-09-12.md`
**Date**: 2026-09-12
**Purpose**: Document the technical review of the multi-node systems research package, flag inaccuracies and over-engineering, and set the starting point for the next research session.

---

## What was reviewed

All six documents in `.handoff/research/multi-node-systems/`:

| Doc | Topic | Verdict |
|---|---|---|
| `README.md` | Executive summary, findings matrix, references | Solid overview; findings matrix is accurate |
| `01-AUTH-AND-ZERO-TRUST-CLUSTERING.md` | PAKE pairing, mTLS, Noise, capability tokens | **Stale audit** (see below); SPAKE2+ implementation hand-wave |
| `02-SHARED-REDUNDANT-DATABASES-AND-STATE.md` | SQLite replication, 2-node quorum, CRDTs | Strongest section; cr-sqlite has dependency tension |
| `03-SHARED-COMPUTE-AND-INFERENCE-DISPATCH.md` | LAN compute physics, tensor vs pipeline vs request routing | Physics correct; sliding-window redactor proposes second choke point |
| `04-NETWORK-TOPOLOGY-DISCOVERY-AND-RESILIENCE.md` | mDNS, VLAN traps, WoL, SWIM | Edge cases all real; SWIM is overkill at current scale |
| `05-SCOPING-AND-RECOMMENDATIONS-FOR-HALBERT.md` | Rejection list, 4-phase roadmap, hardware tiers | Rejection list is the best output; roadmap needs scoping down |

---

## Confirmed solid (no action needed)

These parts are technically correct and verified against the codebase. The next session should treat them as established ground truth, not re-research them.

1. **Tensor parallelism rejection (doc 03)** — The math is right: 160 AllReduce roundtrips per token on 1GbE gives ~7.8 tok/s, on Wi-Fi ~0.6 tok/s. Request-level offloading is the only viable pattern on home LANs. `compute_router.py` already does this.

2. **2-node quorum deadlock (doc 02)** — $Q = \lfloor N/2 \rfloor + 1$ means N=2 deadlocks when either node sleeps. Raft/rqlite/dqlite are correctly rejected. Lease-based active-passive is the right escape hatch and aligns with the Singular Entity model.

3. **4-tier turn classification and 1.5s voice deadline (doc 03)** — Verified against `compute_broker.py:125` (`VOICE_QUEUE_TIMEOUT_S = 1.5`) and `compute_router.py` (`TurnType` enum, 3-consecutive-failure hysteresis, "never offload cognitive_monologue" rule). All match.

4. **mDNS edge cases (doc 04)** — VLAN isolation (TTL=1 multicast), DTIM power-save buffering, DHCP roaming — all genuine home network pathologies. The 3-tier discovery ladder (mDNS → cached unicast → Tailscale) is reasonable.

5. **State semantic tiering (doc 02, section 5)** — G-Set for append-only event logs, DAG merging for conversation trees, MELD contradiction preservation for memory, node-local for physical state. Conceptually sound and aligns with existing architecture.

6. **"What NOT to Build" rejection list (doc 05)** — Raft at N=2, FUSE/macFUSE, heavy daemons (Postgres/Consul/Ceph), cognitive monologue offloading. All correctly identified as traps.

7. **Hardware tier budgets (doc 05, section 5)** — Pi (2-4GB, <512MB RAM, <10GB storage), N100 (8GB, <1.5GB, <25GB), Mac Studio/PC (64-128GB, full RAM, >100GB). Reasonable and matches the low-power handoff.

---

## Inaccuracies and corrections

### 1. Pairing flow audit is stale (doc 01, section 2)

**The research describes a vulnerability that has already been fixed.**

The research's diagram (section 2) shows the PIN being returned in the `PairResponse`, and lists "Cleartext PIN on the Wire" as critical vulnerability #1. But the actual code at `halbert_core/dashboard/routes/peers.py:135-144` says:

> *Deliberately carries no PIN. It used to: the requester was handed the secret it was then asked to prove, so anyone who could reach the port could pair itself and walk away with a bearer token — the PIN was theatre (SE-16 / R10-F1).*

The current flow has three hardening steps the research missed:
- `PairResponse` returns **no PIN** — the PIN is only shown on the host's local-admin screen (`/api/peers/pending`, gated by `require_local_admin`)
- An explicit **approval step** (`/api/peers/pending/{request_id}/approve`) — a person at the host must click approve before the verify endpoint will issue a token
- The verify endpoint rejects with **403 Forbidden** if `pending.approved` is False (`peers.py:360-367`)

The research even references "SE-16 / R10-F1" in passing but didn't update its audit to reflect the fix.

**The remaining real vulnerability is narrower**: no TLS on the transport. The PIN in the verify request body and the bearer token in the response both travel over plaintext HTTP. That's legitimate, but the research overstates it by describing a pre-fix flow.

**Action for next session**: Re-audit `peers.py` against the current code. The cleartext-transport finding stands; the "PIN returned in pairing response" and "self-service token minting" findings are closed.

### 2. SPAKE2+ implementation claim is wrong (doc 01, section 3)

The research says: *"Implement a lightweight Python SPAKE2+ exchange using `cryptography` (already available)."*

This is incorrect on two counts:
- Python's `cryptography` library does **not** provide SPAKE2+. It provides elliptic curve primitives (X25519, P-256), but SPAKE2+ is a protocol built on top of those. You'd need either the `spake2` PyPI package (a new dependency) or a hand-rolled implementation using EC point arithmetic (significant crypto engineering, easy to get wrong).
- `cryptography>=42.0` is an **optional** dependency (in the `integrity` extra group at `halbert_core/pyproject.toml:96-99`), not a hard one. Saying "already available" is misleading — it's only present if the `integrity` extra is installed.

**Action for next session**: Research the actual implementation options for PAKE on Python without adding a hard dependency. Options to evaluate: (a) `spake2` PyPI package as an optional extra, (b) Noise Protocol Framework via `noiseprotocol` package as an optional extra (this gives Noise_XX/Noise_IK which solves mutual auth without PAKE), (c) hand-rolled SPAKE2+ using `cryptography`'s low-level EC API (highest risk), (d) skip PAKE entirely and use the simpler pinned-Ed25519 + TLS approach.

### 3. cr-sqlite has an unresolved dependency tension (doc 02, section 4)

The research calls cr-sqlite "Ideal for active-active multi-node sync" and highlights "Zero daemons. Loadable extension via `db.load_extension()`." But cr-sqlite is a **native SQLite extension** (`.so` on Linux, `.dylib` on macOS) — a platform-specific compiled binary. That's a third hard dependency in disguise, or at minimum an optional extra that needs per-platform builds. The subtractive contract says "exactly two hard dependencies."

The research acknowledges the contract but doesn't reconcile this.

**Action for next session**: Evaluate whether cr-sqlite can be an optional extra (lazy-loaded when present, falls back to RPC proxy when absent). If not, research pure-Python CRDT approaches that don't require native extensions — e.g., application-level G-Set sync over HTTP (which doc 02 section 5.1 already describes for timeline.db, and which needs no extension at all).

### 4. Sliding-window redactor proposes a second redaction choke point (doc 03, section 6)

The research recommends implementing `SlidingWindowRedactor` in `halbert_core/mcp/response.py`. But AGENTS.md's invariant is explicit:

> **Redaction** — `ingestion/redaction_registry.py`, enforced at the response choke point in `security/display_transport.py`. Scrub deterministically *before* the model. Never ask a model to summarize secrets out of a payload.

The streaming redaction problem is real (secrets split across SSE token boundaries), but the fix should extend the existing registry to handle streaming buffers, not create a parallel redaction path in a different module.

**Action for next session**: Design the streaming-redaction extension as a new mode in `redaction_registry.py` (or a streaming adapter that wraps it), wired into `display_transport.py`. Do not create a `SlidingWindowRedactor` class in `mcp/response.py`.

### 5. Biscuit/Macaroon capability tokens need a new library (doc 01, section 5.2)

The research recommends attenuated capability tokens (Biscuit or Macaroons) but doesn't mention that these require additional Python packages (`biscuit-python` or similar). More dependency tension the research doesn't flag.

**Action for next session**: If scoped capability tokens are wanted, evaluate whether a simple signed-JWT approach (using the existing `cryptography` optional dep for Ed25519 signing) suffices, or whether Biscuit's offline attenuation is worth a new optional extra. The existing bearer-token system with per-peer revocation (`DELETE /api/peers/{node_id}`) may be adequate for a 2-3 node home cluster.

---

## Over-engineered (defer until scale demands it)

### SWIM gossip protocol (doc 04, section 5.3)

Recommended for clusters "growing beyond 3-5 nodes." A typical Halbert household has 2-3 nodes. The existing 3-consecutive-failure hysteresis in `compute_router.py` is adequate. SWIM's indirect probing is valuable at 10+ nodes where mesh routing matters. **Defer until node count grows.**

### Full mTLS CA infrastructure (doc 01, section 4.1)

The research recommends an internal Root CA, CSR signing, 90-day node certificates, and 30-day auto-rotation. That's enterprise PKI for a home network. The simpler path — which the research mentions but buries — is Noise_IK with pinned Ed25519 keys (the `body.key` that already exists). One pinned key per peer, no certificate lifecycle, same mutual authentication guarantee. **Use pinned keys, not a CA, for a 2-3 node cluster.**

### Phase 4 warm standby failover (doc 05, section 4)

Encrypted snapshot streaming + warm standby promotion is a lot of machinery for disaster recovery. A simpler version: periodic `VACUUM INTO` + encrypted rsync to the satellite. The "Promote to Canonical" button is a nice UX goal but the replication engine doesn't need to be Litestream-grade for a home deployment. **Start with periodic snapshots; build the promotion UX only if the snapshot approach proves insufficient.**

---

## Immediately buildable (no new hard deps, no founder decisions)

These are the highest-value items from the research that can be implemented right now:

1. **TLS on the peer transport** — the one real remaining vulnerability from doc 01. Even self-signed certs with pinned fingerprints (no CA) would close the cleartext gap. This is the highest-priority security item.

2. **Satellite read-through cache** (Phase 3 of doc 05) — the RPC proxy fragility is real and verified. `PeerConversationStore` (`agents/peer_conversation_store.py`) has zero local cache; every read is an RPC call. A local SQLite mirror for `get_thread` / `recall_memory` would eliminate the `PeerConversationUnavailable` crash on Wi-Fi blips and host sleep.

3. **Streaming redaction through the existing registry** — the split-secret problem is real (secrets split across SSE token boundaries), but route it through `redaction_registry.py` / `display_transport.py`, not a new module. Design a streaming-buffer mode in the existing registry.

---

## Starting point for the next session

1. **Read this document first.** It supersedes the research docs where they conflict.
2. **Re-audit `peers.py`** against current code to get an accurate picture of the remaining transport vulnerability (cleartext HTTP, not the pre-fix PIN-in-response flow).
3. **Resolve the SPAKE2+ vs Noise vs pinned-key question.** The research recommends SPAKE2+ but doesn't account for the implementation cost or the dependency. A decision here unblocks the Phase 1 roadmap.
4. **Resolve the cr-sqlite vs pure-Python-CRDT question.** The research recommends cr-sqlite but doesn't reconcile it with the subtractive contract. A decision here unblocks the Phase 3 replication design.
5. **Design the streaming redaction extension** as a mode in the existing `redaction_registry.py`, not a new module. This is the one item that's fully unblocked and can be built immediately.
6. **Scope the roadmap down.** The 4-phase plan in doc 05 is ambitious. The three immediately-buildable items above are the right first wave. Everything else (capability tokens, SWIM, warm standby, full CA) should be explicitly deferred with a "revisit when N" trigger.

### Key files to read

- `halbert_core/halbert_core/dashboard/routes/peers.py` — current pairing flow (the research's audit is stale)
- `halbert_core/halbert_core/federation/compute_router.py` — 4-tier turn classification, 3-failure hysteresis (verified accurate)
- `halbert_core/halbert_core/federation/compute_broker.py` — `VOICE_QUEUE_TIMEOUT_S = 1.5`, priority queue (verified accurate)
- `halbert_core/halbert_core/agents/peer_conversation_store.py` — the stateless RPC proxy that Phase 3 would add caching to
- `halbert_core/halbert_core/ingestion/redaction_registry.py` — the single redaction choke point (streaming extension goes here)
- `halbert_core/halbert_core/security/display_transport.py` — the enforcement point for redaction
- `halbert_core/pyproject.toml` lines 80-99 — the optional dependency groups (integrity, cognition) and the two hard deps
