# Voice Mode Visual UI — Verbose Implementation Plan

> **Document:** `documentation/design/16-voice-mode-visual-ui-implementation-plan.md`
> **Status:** Implementation Plan (reviewed against live codebase 2026-08-31)
> **Date:** 2026-08-31
> **Branch:** `feat/voice-mode-visual-ui` (worktree: `~/.config/superpowers/worktrees/Halbert/voice-mode-visual-ui`)
> **Implements:** `documentation/design/15-voice-mode-visual-ui-and-touchscreen-spec.md`
> **Reads With:** `documentation/design/11-response-modality-handoff.md`, `documentation/design/14-system-prompts-and-modality-gap-analysis.md`, `documentation/design/DESIGN-SYSTEM-SPEC.md`, `audio-research/01-CORRECTED-ARCHITECTURE.md`, `audio-research/03-UX-SURFACES.md`

> **Execution model:** Every task is labeled with a work tier — **[FABLE]**, **[OPUS]**, or **[GLM5.2]**.
> This session plans *everything* and builds *only* the [FABLE] tasks (Phase 1: the audio-reactive
> mark engine). Everything else is the handoff backlog in §5–§7, written with enough precision
> (exact paths, code, commands, acceptance criteria) for Opus/GLM-class execution without re-derivation.

**Goal:** Build Voice Mode — a full-screen, touch-first, audio-reactive embodiment surface where the Halbert brand mark resonates with real microphone and TTS audio — on top of the existing dashboard SPA, so it runs identically in the Tauri desktop shell and in a `--kiosk` browser on an N150 appliance.

**Architecture:** The browser becomes the voice-mode audio terminal: `getUserMedia` captures 16kHz mic PCM which both feeds a local `AnalyserNode` (visualizer) and streams up a WebSocket to the (registered) `WebRtcIngress`; Piper TTS PCM streams down a new WebSocket and plays through the browser's `AudioContext`, tapped by the same analyser. The mark is re-engineered from one monolithic `<path>` into 10 per-tine `<path>` elements deformed by a fixed-timestep spring/standing-wave physics core. UI state transitions ride the existing agent-turn SSE stream (`modality_resolved`, `speech_segment`), not the `/api/being/events` proactive channel.

**Tech Stack:** React 18.2, TypeScript 5.6, Tailwind 3 (+ `shared-tokens/tokens.css`), Web Audio API (`AnalyserNode`, `AudioWorklet`), FastAPI WebSockets, Piper TTS (sherpa-onnx), vitest + jsdom + @testing-library/react, Storybook 8.

---

## 1. Verified Codebase Reality — Corrections to the Spec

The spec (doc 15) was written against a partly aspirational codebase. The following discrepancies were verified by direct code inspection on 2026-08-31. **The plan below supersedes doc 15 wherever they conflict.**

### 1.1 Brand mark geometry (verified `packages/design-system/src/primitives/HalbertMark.tsx`)

| Spec claim | Verified reality | Consequence |
|---|---|---|
| 10 concentric paths at `display` density | 10 subpaths **joined into one `<path d>`** (`HalbertMark.tsx:48-59,181`) | Per-tine animation requires generating **10 separate `<path>` elements**. Do not reuse `PATHS_DISPLAY` directly. |
| "Y = 944px (Base)" for legs | Legs terminate at Y=512; Y=944 is only the outermost arc's bottom apex (512+432). Inner arc apexes: 512+r. | Path sampler must treat legs and arc separately. |
| Leg tops at Y=80 | Only the spine tops at Y=80. Lane leg tops sit on the 432-radius circle: 82.67, 90.80, 104.71, 125.01, 152.80, 190.01, 240.47, 314.09; lane 9 has no legs (`laneTop()` formula verified against all path strings) | Sampler uses `laneTop(lane) = 512 − √(432² − r²)`. |
| Radii 48..432 | ✅ Exact match (`laneRadius(lane) = 48·lane`) | — |
| `density='auto'` → display at >64px | ✅ Confirmed by code and tests (`HalbertMark.tsx:110-124`, `primitives.test.tsx:218-222`). Doc comments elsewhere claim ≥96px — code wins. | 512px resonator → display tier by default; 48px header emblem → medium tier (6 subpaths). |
| Display stroke-width | 26.67 mark-units (component + all `assets/brand/*.svg`). The parametric model in `marketing/web-v7/src/lib/markGeometry.js` assumes 32/48 pitch (gap 16) | The voice geometry module uses the component's model (pitch 48, stroke 26.67, gap 21.33). Adjacent-tine excursion sums must stay < 21.33 to avoid stroke collision. |

### 1.2 Streaming & event plumbing (verified)

| Spec claim | Verified reality | Consequence |
|---|---|---|
| "`/api/being/events` carries `modality_resolved` / `speech_segment` / `response_chunk`" | **False.** `/api/being/events` (`dashboard/routes/being.py:33`) streams only proactive events from `ProactiveEventBus`: `finding \| morning_report \| approval_request \| system_anomaly`. The modality events ride the **agent turn SSE stream**: `POST /api/agent/message` (`routes/agent.py:1424`), consumed by `useAgentStream` via fetch-reader, emitted by `agents/state_machine.py:2928` (`modality_resolved`) and `:2944` (`speech_segment`) — **not** by `integrations/modality_wiring.py` (which is a pure helper: demux/resolve/pronounce, no event emission). | Voice Mode subscribes via `useAgentStream` (it initiates its own turns there anyway); `/api/being/events` is only for proactive wake triggers (Task O5). |
| SSE event types exist (`SpeechSegmentEvent`, `ResponseModality`) | ✅ Exact: `useAgentStream.ts:244-263`. `ResponseModality = 'text'\|'voice'\|'mixed'\|'deferred'`; `SpeechSegmentEvent { text, role, prosody { rate, volume, whisper } }`. Handlers at `useAgentStream.ts:804-834`. | Reuse verbatim. No type work needed. |
| `AcousticAuraIndicator` polls `/api/audio/status` (2s) | ✅ (`components/audio/AcousticAuraIndicator.tsx:47,62`; `AudioState` vocabulary `idle\|listening\|recognized\|thinking\|speaking\|error` matches spec §4 exactly) — **but the route hardcodes `"state": "idle"`** (`routes/audio.py:120`, `TODO: read from pipeline coordinator`). `AudioPipelineCoordinator.get_status()` with real state exists unconnected (`audio/pipeline.py:501-521`). | Task O1 wires them. Until then every state-driven surface shows `idle`. |
| Browser 16kHz mic ingress | `WebRtcIngress` fully implemented (`audio/ingress/webrtc_ingress.py`, WS binary PCM frames, queue-full drop-oldest) but **never registered as a route** (zero hits outside its file). Frontend has **no** streaming capture code; only a one-shot `MediaRecorder`→base64 enrollment POST (`VoiceEnrollmentModal.tsx:48-53`). | Task O2 registers `/api/audio/stream`; Task O7 builds the browser `AudioWorklet` uplink. |
| TTS reaches the browser | **Nothing does.** `AudioPipeline.speak()` discards PCM chunks with a literal `pass` (`audio/pipeline.py:573-610`). `HalbertVoiceBackend.synthesize()` (`integrations/voice_backend.py:80-146`) buffers PCM into a `SpeechResult` for the Haloysius engine, which never forwards it. No `audio/*` route exists; the frontend contains zero playback code. | Task O3 adds a TTS egress WebSocket + browser PCM player. This is the largest greenfield piece. |
| Biometric badge (speaker + confidence) | CAM++ 256-dim engine exists (`audio/speech/speaker_id.py`, `SpeakerIdentifier.identify → SpeakerMatch`), per-turn `VoiceTurnObservation { speaker_id, speaker_name, speaker_role, speaker_confidence }` computed at `pipeline.py:361-391` — but `AudioPipelineCoordinator` is **never instantiated in production** and no endpoint exposes the latest observation. | Task O4 exposes it on the `/api/audio/status` payload. |
| Acoustic anomaly → urgent screen wake | CED-tiny tagger exists (`audio/acoustic/audio_tagger.py`); `AcousticAnomalyDetector` exists (`findings/detectors/acoustic_anomaly.py:58`); chain to SSE **broken in 3 places**: nobody calls `add_event()`; coordinator never instantiated; `useBeingEvents.ts:26` lacks the acoustic type and `AcousticAnomalyModule.tsx` renders nowhere. | Task O5 wires the whole chain. |
| Quiet hours deferred to `modality_wiring.py` | ✅ `get_quiet_hours_policy()` (22:00–07:00), `should_speak_proactively()`, `LIFE_SAFETY_EVENT_TYPES` all present (`integrations/modality_wiring.py:203-472`). Note **dual sources**: engine policy is hardcoded 22–7; configurable hours live in `BeingConfig.quiet_hours` (used by `ProactiveGate`, `proactive/gate.py:88-162`). Pronunciation lexicon: **39 terms**, not "40+" (`modality_wiring.py:53-99`). No REST endpoint exposes any of it; only quiet-hours config via `GET /api/audio/config` and `/api/being`. | Voice Mode never computes quiet hours itself; reads config for display only (Task G3 adds the missing settings UI). |
| Wake word | `WakeWordSpotter` (openWakeWord) exists (`audio/speech/wake_word.py:44`); "Hey Halbert" model intentionally untrained/deferred. sherpa-onnx does VAD/ASR/TTS/speaker-ID/tagging, not wake word. | Voice Mode v1 uses push-to-talk + screen tap; wake-word wake is out of scope (documented in §7 risks). |
| Screen power management | **Nothing exists** — no DPMS/xset/ddcutil/backlight writes anywhere; only a read-only backlight scanner (`discovery/scanners/laptop.py:341-381`). | Task P2 is greenfield (Python daemon + frontend tiers). |
| `VoiceCompanionPill` cycles segments | **Bug:** its `useEffect` (`VoiceCompanionPill.tsx:23-33`) never increments `currentIdx` — only segment 1 ever displays. Also uses raw `orange-500`/`purple-500` classes (token violation; canonical tokens are `shared-tokens/tokens.css`). | Task G1. |
| `SpeakerProfilesCard` Test button | Mock: fakes `0.92` via `setTimeout`; never calls the existing `POST /api/audio/speakers/{id}/test` (`SpeakerProfilesCard.tsx:70-79` vs `routes/audio.py:211`). | Task G2. |
| `voice-hud` Tauri window | Exists in Rust (`src-tauri/src/floating_panel.rs`: borderless 480×72 non-activating panel loading route `voice-hud`) — **but the `voice-hud` frontend route was never built**, and no frontend code invokes the Tauri commands. `tauri.conf.json` has no fullscreen/kiosk keys; capabilities grant only `core:default`+`opener:default`. | Phase 3 (Task P4) decides the HUD's fate: build the route or retire the window. |
| Shell & routing | React Router v6, routes in `src/App.tsx:91-110`; `Layout.tsx` renders page children **only in browsing mode** (engaged mode renders `HostShell`); `ShellModeContext` = `'engaged' \| 'browsing'` only; conversation in-flight state is hook-local (`useAgentStream`) and dies on unmount — only server-persisted timeline turns survive view switches (`useTimeline`). No zustand/store. No touch/gesture infrastructure anywhere. `Jobs.tsx`/`Memory.tsx` exist unrouted. | Tasks O7–O8. In-flight continuity across Voice↔Canvas is a documented limitation for v1 (§7). |

