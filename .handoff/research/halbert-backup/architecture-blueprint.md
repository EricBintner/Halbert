# Halbert State Vault: Architecture Blueprint

**Date**: 2026-09-12  
**Status**: Research / exploratory — not a committed design

---

## 1. Design Constraints

These are architectural constraints drawn from existing Halbert decisions:

| Constraint | Source | Impact on Backup |
|---|---|---|
| **Tier 2 secrets: scrub before model, local-first** | DECISIONS.md:16 | Secrets must be encrypted at rest in the backup. No model summarization of secret payloads. |
| **Singular entity: canonical host holds memory** | DECISIONS.md:28 | The canonical host is the primary backup source. Satellites proxy — they don't hold authoritative copies. |
| **SQLite WAL handling** | FD-11 (revised) | WAL must be checkpointed (`PRAGMA wal_checkpoint(TRUNCATE)`) before snapshot to avoid backup corruption. |
| **Corrupt key file must not silently mint new identity** | INTEG-08 | A restored `body.key` must be validated before use. A missing key on restore is a fatal error, not a silent regeneration. |
| **Haloysius subtractive contract: 2 hard deps** | AGENTS.md | Backup tooling must not add hard dependencies to `haloysius`. It lives in `halbert_core` or a new optional module. |
| **No managed cloud service** | User direction | Halbert NEVER operates cloud infrastructure. Backups are written to user-owned storage destinations. |

---

## 2. Tiered State Model

```
┌─────────────────────────────────────────────────────────────────────┐
│                        HALBERT STATE TIERS                           │
├─────────────────────────────────────────────────────────────────────┤
│ TIER A: "The Soul" (< 10 MB)                                       │
│  ■ Identity keys (body.key, DID)                                    │
│  ■ Persona definitions (being.yml: body name, voice, traits)        │
│  ■ Peer credentials (peers.json: hashed tokens, endpoints)          │
│  ■ Model slot configuration (models.yml)                            │
│  ■ Preferences (preferences.yml)                                    │
│  ■ Skills and lenses config directories                             │
│  → Backed up on every config change. Strictly encrypted.            │
├─────────────────────────────────────────────────────────────────────┤
│ TIER B: "The Memories" (50 MB – 2 GB)                               │
│  ■ PersonaMemoryStore (autobiography, learned facts, relationships) │
│  ■ conversation.db (all threads, turns, messages, receipts)         │
│  ■ state_ledger.db (machine state change history)                   │
│  ■ timeline.db (90-day event flight recorder)                       │
│  ■ findings.db (active/resolved system findings)                    │
│  ■ Config canon snapshots (data/config/canon/, data/config/snaps/)  │
│  → Incremental daily snapshots. Encrypted.                          │
├─────────────────────────────────────────────────────────────────────┤
│ TIER C: "The Body" (10 – 70 GB) — EXCLUDED FROM BACKUPS            │
│  ○ Foundation model weights (.gguf, .safetensors)                   │
│  ○ Python venv, node_modules, Rust build artifacts                  │
│  ○ Vault markdown projections (deterministically rebuilt)           │
│  ○ OS packages and runtimes                                         │
│  ○ Cache directories                                                │
│  → Re-downloaded on demand. Manifest records model slot → URL/hash. │
└─────────────────────────────────────────────────────────────────────┘
```

**Total portable state: under 2 GB for a mature, heavily-used Halbert instance.** Typically under 500 MB. This is a single USB key. This is a file you email to yourself.

---

## 3. The Backup Archive (`.halbert-backup`)

### 3.1 Archive Structure

```
halbert-2026-09-12T14-00-00Z.halbert-backup
├── manifest.json           # Schema version, node ID, creation timestamp,
│                           # component list, model dependency manifest
├── identity/
│   ├── body.key.enc        # Ed25519 private key, envelope-encrypted
│   ├── did.txt             # Plaintext did:key (public, for verification)
│   └── custody.json        # Custody tier at backup time (file/keychain/tpm)
├── config/
│   ├── being.yml.enc       # Persona definitions, peer token, canonical URLs
│   ├── peers.json.enc      # Peer credential hashes, endpoints, capabilities
│   ├── models.yml.enc      # Model slot configuration
│   ├── preferences.yml.enc # User preferences
│   ├── skills/             # Skill definitions
│   └── lenses/             # Lens definitions
├── databases/
│   ├── persona_memory.db.enc    # SQLite (WAL-checkpointed before snapshot)
│   ├── conversation.db.enc      # SQLite
│   ├── state_ledger.db.enc      # SQLite
│   ├── timeline.db.enc          # SQLite
│   └── findings.db.enc          # SQLite
└── model-manifest.json     # NOT encrypted. Lists model slots → download URLs
                            # and SHA-256 digests for re-hydration.
```

