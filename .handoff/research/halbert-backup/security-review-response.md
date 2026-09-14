# Security & Auth Review — Response

**Date**: 2026-09-13
**Status**: Review complete
**In response to**: [`security-review-request.md`](security-review-request.md)
**Method**: Every claim below was checked against the current code, and the load-bearing ones were verified **empirically** against the real production app (`create_app()` with production mounts, real client addresses, TestClient). The probe is reproduced in the appendix so the next session can re-run it.

---

## Verdicts at a glance

| Q | Subject | Verdict | v1 blocker? |
|---|---|---|---|
| Q1 | `require_trust_anchor` alongside `require_local_admin` | **With changes** — and it does not work at all against today's mounts (see F-A) | Yes — F-A is |
| Q2 | `trust_anchor` role definition and escalation | Safe with three cheap constraints | No |
| Q3 | Transport security (LAN HTTP) | With changes — consent-gated HTTP, HTTPS for anything off-LAN | Yes for the companion app |
| Q4 | Replica sync endpoint | With changes — sender-role check, filename allowlist, and a protocol gap to close (F-D) | Yes — F-D is |
| Q5 | Promotion endpoint | Safe — local-admin only is right; add pre-promotion snapshot + promoted-refuses-pushes fence | No |
| Q6 | PBKDF2 + AES-256-GCM | Safe — refuse-without-cryptography is correct; reconcile the per-file-key contradiction; add filename AAD | No |
| Q7 | iOS Keychain custody | Safe with `WhenPasscodeSetThisDeviceOnly` | No |
| Q8 | QR pairing | Safe if the PIN stays out of the QR — **two plan docs contradict each other on this** | Cheap fix, do before 1.9 |
| Q9 | Voice WebSocket auth | **Does not work as planned** — `websocket_authenticated` accepts only the dashboard token (F-A corollary) | Yes — required change |
| Q10 | Face ID gate for approvals | Acceptable for v1 — the token is the credential; add ID sanitisation | No |
| Q11 | Lost device / revocation | Sound; document the canonical-down+phone-lost corner; defer expiry | No |
| Q12 | Split-brain / fencing | Acceptable for v1 with the receiver-side fence; defer epoch tokens | No |

---

## Findings that reframe the questions

These were found while verifying the request's premises. **F-A invalidates the premise of Q1, Q4, Q8, Q9, Q10 and the entire companion-app backend plan.** Read this section before the per-question answers; several questions are answered primarily by reference to it.

### F-A (Critical): the peers and approvals routers sit behind `require_owner` in production, and `require_owner` does not accept peer tokens

The request's "Existing Auth Surface" section describes what the pairing code *would do* if the router were mounted the way the tests mount it. In production it is not.

- `dashboard/app.py:1359` — `mount_api(peers.router, tags=["peers"])`. `dashboard/app.py:1318` — `mount_api(approvals.router, prefix="/api/approvals", tags=["approvals"])`. `dashboard/app.py:1368` — conversations, same.
- `dashboard/auth.py:89` — `SELF_AUTHENTICATING = ("compute-peer", "websocket")`. `"peers"`, `"approvals"` and `"conversations"` are **not** in it, so `mount_router` (`auth.py:452`) attaches `Depends(require_owner)` to every route on those routers.
- `require_owner` runs **before** any route-level dependency, and `AuthState.check` (`auth.py:350-356`) compares the credential against **one** value: the dashboard API token (`load_or_create_token()` — `<state_dir>/api-token` or `HALBERT_API_TOKEN`). Peer tokens live in a different namespace entirely (`PeersConfig`, SHA-256 hashes in `peers.json`) and are never consulted.

Empirically verified against the real app:

| Caller | Route | Result |
|---|---|---|
| Remote, no credential | `POST /api/peers/pair` | **401** — a new satellite cannot start pairing |
| Remote, no credential | `POST /api/peers/verify` | **401** |
| Remote, valid **peer** token | `GET /api/peers/list` | **401** |
| Remote, valid **peer** token | `GET /api/conversations/health` | **401** — the P3b conversation mesh rejects genuine peer tokens |
| Remote, valid **peer** token | `POST /api/compute/v1/chat/completions` | **503** — auth *passed* (no model configured); the one router that honours peer tokens |
| Remote, valid **peer** token | WS `/api/audio/stream?token=<peer>` | **rejected (1008)** |
| Remote, valid **dashboard** token | WS `/api/audio/stream?token=<dashboard>` | connected |

Consequences:

1. **The documented pairing flow is unreachable in production.** `POST /api/peers/pair` is described in the request (and every handoff doc) as "no auth required — the request itself is the auth intent." It 401s. A phone or satellite with no credential cannot join, period. The pairing tests (`tests/test_peer_pairing_security.py:59`) mount the router with bare `app.include_router(...)`, bypassing the production door — so the suite proves the handshake works while production never runs it.
2. **The proposed `require_trust_anchor` dependency can never be reached by a phone.** It would be a per-route dependency on routes that already carry mount-level `require_owner`, which runs first and 401s any peer token before `require_trust_anchor` executes.
3. **The same applies to `/api/peers/sync-replica` (Step 1.3)** — the canonical's push would arrive with a peer token and die at `require_owner` — and to `GET /api/entity/status` (new `entity.py` router, mounted via `mount_api` → `require_owner` by default).
4. **The existing P3b conversation mesh has the same defect.** `PeerConversationStore` sends `being.yml`'s `peer_token` as a Bearer credential; if that value is a genuine peer token from `/api/peers/verify`, production 401s it. The mesh can only be working today if `peer_token` actually holds the canonical's **dashboard token** — the full owner credential — which is a materially weaker security model than the per-peer token system the docs describe. `tests/test_conversation_routes.py` also mounts its router bare, so production behavior is untested.

**The fix (required before any of the planned code is written):** make the peers router self-authenticating — add `"peers"` to `SELF_AUTHENTICATING` — *and* give every route in `peers.py` an explicit per-route guard, because the mount-level `require_owner` is currently the only thing standing in front of several routes that have none. Concretely, before the flip, audit and assign:

