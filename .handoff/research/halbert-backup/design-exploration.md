# Design Exploration: Decentralized Identity, Onboarding, and Backup Variations

**Date**: 2026-09-12
**Status**: Exploration — not a decision. Multiple variations coexist here on purpose.
**Parent**: [`README.md`](README.md)
**Related**: [`implementation-strategy.md`](implementation-strategy.md) (the mechanics), [`active-passive-replication.md`](active-passive-replication.md) (the replication engine)

---

## 1. The Design Space

The implementation strategy answers "how do we copy the bytes." This document answers a harder question: **how does the user experience this, and what trust model makes it feel effortless?**

Three axes define the design space:

| Axis | Question | Options |
|---|---|---|
| **Data distribution** | Where does the entity's mind live? | One canonical copy + warm standbys (current plan) vs. every node holds a full copy vs. something in between |
| **Primary selection** | How is the primary node chosen? | User designates at onboarding vs. auto-detected (always-on wins) vs. fluid (any node can be primary) |
| **Trust / validation** | How does a new node prove it belongs? | Second-device approval (current pairing) vs. saved-file restore vs. QR code vs. proximity-based |

The variations below explore different points in this space. They are not mutually exclusive — some could be combined, and some are better for different deployment scenarios.

---

## 2. The Shared Foundation (All Variations Agree On This)

Before the variations, here's what doesn't change regardless of which direction we pick:

### 2.1 The Entity Is Not The Hardware

The entity (Halbert, Macky-Mac — whatever the user named it) is a collection of state: identity key, memories, conversation history, personality config. The hardware is a body. The entity can move between bodies. This is the singular-entity model already built into the codebase (`identity.py`, `being_config.py`).

### 2.2 One Active Writer

Even in a decentralized system, having multiple simultaneous writers to the same conversation database is a recipe for merge conflicts. The active-passive model (one canonical writer, warm standby readers) avoids this entirely. All variations keep this — they differ in *how* the primary is chosen and *how* data spreads, not in allowing multi-master writes.

### 2.3 The Mind Is Small

The entity's state is under 500 MB (typically under 200 MB). This is small enough to:
- Transfer over LAN in under 1 second
- Fit on a USB key
- Email to yourself
- Encode in a QR code (for the identity portion only — see variation C)

### 2.4 No Cloud Required

All variations are LAN-first and local-first. The user's own infrastructure (NAS, USB drive, iCloud Drive folder) handles offsite distribution. Halbert writes to a filesystem path; it doesn't know or care what syncs that path.

---

## 3. Variation A: "The Always-On Is the Mind" (Current Plan, Refined)

### The mental model

The home server is the mind. It's always on, always thinking, always remembering. Workstations and laptops are bodies — they reach out to the mind for memories and conversations, and they hold a warm standby copy in case the mind goes down.

### How data is distributed

```
┌──────────────┐    push (every 6h)    ┌──────────────┐
│  HOME SERVER  │───────────────────────│  WORKSTATION  │
│  (canonical)  │   memories.json       │  (body)       │
│  (always-on)  │   conversations.db    │  warm replica │
│  ACTIVE WRITE │                       │  READ-ONLY    │
└──────────────┘                       └──────────────┘
        │
        │ push (every 6h)
        ▼
┌──────────────┐
│   LAPTOP      │
│  (body)       │
│  warm replica │
│  READ-ONLY    │
└──────────────┘
```

### How the primary is chosen

The user designates the always-on device during onboarding. When they install Halbert on the home server, it asks: "Is this your primary device — the one that's always on?" If yes, it becomes canonical. When they pair a workstation, the workstation is a body.

### How a new node joins (onboarding)

