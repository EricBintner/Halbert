# Implementation Plan: Phase 1 + Phase 2

**Date**: 2026-09-12
**Status**: Draft for review
**Parent**: [`implementation-strategy.md`](implementation-strategy.md) (the full strategy), [`open-questions-resolved.md`](open-questions-resolved.md) (the decisions)

---

## How to Read This

This is the concrete plan: every file, every function signature, every test, in merge order. The strategy doc explains *why*; this doc says *what* and *when*. Each step is a branch that can be reviewed and merged independently.

Steps are grouped into commits. Each commit is independently testable. A step is "done" when its tests pass and it merges clean.

---

## Phase 1: Peer Replication

### Step 1.1 — Snapshot Engine

**Branch**: `feat/replica-snapshot`

**New files**:
- `halbert_core/halbert_core/replica/__init__.py`
- `halbert_core/halbert_core/replica/snapshot.py`
- `halbert_core/tests/replica/__init__.py`
- `halbert_core/tests/replica/test_snapshot.py`

**`replica/snapshot.py`** — public API:

```python
@dataclass
class SnapshotTarget:
    source: Path
    method: Literal["file_copy", "sqlite_backup"]
    name: str  # filename in the staging dir

@dataclass
class SnapshotResult:
    staging_dir: Path
    manifest: dict  # {name: sha256, size, method}
    created_at: str  # ISO 8601

# The replication set — only entity-level state
REPLICATION_TARGETS = [
    SnapshotTarget(
        source=Path(data_dir()) / "personas" / persona_id / "memories.json",
        method="file_copy",
        name="memories.json",
    ),
    SnapshotTarget(
        source=Path(data_dir()) / "conversations.db",
        method="sqlite_backup",
        name="conversations.db",
    ),
]

def create_snapshot(targets: list[SnapshotTarget]) -> SnapshotResult:
    """Snapshot files to a temp staging dir.

    - file_copy: shutil.copy2 (atomic — the store writes via temp+rename)
    - sqlite_backup: sqlite3.Connection.backup() (online, concurrent-writer-safe)
    - SHA-256 each result, build manifest
    - Returns staging dir path + manifest
    """

def create_replication_snapshot() -> SnapshotResult:
    """Convenience: snapshot the standard replication set."""
    return create_snapshot(REPLICATION_TARGETS)
```

**Tests** (`test_snapshot.py`):
- `test_file_copy_snapshot_matches_source` — byte-identical
- `test_sqlite_backup_passes_integrity_check` — `PRAGMA integrity_check` on the copy
- `test_sqlite_backup_excludes_uncommitted_writes` — open a write txn during backup, verify snapshot doesn't include it
- `test_snapshot_works_when_memories_json_missing` — fresh install, no memories yet
- `test_snapshot_works_when_conversations_db_missing` — fresh install, no threads yet
- `test_manifest_records_sha256_and_size` — manifest has correct digests
- `test_snapshot_targets_are_configurable` — pass a custom target list (Phase 2 reuses this)

**No new dependencies.** `sqlite3`, `shutil`, `hashlib`, `tempfile` — all stdlib.

**Merge gate**: `arch -arm64 .venv/bin/python -m pytest halbert_core/tests/replica/test_snapshot.py`

---

### Step 1.2 — Satellite Replica Store

**Branch**: `feat/replica-store` (depends on 1.1)

**New files**:
- `halbert_core/halbert_core/replica/store.py`
- `halbert_core/tests/replica/test_store.py`

**`replica/store.py`** — public API:

```python
@dataclass
class ReplicaMeta:
    source_node_id: str
    created_at: str  # ISO 8601
    memory_count: int  # parsed from memories.json
    thread_count: int  # SELECT count(*) from conversations
    file_digests: dict  # {name: sha256}

class ReplicaStore:
    def __init__(self, replica_dir: Path | None = None):
        """Defaults to ~/.local/share/halbert/canonical_replica/"""

    def receive(self, staging_dir: Path, manifest: dict) -> ReplicaMeta:
        """Validate and store a received snapshot.

        1. Verify SHA-256 of each file against manifest
        2. conversations.db: PRAGMA quick_check
        3. memories.json: json.loads (validate parse)
        4. Atomic swap: write to temp dir, rename over the replica dir
        5. Return metadata
        """

    def meta(self) -> ReplicaMeta | None:
        """Current replica metadata, or None if no replica."""

    def path(self) -> Path:
        """Path to the replica directory."""

    def is_valid(self) -> bool:
        """Quick validity check — files exist and pass quick_check."""
```

