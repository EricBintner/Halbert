// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import * as React from 'react'
import { cx } from '../lib'

export interface IconDockItem {
  id: string
  /** Accessible name and tooltip, e.g. "GitHub". Sentence case, no terminal punctuation. */
  label: string
  /** Rendered at 16px in currentColor — a lucide icon, a brand glyph, anything that takes className. */
  icon: React.ComponentType<{ className?: string }>
  /** Renders an anchor. Absolute URLs open in a new tab with rel="noopener noreferrer". */
  href?: string
  /** Renders a button. */
  onClick?: () => void
  /**
   * Renders a native disabled button: announced by name, dimmed, out of the
   * tab order, with a "coming soon" tooltip. An item with neither `href` nor
   * `onClick` is treated the same way — a placeholder for a link that does
   * not exist yet.
   */
  disabled?: boolean
}

export interface IconDockProps extends Omit<React.HTMLAttributes<HTMLElement>, 'children'> {
  items: IconDockItem[]
  /** Accessible name of the dock. @default "Links" */
  label?: string
  orientation?: 'horizontal' | 'vertical'
}

const isExternal = (href: string) => /^https?:\/\//i.test(href)

/**
 * A bare row of icon-only links or actions.
 *
 * No plate, no hairline, no shadow: the glyphs inherit the ink of whatever
 * they sit in, which is what lets a consumer paint a second, masked copy in
 * another ink — the marketing site inverts the dock where the vermilion
 * stroke passes under it, the same way its header logo inverts.
 *
 * Every control is named by `label`; the glyph is decorative. A disabled item
 * is a real disabled <button> rather than a styled span, so assistive tech
 * announces it as dimmed and it never lands in the tab order.
 */
export const IconDock = React.forwardRef<HTMLElement, IconDockProps>(function IconDock(
  { items, label = 'Links', orientation = 'horizontal', className, ...props },
  ref,
) {
  return (
    <nav
      ref={ref}
      className={cx('hb-dock', orientation === 'vertical' && 'hb-dock--vertical', className)}
      aria-label={label}
      {...props}
    >
      {items.map((item) => {
        const Icon = item.icon
        const glyph = (
          <span className="hb-dock__glyph" aria-hidden="true">
            <Icon />
          </span>
        )

        if (item.disabled || (!item.href && !item.onClick)) {
          return (
            <button
              key={item.id}
              type="button"
              className="hb-dock__btn"
              disabled
              aria-label={item.label}
              title={`${item.label} · coming soon`}
            >
              {glyph}
            </button>
          )
        }

        if (item.href) {
          const external = isExternal(item.href)
          return (
            <a
              key={item.id}
              className="hb-dock__btn"
              href={item.href}
              aria-label={item.label}
              title={item.label}
              target={external ? '_blank' : undefined}
              rel={external ? 'noopener noreferrer' : undefined}
            >
              {glyph}
            </a>
          )
        }

        return (
          <button
            key={item.id}
            type="button"
            className="hb-dock__btn"
            aria-label={item.label}
            title={item.label}
            onClick={item.onClick}
          >
            {glyph}
          </button>
        )
      })}
    </nav>
  )
})
