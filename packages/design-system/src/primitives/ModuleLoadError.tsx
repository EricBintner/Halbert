// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * ModuleLoadError — compact "couldn't load <module>" state.
 * HTTP 403 renders distinctly with a lock icon.
 */

import { cx } from '../lib'

export interface ModuleLoadErrorProps {
  /** Human-readable module name, e.g. "config diff". */
  module: string
  /** HTTP status of the failed fetch, when known. */
  status?: number
  /** Server-supplied detail, when available. */
  message?: string
  className?: string
}

/* Inline SVG icons */
function AlertCircleIcon() {
  return (
    <svg width={14} height={14} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="10" />
      <line x1="12" y1="8" x2="12" y2="12" />
      <line x1="12" y1="16" x2="12.01" y2="16" />
    </svg>
  )
}
function LockIcon() {
  return (
    <svg width={14} height={14} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
      <path d="M7 11V7a5 5 0 0 1 10 0v4" />
    </svg>
  )
}

export function ModuleLoadError({ module, status, message, className }: ModuleLoadErrorProps) {
  const forbidden = status === 403
  const text = forbidden
    ? message || `${module} not allowed`
    : message || `Couldn't load ${module}`

  return (
    <div className={cx('hb-module-error', forbidden && 'hb-module-error--forbidden', className)} role="alert">
      <span className="hb-module-error__icon">
        {forbidden ? <LockIcon /> : <AlertCircleIcon />}
      </span>
      <span className="hb-module-error__text">{text}</span>
      {status !== undefined && (
        <span className="hb-module-error__code">HTTP {status}</span>
      )}
    </div>
  )
}
