// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import * as React from 'react'
import { cx, useId } from '../lib'
import { fmt, scale, type ChartJob, type ChartTone } from './foundation'

/** Job: a usable scope nested inside a larger one. */
export const JOB: ChartJob = 'scope-within-scope'

export interface RangeBarProps extends React.HTMLAttributes<HTMLDivElement> {
  /** The outer total, e.g. all system memory. */
  total: number
  /** The addressable ceiling inside that total, e.g. what the GPU may use. */
  ceiling: number
  /** What is actually consumed inside the ceiling. */
  used: number
  unit?: string
  /** Names for the three quantities, used in the captions. */
  totalLabel?: string
  ceilingLabel?: string
  usedLabel?: string
  caption?: React.ReactNode
  tone?: ChartTone
}

const W = 320
const H = 84
const TRACK_Y = 24
const TRACK_H = 26

/**
 * RangeBar — a scope inside a scope.
 *
 * This Mac has 128 GB of unified memory, of which the GPU may address 96, of
 * which it is using 0.93. That is three nested quantities and a flat meter has
 * to discard two of them: it would read "0.7%" and lose the 96, which is the
 * number that decides whether a model fits. A discrete card's VRAM has no inner
 * scope and stays a plain meter — pick the form from `memory_architecture`.
 */
export const RangeBar = React.forwardRef<HTMLDivElement, RangeBarProps>(function RangeBar(
  {
    total,
    ceiling,
    used,
    unit = 'GB',
    totalLabel = 'SYSTEM',
    ceilingLabel = 'CEILING',
    usedLabel = 'IN USE',
    caption,
    tone = 'data-4',
    className,
    id,
    ...props
  },
  ref,
) {
  const chartId = useId(id)
  const safeTotal = total > 0 ? total : 1
  const capX = scale(Math.min(ceiling, safeTotal), 0, safeTotal, 0, W)
  const useX = scale(Math.min(used, safeTotal), 0, safeTotal, 0, W)

  const summary =
    `${fmt(used)} ${unit} in use of a ${fmt(ceiling)} ${unit} ceiling, ` +
    `within ${fmt(total)} ${unit} total`

  return (
    <div ref={ref} id={chartId} className={cx('hb-chart', 'hb-range', className)} {...props}>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={summary} className="hb-chart__svg">
        {caption && (
          <text x={0} y={11} className="hb-chart__caption">
            {caption}
          </text>
        )}

        <rect x={0} y={TRACK_Y} width={W} height={TRACK_H} className="hb-range__total" />
        <rect
          x={0}
          y={TRACK_Y}
          width={Math.max(1, capX)}
          height={TRACK_H}
          className={cx('hb-range__ceiling', `hb-range__ceiling--${tone}`)}
        />
        <rect
          x={0}
          y={TRACK_Y}
          width={Math.max(1.5, useX)}
          height={TRACK_H}
          className={cx('hb-range__used', `hb-range__used--${tone}`)}
        />

        <text x={2} y={TRACK_Y + TRACK_H + 14} className="hb-chart__tick">
          {usedLabel} {fmt(used)}
        </text>
        <text x={capX} y={TRACK_Y + TRACK_H + 14} className="hb-chart__tick" textAnchor="end">
          {ceilingLabel} {fmt(ceiling, 0)} {unit}
        </text>
        <text x={W} y={TRACK_Y + TRACK_H + 14} className="hb-chart__tick" textAnchor="end">
          {totalLabel} {fmt(total, 0)} {unit}
        </text>
      </svg>
    </div>
  )
})
