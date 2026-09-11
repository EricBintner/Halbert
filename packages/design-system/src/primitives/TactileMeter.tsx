// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import * as React from 'react'
import { cx, useId } from '../lib'

export type TactileMeterTone =
  | 'neutral'
  | 'critical'
  | 'data-blue'
  | 'data-teal'
  | 'data-purple'
  | 'data-orange'

export interface TactileMeterProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Fill percentage (0-100). Clamped automatically. */
  value: number
  /** Metric label (e.g., "Root Filesystem", "CPU Load"). */
  label?: React.ReactNode
  /** Sub-label or path (e.g., "/ · ext4"). */
  sub?: React.ReactNode
  /** Explicit value label override (e.g., "45.0 GB / 100.0 GB (45%)"). */
  valueLabel?: React.ReactNode
  /** Unit suffix for default display (default: "%"). */
  unit?: string
  /** Mechanical scale tick marks in percentage (default: [25, 50, 75, 90]). */
  ticks?: number[]
  /** Whether to render tick marks on the track (default: true). */
  showTicks?: boolean
  /**
   * Tone for the gauge fill:
   * - 'neutral' (default): calm precision graphite ink (Tufte baseline)
   * - 'critical': alarm crimson (active fault or critical capacity)
   * - categorical data series: 'data-blue', 'data-teal', 'data-purple', 'data-orange'
   */
  tone?: TactileMeterTone
  /** Track height variant (default: 'md'). */
  size?: 'sm' | 'md' | 'lg'
  /**
   * Sensor offline or unmeasurable state. Renders an honest degraded state
   * rather than a plausible-looking zero — Computational Honesty Gate.
   */
  offline?: boolean
}

/**
 * TactileMeter — A precision horizontal instrument gauge.
 *
 * Implements the Braun / Olivetti instrument language:
 * - Rigid baseline coordinate space (100% full-width track).
 * - Physical mechanical tick marks at standard operational thresholds.
 * - Tabular engineering monospace numerals preventing layout reflow.
 * - Honest [Sensor offline] state.
 */
export const TactileMeter = React.forwardRef<HTMLDivElement, TactileMeterProps>(function TactileMeter(
  {
    value,
    label,
    sub,
    valueLabel,
    unit = '%',
    ticks = [25, 50, 75, 90],
    showTicks = true,
    tone = 'neutral',
    size = 'md',
    offline = false,
    className,
    id,
    ...props
  },
  ref,
) {
  const meterId = useId(id)
  const labelId = label ? `${meterId}-label` : undefined
  const clamped = Math.max(0, Math.min(100, isNaN(value) ? 0 : value))

  // In elite dataviz, single meters default to neutral ink; only critical faults tint red
  const resolvedTone: TactileMeterTone = tone

  const formattedValue = valueLabel ?? (offline ? '[Sensor offline]' : `${clamped.toFixed(1)}${unit}`)

  return (
    <div
      ref={ref}
      id={meterId}
      className={cx(
        'hb-tactile-meter',
        `hb-tactile-meter--${size}`,
        `hb-tactile-meter--${resolvedTone}`,
        offline && 'is-offline',
        className,
      )}
      {...props}
    >
      {(label || sub || valueLabel !== undefined || !offline) && (
        <div className="hb-tactile-meter__header">
          <div className="hb-tactile-meter__identity">
            {label && (
              <span id={labelId} className="hb-tactile-meter__label">
                {label}
              </span>
            )}
            {sub && <span className="hb-tactile-meter__sub">{sub}</span>}
          </div>
          <div className="hb-tactile-meter__readout">
            <span className="hb-tactile-meter__value">{formattedValue}</span>
          </div>
        </div>
      )}

      {/* The Instrument Gauge Track */}
      <div
        className="hb-tactile-meter__track"
        role="meter"
        aria-labelledby={labelId}
        aria-valuenow={offline ? undefined : clamped}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuetext={typeof formattedValue === 'string' ? formattedValue : undefined}
      >
        {!offline && (
          <div
            className="hb-tactile-meter__fill"
            style={{ width: `${clamped}%` }}
          />
        )}

        {/* Mechanical Scale Tick Marks */}
        {showTicks && !offline && ticks.map((tick) => {
          if (tick <= 0 || tick >= 100) return null
          const isCritical = tick >= 90
          return (
            <span
              key={tick}
              className={cx(
                'hb-tactile-meter__tick',
                isCritical && 'hb-tactile-meter__tick--critical',
              )}
              style={{ left: `${tick}%` }}
              aria-hidden="true"
            />
          )
        })}

        {offline && (
          <div className="hb-tactile-meter__offline-strip" aria-hidden="true">
            <span className="hb-tactile-meter__offline-text">OFFLINE</span>
          </div>
        )}
      </div>
    </div>
  )
})
