// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import * as React from 'react'
import { cx, useId } from '../lib'
import type { StatusTone } from '../primitives/StatusBadge'

export interface MetricCardProps extends React.HTMLAttributes<HTMLDivElement> {
  label: string
  /** The reading. Rendered in the tabular mono face so it cannot reflow as it ticks. */
  value: React.ReactNode
  sub?: React.ReactNode
  tone?: StatusTone
  /** Fill percentage, 0-100. Omit for a card with no gauge. */
  bar?: number
  /**
   * The sensor could not be read. Renders an honest degraded state instead of a
   * plausible-looking number — Computational Honesty Gate, brand guidelines §7.
   */
  offline?: boolean
}

/** Live sensor card — CPU, memory, storage. */
export const MetricCard = React.forwardRef<HTMLDivElement, MetricCardProps>(function MetricCard(
  { label, value, sub, tone, bar, offline = false, className, id, ...props },
  ref,
) {
  const cardId = useId(id)
  const labelId = `${cardId}-label`
  const clamped = bar == null ? null : Math.max(0, Math.min(100, bar))

  return (
    <div
      ref={ref}
      id={cardId}
      className={cx('hb-metric', tone && `hb-metric--${tone}`, offline && 'is-offline', className)}
      {...props}
    >
      <div className="hb-metric__label" id={labelId}>
        {label}
      </div>

      {offline ? (
        <div className="hb-metric__offline">[Sensor offline]</div>
      ) : (
        <>
          <div className="hb-metric__value">{value}</div>
          {clamped != null && (
            <div
              className="hb-metric__gauge"
              role="meter"
              aria-labelledby={labelId}
              aria-valuenow={clamped}
              aria-valuemin={0}
              aria-valuemax={100}
            >
              <div className="hb-metric__fill" style={{ width: `${clamped}%` }} />
            </div>
          )}
          {sub && <div className="hb-metric__sub">{sub}</div>}
        </>
      )}
    </div>
  )
})
