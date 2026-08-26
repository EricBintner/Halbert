// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import * as React from 'react'
import { cx, useId } from '../lib'

export interface SelectOption {
  value: string
  label: string
  disabled?: boolean
}

export interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  label: string
  hideLabel?: boolean
  hint?: string
  error?: string
  options: SelectOption[]
  placeholder?: string
}

/**
 * A styled native <select>.
 *
 * Deliberately native rather than a custom listbox: keyboard behaviour, type-
 * ahead, screen-reader semantics, and mobile pickers all come free and correct.
 * A hand-rolled listbox is a large accessibility surface to own for a control
 * whose native version already matches the aesthetic once it is skinned.
 */
export const Select = React.forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { label, hideLabel = false, hint, error, options, placeholder, className, id, ...props },
  ref,
) {
  const selectId = useId(id)
  const hintId = `${selectId}-hint`
  const errorId = `${selectId}-error`
  const describedBy = [hint ? hintId : null, error ? errorId : null].filter(Boolean).join(' ') || undefined

  return (
    <div className={cx('hb-field', error && 'is-invalid', className)}>
      <label className={cx('hb-field__label', hideLabel && 'hb-visually-hidden')} htmlFor={selectId}>
        {label}
      </label>
      <div className="hb-select__wrap">
        <select
          ref={ref}
          id={selectId}
          className="hb-select"
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          {...props}
        >
          {placeholder && (
            <option value="" disabled>
              {placeholder}
            </option>
          )}
          {options.map((option) => (
            <option key={option.value} value={option.value} disabled={option.disabled}>
              {option.label}
            </option>
          ))}
        </select>
        <span className="hb-select__chevron" aria-hidden="true" />
      </div>
      {hint && !error && (
        <p className="hb-field__hint" id={hintId}>
          {hint}
        </p>
      )}
      {error && (
        <p className="hb-field__error" id={errorId} role="alert">
          {error}
        </p>
      )}
    </div>
  )
})
