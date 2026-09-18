// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import * as React from 'react'
import { cx, useId } from '../lib'
import { scale, type ChartJob } from './foundation'

/** Job: facts that were true over an interval, some still open. */
export const JOB: ChartJob = 'facts-with-lifespans'

export interface Lifespan {
  id: string
  /** What was believed, e.g. the entity name. */
  label: string
  /** Epoch seconds the belief began. */
  from: number
  /** Epoch seconds it was retired, or null while still held. */
  to?: number | null
  /** Optional detail for the hover title. */
  detail?: string
}

export interface LifespanBarsProps extends React.HTMLAttributes<HTMLDivElement> {
  items: Lifespan[]
  /** Window start. Defaults to the earliest `from`. */
  start?: number
  /** Window end — "now". Defaults to the latest bound. */
  end?: number
  /** Caption under the axis, left and right. */
  startLabel?: string
  endLabel?: string
}

const W = 320
const LABEL_W = 76
const ROW_H = 15
const TOP = 12

/**
 * LifespanBars — a belief is an interval, not a value.
 *
 * The state ledger stores every triple with `valid_from` and `valid_to`, so the
 * question it can answer is one nothing else in the product can: what does this
 * machine believe now, and what has it stopped believing? An open bar runs to
 * the right edge; a closed one stops where it was retired.
 */
export const LifespanBars = React.forwardRef<HTMLDivElement, LifespanBarsProps>(
  function LifespanBars(
    { items, start, end, startLabel = 'EARLIER', endLabel = 'NOW', className, id, ...props },
    ref,
  ) {
    const chartId = useId(id)

    const bounds = React.useMemo(() => {
      const froms = items.map((i) => i.from).filter(isFinite)
      const tos = items.map((i) => i.to).filter((t): t is number => typeof t === 'number' && isFinite(t))
      const lo = start ?? (froms.length ? Math.min(...froms) : 0)
      const hi = end ?? Math.max(lo + 1, ...froms, ...tos)
      return { lo, hi: hi > lo ? hi : lo + 1 }
    }, [items, start, end])

    const height = TOP + items.length * ROW_H + 28
    const axisY = TOP + items.length * ROW_H + 4
    const x1 = LABEL_W
    const x2 = W - 4

    const open = items.filter((i) => i.to == null).length
    const summary = `${items.length} beliefs, ${open} still held, ${items.length - open} retired`

    return (
      <div ref={ref} id={chartId} className={cx('hb-chart', 'hb-lifespan', className)} {...props}>
        <svg viewBox={`0 0 ${W} ${height}`} role="img" aria-label={summary} className="hb-chart__svg">
          {items.map((it, i) => {
            const y = TOP + i * ROW_H
            const isOpen = it.to == null
            const bx = scale(it.from, bounds.lo, bounds.hi, x1, x2)
            const ex = isOpen ? x2 : scale(it.to as number, bounds.lo, bounds.hi, x1, x2)
            return (
              <g key={it.id}>
                <text x={LABEL_W - 8} y={y + 8} className="hb-chart__tick" textAnchor="end">
                  {it.label}
                </text>
                <rect
                  x={bx}
                  y={y}
                  width={Math.max(2, ex - bx)}
                  height={10}
                  rx={1}
                  className={cx(
                    'hb-lifespan__bar',
                    isOpen ? 'hb-lifespan__bar--open' : 'hb-lifespan__bar--closed',
                  )}
                >
                  <title>{it.detail ?? `${it.label}${isOpen ? ' — still held' : ' — retired'}`}</title>
                </rect>
                {!isOpen && <line x1={ex} y1={y - 2} x2={ex} y2={y + 12} className="hb-lifespan__cap" />}
              </g>
            )
          })}

          <line x1={x1} y1={axisY} x2={x2} y2={axisY} className="hb-chart__axis" />
          <text x={x1} y={axisY + 13} className="hb-chart__tick">
            {startLabel}
          </text>
          <text x={x2} y={axisY + 13} className="hb-chart__tick" textAnchor="end">
            {endLabel}
          </text>
        </svg>
      </div>
    )
  },
)
