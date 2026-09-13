# Active-Passive Canonical Replication & Warm Standby (Current Proposal)

**Date**: 2026-09-12  
**Status**: Current Proposal (Supersedes Stateless Proxy Model)  
**Parent Directory**: [`.handoff/research/halbert-backup/`](README.md)  
**Related**:
- [`state-topology.md`](state-topology.md) (Identified Scenario B: Canonical Host Death)
- [`architecture-blueprint.md`](architecture-blueprint.md) (State Vault Archive Format)
- [`multi-persona-and-identity-variations.md`](multi-persona-and-identity-variations.md) (Multi-Persona Boundaries)
- [`.handoff/DISTRIBUTED-MEMORY-ARCHITECTURE-2026-09-09.md`](../DISTRIBUTED-MEMORY-ARCHITECTURE-2026-09-09.md) (Why Multi-Master CRDTs were rejected)

---

## 1. Executive Summary & Paradigm Shift

### The Previous Model: Stateless Remote Proxies
Under the original Singular Entity implementation plan, satellite bodies (workstations, laptops) maintained **zero local memory or conversation history**. `PeerMemoryBackend` and `PeerConversationStore` acted as live HTTP proxies to the Canonical Host (Home Assistant / home server).

**The Vulnerability**:
As identified in [`state-topology.md:Scenario B`](state-topology.md), this created a critical single point of failure:
- If the Canonical Host suffered drive failure or hardware death, satellites were completely stranded.
- If the Canonical Host was temporarily rebooting or offline, satellites suffered instant amnesia (`PeerMemoryUnavailable`).
- Recovery required locating an external backup archive, manual re-flashing, and key restoration.

### The New Paradigm: Single Active Writer + Warm Standby Replicas
Rather than adopting complex multi-master CRDTs (which were evaluated and rejected in `DISTRIBUTED-MEMORY-ARCHITECTURE-2026-09-09.md`), Halbert adopts **Active-Passive Asynchronous Replication**:

1. **Single Active Writer**: Only the Canonical Host writes to the authoritative database during normal operations. There is **zero write-conflict resolution** and **zero CRDT merge complexity**.
2. **Warm Standby Peer Replicas**: The Canonical Host periodically pushes its complete memory and thread state (`memory_v2.db`, `conversation.db`, `state_ledger.db`) to paired satellites over the existing authenticated peer mesh.
3. **Instant Local Redundancy**: Every paired satellite (e.g. Mac Studio, Linux workstation) holds a local, warm point-in-time copy of the entity's mind.
4. **One-Click Promotion**: If the Canonical Host burns out, any paired satellite can be promoted to the Canonical Host in under 5 seconds.

---

## 2. Architectural Mechanics

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    ACTIVE-PASSIVE REPLICATION TOPOLOGY                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  CANONICAL HOST (Home Server)               SATELLITE BODY (Workstation)    │
│  ┌──────────────────────────────┐           ┌─────────────────────────────┐ │
│  │ [ACTIVE WRITER]              │           │ [PASSIVE STANDBY / CLIENT]  │ │
│  │                              │           │                             │ │
│  │  ■ PersonaMemoryStore (Live) │           │  ○ PeerMemoryBackend (Proxy)│ │
│  │  ■ conversation.db (Live)    │           │  ○ PeerConversationStore    │ │
│  │  ■ state_ledger.db (Live)    │           │                             │ │
│  │                              │           │  ■ canonical_replica/       │ │
│  │  Cadence: Every 4-6 hours,   │           │    - memory_v2.db (Warm)    │ │
│  │  or nightly consolidation:   │   LAN     │    - conversation.db (Warm) │ │
│  │  1. Checkpoint & VACUUM INTO ├──────────►│    - state_ledger.db (Warm) │ │
│  │  2. Push compressed snapshot │  Stream   │                             │ │
│  │     over Peer RPC            │           │  ■ Local body.key & state   │ │
│  └──────────────────────────────┘           └─────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.1 The Replication Pipeline
Halbert's databases are compact (< 50 MB to 200 MB compressed). Replicating this state does not require a heavy streaming daemon (like Raft or Kafka). It leverages standard SQLite primitives:

1. **Triggering Events**:
   - **Periodic Schedule**: Every 4 to 6 hours.
   - **Cognitive Consolidation**: Nightly when the cognitive loop consolidates daily episodic memories into the knowledge graph.
   - **Pre-Update**: Immediately prior to software updates or system package upgrades.
   - **Operator Command**: On-demand via the dashboard or CLI.