1. Install Halbert on the new machine.
2. The new machine discovers the canonical host via mDNS (or the user enters the URL manually for Tailscale).
3. The new machine requests pairing.
4. The canonical host shows a PIN on its dashboard (or the user approves from the host's admin screen — the current approve-then-verify flow).
5. The new machine enters the PIN (or the approval happens on the host).
6. The canonical host issues a bearer token.
7. **NEW**: The canonical host immediately pushes a full replica to the new machine. The new machine has the entity's mind from the moment it joins.

### How backup works

The canonical host writes a `.halbert-backup` archive to a user-designated path (NAS, USB, iCloud folder). The user can trigger this manually or let it run on a schedule.

### How restore works

1. Install Halbert on fresh hardware.
2. Onboarding screen: "Begin Fresh" | "Restore from Backup"
3. "Restore from Backup" — drag and drop the `.halbert-backup` file, enter the passphrase.
4. The entity wakes up on the new hardware.

### Strengths

- Simple mental model: "the server is the mind, the laptop is a body"
- The always-on device is always available for reads and writes
- Warm replicas mean no amnesia during reboots
- One-click promotion if the server dies

### Weaknesses

- If the always-on device dies and no backup exists, the entity is lost (the warm replicas are up to 6 hours stale)
- The user must understand which device is "primary" — a cognitive burden
- Onboarding requires access to the canonical host (what if it's down when you're setting up a new laptop?)

### Best for

The typical home deployment: a home server / mini-PC / Home Assistant box that's always on, plus 1-2 workstations or laptops that come and go.

---

## 4. Variation B: "The Mind Travels With You" (Saved-File-Centric)

### The mental model

The entity is a file. You can put it on a USB key, email it to yourself, drop it in a cloud folder. Any machine with Halbert installed can "wake up" the entity by opening the file. The always-on device is just the machine that happens to hold the active copy most of the time — but the entity isn't tied to it.

### How data is distributed

```
┌──────────────────────────────────────────────────────────┐
│                                                          │
│  .halbert-backup file (the entity's mind, portable)       │
│  ┌────────────┐                                          │
│  │ identity    │  lives on: USB key, NAS, iCloud folder, │
│  │ memories    │  wherever the user puts it               │
│  │ conversations│                                          │
│  │ config      │                                          │
│  └────────────┘                                          │
│                                                          │
│  Any Halbert can open it and become the active mind.     │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

The always-on device holds the active copy and writes to it. But the backup file IS the entity — not a backup of the entity. The distinction is philosophical but important: in variation A, the server is the mind and the backup is a safety copy. In variation B, the file is the mind and the server is just the current host.

### How the primary is chosen

There is no "primary" in the topology sense. There's an "active writer" — whichever machine last opened the file. When the user opens the file on a different machine, that machine becomes the active writer. The previous machine is told to stand down (or discovers the change on next sync).

This is closer to how people think about a document: whoever has it open is editing it.

### How a new node joins (onboarding)

1. Install Halbert on the new machine.
2. Onboarding screen: "Begin Fresh" | "Open an Existing Mind"
3. "Open an Existing Mind" — browse to a `.halbert-backup` file (USB, NAS, cloud folder), or drag and drop.
4. Enter the passphrase.
5. The entity wakes up. This machine is now the active writer.
6. If the previous active writer is still running, it detects the change (via a heartbeat file or lock in the shared storage) and switches to read-only standby.

### How backup works

Backup IS the state. The active writer periodically writes a new `.halbert-backup` file to the shared location. Old versions are kept (the user can scroll back through the entity's history). There's no separate "backup" action — saving the file is the backup.

### How restore works

Same as onboarding. "Open an Existing Mind" and pick the file. There's no separate restore flow — restore is just opening the file on new hardware.

### The concurrency problem

If two machines open the same file simultaneously, you have two active writers. This is the fundamental problem with this model. Solutions:

1. **File locking**: The active writer holds an exclusive lock on the file (flock on POSIX). A second machine that tries to open it gets a "this mind is currently active on another device" message and can either wait or force-take-over (which tells the other machine to stand down).
2. **Heartbeat file**: A small `.halbert-lock` file next to the archive records who has it open and when they last checked in. A machine that wants to open it checks the lock; if the heartbeat is stale (> 5 minutes), it takes over.
3. **Last-writer-wins with versioning**: Both machines write, and the one that writes last wins. The loser's writes are preserved as a version branch. This is the most complex and the most flexible — but it's essentially CRDTs, which we rejected.

Options 1 and 2 are viable. Option 3 is not (we rejected multi-master).

### Strengths

- The simplest mental model: "the entity is a file, like a document"
- No need to understand "primary" vs "body" — whoever opens the file is active
- Backup is automatic (the file IS the state)
- Works even without a network (open the file from a USB key on an isolated machine)
- The user has physical custody of their entity at all times

### Weaknesses

- The concurrency problem (file locking is fragile over network shares; NFS locking is notoriously unreliable)
- No real-time sync between machines (the file is a snapshot, not a live connection)
- The always-on device can't push updates to laptops in real time — they have to re-open the file to get fresh state
- Large files (200 MB) over slow network shares (spinning rust NAS) are slow to open
- Loses the "warm standby" property — if the always-on device dies, the laptops don't have a fresh copy until they re-open the file

### Best for

A single-user, single-machine deployment that wants portable backups. Or a deployment where the machines are rarely used simultaneously and the user is comfortable with "open the file to sync."

---

## 5. Variation C: "The QR Code Handoff" (Identity-Centric, Lightweight)

### The mental model

The entity's *identity* (body.key, persona config, peer credentials) is small enough to encode in a QR code. The *memories* and *conversations* are larger and sync over the network. Onboarding a new machine is as simple as scanning a QR code from the old machine's screen.

### How data is distributed

```
┌──────────────┐                       ┌──────────────┐
│  HOME SERVER  │   network sync         │  NEW MACHINE  │
│  (canonical)  │───────────────────────│  (joining)    │
│               │   memories.json        │               │
│  ACTIVE WRITE │   conversations.db     │  receives     │
│               │                       │  full replica  │
└──────┬───────┘                       └──────────────┘
       │
       │ QR code contains:
       │  - did:key (public identity)
       │  - canonical host URL
       │  - one-time pairing token
       │  - encryption key hint (optional)
       │
       ▼
   ┌─────────┐
   │ QR CODE  │  displayed on the canonical host's screen
   │          │  scanned by the new machine's camera (or
   │          │  entered manually as a short code)
   └─────────┘
