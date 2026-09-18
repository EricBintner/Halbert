// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import * as React from 'react'
import { cx, useId } from '../lib'
import { fmt, scale, thresholdTone, type ChartJob, type ChartTone } from './foundation'

/** Job: one measure compared across several named peers. */
export const JOB: ChartJob = 'measure-across-peers'

export interface DotPlotItem {
  id: string
  /** Peer name, e.g. a volume or a node. */
  label: string
  value: number
  /** Override the threshold-derived pigment. */
  tone?: ChartTone
  /** Sensor dark for this peer only. */
  offline?: boolean
}

export interface DotPlotProps extends React.HTMLAttributes<HTMLDivElement> {
  items: DotPlotItem[]
  /** Scale minimum (default 0). */
  min?: number
  /** Scale maximum (default 100). */
  max?: number
  /** Unit appended to the axis and readings. */
  unit?: string
  /** Show each peer's reading at the right (default true). */
  showValues?: boolean
  /** Threshold at which a dot wears the warning pigment. */
  warnAt?: number
  /** Threshold at which a dot wears the critical pigment. */
  critAt?: number
}

const W = 320
const LABEL_W = 92
const PAD_R = 34
const ROW_H = 15
const TOP = 12

/**
 * DotPlot — several peers on one shared axis.
 *
 * Seven volumes each have a fill percentage. As seven stacked meters, comparing
 * them means reading seven numbers and holding them in your head; on one axis
 * the spread is the first thing you see. Keep the meters for reading a single
 * volume — this is the overview that sits above them.
 */
export const DotPlot = React.forwardRef<HTMLDivElement, DotPlotProps>(function DotPlot(
  {
    items,
    min = 0,
    max = 100,
    unit = '%',
    showValues = true,
    warnAt = 75,
    critAt = 90,
    className,
    id,
    ...props
  },
  ref,
) {
  const chartId = useId(id)
  const height = TOP + items.length * ROW_H + 30
  const axisY = TOP + items.length * ROW_H + 6
  const x1 = LABEL_W
  const x2 = W - (showValues ? PAD_R : 4)

  const summary = items
    .map((it) => `${it.label} ${it.offline ? 'offline' : `${fmt(it.value, 0)}${unit}`}`)
    .join(', ')

  return (
    <div
      ref={ref}
      id={chartId}
      className={cx('hb-chart', 'hb-dotplot', className)}
      {...props}
    >
      <svg viewBox={`0 0 ${W} ${height}`} role="img" aria-label={summary} className="hb-chart__svg">
        {items.map((it, i) => {
          const y = TOP + i * ROW_H
          const tone = it.tone ?? thresholdTone(it.value, warnAt, critAt)
          return (
            <g key={it.id}>
              <line x1={x1} y1={y} x2={x2} y2={y} className="hb-dotplot__rail" />
              <text x={LABEL_W - 8} y={y + 3.5} className="hb-chart__tick" textAnchor="end">
                {it.label}
              </text>
              {it.offline ? (
                <text x={x1 + 4} y={y + 3.5} className="hb-chart__offline-inline">
                  NO READING
                </text>
              ) : (
                <circle
                  cx={scale(it.value, min, max, x1, x2)}
                  cy={y}
                  r={4.5}
                  className={cx('hb-dotplot__dot', `hb-dotplot__dot--${tone}`)}
                />
              )}
              {showValues && !it.offline && (
                <text x={W - 2} y={y + 3.5} className="hb-chart__value" textAnchor="end">
                  {fmt(it.value, 0)}
                </text>
              )}
            </g>
          )
        })}

        <line x1={x1} y1={axisY} x2={x2} y2={axisY} className="hb-chart__axis" />
        <text x={x1} y={axisY + 13} className="hb-chart__tick">
          {min}
          {unit}
        </text>
        <text x={(x1 + x2) / 2} y={axisY + 13} className="hb-chart__tick" textAnchor="middle">
          {Math.round((min + max) / 2)}
          {unit}
        </text>
        <text x={x2} y={axisY + 13} className="hb-chart__tick" textAnchor="end">
          {max}
          {unit}
        </text>
      </svg>
    </div>
  )
})
