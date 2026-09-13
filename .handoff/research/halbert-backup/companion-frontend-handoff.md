# Companion Frontend: One Tauri Build for Tablet, Kiosk, and Mobile

**Date**: 2026-09-12
**Status**: Active plan — replaces [`ios-companion-handoff.md`](ios-companion-handoff.md) (SwiftUI)
**Parent**: [`open-questions-resolved.md`](open-questions-resolved.md) (Q7, Q8), [`design-exploration.md`](design-exploration.md) (variation E), [`DECISIONS.md`](../../../DECISIONS.md)
**Supersedes**: [`ios-companion-handoff.md`](ios-companion-handoff.md) (frontend sections 7-10; backend sections 5-6 carried forward)

---

## 1. Decision

The companion app is not a new product. It is the existing Tauri v2 dashboard
build targeted at iOS, reusing the Voice Mode frontend as the one source of
truth for tablet, kiosk, and phone form factors. Features are gated by
hardware capability and form factor, not by forking the codebase.

The previous plan (`ios-companion-handoff.md`) proposed a standalone native
SwiftUI app. That approach would rebuild the audio-reactive HalbertMark, the
voice mode state machine, the PCM uplink, the TTS downlink, the standby
controller, the on-screen keyboard, the subtitle ribbon, the speaker badge,
and the entire design token system — all of which already exist, are tested,
and run in a webview. Rebuilding them in SwiftUI doubles the maintenance
surface for zero user-facing gain.

**One frontend, three form factors:**

| Form factor | Runtime | How it launches | Sidecar |
|---|---|---|---|
| Desktop (macOS/Linux/Windows) | Tauri + WKWebView/WebView2/WebKitGTK | `make dev` / `make build` | Spawns `halbert-api` sidecar |
| Kiosk (N150 appliance) | Chromium kiosk → `/voice` | `halbert-kiosk.service` | Backend runs as systemd unit |
| Tablet / Phone (iOS) | Tauri v2 + WKWebView | Xcode build / TestFlight | Connects to remote host URL |

The kiosk path already exists and runs today. The iOS path is the same React
code in a Tauri v2 mobile build instead of a Chromium tab.

---

## 2. What Already Exists

### Voice Mode (`/voice` route)

The full-screen, touch-first, audio-reactive voice surface is built and
deployed. Spec: `documentation/design/15-voice-mode-visual-ui-and-touchscreen-spec.md`.

- **`VoiceMode.tsx`** — 7-state posture machine, audio-reactive HalbertMark,
  PCM uplink, TTS downlink, barge-in, speaker badge, subtitle ribbon.
- **`TouchBar.tsx`** — 48px touch targets (above the 44px floor of spec §8).
- **`StandbyController.tsx`** — multi-tier dim/blackout for idle kiosk
  displays, POSTs to `/api/system/display` for hardware DPMS.
- **`OnScreenKeyboard.tsx`** — glide keyboard for touch input.
- **`SubtitleRibbon.tsx`** — live transcript display.
- **`SpeakerBadge.tsx`** — CAM++ speaker identification display.
- **`PcmUplink` (`lib/pcmCapture.ts`)** — `getUserMedia` → AudioWorklet →
  WebSocket to `/api/audio/stream` (16kHz s16le mono).
- **`TtsPlaybackClient` (`lib/ttsPlayback.ts`)** — WebSocket subscriber to
  `/api/audio/tts`, plays Piper PCM, handles `{"type":"cancel"}` barge-in.

### Kiosk Deployment

`scripts/halbert-kiosk.service` launches Chromium in `--kiosk` mode pointing
at `http://localhost:<port>/voice` on an Intel N150 with a 10" capacitive
touch display. The same React code that runs in the kiosk runs in the Tauri
desktop app. Documentation: `documentation/operations/kiosk-appliance.md`.

### Tauri v2 Mobile Scaffolding

The Rust entry point already has the mobile annotation:

```rust
#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() { ... }
```
(`halbert_core/halbert_core/dashboard/frontend/src-tauri/src/lib.rs:513`)

