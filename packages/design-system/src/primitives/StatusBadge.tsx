// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import * as React from 'react'
import { cx } from '../lib'

export type StatusTone = 'nominal' | 'warning' | 'critical' | 'telemetry' | 'neutral'

export interface StatusBadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  tone?: StatusTone
  /**
   * Announce the state to assistive tech as it changes. Use for values that
   * update in place (a host going from Nominal to Critical), not for static
   * labels — a page of live regions is a page that never stops talking.
   */
  live?: boolean
  children: React.ReactNode
}

/**
 * Telemetry indicator pill.
 *
 * `children` is required, and that is a brand rule rather than an oversight:
 * colour alone fails WCAG 1.4.1 and tells a colourblind reader nothing. A pill
 * that only turns amber has communicated nothing at all.
 */
export const StatusBadge = React.forwardRef<HTMLSpanElement, StatusBadgeProps>(function StatusBadge(
  { tone = 'neutral', live = false, className, children, ...props },
  ref,
) {
  return (
    <span
      ref={ref}
      className={cx('hb-badge', `hb-badge--${tone}`, className)}
      role={live ? 'status' : undefined}
      aria-live={live ? 'polite' : undefined}
      {...props}
    >
      {children}
    </span>
  )
})
