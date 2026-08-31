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
  {
    size = 512,
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
