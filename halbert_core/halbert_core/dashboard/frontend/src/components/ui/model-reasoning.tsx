/**
 * ModelReasoning - Phase 32 Extended Thinking UI
 * 
 * Displays reasoning/thinking content from reasoning models like
 * DeepSeek R1, QwQ, or Claude with extended thinking.
 * 
 * Shows the model's chain-of-thought in a collapsible "Reasoned for Xs" format.
 * Different from ThinkingSteps (ReAct tool loops) - this shows internal reasoning.
 */

import { useState, useEffect, useRef } from 'react'
import { ChevronDown, ChevronRight, Sparkles, Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'

interface ModelReasoningProps {
  thinking: string
  isThinking?: boolean
  durationMs?: number
  defaultExpanded?: boolean
  className?: string
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
  return `${Math.floor(ms / 60000)}m ${Math.floor((ms % 60000) / 1000)}s`
}

export function ModelReasoning({
  thinking,
  isThinking = false,
  durationMs = 0,
  defaultExpanded = false,
  className,
}: ModelReasoningProps) {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded)
  const [displayDuration, setDisplayDuration] = useState(durationMs)
  const startTimeRef = useRef<number | null>(null)
  const prevThinkingLenRef = useRef<number>(0)
  
  // Track thinking duration in real-time - start when content appears OR isThinking is true
  useEffect(() => {
    // Start timer when thinking begins or when we first get thinking content
    if (isThinking && !startTimeRef.current) {
      startTimeRef.current = Date.now()
    }
    prevThinkingLenRef.current = thinking.length
    
    // Update timer ONLY while isThinking is true
    if (isThinking) {
      const interval = setInterval(() => {
        if (startTimeRef.current) {
          setDisplayDuration(Date.now() - startTimeRef.current)
        }
      }, 100)
      return () => clearInterval(interval)
    } else if (startTimeRef.current) {
      // Finalize duration when thinking stops - freeze the timer
      const finalDuration = durationMs || (Date.now() - startTimeRef.current)
      setDisplayDuration(finalDuration)
      // Don't reset startTimeRef so we keep the final value
    }
  }, [isThinking, durationMs])
  
  // Auto-expand when thinking starts
  useEffect(() => {
    if (isThinking) {
      setIsExpanded(true)
    }
  }, [isThinking])

  if (!thinking && !isThinking) {
    return null
  }

  // Format thinking content for display - add paragraph breaks
  const formattedThinking = thinking
    .split('\n')
    .map(line => line.trim())
    .filter(line => line)
    .join('\n\n')  // Double newline for paragraph spacing

  return (
    <div className={cn(
      "rounded-lg border bg-gradient-to-br from-violet-500/5 to-purple-500/5 border-violet-500/20 text-card-foreground shadow-sm min-w-[280px] w-full",
      className
    )}>
      {/* Header - Collapsible */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-violet-500/10 transition-colors"
      >
        <div className="flex items-center gap-2">
          {isThinking ? (
            <Loader2 className="h-4 w-4 animate-spin text-violet-500" />
          ) : (
            <Sparkles className="h-4 w-4 text-violet-500" />
          )}
          <span className="font-medium text-sm text-violet-700 dark:text-violet-300">
            {isThinking 
              ? `Reasoning... ${displayDuration > 0 ? formatDuration(displayDuration) : ''}` 
              : `Reasoned for ${formatDuration(displayDuration)}`}
          </span>
        </div>
        <div className="flex items-center gap-2">
          {thinking && (
            <span className="text-xs text-muted-foreground">
              {thinking.length > 1000 
                ? `${Math.round(thinking.length / 1000)}k chars` 
                : `${thinking.length} chars`}
            </span>
          )}
          {isExpanded ? (
            <ChevronDown className="h-4 w-4 text-muted-foreground" />
          ) : (
            <ChevronRight className="h-4 w-4 text-muted-foreground" />
          )}
        </div>
      </button>

      {/* Reasoning Content - Expandable */}
      {isExpanded && (
        <div className="border-t border-violet-500/20 px-4 py-3 max-h-80 overflow-y-auto">
          <div className="text-xs text-foreground/90 whitespace-pre-wrap leading-relaxed space-y-2">
            {formattedThinking || (
              <span className="italic text-foreground/60">
                Model is reasoning about your question...
              </span>
            )}
          </div>
          
          {/* Thinking indicator for in-progress */}
          {isThinking && (
            <div className="flex items-center gap-2 mt-3 pt-3 border-t border-dashed border-violet-500/20">
              <div className="flex gap-1">
                <span className="w-1.5 h-1.5 bg-violet-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                <span className="w-1.5 h-1.5 bg-violet-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                <span className="w-1.5 h-1.5 bg-violet-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
              <span className="text-xs text-foreground/60 italic">
                Still thinking...
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default ModelReasoning
