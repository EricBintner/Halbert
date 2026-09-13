# Halbert Backup Architecture & State Recovery — Deep Research

**Location**: `.handoff/research/halbert-backup/`  
**Date**: 2026-09-12  
**Subject**: Comprehensive research on backup mechanisms, disaster recovery, the primary-satellite backup topology, and an Apple-like "restore from backup" onboarding experience for Halbert.

---

## Document Directory

| Document | Focus |
|---|---|
| [`active-passive-replication.md`](active-passive-replication.md) | **★ Current Proposal**: Active-Passive Canonical Peer Replication & Warm Standby Failover. Replaces the vulnerable stateless proxy model with single-writer + periodic peer snapshot streaming. |
| [`state-topology.md`](state-topology.md) | What state lives where across the singular entity model. Replicated vs node-local. What survives a dead node today and what doesn't. |
| [`industry-survey.md`](industry-survey.md) | How Apple (Quick Start, Time Machine), Home Assistant, Synology, Proxmox, and self-hosted projects handle backup, restore, and identity portability. |
| [`architecture-blueprint.md`](architecture-blueprint.md) | Proposed Halbert State Vault architecture: tiered state separation, encryption model, primary-satellite backup topology, and the "Restore from Backup" onboarding UX. |
| [`multi-persona-and-identity-variations.md`](multi-persona-and-identity-variations.md) | How State Vault handles Independent Entities (e.g. Halbert vs Macky-Mac), Costume Facades, and Private Guest Personas with exclusive memory sets. |
| [`implementation-strategy.md`](implementation-strategy.md) | **★ Implementation Plan**: Phased build order (peer replication first, State Vault second), step-by-step with files, tests, and merge strategy. Incorporates all review corrections. |
| [`design-exploration.md`](design-exploration.md) | **★ Design Exploration**: Five variations of the trust model, onboarding flow, and data distribution. Explores QR codes, phone-as-trust-anchor, lease-based auto-failover, and "file is the mind" models. Not a decision — a space map. |
| [`open-questions-resolved.md`](open-questions-resolved.md) | **★ Resolutions**: All open questions from the design exploration, answered through the user's-perspective lens. Includes the iOS companion app spec (theoretical — design the spec, don't build it). |
| [`implementation-plan.md`](implementation-plan.md) | **★ Implementation Plan**: Concrete Phase 1 + Phase 2 plan — every file, function signature, test case, and merge gate, in merge order. The executable version of the strategy. |
| [`companion-frontend-handoff.md`](companion-frontend-handoff.md) | **★ Active Plan**: One Tauri v2 build for tablet, kiosk, and mobile — reuses the existing Voice Mode frontend, gates features by form factor, native Swift only for iOS extension targets. Replaces the SwiftUI approach. |
| [`ios-companion-handoff.md`](ios-companion-handoff.md) | **SUPERSEDED**: Original SwiftUI companion app spec. Backend sections (5-6: `trust_anchor` role, wire contracts) carried forward into the active plan. Frontend sections (7-10) replaced. |
| [`security-review-request.md`](security-review-request.md) | **★ Review Request**: 12 specific security and auth questions for a reviewer, grounded in the actual auth code. Covers `trust_anchor` role, transport security, replica sync, promotion fencing, backup encryption, recovery key custody, QR pairing, voice streaming, staged command approval, lost device, and split-brain. |
| [`security-review-response.md`](security-review-response.md) | **★ Review Response**: Verdicts on all 12 questions, empirically verified against the real `create_app()` mounts. Headline: the peers/approvals/conversations routers sit behind `require_owner`, which rejects peer tokens — pairing is unreachable in production (F-A), the companion app's only working credential would be the owner token (F-B), and the replica push has no defined credential (F-D). Includes a new Step 1.0 and the probe script. |

---

## Key Findings

1. **Halbert's existing five protection layers (pre-edit `.bak`, in-memory checkpoints, canon snapshots, Btrfs rollback, host fleet monitoring) protect the system Halbert manages, but do not protect Halbert itself.** The canonical node is a single point of failure for persona memory and conversation threads.

2. **Halbert's state is small.** The "soul" of a Halbert (identity keys, persona config, learned preferences, conversation history, and memory databases) is typically < 500 MB. Foundation model weights (10–70 GB) are commodity and should never be backed up — they are re-downloaded on demand.

3. **The previous peer sync was a vulnerable stateless proxy, but the active proposal resolves this with Active-Passive Replication.** Instead of satellites being fragile client proxies that get amnesia when the server reboots, the Canonical Host pushes periodic snapshots to paired satellites. Satellites maintain warm read-only standby replicas, allowing graceful read-fallback during outages and one-click promotion if the server dies.

