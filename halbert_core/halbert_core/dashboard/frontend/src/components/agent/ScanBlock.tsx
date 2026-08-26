// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * ScanBlock Component
 * 
 * Shows the "I am looking" phase - when agent is searching/scanning.
 * Displays pulsing animation with search context.
 */

import { Search, Database, Globe, Brain, Loader2, CheckCircle2, FileText } from 'lucide-react';
import { cn } from '../../lib/utils';

export type ScanSource = 'rag' | 'memory' | 'discovery' | 'web' | 'file';

interface ScanBlockProps {
  query?: string;
  source: ScanSource;
  fileCount?: number;
  isComplete?: boolean;
  resultsCount?: number;
  className?: string;
}

const SOURCE_CONFIG: Record<ScanSource, { icon: typeof Search; label: string; color: string; bgColor: string }> = {
  rag: { icon: Database, label: 'Documents', color: 'text-info dark:text-info', bgColor: 'bg-blue-100 dark:bg-info/10' },
  memory: { icon: Brain, label: 'Memory', color: 'text-purple-600 dark:text-purple-400', bgColor: 'bg-purple-100 dark:bg-purple-500/10' },
  discovery: { icon: Search, label: 'System', color: 'text-info dark:text-info', bgColor: 'bg-cyan-100 dark:bg-info/10' },
  web: { icon: Globe, label: 'Web', color: 'text-green-600 dark:text-green-400', bgColor: 'bg-green-100 dark:bg-green-500/10' },
  file: { icon: FileText, label: 'Files', color: 'text-orange-600 dark:text-orange-400', bgColor: 'bg-orange-100 dark:bg-orange-500/10' },
};

export function ScanBlock({
  query,
  source,
  fileCount,
  isComplete = false,
  resultsCount,
  className = '',
}: ScanBlockProps) {
  const config = SOURCE_CONFIG[source];
  const Icon = config.icon;
  
  return (
    <div 
      className={cn(
        'flex items-center gap-2 px-2 py-1.5 rounded-md border transition-all duration-300',
        isComplete 
          ? 'bg-muted/50 border-border/50' 
          : `${config.bgColor} border-border/50 animate-pulse`,
        className
      )}
    >
      <div className={cn(
        'flex items-center justify-center w-6 h-6 rounded-full transition-all duration-300',
        isComplete ? 'bg-green-100 dark:bg-green-500/20' : config.bgColor
      )}>
        {!isComplete ? (
          <Loader2 className={cn('h-3 w-3 animate-spin', config.color)} />
        ) : (
          <CheckCircle2 className="h-3 w-3 text-green-600 dark:text-green-400" />
        )}
      </div>
      
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5">
          <Icon className={cn('h-3 w-3', config.color)} />
          <span className="text-[10px] font-medium text-foreground">
            {!isComplete ? 'Searching' : 'Searched'} {config.label}
          </span>
          {fileCount !== undefined && fileCount > 0 && (
            <span className="text-[10px] text-muted-foreground">
              • {fileCount} items
            </span>
          )}
        </div>
        
        {query && (
          <div className="text-[10px] text-muted-foreground truncate">
            <span className="opacity-70">Query:</span> {query}
          </div>
        )}
      </div>
      
      {isComplete && resultsCount !== undefined && (
        <div className={cn(
          'text-[10px] font-medium px-1.5 py-0.5 rounded-full transition-all',
          resultsCount > 0 
            ? 'bg-green-100 dark:bg-green-500/20 text-green-600 dark:text-green-400' 
            : 'bg-muted text-muted-foreground'
        )}>
          {resultsCount} found
        </div>
      )}
      
      {!isComplete && (
        <div className="flex gap-0.5 items-center">
          <span className="w-1 h-1 rounded-full bg-primary animate-bounce" style={{ animationDelay: '0ms' }} />
          <span className="w-1 h-1 rounded-full bg-primary animate-bounce" style={{ animationDelay: '150ms' }} />
          <span className="w-1 h-1 rounded-full bg-primary animate-bounce" style={{ animationDelay: '300ms' }} />
        </div>
      )}
    </div>
  );
}

export default ScanBlock;
