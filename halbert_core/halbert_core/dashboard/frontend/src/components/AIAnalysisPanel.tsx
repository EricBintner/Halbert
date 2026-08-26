// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * AIAnalysisPanel - Reusable AI analysis component.
 * 
 * Provides a consistent UI for AI-powered analysis across all pages.
 * Supports quick analysis (guide model) and deep research (specialist model).
 */

import { useState } from 'react'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { 
  Sparkles, 
  AlertCircle, 
  Info, 
  Loader2,
  RefreshCw,
  MessageSquare,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { openChat } from '@/components/SendToChat'
import { api } from '@/lib/api'

export interface AIAnalysis {
  analysis: string
  recommendations: string[]
  health_score: number
  issues_found: boolean
  critical_issues?: string[]
  model_used?: string
}

interface AIAnalysisPanelProps {
  /** Type of discovery to analyze (backup, service, storage, network, security) */
  type: string
  /** Title shown in the panel header */
  title: string
  /** Whether analysis can be run (e.g., has data to analyze) */
  canAnalyze?: boolean
  /** Optional context builder function for research button */
  buildContext?: () => string
  /** Optional custom research question */
  researchQuestion?: string
  /** Icon color class */
}

export function AIAnalysisPanel({
  type,
  title,
  canAnalyze = true,
  buildContext,
  researchQuestion,
}: AIAnalysisPanelProps) {
  const [analysis, setAnalysis] = useState<AIAnalysis | null>(null)
  const [analyzing, setAnalyzing] = useState(false)

  const runAnalysis = async () => {
    setAnalyzing(true)
    try {
      const result = await api.analyzeDiscoveries(type, true)  // Use specialist model for deep analysis
      setAnalysis(result)
    } catch (error) {
      console.error('AI analysis failed:', error)
      setAnalysis({
        analysis: 'Unable to connect to AI. Please ensure Ollama is running.',
        health_score: 0,
        issues_found: true,
        recommendations: ['Start Ollama service', 'Check network connectivity'],
      })
    } finally {
      setAnalyzing(false)
    }
  }

  const defaultContext = () => {
    if (!analysis) return `Analyzing ${type}...`
    return `## ${title} Analysis\n\n${analysis.analysis}\n\nHealth Score: ${analysis.health_score}%`
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
                {analysis && (
                  <Badge variant="outline" className={cn(
                    "ml-2",
                    analysis.health_score >= 80 ? "border-success/50 text-success" :
                    analysis.health_score >= 50 ? "border-warning/50 text-warning" :
                    "border-error/50 text-error"
                  )}>
                    Health: {analysis.health_score}%
                  </Badge>
                )}
              </h3>
              {analysis ? (
                <div className="mt-2 space-y-3">
                  <p className="text-sm text-muted-foreground">{analysis.analysis}</p>
                  
                  {/* Critical Issues */}
                  {analysis.critical_issues && analysis.critical_issues.length > 0 && (
                    <div className="p-2 rounded-md bg-error-muted border border-error/30">
                      <p className="text-xs font-semibold text-error mb-1">⚠️ Critical Issues:</p>
                      <ul className="space-y-1">
                        {analysis.critical_issues.map((issue, i) => (
                          <li key={i} className="text-sm text-error flex items-start gap-2">
                            <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
                            {issue}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  
                  {/* Recommendations */}
                  {analysis.recommendations.length > 0 && (
                    <div className="mt-3">
                      <p className="text-xs font-semibold text-muted-foreground mb-2">Recommendations:</p>
                      <ul className="space-y-1">
                        {analysis.recommendations.map((rec, i) => (
                          <li key={i} className="text-sm text-muted-foreground flex items-start gap-2">
                            <Info className="h-4 w-4 shrink-0 mt-0.5 text-status-telemetry" />
                            {rec}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  
                  {/* Model info */}
                  {analysis.model_used && (
                    <p className="text-xs text-muted-foreground/60">
                      Analyzed using {analysis.model_used}
                    </p>
                  )}
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
                  {analysis ? <RefreshCw className="h-4 w-4 mr-2" /> : <Sparkles className="h-4 w-4 mr-2" />}
                  {analysis ? 'Refresh' : 'Analyze'}
                </>
              )}
            </Button>
            {analysis && (
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
