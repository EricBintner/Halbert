/**
 * Services Page - View and manage system services.
 * 
 * Based on Phase 9 research: docs/Phase9/deep-dives/05-services-daemons.md
 */

import { useEffect, useState, useCallback } from 'react'
import { useScan } from '@/contexts/ScanContext'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { api } from '@/lib/api'
import { generationQueue } from '@/lib/generationQueue'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from '@/components/ui/sheet'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { 
  Server, 
  RefreshCw, 
  Play, 
  Square, 
  RotateCcw,
  AlertCircle,
  CheckCircle,
  Container,
  Search,
  ChevronRight,
  Shield,
  HardDrive,
  Network,
  Monitor,
  Volume2,
  Printer,
  Database,
  Globe,
  Box,
  Cog,
  AlertTriangle,
  Sparkles,
  Loader2,
  MessageCircle,
  Stethoscope,
  Copy,
  Check,
  Terminal,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { AIAnalysisPanel } from '@/components/AIAnalysisPanel'
import { openChat } from '@/components/SendToChat'
import { SystemItemActions } from '@/components/domain'

/**
 * Executable code block component with copy and run buttons
 */
function CodeBlock({ code, lang }: { code: string; lang: string }) {
  const [copied, setCopied] = useState(false)
  
  const handleCopy = () => {
    navigator.clipboard.writeText(code)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }
  
  const handleExecute = () => {
    window.dispatchEvent(new CustomEvent('halbert:run-command', { 
      detail: { command: code } 
    }))
  }
  
  const isExecutable = ['bash', 'sh', 'shell', 'zsh', ''].includes(lang.toLowerCase())
  
  return (
    <div className="rounded-md overflow-hidden border border-border/50 bg-zinc-900 my-2">
      <div className="flex items-center justify-between px-2 py-1 bg-zinc-800 border-b border-border/30">
        <div className="flex items-center gap-1.5">
          <Terminal className="h-3 w-3 text-green-400" />
          <span className="text-[10px] text-zinc-400 font-mono">{lang || 'bash'}</span>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={handleCopy}
            className="p-1 rounded hover:bg-zinc-700 transition-colors"
            title="Copy"
          >
            {copied ? (
              <Check className="h-3 w-3 text-green-400" />
            ) : (
              <Copy className="h-3 w-3 text-zinc-400" />
            )}
          </button>
          {isExecutable && (
            <button
              onClick={handleExecute}
              className="p-1 rounded hover:bg-zinc-700 transition-colors"
              title="Run in Terminal"
            >
              <Play className="h-3 w-3 text-green-400" />
            </button>
          )}
        </div>
      </div>
      <pre className="p-2 text-[11px] font-mono text-green-300 overflow-x-auto">
        <code>{code}</code>
      </pre>
    </div>
  )
}

/**
 * Simple markdown renderer for LLM output.
 * Handles: **bold**, headers, bullet points, code blocks, and paragraphs.
 */
function renderMarkdown(text: string): React.ReactNode {
  if (!text) return null
  
  // First, extract and replace code blocks with placeholders
  const codeBlocks: Array<{ lang: string; code: string }> = []
  const textWithPlaceholders = text.replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) => {
    codeBlocks.push({ lang: lang || 'bash', code: code.trim() })
    return `__CODE_BLOCK_${codeBlocks.length - 1}__`
  })
  
  // Split into paragraphs (but keep single newlines within bullet lists)
  const paragraphs = textWithPlaceholders.split(/\n\n+/)
  
  return paragraphs.map((paragraph, pIndex) => {
    const trimmed = paragraph.trim()
    
    // Check if this is a code block placeholder
    const codeMatch = trimmed.match(/^__CODE_BLOCK_(\d+)__$/)
    if (codeMatch) {
      const block = codeBlocks[parseInt(codeMatch[1])]
      return <CodeBlock key={pIndex} code={block.code} lang={block.lang} />
    }
    
    // Handle ## headers (section headers)
    if (trimmed.startsWith('## ')) {
      return (
        <h3 key={pIndex} className="font-semibold text-sm text-primary mt-4 mb-2 pb-1 border-b border-border first:mt-0">
          {trimmed.slice(3)}
        </h3>
      )
    }
    
    // Handle # headers (main title)
    if (trimmed.startsWith('# ')) {
      return (
        <h2 key={pIndex} className="font-bold text-base mt-3 mb-2 first:mt-0">
          {trimmed.slice(2)}
        </h2>
      )
    }
    
    // Handle bullet points (lines starting with - or *)
    if (trimmed.match(/^[-*•]\s/m)) {
      const items = trimmed.split(/\n/).filter(line => line.trim())
      return (
        <ul key={pIndex} className="space-y-1.5 my-2 ml-1">
          {items.map((item, iIndex) => (
            <li key={iIndex} className="text-sm flex items-start gap-2">
              <span className="text-muted-foreground mt-1.5 text-[6px]">●</span>
              <span className="flex-1">{formatInlineMarkdown(item.replace(/^[-*•]\s*/, ''))}</span>
            </li>
          ))}
        </ul>
      )
    }
    
    // Regular paragraph with inline formatting
    return (
      <p key={pIndex} className="text-sm leading-relaxed mb-3 last:mb-0 text-foreground/90">
        {formatInlineMarkdown(trimmed)}
      </p>
    )
  })
}

