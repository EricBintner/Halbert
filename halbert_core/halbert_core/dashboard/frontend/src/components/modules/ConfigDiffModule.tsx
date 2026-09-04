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

/** The recorded change, as `/api/state/why` returns it. */
interface WhyRecord {
  reason: string
  actor: string
  valid_from: number
}

export default function ConfigDiffModule({ path, findingId }: ConfigDiffModuleProps) {
  const [content, setContent] = useState<string>('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<FetchError | null>(null)
  // What the change ledger recorded about this file, fetched independently:
  // the diff must still render when the ledger has nothing, and "nothing
  // recorded" is a legitimate answer rather than a failure.
  const [why, setWhy] = useState<WhyRecord | null>(null)

  useEffect(() => {
    if (!path) {
      setError({ message: 'No path provided' })
      setLoading(false)
      return
    }

    let cancelled = false

    // Independent of the diff fetch on purpose. A ledger that is empty,
    // unreachable or answering 503 must not stop the file rendering.
    setWhy(null)
    fetch(apiUrl(`/api/state/why?path=${encodeURIComponent(path)}`))
      .then(r => (r.ok ? r.json() : null))
      .then(d => {
        if (cancelled || !d?.found || !d?.current) return
        setWhy({
          reason: d.current.reason,
          actor: d.current.actor,
          valid_from: d.current.valid_from,
        })
      })
      .catch(() => { /* no record is a normal answer, not an error */ })

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

  // Deliberately not a before/after diff. The ledger stores content digests,
  // not content, so it cannot reconstruct the previous text — and rendering
  // two digests as a "diff" would look like one without being one. What it
  // can say truthfully is who changed this, when, and why.
  const recordedWhy = why && (
    <div className="border-b border-border bg-muted/20 px-3 py-2 text-xs text-muted-foreground">
      <span className="font-medium text-foreground">
        {why.reason === 'unrecorded'
          ? 'No reason was recorded for the last change'
          : why.reason}
      </span>
      {' — '}
      changed by {why.actor}
      {Number.isFinite(why.valid_from) && (
        <> on {new Date(why.valid_from * 1000).toLocaleString()}</>
      )}
    </div>
  )

  return (
    <div className="rounded-lg border border-border overflow-hidden">
      {recordedWhy}
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
