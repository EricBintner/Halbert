// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import * as React from 'react'
import { cx, useId } from '../lib'
import { scale, type ChartJob, type ChartTone } from './foundation'

/** Job: one measure's recent history, beside the number it belongs to. */
export const JOB: ChartJob = 'measure-over-time'

export interface SparklineProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Oldest sample first. */
  values: number[]
  min?: number
  max?: number
  tone?: ChartTone
  /** Fill under the line (default true). */
  area?: boolean
  /** Mark the newest sample (default true). */
  showEndpoint?: boolean
  /** Accessible description; the tile's own label usually supplies this. */
  'aria-label'?: string
  /** No history yet. Renders a flat rule, not a fabricated line. */
  empty?: boolean
}

const W = 160
const H = 34
const PAD = 3

/**
 * Sparkline — the shape of the last minute, at the size of a word.
 *
 * Pairs with the number rather than replacing it: the reading answers "what is
 * it", the line answers "is it climbing", and neither is much use alone. Needs
 * a history buffer behind `/api/status`, which today returns instants only —
 * with `empty` it says so instead of drawing a straight line through one point.
 */
export const Sparkline = React.forwardRef<HTMLDivElement, SparklineProps>(function Sparkline(
  {
    values,
    min,
    max,
    tone = 'data-1',
    area = true,
    showEndpoint = true,
    empty = false,
    className,
    id,
    'aria-label': ariaLabel,
    ...props
  },
  ref,
) {
  const chartId = useId(id)
  const clean = values.filter((v) => isFinite(v))
  const hasData = !empty && clean.length >= 2

  const lo = min ?? (hasData ? Math.min(...clean) : 0)
  const hi = max ?? (hasData ? Math.max(...clean) : 1)
  const span = hi - lo || 1

  const pts = hasData
    ? clean.map((v, i) => {
        const x = PAD + (i / (clean.length - 1)) * (W - PAD * 2)
        const y = scale(v, lo, lo + span, H - PAD, PAD)
        return [x, y] as const
      })
    : []

  const line = pts.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' ')
  const fill = pts.length
    ? [
        `M ${pts[0][0].toFixed(1)} ${H}`,
        ...pts.map(([x, y]) => `L ${x.toFixed(1)} ${y.toFixed(1)}`),
        `L ${pts[pts.length - 1][0].toFixed(1)} ${H}`,
        'Z',
      ].join(' ')
    : ''

  return (
    <div
      ref={ref}
      id={chartId}
      className={cx('hb-chart', 'hb-spark', className)}
      {...props}
    >
      <svg
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label={ariaLabel ?? (hasData ? 'Recent trend' : 'No history recorded yet')}
        className="hb-chart__svg"
        preserveAspectRatio="none"
      >
        {hasData ? (
          <>
            {area && <path d={fill} className={cx('hb-spark__area', `hb-spark__area--${tone}`)} />}
            <polyline points={line} className={cx('hb-spark__line', `hb-spark__line--${tone}`)} />
            {showEndpoint && (
              <circle
                cx={pts[pts.length - 1][0]}
                cy={pts[pts.length - 1][1]}
                r={2.6}
                className={cx('hb-spark__end', `hb-spark__end--${tone}`)}
                vectorEffect="non-scaling-stroke"
              />
            )}
          </>
        ) : (
          <line x1={PAD} y1={H / 2} x2={W - PAD} y2={H / 2} className="hb-spark__empty" />
        )}
      </svg>
    </div>
  )
})