**Tests** (`test_store.py`):
- `test_receive_valid_snapshot_stores_and_records_meta`
- `test_receive_corrupt_conversations_db_rejected_old_preserved`
- `test_receive_corrupt_memories_json_rejected_old_preserved`
- `test_receive_wrong_sha256_rejected`
- `test_meta_returns_none_when_no_replica`
- `test_receive_replaces_old_atomically`
- `test_is_valid_returns_false_after_partial_write` (simulate a crash mid-swap)

**Merge gate**: `arch -arm64 .venv/bin/python -m pytest halbert_core/tests/replica/test_store.py`

---

### Step 1.3 — Sync-Replica Endpoint + Push

**Branch**: `feat/replica-sync` (depends on 1.1, 1.2)

**New files**:
- `halbert_core/halbert_core/replica/push.py`
- `halbert_core/tests/replica/test_push.py`
- `halbert_core/tests/replica/test_sync_endpoint.py`

**Modified files**:
- `halbert_core/halbert_core/dashboard/routes/peers.py` — add receive endpoint

**`replica/push.py`**:

```python
@dataclass
class PushReport:
    peer_id: str
    success: bool
    error: str | None = None

def push_snapshot_to_peers(snapshot: SnapshotResult) -> list[PushReport]:
    """POST the snapshot to every non-revoked body peer.

    - Reads peers from PeersConfig.list_peers()
    - Filters: role == "body", revoked == False
    - POST /api/peers/sync-replica with multipart body (snapshot files + manifest)
    - Bearer-token auth (same token as compute peer)
    - Returns per-peer report
    """
```

**New endpoint in `peers.py`**:

```python
@router.post("/api/peers/sync-replica")
async def receive_replica(
    request: Request,
    _auth: None = Depends(require_peer_auth),
) -> Dict[str, Any]:
    """Receive a warm standby replica from the canonical host.

    - Reads multipart body (snapshot files + manifest)
    - Hands to ReplicaStore.receive()
    - Returns {"accepted": true, "meta": {...}} or error
    """
```

**Tests**:
- `test_push_to_mock_satellite_returns_200`
- `test_push_with_wrong_bearer_token_returns_401`
- `test_push_to_unreachable_peer_records_failure_continues_to_next`
- `test_receive_endpoint_validates_and_stores`
- `test_receive_endpoint_rejects_corrupt_bundle_with_400`

**Integration point**: Uses `require_peer_auth` from `federation/peer_middleware.py` (same auth as compute peer link). The `PeersConfig.list_peers()` already filters by role and revoked status.

**Merge gate**: `arch -arm64 .venv/bin/python -m pytest halbert_core/tests/replica/test_push.py halbert_core/tests/replica/test_sync_endpoint.py`

---

### Step 1.4 — Periodic Push Trigger

**Branch**: `feat/replica-push-loop` (depends on 1.3)

**New files**:
- `halbert_core/tests/replica/test_push_loop.py`

**Modified files**:
- `halbert_core/halbert_core/replica/push.py` — add `_replica_push_loop`
- `halbert_core/halbert_core/dashboard/app.py` — start the loop for canonical hosts
- `halbert_core/halbert_core/config/being_config.py` — add `replica_push_interval_s` field

**`push.py` addition**:

```python
async def _replica_push_loop(interval_s: float = 21600) -> None:
    """Periodically snapshot and push to peers.

    - Catches per-snapshot failures (logs, continues)
    - Catches per-peer failures (logs, continues to next peer)
    - Cancelled cleanly by app shutdown
    """

def start_replica_push_loop(app, interval_s: float | None = None) -> asyncio.Task | None:
    """Start the push loop if this node is a canonical host.

    Returns None (no task) if this node is not canonical.
    Canonical = no canonical_memory_url set AND has at least one body peer.
    """
```

**`app.py` modification** (in `create_app()`, near line 1417 where `start_thread_tick_heartbeat` is called):