---

## 2. Architecture Decisions

### Decision 1 — The browser is the voice-mode audio terminal
No dual-capture of the host mic, no backend PCM tap for visualization.

```
LISTENING:  getUserMedia(16kHz, AEC) ─┬─▶ AnalyserNode ─▶ AudioReactiveHalbertMark
                                      └─▶ AudioWorklet ─▶ WS /api/audio/stream ─▶ WebRtcIngress ─▶ VAD/ASR
SPEAKING:   state_machine ─▶ PiperTTS PCM ─▶ WS /api/audio/tts ─▶ PcmPlayer (AudioContext)
                                                                       └─▶ AnalyserNode ─▶ AudioReactiveHalbertMark
```
Rationale: one capture path (Chromium-grade echo cancellation when playback and capture share the browser); the analyser and playback are sample-synchronized by construction; identical code runs in Tauri's webview and a kiosk Chromium. ALSA exclusive-device conflicts are avoided entirely. Latency for the visualizer is zero-copy local.

### Decision 2 — Ten per-tine `<path>` elements, driven by direct DOM mutation
`HalbertMark.tsx` stays untouched. The new component renders 10 `<path>` siblings and writes `d` attributes via refs at 60fps, bypassing React reconciliation (the physics lives in refs, not state). Initial render (and SSR/Storybook-static render) uses the exact static geometry, so first paint is correct without audio.

### Decision 3 — FFT bin edges are computed, not hardcoded
Doc 15's `TINE_BIN_RANGES` assumes 16kHz/64 bins. Browsers run `AudioContext` at 44.1/48kHz; getUserMedia resamples the *capture*, not the context. `binRangesFor(sampleRate, binCount)` applies the spec's own center-frequency argmin rule; at 16kHz/64 it reproduces the spec table exactly (verified: rounding bin edges, e.g. 700Hz → round(5.6) = 6 matches spec's `[6,8]`). The static table remains as the documented reference and a test invariant.

### Decision 4 — Arc displacement is junction-pinned (spec improvement)
Doc 15 §3.2's radial arc displacement `B·E·cos(mθ+ψ)` has no boundary window — cos(ψ) ≠ 0 at θ=0/π would tear the arc away from the legs each frame. The implementation multiplies by a Hann window `sin²(θ)` over θ∈[0,π], mirroring §3.1's leg pinning, so leg/arc junctions are continuous by construction. Leg endpoints additionally pin via `hann(u)` which is 0 at both ends. This preserves the spec's *intent* (resonant arcs) while removing the geometric defect.

### Decision 5 — Voice Mode is a route, not a window
`/voice` joins `src/App.tsx`. `Layout.tsx` gets a full-bleed exception (same pattern as `isSettingsRoute`, `Layout.tsx:185`); `ShellModeContext` gains `'voice'` as a third mode (set automatically when entering `/voice`, restored on exit). Phase 3 packaging (Chromium kiosk unit, Tauri window config) treats the page as runtime-agnostic. The dark `#000000` standby canvas is a deliberate, scoped divergence from the daylight palette: Voice Mode's tokens resolve against its own black surface (the mark is `tone='accent'` vermilion, which reads on black; white-on-vermilion text rules don't apply here).

### Decision 6 — The physics/geometry core is pure TypeScript, DOM-free
`geometry.ts`, `springs.ts`, `spectrum.ts` contain no React and no Web Audio types. This makes them unit-testable in jsdom, importable by a future Canvas2D fallback, and reusable by the `voice-hud` panel later. The component layer (`AudioReactiveHalbertMark.tsx`) only glues sources → bank → path strings.

---

## 3. File Structure

**Phase 1 [FABLE, this branch]** — `packages/design-system/`:
```
src/voice/
├── geometry.ts                    # parametric mark model, per-tine sampler, deform → path d
├── springs.ts                     # ResonatorBank: fixed-timestep spring array + phase drift
├── spectrum.ts                    # bin mapping + AudioEnergySource + synthetic/idle/analyser sources
├── AudioReactiveHalbertMark.tsx   # React component (refs + rAF, SSR-safe)
└── index.ts                       # voice barrel
src/test/
├── voiceGeometry.test.ts
├── voiceSprings.test.ts
├── voiceSpectrum.test.ts
└── audioReactiveMark.test.tsx
src/stories/AudioReactiveHalbertMark.stories.tsx
src/index.ts                       # add voice exports
```

**Phase 2 [OPUS, handoff]** — backend then frontend:
```
halbert_core/halbert_core/dashboard/routes/audio.py          # O1 live status, O4 speaker badge
halbert_core/halbert_core/dashboard/routes/websocket.py      # O2 /api/audio/stream, O3 /api/audio/tts
halbert_core/halbert_core/dashboard/app.py                   # O2 coordinator bootstrap (startup:373)
halbert_core/halbert_core/agents/state_machine.py            # O3 TTS egress hook (after :2944)
halbert_core/halbert_core/findings/detectors/acoustic_anomaly.py  # O5 call-site wiring
halbert_core/halbert_core/dashboard/frontend/src/
├── hooks/useVoiceModeMachine.ts                             # O6 7-state machine
├── lib/pcmCapture.ts                                        # O7 AudioWorklet uplink
├── lib/ttsPlayback.ts                                       # O3 PCM player + analyser tap
├── pages/VoiceMode.tsx                                      # O7 full-screen screen
├── components/voice/{SubtitleRibbon,TouchBar,SpeakerBadge,OnScreenKeyboard}.tsx  # O7/O9
├── contexts/ShellModeContext.tsx                            # O8 third mode
├── components/Layout.tsx                                    # O8 full-bleed voice route
└── App.tsx                                                  # O8 /voice route
```

**Phase 3 [OPUS/GLM, handoff]** and adjacent fixes [GLM] are specified in §5–§7.

---

## 4. Phase 1 [FABLE] — The Audio-Reactive Mark Engine (build now)

> **Build status: ✅ COMPLETE on this branch** (2026-08-31). F1 `e1aec3f2`, F2 `e8dbd809`,
> F3 `7fea0a61`, F4 `b67c852a`, F5 `a6d8edfd`. Suite: 53/53 passing (29 baseline + 24 new),
> `tsc --noEmit` clean, `build-storybook` builds. One as-built correction vs. the code blocks
> below: lane-1 static leg top is `82.67` (not 82.68) — the shipped test and this document's
> blocks were both corrected.

Design-system package commands (run from `packages/design-system/`):
- Test: `npm run test` (vitest, jsdom) · Typecheck: `npm run typecheck` · Stories: `npm run storybook`
- Baseline verified on this branch: **29/29 tests pass**.

### Task F1 [FABLE]: Per-tine geometry — `src/voice/geometry.ts`

**Files:**
- Create: `packages/design-system/src/voice/geometry.ts`
- Test: `packages/design-system/src/test/voiceGeometry.test.ts`

The static mark (verified in §1.1): spine `M 512 80 V 512`; lanes 1–9 full U's, radius `48·lane`, arc center (512,512), leg tops on the 432-circle. Lane 9 is a bare semicircle. Deformation per spec §3.1/§3.2 with Decision 4's arc window.

- [ ] **Step 1: Write the failing tests** — `src/test/voiceGeometry.test.ts`:

```ts
// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { describe, it, expect } from 'vitest'
import {
  MARK,
  TINE_COUNT,
  TINE_AMPLITUDES,
  TINE_MODES,
  laneRadius,
  laneTop,
  tinePathD,
  STATIC_TINE_PATHS,
} from '../voice/geometry'

function firstPoint(d: string): [number, number] {
  const m = d.match(/^M ([\d.-]+) ([\d.-]+)/)!
  return [parseFloat(m[1]), parseFloat(m[2])]
}
function points(d: string): Array<[number, number]> {
  return d
    .replace(/^M /, '')
    .split(' L ')
    .map((p) => p.split(' ').map(Number) as [number, number])
}

describe('mark voice geometry', () => {
  it('matches the verified static mark model', () => {
    expect(TINE_COUNT).toBe(10) // spine + 9 lanes
    expect(laneRadius(9)).toBe(432)
    expect(laneTop(1)).toBeCloseTo(82.67, 2)
    expect(laneTop(9)).toBeCloseTo(512, 5) // lane 9 has no legs
  })

  it('static tine paths reproduce the display-density endpoints', () => {
    expect(STATIC_TINE_PATHS).toHaveLength(10)
    // spine: M 512 80 ... 512 512
    expect(firstPoint(STATIC_TINE_PATHS[0])).toEqual([512, 80])
    // lane 1 left-leg top
    expect(firstPoint(STATIC_TINE_PATHS[1])).toEqual([464, 82.67])
    // lane 9 bare semicircle: (80,512) .. (944,512)
    expect(firstPoint(STATIC_TINE_PATHS[9])).toEqual([80, 512])
    const lane9 = points(STATIC_TINE_PATHS[9])
    expect(lane9[lane9.length - 1]).toEqual([944, 512])
    // arc apex of lane 4 is at y = 512 + 192 = 704
    const lane4 = points(STATIC_TINE_PATHS[4])
    const apexY = Math.max(...lane4.map(([, y]) => y))
    expect(apexY).toBeCloseTo(704, 1)
  })

  it('pins all junctions under displacement (no tearing)', () => {
    for (let lane = 1; lane <= 9; lane++) {
      const displaced = tinePathD(lane, TINE_AMPLITUDES[lane], 1.234)
      const pts = points(displaced)
      const statik = points(STATIC_TINE_PATHS[lane])
      // leg tops and leg/arc junctions do not move
      expect(pts[0]).toEqual(statik[0])
      expect(pts[pts.length - 1]).toEqual(statik[statik.length - 1])
      if (lane < 9) {
        // the leg-bottom junction (start of the arc run) is pinned
        const legBottom = statik[24] // LEG_SAMPLES: 0..24 on the left leg
        expect(pts[24][0]).toBeCloseTo(legBottom[0], 2)
        expect(pts[24][1]).toBeCloseTo(legBottom[1], 2)
      }
    }
  })

  it('displaces interior points and mirrors leg directions', () => {
    const d = tinePathD(4, 10, 0)
    const pts = points(d)
    const statik = points(STATIC_TINE_PATHS[4])
    // left-leg midpoint moves outward (−x); right-leg midpoint moves outward (+x)
    const leftMid = 12
    expect(pts[leftMid][0]).toBeLessThan(statik[leftMid][0])
    const rightMid = pts.length - 1 - 12
    expect(pts[rightMid][0]).toBeGreaterThan(statik[rightMid][0])
  })

  it('keeps adjacent tine excursions inside the inter-lane gap', () => {
    // display-tier gap = 48 pitch − 26.67 stroke = 21.33 units
    for (let k = 0; k < TINE_COUNT - 1; k++) {
      expect(TINE_AMPLITUDES[k] + TINE_AMPLITUDES[k + 1]).toBeLessThan(21.33)
    }
    expect(TINE_MODES).toHaveLength(TINE_COUNT)
  })

  it('spine pins both ends and flexes in the middle', () => {
    const d = tinePathD(0, TINE_AMPLITUDES[0], 0)
    const pts = points(d)
    expect(pts[0]).toEqual([512, 80])
    expect(pts[pts.length - 1]).toEqual([512, 512])
    const midXs = pts.slice(4, -4).map(([x]) => x)
    expect(Math.max(...midXs.map((x) => Math.abs(x - 512)))).toBeGreaterThan(0.5)
  })
})
```

