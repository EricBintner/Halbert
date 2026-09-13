# State Vault: Multiple Personas, Independent Entities, and Guest Memory Isolation

**Date**: 2026-09-12  
**Status**: Architecture & Design  
**Parent Document**: [`.handoff/research/halbert-backup/architecture-blueprint.md`](architecture-blueprint.md)  
**Related**: 
- [`DECISIONS.md:28`](../../DECISIONS.md) (Singular Entity vs Independent Node)
- [`.handoff/HANDOFF-SINGULAR-ENTITY-MULTI-BODY-2026-08-31.md`](../HANDOFF-SINGULAR-ENTITY-MULTI-BODY-2026-08-31.md)
- [`.handoff/DESIGN-GUEST-PERSONA-2026-09-06.md`](../DESIGN-GUEST-PERSONA-2026-09-06.md)
- [`.handoff/REVIEW-PRIVATE-MODE-2026-09-06.md`](../REVIEW-PRIVATE-MODE-2026-09-06.md)
- [`.handoff/ANALYSIS-GUEST-SHARING-VS-WHAT-IS-BUILT-2026-09-10.md`](../ANALYSIS-GUEST-SHARING-VS-WHAT-IS-BUILT-2026-09-10.md)

---

## 1. The Core Identity Spectrum

In Halbert, an installation can operate across a spectrum of identity configurations:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            IDENTITY SPECTRUM                                │
├──────────────────────────────┬──────────────────────────────┬───────────────┤
│ 1. Singular Entity           │ 2. Independent Entities      │ 3. Personas & │
│    (One Mind, Multi-Body)    │    (Separate Minds on LAN)   │    Guests     │
│                              │                              │               │
│ • Home = "Halbert"           │ • Home = "Halbert"           │ • Costume     │
│ • Desk = "Halbert (desk)"    │ • Desk = "Macky-Mac"         │   Facade      │
│ • Shared persona_id          │ • Distinct persona_ids       │ • Private     │
│ • Shared memory & threads    │ • Distinct memory & threads  │   Guest       │
│ • One canonical mind         │ • Share GPU/tools, NOT mind  │   (Exclusive) │
└──────────────────────────────┴──────────────────────────────┴───────────────┘
```

The State Vault backup architecture must cleanly handle all three without leaking private memory or entangling separate entities.

---

## 2. Singular Entity vs. Independent Entities ("Macky-Mac")

### 2.1 The Topology Difference

| Dimension | Singular Entity (Default) | Independent Entities (e.g. "Halbert" & "Macky-Mac") |
|---|---|---|
| **`persona_id`** | Identical across devices (`"halbert"`) | Unique per device (`"halbert"` on server, `"macky_mac"` on workstation) |
| **`canonical_memory_url`** | Pointed at Canonical Host on satellites | **Unset** on all devices (`None`) |
| **Memory Store** | Single shared `PersonaMemoryStore` on Canonical Host | Independent `PersonaMemoryStore` on **each machine** |
| **Conversation Threads** | Single shared `conversation.db` on Canonical Host | Independent `conversation.db` on **each machine** |
| **Peer Federation** | Satellites join with `role: "body"` | Nodes join with `role: "compute_provider"` |
| **What is Shared?** | Memory, threads, identity, compute | **Compute only** (GPU offload, terminal commands, MCP tools) |

### 2.2 Backup Behavior: Independent Entities

When devices are separate entities (e.g. Home is "Halbert", Workstation is "Macky-Mac"):

1. **Autonomous Entity Vaults**:
   - Each machine produces its own self-contained `.halbert-backup` archive:
     - `halbert-home-2026-09-12.halbert-backup` (Halbert's soul, memory, threads, host state)
     - `mackymac-workstation-2026-09-12.halbert-backup` (Macky-Mac's soul, memory, threads, host state)
   - Neither vault contains the other's memories, threads, or private keys.
   - Each entity has its own `did:key` cryptographic identity in `identity/body.key.enc`.

2. **Fleet Backup Coordination (From the Workstation Management UI)**:
   - When the operator clicks "Back up fleet" on the Workstation dashboard:
     - The workstation backs up Macky-Mac locally.
     - The workstation issues an authenticated RPC `POST /api/backup/now` to the Home Server.
     - The Home Server packages Halbert's vault and streams it to the workstation or writes it to the designated shared storage path (e.g. NAS share or iCloud Drive folder).
     - Result: Two cleanly separated archives side-by-side in the destination folder.

3. **Restoration Isolation**:
   - If the Home Server dies, restoring `halbert-home-*.halbert-backup` restores Halbert. Macky-Mac is untouched.
   - If the Workstation dies, restoring `mackymac-workstation-*.halbert-backup` restores Macky-Mac with his unique personality, memories, and coding context intact.
   - **No cross-contamination**: A restore operation strictly checks `manifest.json -> entity_name` and `persona_id`. Halbert cannot accidentally be restored over Macky-Mac.

---

## 3. Guest Personas: Costume Facade vs. Private Guest

In Halbert, personas are managed via `~/.config/halbert/personas/*.yml` (registered in `PersonaStore`). There are two distinct classes of guest personas:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          GUEST PERSONA TAXONOMY                             │
├──────────────────────────────────────┬──────────────────────────────────────┤
│ A. Costume Facade (Standard Guest)   │ B. Private Guest (Strict Isolation)  │
│                                      │                                      │
│ • Presentation layer over Halbert    │ • Fully isolated memory & context    │
│ • Shares Halbert's underlying tools  │ • Does NOT write to Halbert's memory │
│ • Normal mode writes to Halbert log  │ • Exclusive database/namespace       │
│ • Example: Custom voice/tone for     │ • Example: Confidentially interacting│
│   kids or home entertainment         │   with external agent (H2 sibling)   │
└──────────────────────────────────────┴──────────────────────────────────────┘
```

### 3.1 Costume Facade (Standard Guest Persona)

- **Definition**: A lightweight personality disguise (e.g., custom name, voice, system prompt directives). Halbert's agent still answers every turn.
- **State Footprint**:
  - Configuration: `~/.config/halbert/personas/<persona_name>.yml` (name, voice profile, greeting, directives).
  - Memory: Writes directly into Halbert's `PersonaMemoryStore` and `conversation.db` (`Owner.HALBERT`).
- **State Vault Handling**:
  - Packed into Tier A (`config/personas/`).
  - Restored automatically whenever Halbert is restored.
  - Zero special encryption requirements beyond the standard backup passphrase.

### 3.2 Private Guest Persona (Fully Exclusive Memory Set)

- **Definition**: A guest persona running in **Private Mode** (e.g., an H2 companion fronting on Halbert, or a sensitive personal persona).
- **The Invariant Law (`I6` / `R2`)**:
  - *"The guest may not read what it may not write."*
  - *"Halbert's own psyche never learns a guest's evenings."*
  - `route_write` redirects `conversation.message` and `cognition.tick` away from Halbert's store to the guest's exclusive store (`Owner.GUEST`).
- **State Footprint**:
  - Configuration: `~/.config/halbert/personas/private_<guest_id>.yml`
  - Exclusive Memory DB: `~/.local/share/halbert/guests/<guest_id>/memory.db`
  - Exclusive Conversation DB: `~/.local/share/halbert/guests/<guest_id>/conversation.db`
  - *Strictly segregated from `memory_v2.db` and `conversation.db`!*

---

## 4. State Vault Packaging for Multiple & Private Personas

### 4.1 Modular Archive Structure

To ensure cryptographic and architectural isolation, the `.halbert-backup` format uses a **modular enclave structure**:

```
halbert-2026-09-12.halbert-backup
├── manifest.json                  # Top-level manifest
├── entity/                        # Primary Entity State
│   ├── identity.enc               # body.key (Ed25519)
│   ├── config.enc                 # being.yml, peers.json, models.yml
│   └── databases/
│       ├── memory.db.enc          # Primary autobiography
│       ├── conversation.db.enc    # Primary threads
│       ├── state_ledger.db.enc    # Machine state
│       └── timeline.db.enc        # Event recorder
├── personas/                      # Public / Costume Personas
│   ├── kids_mode.yml.enc
│   └── butler.yml.enc
└── private_enclaves/              # ISOLATED PRIVATE GUEST SHARDS
    ├── guest_h2_alpha/
    │   ├── manifest.json          # Enclave descriptor (guest_id, cipher_suite)
    │   ├── persona.enc            # Guest persona configuration
    │   ├── memory.db.enc          # Private memory graph (SEPARATELY ENCRYPTED)
    │   └── conversation.db.enc    # Private threads (SEPARATELY ENCRYPTED)
    └── guest_finance/
        ├── manifest.json
        ├── memory.db.enc
        └── conversation.db.enc
```

### 4.2 Key Separation & Multi-Key Unwrapping

How encryption is handled across private enclaves:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        KEY DERIVATION MODEL                            │
│                                                                        │
│  User Master Passphrase                                                │
│         │                                                              │
│         ▼                                                              │
│  Argon2id KDF ─────────► Entity Master Key                             │
│                               │                                        │
│          ┌────────────────────┴───────────────────┐                    │
│          ▼                                        ▼                    │
│   Encrypts Primary                        Encrypts Enclave Key Slot    │
│   Entity & Costumes                       (Optional secondary secret)  │
│   (Halbert / Macky-Mac)                           │                    │
│                                                   ▼                    │
│                                           Private Enclave Key          │
│                                           (guest_h2_alpha memory)      │
└────────────────────────────────────────────────────────────────────────┘
```

1. **Default Mode (Unified Passphrase, Segregated Storage)**:
   - The user's backup passphrase unlocks both the primary entity and the private enclaves.
   - Even though decrypted by the same master key, the storage directories remain strictly segregated on disk upon restoration (`guests/<guest_id>/`).
   - Halbert's cognition tick **never** crawls or indexes the guest's directory.
2. **Strict Privacy Mode (Dual-Secret Enclave)**:
   - A Private Guest can optionally require its **own independent passphrase/PIN** to unlock its enclave inside the backup.
   - If the main backup is restored without entering the private guest's PIN, the private guest shard remains an unreadable ciphertext blob (`guest_h2_alpha.locked`) on disk.
   - Halbert boots normally; the private persona cannot be awakened until its owner supplies the second secret.

---

## 5. Granular Restoration Matrix

When the user restores a `.halbert-backup` file on fresh hardware, the restoration wizard presents a granular restoration manifest:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     RESTORE ENTITY & PERSONAS                           │
├─────────────────────────────────────────────────────────────────────────┤
│ Archive: halbert-home-2026-09-12.halbert-backup                         │
│ Created: September 12, 2026 at 14:00                                    │
│                                                                         │
│ Select components to restore:                                           │
│                                                                         │
│ [X] Primary Entity: Halbert (Canonical Mind)                            │
│     • Identity DID: did:key:z6Mku...                                    │
│     • Memory: 2,847 facts                                               │
│     • Conversations: 156 threads                                        │
│                                                                         │
│ [X] Paired Satellite Mesh (3 devices)                                   │
│     • Workstation (M1 Max), Kitchen Speaker, Garage Node                │
│                                                                         │
│ [X] Costume Personas                                                    │
│     • Butler (voice: en-GB-neural), Kids Mode                           │
│                                                                         │
│ [ ] Private Guest Enclaves (2 detected)                                 │
│     [X] Guest H2 (Requires Passphrase: [ ********** ])                  │
│     [ ] Guest Finance (Excluded from this restore)                      │
│                                                                         │
│ ┌───────────────────────────────────┐ ┌───────────────────────────────┐ │
│ │ Restore Selected Components       │ │ Cancel                        │ │
│ └───────────────────────────────────┘ └───────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
```

### Invariants Maintained
1. **No Accidental Promotion**: A private guest's memories are never dumped into `memory_v2.db`. They are restored strictly to `~/.local/share/halbert/guests/<guest_id>/`.
2. **Entity Name Safeguard**: Restoring an archive on an existing installation checks entity names. If the existing node is named "Macky-Mac" and the archive is named "Halbert", the UI warns: *"This archive belongs to 'Halbert'. Restoring will replace 'Macky-Mac's identity."*
3. **Peer Token Preservations**: Restoring an entity with its `peers.json` preserves all satellite relationships. If Macky-Mac was a compute provider for Halbert, that pairing resumes immediately after Halbert's restore.

---

## 6. Technical Review (2026-09-12)

**Reviewer**: Verified against `halbert_core/` and `Haloysius/` source.

### 6.1 `memory_v2.db` → `memories.json`

Invariant 1 says: "A private guest's memories are never dumped into `memory_v2.db`." But `PersonaMemoryStore` stores memories as `memories.json` (JSON file), not `memory_v2.db` (SQLite). See review of `active-passive-replication.md` section 6.1 for evidence.

**Fix**: Change `memory_v2.db` to `memories.json` in invariant 1.

### 6.2 Archive structure is inconsistent with architecture-blueprint.md

Section 4.1 shows a modular archive structure:
```
halbert-2026-09-12.halbert-backup
├── manifest.json
├── entity/
│   ├── identity.enc
│   ├── config.enc
│   └── databases/
│       ├── memory.db.enc
│       ├── conversation.db.enc
│       ├── state_ledger.db.enc
│       └── timeline.db.enc
├── personas/
└── private_enclaves/
```

But `architecture-blueprint.md` section 3.1 shows a different structure:
```
halbert-2026-09-12T14-00-00Z.halbert-backup
├── manifest.json
├── identity/
├── config/
├── databases/
│   ├── persona_memory.db.enc
│   ├── conversation.db.enc
│   ├── state_ledger.db.enc
│   ├── timeline.db.enc
│   └── findings.db.enc
└── model-manifest.json
```

These need to be reconciled. The multi-persona doc's structure is better (it separates enclaves), but the directory names and file names differ.

**Fix**: Adopt one structure. Recommended: use the multi-persona doc's `entity/` + `personas/` + `private_enclaves/` structure as the canonical one, and update `architecture-blueprint.md` to match. Fix the file names in both:
- `memory.db.enc` / `persona_memory.db.enc` → `memories.json.enc` (it's JSON, not SQLite)
- `conversation.db.enc` → `conversations.db.enc` (plural)

### 6.3 Private guest storage format is unspecified

Section 3.2 says private guests have:
- Exclusive Memory DB: `~/.local/share/halbert/guests/<guest_id>/memory.db`
- Exclusive Conversation DB: `~/.local/share/halbert/guests/<guest_id>/conversation.db`

But the main entity's memory is `memories.json` (JSON), not a `.db` (SQLite). Are private guest memories also JSON? Or do they use a different store? The doc says `memory.db` which implies SQLite, but the main `PersonaMemoryStore` uses JSON.

Looking at the codebase: `PersonaMemoryStore` is instantiated with a `persona_id`. A private guest would use a different `persona_id`, so it would get its own `memories.json` under `state_dir("personas", <guest_id>)`. The guest's memory is also JSON, not SQLite.

**Fix**: Change `memory.db` to `memories.json` and `conversation.db` to `conversations.db` in section 3.2. The guest's storage is the same format as the main entity's, just under a different persona_id.

### 6.4 Dual-secret enclave (section 4.2) adds significant complexity

Section 4.2 describes a "Strict Privacy Mode" where a private guest can require its own independent passphrase to unlock its enclave inside the backup. This means:
- The backup archive contains ciphertext blobs that can't be decrypted with the main passphrase alone
- The restore flow needs to handle partial decryption (main entity restored, enclaves locked)
- The user needs to manage multiple passphrases

This is a significant UX and implementation complexity increase. For a 2-3 node home cluster, is this level of multi-key encryption warranted? The simpler approach (unified passphrase, segregated storage directories) already provides architectural isolation — the guest's memories are in a separate directory and Halbert's cognition tick never crawls it.

**Recommendation**: Defer dual-secret enclaves. Ship with "Default Mode (Unified Passphrase, Segregated Storage)" first. The directory-level segregation already maintains the invariant ("Halbert's own psyche never learns a guest's evenings"). Add dual-secret only if a threat model demands it (e.g., shared backup storage where the main passphrase holder shouldn't access guest memories).

### 6.5 `peers.json` preservation on restore (invariant 3) is correct but incomplete

Invariant 3 says restoring `peers.json` preserves satellite relationships. This is correct — `peers.json` stores SHA-256 hashes of bearer tokens (`peers_config.py:18-21`), and the satellites still have their raw `peer_token` in their `being.yml`, so they can re-authenticate immediately.

But the doc doesn't mention: if the canonical host is restored from a backup taken **before** a satellite was paired, that satellite's token hash won't be in `peers.json`. The satellite will get 401 on every request and need to re-pair. This is already noted in `architecture-blueprint.md` section 5.4, but should be cross-referenced here.

**Fix**: Add a note to invariant 3: "Satellites added after the backup was taken will need to re-pair (their token hash is not in the restored `peers.json`)."

### 6.6 Entity name safeguard (invariant 2) — how is the entity name stored?

Invariant 2 says the restore checks entity names. The entity name is resolved through `identity.py:resolve_entity_name()` with a priority chain: `HALBERT_DISPLAY_NAME` → `preferences.yml:ai_name` → `being.yml:name` → hostname → "Halbert". The backup stores `being.yml` and `preferences.yml`, so the name travels with the archive.

But the check needs to compare the archive's name against the **current** node's name. If the current node has no name set (fresh install), the resolver falls back to the hostname. The restore UI should show the archive's name and the current node's name (or "unnamed (hostname: foo)") for comparison.

**Fix**: Add a note that the entity name comparison uses `resolve_entity_name()` on both sides, and a fresh install with no name set shows the hostname as the current name.
