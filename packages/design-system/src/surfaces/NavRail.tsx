// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import * as React from 'react'
import { cx, useId } from '../lib'

export interface NavRailItem {
  id: string
  label: string
  /** Icon component rendered at 16px. Pass a lucide icon or any component accepting className. */
  icon?: React.ComponentType<{ className?: string }>
}

export interface NavRailSection {
  id: string
  label: string
  items: NavRailItem[]
}

export interface NavRailProps extends Omit<React.HTMLAttributes<HTMLElement>, 'title' | 'onSelect'> {
  sections: NavRailSection[]
  /** The id of the active item, matched against `NavRailItem.id`. */
  activeId: string
  /** Called with the item id when an item is activated. */
  onSelect: (id: string) => void
  /** Optional node rendered at the very top — a back button, a brand mark, etc. */
  header?: React.ReactNode
  /** Renders a filter input below the header. Filtering is handled internally. */
  searchable?: boolean
  searchPlaceholder?: string
  /**
   * Tab semantics. When true, the item list gets `role="tablist"` and each item
   * gets `role="tab"` with `aria-selected`, so a settings panel reads as tabs
   * rather than navigation. The active id is still driven by the consumer.
   */
  tabMode?: boolean
}

/**
 * The shared left navigation rail.
 *
 * One component, one set of classes, two consumers: the dashboard page rail and
 * the settings panel rail. Because the typography lives here and not in two
 * copy-pasted Tailwind class strings, the two rails cannot drift apart — which
 * is the defect this component exists to close.
 *
 * Plain CSS on the shared token variables, like every other surface in this
 * library: the dashboard runs Tailwind v3 and the marketing site Tailwind v4,
 * so utility classes in library source would scan differently across the majors.
 * Tokens are the portable layer.
 */
export const NavRail = React.forwardRef<HTMLElement, NavRailProps>(function NavRail(
  {
    sections,
    activeId,
    onSelect,
    header,
    searchable = false,
    searchPlaceholder = 'Filter…',
    tabMode = false,
    className,
    id,
    ...props
  },
  ref,
) {
  const railId = useId(id)
  const [query, setQuery] = React.useState('')

  const filtered = React.useMemo(() => {
    if (!query.trim()) return sections
    const q = query.toLowerCase()
    return sections
      .map((section) => ({
        ...section,
        items: section.items.filter(
          (item) =>
            item.label.toLowerCase().includes(q) ||
            section.label.toLowerCase().includes(q) ||
            item.id.includes(q),
        ),
      }))
      .filter((section) => section.items.length > 0)
  }, [sections, query])

  return (
    <nav
      ref={ref}
      id={railId}
      className={cx('hb-navrail', className)}
      aria-label={tabMode ? 'Settings sections' : 'Navigation'}
      {...props}
    >
      {header && <div className="hb-navrail__header">{header}</div>}

      {searchable && (
        <div className="hb-navrail__search">
          <svg className="hb-navrail__search-icon" viewBox="0 0 24 24" aria-hidden="true">
            <path
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              d="m21 21-4.3-4.3M11 19a8 8 0 1 1 0-16 8 8 0 0 1 0 16Z"
            />
          </svg>
          <input
            type="text"
            className="hb-navrail__search-input"
            placeholder={searchPlaceholder}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Escape') setQuery('')
            }}
            aria-label={searchPlaceholder}
          />
        </div>
      )}

      <div
        className="hb-navrail__sections"
        role={tabMode ? 'tablist' : undefined}
        aria-orientation={tabMode ? 'vertical' : undefined}
      >
        {filtered.map((section) => (
          <div key={section.id} className="hb-navrail__section">
            <p className="hb-navrail__section-label">{section.label}</p>
            {section.items.map((item) => {
              const isActive = item.id === activeId
              const Icon = item.icon
              return (
                <button
                  key={item.id}
                  type="button"
                  role={tabMode ? 'tab' : undefined}
                  aria-selected={tabMode ? isActive : undefined}
                  data-active={isActive}
                  className="hb-navrail__item"
                  onClick={() => onSelect(item.id)}
                >
                  {Icon && <Icon className="hb-navrail__icon" />}
                  <span className="hb-navrail__label">{item.label}</span>
                </button>
              )
            })}
          </div>
        ))}
      </div>
    </nav>
  )
})
