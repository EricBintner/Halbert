// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * Sharing Page - View network shares, VPN peers, and cloud mounts.
 * 
 * Based on Phase 17 research: docs/Phase17/SHARING-TAB-RESEARCH.md
 */

import { useEffect, useState, useMemo } from 'react'
// ConfigEditor is handled globally by Layout.tsx via halbert:open-config-editor event
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { api } from '@/lib/api'
import { ConfigFileButton, PageHeader } from '@/components/domain'
import { useScanPage, useCopyToClipboard } from '@/hooks'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from '@/components/ui/sheet'
import { 
  RefreshCw, 
  HardDrive,
  Share2,
  Globe,
  Shield,
  Cloud,
  Server,
  ChevronRight,
  Loader2,
  FolderOpen,
  Copy,
  CheckCircle2,
  XCircle,
  FileCode,
  Pencil,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { AIAnalysisPanel } from '@/components/AIAnalysisPanel'
import { openChat } from '@/components/SendToChat'
import { SystemItemActions } from '@/components/domain'

interface SharingItem {
  id: string
  name: string
  title: string
  description: string
  status: string
  severity: string
  // Phase 24: Consolidation fields
  config_path?: string
  group_key?: string
  suppress_display?: boolean
  data: {
    share_type: string
    // NFS/SMB mount
    server?: string
    mount_point?: string
    export_path?: string
    share_name?: string
    options?: string
    nfs_version?: string
    read_write?: boolean
    connected?: boolean
    has_credentials?: boolean
    // NFS/SMB export
    clients?: string
    path?: string
    comment?: string
    guest_ok?: boolean
    read_only?: boolean
    browseable?: boolean
    active?: boolean
    // Tailscale peers
    hostname?: string
    dns_name?: string
    os?: string
    ip?: string
    all_ips?: string[]
    online?: boolean
    is_exit_node?: boolean
    peer_id?: string
    // Tailscale Drive
    user?: string
    // WireGuard
    interface?: string
    public_key?: string
    endpoint?: string
    allowed_ips?: string
    latest_handshake?: string
    transfer?: string
    // Cloud
    remote?: string
    source?: string
    label?: string
    // Config file
    config_path?: string
  }
}

// Group sharing items by type
function groupByShareType(items: SharingItem[]) {
  const groups: Record<string, SharingItem[]> = {
    'nfs-mount': [],
    'smb-mount': [],
    'nfs-export': [],
    'smb-export': [],
    'taildrive': [],
    'tailscale-peer': [],
    'wireguard-peer': [],
    'cloud': [],
  }
  
  for (const item of items) {
    const type = item.data.share_type
    if (type === 'nfs-mount') groups['nfs-mount'].push(item)
    else if (type === 'smb-mount') groups['smb-mount'].push(item)
    else if (type === 'nfs-export') groups['nfs-export'].push(item)
    else if (type === 'smb-export') groups['smb-export'].push(item)
    else if (type === 'taildrive' || type === 'taildrive-mount') groups['taildrive'].push(item)
    else if (type === 'tailscale-peer') groups['tailscale-peer'].push(item)
    else if (type === 'wireguard-peer') groups['wireguard-peer'].push(item)
    else groups['cloud'].push(item)
  }
  
  return groups
}

// Phase 24: Group exports by their config file for fused display
interface ExportGroup {
  key: string
  configPath: string
  type: 'nfs' | 'samba'
  items: SharingItem[]
}

function groupExportsByConfig(items: SharingItem[]): ExportGroup[] {
  const groups = new Map<string, ExportGroup>()
  
  for (const item of items) {
    const configPath = item.config_path || item.data.config_path
    if (!configPath) {
      // No config path - treat as individual
      groups.set(item.id, {
        key: item.id,
        configPath: '',
        type: item.data.share_type === 'nfs-export' ? 'nfs' : 'samba',
        items: [item],
      })
      continue
    }
    
    const key = `${item.data.share_type}:${configPath}`
    if (!groups.has(key)) {
      groups.set(key, {
        key,
        configPath,
        type: item.data.share_type === 'nfs-export' ? 'nfs' : 'samba',
        items: [],
      })
    }
    groups.get(key)!.items.push(item)
  }
  
  return Array.from(groups.values())
}

// Phase 24: Group WireGuard peers by interface config
interface WireGuardGroup {
  key: string
  interfaceName: string
  configPath: string | null
  peers: SharingItem[]
}

function groupWireGuardPeers(items: SharingItem[]): WireGuardGroup[] {
  const groups = new Map<string, WireGuardGroup>()
  
  for (const item of items) {
    const interfaceName = item.data.interface || 'unknown'
    const configPath = item.config_path || null
    const key = `wg:${interfaceName}`
    
    if (!groups.has(key)) {
      groups.set(key, {
        key,
        interfaceName,
        configPath,
        peers: [],
      })
    }
    groups.get(key)!.peers.push(item)
  }
  
  return Array.from(groups.values())
}

export function Sharing() {
  const [sharing, setSharing] = useState<SharingItem[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedItem, setSelectedItem] = useState<SharingItem | null>(null)
  // ConfigEditor state removed - now handled globally by Layout.tsx

  useEffect(() => {
    loadSharing()
  }, [])

  const loadSharing = async () => {
    try {
      const data = await api.getDiscoveries('sharing')
      setSharing(data.discoveries || [])
    } catch (error) {
      console.error('Failed to load sharing:', error)
    } finally {
      setLoading(false)
    }
  }

  const { scanning, handleScan } = useScanPage({
    scanType: 'sharing',
    onScanComplete: loadSharing,
  })

  const { copiedId: copied, copy: copyToClipboard } = useCopyToClipboard()

  const groups = groupByShareType(sharing)
  
  // Phase 24: Group exports by config file for fused display
  const groupedExports = useMemo(() => {
    const allExports = [...groups['nfs-export'], ...groups['smb-export']]
    return groupExportsByConfig(allExports)
  }, [groups])
  
  // Phase 24: Group WireGuard peers by interface
  const groupedWireGuard = useMemo(() => {
    return groupWireGuardPeers(groups['wireguard-peer'])
  }, [groups])
  
  // Count totals for summary
  const mountCount = groups['nfs-mount'].length + groups['smb-mount'].length
  const exportCount = groups['nfs-export'].length + groups['smb-export'].length
  const vpnPeerCount = groups['tailscale-peer'].length + groups['wireguard-peer'].length
  const cloudCount = groups['cloud'].length

  const getIcon = (item: SharingItem) => {
    const type = item.data.share_type
    if (type === 'nfs-mount' || type === 'smb-mount') 
      return <HardDrive className="h-5 w-5 text-info" />
    if (type === 'nfs-export' || type === 'smb-export') 
      return <Share2 className="h-5 w-5 text-success" />
    if (type === 'tailscale-peer') 
      return <Globe className="h-5 w-5 text-purple-500" />
    if (type === 'wireguard-peer') 
      return <Shield className="h-5 w-5 text-warning" />
    return <Cloud className="h-5 w-5 text-info" />
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  // ConfigEditor is now handled globally by Layout.tsx

  return (
    <div className="space-y-6">
      {/* Header */}
      <PageHeader
        icon={<Share2 className="h-8 w-8" />}
        title="Sharing"
        description="Network shares, VPN peers, and cloud mounts"
        scanning={scanning}
        onScan={handleScan}
      />

      {/* Summary Cards */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-4">
              <div className="p-3 bg-info/10 rounded-lg">
                <HardDrive className="h-6 w-6 text-info" />
              </div>
              <div>
                <p className="text-2xl font-bold">{mountCount}</p>
                <p className="text-sm text-muted-foreground">Network Mounts</p>
              </div>
            </div>
          </CardContent>
        </Card>
        
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-4">
              <div className="p-3 bg-success/10 rounded-lg">
                <Share2 className="h-6 w-6 text-success" />
              </div>
              <div>
                <p className="text-2xl font-bold">{exportCount}</p>
                <p className="text-sm text-muted-foreground">Exported Shares</p>
              </div>
            </div>
          </CardContent>
        </Card>
        
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-4">
              <div className="p-3 bg-purple-500/10 rounded-lg">
                <Globe className="h-6 w-6 text-purple-500" />
              </div>
              <div>
                <p className="text-2xl font-bold">{vpnPeerCount}</p>
                <p className="text-sm text-muted-foreground">VPN Peers</p>
              </div>
            </div>
          </CardContent>
        </Card>
        
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-4">
              <div className="p-3 bg-info/10 rounded-lg">
                <Cloud className="h-6 w-6 text-info" />
              </div>
              <div>
                <p className="text-2xl font-bold">{cloudCount}</p>
                <p className="text-sm text-muted-foreground">Cloud Mounts</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Network Mounts */}
      {(groups['nfs-mount'].length > 0 || groups['smb-mount'].length > 0) && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <HardDrive className="h-5 w-5" />
              Network Mounts
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {[...groups['nfs-mount'], ...groups['smb-mount']].map((item) => (
                <div
                  key={item.id}
                  className="flex items-center justify-between p-4 rounded-lg border hover:bg-accent/50 cursor-pointer transition-colors"
                  onClick={() => setSelectedItem(item)}
                >
                  <div className="flex items-center gap-4">
                    {getIcon(item)}
                    <div>
                      <p className="font-medium">{item.data.mount_point}</p>
                      <p className="text-sm text-muted-foreground">
                        {item.data.share_type === 'nfs-mount' ? 'NFS' : 'SMB'} from {item.data.server}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge
                      className={cn(
                        item.data.connected && 'bg-success',
                        !item.data.connected && 'bg-warning',
                      )}
                    >
                      {item.status}
                    </Badge>
                    <SystemItemActions
                      item={{
                        name: item.data.mount_point || item.title,
                        type: 'sharing',
                        id: `sharing/${item.id}`,
                        description: item.description,
                        context: `${item.data.share_type === 'nfs-mount' ? 'NFS' : 'SMB'} mount from ${item.data.server}\nMount: ${item.data.mount_point}`,
                        data: item.data,
                      }}
                      variant="icon"
                      size="sm"
                      showChat={false}
                    />
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 w-7 p-0"
                      title="Copy path"
                      onClick={(e) => {
                        e.stopPropagation()
                        copyToClipboard(item.data.mount_point || '', item.id)
                      }}
                    >
                      {copied === item.id ? (
                        <CheckCircle2 className="h-4 w-4 text-success" />
                      ) : (
                        <Copy className="h-4 w-4" />
                      )}
                    </Button>
                    <ChevronRight className="h-4 w-4 text-muted-foreground" />
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Exported Shares - Phase 24: Fused by config file */}
      {groupedExports.length > 0 && (
        <div className="space-y-4">
          {groupedExports.map((group) => (
            <Card key={group.key} className="overflow-hidden">
              {/* Fused Header with Config Button and AI Actions */}
              <div className="flex items-center justify-between p-4 bg-muted/50 border-b">
                <div className="flex items-center gap-2">
                  <Share2 className="h-5 w-5 text-success" />
                  <span className="font-semibold">
                    {group.type === 'nfs' ? 'NFS Exports' : 'Samba Shares'}
                  </span>
                  {group.items.length > 1 && (
                    <Badge variant="outline" className="text-xs">
                      {group.items.length} shares
                    </Badge>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  {/* AI @ mention for the whole config group */}
                  <SystemItemActions
                    item={{
                      name: group.type === 'nfs' ? 'NFS Exports' : 'Samba Shares',
                      type: 'sharing',
                      id: `sharing/${group.key}`,
                      description: `${group.items.length} ${group.type === 'nfs' ? 'NFS exports' : 'Samba shares'}${group.configPath ? ` in ${group.configPath}` : ''}`,
                      context: `${group.type === 'nfs' ? 'NFS Exports' : 'Samba Shares'}:\n${group.items.map(i => `- ${i.data.share_name || i.title}: ${i.data.path}`).join('\n')}${group.configPath ? `\n\nConfig: ${group.configPath}` : ''}`,
                      data: { shares: group.items.map(i => i.data), config_path: group.configPath },
                    }}
                    variant="icon"
                    size="sm"
                    showChat={false}
                  />
                  {group.configPath && (
                    <ConfigFileButton 
                      path={group.configPath} 
                      variant="full"
                      size="sm"
                    />
                  )}
                </div>
              </div>
              
              <CardContent className="p-0">
                {group.items.map((item, idx) => (
                  <div
                    key={item.id}
                    className={cn(
                      "flex items-center justify-between p-4 hover:bg-accent/50 cursor-pointer transition-colors",
                      idx < group.items.length - 1 && "border-b border-dashed"
                    )}
                    onClick={() => setSelectedItem(item)}
                  >
                    <div className="flex items-center gap-4">
                      <div className="p-2 rounded-full bg-success/10">
                        <FolderOpen className="h-4 w-4 text-success" />
                      </div>
                      <div>
                        <p className="font-medium">{item.data.share_name || item.title.replace('Share: ', '')}</p>
                        <p className="text-sm text-muted-foreground">
                          {item.data.path}
                          {item.data.comment && ` — ${item.data.comment}`}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      {item.data.guest_ok && (
                        <Badge variant="outline" className="text-warning border-warning">
                          Guest OK
                        </Badge>
                      )}
                      {item.data.read_only && (
                        <Badge variant="outline" className="text-slate-500">
                          Read Only
                        </Badge>
                      )}
                      <Badge
                        className={cn(
                          item.data.active && 'bg-success',
                          !item.data.active && 'bg-slate-500',
                        )}
                      >
                        {item.status}
                      </Badge>
                      <SystemItemActions
                        item={{
                          name: item.data.share_name || item.title,
                          type: 'sharing',
                          id: `sharing/${item.id}`,
                          description: item.description,
                          context: `Share: ${item.data.share_name || item.title}\nPath: ${item.data.path}${item.data.comment ? `\nComment: ${item.data.comment}` : ''}`,
                          data: item.data,
                        }}
                        variant="icon"
                        size="sm"
                        showChat={false}
                      />
                      <ChevronRight className="h-4 w-4 text-muted-foreground" />
                    </div>
                  </div>
                ))}
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Tailscale Drives */}
      {groups['taildrive'].length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Share2 className="h-5 w-5 text-purple-500" />
              Tailscale Drives
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {groups['taildrive'].map((item) => (
                <div
                  key={item.id}
                  className="flex items-center justify-between p-4 rounded-lg border hover:bg-accent/50 cursor-pointer transition-colors"
                  onClick={() => setSelectedItem(item)}
                >
                  <div className="flex items-center gap-4">
                    <div className="p-2 rounded-full bg-purple-500/10">
                      <Share2 className="h-5 w-5 text-purple-500" />
                    </div>
                    <div>
                      <p className="font-medium">{item.title}</p>
                      <p className="text-sm text-muted-foreground">
                        {item.data.path}
                        {item.data.user && <span className="ml-2 text-xs">as {item.data.user}</span>}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge
                      className={cn(
                        item.data.active && 'bg-success',
                        !item.data.active && 'bg-warning',
                      )}
                    >
                      {item.status}
                    </Badge>
                    <SystemItemActions
                      item={{
                        name: item.title,
                        type: 'sharing',
                        id: `sharing/${item.id}`,
                        description: item.description,
                        context: `Tailscale Drive: ${item.title}\nPath: ${item.data.path}${item.data.user ? `\nUser: ${item.data.user}` : ''}`,
                        data: item.data,
                      }}
                      variant="icon"
                      size="sm"
                      showChat={false}
                    />
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 w-7 p-0"
                      title="Copy path"
                      onClick={(e) => {
                        e.stopPropagation()
                        copyToClipboard(item.data.path || '', item.id)
                      }}
                    >
                      {copied === item.id ? (
                        <CheckCircle2 className="h-4 w-4 text-success" />
                      ) : (
                        <Copy className="h-4 w-4" />
                      )}
                    </Button>
                    <ChevronRight className="h-4 w-4 text-muted-foreground" />
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Tailscale Peers */}
      {groups['tailscale-peer'].length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Globe className="h-5 w-5" />
              Tailscale Network
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {groups['tailscale-peer'].map((item) => (
                <div
                  key={item.id}
                  className="flex items-center justify-between p-4 rounded-lg border hover:bg-accent/50 cursor-pointer transition-colors"
                  onClick={() => setSelectedItem(item)}
                >
                  <div className="flex items-center gap-4">
                    <div className={cn(
                      "p-2 rounded-full",
                      item.data.online ? "bg-success/10" : "bg-slate-500/10"
                    )}>
                      {item.data.os?.toLowerCase().includes('linux') ? (
                        <Server className="h-5 w-5" />
                      ) : item.data.os?.toLowerCase().includes('windows') ? (
                        <Server className="h-5 w-5" />
                      ) : (
                        <Globe className="h-5 w-5" />
                      )}
                    </div>
                    <div>
                      <p className="font-medium">{item.data.hostname}</p>
                      <p className="text-sm text-muted-foreground">
                        {item.data.ip} {item.data.os && `(${item.data.os})`}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {item.data.is_exit_node && (
                      <Badge variant="outline">Exit Node</Badge>
                    )}
                    <div className="flex items-center gap-2">
                      {item.data.online ? (
                        <CheckCircle2 className="h-4 w-4 text-success" />
                      ) : (
                        <XCircle className="h-4 w-4 text-slate-400" />
                      )}
                      <span className={cn(
                        "text-sm",
                        item.data.online ? "text-success" : "text-muted-foreground"
                      )}>
                        {item.status}
                      </span>
                    </div>
                    <SystemItemActions
                      item={{
                        name: item.data.hostname || item.title,
                        type: 'sharing',
                        id: `sharing/${item.id}`,
                        description: item.description,
                        context: `Tailscale Peer: ${item.data.hostname}\nIP: ${item.data.ip}${item.data.os ? `\nOS: ${item.data.os}` : ''}${item.data.dns_name ? `\nDNS: ${item.data.dns_name}` : ''}\nStatus: ${item.data.online ? 'Online' : 'Offline'}`,
                        data: item.data,
                      }}
                      variant="icon"
                      size="sm"
                      showChat={false}
                    />
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 w-7 p-0"
                      title="Copy IP"
                      onClick={(e) => {
                        e.stopPropagation()
                        copyToClipboard(item.data.ip || '', item.id)
                      }}
                    >
                      {copied === item.id ? (
                        <CheckCircle2 className="h-4 w-4 text-success" />
                      ) : (
                        <Copy className="h-4 w-4" />
                      )}
                    </Button>
                    <ChevronRight className="h-4 w-4 text-muted-foreground" />
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Phase 24: WireGuard Peers - Grouped by Interface */}
      {groups['wireguard-peer'].length > 0 && (
        <div className="space-y-4">
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <Shield className="h-5 w-5" />
            WireGuard Peers ({groups['wireguard-peer'].length})
          </h2>
          {groupedWireGuard.map((group) => (
            <Card key={group.key} className="overflow-hidden">
              {/* Fused Header with Config Button and AI Actions */}
              <div className="flex items-center justify-between p-4 bg-muted/50 border-b">
                <div className="flex items-center gap-2">
                  <Shield className="h-5 w-5 text-warning" />
                  <span className="font-semibold font-mono">{group.interfaceName}</span>
                  <Badge variant="outline" className="text-xs">
                    {group.peers.filter(p => p.data.online).length}/{group.peers.length} connected
                  </Badge>
                </div>
                <div className="flex items-center gap-2">
                  {/* AI @ mention for the whole WireGuard interface */}
                  <SystemItemActions
                    item={{
                      name: `WireGuard ${group.interfaceName}`,
                      type: 'sharing',
                      id: `sharing/wireguard-${group.interfaceName}`,
                      description: `WireGuard interface ${group.interfaceName} with ${group.peers.length} peers`,
                      context: `WireGuard Interface: ${group.interfaceName}\nPeers: ${group.peers.length} (${group.peers.filter(p => p.data.online).length} connected)\n${group.peers.map(p => `- ${p.data.public_key?.slice(0, 16)}... → ${p.data.allowed_ips || 'N/A'} (${p.data.online ? 'connected' : 'offline'})`).join('\n')}${group.configPath ? `\n\nConfig: ${group.configPath}` : ''}`,
                      data: { interface: group.interfaceName, peers: group.peers.map(p => p.data), config_path: group.configPath },
                    }}
                    variant="icon"
                    size="sm"
                    showChat={false}
                  />
                  {group.configPath && (
                    <ConfigFileButton 
                      path={group.configPath} 
                      variant="full"
                      size="sm"
                    />
                  )}
                </div>
              </div>
              
              <CardContent className="p-0">
                {group.peers.map((item, idx) => (
                  <div
                    key={item.id}
                    className={cn(
                      "flex items-center justify-between p-4 hover:bg-accent/50 cursor-pointer transition-colors",
                      idx < group.peers.length - 1 && "border-b border-dashed"
                    )}
                    onClick={() => setSelectedItem(item)}
                  >
                    <div className="flex items-center gap-4">
                      <div className={cn(
                        "p-2 rounded-full",
                        item.data.online ? "bg-success/10" : "bg-slate-500/10"
                      )}>
                        <Shield className={cn(
                          "h-4 w-4",
                          item.data.online ? "text-success" : "text-slate-500"
                        )} />
                      </div>
                      <div>
                        <p className="font-medium font-mono text-sm">
                          {item.data.public_key?.slice(0, 16)}...
                        </p>
                        <p className="text-sm text-muted-foreground">
                          {item.data.endpoint || 'No endpoint'} • {item.data.allowed_ips || 'No allowed IPs'}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge
                        className={cn(
                          "text-xs",
                          item.data.online && 'bg-success',
                          !item.data.online && 'bg-slate-500',
                        )}
                      >
                        {item.status}
                      </Badge>
                      {item.data.latest_handshake && item.data.latest_handshake !== 'Never' && (
                        <span className="text-xs text-muted-foreground">
                          {item.data.latest_handshake}
                        </span>
                      )}
                      <SystemItemActions
                        item={{
                          name: `WireGuard Peer ${item.data.public_key?.slice(0, 8)}...`,
                          type: 'sharing',
                          id: `sharing/${item.id}`,
                          description: item.description,
                          context: `WireGuard Peer\nPublic Key: ${item.data.public_key}\nEndpoint: ${item.data.endpoint || 'N/A'}\nAllowed IPs: ${item.data.allowed_ips || 'N/A'}\nStatus: ${item.data.online ? 'Connected' : 'Offline'}`,
                          data: item.data,
                        }}
                        variant="icon"
                        size="sm"
                        showChat={false}
                      />
                      <ChevronRight className="h-4 w-4 text-muted-foreground" />
                    </div>
                  </div>
                ))}
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Cloud Mounts */}
      {groups['cloud'].length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Cloud className="h-5 w-5" />
              Cloud Mounts
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {groups['cloud'].map((item) => (
                <div
                  key={item.id}
                  className="flex items-center justify-between p-4 rounded-lg border hover:bg-accent/50 cursor-pointer transition-colors"
                  onClick={() => setSelectedItem(item)}
                >
                  <div className="flex items-center gap-4">
                    {getIcon(item)}
                    <div>
                      <p className="font-medium">{item.data.mount_point}</p>
                      <p className="text-sm text-muted-foreground">
                        {item.data.label || item.data.remote || 'Cloud mount'}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge
                      className={cn(
                        item.data.connected && 'bg-success',
                        !item.data.connected && 'bg-warning',
                      )}
                    >
                      {item.status}
                    </Badge>
                    <SystemItemActions
                      item={{
                        name: item.data.mount_point || item.title,
                        type: 'sharing',
                        id: `sharing/${item.id}`,
                        description: item.description,
                        context: `Cloud Mount: ${item.data.mount_point}\nRemote: ${item.data.remote || item.data.label || 'N/A'}\nStatus: ${item.data.connected ? 'Connected' : 'Disconnected'}`,
                        data: item.data,
                      }}
                      variant="icon"
                      size="sm"
                      showChat={false}
                    />
                    <ChevronRight className="h-4 w-4 text-muted-foreground" />
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Empty State */}
      {sharing.length === 0 && (
        <Card>
          <CardContent className="py-12">
            <div className="text-center space-y-4">
              <div className="mx-auto w-16 h-16 bg-muted rounded-full flex items-center justify-center">
                <Share2 className="h-8 w-8 text-muted-foreground" />
              </div>
              <div>
                <h3 className="text-lg font-semibold">No Shares Found</h3>
                <p className="text-muted-foreground">
                  No NFS/SMB mounts, VPN peers, or cloud mounts detected.
                </p>
              </div>
              <Button onClick={handleScan} variant="outline">
                <RefreshCw className="h-4 w-4 mr-2" />
                Scan for Shares
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Detail Sheet */}
      <Sheet open={!!selectedItem} onOpenChange={() => setSelectedItem(null)}>
        <SheetContent className="w-[400px] sm:w-[540px]">
          <SheetHeader>
            <SheetTitle className="flex items-center gap-2">
              {selectedItem && getIcon(selectedItem)}
              {selectedItem?.title}
            </SheetTitle>
            <SheetDescription>
              {selectedItem?.description}
            </SheetDescription>
          </SheetHeader>
          
          {selectedItem && (
            <div className="mt-6 space-y-4">
              {/* Status */}
              <div className="flex items-center justify-between">
                <span className="text-sm text-muted-foreground">Status</span>
                <Badge className={cn(
                  selectedItem.severity === 'success' && 'bg-success',
                  selectedItem.severity === 'warning' && 'bg-warning',
                  selectedItem.severity === 'info' && 'bg-info',
                )}>
                  {selectedItem.status}
                </Badge>
              </div>

              {/* Dynamic fields based on type */}
              {selectedItem.data.server && (
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">Server</span>
                  <span className="font-mono text-sm">{selectedItem.data.server}</span>
                </div>
              )}
              
              {selectedItem.data.mount_point && (
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">Mount Point</span>
                  <span className="font-mono text-sm">{selectedItem.data.mount_point}</span>
                </div>
              )}
              
              {selectedItem.data.export_path && (
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">Export Path</span>
                  <span className="font-mono text-sm">{selectedItem.data.export_path}</span>
                </div>
              )}
              
              {selectedItem.data.path && (
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">Path</span>
                  <span className="font-mono text-sm">{selectedItem.data.path}</span>
                </div>
              )}
              
              {selectedItem.data.ip && (
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">IP Address</span>
                  <span className="font-mono text-sm">{selectedItem.data.ip}</span>
                </div>
              )}
              
              {selectedItem.data.dns_name && (
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">DNS Name</span>
                  <span className="font-mono text-sm">{selectedItem.data.dns_name}</span>
                </div>
              )}
              
              {selectedItem.data.os && (
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">OS</span>
                  <span className="text-sm">{selectedItem.data.os}</span>
                </div>
              )}
              
              {selectedItem.data.options && (
                <div className="space-y-1">
                  <span className="text-sm text-muted-foreground">Options</span>
                  <p className="font-mono text-xs bg-muted p-2 rounded break-all">
                    {selectedItem.data.options}
                  </p>
                </div>
              )}
              
              {/* Config File */}
              {selectedItem.data.config_path && (
                <div className="p-3 rounded-lg bg-muted/50 border">
                  <div className="flex items-center gap-2 mb-2">
                    <FileCode className="h-4 w-4 text-muted-foreground" />
                    <span className="text-sm font-medium">Config File</span>
                  </div>
                  <p className="font-mono text-xs break-all">{selectedItem.data.config_path}</p>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="mt-2 h-7 text-xs"
                    onClick={() => copyToClipboard(selectedItem.data.config_path || '', `config-${selectedItem.id}`)}
                  >
                    {copied === `config-${selectedItem.id}` ? (
                      <>
                        <CheckCircle2 className="h-3 w-3 mr-1 text-success" />
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
                    className="mt-2 ml-2 h-7 text-xs"
                    onClick={() => {
                      const configPath = selectedItem.data.config_path || ''
                      const fileName = configPath.split('/').pop() || 'config'
                      const itemName = selectedItem.title
                      setSelectedItem(null) // Close the drawer
                      // Open chat with configPath so the Edit Config button appears in chat
                      openChat({
                        title: `Config: ${fileName}`,
                        type: 'config',
                        context: `Editing **${itemName}** sharing configuration.\n\nFile: \`${configPath}\`\n\nI can help you modify this config file. Just tell me what changes you'd like to make.`,
                        configPath: configPath,
                        newConversation: true,
                      })
                      // Also open the config editor
                      window.dispatchEvent(new CustomEvent('halbert:open-config-editor', {
                        detail: { filePath: configPath }
                      }))
                    }}
                  >
                    <Pencil className="h-3 w-3 mr-1" />
                    Edit Config
                  </Button>
                </div>
              )}

              {/* Actions */}
              <div className="pt-4 space-y-2">
                {selectedItem.data.mount_point && (
                  <Button 
                    className="w-full" 
                    variant="outline"
                    onClick={() => {
                      // Open in file manager (best effort)
                      window.open(`file://${selectedItem.data.mount_point}`, '_blank')
                    }}
                  >
                    <FolderOpen className="h-4 w-4 mr-2" />
                    Open Location
                  </Button>
                )}
                
                <SystemItemActions
                  item={{
                    name: selectedItem.title,
                    type: 'sharing',
                    id: `sharing/${selectedItem.id}`,
                    description: selectedItem.description,
                    status: selectedItem.status,
                    data: selectedItem.data,
                    context: JSON.stringify(selectedItem.data, null, 2),
                  }}
                  variant="full"
                  className="w-full justify-center"
                />
              </div>
            </div>
          )}
        </SheetContent>
      </Sheet>

      {/* AI Analysis */}
      <AIAnalysisPanel
        type="sharing"
        title="Sharing Analysis"
        buildContext={() => {
          const parts = [`### Sharing Overview\n`]
          parts.push(`- ${mountCount} network mounts (NFS/SMB)`)
          parts.push(`- ${exportCount} exported shares`)
          parts.push(`- ${vpnPeerCount} VPN peers`)
          parts.push(`- ${cloudCount} cloud mounts\n`)
          
          if (groups['tailscale-peer'].length > 0) {
            parts.push(`### Tailscale Peers:`)
            groups['tailscale-peer'].forEach(p => {
              parts.push(`- ${p.data.hostname}: ${p.data.ip} (${p.data.online ? 'online' : 'offline'})`)
            })
          }
          
          if (groups['nfs-mount'].length > 0 || groups['smb-mount'].length > 0) {
            parts.push(`\n### Network Mounts:`)
            ;[...groups['nfs-mount'], ...groups['smb-mount']].forEach(m => {
              parts.push(`- ${m.data.mount_point}: ${m.data.server} (${m.data.connected ? 'connected' : 'disconnected'})`)
            })
          }
          
          return parts.join('\n')
        }}
        researchQuestion="Analyze my network sharing setup. Are there security concerns? Performance improvements?"
      />
    </div>
  )
}