2. **Snapshot Creation on Canonical Host**:
   - Executes `PRAGMA wal_checkpoint(TRUNCATE)` to guarantee WAL consistency.
   - Calls SQLite's online backup API: `VACUUM INTO '/tmp/halbert_replica_stage/...'`.
   - Bundles the SQLite snapshots into a compressed, signed shard.
3. **Transport**:
   - Canonical Host issues `POST /api/peers/sync-replica` to all non-revoked paired bodies with `role: "body"`.
   - Authenticated via the existing SHA-256 bearer token infrastructure (`peers_config.py`).
   - Transfers across LAN in < 1 second.
4. **Storage on Satellite**:
   - Stored in a isolated staging directory: `~/.local/share/halbert/canonical_replica/`.
   - The satellite marks the replica timestamp and validates SQLite file integrity (`PRAGMA quick_check`).
   - The satellite **never writes** to this replica folder during normal operation.

---

## 3. Failure & Recovery Modes

### Scenario 1: Temporary Network Glitch or Canonical Host Reboot
* **What happens**: The Canonical Host restarts for an OS update.
* **Old Behavior**: Workstation queries failed with `PeerMemoryUnavailable`.
* **New Behavior (Read-Fallback Mode)**:
  - If the remote proxy fails to connect, the satellite seamlessly falls back to **Read-Only execution** against its local `canonical_replica/memory_v2.db`.
  - The workstation still knows the user's name, preferences, past context, and conversation history.
  - New thoughts or user messages are buffered locally in an in-memory queue.
  - Once the Canonical Host comes back online, the queue flushes, and the satellite transitions back to normal proxy mode. Zero disruption to the user.

### Scenario 2: Canonical Host Hardware Destroys / Drive Blowout (Scenario B)
* **What happens**: The home server's SSD completely dies.
* **Recovery Flow**:
  1. The workstation dashboard notices the canonical heartbeat is lost (> 15 minutes).
  2. The workstation displays an action banner in the desktop UI:
     > **"Canonical Host ('home') is unreachable.**  
     > A local warm replica from 2 hours ago (2,847 memories, 156 threads) is ready on this machine.  
     > Would you like to promote this Workstation to the Canonical Mind?"  
     > **[ Promote to Canonical ]**
  3. The operator clicks **Promote**:
     - The workstation copies `canonical_replica/*` into its active `data_dir/`.
     - Clears `canonical_memory_url` in `being.yml`.
     - Sets its local entity role to `canonical`.
     - The local Halbert daemon hot-reloads its memory adapters.
  4. **Outcome**: Within 3 seconds, the Workstation is now the authoritative mind. No data was lost except the last 2 hours of idle background telemetry.
  5. **Hardware Replacement**: When a new home server mini-PC arrives weeks later, the operator simply installs Halbert on it, pairs it with the workstation, and runs **"Transfer Canonical Role to Home Server"**, restoring the original topology seamlessly.

---

## 4. Interaction with Other Systems

### 4.1 Relationship to State Vault Offsite Backups
Active-Passive Peer Replication does not replace State Vault offsite archives; they are complementary layers of defense:

| Layer | Mechanism | Protection Focus | Storage Location |
|---|---|---|---|
| **Layer 1: Peer Standby** | Active-Passive Snapshot Push | **Instant Hardware Failure** (Drive death, mini-PC blowout) | Paired peer disks (Workstation NVMe) |
| **Layer 2: State Vault** | Client-side Encrypted `.halbert-backup` | **Catastrophic / Whole-House Disaster** (Fire, flood, theft of all hardware) | User-owned external drive, NAS, iCloud/Google Drive |

### 4.2 Multi-Persona & Private Guest Protection
In accordance with [`multi-persona-and-identity-variations.md`](multi-persona-and-identity-variations.md):
- **Standard Personas & Costumes**: Replicated automatically as part of the primary autobiography.
- **Private Guest Personas (Strict Isolation)**:
  - Private guest databases (`guests/<guest_id>/memory.db`) are **NOT** pushed to satellites by default.
  - They represent confidential sessions (e.g. an H2 companion or financial persona) that belong only to the host or a specific body.
  - If a user explicitly designates a satellite as an authorized private node, the private shard is transferred as a separate, sealed encrypted blob.

---

## 5. Summary of Advantages