/**
 * Format inline markdown: **bold**, [links](url)
 */
function formatInlineMarkdown(text: string): React.ReactNode {
  const parts: React.ReactNode[] = []
  let keyIndex = 0
  
  // Combined regex for **bold** and [link](url)
  const combinedRegex = /\*\*(.+?)\*\*|\[([^\]]+)\]\(([^)]+)\)/g
  let lastIndex = 0
  let match
  
  while ((match = combinedRegex.exec(text)) !== null) {
    // Add text before the match
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index))
    }
    
    if (match[1]) {
      // Bold text
      parts.push(<strong key={keyIndex++} className="font-semibold">{match[1]}</strong>)
    } else if (match[2] && match[3]) {
      // Link [text](url)
      parts.push(
        <a 
          key={keyIndex++} 
          href={match[3]} 
          target="_blank" 
          rel="noopener noreferrer"
          className="text-primary hover:underline"
        >
          {match[2]}
        </a>
      )
    }
    
    lastIndex = match.index + match[0].length
  }
  
  // Add remaining text
  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex))
  }
  
  return parts.length > 0 ? parts : text
}

interface Service {
  id: string
  name: string
  title: string
  description: string
  status: string
  severity: string
  data: {
    service_type: string
    enabled: boolean
    memory_mb?: number
    unit_file?: string
    container_name?: string
    image?: string
    category?: string
    is_critical?: boolean
    install_source?: string
    context_hint?: string
  }
}

type StatusFilter = 'all' | 'running' | 'failed' | 'stopped' | 'docker'
type CategoryFilter = 'all' | 'audio' | 'network' | 'storage' | 'desktop' | 'security' | 'print' | 
  'virtualization' | 'database' | 'web' | 'packages' | 'power' | 'logging' | 'time' | 'hardware' | 
  'session' | 'cloud' | 'backup' | 'bluetooth' | 'messaging' | 'diagnostics' | 'other'

const CATEGORY_CONFIG: Record<CategoryFilter, { label: string; icon: React.ReactNode; color: string }> = {
  all: { label: 'All Types', icon: <Server className="h-4 w-4" />, color: 'text-muted-foreground' },
  audio: { label: 'Audio', icon: <Volume2 className="h-4 w-4" />, color: 'text-purple-500' },
  network: { label: 'Network', icon: <Network className="h-4 w-4" />, color: 'text-blue-500' },
  storage: { label: 'Storage', icon: <HardDrive className="h-4 w-4" />, color: 'text-orange-500' },
  desktop: { label: 'Desktop', icon: <Monitor className="h-4 w-4" />, color: 'text-green-500' },
  security: { label: 'Security', icon: <Shield className="h-4 w-4" />, color: 'text-red-500' },
  print: { label: 'Print', icon: <Printer className="h-4 w-4" />, color: 'text-cyan-500' },
  virtualization: { label: 'Virtual', icon: <Box className="h-4 w-4" />, color: 'text-indigo-500' },
  database: { label: 'Database', icon: <Database className="h-4 w-4" />, color: 'text-yellow-500' },
  web: { label: 'Web', icon: <Globe className="h-4 w-4" />, color: 'text-pink-500' },
  packages: { label: 'Packages', icon: <Box className="h-4 w-4" />, color: 'text-emerald-500' },
  power: { label: 'Power', icon: <Cog className="h-4 w-4" />, color: 'text-amber-500' },
  logging: { label: 'Logging', icon: <Server className="h-4 w-4" />, color: 'text-slate-500' },
  time: { label: 'Time', icon: <Cog className="h-4 w-4" />, color: 'text-sky-500' },
  hardware: { label: 'Hardware', icon: <Cog className="h-4 w-4" />, color: 'text-zinc-500' },
  session: { label: 'Session', icon: <Monitor className="h-4 w-4" />, color: 'text-violet-500' },
  cloud: { label: 'Cloud', icon: <Globe className="h-4 w-4" />, color: 'text-sky-400' },
  backup: { label: 'Backup', icon: <HardDrive className="h-4 w-4" />, color: 'text-teal-500' },
  bluetooth: { label: 'Bluetooth', icon: <Network className="h-4 w-4" />, color: 'text-blue-400' },
  messaging: { label: 'IPC', icon: <Server className="h-4 w-4" />, color: 'text-fuchsia-500' },
  diagnostics: { label: 'Diag', icon: <AlertCircle className="h-4 w-4" />, color: 'text-rose-500' },
  other: { label: 'Other', icon: <Server className="h-4 w-4" />, color: 'text-muted-foreground' },
}