```python
# After the heartbeat task is started:
if _is_canonical_host():
    interval = being_config.replica_push_interval_s  # default 21600 (6h)
    app.state.replica_push_task = asyncio.create_task(
        _replica_push_loop(interval_s=interval)
    )
```

**`being_config.py` addition**:

```python
replica_push_interval_s: int = 21600  # 6 hours, configurable
```

**Tests**:
- `test_push_loop_fires_on_interval`
- `test_push_loop_skips_non_canonical_hosts`
- `test_push_loop_catches_per_peer_failure_continues`
- `test_push_loop_catches_snapshot_failure_continues`
- `test_push_loop_cancellable_on_shutdown`
- `test_interval_reads_from_being_yml`

**Merge gate**: `arch -arm64 .venv/bin/python -m pytest halbert_core/tests/replica/test_push_loop.py`

---

### Step 1.5 — Peer Liveness Probe

**Branch**: `feat/replica-liveness` (depends on 1.2)

**New files**:
- `halbert_core/halbert_core/replica/liveness.py`
- `halbert_core/tests/replica/test_liveness.py`

**`replica/liveness.py`**:

```python
class PeerLivenessProbe:
    """Polls the canonical host's health endpoint.

    3-strike hysteresis (same pattern as compute_router.py):
    - 3 consecutive failures → canonical_reachable = False
    - 1 success → canonical_reachable = True
    """

    def __init__(self, peer_url: str, bearer_token: str, interval_s: float = 30.0):
        self._peer_url = peer_url
        self._token = bearer_token
        self._interval = interval_s
        self._failures = 0
        self._reachable = True
        self._task: asyncio.Task | None = None

    @property
    def canonical_reachable(self) -> bool:
        return self._reachable

    async def start(self) -> None: ...
    async def stop(self) -> None: ...

    async def _poll_once(self) -> bool:
        """GET {peer_url}/api/conversations/health → 200 = alive."""
```

**Tests**:
- `test_three_consecutive_failures_flips_to_unreachable`
- `test_one_success_after_failures_flips_back_to_reachable`
- `test_two_failures_then_success_stays_reachable`
- `test_probe_catches_connection_errors`
- `test_probe_catches_timeouts`
- `test_probe_catches_non_200_responses`
- `test_probe_start_stop_clean`

**Merge gate**: `arch -arm64 .venv/bin/python -m pytest halbert_core/tests/replica/test_liveness.py`

---

### Step 1.6 — Read-Fallback Mode

**Branch**: `feat/replica-fallback` (depends on 1.2, 1.5)

**New files**:
- `halbert_core/halbert_core/replica/fallback.py`
- `halbert_core/tests/replica/test_fallback.py`

**Modified files**:
- `halbert_core/halbert_core/integrations/cognition_wiring.py` — add replica fallback to `_create_memory_store`

**`replica/fallback.py`**:

```python
# Read-only methods that are safe to serve from a stale replica.
# Everything else in PEER_CONVERSATION_METHODS is a write — raise on fallback.
READ_ONLY_METHODS = frozenset({
    "get", "list_conversations", "search",
    "get_thread", "list_threads", "current_open_thread", "get_or_open_thread",
    "list_messages", "recent_messages", "last_turn_id", "pending_notes",
    "list_turns", "search_receipts", "search_snippets",
    "list_somatic_blocks", "get_terminal_block", "list_terminal_blocks",
    "get_terminal_session", "list_terminal_sessions", "list_open_loops",
})

class FallbackConversationStore:
    """Wraps PeerConversationStore with read-fallback to a local replica.

    Writes always go to the peer (or raise if peer is down).
    Reads fall back to the local replica when the peer is unreachable.
    """

    def __init__(self, peer_store: PeerConversationStore, replica: ReplicaStore):
        self._peer = peer_store
        self._replica = replica

    def _invoke(self, method: str, args: list, kwargs: dict) -> Any:
        try:
            return self._peer._invoke(method, args, kwargs)
        except PeerConversationUnavailable:
            if method in READ_ONLY_METHODS:
                return self._replica_invoke(method, args, kwargs)
            raise  # writes don't fall back

    def _replica_invoke(self, method: str, args: list, kwargs: dict) -> Any:
        """Open a read-only SQLite connection to the replica's conversations.db
        and invoke the method locally."""
```

