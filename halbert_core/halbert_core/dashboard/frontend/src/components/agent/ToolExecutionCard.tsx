// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * ToolExecutionCard Component
 * 
 * Displays tool execution status with expandable details.
 * Based on research5.md Part 8.3.
 */

import { useState } from 'react';
import { type ToolExecution } from '../../hooks/useAgentStream';

interface ToolExecutionCardProps {
  execution: ToolExecution;
  onRetry?: (executionId: string) => void;
}

const STATUS_CONFIG = {
  running: {
    icon: '⟳',
    label: 'running',
    bgColor: 'bg-status-telemetry-bg',
    borderColor: 'border-status-telemetry-line',
    textColor: 'text-status-telemetry',
  },
  success: {
    icon: '✓',
    label: 'exit 0',
    bgColor: 'bg-status-nominal-bg',
    borderColor: 'border-status-nominal-line',
    textColor: 'text-status-nominal',
  },
  error: {
    icon: '✗',
    label: 'error',
    bgColor: 'bg-status-critical-bg',
    borderColor: 'border-status-critical-line',
    textColor: 'text-status-critical',
  },
};

export function ToolExecutionCard({ execution, onRetry }: ToolExecutionCardProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const config = STATUS_CONFIG[execution.status];

  return (
    <div 
      className={`
        rounded-lg border ${config.borderColor} ${config.bgColor}
        overflow-hidden
      `}
    >
      <div 
        className="flex items-center justify-between p-2 cursor-pointer hover:bg-opacity-80"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div className="flex items-center gap-2">
          <span
            className={`${config.textColor} text-sm`}
          >
            {config.icon}
          </span>
          <div>
            <div className="font-medium text-foreground text-xs">{execution.tool}</div>
            <div className="text-[10px] text-muted-foreground">{config.label}</div>
          </div>
        </div>
        <span className="text-muted-foreground text-xs">
          {isExpanded ? '▲' : '▼'}
        </span>
      </div>

      {isExpanded && (
        <div className="border-t p-2 space-y-2">
          <div>
            <div className="text-[10px] font-medium text-muted-foreground mb-1">Arguments</div>
            <pre className="text-[10px] bg-muted rounded p-1.5 overflow-x-auto border">
              {JSON.stringify(execution.args, null, 2)}
            </pre>
          </div>

          {execution.result !== undefined && (
            <div>
              <div className="text-[10px] font-medium text-muted-foreground mb-1">Result</div>
              <pre className="text-[10px] bg-muted rounded p-1.5 overflow-x-auto border max-h-24">
                {typeof execution.result === 'string' 
                  ? execution.result 
                  : JSON.stringify(execution.result, null, 2)}
              </pre>
            </div>
          )}

          {execution.error && (
            <div>
              <div className="text-[10px] font-medium text-destructive mb-1">Error</div>
              <pre className="text-[10px] bg-destructive/10 text-destructive rounded p-1.5 border border-destructive/30">
                {execution.error}
              </pre>
            </div>
          )}

          {execution.status === 'error' && onRetry && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                onRetry(execution.executionId);
              }}
              className="text-xs text-primary hover:text-primary/80 font-medium"
            >
              Retry
            </button>
          )}
        </div>
      )}
    </div>
  );
}

export default ToolExecutionCard;
