// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import * as React from 'react'
import { cx, useId } from '../lib'
import { fmt, seriesTone, type ChartJob, type ChartTone } from './foundation'

/** Job: one instance's passage through ordered stages. */
export const JOB: ChartJob = 'instance-through-stages'

export interface Stage {
  id: string
  /** Stage name, e.g. "SEARCHING". */
  label: string
  /** Seconds elapsed before this stage began. */
  start: number
  /** Seconds this stage lasted. */
  duration: number
  tone?: ChartTone
  detail?: string
}

export interface WaterfallProps extends React.HTMLAttributes<HTMLDivElement> {
  stages: Stage[]
  /** Total span in seconds. Defaults to the end of the last stage. */
  total?: number
  /** Unit shown on the axis (default "s"). */
  unit?: string
  /** Show each stage's duration at its right edge (default true). */
  showDurations?: boolean
}

const W = 320
const LABEL_W = 82
const ROW_H = 17
const TOP = 10

/**
 * Waterfall — where one turn spent its time.
 *
 * A turn walks PLANNING → SEARCHING → READING → EXECUTING → RESPONDING, and the
 * only useful question about a slow one is which stage ate the seconds. A total
 * duration cannot answer that and five meters cannot either: the stages are
 * consecutive, so their position on a shared clock is the information.
 */
export const Waterfall = React.forwardRef<HTMLDivElement, WaterfallProps>(function Waterfall(
  { stages, total, unit = 's', showDurations = true, className, id, ...props },
  ref,
) {
  const chartId = useId(id)
  const span =
    total ?? Math.max(0.001, ...stages.map((s) => s.start + s.duration))
  const height = TOP + stages.length * ROW_H + 24
  const axisY = TOP + stages.length * ROW_H + 2
  const x1 = LABEL_W
  const x2 = W - (showDurations ? 34 : 4)

  const slowest = stages.reduce(
    (a, b) => (b.duration > (a?.duration ?? -1) ? b : a),
    undefined as Stage | undefined,
  )
  const summary =
    `${fmt(span)}${unit} total` +
    (slowest ? `, longest stage ${slowest.label} at ${fmt(slowest.duration)}${unit}` : '')

  return (
    <div ref={ref} id={chartId} className={cx('hb-chart', 'hb-waterfall', className)} {...props}>
      <svg viewBox={`0 0 ${W} ${height}`} role="img" aria-label={summary} className="hb-chart__svg">
        {stages.map((st, i) => {
          const y = TOP + i * ROW_H
          const bx = x1 + (st.start / span) * (x2 - x1)
          const bw = Math.max(2, (st.duration / span) * (x2 - x1))
          const tone = st.tone ?? seriesTone(i)
          return (
            <g key={st.id}>
              <text x={LABEL_W - 8} y={y + 9} className="hb-chart__tick" textAnchor="end">
                {st.label}
              </text>
              <rect
                x={bx}
                y={y}
                width={bw}
                height={11}
                rx={1}
                className={cx('hb-waterfall__bar', `hb-waterfall__bar--${tone}`)}
              >
                <title>{st.detail ?? `${st.label} — ${fmt(st.duration)}${unit}`}</title>
              </rect>
              {showDurations && (
                <text x={W - 2} y={y + 9} className="hb-chart__value" textAnchor="end">
                  {fmt(st.duration)}
                </text>
              )}
            </g>
          )
        })}

        <line x1={x1} y1={axisY} x2={x2} y2={axisY} className="hb-chart__axis" />
        <text x={x1} y={axisY + 13} className="hb-chart__tick">
          0{unit}
        </text>
        <text x={x2} y={axisY + 13} className="hb-chart__tick" textAnchor="end">
          {fmt(span)}
          {unit}
        </text>
      </svg>
    </div>
  )
})