- [ ] **Step 2: Run to verify failure**
  Run: `cd packages/design-system && npx vitest run src/test/voiceGeometry.test.ts`
  Expected: FAIL — `Cannot find module '../voice/geometry'`

- [ ] **Step 3: Implement** — `packages/design-system/src/voice/geometry.ts` (complete):

```ts
// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * Parametric geometry of the Halbert mark, display density, split per tine.
 *
 * Verified against packages/design-system/src/primitives/HalbertMark.tsx
 * (2026-08-31): 1024x1024 viewBox; spine M 512 80 V 512; nine U-lanes of
 * radius 48*lane drawn left-leg-down -> bottom semicircle -> right-leg-up;
 * leg tops sit on the 432-radius circle around (512, 512); lane 9 is a bare
 * semicircle; display stroke-width 26.67 (gap between lanes: 21.33).
 *
 * The audio deformation follows documentation/design/15-...spec §3:
 * standing waves on the vertical legs with a Hann window pinning both ends,
 * radial cosine flex on the base arc with a Hann window over theta in
 * [0, PI] pinning the leg/arc junctions (spec improvement — the un-windowed
 * cosine in spec §3.2 would tear the arc off the legs whenever the phase is
 * non-zero).
 */

export const MARK = Object.freeze({
  cx: 512,
  cy: 512,
  outerR: 432,
  laneStep: 48,
  lanes: 9,
  spine: { top: 80, bottom: 512 },
} as const)

/** Tine 0 is the spine; tines 1..9 are the U-lanes. */
export const TINE_COUNT = MARK.lanes + 1

export function laneRadius(lane: number): number {
  return MARK.laneStep * lane
}

/** y of a lane's leg tops (round-cap center sits half a stroke above). */
export function laneTop(lane: number): number {
  const r = laneRadius(lane)
  return MARK.cy - Math.sqrt(Math.max(0, MARK.outerR ** 2 - r ** 2))
}

/**
 * Spatial harmonic mode per tine (n_k in spec §3.1). Inner structures ripple
 * (mode 2), the long outer legs use the fundamental to avoid visible kinks.
 */
export const TINE_MODES: readonly number[] = [2, 2, 2, 1, 1, 1, 1, 1, 1, 1]

/**
 * Maximum lateral excursion per tine (mark units) at full spectral energy.
 * Invariant: neighboring sums stay below the 21.33-unit inter-lane gap so
 * strokes can never visually collide (test-enforced).
 */
export const TINE_AMPLITUDES: readonly number[] = [4, 6, 7, 8, 9, 9, 10, 10, 10, 8]

/** Phase drift rates (rad/s) — inner tines shimmer faster than outer ones. */
export const TINE_DRIFT: readonly number[] = [1.4, 1.2, 1.0, 0.9, 0.8, 0.7, 0.6, 0.55, 0.5, 0.45]

export const LEG_SAMPLES = 24
export const ARC_SAMPLES = 48
export const SPINE_SAMPLES = 32

function hann(u: number): number {
  const s = Math.sin(Math.PI * u)
  return s * s
}

function fmt(v: number): string {
  return String(Math.round(v * 100) / 100)
}

function pt(x: number, y: number): string {
  return `${fmt(x)} ${fmt(y)}`
}

/**
 * Build the `d` string for one tine.
 * @param lane 0 = spine, 1..9 = U-lanes
 * @param displacement signed crest displacement in mark units; the caller
 *        passes A_k * E_k(t) where E is the spring-smoothed band energy
 * @param phase current phase drift phi_k(t) in radians
 */
export function tinePathD(lane: number, displacement: number, phase: number): string {
  if (lane === 0) {
    const top = MARK.spine.top
    const len = MARK.spine.bottom - top
    const mode = TINE_MODES[0]
    const pts: string[] = []
    for (let i = 0; i <= SPINE_SAMPLES; i++) {
      const u = i / SPINE_SAMPLES
      const y = top + u * len
      const dx = displacement * Math.sin(mode * Math.PI * u + phase) * hann(u)
      pts.push(pt(MARK.cx + dx, y))
    }
    return `M ${pts.join(' L ')}`
  }

  const r = laneRadius(lane)
  const mode = TINE_MODES[lane]

  if (lane === MARK.lanes) {
    // Lane 9: bare semicircle (no legs), theta 0..PI from left to right.
    const pts: string[] = []
    for (let i = 0; i <= ARC_SAMPLES; i++) {
      const u = i / ARC_SAMPLES
      const th = u * Math.PI
      const rr = r + displacement * Math.cos(mode * th + phase) * hann(u)
      pts.push(pt(MARK.cx - rr * Math.cos(th), MARK.cy + rr * Math.sin(th)))
    }
    return `M ${pts.join(' L ')}`
  }

  const top = laneTop(lane)
  const legLen = MARK.cy - top
  const pts: string[] = []

  // Left leg, top -> bottom. Outward normal is -x.
  for (let i = 0; i <= LEG_SAMPLES; i++) {
    const u = i / LEG_SAMPLES
    const y = top + u * legLen
    const dx = -displacement * Math.sin(mode * Math.PI * u + phase) * hann(u)
    pts.push(pt(MARK.cx - r + dx, y))
  }

  // Base arc, theta 0..PI (left-bottom -> apex -> right-bottom), skipping
  // both endpoints: they coincide with the pinned leg bottoms.
  for (let i = 1; i < ARC_SAMPLES; i++) {
    const u = i / ARC_SAMPLES
    const th = u * Math.PI
    const rr = r + displacement * Math.cos(mode * th + phase) * hann(u)
    pts.push(pt(MARK.cx - rr * Math.cos(th), MARK.cy + rr * Math.sin(th)))
  }

  // Right leg, bottom -> top. Outward normal is +x.
  for (let i = 1; i <= LEG_SAMPLES; i++) {
    const u = 1 - i / LEG_SAMPLES
    const y = top + u * legLen
    const dx = displacement * Math.sin(mode * Math.PI * u + phase) * hann(u)
    pts.push(pt(MARK.cx + r + dx, y))
  }

  return `M ${pts.join(' L ')}`
}

/** The exact static mark, one path per tine (first paint / SSR / no audio). */
export const STATIC_TINE_PATHS: readonly string[] = Array.from(
  { length: TINE_COUNT },
  (_, k) => tinePathD(k, 0, 0),
)
```

- [ ] **Step 4: Run to verify pass**
  Run: `npx vitest run src/test/voiceGeometry.test.ts`
  Expected: 6 tests pass.

- [ ] **Step 5: Commit**
```bash
git add packages/design-system/src/voice/geometry.ts packages/design-system/src/test/voiceGeometry.test.ts
git commit -m "feat(design-system): per-tine parametric mark geometry with windowed deformation"
```

---

### Task F2 [FABLE]: Spring physics core — `src/voice/springs.ts`

**Files:**
- Create: `packages/design-system/src/voice/springs.ts`
- Test: `packages/design-system/src/test/voiceSprings.test.ts`

Spec §3.3: 2nd-order damped spring per tine (k=140, c=18.5, m=1), semi-implicit Euler, fixed 8ms substep, render interpolation between the two latest physics states.

- [ ] **Step 1: Write the failing tests** — `src/test/voiceSprings.test.ts`:

```ts
// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { describe, it, expect } from 'vitest'
import { ResonatorBank, FIXED_TIMESTEP, SPRING_DEFAULTS } from '../voice/springs'

/** Drive the bank in fixed render steps for `seconds`. */
function drive(bank: ResonatorBank, seconds: number, fps = 60): number {
  const frames = Math.round(seconds * fps)
  let alpha = 0
  for (let i = 0; i < frames; i++) alpha = bank.step(1 / fps)
  return alpha
}

describe('ResonatorBank', () => {
  it('converges to the target energy', () => {
    const bank = new ResonatorBank()
    const target = new Array(10).fill(0).map((_, k) => k / 9)
    bank.setTargets(target)
    drive(bank, 2)
    for (let k = 0; k < 10; k++) {
      expect(bank.interpolated(k, 1)).toBeCloseTo(target[k], 1)
    }
  })

  it('attacks fast and decays without runaway oscillation', () => {
    const bank = new ResonatorBank()
    bank.setTargets(new Array(10).fill(1))
    // closed-form 2nd-order step response at k=140, c=18.5, m=1:
    // zeta = 0.782, omega_n = 11.83 -> y(0.18s) ~= 0.72, y(0.12s) ~= 0.47
    drive(bank, 0.18)
    const v = bank.interpolated(3, 1)
    expect(v).toBeGreaterThan(0.6)
    drive(bank, 2)
    let peak = 0
    const now = bank.interpolated(3, 1)
    bank.setTargets(new Array(10).fill(0))
    // decay: bounded overshoot below zero, settles
    for (let i = 0; i < 120; i++) {
      bank.step(1 / 60)
      peak = Math.min(peak, bank.interpolated(3, 1))
    }
    expect(peak).toBeGreaterThan(-0.35 * 1) // undershoot bounded
    drive(bank, 2)
    expect(Math.abs(bank.interpolated(3, 1))).toBeLessThan(0.01)
    expect(now).toBeGreaterThan(0.9)
  })

  it('is stable at 30fps (N150 frame dips)', () => {
    const bank = new ResonatorBank()
    bank.setTargets(new Array(10).fill(1))
    drive(bank, 3, 30)
    for (let k = 0; k < 10; k++) {
      const v = bank.interpolated(k, 1)
      expect(Number.isFinite(v)).toBe(true)
      expect(v).toBeGreaterThan(0.9)
      expect(v).toBeLessThan(1.21)
    }
  })

  it('does not spiral after a long stall (accumulator clamp)', () => {
    const bank = new ResonatorBank()
    bank.setTargets(new Array(10).fill(1))
    bank.step(30) // a 30-second hitch (e.g. backgrounded tab restore)
    drive(bank, 2)
    expect(bank.interpolated(0, 1)).toBeLessThan(1.21)
  })

  it('advances per-tine phase drift at its own rate', () => {
    const bank = new ResonatorBank()
    bank.step(FIXED_TIMESTEP * 4)
    expect(bank.phases[0]).toBeCloseTo(1.4 * FIXED_TIMESTEP * 4, 6)
    expect(bank.phases[9]).toBeCloseTo(0.45 * FIXED_TIMESTEP * 4, 6)
  })

  it('clamps targets into [0, 1]', () => {
    const bank = new ResonatorBank()
    bank.setTargets([5, -3, Number.NaN, 0.5, 0, 0, 0, 0, 0, 0])
    drive(bank, 2)
    expect(bank.interpolated(0, 1)).toBeCloseTo(1, 1)
    expect(bank.interpolated(1, 1)).toBeCloseTo(0, 1)
    expect(bank.interpolated(3, 1)).toBeCloseTo(0.5, 1)
  })

  it('exposes the documented spring constants', () => {
    expect(SPRING_DEFAULTS).toEqual({ stiffness: 140, damping: 18.5, mass: 1 })
    expect(FIXED_TIMESTEP).toBe(0.008)
  })
})
```

