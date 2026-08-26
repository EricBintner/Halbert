// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { useCallback } from 'react'
import { ExternalLink, Info } from 'lucide-react'
import { AIModelsSettings } from '@/components/llm'
import { useLLMConfig } from '@/hooks/useLLMConfig'
import { useSourcePrepDaemon } from '@/hooks/useSourcePrepDaemon'

/**
 * UnifiedLLMSettings — wrapper that renders AIModelsSettings with an
 * informational banner when the SourcePrep daemon is detected.
 *
 * The picker is ALWAYS visible. When the SourcePrep daemon is running on
 * :8400, a banner notes that SourcePrep's dashboard also has model settings
 * and provides a deep link — but it does NOT hide Halbert's native picker.
 * Halbert needs its own model configuration (Fast, Thinking, Vision) that
 * is independent of SourcePrep's pipeline slots.
 */
export function UnifiedLLMSettings() {
  const daemon = useSourcePrepDaemon()
  const llm = useLLMConfig()

  const handleModeApply = useCallback(async () => {
    await llm.flushPendingSave()
  }, [llm])

  return (
    <div className="space-y-4">
      {/* SourcePrep daemon detected — informational banner (non-blocking) */}
      {daemon.isDaemonRunning && !daemon.isProbing && (
        <div className="rounded-lg border border-border p-4 bg-surface">
          <div className="flex items-start gap-3">
            <Info className="h-4 w-4 text-info flex-shrink-0 mt-0.5" />
            <div className="flex-1">
              <p className="text-sm text-text-muted">
                SourcePrep daemon is running on port {daemon.daemonUrl.replace('http://', '')}.
                Halbert's model settings below are shared with SourcePrep via the same config.
                You can also manage models from the{' '}
                <a
                  href={`${daemon.daemonUrl}/?settings=chunking-embeddings`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-primary hover:underline"
                >
                  SourcePrep dashboard
                  <ExternalLink className="h-3 w-3" />
                </a>.
              </p>
            </div>
          </div>
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
