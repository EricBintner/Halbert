// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import * as React from 'react'
import { cx } from '../lib'

export type StatusTone = 'nominal' | 'warning' | 'critical' | 'telemetry' | 'neutral'

/** Convenience aliases so dashboard consumers don't have to translate. */
type ToneAlias = 'success' | 'error' | 'danger' | 'info'

const TONE_ALIAS: Record<ToneAlias, StatusTone> = {
  success: 'nominal',
  error: 'critical',
  danger: 'critical',
  info: 'telemetry',
}

function resolveTone(tone: StatusTone | ToneAlias): StatusTone {
  return (TONE_ALIAS as Record<string, StatusTone>)[tone] ?? tone
}

export interface StatusBadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  tone?: StatusTone | ToneAlias
  /**
   * Announce the state to assistive tech as it changes. Use for values that
   * update in place (a host going from Nominal to Critical), not for static
   * labels — a page of live regions is a page that never stops talking.
   */
  live?: boolean
  /** Optional icon placed before children. */
  icon?: React.ReactNode
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
  { tone = 'neutral', live = false, icon, className, children, ...props },
  ref,
) {
  const resolved = resolveTone(tone)
  return (
    <span
      ref={ref}
      className={cx('hb-badge', `hb-badge--${resolved}`, className)}
      role={live ? 'status' : undefined}
      aria-live={live ? 'polite' : undefined}
      {...props}
    >
      {icon && <span className="hb-badge__icon" aria-hidden="true">{icon}</span>}
      {children}
    </span>
  )
})

