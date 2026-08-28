// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * ToolExecutionCard Component
 * 
 * Displays tool execution status with expandable details.
 * Based on research5.md Part 8.3.
 */

import { useState, type ReactNode } from 'react';
import { type ToolExecution } from '../../hooks/useAgentStream';
import { StatusLight, type StatusLightState } from './StatusLight';

interface ToolExecutionCardProps {
  execution: ToolExecution;
  onRetry?: (executionId: string) => void;
  /** Plan B: block id for run_command blocks. */
  blockId?: string;
  /** Plan B: block output (frozen <pre> when block is complete). */
  blockOutput?: string;
  /** Plan B: block exit code. */
  blockExitCode?: number | null;
  /** Plan B: block duration in seconds. */
  blockDuration?: number;
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

export function ToolExecutionCard({ execution, onRetry, blockId, blockOutput, blockExitCode, blockDuration }: ToolExecutionCardProps): ReactNode {
  const [isExpanded, setIsExpanded] = useState(false);
  const config = STATUS_CONFIG[execution.status];

  // Plan B: map execution status to StatusLight state
  const lightState: StatusLightState =
    execution.status === 'running' ? 'running' :
    execution.status === 'error' ? 'error' :
    'done_unseen';

  // Plan B: for run_command with a block, render the block output
  const isCommandBlock = execution.tool === 'run_command' && blockId;
  // Suppress the card's own <pre> result when a block renders
  const suppressResult = isCommandBlock && blockOutput !== undefined;

  // Plan B: one-line result for short completed blocks
  const isShortBlock = isCommandBlock && blockDuration !== undefined && blockDuration < 2 && blockOutput !== undefined;

  return (
    <div
      className={`rounded-lg border ${config.borderColor} ${config.bgColor} overflow-hidden`}
      data-terminal-block={blockId}
    >
      {/* Header — StatusLight on a surface strip, not the status-tinted body */}
      <div
        className="flex items-center justify-between p-2 cursor-pointer hover:bg-opacity-80 bg-surface"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div className="flex items-center gap-2">
          <StatusLight
            state={lightState}
            exitCode={blockExitCode ?? (execution.status === 'error' ? 1 : 0)}
            size="sm"
          />
          <div>
            <div className="font-medium text-foreground text-xs">{execution.tool}</div>
            {/* Plan B: labels are measurements, not "Success"/"Error" */}
            <div className="text-[10px] text-muted-foreground">
              {isCommandBlock && blockExitCode != null
                ? `exit ${blockExitCode}${blockDuration != null ? ` · ${blockDuration.toFixed(1)}s` : ''}`
                : config.label}
            </div>
          </div>
        </div>
        <span className="text-muted-foreground text-xs">
          {isExpanded ? '\u25B2' : '\u25BC'}
        </span>
      </div>

      {/* Plan B: short block one-line result (not expanded) */}
      {isShortBlock && !isExpanded && (
        <div className="px-2 pb-1 text-[10px] font-mono text-muted-foreground truncate">
          $ {String((execution.args as Record<string, unknown>)?.command ?? execution.tool)} · exit {blockExitCode ?? '?'}
        </div>
      )}

      {isExpanded && (
        <div className="border-t p-2 space-y-2">
          <div>
            <div className="text-[10px] font-medium text-muted-foreground mb-1">Arguments</div>
            <pre className="text-[10px] bg-muted rounded p-1.5 overflow-x-auto border">
              {JSON.stringify(execution.args, null, 2)}
            </pre>
          </div>

          {/* Plan B: block output (frozen <pre>) — replaces the result <pre> */}
          {isCommandBlock && blockOutput !== undefined && (
            <div>
              <div className="text-[10px] font-medium text-muted-foreground mb-1">Block output</div>
              <pre className="text-[10px] bg-muted rounded p-1.5 overflow-x-auto border max-h-48">
                {blockOutput}
              </pre>
            </div>
          )}

          {/* Suppress the raw result when a block renders */}
          {!suppressResult && execution.result !== undefined && (
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
