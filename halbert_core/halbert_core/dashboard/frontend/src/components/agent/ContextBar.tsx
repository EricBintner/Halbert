// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * ContextBar + ContextPill Components
 * 
 * Shows pinned context - files, searches, memories that the agent has "loaded".
 * "The user sees exactly what the AI has loaded into its brain."
 */

import { useState } from 'react';
import { FileText, Search, Brain, Globe, FolderOpen, MessageSquare, X, ChevronDown, ChevronUp } from 'lucide-react';

export type ContextType = 'file' | 'search' | 'memory' | 'web' | 'directory' | 'thread';

export interface ContextItem {
  id: string;
  type: ContextType;
  label: string;
  path?: string;
  preview?: string;
  tokens?: number;
  /** Why this is here, shown on hover — a thread chip's match terms ("matched: samba, share"). */
  hint?: string;
}

interface ContextPillProps {
  item: ContextItem;
  onRemove?: () => void;
  onClick?: () => void;
  isExpanded?: boolean;
}

/**
 * `noun` is the spoken prefix of the chip's accessible name ("earlier
 * subject: pulled in: Samba share setup · 2026-07-14"). The `thread` entry is
 * the only one on canonical tokens (telemetry); the older entries keep their
 * pre-existing palette classes — the literal-colour ratchet allows existing
 * debt, not new debt, so nothing here may add a palette class.
 */
const TYPE_CONFIG: Record<ContextType, { icon: typeof FileText; color: string; bg: string; noun: string }> = {
  file: { icon: FileText, color: 'text-info dark:text-info', bg: 'bg-blue-100 dark:bg-info/10 border-blue-200 dark:border-info/20', noun: 'file' },
  search: { icon: Search, color: 'text-purple-600 dark:text-purple-400', bg: 'bg-purple-100 dark:bg-purple-500/10 border-purple-200 dark:border-purple-500/20', noun: 'search' },
  memory: { icon: Brain, color: 'text-error dark:text-error', bg: 'bg-error-muted dark:bg-error/10 border-error-muted dark:border-error/20', noun: 'memory' },
  web: { icon: Globe, color: 'text-success dark:text-success', bg: 'bg-success-muted dark:bg-success/10 border-success-muted dark:border-success/20', noun: 'web' },
  directory: { icon: FolderOpen, color: 'text-warning dark:text-warning', bg: 'bg-warning-muted dark:bg-warning/10 border-warning-muted dark:border-warning/20', noun: 'directory' },
  thread: { icon: MessageSquare, color: 'text-status-telemetry', bg: 'bg-status-telemetry-bg border-status-telemetry-line', noun: 'earlier subject' },
};

export function ContextPill({ item, onRemove, onClick, isExpanded: _isExpanded }: ContextPillProps) {
  const config = TYPE_CONFIG[item.type];
  const Icon = config.icon;

  return (
    <span className={`inline-flex items-center rounded border text-[11px] font-mono ${config.bg}`}>
      <button
        type="button"
        aria-label={`${config.noun}: ${item.label}`}
        title={item.hint}
        onClick={onClick}
        className="inline-flex items-center gap-1 px-1.5 py-0.5 hover:opacity-80 transition-opacity focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
      >
        <Icon className={`h-2.5 w-2.5 ${config.color}`} aria-hidden="true" />
        <span className="text-foreground max-w-[140px] truncate">{item.label}</span>
        {item.tokens ? (
          <span className="text-muted-foreground text-[11px]">({item.tokens})</span>
        ) : null}
      </button>
      {onRemove && (
        <button
          type="button"
          aria-label={`Drop ${item.label} from context`}
          onClick={onRemove}
          className="mr-0.5 p-0.5 hover:bg-accent rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
        >
          <X className="h-2.5 w-2.5 text-muted-foreground" aria-hidden="true" />
        </button>
      )}
    </span>
  );
}

interface ContextBarProps {
  items: ContextItem[];
  onRemoveItem?: (id: string) => void;
  onItemClick?: (item: ContextItem) => void;
  className?: string;
}

export function ContextBar({ items, onRemoveItem, onItemClick, className = '' }: ContextBarProps) {
  const [isCollapsed, setIsCollapsed] = useState(false);

  if (items.length === 0) return null;

  const totalTokens = items.reduce((sum, item) => sum + (item.tokens || 0), 0);

  return (
    <div className={`border-b bg-muted/30 ${className}`}>
      <div className="flex items-center justify-between px-2 py-1">
        <div className="flex items-center gap-1.5">
          <span className="text-[11px] text-muted-foreground">Context</span>
          <span className="text-[11px] text-muted-foreground/70">
            {items.length} items • ~{totalTokens} tokens
          </span>
        </div>
        <button
          type="button"
          aria-label={isCollapsed ? 'Expand context' : 'Collapse context'}
          aria-expanded={!isCollapsed}
          onClick={() => setIsCollapsed(!isCollapsed)}
          className="p-0.5 hover:bg-accent rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
        >
          {isCollapsed ? (
            <ChevronDown className="h-2.5 w-2.5 text-muted-foreground" aria-hidden="true" />
          ) : (
            <ChevronUp className="h-2.5 w-2.5 text-muted-foreground" aria-hidden="true" />
          )}
        </button>
      </div>

      {!isCollapsed && (
        <div className="flex flex-wrap gap-1 px-2 pb-1.5">
          {items.map((item) => (
            <ContextPill
              key={item.id}
              item={item}
              onRemove={onRemoveItem ? () => onRemoveItem(item.id) : undefined}
              onClick={onItemClick ? () => onItemClick(item) : undefined}
            />
          ))}
        </div>
      )}
    </div>
  );
}

/**
 * ContextPreview - Expandable preview of a context item
 */
interface ContextPreviewProps {
  item: ContextItem;
  onClose: () => void;
}

export function ContextPreview({ item, onClose }: ContextPreviewProps) {
  const config = TYPE_CONFIG[item.type];
  const Icon = config.icon;
  
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-full max-w-2xl max-h-[80vh] bg-background rounded-lg border border-border shadow-xl overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b border-border bg-muted">
          <div className="flex items-center gap-2">
            <Icon className={`h-4 w-4 ${config.color}`} />
            <span className="text-sm text-foreground">{item.label}</span>
            {item.path && (
              <span className="text-xs text-muted-foreground">{item.path}</span>
            )}
          </div>
          <button
            onClick={onClose}
            className="p-1 hover:bg-muted rounded"
          >
            <X className="h-4 w-4 text-muted-foreground" />
          </button>
        </div>
        
        <div className="p-4 overflow-auto max-h-[60vh]">
          <pre className="text-xs text-foreground whitespace-pre-wrap font-mono">
            {item.preview || 'No preview available'}
          </pre>
        </div>
      </div>
    </div>
  );
}

export default ContextBar;
