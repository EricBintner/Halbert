// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import * as React from 'react'
import { cx, useId } from '../lib'
import type { ChartJob, ChartTone } from './foundation'

/** Job: many items, each in one of a few states. */
export const JOB: ChartJob = 'state-across-items'

export interface MatrixItem {
  id: string
  /** Item name, surfaced on hover. */
  label: string
  /** Which state bucket this item is in. Must match a `states` key. */
  state: string
  detail?: string
}

export interface MatrixState {
  /** Bucket key, matching `MatrixItem.state`. */
  key: string
  /** Human name for the legend. */
  label: string
  tone: ChartTone
}

export interface StatusMatrixProps extends React.HTMLAttributes<HTMLDivElement> {
  items: MatrixItem[]
  /** The state vocabulary, in legend order. */
  states: MatrixState[]
  /** Marks per row (default 16). */
  columns?: number
  /** Render the counted legend beneath (default true). */
  showLegend?: boolean
}

const W = 320
const GAP = 5

/**
 * StatusMatrix — one mark per item, coloured by state.
 *
 * Ninety-three services is the largest dataset in the product and it renders as
 * a list of words. A run state is not a magnitude, so a bar was never the right
 * instrument; a grid answers "is anything wrong" before you have read anything,
 * and names the offender on hover.
 *
 * This wants a normalized state enum, not a formatted string. `service.status`
 * currently reads "Running (PID 63202)", which yields one bucket per process.
 */
export const StatusMatrix = React.forwardRef<HTMLDivElement, StatusMatrixProps>(
  function StatusMatrix(
    { items, states, columns = 16, showLegend = true, className, id, ...props },
    ref,
  ) {
    const chartId = useId(id)
    const cell = (W - (columns - 1) * GAP) / columns
    const rows = Math.ceil(items.length / columns) || 1
    const height = rows * (cell + GAP)

    const toneFor = React.useMemo(() => {
      const m: Record<string, ChartTone> = {}
      states.forEach((s) => (m[s.key] = s.tone))
      return m
    }, [states])

    const counts = React.useMemo(() => {
      const c: Record<string, number> = {}
      items.forEach((it) => (c[it.state] = (c[it.state] ?? 0) + 1))
      return c
    }, [items])

    const summary =
      `${items.length} items — ` +
      states
        .filter((s) => counts[s.key])
        .map((s) => `${counts[s.key]} ${s.label.toLowerCase()}`)
        .join(', ')

    return (
      <div ref={ref} id={chartId} className={cx('hb-chart', 'hb-matrix', className)} {...props}>
        <svg
          viewBox={`0 0 ${W} ${Math.max(height, cell)}`}
          role="img"
          aria-label={summary}
          className="hb-chart__svg"
        >
          {items.map((it, i) => {
            const col = i % columns
            const row = Math.floor(i / columns)
            const tone = toneFor[it.state] ?? 'neutral'
            return (
              <rect
                key={it.id}
                x={col * (cell + GAP)}
                y={row * (cell + GAP)}
                width={cell}
                height={cell * 0.86}
                rx={1.5}
                className={cx('hb-matrix__cell', `hb-matrix__cell--${tone}`)}
              >
                <title>{it.detail ?? `${it.label} — ${it.state}`}</title>
              </rect>
            )
          })}
        </svg>

        {showLegend && (
          <ul className="hb-matrix__legend">
            {states
              .filter((s) => counts[s.key])
              .map((s) => (
                <li key={s.key}>
                  <span className={cx('hb-matrix__swatch', `hb-matrix__cell--${s.tone}`)} aria-hidden="true" />
                  <span className="hb-matrix__legend-label">{s.label}</span>
                  <span className="hb-matrix__legend-count">{counts[s.key]}</span>
                </li>
              ))}
          </ul>
        )}
      </div>
    )
  },
)
