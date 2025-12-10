/**
 * AIAnalysisPanel - Reusable AI analysis component.
 * 
 * Provides a consistent UI for AI-powered analysis across all pages.
 * Supports quick analysis (7b model) and deep research (70b model).
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
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { ResearchButton } from '@/components/SendToChat'
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
  /** Gradient colors for the panel (from-X to-Y) */
  gradientFrom?: string
  gradientTo?: string
  /** Icon color class */
  iconColor?: string
}

export function AIAnalysisPanel({
  type,
  title,
  canAnalyze = true,
  buildContext,
  researchQuestion,
  gradientFrom = 'from-blue-50/50',
  gradientTo = 'to-purple-50/50',
  iconColor = 'text-blue-600 dark:text-blue-400',
}: AIAnalysisPanelProps) {
  const [analysis, setAnalysis] = useState<AIAnalysis | null>(null)
  const [analyzing, setAnalyzing] = useState(false)

  const runAnalysis = async () => {
    setAnalyzing(true)
    try {
      const result = await api.analyzeDiscoveries(type, false)
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
    <Card className={cn(
      "border-blue-200 bg-gradient-to-r dark:from-blue-950/20 dark:to-purple-950/20",
      gradientFrom,
      gradientTo
    )}>
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-start gap-3 flex-1">
            <div className="p-2 rounded-lg bg-blue-100 dark:bg-blue-900/50">
              <Sparkles className={cn("h-5 w-5", iconColor)} />
            </div>
            <div className="flex-1 min-w-0">
              <h3 className="font-semibold text-blue-900 dark:text-blue-100 flex items-center gap-2">
                AI {title} Analysis
                {analysis && (
                  <Badge variant="outline" className={cn(
                    "ml-2",
                    analysis.health_score >= 80 ? "border-green-500 text-green-600" :
                    analysis.health_score >= 50 ? "border-yellow-500 text-yellow-600" :
                    "border-red-500 text-red-600"
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
                    <div className="p-2 rounded bg-red-100 dark:bg-red-900/30 border border-red-200 dark:border-red-800">
                      <p className="text-xs font-semibold text-red-700 dark:text-red-300 mb-1">⚠️ Critical Issues:</p>
                      <ul className="space-y-1">
                        {analysis.critical_issues.map((issue, i) => (
                          <li key={i} className="text-sm text-red-600 dark:text-red-400 flex items-start gap-2">
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
                            <Info className="h-4 w-4 shrink-0 mt-0.5 text-blue-500" />
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
              <ResearchButton
                context={buildContext ? buildContext() : defaultContext()}
                title={title}
                type={type}
                question={researchQuestion || defaultQuestion}
              />
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
      <ResearchButton
        context={context}
        title={itemName}
        type={type}
        question={`Analyze ${itemName} and suggest improvements.`}
        size="sm"
        variant="ghost"
      />
    </div>
  )
}