1. **Radical Simplicity**: Reuses the exact same SQLite snapshot logic as State Vault. Zero CRDTs, zero multi-master vector sync, zero merge conflicts.
2. **Self-Healing Fleet**: The hardware running Halbert becomes completely disposable. If any computer in the fleet catches fire, the remaining paired computers already hold the entity's mind.
3. **Graceful Degradation**: Offline laptops and workstations don't get amnesia when separated from the home server; they retain read capability from their last synced replica.
4. **Zero Cloud Requirement**: 100% LAN-driven, private, fast, and compliant with Halbert's local-first mandate.

---

## 6. Technical Review (2026-09-12)

**Reviewer**: Scrutinized against the actual codebase (`halbert_core/` and `Haloysius/`).
**Verdict**: The paradigm shift (stateless proxy → warm standby) is the right direction, but the implementation details contain several factual errors about the current storage layer that invalidate parts of the replication pipeline design. Fix the storage model first, then the pipeline falls out correctly.

### 6.1 Critical: PersonaMemoryStore is JSON, not SQLite

**The single most important error in this document.** The replication pipeline (section 2.1) is built around SQLite snapshot primitives — `PRAGMA wal_checkpoint(TRUNCATE)`, `VACUUM INTO`, SQLite online backup API — applied to `memory_v2.db`. But `PersonaMemoryStore` does not use SQLite.

The actual storage (`Haloysius/src/haloysius/memory_v2/store.py:149-152`):
```python
def _get_data_path(self) -> Path:
    data_dir = state_dir("personas", self.persona_id)
    return data_dir / "memories.json"
```

Memories are stored as a **JSON file** (`memories.json`), loaded into an in-memory dict (`self._memories`), and flushed back to JSON. There is no WAL, no journal mode, no checkpoint. The `VACUUM INTO` / `wal_checkpoint` pipeline is irrelevant for this store — a simple file copy is the correct snapshot mechanism.

The `observations.db` (the FTS5 hybrid search index in `observation_store.py`) IS SQLite, but that is a body-local derived index, deliberately NOT proxied (confirmed in `cognition_wiring.py:228-252`). It should not be replicated.

**Fix**: Replace `memory_v2.db` with `memories.json` throughout. The replication pipeline for persona memory is a file copy + embedding index rebuild, not a SQLite snapshot. The embedding index (`all-MiniLM-L6-v2`) is derived from the JSON and can be rebuilt on the satellite after receiving the JSON — no need to transfer the embedding vectors.

### 6.2 Critical: `conversation.db` should be `conversations.db` (plural)

Every document in this folder uses `conversation.db` (singular). The actual file is `conversations.db` (plural), confirmed at `halbert_core/agents/conversation_sqlite.py:150`:
```python
resolved = Path(data_dir()) / "conversations.db"
```

**Fix**: Global rename to `conversations.db` across all documents.

### 6.3 Critical: `state_ledger.db` and `timeline.db` should NOT be replicated

Section 2's replication set includes `state_ledger.db`. The topology diagram shows it as `(Warm)` on the satellite. But `state-topology.md` section 2B classifies `state_ledger.db` as **host-local**, and the code confirms it (`state_store.py:11-12`):

> *No `persona_id`. Halbert is the machine; there is exactly one subject of these facts. Memory is host-bound.*

Replicating the canonical host's `state_ledger.db` to a satellite gives the satellite **another machine's state changes** — file hashes, config changes, and provenance for hardware the satellite doesn't have. If the satellite is promoted, it should start recording its own machine state from that point forward, not inherit the dead host's state triples.

Same for `timeline.db` — it's a 90-day event flight recorder for this specific body (`cognition_wiring.py:228-252` describes the observation index as deliberately not proxied; `timeline.py:108-118` confirms it's per-body). Replicating it conflates two machines' event histories.

**Fix**: The replication set should be **only entity-level state**: `memories.json` (persona memory) and `conversations.db` (threads). Remove `state_ledger.db` and `timeline.db` from the replication pipeline. They are host-local by design and belong only in the per-node State Vault backup (architecture-blueprint.md Tier B), not in peer replication.

### 6.4 `VACUUM INTO` is not the online backup API

Section 2.1 says: "Calls SQLite's online backup API: `VACUUM INTO '/tmp/halbert_replica_stage/...'`."

These are two different SQLite features:
- **`VACUUM INTO`** — creates a new database file by rewriting all pages. Requires no concurrent writers (acquires an exclusive lock for the duration). Available since SQLite 3.27.
- **Online backup API** (`sqlite3.Connection.backup()`) — copies page-by-page, works concurrently with writers. This is what `architecture-blueprint.md` section 3.3 correctly describes as `sqlite3 source.db ".backup target.db"`.

