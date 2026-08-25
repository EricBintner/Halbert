import { useState, useCallback, useEffect, useRef, useMemo } from 'react'
import type {
  LLMConfig,
  SavedEndpoint,
  EndpointTestResult,
  LLMSlotsStatus,
  AssignmentMode,
} from '@/types/llm'
import { stripModeFields } from '@/components/llm/llmConfigHelpers'

interface UseLLMConfigOptions {
  onDirty?: () => void
  onSwapModel?: () => void
  onWarnings?: (warnings: string[]) => void
}

/**
 * Halbert's LLM config hook — adapted from SourcePrep's useLLMConfig.
 *
 * Manages LLM endpoint configuration, model fetching/testing, slot status,
 * and auto-persistence via the Halbert LLM router (dashboard/routes/llm.py).
 *
 * Key differences from SourcePrep's hook:
 * - No SQLite settings store — uses YAML (models.yml) via PUT /global/config
 * - No compute node management (Halbert is single-node)
 * - No assignment blocks / mapped mode (Halbert uses structured mode only)
 * - No mode switch (always structured)
 * - Slot status is a stub (Halbert has no pipeline scheduler)
 */
export function useLLMConfig({ onDirty, onSwapModel, onWarnings }: UseLLMConfigOptions = {}) {
  const onDirtyRef = useRef(onDirty)
  onDirtyRef.current = onDirty
  const onSwapModelRef = useRef(onSwapModel)
  onSwapModelRef.current = onSwapModel
  const onWarningsRef = useRef(onWarnings)
  onWarningsRef.current = onWarnings

  const persistEndpointsWithWarnings = useCallback(
    async (saved_endpoints: SavedEndpoint[]): Promise<void> => {
      try {
        const r = await fetch('/global/config', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ llm_config: { saved_endpoints } as unknown as LLMConfig }),
        })
        if (!r.ok) return
        const json = await r.json()
        const warnings = json?.warnings ?? []
        if (Array.isArray(warnings) && warnings.length > 0) {
          onWarningsRef.current?.(warnings)
        }
      } catch {
        // Silent — fire-and-forget
      }
    },
    [],
  )

  // ── State ───────────────────────────────────────────────────
  const [llmConfig, setLLMConfig] = useState<LLMConfig>({
    saved_endpoints: [
      { id: 'default_ollama', name: 'Default Ollama', provider: 'ollama', url: 'http://localhost:11434' },
    ],
    embedding: { source: 'endpoint', endpoint_id: 'default_ollama', model: 'nomic-embed-text' },
    small_model: { enabled: false },
    large_model: { enabled: false },
    code_model: { enabled: false },
  })
  const [availableModels, setAvailableModels] = useState<Record<string, string[]>>({})
  const [modelDetails, setModelDetails] = useState<Record<string, Array<{ name: string; context_window?: string; cost_tier?: string; rate_limits?: { rpd?: number; rpm?: number }; batch_estimate?: { files_per_request: number; daily_file_capacity?: number } }>>>({})
  const [loadingModels, setLoadingModels] = useState<Record<string, boolean>>({})
  const [cloudModels, setCloudModels] = useState<Record<string, string[]>>({})
  const [loadingCloudModels, setLoadingCloudModels] = useState<Record<string, boolean>>({})
  const [testingSlot, setTestingSlot] = useState<'embedding' | 'small' | 'large' | 'code' | 'coordinator' | null>(null)
  const [testResults, setTestResults] = useState<Record<string, EndpointTestResult>>({})
  const [llmSlotsStatus, setLlmSlotsStatus] = useState<LLMSlotsStatus | null>(null)

  const mergeContextCache = useCallback((details: Array<{ name: string; context_tokens?: number }>) => {
    const updates: Record<string, number> = {}
    for (const d of details) {
      if (d.context_tokens && d.context_tokens > 0) {
        updates[d.name] = d.context_tokens
      }
    }
    if (Object.keys(updates).length === 0) return
    setLLMConfig((prev) => ({
      ...prev,
      model_context_cache: { ...prev.model_context_cache, ...updates },
    }))
    onDirtyRef.current?.()
  }, [])

  const handleClearTestResult = useCallback((slot: string) => {
    setTestResults((prev) => {
      const next = { ...prev }
      delete next[slot]
      return next
    })
  }, [])

  // ── Handlers ────────────────────────────────────────────────

  const handleLLMConfigChange = useCallback((cfg: LLMConfig) => {
    setLLMConfig(cfg)
    onDirtyRef.current?.()
  }, [])

  const handleAddEndpoint = useCallback((endpoint: Omit<SavedEndpoint, 'id'>) => {
    const id = `ep_${Date.now()}_${Math.random().toString(16).slice(2)}`
    setLLMConfig((prev) => {
      const saved_endpoints = [...prev.saved_endpoints, { ...endpoint, id }]
      void persistEndpointsWithWarnings(saved_endpoints)
      return { ...prev, saved_endpoints }
    })
    onDirtyRef.current?.()
  }, [persistEndpointsWithWarnings])

  const handleEditEndpoint = useCallback((endpoint: SavedEndpoint) => {
    setLLMConfig((prev) => {
      const saved_endpoints = prev.saved_endpoints.map((e) => (e.id === endpoint.id ? endpoint : e))
      void persistEndpointsWithWarnings(saved_endpoints)
      return { ...prev, saved_endpoints }
    })
    onDirtyRef.current?.()
  }, [persistEndpointsWithWarnings])

  const handleDeleteEndpoint = useCallback((id: string) => {
    setLLMConfig((prev) => {
      const saved_endpoints = prev.saved_endpoints.filter((e) => e.id !== id)
      void persistEndpointsWithWarnings(saved_endpoints)
      return { ...prev, saved_endpoints }
    })
    onDirtyRef.current?.()
  }, [persistEndpointsWithWarnings])

  const handleTestEndpoint = useCallback(async (endpoint: SavedEndpoint) => {
    const r = await fetch('/api/llm/proxy/test', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ provider: endpoint.provider, url: endpoint.url, api_key: endpoint.api_key }),
    })
    if (!r.ok) throw new Error(`HTTP ${r.status}`)
    const json = await r.json()
    const data = json?.data ?? json
    if (Array.isArray(data.models)) {
      setAvailableModels((prev) => ({ ...prev, [endpoint.id]: data.models }))
    }
    return data as EndpointTestResult
  }, [])

  const handleFetchModels = useCallback(async (endpointId: string, slot?: string) => {
    const ep = llmConfig.saved_endpoints.find((e) => e.id === endpointId)
    if (!ep) return []
    setLoadingModels((prev) => ({ ...prev, [endpointId]: true }))
    try {
      const r = await fetch('/api/llm/proxy/models', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider: ep.provider, url: ep.url, api_key: ep.api_key, slot }),
      })
      const json = await r.json().catch(() => null)
      if (!r.ok) {
        const errMsg = json?.error?.message || json?.message || `HTTP ${r.status}`
        console.warn(`[LLM] Failed to fetch models for ${ep.provider}: ${errMsg}`)
        return []
      }
      const data = json?.data ?? json
      const models = Array.isArray(data.models) ? data.models : []
      setAvailableModels((prev) => ({ ...prev, [endpointId]: models }))
      if (Array.isArray(data.model_details)) {
        setModelDetails((prev) => ({ ...prev, [endpointId]: data.model_details }))
        mergeContextCache(data.model_details)
      }
      return models
    } catch (e) {
      console.warn('[LLM] Model fetch error:', e)
      return []
    } finally {
      setLoadingModels((prev) => ({ ...prev, [endpointId]: false }))
    }
  }, [llmConfig.saved_endpoints, mergeContextCache])

  const handleFetchCloudModels = useCallback(async (endpointId: string): Promise<string[]> => {
    const ep = llmConfig.saved_endpoints.find((e) => e.id === endpointId)
    if (!ep || ep.provider !== 'ollama') return []
    if (endpointId in cloudModels) return cloudModels[endpointId]
    setLoadingCloudModels((prev) => ({ ...prev, [endpointId]: true }))
    try {
      const r = await fetch('/api/llm/proxy/cloud-models', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider: ep.provider, url: ep.url, api_key: ep.api_key }),
      })
      const json = await r.json().catch(() => null)
      if (!r.ok) return []
      const data = json?.data ?? json
      const models: string[] = Array.isArray(data.cloud_models) ? data.cloud_models : []
      setCloudModels((prev) => ({ ...prev, [endpointId]: models }))
      return models
    } catch (e) {
      console.warn('[LLM] Cloud model fetch error:', e)
      return []
    } finally {
      setLoadingCloudModels((prev) => ({ ...prev, [endpointId]: false }))
    }
  }, [llmConfig.saved_endpoints, cloudModels])

  const handleTestModel = useCallback(async (slotType: 'embedding' | 'small' | 'large' | 'code' | 'coordinator') => {
    let endpointId: string | undefined
    let model: string | undefined
    let kind = 'completion'
    if (slotType === 'embedding') {
      endpointId = llmConfig.embedding.endpoint_id; model = llmConfig.embedding.model; kind = 'embedding'
    } else if (slotType === 'small') {
      endpointId = llmConfig.small_model.endpoint_id; model = llmConfig.small_model.model
    } else if (slotType === 'code') {
      endpointId = llmConfig.code_model.endpoint_id; model = llmConfig.code_model.model
    } else if (slotType === 'coordinator') {
      endpointId = llmConfig.coordinator_model?.endpoint_id; model = llmConfig.coordinator_model?.model
    } else {
      endpointId = llmConfig.large_model.endpoint_id; model = llmConfig.large_model.model
    }
    const ep = llmConfig.saved_endpoints.find((e) => e.id === endpointId)
    if (!ep || !model) {
      const res: EndpointTestResult = { success: false, message: 'Model not configured.' }
      setTestResults((prev) => ({ ...prev, [slotType]: res }))
      return res
    }
    setTestingSlot(slotType)
    try {
      const slotKey = slotType === 'small' ? 'small_model' : slotType === 'large' ? 'large_model' : slotType === 'code' ? 'code_model' : slotType === 'coordinator' ? 'coordinator_model' : undefined
      const r = await fetch('/api/llm/proxy/test-model', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider: ep.provider, url: ep.url, api_key: ep.api_key, model, kind, slot: slotKey }),
      })
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      const json = await r.json()
      const data = (json?.data ?? json) as EndpointTestResult
      setTestResults((prev) => ({ ...prev, [slotType]: data }))
      return data
    } finally {
      setTestingSlot(null)
    }
  }, [llmConfig])

  const fetchLLMSlotsStatus = useCallback(async () => {
    try {
      const r = await fetch('/llm/slots/status')
      if (!r.ok) return
      const json = await r.json()
      const data = json?.data ?? json
      setLlmSlotsStatus(data as LLMSlotsStatus)
    } catch {
      // Silent
    }
  }, [])

  const handleDownloadModel = useCallback(async (slot: 'embedding') => {
    try {
      if (slot === 'embedding') {
        await fetch('/embedding/download', { method: 'POST' })
      }
    } catch (err) {
      console.error(`Failed to trigger ${slot} download:`, err)
    }
  }, [])

  const handleModeSwitch = useCallback(async (mode: AssignmentMode, _blocks?: LLMConfig['assignment_blocks']) => {
    // Halbert only supports structured mode — no-op for mapped mode
    setLLMConfig((prev) => ({
      ...prev,
      assignment_mode: mode,
    }))
    void fetchLLMSlotsStatus()
  }, [fetchLLMSlotsStatus])

  // ── Debounced auto-save ─────────────────────────────────────
  const [autoSaveEnabled, setAutoSaveEnabled] = useState(false)
  const saveValue = useMemo(() => stripModeFields(llmConfig), [llmConfig])
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (!autoSaveEnabled) return
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current)
    saveTimerRef.current = setTimeout(async () => {
      try {
        const r = await fetch('/global/config', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ llm_config: llmConfig }),
        })
        if (r.ok) {
          const json = await r.json()
          const warnings = json?.warnings ?? []
          if (Array.isArray(warnings) && warnings.length > 0) {
            onWarningsRef.current?.(warnings)
          }
        }
      } catch {
        // Silent fail
      }
    }, 1500)
    return () => {
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current)
    }
  }, [saveValue, autoSaveEnabled, llmConfig])

  const markLLMConfigClean = useCallback(() => {
    setAutoSaveEnabled(true)
  }, [])

  const flushPendingSave = useCallback(async () => {
    if (saveTimerRef.current) {
      clearTimeout(saveTimerRef.current)
      saveTimerRef.current = null
    }
    try {
      await fetch('/global/config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ llm_config: llmConfig }),
      })
    } catch {
      // Silent
    }
  }, [llmConfig])

  // ── Load config from backend on mount ───────────────────────
  useEffect(() => {
    (async () => {
      try {
        const r = await fetch('/global/config')
        if (!r.ok) return
        const json = await r.json()
        const data = json?.data ?? json
        const llmCfg = data?.llm_config
        if (llmCfg && typeof llmCfg === 'object') {
          setLLMConfig((prev) => ({ ...prev, ...llmCfg }))
        }
        markLLMConfigClean()
      } catch {
        // Silent — use defaults
        markLLMConfigClean()
      }
    })()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // ── Auto-fetch models for pre-configured endpoints ──────────
  useEffect(() => {
    const endpointIds = new Set<string>()
    if (llmConfig.embedding.source === 'endpoint' && llmConfig.embedding.endpoint_id) {
      endpointIds.add(llmConfig.embedding.endpoint_id)
    }
    if (llmConfig.small_model.endpoint_id) endpointIds.add(llmConfig.small_model.endpoint_id)
    if (llmConfig.large_model.endpoint_id) endpointIds.add(llmConfig.large_model.endpoint_id)
    if (llmConfig.coordinator_model?.endpoint_id) endpointIds.add(llmConfig.coordinator_model.endpoint_id)

    for (const epId of endpointIds) {
      if (!availableModels[epId]?.length) {
        void handleFetchModels(epId)
      }
    }
  // Run once on mount
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return {
    llmConfig,
    setLLMConfig,
    availableModels,
    modelDetails,
    loadingModels,
    cloudModels,
    loadingCloudModels,
    testingSlot,
    testResults,
    llmSlotsStatus,
    handleLLMConfigChange,
    handleAddEndpoint,
    handleEditEndpoint,
    handleDeleteEndpoint,
    handleTestEndpoint,
    handleFetchModels,
    handleFetchCloudModels,
    handleTestModel,
    handleClearTestResult,
    handleDownloadModel,
    handleModeSwitch,
    markLLMConfigClean,
    fetchLLMSlotsStatus,
    flushPendingSave,
  }
}
