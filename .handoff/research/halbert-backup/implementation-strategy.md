# Implementation Strategy: Backup & Replication

**Date**: 2026-09-12
**Status**: Plan (not yet committed)
**Builds on**: All five research documents in this folder, incorporating the technical review corrections.
**Parent**: [`README.md`](README.md)

---

## 1. Phasing Decision

**Phase 1: Peer Replication (Warm Standby)** — build first.
**Phase 2: State Vault (Backup Archive)** — build second, reuses Phase 1's snapshot engine.

### Why peer replication first

1. **Solves the acute problem.** The canonical host is a single point of failure today. A dead SSD means total amnesia. Peer replication puts a warm copy on every satellite — the highest-value gap to close.
2. **Simpler.** No encryption, no archive format, no restore UX, no new dependencies. It's a file copy + SQLite online backup + a new endpoint + a liveness probe.
3. **Reuses existing infrastructure.** The peer mesh, bearer tokens, health endpoint, and heartbeat loop all exist. The snapshot engine built here is directly reusable by Phase 2.
4. **No founder decisions blocking.** The encryption KDF choice (PBKDF2 vs Argon2id) and write-fallback behavior are Phase 2 / cross-cutting concerns that don't block Phase 1.

### Why State Vault second

1. **Protects against catastrophic loss** (fire, flood, theft of all hardware) — a different threat than hardware failure.
2. **Needs the encryption layer** — a design decision that benefits from being made with the full archive format in view.
3. **Needs the restore UX** — OOBE integration, which depends on the onboarding wizard existing.
4. **Reuses Phase 1's snapshot engine** — the code that copies `memories.json` and backs up `conversations.db` is the same code, just writing to a different destination.

---

## 2. Corrected Storage Model (Applies to Both Phases)

The technical review established that the research docs had the storage model wrong. This is the corrected model the strategy builds on:

| Store | Format | File | Replicates? | Backup Tier |
|---|---|---|---|---|
| Persona memory | **JSON** | `~/.local/share/halbert/personas/<id>/memories.json` | Yes (entity-level) | Tier B |
| Conversation threads | **SQLite** (WAL) | `~/.local/share/halbert/conversations.db` | Yes (entity-level) | Tier B |
| State ledger | SQLite (WAL) | `~/.local/share/halbert/state_ledger.db` | **No** (host-local) | Tier B (per-node) |
| Timeline | SQLite (WAL) | `~/.local/share/halbert/timeline.db` | **No** (host-local) | Tier B (per-node) |
| Findings | SQLite (WAL) | `~/.local/share/halbert/findings.db` | **No** (host-local) | Tier B (per-node) |
| Observation index | SQLite (WAL) | `~/.local/share/halbert/personas/<id>/observations.db` | **No** (body-local) | Exclude (derived) |
| Body identity | Raw bytes | `~/.local/state/halbert/keys/body.key` | **No** (node identity) | Tier A |
| Peer credentials | JSON | `~/.config/halbert/peers.json` | **No** (host-local) | Tier A |
| Entity config | YAML | `~/.config/halbert/being.yml` | **No** (node config) | Tier A |

**Replication set** (entity-level state that travels between nodes): `memories.json` + `conversations.db`. Nothing else.

**Snapshot mechanism per store**:
- `memories.json` — file copy. `PersonaMemoryStore` writes atomically (temp-file + rename), so a copy is a consistent point-in-time snapshot. No checkpoint needed.
- `conversations.db` — `sqlite3.Connection.backup()` (the online backup API). Works with concurrent writers. `VACUUM INTO` is wrong (exclusive lock).

---

## 3. Phase 1: Peer Replication

### 3.1 Components

```
┌─────────────────────────────────────────────────────────────────────┐
│                    PHASE 1 COMPONENT MAP                             │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  CANONICAL HOST                                                      │
│  ┌───────────────────────┐   ┌───────────────────────┐              │
│  │ replica/snapshot.py   │   │ dashboard/routes/     │              │
│  │  - copy memories.json │   │   peers.py            │              │
│  │  - backup conv.db      │   │  + POST sync-replica  │              │
│  │  - bundle + sign       │   │   (receive on sat.)  │              │
│  └───────┬───────────────┘   └───────────────────────┘              │
│          │ push                                                    │
│  ┌───────▼───────────────┐   ┌───────────────────────┐              │
│  │ replica/push.py       │   │ app.py                │              │
│  │  - iterate peers      │   │  + hook into heartbeat │              │
│  │  - POST to each body  │   │    loop for periodic   │              │
│  └───────────────────────┘   │    push trigger        │              │
│                              └───────────────────────┘              │
│                                                                     │
│  SATELLITE BODY                                                      │
│  ┌───────────────────────┐   ┌───────────────────────┐              │
│  │ replica/store.py      │   │ replica/liveness.py   │              │
│  │  - receive snapshot   │   │  - poll health ep     │              │
│  │  - validate integrity  │   │  - 3-strike hysteresis│              │
│  │  - store in replica/  │   │  - emit status events │              │
│  └───────────────────────┘   └───────────────────────┘              │
│  ┌───────────────────────┐   ┌───────────────────────┐              │
│  │ replica/fallback.py   │   │ replica/promotion.py  │              │
│  │  - read-fallback mode │   │  - copy replica→active│              │
│  │  - wire into cognition│   │  - clear canonical URLs│              │
│  │    wiring + conv store│   │  - hot-reload adapters │              │
│  └───────────────────────┘   └───────────────────────┘              │
│                                                                     │
│  DASHBOARD                                                           │
│  ┌───────────────────────┐                                          │
│  │ dashboard/routes/     │                                          │
│  │   replica.py (new)    │                                          │
│  │  - GET replica/status │                                          │
│  │  - POST replica/      │                                          │
│  │    promote            │                                          │
│  └───────────────────────┘                                          │
└─────────────────────────────────────────────────────────────────────┘
```

