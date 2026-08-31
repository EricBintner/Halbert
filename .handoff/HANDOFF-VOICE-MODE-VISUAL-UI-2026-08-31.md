# Handoff: Voice Mode Visual UI — Phase 1 Built, Backlog Tiered

> **Date:** 2026-08-31
> **Branch:** `feat/voice-mode-visual-ui` (worktree `~/.config/superpowers/worktrees/Halbert/voice-mode-visual-ui`)
> **Plan of record:** `documentation/design/16-voice-mode-visual-ui-implementation-plan.md` — every remaining task is specified there with exact files, code, test commands, and a model-tier label ([OPUS] / [GLM5.2]).
> **Spec:** `documentation/design/15-voice-mode-visual-ui-and-touchscreen-spec.md` (working-tree refinements carried into this branch as the first commit; main's working tree still holds an identical dirty copy — discard or merge when this lands).

## What this session built (FABLE tier — Phase 1, verified green)

The audio-reactive mark engine in `packages/design-system/src/voice/`:

| Commit | Piece |
|---|---|
| `4952df2e` | doc-15 spec refinements carried from main's dirty working tree |
| `095a399a` | doc-16 verbose implementation plan (plan of record) |
| `e1aec3f2` | `geometry.ts` — per-tine parametric mark model, standing-wave + radial deform with Hann junction pinning, `STATIC_TINE_PATHS` |
| `e8dbd809` | `springs.ts` — `ResonatorBank`: 10 springs (k=140, c=18.5, m=1), symplectic Euler at fixed 8ms substeps, render interpolation, accumulator clamp |
| `7fea0a61` | `spectrum.ts` — computed FFT bin→tine ranges (reproduces spec table at 16kHz/64), `AudioEnergySource` interface, Synthetic/IdleBreathing/Analyser sources, media-stream + node factories |
| `b67c852a` | `AudioReactiveHalbertMark.tsx` — 10 per-tine `<path>`s driven by direct DOM `d` mutation from a rAF loop (no React re-render at 60fps), thinking-contraction spring, error tint, SSR-safe static first paint |
| `a6d8edfd` | Storybook stories: idle/listening/speaking/thinking/error, dark canvas, live mic, oscillator test tones |

**Verification:** 53/53 vitest tests pass (29 baseline + 24 new), `tsc --noEmit` clean, `build-storybook` builds. Run from `packages/design-system/`: `npm run test && npm run typecheck`.

## Key decisions (rationale in plan §2)

1. **Browser is the voice-mode audio terminal** — getUserMedia mic → local AnalyserNode + WS uplink; Piper PCM → browser playback tapped by the same analyser. One capture path, Chromium AEC, identical in Tauri and kiosk browser.
2. **Voice Mode is a `/voice` route** in the dashboard SPA — runtime-agnostic; kiosk/Tauri packaging deferred to Phase 3.
3. **UI state rides the agent-turn SSE stream** (`POST /api/agent/message` via `useAgentStream`), NOT `/api/being/events` (that's proactive-only: finding/morning_report/approval_request/system_anomaly).
4. **Arc displacement is junction-pinned** (spec §3.2 as written tears the arc off the legs); amplitude table is capped so adjacent tines can't collide within the 21.33-unit gap.
5. **Bin edges computed from the live sample rate** — browsers run AudioContext at 44.1/48kHz; the spec's static table only holds at 16kHz/64 bins.

## Backlog (everything is specced in plan §5–§7)

**[OPUS]** — O1 live `/api/audio/status` (route hardcodes `idle`; `AudioPipelineCoordinator.get_status()` exists at `audio/pipeline.py:501`), O2 coordinator bootstrap in `app.py` startup:373 + register `WebRtcIngress` at `/api/audio/stream` (dead code today), O3 TTS egress WS `/api/audio/tts` + state_machine hook + frontend `TtsPlaybackClient`, O4 speaker badge on status payload, O5 acoustic-anomaly chain (3 broken links: `add_event` never called, coordinator never instantiated, `useBeingEvents` lacks the type), O6 `useVoiceModeMachine` reducer, O7 `VoiceMode.tsx` + subtitle ribbon + `pcmCapture.ts` worklet uplink, O8 routing/`ShellModeContext` third mode/`Layout` full-bleed exception, P1 standby tiers, P2 display-power daemon (greenfield — nothing exists today), P4 Tauri window + orphan `voice-hud` decision.

**[GLM5.2]** — O9 on-screen keyboard + quick chips; G1 `VoiceCompanionPill` segment cycling (effect never increments `currentIdx`) + raw `orange-500`→token classes; G2 `SpeakerProfilesCard` Test button → real `/api/audio/speakers/{id}/test` (currently fakes 0.92); G3 quiet-hours UI in `AudioSettings` + two dead privacy switches; G4 spec errata (HalbertMark JSDoc ≥96px vs code >64px; lexicon is 39 terms not "40+"); P3 kiosk systemd unit + runbook; P5 hardware validation matrix.

## Gotchas for the successor session

- **Worktree venv trap:** editable `halbert_core` installs resolve to the MAIN tree from this worktree. Use the meta-path-stripping wrapper + `arch -arm64` for backend pytest, or you test the wrong code (see project memory `halbert-worktree-venv-gotchas`).
- **41 pre-existing backend test failures on main** — compare against that baseline, never assume your task broke the suite.
- **`response_chunk` is LLM output text, not STT** — doc 15 Phase 2 mislabels it; live STT subtitles need the O2/O4 observation channel.
- **Pronunciation is already applied server-side** (`apply_pronunciation` in `state_machine.py:2931`) — no frontend lexicon work (doc 15's last Phase-2 bullet is obsolete).
- **Conversation in-flight state dies on unmount** (hook-local in `useAgentStream`) — v1 accepts persisted-history-only continuity; lifting it to a module store (pattern: `terminalSessionStore`) is the follow-up.
- Tauri on Linux renders **WebKitGTK, not Chromium** — Web Audio/AEC weaker; P4 is blocked on P3/P5 hardware findings.

## Merge notes

First commit duplicates main's dirty spec edit; when this branch merges, `git checkout` the branch's copy of doc 15 or resolve the trivial content-identical conflict. Branch targets `main` via normal PR/merge flow.
