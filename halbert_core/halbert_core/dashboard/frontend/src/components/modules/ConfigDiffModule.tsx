/**
 * ConfigDiffModule — shows a config file diff inline in the conversation.
 *
 * Phase 8 / T8c.1.
 */

import { useState, useEffect } from 'react'
import { FileText, Loader2 } from 'lucide-react'

interface ConfigDiffModuleProps {
  path?: string
  findingId?: string
}

export default function ConfigDiffModule({ path, findingId }: ConfigDiffModuleProps) {
  const [content, setContent] = useState<string>('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!path) {
      setError('No path provided')
      setLoading(false)
      return
    }

    fetch(`/api/modules/config-diff/data?path=${encodeURIComponent(path)}${findingId ? `&finding_id=${findingId}` : ''}`)
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })
      .then(data => {
        setContent(data.content || '')
        setLoading(false)
      })
      .catch(e => {
        setError(e.message)
        setLoading(false)
      })
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
      <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
        Error: {error}
      </div>
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
