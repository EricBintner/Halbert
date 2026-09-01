# Handoff: Voice Mode Opus Batch — ALL 11 TASKS COMPLETE

> **Date:** 2026-09-01
> **Branch:** `feat/voice-mode-visual-ui` (worktree `/Volumes/4TB-BAD/Halbert/.claude/worktrees/voice-mode-opus`)
> **Plan of record:** `documentation/design/16-voice-mode-visual-ui-implementation-plan.md` (§5 build-status banner lists every commit SHA)
> **Predecessor:** `.handoff/HANDOFF-VOICE-MODE-VISUAL-UI-2026-08-31.md` (Phase 1 + backlog)
> **Scope executed:** every [OPUS]-tier task: O1–O8, P1, P2, P4. The [GLM5.2] tasks (O9, G1–G4, P3, P5) were handled by a concurrent session on the shared branch (commit `2293a160` + later work on `feat/voice-mode-mark-v2`).

## Where things stand

- **Branch state:** `feat/voice-mode-visual-ui` at `78d21a7e`, clean tree, NOT pushed/merged. All Opus commits sit on top of main@`3f3aee77` plus the concurrent session's GLM commit `2293a160`.
- **Concurrent session:** worked the GLM tier in the *original* shared worktree, then moved to a design-system mark refactor on branch `feat/voice-mode-mark-v2` (v2 work survives on `voice-mode-v2-backup` per their session memory — confirm with them before touching design-system voice files; my branch carries one surgical additive fix there, `5bee80c7`: `createNodeAnalyserSource.stop()` now disconnects its analyser).
- **Tests at wrap:** frontend 698/698 (65 files), design-system 54/54, backend targeted suites 181/181 (display-power + tts-egress + the O1–O5 battery). Backend full-suite baseline on this base: 71 pre-existing failures (unchanged; diff against that list, never eyeball).

## What was built (task → commits)

| Task | Commits | One-line summary |
|---|---|---|
| O1 | `7ec4d173`, `2ea56376` | `/api/audio/status` serves live coordinator state, byte-identical static fallback |
| O2 | `d967cc8b`, `bac739bd` | `CAP_AUDIO` capability; coordinator bootstrap in app.py (failure-isolated, partial-start cleanup); `/api/audio/stream` WS; `add_ingress()` (fixes a latent plan-snippet bug: unstarted ingress) |
| O3 | `b70c7296`, `c841b35b`, `045aa4ee`, `c818191c`, `2bfea6c6` | TTS egress end-to-end: hub + `/api/audio/tts` WS + state-machine Piper streaming with barge-in (incl. the between-segments window) + `TtsPlaybackClient` (autoplay resume, per-turn onDone, cancel frame); side-fix: Piper `_sample_rate` was never recorded (22050Hz voices played at 16k) |
| O4 | `9f001d00`, `38e67a39` | `get_status()["speaker"]` (truthful no-match degradation, Wyoming non-clobber) + token-styled `SpeakerBadge` |
| O5 | `98a434f9`, `2033ad79` | Acoustic-anomaly urgent-wake chain: `proactive/acoustic_bridge.py` (long-lived runner sharing the sweep DB, immediate drain), `ProactiveGate` treats `anomaly_severity >= 2` as life-safety during quiet hours, badge renders the module (unwired actions hidden by default), `voiceModeEvents.ts` wake seam |
| O6 | `fc6a11c8`, `43f51916` | 77-cell table-driven reducer + hook (30s standby decay, transition-gated arming, stale-`turn_complete` guard) + `visualStateFor` |
| O7 | `65b74ac1`, `42a71d33`, `ac2576b1`, `5bee80c7` | `VoiceMode.tsx` screen + SubtitleRibbon/TouchBar + `pcmCapture.ts` (worklet→Blob-URL uplink, ScriptProcessor fallback) + per-turn TTS session-id minting (connect-before-send, test-pinned) |
| O8 | `ce7ce03b` | `/voice` route, third `'voice'` shell mode (store/restore, never persisted), full-bleed (shell top bar hidden — clipping math justified it), top-bar entry |
| P1 | `08a6691b`, `81495230` | `StandbyController`: 30s dim+clock / 10min blackout / restore; mark unmounted at blackout (rAF burn); `POST /api/system/display {"idle_seconds"}` contract |
| P2 | `07d53549`, `f2b6c68c`, `48868145` | `system/display_power.py`: sysfs backlight + xset DPMS, threshold-mapped idle reports, never-brighten, baseline restore, wake-before-speak via `asyncio.to_thread`; readable-vs-writable split for non-root kiosks; shared `iter_backlight_interfaces()` with the laptop scanner |
| P4 | `78d21a7e` | Option (a) chosen: `voice-hud` route built (BroadcastChannel relay `hudChannel` + `useHudSpeechPublisher` in AgentChat + `VoiceHud` page + top-bar summon button + Layout full-bleed exception + onboarding-gate skip). Rust untouched; `audio_capture.rs` KEPT as the desktop-AEC hedge |

