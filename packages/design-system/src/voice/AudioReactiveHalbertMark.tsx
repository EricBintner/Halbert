// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import * as React from 'react'
import { cx } from '../lib'
import {
  TINE_AMPLITUDES,
  TINE_DRIFT,
  staticTinePaths,
  tineCount,
  tinePathD,
  type TinePathOptions,
  type TravelingBulge,
  type VoiceDensity,
} from './geometry'
import { PLUCK_SPRING, ResonatorBank, SPRING_DEFAULTS } from './springs'
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
const STROKE_BY_DENSITY: Record<VoiceDensity, number> = { medium: 48, display: 26.67 }

/** Speaking: an energy onset above this delta strikes the tine. */
const PLUCK_ONSET_DELTA = 0.04
/** Strike strength: onset delta -> injected spring velocity. */
const PLUCK_GAIN = 3
/** Thinking: quiet baseline so the traveling bulges read cleanly. */
const THINKING_BASELINE = 0.015

interface ActiveBulge {
  tine: number
  start: number
  duration: number
  height: number
  width: number
}

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
  const count = tineCount(density)
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

    // Speaking uses the underdamped plucked-string spring; every onset
    // strikes its tine. Listening/idle uses the smooth well-damped spring.
    const bank = new ResonatorBank(
      TINE_DRIFT[density],
      state === 'speaking' ? PLUCK_SPRING : SPRING_DEFAULTS,
    )
    const amplitudes = TINE_AMPLITUDES[density]
    const raw = new Float32Array(count)
    const prevRaw = new Float32Array(count)

    // Thinking "snake" bulges: staggered spawns, 2-3 concurrently traveling.
    // nextSpawn is armed on the first frame so it shares the frame clock
    // (performance.now() and rAF timestamps may have different origins).
    let bulges: ActiveBulge[] = []
    let nextSpawn: number | null = null
    const bulgesByTine: TravelingBulge[][] = Array.from({ length: count }, () => [])

    let contract = 0 // 0 = full size, 1 = thinking contraction
    let contractV = 0
    let last = performance.now()
    let raf = 0

    const frame = (nowMs: number) => {
      raf = requestAnimationFrame(frame)
      const dt = Math.min(0.1, Math.max(0, (nowMs - last) / 1000))
      last = nowMs
      const t = nowMs / 1000

      active.readEnergies(raw, t)
      if (state === 'thinking') raw.fill(THINKING_BASELINE)
      if (state === 'speaking') {
        for (let k = 0; k < count; k++) {
          const dv = raw[k] - prevRaw[k]
          if (dv > PLUCK_ONSET_DELTA) bank.injectVelocity(k, dv * PLUCK_GAIN)
        }
      }
      prevRaw.set(raw)
      bank.setTargets(raw)
      const alpha = bank.step(dt)

      // Thinking: spawn traveling bulges on random tines (sequential,
      // 2-3 alive at once); cull them on state exit or journey end.
      if (state === 'thinking') {
        if (nextSpawn === null) nextSpawn = t + 0.3
        if (t >= nextSpawn && bulges.length < 3) {
          const busy = new Set(bulges.map((b) => b.tine))
          let pick = Math.floor(Math.random() * count)
          if (busy.has(pick)) pick = (pick + 1) % count
          bulges.push({
            tine: pick,
            start: t,
            duration: 0.9 + Math.random() * 0.7,
            height: 7 + Math.random() * 4,
            width: 0.07,
          })
          nextSpawn = t + 0.45 + Math.random() * 0.75
        }
      } else if (bulges.length > 0) {
        bulges = []
      }
      bulges = bulges.filter((b) => (t - b.start) / b.duration <= 1)
      for (const arr of bulgesByTine) arr.length = 0
      for (const b of bulges) {
        bulgesByTine[b.tine].push({
          center: (t - b.start) / b.duration,
          width: b.width,
          height: b.height,
        })
      }

      // Thinking contraction (spec §4.1 state 4): gentle spring scale 1 -> 0.94
      const contractTarget = state === 'thinking' ? 1 : 0
      const ca = 60 * (contractTarget - contract) - 14 * contractV
      contractV += ca * dt
      contract += contractV * dt

      for (let k = 0; k < count; k++) {
        const el = pathRefs.current[k]
        if (!el) continue
        const opts: TinePathOptions =
          bulgesByTine[k].length > 0
            ? { density, bulges: bulgesByTine[k] }
            : { density }
        const displacement = amplitudes[k] * sensitivity * bank.interpolated(k, alpha)
        el.setAttribute('d', tinePathD(k, displacement, bank.phases[k], opts))
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
  }, [source, state, sensitivity, density, count])

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
