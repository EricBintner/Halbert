# Open Questions: Resolved

**Date**: 2026-09-12
**Status**: Decisions (not yet founder-ratified)
**Parent**: [`design-exploration.md`](design-exploration.md) section 11
**Lens**: User's perspective first. Simplest path that accomplishes the most. iOS app is theoretical — design the spec for it, don't depend on it.

---

## How to Read This

Each question is answered with:
- **The question** (from design-exploration.md section 11, or new)
- **The user's experience** — what it feels like
- **The decision** — what we build
- **Why it's the simplest path** — why nothing simpler would work
- **How the iOS app changes it later** — what the app adds, without requiring us to pre-build for it

---

## Q1: Manual promotion or automatic failover?

### The user's experience

**Manual**: The home server dies overnight. In the morning, the user talks to the workstation. The workstation says: "I can't reach the home server. I still have all our memories from 6 hours ago. Would you like me to take over?" The user clicks one button. The workstation becomes the mind.

**Automatic**: The home server dies overnight. The workstation detects it within 90 seconds and takes over silently. In the morning, the user talks to the workstation and it just works. They may not even know the server died.

### The decision: Manual, for now.

Manual promotion is simpler to build, simpler to reason about, and gives the user agency. The warm replica means the workstation still has all the memories and can serve reads — the user doesn't experience amnesia, they just can't form new memories until they click "Promote."

### Why nothing simpler would work

Automatic failover requires lease management, election, and split-brain prevention. That's a real distributed systems problem. Manual promotion is one button. The gap between them is weeks of engineering for a scenario (hardware death) that happens rarely.

The warm replica already solves the acute problem: no amnesia during reboots or short outages. Manual promotion solves the long outage: one click and you're the mind. The only thing automatic failover adds is not having to click — and that click gives the user a moment to understand what happened.

### How the iOS app changes it later

The phone can authorize the promotion remotely. The user doesn't need to walk to the workstation — they get a push notification ("Home server is unreachable. Promote Workstation?") and tap "Yes." Same manual flow, just approved from the pocket instead of the dashboard. No architectural change — the promotion endpoint is the same, the approval surface is the phone.

If automatic failover is ever wanted, it's an opt-in setting: "Allow automatic promotion when the canonical host is unreachable for > 5 minutes." The lease mechanism from variation D layers on top of the existing manual promotion code. But it's not needed for v1.

---

## Q2: Is the QR code worth it?

### The user's experience

**Without QR**: To pair a new laptop, the user opens the canonical host's dashboard, reads a 4-digit PIN, walks to the laptop, types the host's URL and the PIN. Two fields, one of them a URL with a port number.

**With QR**: The canonical host's dashboard shows a QR code. The user points the new laptop's camera at it (or scans with their phone). The URL and pairing token are transferred instantly. No typing.

### The decision: Yes, but it's a rendering choice, not an architecture.

The QR code encodes the same data the pairing flow already produces: the canonical host's URL and a one-time pairing token. Generating a QR code is a frontend concern — a JS library renders the pairing data as a QR image in the dashboard. No new backend code, no new endpoints, no new data.

The existing pairing flow already has:
- `POST /api/peers/pair` — creates a pending pairing, returns a `request_id`
- `GET /api/peers/pending` — shows pending pairings with their PINs (local admin only)
- `POST /api/peers/pending/{request_id}/approve` — the approval step
- `POST /api/peers/verify` — exchanges the PIN for a bearer token

The QR code just encodes the canonical host URL + the `request_id` + the PIN into a scannable image. The new machine scans it, parses the data, and calls the same endpoints in the same order. The backend doesn't know or care that the data arrived via QR instead of typing.

### Why this is the simplest path

The QR code is ~50 lines of frontend code (a JS QR library + a canvas render). It doesn't change the pairing protocol, the auth model, or the backend. It's the highest UX return per line of code in this entire system.

The fallback for headless machines (no camera): the dashboard shows the QR code alongside the URL + PIN as text. The user types them. Same as today.

