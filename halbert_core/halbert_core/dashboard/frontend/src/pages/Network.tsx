/**
 * Network Page - View network interfaces and connectivity.
 * 
 * Based on Phase 9 research: docs/Phase9/deep-dives/07-network-deep-dive.md
 */

import { useEffect, useState } from 'react'
import { useScan } from '@/contexts/ScanContext'
import { ConfigEditor } from '@/components/ConfigEditor'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { api } from '@/lib/api'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from '@/components/ui/sheet'
import { 
  Wifi, 
  RefreshCw, 
  Shield,
  Network as NetworkIcon,
  Globe,
  AlertCircle,
  ChevronRight,
  Sparkles,
  Loader2,
  MessageCircle,
  HelpCircle,
  Pencil,
  Check,
  X,
  FileCode,
  Copy,
  CheckCircle2,
} from 'lucide-react'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'
import { AIAnalysisPanel } from '@/components/AIAnalysisPanel'
import { openChat } from '@/components/SendToChat'
import { SystemItemActions } from '@/components/domain'

interface PortDetail {
  port: number
  address: string
  process: string
  name: string
  description: string
  protocol: string
}

interface NetworkItem {
  id: string
  name: string
  title: string
  description: string
  status: string
  severity: string
  data: {
    interface?: string
    type?: string
    operstate?: string
    ipv4?: string
    ipv6?: string
    mac?: string
    tool?: string
    active?: boolean
    ports?: number[]
    port_details?: PortDetail[]
    count?: number
    speed?: string
    mtu?: number
    master?: string  // Bridge master if this is a bridge port
    link_type?: string
    info_kind?: string
    config_path?: string  // Network config file path
  }
}

/**
 * Simple markdown renderer for explanations
 */
function renderMarkdown(text: string): React.ReactNode {
  if (!text) return null
  
  const paragraphs = text.split(/\n\n+/)
  
  return paragraphs.map((paragraph, pIndex) => {
    const trimmed = paragraph.trim()
    
    if (trimmed.startsWith('## ')) {
      return (
        <h3 key={pIndex} className="font-semibold text-sm text-primary mt-4 mb-2 pb-1 border-b border-border first:mt-0">
          {trimmed.slice(3)}
        </h3>
      )
    }
    
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
    
    return (
      <p key={pIndex} className="text-sm leading-relaxed mb-3 last:mb-0 text-foreground/90">
        {formatInlineMarkdown(trimmed)}
      </p>
    )
  })
}

function formatInlineMarkdown(text: string): React.ReactNode {
  const parts: React.ReactNode[] = []
  let keyIndex = 0
  const combinedRegex = /\*\*(.+?)\*\*|\[([^\]]+)\]\(([^)]+)\)/g
  let lastIndex = 0
  let match
  
  while ((match = combinedRegex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index))
    }
    if (match[1]) {
      parts.push(<strong key={keyIndex++} className="font-semibold">{match[1]}</strong>)
    } else if (match[2] && match[3]) {
      parts.push(
        <a key={keyIndex++} href={match[3]} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">
          {match[2]}
        </a>
      )
    }
    lastIndex = match.index + match[0].length
  }
  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex))
  }
  return parts.length > 0 ? parts : text
}