## Process notes / caveats for the successor

1. **P4 is the only task WITHOUT an external review pass.** The session hit a weekly API rate limit mid-review; I finished the last three wirings (App.tsx route element, AgentChat publisher mount, Layout exception + summon-button mount) directly. Implementation is 698/698 + `tsc` clean, but run the two-stage review (spec + quality) on `78d21a7e` before merging if you want parity with the other ten tasks. The P4 subagent's original brief is in the session transcript; the essentials: BroadcastChannel relay is the documented data path; HUD auto-dismisses when the relayed turn ends; a Rust-side follow-up is noted in `VoiceHud.tsx`'s header (the `voice-hud:hotkey` interrupt event only reaches the HUD webview, not the main window's TTS player).
2. **Worktree/branch hazard (recorded in project memory):** a concurrent session can switch a SHARED worktree's checked-out branch mid-task (it happened; one commit landed on their branch and had to be relocated via temp-index plumbing). The Opus work now lives in its own worktree (`.claude/worktrees/voice-mode-opus`); keep it that way until merge.
3. **Backend tests from any worktree:** ONLY via `arch -arm64 /Volumes/4TB-BAD/Halbert/.venv/bin/python wt_pytest.py <args>` from the worktree root (wrapper present; the venv editable install resolves `halbert_core` to the MAIN tree otherwise). Frontend: `npx vitest run` + `npx tsc --noEmit` from `halbert_core/halbert_core/dashboard/frontend/`.

## Parked decisions & follow-ups (deliberately not done)

- **Keyboard-only mic error:** `turn_complete` → listening opens the mic even for keyboard-only users; on a deployment without pre-granted permission, gUM denial lands the machine in `error`. Product call needed: is gUM-denied a full machine error? (Owners: P1/O8 follow-up.)
- **"Quiet" proactivity dial:** severity-2 acoustic wakes bypass quiet HOURS (O5) but are still suppressed at gate step 1 by a `quiet` dial setting and in safe mode. Long-term fix suggested by review: publish severity-2 acoustic findings with severity `"critical"` (collapses all three gate steps). A note at `gate.py` or in doc 16 would prevent someone assuming the wake guarantee is unconditional.
- **Severity-2 gate comment** (one paragraph in doc 16 or `gate.py:78-83`) naming dial/safe-mode suppression explicitly — same item, documentation half.
- **P2 module doc's kiosk note:** without a udev rule the backlight path silently no-ops (`available.backlight: false`) — record in `documentation/operations/kiosk-appliance.md` (P3's runbook, concurrent session's file).
- **In-flight conversation continuity** across Voice↔Canvas remains the accepted v1 limitation (hook-local state in `useAgentStream`); module-store lift is the planned follow-up.
- **HUD Rust follow-ups** (in `VoiceHud.tsx` header): hotkey-interrupt event doesn't reach the main window's TTS player; no in-HUD hide command beyond the mouse fallback.
- **Design-system pile** (concurrent session's refactor branch): `createNodeAnalyserSource` analyser-disconnect is FIXED on my branch (`5bee80c7`) — resolve trivially when their mark-v2 re-lands; the stale spec §6.1 `[<Settings>]` control in the voice header is a wireframe deviation left to the mark-v2 owner.
- **Merge notes:** branch is unpushed. First commit of the predecessor branch duplicated main's dirty doc-15 edit — resolve content-identical on merge. O1's regression-lock tests build their own app, so no coordinator-state coupling.

## Verification quick-sheet

```bash
cd /Volumes/4TB-BAD/Halbert/.claude/worktrees/voice-mode-opus
arch -arm64 /Volumes/4TB-BAD/Halbert/.venv/bin/python wt_pytest.py \
  halbert_core/tests/test_audio_routes.py halbert_core/tests/test_audio_stream_ws.py \
  halbert_core/tests/test_tts_egress.py halbert_core/tests/test_acoustic_bridge.py \
  halbert_core/tests/test_audio_pipeline_speaker.py halbert_core/tests/test_display_power.py -v
cd halbert_core/halbert_core/dashboard/frontend && npx vitest run && npx tsc --noEmit
cd ../../../packages/design-system && npm run test && npm run typecheck
```