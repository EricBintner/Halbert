// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * Collapsible — lightweight accordion with sticky header and action slots.
 * Does not use Radix — a ~80-line standalone implementation.
 */

import * as React from 'react'
import { cx } from '../lib'

export interface CollapsibleProps {
  title: React.ReactNode
  children: React.ReactNode
  defaultOpen?: boolean
  /** Collapsed summary text. Hidden when open. */
  summary?: React.ReactNode
  className?: string
  headerClassName?: string
  contentClassName?: string
  /** Action buttons shown in the header (clicks don't toggle). */
  actions?: React.ReactNode
  /** Make header sticky when expanded. */
  stickyHeader?: boolean
}

/* Inline SVG chevrons */
function ChevronDown() {
  return (
    <svg width={16} height={16} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <polyline points="6 9 12 15 18 9" />
    </svg>
  )
}
function ChevronRight() {
  return (
    <svg width={16} height={16} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <polyline points="9 18 15 12 9 6" />
    </svg>
  )
}

export function Collapsible({
  title, children, defaultOpen = false,
  summary, className, headerClassName, contentClassName,
  actions, stickyHeader = false,
}: CollapsibleProps) {
  const [isOpen, setIsOpen] = React.useState(defaultOpen)

  return (
    <div className={cx('hb-collapsible', isOpen && 'is-open', className)}>
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className={cx(
          'hb-collapsible__header',
          isOpen && stickyHeader && 'hb-collapsible__header--sticky',
          headerClassName,
        )}
      >
        <span className="hb-collapsible__chevron">
          {isOpen ? <ChevronDown /> : <ChevronRight />}
        </span>
        <span className="hb-collapsible__title-area">
          <span className="hb-collapsible__title">{title}</span>
          {!isOpen && summary && (
            <span className="hb-collapsible__summary">{summary}</span>
          )}
        </span>
        {actions && (
          // eslint-disable-next-line jsx-a11y/click-events-have-key-events, jsx-a11y/no-static-element-interactions
          <span className="hb-collapsible__actions" onClick={(e) => e.stopPropagation()}>
            {actions}
          </span>
        )}
      </button>
      {isOpen && (
        <div className={cx('hb-collapsible__body', contentClassName)}>
          {children}
        </div>
      )}
    </div>
  )
}

export interface CollapsibleGroupProps {
  children: React.ReactNode
  className?: string
}

export function CollapsibleGroup({ children, className }: CollapsibleGroupProps) {
  return (
    <div className={cx('hb-collapsible-group', className)}>
      {children}
    </div>
  )
}