export function Network() {
  const { refreshTrigger } = useScan()
  
  const [network, setNetwork] = useState<NetworkItem[]>([])
  const [loading, setLoading] = useState(true)
  const [scanning, setScanning] = useState(false)
  const [selectedInterface, setSelectedInterface] = useState<NetworkItem | null>(null)
  const [explanation, setExplanation] = useState<string | null>(null)
  const [loadingExplanation, setLoadingExplanation] = useState(false)
  const [editingConfig, setEditingConfig] = useState<string | null>(null)
  
  // Edit classification state
  const [editingInterface, setEditingInterface] = useState<NetworkItem | null>(null)
  const [editType, setEditType] = useState('')
  const [editDescription, setEditDescription] = useState('')
  const [identifying, setIdentifying] = useState(false)
  const [saving, setSaving] = useState(false)
  const [copied, setCopied] = useState<string | null>(null)

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text)
    setCopied(id)
    setTimeout(() => setCopied(null), 2000)
  }

  // Cache helpers for persistent explanations
  const CACHE_KEY = 'halbert_network_explanations'
  
  const getCachedExplanation = (name: string): string | null => {
    try {
      const cache = JSON.parse(localStorage.getItem(CACHE_KEY) || '{}')
      return cache[name] || null
    } catch {
      return null
    }
  }
  
  const setCachedExplanation = (name: string, exp: string) => {
    try {
      const cache = JSON.parse(localStorage.getItem(CACHE_KEY) || '{}')
      cache[name] = exp
      localStorage.setItem(CACHE_KEY, JSON.stringify(cache))
    } catch (e) {
      console.warn('Failed to cache explanation:', e)
    }
  }

  useEffect(() => {
    loadNetwork()
  }, [])

  // Refresh when system-wide scan completes (via context)
  useEffect(() => {
    if (refreshTrigger > 0) {
      loadNetwork()
    }
  }, [refreshTrigger])

  // Also listen for window events (backup mechanism)
  useEffect(() => {
    const handleScanComplete = () => loadNetwork()
    window.addEventListener('halbert-scan-complete', handleScanComplete)
    return () => window.removeEventListener('halbert-scan-complete', handleScanComplete)
  }, [])

  const loadNetwork = async () => {
    try {
      const data = await api.getDiscoveries('network')
      setNetwork(data.discoveries || [])
    } catch (error) {
      console.error('Failed to load network:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleScan = async () => {
    setScanning(true)
    try {
      await api.scanDiscoveries('network')
      await loadNetwork()
    } catch (error) {
      console.error('Scan failed:', error)
    } finally {
      setScanning(false)
    }
  }

  // Separate by type
  const interfaces = network.filter(n => n.name.startsWith('iface-'))
  const firewalls = network.filter(n => n.name.startsWith('firewall-'))
  const ports = network.find(n => n.name === 'listening-ports')

  const getIcon = (item: NetworkItem) => {
    if (item.data.type === 'WiFi') return <Wifi className="h-5 w-5 text-blue-500" />
    if (item.data.type === 'Unknown') return <HelpCircle className="h-5 w-5 text-yellow-500" />
    if (item.data.type?.toLowerCase().includes('vpn') || item.data.type?.toLowerCase().includes('tailscale')) 
      return <Shield className="h-5 w-5 text-purple-500" />
    if (item.name.startsWith('firewall-')) return <Shield className="h-5 w-5 text-green-500" />
    if (item.name === 'listening-ports') return <Globe className="h-5 w-5 text-purple-500" />
    return <NetworkIcon className="h-5 w-5 text-muted-foreground" />
  }

  // Start editing an interface classification
  const startEditClassification = (iface: NetworkItem, e?: React.MouseEvent) => {
    e?.stopPropagation()
    setEditingInterface(iface)
    setEditType(iface.data.type || 'Unknown')
    setEditDescription(iface.description || '')
  }

  // Ask AI to identify an unknown interface
  const identifyInterface = async () => {
    if (!editingInterface) return
    setIdentifying(true)
    
    try {
      const ifaceName = editingInterface.data.interface || editingInterface.name.replace('iface-', '')
      const context = `MAC: ${editingInterface.data.mac || 'unknown'}, State: ${editingInterface.data.operstate || 'unknown'}`
      
      const res = await fetch(`/api/discoveries/learned/identify?name=${encodeURIComponent(ifaceName)}&context=${encodeURIComponent(context)}`, {
        method: 'POST'
      })
      const data = await res.json()
      
      if (data.suggested_type) {
        setEditType(data.suggested_type)
      }
      if (data.suggested_description) {
        setEditDescription(data.suggested_description)
      }
    } catch (error) {
      console.error('Failed to identify interface:', error)
    } finally {
      setIdentifying(false)
    }
  }

  // Save the classification
  const saveClassification = async () => {
    if (!editingInterface || !editType) return
    setSaving(true)
    
    try {
      const ifaceName = editingInterface.data.interface || editingInterface.name.replace('iface-', '')
      
      await fetch('/api/discoveries/learned/classify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: ifaceName,
          type: editType,
          description: editDescription,
          purpose: ''
        })
      })
      
      // Rescan to pick up the new classification
      await handleScan()
      setEditingInterface(null)
    } catch (error) {
      console.error('Failed to save classification:', error)
    } finally {
      setSaving(false)
    }
  }

  const openInterfaceDetail = async (iface: NetworkItem) => {
    setSelectedInterface(iface)
    
    // Check cache first
    const cached = getCachedExplanation(iface.name)
    if (cached) {
      setExplanation(cached)
      setLoadingExplanation(false)
      return
    }
    
    // Generate explanation
    setExplanation(null)
    setLoadingExplanation(true)
    
    try {
      // For now, generate a basic explanation (we can add a backend endpoint later)
      const exp = generateInterfaceExplanation(iface)
      setExplanation(exp)
      setCachedExplanation(iface.name, exp)
    } catch (error) {
      console.error('Failed to generate explanation:', error)
      setExplanation('Unable to generate explanation.')
    } finally {
      setLoadingExplanation(false)
    }
  }

  const generateInterfaceExplanation = (iface: NetworkItem): string => {
    const type = iface.data.type || 'Unknown'
    const isConnected = iface.status === 'Connected' || iface.data.operstate === 'up'
    
    let explanation = `## What this interface does\n\n`
    
    if (type === 'Ethernet') {
      explanation += `This is a wired Ethernet connection. It provides a stable, high-speed connection to your local network or the internet via a physical cable.\n\n`
    } else if (type === 'WiFi') {
      explanation += `This is a wireless network interface. It connects your system to WiFi networks for internet and local network access.\n\n`
    } else if (iface.name.includes('tailscale')) {
      explanation += `This is a **Tailscale** VPN interface. Tailscale is a zero-config VPN that creates a secure, private mesh network (called a "tailnet") between your devices.\n\n`
      explanation += `## Key Features\n\n`
      explanation += `- **WireGuard-based**: Uses modern WireGuard protocol for fast, secure encryption\n`
      explanation += `- **NAT traversal**: Works through firewalls and NAT without port forwarding\n`
      explanation += `- **MagicDNS**: Access devices by name (e.g., \`laptop.tailnet-name.ts.net\`)\n`
      explanation += `- **ACLs**: Control who can access what with access control lists\n`
      explanation += `- **Exit nodes**: Route traffic through another device for privacy\n\n`
      explanation += `## Common Commands\n\n`
      explanation += `- \`tailscale status\` - Show connected devices\n`
      explanation += `- \`tailscale ping <device>\` - Test connectivity\n`
      explanation += `- \`tailscale up --exit-node=<device>\` - Use exit node\n`
      explanation += `- \`tailscale down\` - Disconnect from tailnet\n\n`
    } else if (iface.name.includes('docker') || iface.name.includes('br-')) {
      explanation += `This is a Docker bridge network interface. It enables networking between Docker containers and the host system.\n\n`
    } else if (iface.name.includes('bond')) {
      explanation += `This is a bonded network interface. It combines multiple physical interfaces for redundancy or increased bandwidth.\n\n`
    } else if (iface.name.includes('br0') || iface.name.includes('virbr')) {
      explanation += `This is a network bridge interface. It connects multiple network segments together, often used for virtual machines.\n\n`
    } else {
      explanation += `This is a network interface that enables network connectivity for your system.\n\n`
    }
    
    explanation += `## Technical Details\n\n`
    explanation += `- **Type**: ${type}\n`
    explanation += `- **Status**: ${isConnected ? 'Connected and active' : 'Not connected'}\n`
    if (iface.data.ipv4) explanation += `- **IPv4 Address**: ${iface.data.ipv4}\n`
    if (iface.data.mac) explanation += `- **MAC Address**: ${iface.data.mac}\n`
    if (iface.data.speed) explanation += `- **Speed**: ${iface.data.speed}\n`
    if (iface.data.mtu) explanation += `- **MTU**: ${iface.data.mtu}\n`
    
    explanation += `\n## Learn More\n\n`
    if (iface.name.includes('tailscale')) {
      explanation += `[Tailscale Documentation](https://tailscale.com/kb/)`
    } else {
      explanation += `[Arch Wiki - Network Configuration](https://wiki.archlinux.org/title/Network_configuration)`
    }
    
    return explanation
  }

  const continueInChat = (iface: NetworkItem, context: string) => {
    // Open chat with the AI-generated context as the first message
    openChat({
      title: iface.title || iface.name,
      type: 'network',
      context: context,
      itemId: iface.data.interface || iface.name,
      newConversation: true,
      useSpecialist: false,
      prefillMessage: iface.severity === 'critical' 
        ? 'This interface has issues. What could be wrong?' 
        : 'Tell me more about this network interface.',
    })
  }

  // Get port details for display
  const getPortDetails = (): PortDetail[] => {
    if (!ports?.data.port_details) return []
    return ports.data.port_details
  }

  if (loading) {
    return <div className="flex items-center justify-center h-64">Loading...</div>
  }

  // Show editor instead of normal content when editing
  if (editingConfig) {
    return (
      <ConfigEditor
        filePath={editingConfig}
        onClose={() => setEditingConfig(null)}
      />
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold flex items-center gap-2">
            <NetworkIcon className="h-8 w-8" />
            Network
          </h1>
          <p className="text-muted-foreground">
            Network interfaces, firewall, and connectivity
          </p>
        </div>
        <Button variant="outline" onClick={handleScan} disabled={scanning}>
          <RefreshCw className={cn("h-4 w-4 mr-2", scanning && "animate-spin")} />
          {scanning ? 'Scanning...' : 'Scan'}
        </Button>
      </div>

      {/* Stats */}
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Interfaces</p>
                <p className="text-2xl font-bold">{interfaces.length}</p>
              </div>
              <NetworkIcon className="h-8 w-8 text-muted-foreground" />
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Firewall</p>
                <p className="text-2xl font-bold text-green-500">
                  {firewalls.some(f => f.data.active) ? 'Active' : 'Inactive'}
                </p>
              </div>
              <Shield className="h-8 w-8 text-green-500" />
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Listening Ports</p>
                <p className="text-2xl font-bold">{ports?.data.count || 0}</p>
              </div>
              <Globe className="h-8 w-8 text-purple-500" />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Network Interfaces */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <NetworkIcon className="h-5 w-5" />
            Network Interfaces
          </CardTitle>
        </CardHeader>
        <CardContent>
          {interfaces.length === 0 ? (
            <p className="text-muted-foreground">No interfaces discovered</p>
          ) : (
            <div className="space-y-4">
              {interfaces.map((iface) => (
                <div
                  key={iface.id}
                  className="flex items-center justify-between p-4 rounded-lg border hover:bg-accent/50 cursor-pointer transition-colors"
                  onClick={() => openInterfaceDetail(iface)}
                >
                  <div className="flex items-center gap-4">
                    {getIcon(iface)}
                    <div>
                      <p className="font-medium">{iface.title}</p>
                      <div className="text-sm text-muted-foreground space-y-1">
                        {iface.data.ipv4 && <p>IPv4: {iface.data.ipv4}</p>}
                        {!iface.data.ipv4 && iface.data.master && (
                          <p>Bridge port → <span className="font-medium">{iface.data.master}</span></p>
                        )}
                        {iface.data.mac && <p>MAC: {iface.data.mac}</p>}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <Badge
                      className={cn(
                        iface.severity === 'success' && 'bg-green-500',
                        iface.severity === 'warning' && 'bg-yellow-500',
                        iface.severity === 'info' && 'bg-blue-500',
                      )}
                    >
                      {iface.status}
                    </Badge>
                    {/* Edit button for Unknown/Other types */}
                    {(iface.data.type === 'Unknown' || iface.data.type === 'Other') && (
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-8 w-8 p-0 text-yellow-500 hover:text-yellow-600"
                        title="Classify this interface"
                        onClick={(e) => startEditClassification(iface, e)}
                      >
                        <Pencil className="h-4 w-4" />
                      </Button>
                    )}
                    <SystemItemActions
                      item={{
                        name: iface.title,
                        type: 'network',
                        id: iface.data.interface || iface.name,
                        context: `Interface: ${iface.title}\nType: ${iface.data.type || 'unknown'}\nStatus: ${iface.status}\nIPv4: ${iface.data.ipv4 || 'none'}\nMAC: ${iface.data.mac || 'none'}`,
                      }}
                      size="sm"
                    />
                    <ChevronRight className="h-4 w-4 text-muted-foreground" />
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Firewall */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Shield className="h-5 w-5" />
            Firewall Status
          </CardTitle>
        </CardHeader>
        <CardContent>
          {firewalls.length === 0 ? (
            <div className="flex items-center gap-3 p-4 rounded-lg bg-yellow-500/10 border border-yellow-500/20">
              <AlertCircle className="h-5 w-5 text-yellow-500" />
              <div>
                <p className="font-medium">No firewall detected</p>
                <p className="text-sm text-muted-foreground">
                  Consider enabling UFW or firewalld for security
                </p>
              </div>
            </div>
          ) : (
            <div className="space-y-4">
              {firewalls.map((fw) => (
                <div
                  key={fw.id}
                  className="flex items-center justify-between p-4 rounded-lg border"
                >
                  <div className="flex items-center gap-4">
                    <Shield className={cn(
                      "h-8 w-8",
                      fw.data.active ? "text-green-500" : "text-yellow-500"
                    )} />
                    <div>
                      <p className="font-medium">{fw.title}</p>
                      <p className="text-sm text-muted-foreground">{fw.description}</p>
                    </div>
                  </div>
                  <Badge
                    className={cn(
                      fw.data.active ? 'bg-green-500' : 'bg-yellow-500',
                    )}
                  >
                    {fw.status}
                  </Badge>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Listening Ports */}
      {ports && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Globe className="h-5 w-5" />
              Listening Ports ({ports.data.count || 0})
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="mb-4 text-sm text-muted-foreground">
              Services currently accepting network connections on this system.
            </p>
            <div className="grid gap-2">
              {getPortDetails().map((portInfo) => (
                <div 
                  key={portInfo.port} 
                  className="flex items-center justify-between p-3 rounded-lg border hover:bg-accent/30 transition-colors"
                >
                  <div className="flex items-center gap-3">
                    <Badge 
                      variant="outline" 
                      className={cn(
                        "font-mono text-sm",
                        portInfo.port < 1024 && "border-blue-500 text-blue-600",
                        portInfo.port >= 3000 && portInfo.port < 10000 && "border-green-500 text-green-600"
                      )}
                    >
                      {portInfo.port}
                    </Badge>
                    <div>
                      <p className="font-medium text-sm">{portInfo.name}</p>
                      <p className="text-xs text-muted-foreground">{portInfo.description}</p>
                    </div>
                  </div>
                  <div className="text-right">
                    <span className="text-xs font-mono text-muted-foreground">{portInfo.process}</span>
                    <p className="text-[10px] text-muted-foreground">{portInfo.protocol}</p>
                  </div>
                </div>
              ))}
              {getPortDetails().length === 0 && (ports.data.ports || []).length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {(ports.data.ports || []).map((port) => (
                    <Badge key={port} variant="outline">
                      {port}
                    </Badge>
                  ))}
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Interface Detail Drawer */}
      <Sheet open={!!selectedInterface} onOpenChange={(open) => !open && setSelectedInterface(null)}>
        <SheetContent side="right" className="w-[400px] sm:w-[450px] flex flex-col">
          {selectedInterface && (
            <div className="flex flex-col h-full">
              <SheetHeader className="flex-shrink-0">
                <div className="flex items-center gap-3">
                  <div className="p-2 rounded-lg bg-muted">
                    {getIcon(selectedInterface)}
                  </div>
                  <div>
                    <SheetTitle>{selectedInterface.title}</SheetTitle>
                    <SheetDescription>{selectedInterface.description}</SheetDescription>
                  </div>
                </div>
              </SheetHeader>

              <div className="mt-3 flex-1 flex flex-col overflow-hidden min-h-0">
                {/* Status & Type */}
                <div className="flex items-center gap-3 flex-shrink-0 text-sm">
                  <Badge
                    className={cn(
                      selectedInterface.severity === 'success' && 'bg-green-500',
                      selectedInterface.severity === 'warning' && 'bg-yellow-500',
                      selectedInterface.severity === 'info' && 'bg-blue-500',
                    )}
                  >
                    {selectedInterface.status}
                  </Badge>
                  <span className="text-muted-foreground">•</span>
                  <span className="font-medium">{selectedInterface.data.type || 'Unknown'}</span>
                </div>

                {/* Details */}
                <div className="flex-shrink-0 mt-3 text-sm border-t pt-2">
                  {selectedInterface.data.ipv4 && (
                    <div className="flex justify-between py-1 border-b border-border/50">
                      <span className="text-muted-foreground">IPv4</span>
                      <span className="font-mono font-medium">{selectedInterface.data.ipv4}</span>
                    </div>
                  )}
                  {selectedInterface.data.ipv6 && (
                    <div className="flex justify-between py-1 border-b border-border/50">
                      <span className="text-muted-foreground">IPv6</span>
                      <span className="font-mono font-medium text-xs truncate max-w-[200px]">{selectedInterface.data.ipv6}</span>
                    </div>
                  )}
                  {selectedInterface.data.mac && (
                    <div className="flex justify-between py-1 border-b border-border/50">
                      <span className="text-muted-foreground">MAC</span>
                      <span className="font-mono font-medium">{selectedInterface.data.mac}</span>
                    </div>
                  )}
                  {selectedInterface.data.speed && (
                    <div className="flex justify-between py-1 border-b border-border/50">
                      <span className="text-muted-foreground">Speed</span>
                      <span className="font-medium">{selectedInterface.data.speed}</span>
                    </div>
                  )}
                  {selectedInterface.data.mtu && (
                    <div className="flex justify-between py-1">
                      <span className="text-muted-foreground">MTU</span>
                      <span className="font-medium">{selectedInterface.data.mtu}</span>
                    </div>
                  )}
                </div>
                
                {/* Config File */}
                {selectedInterface.data.config_path && (
                  <div className="p-3 rounded-lg bg-muted/50 border mt-3">
                    <div className="flex items-center gap-2 mb-2">
                      <FileCode className="h-4 w-4 text-muted-foreground" />
                      <span className="text-sm font-medium">Config File</span>
                    </div>
                    <p className="font-mono text-xs break-all">{selectedInterface.data.config_path}</p>
                    <div className="flex gap-2 mt-2">
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 text-xs"
                        onClick={() => copyToClipboard(selectedInterface.data.config_path || '', `config-${selectedInterface.id}`)}
                      >
                        {copied === `config-${selectedInterface.id}` ? (
                          <>
                            <CheckCircle2 className="h-3 w-3 mr-1 text-green-500" />
                            Copied
                          </>
                        ) : (
                          <>
                            <Copy className="h-3 w-3 mr-1" />
                            Copy Path
                          </>
                        )}
                      </Button>
                      <Button
                        variant="default"
                        size="sm"
                        className="h-7 text-xs"
                        onClick={() => {
                          const configPath = selectedInterface.data.config_path || ''
                          setSelectedInterface(null)
                          setEditingConfig(configPath)
                          openChat({
                            title: `Config: ${configPath.split('/').pop()}`,
                            type: 'config',
                          })
                        }}
                      >
                        <Pencil className="h-3 w-3 mr-1" />
                        Edit Config
                      </Button>
                    </div>
                  </div>
                )}

                {/* Listening Ports - Simple pill view */}
                {getPortDetails().length > 0 && (
                  <div className="flex-shrink-0 mt-3 text-sm">
                    <h4 className="text-sm font-medium flex items-center gap-2 mb-2">
                      <Globe className="h-4 w-4 text-purple-500" />
                      Listening Ports
                    </h4>
                    <div className="flex flex-wrap gap-1.5">
                      {getPortDetails().slice(0, 12).map((portInfo) => (
                        <Badge 
                          key={portInfo.port} 
                          variant="outline" 
                          className="text-xs"
                          title={`${portInfo.name}: ${portInfo.description}`}
                        >
                          {portInfo.port}
                        </Badge>
                      ))}
                      {getPortDetails().length > 12 && (
                        <Badge variant="outline" className="text-xs text-muted-foreground">
                          +{getPortDetails().length - 12} more
                        </Badge>
                      )}
                    </div>
                  </div>
                )}

                {/* AI Explanation */}
                <div className="flex-1 flex flex-col min-h-0 mt-3">
                  <h4 className="text-sm font-medium flex items-center gap-2 flex-shrink-0">
                    <Sparkles className="h-4 w-4 text-purple-500" />
                    About This Interface
                  </h4>
                  
                  <div className="p-3 rounded-lg bg-muted/50 flex-1 overflow-y-auto mt-2">
                    {loadingExplanation ? (
                      <div className="flex items-center gap-2 text-muted-foreground">
                        <Loader2 className="h-4 w-4 animate-spin" />
                        <span>Generating explanation...</span>
                      </div>
                    ) : (
                      <div className="prose prose-sm dark:prose-invert max-w-none">
                        {renderMarkdown(explanation || 'No explanation available.')}
                      </div>
                    )}
                  </div>
                  <div className="flex justify-end mt-1 flex-shrink-0">
                    <button
                      className="p-1 rounded text-muted-foreground hover:text-foreground transition-colors"
                      onClick={() => continueInChat(selectedInterface, explanation || '')}
                      title="Continue in Chat"
                    >
                      <MessageCircle className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )}
        </SheetContent>
      </Sheet>

      {/* AI Analysis Panel */}
      <AIAnalysisPanel
        type="network"
        title="Network"
        canAnalyze={interfaces.length > 0}
        buildContext={() => {
          const parts = [`## Network Analysis Context\n`]
          parts.push(`- ${interfaces.length} network interfaces`)
          parts.push(`- Firewall: ${firewalls.some(f => f.data.active) ? 'Active' : 'Inactive'}`)
          parts.push(`- ${ports?.data.count || 0} listening ports\n`)
          
          // Connected interfaces
          const connected = interfaces.filter(i => i.status === 'Connected' || i.data.operstate === 'up')
          if (connected.length > 0) {
            parts.push(`### Connected Interfaces:`)
            connected.forEach(i => {
              parts.push(`- ${i.name}: ${i.data.ipv4 || 'No IP'} (${i.data.type || 'Unknown'})`)
            })
          }
          
          return parts.join('\n')
        }}
        researchQuestion="Analyze my network configuration and identify any connectivity or security issues."
      />

      {/* Edit Classification Dialog */}
      {editingInterface && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div 
            className="absolute inset-0 bg-background/80 backdrop-blur-sm"
            onClick={() => setEditingInterface(null)}
          />
          <div className="relative z-50 w-full max-w-md rounded-lg border bg-card p-6 shadow-lg">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold">Classify Interface</h3>
              <Button 
                variant="ghost" 
                size="sm"
                className="h-8 w-8 p-0"
                onClick={() => setEditingInterface(null)}
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
            
            <div className="space-y-4">
              <div>
                <p className="text-sm text-muted-foreground mb-1">Interface</p>
                <p className="font-medium">{editingInterface.data.interface || editingInterface.name}</p>
                {editingInterface.data.mac && (
                  <p className="text-xs text-muted-foreground">MAC: {editingInterface.data.mac}</p>
                )}
              </div>
              
              <div>
                <label className="text-sm font-medium">Type</label>
                <Input 
                  value={editType}
                  onChange={(e) => setEditType(e.target.value)}
                  placeholder="e.g., Tailscale VPN, Network Bridge"
                  className="mt-1"
                />
              </div>
              
              <div>
                <label className="text-sm font-medium">Description</label>
                <Input 
                  value={editDescription}
                  onChange={(e) => setEditDescription(e.target.value)}
                  placeholder="What this interface does"
                  className="mt-1"
                />
              </div>
              
              <div className="flex items-center gap-2 pt-2">
                <Button
                  variant="outline"
                  onClick={identifyInterface}
                  disabled={identifying}
                  className="flex-1"
                >
                  {identifying ? (
                    <>
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      Identifying...
                    </>
                  ) : (
                    <>
                      <Sparkles className="h-4 w-4 mr-2" />
                      Ask AI
                    </>
                  )}
                </Button>
                <Button
                  onClick={saveClassification}
                  disabled={saving || !editType}
                  className="flex-1"
                >
                  {saving ? (
                    <>
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      Saving...
                    </>
                  ) : (
                    <>
                      <Check className="h-4 w-4 mr-2" />
                      Save
                    </>
                  )}
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