export function Services() {
  const { refreshTrigger } = useScan()
  
  const [services, setServices] = useState<Service[]>([])
  const [loading, setLoading] = useState(true)
  const [scanning, setScanning] = useState(false)
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')
  const [categoryFilter, setCategoryFilter] = useState<CategoryFilter>('all')
  const [search, setSearch] = useState('')
  const [selectedService, setSelectedService] = useState<Service | null>(null)
  const [llmExplanation, setLlmExplanation] = useState<string | null>(null)
  const [failureDiagnosis, setFailureDiagnosis] = useState<string | null>(null)
  const [activeAiTab, setActiveAiTab] = useState<'explanation' | 'diagnosis'>('explanation')
  const [, forceUpdate] = useState({})  // Force re-render on queue changes
  const [queueCount, setQueueCount] = useState(0)

  // Subscribe to queue changes
  useEffect(() => {
    const unsubscribe = generationQueue.subscribe(() => {
      forceUpdate({})
      setQueueCount(generationQueue.getPendingCount())
      
      // Update local state with completed results
      if (selectedService) {
        const expResult = generationQueue.getResult(selectedService.name, 'explanation')
        if (expResult && expResult !== llmExplanation) {
          setLlmExplanation(expResult)
          setCachedExplanation(selectedService.name, expResult)
        }
        
        const diagResult = generationQueue.getResult(selectedService.name, 'diagnosis')
        if (diagResult && diagResult !== failureDiagnosis) {
          setFailureDiagnosis(diagResult)
        }
      }
    })
    return unsubscribe
  }, [selectedService, llmExplanation, failureDiagnosis])

  // Cache helpers for persistent explanations
  const EXPLANATION_CACHE_KEY = 'halbert_service_explanations'
  
  const getCachedExplanation = (serviceName: string): string | null => {
    try {
      const cache = JSON.parse(localStorage.getItem(EXPLANATION_CACHE_KEY) || '{}')
      return cache[serviceName] || null
    } catch {
      return null
    }
  }
  
  const setCachedExplanation = (serviceName: string, explanation: string) => {
    try {
      const cache = JSON.parse(localStorage.getItem(EXPLANATION_CACHE_KEY) || '{}')
      cache[serviceName] = explanation
      localStorage.setItem(EXPLANATION_CACHE_KEY, JSON.stringify(cache))
    } catch (e) {
      console.warn('Failed to cache explanation:', e)
    }
  }
  
  // Check if loading (either pending or processing in queue)
  const isLoadingExplanation = useCallback((serviceName: string) => {
    return generationQueue.hasPending(serviceName, 'explanation')
  }, [])
  
  const isLoadingDiagnosis = useCallback((serviceName: string) => {
    return generationQueue.hasPending(serviceName, 'diagnosis')
  }, [])

  useEffect(() => {
    loadServices()
  }, [])

  // Refresh when system-wide scan completes (via context)
  useEffect(() => {
    if (refreshTrigger > 0) {
      loadServices()
    }
  }, [refreshTrigger])

  // Also listen for window events (backup mechanism)
  useEffect(() => {
    const handleScanComplete = () => loadServices()
    window.addEventListener('halbert-scan-complete', handleScanComplete)
    return () => window.removeEventListener('halbert-scan-complete', handleScanComplete)
  }, [])

  const loadServices = async () => {
    try {
      const data = await api.getDiscoveries('service')
      setServices(data.discoveries || [])
    } catch (error) {
      console.error('Failed to load services:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleScan = async () => {
    setScanning(true)
    try {
      await api.scanDiscoveries('service')
      await loadServices()
    } catch (error) {
      console.error('Scan failed:', error)
    } finally {
      setScanning(false)
    }
  }

  const [actionLoading, setActionLoading] = useState<string | null>(null)
  const [actionResult, setActionResult] = useState<{ success: boolean; message: string } | null>(null)

  const handleAction = async (service: Service, action: string, e?: React.MouseEvent) => {
    e?.stopPropagation()
    
    if (action !== 'start' && action !== 'stop' && action !== 'restart') {
      console.warn(`Unknown action: ${action}`)
      return
    }
    
    setActionLoading(action)
    setActionResult(null)
    
    try {
      const response = await api.controlService(service.name, action)
      setActionResult({
        success: response.success,
        message: response.message
      })
      
      // Refresh the service list after a successful action
      if (response.success) {
        setTimeout(() => {
          loadServices()
          setActionResult(null)
        }, 1500)
      }
    } catch (error) {
      console.error(`Failed to ${action} service:`, error)
      setActionResult({
        success: false,
        message: `Failed to ${action} service: ${error}`
      })
    } finally {
      setActionLoading(null)
    }
  }

  const openServiceDetail = (service: Service) => {
    setSelectedService(service)
    setActiveAiTab('explanation')
    
    // Check cache first - explanations persist as machine self-knowledge
    const cached = getCachedExplanation(service.name)
    if (cached) {
      setLlmExplanation(cached)
      return
    }
    
    // Check if already in queue or completed
    const queueResult = generationQueue.getResult(service.name, 'explanation')
    if (queueResult) {
      setLlmExplanation(queueResult)
      setCachedExplanation(service.name, queueResult)
      return
    }
    
    // Check for cached diagnosis too
    const cachedDiag = generationQueue.getCachedDiagnosis(service.name, service.status)
    if (cachedDiag) {
      setFailureDiagnosis(cachedDiag)
    } else {
      setFailureDiagnosis(null)
    }
    
    // Enqueue explanation generation if not already pending
    if (!generationQueue.hasPending(service.name, 'explanation')) {
      setLlmExplanation(null)
      generationQueue.enqueue(service.name, 'explanation')
    }
  }

  const diagnoseFailure = (service: Service) => {
    // Check cache first (with TTL and status invalidation)
    const cached = generationQueue.getCachedDiagnosis(service.name, service.status)
    if (cached) {
      setFailureDiagnosis(cached)
      return
    }
    
    // Check if already completed in queue
    const queueResult = generationQueue.getResult(service.name, 'diagnosis')
    if (queueResult) {
      setFailureDiagnosis(queueResult)
      return
    }
    
    // Enqueue diagnosis generation if not already pending
    if (!generationQueue.hasPending(service.name, 'diagnosis')) {
      setFailureDiagnosis(null)
      generationQueue.enqueue(service.name, 'diagnosis', service.status)
    }
  }

  const continueInChat = (service: Service, context: string) => {
    // Close the drawer first
    setSelectedService(null)
    
    // Open chat with the AI-generated context as the first message
    openChat({
      title: service.name,
      type: 'service',
      context: context,
      itemId: service.name,
      newConversation: true,
      useSpecialist: false,
    })
  }

  const getCategoryIcon = (category?: string) => {
    const cat = (category || 'other') as CategoryFilter
    return CATEGORY_CONFIG[cat]?.icon || CATEGORY_CONFIG.other.icon
  }

  const getCategoryColor = (category?: string) => {
    const cat = (category || 'other') as CategoryFilter
    return CATEGORY_CONFIG[cat]?.color || CATEGORY_CONFIG.other.color
  }

  const filteredServices = services.filter(s => {
    // Apply status filter
    if (statusFilter === 'running' && s.status !== 'Running') return false
    if (statusFilter === 'failed' && s.severity !== 'critical') return false
    if (statusFilter === 'stopped' && s.status !== 'Stopped') return false
    if (statusFilter === 'docker' && s.data.service_type !== 'docker') return false

    // Apply category filter
    if (categoryFilter !== 'all') {
      const serviceCategory = s.data.category || 'other'
      if (serviceCategory !== categoryFilter) return false
    }

    // Apply search
    if (search) {
      const searchLower = search.toLowerCase()
      return (
        s.name.toLowerCase().includes(searchLower) ||
        s.description.toLowerCase().includes(searchLower) ||
        (s.data.context_hint?.toLowerCase().includes(searchLower))
      )
    }

    return true
  })

  // Category counts for filter badges
  const categoryCounts = services.reduce((acc, s) => {
    const cat = s.data.category || 'other'
    acc[cat] = (acc[cat] || 0) + 1
    return acc
  }, {} as Record<string, number>)

  const stats = {
    total: services.length,
    running: services.filter(s => s.status === 'Running').length,
    failed: services.filter(s => s.severity === 'critical').length,
    docker: services.filter(s => s.data.service_type === 'docker').length,
  }

  if (loading) {
    return <div className="flex items-center justify-center h-64">Loading...</div>
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold flex items-center gap-2">
            <Server className="h-8 w-8" />
            Services
          </h1>
          <p className="text-muted-foreground">
            Manage system services and containers
          </p>
        </div>
        <Button variant="outline" onClick={handleScan} disabled={scanning}>
          <RefreshCw className={cn("h-4 w-4 mr-2", scanning && "animate-spin")} />
          {scanning ? 'Scanning...' : 'Scan'}
        </Button>
      </div>

      {/* Stats */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card className="cursor-pointer hover:bg-accent/50" onClick={() => setStatusFilter('all')}>
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Total</p>
                <p className="text-2xl font-bold">{stats.total}</p>
              </div>
              <Server className="h-8 w-8 text-muted-foreground" />
            </div>
          </CardContent>
        </Card>
        <Card className="cursor-pointer hover:bg-accent/50" onClick={() => setStatusFilter('running')}>
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Running</p>
                <p className="text-2xl font-bold text-green-500">{stats.running}</p>
              </div>
              <CheckCircle className="h-8 w-8 text-green-500" />
            </div>
          </CardContent>
        </Card>
        <Card className="cursor-pointer hover:bg-accent/50" onClick={() => setStatusFilter('failed')}>
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Failed</p>
                <p className="text-2xl font-bold text-red-500">{stats.failed}</p>
              </div>
              <AlertCircle className="h-8 w-8 text-red-500" />
            </div>
          </CardContent>
        </Card>
        <Card className="cursor-pointer hover:bg-accent/50" onClick={() => setStatusFilter('docker')}>
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Docker</p>
                <p className="text-2xl font-bold text-blue-500">{stats.docker}</p>
              </div>
              <Container className="h-8 w-8 text-blue-500" />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Search & Status Filters */}
      <div className="flex gap-4">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
          <input
            type="text"
            placeholder="Search services..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-9 pr-4 py-2 rounded-md border bg-background"
          />
        </div>
        <div className="flex gap-2">
          {(['all', 'running', 'failed', 'stopped', 'docker'] as StatusFilter[]).map((f) => (
            <Button
              key={f}
              variant={statusFilter === f ? 'default' : 'outline'}
              size="sm"
              onClick={() => setStatusFilter(f)}
            >
              {f.charAt(0).toUpperCase() + f.slice(1)}
            </Button>
          ))}
        </div>
      </div>

      {/* Category Filters */}
      <div className="flex flex-wrap gap-2">
        {(Object.keys(CATEGORY_CONFIG) as CategoryFilter[]).map((cat) => {
          const config = CATEGORY_CONFIG[cat]
          const count = cat === 'all' ? services.length : (categoryCounts[cat] || 0)
          if (cat !== 'all' && count === 0) return null
          
          return (
            <Button
              key={cat}
              variant={categoryFilter === cat ? 'default' : 'outline'}
              size="sm"
              onClick={() => setCategoryFilter(cat)}
              className="gap-1.5"
            >
              <span className={cn(categoryFilter !== cat && config.color)}>
                {config.icon}
              </span>
              {config.label}
              <Badge variant="secondary" className="ml-1 px-1.5 py-0 text-xs">
                {count}
              </Badge>
            </Button>
          )
        })}
      </div>

      {/* Service List */}
      <Card>
        <CardContent className="p-0">
          <div className="divide-y">
            {filteredServices.length === 0 ? (
              <div className="p-8 text-center text-muted-foreground">
                {services.length === 0 
                  ? "No services discovered. Click Scan to find services."
                  : "No services match your filters."}
              </div>
            ) : (
              filteredServices.map((service) => (
                <div
                  key={service.id}
                  className="flex items-center justify-between p-4 hover:bg-accent/30 cursor-pointer group"
                  onClick={() => openServiceDetail(service)}
                >
                  <div className="flex items-center gap-4 flex-1 min-w-0">
                    <div className={cn("flex-shrink-0", getCategoryColor(service.data.category))}>
                      {service.data.service_type === 'docker' ? (
                        <Container className="h-5 w-5" />
                      ) : (
                        getCategoryIcon(service.data.category)
                      )}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <p className="font-medium">{service.name}</p>
                        {service.data.is_critical && (
                          <Badge variant="outline" className="text-xs border-red-500 text-red-500">
                            Critical
                          </Badge>
                        )}
                      </div>
                      <p className="text-sm text-muted-foreground truncate">
                        {service.description}
                      </p>
                      {service.data.context_hint && (
                        <p className="text-xs text-muted-foreground/70 mt-0.5 truncate">
                          {service.data.context_hint}
                        </p>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-4">
                    {service.data.memory_mb && (
                      <span className="text-sm text-muted-foreground">
                        {service.data.memory_mb.toFixed(0)} MB
                      </span>
                    )}
                    <Badge
                      className={cn(
                        service.severity === 'critical' && 'bg-red-500',
                        service.severity === 'warning' && 'bg-yellow-500',
                        service.severity === 'success' && 'bg-green-500',
                        service.severity === 'info' && service.status === 'Completed' && 'bg-violet-500',
                        service.severity === 'info' && service.status !== 'Completed' && 'bg-slate-500',
                      )}
                    >
                      {service.status}
                    </Badge>
                    <div className="flex gap-1">
                      {service.status === 'Running' ? (
                        <>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8"
                            onClick={(e) => handleAction(service, 'restart', e)}
                            title="Restart"
                          >
                            <RotateCcw className="h-4 w-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8"
                            onClick={(e) => handleAction(service, 'stop', e)}
                            title="Stop"
                          >
                            <Square className="h-4 w-4" />
                          </Button>
                        </>
                      ) : (
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8"
                          onClick={(e) => handleAction(service, 'start', e)}
                          title="Start"
                        >
                          <Play className="h-4 w-4" />
                        </Button>
                      )}
                    </div>
                    <SystemItemActions
                      item={{
                        name: service.name,
                        type: 'service',
                        id: `service/${service.name}`,
                        description: service.description,
                        status: service.status,
                        data: service.data,
                        context: `Service: ${service.name}\nStatus: ${service.status}\nDescription: ${service.description}`,
                      }}
                      size="sm"
                    />
                    <ChevronRight className="h-4 w-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
                  </div>
                </div>
              ))
            )}
          </div>
        </CardContent>
      </Card>

      {/* Service Detail Drawer */}
      <Sheet open={!!selectedService} onOpenChange={(open) => !open && setSelectedService(null)}>
        <SheetContent className="flex flex-col overflow-hidden">
          {selectedService && (
            <div className="flex flex-col h-full">
              <SheetHeader className="flex-shrink-0">
                <div className="flex items-center gap-3">
                  <div className={cn("p-2 rounded-lg bg-muted", getCategoryColor(selectedService.data.category))}>
                    {selectedService.data.service_type === 'docker' ? (
                      <Container className="h-6 w-6" />
                    ) : (
                      getCategoryIcon(selectedService.data.category)
                    )}
                  </div>
                  <div>
                    <SheetTitle className="flex items-center gap-2">
                      {selectedService.name}
                      {selectedService.data.is_critical && (
                        <AlertTriangle className="h-4 w-4 text-red-500" />
                      )}
                    </SheetTitle>
                    <SheetDescription>{selectedService.description}</SheetDescription>
                  </div>
                </div>
              </SheetHeader>

              <div className="mt-3 flex-1 flex flex-col overflow-hidden min-h-0">
                {/* Status & Category - Inline */}
                <div className="flex items-center gap-3 flex-shrink-0 text-sm">
                  <Badge
                    className={cn(
                      selectedService.severity === 'critical' && 'bg-red-500',
                      selectedService.severity === 'warning' && 'bg-yellow-500',
                      selectedService.severity === 'success' && 'bg-green-500',
                      selectedService.severity === 'info' && selectedService.status === 'Completed' && 'bg-violet-500',
                      selectedService.severity === 'info' && selectedService.status !== 'Completed' && 'bg-slate-500',
                    )}
                  >
                    {selectedService.status}
                  </Badge>
                  <span className="text-muted-foreground">•</span>
                  <span className={cn("font-medium capitalize", getCategoryColor(selectedService.data.category))}>
                    {selectedService.data.category || 'Other'}
                  </span>
                </div>

                {/* Compact Metadata */}
                <div className="flex-shrink-0 mt-3 text-sm border-t pt-2">
                  <div className="flex justify-between py-1 border-b border-border/50">
                    <span className="text-muted-foreground">Installed by</span>
                    <span className="font-medium">
                      {selectedService.data.install_source === 'user' ? 'User' : 
                       selectedService.data.install_source === 'system' ? 'OS' : 'Unknown'}
                    </span>
                  </div>
                  <div className="flex justify-between py-1 border-b border-border/50">
                    <span className="text-muted-foreground">Type</span>
                    <span className="font-medium capitalize">{selectedService.data.service_type}</span>
                  </div>
                  <div className="flex justify-between py-1 border-b border-border/50">
                    <span className="text-muted-foreground">Enabled</span>
                    <span className="font-medium">{selectedService.data.enabled ? 'Yes' : 'No'}</span>
                  </div>
                  {selectedService.data.memory_mb && (
                    <div className="flex justify-between py-1 border-b border-border/50">
                      <span className="text-muted-foreground">Memory</span>
                      <span className="font-medium">{selectedService.data.memory_mb.toFixed(1)} MB</span>
                    </div>
                  )}
                  {selectedService.data.unit_file && (
                    <div className="flex justify-between py-1">
                      <span className="text-muted-foreground">Unit File</span>
                      <span className="font-medium font-mono text-xs truncate max-w-[180px]">{selectedService.data.unit_file}</span>
                    </div>
                  )}
                </div>

                {/* AI Insights - Tabs for failed services */}
                <div className="flex-1 flex flex-col min-h-0 overflow-hidden mt-3">
                  {selectedService.severity === 'critical' ? (
                    // Tabbed view for failed services
                    <Tabs value={activeAiTab} onValueChange={(v) => setActiveAiTab(v as 'explanation' | 'diagnosis')} className="flex-1 flex flex-col min-h-0">
                      <TabsList className="grid w-full grid-cols-2 flex-shrink-0">
                        <TabsTrigger value="explanation" className="gap-1.5">
                          <Sparkles className="h-3.5 w-3.5" />
                          Explanation
                        </TabsTrigger>
                        <TabsTrigger 
                          value="diagnosis" 
                          className="gap-1.5"
                          onClick={() => {
                            if (!failureDiagnosis && !isLoadingDiagnosis(selectedService.name)) {
                              diagnoseFailure(selectedService)
                            }
                          }}
                        >
                          <Stethoscope className="h-3.5 w-3.5" />
                          Why It Failed
                        </TabsTrigger>
                      </TabsList>
                      
                      <TabsContent value="explanation" className="mt-2 flex-1 flex flex-col min-h-0 overflow-hidden data-[state=inactive]:hidden">
                        <div className="p-3 rounded-lg bg-muted/50 flex-1 overflow-y-auto min-h-0">
                          {isLoadingExplanation(selectedService.name) ? (
                            <div className="flex flex-col items-center gap-2 text-muted-foreground py-4">
                              <Loader2 className="h-4 w-4 animate-spin" />
                              <span>Generating explanation...</span>
                              {queueCount > 1 && (
                                <span className="text-xs text-muted-foreground/70">
                                  {queueCount - 1} other request{queueCount > 2 ? 's' : ''} ahead
                                </span>
                              )}
                            </div>
                          ) : (
                            <div className="prose prose-sm dark:prose-invert max-w-none">
                              {renderMarkdown(llmExplanation || selectedService.data.context_hint || 'No explanation available.')}
                            </div>
                          )}
                        </div>
                        <div className="flex justify-end mt-1 flex-shrink-0">
                          <button
                            className="p-1 rounded text-muted-foreground hover:text-foreground transition-colors"
                            onClick={() => continueInChat(selectedService, llmExplanation || '')}
                            title="Continue in Chat"
                          >
                            <MessageCircle className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      </TabsContent>
                      
                      <TabsContent value="diagnosis" className="mt-2 flex-1 flex flex-col min-h-0 overflow-hidden data-[state=inactive]:hidden">
                        <div className="p-3 rounded-lg bg-red-500/10 flex-1 overflow-y-auto min-h-0">
                          {isLoadingDiagnosis(selectedService.name) ? (
                            <div className="flex flex-col items-center gap-2 text-muted-foreground py-4">
                              <Loader2 className="h-4 w-4 animate-spin" />
                              <span>Analyzing service logs and status...</span>
                              {queueCount > 1 && (
                                <span className="text-xs text-muted-foreground/70">
                                  {queueCount - 1} other request{queueCount > 2 ? 's' : ''} ahead
                                </span>
                              )}
                            </div>
                          ) : (
                            <div className="prose prose-sm dark:prose-invert max-w-none">
                              {renderMarkdown(failureDiagnosis || 'Click this tab to diagnose why the service failed.')}
                            </div>
                          )}
                        </div>
                        <div className="flex justify-end mt-1 flex-shrink-0">
                          <button
                            className="p-1 rounded text-muted-foreground hover:text-foreground transition-colors"
                            onClick={() => continueInChat(selectedService, failureDiagnosis || '')}
                            title="Continue in Chat"
                          >
                            <MessageCircle className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      </TabsContent>
                    </Tabs>
                  ) : (
                    // Simple view for non-failed services
                    <div className="flex-1 flex flex-col min-h-0">
                      <h4 className="text-sm font-medium flex items-center gap-2 flex-shrink-0">
                        <Sparkles className="h-4 w-4 text-purple-500" />
                        AI Explanation
                      </h4>
                      
                      <div className="p-3 rounded-lg bg-muted/50 flex-1 overflow-y-auto mt-2">
                        {isLoadingExplanation(selectedService.name) ? (
                          <div className="flex flex-col items-center gap-2 text-muted-foreground py-4">
                            <Loader2 className="h-4 w-4 animate-spin" />
                            <span>Generating explanation...</span>
                            {queueCount > 1 && (
                              <span className="text-xs text-muted-foreground/70">
                                {queueCount - 1} other request{queueCount > 2 ? 's' : ''} ahead
                              </span>
                            )}
                          </div>
                        ) : (
                          <div className="prose prose-sm dark:prose-invert max-w-none">
                            {renderMarkdown(llmExplanation || selectedService.data.context_hint || 'No explanation available.')}
                          </div>
                        )}
                      </div>
                      <div className="flex justify-end mt-1 flex-shrink-0">
                        <button
                          className="p-1 rounded text-muted-foreground hover:text-foreground transition-colors"
                          onClick={() => continueInChat(selectedService, llmExplanation || '')}
                          title="Continue in Chat"
                        >
                          <MessageCircle className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    </div>
                  )}
                </div>

                {/* Actions */}
                <div className="flex-shrink-0 pt-2">
                  {actionResult && (
                    <div className={cn(
                      "text-sm mb-2 p-2 rounded",
                      actionResult.success ? "bg-green-500/10 text-green-600" : "bg-red-500/10 text-red-600"
                    )}>
                      {actionResult.message}
                    </div>
                  )}
                  <div className="flex flex-wrap gap-2">
                    {selectedService.status === 'Running' ? (
                      <>
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={!!actionLoading}
                          onClick={(e) => handleAction(selectedService, 'restart', e)}
                        >
                          {actionLoading === 'restart' ? (
                            <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                          ) : (
                            <RotateCcw className="h-4 w-4 mr-2" />
                          )}
                          Restart
                        </Button>
                        <Button
                          variant="destructive"
                          size="sm"
                          disabled={!!actionLoading}
                          onClick={(e) => handleAction(selectedService, 'stop', e)}
                        >
                          {actionLoading === 'stop' ? (
                            <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                          ) : (
                            <Square className="h-4 w-4 mr-2" />
                          )}
                          Stop
                        </Button>
                      </>
                    ) : (
                      <Button
                        variant="default"
                        size="sm"
                        disabled={!!actionLoading}
                        onClick={(e) => handleAction(selectedService, 'start', e)}
                      >
                        {actionLoading === 'start' ? (
                          <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                        ) : (
                          <Play className="h-4 w-4 mr-2" />
                        )}
                        Start
                      </Button>
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}
        </SheetContent>
      </Sheet>

      {/* AI Analysis Panel */}
      <AIAnalysisPanel
        type="service"
        title="Service"
        canAnalyze={services.length > 0}
        buildContext={() => {
          const parts = [`## Service Analysis Context\n`]
          parts.push(`Found ${services.length} services:\n`)
          parts.push(`- Running: ${stats.running}`)
          parts.push(`- Failed: ${stats.failed}`)
          parts.push(`- Docker containers: ${stats.docker}\n`)
          
          // Include failed services
          const failed = services.filter(s => s.severity === 'critical')
          if (failed.length > 0) {
            parts.push(`### Failed Services:`)
            failed.forEach(s => parts.push(`- ${s.name}: ${s.status} (${s.description || 'No description'})`))
          }
          
          return parts.join('\n')
        }}
        researchQuestion="Analyze my service configuration and identify any issues or potential improvements."
      />
    </div>
  )
}
