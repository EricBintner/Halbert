// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { useCallback } from 'react'
import { ExternalLink, ShieldCheck, AlertTriangle } from 'lucide-react'
import { AIModelsSettings } from '@/components/llm'
import { useLLMConfig } from '@/hooks/useLLMConfig'
import { useSourcePrepDaemon } from '@/hooks/useSourcePrepDaemon'
import { Button } from '@/components/prep-primitives'

/**
 * UnifiedLLMSettings — wrapper that renders AIModelsSettings with daemon-detection deferral.
 *
 * When the SourcePrep daemon is detected on :8400:
 *   - The native LLM picker is disabled
 *   - A banner links to the SourcePrep dashboard for model management
 *
 * When the daemon is down:
 *   - The native AIModelsSettings picker is fully active
 */
export function UnifiedLLMSettings() {
  const daemon = useSourcePrepDaemon()
  const llm = useLLMConfig()

  const handleModeApply = useCallback(async () => {
    await llm.flushPendingSave()
  }, [llm])

  // ── Daemon is running — defer to SourcePrep dashboard ───────
  if (daemon.isDaemonRunning) {
    return (
      <div className="space-y-4">
        <div className="rounded-lg border border-border p-6 bg-surface">
          <div className="flex items-start gap-3">
            <ShieldCheck className="h-5 w-5 text-success flex-shrink-0 mt-0.5" />
            <div className="space-y-2 flex-1">
              <h3 className="text-base font-semibold text-text">
                SourcePrep daemon is managing LLM models
              </h3>
              <p className="text-sm text-text-muted">
                The SourcePrep daemon is running on port {daemon.daemonUrl.replace('http://', '')}.
                Model configuration is managed centrally through the SourcePrep dashboard to keep
                Halbert and SourcePrep in sync.
              </p>
              <div className="flex items-center gap-3 pt-2">
                <a href={`${daemon.daemonUrl}/?settings=chunking-embeddings`} target="_blank" rel="noopener noreferrer">
                  <Button variant="default" size="sm">
                    <ExternalLink className="h-4 w-4" />
                    Open SourcePrep Settings
                  </Button>
                </a>
                <span className="text-xs text-text-subtle">
                  The native model picker will re-enable when the daemon stops.
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    )
  }

  // ── Daemon is down — render native AIModelsSettings ─────────
  return (
    <div className="space-y-4">
      {daemon.isProbing ? null : (
        <div className="flex items-center gap-2 text-xs text-text-subtle">
          <AlertTriangle className="h-3.5 w-3.5" />
          <span>
            SourcePrep daemon not detected — using Halbert's native model picker.
            Start the daemon with <code className="bg-surface-raised px-1 rounded">prep serve</code> to unify.
          </span>
        </div>
      )}
      <AIModelsSettings
        config={llm.llmConfig}
        onConfigChange={llm.handleLLMConfigChange}
        onAddEndpoint={llm.handleAddEndpoint}
        onEditEndpoint={llm.handleEditEndpoint}
        onDeleteEndpoint={llm.handleDeleteEndpoint}
        onTestEndpoint={llm.handleTestEndpoint}
        onFetchModels={llm.handleFetchModels}
        onTestModel={llm.handleTestModel}
        onClearTestResult={llm.handleClearTestResult}
        onHFDownload={llm.handleDownloadModel}
        availableModels={llm.availableModels}
        modelDetails={llm.modelDetails}
        loadingModels={llm.loadingModels}
        cloudModels={llm.cloudModels}
        loadingCloudModels={llm.loadingCloudModels}
        onFetchCloudModels={llm.handleFetchCloudModels}
        testingSlot={llm.testingSlot}
        testResults={llm.testResults}
        onModeApply={handleModeApply}
      />
    </div>
  )
}