- [ ] **Step 2: Run to verify failure** — `npx vitest run src/test/voiceSprings.test.ts` → module not found.

- [ ] **Step 3: Implement** — `src/voice/springs.ts` (complete):

```ts
// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * Spring-physics core for the audio-reactive Halbert mark (spec §3.3).
 *
 * One critically-damped-ish 2nd-order spring per tine converts raw spectral
 * energy targets into organic motion: fast attack on transient phonemes,
 * smooth decay, no square-wave strobing. Integration is semi-implicit
 * (symplectic) Euler at a fixed 8ms substep, accumulator-driven from the
 * variable requestAnimationFrame delta, so behavior is identical at 60fps
 * and at the 30fps the N150 kiosk may dip to. omega = sqrt(k/m) ~ 11.8,
 * omega * dt = 0.094 — deep inside the stability region.
 */

import { TINE_COUNT, TINE_DRIFT } from './geometry'

export const SPRING_DEFAULTS = Object.freeze({ stiffness: 140, damping: 18.5, mass: 1 })
export const FIXED_TIMESTEP = 0.008

/** Never integrate more than this per step call — breaks the death spiral
 * after a backgrounded tab or a long GC pause. */
const MAX_ACCUMULATED = 0.25

function clamp01(v: number): number {
  if (Number.isNaN(v)) return 0
  return Math.min(1, Math.max(0, v))
}

export class ResonatorBank {
  private readonly currents = new Float64Array(TINE_COUNT)
  private readonly previous = new Float64Array(TINE_COUNT)
  private readonly velocities = new Float64Array(TINE_COUNT)
  private readonly targets = new Float64Array(TINE_COUNT)
  /** Continuous phase drift per tine, phi_k(t) = integral of omega_k. */
  readonly phases = new Float64Array(TINE_COUNT)
  private accumulator = 0

  constructor(
    private readonly stiffness = SPRING_DEFAULTS.stiffness,
    private readonly damping = SPRING_DEFAULTS.damping,
    private readonly mass = SPRING_DEFAULTS.mass,
  ) {}

  /** Set raw spectral energy targets (values are clamped to [0, 1]). */
  setTargets(energies: ArrayLike<number>): void {
    for (let k = 0; k < TINE_COUNT; k++) {
      this.targets[k] = clamp01(energies[k] ?? 0)
    }
  }

  /**
   * Advance physics by a render delta (seconds).
   * @returns render-interpolation alpha in [0, 1] for interpolated()
   */
  step(dtSeconds: number): number {
    this.accumulator = Math.min(this.accumulator + Math.max(0, dtSeconds), MAX_ACCUMULATED)
    const h = FIXED_TIMESTEP
    while (this.accumulator >= h) {
      for (let k = 0; k < TINE_COUNT; k++) {
        this.previous[k] = this.currents[k]
        const a =
          (this.stiffness * (this.targets[k] - this.currents[k]) -
            this.damping * this.velocities[k]) /
          this.mass
        this.velocities[k] += a * h
        this.currents[k] += this.velocities[k] * h
        this.phases[k] += TINE_DRIFT[k] * h
      }
      this.accumulator -= h
    }
    return clamp01(this.accumulator / h)
  }

  /** Spring value for tine k, interpolated for smooth rendering. */
  interpolated(k: number, alpha: number): number {
    return this.previous[k] + (this.currents[k] - this.previous[k]) * alpha
  }
}
```

- [ ] **Step 4: Run to verify pass** — `npx vitest run src/test/voiceSprings.test.ts` → 7 pass.

- [ ] **Step 5: Commit**
```bash
git add packages/design-system/src/voice/springs.ts packages/design-system/src/test/voiceSprings.test.ts
git commit -m "feat(design-system): fixed-timestep resonator spring bank for voice mark"
```

---

### Task F3 [FABLE]: Spectrum mapping & energy sources — `src/voice/spectrum.ts`

**Files:**
- Create: `packages/design-system/src/voice/spectrum.ts`
- Test: `packages/design-system/src/test/voiceSpectrum.test.ts`

Spec §3.4 + Decision 3. `AudioEnergySource` is the only type the component knows; Web Audio types never appear in component props.

- [ ] **Step 1: Write the failing tests** — `src/test/voiceSpectrum.test.ts`:

```ts
// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { describe, it, expect } from 'vitest'
import {
  TINE_BIN_RANGES_16K_64,
  SUB_BASS_ATTENUATION,
  binRangesFor,
  tineEnergies,
  SyntheticEnergySource,
  IdleBreathingSource,
  createAnalyserEnergySource,
} from '../voice/spectrum'

describe('FFT bin mapping', () => {
  it('reproduces the spec table exactly at 16kHz / 64 bins', () => {
    expect(binRangesFor(16000, 64)).toEqual(TINE_BIN_RANGES_16K_64)
  })

  it('rescales for a 48kHz context', () => {
    const ranges = binRangesFor(48000, 192) // 125 Hz per bin — same Hz bands
    expect(ranges).toEqual(TINE_BIN_RANGES_16K_64) // -> same bin indices
    const coarse = binRangesFor(48000, 64) // 375 Hz per bin
    expect(coarse[0]).toEqual([11, 21]) // 4000/375=10.7->11, 8000/375=21.3->21
    expect(coarse[9]).toEqual([0, 1]) // 40..100 Hz clamps to 1 bin
  })

  it('normalizes mean band energy to [0, 1] with sub-bass attenuation', () => {
    const full = new Uint8Array(64).fill(255)
    const out = tineEnergies(full)
    expect(out[0]).toBeCloseTo(1, 5)
    expect(out[8]).toBeCloseTo(1, 5)
    expect(out[9]).toBeCloseTo(SUB_BASS_ATTENUATION, 5)
    const silent = tineEnergies(new Uint8Array(64))
    expect(Array.from(silent)).toEqual(new Array(10).fill(0))
  })
})

describe('energy sources', () => {
  it('SyntheticEnergySource replays a script deterministically', () => {
    const src = new SyntheticEnergySource((t, out) => {
      out[5] = t
    })
    const out = new Float32Array(10)
    src.readEnergies(out, 0.25)
    expect(out[5]).toBeCloseTo(0.25, 5)
    expect(out[0]).toBe(0)
  })

  it('IdleBreathingSource stays in the breathing envelope', () => {
    const src = new IdleBreathingSource()
    const out = new Float32Array(10)
    for (const t of [0, 0.7, 1.4, 2.1, 2.8, 3.5, 100]) {
      src.readEnergies(out, t)
      for (const v of out) {
        expect(v).toBeGreaterThanOrEqual(0)
        expect(v).toBeLessThanOrEqual(0.12)
      }
    }
  })

  it('createAnalyserEnergySource maps byte spectra through computed ranges', () => {
    // structural mock: 64 bins at 48kHz -> 375 Hz/bin; brilliance band is
    // bins [11, 21) — fill all of them so the mean hits 1.0
    const bins = new Uint8Array(64)
    bins.fill(255, 11, 21)
    const fakeAnalyser = {
      frequencyBinCount: 64,
      getByteFrequencyData(out: Uint8Array) {
        out.set(bins)
      },
    }
    const src = createAnalyserEnergySource(fakeAnalyser, 48000)
    const out = new Float32Array(10)
    expect(src.readEnergies(out, 0)).toBe(10)
    expect(out[0]).toBeCloseTo(1, 5) // brilliance ring lights up
    expect(out[4]).toBeCloseTo(0, 5) // vocal core stays dark
  })
})
```

- [ ] **Step 2: Run to verify failure** — `npx vitest run src/test/voiceSpectrum.test.ts` → module not found.

- [ ] **Step 3: Implement** — `src/voice/spectrum.ts` (complete):

