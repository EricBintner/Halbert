/**
 * EvidenceModule — log excerpt viewer with highlighting.
 *
 * Phase 8 / T8c.4.
 *
 * Fetch failures and error payloads render a compact error state (HTTP 403 =
 * "log source not allowed") instead of an empty log box or endless spinner.
 */

import { useState, useEffect } from 'react'
import { BookOpen, Loader2, Search } from 'lucide-react'
import { ModuleLoadError } from './ModuleLoadError'
import { apiUrl } from '@/lib/apiBase'

interface EvidenceModuleProps {
  source?: string
  cursor?: string
  query?: string
}

interface FetchError {
  status?: number
  message: string
}

export default function EvidenceModule({ source, cursor, query }: EvidenceModuleProps) {
  const [lines, setLines] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [fetchError, setFetchError] = useState<FetchError | null>(null)
  const [note, setNote] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState(query || '')

  useEffect(() => {
    if (!source) {
      setFetchError({ message: 'No evidence source provided' })
      setLoading(false)
      return
    }

    let cancelled = false

    const params = new URLSearchParams({ source })
    if (cursor) params.set('cursor', cursor)
    if (searchQuery) params.set('query', searchQuery)

    fetch(apiUrl(`/api/modules/evidence/data?${params}`))
      .then(async r => {
        const data = await r.json().catch(() => null)
        if (!r.ok) {
          const err: FetchError = {
            status: r.status,
            message: data?.error || data?.note || `HTTP ${r.status}`,
          }
          throw err
        }
        if (data?.status && data.status !== 'ok') {
          throw { message: data?.error || `Unexpected status: ${data.status}` } as FetchError
        }
        return data
      })
      .then(data => {
        if (cancelled) return
        setLines(data?.lines || [])
        setNote(data?.note || null)
        setFetchError(null)
        setLoading(false)
      })
      .catch(e => {
        if (cancelled) return
        setFetchError({ status: e?.status, message: e?.message || 'Failed to load evidence' })
        setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [source, cursor, searchQuery])

  if (loading) {
    return (
      <div className="flex items-center gap-2 rounded-lg border border-border bg-muted/30 p-4 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading evidence...
      </div>
    )
  }

  if (fetchError) {
    return (
      <ModuleLoadError
        module="evidence"
        status={fetchError.status}
        message={
          fetchError.status === 403
            ? `Log source not allowed: ${source}`
            : fetchError.message
        }
      />
    )
  }

  return (
    <div className="rounded-lg border border-border overflow-hidden">
      <div className="flex items-center gap-2 border-b border-border bg-muted/50 px-3 py-2">
        <BookOpen className="h-4 w-4 text-muted-foreground" />
        <span className="text-sm font-medium">Evidence</span>
        <span className="text-xs text-muted-foreground font-mono truncate ml-auto">{source}</span>
      </div>

      {searchQuery !== undefined && (
        <div className="flex items-center gap-2 border-b border-border px-3 py-2">
          <Search className="h-3.5 w-3.5 text-muted-foreground" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Filter logs..."
            className="flex-1 bg-transparent text-xs outline-none placeholder:text-muted-foreground"
          />
        </div>
      )}

      <div className="max-h-[300px] overflow-auto">
        {lines.length === 0 ? (
          <div className="p-4 text-sm text-muted-foreground">
            {note || 'No log lines found'}
          </div>
        ) : (
          <pre className="text-xs p-2 font-mono leading-relaxed">
            {lines.map((line) => (
              <div
                key={line.line_no}
                className="flex hover:bg-muted/30 py-0.5"
              >
                <span className="select-none text-muted-foreground/50 w-10 text-right pr-2 shrink-0">
                  {line.line_no}
                </span>
                <span className="whitespace-pre-wrap break-all">{line.content}</span>
              </div>
            ))}
          </pre>
        )}
      </div>
    </div>
  )
}
