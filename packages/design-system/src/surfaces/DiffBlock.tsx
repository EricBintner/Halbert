// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * DiffBlock — code change viewer with Apply/Reject actions.
 * Includes a simplified line-by-line diff algorithm and a DiffSummary bar.
 */

import { useState } from 'react'
import { cx } from '../lib'

export interface DiffBlockProps {
  filePath: string
  oldContent?: string
  newContent: string
  additions?: number
  deletions?: number
  onApply: () => void
  onReject: () => void
  status?: 'pending' | 'applied' | 'rejected'
  /** Stored turn: pending diff is a record, not a choice. */
  readOnly?: boolean
  className?: string
}

/* Inline SVG micro-icons */
function CheckIcon() {
  return (
    <svg width={10} height={10} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={3} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <polyline points="20 6 9 17 4 12" />
    </svg>
  )
}
function XIcon() {
  return (
    <svg width={10} height={10} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={3} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  )
}
function ChevronDown() {
  return (
    <svg width={12} height={12} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <polyline points="6 9 12 15 18 9" />
    </svg>
  )
}
function ChevronUp() {
  return (
    <svg width={12} height={12} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <polyline points="18 15 12 9 6 15" />
    </svg>
  )
}
function FileIcon() {
  return (
    <svg width={12} height={12} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z" />
      <polyline points="14 2 14 8 20 8" />
    </svg>
  )
}
function GitBranchIcon() {
  return (
    <svg width={12} height={12} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <line x1="6" y1="3" x2="6" y2="15" /><circle cx="18" cy="6" r="3" /><circle cx="6" cy="18" r="3" /><path d="M18 9a9 9 0 0 1-9 9" />
    </svg>
  )
}

export function DiffBlock({
  filePath, oldContent, newContent,
  additions = 0, deletions = 0,
  onApply, onReject,
  status = 'pending', readOnly = false, className,
}: DiffBlockProps) {
  const [isExpanded, setIsExpanded] = useState(true)

  const renderUnifiedDiff = () => {
    if (!oldContent) {
      return newContent.split('\n').map((line, i) => (
        <div key={i} className="hb-diff__line hb-diff__line--add">
          <span className="hb-diff__ln">{i + 1}</span>
          <span className="hb-diff__code">+ {line}</span>
        </div>
      ))
    }

    const oldLines = oldContent.split('\n')
    const newLines = newContent.split('\n')
    const diffLines: Array<{ type: 'context' | 'add' | 'remove'; content: string; lineNum?: number }> = []
    let oldIdx = 0, newIdx = 0

    while (oldIdx < oldLines.length || newIdx < newLines.length) {
      if (oldIdx >= oldLines.length) {
        diffLines.push({ type: 'add', content: newLines[newIdx], lineNum: newIdx + 1 }); newIdx++
      } else if (newIdx >= newLines.length) {
        diffLines.push({ type: 'remove', content: oldLines[oldIdx], lineNum: oldIdx + 1 }); oldIdx++
      } else if (oldLines[oldIdx] === newLines[newIdx]) {
        diffLines.push({ type: 'context', content: oldLines[oldIdx], lineNum: oldIdx + 1 }); oldIdx++; newIdx++
      } else {
        diffLines.push({ type: 'remove', content: oldLines[oldIdx], lineNum: oldIdx + 1 })
        diffLines.push({ type: 'add', content: newLines[newIdx], lineNum: newIdx + 1 }); oldIdx++; newIdx++
      }
    }

    return diffLines.map((line, i) => (
      <div key={i} className={cx('hb-diff__line', `hb-diff__line--${line.type}`)}>
        <span className="hb-diff__ln">{line.lineNum}</span>
        <span className="hb-diff__code">
          {line.type === 'add' ? '+' : line.type === 'remove' ? '-' : ' '} {line.content}
        </span>
      </div>
    ))
  }

  return (
    <div className={cx('hb-diff', `hb-diff--${status}`, className)}>
      {/* Header */}
      <div className="hb-diff__header">
        <span className="hb-diff__file">
          <FileIcon />
          <span className="hb-diff__path">{filePath}</span>
          {additions > 0 && <span className="hb-diff__stat hb-diff__stat--add">+{additions}</span>}
          {deletions > 0 && <span className="hb-diff__stat hb-diff__stat--del">-{deletions}</span>}
        </span>

        <span className="hb-diff__actions">
          {status === 'pending' && readOnly && (
            <span className="hb-diff__label">proposed</span>
          )}
          {status === 'pending' && !readOnly && (
            <>
              <button onClick={onReject} className="hb-diff__btn hb-diff__btn--reject"><XIcon /> Reject</button>
              <button onClick={onApply} className="hb-diff__btn hb-diff__btn--apply"><CheckIcon /> Apply</button>
            </>
          )}
          {status === 'applied' && (
            <span className="hb-diff__label hb-diff__label--applied"><CheckIcon /> Applied</span>
          )}
          {status === 'rejected' && (
            <span className="hb-diff__label hb-diff__label--rejected"><XIcon /> Rejected</span>
          )}
          <button onClick={() => setIsExpanded(!isExpanded)} className="hb-diff__expand-btn">
            {isExpanded ? <ChevronUp /> : <ChevronDown />}
          </button>
        </span>
      </div>

      {isExpanded && (
        <pre className="hb-diff__body">{renderUnifiedDiff()}</pre>
      )}
    </div>
  )
}

/* ---- DiffSummary ---- */

export interface DiffSummaryProps {
  diffs: Array<{ filePath: string; additions: number; deletions: number }>
  onApplyAll: () => void
  onRejectAll: () => void
  className?: string
}

export function DiffSummary({ diffs, onApplyAll, onRejectAll, className }: DiffSummaryProps) {
  const totalAdd = diffs.reduce((s, d) => s + d.additions, 0)
  const totalDel = diffs.reduce((s, d) => s + d.deletions, 0)

  return (
    <div className={cx('hb-diff-summary', className)}>
      <span className="hb-diff-summary__info">
        <GitBranchIcon />
        <span>{diffs.length} file{diffs.length !== 1 ? 's' : ''} changed</span>
        <span className="hb-diff__stat hb-diff__stat--add">+{totalAdd}</span>
        <span className="hb-diff__stat hb-diff__stat--del">-{totalDel}</span>
      </span>
      <span className="hb-diff-summary__actions">
        <button onClick={onRejectAll} className="hb-diff__btn">Reject All</button>
        <button onClick={onApplyAll} className="hb-diff__btn hb-diff__btn--apply-all">Apply All</button>
      </span>
    </div>
  )
}