```ts
// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * FFT bin -> tine energy mapping and the AudioEnergySource abstraction.
 *
 * Spec §3.4 groups linear FFT bins into the 10 vocal registers of §2.2.
 * Browser AudioContexts typically run at 44.1/48kHz regardless of the 16kHz
 * capture rate, so bin edges are COMPUTED from the context sample rate and
 * bin count (spec formula: nearest bin center to each band edge). At the
 * reference 16kHz/64-bin configuration this reproduces the spec table
 * bit-for-bit (test-enforced).
 *
 * The AudioReactiveHalbertMark component only knows AudioEnergySource —
 * Web Audio types never appear in its props (SSR/Storybook-safe).
 */

import { TINE_COUNT } from './geometry'

/** Vocal register band edges in Hz, inner (tine 0) to outer (tine 9). */
export const TINE_BAND_HZ: ReadonlyArray<readonly [number, number]> = [
  [4000, 8000], // brilliance / air
  [2500, 4000], // sibilance
  [1500, 2500], // upper mids
  [1000, 1500], // vowel clarity
  [700, 1000],  // vocal core
  [500, 700],   // vowel body
  [350, 500],   // warmth
  [200, 350],   // chest formant
  [100, 200],   // vocal fundamental
  [40, 100],    // sub-bass / room
]

/** The spec §3.4 reference table (16kHz sample rate, 64 FFT bins). */
export const TINE_BIN_RANGES_16K_64: ReadonlyArray<readonly [number, number]> = [
  [32, 64], [20, 32], [12, 20], [8, 12], [6, 8],
  [4, 6], [3, 4], [2, 3], [1, 2], [0, 1],
]

/** Bins 0-1 are mostly DC and room rumble; keep the outer arc calm (§3.4). */
export const SUB_BASS_ATTENUATION = 0.3

/**
 * Bin ranges (inclusive lower, exclusive upper) for a given context rate and
 * bin count. Band edges are rounded to the nearest bin — the center-frequency
 * argmin rule from spec §3.4.
 */
export function binRangesFor(
  sampleRate: number,
  binCount: number,
): Array<[number, number]> {
  const hzPerBin = sampleRate / 2 / binCount
  return TINE_BAND_HZ.map(([lo, hi]) => {
    const a = Math.min(binCount - 1, Math.max(0, Math.round(lo / hzPerBin)))
    const b = Math.min(binCount, Math.max(a + 1, Math.round(hi / hzPerBin)))
    return [a, b] as [number, number]
  })
}

/** Mean-normalized per-tine energies for one byte-frequency frame. */
export function tineEnergies(
  freqData: Uint8Array,
  ranges: ReadonlyArray<readonly [number, number]> = TINE_BIN_RANGES_16K_64,
  out: Float32Array = new Float32Array(TINE_COUNT),
): Float32Array {
  for (let k = 0; k < TINE_COUNT; k++) {
    const [lo, hi] = ranges[k]
    let sum = 0
    for (let j = lo; j < hi && j < freqData.length; j++) sum += freqData[j]
    let e = hi > lo ? sum / (hi - lo) / 255 : 0
    if (k === TINE_COUNT - 1) e *= SUB_BASS_ATTENUATION
    out[k] = e
  }
  return out
}

/** What the mark consumes each frame. Implementations own their resources. */
export interface AudioEnergySource {
  /** Allocate resources. May reject; the component logs and renders static. */
  start(): void | Promise<void>
  /** Release resources. Idempotent. */
  stop(): void
  /** Fill `out` with per-tine energies in [0, 1]; returns tine count. */
  readEnergies(out: Float32Array, tSeconds: number): number
}

/** Scripted energies for tests and Storybook (no audio hardware needed). */
export class SyntheticEnergySource implements AudioEnergySource {
  constructor(
    private readonly script: (t: number, out: Float32Array) => void,
  ) {}
  start(): void {}
  stop(): void {}
  readEnergies(out: Float32Array, tSeconds: number): number {
    out.fill(0)
    this.script(tSeconds, out)
    return TINE_COUNT
  }
}

/** Slow 3.5s breathing for idle/standby (spec §4.1 state 1). */
export class IdleBreathingSource implements AudioEnergySource {
  start(): void {}
  stop(): void {}
  readEnergies(out: Float32Array, tSeconds: number): number {
    const w = (2 * Math.PI * tSeconds) / 3.5
    for (let k = 0; k < TINE_COUNT; k++) {
      out[k] = Math.max(0, 0.05 + 0.045 * Math.sin(w + k * 0.55))
    }
    return TINE_COUNT
  }
}

/** Minimal structural view of an AnalyserNode (no DOM type leak, mockable). */
export interface ByteFrequencyNode {
  readonly frequencyBinCount: number
  getByteFrequencyData(out: Uint8Array): void
}

/** Adapt any analyser (real or mock) into an energy source. */
export function createAnalyserEnergySource(
  analyser: ByteFrequencyNode,
  sampleRate: number,
): AudioEnergySource {
  const binCount = analyser.frequencyBinCount
  const ranges = binRangesFor(sampleRate, binCount)
  const bytes = new Uint8Array(binCount)
  return {
    start() {},
    stop() {},
    readEnergies(out: Float32Array): number {
      analyser.getByteFrequencyData(bytes)
      tineEnergies(bytes, ranges, out)
      return TINE_COUNT
    },
  }
}

export interface MediaStreamAnalyserOptions {
  /** fftSize 128 -> 64 bins (128-sample frames are plenty for 10 bands). */
  fftSize?: number
  minDecibels?: number // default -85 (voice floor)
  maxDecibels?: number // default -25
}

/**
 * Browser glue: build an analyser source from a getUserMedia stream.
 * The AudioContext is created lazily in start() — call sites must invoke it
 * from a user gesture (browsers block audio startup otherwise).
 */
export function createMediaStreamAnalyserSource(
  stream: MediaStream,
  opts: MediaStreamAnalyserOptions = {},
): AudioEnergySource {
  let context: AudioContext | null = null
  let inner: AudioEnergySource | null = null
  return {
    start() {
      if (typeof window === 'undefined') return
      context = new AudioContext()
      const source = context.createMediaStreamSource(stream)
      const analyser = context.createAnalyser()
      analyser.fftSize = opts.fftSize ?? 128
      analyser.smoothingTimeConstant = 0 // the spring bank smooths instead
      analyser.minDecibels = opts.minDecibels ?? -85
      analyser.maxDecibels = opts.maxDecibels ?? -25
      source.connect(analyser) // analyser is a terminal node — no audible tap
      inner = createAnalyserEnergySource(analyser, context.sampleRate)
    },
    stop() {
      inner = null
      void context?.close()
      context = null
    },
    readEnergies(out: Float32Array, t: number): number {
      return inner ? inner.readEnergies(out, t) : 0
    },
  }
}

/** Same glue for an existing node (e.g. the Phase-2 TTS playback tap). */
export function createNodeAnalyserSource(
  node: AudioNode,
  opts: MediaStreamAnalyserOptions = {},
): AudioEnergySource {
  let inner: AudioEnergySource | null = null
  return {
    start() {
      const analyser = node.context.createAnalyser()
      analyser.fftSize = opts.fftSize ?? 128
      analyser.smoothingTimeConstant = 0
      analyser.minDecibels = opts.minDecibels ?? -85
      analyser.maxDecibels = opts.maxDecibels ?? -25
      node.connect(analyser)
      inner = createAnalyserEnergySource(analyser, node.context.sampleRate)
    },
    stop() {
      inner = null
    },
    readEnergies(out: Float32Array, t: number): number {
      return inner ? inner.readEnergies(out, t) : 0
    },
  }
}
```

- [ ] **Step 4: Run to verify pass** — `npx vitest run src/test/voiceSpectrum.test.ts` → 7 pass.

- [ ] **Step 5: Commit**
```bash
git add packages/design-system/src/voice/spectrum.ts packages/design-system/src/test/voiceSpectrum.test.ts
git commit -m "feat(design-system): FFT bin mapping and audio energy sources for voice mark"
```

---

### Task F4 [FABLE]: The component — `src/voice/AudioReactiveHalbertMark.tsx`

**Files:**
- Create: `packages/design-system/src/voice/AudioReactiveHalbertMark.tsx`, `src/voice/index.ts`
- Modify: `packages/design-system/src/index.ts` (exports)
- Test: `packages/design-system/src/test/audioReactiveMark.test.tsx`

Decisions 2 & 5: 10 `<path>` refs mutated directly; static first paint; `idle` uses `IdleBreathingSource` when no source is provided; `thinking` adds a slow inward contraction spring on the group; `error` re-tints the stroke to `--color-status-error`.

- [ ] **Step 1: Write the failing tests** — `src/test/audioReactiveMark.test.tsx`:

```tsx
// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render } from '@testing-library/react'

import { AudioReactiveHalbertMark } from '../voice/AudioReactiveHalbertMark'
import { STATIC_TINE_PATHS } from '../voice/geometry'
import type { AudioEnergySource } from '../voice/spectrum'

/** Controllable rAF: callbacks queue; pumpTimes drives frames by hand. */
let pending: Array<[number, FrameRequestCallback]> = []
let rafId = 0
let clock = 0

function installFakeRaf() {
  pending = []
  vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => {
    rafId += 1
    pending.push([rafId, cb])
    return rafId
  })
  vi.stubGlobal('cancelAnimationFrame', (id: number) => {
    pending = pending.filter(([pid]) => pid !== id)
  })
}

function pump(frames: number, dtMs = 16.7) {
  for (let i = 0; i < frames; i++) {
    const q = pending
    pending = []
    clock += dtMs
    for (const [, cb] of q) cb(clock)
  }
}

function constSource(v: number): AudioEnergySource {
  return {
    start: vi.fn(),
    stop: vi.fn(),
    readEnergies(out) {
      out.fill(v)
      return 10
    },
  }
}

describe('AudioReactiveHalbertMark', () => {
  beforeEach(installFakeRaf)
  afterEach(() => vi.unstubAllGlobals())

  it('renders 10 tine paths with the exact static geometry on first paint', () => {
    const { container } = render(<AudioReactiveHalbertMark size={512} />)
    const paths = container.querySelectorAll('path')
    expect(paths).toHaveLength(10)
    paths.forEach((p, k) => expect(p.getAttribute('d')).toBe(STATIC_TINE_PATHS[k]))
    expect(container.querySelector('svg')).toHaveAttribute('viewBox', '0 0 1024 1024')
  })

  it('animates d attributes from the energy source without re-rendering React', () => {
    const { container } = render(
      <AudioReactiveHalbertMark size={512} source={constSource(1)} />,
    )
    const paths = container.querySelectorAll('path')
    pump(120) // ~2s of frames: springs approach full energy
    const d4 = paths[4].getAttribute('d')!
    expect(d4).not.toBe(STATIC_TINE_PATHS[4])
    // junction pinning holds under animation: first/last points unchanged
    expect(d4.startsWith(STATIC_TINE_PATHS[4].split(' L ')[0])).toBe(true)
    expect(d4.endsWith(STATIC_TINE_PATHS[4].split(' L ').pop()!)).toBe(true)
  })

  it('starts and stops the source with mount lifecycle', () => {
    const src = constSource(0.5)
    const { unmount } = render(<AudioReactiveHalbertMark source={src} />)
    expect(src.start).toHaveBeenCalledTimes(1)
    pump(2)
    unmount()
    expect(src.stop).toHaveBeenCalledTimes(1)
    pump(5) // no callbacks survive unmount — nothing to assert but absence of throw
  })

  it('falls back to idle breathing when no source is given', () => {
    const { container } = render(<AudioReactiveHalbertMark />)
    const paths = container.querySelectorAll('path')
    pump(90)
    expect(paths[2].getAttribute('d')).not.toBe(STATIC_TINE_PATHS[2])
  })

  it('applies state classes and the error tint', () => {
    const { container, rerender } = render(<AudioReactiveHalbertMark state="listening" />)
    expect(container.querySelector('svg')).toHaveClass('hb-reactive-mark--listening')
    rerender(<AudioReactiveHalbertMark state="error" />)
    expect(container.querySelector('svg')).toHaveClass('hb-reactive-mark--error')
    expect(container.querySelector('g')!.getAttribute('stroke')).toContain(
      '--color-status-error',
    )
  })
})
```

- [ ] **Step 2: Run to verify failure** — `npx vitest run src/test/audioReactiveMark.test.tsx` → module not found.

- [ ] **Step 3: Implement** — `src/voice/AudioReactiveHalbertMark.tsx` (complete):

