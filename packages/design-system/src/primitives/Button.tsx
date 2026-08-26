// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import * as React from 'react'
import { cx, Slot } from '../lib'

export type ButtonVariant = 'primary' | 'outline' | 'ghost' | 'danger'
export type ButtonSize = 'sm' | 'md' | 'lg'

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  size?: ButtonSize
  /** Renders a spinner, sets aria-busy, and blocks activation. */
  loading?: boolean
  /** Merge props onto the single child element instead of rendering a <button>. */
  asChild?: boolean
}

/**
 * The primary action control.
 *
 * `primary` fills with --color-accent-strong, NOT --color-accent. The brand
 * shade measures 4.30:1 against white and fails AA as a text-bearing fill; the
 * strong shade is the licensed one at 4.98:1. See the Surface Licence in
 * documentation/design/BRAND-GUIDELINES-AND-AESTHETIC.md §3.1.
 *
 * `danger` is deliberately a different red from `primary`. Vermilion means
 * "act"; critical means "something is wrong". A vermilion delete button reads
 * as encouragement.
 */
export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = 'outline', size = 'md', loading = false, asChild = false, className, children, disabled, onClick, ...props },
  ref,
) {
  const isDisabled = disabled || loading

  const handleClick = (event: React.MouseEvent<HTMLElement>) => {
    // A loading button must not fire twice. `asChild` targets an arbitrary
    // element — often an <a>, which has no `disabled` attribute to lean on —
    // so the guard lives here rather than relying on the DOM.
    if (isDisabled) {
      event.preventDefault()
      return
    }
    onClick?.(event as React.MouseEvent<HTMLButtonElement>)
  }

  const shared = {
    className: cx('hb-btn', `hb-btn--${variant}`, `hb-btn--${size}`, loading && 'is-loading', className),
    'aria-busy': loading || undefined,
    onClick: handleClick,
  }

  const decorate = (label: React.ReactNode) => (
    <>
      {loading && <span className="hb-btn__spinner" aria-hidden="true" />}
      <span className="hb-btn__label">{label}</span>
    </>
  )

  if (asChild) {
    // Graft the spinner and label wrapper into the child's own children, then
    // let Slot merge our props onto it. Passing the decorated content to Slot
    // directly would hand it a fragment, which is not a single element.
    const child = React.Children.only(children) as React.ReactElement<{ children?: React.ReactNode }>
    return (
      <Slot ref={ref as React.Ref<HTMLElement>} {...shared} aria-disabled={isDisabled || undefined} {...props}>
        {React.cloneElement(child, undefined, decorate(child.props.children))}
      </Slot>
    )
  }

  return (
    <button ref={ref} type="button" {...shared} disabled={isDisabled} {...props}>
      {decorate(children)}
    </button>
  )
})
