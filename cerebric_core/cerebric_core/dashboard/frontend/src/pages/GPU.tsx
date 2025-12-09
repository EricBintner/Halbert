/**
 * GPU Page - GPU hardware detection and driver management.
 * 
 * Phase 14: GPU Driver Assistant
 * Shows GPU hardware, current drivers, and provides AI-powered recommendations.
 */

import { useEffect, useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import {
  Cpu,
  RefreshCw,
  AlertTriangle,
  CheckCircle,
  ExternalLink,
  Thermometer,
  Gauge,
  MemoryStick,
  Zap,
  Monitor,
  HelpCircle,
  Download,
  Search,
  Sparkles,
  Terminal,
  Copy,
  Check,
  Globe,
  ArrowUpCircle,
  ShieldCheck,
  Package,
  Clock,
} from 'lucide-react'
import { cn } from '@/lib/utils'

interface GPUInfo {
  vendor: string
  model: string
  vram_mb: number
  driver_version: string | null
  driver_type: string | null  // 'nvidia', 'nvidia-open', 'nouveau', 'amdgpu', 'radeon', 'i915', etc.
  cuda_version: string | null
  pci_id: string
  role: 'auto' | 'display' | 'compute'  // GPU role for multi-GPU systems
  // Runtime stats (if nvidia-smi available)
  temperature_c: number | null
  power_draw_w: number | null
  power_limit_w: number | null
  utilization_percent: number | null
  memory_used_mb: number | null
  memory_total_mb: number | null
}

interface GPUData {
  gpus: GPUInfo[]
  has_nvidia: boolean
  has_amd: boolean
  has_intel: boolean
  nvidia_smi_available: boolean
  recommended_driver: string | null
  driver_status: 'optimal' | 'outdated' | 'missing' | 'unknown'
  issues: string[]
}

interface GPUAnalysis {
  analysis: string
  health_score: number
  current_status?: string
  driver_assessment?: {
    current_version?: string
    latest_stable_version?: string | null
    version_comparison?: 'newer_than_stable' | 'at_stable' | 'older_than_stable'
    action_recommended?: 'none' | 'upgrade' | 'consider_lts_downgrade'
    version_analysis?: string
    change_risk?: 'safe' | 'moderate' | 'high'
    // Legacy fields for backwards compatibility
    upgrade_risk?: 'safe' | 'moderate' | 'high'
    should_upgrade?: boolean
    current_is_latest?: boolean
    recommended_version?: string | null
  }
  cuda_assessment?: {
    compatible: boolean
    current_version?: string
    latest_version?: string | null
    version_analysis?: string
    recommended_version?: string | null  // Legacy
  }
  recommendations?: Array<{
    priority: 'high' | 'medium' | 'low'
    action: string
    command?: string
    reason?: string
  }>
  known_compatible_combos?: Array<{
    driver: string
    cuda: string
    note?: string
  }>
  warnings?: string[]
  ml_compatibility?: Record<string, string>
  web_sources?: Array<{
    title: string
    url: string
    snippet: string
  }>
  raw_context?: {
    gpu: GPUInfo
    system: Record<string, unknown>
  }
}

const vendorIcons: Record<string, string> = {
  nvidia: '🟢',
  amd: '🔴',
  intel: '🔵',
}

export function GPU() {
  const [gpuData, setGpuData] = useState<GPUData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  
  // Deep analysis state
  const [analysis, setAnalysis] = useState<GPUAnalysis | null>(null)
  const [analyzing, setAnalyzing] = useState(false)
  const [copiedCommand, setCopiedCommand] = useState<string | null>(null)
  const [analysisCache, setAnalysisCache] = useState<{
    scanned_at: string | null
    is_stale: boolean
    age_days: number | null
  }>({ scanned_at: null, is_stale: true, age_days: null })

  const loadCachedAnalysis = async () => {
    try {
      const res = await fetch('/api/gpu/analysis-cache')
      if (res.ok) {
        const data = await res.json()
        if (data.cached && data.analysis) {
          setAnalysis(data.analysis)
          setAnalysisCache({
            scanned_at: data.scanned_at,
            is_stale: data.is_stale,
            age_days: data.age_days,
          })
        }
      }
    } catch (err) {
      console.error('Failed to load cached analysis:', err)
    }
  }

  const loadGPUData = async () => {
    try {
      const response = await fetch('/api/gpu/info')
      if (!response.ok) throw new Error('Failed to load GPU info')
      const data = await response.json()
      setGpuData(data)
      setError(null)
    } catch (err) {
      setError('Failed to load GPU information')
      console.error(err)
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }

  useEffect(() => {
    loadGPUData()
    loadCachedAnalysis()  // Load any cached analysis
    // Refresh every 5 seconds for live stats
    const interval = setInterval(loadGPUData, 5000)
    return () => clearInterval(interval)
  }, [])

  const handleRefresh = () => {
    setRefreshing(true)
    loadGPUData()
  }

  const getVendor = (gpu: GPUInfo): string => {
    const model = gpu.model.toLowerCase()
    if (model.includes('nvidia') || gpu.vendor.toLowerCase().includes('nvidia')) return 'nvidia'
    if (model.includes('amd') || model.includes('radeon') || gpu.vendor.toLowerCase().includes('amd')) return 'amd'
    if (model.includes('intel') || gpu.vendor.toLowerCase().includes('intel')) return 'intel'
    return 'unknown'
  }

  const getDriverStatusBadge = (status: string) => {
    switch (status) {
      case 'optimal':
        return <Badge className="bg-green-500"><CheckCircle className="h-3 w-3 mr-1" />Optimal</Badge>
      case 'outdated':
        return <Badge className="bg-amber-500"><AlertTriangle className="h-3 w-3 mr-1" />Outdated</Badge>
      case 'missing':
        return <Badge variant="destructive"><AlertTriangle className="h-3 w-3 mr-1" />Missing</Badge>
      default:
        return <Badge variant="secondary"><HelpCircle className="h-3 w-3 mr-1" />Unknown</Badge>
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (error || !gpuData) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold">GPU</h1>
            <p className="text-muted-foreground">Graphics hardware and drivers</p>
          </div>
        </div>
        <Card>
          <CardContent className="pt-6">
            <div className="text-center py-8">
              <Monitor className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
              <p className="text-muted-foreground">{error || 'No GPU information available'}</p>
              <Button variant="outline" className="mt-4" onClick={handleRefresh}>
                <RefreshCw className="h-4 w-4 mr-2" />
                Retry
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">GPU</h1>
          <p className="text-muted-foreground">
            {gpuData.gpus.length} GPU{gpuData.gpus.length !== 1 ? 's' : ''} detected
          </p>
        </div>
        <div className="flex items-center gap-2">
          {getDriverStatusBadge(gpuData.driver_status)}
          <Button variant="outline" size="sm" onClick={handleRefresh} disabled={refreshing}>
            <RefreshCw className={cn("h-4 w-4 mr-2", refreshing && "animate-spin")} />
            Refresh
          </Button>
        </div>
      </div>

      {/* Issues Alert */}
      {gpuData.issues.length > 0 && (
        <Card className="border-amber-500/50 bg-amber-500/5">
          <CardContent className="pt-6">
            <div className="flex items-start gap-3">
              <AlertTriangle className="h-5 w-5 text-amber-500 mt-0.5" />
              <div>
                <h3 className="font-medium text-amber-600 dark:text-amber-400">Issues Detected</h3>
                <ul className="mt-2 space-y-1 text-sm text-muted-foreground">
                  {gpuData.issues.map((issue, i) => (
                    <li key={i}>• {issue}</li>
                  ))}
                </ul>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* GPU Cards */}
      <div className="grid gap-6">
        {gpuData.gpus.map((gpu, index) => {
          const vendor = getVendor(gpu)
          const hasStats = gpu.temperature_c !== null || gpu.utilization_percent !== null
          
          return (
            <Card key={index}>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className={cn(
                      "w-10 h-10 rounded-lg flex items-center justify-center text-xl",
                      vendor === 'nvidia' && "bg-green-500/10",
                      vendor === 'amd' && "bg-red-500/10",
                      vendor === 'intel' && "bg-blue-500/10",
                    )}>
                      {vendorIcons[vendor] || '🎮'}
                    </div>
                    <div>
                      <CardTitle className="text-lg">{gpu.model}</CardTitle>
                      <CardDescription>{gpu.vendor} • {gpu.pci_id}</CardDescription>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {/* GPU Role Selector */}
                    <select
                      value={gpu.role || 'auto'}
                      onChange={async (e) => {
                        const newRole = e.target.value
                        const pciIdSafe = gpu.pci_id.replace(/:/g, '-')
                        try {
                          const res = await fetch(`/api/gpu/role/${pciIdSafe}?role=${newRole}`, { method: 'PUT' })
                          if (res.ok) {
                            loadGPUData() // Refresh to show new role
                          }
                        } catch (err) {
                          console.error('Failed to set GPU role:', err)
                        }
                      }}
                      className="h-8 px-2 text-xs rounded-md border border-input bg-background"
                      title="Set GPU role for multi-GPU systems"
                    >
                      <option value="auto">Auto</option>
                      <option value="display">Display</option>
                      <option value="compute">Compute</option>
                    </select>
                    <Badge variant="outline" className="text-xs">
                      {gpu.vram_mb ? `${(gpu.vram_mb / 1024).toFixed(0)} GB VRAM` : 'Unknown VRAM'}
                    </Badge>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="space-y-6">
                {/* Driver Info */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div className="space-y-1">
                    <p className="text-xs text-muted-foreground">Driver</p>
                    <p className="font-medium">{gpu.driver_type || 'Unknown'}</p>
                  </div>
                  <div className="space-y-1">
                    <p className="text-xs text-muted-foreground">Version</p>
                    <p className="font-medium">{gpu.driver_version || 'Not detected'}</p>
                  </div>
                  {gpu.cuda_version && (
                    <div className="space-y-1">
                      <p className="text-xs text-muted-foreground">CUDA</p>
                      <p className="font-medium">{gpu.cuda_version}</p>
                    </div>
                  )}
                  {gpu.memory_total_mb && (
                    <div className="space-y-1">
                      <p className="text-xs text-muted-foreground">Memory</p>
                      <p className="font-medium">
                        {((gpu.memory_used_mb || 0) / 1024).toFixed(1)} / {(gpu.memory_total_mb / 1024).toFixed(1)} GB
                      </p>
                    </div>
                  )}
                </div>

                {/* Live Stats (if available) */}
                {hasStats && (
                  <div className="border-t pt-4">
                    <p className="text-xs text-muted-foreground mb-3">Live Statistics</p>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                      {gpu.utilization_percent !== null && (
                        <div className="space-y-2">
                          <div className="flex items-center justify-between text-sm">
                            <span className="flex items-center gap-1.5">
                              <Gauge className="h-4 w-4 text-muted-foreground" />
                              GPU Load
                            </span>
                            <span className="font-medium">{gpu.utilization_percent}%</span>
                          </div>
                          <Progress value={gpu.utilization_percent} className="h-2" />
                        </div>
                      )}
                      {gpu.memory_used_mb !== null && gpu.memory_total_mb && (
                        <div className="space-y-2">
                          <div className="flex items-center justify-between text-sm">
                            <span className="flex items-center gap-1.5">
                              <MemoryStick className="h-4 w-4 text-muted-foreground" />
                              VRAM
                            </span>
                            <span className="font-medium">{Math.round((gpu.memory_used_mb / gpu.memory_total_mb) * 100)}%</span>
                          </div>
                          <Progress value={(gpu.memory_used_mb / gpu.memory_total_mb) * 100} className="h-2" />
                        </div>
                      )}
                      {gpu.temperature_c !== null && (
                        <div className="space-y-2">
                          <div className="flex items-center justify-between text-sm">
                            <span className="flex items-center gap-1.5">
                              <Thermometer className="h-4 w-4 text-muted-foreground" />
                              Temp
                            </span>
                            <span className={cn(
                              "font-medium",
                              gpu.temperature_c > 80 && "text-red-500",
                              gpu.temperature_c > 70 && gpu.temperature_c <= 80 && "text-amber-500",
                            )}>
                              {gpu.temperature_c}°C
                            </span>
                          </div>
                          <Progress 
                            value={Math.min(100, (gpu.temperature_c / 100) * 100)} 
                            className={cn(
                              "h-2",
                              gpu.temperature_c > 80 && "[&>div]:bg-red-500",
                              gpu.temperature_c > 70 && gpu.temperature_c <= 80 && "[&>div]:bg-amber-500",
                            )}
                          />
                        </div>
                      )}
                      {gpu.power_draw_w !== null && (
                        <div className="space-y-2">
                          <div className="flex items-center justify-between text-sm">
                            <span className="flex items-center gap-1.5">
                              <Zap className="h-4 w-4 text-muted-foreground" />
                              Power
                            </span>
                            <span className="font-medium">
                              {gpu.power_draw_w}W{gpu.power_limit_w ? ` / ${gpu.power_limit_w}W` : ''}
                            </span>
                          </div>
                          {gpu.power_limit_w && (
                            <Progress value={(gpu.power_draw_w / gpu.power_limit_w) * 100} className="h-2" />
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* Quick Links */}
                {vendor === 'nvidia' && (
                  <div className="border-t pt-4 flex gap-2">
                    <Button variant="outline" size="sm" asChild>
                      <a href="https://www.nvidia.com/drivers" target="_blank" rel="noopener noreferrer">
                        <Download className="h-4 w-4 mr-2" />
                        NVIDIA Drivers
                        <ExternalLink className="h-3 w-3 ml-2" />
                      </a>
                    </Button>
                    <Button variant="outline" size="sm" asChild>
                      <a href="https://developer.nvidia.com/cuda-downloads" target="_blank" rel="noopener noreferrer">
                        <Cpu className="h-4 w-4 mr-2" />
                        CUDA Toolkit
                        <ExternalLink className="h-3 w-3 ml-2" />
                      </a>
                    </Button>
                  </div>
                )}
                {vendor === 'amd' && (
                  <div className="border-t pt-4 flex gap-2">
                    <Button variant="outline" size="sm" asChild>
                      <a href="https://www.amd.com/en/support" target="_blank" rel="noopener noreferrer">
                        <Download className="h-4 w-4 mr-2" />
                        AMD Drivers
                        <ExternalLink className="h-3 w-3 ml-2" />
                      </a>
                    </Button>
                  </div>
                )}
              </CardContent>
            </Card>
          )
        })}
      </div>

      {/* No GPU Detected */}
      {gpuData.gpus.length === 0 && (
        <Card>
          <CardContent className="pt-6">
            <div className="text-center py-8">
              <Monitor className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
              <h3 className="font-medium mb-2">No Dedicated GPU Detected</h3>
              <p className="text-sm text-muted-foreground">
                This system appears to be using integrated graphics or no GPU was found.
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      {/* GPU Deep Analysis Panel */}
      {gpuData.gpus.length > 0 && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="flex items-center gap-2">
                  <Sparkles className="h-5 w-5 text-blue-500" />
                  AI GPU Advisor
                </CardTitle>
                <CardDescription>
                  Deep analysis with web grounding for driver recommendations
                </CardDescription>
              </div>
              <div className="flex items-center gap-2">
                {analysis && (
                  <Badge className={cn(
                    analysis.health_score >= 80 && "bg-green-500",
                    analysis.health_score >= 50 && analysis.health_score < 80 && "bg-amber-500",
                    analysis.health_score < 50 && "bg-red-500",
                  )}>
                    Health: {analysis.health_score}%
                  </Badge>
                )}
                <Button 
                  onClick={async () => {
                    setAnalyzing(true)
                    try {
                      const res = await fetch('/api/gpu/analyze', { method: 'POST' })
                      if (res.ok) {
                        const data = await res.json()
                        setAnalysis(data)
                        // Reset cache metadata (fresh scan)
                        setAnalysisCache({
                          scanned_at: new Date().toISOString(),
                          is_stale: false,
                          age_days: 0,
                        })
                      }
                    } catch (err) {
                      console.error('Analysis failed:', err)
                    } finally {
                      setAnalyzing(false)
                    }
                  }}
                  disabled={analyzing}
                  size="sm"
                  variant={analysisCache.is_stale && analysis ? "default" : "outline"}
                >
                  {analyzing ? (
                    <>
                      <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                      Analyzing...
                    </>
                  ) : (
                    <>
                      <Search className="h-4 w-4 mr-2" />
                      {analysisCache.is_stale && analysis ? "Refresh Scan" : "Deep Scan"}
                    </>
                  )}
                </Button>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            {!analysis ? (
              <div className="text-center py-8 text-muted-foreground">
                <Cpu className="h-12 w-12 mx-auto mb-4 opacity-50" />
                <p>Click "Deep Scan" to analyze your GPU setup</p>
                <p className="text-xs mt-1">Gathers system context, checks web for latest drivers</p>
              </div>
            ) : (
              <div className="space-y-6">
                {/* Stale Analysis Banner */}
                {analysisCache.is_stale && (
                  <div className="flex items-center gap-2 p-3 bg-amber-500/10 border border-amber-500/30 rounded-lg text-amber-700 dark:text-amber-400">
                    <Clock className="h-4 w-4 flex-shrink-0" />
                    <span className="text-sm">
                      This analysis is {analysisCache.age_days ? `${analysisCache.age_days} days` : 'over a week'} old. 
                      Consider running a fresh scan for up-to-date recommendations.
                    </span>
                  </div>
                )}
                
                {/* Analysis Summary */}
                <div className="p-4 bg-muted/50 rounded-lg">
                  <div className="flex items-start justify-between gap-4">
                    <p className="text-sm">{analysis.analysis}</p>
                    {analysisCache.scanned_at && (
                      <span className="text-xs text-muted-foreground whitespace-nowrap">
                        Scanned {new Date(analysisCache.scanned_at).toLocaleDateString()}
                      </span>
                    )}
                  </div>
                </div>

                {/* Driver & CUDA Assessment */}
                {(analysis.driver_assessment || analysis.cuda_assessment) && (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {analysis.driver_assessment && (
                      <div className="p-4 border rounded-lg space-y-3">
                        <div className="flex items-center gap-2">
                          <ArrowUpCircle className="h-4 w-4 text-blue-500" />
                          <span className="font-medium text-sm">Driver Assessment</span>
                        </div>
                        <div className="space-y-2 text-sm">
                          {/* Current vs Latest */}
                          <div className="grid grid-cols-2 gap-2">
                            <div>
                              <span className="text-xs text-muted-foreground block">Current</span>
                              <span className="font-mono text-xs">
                                {analysis.driver_assessment.current_version || 'Unknown'}
                              </span>
                            </div>
                            <div>
                              <span className="text-xs text-muted-foreground block">Latest Stable</span>
                              <span className="font-mono text-xs">
                                {analysis.driver_assessment.latest_stable_version || 
                                 analysis.driver_assessment.recommended_version || 'Unknown'}
                              </span>
                            </div>
                          </div>
                          
                          {/* Version Status */}
                          <div className="flex items-center justify-between pt-1 border-t">
                            <span className="text-muted-foreground">Status:</span>
                            <Badge variant={
                              analysis.driver_assessment.version_comparison === 'newer_than_stable' ? "default" :
                              analysis.driver_assessment.version_comparison === 'at_stable' ? "default" :
                              analysis.driver_assessment.action_recommended === 'none' ? "default" : "secondary"
                            } className={cn(
                              analysis.driver_assessment.version_comparison === 'newer_than_stable' && "bg-blue-500/20 text-blue-600 border-blue-500/30"
                            )}>
                              {analysis.driver_assessment.version_comparison === 'newer_than_stable' 
                                ? "Ahead of stable (dev/beta)" 
                                : analysis.driver_assessment.version_comparison === 'at_stable'
                                ? "At latest stable"
                                : analysis.driver_assessment.action_recommended === 'upgrade'
                                ? "Upgrade available"
                                : "OK"}
                            </Badge>
                          </div>
                          
                          {/* Action Recommendation */}
                          {analysis.driver_assessment.action_recommended && analysis.driver_assessment.action_recommended !== 'none' && (
                            <div className="flex items-center justify-between">
                              <span className="text-muted-foreground">Action:</span>
                              <Badge variant="outline" className={cn(
                                analysis.driver_assessment.action_recommended === 'upgrade' && "text-amber-600",
                                analysis.driver_assessment.action_recommended === 'consider_lts_downgrade' && "text-blue-600",
                              )}>
                                {analysis.driver_assessment.action_recommended === 'upgrade' 
                                  ? "Consider upgrading" 
                                  : "LTS available (optional)"}
                              </Badge>
                            </div>
                          )}
                          
                          {/* Version Analysis */}
                          {analysis.driver_assessment.version_analysis && (
                            <p className="text-xs text-muted-foreground bg-muted/50 p-2 rounded">
                              {analysis.driver_assessment.version_analysis}
                            </p>
                          )}
                          
                          {/* Risk if changing */}
                          {(analysis.driver_assessment.change_risk || analysis.driver_assessment.upgrade_risk) && (
                            <div className="flex items-center justify-between">
                              <span className="text-muted-foreground">Change risk:</span>
                              <Badge variant="outline" className={cn(
                                (analysis.driver_assessment.change_risk || analysis.driver_assessment.upgrade_risk) === 'safe' && "text-green-600",
                                (analysis.driver_assessment.change_risk || analysis.driver_assessment.upgrade_risk) === 'moderate' && "text-amber-600",
                                (analysis.driver_assessment.change_risk || analysis.driver_assessment.upgrade_risk) === 'high' && "text-red-600",
                              )}>
                                {analysis.driver_assessment.change_risk || analysis.driver_assessment.upgrade_risk}
                              </Badge>
                            </div>
                          )}
                        </div>
                      </div>
                    )}
                    {analysis.cuda_assessment && (
                      <div className="p-4 border rounded-lg space-y-3">
                        <div className="flex items-center gap-2">
                          <Package className="h-4 w-4 text-green-500" />
                          <span className="font-medium text-sm">CUDA Assessment</span>
                        </div>
                        <div className="space-y-2 text-sm">
                          {/* Current vs Latest */}
                          <div className="grid grid-cols-2 gap-2">
                            <div>
                              <span className="text-xs text-muted-foreground block">Current</span>
                              <span className="font-mono text-xs">
                                {analysis.cuda_assessment.current_version || 'Unknown'}
                              </span>
                            </div>
                            <div>
                              <span className="text-xs text-muted-foreground block">Latest</span>
                              <span className="font-mono text-xs">
                                {analysis.cuda_assessment.latest_version || 
                                 analysis.cuda_assessment.recommended_version || 'Unknown'}
                              </span>
                            </div>
                          </div>
                          
                          {/* Compatibility */}
                          <div className="flex items-center justify-between pt-1 border-t">
                            <span className="text-muted-foreground">Compatible:</span>
                            <Badge variant={analysis.cuda_assessment.compatible ? "default" : "destructive"}>
                              {analysis.cuda_assessment.compatible ? "Yes" : "No"}
                            </Badge>
                          </div>
                          
                          {/* Version Analysis */}
                          {analysis.cuda_assessment.version_analysis && (
                            <p className="text-xs text-muted-foreground bg-muted/50 p-2 rounded">
                              {analysis.cuda_assessment.version_analysis}
                            </p>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {/* ML Framework Compatibility */}
                {analysis.ml_compatibility && Object.keys(analysis.ml_compatibility).length > 0 && (
                  <div>
                    <h4 className="text-sm font-medium mb-2 flex items-center gap-2">
                      <ShieldCheck className="h-4 w-4" />
                      ML Framework Compatibility
                    </h4>
                    <div className="flex flex-wrap gap-2">
                      {Object.entries(analysis.ml_compatibility).map(([framework, status]) => (
                        <Badge 
                          key={framework} 
                          variant="outline"
                          className={cn(
                            status === 'compatible' && "border-green-500 text-green-600",
                            status === 'needs_update' && "border-amber-500 text-amber-600",
                            status === 'not_installed' && "border-gray-400 text-gray-500",
                          )}
                        >
                          {framework}: {status}
                        </Badge>
                      ))}
                    </div>
                  </div>
                )}

                {/* Warnings */}
                {analysis.warnings && analysis.warnings.length > 0 && (
                  <div className="p-4 bg-amber-500/10 border border-amber-500/30 rounded-lg">
                    <h4 className="text-sm font-medium mb-2 flex items-center gap-2 text-amber-600">
                      <AlertTriangle className="h-4 w-4" />
                      Warnings
                    </h4>
                    <ul className="text-sm space-y-1">
                      {analysis.warnings.map((warning, i) => (
                        <li key={i}>• {warning}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Known Compatible Combinations - subtle reference info */}
                {analysis.known_compatible_combos && analysis.known_compatible_combos.length > 0 && (
                  <div className="text-xs text-muted-foreground border-t pt-4">
                    <p className="mb-2 flex items-center gap-1">
                      <HelpCircle className="h-3 w-3" />
                      Known compatible driver/CUDA combinations for reference:
                    </p>
                    <div className="flex flex-wrap gap-2">
                      {analysis.known_compatible_combos.map((combo, i) => (
                        <span key={i} className="px-2 py-1 bg-muted rounded text-xs font-mono">
                          {combo.driver} + CUDA {combo.cuda}
                          {combo.note && <span className="text-muted-foreground/70 ml-1">({combo.note})</span>}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {/* Recommendations */}
                {analysis.recommendations && analysis.recommendations.length > 0 && (
                  <div>
                    <h4 className="text-sm font-medium mb-3 flex items-center gap-2">
                      <CheckCircle className="h-4 w-4 text-green-500" />
                      Recommendations
                    </h4>
                    <div className="space-y-3">
                      {analysis.recommendations.map((rec, i) => (
                        <div key={i} className="p-3 border rounded-lg">
                          <div className="flex items-start justify-between gap-2">
                            <div className="flex-1">
                              <div className="flex items-center gap-2 mb-1">
                                <Badge variant="outline" className={cn(
                                  rec.priority === 'high' && "border-red-500 text-red-600",
                                  rec.priority === 'medium' && "border-amber-500 text-amber-600",
                                  rec.priority === 'low' && "border-blue-500 text-blue-600",
                                )}>
                                  {rec.priority}
                                </Badge>
                                <span className="text-sm font-medium">{rec.action}</span>
                              </div>
                              {rec.reason && (
                                <p className="text-xs text-muted-foreground">{rec.reason}</p>
                              )}
                            </div>
                          </div>
                          {rec.command && (
                            <div className="mt-2 flex items-center gap-2">
                              <code className="flex-1 text-xs bg-muted px-2 py-1 rounded font-mono overflow-x-auto">
                                {rec.command}
                              </code>
                              <Button 
                                variant="ghost" 
                                size="sm"
                                title="Send to chat for execution"
                                onClick={() => {
                                  window.dispatchEvent(new CustomEvent('cerebric:send-to-chat', {
                                    detail: { 
                                      command: rec.command,
                                      context: `GPU Driver recommendation: ${rec.action}`
                                    }
                                  }))
                                }}
                              >
                                <Terminal className="h-4 w-4" />
                              </Button>
                              <Button 
                                variant="ghost" 
                                size="sm"
                                title="Copy to clipboard"
                                onClick={() => {
                                  navigator.clipboard.writeText(rec.command!)
                                  setCopiedCommand(rec.command!)
                                  setTimeout(() => setCopiedCommand(null), 2000)
                                }}
                              >
                                {copiedCommand === rec.command ? (
                                  <Check className="h-4 w-4 text-green-500" />
                                ) : (
                                  <Copy className="h-4 w-4" />
                                )}
                              </Button>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Web Sources */}
                {analysis.web_sources && analysis.web_sources.length > 0 && (
                  <div>
                    <h4 className="text-sm font-medium mb-2 flex items-center gap-2 text-muted-foreground">
                      <Globe className="h-4 w-4" />
                      Sources Used
                    </h4>
                    <div className="space-y-1">
                      {analysis.web_sources.map((source, i) => (
                        <a 
                          key={i}
                          href={source.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="block text-xs text-blue-500 hover:underline truncate"
                        >
                          {source.title}
                        </a>
                      ))}
                    </div>
                  </div>
                )}

                {/* System Context (collapsed) */}
                {analysis.raw_context?.system && (
                  <details className="text-xs">
                    <summary className="cursor-pointer text-muted-foreground hover:text-foreground">
                      <Terminal className="h-3 w-3 inline mr-1" />
                      View System Context
                    </summary>
                    <pre className="mt-2 p-2 bg-muted rounded text-xs overflow-auto max-h-40">
                      {JSON.stringify(analysis.raw_context.system, null, 2)}
                    </pre>
                  </details>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  )
}