### How the iOS app changes it later

The phone scans the QR code from the canonical host's screen and initiates the pairing on behalf of the new machine. Or: the phone generates its own QR code that the new machine scans (the phone as pairing proxy). Either way, the backend is the same — the QR code is just a data transport.

The iOS app also enables a flow that doesn't exist today: the phone scans the QR code, the phone approves the pairing (2FA), and the new machine receives its token without anyone typing anything. But that's the app adding a convenience layer, not the backend needing to know about it.

---

## Q3: Should the phone be a trust anchor?

### The user's experience

**Without the phone**: To approve a new device, the user walks to the canonical host's dashboard and clicks "Approve." They have to be physically at the server.

**With the phone**: The user's phone buzzes. "A new device ('workstation') wants to join." They tap "Approve" from the couch.

### The decision: The approval surface is already abstracted. The phone is a future client of the same API.

The existing code already has the right shape:
- `POST /api/peers/pending/{request_id}/approve` — guarded by `require_local_admin`
- The approval is an API call, not a button in a specific UI

Today, `require_local_admin` means "you're on localhost with admin credentials." When the iOS app exists, the approval endpoint gets a second auth path: "you're the paired phone." The endpoint signature doesn't change — the auth dependency gains a second branch.

This means: **build nothing for the phone now.** The approval API is already the right shape. The phone is a future client of `POST /api/peers/pending/{request_id}/approve` with a different auth credential. The only backend change when the app ships is adding a phone-token auth path alongside `require_local_admin`.

### Why this is the simplest path

We don't need to decide the phone's auth mechanism now. We don't need to build a push notification service. We don't need to design a phone pairing flow. The approval endpoint exists and works. When the phone is built, it calls the same endpoint. The only precondition is that the endpoint stays an API call (not coupled to the dashboard UI), which it already is.

### How the iOS app changes it later

The phone becomes a second approval surface. The auth model adds one path:

```
Current:  require_local_admin → localhost admin session
Future:   require_local_admin OR require_phone_token → localhost OR paired phone
```

The phone pairs once (via the existing pairing flow — the phone is just another body with a special role). After that, it can call the approval endpoint. Push notifications are a transport concern (APNs delivers them); the backend just exposes `GET /api/peers/pending` for the phone to poll, or a WebSocket/SSE stream for push.

---

## Q4: Is "the file is the mind" (variation B) worth exploring as a live topology?

### The user's experience

**Variation B**: The entity is a `.halbert-backup` file. You open it on any machine and that machine becomes the mind. Like opening a document.

**Variation A + B hybrid**: The entity lives on the always-on server. The `.halbert-backup` file is the portable backup. You restore from it on fresh hardware. The file is the mind's *snapshot*, not its *live state*.

### The decision: The file is the backup, not the live topology. Variation A for live, B for the backup format.

The concurrency problem kills variation B as a live topology. Two machines opening the same file simultaneously means two writers, which means merge conflicts, which means CRDTs, which we rejected. File locking over network shares is unreliable (NFS locking is a known hellscape). Last-writer-wins loses data.

But the *mental model* from variation B is the right one for backups: "your Halbert is a file you can put on a USB key." That's the restore experience. The `.halbert-backup` file IS the entity's mind in portable form. You just don't run live from it — you restore from it.

### Why this is the simplest path

