/**
 * EvidenceModule — log excerpt viewer with highlighting.
 *
 * Phase 8 / T8c.4.
 */

import { useState, useEffect } from 'react'
import { BookOpen, Loader2, Search } from 'lucide-react'

interface EvidenceModuleProps {
  source?: string
  cursor?: string
  query?: string
}

export default function EvidenceModule({ source, cursor, query }: EvidenceModuleProps) {
  const [lines, setLines] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState(query || '')

  useEffect(() => {
    if (!source) {
      setError('No source provided')
      setLoading(false)
      return
    }

    const params = new URLSearchParams({ source })
    if (cursor) params.set('cursor', cursor)
    if (searchQuery) params.set('query', searchQuery)

    fetch(`/api/modules/evidence/data?${params}`)
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })
      .then(data => {
        if (data.status === 'ok') {
          setLines(data.lines || [])
          setError(data.note || null)
        }
        setLoading(false)
      })
      .catch(e => {
        setError(e.message)
        setLoading(false)
      })
  }, [source, cursor, searchQuery])

  if (loading) {
    return (
      <div className="flex items-center gap-2 rounded-lg border border-border bg-muted/30 p-4 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading evidence...
      </div>
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
            {error || 'No log lines found'}
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
