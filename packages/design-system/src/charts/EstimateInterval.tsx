// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import * as React from 'react'
import { cx, useId } from '../lib'
import { scale, type ChartJob, type ChartTone } from './foundation'

/** Job: a proportion estimated from a sample small enough to doubt. */
export const JOB: ChartJob = 'estimate-with-uncertainty'

/**
 * Wilson score interval for a binomial proportion.
 *
 * Chosen over the textbook normal approximation because that one misbehaves
 * badly at the sample sizes this product actually has — at n=8 it can return
 * bounds outside 0..1. Wilson stays inside the range and stays sane near 0 and
 * 1. Where a caller has a stricter figure (the exact Clopper–Pearson interval
 * the attunement threshold rule specifies) it can pass `low` and `high`
 * directly and this is not used.
 */
export function wilsonInterval(successes: number, n: number, z = 1.96): [number, number] {
  if (!n || n <= 0) return [0, 1]
  const p = Math.max(0, Math.min(1, successes / n))
  const z2 = z * z
  const denom = 1 + z2 / n
  const centre = (p + z2 / (2 * n)) / denom
  const half = (z / denom) * Math.sqrt((p * (1 - p)) / n + z2 / (4 * n * n))
  return [Math.max(0, centre - half), Math.min(1, centre + half)]
}

export interface EstimateIntervalProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Events observed, e.g. dismissals. */
  successes: number
  /** Sample size. */
  n: number
  /** Lower bound 0..1. Computed with Wilson when omitted. */
  low?: number
  /** Upper bound 0..1. Computed with Wilson when omitted. */
  high?: number
  /** What the proportion is of, e.g. "dismissal rate". */
  label?: React.ReactNode
  /** A decision threshold to mark on the scale, 0..1. */
  threshold?: number
  thresholdLabel?: string
  tone?: ChartTone
}

const W = 320
const H = 84
const PAD = 22

/**
 * EstimateInterval — the estimate, and what the sample actually licenses.
 *
 * Six dismissals out of eight is "75%", and drawn as a bar it reads as a
 * measurement. It is not: at n=8 the interval covers most of the range. This
 * matters beyond honesty — the proactivity dial is meant to move on evidence
 * like this, and a form that hides the width invites acting on noise.
 */
export const EstimateInterval = React.forwardRef<HTMLDivElement, EstimateIntervalProps>(
  function EstimateInterval(
    {
      successes,
      n,
      low,
      high,
      label,
      threshold,
      thresholdLabel,
      tone = 'data-2',
      className,
      id,
      ...props
    },
    ref,
  ) {
    const chartId = useId(id)
    const [wLow, wHigh] = wilsonInterval(successes, n)
    const lo = low ?? wLow
    const hi = high ?? wHigh
    const point = n > 0 ? successes / n : 0

    const x = (v: number) => scale(v, 0, 1, PAD, W - PAD)
    const pct = (v: number) => `${Math.round(v * 100)}%`

    const summary = `${pct(point)} from ${n} samples, plausible range ${pct(lo)} to ${pct(hi)}`

    return (
      <div ref={ref} id={chartId} className={cx('hb-chart', 'hb-estimate', className)} {...props}>
        <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={summary} className="hb-chart__svg">
          {label && (
            <text x={0} y={11} className="hb-chart__caption">
              {label} · n = {n}
            </text>
          )}

          <line x1={PAD} y1={44} x2={W - PAD} y2={44} className="hb-chart__axis" />

          {threshold != null && (
            <>
              <line x1={x(threshold)} y1={30} x2={x(threshold)} y2={58} className="hb-estimate__threshold" />
              {thresholdLabel && (
                <text x={x(threshold)} y={78} className="hb-chart__tick" textAnchor="middle">
                  {thresholdLabel}
                </text>
              )}
            </>
          )}

          <line
            x1={x(lo)}
            y1={44}
            x2={x(hi)}
            y2={44}
            className={cx('hb-estimate__whisker', `hb-estimate__whisker--${tone}`)}
          />
          <line x1={x(lo)} y1={38} x2={x(lo)} y2={50} className={cx('hb-estimate__cap', `hb-estimate__cap--${tone}`)} />
          <line x1={x(hi)} y1={38} x2={x(hi)} y2={50} className={cx('hb-estimate__cap', `hb-estimate__cap--${tone}`)} />
          <circle cx={x(point)} cy={44} r={5.5} className={cx('hb-estimate__point', `hb-estimate__point--${tone}`)} />

          <text x={x(point)} y={30} className="hb-chart__value" textAnchor="middle">
            {pct(point)}
          </text>
          <text x={x(lo)} y={62} className="hb-chart__tick" textAnchor="end">
            {pct(lo)}
          </text>
          <text x={x(hi)} y={62} className="hb-chart__tick" textAnchor="start">
            {pct(hi)}
          </text>
        </svg>
      </div>
    )
  },
)