```tsx
// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import * as React from 'react'
import { cx } from '../lib'
import { STATIC_TINE_PATHS, TINE_AMPLITUDES, TINE_COUNT, tinePathD } from './geometry'
import { ResonatorBank } from './springs'
import type { AudioEnergySource } from './spectrum'
import { IdleBreathingSource } from './spectrum'
import type { HalbertMarkTone } from '../primitives/HalbertMark'

/** Voice Mode visual states (spec §4.1), aligned with AudioState in
 * halbert_core/.../components/audio/AcousticAuraIndicator.tsx. */
export type VoiceVisualState =
  | 'idle'
  | 'listening'
  | 'recognized'
  | 'thinking'
  | 'speaking'
  | 'error'

export interface AudioReactiveHalbertMarkProps
  extends Omit<React.SVGAttributes<SVGSVGElement>, 'children'> {
  /** Rendered size (px or CSS unit). Voice Mode uses 512. @default 512 */
  size?: number | string
  /** Color tone; same resolution as HalbertMark. @default 'accent' */
  tone?: HalbertMarkTone
  /** Custom stroke override (wins over tone). */
  color?: string
  /** Current voice state. 'idle' breathes when no source is attached. */
  state?: VoiceVisualState
  /** Live audio energy source (mic for listening, TTS playback for
   * speaking). null/undefined -> synthesized idle breathing. */
  source?: AudioEnergySource | null
  /** Energy gain multiplier. @default 1 */
  sensitivity?: number
}

const STROKE_BY_TONE: Record<Exclude<HalbertMarkTone, 'badge'>, string> = {
  accent: 'var(--color-accent, #D34E24)',
  ink: 'var(--color-ink, #1A1918)',
  canvas: 'var(--color-canvas, #F7F5F0)',
  current: 'currentColor',
}
const ERROR_STROKE = 'var(--color-status-error, #C83E2D)'
const DISPLAY_STROKE_WIDTH = 26.67

export const AudioReactiveHalbertMark = React.forwardRef<
  SVGSVGElement,
  AudioReactiveHalbertMarkProps
>(function AudioReactiveHalbertMark(
  { size = 512, tone = 'accent', color, state = 'idle', source = null, sensitivity = 1, className, style, ...props },
  ref,
) {
  const pathRefs = React.useRef<Array<SVGPathElement | null>>([])
  const groupRef = React.useRef<SVGGElement | null>(null)

  React.useEffect(() => {
    const active: AudioEnergySource = source ?? new IdleBreathingSource()
    try {
      const started = active.start()
      if (started && typeof (started as Promise<void>).catch === 'function') {
        ;(started as Promise<void>).catch((err) =>
          console.warn('[voice-mark] energy source failed to start', err),
        )
      }
    } catch (err) {
      console.warn('[voice-mark] energy source failed to start', err)
    }

    const bank = new ResonatorBank()
    const energies = new Float32Array(TINE_COUNT)
    let contract = 0 // 0 = full size, 1 = thinking contraction
    let contractV = 0
    let last = performance.now()
    let raf = 0

    const frame = (nowMs: number) => {
      raf = requestAnimationFrame(frame)
      const dt = Math.min(0.1, Math.max(0, (nowMs - last) / 1000))
      last = nowMs
      const t = nowMs / 1000

      active.readEnergies(energies, t)
      bank.setTargets(energies)
      const alpha = bank.step(dt)

      // Thinking contraction (spec §4.1 state 4): gentle spring scale 1 -> 0.94
      const contractTarget = state === 'thinking' ? 1 : 0
      const ca = 60 * (contractTarget - contract) - 14 * contractV
      contractV += ca * dt
      contract += contractV * dt

      for (let k = 0; k < TINE_COUNT; k++) {
        const el = pathRefs.current[k]
        if (!el) continue
        const displacement =
          TINE_AMPLITUDES[k] * sensitivity * bank.interpolated(k, alpha)
        el.setAttribute('d', tinePathD(k, displacement, bank.phases[k]))
      }
      const g = groupRef.current
      if (g) {
        const s = 1 - 0.06 * contract
        g.setAttribute(
          'transform',
          `translate(${512 * (1 - s)} ${512 * (1 - s)}) scale(${s})`,
        )
      }
    }
    raf = requestAnimationFrame(frame)

    return () => {
      cancelAnimationFrame(raf)
      try {
        active.stop()
      } catch {
        /* stop is best-effort */
      }
    }
  }, [source, state, sensitivity])

  const stroke = state === 'error' ? ERROR_STROKE : (color ?? STROKE_BY_TONE[tone === 'badge' ? 'accent' : tone])

  return (
    <svg
      ref={ref}
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 1024 1024"
      width={size}
      height={size}
      className={cx('hb-reactive-mark', `hb-reactive-mark--${state}`, className)}
      style={{ display: 'inline-block', verticalAlign: 'middle', flexShrink: 0, ...style }}
      aria-hidden="true"
      {...props}
    >
      <g
        ref={groupRef}
        fill="none"
        stroke={stroke}
        strokeWidth={DISPLAY_STROKE_WIDTH}
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        {STATIC_TINE_PATHS.map((d, k) => (
          <path
            key={k}
            d={d}
            ref={(el) => {
              pathRefs.current[k] = el
            }}
          />
        ))}
      </g>
    </svg>
  )
})
```

And `src/voice/index.ts` (complete):

```ts
// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
export { AudioReactiveHalbertMark } from './AudioReactiveHalbertMark'
export type {
  AudioReactiveHalbertMarkProps,
  VoiceVisualState,
} from './AudioReactiveHalbertMark'
export type { AudioEnergySource, ByteFrequencyNode, MediaStreamAnalyserOptions } from './spectrum'
export {
  SyntheticEnergySource,
  IdleBreathingSource,
  createAnalyserEnergySource,
  createMediaStreamAnalyserSource,
  createNodeAnalyserSource,
  tineEnergies,
  binRangesFor,
  TINE_BAND_HZ,
  TINE_BIN_RANGES_16K_64,
  SUB_BASS_ATTENUATION,
} from './spectrum'
export { ResonatorBank, SPRING_DEFAULTS, FIXED_TIMESTEP } from './springs'
export {
  MARK,
  TINE_COUNT,
  TINE_AMPLITUDES,
  TINE_MODES,
  TINE_DRIFT,
  laneRadius,
  laneTop,
  tinePathD,
  STATIC_TINE_PATHS,
} from './geometry'
```

Export from the package root — append to `src/index.ts` after the HalbertMark export block (line ~20):

```ts
// Voice Mode
export * from './voice'
```

(Verify no name collisions: `MARK`, `tinePathD` etc. are not exported elsewhere in the package — confirmed by inspection of `src/index.ts`.)

- [ ] **Step 4: Run tests + typecheck**
  - `npx vitest run src/test/audioReactiveMark.test.tsx` → 5 pass
  - `npm run test` → 29 baseline + 24 new = 53 pass
  - `npm run typecheck` → clean

- [ ] **Step 5: Commit**
```bash
git add packages/design-system/src/voice/ packages/design-system/src/index.ts packages/design-system/src/test/audioReactiveMark.test.tsx
git commit -m "feat(design-system): AudioReactiveHalbertMark component with rAF/physics loop"
```

---

### Task F5 [FABLE]: Storybook stories — synthetic tones, no microphone required

**Files:**
- Create: `packages/design-system/src/stories/AudioReactiveHalbertMark.stories.tsx`

Spec §8 Phase 1: stories must exercise the engine without a mic. `SyntheticEnergySource` drives scripted formant sweeps; a button-driven `getUserMedia` story proves the real path (user gesture initializes the AudioContext); an oscillator story feeds pure tones through a silent gain to the analyser — a 220Hz tone lights rings 4–8, a 4kHz tone lights ring 0–1 only.

Complete file:

```tsx
// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import * as React from 'react'
import type { Meta, StoryObj } from '@storybook/react'
import { AudioReactiveHalbertMark } from '../voice/AudioReactiveHalbertMark'
import {
  SyntheticEnergySource,
  createMediaStreamAnalyserSource,
  createNodeAnalyserSource,
} from '../voice/spectrum'
import type { AudioEnergySource } from '../voice/spectrum'

const meta: Meta<typeof AudioReactiveHalbertMark> = {
  title: 'Voice/AudioReactiveHalbertMark',
  component: AudioReactiveHalbertMark,
  parameters: { layout: 'centered', backgrounds: { default: 'dark' } },
}
export default meta
type Story = StoryObj<typeof AudioReactiveHalbertMark>

/** Vowel-ish formant sweep: energy walks from chest (outer) to air (inner). */
const formantSweep = new SyntheticEnergySource((t, out) => {
  for (let k = 0; k < 10; k++) {
    const center = 4.5 + 4 * Math.sin(t * 0.9)
    out[k] = Math.exp(-((k - center) ** 2) / 3) * (0.55 + 0.45 * Math.sin(t * 6 + k))
  }
})

export const IdleBreathing: Story = { args: { size: 512, state: 'idle' } }

export const Listening: Story = {
  args: { size: 512, state: 'listening', source: formantSweep },
}

export const Speaking: Story = {
  args: { size: 512, state: 'speaking', source: formantSweep, sensitivity: 1.2 },
}

export const Thinking: Story = { args: { size: 512, state: 'thinking' } }
export const ErrorState: Story = { args: { size: 512, state: 'error' } }
export const OnDarkCanvas: Story = {
  args: { size: 512, state: 'listening', source: formantSweep },
  decorators: [
    (StoryFn) => (
      <div style={{ background: '#000', padding: 48 }}>
        <StoryFn />
      </div>
    ),
  ],
}

/** Live microphone (user gesture starts the AudioContext). */
export const LiveMicrophone: Story = {
  render: () => {
    const [source, setSource] = React.useState<AudioEnergySource | null>(null)
    const [error, setError] = React.useState<string | null>(null)
    return (
      <div style={{ display: 'grid', gap: 16, justifyItems: 'center' }}>
        <AudioReactiveHalbertMark size={512} state="listening" source={source} />
        <button
          onClick={async () => {
            try {
              const stream = await navigator.mediaDevices.getUserMedia({
                audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
              })
              setSource(createMediaStreamAnalyserSource(stream))
            } catch (e) {
              setError(String(e))
            }
          }}
        >
          Enable microphone
        </button>
        {error && <p role="alert">{error}</p>}
      </div>
    )
  },
}

/** Pure test tones through a MUTED gain: 220 Hz lights the outer rings,
 * 4000 Hz lights only the center spine (validates the log-scale mapping). */
export const OscillatorTestTones: Story = {
  render: () => {
    const [freq, setFreq] = React.useState(220)
    const [source, setSource] = React.useState<AudioEnergySource | null>(null)
    const ctxRef = React.useRef<AudioContext | null>(null)
    const oscRef = React.useRef<OscillatorNode | null>(null)
    const start = () => {
      const ctx = new AudioContext()
      const osc = ctx.createOscillator()
      osc.frequency.value = freq
      const gain = ctx.createGain()
      gain.gain.value = 0.15 // audible but quiet in Storybook
      osc.connect(gain)
      gain.connect(ctx.destination)
      osc.start()
      ctxRef.current = ctx
      oscRef.current = osc
      setSource(createNodeAnalyserSource(gain))
    }
    React.useEffect(
      () => () => {
        oscRef.current?.stop()
        void ctxRef.current?.close()
      },
      [],
    )
    return (
      <div style={{ display: 'grid', gap: 16, justifyItems: 'center' }}>
        <AudioReactiveHalbertMark size={512} state="speaking" source={source} />
        <label>
          Tone: {freq} Hz{' '}
          <input
            type="range"
            min={80}
            max={6000}
            value={freq}
            onChange={(e) => {
              const f = Number(e.target.value)
              setFreq(f)
              if (oscRef.current) oscRef.current.frequency.value = f
            }}
          />
        </label>
        <button onClick={start}>Start tone</button>
      </div>
    )
  },
}
```

