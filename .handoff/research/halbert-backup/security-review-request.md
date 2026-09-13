# Security & Auth Review Request

**Date**: 2026-09-12
**Status**: Handoff — requesting review (completed; see [`security-review-response.md`](security-review-response.md))
**Scope**: Security layers and auth handling across the backup + replication + companion app plan
**Reviewer**: Security-focused pass before any of this code is written

> **Post-review note (2026-09-13):** The review response found that the "Existing Auth Surface" section below describes what the pairing code *would do* if the router were mounted the way the tests mount it. In production, the peers, approvals, and conversations routers sit behind `require_owner` (via `mount_api`), which rejects peer tokens entirely — so `POST /api/peers/pair` 401s for a credential-less remote caller, and every peer-token-bearing request to those routers 401s too. This is finding **F-A** in the response, and it invalidates the premise of Q1, Q4, Q8, Q9, and Q10 until the mounts are restructured. The corrections below are marked with **[F-A correction]** where the production behavior differs from what this section originally stated.

---

## What This Is

This is not a design doc. It is a list of specific security questions and concerns that need a reviewer's eyes before implementation begins. Every question is grounded in the actual auth code that exists today and the specific changes the plan proposes.

The plan spans three documents:
- [`implementation-plan.md`](implementation-plan.md) — Phase 1 (peer replication) + Phase 2 (State Vault backup)
- [`companion-frontend-handoff.md`](companion-frontend-handoff.md) — the active companion app plan (Tauri v2, not SwiftUI)
- [`ios-companion-handoff.md`](ios-companion-handoff.md) — superseded frontend, but backend sections 5-6 are carried forward

The security-relevant surfaces are:
1. The existing peer token system (`peers_config.py`, `peer_middleware.py`)
2. The existing local admin boundary (`require_local_admin` in `peer_middleware.py`)
3. The existing dashboard auth boundary (`auth.py` — host/origin checks, session tokens)
4. The proposed `trust_anchor` peer role and `require_trust_anchor` dependency
5. The proposed replica sync endpoint (`POST /api/peers/sync-replica`)
6. The proposed promotion endpoint (`POST /api/replica/promote`)
7. The proposed backup archive encryption (PBKDF2 + AES-256-GCM)
8. The proposed recovery key custody (iOS Keychain / Secure Enclave)
9. The proposed QR code pairing flow
10. Transport security (LAN HTTP, Tailscale HTTPS, future mTLS)

---

## The Existing Auth Surface (What We're Building On)

### Peer token system (`peers_config.py` + `peer_middleware.py`)

- One bearer token per peer. Generated during pairing (`POST /api/peers/verify`).
- Stored as SHA-256 hash in `peers.json` on the canonical host. Raw token lives on the peer.
- `verify_token()` does constant-time comparison (`hmac.compare_digest`) against the hash.
- Revoked tokens are rejected immediately. No grace period.
- Raw token is never logged. Only `node_id` and `node_name` appear in logs.
- `require_peer_auth` is the FastAPI dependency. Returns a `PeerContext` with `node_id`, `node_name`, `role`, `capabilities`.
- `optional_peer_auth` is the non-raising variant (returns None instead of 401).

> **[F-A correction]** The peer token system is sound in isolation, but in production the routers that would honour it (peers, approvals, conversations) sit behind `require_owner`, which only checks the dashboard API token. A peer token presented to those routers 401s. Only the compute-peer router (tagged `"compute-peer"`, in `SELF_AUTHENTICATING`) actually honours peer tokens in production. The WebSocket door (`websocket_authenticated`) also checks against the dashboard token only, not `PeersConfig` — see Q9.

### Local admin boundary (`require_local_admin` in `peer_middleware.py:262`)

