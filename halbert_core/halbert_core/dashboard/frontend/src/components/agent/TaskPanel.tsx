// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * TaskPanel Component
 * 
 * Phase 59: Inline task panel for displaying Agent tasks within primary Chat.
 * Provides visual differentiation between conversational chat and task execution.
 * 
 * Features:
 * - Gradient border (blue-purple) to distinguish from regular messages
 * - Collapsible after completion
 * - Pulse animation while active
 * - State-based color indicators
 */

import { useState, useEffect } from 'react';
import { 
  ChevronDown, 
  ChevronUp, 
  CheckCircle2, 
  XCircle, 
  Loader2,
  AlertCircle,
  Bot,
} from 'lucide-react';
import { cn } from '../../lib/utils';
import { StateBadge } from './StateBadge';
import { PlanChecklist } from './PlanChecklist';
import { ToolExecutionCard } from './ToolExecutionCard';
import { ConfidenceIndicator } from './ConfidenceIndicator';
import { ThinkingPanel } from './ThinkingPanel';
import { DiffBlock } from './DiffBlock';
import type { 
  AgentState, 
  PlanStep, 
  ToolExecution, 
  DiffProposal,
  CRAGAction,
} from '../../hooks/useAgentStream';

// Extended task state that includes completion states
export type TaskState = AgentState | 'complete' | 'cancelled';

export interface TaskPanelProps {
  taskId: string;
  title: string;
  state: TaskState;
  plan?: PlanStep[];
  currentStep?: number;
  toolExecutions?: ToolExecution[];
  diffProposals?: DiffProposal[];
  thinking?: string;
  confidence?: number;
  cragAction?: CRAGAction;
  response?: string;
  error?: string;
  isStreaming?: boolean;
  loopCount?: number;
  onConfirm?: (actionId: string, confirmed: boolean) => void;
  onApplyDiff?: (diffId: string) => void;
  onRejectDiff?: (diffId: string) => void;
  className?: string;
}

