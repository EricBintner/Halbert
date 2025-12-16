/**
 * ThinkingSteps - Phase 21 ReAct Thinking UI
 * 
 * Displays AI reasoning steps in a collapsible "Thought for Xs" format,
 * similar to Windsurf Cascade and Cursor.
 * 
 * Shows:
 * - Thought steps (brain icon)
 * - Action steps (terminal icon)  
 * - Observation steps (eye icon)
 * - Final synthesis (check icon)
 */

import { useState } from 'react'
import { ChevronDown, ChevronRight, Brain, Terminal, Eye, CheckCircle, AlertCircle, Clock, Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Badge } from './badge'

export interface ThinkingStep {
  type: 'thought' | 'action' | 'observation' | 'final'
  content: string
  duration_ms?: number
  tool_name?: string
  tool_args?: Record<string, unknown>
  tool_result?: Record<string, unknown>
  error?: string
}

interface ThinkingStepsProps {
  steps: ThinkingStep[]
  totalDurationMs?: number
  isThinking?: boolean
  defaultExpanded?: boolean
  className?: string
}

const stepIcons: Record<string, React.ReactNode> = {
  thought: <Brain className="h-4 w-4" />,
  action: <Terminal className="h-4 w-4" />,
  observation: <Eye className="h-4 w-4" />,
  final: <CheckCircle className="h-4 w-4" />,
}

const stepColors: Record<string, string> = {
  thought: 'text-blue-500 bg-blue-500/10',
  action: 'text-amber-500 bg-amber-500/10',
  observation: 'text-green-500 bg-green-500/10',
  final: 'text-purple-500 bg-purple-500/10',
}

const stepLabels: Record<string, string> = {
  thought: 'Thought',
  action: 'Action',
  observation: 'Observation',
  final: 'Answer',
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

export function ThinkingSteps({
  steps,
  totalDurationMs = 0,
  isThinking = false,
  defaultExpanded = false,
  className,
}: ThinkingStepsProps) {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded)

  if (steps.length === 0 && !isThinking) {
    return null
  }

  const displayDuration = totalDurationMs || steps.reduce((acc, s) => acc + (s.duration_ms || 0), 0)
  const hasErrors = steps.some(s => s.error)
  const actionCount = steps.filter(s => s.type === 'action').length

  return (
    <div className={cn(
      "rounded-lg border bg-card text-card-foreground shadow-sm overflow-hidden",
      hasErrors && "border-amber-500/50",
      className
    )}>
      {/* Header - Collapsible */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-accent/50 transition-colors"
      >
        <div className="flex items-center gap-2">
          {isThinking ? (
            <Loader2 className="h-4 w-4 animate-spin text-blue-500" />
          ) : (
            <Brain className="h-4 w-4 text-blue-500" />
          )}
          <span className="font-medium text-sm">
            {isThinking ? 'Thinking...' : `Thought for ${formatDuration(displayDuration)}`}
          </span>
          {actionCount > 0 && (
            <Badge variant="secondary" className="text-xs ml-2">
              {actionCount} tool{actionCount > 1 ? 's' : ''}
            </Badge>
          )}
          {hasErrors && (
            <AlertCircle className="h-4 w-4 text-amber-500 ml-1" />
          )}
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">
            {steps.length} step{steps.length !== 1 ? 's' : ''}
          </span>
          {isExpanded ? (
            <ChevronDown className="h-4 w-4 text-muted-foreground" />
          ) : (
            <ChevronRight className="h-4 w-4 text-muted-foreground" />
          )}
        </div>
      </button>

      {/* Steps - Expandable */}
      {isExpanded && (
        <div className="border-t">
          {steps.map((step, index) => (
            <ThinkingStepItem key={index} step={step} index={index} />
          ))}
          
          {/* Thinking indicator for in-progress */}
          {isThinking && (
            <div className="flex items-center gap-3 px-4 py-3 bg-blue-500/5 border-t border-dashed">
              <div className="p-1.5 rounded-md bg-blue-500/10">
                <Loader2 className="h-4 w-4 animate-spin text-blue-500" />
              </div>
              <span className="text-sm text-muted-foreground italic">
                Reasoning...
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function ThinkingStepItem({ step, index }: { step: ThinkingStep; index: number }) {
  const [showDetails, setShowDetails] = useState(false)
  const hasDetails = step.tool_args || step.tool_result || step.error

  return (
    <div
      className={cn(
        "flex items-start gap-3 px-4 py-3",
        index > 0 && "border-t border-dashed",
        step.error && "bg-amber-500/5"
      )}
    >
      {/* Icon */}
      <div className={cn(
        "p-1.5 rounded-md shrink-0 mt-0.5",
        stepColors[step.type]
      )}>
        {stepIcons[step.type]}
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <span className={cn(
            "text-xs font-medium uppercase tracking-wide",
            step.error ? "text-amber-500" : "text-muted-foreground"
          )}>
            {stepLabels[step.type]}
            {step.tool_name && `: ${step.tool_name}`}
          </span>
          {step.duration_ms !== undefined && step.duration_ms > 0 && (
            <span className="text-xs text-muted-foreground flex items-center gap-1">
              <Clock className="h-3 w-3" />
              {formatDuration(step.duration_ms)}
            </span>
          )}
        </div>

        <p className="text-sm whitespace-pre-wrap break-words">
          {step.content}
        </p>

        {/* Error display */}
        {step.error && (
          <div className="mt-2 p-2 rounded bg-red-500/10 text-red-500 text-xs font-mono">
            {step.error}
          </div>
        )}

        {/* Expandable details for tool calls */}
        {hasDetails && !step.error && (
          <button
            onClick={() => setShowDetails(!showDetails)}
            className="mt-2 text-xs text-muted-foreground hover:text-foreground flex items-center gap-1"
          >
            {showDetails ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
            {showDetails ? 'Hide' : 'Show'} details
          </button>
        )}

        {showDetails && (
          <div className="mt-2 space-y-2">
            {step.tool_args && (
              <div className="p-2 rounded bg-muted/50 text-xs">
                <span className="font-medium text-muted-foreground">Arguments:</span>
                <pre className="mt-1 overflow-x-auto text-xs">
                  {JSON.stringify(step.tool_args, null, 2)}
                </pre>
              </div>
            )}
            {step.tool_result && (
              <div className="p-2 rounded bg-muted/50 text-xs">
                <span className="font-medium text-muted-foreground">Result:</span>
                <pre className="mt-1 overflow-x-auto text-xs max-h-40 overflow-y-auto">
                  {JSON.stringify(step.tool_result, null, 2)}
                </pre>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

export default ThinkingSteps