For `conversations.db` (the only SQLite file that actually needs replication), the online backup API is the right choice because the canonical host may have active writes during the snapshot. `VACUUM INTO` would block writes.

**Fix**: Use the online backup API (`Connection.backup()`) for `conversations.db`, not `VACUUM INTO`. For `memories.json`, just copy the file (the store flushes atomically via temp-file + rename).

### 6.5 No peer heartbeat/liveness mechanism exists

Section 3, Scenario 2 says: "The workstation dashboard notices the canonical heartbeat is lost (> 15 minutes)."

There is no peer liveness detection in the codebase. The existing `heartbeat_s` config in `being.yml` drives the thread-tick loop (`dashboard/app.py`), not peer health monitoring. `PeerConversationStore` and `PeerMemoryBackend` raise on connection failure but do not track liveness state or emit heartbeat events.

**Fix**: Acknowledge that a peer liveness probe needs to be built. A minimal version: periodic `GET /api/conversations/health` poll (the health endpoint already exists, confirmed in `peer_conversation_store.py:22-24`) with a dead-after-N-consecutive-failures threshold. This is the same 3-strike hysteresis pattern already used in `compute_router.py`.

### 6.6 Promotion must clear both `canonical_memory_url` AND `canonical_thread_url`

Section 3, Scenario 2 says: "Clears `canonical_memory_url` in `being.yml`."

But `being.yml` has two canonical URLs (`being_config.py:263-271`):
- `canonical_memory_url` — for `PeerMemoryBackend`
- `canonical_thread_url` — for `PeerConversationStore`

Both must be cleared for the satellite to become self-authoritative. Additionally, the config validator (`being_config.py:376-378`) requires `persona_id_override` when either canonical URL is set:
```python
if (self.canonical_memory_url or self.canonical_thread_url) and not self.persona_id_override:
    raise ValueError(...)
```