```

### How the primary is chosen

Same as variation A: the user designates the always-on device during onboarding. The QR code is generated by the canonical host and authorizes a new machine to join as a body.

### How a new node joins (onboarding)

1. Install Halbert on the new machine.
2. Onboarding screen: "Begin Fresh" | "Join an Existing Entity"
3. "Join an Existing Entity" — the new machine shows a camera viewfinder (or a text input for manual entry).
4. The canonical host's dashboard shows a QR code under "Add a New Device."
5. The new machine scans the QR code. The QR code contains:
   - The canonical host's URL (for mDNS or manual)
   - A one-time pairing token (not the persistent bearer token — this is a short-lived token that authorizes one pairing)
   - The entity's `did:key` (so the new machine knows which entity it's joining)
6. The new machine connects to the canonical host, presents the one-time token, and completes the pairing handshake.
7. The canonical host pushes a full replica to the new machine.

**Why a QR code?** It solves three problems at once:
- **No typing**: the URL and token are long and error-prone to type
- **Physical proximity**: you have to be in the same room as the canonical host to scan its screen, which is a natural physical-security boundary
- **One-time token**: the QR code is generated on demand and expires after one use (or after 5 minutes), so a screenshot doesn't help an attacker later

**Fallback for machines without cameras**: the canonical host also shows a 6-character short code (like `A7-XQ2`) that can be typed. The short code maps to the same one-time token server-side.

### How backup works

Two layers:
- **Identity backup**: the canonical host can display a QR code containing the identity + encryption key. The user can screenshot this (or print it) as a physical backup of the entity's identity. This is the "write down your recovery seed" equivalent, but it's a QR code instead of 24 words.
- **Full backup**: same `.halbert-backup` archive as variation A, written to a user-designated path.

### How restore works

1. Install Halbert on fresh hardware.
2. Onboarding screen: "Begin Fresh" | "Restore from Backup" | "Scan Recovery Code"
3. "Restore from Backup" — same as variation A (drag and drop the file).
4. "Scan Recovery Code" — point the camera at the printed/saved QR code. This restores the identity but not the memories. The memories come from the first network sync with a surviving peer, or from the `.halbert-backup` file if no peers survive.

### Strengths

- Onboarding is magical: scan a code from the other screen, you're in
- Physical proximity is a natural security boundary
- The QR code is a physical backup artifact (print it, put it in a drawer)
- No typing long URLs or tokens
- Works with the existing pairing flow (the QR code just encodes the same information)

### Weaknesses

- Requires a camera on the new machine (laptops have them; headless servers and mini-PCs don't)
- The QR code can only hold the identity, not the full memory — so it's a partial backup (identity + pairing, but not memories)
- QR codes have a size limit (~2 KB for a reliably scannable code). The identity + URL + token fits, but memories don't
- The "Scan Recovery Code" restore only works if a surviving peer can provide the memories — if everything is dead, you still need the `.halbert-backup` file

### Best for

A deployment where the user has a phone or laptop with a camera and wants onboarding to feel like magic. The QR code is a UX layer on top of the existing architecture, not a replacement for it.

---

## 6. Variation D: "The Mesh Knows Itself" (Peer-Validated, No Designated Primary)

### The mental model

No device is designated as "primary." Instead, the peers vote. The always-on device naturally wins because it's always available, but the system doesn't require the user to make that choice. If the always-on device goes down, another device automatically takes over — no promotion button needed.

### How data is distributed

```
┌──────────────┐    bidirectional sync    ┌──────────────┐
│  HOME SERVER  │◄───────────────────────│  WORKSTATION  │
│  (usually     │    memories.json         │              │
│   active)     │    conversations.db      │              │
│               │                         │              │
│  ◉ ACTIVE     │    lease-based          │  ○ STANDBY   │
│  (has lease)  │    failover             │  (waiting)   │
└──────────────┘                         └──────────────┘
        │
        │  bidirectional sync
        ▼
