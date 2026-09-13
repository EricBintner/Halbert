# Industry Survey: Backup, Restore, and Identity Portability

**Date**: 2026-09-12

---

## 1. Apple Quick Start & iCloud Transfer

### UX Flow
1. Bring the new device near an existing unlocked device. An animated particle nebula appears on the new device; the old device opens a camera reticle to scan it (fallback: 6-digit PIN).
2. User enters old device passcode on the new device, unlocking the cryptographic keychain.
3. Choose: *"Transfer Directly"* (peer-to-peer Wi-Fi + Bluetooth) or *"Download from iCloud"*.
4. Face ID / Touch ID re-enrolled locally (biometric templates never leave the Secure Enclave).
5. Two-phase restore:
   - **Phase 1**: Critical state (accounts, databases, SMS, app sandboxes, layout) restores first. Device boots immediately.
   - **Phase 2**: App binaries re-downloaded from App Store in background (placeholder icons with progress rings). Full-resolution photos lazy-download on demand.
6. Old device prompts: *"Erase This iPhone?"*

### Key Architectural Patterns
- **Hardware-sealed keys never transfer**: Biometric templates, Apple Pay device tokens, and Secure Enclave roots stay behind. They're re-enrolled fresh.
- **Heavy assets excluded**: App binaries, OS system files, caches are never backed up. They're commodity downloads.
- **Class-based encryption**: Every file encrypted with a per-file key wrapped by a class key tied to the device's Secure Enclave UID.

---

## 2. Apple Time Machine

### Incremental Mechanics
- Modern macOS uses **APFS snapshots** (instantaneous, copy-on-write).
- **FSEvents** kernel daemon tracks directory-level mutations, allowing incremental sets to be computed in seconds without traversing millions of inodes.
- **Local snapshots**: When disconnected from backup storage, hourly local snapshots are maintained on the internal SSD.

### What's Excluded
- **Signed System Volume**: The immutable, cryptographically sealed OS root. Only the writable Data subvolume is backed up.
- Caches, swap files, Spotlight indexes, VM disk images tagged with `com.apple.metadata:com_apple_backup_excludeItem`.

### Restore Experience
- **In-place**: Boot to Recovery, choose "Restore from Time Machine", replaces the Data volume.
- **Migration Assistant (fresh hardware)**: During setup, prompts *"Transfer Information from a Time Machine Backup"*. Granular checkboxes: User Accounts, Applications, Files, System Settings. Reconstructs POSIX UIDs/GIDs and preserves permissions.

---

## 3. Home Assistant Backup & Restore

### Archive Structure
```
backup_2026_09_12.tar
├── backup.json             # Manifest: HA Core version, date, add-on list
├── homeassistant.tar.gz    # /config directory
│   ├── configuration.yaml
│   ├── secrets.yaml        # Plaintext secrets (passwords, tokens)
│   ├── home-assistant_v2.db# SQLite recorder (sensor history)
│   └── .storage/           # Entity/device registries, auth, OAuth tokens
├── addons/
│   ├── core_mosquitto.tar.gz    # MQTT broker data & credentials
│   └── zigbee2mqtt.tar.gz       # Zigbee network keys, PAN ID, channel
└── folders/
    ├── ssl.tar.gz           # TLS certs & private keys
    └── share.tar.gz
```

### Encryption
- Optional password protection: AES-128/256-CBC via PBKDF2 key derivation.
- Encrypts the entire outer payload. Without the password, nothing is readable.

### OOBE Restore Flow
1. Flash HAOS to fresh hardware. Power on. Navigate to `http://homeassistant.local:8123`.
2. Landing screen: **"Create My Smart Home"** (primary) or **"Restore from a previous backup"** (secondary link).
3. Drag-and-drop the `.tar` file. Enter password if encrypted.
4. Choose Full Restore or Partial (selective add-ons/core).
5. Supervisor unpacks `/config`, re-installs Docker container image tags from the manifest, restores add-on data, reboots.
6. Zigbee pairings, Z-Wave meshes, dashboards, and automations work immediately — no device re-pairing.

### Lesson for Halbert
Home Assistant's OOBE restore is the closest analogy to what Halbert needs. The critical UX insight: **the restore option is a secondary affordance on the very first screen**, not buried in settings. A first-time setup and a restoration are the same onboarding flow.

---

## 4. Synology NAS (Hyper Backup)

### Three Tiers
1. **Configuration Backup (`.dss`, ~1 MB)**: User accounts, password hashes, share ACLs, network settings, scheduled tasks. Restorable in < 30 seconds on a fresh NAS.
2. **Hyper Backup (data + applications)**: Content-Defined Chunking (CDC), cross-version deduplication, client-side AES-256 encryption before transmission. Smart recycle pruning (hourly → daily → weekly).
3. **Active Backup (bare-metal)**: Bootable USB recovery media streams raw partition blocks back to bare-metal drives over LAN.

### Key Pattern
- **Hyper Backup Explorer**: A standalone desktop app that lets users mount and browse multi-version backup repositories on Mac/Windows/Linux *without needing a Synology NAS*. The backup file is self-contained and readable with just a passphrase.

---

## 5. Proxmox Backup Server (PBS)

