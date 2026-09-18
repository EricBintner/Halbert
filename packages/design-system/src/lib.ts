// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import * as React from 'react'

/** Join class names, dropping falsy entries. No dependency needed for this. */
export function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(' ')
}

/**
 * Minimal `asChild` support.
 *
 * The roadmap specifies Radix Slot for Button. This does the same job in ~20
 * lines without adding a runtime dependency, which matters here: the library is
 * consumed by one app on React 18 and another on React 19, so every dependency
 * is a version-range negotiation across both.
 */
export const Slot = React.forwardRef<HTMLElement, React.HTMLAttributes<HTMLElement> & { children?: React.ReactNode }>(
  function Slot({ children, ...slotProps }, ref) {
    if (!React.isValidElement(children)) return null
    const child = children as React.ReactElement<Record<string, unknown>>
    const childProps = child.props

    return React.cloneElement(child, {
      ...slotProps,
      ...childProps,
      // Merge rather than clobber: the caller's className and the child's both matter.
      className: cx(slotProps.className as string, childProps.className as string),
      style: { ...(slotProps.style as object), ...(childProps.style as object) },
      ref,
    } as Record<string, unknown>)
  },
)

/** Stable id for label/description wiring, with a React 18 fallback. */
export function useId(provided?: string): string {
  const generated = React.useId()
  return provided ?? generated
}