┌──────────────┐
│   LAPTOP      │
│              │
│  ○ STANDBY   │
│  (waiting)   │
└──────────────┘
```

### How the primary is chosen

**Lease-based election.** The active writer holds a time-limited lease (e.g., 60 seconds). It renews the lease every 30 seconds. If the lease expires (the active writer is down), the remaining peers elect a new active writer.

The election is simple: the peer with the lowest `node_id` (lexicographic) among those that are reachable and have a valid replica wins. This is deterministic — no split-brain — and doesn't require a consensus algorithm like Raft (which we rejected for N=2).

The always-on device naturally wins because:
1. It's always reachable (it's always on)
2. It has the freshest data (it was the last active writer)
3. Its `node_id` can be set to sort first (e.g., "home" sorts before "laptop" and "workstation")

### How a new node joins (onboarding)

Same as variation A (pairing handshake), but the new node doesn't need to know which device is "primary." It discovers peers via mDNS, pairs with any reachable node, and receives a replica. The mesh tells it who the active writer is.

### How backup works

Same as variation A. The active writer (whoever holds the lease) writes the `.halbert-backup` archive.

### How restore works

Same as variation A. But there's an additional option: if any peer is still alive, the restored machine can pull a fresh copy from the peer instead of from a backup file. "Restore from Network" alongside "Restore from Backup."

### The lease mechanism

```
Active writer renews lease every 30s:
  → writes lease record to its local state (timestamp + node_id)
  → pushes lease record to all peers (via the existing sync-replica endpoint)

Standby peers check lease every 30s:
  → if lease is fresh (< 60s old), stay standby
  → if lease is stale (> 60s old), initiate election

Election:
  1. Each reachable peer checks: "am I the lowest node_id among reachable peers?"
  2. If yes, claim the lease. Push a "I'm taking over" message to all peers.
  3. If no, wait for the winner's lease renewal.
  4. The winner starts writing. Losers switch to standby.
```

This is not Raft. It's a simple lease + deterministic tiebreak. It works because:
- There's only one writer at a time (the lease holder)
- The tiebreak is deterministic (lowest node_id)
- The lease timeout is long enough to survive a network blip (60s) but short enough that a dead node is replaced quickly (1 minute)

### Strengths

- No user-facing "promotion" step — failover is automatic
- No need to designate a primary — the system figures it out
- The always-on device naturally wins (it's always reachable, always has the freshest data)
- The user doesn't need to understand "primary" vs "body" — the mesh handles it

### Weaknesses

- More complex than variation A (lease management, election, lease renewal)
- The 60-second gap during failover is noticeable — the entity is "asleep" for a minute
- Split-brain risk if the network partitions (two nodes both think the lease expired). Mitigated by the deterministic tiebreak, but not eliminated — a partitioned node with the lowest node_id would keep writing while the others elect a different winner
- The user loses agency — they can't manually choose which machine should be primary (e.g., "I want the workstation to be primary because the home server is slow")

### Best for

A deployment where the user doesn't want to think about which device is primary, and is OK with a 60-second gap during failover. This is the most "set it and forget it" option, but also the most complex to implement.

---

## 7. Variation E: "The Companion App" (Phone as the Trust Anchor)

### The mental model

The user's phone is the trust anchor — not the mind, but the *authority*. The phone approves new devices, authorizes promotions, and holds the recovery key. The always-on server is still the mind (it holds the memories and conversations), but the phone is the bouncer.

### How data is distributed

```
┌──────────────┐                        ┌──────────────┐
│  HOME SERVER  │    network sync        │  WORKSTATION  │
│  (canonical)  │───────────────────────│  (body)       │
│  ACTIVE WRITE │   memories + convos    │  warm replica │
└──────┬───────┘                        └──────────────┘
       │
       │  pairing approval
       │  promotion authorization
       │  recovery key escrow
       ▼