### Architecture
- **Chunk-based deduplication**: Variable-size chunks (~4 MB) indexed by SHA-256. Identical OS files across 50 VMs stored once.
- **Client-side zero-knowledge encryption**: AES-256-GCM on the hypervisor node *before* network transfer. The backup server is untrusted.
- **Master Key Escrow**: Symmetric keys encrypted with an RSA public master key and embedded in the manifest. If the daily password is lost, the offline RSA private key (stored on paper or in a vault) can decrypt any backup.
- **Live Restore**: VMs boot *immediately* while the rest of the disk restores in the background.

### Lesson for Halbert
The live restore pattern (boot from critical state while heavy assets stream in background) directly maps to the two-phase awakening experience.

---

## 6. Self-Hosted Identity Portability

| Project | Primary State | Export Mechanism | Key Lesson |
|---|---|---|---|
| **Nextcloud** | PostgreSQL + `config.php` (`passwordsalt`, `secret`, `instanceid`) | DB dump + data rsync | Missing `passwordsalt` breaks all password hashes and app tokens. Identity atoms must be backed up atomically. |
| **Immich** | PostgreSQL (`pgvector` for CLIP/face vectors) + original photos | `immich-admin` DB dump + restic | **Derived caches** (thumbnails, ML vectors) can be omitted from backup (shrinks by 60%) but re-computing them takes days of CPU/GPU. |
| **Vaultwarden** | SQLite + `rsa_key.pem` + attachments | Filesystem copy of SQLite | **Zero-knowledge by design**: Server never sees the master key. Client derives key via Argon2id. Restoring on fresh hardware requires zero identity re-negotiation. |
| **TrueNAS** | `truenas.db` (SQLite holding entire system state) | Upload the single SQLite file on fresh install | One database file imports pools, users, shares, tasks, and secrets. The ultimate single-file restore. |

### Architectural Pitfalls
1. **Hardware-Bound Entanglement**: If secrets are sealed to a TPM without an escrow/export key, motherboard failure = permanent data loss.
2. **Domain/URL Lock-In**: Hardcoded FQDNs in config break on subnet or domain changes.
3. **Split-Timestamp Backup**: Separately backing up the database and config at different times leads to salt mismatches and corrupted foreign keys. **Atomic snapshots are essential.**

---

## 7. Technical Review (2026-09-12)

**Reviewer**: Verified against `halbert_core/` and `Haloysius/` source.

### 7.1 Vaultwarden's Argon2id is not a precedent for Halbert using Argon2id

The Vaultwarden row says "Client derives key via Argon2id." This is accurate for Vaultwarden, but citing it as precedent for Halbert using Argon2id (as `architecture-blueprint.md` section 3.2 does) overlooks the dependency cost. Vaultwarden is a Rust project with Argon2 in its dependency tree; Halbert is Python with a subtractive contract (two hard deps). Argon2id in Python requires `argon2-cffi` (native extension) or a hand-rolled implementation. See the architecture-blueprint review (section 8.2) for the full analysis.

**Fix**: Add a note to the Vaultwarden row: "Argon2id is native to Vaultwarden's Rust stack; in Python it requires `argon2-cffi` (native extension). Halbert should use PBKDF2-HMAC-SHA256 (stdlib) instead — see architecture-blueprint.md section 8.2."

### 7.2 Home Assistant stores secrets in plaintext — Halbert should not

The HA backup structure shows `secrets.yaml` (plaintext passwords, tokens) inside the encrypted outer archive. This works for HA because the entire archive is encrypted as one blob. But Halbert's `peers.json` stores only SHA-256 **hashes** (never raw tokens), and `body.key` is a private key that should be separately envelope-encrypted. The HA pattern of "encrypt everything as one blob" is simpler but less granular than Halbert's design needs.

**No fix needed** — this is a difference, not an error. But the architecture-blueprint's per-file encryption model (section 3.2) is the right choice for Halbert, not HA's single-blob model.

### 7.3 The "Atomic snapshots are essential" pitfall (item 3) is correctly identified

This is the most important pitfall for Halbert. The backup must snapshot `memories.json` and `conversations.db` at the same logical point in time. If they're snapshotted separately, the conversation store may reference memories that aren't in the memory snapshot (or vice versa). The online backup API for SQLite and the atomic file copy for JSON both produce consistent point-in-time copies, but they must be coordinated — take both snapshots before either can change.

**No fix needed** — the pitfall is correctly identified. The implementation (in `architecture-blueprint.md` section 3.3) should take both snapshots in quick succession, ideally with a brief write pause on the canonical host.

### 7.4 Apple's "hardware-sealed keys never transfer" pattern is the right model for `body.key`

The survey notes that Apple's Secure Enclave keys stay behind and are re-enrolled fresh. This is the right model for `body.key` on hardware custody (Secure Enclave / TPM). But Halbert's `body.key` also supports file custody (0600 file) and OS keystore (Keychain / Secret Service). The backup must export the private key bytes from whatever custody tier is active, envelope-encrypt them, and re-import on restore. This is a deliberate departure from Apple's "never transfer" model — necessary because Halbert's identity must survive hardware death.

**No fix needed** — the survey correctly identifies the pattern. The architecture-blueprint (section 3.2) correctly unwraps the hardware layer and re-wraps with the portable passphrase for export.