- [ ] **Step: verify** — `npm run storybook`, open `Voice/AudioReactiveHalbertMark`, confirm: idle breathes, sweep animates, thinking contracts, error tints, live mic reacts.
- [ ] **Step: Commit**
```bash
git add packages/design-system/src/stories/AudioReactiveHalbertMark.stories.tsx
git commit -m "feat(design-system): Storybook stories for the audio-reactive mark (synthetic tones, live mic)"
```

---

## 5. Phase 2 [OPUS, handoff] — Voice Mode Screen & Audio Plumbing

Ordering matters: backend tasks O1–O5 are independent of each other and all precede O7's full behavior, but O6/O7/O8 can develop against the SSE contract alone (subtitle ribbon + state transitions) before TTS audio lands in O3. Every task lists its own test command; the Python suite runs in the repo venv (`arch -arm64` prefix on this machine — see memory note and `.claude/worktrees` wrapper caveat: from a worktree, the editable `halbert_core` install resolves to the MAIN tree unless the meta-path-stripping wrapper is used).

### Task O1 [OPUS]: Live `/api/audio/status`

**Files:** Modify `halbert_core/halbert_core/dashboard/routes/audio.py:112-128`. Test: `halbert_core/tests/test_audio_routes.py` (add).

Replace the hardcoded state with the coordinator's real status, falling back to today's static payload when no coordinator exists (the common case until O2 lands):

```python
from fastapi import Request

@router.get("/status")
async def get_audio_status(request: Request):
    """Audio subsystem status — live when the pipeline coordinator is up."""
    coordinator = getattr(request.app.state, "audio_coordinator", None)
    if coordinator is not None:
        try:
            return coordinator.get_status()
        except Exception as e:
            logger.warning(f"coordinator status failed, using static fallback: {e}")
    cfg = load_config()
    return {
        "enabled": cfg.enabled,
        "available": is_audio_available(),
        "sherpa_onnx_installed": is_audio_available(),
        "state": "idle",
        "engines": {  # unchanged fallback block
            "vad": is_audio_available(),
            "asr": is_audio_available(),
            "tts": is_audio_available() and cfg.tts.enabled,
            "speaker_id": is_audio_available() and cfg.speaker_id.enabled,
            "audio_tagger": is_audio_available() and cfg.acoustic_events.enabled,
        },
    }
```

Tests: (a) no `app.state.audio_coordinator` → payload identical to today (regression lock); (b) a stub coordinator whose `get_status()` returns `{"state": "listening", ...}` is reflected verbatim; (c) a raising coordinator falls back to static. Run: `pytest halbert_core/tests/test_audio_routes.py -k status -v`. Commit: `fix(audio): live pipeline state on /api/audio/status with static fallback`.

### Task O2 [OPUS]: Coordinator bootstrap + WebRtcIngress registration

**Files:** Modify `halbert_core/halbert_core/dashboard/app.py` (startup at :373, shutdown at :738), `halbert_core/halbert_core/dashboard/routes/websocket.py`. Test: `halbert_core/tests/test_audio_stream_ws.py` (add).

1. In the `@app.on_event("startup")` handler (after the existing `ws_manager` creation), bootstrap the pipeline when enabled:

```python
from ..audio.config import load_config as load_audio_config

audio_cfg = load_audio_config()
coordinator = None
if audio_cfg.enabled:
    from ..audio.pipeline import AudioPipelineCoordinator
    from ..audio.ingress.webrtc_ingress import WebRtcIngress
    coordinator = AudioPipelineCoordinator(config=audio_cfg)
    coordinator._ingress_adapters.append(WebRtcIngress(area_id="dashboard_voice"))
    await coordinator.start()
app.state.audio_coordinator = coordinator
```

(Add the matching `await coordinator.stop()` to the shutdown handler. If accessing `_ingress_adapters` feels too private, the cleaner form is an `add_ingress(adapter)` setter on the coordinator — add it in this task with a unit test.)

2. Register the WebSocket in `routes/websocket.py`:

```python
@router.websocket("/api/audio/stream")
async def audio_stream_endpoint(websocket: WebSocket):
    await websocket.accept()
    coordinator = getattr(websocket.app.state, "audio_coordinator", None)
    ingress = None
    if coordinator is not None:
        ingress = next(
            (a for a in coordinator._ingress_adapters if a.source_type == "dashboard"),
            None,
        )
    if ingress is None:
        await websocket.close(code=1013)  # try again later — pipeline disabled
        return
    await ingress.handle_websocket(websocket)
```

Tests: route accepts binary frames and enqueues `AudioChunk`s when the coordinator is present; closes 1013 when absent. Run: `pytest halbert_core/tests/test_audio_stream_ws.py -v`. Commit: `feat(audio): production pipeline bootstrap + /api/audio/stream WebSocket ingress`.

### Task O3 [OPUS]: TTS egress — Piper PCM → browser player

**Files:** Create `halbert_core/halbert_core/dashboard/routes/tts_egress.py` (hub), modify `routes/websocket.py` (route), `agents/state_machine.py` (hook after :2960), create frontend `src/lib/ttsPlayback.ts`. Tests: backend WS pub/sub + a state-machine test with a fake hub; frontend unit test with a stubbed `AudioContext`.

Protocol over `/api/audio/tts?session_id=…`: JSON text frame `{"type":"begin","sample_rate":22050,"format":"s16le"}`, binary PCM frames, JSON `{"type":"end"}` / `{"type":"cancelled"}`. Hub: `class TtsEgressHub { subscribe(session_id, ws); publish(session_id, data: bytes|dict); cancel(session_id) }` on `app.state.tts_egress`.

State machine hook (inside the `should_speak(...)` block after segment emission, only when `app.state.tts_egress` has a subscriber for `self.ctx.session_id`): synthesize each spoken segment with the existing `PiperTTS` instance from the voice backend, `publish` the begin frame, stream chunks, publish end. Barge-in: the existing `BargeInToken` (`pipeline.create_barge_in_token()`) already cancels `PiperTTS.synthesize` between chunks; on cancel publish `{"type":"cancelled"}`.

Frontend `ttsPlayback.ts`:

```ts
export class TtsPlaybackClient {
  private ctx: AudioContext | null = null
  private nextStart = 0
  /** Tap point for the visualizer: const source = createNodeAnalyserSource(client.out) */
  readonly out: GainNode | null = null
  constructor(private readonly url: string) {}
  connect(onDone?: () => void): void { /* WS + begin/end/cancelled handling */ }
  private schedulePcm(bytes: ArrayBuffer, sampleRate: number): void { /* s16le -> Float32 -> AudioBufferSourceNode at max(now, nextStart) */ }
  cancel(): void { /* stop all sources, nextStart = 0 */ }
  close(): void {}
}
```

Voice Mode creates the client on mount with the active session id; the mark's speaking source is `createNodeAnalyserSource(client.out)`. Tests: PCM scheduling math (chunk → correct sample counts, sequential `start` times), cancel empties the queue. Commits: `feat(audio): TTS egress hub + /api/audio/tts WebSocket` / `feat(audio): stream Piper PCM to voice sessions from the state machine` / `feat(frontend): TtsPlaybackClient with visualizer tap`.

### Task O4 [OPUS]: Speaker badge via status payload

**Files:** Modify `audio/pipeline.py` (remember last `VoiceTurnObservation` + add to `get_status()` output as `"speaker": {name, role, confidence}` or `null`), O1's handler inherits it. Modify `AcousticAuraIndicator`'s `AudioStatus` interface + Voice Mode `SpeakerBadge`. Tests: pipeline unit test — after `_process_speech_segment` with a stubbed `SpeakerIdentifier`, `get_status()["speaker"]` carries the match. Commit: `feat(audio): expose last identified speaker on /api/audio/status`.

### Task O5 [OPUS]: Acoustic anomaly → urgent wake chain (3 repairs)

1. `AudioPipelineCoordinator` start (O2) sets `on_acoustic_event`: look up the `AcousticAnomalyDetector` from the findings registry (`detector_runner`) and call `add_event(**evt)` — match the existing field names at `acoustic_anomaly.py:58-96`.
2. `useBeingEvents.ts:26` event union gains `'acoustic'` (the category `DetectorRunner` publishes).
3. Render `AcousticAnomalyModule` for acoustic events: the Timeline summon path (`pages/Dashboard.tsx` / proactive card switch — find the `system_anomaly` render site and add the acoustic branch; `AcousticAnomalyModule` takes `AcousticAnomalyData` verbatim).
4. Voice Mode behavior: an acoustic event with `anomaly_severity >= 2` forces the visual state to wake (full brightness + amber pulse class) even from standby — implement inside `useVoiceModeMachine` as an input event.
Tests: detector→bus→payload unit test; hook reducer test for the wake transition. Commit: `feat(audio): wire CED-tiny anomalies through findings → SSE → timeline and voice wake`.

### Task O6 [OPUS]: `useVoiceModeMachine` — the 7-state reducer

**Files:** Create `frontend/src/hooks/useVoiceModeMachine.ts`. Test: `src/hooks/__tests__/useVoiceModeMachine.test.ts` (the frontend has no co-located hook tests yet; follow `vitest` config in the dashboard frontend).

Pure reducer, no React in the core (consistent with Decision 6):

```ts
export type VoiceModeState = 'standby' | 'listening' | 'recognized' | 'thinking' | 'speaking' | 'interrupted' | 'error'
export type VoiceModeEvent =
  | { type: 'wake' }                                   // tap / push-to-talk / acoustic wake
  | { type: 'vad_end' }                                // manual or WS VAD end-of-speech
  | { type: 'speaker_recognized'; name: string; role: string; confidence: number }
  | { type: 'modality_resolved'; modality: ResponseModality }
  | { type: 'speech_segment'; segment: SpeechSegmentEvent }
  | { type: 'turn_complete' }
  | { type: 'interrupt' }                              // barge-in or mark tap during speaking
  | { type: 'error'; message: string }
  | { type: 'dismiss' }
export function voiceModeReducer(s: VoiceModeState, e: VoiceModeEvent): VoiceModeState // transitions per spec §4 mermaid
```

Mapping to the verified streams (§1.2): `listening` is entered locally on push-to-talk (mic is live before any turn); `thinking` begins when `useAgentStream.isStreaming` goes true after `sendMessage`; `modality_resolved === 'voice' | 'mixed'` + first `speech_segment` → `speaking`; `isStreaming` false → `turn_complete` → `standby` after a 30s inactivity timer. The `AudioState` from `/api/audio/status` (O1) is a secondary, coarser input covering ingress failures (`error`). Tests: full transition matrix from spec §4 including the standby timeout and barge-in reset. Commit: `feat(voice): voice-mode state machine hook driving the reactive mark`.

### Task O7 [OPUS]: `VoiceMode.tsx` screen

**Files:** Create `src/pages/VoiceMode.tsx`, `src/components/voice/SubtitleRibbon.tsx`, `src/components/voice/TouchBar.tsx`, `src/components/voice/SpeakerBadge.tsx`, `src/lib/pcmCapture.ts` (AudioWorklet uplink to `/api/audio/stream`). Tests: component tests with stubbed hooks/sources.

