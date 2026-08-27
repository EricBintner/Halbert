// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * DiffBlock Component
 * 
 * Shows code changes as a diff with Apply/Reject actions.
 * "The AI doesn't ask to copy code. It asks to write to disk."
 */

import { useState } from 'react';
import { Check, X, ChevronDown, ChevronUp, FileText, GitBranch } from 'lucide-react';

interface DiffBlockProps {
  filePath: string;
  oldContent?: string;
  newContent: string;
  additions?: number;
  deletions?: number;
  onApply: () => void;
  onReject: () => void;
  status?: 'pending' | 'applied' | 'rejected';
  /** A stored turn: the session is gone, so a pending diff is a record, not a choice. */
  readOnly?: boolean;
  className?: string;
}

export function DiffBlock({
  filePath,
  oldContent,
  newContent,
  additions = 0,
  deletions = 0,
  onApply,
  onReject,
  status = 'pending',
  readOnly = false,
  className = '',
}: DiffBlockProps) {
  const [isExpanded, setIsExpanded] = useState(true);
  const [_viewMode, _setViewMode] = useState<'unified' | 'split'>('unified');
  
  // Simple diff visualization (in production, use a proper diff library)
  const renderUnifiedDiff = () => {
    if (!oldContent) {
      // New file - show all as additions
      return newContent.split('\n').map((line, i) => (
        <div key={i} className="flex">
          <span className="w-8 text-right pr-1 text-muted-foreground select-none text-[10px]">
            {i + 1}
          </span>
          <span className="flex-1 bg-success-muted dark:bg-success/10 text-success dark:text-success px-1">
            + {line}
          </span>
        </div>
      ));
    }
    
    // Simple line-by-line diff (simplified)
    const oldLines = oldContent.split('\n');
    const newLines = newContent.split('\n');
    const diffLines: Array<{ type: 'context' | 'add' | 'remove'; content: string; lineNum?: number }> = [];
    
    // Very simplified diff - in production use diff-match-patch or similar
    let oldIdx = 0;
    let newIdx = 0;
    
    while (oldIdx < oldLines.length || newIdx < newLines.length) {
      if (oldIdx >= oldLines.length) {
        diffLines.push({ type: 'add', content: newLines[newIdx], lineNum: newIdx + 1 });
        newIdx++;
      } else if (newIdx >= newLines.length) {
        diffLines.push({ type: 'remove', content: oldLines[oldIdx], lineNum: oldIdx + 1 });
        oldIdx++;
      } else if (oldLines[oldIdx] === newLines[newIdx]) {
        diffLines.push({ type: 'context', content: oldLines[oldIdx], lineNum: oldIdx + 1 });
        oldIdx++;
        newIdx++;
      } else {
        diffLines.push({ type: 'remove', content: oldLines[oldIdx], lineNum: oldIdx + 1 });
        diffLines.push({ type: 'add', content: newLines[newIdx], lineNum: newIdx + 1 });
        oldIdx++;
        newIdx++;
      }
    }
    
    return diffLines.map((line, i) => {
      const bgColor = line.type === 'add' ? 'bg-success-muted dark:bg-success/10' : 
                      line.type === 'remove' ? 'bg-error-muted dark:bg-error/10' : '';
      const textColor = line.type === 'add' ? 'text-success dark:text-success' : 
                        line.type === 'remove' ? 'text-error dark:text-error' : 'text-muted-foreground';
      const prefix = line.type === 'add' ? '+' : line.type === 'remove' ? '-' : ' ';
      
      return (
        <div key={i} className={`flex ${bgColor}`}>
          <span className="w-8 text-right pr-1 text-muted-foreground select-none text-[10px]">
            {line.lineNum}
          </span>
          <span className={`flex-1 px-1 ${textColor}`}>
            {prefix} {line.content}
          </span>
        </div>
      );
    });
  };
  
  const statusColors = {
    pending: 'border-border',
    applied: 'border-success/50 bg-success-muted dark:bg-success/5',
    rejected: 'border-error/50 bg-error-muted dark:bg-error/5',
  };
  
  return (
    <div className={`rounded-md border ${statusColors[status]} overflow-hidden ${className}`}>
      {/* Header */}
      <div className="flex items-center justify-between px-2 py-1.5 bg-muted/50 border-b">
        <div className="flex items-center gap-1.5">
          <FileText className="h-3 w-3 text-muted-foreground" />
          <span className="text-[10px] text-foreground font-mono truncate max-w-[150px]">{filePath}</span>
          <div className="flex items-center gap-1 text-[10px]">
            {additions > 0 && (
              <span className="text-success dark:text-success">+{additions}</span>
            )}
            {deletions > 0 && (
              <span className="text-error dark:text-error">-{deletions}</span>
            )}
          </div>
        </div>
        
        <div className="flex items-center gap-1">
          {status === 'pending' && readOnly && (
            <span className="text-[11px] font-mono text-ink-tertiary">proposed</span>
          )}
          {status === 'pending' && !readOnly && (
            <>
              <button
                onClick={onReject}
                className="flex items-center gap-0.5 px-1.5 py-0.5 text-[10px] text-destructive hover:bg-destructive/10 rounded transition-colors"
              >
                <X className="h-2.5 w-2.5" />
                Reject
              </button>
              <button
                onClick={onApply}
                className="flex items-center gap-0.5 px-1.5 py-0.5 text-[10px] text-success dark:text-success bg-success-muted dark:bg-success/10 hover:bg-success-muted dark:hover:bg-success/20 rounded transition-colors"
              >
                <Check className="h-2.5 w-2.5" />
                Apply
              </button>
            </>
          )}
          {status === 'applied' && (
            <span className="flex items-center gap-0.5 text-[10px] text-success dark:text-success">
              <Check className="h-2.5 w-2.5" />
              Applied
            </span>
          )}
          {status === 'rejected' && (
            <span className="flex items-center gap-0.5 text-[10px] text-destructive">
              <X className="h-2.5 w-2.5" />
              Rejected
            </span>
          )}
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            className="p-0.5 hover:bg-accent rounded"
          >
            {isExpanded ? (
              <ChevronUp className="h-3 w-3 text-muted-foreground" />
            ) : (
              <ChevronDown className="h-3 w-3 text-muted-foreground" />
            )}
          </button>
        </div>
      </div>
      
      {/* Diff Content */}
      {isExpanded && (
        <div className="overflow-x-auto max-h-32">
          <pre className="text-[10px] font-mono p-0 m-0">
            {renderUnifiedDiff()}
          </pre>
        </div>
      )}
    </div>
  );
}

