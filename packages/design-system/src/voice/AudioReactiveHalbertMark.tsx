// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import * as React from 'react'
import { cx } from '../lib'
import {
  MAX_DISPLACEMENT_MULTIPLIER,
  TINE_AMPLITUDES,
  staticTinePaths,
  tineCount,
  tinePathD,
  type TinePathOptions,
  type TravelingBulge,
  type VoiceDensity,
} from './geometry'
import { ResonatorBank, STRING_LADDER, SWELL_SPRING } from './springs'
import {
  IdlePlucker,
  OnsetPlucker,
  PluckQueue,
  STATE_EXCITATION,
  strum,
  type StateExcitation,
  type VoiceVisualState,
} from './excitation'
import type { AudioEnergySource } from './spectrum'
import { IdleBreathingSource } from './spectrum'
import type { HalbertMarkTone } from '../primitives/HalbertMark'

export type { VoiceVisualState } from './excitation'

export interface AudioReactiveHalbertMarkProps
  extends Omit<React.SVGAttributes<SVGSVGElement>, 'children'> {
  /** Rendered size (px or CSS unit). Voice Mode uses 512. @default 512 */
  size?: number | string
  /**
   * Optical density: 'medium' (6 tines — the Voice Mode default since
   * 2026-08-31 v2 tuning) or 'display' (10 tines).
   * @default 'medium'
   */
  density?: VoiceDensity
  /** Color tone; same resolution as HalbertMark. @default 'accent' */
  tone?: HalbertMarkTone
  /** Custom stroke override (wins over tone). */
  color?: string
  /** Current voice state. 'idle' breathes when no source is attached. */
  state?: VoiceVisualState
  /** Live audio energy source (mic for listening, TTS playback for
   * speaking). null/undefined -> synthesized idle breathing. */
  source?: AudioEnergySource | null
  /**
   * Scales how hard strikes land and how far the lean goes. It is applied
   * to the incoming level, before the string's energy limiter, so a loud
   * strike saturates the string rather than clipping the drawn path.
   * @default 1
   */
  sensitivity?: number
}

const STROKE_BY_TONE: Record<Exclude<HalbertMarkTone, 'badge'>, string> = {
  accent: 'var(--color-accent, #D34E24)',
  ink: 'var(--color-ink, #1A1918)',
  canvas: 'var(--color-canvas, #F7F5F0)',
  current: 'currentColor',
}
const ERROR_STROKE = 'var(--color-status-error, #C83E2D)'
const STROKE_BY_DENSITY: Record<VoiceDensity, number> = { medium: 48, display: 26.67 }

/** The per-state lean weight glides to its target with this time constant,
 * so a state change never pops the lean (speaking 0.3 -> idle 1.0). */
const SWELL_WEIGHT_RAMP_SECONDS = 0.12

interface ActiveBulge {
  tine: number
  start: number
  duration: number
  height: number
  width: number
}

function excitationFor(state: string): StateExcitation {
  return STATE_EXCITATION[state as VoiceVisualState] ?? STATE_EXCITATION.idle
}

/**
 * Everything that must survive a source swap: the strings keep ringing and
 * a pending strum keeps walking when the app hands the mark a new analyser
 * (mic tap -> TTS tap) in the same render as a state change. Rebuilt only
 * when the density changes; the frame loop reads density and amplitudes
 * from here so a frame that lands between a density commit and the effect
 * re-run still draws consistent geometry.
 */
interface Engine {
  density: VoiceDensity
  count: number
  amplitudes: readonly number[]
  ring: ResonatorBank
  swell: ResonatorBank
  onsets: OnsetPlucker
  queue: PluckQueue
  idle: IdlePlucker
  raw: Float32Array
  scaled: Float32Array
  /** The state the engine last acted on. Seeded 'idle' so mounting in any
   * other state counts as entering it (a mount in `recognized` strums). */
  seenState: VoiceVisualState
  /** Current lean weight, ramping toward the state's target. */
  swellWeight: number
  bulges: ActiveBulge[]
  /** Armed on the first thinking frame so it shares the frame clock. */
  nextSpawn: number | null
  bulgesByTine: TravelingBulge[][]
  /** 0 = full size, 1 = thinking contraction; a small spring of its own. */
  contract: number
  contractV: number
}

function createEngine(density: VoiceDensity, initialState: string): Engine {
  const count = tineCount(density)
  return {
    density,
    count,
    amplitudes: TINE_AMPLITUDES[density],
    ring: ResonatorBank.strings(STRING_LADDER[density]),
    swell: ResonatorBank.uniform(count, SWELL_SPRING),
    onsets: new OnsetPlucker(count),
    queue: new PluckQueue(),
    idle: new IdlePlucker(count),
    raw: new Float32Array(count),
    scaled: new Float32Array(count),
    seenState: 'idle',
    swellWeight: excitationFor(initialState).swellWeight,
    bulges: [],
    nextSpawn: null,
    bulgesByTine: Array.from({ length: count }, () => []),
    contract: 0,
    contractV: 0,
  }
}

