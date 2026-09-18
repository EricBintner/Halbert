// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * WhyChip — provenance citation chip for agent responses.
 *
 * A small chip that appears next to claims in the conversation. On
 * hover/click shows a popover listing evidence refs.  Each ref is
 * clickable — opens the source (file viewer, log viewer, etc).
 */

import { useEffect, useState } from 'react'
import { cx } from '../lib'

export interface ProvenanceRef {
  type:
    | 'log_cursor'
    | 'snapshot_id'
    | 'metric_window'
    | 'path_lines'
    | 'memory_id'
    | 'observation_id'
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

export interface WhyChipProps {
  provenance: ProvenanceRef[]
  onExpand?: (ref: ProvenanceRef) => void
  className?: string
}

/* Inline SVG icons — avoids lucide-react runtime dep */
function BookOpenIcon({ size = 12 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z" />
      <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z" />
    </svg>
  )
}
function FileTextIcon({ size = 14 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z" />
      <polyline points="14 2 14 8 20 8" />
      <line x1="16" y1="13" x2="8" y2="13" />
      <line x1="16" y1="17" x2="8" y2="17" />
      <line x1="10" y1="9" x2="8" y2="9" />
    </svg>
  )
}
function ActivityIcon({ size = 14 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
    </svg>
  )
}
function DatabaseIcon({ size = 14 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <ellipse cx="12" cy="5" rx="9" ry="3" />
      <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3" />
      <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5" />
    </svg>
  )
}
function ClockIcon({ size = 14 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="10" />
      <polyline points="12 6 12 12 16 14" />
    </svg>
  )
}
function ExternalLinkIcon({ size = 12 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
      <polyline points="15 3 21 3 21 9" />
      <line x1="10" y1="14" x2="21" y2="3" />
    </svg>
  )
}

const REF_ICON: Record<string, typeof FileTextIcon> = {
  log_cursor: ClockIcon,
  snapshot_id: DatabaseIcon,
  metric_window: ActivityIcon,
  path_lines: FileTextIcon,
  memory_id: BookOpenIcon,
  observation_id: BookOpenIcon,
}

export function WhyChip({ provenance, onExpand, className }: WhyChipProps) {
  const [expanded, setExpanded] = useState(false)

  // Escape closes it. Without this the popover is dismissable only by pointer:
  // the backdrop is a bare div with an onClick, which a keyboard never reaches,
  // so a keyboard user who opened the chip could not shut it again.
  useEffect(() => {
    if (!expanded) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setExpanded(false)
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [expanded])

  if (!provenance || provenance.length === 0) return null

  const count = provenance.length
  const label = `${count} source${count > 1 ? 's' : ''}`

  return (
    <div className={cx('hb-why-chip', className)} style={{ display: 'inline-flex', position: 'relative' }}>
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="hb-why-chip__trigger"
        title={label}
        // Without this the button's accessible name is the bare count, so a
        // screen reader announces the chip as "3, button" and the reader has
        // no idea what three of anything means. `title` cannot supply the name
        // here: an element with text content takes its name from that text.
        aria-label={label}
        aria-expanded={expanded}
        aria-haspopup="true"
      >
        <BookOpenIcon />
        <span aria-hidden="true">{count}</span>
      </button>

      {expanded && (
        <>
          {/* Backdrop */}
          <div
            style={{ position: 'fixed', inset: 0, zIndex: 40 }}
            onClick={() => setExpanded(false)}
          />
          {/* Popover */}
          <div className="hb-why-chip__popover">
            <div className="hb-why-chip__heading">Evidence and sources</div>
            <div className="hb-why-chip__list">
              {provenance.map((ref) => {
                const Icon = REF_ICON[ref.type] || FileTextIcon
                const expandsInline = Boolean(onExpand) && EXPANDABLE_REF_TYPES.has(ref.type)
                const actionable = expandsInline || Boolean(ref.url)

                const body = (
                  <>
                    <span className="hb-why-chip__ref-icon"><Icon /></span>
                    <span className="hb-why-chip__ref-body">
                      <span className="hb-why-chip__ref-label">{ref.label || ref.ref}</span>
                      <span className="hb-why-chip__ref-id">{ref.ref}</span>
                    </span>
                    {ref.url && (
                      <span className="hb-why-chip__ref-link"><ExternalLinkIcon /></span>
                    )}
                  </>
                )

                // Keyed by what the ref IS, not by its position: keying on the
                // array index remounts every row below one that is removed.
                const key = `${ref.type}:${ref.ref}`

                // A row with nowhere to go is not a control. Rendering it as a
                // button would put it in the tab order and promise a click that
                // does nothing — the popover is already its own detail view.
                if (!actionable) {
                  return (
                    <div key={key} className="hb-why-chip__ref" aria-disabled="true">
                      {body}
                    </div>
                  )
                }

                return (
                  <button
                    key={key}
                    type="button"
                    onClick={() => {
                      if (expandsInline) {
                        onExpand?.(ref)
                      } else if (ref.url) {
                        // noopener/noreferrer: without them the opened tab gets
                        // a handle on this window through window.opener.
                        window.open(ref.url, '_blank', 'noopener,noreferrer')
                      }
                      setExpanded(false)
                    }}
                    className="hb-why-chip__ref"
                  >
                    {body}
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