4. **Every successful appliance backup system uses the same pattern**: client-side encryption, user-owned storage (no vendor cloud), modular archive structure, and a two-phase restore (critical state boots instantly, heavy assets rehydrate in the background).

5. **The most natural Halbert UX maps to Apple's Quick Start + Home Assistant's OOBE**: LAN proximity discovery between old and new hardware, or a portable encrypted archive file the user stores on their own NAS/drive/cloud folder.

---

## Technical Review (2026-09-12)

All five documents were scrutinized against the actual codebase (`halbert_core/` and `Haloysius/`). Each document now has a "Technical Review" section appended with specific findings. The summary of cross-cutting issues:

### Critical errors (affect the core design)

1. **PersonaMemoryStore is JSON, not SQLite.** Every document refers to `memory_v2.db` as a SQLite database needing WAL checkpointing. The actual storage is `memories.json` (a JSON file), confirmed at `Haloysius/src/haloysius/memory_v2/store.py:149-152`. The entire SQLite snapshot pipeline (`VACUUM INTO`, `wal_checkpoint`) is irrelevant for persona memory — it's a file copy. Only `conversations.db` is SQLite.

2. **`conversation.db` → `conversations.db` (plural).** The actual file is `conversations.db` (`conversation_sqlite.py:150`). Every document uses the singular form.

3. **`state_ledger.db` and `timeline.db` are host-local, not entity-level.** The active-passive doc includes `state_ledger.db` in the replication set, but `state_store.py:11-12` says "No `persona_id`. Halbert is the machine; there is exactly one subject of these facts. Memory is host-bound." Replicating another machine's state ledger is semantically wrong. Only `memories.json` and `conversations.db` should be replicated.

4. **`cryptography` is not a transitive dependency.** The blueprint says "already a transitive dependency via other paths." It's in the `integrity` optional extra (`pyproject.toml:96-99`), not a hard dep. Must be declared as a new `backup` optional extra.

5. **BIP-39 and Argon2id need new dependencies.** Neither exists in the codebase. Use PBKDF2-HMAC-SHA256 (stdlib) and a recovery passphrase instead — zero new dependencies, aligned with the subtractive contract.

### Design corrections

6. **`VACUUM INTO` is not the online backup API.** Use `sqlite3.Connection.backup()` for `conversations.db` (works with concurrent writers). `VACUUM INTO` acquires an exclusive lock.

7. **No peer liveness mechanism exists.** The "heartbeat lost" detection needs to be built. Use the existing health endpoint + 3-strike hysteresis pattern from `compute_router.py`.

8. **Promotion must clear both `canonical_memory_url` AND `canonical_thread_url`.** The active-passive doc only mentions the memory URL. Both are in `being.yml` (`being_config.py:267,271`).

9. **Write buffering during read-fallback reintroduces merge complexity.** Either disk-back the queue with conflict detection, or drop write buffering (read-only fallback with clear error on new writes).

10. **Archive structures are inconsistent between docs.** The blueprint uses `identity/` + `config/` + `databases/`; the multi-persona doc uses `entity/` + `personas/` + `private_enclaves/`. Reconcile to one.

### What's correct (no action needed)

- The paradigm shift (stateless proxy → warm standby) is the right direction
- `peers.json` stores SHA-256 hashes (confirmed at `peers_config.py:18-21`)
- `body.key` is Ed25519 for `did:key` identity (confirmed at `crypto/storage.py:47-53`)
- The industry survey's patterns (client-side encryption, user-owned storage, two-phase restore) are sound
- The "atomic snapshots are essential" pitfall is correctly identified
- State topology's host-local classification is correct (the error is in the active-passive doc contradicting it)
- The tiered state model (Tier A soul, Tier B memories, Tier C excluded) is sound

### Recommended next steps

1. Fix the storage model first: `memories.json` (JSON, file copy) + `conversations.db` (SQLite, online backup API). Remove `state_ledger.db` and `timeline.db` from the replication set.
2. Decide on encryption: PBKDF2 (stdlib, zero deps) vs Argon2id (new optional extra). Recommended: PBKDF2.
3. Decide on write buffering: read-only fallback (simple, honest) vs disk-backed queue (complex, needs conflict detection). Recommended: read-only fallback for v1.
4. Reconcile the archive structure across all documents.
5. Build the peer liveness probe (health endpoint polling + 3-strike hysteresis).
