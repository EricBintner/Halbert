// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * Activity Indicators - Cascade-style streaming event UI
 * 
 * Based on research2.md streaming protocol:
 * - Type: "Scan" - "Scanning 15 files for 'auth_middleware'..."
 * - Type: "Read" - Context pill showing loaded file
 * - Type: "Diff" - Side-by-side diff view (placeholder)
 */

import { FileText, GitCompare, Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'

// Context pill - "I have read this"
interface ContextPillProps {
  filename: string
  /** Inclusive [start, end] line range. */
  lines?: [number, number]
  onClick?: () => void
  className?: string
}

export function ContextPill({ 
  filename, 
  lines,
  onClick,
  className 
}: ContextPillProps) {
  const shortName = filename.split('/').pop() || filename
  
  return (
    <button
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-1.5 px-2 py-1 rounded text-xs",
        "bg-info-muted text-info border border-info/20",
        "hover:bg-info/20 transition-colors cursor-pointer",
        className
      )}
      title={filename}
    >
      <FileText className="h-3 w-3" />
      <span className="font-mono">{shortName}</span>
      {lines && (
        <span className="text-muted-foreground">:{lines[0]}-{lines[1]}</span>
      )}
    </button>
  )
}

// Diff indicator - "I have prepared this change"
interface DiffIndicatorProps {
  filename: string
  additions?: number
  deletions?: number
  onApply?: () => void
  onReject?: () => void
  className?: string
}

export function DiffIndicator({ 
  filename, 
  additions = 0, 
  deletions = 0,
  onApply,
  onReject,
  className 
}: DiffIndicatorProps) {
  const shortName = filename.split('/').pop() || filename
  
  return (
    <div className={cn(
      "flex items-center justify-between gap-3 px-3 py-2 rounded-lg",
      "bg-purple-500/10 border border-purple-500/20",
      className
    )}>
      <div className="flex items-center gap-2">
        <GitCompare className="h-4 w-4 text-purple-500" />
        <span className="text-sm font-mono">{shortName}</span>
        <div className="flex items-center gap-1 text-xs">
          {additions > 0 && (
            <span className="text-green-500">+{additions}</span>
          )}
          {deletions > 0 && (
            <span className="text-red-500">-{deletions}</span>
          )}
        </div>
      </div>
      
      {(onApply || onReject) && (
        <div className="flex items-center gap-2">
          {onReject && (
            <button
              onClick={onReject}
              className="px-2 py-1 text-xs rounded bg-muted hover:bg-muted/80 transition-colors"
            >
              Reject
            </button>
          )}
          {onApply && (
            <button
              onClick={onApply}
              className="px-2 py-1 text-xs rounded bg-purple-500 text-white hover:bg-purple-600 transition-colors"
            >
              Apply
            </button>
          )}
        </div>
      )}
    </div>
  )
}

// Loading indicator with custom message
interface LoadingIndicatorProps {
  message?: string
  className?: string
}

export function LoadingIndicator({ 
  message = "Processing...",
  className 
}: LoadingIndicatorProps) {
  return (
    <div className={cn(
      "flex items-center gap-2 text-xs text-muted-foreground",
      className
    )}>
      <Loader2 className="h-3 w-3 animate-spin" />
      <span>{message}</span>
    </div>
  )
}

export default {
  ContextPill,
  DiffIndicator,
  LoadingIndicator,
}
