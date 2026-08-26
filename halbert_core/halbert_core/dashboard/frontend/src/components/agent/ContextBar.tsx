// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * ContextBar + ContextPill Components
 * 
 * Shows pinned context - files, searches, memories that the agent has "loaded".
 * "The user sees exactly what the AI has loaded into its brain."
 */

import { useState } from 'react';
import { FileText, Search, Brain, Globe, FolderOpen, X, ChevronDown, ChevronUp } from 'lucide-react';

export type ContextType = 'file' | 'search' | 'memory' | 'web' | 'directory';

export interface ContextItem {
  id: string;
  type: ContextType;
  label: string;
  path?: string;
  preview?: string;
  tokens?: number;
}

interface ContextPillProps {
  item: ContextItem;
  onRemove?: () => void;
  onClick?: () => void;
  isExpanded?: boolean;
}

const TYPE_CONFIG: Record<ContextType, { icon: typeof FileText; color: string; bg: string }> = {
  file: { icon: FileText, color: 'text-blue-600 dark:text-blue-400', bg: 'bg-blue-100 dark:bg-blue-500/10 border-blue-200 dark:border-blue-500/20' },
  search: { icon: Search, color: 'text-purple-600 dark:text-purple-400', bg: 'bg-purple-100 dark:bg-purple-500/10 border-purple-200 dark:border-purple-500/20' },
  memory: { icon: Brain, color: 'text-pink-600 dark:text-pink-400', bg: 'bg-pink-100 dark:bg-pink-500/10 border-pink-200 dark:border-pink-500/20' },
  web: { icon: Globe, color: 'text-green-600 dark:text-green-400', bg: 'bg-green-100 dark:bg-green-500/10 border-green-200 dark:border-green-500/20' },
  directory: { icon: FolderOpen, color: 'text-orange-600 dark:text-orange-400', bg: 'bg-orange-100 dark:bg-orange-500/10 border-orange-200 dark:border-orange-500/20' },
};

export function ContextPill({ item, onRemove, onClick, isExpanded: _isExpanded }: ContextPillProps) {
  const config = TYPE_CONFIG[item.type];
  const Icon = config.icon;
  
  return (
    <div 
      className={`
        inline-flex items-center gap-1 px-1.5 py-0.5 rounded border text-[10px]
        ${config.bg} cursor-pointer hover:opacity-80 transition-opacity
      `}
      onClick={onClick}
    >
      <Icon className={`h-2.5 w-2.5 ${config.color}`} />
      <span className="text-foreground max-w-[80px] truncate">{item.label}</span>
      {item.tokens && (
        <span className="text-muted-foreground text-[9px]">({item.tokens})</span>
      )}
      {onRemove && (
        <button
          onClick={(e) => { e.stopPropagation(); onRemove(); }}
          className="ml-0.5 p-0.5 hover:bg-accent rounded"
        >
          <X className="h-2 w-2 text-muted-foreground" />
        </button>
      )}
    </div>
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
          <span className="text-[10px] text-muted-foreground">Context</span>
          <span className="text-[9px] text-muted-foreground/70">
            {items.length} items • ~{totalTokens} tokens
          </span>
        </div>
        <button
          onClick={() => setIsCollapsed(!isCollapsed)}
          className="p-0.5 hover:bg-accent rounded"
        >
          {isCollapsed ? (
            <ChevronDown className="h-2.5 w-2.5 text-muted-foreground" />
          ) : (
            <ChevronUp className="h-2.5 w-2.5 text-muted-foreground" />
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
      <div className="w-full max-w-2xl max-h-[80vh] bg-zinc-900 rounded-lg border border-zinc-700 shadow-xl overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-700 bg-zinc-800">
          <div className="flex items-center gap-2">
            <Icon className={`h-4 w-4 ${config.color}`} />
            <span className="text-sm text-zinc-200">{item.label}</span>
            {item.path && (
              <span className="text-xs text-zinc-500">{item.path}</span>
            )}
          </div>
          <button
            onClick={onClose}
            className="p-1 hover:bg-zinc-700 rounded"
          >
            <X className="h-4 w-4 text-zinc-400" />
          </button>
        </div>
        
        <div className="p-4 overflow-auto max-h-[60vh]">
          <pre className="text-xs text-zinc-300 whitespace-pre-wrap font-mono">
            {item.preview || 'No preview available'}
          </pre>
        </div>
      </div>
    </div>
  );
}

export default ContextBar;