**`cognition_wiring.py` modification** (in `_create_memory_store()`, after the `PeerMemoryBackend` try/except):

```python
# After the existing PeerMemoryBackend fallback:
# Check for a local replica before falling back to empty local store
from ..replica.store import ReplicaStore
replica = ReplicaStore()
if replica.meta() is not None and not _canonical_reachable():
    # Point PersonaMemoryStore at the replica's memories.json
    return PersonaMemoryStore.from_replica_path(replica.path() / "memories.json")
```

**Tests**:
- `test_memory_store_peer_reachable_uses_peer_backend`
- `test_memory_store_peer_unreachable_with_replica_uses_replica`
- `test_memory_store_peer_unreachable_no_replica_uses_local`
- `test_conversation_store_peer_reachable_uses_peer`
- `test_conversation_store_peer_unreachable_read_served_from_replica`
- `test_conversation_store_peer_unreachable_write_raises`
- `test_conversation_store_peer_returns_serves_from_peer_again`

**Merge gate**: `arch -arm64 .venv/bin/python -m pytest halbert_core/tests/replica/test_fallback.py`

---

### Step 1.7 — Promotion Flow + Dashboard Routes

**Branch**: `feat/replica-promotion` (depends on 1.2)

**New files**:
- `halbert_core/halbert_core/replica/promotion.py`
- `halbert_core/halbert_core/dashboard/routes/replica.py`
- `halbert_core/tests/replica/test_promotion.py`

**Modified files**:
- `halbert_core/halbert_core/dashboard/app.py` — mount the replica router

**`replica/promotion.py`**:

```python
@dataclass
class PromotionResult:
    success: bool
    old_canonical_url: str
    replica_timestamp: str
    memory_count: int
    thread_count: int
    error: str | None = None

def promote_to_canonical() -> PromotionResult:
    """Promote this satellite's warm replica to active state.

    1. Verify a replica exists and is valid (ReplicaStore.is_valid())
    2. Copy replica/memories.json → data_dir/personas/<id>/memories.json
    3. Copy replica/conversations.db → data_dir/conversations.db
    4. Clear canonical_memory_url in being.yml
    5. Clear canonical_thread_url in being.yml
    6. Clear the persona memory store cache (cognition_wiring globals)
    7. Return result
    """
```

**`dashboard/routes/replica.py`**:

```python
router = APIRouter()

@router.get("/api/replica/status")
async def replica_status() -> Dict[str, Any]:
    """Replica metadata, liveness state, promotion eligibility."""
    store = ReplicaStore()
    meta = store.meta()
    return {
        "has_replica": meta is not None,
        "replica": meta.__dict__ if meta else None,
        "canonical_reachable": _liveness_probe().canonical_reachable if _liveness_probe() else True,
        "can_promote": meta is not None and store.is_valid(),
    }

@router.post("/api/replica/promote")
async def promote(
    _admin: None = Depends(require_local_admin),
) -> Dict[str, Any]:
    """Promote this satellite to canonical host."""
    result = promote_to_canonical()
    if not result.success:
        raise HTTPException(400, result.error)
    return result.__dict__
```

**`app.py` modification** (near line 1359 where peers.router is mounted):

```python
mount_api(replica.router, tags=["replica"])
```

**Tests**:
- `test_promotion_with_valid_replica_succeeds`
- `test_promotion_with_no_replica_fails`
- `test_promotion_with_corrupt_replica_fails`
- `test_promotion_clears_both_canonical_urls`
- `test_promotion_idempotent_second_run_noop`
- `test_promotion_requires_local_admin`
- `test_replica_status_returns_meta_when_replica_exists`
- `test_replica_status_returns_empty_when_no_replica`

**Merge gate**: `arch -arm64 .venv/bin/python -m pytest halbert_core/tests/replica/test_promotion.py`

---

### Step 1.8 — Dashboard UI: Replica Status + Promotion

**Branch**: `feat/replica-ui` (depends on 1.7)