| Route | Per-route guard it needs |
|---|---|
| `POST /api/peers/pair` | none (by design — PIN + approval are the boundary) |
| `GET /api/peers/pending`, approve, reject-pending | `require_local_admin` (already present) |
| `POST /api/peers/verify` | PIN + `pending.approved` (already load-bearing; no other guard needed) |
| `GET /api/peers/list` | `require_peer_auth` (already present) |
| `DELETE /api/peers/{node_id}` | local-or-self (already in code) |
| `PUT /api/peers/{node_id}/wol` | `require_peer_auth` — but see F-E |
| `POST /api/peers/compute-peer` | **needs a new guard** — writes LLM config *including a token*; today only the mount protects it |
| `GET /api/peers/discovered` | needs a guard or deliberate public listing (currently returns `[]`, low risk) |

The approvals router is harder: **every read route** (`GET ""`, `/history`, `/proposals`, `/{request_id}`) relies on mount-level `require_owner` and carries sensitive content (command text, reasoning, paths). Making that router self-authenticating means adding `require_owner` per-route to all reads and `require_trust_anchor` to the two decision routes — a real, deliberate restructure, not a one-line dependency addition. A census-style test asserting the production mounts (not bare `include_router`) is the merge gate for this work.

### F-B (Critical, follows from F-A): as mounted today, the companion app's only working credential is the owner token

If the app is built against the current mounts, the phone cannot pair (F-A), so the only credential that will actually work is the canonical's dashboard token pasted into the app. That token is the **owner credential for the entire machine** — terminal exec, arbitrary file write, `/api/state/forget`, `/api/settings/policy`. "The phone is a least-privilege trust anchor" silently becomes "the phone holds the owner key." This is a security regression the plan must not ship into: fix F-A first, then the phone's Keychain holds a revocable, role-scoped peer token.

### F-C (High): approval IDs are used as file path components with no validation

`approval/engine.py`: `get_request` does `requests_dir / f"{request_id}.json"`, and `_save_request` writes the same path. `request_id` arrives from the URL. An id containing `../` reads (`GET /{request_id}`) and — worse — writes (`approve`/`reject` persist through `_save_request`) outside `requests_dir`, with partially attacker-influenced JSON content. Today the door in front of it is `require_owner`, so this is not a remote-unauthenticated hole, but it is an arbitrary-file-write primitive for any process holding the token, and it becomes reachable by a trust_anchor peer the moment Q1 lands. **Fix:** reject any `request_id` that is not UUID-shaped before it touches a path (also answers Q10.4). Cheap; do it in the same branch as F-A.

### F-D (High, design gap): nothing in the plan says what credential the canonical uses *to push*, or what the satellite calls it

The pairing flow is one-directional: when the satellite pairs, the **canonical** mints and stores a credential, and the satellite receives the raw token. The satellite's `PeersConfig` has **no record of the canonical** and has never issued it a token. So when the canonical POSTs to the satellite's `/api/peers/sync-replica`:

- `require_peer_auth` on the satellite finds no matching peer → 401. There is no valid credential to present.
- Even once one exists, Q4.1's sender-role check has no role to check — "is the sender the canonical?" is unanswerable until the satellite records the canonical with a defined role.

The plan needs one of: (a) a reverse-pairing step in which the satellite issues the canonical a token and records it as `role="canonical"`; or (b) an operator-pasted canonical entry in the satellite's `peers.json` with the same effect. Option (a) can reuse the existing handshake in the other direction. Without this, Step 1.3's tests will pass against bare-mounted routers and the feature will 401 in production — the same failure mode as F-A, repeating.

### F-E (Medium): any authenticated peer can rewrite any other peer's Wake-on-LAN settings

`PUT /api/peers/{node_id}/wol` guards with `require_peer_auth` but never checks that the caller is the local admin or the named peer. Peer A can silently disable peer B's wake-from-sleep (or point B's `wol_mac` elsewhere). Same class as the R10-F5 revocation finding the request quotes. Fix: local-or-self, same predicate `DELETE` already uses. One guard, do it with F-A.

### F-F (Medium): TTS subscription is by guessable `session_id`, cross-persona

`/api/audio/tts?session_id=...` subscribes to any session's synthesised audio; `session_id` is a correlation handle, not a secret (Q9.4 asks exactly this). Within one owner's devices this is acceptable; note the interaction with **guest personas** — `peers_config.py` reserves the `home:` namespace precisely because sibling-home sessions exist, so a subscribed client can potentially listen to a *guest session's* TTS. For v1: acceptable with eyes open; the fix when needed is to hand the subscriber the session id only through the same authenticated channel that created the turn. Flagging so it's a decision, not a surprise.

---

## Q1 — `require_trust_anchor` alongside `require_local_admin`

**Verdict: with changes — and blocked on F-A.**

1. **Is it safe for a remote peer to approve pairings?** Yes, with one carve-out, and the R10-F5 fear does not apply as stated. `require_local_admin`'s comment guards the controls that *rewrite identity or cut peers off* — revocation, entity mode, body name, the trusted token. Approving a pairing **adds** a peer; it revokes nothing and rewrites nothing. Provided revocation, entity config, and `require_local_admin`'s other subjects stay local-only, letting the phone approve *additions* is the possession-factor 2FA the resolved-questions doc (Q8) already decided on. **Carve-out:** the pending-approval endpoint must refuse to approve a pending request whose requested `role == "trust_anchor"` when the caller is a peer — trust anchors are minted only at the machine. That single check closes Q2.2's "phone pairs phone" chain.
2. **Escalation to `trust_anchor`:** not possible remotely today. `require_peer_auth` returns whatever role is on the stored credential; the only remote mutation path (`set_capabilities`) writes `capabilities`, never `role`. A compromised *body* peer can revoke **itself** and re-pair requesting `trust_anchor` — but re-pairing still needs an approval act, and with the carve-out above that approval must happen at the machine. The role string is not enum-validated at `add_peer` (any string is stored) — add a `KNOWN_PEER_ROLES` check alongside the existing `KNOWN_PEER_CAPABILITIES` warning so garbage roles can't be minted through a hand-edited pairing. Note also that the approving operator *does* see the requested role (`PendingPairingInfo.role`), so the PIN screen is where a social-engineered `role=trust_anchor` is visible — keep that field prominent in the UI.
3. **The 401/403 catch is correct and sufficient.** `require_local_admin` can only raise 403 (`peer_middleware.py:277`); it does no Host checking. The 421 Misdirected path lives in `HostHeaderMiddleware`, which is app-level and runs before routing on *every* route including self-authenticating ones — so a bad Host never reaches the dependency at all. The correction from "catch all `HTTPException`" to "catch 401/403" is right, though it was defensive: the only thing the old form could swallow was a 403 that was about to be re-derived anyway.
4. **Revocation staleness:** no concern. `verify_token` re-reads the live store on every request; a revoked phone is dead within one request cycle, already tested.

