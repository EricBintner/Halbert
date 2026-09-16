// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import * as React from 'react'
import { cx } from '../lib'
import {
  DEFAULT_DENSITY,
  MAX_DISPLACEMENT_MULTIPLIER,
  STROKE_WIDTH,
  TINE_AMPLITUDES,
  bulgePolygonPoints,
  staticTinePaths,
  tineCount,
  tineLengths,
  tinePathD,
  type Retraction,
  type TinePathOptions,
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
import { Listener } from './listening'
import type { AudioEnergySource } from './spectrum'
import { IdleBreathingSource } from './spectrum'
import type { HalbertMarkTone } from '../primitives/HalbertMark'

export type { VoiceVisualState } from './excitation'

export interface AudioReactiveHalbertMarkProps
  extends Omit<React.SVGAttributes<SVGSVGElement>, 'children'> {
  /** Rendered size (px or CSS unit). Voice Mode uses 512. @default 512 */
  size?: number | string
  /**
   * Optical density: 'brand' (the ratified 7-line mark, the voice mark
   * everywhere), 'medium' (6 tines) or 'display' (10 tines).
   * @default 'brand'
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

/** The per-state lean weight glides to its target with this time constant,
 * so a state change never pops the lean (speaking 0.3 -> idle 1.0). */
const SWELL_WEIGHT_RAMP_SECONDS = 0.12
/** The retraction weight glides too, so leaving listening lets the ends
 * slide back out rather than snap. */
const RETRACT_WEIGHT_RAMP_SECONDS = 0.25
/** Below this weight the trim is skipped entirely (exact static geometry). */
const RETRACT_EPSILON = 0.001

/**
 * Thinking: "a python that ate a baseball" (design doc 17). Several balls
 * travel the lines at once, in both directions, each the same physical size
 * (sigma in mark units), crossing a line in under a second.
 */
export const THINKING_BULGES = Object.freeze({
  /** Balls alive at once (also the size of the polygon pool). */
  max: 5,
  /** Seconds into thinking before the first ball, then the gap between spawns. */
  firstSpawnSeconds: 0.15,
  spawnMin: 0.15,
  spawnMax: 0.35,
  /** Seconds for a ball to cross its line, end to end. */
  durationMin: 0.45,
  durationMax: 0.8,
  /** Gaussian sigma of the ball along the line, in mark units. */
  sigmaUnits: 36,
  /** Extra half-width at the ball's centre, in mark units per side. Two
   * neighbouring balls at the same spot must clear the 24-unit brand gap. */
  heightMin: 8,
  heightMax: 11,
  /** Often a second ball runs in step on another line, any of them: same
   * start, same speed, same direction. (The spine keeps its own pace and
   * never pairs.) */
  pairProbability: 0.5,
  /** The spine's ball runs this much faster than the others… */
  spineSpeedFactor: 2,
  /** …and often crosses the spine and comes straight back. */
  spineRoundTripProbability: 0.5,
})

interface ActiveBulge {
  tine: number
  start: number
  /** Seconds for the whole journey (both legs of a round trip). */
  duration: number
  height: number
  /** Travelling from the path's first end to its last, or the other way. */
  forward: boolean
  /** Across and straight back again. */
  roundTrip: boolean
}

/** Where along its line a ball is, 0 = the path's first end; outside [0, 1]
 * before it starts (a paired follower waiting its turn). */
function bulgeCentre(b: ActiveBulge, t: number): number {
  const p = (t - b.start) / b.duration
  const leg = b.roundTrip ? (p < 0.5 ? 2 * p : 2 - 2 * p) : p
  return b.forward ? leg : 1 - leg
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
  listener: Listener
  raw: Float32Array
  scaled: Float32Array
  /** This frame's displacement multiplier per tine (ring + lean, clamped). */
  multipliers: Float64Array
  /** The state the engine last acted on. Seeded 'idle' so mounting in any
   * other state counts as entering it (a mount in `recognized` strums). */
  seenState: VoiceVisualState
  /** Current lean weight, ramping toward the state's target. */
  swellWeight: number
  /** Current retraction weight, ramping toward the state's target. */
  retractWeight: number
  trims: Retraction[]
  bulges: ActiveBulge[]
  /** Armed on the first thinking frame so it shares the frame clock. */
  nextSpawn: number | null
  /** 0 = full size, 1 = thinking contraction; a small spring of its own. */
  contract: number
  contractV: number
}

/**
 * @param carry the engine being replaced on a density change, if any: its
 *        posture (which state it last acted on, the ramped weights, the
 *        listener's envelopes) carries over so nothing restarts or strums
 *        again. On mount there is nothing to carry: the state is seeded
 *        'idle' so mounting in any other state counts as entering it.
 */
function createEngine(density: VoiceDensity, initialState: string, carry: Engine | null): Engine {
  const count = tineCount(density)
  const initial = excitationFor(initialState)
  const listener = new Listener(tineLengths(density))
  if (carry) listener.adopt(carry.listener)
  return {
    density,
    count,
    amplitudes: TINE_AMPLITUDES[density],
    ring: ResonatorBank.strings(STRING_LADDER[density]),
    swell: ResonatorBank.uniform(count, SWELL_SPRING),
    onsets: new OnsetPlucker(count),
    queue: new PluckQueue(),
    idle: new IdlePlucker(count),
    listener,
    raw: new Float32Array(count),
    scaled: new Float32Array(count),
    multipliers: new Float64Array(count),
    seenState: carry ? carry.seenState : 'idle',
    swellWeight: carry ? carry.swellWeight : initial.swellWeight,
    retractWeight: carry ? carry.retractWeight : initial.retract,
    trims: Array.from({ length: count }, () => ({ start: 0, end: 0 })),
    bulges: [],
    nextSpawn: null,
    contract: 0,
    contractV: 0,
  }
}

/**
 * The Halbert mark as a set of plucked strings that can also listen
 * (design doc 17).
 *
 * Each frame: the energy source supplies a level per tine; rising levels
 * pluck that tine's string (ring), the level itself leans it a little
 * (swell); the sum, clamped to the geometry ceiling, is the tine's
 * displacement. In the listening posture the lines withdraw their ends
 * instead (listening.ts), a trim of the same path. Thinking lays travelling
 * swellings over the lines as filled polygons. State only changes how the
 * strings are struck and whether they withdraw — the strings themselves
 * (pitch, sustain) never change, which is what keeps every surface's motion
 * identical.
 */
export const AudioReactiveHalbertMark = React.forwardRef<
  SVGSVGElement,
  AudioReactiveHalbertMarkProps
>(function AudioReactiveHalbertMark(
  {
    size = 512,
    density = DEFAULT_DENSITY,
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
  const bulgeRefs = React.useRef<Array<SVGPolygonElement | null>>([])
  const groupRef = React.useRef<SVGGElement | null>(null)
  const stateRef = React.useRef(state)
  stateRef.current = state
  // The mount state only seeds the lean and retraction weights; later states
  // are read live. A density change rebuilds the engine but carries the
  // previous one's posture over.
  const initialStateRef = React.useRef(state)
  const engineRef = React.useRef<Engine | null>(null)
  const engine = React.useMemo(
    () => createEngine(density, initialStateRef.current, engineRef.current),
    [density],
  )
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
      if (!e) return
      const dt = Math.min(0.1, Math.max(0, (nowMs - last) / 1000))
      last = nowMs
      const t = nowMs / 1000
      const { count, ring, swell, raw, scaled, amplitudes, multipliers } = e

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
      e.retractWeight +=
        (excitation.retract - e.retractWeight) *
        (1 - Math.exp(-dt / RETRACT_WEIGHT_RAMP_SECONDS))

      active.readEnergies(raw, t)
      for (let k = 0; k < count; k++) scaled[k] = raw[k] * sensitivity
      e.onsets.feed(scaled, excitation.pluckGain, ring)
      e.queue.flush(t, ring)
      if (state === 'idle') e.idle.tick(t, ring)
      e.listener.feed(scaled, dt, t)
      swell.setTargets(scaled)
      const ringAlpha = ring.step(dt)
      const swellAlpha = swell.step(dt)

      // Thinking: spawn balls on random lines, several alive at once, each
      // heading one way or the other, often in pairs; the spine's run twice
      // as fast and often bounce straight back. Cull on state exit or arrival.
      const B = THINKING_BULGES
      if (state === 'thinking') {
        if (e.nextSpawn === null) e.nextSpawn = t + B.firstSpawnSeconds
        if (t >= e.nextSpawn && e.bulges.length < B.max) {
          const busy = new Set(e.bulges.map((b) => b.tine))
          let pick = Math.floor(Math.random() * count)
          if (busy.has(pick)) pick = (pick + 1) % count
          const oneWay =
            (B.durationMin + Math.random() * (B.durationMax - B.durationMin)) /
            (pick === 0 ? B.spineSpeedFactor : 1)
          const height = B.heightMin + Math.random() * (B.heightMax - B.heightMin)
          const forward = Math.random() < 0.5
          const paired =
            Math.random() < B.pairProbability && pick !== 0 && e.bulges.length <= B.max - 2
          const roundTrip = pick === 0 && Math.random() < B.spineRoundTripProbability
          const duration = oneWay * (roundTrip ? 2 : 1)
          e.bulges.push({ tine: pick, start: t, duration, height, forward, roundTrip })
          if (paired) {
            // a partner in step on any other free line (never the spine)
            const free: number[] = []
            for (let k = 1; k < count; k++) if (k !== pick && !busy.has(k)) free.push(k)
            if (free.length > 0) {
              const partner = free[Math.floor(Math.random() * free.length)]
              e.bulges.push({ tine: partner, start: t, duration, height, forward, roundTrip })
            }
          }
          e.nextSpawn = t + B.spawnMin + Math.random() * (B.spawnMax - B.spawnMin)
        }
      } else if (e.bulges.length > 0) {
        e.bulges = []
        e.nextSpawn = null
      }
      e.bulges = e.bulges.filter((b) => (t - b.start) / b.duration <= 1)

      // Thinking contraction (spec §4.1 state 4): gentle spring scale 1 -> 0.94
      const contractTarget = state === 'thinking' ? 1 : 0
      const ca = 60 * (contractTarget - e.contract) - 14 * e.contractV
      e.contractV += ca * dt
      e.contract += e.contractV * dt

      const retracting = e.retractWeight > RETRACT_EPSILON
      for (let k = 0; k < count; k++) {
        const unclamped =
          ring.interpolated(k, ringAlpha) + e.swellWeight * swell.interpolated(k, swellAlpha)
        multipliers[k] = Math.max(
          -MAX_DISPLACEMENT_MULTIPLIER,
          Math.min(MAX_DISPLACEMENT_MULTIPLIER, unclamped),
        )
        if (retracting) {
          const trim = e.trims[k]
          trim.start = e.retractWeight * e.listener.retraction(k, 0)
          trim.end = e.retractWeight * e.listener.retraction(k, 1)
        }
        const el = pathRefs.current[k]
        if (!el) continue
        const opts: TinePathOptions = { density: e.density }
        if (retracting) opts.trim = e.trims[k]
        el.setAttribute('d', tinePathD(k, amplitudes[k] * multipliers[k], opts))
      }
      for (let i = 0; i < B.max; i++) {
        const el = bulgeRefs.current[i]
        if (!el) continue
        const b = e.bulges[i]
        if (!b) {
          el.setAttribute('points', '')
          continue
        }
        el.setAttribute(
          'points',
          bulgePolygonPoints(
            b.tine,
            { center: bulgeCentre(b, t), sigmaUnits: B.sigmaUnits, height: b.height },
            {
              density: e.density,
              displacement: amplitudes[b.tine] * multipliers[b.tine],
              strokeWidth: STROKE_WIDTH[e.density],
              trim: retracting ? e.trims[b.tine] : undefined,
            },
          ),
        )
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
        strokeWidth={STROKE_WIDTH[density]}
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
        {/* Thinking's travelling swellings: filled in the line's colour, laid
         * over the strokes, inside the same contracting group. */}
        <g fill={stroke} stroke="none">
          {Array.from({ length: THINKING_BULGES.max }, (_, i) => (
            <polygon
              key={i}
              points=""
              ref={(el) => {
                bulgeRefs.current[i] = el
              }}
            />
          ))}
        </g>
      </g>
    </svg>
  )
})