/**
 * DiffSummary - Compact summary of pending changes
 */
interface DiffSummaryProps {
  diffs: Array<{ filePath: string; additions: number; deletions: number }>;
  onApplyAll: () => void;
  onRejectAll: () => void;
}

export function DiffSummary({ diffs, onApplyAll, onRejectAll }: DiffSummaryProps) {
  const totalAdditions = diffs.reduce((sum, d) => sum + d.additions, 0);
  const totalDeletions = diffs.reduce((sum, d) => sum + d.deletions, 0);
  
  return (
    <div className="flex items-center justify-between px-2 py-1.5 bg-muted/50 rounded-md border">
      <div className="flex items-center gap-2">
        <GitBranch className="h-3 w-3 text-muted-foreground" />
        <span className="text-[10px] text-foreground">
          {diffs.length} file{diffs.length !== 1 ? 's' : ''} changed
        </span>
        <div className="flex items-center gap-1 text-[10px]">
          <span className="text-success dark:text-success">+{totalAdditions}</span>
          <span className="text-error dark:text-error">-{totalDeletions}</span>
        </div>
      </div>
      
      <div className="flex items-center gap-1">
        <button
          onClick={onRejectAll}
          className="px-2 py-0.5 text-[10px] text-muted-foreground hover:bg-accent rounded transition-colors"
        >
          Reject All
        </button>
        <button
          onClick={onApplyAll}
          className="px-2 py-0.5 text-[10px] text-white bg-success hover:bg-success rounded transition-colors"
        >
          Apply All
        </button>
      </div>
    </div>
  );
}

export default DiffBlock;