Clearing the URLs is safe (the validator only fires when they're set), but the promotion flow should explicitly handle both URLs and document the `persona_id_override` interaction.

**Fix**: Update the promotion steps to clear both `canonical_memory_url` and `canonical_thread_url`. Document that `persona_id_override` can remain set (it's harmless when no canonical URL points anywhere) or be cleared for clarity.

### 6.7 Write buffering during read-fallback is underspecified

Section 3, Scenario 1 says: "New thoughts or user messages are buffered locally in an in-memory queue. Once the Canonical Host comes back online, the queue flushes."

Problems:
1. **No buffering exists.** `PeerMemoryBackend` raises `PeerMemoryUnavailable` on failure — it has no queue. `PeerConversationStore` raises `PeerConversationUnavailable` — same. The queue is a new component that needs to be built.
2. **In-memory queue is volatile.** If the satellite restarts during the outage (OS update, crash), the queue is lost. A disk-backed queue (e.g., a local SQLite WAL table) would survive restarts.
3. **Flush conflict resolution is unaddressed.** If the canonical host was only temporarily down (reboot, not dead), it may have received writes from another satellite during the outage. When the queue flushes, those writes may conflict with the buffered writes. The doc says "zero CRDT merge complexity" but the queue reintroduces exactly the merge problem it claims to avoid.
4. **Conversation writes are order-sensitive.** `append_message`, `update_message`, `move_leaf` are not commutative. Queue flush must replay in order, and the canonical host must not have advanced the thread state in a way that makes the replay invalid.

**Fix**: Either (a) make the queue disk-backed and replay-only-on-clean-reconnect (with a conflict detection check before flush), or (b) drop the write-buffering claim and say the satellite is read-only during canonical host outage — new writes are refused with a clear error message. Option (b) is simpler and honest. The user can still talk to the satellite; it just can't form new memories or threads until the canonical host returns.

### 6.8 "Under 5 seconds" / "3 seconds" promotion is optimistic

Section 1 says "under 5 seconds." Section 3 says "Within 3 seconds." The promotion involves:
- Copying `memories.json` (potentially 50-200 MB for a mature instance) and `conversations.db` (similar) from `canonical_replica/` to `data_dir/`
- Clearing config
- Hot-reloading memory adapters — `PersonaMemoryStore.__init__` calls `_load_from_disk()` (JSON parse) then `_sync_embeddings()` (sentence-transformers model load + embedding computation for all memories)

The embedding model load (`all-MiniLM-L6-v2` via `MemoryEmbedder`) can take 5-15 seconds on first load (model download + PyTorch init) or 2-5 seconds on warm cache. The `_sync_embeddings()` call recomputes embeddings for all memories if the embedding store is stale.

**Fix**: Either (a) say "under 30 seconds" to be honest, or (b) say the satellite keeps its embedding index warm (the replica includes the embedding store alongside `memories.json`), so promotion only needs to reload the store without recomputing embeddings. Option (b) is better but requires replicating the embedding store too.

### 6.9 No mention of the embedding model dependency for the satellite

`PersonaMemoryStore` requires `all-MiniLM-L6-v2` (via `haloysius.memory.embeddings.MemoryEmbedder`). The satellite needs this model available to serve as a read-fallback or after promotion. If the satellite has never run a local `PersonaMemoryStore` (it's been a pure proxy), the model may not be cached locally.

**Fix**: The promotion flow should verify the embedding model is available on the satellite. If not, either (a) download it as part of the promotion (adds 90 MB + time), or (b) pre-warm it when the satellite first receives a replica. The replica push is a good trigger to ensure the model is cached.

### 6.10 `POST /api/peers/sync-replica` endpoint doesn't exist

Section 2.1 proposes this endpoint but it doesn't exist in the codebase (confirmed: no matches for `sync-replica` or `sync_replica` outside this document). The research should mark this as a proposed new endpoint, not something that leverages existing infrastructure.

**Fix**: Mark the endpoint as proposed. Note that it needs to be added to `dashboard/routes/peers.py` alongside the existing peer RPC endpoints, with the same bearer-token authentication.

### 6.11 "Transfer Canonical Role back" is the same problem in reverse

Section 3, Scenario 2, step 5 says: "When a new home server mini-PC arrives weeks later, the operator simply installs Halbert on it, pairs it with the workstation, and runs 'Transfer Canonical Role to Home Server', restoring the original topology seamlessly."

This is underspecified. At this point:
- The workstation is the canonical host with new writes since promotion
- The new server is a fresh install with no state
- "Transfer Canonical Role" means: new server becomes canonical, workstation becomes a body
- This requires: workstation pushes its current state to the new server (same replication mechanism), then the new server promotes itself, then the workstation clears its canonical URLs and points them at the new server

This is the same replication + promotion flow, but in reverse. The doc should acknowledge that the "Transfer Canonical Role" operation is symmetric — it's the same promote-and-repoint mechanism, just initiated from the current canonical host instead of from a satellite.

**Fix**: Document the reverse transfer as: (1) new node pairs as a body, (2) current canonical pushes a replica to the new node, (3) new node promotes (same promotion flow), (4) old canonical clears its URLs and points them at the new node, (5) old canonical becomes a body. The old canonical's local state (state_ledger, timeline) stays local — it doesn't transfer.

### 6.12 `cryptography` is NOT "already a transitive dependency"

This is a cross-reference to `architecture-blueprint.md` section 7, which says: "cryptography package for AES-256-GCM (already a transitive dependency via other paths). No new hard dependencies."

This is the same error the multi-node review flagged for SPAKE2+. `cryptography>=42.0` is in the `integrity` optional extra group (`halbert_core/pyproject.toml:96-99`), not a hard dependency. The two hard dependencies are `pyyaml>=6.0` and `requests>=2.31.0` (the subtractive contract). The `cryptography` package is only present if the `integrity` extra is installed.

**Fix**: The backup encryption layer must either (a) use only stdlib crypto (limited — Python's stdlib has `hashlib` but no AES), (b) declare `cryptography` as a new optional extra (`backup` extra group), or (c) use `pyyaml`'s nothing and `requests`'s nothing and hand-roll AES (dangerous). Option (b) is correct: add a `backup` optional extra with `cryptography>=42.0` and `argon2-cffi>=23.0` (see 6.13).

### 6.13 BIP-39 and Argon2id require new dependencies not mentioned

`architecture-blueprint.md` section 3.2 proposes:
- "Recovery Seed (24-word BIP-39)" — no BIP-39 implementation in the codebase. Needs `mnemonic` package or hand-rolled BIP-39 (non-trivial).
- "Argon2id KDF (memory-hard)" — no Argon2 in the codebase. Needs `argon2-cffi` (native extension, platform-specific builds) or hand-rolled Argon2 (very dangerous to hand-roll).

Neither dependency cost is mentioned. Both would be new optional extras at minimum.

**Fix**: Either (a) add both as optional extras in a `backup` group and note the platform-specific build requirement for `argon2-cffi`, or (b) simplify the key derivation to PBKDF2-HMAC-SHA256 (stdlib, no new dependency) and drop BIP-39 in favor of a user-chosen recovery passphrase (simpler, no new dep). Option (b) is more aligned with the subtractive contract.

### 6.14 Stale pairing flow reference (cross-ref from state-topology.md)

`state-topology.md` section 3, Scenario A says: "Re-pairing a replacement machine: install Halbert, run the 4-digit PIN pairing handshake."

The multi-node review (`HANDOFF-REVIEW-2026-09-12.md` finding #1) already established that the pairing flow has been hardened:
- `PairResponse` returns no PIN (SE-16 / R10-F1 fix)
- An explicit approval step is required (`/api/peers/pending/{request_id}/approve`)
- The verify endpoint rejects with 403 if not approved

**Fix**: Update the reference to say "run the pairing handshake (request → approve → verify)" instead of "4-digit PIN pairing handshake."

### 6.15 Summary of corrections needed

| # | Severity | What | Fix |
|---|----------|------|-----|
| 6.1 | **Critical** | `memory_v2.db` doesn't exist; persona memory is `memories.json` (JSON, not SQLite) | Replace with `memories.json`; replication is a file copy, not SQLite snapshot |
| 6.2 | **Critical** | `conversation.db` → `conversations.db` (plural) | Global rename |
| 6.3 | **Critical** | `state_ledger.db` and `timeline.db` are host-local, should not be replicated | Remove from replication set; only entity-level state replicates |
| 6.4 | High | `VACUUM INTO` is not the online backup API | Use `Connection.backup()` for `conversations.db` |
| 6.5 | High | No peer liveness mechanism exists | Acknowledge it needs to be built; use health-endpoint polling + 3-strike hysteresis |
| 6.6 | High | Promotion must clear both `canonical_memory_url` and `canonical_thread_url` | Update promotion steps |
| 6.7 | High | Write buffering is underspecified and reintroduces merge complexity | Either disk-back the queue with conflict detection, or drop write buffering (read-only fallback) |
| 6.8 | Medium | "Under 5 seconds" promotion is optimistic | Say "under 30 seconds" or pre-warm the embedding index |
| 6.9 | Medium | No mention of embedding model dependency on satellite | Verify model availability as part of promotion |
| 6.10 | Low | `POST /api/peers/sync-replica` doesn't exist | Mark as proposed |
| 6.11 | Medium | "Transfer Canonical Role back" is underspecified | Document as symmetric promote-and-repoint |
| 6.12 | High | `cryptography` is not a transitive dependency | Declare as optional extra |
| 6.13 | High | BIP-39 and Argon2id need new dependencies | Use PBKDF2 (stdlib) + recovery passphrase instead |
| 6.14 | Low | Stale pairing flow reference | Update to reflect current approve-then-verify flow |

### 6.16 What the corrected replication pipeline should look like

After fixing the above, the replication set and pipeline become:

**Replicated (entity-level state):**
- `memories.json` — persona memory (JSON file, simple copy)
- `conversations.db` — conversation threads (SQLite, online backup API)

**NOT replicated (host-local by design):**
- `state_ledger.db` — machine state for this body
- `timeline.db` — event recorder for this body
- `findings.db` — system findings for this body
- `observations.db` — search index for this body
- `body.key` — this node's cryptographic identity

**Snapshot pipeline (on canonical host):**
1. Flush `memories.json` — the store already writes atomically (temp-file + rename), so a copy is consistent
2. `conversations.db` — `sqlite3.Connection.backup()` (online backup API, works with concurrent writers)
3. Bundle both into a compressed, signed shard
4. Push to satellites via `POST /api/peers/sync-replica` (proposed endpoint)

**Satellite storage:**
- `~/.local/share/halbert/canonical_replica/memories.json`
- `~/.local/share/halbert/canonical_replica/conversations.db`
- Validate on receipt: JSON parse check for memories, `PRAGMA quick_check` for conversations

**Promotion:**
1. Copy `canonical_replica/memories.json` → `data_dir/personas/<persona_id>/memories.json`
2. Copy `canonical_replica/conversations.db` → `data_dir/conversations.db`
3. Clear `canonical_memory_url` and `canonical_thread_url` in `being.yml`
4. Verify embedding model is available (pre-warm if not)
5. Hot-reload memory adapter and conversation store
6. Estimated time: 10-30 seconds (dominated by embedding model load + JSON parse)
