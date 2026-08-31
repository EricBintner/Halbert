// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * AIAnalysisPanel - Reusable AI analysis component.
 *
 * Routes the "Analyze" button through the main agent with the specialist
 * tier and a hardwired retrieval scope ("host"), so the analysis is the
 * same Halbert — same voice, same retrieval, same being config — just
 * scoped to the silo and answered by the thinking model. The turn is
 * persisted as a separate thread; "Continue in chat" hands the analysis
 * context to the main orchestrator.
 */

import { useState, useRef, useCallback, useEffect } from 'react'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import {
  Sparkles,
  Loader2,
  RefreshCw,
  MessageSquare,
} from 'lucide-react'
import { openChat } from '@/components/SendToChat'
import { apiUrl } from '@/lib/apiBase'
import { MarkdownRenderer } from '@/components/domain'

interface AIAnalysisPanelProps {
  /** Type of discovery to analyze (backup, service, storage, network, security) */
  type: string
  /** Title shown in the panel header */
  title: string
  /** Whether analysis can be run (e.g., has data to analyze) */
  canAnalyze?: boolean
  /** Optional context builder function for the "Continue in chat" button */
  buildContext?: () => string
  /** Optional custom research question for "Continue in chat" prefill */
  researchQuestion?: string
  /** Optional override for the analysis prompt sent to the agent (defaults to a generic ${type} analysis) */
  message?: string
  /** Optional label for the analyze button (e.g. "Deep Scan") */
  analyzeLabel?: string
}

export function AIAnalysisPanel({
  type,
  title,
  canAnalyze = true,
  buildContext,
  researchQuestion,
  message,
  analyzeLabel,
}: AIAnalysisPanelProps) {
  const [analysisText, setAnalysisText] = useState('')
  const [thinkingText, setThinkingText] = useState('')
  const [analyzing, setAnalyzing] = useState(false)
  const [hasAnalysis, setHasAnalysis] = useState(false)
  const abortRef = useRef<AbortController | null>(null)

  // Abort any in-flight analysis when the panel unmounts (user navigates away)
  useEffect(() => () => abortRef.current?.abort(), [])

  const runAnalysis = useCallback(async () => {
    // Cancel any in-flight analysis
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

    setAnalyzing(true)
    setAnalysisText('')
    setThinkingText('')
    setHasAnalysis(false)

    const prompt = message ?? `Analyze my ${type} configuration on this system. Look at what's set up, identify any issues, risks, or misconfigurations, and suggest improvements. Be specific about what you find — reference actual config files and settings.`

    try {
      const response = await fetch(apiUrl('/api/agent/message'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: prompt,
          tier: 'specialist',
          scope: 'host',
          max_tokens: 8192,
          temperature: 0.7,
        }),
        signal: controller.signal,
      })

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`)
      }

      const reader = response.body?.getReader()
      const decoder = new TextDecoder()
      if (!reader) throw new Error('No response body')

      let buffer = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          try {
            const data = JSON.parse(line.slice(6))
            if (data.type === 'response_chunk' && data.content) {
              setAnalysisText((prev) => prev + data.content)
              setHasAnalysis(true)
            } else if (data.type === 'thinking' && data.content) {
              setThinkingText((prev) => prev + data.content)
            } else if (data.type === 'error') {
              setAnalysisText(`Analysis error: ${data.message || data.error || 'Unknown error'}`)
              setHasAnalysis(true)
            }
          } catch {
            // Ignore partial JSON
          }
        }
      }
    } catch (err: unknown) {
      if (err instanceof Error && err.name !== 'AbortError') {
        console.error('AI analysis failed:', err)
        setAnalysisText(
          'Unable to connect to Halbert. Please ensure the backend and model are running.',
        )
        setHasAnalysis(true)
      }
    } finally {
      // Only clear analyzing if this controller is still current —
      // a superseded request's finally must not clobber the active one's state.
      if (abortRef.current === controller) {
        setAnalyzing(false)
      }
    }
  }, [type, message])

  const defaultContext = () => {
    if (!analysisText) return `Analyzing ${type}...`
    return `## ${title} Analysis\n\n${analysisText}`
  }

  const defaultQuestion = `Give me a detailed analysis of my ${type} configuration, including potential risks and improvement suggestions.`

  return (
    // A sky-to-purple gradient is the "AI feature" cliché the brand rejects
    // outright, and this panel renders on six pages, so it was the single most
    // off-brand thing in the product. It is a proposal grounded in retrieval,
    // which is what the telemetry pigment means.
    <Card className="border-status-telemetry/30 bg-status-telemetry-bg">
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-start gap-3 flex-1">
            <div className="p-2 rounded-md bg-surface">
              <Sparkles className="h-5 w-5 text-status-telemetry" />
            </div>
            <div className="flex-1 min-w-0">
              <h3 className="font-semibold text-foreground flex items-center gap-2">
                AI {title} Analysis
              </h3>
              {hasAnalysis || analyzing ? (
                <div className="mt-2 space-y-2">
                  {thinkingText && analyzing && (
                    <p className="text-xs text-muted-foreground/60 italic">
                      {thinkingText.slice(-200)}
                    </p>
                  )}
                  {analysisText ? (
                    <div className="text-sm text-muted-foreground prose prose-sm max-w-none dark:prose-invert">
                      <MarkdownRenderer text={analysisText} />
                    </div>
                  ) : analyzing ? (
                    <p className="text-sm text-muted-foreground">Thinking...</p>
                  ) : null}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground mt-1">
                  Get AI-powered insights about your {type} configuration and recommendations for improvement.
                </p>
              )}
            </div>
          </div>

          {/* Action buttons */}
          <div className="flex gap-2 shrink-0">
            <Button
              variant="outline"
              size="sm"
              onClick={runAnalysis}
              disabled={analyzing || !canAnalyze}
            >
              {analyzing ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Analyzing...
                </>
              ) : (
                <>
                  {hasAnalysis ? <RefreshCw className="h-4 w-4 mr-2" /> : <Sparkles className="h-4 w-4 mr-2" />}
                  {hasAnalysis ? 'Refresh' : analyzeLabel ?? 'Analyze'}
                </>
              )}
            </Button>
            {hasAnalysis && (
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8"
                title="Continue in chat"
                onClick={() => openChat({
                  title,
                  type,
                  context: buildContext ? buildContext() : defaultContext(),
                  newConversation: true,
                  prefillMessage: researchQuestion || defaultQuestion,
                })}
              >
                <MessageSquare className="h-4 w-4" />
              </Button>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

/**
 * Compact version for embedding in cards/sections
 */
interface AIQuickAnalysisProps {
  type: string
  itemName: string
  context: string
}

export function AIQuickAnalysis({ type, itemName, context }: AIQuickAnalysisProps) {
  return (
    <div className="flex items-center gap-2 mt-2">
      <Button
        variant="ghost"
        size="sm"
        className="gap-1"
        onClick={() => openChat({
          title: itemName,
          type,
          context,
          newConversation: true,
          prefillMessage: `Analyze ${itemName} and suggest improvements.`,
        })}
      >
        <MessageSquare className="h-3 w-3" />
        Ask AI
      </Button>
    </div>
  )
}