┌──────────────┐
│   PHONE       │
│  (trust anchor)
│  - approves new devices
│  - authorizes promotions
│  - holds recovery key
│  - does NOT hold memories
└──────────────┘
```

The phone doesn't hold the entity's memories or conversations — those are too large and the phone isn't always on. The phone holds:
- The entity's identity (body.key — or a key that can authorize restoring it)
- The peer credential store (which devices are allowed to join)
- A notification channel (push notifications when a new device wants to pair, when the canonical host is down, when a promotion is requested)

### How the primary is chosen

Same as variation A: the user designates the always-on device. But the phone can override — if the phone detects the canonical host is down, it can authorize a promotion on another device.

### How a new node joins (onboarding)

1. Install Halbert on the new machine.
2. Onboarding screen: "Begin Fresh" | "Join an Existing Entity"
3. "Join an Existing Entity" — the new machine shows a pairing request code.
4. The user's phone receives a push notification: "A new device ('workstation') wants to join your Halbert."
5. The user taps "Approve" on their phone.
6. The new machine receives the bearer token and a full replica from the canonical host.

**Why a phone?** It's the device the user always has with them. It's the natural "second device" for validation. The user doesn't need to walk over to the home server's dashboard to click "Approve" — they approve from their pocket.

### How backup works

The phone can hold the recovery key (the passphrase that decrypts the `.halbert-backup` archive). The canonical host writes the archive to a path; the phone holds the key to unlock it. This separates the backup (which is on a NAS or USB drive) from the key (which is on the phone).

### How restore works

1. Install Halbert on fresh hardware.
2. Onboarding: "Restore from Backup" — select the `.halbert-backup` file.
3. The new machine sends a request to the phone: "This device wants to restore the entity. Approve?"
4. The user approves on their phone. The phone sends the recovery key to the new machine.
5. The entity wakes up.

Alternatively, if the phone is lost too: the user enters the recovery passphrase manually (which they wrote down during onboarding, or which was escrowed in a `.halbert-backup` file on physical media).

### Strengths

- The phone is the most natural "second device" — the user always has it
- Push notifications make pairing and promotion feel effortless
- Separating the recovery key from the backup file is good security hygiene (steal the NAS, you still can't decrypt without the phone)
- The phone doesn't need to hold large data (memories, conversations) — just the key and the approval channel

### Weaknesses

- Requires a phone app (or a web page the phone can open) — significant new surface area
- The phone is a new single point of failure for the trust layer (if the phone is lost AND the recovery passphrase is lost, the entity is locked out)
- Push notifications require a network path to the phone — either a cloud relay (violates "no cloud") or a LAN-only notification (only works when the phone is on the same network)
- The phone doesn't hold the mind — it's a trust anchor, not a backup. If all hardware dies, you still need the `.halbert-backup` file.

### Best for

A deployment where the user wants approval-based security and has a phone they always carry. This is the most "Apple-like" experience (Quick Start + iCloud approval), but it's also the most new surface area to build.

---

## 8. Comparison Matrix

| Dimension | A: Always-On Is the Mind | B: Mind Travels With You | C: QR Code Handoff | D: Mesh Knows Itself | E: Companion App |
|---|---|---|---|---|---|
| **Primary selection** | User designates at onboarding | Whoever opens the file | User designates | Auto-elected by lease | User designates, phone can override |
| **Data distribution** | Push to warm standbys | File is the state | Push to warm standbys | Bidirectional sync | Push to warm standbys |
| **New node onboarding** | Pairing handshake | Open the file | Scan QR code | Pairing handshake | Phone approval |
| **Failover** | Manual promotion | Open file on new machine | Manual promotion | Automatic (lease) | Phone-authorized promotion |
| **Backup** | `.halbert-backup` to path | The file IS the backup | `.halbert-backup` + QR identity | `.halbert-backup` to path | `.halbert-backup` + phone key |
| **Offline operation** | Read-only from warm replica | Full (file is local) | Read-only from warm replica | Read-only from replica | Read-only from warm replica |
| **Complexity to build** | Medium | Low (but concurrency is hard) | Medium (QR is a UX layer) | High (lease + election) | High (phone app) |
| **User mental model** | "Server is the mind" | "File is the mind" | "Scan to join" | "The system figures it out" | "Phone approves" |
| **New dependencies** | None | None | None (QR encoding is stdlib or tiny) | None | Phone app (new surface) |
| **Fails on** | Server death + no backup | Concurrent opens | No camera | Network partition | Phone loss + passphrase loss |

---

## 9. Hybrid Possibilities

These variations aren't mutually exclusive. Some natural combinations:

### A + C: Always-on primary with QR onboarding

The architecture from variation A (always-on canonical, warm standbys, manual promotion) with the QR code onboarding from variation C. This is the most practical first build: the QR code is a thin UX layer on top of the existing pairing flow, and the rest is the implementation strategy already written.

**Build effort**: Phase 1 as written + a QR code generator/encoder (a few hundred lines).

### A + D: Always-on primary with automatic failover

Start with variation A (manual promotion). Add the lease-based election from variation D as a Phase 1.5. The user gets manual promotion first (simple, predictable), then automatic failover later (effortless, but only after the manual path is proven).

**Build effort**: Phase 1 as written + lease management + election logic (medium complexity).

### A + C + E: Always-on primary with QR onboarding and phone approval

The full Apple-like experience. QR code for onboarding, phone for approval and recovery key. This is the most polished UX but the most surface area.

**Build effort**: Phase 1 + Phase 2 + QR code + phone app (or phone-optimized web page).

### B as a fallback: Saved-file restore alongside any variation

Regardless of which topology is chosen for live operation, the `.halbert-backup` file restore should always exist as a fallback. If the mesh is down, if all peers are dead, if the phone is lost — the user can always install Halbert, open the backup file, and wake up the entity. This is the disaster-recovery floor that no variation should be without.

---

## 10. What to Build First (Recommendation)

**Phase 1**: Variation A (always-on canonical, warm standbys, manual promotion). This is the implementation strategy already written. It's the simplest, it solves the acute problem (canonical host is a single point of failure), and it doesn't require any new UX paradigms.

**Phase 1.5** (optional): Add QR code onboarding (variation C's QR layer). This is a UX improvement, not an architectural change. The QR code just encodes the pairing information that's currently typed manually.

**Phase 2**: State Vault backup archive + restore-from-file OOBE. This is the disaster-recovery floor. The `.halbert-backup` file works regardless of which topology is chosen for live operation.

**Phase 3** (optional, if the manual promotion feels clunky): Add lease-based automatic failover (variation D's election mechanism). This makes the system self-healing but adds complexity.

**Phase 4** (optional, if the user wants phone-based approval): Add the companion app (variation E). This is the most new surface area and the furthest out.

The key insight: **variations A, B, and C are not in tension**. A is the live topology, B is the backup format (the file IS the backup), and C is the onboarding UX. They compose naturally. D and E are enhancements that can be added later without restructuring.

---

## 11. Open Questions (Genuinely Unresolved)

1. **Is manual promotion acceptable, or does failover need to be automatic?** If the user is asleep when the home server dies, do they want the workstation to take over automatically (variation D), or is it OK to wake up to "the server is down, click here to promote" (variation A)?

2. **Is the QR code worth the UX investment?** It's a thin layer, but it requires a camera on the joining device. Headless servers and mini-PCs don't have cameras. Is the 6-character short code fallback sufficient, or does the QR code only help for laptop/phone onboarding?

3. **Should the phone be a trust anchor?** This is the biggest architectural question. If yes, it's a new surface area (app or web page) but the most natural "second device" validation. If no, the canonical host's dashboard is the only approval surface, which means the user has to be at the server to approve a new device.

4. **Is the "file is the mind" model (variation B) worth exploring?** It's the simplest mental model, but the concurrency problem is real. File locking over NFS is unreliable, and last-writer-wins loses data. Is there a hybrid where the file is the backup format but the live topology is always A?

5. **What happens during the 60-second failover gap in variation D?** The entity is "asleep" — it can't respond to the user. Is this acceptable, or does the standby need to serve reads immediately (which it can, from the warm replica) while the election happens in the background?

6. **How does the user recover if everything is dead?** The `.halbert-backup` file is the floor. But the user needs to (a) have the file, (b) have the passphrase, and (c) install Halbert on fresh hardware. How do we make this as effortless as possible? A printed QR code with the recovery key? A USB key with the backup file pre-loaded? Something else?