Layout per spec §6.1, dark canvas (`bg-black`, mark `tone="accent"`, tokens for text: `text-[#F7F5F0]` via `--color-canvas`):
- Top bar: `SpeakerBadge` (from O4; hidden until a recognition arrives), area label, mute button.
- Center: `AudioReactiveHalbertMark size={512}` — source switches with machine state: `listening` → mic analyser source (from `pcmCapture`'s stream), `speaking` → `createNodeAnalyserSource(ttsClient.out)`.
- `SubtitleRibbon`: consumes `session.speechSegments` from `useAgentStream` directly (same interface as `VoiceCompanionPill`; the spec's "reference PronunciationLexicon for display" happens server-side already — `apply_pronunciation` runs in `state_machine.py:2931`, so **no frontend lexicon work** — display `speechText`/`displayText` as-is; this corrects doc 15 Phase 2's last bullet).
- `TouchBar`: `[Mic] Tap to Speak` / `[Keyboard]` / `[ArrowUpRight] Host Canvas` per §6.2; center-mark tap handling: speaking → `ttsClient.cancel()` + interrupt event; idle → push-to-talk start; listening → `vad_end`.
- `pcmCapture.ts`: `getUserMedia({ audio: { channelCount: 1, sampleRate: 16000, echoCancellation: true, noiseSuppression: true } })` → `AudioWorklet` (fall back to `ScriptProcessorNode` in WebKitGTK) → 16-bit PCM frames → WS `/api/audio/stream`; exposes the same stream for the analyser source so capture and visualization share one graph.
- Turn submission: when the machine fires `vad_end`, send the accumulated transcript — note the transcript arrives back AS `response_chunk`-style STT events only after O2 is producing observations; for v1 the page sends `sendMessage(text)` where `text` comes from the STT observation channel (O2's coordinator `on_voice_turn` → surface via the status/SSE channel chosen in O4). If STT isn't live yet, the on-screen keyboard (O9) is the input path.

Note on `response_chunk`: doc 15 suggests using it for "live STT transcription display" — **wrong stream**; `response_chunk` is LLM output text. Live STT subtitles come from the STT observation channel (O2/O4), and the *spoken* subtitle ribbon reads `speech_segment`. The plan corrects this.

### Task O8 [OPUS]: Routing & shell integration

**Files:** Modify `src/App.tsx:91-110`, `src/components/Layout.tsx` (add `isVoiceRoute` beside `isSettingsRoute`:185 — full-bleed, no rail, no padded main), `src/contexts/ShellModeContext.tsx` (`ShellMode = 'engaged' | 'browsing' | 'voice'`; entering `/voice` stores the previous mode and sets `voice`; leaving restores). Voice entry points: nav is inappropriate (it's a mode, like settings) — top-bar button beside `ModeSwitch` + deep link. Host-canvas return edge: `navigate('/')` + `setMode('engaged')`. **Conversation continuity**: in-flight turns do NOT survive the switch (state is hook-local in `useAgentStream`); completed turns re-hydrate from `useTimeline`. v1 accepts this (spec §6.2(3) is downgraded to "history preserved"), with a follow-up to lift turn state into a module-level store mirroring `terminalSessionStore`. Tests: reducer + Layout render test asserting no rail on `/voice`. Commit: `feat(shell): /voice route with third shell mode and full-bleed layout`.

### Task O9 [GLM5.2]: On-screen keyboard + quick chips

**Files:** Create `src/components/voice/OnScreenKeyboard.tsx`. Bottom-sheet glide per §6.2(2): mark scales to a 48px header emblem (`HalbertMark size={48}` — medium tier per §1.1, deliberately NOT the reactive component), keyboard input writes into the same `sendMessage` path. Quick-intent chips: `"System Vitals"`, `"Check Storage"`, `"Lock Doors"`, `"Run Health Scan"`. Keyboard rows are plain buttons (no IME) — a real virtual keyboard layout is acceptable; do not pull a dependency. Tests: chip click → `sendMessage` spy. Commit: `feat(voice): touch keyboard overlay with quick-intent chips`.

---

## 6. Phase 3 [OPUS/GLM, handoff] — Appliance Integration

### Task P1 [OPUS]: Standby tier controller (frontend)
`src/components/voice/StandbyController.tsx` implementing spec §5.2 tiers 1–2 in-app: idle timer (30s → ultra-dim breathing at 10% opacity + room clock; 10min → `#000` software blackout, `cursor: none`); any pointer event or machine `wake` restores. Tier 3 hardware dimming is delegated to P2 via `POST` to a new endpoint — the controller only reports idle duration. Quiet-hours remain the engine's job (`should_speak_proactively` already gates proactive speech; the controller reads `quiet_hours` from `/api/audio/config` for display only). Tests: fake-timer transitions. Commit: `feat(voice): multi-tier standby controller`.

### Task P2 [OPUS]: Screen power daemon (backend, greenfield)
Create `halbert_core/halbert_core/system/display_power.py`: backlight control through `/sys/class/backlight/*/brightness` (discover the writable device by reusing `discovery/scanners/laptop.py:341-381`'s scan, then write), DPMS via `xset dpms force off` when X11 is present, graceful no-op elsewhere. Endpoints: `GET/POST /api/system/display` (`{"backlight": 0..100, "blanked": bool}`). Wake-before-speak: the TTS egress hook (O3) calls `display_power.wake()` before publishing `begin` when a voice session is active. Tests: fake sysfs via tmpdir fixtures. Commit: `feat(system): display power daemon with backlight/DPMS control`.

### Task P3 [GLM5.2]: Kiosk packaging (docs + unit file)
`documentation/operations/kiosk-appliance.md` + `scripts/halbert-kiosk.service`: systemd `--user` unit launching `chromium --kiosk --app=http://localhost:<port>/voice --incognito --noerrdialogs --disable-infobars --check-for-update-interval=31536000`, with `xset s off -dpms` preamble (P2 owns DPMS thereafter). Record the WebKitGTK caveat (Tauri-on-Linux ≠ Chromium; Web Audio + AEC materially weaker) from Decision 5. Commit: `docs(operations): N150 kiosk appliance runbook + systemd unit`.

### Task P4 [OPUS]: Tauri window & the orphan `voice-hud`
Decide and implement one: (a) build the missing `voice-hud` frontend route so the existing Rust panel renders `VoiceCompanionPill`-style content (the Rust doc contract), or (b) remove the window + `hud_hotkey.rs` + `audio_capture.rs` and document retirement. Also add `tauri.conf.json` `fullscreen/kiosk` keys for the main window **only if** the appliance will run the Tauri shell (pending real-device AEC verification from P3). Commit: `feat(tauri): voice HUD route` or `chore(tauri): retire unused voice-hud window`.

### Task P5 [GLM5.2]: Hardware validation matrix
Manual checklist: N150 + 10" HDMI capacitive touch — 60fps path deformation (Chrome DevTools FPS meter), wake-from-black latency (<50ms software, <100ms backlight), touch hit-areas ≥ 44px, TTS↔visualizer sync (clap test), 24h soak on standby tiers. Record results in `.handoff/`.

---

## 7. Adjacent Fixes [GLM5.2, handoff]

### Task G1 [GLM5.2]: VoiceCompanionPill segment cycling + tokens
`src/components/audio/VoiceCompanionPill.tsx:23-33`: replace the no-op effect with a real interval that advances `currentIdx` every ~3.5s (bounded at `segments.length-1`), resetting when `isActive`/segments change. Replace raw `orange-500`/`purple-500` classes with token classes (`text-vermilion`, `bg-vermilion/10`, `border-vermilion/30`; whisper badge → status-info tokens) per the canonical palette rule (`shared-tokens/tokens.css`). Test: vi.useFakeTimers advancing through 3 segments. Commit: `fix(audio): cycle speech segments in VoiceCompanionPill; use design tokens`.

### Task G2 [GLM5.2]: SpeakerProfilesCard real Test button
`SpeakerProfilesCard.tsx:70-79`: on Test, capture 2s of mic — reuse `VoiceEnrollmentModal.tsx:48-53`'s `getUserMedia`+`MediaRecorder` pattern — base64 → POST `/api/audio/speakers/{id}/test` (exists at `routes/audio.py:211`); render `{matched, score, threshold}` from the real response; handle 503 (sherpa-onnx missing) with a disabled-state tooltip. Test: fetch mock. Commit: `fix(audio): wire speaker test button to the verification endpoint`.

### Task G3 [GLM5.2]: AudioSettings quiet-hours UI + dead switches
`AudioSettings.tsx`: Privacy card gains quiet-hours enable + start/end time inputs bound to `POST /api/being` (`BeingConfigUpdate.quiet_hours`, `settings.py:3033`); the `delete_raw_audio` and `ignore_tv_babble` switches (currently `onCheckedChange={() => {}}` no-ops at :350-356) get wired to `POST /api/audio/config` fields or removed if the config schema lacks them (check `audio/config.py` first). Commit: `feat(settings): quiet-hours controls and functional privacy switches`.

### Task G4 [GLM5.2]: Spec/errata sweep
Fix `HalbertMark.tsx` JSDoc density thresholds (says ≥96px, code says >64px) and the 39-vs-"40+" lexicon count in doc 15; reconcile the dual quiet-hours sources note (engine hardcoded 22–7 vs `BeingConfig`) by documenting the engine as authoritative for voice and the gate config as the proactive-alert override. Commit: `docs(design): errata from voice-mode verification pass`.

---

## 8. Acceptance & Risk

**Phase 1 acceptance (this session):** ✅ `npm run test` in `packages/design-system` → 53 passing; `npm run typecheck` clean; `build-storybook` builds; Voice stories animate from synthetic sources without a mic; static first-paint markup byte-identical to the standalone mark geometry; energy-source lifecycle starts/stops with mount; all junction-pinning invariants test-enforced.

**Known risks & deferrals:**
1. **WebKitGTK gap** — Tauri on Linux renders WebKitGTK, not Chromium: Web Audio FFT and getUserMedia AEC are weaker there. Voice Mode is verified in Chromium; P4 decides the Tauri appliance story after hardware testing. (Spec diagram says "Kiosk Chromium" — this plan makes that explicit.)
2. **Wake word** — `hey_halbert` model untrained by design; v1 wake is tap/PTT/acoustic-anomaly only.
3. **In-flight conversation continuity** across Voice↔Canvas is lost on unmount (hook-local state); v1 downgrades spec §6.2(3) to persisted history only, with a module-store follow-up.
4. **STT live subtitles** depend on O2+O4; without them the keyboard (O9) is the input path and the ribbon shows spoken output only.
5. **Worktree venv trap** — from this worktree, `halbert_core` editable installs resolve to the main tree; run backend tests via the meta-path-stripping wrapper with `arch -arm64` (see project memory) or the backend tasks will silently test the wrong tree.
6. **Canvas2D fallback** — spec §3.3's optimization hatch stays closed until N150 profiling (P5) shows frame drops; the DOM-free physics core makes it a renderer-only change.

---

> **Design Law (unchanged):** *The mark does not merely display sound; it embodies the voice.*