**Simpler path:** none — this is the simplest shape. But its realisation is the F-A restructure, which the plan currently doesn't contain at all. Add it as **Step 1.0** in the implementation plan: *re-mount the peers and approvals routers with explicit per-route guards + a production-mount census test.* Every later step silently 401s without it.

**Blocker:** yes — F-A, before any trust_anchor code merges.

---

## Q2 — the `trust_anchor` role

**Verdict: safe with three cheap constraints.**

1. **Where is the role validated?** Caller-side is the right boundary for v1: `require_peer_auth` is the *authentication* choke point (one token, one revocation path — the C1 design), and `require_trust_anchor` is the *authorisation* predicate that consumes it. That mirrors how `capabilities` already work (`has_capability` at the call site). Do not push role checks into `require_peer_auth`; it would give every peer-bearing route an implicit policy and split the "who may do what" decision across two files.
2. **Can a trust_anchor approve another trust_anchor?** Close it by policy, not by counting: the carve-out in Q1.1 (peer-callers cannot approve `role=trust_anchor` pairings) is simpler than a count cap, is testable in one line, and makes "the phone can never mint a phone" an invariant rather than a heuristic. No limit on *how many* trust anchors a local admin chooses to mint — that's the operator's call, made at the machine.
3. **Can trust_anchor revoke peers?** No, and that's correct. `DELETE /api/peers/{node_id}` is local-or-self (the request's description "require_local_admin only" is slightly off — self-revocation exists at `peers.py:467-474`, and it's load-bearing: a phone must be able to unpair *itself*). A phone that could revoke others would re-open R10-F5 verbatim. Feature, not limitation. **But:** F-E is the same bug class sitting in the WoL route today — fix it in the same branch.
4. **Role or capability?** Role. The capabilities list is hardware routing (`gpu_llm`, `vision`, …) — what a peer *is made of*. Trust-anchor powers are *identity-level grants* about what a peer *is trusted to do*, and there are exactly three of them (`approve_pairing`, `approve_command`, `approve_restore`) — one role covers all three for v1. If the day comes where a trust anchor should hold some subset, promote to capabilities then; not now. Adding a parallel fine-grained system now is the one thing the subtractive contract says not to do.

**Simpler path:** role + the Q1.1 carve-out + enum validation at `add_peer`. Three small pieces.

**Blocker:** no — but it lands only after F-A.

---

## Q3 — transport security

**Verdict: with changes; the strongest form of this finding is F-B.**

1. **Cleartext LAN HTTP:** not acceptable as a silent default, for one reason the request understates: under F-B, what travels is not "a trust_anchor token" — it's the *owner credential*. Even post-F-A, a long-lived, non-expiring approval credential on a wireless network a phone carries to coffee shops is a different asset than the same token on a rack-mounted host that never leaves the house. **Require:** the app refuses plaintext connections to non-loopback hosts by default; connecting over `http://` demands an explicit, per-host "I'm on my home LAN" consent; anything off-LAN must be HTTPS (Tailscale). That is one frontend gate — cheap, honest, and it matches the fail-closed posture the codebase already takes elsewhere (`guard_bind` refuses an unauthenticated wide bind outright).
2. **Does the companion make the cleartpeer-transport finding worse?** Yes, qualitatively: the host sits on a network the user controls; the phone roams onto networks they don't. The multi-node review's finding and this plan should be treated as one item — the phone is the first *roaming* holder of a Halbert credential.
3. **Tailscale preference:** detect and prefer automatically when a Tailscale interface is present, but let the user override — auto-detection logic grows into its own feature if it tries to be clever. URL scheme in the app settings, HTTPS badge, done.
4. **`?token=` in the WebSocket URL:** acceptable for v1 with the F-A fix in place, for these reasons: the query string lands in uvicorn's access log (local to the server) but WS handshakes carry `Origin`, not `Referer`, so the classic Referer leak does not exist; and the alternative for a WS client genuinely is "the URL" — browsers can't set headers on a handshake, and the phone's WKWebView is in the same boat. The real cost is that the token is long-lived; the remedy already sketched in `auth.py:398` — a short-lived stream ticket minted over an authenticated HTTP call, then used in the WS URL — is the right v2. Ship v1 with eyes open; note the ticket as planned follow-up.
5. **mTLS:** defer. With HTTPS-only-remote + LAN consent, mTLS defends against a threat (a compromised LAN peer) that v1 doesn't otherwise defend against anything for. Not a prerequisite. Revisit when there are multi-tenant networks in the picture.

**Simpler path:** consent-gated HTTP + "prefer HTTPS" + the existing Tauri TLS story via Tailscale. No new crypto infrastructure in v1.

**Blocker:** yes for the companion app (the HTTP gate is a launch requirement); mTLS is not.

---

## Q4 — replica sync endpoint

**Verdict: with changes; blocked on F-A and F-D.**