- Checks `_is_local_client(request)` — does the request come from a loopback address?
- `_is_loopback_host()` parses the IP address (not the hostname string — that was A12 bug 4).
- Fails closed if no client address is available (SEC-1 fix).
- Deliberately NOT satisfiable by a peer token. The comment says: "these are the controls that rewrite this node's own identity — its entity mode, its body name, the token it trusts — and revoke other peers. A peer that could reach them could rename the body it federates with, or cut every other peer off (R10-F5)."

### Dashboard auth boundary (`auth.py`)

- `host_allowed()` — DNS-rebinding defense. Rejects unrecognized Host headers.
- `origin_allowed()` — WebSocket handshake defense. Returns True for no Origin (non-browser client).
- `credential_from_headers()` — extracts bearer token, X-Halbert-Peer-Token header, or session cookie.
- `require_owner` — the main auth dependency. Checks host, origin, and credential.
- `require_owner_stream` — same, plus `?token=` query parameter for SSE (EventSource can't set headers).
- `websocket_authenticated()` — WebSocket handshake check. Accepts `?token=` query parameter.
- `HostHeaderMiddleware` — rejects unrecognized Host headers before routing, even on public paths.

### The pairing flow (`dashboard/routes/peers.py`)

> **[F-A correction]** In production (`create_app()`), the peers router is mounted via `mount_api(peers.router, tags=["peers"])` at `app.py:1359`. `"peers"` is not in `SELF_AUTHENTICATING` (`auth.py:89`), so `mount_router` attaches `Depends(require_owner)` to every route. `require_owner` checks the credential against the dashboard API token only — peer tokens are never consulted. This means every route below 401s for a remote caller with a peer token (or no token) in production, even though the per-route guards described here are correct in isolation. The pairing tests mount the router bare (`app.include_router(...)`), bypassing the production door, so the suite proves the handshake works while production never runs it. See F-A in the response for the full empirical probe and the required fix (Step 1.0).

- `POST /api/peers/pair` — creates a pending pairing, returns `request_id`. Per-route: no guard (by design — PIN + approval are the boundary). **[F-A correction]** In production this 401s because the mount-level `require_owner` runs first and rejects credential-less remote callers.
- `GET /api/peers/pending` — lists pending pairings with PINs. Per-route: `require_local_admin`.
- `POST /api/peers/pending/{request_id}/approve` — the approval step. Per-route: `require_local_admin`.
- `POST /api/peers/verify` — exchanges the PIN for a bearer token. Checks `pending.approved` (the load-bearing line — a PIN match alone used to be enough, which issued tokens to anyone who asked twice). **[F-A correction]** In production this 401s for a credential-less remote caller because of the mount-level `require_owner`.
- `DELETE /api/peers/{node_id}` — revokes a peer. **[Correction]** Per-route: local-or-self (the local admin OR the peer named by `{node_id}` revoking itself — self-revocation exists at `peers.py:467-474` and is load-bearing: a phone must be able to unpair itself). Not `require_local_admin`-only as originally stated.

---

## Questions for the Reviewer

### Q1: Is `require_trust_anchor` safe to add alongside `require_local_admin`?

**The proposal** (from `companion-frontend-handoff.md` section 3.5):

```python
async def require_trust_anchor(request: Request) -> None:
    try:
        await require_local_admin(request)
        return
    except HTTPException as e:
        if e.status_code not in (401, 403):
            raise
    peer = await require_peer_auth(request)
    if getattr(peer, "role", None) != "trust_anchor":
        raise HTTPException(403, "Only trust_anchor peers can approve sensitive operations")
```

**The concern**: `require_local_admin` was deliberately designed to be unsatisfiable by a peer token (see the comment at `peer_middleware.py:262-274`). The plan proposes adding `require_trust_anchor` to three endpoints that currently use `require_local_admin`:
- `POST /api/peers/pending/{request_id}/approve` — approve a new device pairing
- `POST /api/approvals/{approval_id}/approve` — approve a staged command
- `POST /api/backup/restore` — restore from a backup archive

**Questions**:
1. Is it safe to allow a remote peer (the phone) to approve pairing requests? This is the exact action `require_local_admin` was designed to prevent — "a peer that could reach them could... cut every other peer off (R10-F5)."
2. The `trust_anchor` role is new. Can a peer with `role == "body"` or `role == "compute_provider"` escalate to `trust_anchor`? The role is set during pairing (`POST /api/peers/verify` returns the token with the role the pairing requested). Is the role field in the pairing request trusted, or validated?
3. The catch clause only re-raises 401/403 from `require_local_admin`. A 421 (Misdirected Request, from the Host header check) would propagate. Is that the right behavior? (The companion-frontend-handoff already corrected this from the original "catch all HTTPException" — is the correction sufficient? **[Confirmed in response Q1.3]** Yes — `require_local_admin` can only raise 403 (`peer_middleware.py:277`); it does no Host checking. The 421 path lives in `HostHeaderMiddleware`, which is app-level and runs before routing on every route including self-authenticating ones, so a bad Host never reaches the dependency at all. The correction is right, though it was defensive: the only thing the old catch-all form could swallow was a 403 that was about to be re-derived anyway.)
4. Should `require_trust_anchor` also check that the peer's token hasn't been revoked since the request started? `require_peer_auth` already does this (via `verify_token`), but the double-check in `require_trust_anchor` is worth confirming.

### Q2: The `trust_anchor` role — what can it do, and what stops escalation?

**The proposal**: A new role in `peers_config.py` alongside `body`, `compute_provider`, and legacy `satellite`.

**Capabilities**:
- Can approve peer pairing requests
- Can approve staged commands
- Can read aggregated status (`GET /api/entity/status`)
- Can stream voice audio (`/api/audio/stream`, `/api/audio/tts`)
- Cannot act as a compute provider
- Cannot receive database replica pushes

**Questions**:
1. Where is the role validated? `require_peer_auth` returns the `PeerContext` with the role, but it doesn't check the role — that's the caller's job. Is that the right boundary, or should `require_peer_auth` enforce role-based access?
2. Can a `trust_anchor` peer approve *another* `trust_anchor` pairing? If so, a compromised phone could pair another phone, which could pair another phone... Is there a limit on the number of `trust_anchor` peers?
3. Can a `trust_anchor` peer revoke other peers? `DELETE /api/peers/{node_id}` is guarded by local-or-self (the local admin OR the peer named by `{node_id}` — self-revocation is load-bearing for the phone's unpair-itself flow), not `require_trust_anchor`. Is that the right call? (The phone can't revoke *other* peers — only the local admin or the peer itself can. Is that a limitation or a feature?)
4. The `capabilities` field on `PeerContext` is a list of strings. Is `trust_anchor` a role or a capability? If it's a role, should the capabilities list also include something like `"approve_pairing"`, `"approve_command"`, `"approve_restore"` for finer-grained control?

### Q3: Transport security — is LAN HTTP acceptable for the companion app?

**Current state**: The dashboard binds `127.0.0.1` by default. `HALBERT_HOST` can open it to the LAN. The companion app connects over LAN HTTP (or Tailscale HTTPS).

**The concern**: The bearer token travels in cleartext over LAN HTTP. Anyone on the same network with a packet sniffer can capture it. The token is long-lived (no expiry). A captured token grants `trust_anchor` privileges.

**Questions**:
1. Is cleartext LAN HTTP acceptable for v1, with a clear warning to the user? Or should the companion app refuse to connect over HTTP (HTTPS only)?
2. The multi-node review (`HANDOFF-REVIEW-2026-09-12.md`) flagged cleartext peer transport as a real remaining security issue. Does the companion app make this worse (the phone is on a less-trusted network — coffee shop WiFi, etc.)?
3. Tailscale provides TLS automatically. Should the companion app detect Tailscale and prefer the Tailscale URL? Or should the user be responsible for choosing HTTPS vs HTTP?
4. The `?token=` query parameter for WebSocket auth is already accepted (see `websocket_authenticated` in `auth.py:474`). The token in a URL lands in access logs and `Referer` headers. The companion app uses WebSocket for audio streaming. Is this acceptable, or should the companion app use a different auth mechanism for WebSocket?
5. The plan mentions "future mTLS with pinned peer certificates." Is that a prerequisite for v1, or can it come later? What's the risk of shipping v1 without it?

### Q4: The replica sync endpoint — is it safe to accept snapshots from a peer?

**The proposal** (from `implementation-plan.md` Step 1.3):

```python
@router.post("/api/peers/sync-replica")
async def receive_replica(
    request: Request,
    _auth: None = Depends(require_peer_auth),
) -> Dict[str, Any]:
```

**The concern**: The satellite accepts a snapshot bundle (files) from the canonical host and writes them to disk (`~/.local/share/halbert/canonical_replica/`). The bundle contains `memories.json` and `conversations.db`.

> **[F-D correction — design gap]** The pairing flow is one-directional: when the satellite pairs, the *canonical* mints and stores a credential, and the satellite receives the raw token. The satellite's `PeersConfig` has **no record of the canonical** and has never issued it a token. So when the canonical POSTs to the satellite's `/api/peers/sync-replica`, `require_peer_auth` on the satellite finds no matching peer → 401. There is no valid credential to present. The plan needs a reverse-pairing step (the satellite issues the canonical a token and records it as `role="canonical"`) or an operator-pasted canonical entry in the satellite's `peers.json`. Without this, Step 1.3's tests pass against bare-mounted routers and the feature 401s in production — the same failure mode as F-A.

**Questions**:
1. `require_peer_auth` accepts any valid peer token. Should the sync-replica endpoint check that the sender's role is `canonical` (or at least not `trust_anchor`)? The phone shouldn't be pushing replicas.
2. The snapshot bundle is validated (SHA-256, `PRAGMA quick_check`, JSON parse). But what about the *content*? A malicious canonical host could push a snapshot with crafted conversation data. Is the satellite trusting the canonical host's data, or should there be additional validation?
3. The replica is written to `canonical_replica/` via an atomic swap (temp dir + rename). Is there a path traversal risk in the bundle's filenames? The manifest records filenames — are they validated to be within the replica directory?
4. The replica is never executed or loaded until promotion. Is that sufficient isolation, or should the replica directory be sandboxed (e.g., read-only until promotion)?

### Q5: The promotion endpoint — is it safe to promote from a remote peer?

**The proposal** (from `implementation-plan.md` Step 1.7):

```python
@router.post("/api/replica/promote")
async def promote(
    _admin: None = Depends(require_local_admin),
) -> Dict[str, Any]:
```

**The concern**: Promotion overwrites the satellite's active state (`memories.json`, `conversations.db`) with the replica's contents and clears the canonical URLs in `being.yml`.

**Questions**:
1. The endpoint is guarded by `require_local_admin` (not `require_trust_anchor`). This means the phone can't trigger promotion remotely — the user has to be at the satellite's dashboard. Is that the right call? (The companion-frontend-handoff excludes `/api/replica/promote` from `require_trust_anchor` — "the replication subsystem does not exist yet." When it does exist, should the phone be able to trigger it?)
2. Promotion overwrites `being.yml` (clears `canonical_memory_url` and `canonical_thread_url`). Is there a risk of the user losing their local config? Should promotion create a backup of `being.yml` before modifying it?
3. Promotion copies the replica's `conversations.db` over the local one. If the satellite has its own local conversations (it shouldn't — it's a body, not a canonical host — but what if it was promoted before and then demoted?), those conversations are lost. Should promotion check for local state before overwriting?
4. After promotion, the old canonical host (when it comes back) still thinks it's canonical. Is there a fencing mechanism, or is "the user manually re-pairs the old host" the only defense? The implementation plan says "manual promotion" — is that sufficient, or does the plan need a generation/epoch token?

### Q6: Backup archive encryption — is PBKDF2 + AES-256-GCM sufficient?

**The proposal** (from `implementation-plan.md` Step 2.2):

- KDF: PBKDF2-HMAC-SHA256, 600,000 iterations (OWASP 2023 recommendation)
- Cipher: AES-256-GCM (authenticated encryption)
- Per-file random nonce (12 bytes, prepended to ciphertext)
- Salt: random per archive (stored in manifest)
- No BIP-39 mnemonic. User-chosen recovery passphrase.

**Questions**:
1. Is 600,000 iterations sufficient for PBKDF2-HMAC-SHA256? OWASP 2023 says yes. Is there a reason to go higher (the backup contains `body.key` — the entity's private Ed25519 key)?
2. The salt is stored in the manifest (plaintext). Is that acceptable? (The salt doesn't need to be secret — it just needs to be unique per archive. But confirm.)
3. The nonce is 12 bytes (96 bits), random per file. AES-GCM with a random nonce is safe up to ~2^32 encryptions under the same key. We're encrypting ~10 files per archive. Is the random nonce safe, or should it be deterministic (counter-based)?
4. The master key is derived from the passphrase + salt. Per-file keys are not used — the same master key encrypts every file. Is that acceptable, or should each file get its own key (wrapped by the master key)? **[Correction — the plan contradicts itself.]** Step 2.2's `encrypt_file` encrypts with the master key directly; Step 2.3's `create_backup` docstring says "encrypt each file with per-file keys wrapped by master key." These cannot both ship. The response (Q6.4) recommends reconciling to the simple one (master key, random nonce per file) — key-wrapping buys per-file revocation granularity nobody uses in a ten-file archive.
5. The `cryptography` package is a new optional extra (`backup`). The plan says "encryption is mandatory, not optional" (the archive contains `body.key`). But the import is lazy and the engine "refuses to create encrypted archives if absent." Is "refuse to run" the right behavior, or should the engine fall back to plaintext with a warning? (The plan says refuse — confirm that's the right call for a backup containing identity keys.)
6. The passphrase is never sent to the server. It's a local secret. But the companion app stores it in the iOS Keychain. Is that an acceptable trust boundary, or should the passphrase never leave the user's head (typed manually on restore)?
7. **[New — from response Q6 addition]** Should each ciphertext bind its filename as AES-GCM associated data (`AESGCM.encrypt(nonce, plaintext, name.encode())`)? It's free, and it makes intra-archive file swaps (rename `conversations.db.enc` to `memories.json.enc`) fail at decrypt instead of at parse. Should digest verification be part of the restore engine, not just the vault writer?

### Q7: Recovery key custody — is the iOS Keychain the right place?

**The proposal**: The backup passphrase is stored in the iOS Keychain with `kSecAttrAccessibleWhenUnlockedThisDeviceOnly` (Secure Enclave-backed, no iCloud sync).

**Questions**:
1. `WhenUnlockedThisDeviceOnly` means the key is accessible while the device is unlocked, but not after a reboot until the first unlock. Is that the right access level? Should it be `WhenPasscodeSetThisDeviceOnly` (requires a passcode to be set, and the key is destroyed if the passcode is removed)?
2. The Keychain entry is not synced to iCloud (`kSecAttrSynchronizable = false`). Good. But what about iTunes encrypted backups? Does an iTunes backup of the phone include Keychain entries? (It does, if the backup is encrypted. Is that a risk?)
3. If the phone is lost, the passphrase is gone. The user needs to have written it down (or printed the QR code). Is the plan's "three nudges" (onboarding, periodic, pre-update) sufficient to ensure the user has a backup of the passphrase?
4. The plan says the phone can display the passphrase as a QR code for restore. The QR code contains the passphrase in cleartext. Is that acceptable? (It's a local display, scanned by the new machine. But anyone who sees the screen can read it.)

### Q8: QR code pairing — is the QR content safe?

**The proposal** (from `implementation-plan.md` Step 1.9 and `companion-frontend-handoff.md` section 7.3):

> **[Correction — the plan docs contradict each other.]** `companion-frontend-handoff.md` §7.3 says "the QR only carries the URL… the extra step [PIN] is the security boundary." But `implementation-plan.md` Step 1.9 has `PairingQRCode.tsx` encode `{url, request_id, pin, entity}` — the PIN *is* in the QR payload. The request originally asserted "It does NOT encode a pairing token or PIN," which matched the companion-handoff but contradicted the implementation plan that would actually get built. This is a live contradiction, not a hypothetical one. The response (Q8) recommends dropping `pin` from the QR payload — `url`, `request_id`, `entity` are fine (`request_id` saves a round trip and is not a secret); the PIN should be shown as text below the QR for the headless fallback and stay out of the scannable payload.

The intended pairing flow is: scan QR → get URL (+ `request_id`) → `POST /api/peers/pair` → desktop shows PIN → user enters PIN → `POST /api/peers/verify`.

**Questions**:
1. The QR code only contains the URL (+ `request_id`). Is that sufficient? The user still has to enter the PIN manually. Is the QR code worth the UX investment if it only saves typing the URL?
2. The companion-frontend-handoff says "the QR only carries the URL" and "the extra step [PIN] is the security boundary." Is the PIN a sufficient security boundary? It's a 4-digit code (10,000 possibilities). The pairing flow has `PAIRING_MAX_ATTEMPTS` (**[Correction]** at `peers.py:92`, not line 371 — the original line ref was stale) — how many attempts is that? Is it enough to prevent brute force?
3. The QR code is displayed on the canonical host's dashboard. Anyone in the room can photograph it. But it only contains the URL (+ `request_id`, a random UUID) — no secret. Is that acceptable?
4. Should the QR code also encode a one-time token that pre-approves the pairing (skipping the PIN step)? The companion-frontend-handoff recommends against this ("the QR only carries the URL"). Is that the right call? (The user has to be physically present to read the PIN — that's the security boundary. A one-time token in the QR would remove that boundary.)

### Q9: Voice audio streaming — is the WebSocket auth sufficient?

**The proposal**: The companion app streams PCM audio to `/api/audio/stream` via WebSocket. Auth is via `?token=` query parameter (the same mechanism the dashboard uses).

> **[F-A correction]** `websocket_authenticated` (`auth.py:456-475`) checks the credential against `AuthState.token` — the *dashboard token* — via `state.check`. A peer token in `?token=` is refused (1008); empirically confirmed in the response's probe. The companion-handoff's "the iOS app uses this with its Keychain-stored bearer token" only works if that stored token is the dashboard token (F-B). **Required change:** extend `websocket_authenticated` to verify against `PeersConfig` as well (peer path mirrors the `optional_peer_auth` extraction), so a `trust_anchor` peer can open `/api/audio/stream` and `/api/audio/tts` with its own revocable token. This is a prerequisite for the voice MVP, not an enhancement.

**Questions**:
1. The `websocket_authenticated` function in `auth.py:456` accepts `?token=` query parameter. The token is the peer bearer token. Is it acceptable to put a long-lived `trust_anchor` token in a URL? (It lands in access logs.)
2. The audio stream goes to `AudioCoordinator.get_ingress("dashboard")` for VAD, ASR, and CAM++ speaker identification. Is the audio stream authenticated as a `trust_anchor` peer, or does it lose the peer context after the WebSocket handshake? (The WebSocket handler may not have the `PeerContext` — it's a WebSocket, not a FastAPI route.)
3. The CAM++ speaker identification (`voice_auth_gate.py`) uses a 0.82 cosine-similarity threshold for admin voice. Is the phone's audio stream trusted for speaker identification, or is it treated as untrusted input? (A compromised phone could play a recording of the admin's voice.)
4. The TTS downlink (`/api/audio/tts`) streams synthesized audio back. Is the downlink authenticated? (The companion app subscribes with a `session_id` — is the `session_id` a secret, or can it be guessed?)

### Q10: Staged command approval — is the Face ID gate sufficient?

**The proposal**: The companion app shows staged commands and the user approves with Face ID. On biometric success, the app posts to `/api/approvals/{id}/approve` with its Keychain-stored bearer token.

**Questions**:
1. Face ID is a local biometric check on the phone. The approval is a bearer token POST to the server. The server doesn't know that Face ID was performed — it only knows that a valid `trust_anchor` token was presented. Is that sufficient? (The phone's app enforces Face ID before sending the token. A compromised app could skip Face ID and send the token directly.)
2. Should the server require a cryptographic proof of biometric authentication (e.g., a signed assertion from the Secure Enclave)? This would require a native iOS component (the Tauri plugin) to generate the signature. Is that worth the complexity for v1?
3. The staged command approval is for privileged actions (`systemctl`, `apt`, firewall changes, file deletions). If a compromised phone approves a destructive command, the damage is done. Is there a server-side safeguard (e.g., a confirmation step on the canonical host's dashboard), or is the phone approval the final word?
4. The `POST /api/approvals/{approval_id}/approve` endpoint — is the `approval_id` guessable? **[Correction]** The IDs are server-generated UUIDs in the paths that create them (`approvals.py:136`), not sequential integers. But the engine accepts *any* caller-supplied id, and `request_id` is concatenated into a filesystem path in `approval/engine.py` (`requests_dir / f"{request_id}.json"`) with no validation — that's **F-C** in the response, an arbitrary-read/write primitive behind the auth door (an id containing `../` reads or writes outside `requests_dir`). This becomes peer-reachable the moment Q1 lands. Fix: reject any `request_id` that is not UUID-shaped before it touches a path.

### Q11: Lost device and revocation — is the recovery path sound?

**The proposal**: If the phone is lost, the user revokes it from the canonical host's dashboard (`DELETE /api/peers/{phone_node_id}`). The token is invalidated immediately.

**Questions**:
1. The revocation is local-or-self (the local admin OR the peer named by `{node_id}` revoking itself) — **[Correction]** not `require_local_admin`-only as originally stated. The user has to be at the canonical host's dashboard to revoke *another* peer. If the canonical host is also down (the phone was the only way to reach it remotely), the user is locked out of remote control until the canonical returns. Is that acceptable?
2. After revocation, the phone's token is dead. But the phone still has the recovery passphrase in the Keychain. If the phone is stolen and the thief bypasses the passcode (e.g., via a forensic tool), they have the passphrase. Is that a risk? (The passphrase alone doesn't grant access to the entity — you also need the `.halbert-backup` file. But if the thief has both the phone and the backup file...)
3. The plan says "the user can revoke the phone from the canonical host's dashboard." But what if the user doesn't notice the phone is lost for days? The token is valid until revoked. Is there a case for token expiry (e.g., the phone re-pairs every 30 days)?
4. What happens if the user loses ALL devices (phone + canonical host + all satellites)? The `.halbert-backup` file + passphrase is the only recovery path. Is that documented clearly enough?

### Q12: Split-brain and fencing — is manual promotion safe without a generation token?

**The proposal** (from `open-questions-resolved.md` Q1): Manual promotion. The user clicks a button. No automatic failover, no lease, no election.

**The concern**: After promotion, the old canonical host (when it comes back) still thinks it's canonical. Two canonical hosts can exist simultaneously.

**Questions**:
1. The implementation plan says "the old canonical host will need to re-pair when it comes back." Is that the fencing mechanism? (The promoted satellite has a new `peers.json` that doesn't include the old canonical host's token. The old canonical host's token is invalid on the new canonical. But the old canonical host still has its own `peers.json` with the satellite's token — it can still push replicas to the satellite, which the satellite would reject because the sender's role isn't `canonical`... wait, does the satellite check the sender's role on sync-replica? See Q4.)
2. Is "manual re-pairing" a sufficient fence, or does the plan need a generation/epoch token? (A generation token would be a number in `being.yml` that increments on every promotion. A peer rejects sync-replica pushes from a sender with a lower generation. This prevents the old canonical host from pushing stale data to the new canonical.)
3. What happens to in-flight writes when the old canonical host comes back? If the old canonical host accepted a conversation message while the satellite was promoted, that message is lost (the satellite's replica doesn't have it, and the old canonical host's data is stale). Is that acceptable, or does the plan need a write-replay mechanism?
4. The `open-questions-resolved.md` Q1 says "the warm replica already solves the acute problem: no amnesia during reboots or short outages." But a promotion is not a short outage — it's a topology change. Is the warm replica sufficient, or does promotion need additional safeguards?

---

## What the Reviewer Should Produce

For each question:
1. **Is the proposed approach safe?** (Yes / No / With changes)
2. **If "with changes," what changes?** (Specific, implementable)
3. **Is there a simpler approach that achieves the same security?** (The user's standing preference is the simplest path that works.)
4. **Is this a blocker for v1, or can it be deferred?** (Some of these may be acceptable risks for an initial release with no users.)

The reviewer should also flag any security concerns not listed here — this list is from the plan's perspective, not from an adversarial review.

---

## Files to Review Against

| File | What it contains |
|---|---|
| `halbert_core/halbert_core/federation/peer_middleware.py` | `require_peer_auth`, `require_local_admin`, `optional_peer_auth` |
| `halbert_core/halbert_core/federation/peers_config.py` | Token storage (SHA-256 hashes), `verify_token`, revocation |
| `halbert_core/halbert_core/dashboard/auth.py` | `host_allowed`, `origin_allowed`, `require_owner`, `websocket_authenticated` |
| `halbert_core/halbert_core/dashboard/routes/peers.py` | Pairing flow: `pair`, `pending`, `approve`, `verify`, `revoke` |
| `halbert_core/halbert_core/integrations/voice_auth_gate.py` | CAM++ speaker identification, 0.82 cosine-similarity threshold |
| `halbert_core/halbert_core/dashboard/routes/approvals.py` | Staged command approval endpoints |
| `halbert_core/halbert_core/dashboard/routes/websocket.py` | Audio stream WebSocket handlers |
| `halbert_core/halbert_core/crypto/storage.py` | `body.key` custody (Keychain, Secret Service, file fallback) |
| `halbert_core/halbert_core/identity.py` | `resolve_entity_role`, `resolve_entity_name`, `ENTITY_ROLE_CANONICAL/BODY/INDEPENDENT` |
| `halbert_core/halbert_core/config/being_config.py` | `canonical_memory_url`, `canonical_thread_url`, `peer_token` — **[F-A note]** the docs treat `peer_token` as a peer token, but the production door only honours it if it is the dashboard token. When F-A lands, decide and document which token belongs in that field, and consider naming it for what it is. |
| `halbert_core/halbert_core/dashboard/app.py` | `create_app()`, `mount_api()` — **[F-A]** the production mounts that put `require_owner` in front of the peers/approvals/conversations routers |
| `halbert_core/halbert_core/dashboard/routes/approvals.py` | Staged command approval endpoints — **[F-C]** `request_id` reaches filesystem path concatenation unvalidated |
| `halbert_core/halbert_core/approval/engine.py` | **[F-C]** `get_request` / `_save_request` concatenate `request_id` into a path with no UUID-shape validation |
| `DECISIONS.md` | FDR-02 (license), FDR-03 (bundle IDs), SEC-1 (fail-closed), SEC-D10 (platform config) |