### 3.2 Encryption Envelope

```
┌────────────────────────────────────────────────────────────────┐
│                    ENCRYPTION MODEL                            │
│                                                                │
│  User provides ONE of:                                         │
│  ┌──────────────────┐    ┌──────────────────────────────────┐  │
│  │ Passphrase       │ OR │ Recovery Seed (24-word BIP-39)    │  │
│  │ (daily use)      │    │ (disaster recovery, write down)  │  │
│  └────────┬─────────┘    └──────────────┬───────────────────┘  │
│           │                             │                      │
│           ▼                             ▼                      │
│  ┌──────────────────┐    ┌──────────────────────────────────┐  │
│  │ Argon2id KDF     │    │ BIP-39 → Master Seed → KDF      │  │
│  │ (memory-hard)    │    │                                  │  │
│  └────────┬─────────┘    └──────────────┬───────────────────┘  │
│           │                             │                      │
│           └──────────┬──────────────────┘                      │
│                      ▼                                         │
│            ┌──────────────────┐                                │
│            │ Master Key       │                                │
│            │ (AES-256-GCM)   │                                │
│            └────────┬─────────┘                                │
│                     │                                          │
│            ┌────────┴─────────┐                                │
│            │ Per-file keys    │ (each .enc file gets a         │
│            │ wrapped by       │  unique nonce + per-file key   │
│            │ master key       │  wrapped in the master key)    │
│            └──────────────────┘                                │
└────────────────────────────────────────────────────────────────┘
```

**Hardware decoupling**: On-node, the master key may be sealed to the OS keychain or TPM for daily use. But the *export* archive always unwraps the hardware layer and re-wraps with the portable passphrase/seed key. This ensures no hardware entanglement — any machine with the passphrase can restore.

### 3.3 SQLite Backup Safety

Before including any SQLite database in the archive:

1. `PRAGMA wal_checkpoint(TRUNCATE)` — flush WAL to the main database file, then truncate the WAL.
2. `sqlite3 source.db ".backup target.db"` — use SQLite's online backup API for a consistent point-in-time copy. This is safe even while the database is being written to.
3. Encrypt the copy, not the original.
4. Validate the copy with `PRAGMA integrity_check` before archiving.

---

## 4. Primary-Satellite Backup Topology

### 4.1 Who Backs Up What