1. **Sender role check:** yes, add it — but it's unanswerable until F-D defines the satellite's record of the canonical. Concretely: the satellite records the canonical as `role="canonical"` (reverse-pairing reusing the existing handshake), and the endpoint accepts pushes only from that role. Note the plan's `push_snapshot_to_peers` filters *its own* peer list by `role == "body"`, which is the sender side; the receiver-side check is the one that matters and the one missing. Also add the state guard: **a promoted node refuses all sync-replica pushes** (see Q12 — this is the fence).
2. **Content trust:** the satellite trusting the canonical's data is the design — they are one entity, and a malicious canonical is outside any threat model the satellite can defend against (it already holds the entity's identity). The validation the plan has (SHA-256 vs manifest, `PRAGMA quick_check`, JSON parse) is the right scope: it defends against *corruption and transport damage*, not malice. One addition: the replica directory should be `0700` — it holds the entity's full memory and conversations, same sensitivity class as the live data dir.
3. **Path traversal:** real. The multipart filenames become file writes under `canonical_replica/`, and nothing in the plan validates them. Simplest fix, by construction: **ignore client-supplied filenames entirely** — accept only the two known payload names (`memories.json`, `conversations.db`) from the manifest, reject anything else. An allowlist of two beats a sanitiser.
4. **Sandboxing the replica until promotion:** the read-fallback feature (Step 1.6) reads it while the canonical is down, so "never loaded until promotion" isn't the shipped reality anyway. Read-only SQLite connections + JSON parse + `quick_check` is adequate; skip the sandbox, keep the mode bits.

**Simpler path:** filename allowlist instead of sanitisation; role allowlist instead of denylist; promoted-refuses-pushes instead of a sandbox.

**Blocker:** yes — F-D must be designed before Step 1.3 can be implemented at all; F-A must land before it can be tested in production shape.

---

## Q5 — promotion endpoint

**Verdict: safe; two small additions.**

1. **Local-admin only is the right call for v1.** Promotion is the one act that creates a *second canonical*; making it performable from a pocket device multiplies the split-brain surface for no v1 user gain (the user is standing at the promoted machine in the scenario that matters — the canonical is dead and the phone may be unreachable too). The companion-handoff already excludes `/api/replica/promote`; when replication ships, keep the exclusion and revisit with the phone-only disaster scenario in mind. Note the endpoint as planned also sits behind `require_owner` (F-A) — for the *local* operator that's fine, the dashboard token is local.
2. **`being.yml` backup:** yes — before clearing `canonical_memory_url`/`canonical_thread_url` (`being_config.py:267,271`), copy `being.yml` to a timestamped sidecar in the config dir. Matches the standing rule (leave superseded data on disk, never delete), costs three lines, and makes "un-promote by hand" possible after a mistaken promotion.
3. **Local-state check before overwrite:** the demoted-then-repromoted scenario is real once promotion exists. Simplest honest rule: if the local `memories.json` is non-empty *and differs* from the replica's, move the local pair to a `demoted-state-<timestamp>/` directory before overwriting, and say so in the result/report. No merge logic, no prompts — the data is preserved, the operator can look at it, "leave superseded data on disk" is honoured.
4. **Split-brain fencing:** see Q12.

**Simpler path:** snapshot + quarantine-move, no merge, no prompts.

**Blocker:** no.

---

## Q6 — backup encryption

**Verdict: safe; the plan contradicts itself in one place; one cheap addition.**

