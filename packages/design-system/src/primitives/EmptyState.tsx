// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * EmptyState — consistent "no items found" placeholder for any page/section.
 */

import * as React from 'react'
import { cx } from '../lib'

export interface EmptyStateProps {
  /** Custom icon node. Falls back to a default inbox SVG. */
  icon?: React.ReactNode
  /** Title text (e.g., "No Backups Found") */
  title: string
  /** Description text */
  description?: string
  /** Action element (button, link, etc.) */
  action?: React.ReactNode
  className?: string
}

function DefaultIcon() {
  return (
    <svg width={48} height={48} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <polyline points="22 12 16 12 14 15 10 15 8 12 2 12" />
      <path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z" />
    </svg>
  )
}

export function EmptyState({ icon, title, description, action, className }: EmptyStateProps) {
  return (
    <div className={cx('hb-empty-state', className)}>
      <div className="hb-empty-state__icon">
        {icon || <DefaultIcon />}
      </div>
      <h3 className="hb-empty-state__title">{title}</h3>
      {description && (
        <p className="hb-empty-state__description">{description}</p>
      )}
      {action && (
        <div className="hb-empty-state__action">{action}</div>
      )}
    </div>
  )
}
