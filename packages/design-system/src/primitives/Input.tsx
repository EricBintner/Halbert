// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import * as React from 'react'
import { cx, useId } from '../lib'

export interface InputProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'size'> {
  label: string
  /** Visually hide the label but keep it for assistive tech. */
  hideLabel?: boolean
  hint?: string
  error?: string
  /** Render in the tabular mono face — for paths, sizes, identifiers. */
  mono?: boolean
}

/**
 * Tactile form field matching the AppWindow treatment.
 *
 * `label` is required. A placeholder is not a label: it disappears on focus,
 * fails 3.3.2, and --color-ink-ghost is not licensed for text that must be
 * read. Placeholders here are supplementary only.
 */
export const Input = React.forwardRef<HTMLInputElement, InputProps>(function Input(
  { label, hideLabel = false, hint, error, mono = false, className, id, ...props },
  ref,
) {
  const inputId = useId(id)
  const hintId = `${inputId}-hint`
  const errorId = `${inputId}-error`

  const describedBy = [hint ? hintId : null, error ? errorId : null].filter(Boolean).join(' ') || undefined

  return (
    <div className={cx('hb-field', error && 'is-invalid', className)}>
      <label className={cx('hb-field__label', hideLabel && 'hb-visually-hidden')} htmlFor={inputId}>
        {label}
      </label>
      <input
        ref={ref}
        id={inputId}
        className={cx('hb-input', mono && 'hb-input--mono')}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        {...props}
      />
      {hint && !error && (
        <p className="hb-field__hint" id={hintId}>
          {hint}
        </p>
      )}
      {error && (
        // role=alert so a validation failure is announced when it appears.
        <p className="hb-field__error" id={errorId} role="alert">
          {error}
        </p>
      )}
    </div>
  )
})