export function TaskPanel({
  taskId: _taskId,
  title,
  state,
  plan = [],
  currentStep = 0,
  toolExecutions = [],
  diffProposals = [],
  thinking,
  confidence = 0,
  cragAction,
  response,
  error,
  isStreaming = false,
  loopCount = 0,
  onConfirm: _onConfirm,
  onApplyDiff,
  onRejectDiff,
  className,
}: TaskPanelProps) {
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [autoCollapsed, setAutoCollapsed] = useState(false);

  // Auto-collapse completed tasks after a delay
  useEffect(() => {
    if ((state === 'complete' || state === 'error' || state === 'cancelled') && !autoCollapsed) {
      const timer = setTimeout(() => {
        setIsCollapsed(true);
        setAutoCollapsed(true);
      }, 3000);
      return () => clearTimeout(timer);
    }
  }, [state, autoCollapsed]);

  const isActive = !['complete', 'error', 'cancelled', 'idle'].includes(state);
  const isSuccess = state === 'complete';
  const isError = state === 'error';

  // Get status icon
  const StatusIcon = () => {
    if (isStreaming || isActive) {
      return <Loader2 className="h-4 w-4 animate-spin text-blue-400" />;
    }
    if (isSuccess) {
      return <CheckCircle2 className="h-4 w-4 text-green-400" />;
    }
    if (isError) {
      return <XCircle className="h-4 w-4 text-red-400" />;
    }
    return <Bot className="h-4 w-4 text-zinc-400" />;
  };

  return (
    <div
      className={cn(
        // Base styles
        "rounded-lg overflow-hidden transition-all duration-300",
        // Gradient border effect using pseudo-element technique
        "relative",
        // Active state: pulse animation
        isActive && "animate-pulse-subtle",
        className
      )}
    >
      {/* Gradient border wrapper */}
      <div
        className={cn(
          "absolute inset-0 rounded-lg p-[1px]",
          // Gradient based on state
          isActive && "bg-gradient-to-br from-blue-500/50 via-purple-500/40 to-blue-500/50",
          isSuccess && "bg-gradient-to-br from-green-500/40 to-emerald-500/40",
          isError && "bg-gradient-to-br from-red-500/40 to-orange-500/40",
          !isActive && !isSuccess && !isError && "bg-zinc-700/50"
        )}
      />
      
      {/* Content */}
      <div
        className={cn(
          "relative rounded-lg m-[1px]",
          // Background based on state
          isActive && "bg-gradient-to-br from-blue-950/30 to-purple-950/30",
          isSuccess && "bg-gradient-to-br from-green-950/20 to-emerald-950/20",
          isError && "bg-gradient-to-br from-red-950/20 to-orange-950/20",
          !isActive && !isSuccess && !isError && "bg-zinc-900/80"
        )}
      >
        {/* Header - always visible */}
        <button
          onClick={() => setIsCollapsed(!isCollapsed)}
          className="w-full px-4 py-3 flex items-center gap-3 text-left hover:bg-white/5 transition-colors"
        >
          <StatusIcon />
          
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-zinc-200 truncate">
                {title}
              </span>
              {/* Only pass valid AgentState to StateBadge */}
              {state !== 'complete' && state !== 'cancelled' && (
                <StateBadge state={state} showPulse={isStreaming} />
              )}
              {state === 'complete' && (
                <span className="px-1.5 py-0.5 text-[10px] font-medium bg-green-500/20 text-green-400 rounded">COMPLETE</span>
              )}
              {state === 'cancelled' && (
                <span className="px-1.5 py-0.5 text-[10px] font-medium bg-zinc-500/20 text-zinc-400 rounded">CANCELLED</span>
              )}
            </div>
            {isCollapsed && response && (
              <p className="text-xs text-zinc-400 truncate mt-0.5">
                {response.slice(0, 80)}{response.length > 80 ? '...' : ''}
              </p>
            )}
          </div>
          
          {loopCount > 0 && (
            <span className="text-xs text-zinc-500">Loop {loopCount}</span>
          )}
          
          {isCollapsed ? (
            <ChevronDown className="h-4 w-4 text-zinc-500" />
          ) : (
            <ChevronUp className="h-4 w-4 text-zinc-500" />
          )}
        </button>

        {/* Expandable content */}
        {!isCollapsed && (
          <div className="px-4 pb-4 space-y-3">
            {/* Plan checklist */}
            {plan.length > 0 && (
              <PlanChecklist plan={plan} currentStep={currentStep} />
            )}

            {/* Tool executions */}
            {toolExecutions.map((exec) => (
              <ToolExecutionCard key={exec.executionId} execution={exec} />
            ))}

            {/* Diff proposals */}
            {diffProposals.map((diff) => (
              <DiffBlock
                key={diff.id}
                filePath={diff.filePath}
                oldContent={diff.oldContent}
                newContent={diff.newContent}
                additions={diff.additions}
                deletions={diff.deletions}
                status={diff.status}
                onApply={() => onApplyDiff?.(diff.id)}
                onReject={() => onRejectDiff?.(diff.id)}
              />
            ))}

            {/* Thinking panel */}
            {thinking && (
              <ThinkingPanel thinking={thinking} isStreaming={isStreaming} />
            )}

            {/* Confidence indicator */}
            {confidence > 0 && (
              <ConfidenceIndicator
                confidence={confidence}
                cragAction={cragAction}
                size="sm"
              />
            )}

            {/* Response */}
            {response && (
              <div className="text-sm text-zinc-300 whitespace-pre-wrap">
                {response}
                {isStreaming && (
                  <span className="inline-block w-2 h-4 bg-zinc-400 animate-pulse ml-0.5" />
                )}
              </div>
            )}

            {/* Error display */}
            {error && (
              <div className="flex items-start gap-2 p-2 bg-red-500/10 border border-red-500/30 rounded text-xs text-red-400">
                <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
                <span>{error}</span>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default TaskPanel;