```
┌─────────────────────────────────────────────────────────────────┐
│                     BACKUP RESPONSIBILITIES                      │
│                                                                  │
│  CANONICAL HOST (Primary Halbert / HA Server)                    │
│  ┌─────────────────────────────────────────────────────────┐     │
│  │ Backs up:                                               │     │
│  │  ■ Its own Tier A (soul) + Tier B (memories)            │     │
│  │  ■ The shared entity state (persona memory, threads)    │     │
│  │                                                         │     │
│  │ Writes to:                                              │     │
│  │  ■ Local: Btrfs snapshot (hourly, pre-action)           │     │
│  │  ■ Export: .halbert-backup archive to user-designated    │     │
│  │    destination (NAS share, external drive, iCloud Drive  │     │
│  │    folder, Google Drive folder — any mounted path)       │     │
│  └─────────────────────────────────────────────────────────┘     │
│                                                                  │
│  SATELLITE BODY (Workstation, Laptop)                            │
│  ┌─────────────────────────────────────────────────────────┐     │
│  │ Backs up:                                               │     │
│  │  ■ Its own Tier A only (being.yml, body.key, models.yml)│     │
│  │  ■ Its local state_ledger.db and timeline.db            │     │
│  │                                                         │     │
│  │ Does NOT back up:                                       │     │
│  │  ○ Entity persona memory (doesn't hold a copy)          │     │
│  │  ○ Entity conversations (doesn't hold a copy)           │     │
│  │                                                         │     │
│  │ Writes to:                                              │     │
│  │  ■ The canonical host (push a satellite shard)          │     │
│  │  ■ OR local export to same user-designated destination  │     │
│  └─────────────────────────────────────────────────────────┘     │
│                                                                  │
│  NAMING CONVENTION (prevents cloud sync conflicts):              │
│  halbert-<node_id>-<ISO-timestamp>.halbert-backup                │
│  e.g. halbert-homelab-2026-09-12T14-00-00Z.halbert-backup        │
│  e.g. halbert-desk-2026-09-12T14-00-00Z.halbert-backup           │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 Centralized BUT Distributed

The user's vision: "centralized, but also distributed." Here's how:

- **Centralized**: The canonical host is the backup coordinator. It knows the schedule, triggers the snapshots, and writes the primary archive. Satellites push their lightweight shards to the canonical host as part of the backup cycle (or independently).
- **Distributed**: The archive is written to a user-designated storage destination that the user controls. If the user points to an iCloud Drive folder, the file syncs to Apple's infrastructure automatically — Halbert doesn't know or care about the cloud layer. If they point to a NAS SMB share, it's local and fast. If they plug in a USB drive, it works too.

This means:
- Halbert writes a file to a path.
- The user's existing infrastructure (iCloud, Google Drive, Synology, manual USB) handles the off-site distribution.
- Halbert doesn't implement cloud APIs, OAuth flows, or sync engines.

### 4.3 Backup Destinations (User-Owned)

| Destination | How Halbert Sees It | User Setup |
|---|---|---|
| **External USB drive** | A mounted path (`/mnt/backup`, `/Volumes/HalbertBackup`) | Plug it in. Tell Halbert the path. |
| **NAS SMB/NFS share** | A mounted path (`/mnt/nas/halbert-backup`) | Mount the share. Tell Halbert the path. |
| **iCloud Drive folder** | A local path (`~/Library/Mobile Documents/.../Halbert/`) | Create a folder in iCloud Drive. Tell Halbert the path. iCloud handles the sync. |
| **Google Drive folder** | A local path via Google Drive for Desktop | Same pattern. |
| **Restic/Borg repo** | Advanced: Halbert shells out to restic/borg if installed | User configures restic repo. Halbert detects it via the existing `BackupScanner`. |

**Halbert only ever writes to a local filesystem path.** The user's choice of sync/replication infrastructure is their own. This keeps the implementation trivially simple and the dependency footprint at zero.

### 4.4 Schedule

| Event | Trigger | What Happens |
|---|---|---|
| **Config change** | Any write via `write_config.py` | Tier A soul snapshot updated (lightweight, < 1 second). |
| **Hourly** | Cron / systemd timer | Btrfs subvolume snapshot (if available). Local protection only. |
| **Nightly** | Cron / systemd timer | Full `.halbert-backup` archive generated and written to the configured export path. Old archives pruned per retention policy (e.g. keep 7 daily, 4 weekly). |
| **Pre-update** | Before `halbert update` | Full archive as a safety net before software update. |
| **On demand** | Dashboard button or CLI | "Back up now" for the user who's about to do something risky. |

---

## 5. The "Restore from Backup" Onboarding Experience

### 5.1 The Landing Screen

When a user installs Halbert on fresh hardware and navigates to the dashboard for the first time:

```
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│                    Welcome.                                   │
│                                                              │
│        ┌──────────────────────────────────┐                  │
│        │                                  │                  │
│        │   Begin Fresh                    │                  │
│        │   Start with a new identity      │                  │
│        │                                  │                  │
│        └──────────────────────────────────┘                  │
│                                                              │
│        ┌──────────────────────────────────┐                  │
│        │                                  │                  │
│        │   Restore from Backup            │                  │
│        │   Continue from a saved state    │                  │
│        │                                  │                  │
│        └──────────────────────────────────┘                  │
│                                                              │
│        ┌──────────────────────────────────┐                  │
│        │                                  │                  │
│        │   Transfer from Another Halbert  │                  │
│        │   Move your identity over LAN    │                  │
│        │                                  │                  │
│        └──────────────────────────────────┘                  │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### 5.2 Restore from Backup Flow

1. **Select archive**: User drags and drops a `.halbert-backup` file, browses to a mounted path (USB drive, NAS share, cloud folder), or pastes a filesystem path.
2. **Decrypt**: Prompted for passphrase or recovery seed. The manifest is read to show what's inside (node name, backup date, component list).
3. **Preview**: Dashboard shows what will be restored:
   - Identity: `did:key:z6Mk...` (body name: "homelab")
   - Persona memory: 2,847 facts
   - Conversations: 156 threads
   - State changes: 4,102 entries
   - Model slots: 3 configured (weights will be re-downloaded)
