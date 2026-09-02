# Hardware Validation Matrix — N150 Voice Mode Appliance

> **Date:** 2026-08-31
> **Status:** Pending hardware testing (checklist for on-device validation)
> **Target:** Intel N150, 16GB RAM, 256GB NVMe, 10" HDMI capacitive touch display

## Purpose

This is a manual checklist to validate Voice Mode on the actual N150 appliance
hardware. All tests require a running Halbert backend with audio subsystem
enabled and the Chromium kiosk browser pointing at `/voice`.

Record results in the "Result" column and file issues for any failures.

## Validation Matrix

### 1. Visual Performance

| # | Test | Target | Method | Result |
|---|------|--------|--------|--------|
| 1.1 | 60fps path deformation | >=55fps sustained | Chrome DevTools FPS meter (Ctrl+Shift+P → "Show FPS meter"); speak into mic for 30s | |
| 1.2 | Spring physics stability at 30fps | No visual judder or spiral | Throttle CPU to 4x slowdown in DevTools; verify mark still animates smoothly | |
| 1.3 | Static first paint correctness | Mark renders before audio | Hard refresh; verify mark is visible before mic permission prompt | |
| 1.4 | Junction pinning under displacement | No arc/leg tearing | Visual inspection during loud audio — arcs stay connected to legs | |

### 2. Wake-from-Black Latency

| # | Test | Target | Method | Result |
|---|------|--------|--------|--------|
| 2.1 | Software wake (standby tier 2 → active) | <50ms | Touch screen after 10min idle; measure time from touch event to mark visible | |
| 2.2 | Hardware backlight wake | <100ms | After DPMS off (P2); send a voice turn; measure backlight-on to mark visible | |
| 2.3 | Standby tier 1 → active | <30ms | Touch screen after 30s idle (ultra-dim); measure restore time | |

### 3. Touch Interaction

| # | Test | Target | Method | Result |
|---|------|--------|--------|--------|
| 3.1 | Touch hit areas | >=44px for all interactive elements | Measure quick-chip buttons, keyboard keys, dismiss/mic buttons in DevTools | |
| 3.2 | Keyboard input latency | <100ms from tap to character in input field | Type "hello" on on-screen keyboard; observe responsiveness | |
| 3.3 | Quick-chip tap → send | <200ms from tap to message sent | Tap "System Vitals"; verify message appears in conversation | |
| 3.4 | Multi-touch rejection | No phantom inputs | Two-finger touch on keyboard; verify no double-key events | |

### 4. Audio Sync

| # | Test | Target | Method | Result |
|---|------|--------|--------|--------|
| 4.1 | TTS ↔ visualizer sync | <100ms offset | Clap test: send a message that triggers TTS; verify mark animates in sync with audible speech | |
| 4.2 | Mic capture → visualizer latency | <50ms | Speak into mic; verify mark responds in real-time (not delayed) | |
| 4.3 | Echo cancellation | No audible echo | Enable TTS + mic simultaneously; verify no feedback loop | |
| 4.4 | Barge-in cancellation | TTS stops within 200ms of VAD trigger | Speak while TTS is playing; verify TTS stops promptly | |

### 5. Standby Soak Test

| # | Test | Target | Method | Result |
|---|------|--------|--------|--------|
| 5.1 | 24h standby tier 1 (ultra-dim) | No crash, no memory leak | Leave idle for 30s → tier 1; monitor for 24h; check process memory | |
| 5.2 | 24h standby tier 2 (blackout) | No crash, wakes on touch | Leave idle for 10min → tier 2; monitor for 24h; verify touch wakes | |
| 5.3 | Wake-word listener stability | Listener active throughout soak | Verify Wyoming/local mic ingress still receives audio after 24h | |
| 5.4 | CPU usage in standby | <5% sustained | `top` or `htop` during tier 2 standby | |

### 6. Acoustic Anomaly Detection

| # | Test | Target | Method | Result |
|---|------|--------|--------|--------|
| 6.1 | Smoke alarm detection | Triggers within 5s | Play smoke alarm sound from phone; verify anomaly finding appears | |
| 6.2 | Screen wake on anomaly | Wakes from standby | In standby tier 2; trigger anomaly; verify screen wakes | |
| 6.3 | Life-safety bypass of quiet hours | Anomaly alerts during quiet hours | Enable quiet hours; trigger anomaly; verify alert still fires | |

## Sign-off

| Validator | Date | Result |
|-----------|------|--------|
| | | |

## Notes

**Updated 2026-09-02 (SONNET-05):** P2/O3/O5 are no longer unbuilt — all
three landed on `main` in the Voice Mode Opus batch (`.handoff/HANDOFF-VOICE-MODE-OPUS-RESULTS-2026-09-01.md`)
and the subsequent OPUS-02 packet this session made the voice chain actually
reachable end to end (`U2-15` fix, `65ff3e83`). No test below is genuinely
"blocked" on missing code any more — every row is blocked only on the
hardware run itself, which is still at **0/22 completed**
(`.handoff/RESULTS-OPUS-BATCH-2026-09-01.md` §4). Do not re-mark rows
"blocked" for the reasons below; they no longer apply.

- Tests 1.x require the audio-reactive mark engine (Phase 1, complete)
- ~~Tests 2.2, 5.2 require the display power daemon (P2, OPUS — not yet built)~~ — P2 shipped: `system/display_power.py` (sysfs backlight + xset DPMS, wake-before-speak).
- ~~Tests 4.3, 4.4 require the TTS egress WebSocket (O3, OPUS — not yet built)~~ — O3 shipped, and as of OPUS-02 (2026-09-02) is reachable from a real turn, not only under test mocks (see the O3 caveat in the Voice Mode Opus results handoff).
- ~~Test 6.x requires the acoustic anomaly chain wiring (O5, OPUS — not yet built)~~ — O5 shipped: `proactive/acoustic_bridge.py` + `ProactiveGate` severity-2 handling.
- No real audio has ever gone through this chain (no sherpa-onnx/openwakeword/Piper voices in `.venv`, `AudioConfig.enabled` defaults False) — the hardware run below is what would first exercise it for real, not a code gap.
