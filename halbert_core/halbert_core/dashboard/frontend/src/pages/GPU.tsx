// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
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
  Loader2,
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
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { apiUrl } from '@/lib/apiBase'
import { SystemItemActions, PageHeader } from '@/components/domain'
import { Select } from '@/components/ui/select'
import { WhyBrain } from '@/components/ui/why-brain'
import { AIAnalysisPanel } from '@/components/AIAnalysisPanel'

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

const vendorIcons: Record<string, string> = {
  nvidia: '🟢',
  amd: '🔴',
  intel: '🔵',
}

/** Diagnostic prompt for the shared AI analysis panel (specialist tier, host scope). */
const GPU_DIAGNOSTIC_MESSAGE = `Analyze my GPU setup on this system for driver and CUDA compatibility. Use your GPU tools (gpu_info, gpu_system_context) to gather live details, retrieve the NVIDIA driver/CUDA compatibility guidance from your knowledge base, and use web search for current driver releases if needed. Assess whether the current driver version is optimal for this GPU and kernel, check compatibility between driver, CUDA, and any ML frameworks (PyTorch/TensorFlow), and only recommend an upgrade if a specific newer version provides clear benefits. Provide specific recommendations with commands and any warnings about the current setup.`

export function GPU() {
  const [gpuData, setGpuData] = useState<GPUData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)

  const loadGPUData = async () => {
    try {
      const response = await fetch(apiUrl('/api/gpu/info'))
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
        return <Badge className="bg-success"><CheckCircle className="h-3 w-3 mr-1" />Optimal</Badge>
      case 'outdated':
        return <Badge className="bg-warning"><AlertTriangle className="h-3 w-3 mr-1" />Outdated</Badge>
      case 'missing':
        return <Badge variant="destructive"><AlertTriangle className="h-3 w-3 mr-1" />Missing</Badge>
      default:
        return <Badge variant="secondary"><HelpCircle className="h-3 w-3 mr-1" />Unknown</Badge>
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
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
      <PageHeader
        icon={<Cpu className="h-8 w-8" />}
        title="GPU"
        description={`${gpuData.gpus.length} GPU${gpuData.gpus.length !== 1 ? 's' : ''} detected`}
        scanning={refreshing}
        onScan={handleRefresh}
        scanText="Refresh"
        actions={getDriverStatusBadge(gpuData.driver_status)}
      />

      {/* Issues Alert */}
      {gpuData.issues.length > 0 && (
        <Card className="border-warning/50 bg-warning/5">
          <CardContent className="pt-6">
            <div className="flex items-start gap-3">
              <AlertTriangle className="h-5 w-5 text-warning mt-0.5" />
              <div>
                <h3 className="font-medium text-warning dark:text-warning">Issues Detected</h3>
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
                      vendor === 'nvidia' && "bg-success/10",
                      vendor === 'amd' && "bg-error/10",
                      vendor === 'intel' && "bg-info/10",
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
                    <Select
                      size="sm"
                      value={gpu.role || 'auto'}
                      onChange={async (e) => {
                        const newRole = e.target.value
                        const pciIdSafe = gpu.pci_id.replace(/:/g, '-')
                        try {
                          const res = await fetch(apiUrl(`/api/gpu/role/${pciIdSafe}?role=${newRole}`), { method: 'PUT' })
                          if (res.ok) {
                            loadGPUData() // Refresh to show new role
                          }
                        } catch (err) {
                          console.error('Failed to set GPU role:', err)
                        }
                      }}
                      title="Set GPU role for multi-GPU systems"
                    >
                      <option value="auto">Auto</option>
                      <option value="display">Display</option>
                      <option value="compute">Compute</option>
                    </Select>
                    <Badge variant="outline" className="text-xs">
                      {gpu.vram_mb ? `${(gpu.vram_mb / 1024).toFixed(0)} GB VRAM` : 'Unknown VRAM'}
                    </Badge>
                    <WhyBrain
                      itemId={`gpu:${gpu.pci_id}`}
                      itemName={gpu.model}
                      itemType="gpu"
                      size="sm"
                    />
                    <SystemItemActions
                      item={{
                        name: gpu.model,
                        type: 'gpu',
                        id: `gpu/${gpu.pci_id}`,
                        description: `${gpu.vendor} GPU`,
                        status: gpu.driver_type ? 'Driver Loaded' : 'No Driver',
                        data: {
                          vendor: gpu.vendor,
                          pci_id: gpu.pci_id,
                          vram_mb: gpu.vram_mb,
                          driver_type: gpu.driver_type,
                          driver_version: gpu.driver_version,
                          cuda_version: gpu.cuda_version,
                        },
                        context: `GPU: ${gpu.model}\nVendor: ${gpu.vendor}\nDriver: ${gpu.driver_type || 'Unknown'} ${gpu.driver_version || ''}\nVRAM: ${gpu.vram_mb ? (gpu.vram_mb / 1024).toFixed(0) + ' GB' : 'Unknown'}\nCUDA: ${gpu.cuda_version || 'N/A'}`,
                      }}
                      size="sm"
                    />
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
                              gpu.temperature_c > 80 && "text-error",
                              gpu.temperature_c > 70 && gpu.temperature_c <= 80 && "text-warning",
                            )}>
                              {gpu.temperature_c}°C
                            </span>
                          </div>
                          <Progress 
                            value={Math.min(100, (gpu.temperature_c / 100) * 100)} 
                            className={cn(
                              "h-2",
                              gpu.temperature_c > 80 && "[&>div]:bg-error",
                              gpu.temperature_c > 70 && gpu.temperature_c <= 80 && "[&>div]:bg-warning",
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

      {/* GPU Deep Analysis — shared panel, agent specialist tier / host scope */}
      {gpuData.gpus.length > 0 && (
        <AIAnalysisPanel
          type="GPU"
          title="GPU"
          analyzeLabel="Deep Scan"
          message={GPU_DIAGNOSTIC_MESSAGE}
        />
      )}
    </div>
  )
}