4. **Confirm**: User confirms. Restoration unpacks Tier A configs, then Tier B databases.
5. **Two-phase boot** (the Apple pattern):
   - **Phase 1 (< 30 seconds)**: Identity key loaded, persona config applied, databases unpacked. Halbert boots its core daemon and dashboard. It speaks in its restored voice and personality:
     > *"I'm back. My identity and memories have been restored on this new system. I'm downloading my language models now — I'll be fully conversational shortly."*
   - **Phase 2 (background)**: Model weights download per `model-manifest.json`. Progress bars shown in the dashboard. If the user has the models on a local drive, they can point Halbert at them to skip the download.

### 5.3 Transfer from Another Halbert (LAN Quick Start)

For the scenario where both old and new hardware are alive and on the same network:

1. **Discovery**: New Halbert broadcasts mDNS `_halbert-setup._tcp`. Old Halbert discovers it automatically.
2. **Verification**: Old Halbert's dashboard shows: *"A new Halbert at 192.168.1.150 wants to receive your identity."* A 6-digit numeric code is shown on both screens. User confirms they match.
3. **Transfer**: Direct TLS connection streams the State Vault archive over LAN. No intermediate storage needed.
4. **Cutover prompt**: Old Halbert asks: *"Transfer complete. This device is no longer the canonical host. Erase personal data?"* User can choose to keep it as a satellite body, or wipe it clean.

### 5.4 What Happens to Peers After Restore

If the canonical host is restored from backup:
- **`peers.json` contains the SHA-256 hashes of satellite bearer tokens.** As long as the satellites still have their `peer_token` in `being.yml`, they can re-authenticate immediately. No re-pairing needed.
- **If `peers.json` is lost** (backup too old, or excluded from backup), all satellites must re-pair via the 4-digit PIN handshake.
- **If a satellite was added after the backup was taken**, its credentials won't be in `peers.json`. That satellite will need to re-pair.

---

## 6. Open Questions for the Founder

### 6.1 Encryption Passphrase UX
- Should backup encryption be required or optional? Home Assistant makes it optional (bad for security, good for accessibility). Proxmox and Vaultwarden make it mandatory.
- The BIP-39 recovery seed is powerful but intimidating. Is it right for Halbert's audience, or is a simpler "recovery password" (like Apple's iCloud recovery key) better?

### 6.2 Backup Retention
- How many archives to keep? A simple scheme: 7 daily + 4 weekly + 3 monthly = 14 files × ~500 MB = ~7 GB of backup storage.
- Should the user control this, or should it be opinionated defaults?

### 6.3 Satellite Shards
- Should satellites push their local state (state_ledger, timeline) to the canonical host for inclusion in the primary backup? Or are those acceptable losses?
- If a satellite's state_ledger records "why file X changed," losing that on satellite death means losing the provenance of changes made from that machine. Is that acceptable?

### 6.4 When to Introduce This
- Backup is infrastructure. It needs to exist before there are users with data worth losing.
- But it's also invisible infrastructure — nobody evaluates a product by its backup system.
- **Suggested timing**: Implement the archive format and "back up now" button early. Add the scheduled export and OOBE restore flow once the onboarding wizard exists.

