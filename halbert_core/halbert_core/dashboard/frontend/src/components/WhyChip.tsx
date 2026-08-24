/**
 * WhyChip — provenance citation chip for agent responses.
 *
 * A small chip/icon that appears next to claims in the conversation.
 * On hover/click, shows a popover with the provenance refs.
 * Each ref is clickable — opens the source (file viewer, log viewer, etc).
 *
 * Phase 8 / T8a.3.
 */

import { useState } from 'react'
import { BookOpen, FileText, Activity, Database, Clock, ExternalLink } from 'lucide-react'

export interface ProvenanceRef {
  type: 'log_cursor' | 'snapshot_id' | 'metric_window' | 'path_lines' | 'memory_id' | 'observation_id'
  ref: string
  label: string
  url?: string
}

/**
 * Ref types that resolve to an inline module expansion. Everything else
 * (memory_id, observation_id) keeps the popover itself as the detail view.
 */
const EXPANDABLE_REF_TYPES = new Set<ProvenanceRef['type']>([
  'log_cursor',
  'metric_window',
  'path_lines',
  'snapshot_id',
])

interface WhyChipProps {
  provenance: ProvenanceRef[]
  onExpand?: (ref: ProvenanceRef) => void
}

const REF_ICONS: Record<string, typeof FileText> = {
  log_cursor: Clock,
  snapshot_id: Database,
  metric_window: Activity,
  path_lines: FileText,
  memory_id: BookOpen,
  observation_id: BookOpen,
}

export function WhyChip({ provenance, onExpand }: WhyChipProps) {
  const [expanded, setExpanded] = useState(false)

  if (!provenance || provenance.length === 0) {
    return null
  }

  return (
    <div className="inline-flex relative">
      <button
        onClick={() => setExpanded(!expanded)}
        className="inline-flex items-center gap-1 rounded-full border border-border bg-muted/50 px-2 py-0.5 text-xs text-muted-foreground hover:bg-muted transition-colors"
        title={`${provenance.length} provenance ref${provenance.length > 1 ? 's' : ''}`}
      >
        <BookOpen className="h-3 w-3" />
        <span>{provenance.length}</span>
      </button>

      {expanded && (
        <>
          {/* Backdrop to close on outside click */}
          <div
            className="fixed inset-0 z-40"
            onClick={() => setExpanded(false)}
          />

          {/* Popover */}
          <div className="absolute z-50 mt-1 min-w-[240px] max-w-[400px] rounded-lg border border-border bg-popover p-3 shadow-lg">
            <div className="text-xs font-medium text-muted-foreground mb-2">
              Evidence & Sources
            </div>
            <div className="space-y-1.5">
              {provenance.map((ref, i) => {
                const Icon = REF_ICONS[ref.type] || FileText
                return (
                  <button
                    key={i}
                    onClick={() => {
                      if (onExpand && EXPANDABLE_REF_TYPES.has(ref.type)) {
                        onExpand(ref)
                        setExpanded(false)
                      } else if (ref.url) {
                        window.open(ref.url, '_blank')
                        setExpanded(false)
                      }
                      // memory_id / observation_id without a url keep the
                      // popover open — the popover is itself the detail view.
                    }}
                    className="flex w-full items-start gap-2 rounded-md p-1.5 text-left text-xs hover:bg-muted transition-colors"
                  >
                    <Icon className="h-3.5 w-3.5 mt-0.5 shrink-0 text-muted-foreground" />
                    <div className="flex-1 min-w-0">
                      <div className="font-medium text-foreground truncate">
                        {ref.label || ref.ref}
                      </div>
                      <div className="text-muted-foreground truncate font-mono text-[10px]">
                        {ref.ref}
                      </div>
                    </div>
                    {ref.url && (
                      <ExternalLink className="h-3 w-3 shrink-0 text-muted-foreground" />
                    )}
                  </button>
                )
              })}
            </div>
          </div>
        </>
      )}
    </div>
  )
}
