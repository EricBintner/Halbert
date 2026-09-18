// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import * as React from 'react'
import { cx, useId } from '../lib'
import { fmt, scale, type ChartJob } from './foundation'

/** Job: direction across a few named horizons. */
export const JOB: ChartJob = 'measure-over-time'

export interface SlopePoint {
  /** Horizon name, e.g. "1 min". */
  label: string
  value: number
}

export interface SlopeChartProps extends Omit<React.HTMLAttributes<HTMLDivElement>, 'onSelect'> {
  /** Two or more readings of the same measure, oldest last or first — as given. */
  points: SlopePoint[]
  /** Upper bound of the scale. Defaults to the largest reading plus headroom. */
  max?: number
  /** A meaningful ceiling to draw as a reference, e.g. the core count for load. */
  reference?: number
  /** Label for that reference line. */
  referenceLabel?: string
  /** Unit appended to the readings. */
  unit?: string
  /** Decimal places on the readings (default 1; pass 0 for whole numbers). */
  digits?: number
  /** Readings above this wear the warning pigment. */
  warnAbove?: number
  /** Sensor dark. Renders an explicit unmeasured state, never a flat zero. */
  offline?: boolean
}

const W = 320
const H = 112
const PAD_L = 44
const PAD_R = 8
const TOP = 16
const BASE = 78

/**
 * SlopeChart — the same measure at several horizons, joined.
 *
 * Halbert's load average arrives as three numbers across one, five and fifteen
 * minutes. A meter can show one of them; only the join says whether the machine
 * is climbing or recovering, which is the question an operator actually has.
 */
export const SlopeChart = React.forwardRef<HTMLDivElement, SlopeChartProps>(function SlopeChart(
  {
    points,
    max,
    reference,
    referenceLabel,
    unit = '',
    digits = 1,
    warnAbove,
    offline = false,
    className,
    id,
    ...props
  },
  ref,
) {
  const chartId = useId(id)
  const valid = points.filter((p) => isFinite(p.value))
  const peak = Math.max(...valid.map((p) => p.value), reference ?? 0, 1)
  const top = max ?? peak * 1.12

  const x = (i: number) =>
    points.length < 2
      ? (PAD_L + W - PAD_R) / 2
      : PAD_L + (i / (points.length - 1)) * (W - PAD_L - PAD_R)
  const y = (v: number) => scale(v, 0, top, BASE, TOP)

  const summary = offline
    ? '[Sensor offline]'
    : points.map((p) => `${p.label} ${fmt(p.value, digits)}${unit}`).join(', ')

  return (
    <div
      ref={ref}
      id={chartId}
      className={cx('hb-chart', 'hb-slope', offline && 'is-offline', className)}
      {...props}
    >
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={summary} className="hb-chart__svg">
        {reference != null && reference <= top && (
          <>
            <line
              x1={PAD_L}
              y1={y(reference)}
              x2={W - PAD_R}
              y2={y(reference)}
              className="hb-chart__reference"
            />
            {referenceLabel && (
              <text x={0} y={y(reference) + 3} className="hb-chart__tick">
                {referenceLabel}
              </text>
            )}
          </>
        )}

        <line x1={PAD_L} y1={BASE} x2={W - PAD_R} y2={BASE} className="hb-chart__axis" />
        <text x={0} y={BASE + 3} className="hb-chart__tick">
          0
        </text>

        {!offline && valid.length >= 2 && (
          <polyline
            className="hb-slope__line"
            points={points.map((p, i) => `${x(i)},${y(p.value)}`).join(' ')}
          />
        )}

        {!offline &&
          points.map((p, i) => (
            <circle
              key={p.label}
              cx={x(i)}
              cy={y(p.value)}
              r={warnAbove != null && p.value >= warnAbove ? 4.5 : 4}
              className={cx(
                'hb-slope__node',
                warnAbove != null && p.value >= warnAbove && 'hb-slope__node--warning',
              )}
            />
          ))}

        {points.map((p, i) => (
          <g key={`${p.label}-label`}>
            <text x={x(i)} y={BASE + 16} className="hb-chart__tick" textAnchor="middle">
              {p.label}
            </text>
            <text x={x(i)} y={H - 4} className="hb-chart__value" textAnchor="middle">
              {offline ? '—' : `${fmt(p.value, digits)}${unit}`}
            </text>
          </g>
        ))}

        {offline && (
          <text x={(PAD_L + W - PAD_R) / 2} y={44} className="hb-chart__offline" textAnchor="middle">
            SENSOR OFFLINE
          </text>
        )}
      </svg>
    </div>
  )
})