### 6.5 Model Manifest Scope
- The `model-manifest.json` records which model slots were configured and where to re-download them. Should this include connection slot configs (the user's API keys for cloud models)?
- If yes, those are Tier 2 secrets and must be in the encrypted section.
- If no, the user re-configures cloud connections after restore.

---

## 7. Implementation Sketch (Not a Plan)

If this moves forward, the rough implementation layers:

1. **`halbert_core/backup/vault.py`** — The State Vault engine. Knows how to:
   - Enumerate all Tier A and Tier B paths.
   - Checkpoint all SQLite databases (`PRAGMA wal_checkpoint(TRUNCATE)` + `.backup`).
   - Bundle into a `.halbert-backup` archive with the manifest.
   - Encrypt with AES-256-GCM via a passphrase-derived key (Argon2id).
   - Write to a configured filesystem path.

2. **`halbert_core/backup/restore.py`** — The restore engine. Knows how to:
   - Validate and decrypt an archive.
   - Unpack Tier A configs and Tier B databases into the appropriate directories.
   - Validate `body.key` integrity and refuse silent regeneration.
   - Signal the core daemon to reload.

3. **`halbert_core/dashboard/routes/backup.py`** — Dashboard API routes:
   - `POST /api/backup/now` — trigger on-demand backup.
   - `GET /api/backup/history` — list available archives.
   - `POST /api/backup/restore` — upload and restore from archive.
   - `GET /api/backup/config` — backup destination and schedule.

4. **Dashboard OOBE integration** — Add "Restore from Backup" to the first-run onboarding flow.

5. **CLI** — `halbert backup` and `halbert restore` for headless / SSH access.

**Dependencies**: Standard library only for the core (`tarfile`, `json`, `sqlite3`, `hashlib`). `cryptography` package for AES-256-GCM (already a transitive dependency via other paths). No new hard dependencies.

---

## 8. Technical Review (2026-09-12)

**Reviewer**: Verified against `halbert_core/` and `Haloysius/` source.

### 8.1 Critical: `cryptography` is NOT "already a transitive dependency"

Section 7 claims: "`cryptography` package for AES-256-GCM (already a transitive dependency via other paths). No new hard dependencies."

This is incorrect. `cryptography>=42.0` is in the `integrity` **optional extra** group (`halbert_core/pyproject.toml:96-99`), not a hard dependency. The two hard dependencies are `pyyaml>=6.0` and `requests>=2.31.0` (the subtractive contract). The `cryptography` package is only present if the `integrity` extra is installed. The multi-node review (`HANDOFF-REVIEW-2026-09-12.md` finding #2) flagged this exact same error for SPAKE2+.

**Fix**: Declare a new `backup` optional extra group in `pyproject.toml`:
```toml
backup = [
  "cryptography>=42.0",
]
```
The backup engine imports `cryptography` lazily and degrades gracefully (no encryption, plaintext archive with a warning) when it's absent. This preserves the subtractive contract.

### 8.2 Critical: BIP-39 and Argon2id require new dependencies not mentioned

Section 3.2 proposes:
- **"Recovery Seed (24-word BIP-39)"** — no BIP-39 implementation exists anywhere in the codebase (confirmed: no matches for `BIP-39|bip39|mnemonic|recovery.*seed`). Requires either the `mnemonic` PyPI package (new dependency) or a hand-rolled BIP-39 implementation (non-trivial, easy to get wrong).
- **"Argon2id KDF (memory-hard)"** — no Argon2 implementation in the codebase (confirmed: no matches for `argon2` outside of `rag/scrapers/security_docs.py` which just documents openssl commands). Requires `argon2-cffi` (native extension, platform-specific builds) or a hand-rolled implementation (dangerous).

Neither dependency cost is mentioned. Both violate the subtractive contract if made hard deps.

**Fix**: Two options:
1. **Simplify (recommended)**: Use PBKDF2-HMAC-SHA256 (Python stdlib, `hashlib.pbkdf2_hmac`) instead of Argon2id. Drop BIP-39 in favor of a user-chosen recovery passphrase. This adds zero dependencies and is sufficient for a backup archive that lives on user-owned storage.
2. **Full crypto (if desired)**: Add a `backup` optional extra with `cryptography>=42.0`, `argon2-cffi>=23.0`, and `mnemonic>=1.1`. Note that `argon2-cffi` is a native extension requiring per-platform builds.

Option 1 is more aligned with the subtractive contract and the threat model (the backup is on user-owned storage, not a cloud service — PBKDF2 with a high iteration count is adequate).

### 8.3 `persona_memory.db.enc` should be `memories.json.enc`

Section 3.1 shows `databases/persona_memory.db.enc` in the archive structure. But `PersonaMemoryStore` stores memories as JSON (`memories.json`), not SQLite. See review of `active-passive-replication.md` section 6.1 for the full evidence.

**Fix**: Rename to `memories.json.enc` in the archive structure. The backup engine copies the JSON file; no SQLite checkpoint is needed for it.

### 8.4 `conversation.db.enc` should be `conversations.db.enc` (plural)

Section 3.1 shows `conversation.db.enc`. The actual file is `conversations.db` (plural), at `conversation_sqlite.py:150`.

**Fix**: Rename to `conversations.db.enc`.

### 8.5 `BackupScanner` reference is misleading

Section 4.3 says: "Restic/Borg repo — Advanced: Halbert shells out to restic/borg if installed. User configures restic repo. Halbert detects it via the existing `BackupScanner`."

`BackupScanner` (`discovery/scanners/backup.py`) is a **discovery scanner** — it detects existing backup configurations on the host (rsync scripts, borg repos, restic repos, etc.) and reports them as discoveries. It does not execute backups or integrate with those tools. Saying "Halbert detects it via the existing `BackupScanner`" conflates discovery with execution.

**Fix**: Remove the `BackupScanner` reference. If Halbert should shell out to restic/borg for its own backups, that's a new integration, not something `BackupScanner` provides. The simpler path (write a `.halbert-backup` file to a path) is already the primary design and doesn't need restic/borg integration.

### 8.6 SQLite backup safety (section 3.3) is correct for `conversations.db` but not needed for `memories.json`

Section 3.3 describes:
1. `PRAGMA wal_checkpoint(TRUNCATE)` — correct for `conversations.db` (SQLite, WAL mode)
2. `sqlite3 source.db ".backup target.db"` — correct for `conversations.db` (online backup API)
3. Encrypt the copy — correct
4. `PRAGMA integrity_check` — correct for `conversations.db`

But `memories.json` doesn't need any of this. It's a JSON file written atomically (temp-file + rename by `PersonaMemoryStore`). A simple file copy is a consistent snapshot.

**Fix**: Split section 3.3 into two paths:
- **`conversations.db`**: Steps 1-4 as written (SQLite online backup).
- **`memories.json`**: Simple file copy (the store's atomic write guarantees consistency). Optionally validate JSON parse after copy.

### 8.7 `state_ledger.db` and `timeline.db` should be in Tier B but NOT in peer replication

Section 2, Tier B includes `state_ledger.db` and `timeline.db` as "Incremental daily snapshots. Encrypted." This is correct for the **State Vault backup** (per-node backup to user-owned storage). But these are host-local and should NOT be in the **peer replication** set (the active-passive doc incorrectly includes `state_ledger.db` in replication — see that doc's review section 6.3).

**No fix needed here** — this document correctly puts them in Tier B for backup purposes. The error is in the active-passive doc, which conflates backup-tier state with replication-tier state.

### 8.8 Open question 6.5: model manifest should NOT include cloud API keys

Section 6.5 asks whether `model-manifest.json` should include connection slot configs (API keys for cloud models). The answer is clearly **no** — those are Tier 2 secrets, and AGENTS.md says:

> **Redaction** — `ingestion/redaction_registry.py`, enforced at the response choke point in `security/display_transport.py`. Scrub deterministically *before* the model.

And:

> **Tier 2 (secrets) is answered by a deterministic template, never a model.**

Cloud API keys are Tier 2 secrets. They should be in the encrypted section (`config/models.yml.enc`), not in the plaintext `model-manifest.json`. The manifest should record only model slot names, download URLs, and SHA-256 digests for local model weights.

**Fix**: Answer the open question: cloud connection configs go in the encrypted `config/models.yml.enc`. The `model-manifest.json` (plaintext) contains only local model slot → URL/hash mappings for weight re-download.

### 8.9 Implementation sketch: `cryptography` import must be lazy

Section 7 says the backup engine uses `cryptography` for AES-256-GCM. If `cryptography` is an optional extra (per fix 8.1), the import must be lazy and the engine must degrade gracefully:

```python
try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False
```

When `HAS_CRYPTO` is False, the backup engine should either (a) refuse to create encrypted archives (and tell the user to install the `backup` extra), or (b) write a plaintext archive with a prominent warning. Option (a) is safer — encryption should be required, not optional, for a backup that contains `body.key`.

**Fix**: Add a note that `cryptography` is imported lazily and the backup engine requires the `backup` extra (refuses to run without it, since the archive contains identity keys).

### 8.10 Summary of corrections

| # | Severity | What | Fix |
|---|----------|------|-----|
| 8.1 | **Critical** | `cryptography` is not a transitive dependency | Declare as `backup` optional extra |
| 8.2 | **Critical** | BIP-39 and Argon2id need new deps | Use PBKDF2 (stdlib) + recovery passphrase |
| 8.3 | **Critical** | `persona_memory.db.enc` → `memories.json.enc` | Rename; JSON file, not SQLite |
| 8.4 | High | `conversation.db.enc` → `conversations.db.enc` | Rename to plural |
| 8.5 | Medium | `BackupScanner` reference is misleading | Remove; it's discovery, not execution |
| 8.6 | Medium | SQLite backup steps don't apply to `memories.json` | Split into JSON-copy and SQLite-backup paths |
| 8.7 | None | `state_ledger.db` in Tier B is correct for backup | No fix (error is in active-passive doc) |
| 8.8 | Medium | Open question 6.5: cloud API keys | Answer: encrypted section, not plaintext manifest |
| 8.9 | Medium | `cryptography` import must be lazy | Add lazy import + require `backup` extra |
