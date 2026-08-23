/**
 * CompressionSettings - Context Compression Settings Card
 *
 * Configures the 3-tier compression system:
 * - LinguaCompressor: LLMLingua-2 neural token pruning (178MB, CPU-only)
 * - SemanticCompressor: Rule-based regex compression (zero deps)
 * - MemoryLOD: 6-level structural LOD for memories
 *
 * The app works with or without neural compression enabled.
 */

import { useState, useEffect } from 'react'
import {
  Zap,
  Info,
  Loader2,
  Check,
  Cpu,
  Gauge,
  FlaskConical,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select } from '@/components/ui/select'

const API_BASE = '/api'

interface CompressionStatus {
  available: boolean
  model?: string
  loaded?: boolean
  downloaded?: boolean
  type: string  // lingua | semantic | noop
  error?: string
}

interface CompressionConfig {
  enabled: boolean
  backend: string  // auto | lingua | semantic | noop
  threshold: number
  level: string  // light | standard | aggressive
  lod_epistemic_floor: number
}

interface TestResult {
  input_chars: number
  input_preview: string
  active_backend: string
  results: {
    [key: string]: {
      output_chars: number
      compression_ratio: number
      timing_ms: number
      compressed_preview: string
    }
  }
}

export function CompressionSettings() {
  const [status, setStatus] = useState<CompressionStatus | null>(null)
  const [config, setConfig] = useState<CompressionConfig | null>(null)
  const [loading, setLoading] = useState(true)
  const [showInfo, setShowInfo] = useState(false)
  const [actionMessage, setActionMessage] = useState<{ type: 'success' | 'error' | 'info', text: string } | null>(null)
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<TestResult | null>(null)
  const [testText, setTestText] = useState('')

  useEffect(() => {
    loadStatus()
    loadConfig()
  }, [])

  const loadStatus = async () => {
    try {
      const res = await fetch(`${API_BASE}/compression/status`)
      const data = await res.json()
      setStatus(data)
    } catch (err) {
      console.error('Failed to load compression status:', err)
    }
    setLoading(false)
  }

  const loadConfig = async () => {
    try {
      const res = await fetch(`${API_BASE}/compression/config`)
      const data = await res.json()
      setConfig(data)
    } catch (err) {
      console.error('Failed to load compression config:', err)
    }
  }

  const handleUpdateConfig = async (updates: Partial<CompressionConfig>) => {
    try {
      const res = await fetch(`${API_BASE}/compression/config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updates),
      })
      const data = await res.json()
      if (data.status === 'ok') {
        setConfig(data.config)
        setActionMessage({ type: 'success', text: 'Configuration updated' })
      } else {
        setActionMessage({ type: 'error', text: data.detail || 'Update failed' })
      }
    } catch (err) {
      setActionMessage({ type: 'error', text: 'Failed to update config' })
      console.error('Failed to update config:', err)
    }
  }

  const handleTest = async () => {
    if (!testText.trim()) {
      setActionMessage({ type: 'error', text: 'Enter text to test compression' })
      return
    }
    setTesting(true)
    setActionMessage({ type: 'info', text: 'Running test compression...' })
    try {
      const res = await fetch(`${API_BASE}/compression/test`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: testText }),
      })
      const data = await res.json()
      setTestResult(data)
      setActionMessage({ type: 'success', text: `Test complete: ${data.input_chars} chars compressed via ${data.active_backend}` })
    } catch (err) {
      setActionMessage({ type: 'error', text: 'Test failed' })
      console.error('Test compression failed:', err)
    }
    setTesting(false)
  }

  if (loading) {
    return (
      <Card>
        <CardContent className="py-6">
          <div className="flex items-center justify-center gap-2 text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />Loading compression status...
          </div>
        </CardContent>
      </Card>
    )
  }

  const isActive = status?.available ?? false
  const backendLabel = status?.type === 'lingua' ? 'LLMLingua-2 (Neural)' :
                       status?.type === 'semantic' ? 'Semantic (Rule-based)' :
                       status?.type === 'noop' ? 'Noop (Pass-through)' : 'Unknown'

  return (
    <Card className={isActive ? "border-green-500/50" : ""}>
      <CardContent className="py-4">
        {/* Header */}
        <div className="flex items-center gap-1.5 mb-1">
          <Zap className={`h-4 w-4 flex-shrink-0 ${isActive ? 'text-green-500' : ''}`} />
          <span className="font-semibold text-sm">Context Compression</span>
          <button
            onClick={() => setShowInfo(!showInfo)}
            className="p-0.5 hover:bg-muted rounded"
          >
            <Info className="h-3.5 w-3.5 text-muted-foreground" />
          </button>
          {isActive && (
            <span className="ml-auto text-xs bg-green-500/10 text-green-600 px-2 py-0.5 rounded flex items-center gap-1">
              <Cpu className="h-3 w-3" />{backendLabel}
            </span>
          )}
        </div>
        <p className="text-xs text-muted-foreground mb-3">
          3-tier compression: LLMLingua-2 + Semantic + MemoryLOD
        </p>

        <div className="space-y-3">
          {/* Backend Status */}
          <div className="p-3 bg-muted/30 rounded-lg space-y-2">
            <Label className="text-xs font-medium flex items-center gap-1">
              <Cpu className="h-3 w-3" />Active Backend
            </Label>
            <div className="flex items-center justify-between">
              <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
                <span className={`flex items-center gap-1 ${status?.available ? 'text-green-600' : 'text-muted-foreground'}`}>
                  {status?.available ? <Check className="h-3 w-3" /> : <div className="h-3 w-3 rounded-full border border-current" />}
                  Available
                </span>
                {status?.type === 'lingua' && (
                  <span className={`flex items-center gap-1 ${status?.loaded ? 'text-green-600' : 'text-muted-foreground'}`}>
                    {status?.loaded ? <Check className="h-3 w-3" /> : <div className="h-3 w-3 rounded-full border border-current" />}
                    Model Loaded
                  </span>
                )}
                {status?.type === 'lingua' && (
                  <span className={`flex items-center gap-1 ${status?.downloaded ? 'text-green-600' : 'text-muted-foreground'}`}>
                    {status?.downloaded ? <Check className="h-3 w-3" /> : <div className="h-3 w-3 rounded-full border border-current" />}
                    Downloaded
                  </span>
                )}
              </div>
            </div>
            <p className="text-xs text-muted-foreground">
              {status?.type === 'lingua' && '178MB model, CPU-only, lazy-loaded on first use'}
              {status?.type === 'semantic' && 'Zero dependencies, always available, regex-based'}
              {status?.type === 'noop' && 'No compression (pass-through)'}
            </p>
          </div>

          {/* Configuration */}
          {config && (
            <div className="p-3 bg-muted/30 rounded-lg space-y-3">
              <Label className="text-xs font-medium flex items-center gap-1">
                <Gauge className="h-3 w-3" />Configuration
              </Label>

              {/* Backend selector */}
              <div className="space-y-1">
                <Label className="text-xs text-muted-foreground">Backend</Label>
                <Select
                  value={config.backend}
                  onChange={(e) => handleUpdateConfig({ backend: e.target.value })}
                  variant="sm"
                >
                  <option value="auto">Auto (best available)</option>
                  <option value="lingua">Lingua (neural, 178MB)</option>
                  <option value="semantic">Semantic (rule-based)</option>
                  <option value="noop">Noop (no compression)</option>
                </Select>
              </div>

              {/* Compression level */}
              <div className="space-y-1">
                <Label className="text-xs text-muted-foreground">Compression Level</Label>
                <Select
                  value={config.level}
                  onChange={(e) => handleUpdateConfig({ level: e.target.value })}
                  variant="sm"
                >
                  <option value="light">Light (60% keep)</option>
                  <option value="standard">Standard (40% keep)</option>
                  <option value="aggressive">Aggressive (25% keep)</option>
                </Select>
              </div>

              {/* Threshold */}
              <div className="space-y-1">
                <Label className="text-xs text-muted-foreground">Threshold (tokens)</Label>
                <Input
                  type="number"
                  value={config.threshold}
                  onChange={(e) => {
                    const v = parseInt(e.target.value) || 4000
                    setConfig({ ...config, threshold: v })
                  }}
                  onBlur={(e) => handleUpdateConfig({ threshold: parseInt(e.target.value) || 4000 })}
                  className="h-8 text-xs"
                />
                <p className="text-xs text-muted-foreground">Compress when context exceeds this many tokens</p>
              </div>

              {/* Epistemic floor */}
              <div className="space-y-1">
                <Label className="text-xs text-muted-foreground">LOD Epistemic Floor</Label>
                <Input
                  type="number"
                  step="0.1"
                  min="0"
                  max="1"
                  value={config.lod_epistemic_floor}
                  onChange={(e) => {
                    const v = parseFloat(e.target.value) || 0.8
                    setConfig({ ...config, lod_epistemic_floor: v })
                  }}
                  onBlur={(e) => handleUpdateConfig({ lod_epistemic_floor: parseFloat(e.target.value) || 0.8 })}
                  className="h-8 text-xs"
                />
                <p className="text-xs text-muted-foreground">Never compress high-confidence memories below LOD 2</p>
              </div>
            </div>
          )}

          {/* Test Compression */}
          <div className="p-3 bg-muted/30 rounded-lg space-y-2">
            <Label className="text-xs font-medium flex items-center gap-1">
              <FlaskConical className="h-3 w-3" />Test Compression
            </Label>
            <textarea
              className="w-full h-20 p-2 text-xs font-mono bg-background border rounded resize-none"
              placeholder="Enter text to test compression..."
              value={testText}
              onChange={(e) => setTestText(e.target.value)}
            />
            <Button
              onClick={handleTest}
              size="sm"
              className="h-7 text-xs w-full"
              disabled={testing || !testText.trim()}
            >
              {testing ? <Loader2 className="h-3 w-3 mr-1 animate-spin" /> : <FlaskConical className="h-3 w-3 mr-1" />}
              {testing ? 'Testing...' : 'Run Test'}
            </Button>

            {/* Test Results */}
            {testResult && (
              <div className="space-y-2 mt-2">
                <div className="text-xs text-muted-foreground">
                  Input: {testResult.input_chars} chars via {testResult.active_backend}
                </div>
                {Object.entries(testResult.results).map(([level, data]) => (
                  <div key={level} className="p-2 bg-background rounded text-xs space-y-1">
                    <div className="flex justify-between font-medium">
                      <span>{level}</span>
                      <span className="text-green-600">{data.compression_ratio}x ratio</span>
                    </div>
                    <div className="text-muted-foreground">
                      {data.output_chars} chars in {data.timing_ms}ms
                    </div>
                    <div className="font-mono text-[10px] text-muted-foreground/70 truncate">
                      {data.compressed_preview}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Info Panel */}
        {showInfo && (
          <div className="mt-3 p-2 bg-muted/50 rounded text-xs space-y-1">
            <p>
              <strong>3-Tier System:</strong> LinguaCompressor (178MB neural) →
              SemanticCompressor (zero deps) → NoopCompressor (pass-through)
            </p>
            <p>
              <strong>MemoryLOD:</strong> 6-level structural compression for memories.
              Budget-aware batch packing with epistemic floor protection.
            </p>
            <p>
              <strong>Method:</strong> Token pruning (preserves original text and provenance).
              Unlike generation-based compressors, citations are retained.
            </p>
          </div>
        )}

        {/* Status messages */}
        {actionMessage && (
          <div className="mt-3">
            <div className={`p-2 rounded text-xs flex items-center gap-2 ${
              actionMessage.type === 'success' ? 'bg-green-500/10 text-green-600' :
              actionMessage.type === 'error' ? 'bg-red-500/10 text-red-600' :
              'bg-blue-500/10 text-blue-600'
            }`}>
              {actionMessage.type === 'info' && <Loader2 className="h-3 w-3 animate-spin flex-shrink-0" />}
              {actionMessage.text}
            </div>
          </div>
        )}

        {/* Error from status */}
        {status?.error && !actionMessage && (
          <div className="mt-3 p-2 bg-red-500/10 rounded text-xs text-red-600">
            {status.error}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
