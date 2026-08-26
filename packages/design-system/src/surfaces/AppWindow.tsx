// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import * as React from 'react'
import { cx, useId } from '../lib'

export interface AppWindowProps extends Omit<React.HTMLAttributes<HTMLElement>, 'title'> {
  title: React.ReactNode
  /** Right-aligned mono metadata in the header strip: "2 active", "updates every 5s". */
  meta?: React.ReactNode
  footer?: React.ReactNode
  /** The vermilion pulse dot. Off for inert containers. */
  live?: boolean
  /** Collapsible via the header. Uncontrolled unless `collapsed` is supplied. */
  collapsible?: boolean
  collapsed?: boolean
  defaultCollapsed?: boolean
  onCollapsedChange?: (collapsed: boolean) => void
  children: React.ReactNode
}

/**
 * The universal instrument container — an elevated plate with a header strip,
 * a body, and an optional recessed footer tray.
 *
 * Rendered as <section> with aria-labelledby rather than a bare <div>, so a
 * screen-reader user can navigate a dashboard by its plates.
 */
export const AppWindow = React.forwardRef<HTMLElement, AppWindowProps>(function AppWindow(
  {
    title,
    meta,
    footer,
    live = false,
    collapsible = false,
    collapsed,
    defaultCollapsed = false,
    onCollapsedChange,
    className,
    children,
    id,
    ...props
  },
  ref,
) {
  const windowId = useId(id)
  const titleId = `${windowId}-title`
  const bodyId = `${windowId}-body`

  const [internal, setInternal] = React.useState(defaultCollapsed)
  const isControlled = collapsed !== undefined
  const isCollapsed = isControlled ? collapsed : internal

  const toggle = () => {
    const next = !isCollapsed
    if (!isControlled) setInternal(next)
    onCollapsedChange?.(next)
  }

  const heading = (
    <span className="hb-window__title" id={titleId}>
      {live && <span className="hb-window__pulse" aria-hidden="true" />}
      {title}
    </span>
  )

  return (
    <section
      ref={ref}
      id={windowId}
      className={cx('hb-window', isCollapsed && 'is-collapsed', className)}
      aria-labelledby={titleId}
      {...props}
    >
      <header className="hb-window__head">
        {collapsible ? (
          <button
            type="button"
            className="hb-window__toggle"
            aria-expanded={!isCollapsed}
            aria-controls={bodyId}
            onClick={toggle}
          >
            <span className="hb-window__chevron" aria-hidden="true" />
            {heading}
          </button>
        ) : (
          heading
        )}
        {meta && <span className="hb-window__meta">{meta}</span>}
      </header>

      <div className="hb-window__body" id={bodyId} hidden={isCollapsed}>
        {children}
      </div>

      {footer && !isCollapsed && <footer className="hb-window__foot">{footer}</footer>}
    </section>
  )
})