The crate type includes `cdylib` (required for mobile targets), and
`@tauri-apps/cli ^2.9.4` is already in devDependencies. Tauri v2 has
first-class iOS support — the app runs in WKWebView (Safari's engine), which
has full Web Audio, `getUserMedia`, and AudioWorklet support.

### ShellMode Context

`ShellModeContext.tsx` manages layout modes: `'engaged' | 'browsing' |
'both' | 'voice'`. A companion/mobile mode is the same pattern — a different
layout driven by the same state machine, selected by form factor detection
rather than keyboard shortcuts.

### Auth for Non-Browser Clients

`websocket_authenticated` in `dashboard/auth.py` accepts a `?token=` query
parameter for WebSocket connections from non-browser clients. The iOS app
uses this with its Keychain-stored bearer token. `origin_allowed` returns
`True` when no Origin header is present (the iOS app does not send one).

---

## 3. What Needs Building

### 3.1 Frontend: Form Factor Context

Add a `FormFactorContext` (or extend `ShellModeContext`) that detects the
runtime environment and drives layout:

```typescript
type FormFactor = 'desktop' | 'kiosk' | 'tablet' | 'phone';

// Detection priority:
// 1. Tauri mobile target (iOS) → 'tablet' or 'phone' (by viewport width)
// 2. Kiosk query param or meta tag → 'kiosk'
// 3. Default → 'desktop'
```

The form factor controls:

- **Which ShellMode is available**: mobile/tablet default to a companion
  layout (voice + approvals + status), not the three-panel desktop shell.
- **Which features are surfaced**: camera/vision only on devices with a
  camera; Dynamic Island only on iPhone 14 Pro+; etc.
- **Touch target sizing**: already 48px in Voice Mode; desktop shell
  controls may need larger hit areas on tablet.
- **Panel layout**: desktop is three-panel (rail/centre/conversation);
  tablet is single-panel with swipe between voice/approvals/status;
  phone is single-panel, voice-first.

### 3.2 Frontend: Companion Layout

A new companion layout (not a new app) that composes existing components:

- **Voice surface**: the existing `VoiceMode` page, already touch-first.
- **Approvals list**: a mobile-optimized card list polling
  `/api/approvals`, with Face ID gating on approve (via the Tauri plugin).
- **Status card**: entity name, host reachability, last backup, peer list
  — polling `/api/entity/status` (new endpoint, see 3.4).
- **Settings**: host URL configuration, unpair, recovery key status.

Navigation is a bottom tab bar (voice / approvals / status / settings) on
phone, a side rail on tablet. The kiosk form factor skips navigation — it
stays on voice.

### 3.3 Rust: Sidecar Gating

The sidecar spawn (`spawn_backend` in `lib.rs:125`) must be gated behind
`#[cfg(not(mobile))]`. On mobile, the app connects to a user-provided host
URL instead of `127.0.0.1:<port>`.

```rust
.setup(|app| {
    #[cfg(not(mobile))]
    spawn_backend(app.handle())?;

    // Mobile: no sidecar. The frontend reads the host URL from
    // settings (persisted in Keychain-backed storage) and connects.
    Ok(())
})
```

The `api_base()` function needs a mobile path: read the host URL from app
settings instead of computing `127.0.0.1:<port>`. The `get_api_base`
Tauri command already exposes `api_base()` to the frontend; on mobile it
returns the user-configured URL.

`kill_backend` and the `Backend` managed state are `#[cfg(not(mobile))]`
only. The `RunEvent::Exit` handler that calls `kill_backend` is a no-op on
mobile (the `Backend` state is absent).

### 3.4 Rust: Native Plugins

Two Tauri plugins are needed for the MVP. Both are thin Swift bridges:

**`tauri-plugin-local-auth`** — Face ID / Touch ID:

```swift
// iOS: LAContext.evaluatePolicy(.deviceOwnerAuthenticationWithBiometrics)
// Returns: { success: bool, error: string? }
```

Expose as a Tauri command: `invoke('plugin:local-auth|evaluate', { reason:
'Approve staged command' })`. The frontend calls this before posting to
`/api/approvals/{id}/approve`. On biometric failure, the approval is not
sent. On desktop/kiosk, this plugin is absent and approvals go through the
existing web UI flow.

**`tauri-plugin-keychain`** — Secure Enclave token storage:

```swift
// iOS: SecItemAdd with kSecAttrAccessibleWhenUnlockedThisDeviceOnly
// Store/retrieve the bearer token from the pairing flow.
// No iCloud Keychain sync (kSecAttrSynchronizable = false).
```

Expose as: `invoke('plugin:keychain|set', { key, value })` and
`invoke('plugin:keychain|get', { key })`. The frontend uses this instead of
localStorage for the bearer token on mobile. On desktop, localStorage
remains (the threat model is different — the desktop token file is already
OS-protected).

### 3.5 Backend: Carried Forward from the Superseded Doc

These backend changes are the same regardless of frontend choice. They are
copied from `ios-companion-handoff.md` sections 5-6 with corrections from the
review.

**New peer role: `trust_anchor`**

Current roles in `peers_config.py:155`:
`"compute_provider" | "body" | "satellite" (legacy)`. Add `"trust_anchor"`.

A `trust_anchor` peer:
- Can approve peer pairing requests.
- Can approve staged commands.
- Can read aggregated status.
- Can stream voice audio.
- **Cannot** act as a compute provider.
- **Cannot** receive database replica pushes.

**New middleware: `require_trust_anchor`**

In `federation/peer_middleware.py`. Accepts either local admin
(`require_local_admin`) or an authenticated peer with
`role == "trust_anchor"`. Catch only 401/403 from `require_local_admin`,
not all HTTPException (a 421 Misdirected Request must propagate):

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

**Endpoints guarded by `require_trust_anchor`:**
- `POST /api/peers/pending/{request_id}/approve`
- `POST /api/approvals/{approval_id}/approve`
- `POST /api/backup/restore`

(`POST /api/replica/promote` is excluded — the replication subsystem does
not exist yet. Add it when replication ships.)

**New endpoint: `GET /api/entity/status`**

In `dashboard/routes/entity.py` (new file). Aggregates status in one call:

```python
@router.get("/api/entity/status")
async def entity_status(_auth: None = Depends(require_peer_auth)) -> Dict[str, Any]:
    return {
        "entity_name": resolve_entity_name(),
        "node_id": get_local_node_id(),
        "role": "canonical",
        "peers": list_peers_summary(),
        "last_backup": get_last_backup_timestamp(),
        "memory_count": get_memory_count(),
        "thread_count": get_thread_count(),
        "pending_approvals_count": get_pending_approvals_count(),
    }
```

Helper functions (`list_peers_summary`, `get_last_backup_timestamp`, etc.)
are new thin wrappers over existing stores. `resolve_entity_name` already
exists in `halbert_core/identity.py`.

### 3.6 Host Header Allowlist

When the iOS app connects via mDNS (e.g., `mac-mini.local:8000`), that
hostname must be in the `HALBERT_ALLOWED_HOSTS` allowlist. The
`websocket_authenticated` check in `dashboard/auth.py:466-468` rejects
unknown Host headers. This is a configuration requirement, not a code
change — document it in the pairing flow.

---

## 4. Pairing Flow

The phone pairs using the standard Halbert peer pairing flow, registering
as `role: "trust_anchor"`. The flow is the same one that already exists in
`dashboard/routes/peers.py`, with the PIN-never-returned fix from SE-16:

1. User opens the companion app. Enters the host URL (or scans a QR code
   that encodes it).
2. App sends `POST /api/peers/pair` with `role: "trust_anchor"`.
3. Desktop displays a 60-second PIN.
4. User enters the PIN on the phone.
5. App sends `POST /api/peers/verify` with the PIN.
6. Desktop returns a bearer token.
7. App stores the token in iOS Keychain (via `tauri-plugin-keychain`).

The QR code encodes the host URL for discovery — it is not an alternative
to `POST /api/peers/pair`. The pair request is a separate step that
initiates the handshake.

---

## 5. What Stays Native Swift (Extension Targets)

Phase 3 features that genuinely need native iOS code are built as **Xcode
extension targets** — separate build artifacts that ship alongside the
Tauri app. This is the standard iOS architecture: main app + widget
extension + share extension. The main app stays Tauri.

| Feature | Target type | Why native |
|---|---|---|
| Dynamic Island / Live Activities | Widget extension | Requires `ActivityKit` framework, not available in WKWebView |
| Lock Screen PTT widget | Widget extension | Requires `WidgetKit` |
| iOS Share Sheet ("Send to Halbert") | Share extension | Requires `NSExtensionPrincipalClass` |
| Focus Mode sync | App target (background) | Requires `EnvironmentValues` / `CNCopyCurrentNetworkInfo` |

These are additive — they don't replace the main app. They communicate with
the Halbert host via the same HTTP/WebSocket API the companion app uses.

---

## 6. MVP Scope (Phase 1)

Strictly: **Voice (existing) + Face ID Approvals + Status + Pairing**.

| Item | Status | Work |
|---|---|---|
| Voice Mode page | Exists | Form factor layout only |
| PCM uplink to `/api/audio/stream` | Exists | None |
| TTS downlink from `/api/audio/tts` | Exists | None |
| Barge-in | Exists | None |
| Standby dimming | Exists | None (mobile dims screen via iOS, not DPMS) |
| TouchBar / on-screen keyboard | Exists | None |
| `tauri ios init` | Not done | Generates Xcode project |
| Sidecar gating (`#[cfg(not(mobile))]`) | Not done | ~20 lines in `lib.rs` |
| `api_base()` mobile path | Not done | Read host URL from settings |
| Form factor context | Not done | New React context |
| Companion layout | Not done | New layout composing existing components |
| `tauri-plugin-local-auth` | Not done | Face ID bridge |
| `tauri-plugin-keychain` | Not done | Secure Enclave bridge |
| `trust_anchor` peer role | Not done | `peers_config.py` + `peer_middleware.py` |
| `require_trust_anchor` | Not done | `peer_middleware.py` |
| `/api/entity/status` | Not done | New route file |
| Pairing flow | Exists | Add `trust_anchor` to the role enum |

---

## 7. Open Decisions

### 7.1 iOS App Store License Exception (Blocking)

`LICENSE-EXCEPTION-APPSTORE` grants permission to convey "through the Apple
**Mac** App Store" only. The iOS App Store is a different store. An iOS
build needs either:
- A new exception text covering the iOS App Store, or
- An amendment to the existing exception.

This is a founder decision. FDR-02 ratified the Mac-only scope. Without a
new exception, the iOS app can only be distributed as source or via
TestFlight (which is not "conveyance" under GPL §7, but is not a
distribution path either).

### 7.2 Bundle Identifier

FDR-03 set `ai.halbert.home` (App Store), `ai.halbert.pro` (direct DMG),
`ai.halbert.dashboard` (dev/Linux). SEC-D10 superseded this to
`config/platforms.yml` as canonical. An iOS bundle ID needs to be added
there. Suggested: `ai.halbert.companion` (iOS), keeping `ai.halbert.home`
for the Mac App Store build.

### 7.3 QR Code Content

The pairing QR code encodes the host URL (e.g.,
`http://mac-mini.local:8000`). Should it also encode a one-time pairing
token to skip the PIN step? Current flow: QR gives URL → `POST /api/peers/pair`
→ desktop shows PIN → user enters PIN → `POST /api/peers/verify`. The
extra step is the security boundary (the user must be physically present
to read the PIN). Recommendation: keep it — the QR only carries the URL.

---

## 8. Phased Roadmap

### Phase 1: MVP — Voice + Approvals + Status (iOS)

1. `tauri ios init` — generate the Xcode project
2. Gate sidecar behind `#[cfg(not(mobile))]` in `lib.rs`
3. Add mobile `api_base()` path (host URL from settings)
4. Add `FormFactorContext` to the frontend
5. Build companion layout (bottom tabs: voice / approvals / status / settings)
6. Write `tauri-plugin-local-auth` (Face ID)
7. Write `tauri-plugin-keychain` (Secure Enclave)
8. Add `trust_anchor` role to `peers_config.py`
9. Add `require_trust_anchor` to `peer_middleware.py`
10. Add `/api/entity/status` endpoint
11. Add `trust_anchor` to the pairing flow role enum
12. Resolve the iOS App Store license exception (founder decision)

### Phase 2: Sensory Ingress & Recovery

- Camera capture via `getUserMedia` in WKWebView (works already) →
  `vision_model` slot
- Recovery passphrase custody in Keychain
- QR code display for bare-metal restore

### Phase 3: Ambient & Glanceable (Native Extensions)

- Dynamic Island / Live Activities (Widget extension, `ActivityKit`)
- Lock Screen PTT widget (Widget extension, `WidgetKit`)
- iOS Share Sheet (Share extension)
- Focus Mode attunement sync (background task in app target)

### Phase 4: Physical Presence

- BLE proximity auto-lock (CoreBluetooth in Tauri plugin or extension)
- NFC tag scanning (CoreNFC in Tauri plugin or extension)
- iPadOS layout scaling (form factor context: `tablet` vs `phone`)

---

## 9. What This Approach Avoids

| SwiftUI plan | Tauri plan |
|---|---|
| Rebuild audio-reactive HalbertMark in Swift | Use existing `@halbert/design-system` component |
| Rebuild voice state machine in Swift | Use existing `useVoiceModeMachine` hook |
| Rebuild PCM uplink in `AVAudioEngine` | Use existing `PcmUplink` (Web Audio + WebSocket) |
| Rebuild TTS downlink in Swift | Use existing `TtsPlaybackClient` |
| Rebuild standby controller in Swift | Use existing `StandbyController` (adapted for iOS screen dimming) |
| Rebuild on-screen keyboard in Swift | Use existing `OnScreenKeyboard` |
| Rebuild design token system in Swift | Use existing `shared-tokens/tokens.css` |
| Zero external Swift dependencies (constraint) | Zero new dependencies (Tauri plugins are Rust + Swift, not npm/cocoapods) |
| Separate codebase to maintain | Same codebase, form-factor-gated |
| Separate test suite | Existing Vitest tests cover the frontend |

---

## 10. References

- Voice Mode spec: `documentation/design/15-voice-mode-visual-ui-and-touchscreen-spec.md`
- Voice Mode implementation plan: `documentation/design/16-voice-mode-visual-ui-implementation-plan.md`
- Kiosk runbook: `documentation/operations/kiosk-appliance.md`
- Kiosk systemd unit: `scripts/halbert-kiosk.service`
- VoiceMode page: `halbert_core/halbert_core/dashboard/frontend/src/pages/VoiceMode.tsx`
- ShellMode context: `halbert_core/halbert_core/dashboard/frontend/src/contexts/ShellModeContext.tsx`
- Tauri config: `halbert_core/halbert_core/dashboard/frontend/src-tauri/tauri.conf.json`
- Rust entry point: `halbert_core/halbert_core/dashboard/frontend/src-tauri/src/lib.rs`
- Peer middleware: `halbert_core/halbert_core/federation/peer_middleware.py`
- Peer pairing routes: `halbert_core/halbert_core/dashboard/routes/peers.py`
- Approvals routes: `halbert_core/halbert_core/dashboard/routes/approvals.py`
- WebSocket routes: `halbert_core/halbert_core/dashboard/routes/websocket.py`
- Auth boundary: `halbert_core/halbert_core/dashboard/auth.py`
- License exception: `LICENSE-EXCEPTION-APPSTORE`
- FDR-02 (license decision): `DECISIONS.md` row 2026-09-04
- FDR-07 (App Store build is remote companion): `DECISIONS.md` row 2026-09-04
- Superseded doc: `ios-companion-handoff.md` (backend sections 5-6 still valid)