Variation A (canonical + warm standbys) is already the implementation strategy. Adding variation B as a live topology would mean building a second, concurrent runtime model — file-based instead of network-proxy-based. That doubles the complexity for no user benefit (the user doesn't care whether the sync is a file copy or a network push; they care that their memories are safe).

The hybrid gets the best of both: the live topology is simple (one writer, warm standbys), and the backup is a portable file with the simplest possible mental model ("it's a file, put it somewhere safe").

### How the iOS app changes it later

The phone can hold the recovery key for the `.halbert-backup` file. The file is on a USB key or NAS; the key is on the phone. To restore: install Halbert, point it at the file, scan the QR code from the phone to unlock it. The phone is the key, the file is the mind. But neither the file format nor the restore engine needs to know about the phone — the phone just delivers the passphrase via QR instead of the user typing it.

---

## Q5: The 60-second failover gap (variation D)

### The decision: Moot. We chose manual promotion (Q1). No gap exists.

With manual promotion, there's no election and no gap. The workstation serves reads from its warm replica immediately (the liveness probe detects the outage, the fallback store kicks in). The user clicks "Promote" when they're ready. The promotion takes 10-30 seconds (copy files, clear config, reload adapters).

If automatic failover is ever added (opt-in, post-v1), the warm replica already serves reads during the election. The user experiences no gap — they can recall memories and read conversation history throughout. They just can't form new memories for 60 seconds while the election runs. That's acceptable for a rare event.

### How the iOS app changes it later

The phone can authorize the automatic promotion. "Home server has been unreachable for 5 minutes. Automatically promote Workstation? [Yes] [No]" The user taps Yes from their pocket. The promotion happens without them walking to the workstation. But this is a convenience layer on top of the existing promotion flow, not a new mechanism.

---

## Q6: How does the user recover if everything is dead?

### The user's experience

The house burned down. Every machine is gone. The user buys a new computer, installs Halbert, and...

**The simplest possible recovery**:
1. Install Halbert on the new machine.
2. Onboarding: "Begin Fresh" | "Restore from Backup"
3. "Restore from Backup" — the user plugs in a USB key (or browses to a cloud folder) and selects the `.halbert-backup` file.
4. Enter the passphrase.
5. Halbert wakes up. It's the same entity — same name, same memories, same personality.

### The decision: `.halbert-backup` file + passphrase. That's the floor.

The user needs two things to recover:
1. **The file** — on a USB key, NAS, iCloud Drive folder, wherever they put it
2. **The passphrase** — something they chose and remember (or wrote down)

That's it. No phone, no network, no second device. The file + passphrase works on a fresh, isolated machine. This is the disaster-recovery floor.

### Making it effortless

The hard part isn't the restore — it's making sure the user *has* the file and *remembers* the passphrase when disaster strikes. Three nudges:

1. **At onboarding**: After the user names their Halbert, the system says: "Save your backup. This file contains everything I am. Put it somewhere safe." It writes the `.halbert-backup` file and asks the user to choose a destination (USB, NAS, cloud folder). The user picks a passphrase. The system says: "Write this down. If you forget it, I can't be recovered."

2. **Periodically**: The canonical host writes a new backup on a schedule (nightly). The file at the destination is always fresh. The user doesn't think about it.

3. **Before risky changes**: "I'm about to update my software. Let me save a backup first." Automatic pre-update backup.

### Why this is the simplest path

Every alternative adds a dependency on something that might also be dead:
- Phone recovery: the phone might be in the fire too
- Network recovery: the network might be down
- Peer recovery: all peers are dead (that's the scenario)

The file + passphrase depends on nothing except the user having the file and knowing the passphrase. It's the only recovery path that works when everything is gone.

### How the iOS app changes it later

The phone can hold the passphrase (or a key that unwraps it). The user doesn't need to remember it — they scan a QR code from the phone. But the file is still needed (the phone doesn't hold 200 MB of memories). The phone makes the passphrase effortless; the file is still physical.

The phone can also *remind* the user to back up. A monthly notification: "Your last backup was 30 days ago. Is the backup file still somewhere safe?" This is the kind of nudge that prevents the "I never backed up" disaster.

---

## Q7 (new): What does the iOS app actually do?

### The user's experience

The user installs the Halbert companion app on their phone. It pairs with the canonical host (same pairing flow as any body, but with a special role: `trust_anchor`). The phone:

- **Shows status**: which devices are online, which is canonical, when the last backup was, how many memories/threads the entity has
- **Approves sensitive actions**: new device pairing, promotion, backup restore
- **Scans QR codes**: to initiate pairing from the phone, or to deliver the recovery key
- **Holds the recovery key**: the passphrase (or a key that unwraps it) lives in the phone's Secure Enclave

The phone does NOT:
- Hold memories or conversations (too large, phone isn't always on)
- Run the entity (it's a trust anchor, not a body)
- Serve as a backup destination (too small, not reliable enough)

### The decision: Design the spec, don't build it.

The iOS app is a thin trust layer. It's a client of the existing API, not a new backend component. The backend changes needed when the app ships are minimal:

1. **Phone auth path**: add `require_phone_token` as an alternative to `require_local_admin` on the approval endpoints. The phone pairs once and gets a long-lived token (stored in the Secure Enclave).

2. **Status endpoint**: `GET /api/entity/status` — returns entity name, canonical host, peer list, last backup timestamp, memory/thread counts. The phone polls this (or subscribes via SSE) to show status.

3. **Push notification transport**: the phone can poll `GET /api/peers/pending` for pending pairings. When APNs is wired, the backend sends a push instead. But polling works for v1 of the app.

4. **Recovery key custody**: the phone stores the backup passphrase in the Secure Enclave. The backup engine doesn't need to know about this — the phone just delivers the passphrase to the restore flow via QR code or direct input.

### Why this is the simplest path

The iOS app is a client, not a server. It calls existing endpoints (or near-existing endpoints — the status endpoint is a new aggregation of existing data). It doesn't change the architecture, the data model, or the trust model. It adds a second approval surface and a recovery key custodian.

The spec for the app is:
- **Pairing**: standard pairing flow, role `trust_anchor`, token in Secure Enclave
- **Status**: `GET /api/entity/status` (new, aggregates existing data)
- **Approval**: `POST /api/peers/pending/{id}/approve` with phone token auth (existing endpoint, new auth path)
- **Promotion**: `POST /api/replica/promote` with phone token auth (Phase 1 endpoint, new auth path)
- **Recovery**: phone displays the passphrase as a QR code; the restore flow scans it

That's it. Five endpoints, one new auth path, one new aggregation endpoint. The app is a thin shell over the existing API.

---

## Q8 (new): How does 2FA work in this context?

### The user's experience

A sensitive action happens: a new device wants to join, or a satellite wants to promote, or a backup is being restored. The system requires a second confirmation:

**Today (without the phone)**: The user is at the canonical host's dashboard. They click "Approve." The fact that they're physically at the server IS the second factor — someone who can reach the server's local admin dashboard is trusted.

**With the phone**: The user is anywhere. The phone buzzes. They tap "Approve." The phone is the second factor — someone who has the paired phone is trusted.

### The decision: 2FA is already built. The phone just changes the approval surface.

The existing pairing flow IS 2FA:
1. **First factor**: the new device knows the canonical host's URL (network reachability)
2. **Second factor**: a person at the canonical host clicks "Approve" (physical presence)

The phone replaces the second factor:
1. **First factor**: the new device knows the canonical host's URL
2. **Second factor**: the paired phone taps "Approve" (phone possession)

Same security model, different surface. The backend doesn't change — the approval endpoint is the same. The auth dependency gains a second path (`require_phone_token` alongside `require_local_admin`).

### What counts as a "sensitive action"?

| Action | Requires 2FA? | Why |
|---|---|---|
| Pairing a new device | Yes | A new device joining the entity is the highest-risk action |
| Promoting a satellite to canonical | Yes | Changes which machine is the authoritative writer |
| Restoring from backup | Yes | Overwrites the current entity state |
| Creating a backup | No | Read-only operation; doesn't change state |
| Periodic replica push | No | Automated; doesn't require human approval |
| Reading memories/conversations | No | Normal operation |

### How the iOS app changes it later

The phone handles all "Yes" actions. Without the phone, the user does them at the canonical host's dashboard. With the phone, the user does them from the couch. The backend is the same; the surface is different.

---

## Q9 (new): What's the simplest onboarding that works without the iOS app?

### The user's experience

The user just installed Halbert on a new laptop. They want to join the existing entity.

**Step 1**: The laptop discovers the canonical host via mDNS. (Or the user types the URL if mDNS doesn't work — Tailscale, different VLAN.)

**Step 2**: The laptop sends a pairing request. The canonical host's dashboard shows: "A new device ('laptop') wants to join."

**Step 3**: The user walks to the canonical host (or opens its dashboard remotely) and clicks "Approve."

**Step 4**: The laptop enters the PIN (or scans the QR code if it has a camera).

**Step 5**: The canonical host issues a bearer token AND pushes a full replica. The laptop has the entity's mind from the moment it joins.

### The decision: This is the existing pairing flow + the Phase 1 replica push. No new UX needed.

The onboarding flow is already built (pairing handshake with approve-then-verify). Phase 1 adds the replica push at the end (step 5). The QR code (Q2) makes step 4 easier but isn't required.

The only friction is step 3: the user has to approve at the canonical host. Without the phone, that means walking to the server (or opening its dashboard from the laptop, which is possible but requires knowing the URL and having admin credentials).

### How the iOS app changes it later

Step 3 moves to the phone. The user taps "Approve" from the couch. Everything else is the same.

---

## Q10 (new): What's the simplest backup that works without the iOS app?

### The user's experience

The user wants to make sure their Halbert survives a disaster.

**Step 1**: In the dashboard, the user goes to Settings > Backup. They see: "Save your Halbert to a file. This file contains everything I am — my identity, my memories, our conversations. Put it somewhere safe."

**Step 2**: The user picks a destination: a USB key, a NAS share, an iCloud Drive folder. Any filesystem path.

**Step 3**: The user picks a passphrase. The system says: "Write this down. If you forget it, I can't be recovered."

**Step 4**: The system writes the `.halbert-backup` file. Done.

**To restore**: Install Halbert on fresh hardware. Onboarding: "Restore from Backup." Select the file. Enter the passphrase. The entity wakes up.

### The decision: File to a path + passphrase. That's Phase 2.

No cloud APIs, no OAuth, no sync engine. Halbert writes a file to a local path. The user's existing infrastructure (iCloud, Google Drive, Synology, manual USB) handles the offsite distribution. Halbert doesn't know or care what syncs that path.

### How the iOS app changes it later

The phone can hold the passphrase (Secure Enclave). The user scans a QR code from the phone instead of typing the passphrase. The phone can also remind the user to back up (monthly notification). But the file + passphrase works without the phone.

---

## Summary: The Cleanest Path

```
WHAT WE BUILD NOW (no phone dependency):

Phase 1: Peer Replication
  - Canonical host pushes memories.json + conversations.db to satellites
  - Satellites hold warm read-only replicas
  - Read-fallback when canonical is down
  - Manual promotion (one click)
  - QR code in the dashboard (encodes pairing data, ~50 lines of JS)

Phase 2: State Vault
  - .halbert-backup file (encrypted with passphrase)
  - Write to user-designated path (USB, NAS, cloud folder)
  - Restore from file on fresh hardware
  - OOBE: "Begin Fresh" | "Restore from Backup"


WHAT THE iOS APP ADDS LATER (no backend restructure):

  - Approval surface: phone taps "Approve" instead of walking to the server
  - Recovery key: phone holds the passphrase in Secure Enclave
  - QR scanner: phone scans QR codes for pairing and recovery
  - Status monitor: phone shows entity health, last backup, peer list
  - Backup reminders: monthly nudge to verify the backup file exists

  Backend changes needed: one new auth path (require_phone_token),
  one new aggregation endpoint (GET /api/entity/status). That's it.
```

The architecture is clean because:
- The approval API is already an API call, not a UI coupling
- The backup is a file, not a service
- The pairing flow is already a handshake, not a shared secret
- The replica push reuses the existing peer mesh
- The phone is a client of the existing API, not a new component

Nothing we build now needs to be undone when the phone ships. The phone is a new client of the same endpoints, with a new auth credential. The file + passphrase is the floor; the phone is the ceiling.
