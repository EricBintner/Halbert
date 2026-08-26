// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * ConfigDiffModule — shows a config file diff inline in the conversation.
 *
 * Phase 8 / T8c.1.
 *
 * Fetch failures and error payloads render a compact error state; HTTP 403
 * (path outside the allowed roots) is surfaced distinctly as a "not allowed"
 * state rather than a generic error.
 */

import { useState, useEffect } from 'react'
import { FileText, Loader2 } from 'lucide-react'
import { ModuleLoadError } from './ModuleLoadError'
import { apiUrl } from '@/lib/apiBase'

interface ConfigDiffModuleProps {
  path?: string
  findingId?: string
}

interface FetchError {
  status?: number
  message: string
}

export default function ConfigDiffModule({ path, findingId }: ConfigDiffModuleProps) {
  const [content, setContent] = useState<string>('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<FetchError | null>(null)

  useEffect(() => {
    if (!path) {
      setError({ message: 'No path provided' })
      setLoading(false)
      return
    }

    let cancelled = false

    fetch(apiUrl(`/api/modules/config-diff/data?path=${encodeURIComponent(path)}${findingId ? `&finding_id=${findingId}` : ''}`))
      .then(async r => {
        const data = await r.json().catch(() => null)
        if (!r.ok) {
          throw {
            status: r.status,
            message: data?.error || `HTTP ${r.status}`,
          } as FetchError
        }
        if (data?.status === 'error') {
          throw { message: data?.error || 'Failed to load config' } as FetchError
        }
        return data
      })
      .then(data => {
        if (cancelled) return
        setContent(data?.content || '')
        setError(null)
        setLoading(false)
      })
      .catch(e => {
        if (cancelled) return
        setError({ status: e?.status, message: e?.message || 'Failed to load config' })
        setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [path, findingId])

  if (loading) {
    return (
      <div className="flex items-center gap-2 rounded-lg border border-border bg-muted/30 p-4 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading config...
      </div>
    )
  }

  if (error) {
    return (
      <ModuleLoadError
        module="config diff"
        status={error.status}
        message={
          error.status === 403
            ? `Path not allowed: ${path}`
            : error.message
        }
      />
    )
  }

  const lines = content.split('\n')

  return (
    <div className="rounded-lg border border-border overflow-hidden">
      <div className="flex items-center gap-2 border-b border-border bg-muted/50 px-3 py-2">
        <FileText className="h-4 w-4 text-muted-foreground" />
        <span className="text-sm font-medium font-mono truncate">{path}</span>
      </div>
      <div className="max-h-[400px] overflow-auto">
        <pre className="text-xs p-3 font-mono leading-relaxed">
          {lines.map((line, i) => (
            <div key={i} className="flex hover:bg-muted/30">
              <span className="select-none text-muted-foreground/50 w-10 text-right pr-3 shrink-0">
                {i + 1}
              </span>
              <span className="whitespace-pre-wrap break-all">{line}</span>
            </div>
          ))}
        </pre>
      </div>
    </div>
  )
}