**New files**:
- `halbert_core/halbert_core/dashboard/frontend/src/components/settings/ReplicaStatus.tsx`
- `halbert_core/halbert_core/dashboard/frontend/src/components/settings/ReplicaStatus.test.tsx`

**Modified files**:
- `halbert_core/halbert_core/dashboard/frontend/src/components/settings/tabs/DevicesTab.tsx` — add ReplicaStatus panel

**`ReplicaStatus.tsx`** — renders:
- When canonical is reachable: "Last synced: 2 hours ago (2,847 memories, 156 threads)" — muted status card
- When canonical is unreachable: banner with "Canonical Host is unreachable. A local replica from 2 hours ago is ready. [Promote to Canonical]"
- Promotion confirmation dialog: "This will make this machine the canonical host. The home server will need to re-pair when it comes back. [Cancel] [Promote]"
- No emoji. Colours from `shared-tokens/tokens.css`.

**Tests**:
- `test_renders_empty_state_when_no_replica`
- `test_renders_status_card_when_replica_exists`
- `test_shows_promotion_banner_when_canonical_unreachable`
- `test_promote_button_calls_post_replica_promote`
- `test_promotion_confirmation_dialog_present`
- Contrast gates pass (`scripts/check_contrast.py`)

**Merge gate**: `npm test --workspace halbert-dashboard` + `npm run typecheck`

---

### Step 1.9 — QR Code in Pairing UI

**Branch**: `feat/qr-pairing` (independent of 1.1-1.8; can merge in parallel)

**New dependency**: `qrcode` (npm) — a tiny JS QR rendering library. Add to `dashboard/frontend/package.json`.

**New files**:
- `halbert_core/halbert_core/dashboard/frontend/src/components/settings/PairingQRCode.tsx`
- `halbert_core/halbert_core/dashboard/frontend/src/components/settings/PairingQRCode.test.tsx`

**Modified files**:
- `halbert_core/halbert_core/dashboard/frontend/src/components/settings/tabs/DevicesTab.tsx` — show QR alongside the pending pairings list

**`PairingQRCode.tsx`**:

```tsx
// Renders a QR code encoding the pairing data:
// {
//   url: canonical_host_url,
//   request_id: pending.request_id,
//   entity: entity_name,
// }
//
// NO PIN. The PIN is the out-of-band secret of the whole handshake —
// it travels "through the person doing the pairing" (peers.py), not
// through a photographable surface. A QR carrying it converts
// physical presence into line of sight (security review 2026-09-13,
// Q8; companion-frontend-handoff §7.3 is authoritative on this and
// this step now matches it).
//
// The QR is generated client-side from the pending pairing data
// already fetched by DevicesTab. No new backend endpoint.
//
// Fallback: the URL + PIN are shown as text below the QR
// for headless machines without a camera.
```

**Tests**:
- `test_renders_qr_code_from_pairing_data`
- `test_shows_text_fallback_below_qr`
- `test_qr_encodes_url_request_id_entity_and_no_pin`

**Merge gate**: `npm test --workspace halbert-dashboard` + `npm run typecheck`

---

## Phase 2: State Vault

### Step 2.1 — Archive Format + Manifest

**Branch**: `feat/backup-manifest`

**New files**:
- `halbert_core/halbert_core/backup/__init__.py`
- `halbert_core/halbert_core/backup/manifest.py`
- `halbert_core/tests/backup/__init__.py`
- `halbert_core/tests/backup/test_manifest.py`

**`backup/manifest.py`**:

```python
BACKUP_SCHEMA_VERSION = 1

@dataclass
class BackupManifest:
    schema_version: int  # always 1 for now
    node_id: str
    entity_name: str
    created_at: str  # ISO 8601
    files: dict  # {path: {sha256, size, encrypted: bool}}
    model_manifest: dict | None  # model slots → URLs + hashes (plaintext)

    def to_json(self) -> str: ...
    @classmethod
    def from_json(cls, s: str) -> "BackupManifest": ...
```

**Archive structure** (tar file):
```
manifest.json                  # plaintext, BackupManifest.to_json()
identity/
  body.key.enc                 # AES-256-GCM encrypted
  did.txt                      # plaintext did:key
config/
  being.yml.enc
  peers.json.enc
  models.yml.enc
  preferences.yml.enc
databases/
  memories.json.enc            # JSON, not SQLite
  conversations.db.enc         # SQLite, online backup
  state_ledger.db.enc          # host-local, per-node
  timeline.db.enc              # host-local, per-node
  findings.db.enc              # host-local, per-node
model-manifest.json            # plaintext, model slots → URLs + SHA-256
```

