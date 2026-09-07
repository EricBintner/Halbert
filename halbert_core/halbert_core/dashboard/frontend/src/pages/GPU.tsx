// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * GPU Page - GPU hardware detection, driver management, and AI accelerators.
 *
 * Phase 14: GPU Driver Assistant
 * GPU-1 (2026-09-07): Universal GPU + AI accelerator awareness.
 * Supports discrete GPUs (NVIDIA/AMD/Intel), unified-memory architectures
 * (Apple Silicon, NVIDIA RTX Spark, AMD Strix Halo), and AI accelerators
 * (Coral TPU, Hailo, MemryX, Intel/AMD NPU, Apple ANE).
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
  Apple,
  CircuitBoard,
  Microchip,
  Activity,
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
  vram_mb: number | null
  driver_version: string | null
  driver_type: string | null
  cuda_version: string | null
  pci_id: string
  role: 'auto' | 'display' | 'compute'
  // Runtime stats
  temperature_c: number | null
  power_draw_w: number | null
  power_limit_w: number | null
  utilization_percent: number | null
  memory_used_mb: number | null
  memory_total_mb: number | null
  // GPU-1 normalized fields
  memory_architecture: 'discrete' | 'unified' | 'integrated'
  unified_memory_gb: number | null
  gpu_memory_ceiling_gb: number | null
  gpu_memory_in_use_gb: number | null
  core_count: number | null
  compute_api: string | null  // 'cuda' | 'metal' | 'rocm' | 'directml' | 'opencl'
  memory_source_label: string  // 'VRAM' | 'Unified Memory' | 'System RAM'
}

interface GPUData {
  gpus: GPUInfo[]
  has_nvidia: boolean
  has_amd: boolean
  has_intel: boolean
  has_apple?: boolean
  nvidia_smi_available: boolean
  recommended_driver: string | null
  driver_status: 'optimal' | 'outdated' | 'missing' | 'unknown'
  issues: string[]
}

interface AcceleratorInfo {
  type: 'tpu' | 'npu' | 'ane'
  vendor: string
  model: string
  form_factor: string | null
  device_node: string | null
  tops: number | null
  driver_loaded: boolean
  driver_name: string | null
  driver_version: string | null
  firmware_version: string | null
  temperature_c: number | null
  utilization_percent: number | null
  power_draw_w: number | null
  runtime_available: boolean
  runtime_version: string | null
  status: 'active' | 'idle' | 'missing_driver' | 'missing_runtime' | 'not_detected'
}

interface AcceleratorData {
  accelerators: AcceleratorInfo[]
  has_tpu: boolean
  has_npu: boolean
  has_ane: boolean
  total_tops: number | null
  issues: string[]
}

/** Vendor icon (lucide, no emoji per project rules). */
function VendorIcon({ vendor, className }: { vendor: string; className?: string }) {
  const v = vendor.toLowerCase()
  if (v === 'nvidia') return <CircuitBoard className={cn('text-success', className)} />
  if (v === 'amd') return <CircuitBoard className={cn('text-error', className)} />
  if (v === 'intel') return <CircuitBoard className={cn('text-info', className)} />
  if (v === 'apple') return <Apple className={className} />
  if (v === 'google') return <Microchip className={className} />
  if (v === 'hailo') return <Microchip className={className} />
  if (v === 'memryx') return <Microchip className={className} />
  return <CircuitBoard className={className} />
}

/** Compute API display label. */
function computeApiLabel(api: string | null): string {
  if (!api) return 'Unknown'
  const labels: Record<string, string> = {
    cuda: 'CUDA',
    metal: 'Metal',
    rocm: 'ROCm',
    directml: 'DirectML',
    opencl: 'OpenCL',
  }
  return labels[api] || api
}

/** Diagnostic prompt for the shared AI analysis panel (specialist tier, host scope). */
const GPU_DIAGNOSTIC_MESSAGE = `Analyze my GPU setup on this system for driver and CUDA compatibility. Use your GPU tools (gpu_info, gpu_system_context) to gather live details, retrieve the NVIDIA driver/CUDA compatibility guidance from your knowledge base, and use web search for current driver releases if needed. Assess whether the current driver version is optimal for this GPU and kernel, check compatibility between driver, CUDA, and any ML frameworks (PyTorch/TensorFlow), and only recommend an upgrade if a specific newer version provides clear benefits. Provide specific recommendations with commands and any warnings about the current setup.`

