// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import * as React from 'react'
import { cx, useId } from '../lib'

export type TactileMeterTone =
  | 'auto'
  | 'telemetry'
  | 'nominal'
  | 'warning'
  | 'critical'
  | 'neutral'
  | 'data-1'
  | 'data-2'
  | 'data-3'
  | 'data-4'
  | 'data-5'
  | 'data-blue'
  | 'data-orchid'
  | 'data-teal'
  | 'data-purple'
  | 'data-green'
  | 'data-neutral'

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
   * - 'telemetry' (default): vibrant blueprint cobalt
   * - 'auto': auto-threshold alert: nominal (<75%), warning (75-89%), critical (>=90%)
   * - 'critical': alarm crimson (hardware / capacity fault)
   * - 'warning': warm goldenrod amber
   * - 'nominal': fresh botanical emerald
   * - 'neutral': calm slate graphite
   * - categorical data series: 'data-blue', 'data-orchid', 'data-teal', etc.
   */
  tone?: TactileMeterTone
  /** Track height variant (default: 'md'). */
  size?: 'sm' | 'md' | 'lg' | 'xl' | 'thick' | 'hero'
  /**
   * Sensor offline or unmeasurable state. Renders an honest degraded state
   * rather than a plausible-looking zero — Computational Honesty Gate.
   */
  offline?: boolean
  /**
   * Fixed column width for the label (e.g. 200 or '220px').
   * Guarantees that the `sub` (data path) starts at the exact same horizontal coordinate across stacked meters.
   */
  labelWidth?: number | string
  /**
   * Optional status indicator or alert badge. Rendered in a dedicated layout slot
   * so critical alerts cannot push the readout or break layout.
   */
  statusBadge?: React.ReactNode
  /**
   * Whether to explicitly force rendering the numerical readout even when no label is provided.
   * By default, a pure meter track with no label or sub will NOT render an empty header.
   */
  showReadout?: boolean
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
    tone = 'telemetry',
    size = 'md',
    offline = false,
    labelWidth,
    statusBadge,
    showReadout = false,
    className,
    style,
    id,
    'aria-label': ariaLabel,
    'aria-labelledby': ariaLabelledBy,
    ...props
  },
  ref,
) {
  const meterId = useId(id)
  const labelId = label ? `${meterId}-label` : undefined

  // The name belongs on the node carrying role="meter", not the wrapper the
  // caller's props spread onto. A caller's explicit name wins, else the
  // rendered label names it; an unlabelled meter would otherwise be announced
  // as a bare number.
  const describedByLabel = ariaLabelledBy ?? labelId
  const meterLabel = describedByLabel ? undefined : (ariaLabel ?? 'Gauge reading')
  const clamped = Math.max(0, Math.min(100, isNaN(value) ? 0 : value))

  // Determine tone
  const resolvedTone = React.useMemo(() => {
    if (tone !== 'auto') return tone
    if (clamped >= 90) return 'critical'
    if (clamped >= 75) return 'warning'
    return 'telemetry'
  }, [tone, clamped])

  const formattedValue = valueLabel ?? (offline ? '[Sensor offline]' : `${clamped.toFixed(1)}${unit}`)

  const meterStyles: React.CSSProperties = {
    ...style,
    ...(labelWidth != null
      ? { ['--meter-label-width' as string]: typeof labelWidth === 'number' ? `${labelWidth}px` : labelWidth }
      : {}),
  }

  const hasHeader = Boolean(label || sub || valueLabel !== undefined || statusBadge || showReadout)

  return (
    <div
      ref={ref}
      id={meterId}
      className={cx(
        'hb-tactile-meter',
        `hb-tactile-meter--${size}`,
        `hb-tactile-meter--${resolvedTone}`,
        labelWidth != null && 'hb-tactile-meter--has-label-width',
        offline && 'is-offline',
        className,
      )}
      style={meterStyles}
      {...props}
    >
      {hasHeader && (
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
            {statusBadge && <div className="hb-tactile-meter__status">{statusBadge}</div>}
          </div>
        </div>
      )}

      {/* The Instrument Gauge Track */}
      <div
        className="hb-tactile-meter__track"
        role="meter"
        aria-label={meterLabel}
        aria-labelledby={describedByLabel}
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

        {/* In-Bar Overlay Content */}

        {offline && (
          <div className="hb-tactile-meter__offline-strip" aria-hidden="true">
            <span className="hb-tactile-meter__offline-text">OFFLINE</span>
          </div>
        )}
      </div>
    </div>
  )
})