**Tests**:
- `test_manifest_roundtrips_through_json`
- `test_manifest_validates_required_fields`
- `test_manifest_records_schema_version`

**Merge gate**: `arch -arm64 .venv/bin/python -m pytest halbert_core/tests/backup/test_manifest.py`

---

### Step 2.2 — Encryption Layer

**Branch**: `feat/backup-encrypt` (depends on 2.1)

**Modified files**:
- `halbert_core/pyproject.toml` — add `backup` optional extra

**New files**:
- `halbert_core/halbert_core/backup/encrypt.py`
- `halbert_core/tests/backup/test_encrypt.py`

**`pyproject.toml` addition**:

```toml
backup = [
  "cryptography>=42.0",
]
```

**`backup/encrypt.py`**:

```python
def derive_key(passphrase: str, salt: bytes, iterations: int = 600_000) -> bytes:
    """PBKDF2-HMAC-SHA256. Stdlib only. Zero new hard deps."""
    return hashlib.pbkdf2_hmac("sha256", passphrase.encode(), salt, iterations)

def encrypt_file(plaintext: bytes, key: bytes) -> bytes:
    """AES-256-GCM. Lazy import cryptography; per-file random nonce."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce = os.urandom(12)
    return nonce + AESGCM(key).encrypt(nonce, plaintext, None)

def decrypt_file(ciphertext: bytes, key: bytes) -> bytes:
    """AES-256-GCM decrypt. Nonce is first 12 bytes."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce, body = ciphertext[:12], ciphertext[12:]
    return AESGCM(key).decrypt(nonce, body, None)

def check_crypto_available() -> bool:
    """Can we encrypt? (cryptography installed?)"""
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa
        return True
    except ImportError:
        return False
```

**Tests**:
- `test_pbkdf2_derives_deterministic_key`
- `test_aes_gcm_encrypt_decrypt_roundtrip`
- `test_decrypt_with_wrong_key_raises_invalid_tag`
- `test_check_crypto_available_returns_true_when_installed`
- `test_encrypt_file_lazy_imports_cryptography`

**Merge gate**: `arch -arm64 .venv/bin/python -m pytest halbert_core/tests/backup/test_encrypt.py`

---

### Step 2.3 — Backup Engine

**Branch**: `feat/backup-vault` (depends on 2.1, 2.2, and Phase 1 Step 1.1 for snapshot reuse)

**New files**:
- `halbert_core/halbert_core/backup/vault.py`
- `halbert_core/tests/backup/test_vault.py`

**`backup/vault.py`**:

```python
def create_backup(passphrase: str, export_path: Path) -> Path:
    """Create a .halbert-backup archive at export_path.

    1. Enumerate Tier A: body.key, being.yml, peers.json, models.yml, preferences.yml
    2. Snapshot Tier B:
       - memories.json (file copy — reuse replica/snapshot.py)
       - conversations.db (sqlite backup — reuse replica/snapshot.py)
       - state_ledger.db, timeline.db, findings.db (sqlite backup — same engine)
    3. Derive master key from passphrase (PBKDF2)
    4. Encrypt each file with the master key, per-file random nonce
       (Step 2.2's shape. Key-wrapping buys per-file revocation nobody
       uses in a ~10-member archive — security review 2026-09-13, Q6.4)
    5. Write model-manifest.json (plaintext: model slots → URLs + hashes)
    6. Bundle into tar archive with manifest.json
    7. Write to export_path (atomic: temp file + rename)
    """

def list_backups(export_path: Path) -> list[BackupManifest]:
    """List available archives in the export path."""
```

**Reuses Phase 1**: `replica/snapshot.py`'s `create_snapshot()` with a larger target list (adds `state_ledger.db`, `timeline.db`, `findings.db`).