export function GPU() {
  const [gpuData, setGpuData] = useState<GPUData | null>(null)
  const [accelData, setAccelData] = useState<AcceleratorData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)

  const loadGPUData = async () => {
    try {
      const [gpuRes, accelRes] = await Promise.all([
        fetch(apiUrl('/api/gpu/info')),
        fetch(apiUrl('/api/gpu/accelerators')),
      ])
      if (!gpuRes.ok) throw new Error('Failed to load GPU info')
      const data = await gpuRes.json()
      setGpuData(data)
      setError(null)
      if (accelRes.ok) {
        const accel = await accelRes.json()
        setAccelData(accel)
      }
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
    if (model.includes('apple') || gpu.vendor.toLowerCase().includes('apple')) return 'apple'
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

  const allIssues = [...(gpuData.issues || []), ...(accelData?.issues || [])]

  return (
    <div className="space-y-6">
      {/* Header */}
      <PageHeader
        icon={<Cpu className="h-8 w-8" />}
        title="GPU"
        description={`${gpuData.gpus.length} GPU${gpuData.gpus.length !== 1 ? 's' : ''} detected${accelData && accelData.accelerators.length > 0 ? ` · ${accelData.accelerators.length} AI accelerator${accelData.accelerators.length !== 1 ? 's' : ''}` : ''}`}
        scanning={refreshing}
        onScan={handleRefresh}
        scanText="Refresh"
        actions={getDriverStatusBadge(gpuData.driver_status)}
      />

      {/* Issues Alert */}
      {allIssues.length > 0 && (
        <Card className="border-warning/50 bg-warning/5">
          <CardContent className="pt-6">
            <div className="flex items-start gap-3">
              <AlertTriangle className="h-5 w-5 text-warning mt-0.5" />
              <div>
                <h3 className="font-medium text-warning dark:text-warning">Issues Detected</h3>
                <ul className="mt-2 space-y-1 text-sm text-muted-foreground">
                  {allIssues.map((issue, i) => (
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
          const isUnified = gpu.memory_architecture === 'unified'
          const isIntegrated = gpu.memory_architecture === 'integrated'
          const isApple = vendor === 'apple'
          const memoryLabel = gpu.memory_source_label || (isUnified ? 'Unified Memory' : isIntegrated ? 'System RAM' : 'VRAM')

          return (
            <Card key={index}>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className={cn(
                      'w-10 h-10 rounded-lg flex items-center justify-center',
                      vendor === 'nvidia' && 'bg-success/10',
                      vendor === 'amd' && 'bg-error/10',
                      vendor === 'intel' && 'bg-info/10',
                      vendor === 'apple' && 'bg-muted',
                    )}>
                      <VendorIcon vendor={vendor} className="h-5 w-5" />
                    </div>
                    <div>
                      <CardTitle className="text-lg">{gpu.model}</CardTitle>
                      <CardDescription>
                        {gpu.vendor}
                        {gpu.core_count && ` · ${gpu.core_count} cores`}
                        {gpu.compute_api && ` · ${computeApiLabel(gpu.compute_api)}`}
                      </CardDescription>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {/* GPU Role Selector — hidden for Apple (single-GPU SoC) */}
                    {!isApple && (
                      <Select
                        size="sm"
                        value={gpu.role || 'auto'}
                        onChange={async (e) => {
                          const newRole = e.target.value
                          const pciIdSafe = gpu.pci_id.replace(/:/g, '-')
                          try {
                            const res = await fetch(apiUrl(`/api/gpu/role/${pciIdSafe}?role=${newRole}`), { method: 'PUT' })
                            if (res.ok) {
                              loadGPUData()
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
                    )}
                    <Badge variant="outline" className="text-xs">
                      {isUnified && gpu.unified_memory_gb
                        ? `${gpu.unified_memory_gb} GB Unified`
                        : gpu.vram_mb
                          ? `${(gpu.vram_mb / 1024).toFixed(0)} GB ${memoryLabel}`
                          : `Unknown ${memoryLabel}`}
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
                          memory_architecture: gpu.memory_architecture,
                          compute_api: gpu.compute_api,
                        },
                        context: `GPU: ${gpu.model}\nVendor: ${gpu.vendor}\nDriver: ${gpu.driver_type || 'Unknown'} ${gpu.driver_version || ''}\nMemory: ${gpu.vram_mb ? (gpu.vram_mb / 1024).toFixed(0) + ' GB ' + memoryLabel : 'Unknown'}\nCompute API: ${computeApiLabel(gpu.compute_api)}\nCUDA: ${gpu.cuda_version || 'N/A'}`,
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
                      <p className="text-xs text-muted-foreground">{memoryLabel}</p>
                      <p className="font-medium">
                        {((gpu.memory_used_mb || 0) / 1024).toFixed(1)} / {(gpu.memory_total_mb / 1024).toFixed(1)} GB
                      </p>
                    </div>
                  )}
                </div>

                {/* Unified memory detail for unified architectures */}
                {isUnified && gpu.unified_memory_gb && (
                  <div className="grid grid-cols-2 md:grid-cols-3 gap-4 border-t pt-4">
                    <div className="space-y-1">
                      <p className="text-xs text-muted-foreground">Total Unified Pool</p>
                      <p className="font-medium">{gpu.unified_memory_gb} GB</p>
                    </div>
                    {gpu.gpu_memory_ceiling_gb && (
                      <div className="space-y-1">
                        <p className="text-xs text-muted-foreground">GPU Working-Set Ceiling</p>
                        <p className="font-medium">{gpu.gpu_memory_ceiling_gb} GB</p>
                      </div>
                    )}
                    {gpu.gpu_memory_in_use_gb !== null && (
                      <div className="space-y-1">
                        <p className="text-xs text-muted-foreground">GPU Memory In Use</p>
                        <p className="font-medium">{gpu.gpu_memory_in_use_gb} GB</p>
                      </div>
                    )}
                  </div>
                )}

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
                              {memoryLabel}
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
                              'font-medium',
                              gpu.temperature_c > 80 && 'text-error',
                              gpu.temperature_c > 70 && gpu.temperature_c <= 80 && 'text-warning',
                            )}>
                              {gpu.temperature_c}°C
                            </span>
                          </div>
                          <Progress
                            value={Math.min(100, (gpu.temperature_c / 100) * 100)}
                            className={cn(
                              'h-2',
                              gpu.temperature_c > 80 && '[&>div]:bg-error',
                              gpu.temperature_c > 70 && gpu.temperature_c <= 80 && '[&>div]:bg-warning',
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
                    {/* Note for unified architectures where temp/power require elevated privileges */}
                    {isUnified && gpu.temperature_c === null && gpu.power_draw_w === null && (
                      <p className="text-xs text-muted-foreground mt-3">
                        Temperature and power require elevated privileges on this platform.
                      </p>
                    )}
                  </div>
                )}

                {/* Quick Links — vendor-specific, hidden for Apple (no driver downloads) */}
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

      {/* AI Accelerators Section */}
      {accelData && accelData.accelerators.length > 0 && (
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            <Activity className="h-5 w-5 text-muted-foreground" />
            <h2 className="text-xl font-semibold">AI Accelerators</h2>
            {accelData.total_tops && (
              <Badge variant="outline" className="text-xs">
                {accelData.total_tops} TOPS total
              </Badge>
            )}
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            {accelData.accelerators.map((acc, index) => (
              <Card key={index}>
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-lg flex items-center justify-center bg-muted">
                        <VendorIcon vendor={acc.vendor} className="h-5 w-5" />
                      </div>
                      <div>
                        <CardTitle className="text-base">{acc.model}</CardTitle>
                        <CardDescription>
                          {acc.vendor}
                          {acc.tops && ` · ${acc.tops} TOPS`}
                          {acc.form_factor && ` · ${acc.form_factor}`}
                        </CardDescription>
                      </div>
                    </div>
                    <Badge
                      variant={acc.status === 'active' ? 'default' : 'destructive'}
                      className="text-xs"
                    >
                      {acc.status === 'active' && <CheckCircle className="h-3 w-3 mr-1" />}
                      {acc.status === 'missing_driver' && <AlertTriangle className="h-3 w-3 mr-1" />}
                      {acc.status === 'missing_runtime' && <AlertTriangle className="h-3 w-3 mr-1" />}
                      {acc.status}
                    </Badge>
                  </div>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-2 gap-4 text-sm">
                    <div className="space-y-1">
                      <p className="text-xs text-muted-foreground">Driver</p>
                      <p className="font-medium">
                        {acc.driver_loaded
                          ? `${acc.driver_name || 'Loaded'}${acc.driver_version ? ` ${acc.driver_version}` : ''}`
                          : 'Not loaded'}
                      </p>
                    </div>
                    <div className="space-y-1">
                      <p className="text-xs text-muted-foreground">Runtime</p>
                      <p className="font-medium">
                        {acc.runtime_available
                          ? acc.runtime_version || 'Available'
                          : 'Not available'}
                      </p>
                    </div>
                    {acc.firmware_version && (
                      <div className="space-y-1">
                        <p className="text-xs text-muted-foreground">Firmware</p>
                        <p className="font-medium">{acc.firmware_version}</p>
                      </div>
                    )}
                    {acc.device_node && (
                      <div className="space-y-1">
                        <p className="text-xs text-muted-foreground">Device</p>
                        <p className="font-medium font-mono text-xs">{acc.device_node}</p>
                      </div>
                    )}
                    {acc.temperature_c !== null && (
                      <div className="space-y-1">
                        <p className="text-xs text-muted-foreground">Temperature</p>
                        <p className="font-medium">{acc.temperature_c}°C</p>
                      </div>
                    )}
                    {acc.utilization_percent !== null && (
                      <div className="space-y-1">
                        <p className="text-xs text-muted-foreground">Utilization</p>
                        <p className="font-medium">{acc.utilization_percent}%</p>
                      </div>
                    )}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      )}

      {/* No GPU Detected */}
      {gpuData.gpus.length === 0 && (!accelData || accelData.accelerators.length === 0) && (
        <Card>
          <CardContent className="pt-6">
            <div className="text-center py-8">
              <Monitor className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
              <h3 className="font-medium mb-2">No GPU Detected</h3>
              <p className="text-sm text-muted-foreground">
                This system appears to have no detectable GPU or AI accelerator.
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
