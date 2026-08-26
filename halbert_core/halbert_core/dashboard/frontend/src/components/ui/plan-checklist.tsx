// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * PlanChecklist - Cascade-style plan visualization
 * 
 * Shows the AI's plan as a checklist that updates as steps complete.
 * Based on research2.md: "When the UI detects the <plan> tag, it renders a Checklist Component"
 */

import { useState } from 'react'
import { Check, Circle, Loader2, ChevronDown, ChevronRight, ListChecks } from 'lucide-react'
import { cn } from '@/lib/utils'

export interface PlanStep {
  id: string
  description: string
  status: 'pending' | 'in_progress' | 'completed' | 'failed'
}

interface PlanChecklistProps {
  steps: PlanStep[]
  title?: string
  isExecuting?: boolean
  currentStepIndex?: number
  defaultExpanded?: boolean
  className?: string
}

export function PlanChecklist({
  steps,
  title = "Plan",
  isExecuting = false,
  defaultExpanded = true,
  className,
}: PlanChecklistProps) {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded)
  
  const completedCount = steps.filter(s => s.status === 'completed').length
  const progress = steps.length > 0 ? Math.round((completedCount / steps.length) * 100) : 0

  if (steps.length === 0) {
    return null
  }

  return (
    <div className={cn(
      "rounded-lg border bg-gradient-to-br from-blue-500/5 to-cyan-500/5 border-blue-500/20 shadow-sm overflow-hidden",
      className
    )}>
      {/* Header */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-blue-500/10 transition-colors"
      >
        <div className="flex items-center gap-2">
          {isExecuting ? (
            <Loader2 className="h-4 w-4 animate-spin text-blue-500" />
          ) : (
            <ListChecks className="h-4 w-4 text-blue-500" />
          )}
          <span className="font-medium text-sm text-blue-700 dark:text-blue-300">
            {title}
          </span>
          {/* Progress indicator */}
          <span className="text-xs text-muted-foreground ml-2">
            {completedCount}/{steps.length} complete
          </span>
        </div>
        <div className="flex items-center gap-3">
          {/* Progress bar */}
          <div className="w-20 h-1.5 bg-muted rounded-full overflow-hidden">
            <div 
              className="h-full bg-blue-500 transition-all duration-300"
              style={{ width: `${progress}%` }}
            />
          </div>
          {isExpanded ? (
            <ChevronDown className="h-4 w-4 text-muted-foreground" />
          ) : (
            <ChevronRight className="h-4 w-4 text-muted-foreground" />
          )}
        </div>
      </button>

      {/* Steps */}
      {isExpanded && (
        <div className="border-t border-blue-500/20 px-4 py-2">
          {steps.map((step, index) => (
            <div 
              key={step.id}
              className={cn(
                "flex items-start gap-3 py-2",
                index > 0 && "border-t border-dashed border-muted/50"
              )}
            >
              {/* Status icon */}
              <div className="mt-0.5">
                {step.status === 'completed' ? (
                  <div className="w-5 h-5 rounded-full bg-green-500/20 flex items-center justify-center">
                    <Check className="h-3 w-3 text-green-500" />
                  </div>
                ) : step.status === 'in_progress' ? (
                  <div className="w-5 h-5 rounded-full bg-blue-500/20 flex items-center justify-center">
                    <Loader2 className="h-3 w-3 text-blue-500 animate-spin" />
                  </div>
                ) : step.status === 'failed' ? (
                  <div className="w-5 h-5 rounded-full bg-red-500/20 flex items-center justify-center">
                    <span className="text-red-500 text-xs">✕</span>
                  </div>
                ) : (
                  <div className="w-5 h-5 rounded-full border border-muted-foreground/30 flex items-center justify-center">
                    <Circle className="h-2 w-2 text-muted-foreground/50" />
                  </div>
                )}
              </div>
              
              {/* Step description */}
              <div className="flex-1 min-w-0">
                <p className={cn(
                  "text-sm",
                  step.status === 'completed' && "text-muted-foreground line-through",
                  step.status === 'in_progress' && "text-blue-600 dark:text-blue-400 font-medium",
                  step.status === 'pending' && "text-muted-foreground",
                  step.status === 'failed' && "text-red-500"
                )}>
                  {step.description}
                </p>
              </div>
              
              {/* Step number */}
              <span className="text-xs text-muted-foreground/50">
                {index + 1}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

/**
 * Parse a plan block from LLM output
 * Expects format:
 * <plan>
 * 1. First step
 * 2. Second step
 * </plan>
 */
export function parsePlanFromText(text: string): PlanStep[] {
  const planMatch = text.match(/<plan>([\s\S]*?)<\/plan>/i)
  if (!planMatch) return []
  
  const planContent = planMatch[1]
  const lines = planContent
    .split('\n')
    .map(line => line.trim())
    .filter(line => line && /^\d+\./.test(line))
  
  return lines.map((line, index) => ({
    id: `step-${index}`,
    description: line.replace(/^\d+\.\s*/, ''),
    status: 'pending' as const,
  }))
}

export default PlanChecklist