**Tests**:
- `test_create_backup_writes_archive_with_manifest`
- `test_archive_contains_all_expected_files`
- `test_each_enc_file_decrypts_with_passphrase`
- `test_model_manifest_is_plaintext`
- `test_backup_fresh_install_with_no_memories`
- `test_backup_writes_atomically`
- `test_backup_fails_clearly_without_cryptography`

**Merge gate**: `arch -arm64 .venv/bin/python -m pytest halbert_core/tests/backup/test_vault.py`

---

### Step 2.4 — Restore Engine

**Branch**: `feat/backup-restore` (depends on 2.2, 2.3)

**New files**:
- `halbert_core/halbert_core/backup/restore.py`
- `halbert_core/tests/backup/test_restore.py`

**`backup/restore.py`**:

```python
@dataclass
class RestoreReport:
    entity_name: str
    backup_date: str
    memory_count: int
    thread_count: int
    warnings: list[str]

def restore_backup(archive_path: Path, passphrase: str) -> RestoreReport:
    """Restore from a .halbert-backup archive.

    1. Read manifest, verify schema version
    2. Derive master key from passphrase
    3. Decrypt body.key — validate (INTEG-08: refuse silent regeneration)
    4. Decrypt config files → write to ~/.config/halbert/
    5. Decrypt databases → write to ~/.local/share/halbert/
    6. Check entity name vs current — warn if different
    7. Note: peers added after backup need re-pairing
    8. Return report
    """
```

**Tests**:
- `test_restore_valid_archive_unpacks_all_files`
- `test_restore_wrong_passphrase_fails_no_files_written`
- `test_restore_different_entity_name_warns`
- `test_restore_validates_body_key_integrity`
- `test_restore_idempotent`
- `test_restore_preserves_files_not_in_archive`

**Merge gate**: `arch -arm64 .venv/bin/python -m pytest halbert_core/tests/backup/test_restore.py`

---

### Step 2.5 — Dashboard Routes

**Branch**: `feat/backup-routes` (depends on 2.3, 2.4)

**New files**:
- `halbert_core/halbert_core/dashboard/routes/backup.py`
- `halbert_core/tests/backup/test_routes.py`

**Modified files**:
- `halbert_core/halbert_core/dashboard/app.py` — mount backup router

**`dashboard/routes/backup.py`**:

```python
router = APIRouter()

@router.post("/api/backup/now")
async def backup_now(
    passphrase: str,
    export_path: str,
    _admin: None = Depends(require_local_admin),
) -> Dict[str, Any]:
    """Trigger an on-demand backup."""

@router.get("/api/backup/history")
async def backup_history(
    export_path: str,
    _admin: None = Depends(require_local_admin),
) -> List[Dict[str, Any]]:
    """List available archives in the export path."""

@router.post("/api/backup/restore")
async def restore(
    archive_path: str,
    passphrase: str,
    _admin: None = Depends(require_local_admin),
) -> Dict[str, Any]:
    """Restore from an archive."""

@router.get("/api/backup/config")
async def backup_config() -> Dict[str, Any]:
    """Get backup destination and schedule configuration."""
```

**`app.py` modification**:

```python
mount_api(backup.router, tags=["backup"])
```

**Tests**:
- `test_post_backup_now_creates_archive`
- `test_get_backup_history_lists_archives`
- `test_post_backup_restore_restores_archive`
- `test_all_endpoints_require_local_admin`

**Merge gate**: `arch -arm64 .venv/bin/python -m pytest halbert_core/tests/backup/test_routes.py`

---

### Step 2.6 — CLI

**Branch**: `feat/backup-cli` (depends on 2.3, 2.4)

**Modified files**:
- `halbert_core/pyproject.toml` — add `halbert-backup` and `halbert-restore` entry points
- `halbert_core/halbert_core/dashboard/__main__.py` — add `backup` and `restore` subcommands (or new CLI module)

**`pyproject.toml` addition**:

```toml
halbert-backup = "halbert_core.cli.backup:backup_main"
halbert-restore = "halbert_core.cli.backup:restore_main"
```

**New files**:
- `halbert_core/halbert_core/cli/backup.py`
- `halbert_core/tests/backup/test_cli.py`

**`cli/backup.py`**:

