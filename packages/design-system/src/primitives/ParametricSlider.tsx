// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import * as React from 'react'
import { cx, useId } from '../lib'

export interface ParametricSliderProps
  extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'value' | 'onChange' | 'type' | 'size'> {
  label: string
  value: number
  onValueChange: (value: number) => void
  min?: number
  max?: number
  step?: number
  /** Formats the value for display, e.g. (v) => `${v} GB`. */
  formatValue?: (value: number) => string
  /**
   * The consequence of the current value, in words — "16 GB left for
   * everything else". This is the "parametric" half: the control shows what
   * the setting DOES, not just what it is.
   */
  preview?: (value: number) => React.ReactNode
  /**
   * Spoken form, when the display string is not what a screen reader should
   * hear. Falls back to formatValue, then to the bare number.
   */
  ariaValueText?: (value: number) => string
  /** Values past this point are flagged as risky. */
  cautionAbove?: number
}

/**
 * Headroom preview slider — ZFS ARC sizing, swappiness, cache budgets.
 *
 * Built on a native <input type="range"> rather than a div with role="slider".
 * The native control brings arrow keys, Home/End, PageUp/PageDown, touch
 * dragging, and correct screen-reader semantics already working and correct on
 * every platform. Re-implementing that by hand is a large accessibility
 * surface to own in exchange for styling freedom CSS already provides.
 *
 * The preview text is deliberately NOT an aria-live region. It changes on every
 * keystroke of an arrow key, and a live region here would produce a torrent of
 * interruptions; aria-valuetext on the input carries the same information at
 * exactly the rate a screen reader wants it.
 */
export const ParametricSlider = React.forwardRef<HTMLInputElement, ParametricSliderProps>(
  function ParametricSlider(
    {
      label,
      value,
      onValueChange,
      min = 0,
      max = 100,
      step = 1,
      formatValue,
      preview,
      ariaValueText,
      cautionAbove,
      className,
      id,
      disabled,
      ...props
    },
    ref,
  ) {
    const sliderId = useId(id)
    const previewId = `${sliderId}-preview`

    const display = formatValue ? formatValue(value) : String(value)
    const spoken = ariaValueText ? ariaValueText(value) : display
    const isCaution = cautionAbove != null && value > cautionAbove

    // Guard against a zero-width range producing NaN in the fill percentage.
    const span = max - min
    const pct = span > 0 ? ((value - min) / span) * 100 : 0

    return (
      <div className={cx('hb-slider', isCaution && 'is-caution', disabled && 'is-disabled', className)}>
        <div className="hb-slider__head">
          <label className="hb-slider__label" htmlFor={sliderId}>
            {label}
          </label>
          <output className="hb-slider__value" htmlFor={sliderId} aria-hidden="true">
            {display}
          </output>
        </div>

        <input
          ref={ref}
          id={sliderId}
          className="hb-slider__input"
          type="range"
          min={min}
          max={max}
          step={step}
          value={value}
          disabled={disabled}
          aria-valuetext={spoken}
          aria-describedby={preview ? previewId : undefined}
          style={{ ['--hb-slider-pct' as string]: `${pct}%` }}
          onChange={(event) => onValueChange(Number(event.target.value))}
          {...props}
        />

        {preview && (
          <p className="hb-slider__preview" id={previewId}>
            {preview(value)}
          </p>
        )}
      </div>
    )
  },
)