/**
 * The Halbert mark as a set of plucked strings (design doc 17).
 *
 * Each frame: the energy source supplies a level per tine; rising levels
 * pluck that tine's string (ring), the level itself leans it a little
 * (swell); the sum, clamped to the geometry ceiling, is the tine's
 * displacement. State only changes how the strings are struck — the strings
 * themselves (pitch, sustain) never change, which is what keeps every
 * surface's motion identical.
 */
export const AudioReactiveHalbertMark = React.forwardRef<
  SVGSVGElement,
  AudioReactiveHalbertMarkProps
>(function AudioReactiveHalbertMark(
  {
    size = 512,
    density = 'medium',
    tone = 'accent',
    color,
    state = 'idle',
    source = null,
    sensitivity = 1,
    className,
    style,
    ...props
  },
  ref,
) {
  const pathRefs = React.useRef<Array<SVGPathElement | null>>([])
  const groupRef = React.useRef<SVGGElement | null>(null)
  const stateRef = React.useRef(state)
  stateRef.current = state
  // The mount state only seeds the lean weight; later states are read live.
  const initialStateRef = React.useRef(state)
  const engine = React.useMemo(() => createEngine(density, initialStateRef.current), [density])
  const engineRef = React.useRef(engine)
  engineRef.current = engine
  const staticPaths = React.useMemo(() => staticTinePaths(density), [density])

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

    let last = performance.now()
    let raf = 0

    const frame = (nowMs: number) => {
      raf = requestAnimationFrame(frame)
      const e = engineRef.current
      const dt = Math.min(0.1, Math.max(0, (nowMs - last) / 1000))
      last = nowMs
      const t = nowMs / 1000
      const { count, ring, swell, raw, scaled, amplitudes } = e

      const state = stateRef.current
      if (state !== e.seenState) {
        if (state === 'recognized') strum(e.queue, t, count)
        if (e.seenState === 'idle') e.idle.reset()
        e.seenState = state
      }
      const excitation = excitationFor(state)
      e.swellWeight +=
        (excitation.swellWeight - e.swellWeight) *
        (1 - Math.exp(-dt / SWELL_WEIGHT_RAMP_SECONDS))

      active.readEnergies(raw, t)
      for (let k = 0; k < count; k++) scaled[k] = raw[k] * sensitivity
      e.onsets.feed(scaled, excitation.pluckGain, ring)
      e.queue.flush(t, ring)
      if (state === 'idle') e.idle.tick(t, ring)
      swell.setTargets(scaled)
      const ringAlpha = ring.step(dt)
      const swellAlpha = swell.step(dt)

      // Thinking: spawn traveling bulges on random tines (sequential,
      // 2-3 alive at once); cull them on state exit or journey end.
      if (state === 'thinking') {
        if (e.nextSpawn === null) e.nextSpawn = t + 0.3
        if (t >= e.nextSpawn && e.bulges.length < 3) {
          const busy = new Set(e.bulges.map((b) => b.tine))
          let pick = Math.floor(Math.random() * count)
          if (busy.has(pick)) pick = (pick + 1) % count
          e.bulges.push({
            tine: pick,
            start: t,
            duration: 0.9 + Math.random() * 0.7,
            height: 7 + Math.random() * 4,
            width: 0.07,
          })
          e.nextSpawn = t + 0.45 + Math.random() * 0.75
        }
      } else if (e.bulges.length > 0) {
        e.bulges = []
        e.nextSpawn = null
      }
      e.bulges = e.bulges.filter((b) => (t - b.start) / b.duration <= 1)
      for (const arr of e.bulgesByTine) arr.length = 0
      for (const b of e.bulges) {
        e.bulgesByTine[b.tine].push({
          center: (t - b.start) / b.duration,
          width: b.width,
          height: b.height,
        })
      }

      // Thinking contraction (spec §4.1 state 4): gentle spring scale 1 -> 0.94
      const contractTarget = state === 'thinking' ? 1 : 0
      const ca = 60 * (contractTarget - e.contract) - 14 * e.contractV
      e.contractV += ca * dt
      e.contract += e.contractV * dt

      for (let k = 0; k < count; k++) {
        const el = pathRefs.current[k]
        if (!el) continue
        const opts: TinePathOptions =
          e.bulgesByTine[k].length > 0
            ? { density: e.density, bulges: e.bulgesByTine[k] }
            : { density: e.density }
        const unclamped =
          ring.interpolated(k, ringAlpha) + e.swellWeight * swell.interpolated(k, swellAlpha)
        const m = Math.max(
          -MAX_DISPLACEMENT_MULTIPLIER,
          Math.min(MAX_DISPLACEMENT_MULTIPLIER, unclamped),
        )
        el.setAttribute('d', tinePathD(k, amplitudes[k] * m, opts))
      }
      const g = groupRef.current
      if (g) {
        const s = 1 - 0.06 * e.contract
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
  }, [source, sensitivity, density])

  const stroke =
    state === 'error'
      ? ERROR_STROKE
      : (color ?? STROKE_BY_TONE[tone === 'badge' ? 'accent' : tone])

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
        strokeWidth={STROKE_BY_DENSITY[density]}
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        {staticPaths.map((d, k) => (
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
