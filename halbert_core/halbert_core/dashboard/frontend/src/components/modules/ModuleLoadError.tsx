// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * ModuleLoadError — compact "couldn't load <module>" state shared by all
 * inline conversation modules. HTTP 403 (path/source not allowed) renders
 * distinctly with a lock icon and "not allowed" wording.
 */

import { AlertCircle, Lock } from 'lucide-react'

interface ModuleLoadErrorProps {
  /** Human-readable module name, e.g. "config diff". */
  module: string
  /** HTTP status of the failed fetch, when known. */
  status?: number
  /** Server-supplied detail, when available. */
  message?: string
}

export function ModuleLoadError({ module, status, message }: ModuleLoadErrorProps) {
  const forbidden = status === 403
  const Icon = forbidden ? Lock : AlertCircle
  const text = forbidden
    ? message || `${module} not allowed`
    : message || `Couldn't load ${module}`

  return (
    <div className="flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs text-destructive">
      <Icon className="h-3.5 w-3.5 shrink-0" />
      <span className="break-words">{text}</span>
      {status !== undefined && (
        <span className="ml-auto shrink-0 text-destructive/70 font-mono">HTTP {status}</span>
      )}
    </div>
  )
}