```python
def backup_main():
    """halbert backup --passphrase X --path /mnt/backup"""
    parser = argparse.ArgumentParser(description="Create a Halbert backup archive")
    parser.add_argument("--passphrase", required=True)
    parser.add_argument("--path", required=True, help="Export directory")
    args = parser.parse_args()
    archive = create_backup(args.passphrase, Path(args.path))
    print(f"Backup created: {archive}")

def restore_main():
    """halbert restore --passphrase X --path /mnt/backup/archive.halbert-backup"""
    parser = argparse.ArgumentParser(description="Restore from a Halbert backup archive")
    parser.add_argument("--passphrase", required=True)
    parser.add_argument("--path", required=True, help="Archive file path")
    args = parser.parse_args()
    report = restore_backup(Path(args.path), args.passphrase)
    print(f"Restored: {report.entity_name} ({report.backup_date})")
```

**Tests**:
- `test_cli_backup_creates_archive`
- `test_cli_restore_restores_archive`
- `test_cli_backup_config_shows_current_config`

**Merge gate**: `arch -arm64 .venv/bin/python -m pytest halbert_core/tests/backup/test_cli.py`

---

### Step 2.7 — OOBE: Restore from Backup

**Branch**: `feat/backup-oobe` (depends on 2.5)

**Modified files**:
- `halbert_core/halbert_core/dashboard/frontend/src/components/Onboarding.tsx` — add "Restore from Backup" option
- `halbert_core/halbert_core/dashboard/frontend/src/App.tsx` — handle the restore path in the onboarding gate

**New files**:
- `halbert_core/halbert_core/dashboard/frontend/src/components/onboarding/RestoreFromBackup.tsx`
- `halbert_core/halbert_core/dashboard/frontend/src/components/onboarding/RestoreFromBackup.test.tsx`

**Onboarding flow change** (in `Onboarding.tsx`):

Current flow:
```
welcome → configure → scanning → scan_results → complete
```

New flow:
```
welcome → [Begin Fresh | Restore from Backup]
  Begin Fresh → configure → scanning → scan_results → complete
  Restore from Backup → RestoreFromBackup component → complete
```

**`RestoreFromBackup.tsx`** — renders:
1. File picker: drag-and-drop a `.halbert-backup` file, or browse to a path
2. Passphrase input
3. Preview: shows entity name, memory count, thread count, backup date (fetched from the archive manifest)
4. Confirm button → calls `POST /api/backup/restore`
5. On success: entity wakes up, onboarding completes

**Tests**:
- `test_onboarding_renders_both_options`
- `test_restore_flow_accepts_file_path`
- `test_restore_flow_shows_preview_before_confirming`
- `test_restore_flow_calls_post_backup_restore`
- Contrast gates pass

**Merge gate**: `npm test --workspace halbert-dashboard` + `npm run typecheck`

---

## Merge Order Summary

```
Phase 1 (can start immediately):
  1.1 snapshot engine          ──┐
  1.2 replica store            ──┤
  1.3 sync endpoint + push      ──┤── 1.4 push loop
  1.5 liveness probe            ──┤── 1.6 read-fallback
  1.7 promotion + routes        ──┤── 1.8 dashboard UI
  1.9 QR code (independent)     ──┘

Phase 2 (after Phase 1.1):
  2.1 manifest                  ──┐
  2.2 encryption                ──┤── 2.3 backup engine ──┬── 2.4 restore engine
                                  │                      ├── 2.5 dashboard routes
                                  │                      ├── 2.6 CLI
                                  │                      └── 2.7 OOBE
                                  └── (Phase 1.1 for snapshot reuse)
```

Steps 1.1-1.3 are sequential (each depends on the previous). Steps 1.5, 1.7, and 1.9 can be developed in parallel once 1.2 lands. Phase 2 can start once 1.1 lands (it reuses the snapshot engine).

---

## Test Commands

```bash
# Phase 1
arch -arm64 .venv/bin/python -m pytest halbert_core/tests/replica/

# Phase 2
arch -arm64 .venv/bin/python -m pytest halbert_core/tests/backup/

# Frontend
npm test --workspace halbert-dashboard
npm run typecheck

# From a worktree:
arch -arm64 ./wt_pytest.py halbert_core/tests/replica
arch -arm64 ./wt_pytest.py halbert_core/tests/backup
```
