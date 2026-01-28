/**
 * ClaraSettings - CLaRa Context Compression Settings Card
 * 
 * Allows configuring CLaRa in two modes:
 * - Remote: Use CLaRa-Remembers-It-All server on network
 * - Local: Load model locally (requires 14GB+ VRAM)
 * 
 * The app works with or without CLaRa enabled.
 */

import { useState, useEffect } from 'react'
import {
  Zap,
  Info,
  Loader2,
  Check,
  Power,
  PowerOff,
  Download,
  Server,
  Cpu,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

const API_BASE = '/api'

interface ClaraStatus {
  enabled: boolean
  initialized: boolean
  dependencies_installed: boolean
  model: string
  quantization: string
  vram_required_gb: number
  model_cached: boolean
  load_time_seconds: number | null
  last_error: string | null
  auto_compress_threshold: number
  use_remote?: boolean
  remote_url?: string
  remote_health?: { healthy: boolean; error?: string }
  vram?: {
    cuda_available: boolean
    mps_available?: boolean
    total_gb?: number
    free_gb?: number
    can_run?: boolean
    error?: string
  }
}

export function ClaraSettings() {
  const [status, setStatus] = useState<ClaraStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [installing, setInstalling] = useState(false)
  const [initializing, setInitializing] = useState(false)
  const [showInfo, setShowInfo] = useState(false)
  const [actionMessage, setActionMessage] = useState<{ type: 'success' | 'error' | 'info', text: string } | null>(null)
  const [initStage, setInitStage] = useState<string | null>(null)
  
  // Remote mode state
  const [useRemote, setUseRemote] = useState(false)
  const [remoteUrl, setRemoteUrl] = useState('')
  const [testingConnection, setTestingConnection] = useState(false)

  useEffect(() => {
    loadStatus()
  }, [])

  const loadStatus = async () => {
    try {
      const res = await fetch(`${API_BASE}/clara/status`)
      const data = await res.json()
      setStatus(data)
      setUseRemote(data.use_remote || false)
      setRemoteUrl(data.remote_url || '')
    } catch (err) {
      console.error('Failed to load CLaRa status:', err)
    }
    setLoading(false)
  }

  const handleInstallDeps = async () => {
    setInstalling(true)
    setActionMessage({ type: 'info', text: 'Installing transformers, accelerate, bitsandbytes...' })
    try {
      const res = await fetch(`${API_BASE}/clara/install-deps`, { method: 'POST' })
      const data = await res.json()
      if (data.success) {
        setActionMessage({ type: 'success', text: '✓ Dependencies installed successfully!' })
        await loadStatus()
      } else {
        setActionMessage({ type: 'error', text: data.error || 'Installation failed' })
      }
    } catch (err) {
      setActionMessage({ type: 'error', text: 'Failed to install dependencies' })
      console.error('Failed to install dependencies:', err)
    }
    setInstalling(false)
  }

  const handleToggleAndInit = async () => {
    setInitializing(true)
    setActionMessage(null)
    
    try {
      // Enable if not enabled
      if (!status?.enabled) {
        setInitStage('Enabling CLaRa...')
        await fetch(`${API_BASE}/clara/toggle`, { 
          method: 'POST', 
          headers: { 'Content-Type': 'application/json' }, 
          body: JSON.stringify({ enabled: true }) 
        })
      }
      
      // Initialize
      if (status?.model_cached) {
        setInitStage('Loading model from cache...')
      } else {
        setInitStage('Downloading model from HuggingFace (~14GB)...')
      }
      
      const res = await fetch(`${API_BASE}/clara/initialize`, { method: 'POST' })
      const data = await res.json()
      
      if (data.success) {
        setActionMessage({ type: 'success', text: `✓ CLaRa ready! Loaded in ${data.load_time_seconds?.toFixed(1) || '?'}s` })
      } else {
        setActionMessage({ type: 'error', text: data.error || 'Failed to initialize' })
      }
      await loadStatus()
    } catch (err) {
      setActionMessage({ type: 'error', text: 'Failed to initialize CLaRa' })
      console.error('Failed to initialize CLaRa:', err)
    }
    setInitStage(null)
    setInitializing(false)
  }

  const handleDisable = async () => {
    setActionMessage({ type: 'info', text: 'Unloading model...' })
    try {
      await fetch(`${API_BASE}/clara/unload`, { method: 'POST' })
      await fetch(`${API_BASE}/clara/toggle`, { 
        method: 'POST', 
        headers: { 'Content-Type': 'application/json' }, 
        body: JSON.stringify({ enabled: false }) 
      })
      setActionMessage({ type: 'success', text: '✓ CLaRa disabled, VRAM freed' })
      await loadStatus()
    } catch (err) {
      setActionMessage({ type: 'error', text: 'Failed to disable CLaRa' })
      console.error('Failed to disable CLaRa:', err)
    }
  }

  // Remote mode handlers
  const handleTestConnection = async () => {
    if (!remoteUrl.trim()) {
      setActionMessage({ type: 'error', text: 'Please enter a server URL' })
      return
    }
    setTestingConnection(true)
    setActionMessage({ type: 'info', text: 'Testing connection...' })
    try {
      // Save the URL first
      await fetch(`${API_BASE}/clara/config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ remote_url: remoteUrl.trim() })
      })
      // Then test it
      const res = await fetch(`${API_BASE}/clara/remote/health`)
      const data = await res.json()
      if (data.healthy) {
        setActionMessage({ type: 'success', text: `✓ Connected to CLaRa server at ${remoteUrl}` })
      } else {
        setActionMessage({ type: 'error', text: data.error || 'Connection failed' })
      }
    } catch (err) {
      setActionMessage({ type: 'error', text: 'Failed to test connection' })
      console.error('Failed to test CLaRa connection:', err)
    }
    setTestingConnection(false)
  }

  const handleEnableRemote = async () => {
    if (!remoteUrl.trim()) {
      setActionMessage({ type: 'error', text: 'Please enter a server URL first' })
      return
    }
    setActionMessage({ type: 'info', text: 'Enabling remote mode...' })
    try {
      // Save config with remote mode enabled
      await fetch(`${API_BASE}/clara/config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ use_remote: true, remote_url: remoteUrl.trim() })
      })
      // Enable CLaRa
      await fetch(`${API_BASE}/clara/toggle`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: true })
      })
      setUseRemote(true)
      setActionMessage({ type: 'success', text: '✓ CLaRa remote mode enabled!' })
      await loadStatus()
    } catch (err) {
      setActionMessage({ type: 'error', text: 'Failed to enable remote mode' })
      console.error('Failed to enable remote mode:', err)
    }
  }

  const handleDisableRemote = async () => {
    setActionMessage({ type: 'info', text: 'Disabling remote mode...' })
    try {
      await fetch(`${API_BASE}/clara/config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ use_remote: false })
      })
      await fetch(`${API_BASE}/clara/toggle`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: false })
      })
      setUseRemote(false)
      setActionMessage({ type: 'success', text: '✓ CLaRa remote mode disabled' })
      await loadStatus()
    } catch (err) {
      setActionMessage({ type: 'error', text: 'Failed to disable remote mode' })
      console.error('Failed to disable remote mode:', err)
    }
  }

  if (loading) {
    return (
      <Card>
        <CardContent className="py-6">
          <div className="flex items-center justify-center gap-2 text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />Loading CLaRa status...
          </div>
        </CardContent>
      </Card>
    )
  }

  // Determine state for card styling
  const isActive = status?.enabled && (status?.initialized || useRemote)
  const isReady = status?.dependencies_installed && (status?.vram?.can_run || status?.vram?.mps_available)
  const isRemoteActive = status?.enabled && useRemote

  return (
    <Card className={isActive ? "border-green-500/50" : ""}>
      <CardContent className="py-4">
        {/* Header row with title and info */}
        <div className="flex items-center gap-1.5 mb-1">
          <Zap className={`h-4 w-4 flex-shrink-0 ${isActive ? 'text-green-500' : ''}`} />
          <span className="font-semibold text-sm">Memory Compression</span>
          <button 
            onClick={() => setShowInfo(!showInfo)} 
            className="p-0.5 hover:bg-muted rounded"
          >
            <Info className="h-3.5 w-3.5 text-muted-foreground" />
          </button>
          {isRemoteActive && (
            <span className="ml-auto text-xs bg-green-500/10 text-green-600 px-2 py-0.5 rounded flex items-center gap-1">
              <Server className="h-3 w-3" />Remote
            </span>
          )}
          {isActive && !isRemoteActive && (
            <span className="ml-auto text-xs bg-green-500/10 text-green-600 px-2 py-0.5 rounded flex items-center gap-1">
              <Cpu className="h-3 w-3" />Local
            </span>
          )}
        </div>
        <p className="text-xs text-muted-foreground mb-3">Apple CLaRa - 16x context compression</p>

        <div className="space-y-3">
          {/* Remote Server Section */}
          <div className="p-3 bg-muted/30 rounded-lg space-y-2">
            <div className="flex items-center justify-between">
              <Label className="text-xs font-medium flex items-center gap-1">
                <Server className="h-3 w-3" />Remote Server
              </Label>
              {isRemoteActive && (
                <Button onClick={handleDisableRemote} variant="ghost" size="sm" className="h-6 text-xs">
                  Disable
                </Button>
              )}
            </div>
            <div className="flex gap-2">
              <Input
                type="text"
                placeholder="http://192.168.1.x:8765"
                value={remoteUrl}
                onChange={(e) => setRemoteUrl(e.target.value)}
                className="h-8 text-xs font-mono"
                disabled={isRemoteActive}
              />
              {!isRemoteActive ? (
                <div className="flex gap-1">
                  <Button 
                    onClick={handleTestConnection} 
                    variant="outline" 
                    size="sm" 
                    className="h-8 text-xs"
                    disabled={testingConnection || !remoteUrl.trim()}
                  >
                    {testingConnection ? <Loader2 className="h-3 w-3 animate-spin" /> : 'Test'}
                  </Button>
                  <Button 
                    onClick={handleEnableRemote} 
                    size="sm" 
                    className="h-8 text-xs"
                    disabled={!remoteUrl.trim()}
                  >
                    <Power className="h-3 w-3 mr-1" />Enable
                  </Button>
                </div>
              ) : (
                <span className="flex items-center text-xs text-green-600">
                  <Check className="h-3 w-3 mr-1" />Connected
                </span>
              )}
            </div>
            <p className="text-xs text-muted-foreground">
              Run CLaRa on a powerful machine, use from anywhere.{' '}
              <a 
                href="https://github.com/EricBintner/CLaRa-Remembers-It-All" 
                target="_blank" 
                rel="noopener noreferrer" 
                className="text-blue-500 hover:underline"
              >
                Setup guide →
              </a>
            </p>
          </div>

          {/* Local Mode Section (collapsed if remote is active) */}
          {!isRemoteActive && (
            <div className="p-3 bg-muted/30 rounded-lg space-y-2">
              <Label className="text-xs font-medium flex items-center gap-1">
                <Cpu className="h-3 w-3" />Local Mode
              </Label>
              <div className="flex items-center justify-between">
                <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
                  <span className={`flex items-center gap-1 ${status?.dependencies_installed ? 'text-green-600' : 'text-muted-foreground'}`}>
                    {status?.dependencies_installed ? <Check className="h-3 w-3" /> : <div className="h-3 w-3 rounded-full border border-current" />}
                    Dependencies
                  </span>
                  <span className={`flex items-center gap-1 ${status?.model_cached ? 'text-green-600' : 'text-muted-foreground'}`}>
                    {status?.model_cached ? <Check className="h-3 w-3" /> : <div className="h-3 w-3 rounded-full border border-current" />}
                    Model
                  </span>
                  <span className={`flex items-center gap-1 ${isActive && !useRemote ? 'text-green-600' : 'text-muted-foreground'}`}>
                    {isActive && !useRemote ? <Check className="h-3 w-3" /> : <div className="h-3 w-3 rounded-full border border-current" />}
                    Active
                  </span>
                </div>
                <div className="flex-shrink-0">
                  {!initializing && !installing && (
                    <>
                      {!status?.dependencies_installed ? (
                        <Button onClick={handleInstallDeps} size="sm" className="h-7 text-xs">
                          <Download className="h-3 w-3 mr-1" />Install
                        </Button>
                      ) : !isActive ? (
                        <Button 
                          onClick={handleToggleAndInit} 
                          disabled={!isReady}
                          size="sm"
                          className="h-7 text-xs"
                        >
                          <Power className="h-3 w-3 mr-1" />
                          {status?.model_cached ? 'Load' : 'Setup'}
                        </Button>
                      ) : (
                        <Button onClick={handleDisable} variant="outline" size="sm" className="h-7 text-xs">
                          <PowerOff className="h-3 w-3 mr-1" />Disable
                        </Button>
                      )}
                    </>
                  )}
                  {(initializing || installing) && (
                    <Button disabled size="sm" className="h-7 text-xs">
                      <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                      {installing ? 'Installing...' : 'Loading...'}
                    </Button>
                  )}
                </div>
              </div>
              <p className="text-xs text-muted-foreground">
                Requires ~14GB VRAM (NVIDIA) or unified memory (Apple Silicon)
              </p>
            </div>
          )}
        </div>

        {/* Info Panel (expandable) */}
        {showInfo && (
          <div className="mt-3 p-2 bg-muted/50 rounded text-xs space-y-1">
            <p>
              <strong>Model:</strong>{' '}
              <a 
                href="https://huggingface.co/apple/CLaRa-7B-Instruct" 
                target="_blank" 
                rel="noopener noreferrer" 
                className="text-blue-500 hover:underline"
              >
                apple/CLaRa-7B-Instruct
              </a>
              {' • '}
              <strong>Compression:</strong> 16x
              {' • '}
              <strong>First setup:</strong> ~5-10 min
            </p>
          </div>
        )}

        {/* Progress/Status messages */}
        {(actionMessage || initStage || (status?.last_error && !actionMessage)) && (
          <div className="mt-3 space-y-2">
            {/* VRAM warning */}
            {!status?.vram?.can_run && !status?.vram?.mps_available && status?.dependencies_installed && !isActive && !initStage && (
              <p className="text-xs text-amber-600">
                {status?.vram?.cuda_available 
                  ? `⚠️ Low VRAM: ${status.vram.free_gb?.toFixed(1)}GB free, need ${status.vram_required_gb}GB`
                  : '⚠️ No GPU detected (CUDA or MPS)'}
              </p>
            )}

            {/* Action Message */}
            {actionMessage && (
              <div className={`p-2 rounded text-xs flex items-center gap-2 ${
                actionMessage.type === 'success' ? 'bg-green-500/10 text-green-600' :
                actionMessage.type === 'error' ? 'bg-red-500/10 text-red-600' :
                'bg-blue-500/10 text-blue-600'
              }`}>
                {actionMessage.type === 'info' && <Loader2 className="h-3 w-3 animate-spin flex-shrink-0" />}
                {actionMessage.text}
              </div>
            )}

            {/* Progress Stage */}
            {initStage && (
              <div className="space-y-1.5">
                <div className="flex items-center gap-2 text-xs text-purple-600 dark:text-purple-400">
                  <Loader2 className="h-3.5 w-3.5 animate-spin flex-shrink-0" />
                  <span>{initStage}</span>
                </div>
                {!status?.model_cached && (
                  <div className="h-1.5 bg-purple-200 dark:bg-purple-900 rounded-full overflow-hidden">
                    <div className="h-full bg-purple-500 rounded-full animate-pulse" style={{ width: '60%' }} />
                  </div>
                )}
              </div>
            )}

            {/* Error from status */}
            {status?.last_error && !actionMessage && !isRemoteActive && (
              <div className="p-2 bg-red-500/10 rounded text-xs text-red-600">
                {status.last_error}
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