### 3.2 Implementation Steps (Ordered)

Each step is independently testable and mergeable.

#### Step 1: Snapshot Engine (`replica/snapshot.py`)

**What**: A function that produces a consistent point-in-time bundle of entity-level state.

```python
def create_entity_snapshot(data_dir: Path) -> Path:
    """Snapshot memories.json + conversations.db to a staging dir.

    - memories.json: atomic file copy (the store writes via temp+rename)
    - conversations.db: sqlite3.Connection.backup() (online backup API)
    - Returns path to a staging directory containing both files + a manifest
    """
```

**Files**:
- New: `halbert_core/halbert_core/replica/__init__.py`
- New: `halbert_core/halbert_core/replica/snapshot.py`
- New: `halbert_core/tests/replica/test_snapshot.py`

**Tests**:
- Snapshot of `memories.json` matches the source byte-for-byte
- Snapshot of `conversations.db` passes `PRAGMA integrity_check`
- Snapshot is consistent even with a concurrent writer (open a write transaction during backup, verify the snapshot doesn't include uncommitted writes)
- Snapshot works when `memories.json` doesn't exist yet (fresh install)
- Manifest records source node ID, timestamp, file sizes, SHA-256 digests

**No new dependencies.** Uses `sqlite3` (stdlib), `shutil` (stdlib), `hashlib` (stdlib).

#### Step 2: Satellite Replica Store (`replica/store.py`)

**What**: Receives and validates a snapshot on the satellite side.

```python
class ReplicaStore:
    """Stores and validates warm standby replicas on a satellite body."""

    def receive(self, bundle_path: Path) -> ReplicaMeta:
        """Validate and store a received snapshot bundle.

        - Verify SHA-256 digests against the manifest
        - Validate conversations.db with PRAGMA quick_check
        - Validate memories.json parses as JSON
        - Store in ~/.local/share/halbert/canonical_replica/
        - Record replica timestamp and source node ID
        """

    def meta(self) -> Optional[ReplicaMeta]:
        """Metadata about the current local replica, or None."""

    def path(self) -> Path:
        """Path to the replica directory."""
```

**Files**:
- New: `halbert_core/halbert_core/replica/store.py`
- New: `halbert_core/tests/replica/test_store.py`

**Tests**:
- Receive a valid bundle → stored, meta recorded
- Receive a bundle with a corrupted `conversations.db` → rejected, old replica preserved
- Receive a bundle with a corrupted `memories.json` (invalid JSON) → rejected, old replica preserved
- Receive a bundle with a wrong SHA-256 → rejected
- `meta()` returns None when no replica exists
- Receiving a new replica replaces the old one atomically (temp-dir + rename)

#### Step 3: Sync-Replica Endpoint (`dashboard/routes/peers.py`)

**What**: A new endpoint on the canonical host that pushes snapshots to satellites, and a receiving endpoint on the satellite.

The canonical host pushes; the satellite receives. This matches the existing peer mesh pattern (canonical host initiates RPC to bodies).

**Canonical host push** (`replica/push.py`):
```python
def push_snapshot_to_peers(snapshot_path: Path, peers: PeersConfig) -> PushReport:
    """POST the snapshot bundle to every non-revoked body peer.

    Uses the existing bearer-token auth (same as compute peer link).
    POST /api/peers/sync-replica with multipart body.
    Returns a report of which peers accepted, which failed.
    """
```

**Satellite receive** (add to `dashboard/routes/peers.py`):
```python
@router.post("/api/peers/sync-replica")
async def receive_replica(
    request: Request,
    _auth: None = Depends(require_peer_token),
) -> Dict[str, Any]:
    """Receive a warm standby replica from the canonical host.

    - Accepts the snapshot bundle (multipart or streaming body)
    - Hands to ReplicaStore.receive()
    - Returns {"accepted": true, "meta": {...}} or error
    """
```

**Files**:
- New: `halbert_core/halbert_core/replica/push.py`
- Modified: `halbert_core/halbert_core/dashboard/routes/peers.py` (add endpoint)
- New: `halbert_core/tests/replica/test_push.py`
- New: `halbert_core/tests/replica/test_sync_endpoint.py`

**Tests**:
- Push to a mock satellite → 200, bundle received
- Push with a wrong/missing bearer token → 401
- Push to an unreachable peer → failure recorded, other peers still attempted
- Receive endpoint validates the bundle via ReplicaStore
- Receive endpoint rejects a corrupt bundle with 400

**Integration**: Uses `require_peer_token` dependency (same auth as compute peer). The `peers_config.py` already has `list_peers()` with `role` filtering — filter for `role == "body"` and `revoked == False`.

#### Step 4: Periodic Push Trigger (hook into heartbeat loop)

**What**: The canonical host pushes a snapshot every N hours, hooked into the existing heartbeat loop in `app.py`.

The existing `run_thread_tick_loop` (`app.py:953`) runs every `heartbeat_s` (default 60s). The replication push should run on a much longer cadence (every 4-6 hours). Two options:

**Option A (recommended)**: A separate asyncio task alongside the heartbeat, started in `app.py`'s `create_app()`:
```python
# In create_app(), alongside start_thread_tick_heartbeat(app):
if _is_canonical_host():
    app.state.replica_task = asyncio.create_task(
        _replica_push_loop(interval_s=6 * 3600)
    )
```

**Option B**: A cron/systemd timer that hits `POST /api/peers/sync-replica/push` (a new trigger endpoint). More aligned with the "no background daemons" philosophy but requires external scheduling.

Option A is simpler for a single-process deployment. Option B is better for the systemd unit deployment. **Build A first; add B as a trigger endpoint that calls the same push function.**

**Files**:
- Modified: `halbert_core/halbert_core/dashboard/app.py` (start the push loop for canonical hosts)
- New: `halbert_core/halbert_core/replica/push.py` (add `_replica_push_loop`)
- New: `halbert_core/tests/replica/test_push_loop.py`

**Tests**:
- Push loop fires on the configured interval
- Push loop skips non-canonical hosts (no `canonical_memory_url` set, but has body peers)
- Push loop catches and logs per-peer failures without stopping the loop
- Push loop can be cancelled cleanly (like `stop_thread_tick_heartbeat`)

**Trigger events** (all call the same `push_snapshot_to_peers` function):
- Periodic (every 6 hours, configurable via `being.yml: replica_push_interval_s`)
- Pre-update (before `halbert update` — hook into the existing pre-update flow)
- On-demand (`POST /api/peers/sync-replica/push` — dashboard button)

#### Step 5: Peer Liveness Probe (`replica/liveness.py`)

**What**: Detects when the canonical host is unreachable, so the satellite can enter read-fallback mode.

```python
class PeerLivenessProbe:
    """Polls the canonical host's health endpoint and tracks liveness state.

    Uses the 3-strike hysteresis pattern from compute_router.py:
    - 3 consecutive failures → mark canonical as unreachable
    - 1 success → mark canonical as reachable again

    Polls GET /api/conversations/health (already exists on the canonical host).
    """

    def __init__(self, peer_url: str, bearer_token: str, interval_s: float = 30.0):
        ...

    @property
    def canonical_reachable(self) -> bool:
        ...

    async def start(self): ...
    async def stop(self): ...
```

**Files**:
- New: `halbert_core/halbert_core/replica/liveness.py`
- New: `halbert_core/tests/replica/test_liveness.py`

**Tests**:
- 3 consecutive failures → `canonical_reachable` flips to False
- 1 success after failures → `canonical_reachable` flips back to True
- 2 failures then a success → stays True (hysteresis)
- Probe catches connection errors, timeouts, and non-200 responses
- Probe can be started and stopped cleanly

**Pattern**: Same 3-consecutive-failure hysteresis already used in `compute_router.py` for compute peer health. Reuse the pattern, not the code (different context).

#### Step 6: Read-Fallback Mode (`replica/fallback.py`)

**What**: When the canonical host is unreachable, the satellite serves reads from its local replica.

This is the most delicate integration point. It touches two existing systems:
1. `cognition_wiring._create_memory_store()` — currently returns `PeerMemoryBackend` or `PersonaMemoryStore`
2. `ThreadManager`'s store — currently `PeerConversationStore` or `SqliteConversationStore`

**Memory store fallback**:
```python
def _create_memory_store():
    canonical_url = _get_canonical_memory_url()
    if canonical_url:
        try:
            return PeerMemoryBackend(...)
        except ...:
            pass  # fall through

    # NEW: check for a local replica before falling back to empty local store
    replica = ReplicaStore()
    if replica.meta() is not None:
        # Point PersonaMemoryStore at the replica's memories.json
        return PersonaMemoryStore.from_replica(replica.path())

    return PersonaMemoryStore(_get_persona_id())  # existing local fallback
```

**Conversation store fallback**:
The `PeerConversationStore` raises `PeerConversationUnavailable` on transport failure. The fallback needs to catch this and serve from the local replica. This is a wrapper, not a modification to `PeerConversationStore`:

```python
class FallbackConversationStore:
    """Wraps PeerConversationStore with read-fallback to a local replica.

    Writes always go to the peer (or fail if peer is down — see write-fallback
    decision below). Reads fall back to the local replica when the peer is
    unreachable.
    """

    def __init__(self, peer_store: PeerConversationStore, replica: ReplicaStore):
        ...

    def _invoke(self, method, args, kwargs):
        try:
            return self._peer._invoke(method, args, kwargs)
        except PeerConversationUnavailable:
            if method in READ_ONLY_METHODS:
                return self._replica_invoke(method, args, kwargs)
            raise  # writes don't fall back (see write-fallback decision)
```

**Files**:
- New: `halbert_core/halbert_core/replica/fallback.py`
- Modified: `halbert_core/halbert_core/integrations/cognition_wiring.py` (add replica fallback to `_create_memory_store`)
- New: `halbert_core/tests/replica/test_fallback.py`

**Tests**:
- Memory store: peer reachable → `PeerMemoryBackend` used (existing behavior)
- Memory store: peer unreachable, replica exists → `PersonaMemoryStore` loaded from replica
- Memory store: peer unreachable, no replica → local `PersonaMemoryStore` (existing behavior)
- Conversation store: peer reachable → `PeerConversationStore` used
- Conversation store: peer unreachable, read method → served from replica
- Conversation store: peer unreachable, write method → `PeerConversationUnavailable` raised (read-only fallback)
- Conversation store: peer comes back → seamlessly switches back to peer

**Read-only method set**: The `PEER_CONVERSATION_METHODS` frozenset in `peer_conversation_store.py:66-85` needs to be split into read methods (safe to fallback) and write methods (not safe). Read methods: `get`, `list_conversations`, `search`, `get_thread`, `list_threads`, `current_open_thread`, `get_or_open_thread`, `list_messages`, `recent_messages`, `last_turn_id`, `pending_notes`, `list_turns`, `search_receipts`, `search_snippets`, `list_somatic_blocks`, `get_terminal_block`, `list_terminal_blocks`, `get_terminal_session`, `list_terminal_sessions`, `list_open_loops`. Write methods: everything else.

#### Step 7: Promotion Flow (`replica/promotion.py`)

**What**: When the canonical host is dead, the satellite promotes itself to canonical.

```python
def promote_to_canonical() -> PromotionResult:
    """Promote this satellite's warm replica to active state.

    Steps:
    1. Verify a replica exists and is valid
    2. Copy replica/memories.json → data_dir/personas/<id>/memories.json
    3. Copy replica/conversations.db → data_dir/conversations.db
    4. Clear canonical_memory_url in being.yml
    5. Clear canonical_thread_url in being.yml
    6. Verify embedding model is available (warn if not)
    7. Signal the daemon to hot-reload memory + conversation adapters
    8. Return result (old canonical URL, replica timestamp, new role)
    """
```

**Files**:
- New: `halbert_core/halbert_core/replica/promotion.py`
- New: `halbert_core/halbert_core/dashboard/routes/replica.py` (dashboard API)
- Modified: `halbert_core/halbert_core/dashboard/app.py` (mount the new router)
- New: `halbert_core/tests/replica/test_promotion.py`

**Dashboard routes**:
```python
# dashboard/routes/replica.py
@router.get("/api/replica/status")
async def replica_status() -> Dict[str, Any]:
    """Replica metadata, liveness state, promotion eligibility."""

@router.post("/api/replica/promote")
async def promote_to_canonical() -> Dict[str, Any]:
    """Promote this satellite to canonical host. Requires local admin."""
```

**Tests**:
- Promotion with a valid replica → files copied, URLs cleared, daemon reloaded
- Promotion with no replica → error, no changes
- Promotion with a corrupt replica → error, no changes
- Promotion clears both `canonical_memory_url` and `canonical_thread_url`
- Promotion is idempotent (running twice is safe — second run is a no-op)
- Promotion requires local admin auth (`require_local_admin`)

**Hot-reload**: The daemon needs to reload its memory adapter and conversation store. The existing `_persona_memory_store` cache in `cognition_wiring.py` is a module-level global — clearing it (`_persona_memory_store = None; _persona_memory_store_failed = False`) forces re-creation on next access. The conversation store is held by `ThreadManager` — the daemon needs to re-create the `ThreadManager` or add a `reload_store()` method.

#### Step 8: Dashboard UI

**What**: The satellite dashboard shows replica status and a promotion button when the canonical host is unreachable.

**Files**:
- New: `halbert_core/halbert_core/dashboard/frontend/src/components/settings/ReplicaStatus.tsx`
- Modified: relevant settings tab to include the replica panel

**UI elements** (no emoji, colours from `shared-tokens/tokens.css`):
- Replica status card: "Last synced: 2 hours ago (2,847 memories, 156 threads)"
- Canonical host liveness indicator (green/reachable, red/unreachable)
- When canonical is unreachable: promotion banner with "Promote to Canonical" button
- Promotion confirmation dialog showing what will happen

**Tests**:
- Component renders with no replica (empty state)
- Component renders with a valid replica (status card)
- Component shows promotion banner when canonical is unreachable
- Promotion button triggers `POST /api/replica/promote`
- Contrast gates pass (`scripts/check_contrast.py`)

### 3.3 Write-Fallback Decision (Deferred)

The review identified two options for write behavior during canonical host outage:

**Option A: Read-only fallback (recommended for Phase 1)**
- Satellite serves reads from its warm replica
- New writes are refused with `PeerConversationUnavailable` / `PeerMemoryUnavailable`
- The user gets a clear error: "The canonical host is unreachable. I can still recall our conversations, but I can't form new memories until it's back."
- **Zero merge complexity.** No queue, no replay, no conflict resolution.
- **Honest.** The satellite doesn't pretend to be canonical; it's a read-only warm standby.

**Option B: Disk-backed write queue (defer to Phase 1.5 or Phase 2)**
- Satellite buffers writes to a local SQLite queue table
- On reconnect, replays the queue in order
- Needs conflict detection: if the canonical host received writes from another satellite during the outage, the replayed writes may conflict
- Conversation writes are order-sensitive (`append_message`, `move_leaf` are not commutative)
- **Recommendation**: Build only if read-only fallback proves insufficient in practice. The canonical host is typically an always-on server; outages are short (reboots, updates). A 30-minute read-only window is acceptable.

**Phase 1 ships with Option A.** The `FallbackConversationStore` (Step 6) raises on writes when the peer is down. The architecture leaves room for Option B later — the `FallbackConversationStore` wrapper is where a write queue would slot in.

### 3.4 What Phase 1 Does NOT Include

- **State Vault archive format** — that's Phase 2
- **Encryption** — peer transport is bearer-token authed HTTP (existing); the replica data is plaintext on the satellite's disk (same security posture as the canonical host's disk)
- **Restore from backup OOBE** — Phase 2
- **Offsite backup** — Phase 2
- **Multi-persona private guest replication** — private guest shards are not replicated in Phase 1 (they're host-local by design; see `multi-persona-and-identity-variations.md` section 3.2)
- **Reverse transfer** (canonical → new hardware) — the promotion flow is symmetric, but the "Transfer Canonical Role" UX is a Phase 2 dashboard feature

---

## 4. Phase 2: State Vault (Backup Archive)

### 4.1 Components

```
┌─────────────────────────────────────────────────────────────────────┐
│                    PHASE 2 COMPONENT MAP                             │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  BACKUP ENGINE (writes archives)                                    │
│  ┌───────────────────────┐   ┌───────────────────────┐              │
│  │ backup/vault.py       │   │ backup/encrypt.py      │              │
│  │  - enumerate tiers    │   │  - abstract KDF iface  │              │
│  │  - snapshot (reuse    │   │  - PBKDF2 impl (stdlib)│              │
│  │    Phase 1 engine)    │   │  - AES-256-GCM (crypto)│              │
│  │  - bundle into archive│   │  - per-file key wrap   │              │
│  │  - write to path      │   │  - lazy import + degrade│            │
│  └───────────────────────┘   └───────────────────────┘              │
│                                                                     │
│  RESTORE ENGINE (reads archives)                                    │
│  ┌───────────────────────┐   ┌───────────────────────┐              │
│  │ backup/restore.py     │   │ backup/manifest.py     │              │
│  │  - decrypt archive     │   │  - archive schema      │              │
│  │  - validate integrity  │   │  - version + node ID   │              │
│  │  - unpack to data dir  │   │  - component list      │              │
│  │  - validate body.key   │   │  - model manifest      │              │
│  └───────────────────────┘   └───────────────────────┘              │
│                                                                     │
│  DASHBOARD + CLI                                                     │
│  ┌───────────────────────┐   ┌───────────────────────┐              │
│  │ dashboard/routes/      │   │ CLI                    │              │
│  │   backup.py            │   │  halbert backup        │              │
│  │  - POST /backup/now    │   │  halbert restore       │              │
│  │  - GET /backup/history │   │  halbert backup config │              │
│  │  - POST /backup/restore│   │                       │              │
│  │  - GET /backup/config  │   │                       │              │
│  └───────────────────────┘   └───────────────────────┘              │
│                                                                     │
│  OOBE INTEGRATION                                                    │
│  ┌───────────────────────┐                                          │
│  │ Onboarding wizard     │                                          │
│  │  + "Restore from      │                                          │
│  │    Backup" option      │                                          │
│  └───────────────────────┘                                          │
└─────────────────────────────────────────────────────────────────────┘
```

### 4.2 Implementation Steps (Ordered)

#### Step 1: Archive Format + Manifest (`backup/manifest.py`)

**What**: Define the `.halbert-backup` archive structure and manifest schema.

The archive is a tar file containing:
```
halbert-<node_id>-<ISO-timestamp>.halbert-backup
├── manifest.json                  # Schema version, node ID, timestamp, component list
├── identity/
│   ├── body.key.enc               # Ed25519 private key, envelope-encrypted
│   └── did.txt                    # Plaintext did:key (public, for verification)
├── config/
│   ├── being.yml.enc              # Persona definitions, canonical URLs, peer token
│   ├── peers.json.enc             # Peer credential hashes, endpoints
│   ├── models.yml.enc             # Model slot configuration (includes cloud API keys — Tier 2)
│   ├── preferences.yml.enc        # User preferences (ai_name source)
│   ├── personas/                  # Costume persona definitions
│   └── private_enclaves/          # Private guest shards (separately encrypted)
├── databases/
│   ├── memories.json.enc          # Persona memory (JSON, not SQLite)
│   ├── conversations.db.enc       # Conversation threads (SQLite, online backup)
│   ├── state_ledger.db.enc        # Machine state (host-local, per-node)
│   ├── timeline.db.enc            # Event recorder (host-local, per-node)
│   └── findings.db.enc            # System findings (host-local, per-node)
└── model-manifest.json            # NOT encrypted. Model slots → download URLs + SHA-256
```

**Key correction from the review**: `memories.json.enc` (not `persona_memory.db.enc`), `conversations.db.enc` (plural). Cloud API keys are in the encrypted `models.yml.enc`, not the plaintext `model-manifest.json`.

**Files**:
- New: `halbert_core/halbert_core/backup/__init__.py`
- New: `halbert_core/halbert_core/backup/manifest.py`
- New: `halbert_core/tests/backup/test_manifest.py`

**Tests**:
- Manifest round-trips through JSON serialize/deserialize
- Manifest records schema version, node ID, timestamp, file list with digests
- Manifest validates required fields on load

#### Step 2: Encryption Layer (`backup/encrypt.py`)

**What**: An abstracted encryption interface with a PBKDF2 implementation (stdlib) and an Argon2id implementation (optional extra).

```python
class KeyDerivation(Protocol):
    """Abstract KDF — pick the implementation when Phase 2 Step 2 is built."""
    def derive_key(self, passphrase: str, salt: bytes) -> bytes: ...

class PBKDF2Derivation:
    """PBKDF2-HMAC-SHA256. Stdlib only. Zero new dependencies."""
    def derive_key(self, passphrase: str, salt: bytes,
                   iterations: int = 600_000) -> bytes:
        return hashlib.pbkdf2_hmac("sha256", passphrase.encode(), salt, iterations)

class Argon2idDerivation:
    """Argon2id via argon2-cffi. Optional extra (backup group)."""
    def derive_key(self, passphrase: str, salt: bytes) -> bytes:
        from argon2 import low_level  # lazy import
        return low_level.hash_secret_raw(...)

def encrypt_file(plaintext: bytes, master_key: bytes) -> bytes:
    """AES-256-GCM. Lazy import cryptography; per-file nonce."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce = os.urandom(12)
    aes = AESGCM(master_key)
    return nonce + aes.encrypt(nonce, plaintext, None)

def decrypt_file(ciphertext: bytes, master_key: bytes) -> bytes:
    """AES-256-GCM decrypt. Nonce is the first 12 bytes."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce, body = ciphertext[:12], ciphertext[12:]
    return AESGCM(master_key).decrypt(nonce, body, None)
```

**Dependency strategy**:
- `cryptography>=42.0` — required for AES-256-GCM. Add as a `backup` optional extra. Lazy import; refuse to create encrypted archives if absent (the archive contains `body.key` — encryption is mandatory, not optional).
- `argon2-cffi>=23.0` — optional, only if Argon2id is chosen. Add as a `backup` optional extra. PBKDF2 is the fallback.
- No BIP-39. A user-chosen recovery passphrase replaces the mnemonic seed.

**Files**:
- New: `halbert_core/halbert_core/backup/encrypt.py`
- Modified: `halbert_core/pyproject.toml` (add `backup` optional extra)
- New: `halbert_core/tests/backup/test_encrypt.py`

**Tests**:
- PBKDF2 derivation produces a deterministic key for the same passphrase + salt
- AES-256-GCM encrypt/decrypt round-trips
- Decrypt with wrong key raises `InvalidTag`
- Lazy import: `encrypt_file` raises a clear error if `cryptography` is not installed
- Argon2id derivation (if `argon2-cffi` is installed) produces a deterministic key
- Argon2id derivation gracefully falls back to PBKDF2 if `argon2-cffi` is absent

#### Step 3: Backup Engine (`backup/vault.py`)

**What**: Enumerate state tiers, snapshot, encrypt, bundle into a `.halbert-backup` archive, write to a path.

```python
def create_backup(passphrase: str, export_path: Path) -> Path:
    """Create a .halbert-backup archive at export_path.

    1. Enumerate Tier A (config files, body.key, peers.json)
    2. Snapshot Tier B (memories.json file copy, conversations.db online backup,
       state_ledger.db, timeline.db, findings.db)
    3. Derive master key from passphrase (PBKDF2 or Argon2id)
    4. Encrypt each file with per-file keys wrapped by master key
    5. Write model-manifest.json (plaintext: model slots → URLs + hashes)
    6. Bundle into tar archive with manifest.json
    7. Write to export_path
    """
```

**Reuses Phase 1**: The snapshot of `memories.json` and `conversations.db` uses the same `replica/snapshot.py` functions. The backup engine adds the remaining Tier B databases (`state_ledger.db`, `timeline.db`, `findings.db`) which are host-local and use the same SQLite online backup API.

**Files**:
- New: `halbert_core/halbert_core/backup/vault.py`
- New: `halbert_core/tests/backup/test_vault.py`

**Tests**:
- Create backup → archive exists, manifest is valid JSON
- Archive contains all expected files
- Each `.enc` file decrypts with the passphrase
- `model-manifest.json` is plaintext and contains model slot → URL mappings
- Backup of a fresh install (no memories, no conversations) works
- Backup writes atomically (temp file + rename)
- Backup fails clearly if `cryptography` is not installed

#### Step 4: Restore Engine (`backup/restore.py`)

**What**: Decrypt and unpack a `.halbert-backup` archive into the appropriate directories.

```python
def restore_backup(archive_path: Path, passphrase: str) -> RestoreReport:
    """Restore from a .halbert-backup archive.

    1. Read manifest, verify schema version
    2. Derive master key from passphrase
    3. Decrypt and validate body.key (refuse silent regeneration — INTEG-08)
    4. Decrypt config files → write to ~/.config/halbert/
    5. Decrypt databases → write to ~/.local/share/halbert/
    6. Validate entity name — warn if different from current
    7. Validate peers.json — note satellites added after backup need re-pairing
    8. Signal daemon to reload
    9. Return report (what was restored, what was skipped, warnings)
    """
```

**Key invariants**:
- `body.key` is validated before use (INTEG-08: "A restored `body.key` must be validated before use. A missing key on restore is a fatal error, not a silent regeneration.")
- Entity name safeguard: if the current node's name differs from the archive's, warn before overwriting
- `peers.json` restoration preserves satellite relationships; satellites added after the backup need re-pairing

**Files**:
- New: `halbert_core/halbert_core/backup/restore.py`
- New: `halbert_core/tests/backup/test_restore.py`

**Tests**:
- Restore a valid archive → all files unpacked to correct locations
- Restore with wrong passphrase → clear error, no files written
- Restore an archive with a different entity name → warning emitted
- Restore validates `body.key` (refuses a corrupt key)
- Restore is idempotent (restoring the same archive twice is safe)
- Restore preserves existing files not in the archive (doesn't wipe the data dir)

#### Step 5: Dashboard Routes (`dashboard/routes/backup.py`)

**What**: API endpoints for backup management.

```python
@router.post("/api/backup/now")
async def backup_now(passphrase: str, export_path: str) -> Dict[str, Any]:
    """Trigger an on-demand backup."""

@router.get("/api/backup/history")
async def backup_history() -> List[Dict[str, Any]]:
    """List available archives in the configured export path."""

@router.post("/api/backup/restore")
async def restore_backup(archive_path: str, passphrase: str) -> Dict[str, Any]:
    """Restore from an archive. Requires local admin."""

@router.get("/api/backup/config")
async def backup_config() -> Dict[str, Any]:
    """Get backup destination and schedule configuration."""
```

**Files**:
- New: `halbert_core/halbert_core/dashboard/routes/backup.py`
- Modified: `halbert_core/halbert_core/dashboard/app.py` (mount the router)
- New: `halbert_core/tests/backup/test_routes.py`

**Tests**:
- `POST /api/backup/now` creates an archive
- `GET /api/backup/history` lists archives
- `POST /api/backup/restore` restores an archive (requires local admin)
- `GET /api/backup/config` returns current config
- All endpoints require auth

#### Step 6: CLI (`halbert backup`, `halbert restore`)

**What**: Headless backup and restore for SSH/terminal access.

**Files**:
- Modified: `halbert_core/halbert_core/cli.py` (or wherever the CLI entry point lives — check existing CLI structure)
- New: `halbert_core/tests/backup/test_cli.py`

**Tests**:
- `halbert backup --passphrase X --path /mnt/backup` creates an archive
- `halbert restore --passphrase X --path /mnt/backup/archive.halbert-backup` restores
- `halbert backup config` shows current config
- CLI works without the dashboard running

#### Step 7: OOBE Integration

**What**: "Restore from Backup" as a first-run option alongside "Begin Fresh" and "Transfer from Another Halbert."

**Files**:
- Modified: `halbert_core/halbert_core/dashboard/frontend/src/pages/Onboarding.tsx` (or equivalent)
- New: `halbert_core/halbert_core/dashboard/frontend/src/components/onboarding/RestoreFromBackup.tsx`

**UX flow**:
1. User installs Halbert on fresh hardware, navigates to dashboard
2. Landing screen: "Begin Fresh" | "Restore from Backup" | "Transfer from Another Halbert"
3. "Restore from Backup": drag-and-drop a `.halbert-backup` file, or browse to a mounted path
4. Enter passphrase
5. Preview: shows entity name, memory count, thread count, backup date
6. Confirm → restore engine unpacks → daemon reloads
7. Two-phase boot: identity + memories + conversations load first (< 30s); model weights download in background

**Tests**:
- Onboarding renders all three options
- Restore flow accepts a file path
- Restore flow shows a preview before confirming
- Restore flow calls `POST /api/backup/restore`
- Contrast gates pass

### 4.3 Encryption Decision (Deferred to Step 2)

The strategy abstracts the KDF behind a `KeyDerivation` protocol. When Step 2 is built:

1. **Start with PBKDF2** (stdlib, zero deps). PBKDF2-HMAC-SHA256 with 600,000 iterations meets OWASP 2023 recommendations.
2. **Add Argon2id as an optional upgrade** if the `backup` extra with `argon2-cffi` is installed. The manifest records which KDF was used, so restores pick the right one.
3. **No BIP-39.** A user-chosen recovery passphrase is simpler, has no dependency, and is sufficient for a backup archive on user-owned storage.

The `cryptography` package (for AES-256-GCM) is required — the archive contains `body.key`, so encryption is mandatory. Add a `backup` optional extra:
```toml
backup = [
  "cryptography>=42.0",
]
# Optional stronger KDF:
backup-strong-kdf = [
  "argon2-cffi>=23.0",
]
```

---

## 5. Cross-Cutting Concerns

### 5.1 Snapshot Engine Reuse

Phase 1's `replica/snapshot.py` snapshots `memories.json` + `conversations.db`. Phase 2's `backup/vault.py` needs to snapshot those plus `state_ledger.db`, `timeline.db`, and `findings.db`. The snapshot engine should be designed to accept a list of files to snapshot, not hardcode the replication set:

```python
def snapshot_files(files: list[SnapshotTarget]) -> Path:
    """Snapshot a list of files. Each target specifies the path and
    snapshot method (file_copy or sqlite_backup)."""

@dataclass
class SnapshotTarget:
    source: Path
    method: Literal["file_copy", "sqlite_backup"]
    destination_name: str
```

Phase 1 calls it with the replication set (2 files). Phase 2 calls it with the backup set (5 files). Same engine, different inputs.

### 5.2 Atomic Snapshot Coordination

The "atomic snapshots are essential" pitfall (industry-survey.md item 3) means `memories.json` and `conversations.db` must be snapshotted at the same logical point in time. If they're snapshotted separately, the conversation store may reference memories that aren't in the memory snapshot.

**Implementation**: Take both snapshots in quick succession. For the replication push, this is fine — the canonical host is the single writer, and the snapshot takes < 1 second. For the backup archive, optionally pause the heartbeat loop briefly during the snapshot to ensure consistency. The online backup API for SQLite and the atomic file copy for JSON both produce consistent point-in-time copies.

### 5.3 Embedding Model Availability

`PersonaMemoryStore` requires `all-MiniLM-L6-v2` (via `haloysius.memory.embeddings.MemoryEmbedder`). A satellite that has been a pure proxy may not have the model cached locally.

**Phase 1 (replication)**: The satellite doesn't need the embedding model for read-fallback — it can serve memories from the JSON file without semantic search (fall back to keyword search only). But promotion requires the model.

**Phase 2 (restore)**: The restore engine should verify the embedding model is available and trigger a download if not. The two-phase boot pattern handles this: identity + memories load first, model weights download in the background.

**Implementation**: Add a `verify_embedding_model()` function that checks if `all-MiniLM-L6-v2` is cached. If not, log a warning and start a background download. The promotion flow calls this function and warns the user if the model isn't ready yet.

### 5.4 No Migrations, No Back-Compat

Per AGENTS.md: "No users yet — do not build migrations or back-compat shims unasked." The backup format starts at schema version 1. No migration code. If the format changes, old archives are unreadable — that's acceptable pre-launch.

### 5.5 Subtractive Contract Compliance

| Dependency | Phase | Type | Status |
|---|---|---|---|
| `sqlite3` | Both | stdlib | Already available |
| `shutil`, `hashlib`, `tarfile`, `json` | Both | stdlib | Already available |
| `cryptography>=42.0` | Phase 2 | optional extra (`backup`) | New optional extra; lazy import |
| `argon2-cffi>=23.0` | Phase 2 | optional extra (`backup-strong-kdf`) | New optional extra; lazy import; PBKDF2 fallback |
| `requests` | Phase 1 | hard dep (already exists) | Used by `PeerConversationStore` already |

**No new hard dependencies.** The subtractive contract (2 hard deps: `pyyaml`, `requests`) is preserved.

---

## 6. Risks and Mitigations

| Risk | Phase | Mitigation |
|---|---|---|
| **Snapshot inconsistency** (memories.json and conversations.db snapshotted at different points) | Both | Take both snapshots in quick succession (< 1s). Optionally pause the heartbeat loop during snapshot. The online backup API and atomic file copy both produce consistent point-in-time copies. |
| **Promotion during canonical host reboot** (false positive — host is coming back) | Phase 1 | The liveness probe uses 3-strike hysteresis (3 consecutive failures over ~90s). A reboot takes longer than 90s to trigger. The promotion UI requires manual confirmation — it's not automatic. |
| **Replica staleness** (satellite promotes with a 6-hour-old replica) | Phase 1 | The replica status card shows the replica timestamp. The promotion dialog explicitly states how old the replica is. The user decides. |
| **Embedding model not cached on satellite** | Phase 1 | Promotion warns if the model isn't available. Read-fallback works without it (keyword search only). |
| **`cryptography` not installed** | Phase 2 | The backup engine refuses to create encrypted archives with a clear error. The `backup` extra is documented as required for backup. |
| **Archive format changes** | Phase 2 | Schema version in manifest. No migration code (pre-launch). Old archives become unreadable — acceptable. |
| **Concurrent backup + write** | Phase 2 | SQLite online backup API handles this. JSON file copy is atomic (temp + rename). No write pause needed. |
| **Large conversation database** (> 500 MB) | Both | The online backup API copies page-by-page. The JSON file copy is a single `shutil.copy2`. Both handle large files fine. Transfer over LAN is < 1s for < 200 MB; may take a few seconds for > 500 MB. |

---

## 7. Testing Strategy

### Phase 1

```
halbert_core/tests/replica/
├── test_snapshot.py        # Step 1: snapshot engine
├── test_store.py            # Step 2: satellite replica store
├── test_push.py             # Step 3: push to peers
├── test_sync_endpoint.py    # Step 3: receive endpoint
├── test_push_loop.py        # Step 4: periodic push trigger
├── test_liveness.py         # Step 5: peer liveness probe
├── test_fallback.py         # Step 6: read-fallback mode
└── test_promotion.py       # Step 7: promotion flow
```

All tests use `arch -arm64 .venv/bin/python -m pytest halbert_core/tests/replica` (or `./wt_pytest.py` from a worktree). Test fixtures redirect `HALBERT_DATA_DIR` to tmp_path. No test touches the production data directory (the existing guard in `conversation_sqlite.py:153-159` enforces this).

### Phase 2

```
halbert_core/tests/backup/
├── test_manifest.py         # Step 1: archive format
├── test_encrypt.py          # Step 2: encryption layer
├── test_vault.py            # Step 3: backup engine
├── test_restore.py          # Step 4: restore engine
├── test_routes.py           # Step 5: dashboard routes
└── test_cli.py              # Step 6: CLI
```

### Frontend

```
halbert_core/halbert_core/dashboard/frontend/src/components/settings/
├── ReplicaStatus.tsx
├── ReplicaStatus.test.tsx
└── onboarding/
    ├── RestoreFromBackup.tsx
    └── RestoreFromBackup.test.tsx
```

Frontend tests: `npm test` and `npm run typecheck` from the root (fans out across workspaces).

---

## 8. Merge Strategy

Each step is a separate commit (or small commit cluster). Steps within a phase can be merged incrementally — each step is independently useful:

**Phase 1 merge order**:
1. Steps 1-2 (snapshot + store) — no user-facing change, but the engine exists and is tested
2. Step 3 (sync endpoint) — the canonical host can push, satellites can receive
3. Step 4 (periodic push) — replication happens automatically
4. Step 5 (liveness) — satellites detect canonical host outages
5. Steps 6-7 (fallback + promotion) — satellites can serve reads and promote
6. Step 8 (dashboard UI) — the user can see and interact with the system

**Phase 2 merge order**:
1. Steps 1-2 (format + encryption) — the archive format and crypto layer exist
2. Steps 3-4 (backup + restore) — archives can be created and restored
3. Steps 5-6 (dashboard + CLI) — the user can trigger backups and restores
4. Step 7 (OOBE) — restore is part of first-run onboarding

---

## 9. Open Questions for the Founder

1. **Replication push interval** — 6 hours is the default. Is that right, or should it be configurable from the start? (Recommend: configurable via `being.yml: replica_push_interval_s`, default 21600.)

2. **Should the satellite's local replica be encrypted at rest?** The canonical host's data is plaintext on its own disk. The satellite's replica is the same data, on the satellite's disk. If the satellite disk is encrypted (FileVault, LUKS), the replica is protected. If not, it's plaintext. Should Halbert add its own encryption layer for the replica, or rely on the OS? (Recommend: rely on OS-level encryption for Phase 1; add replica encryption in Phase 2 if needed.)

3. **Should Phase 2 include the "Transfer from Another Halbert" LAN Quick Start flow?** This is the mDNS-based direct transfer between two live machines. It's a nice UX but adds mDNS discovery + direct TLS transfer. (Recommend: defer to Phase 2.5 — the file-based restore covers the same use case with less machinery.)

4. **Private guest replication** — should private guest shards (`guests/<guest_id>/memories.json`) be replicated to satellites? The multi-persona doc says "NOT by default." Is that the right call for Phase 1? (Recommend: yes, not replicated in Phase 1. Private guests are host-local. If the canonical host dies, private guests are lost unless separately backed up via State Vault.)