1. **600k PBKDF2-HMAC-SHA256:** fine. OWASP's current guidance is 600k for PBKDF2-HMAC-SHA256; the real bound on this archive is the *entropy of the user-chosen passphrase*, not the KDF, and no iteration count fixes a 4-word passphrase. Don't raise it — PBKDF2 cost is linear for the attacker *and* the defender, and restore happens on whatever hardware the fire left the user with. (The genuinely stronger move is Argon2id, but that's a new dependency and the resolved-questions doc already chose against it — right call under the subtractive contract.)
2. **Plaintext salt in the manifest:** correct and standard. A salt needs uniqueness, not secrecy; hiding it buys nothing (it's derivable from any ciphertext anyway, since PBKDF2 output is deterministic and testable).
3. **Random 96-bit nonce per file:** safe at this scale. The birthday bound (~2³² encryptions under one key) is irrelevant when the key is fresh per archive (fresh salt) and an archive holds ~10 files. Deterministic counter nonces would add bookkeeping to defend against a non-threat.
4. **Per-file keys:** **unnecessary — and note the plan disagrees with itself.** Step 2.2's `encrypt_file` encrypts with the master key directly; Step 2.3's `create_backup` docstring says "encrypt each file with per-file keys wrapped by master key." Reconcile to the simple one (master key, random nonce per file). Key-wrapping buys per-file revocation granularity nobody uses, in an archive with ten members.
5. **Refuse-to-run without `cryptography`:** correct, and not only acceptable — it's the only defensible behaviour. The archive contains `body.key`, the entity's Ed25519 identity; a "plaintext with a warning" fallback creates unencrypted identity-key archives that a user will absolutely leave lying around because the backup *did* complete. A hard refusal with a one-line fix instruction is the fail-closed pattern (SEC-1) this codebase already commits to. Confirm the plan's choice.
6. **Passphrase custody on the phone:** acceptable *if* the passphrase never crosses a plaintext network (Q3), and with one refinement — see Q7. The restore flows that matter are local anyway (OOBE on fresh hardware types or QR-scans the passphrase from the phone's screen; the archive and the passphrase holder are in the same room). The phone-as-remote-restore-approver variant (passphrase POSTed to `/api/backup/restore` over the wire) is the one path that puts the DR secret on the network — **restrict restore initiation to the machine itself** (which `require_local_admin`-only already does, even post-Q1), and the passphrase never transits HTTP at all. The phone displays; it does not transmit.

**One addition:** bind each ciphertext to its filename with AES-GCM associated data (`AESGCM.encrypt(nonce, plaintext, name.encode())`). It's free, and it makes intra-archive file swaps (rename `conversations.db.enc` to `memories.json.enc`) fail at decrypt instead of at parse. The manifest SHA-256s already catch this *if* restore verifies digests — make digest verification part of the restore engine, not just the vault writer.

**Blocker:** no. (The self-contradiction is a doc fix before Step 2.3 merges.)

---

## Q7 — recovery key custody in the Keychain

**Verdict: safe with one attribute change.**

1. **Use `WhenPasscodeSetThisDeviceOnly`, not `WhenUnlockedThisDeviceOnly`.** The stricter class is strictly better here: the item becomes inaccessible when the device passcode is removed, which closes the "forensic tool strips the passcode" half of the theft story at zero usability cost (Face ID still unlocks the device; the class governs data protection, not biometrics). For a *recovery* secret that the user should need once a year, "requires a passcode to exist" is the right trade.
2. **iTunes encrypted backups:** not a risk with `ThisDeviceOnly` items — Apple excludes `*ThisDeviceOnly` keychain items from *all* device backups, encrypted ones included. The item leaves the Secure Enclave's reach only via screen display. (The moment anyone proposes `WhenUnlocked` *without* `ThisDeviceOnly`, this answer flips — that variant syncs into encrypted computer backups.)
3. **Three nudges:** sufficient for v1 *if* the onboarding nudge produces something that survives the phone: "write this down / print the QR" must be a completion-blocker in the OOBE, not a dismissible toast. The periodic and pre-update nudges are the right cadence. One explicit addition to the copy: the paper copy is the floor — the phone is a convenience, not the recovery path (the resolved-questions doc's Q6 reasoning, applied to the app copy).
4. **QR display of the passphrase:** acceptable. It is a local display consumed by a machine in the same room — the same exposure as showing the passphrase as text, which the flow needs anyway for headless restores. Shoulder-surfing is real but bounded by a deliberate user action; the alternative (never display) breaks the one recovery UX the phone exists to provide. No screen-capture protection games; iOS screenshots of the app are the user's own device.

**Simpler path:** same flow, one attribute stronger.

**Blocker:** no.

---

## Q8 — QR code pairing

**Verdict: safe if the PIN stays out of the QR — which the plan's two documents currently disagree about.**

**The contradiction, stated flatly:** `companion-frontend-handoff.md` §7.3 says "the QR only carries the URL… the extra step [PIN] is the security boundary." `implementation-plan.md` Step 1.9 has `PairingQRCode.tsx` encode `{url, request_id, pin, entity}`. The security-review-request asserts "It does NOT encode a pairing token or PIN." These cannot all ship. The implementation plan is the one that would get built as written — so this is live, not hypothetical.

1. **Is URL-only worth it?** Yes. Typing `http://mac-mini.local:8000` into a phone is the real friction; the URL is public-by-design data (the Host allowlist requires it anyway, §3.6 of the handoff). The PIN is the out-of-band secret — that's the *entire* property that survived SE-16: the PIN travels "through the person doing the pairing" (`peers.py:143`), not through a photographable surface.
2. **PIN brute force — the numbers are verified:** `PAIRING_MAX_ATTEMPTS = 3`, `PAIRING_TTL_S = 60`, `PAIRING_MAX_PENDING = 16` (`peers.py:90-94`; the request's "line 371" is stale). Three tries against 10⁴ in a 60s window, request keyed by `request_id` not PIN so verify is not a PIN oracle — sufficient. The approval gate (`pending.approved`) is the load-bearing line and it holds.
3. **QR photographed off the host's screen:** harmless while it carries only the URL (+ optionally `request_id`, which is a random UUID and useless without the PIN or an approval).
4. **Pre-approving one-time token in the QR: no.** The handoff's recommendation is right, and worth ratifying with the reasoning: a token in the QR converts "physical presence" into "line of sight," and a room camera defeats line of sight at a distance. The PIN's job is to prove the *person*, not the camera.

**Fix:** drop `pin` from the QR payload in Step 1.9 (`url`, `request_id`, `entity` are fine — `request_id` saves a round trip and is not a secret); show PIN as text below the QR as the plan already does for the headless fallback. The QR's *value* is skipping the URL typing; the PIN typing is the security boundary and should stay deliberate.

**Blocker:** no — but fix before Step 1.9 merges, because it's a doc contradiction now and a shipped regression later. (And note: the whole feature 401s until F-A lands, same root cause.)

---

## Q9 — voice audio streaming

**Verdict: does not work as planned — required change, not a judgement call.**

1. **The token-in-URL question is moot until the WS door accepts peer tokens at all.** Verified: `websocket_authenticated` (`auth.py:456-475`) checks the credential against `AuthState.token` — the *dashboard token* — via `state.check`. A peer token in `?token=` is refused (1008); empirically confirmed. The companion-handoff's "the iOS app uses this with its Keychain-stored bearer token" only works if that stored token is the dashboard token — F-B again. **Required change:** extend `websocket_authenticated` to verify against `PeersConfig` as well (peer path mirrors the `optional_peer_auth` extraction), so a `trust_anchor` peer can open `/api/audio/stream` and `/api/audio/tts` with its own revocable token. This is a prerequisite for the voice MVP, not an enhancement.
2. **Does the stream lose the peer context?** Yes — verified. The handler hands the socket to `coordinator.get_ingress("dashboard")` with no `PeerContext`; nothing downstream knows which device is talking. After the Q9.1 fix, label the ingress source with the peer's `node_id` (`source="companion:<node_id>"` alongside the existing `'dashboard'` value at `audio/buffer.py:46`) so telemetry and the speaker-id path can distinguish a room mic from a paired phone. The plumbing exists (source is already a labelled field); it's a tagging change, not a redesign.
3. **CAM++ replay:** real, and the right framing is that it is a *sub-case of phone compromise*, not a new vulnerability class. A stolen-unlocked or compromised phone can replay the admin's voice — but the same attacker holds the trust_anchor token and can simply *approve things*; voice replay is not the cheaper path to anything the token doesn't already grant. The CAM++ gate's threat model is the anonymous room mic, where it earns its keep. v1 mitigation is Q11's revocation story, plus the RoleGate confirmation requirement for HIGH-risk actions by unverified speakers, which already exists. **Defer** lowering the companion's speaker-role cap to `member`; revisit if phone theft becomes an observed pattern rather than a modelled one.
4. **TTS `session_id`:** not a secret — and doesn't need to be. The WS handshake requires the token (post-Q9.1); a caller *with* the token doesn't need to guess session ids to cause harm, and a caller *without* it can't subscribe at all. The real question is cross-session snooping among authenticated clients — see F-F for the guest-persona caveat. v1: acceptable within the owner boundary.

**Simpler path:** extend the existing `state.check` with one peer-store lookup rather than inventing a WS-specific credential scheme.

**Blocker:** yes — Q9.1 is required for the companion voice MVP.

---

## Q10 — Face ID gate for staged command approvals

**Verdict: acceptable for v1; one server-side hygiene fix.**

1. **The server not knowing Face ID happened is fine.** The credential is the token; Face ID is a *local UX gate* that makes the token harder to use without the owner's face. It is honest to describe it that way in the plan rather than as a security control. The moment the approval POST arrives, the server's security property is exactly "a live trust_anchor token was presented" — which is the property the token system was built to provide (revocation, per-peer, hashed at rest).
2. **Secure Enclave signed assertions:** defer, and be explicit about *why*: the assertion would prove "Face ID ran," but the attack it models — malware on the phone that skips the UI and POSTs directly — *already holds the token*, and a signed assertion minted by the same compromised device is forgeable in the relevant sense (the malware *is* the device). WebAuthn-class hardware attestation would defend against a *narrower* class (extracted token, uncompromised OS) at the cost of a native plugin, a registration ceremony, and a verification path. Not worth v1. Revisit only if approvals ever become the sole control on a physically-destructive action.
3. **Server-side safeguard for destructive approvals:** the staged-command system *is* the safeguard — the command is staged, diffed, and shown on the phone before the human taps. For v1, ship as-is. The cheap follow-up worth noting for later: gate `risk_level == 'critical'` approvals to local admin only, leaving the phone able to approve `high` and below (the `risk_level` field already exists on `ApprovalRequest`).
4. **`approval_id` guessability:** the IDs are server-generated UUIDs in the paths that create them (`approvals.py:136`) — not sequential. But the engine accepts *any* caller-supplied id, and `request_id` is concatenated into a filesystem path — that's F-C, an arbitrary-read/write primitive behind the auth door. Fix with UUID-shape validation; it also cleanly answers "can a phone approve arbitrary pending approvals": it can only approve ids that exist *and are well-formed*, and a well-formed id it didn't learn from the server's own list is a 404.

**Simpler path:** token-as-credential + ID sanitisation. No biometric cryptography in v1.

**Blocker:** F-C's sanitisation must land with the F-A branch (it becomes peer-reachable the day Q1 does).

---

## Q11 — lost device and revocation

**Verdict: sound; document the one corner; defer expiry.**

1. **Canonical-down-and-phone-lost:** the user is locked out of *remote* control until the canonical returns — correct behaviour, not a gap. Everything revocation protects against (the phone acting with the owner's authority) can *only be exercised against the canonical*; if the canonical is unreachable, the phone's token is inert for the moment, and when the canonical comes back the first act at the keyboard should be `DELETE /api/peers/{phone}`. State this in the app copy and the docs as the recovery runbook, because it's the question a panicking user will have.
2. **Passphrase on a stolen, passcode-bypassed phone:** bounded correctly by the plan — the passphrase alone decrypts nothing without the `.halbert-backup` file, which is on storage the thief doesn't have. With `WhenPasscodeSetThisDeviceOnly` (Q7) the forensic-bypass case is the one it closes. Residual risk: thief has *both* the phone and the backup file — then the passphrase is crackable at PBKDF2 speed and the archive falls; that's the passphrase-entropy bound from Q6, and the honest answer is the onboarding copy ("write it down" means the passphrase is *strong* too).
3. **Token expiry:** defer. A 30-day re-pair cadence adds a standing user chore to defend against a scenario (weeks-undetected theft with the attacker quietly using approval powers) that revocation already answers better, because the user *notices* a lost phone in minutes, not days. The unresolved case — a *cloned* token used quietly — is not stopped by expiry either unless the cadence is punishing. No users yet; no observed threat; don't build it.
4. **All devices lost:** the file + passphrase floor is already the designed answer (resolved-questions Q6), and the three nudges (Q7.3) are the mitigation for "the user never made one." One addition to the plan's restore docs: the OOBE restore path should say plainly that peers must be re-paired after restore (the archive's `peers.json` restores the *other side's* view; tokens are node-local secrets that no longer exist anywhere).

**Blocker:** no.

---

## Q12 — split-brain and fencing

**Verdict: acceptable for v1 with one cheap fence; defer the epoch.**

1. **"Manual re-pairing is the fence" is not sufficient as stated** — the request's own parenthetical spotted why. After promotion, the old canonical still holds whatever credential the *satellite* issued it (post-F-D) and will keep pushing to the new canonical's sync endpoint. Without a check, those pushes overwrite the promoted node's live state with stale data — silent corruption, the worst failure mode available. The Q4 recommendation is the fence: **a node that has been promoted refuses all `/api/peers/sync-replica` pushes** (it can test this directly: `canonical_memory_url` cleared ⇒ I am canonical ⇒ reject with 409). One conditional, no protocol. The old canonical's pushes fail loudly, its operator sees a wall of 409s, and the re-pairing the plan already prescribes becomes *forced* rather than remembered.
2. **Epoch/generation token:** defer with a defined trigger. The receiver-refuses fence handles the two-node case completely; a generation counter in `being.yml` only starts earning its keep with three-plus nodes where a stale *satellite* could relay stale data, or when automatic failover (which the resolved-questions doc already sketched as an opt-in) makes "which node is canonical" ambiguous to the nodes themselves. Write the trigger into the plan now ("add generation when auto-failover or 3+ node meshes land") so it isn't re-litigated.
3. **In-flight writes on the old canonical:** lost, and acceptable — but only if the promotion dialog says so. The current copy ("The home server will need to re-pair when it comes back") describes the mechanics; add the consequence: "If it turns out the old host was alive, anything written there after this replica was taken will not exist here." Honesty in the one dialog that performs the act.
4. **Warm replica sufficiency:** yes for the topology it serves. Manual promotion + read-fallback + refuse-after-promote is a coherent, explainable protocol; the lease/election machinery it omits is exactly what the resolved-questions doc rejected for v1 (Q1), and nothing in this review found a hole that machinery would close *at this scale*.

**Simpler path:** the fence is one `if` on an existing config field. That's the whole v1 fencing story.

**Blocker:** the fence itself is required at Step 1.7 (promotion) — without it, promotion creates the silent-corruption window rather than closing an outage.

---

## Concerns the request did not list

These are in addition to F-A…F-F above; restated briefly so the complete finding list lives in one document:

- **F-A** — peers/approvals/conversations routers sit behind `require_owner`, which rejects peer tokens; pairing, trust_anchor approvals, sync-replica, entity-status and the WS door as planned all 401 against production mounts. The per-route auth design in `peers.py` has effectively never run in production.
- **F-B** — the companion app's only working credential against today's mounts is the full owner token.
- **F-C** — approval `request_id` reaches filesystem path concatenation unvalidated (arbitrary read/write behind the auth door; peer-reachable once Q1 lands).
- **F-D** — the plan never defines the satellite's peer record for the canonical or the credential the canonical pushes with; Step 1.3 cannot work as specified.
- **F-E** — any authenticated peer can rewrite any other peer's WoL settings (`PUT /api/peers/{node_id}/wol`).
- **F-F** — TTS subscription is by bare `session_id`; fine within the owner boundary, but guest personas make it a cross-persona listening question.
- **Test-shape gap (root of F-A):** the auth census (`test_route_auth_census.py`) validates that every route is *guarded*, and accepts `require_peer_auth` as a guard — but the suites that exercise the peer surface mount routers bare, so "the guards work when production-mounted" is untested. Add one test that drives the pairing flow against the real `create_app()` mounts with a remote client address; it would have caught F-A.
- **Doc drift in the request itself:** `PAIRING_MAX_ATTEMPTS` is at `peers.py:92`, not 371; `DELETE /api/peers/{node_id}` is local-or-self, not `require_local_admin`-only; Step 2.2 vs Step 2.3 disagree on per-file keys (Q6.4); Step 1.9 vs companion-handoff §7.3 disagree on the QR payload (Q8); the ios-companion-handoff's `require_trust_anchor` catch-all was already corrected — confirmed correct as amended (Q1.3).
- **`being.yml peer_token` ambiguity:** the docs treat it as a peer token; the production door only honours it if it is the dashboard token (F-A). When F-A lands, decide and document which token belongs in that field, and consider naming it for what it is.

---

## What must change in the plan, in merge order

1. **New Step 1.0 (before everything):** re-mount peers + approvals routers with explicit per-route guards (`"peers"` and `"approvals"` in `SELF_AUTHENTICATING` + the per-route audit table from F-A); UUID-shape validation on approval IDs (F-C); local-or-self on the WoL route (F-E); a production-mount pairing test (remote client, real `create_app()`). Merge gate: the new census-style test green, and the empirical probe below returns 200/200/200 for anon-pair, peer-token-list, peer-token-WS.
2. **Step 1.3 (sync-replica):** add F-D (reverse-pairing so the satellite holds a `role="canonical"` record and issued-token for the pusher); receiver-side role allowlist `{"canonical"}`; filename allowlist (`memories.json`, `conversations.db` only); replica dir `0700`.
3. **Step 1.7 (promotion):** `being.yml` timestamped sidecar before clearing canonical URLs; quarantine-move of differing local state; **promoted-refuses-pushes fence**; dialog copy states the write-loss consequence.
4. **Step 1.9 (QR):** drop `pin` from the QR payload; reconcile §7.3 and Step 1.9 text.
5. **Step 2.2/2.3 (encryption):** reconcile to master-key-direct; filename AAD; digest verification in restore, not just creation.
6. **Companion app Phase 1:** extend `websocket_authenticated` to accept peer tokens (voice MVP prerequisite); HTTP-consent gate + HTTPS-off-LAN; `WhenPasscodeSetThisDeviceOnly`; trust_anchor pairings approved only at the machine; restore stays local-initiated (passphrase never transits the network).
7. **`peers_config.py`:** role enum validation at `add_peer` (warn-or-reject unknown roles, matching the capabilities precedent).

Deferred, with triggers: epoch/generation fencing (auto-failover or 3+ node meshes), token expiry (observed undetected-compromise pattern), Secure Enclave signed assertions (approvals as sole control on physically-destructive actions), stream tickets for WS URLs (if token-in-log becomes unacceptable), Argon2id (never, absent a contract change), critical-tier approvals local-admin-only (after the phone ships, if the approval surface gets used in practice).

---

## Appendix — the empirical probe

Run with `arch -arm64 .venv/bin/python <script>` from the repo root. These are the load-bearing assertions, condensed; the full session transcript verified each interactively.

```python
import os, tempfile
from pathlib import Path

tmp = tempfile.mkdtemp(prefix="halbert-auth-probe-")
os.environ.update(XDG_STATE_HOME=tmp,
                  HALBERT_CONFIG_DIR=os.path.join(tmp, "config"),
                  HALBERT_DATA_DIR=os.path.join(tmp, "data"))
os.environ.pop("HALBERT_API_TOKEN", None)

from fastapi.testclient import TestClient
from halbert_core.dashboard.app import create_app
from halbert_core.dashboard import auth as dashboard_auth
from halbert_core.federation.peers_config import PeersConfig
import halbert_core.federation.peer_middleware as pm

app = create_app()
tok = dashboard_auth.load_or_create_token()

# 1. A credential-less remote satellite cannot start pairing (expect 401).
sat_anon = TestClient(app, client=("203.0.113.7", 4444))
assert sat_anon.post("/api/peers/pair", json={
    "node_id": "probe-sat", "node_name": "P", "role": "body",
}).status_code == 401

# 2. A genuine peer token does not satisfy require_owner (expect 401s),
#    and only the compute-peer router honours it (auth passes -> 503).
config = PeersConfig(config_path=Path(tmp) / "config" / "peers.json")
config.add_peer(node_id="probe-sat", node_name="P", role="body",
                raw_token="hbt_probetoken123")
pm._peers_config = config  # the singleton require_peer_auth reads
sat = TestClient(app, client=("203.0.113.7", 4444),
                 headers={"Authorization": "Bearer hbt_probetoken123"})
assert sat.get("/api/conversations/health").status_code == 401
assert sat.get("/api/peers/list").status_code == 401
assert sat.post("/api/compute/v1/chat/completions",
                json={"model": "x", "messages": []}).status_code in (200, 503)

# 3. The WebSocket door accepts the dashboard token but not a peer token.
with sat.websocket_connect(f"/api/audio/stream?token={tok}") as ws:
    pass  # connects
try:
    with sat.websocket_connect("/api/audio/stream?token=hbt_probetoken123") as ws:
        raise AssertionError("peer token was accepted on the WS handshake")
except Exception:
    pass  # rejected (1008)

# 4. The local operator (loopback address + dashboard token) can pair.
owner = TestClient(app, client=("127.0.0.1", 4444),
                   headers={"Authorization": f"Bearer {tok}"})
rid = owner.post("/api/peers/pair", json={
    "node_id": "probe-sat", "node_name": "P", "role": "body",
}).json()["request_id"]
assert owner.post(f"/api/peers/pending/{rid}/approve").status_code == 200
```

The pairing *handshake itself* is sound — approve-then-verify, PIN not returned to the requester, three-attempt/60-second window, per-request UUID keys; `tests/test_peer_pairing_security.py` proves all of it. What production breaks is not the handshake but the **front door it stands behind**. Fix the mounts, and the request's original mental model becomes true; until then, every plan document built on it is describing a system that does not run.

---

## Remediation addendum — 2026-09-13 (later the same day)

**Status: Step 1.0 has landed on main, plus more of the response than Step 1.0 called for.** The probe above now passes end to end. What landed, verified by re-running the probe against `create_app()`:

| Finding | State | Where |
|---|---|---|
| F-A — peers/conversations behind the owner-only door | **Fixed** | `SELF_AUTHENTICATING` gains `"peers"`/`"conversations"`; every peers route states its guard; `pair`/`verify` are the two census-listed open routes (PIN + local-admin approval are the boundary, SE-16) |
| F-A trap — approvals relying on mount-level guard only | **Fixed** | every approvals route carries explicit `require_owner` (reads) / `require_trust_anchor` (decisions) |
| F-B — the phone's only working credential would be the owner token | **Closed by F-A** | the phone pairs with `role: trust_anchor` and uses its own revocable peer token |
| F-C — approval ids reach path concatenation unvalidated | **Fixed** | `validate_approval_id` at the engine's storage boundary; routes answer hostile ids 400; `InvalidApprovalId` |
| F-E — any peer can retarget any peer's WoL | **Fixed** | `require_local_or_self_peer` on WoL and revocation (the R10-F5 predicate, lifted into a dependency) |
| Q9.1 — WS door rejects peer tokens | **Fixed, then scoped** | peer tokens admit on the two audio sockets only; `/ws` and the PTY bridge stay owner-only; `allow_peer` defaults to False (a new WS handler is owner-only by omission) |
| Q9.2 — audio stream loses peer context | **Fixed** | peer-authenticated sockets stamp their source; the ingress labels a paired device vs a room mic |
| Q1/Q2 — `require_trust_anchor` itself | **Landed, ahead of this review's schedule** | owner/local/trust_anchor doors on pairing approval + staged-command decisions, with the Q1.1 carve-out (a trust_anchor cannot approve a trust_anchor pairing) and PIN redaction for phone callers on the pending list |
| Role vocabulary | **Fixed** | `KNOWN_PEER_ROLES` with the same warn-not-reject forward-compat rule as capabilities (response item 7) |
| Census blind spot | **Fixed** | include-time tags now propagate to leaf routes (they never had — the tag skip was dead code); guards are checked *before* the tag exemption |
| Production-mount test | **Added** | `tests/test_production_mount_auth.py` drives the real `create_app()` with real client addresses: anon pair 200, peer token on peers/list + conversations/health 200, peer token still 401 on owner routes, per-peer controls per-peer, WS scope |

**The probe, re-run after remediation (all previously-failing rows):**

```
1. ANON  POST /api/peers/pair          -> 200   (was 401)
2. PEER  GET  /api/conversations/health -> 200  (was 401)
3. PEER  GET  /api/peers/list          -> 200   (was 401)
4. PEER  POST /api/compute/v1/chat     -> 503   (auth passed; no model — unchanged)
5. PEER  GET  /api/approvals          -> 403   (trust_anchor door: a body peer is not an anchor — correct)
   PEER  GET  /api/settings/policy   -> 401   (owner surface, unchanged)
6. PEER  WS   /api/audio/stream        -> admitted (was 1008)
   PEER  WS   /api/audio/tts          -> admitted
   PEER  WS   /ws                     -> refused  (owner-only, scoped post-remediation)
   PEER  WS   /ws/terminal/*          -> refused  (the PTY bridge — caught by the re-run)
8. REMOTE approve pairing             -> 403   (local-or-anchor only)
9. LOCAL  approve pairing            -> 200
```

**Two corrections the remediation made to this document's own claims**, recorded here rather than edited above: the review asserted `DELETE /api/peers/{node_id}` was `require_local_admin`-only — the code already allowed self-revocation (the doc-drift item said this too; both were right in different paragraphs); and row 5's 403 is `require_trust_anchor` answering, which this review proposed but did not expect to see on main yet.

**Commits:** F-A/F-E as `83f1b74c` (auth.py, peers.py, peer_middleware.py, census, production-mount test); F-C as `c0cec3db` + test coverage as `9253a122`; the trust_anchor layer and WS peer admission landed with the multi-node merge `8fe1eb4a` and its branch; the WS scope fix (peer admission was unscoped in the first landing) as `1854f7e6`.

**Still open from the "What must change" list (not blockers, tracked for their steps):**

- **F-D** — reverse-pairing so the satellite holds a `role="canonical"` record and the credential the canonical pushes with (blocks Step 1.3; the `KNOWN_PEER_ROLES` vocabulary already reserves the role).
- **Q12 fence** — promoted-refuses-pushes at Step 1.7 (one conditional on the cleared `canonical_memory_url`).
- **Step 2.2/2.3** — filename AAD + digest verification in restore (the per-file-key contradiction is now reconciled in the plan doc).
- **Step 1.9** — the QR payload in the plan doc now matches §7.3 (no PIN); the component doesn't exist yet.
- **Q3's HTTP consent gate** — companion-app concern; no backend code needed.
- **`being.yml peer_token` ambiguity** — decide and document which token belongs in that field now that peer tokens actually work through the door.