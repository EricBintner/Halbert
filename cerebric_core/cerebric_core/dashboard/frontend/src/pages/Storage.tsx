/**
 * Storage Page - View disk and filesystem health.
 * 
 * Based on Phase 9 research: 
 * - docs/Phase9/deep-dives/04-filesystem-health.md
 * - docs/Phase9/deep-dives/09-storage-systems.md
 * - docs/Phase9/deep-dives/STORAGE-UI-REDESIGN.md
 * 
 * Design Principles:
 * 1. Semantic-first: Show purpose ("Home Array") before technical details
 * 2. Group by physical disk: Boot + Root on same disk = one card
 * 3. Show usage bars when collapsed: See capacity at a glance
 * 4. Show physical disks when expanded: Progressive disclosure
 * 5. Aggressive deduplication: Merge btrfs subvolume mounts
 */

import React, { useEffect, useState, useMemo, useRef, useContext, useCallback } from 'react'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import { Collapsible } from '@/components/ui/collapsible'
import { api } from '@/lib/api'
import { 
  HardDrive, 
  RefreshCw, 
  Folder,
  AlertCircle,
  CheckCircle,
  Database,
  Pencil,
  ChevronDown,
  ChevronRight,
  FolderPlus,
  HardDriveDownload,
  Eye,
  EyeOff,
  Terminal,
  Copy,
  Check,
} from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'
import { AIAnalysisPanel } from '@/components/AIAnalysisPanel'
import { openChat } from '@/components/SendToChat'

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

interface ArrayMember {
  device: string
  size: string
  role: string  // Primary role: "data", "spare", "cache", "foreground", "promote", "metadata"
  roles?: string[]  // All roles this device serves (bcachefs can have multiple)
  label?: string  // bcachefs device label e.g. "nvme.u2_01"
  tier?: string   // tier group e.g. "nvme", "hdd"
}

interface StorageItem {
  id: string
  name: string
  title: string
  description: string
  status: string
  severity: string
  data: {
    device?: string
    source?: string          // Legacy: same as device
    parent_disk?: string     // Parent physical disk (e.g., /dev/nvme0n1 for /dev/nvme0n1p2)
    size?: string
    model?: string
    type?: string
    transport?: string
    smart_status?: string
    serial?: string          // Drive serial number
    wwn?: string             // World Wide Name
    fstype?: string
    used?: string
    available?: string
    percent?: number
    mountpoint?: string
    // Multi-disk array info
    array_type?: string      // "btrfs", "bcachefs", "zfs", "mdadm", or null
    array_profile?: string   // "single", "raid1", "raid5", "raid6", "tiered", etc.
    data_profile?: string    // btrfs/bcachefs: data redundancy profile
    metadata_profile?: string // btrfs/bcachefs: metadata redundancy profile
    array_members?: ArrayMember[]  // List of member devices
    array_tiers?: Record<string, string[]>  // bcachefs: tier name -> device list
    tier_targets?: {         // bcachefs/zfs tier target configuration
      foreground?: string    // tier for new writes (cache)
      background?: string    // tier for aged data (storage)
      metadata?: string      // tier for metadata
      promote?: string       // tier for promoted hot data
    }
    // MD RAID specific
    raid_level?: string
    member_count?: number
    members?: string[]  // Component device paths for MD arrays
    // Unmounted volume specific
    uuid?: string
    label?: string
    devices?: string[]  // List of devices in unmounted pool
    device_count?: number
    mounted?: boolean
  }
}

/** A single filesystem after deduplication */
interface FilesystemEntry {
  id: string
  mountpoint: string        // Canonical mount: "/" not "/btrfs/root"
  label: string             // User-friendly: "Root" or "Home"
  fstype: string
  size: string
  used: string
  percent: number
  severity: string
}

/** A group of filesystems that share the same physical disk(s) */
interface DiskGroup {
  id: string
  semanticName: string      // "System Disk" or "Home Array"
  filesystems: FilesystemEntry[]
  disks: StorageItem[]
  diskCount: number
  totalSize: string
  hasWarnings: boolean
  // Array info (for multi-disk filesystems)
  arrayType?: string | null   // "btrfs", "bcachefs", "zfs", "mdadm", or null
  arrayProfile?: string | null // "single", "raid1", "raid5", etc.
  dataProfile?: string | null  // btrfs: data profile (raid0, dup, single, etc.)
  metadataProfile?: string | null // btrfs: metadata profile (dup, raid1, etc.)
  arrayTiers?: Record<string, string[]>  // tier name -> device list (bcachefs)
  arrayMembers?: ArrayMember[]  // Full member info with labels/tiers
}

// ─────────────────────────────────────────────────────────────────────────────
// Custom Names - User can rename volumes
// ─────────────────────────────────────────────────────────────────────────────

const STORAGE_NAMES_KEY = 'cerebric-storage-custom-names'

/** Load custom names from localStorage */
function loadCustomNames(): Record<string, string> {
  try {
    const stored = localStorage.getItem(STORAGE_NAMES_KEY)
    return stored ? JSON.parse(stored) : {}
  } catch {
    return {}
  }
}

/** Save custom names to localStorage */
function saveCustomNames(names: Record<string, string>) {
  try {
    localStorage.setItem(STORAGE_NAMES_KEY, JSON.stringify(names))
  } catch (e) {
    console.error('Failed to save custom names:', e)
  }
}

/** Editable name component with inline editing */
function EditableName({ 
  id, 
  defaultName, 
  customNames, 
  onRename,
  className = ''
}: { 
  id: string
  defaultName: string
  customNames: Record<string, string>
  onRename: (id: string, name: string) => void
  className?: string
}) {
  const [editing, setEditing] = useState(false)
  const [value, setValue] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)
  
  const displayName = customNames[id] || defaultName
  
  const startEdit = (e: React.MouseEvent) => {
    e.stopPropagation()
    setValue(displayName)
    setEditing(true)
  }
  
  const save = () => {
    const trimmed = value.trim()
    if (trimmed && trimmed !== defaultName) {
      onRename(id, trimmed)
    } else if (trimmed === defaultName) {
      // Reset to default - remove custom name
      onRename(id, '')
    }
    setEditing(false)
  }
  
  const cancel = () => {
    setEditing(false)
  }
  
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      save()
    } else if (e.key === 'Escape') {
      cancel()
    }
  }
  
  useEffect(() => {
    if (editing && inputRef.current) {
      inputRef.current.focus()
      inputRef.current.select()
    }
  }, [editing])
  
  if (editing) {
    return (
      <input
        ref={inputRef}
        type="text"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onBlur={save}
        onKeyDown={handleKeyDown}
        className={cn(
          "bg-background border border-primary rounded px-1.5 py-0.5 text-sm font-medium",
          "focus:outline-none focus:ring-1 focus:ring-primary",
          "min-w-[120px]",
          className
        )}
        onClick={(e) => e.stopPropagation()}
      />
    )
  }
  
  return (
    <span className="flex items-center gap-1">
      <span className={cn("font-medium truncate", className)}>{displayName}</span>
      <button 
        type="button"
        onClick={startEdit}
        className="text-muted-foreground hover:text-foreground p-0.5 opacity-60 hover:opacity-100 transition-opacity"
        title="Rename"
      >
        <Pencil className="h-2.5 w-2.5" />
      </button>
    </span>
  )
}

// Create a context for custom names to avoid prop drilling
const CustomNamesContext = React.createContext<{
  customNames: Record<string, string>
  onRename: (id: string, name: string) => void
}>({ customNames: {}, onRename: () => {} })

// ─────────────────────────────────────────────────────────────────────────────
// Deduplication Logic - Aggressive matching for btrfs subvolumes
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Detect if a mount path is a btrfs subvolume mount that duplicates a canonical path.
 * Examples:
 *   /btrfs/root -> duplicate of /
 *   /btrfs/home -> duplicate of /home
 *   /btrfs/@    -> duplicate of /
 */
function isBtrfsSubvolumeDuplicate(mount: string): boolean {
  // Common btrfs subvolume mount patterns
  if (mount.startsWith('/btrfs/')) return true
  if (mount.startsWith('/@')) return true
  if (mount.match(/^\/[^/]+\/@/)) return true  // /something/@...
  return false
}

/**
 * Extract the logical purpose from a mount path.
 * /home -> "home"
 * /btrfs/home -> "home"
 * / -> "root"
 * /btrfs/root -> "root"
 * /btrfs/@ -> "root"
 */
function getMountPurpose(mount: string): string {
  const m = mount.toLowerCase()
  
  // Handle /btrfs/xyz patterns
  if (m.startsWith('/btrfs/')) {
    const sub = m.slice(7).replace(/^@/, '').replace(/\/$/, '')
    if (!sub || sub === '@' || sub === 'root') return 'root'
    return sub
  }
  
  // Handle /@ patterns
  if (m.startsWith('/@')) {
    const sub = m.slice(2).replace(/\/$/, '')
    if (!sub) return 'root'
    return sub
  }
  
  // Standard mounts
  if (m === '/') return 'root'
  if (m === '/home') return 'home'
  if (m === '/boot' || m === '/boot/efi') return 'boot'
  
  // Use last path segment
  const segments = m.split('/').filter(Boolean)
  return segments[segments.length - 1] || 'root'
}

/**
 * Get canonical mount path for a purpose
 */
function getCanonicalMountForPurpose(purpose: string): string {
  switch (purpose) {
    case 'root': return '/'
    case 'home': return '/home'
    case 'boot': return '/boot'
    default: return `/${purpose}`
  }
}

/**
 * Get user-friendly label for a mount purpose
 */
function getPurposeLabel(purpose: string): string {
  switch (purpose) {
    case 'root': return 'Root'
    case 'home': return 'Home'
    case 'boot': return 'Boot'
    case 'var': return 'Var'
    default: return purpose.charAt(0).toUpperCase() + purpose.slice(1)
  }
}

/**
 * Generate semantic name for a filesystem based on its mount point.
 * Uses standard Linux terminology.
 */
function getSemanticName(mountpoint: string, fstype: string, diskCount: number): string {
  const m = mountpoint.toLowerCase()
  
  // Boot partitions
  if (m === '/boot/efi' || m === '/boot' || m === '/efi') {
    return 'Boot Partition'
  }
  
  // Root filesystem
  if (m === '/' || m === '/btrfs/@' || m === '/btrfs/root') {
    return 'System Root'
  }
  
  // Home
  if (m === '/home' || m === '/btrfs/home') {
    return diskCount > 1 ? 'Home Array' : 'Home Storage'
  }
  
  // Common mount points
  if (m.includes('/var')) return 'Var Volume'
  if (m.includes('/tmp')) return 'Temp Volume'
  if (m.includes('/opt')) return 'Opt Volume'
  if (m.includes('/srv')) return 'Server Data'
  
  // Media/data mounts - extract name from path
  if (m.includes('/media/') || m.includes('/mnt/')) {
    // Extract the last meaningful part of the path
    const parts = m.split('/').filter(Boolean)
    const name = parts[parts.length - 1] || 'External'
    // Smart formatting: split on camelCase, underscores, and hyphens
    const formatted = name
      // Insert space before capitals in camelCase (TempBackup -> Temp Backup)
      .replace(/([a-z])([A-Z])/g, '$1 $2')
      // Split on underscores and hyphens
      .split(/[-_]/)
      // Capitalize first letter of each word
      .map(w => w.charAt(0).toUpperCase() + w.slice(1))
      .join(' ')
    
    // Use appropriate suffix based on filesystem type and disk count
    if (fstype === 'bcachefs') {
      return diskCount > 1 ? `${formatted} Pool` : `${formatted} Volume`
    }
    return `${formatted} Volume`
  }
  
  // Generic bcachefs fallback (for non-mnt paths)
  if (fstype === 'bcachefs') {
    return diskCount > 1 ? 'Bcachefs Pool' : 'Bcachefs Volume'
  }
  
  if (m.includes('backup')) return 'Backup Storage'
  if (m.includes('data')) return 'Data Storage'
  
  // Fallback
  const segments = m.split('/').filter(Boolean)
  if (segments.length > 0) {
    const name = segments[segments.length - 1]
    return name.charAt(0).toUpperCase() + name.slice(1) + ' Volume'
  }
  
  return 'Storage Volume'
}

/**
 * Create a fingerprint for filesystem deduplication.
 * Two filesystems with same fingerprint are considered duplicates.
 */
function getFilesystemFingerprint(fs: StorageItem): string {
  const purpose = getMountPurpose(fs.data.mountpoint || '')
  const size = fs.data.size || ''
  const percent = fs.data.percent || 0
  const fstype = fs.data.fstype || ''
  
  // Fingerprint: purpose + size + percent + fstype
  // This catches: /home and /btrfs/home (same purpose, size, percent)
  return `${purpose}|${size}|${percent}|${fstype}`
}

/**
 * Deduplicate filesystems by fingerprint, keeping canonical mount paths.
 */
function deduplicateFilesystems(filesystems: StorageItem[]): FilesystemEntry[] {
  const seen = new Map<string, FilesystemEntry>()
  
  for (const fs of filesystems) {
    const fingerprint = getFilesystemFingerprint(fs)
    const purpose = getMountPurpose(fs.data.mountpoint || '')
    const mountpoint = fs.data.mountpoint || ''
    
    const existing = seen.get(fingerprint)
    
    if (!existing) {
      // First occurrence
      seen.set(fingerprint, {
        id: fs.id,
        mountpoint: isBtrfsSubvolumeDuplicate(mountpoint) 
          ? getCanonicalMountForPurpose(purpose) 
          : mountpoint,
        label: getPurposeLabel(purpose),
        fstype: fs.data.fstype || 'unknown',
        size: fs.data.size || '0',
        used: fs.data.used || '0',
        percent: fs.data.percent || 0,
        severity: fs.severity,
      })
    } else {
      // Duplicate found - prefer canonical mount path
      if (!isBtrfsSubvolumeDuplicate(mountpoint) && isBtrfsSubvolumeDuplicate(existing.mountpoint)) {
        existing.mountpoint = mountpoint
        existing.id = fs.id
      }
    }
  }
  
  return Array.from(seen.values())
}

// ─────────────────────────────────────────────────────────────────────────────
// Physical Disk Grouping
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Extract base device from partition device path.
 * /dev/nvme0n1p2 -> /dev/nvme0n1
 * /dev/sda1 -> /dev/sda
 */
function getBaseDevice(device: string): string {
  if (!device) return ''
  // NVMe: /dev/nvme0n1p2 -> /dev/nvme0n1
  if (device.includes('nvme')) {
    return device.replace(/p\d+$/, '')
  }
  // SATA/SAS: /dev/sda1 -> /dev/sda
  return device.replace(/\d+$/, '')
}

/**
 * Create disk groups - group filesystems by shared physical disk.
 * Boot + Root on same disk = one card with both filesystems.
 * 
 * Uses parent_disk field from backend when available (preferred),
 * falls back to heuristic device path matching.
 */
function createDiskGroups(
  filesystems: FilesystemEntry[],
  rawFilesystems: StorageItem[],
  disks: StorageItem[]
): DiskGroup[] {
  // Build maps from filesystem mountpoint to device/array info
  const fsInfoMap = new Map<string, { 
    device: string
    parentDisk: string | null
    arrayMembers: ArrayMember[]
    arrayType: string | null
    arrayProfile: string | null
    dataProfile: string | null
    metadataProfile: string | null
    arrayTiers: Record<string, string[]>
  }>()
  
  for (const fs of rawFilesystems) {
    const mount = fs.data.mountpoint || ''
    const device = fs.data.device || fs.data.source || ''
    const parentDisk = fs.data.parent_disk || null
    const arrayMembers = (fs.data.array_members || []) as ArrayMember[]
    const arrayType = fs.data.array_type || null
    const arrayProfile = fs.data.array_profile || null
    const dataProfile = fs.data.data_profile || null
    const metadataProfile = fs.data.metadata_profile || null
    const arrayTiers = (fs.data.array_tiers || {}) as Record<string, string[]>
    if (mount) {
      fsInfoMap.set(mount, { device, parentDisk, arrayMembers, arrayType, arrayProfile, dataProfile, metadataProfile, arrayTiers })
    }
  }
  
  // Helper to find matching disks for a filesystem
  const findMatchingDisks = (fs: FilesystemEntry): StorageItem[] => {
    const fsInfo = fsInfoMap.get(fs.mountpoint) || { 
      device: '', 
      parentDisk: null, 
      arrayMembers: [],
      arrayType: null,
      arrayProfile: null,
      dataProfile: null,
      metadataProfile: null,
      arrayTiers: {}
    }
    
    // If we have array members from the backend, use those directly
    if (fsInfo.arrayMembers.length > 0) {
      const memberDevices = new Set(fsInfo.arrayMembers.map(m => m.device))
      return disks.filter(d => {
        const diskDevice = d.data.device || ''
        // Check if disk matches any array member device
        return memberDevices.has(diskDevice)
      })
    }
    
    // Fallback: use parent disk / device matching
    const device = fsInfo.device
    const parentDisk = fsInfo.parentDisk
    const baseDevice = parentDisk || getBaseDevice(device)
    
    return disks.filter(d => {
      const diskDevice = d.data.device || ''
      if (parentDisk && diskDevice === parentDisk) return true
      if (baseDevice && diskDevice === baseDevice) return true
      if (device && diskDevice && device.startsWith(diskDevice) && device !== diskDevice) return true
      return false
    })
  }
  
  // Group filesystems by their physical disk(s)
  // Key = sorted disk device names joined
  const diskKeyToFilesystems = new Map<string, { filesystems: FilesystemEntry[]; disks: StorageItem[] }>()
  
  for (const fs of filesystems) {
    const matchingDisks = findMatchingDisks(fs)
    const diskKey = matchingDisks.length > 0 
      ? matchingDisks.map(d => d.data.device).sort().join(',')
      : `orphan-${fs.id}`  // Filesystems with no disk match get their own group
    
    if (!diskKeyToFilesystems.has(diskKey)) {
      diskKeyToFilesystems.set(diskKey, { filesystems: [], disks: matchingDisks })
    }
    diskKeyToFilesystems.get(diskKey)!.filesystems.push(fs)
  }
  
  // Build final groups
  const groups: DiskGroup[] = []
  
  for (const [diskKey, { filesystems: fsList, disks: matchingDisks }] of diskKeyToFilesystems) {
    // Sort filesystems within group: root, boot, home, then alphabetical
    fsList.sort((a, b) => {
      const priority = (mount: string) => {
        if (mount === '/') return 0
        if (mount === '/boot' || mount === '/boot/efi') return 1
        if (mount === '/home') return 2
        return 3
      }
      return priority(a.mountpoint) - priority(b.mountpoint) || a.mountpoint.localeCompare(b.mountpoint)
    })
    
    // Generate semantic name for the group
    const hasRoot = fsList.some(f => f.mountpoint === '/')
    const hasBoot = fsList.some(f => f.mountpoint === '/boot' || f.mountpoint === '/boot/efi')
    const hasHome = fsList.some(f => f.mountpoint === '/home')
    const diskCount = Math.max(matchingDisks.length, 1)
    
    let semanticName: string
    if (hasRoot || hasBoot) {
      semanticName = diskCount > 1 ? 'System Array' : 'System Disk'
    } else if (hasHome) {
      semanticName = diskCount > 1 ? 'Home Array' : 'Home Storage'
    } else if (fsList.length === 1) {
      // Single filesystem - use its semantic name
      semanticName = getSemanticName(fsList[0].mountpoint, fsList[0].fstype, diskCount)
    } else {
      semanticName = 'Storage Group'
    }
    
    // Calculate total size from largest filesystem
    const totalSize = fsList.reduce((max, fs) => {
      const current = parseFloat(fs.size) || 0
      const maxVal = parseFloat(max) || 0
      return current > maxVal ? fs.size : max
    }, '0')
    
    // Check for disk warnings
    const hasWarnings = matchingDisks.some(d => 
      d.data.smart_status === 'WARNING' || d.data.smart_status === 'FAILED'
    )
    
    // Get array info from the first filesystem (they share the same array)
    const primaryFsInfo = fsInfoMap.get(fsList[0]?.mountpoint)
    const arrayType = primaryFsInfo?.arrayType || null
    const arrayProfile = primaryFsInfo?.arrayProfile || null
    const dataProfile = primaryFsInfo?.dataProfile || null
    const metadataProfile = primaryFsInfo?.metadataProfile || null
    const arrayTiers = primaryFsInfo?.arrayTiers || {}
    const arrayMembers = primaryFsInfo?.arrayMembers || []
    
    groups.push({
      id: diskKey,
      semanticName,
      filesystems: fsList,
      disks: matchingDisks,
      diskCount,
      totalSize,
      hasWarnings,
      arrayType,
      arrayProfile,
      dataProfile,
      metadataProfile,
      arrayTiers,
      arrayMembers,
    })
  }
  
  // Sort groups: system disk first, then home, then others
  groups.sort((a, b) => {
    const hasRoot = (g: DiskGroup) => g.filesystems.some(f => f.mountpoint === '/')
    const hasHome = (g: DiskGroup) => g.filesystems.some(f => f.mountpoint === '/home')
    
    if (hasRoot(a) && !hasRoot(b)) return -1
    if (!hasRoot(a) && hasRoot(b)) return 1
    if (hasHome(a) && !hasHome(b)) return -1
    if (!hasHome(a) && hasHome(b)) return 1
    return a.semanticName.localeCompare(b.semanticName)
  })
  
  return groups
}

// ─────────────────────────────────────────────────────────────────────────────
// Components
// ─────────────────────────────────────────────────────────────────────────────

/** 
 * Get short name for filesystem when inside a multi-fs group.
 * Since the group already has context (e.g., "System Disk"), we use shorter names.
 */
function getShortName(mountpoint: string): string {
  if (mountpoint === '/') return 'Root'
  if (mountpoint === '/boot' || mountpoint === '/boot/efi') return 'Boot'
  if (mountpoint === '/home') return 'Home'
  // For others, use last path segment
  const parts = mountpoint.split('/').filter(Boolean)
  return parts[parts.length - 1] || mountpoint
}

/** Compact usage bar row for grid layout */
function FilesystemUsageBar({ fs, showName = false }: { fs: FilesystemEntry; showName?: boolean }) {
  const shortName = getShortName(fs.mountpoint)
  const { customNames, onRename } = useContext(CustomNamesContext)
  
  return (
    <>
      {/* Column 1: name + mount (only for multi-fs groups) */}
      {showName && (
        <div className="flex items-center gap-1.5">
          <Folder className="h-3.5 w-3.5 text-blue-400 shrink-0" />
          <EditableName
            id={`fs-${fs.mountpoint}`}
            defaultName={shortName}
            customNames={customNames}
            onRename={onRename}
            className="text-sm"
          />
          <span className="text-muted-foreground text-xs">
            {fs.mountpoint}
          </span>
        </div>
      )}
      {/* Column 2: Progress bar */}
      <Progress
        value={fs.percent}
        className={cn(
          "h-2",
          fs.severity === 'critical' && '[&>div]:bg-red-500',
          fs.severity === 'warning' && '[&>div]:bg-yellow-500',
        )}
      />
      {/* Column 3: Size info */}
      <span className="text-muted-foreground text-right text-xs">
        {fs.used}/{fs.size}
      </span>
      {/* Column 4: Percent badge */}
      <Badge
        className={cn(
          "text-xs w-14 justify-center",
          fs.severity === 'critical' && 'bg-red-500',
          fs.severity === 'warning' && 'bg-yellow-500',
          fs.severity === 'success' && 'bg-green-500',
          !['critical', 'warning', 'success'].includes(fs.severity) && 'bg-blue-500',
        )}
      >
        {fs.percent}%
      </Badge>
    </>
  )
}

/** Tier role badge colors */
const TIER_ROLE_CONFIG: Record<string, { label: string; color: string }> = {
  // bcachefs specific roles
  foreground: { label: 'Write', color: 'bg-cyan-500' },
  promote: { label: 'Read', color: 'bg-blue-500' },
  metadata: { label: 'Meta', color: 'bg-purple-500' },
  // Generic roles
  cache: { label: 'Cache', color: 'bg-cyan-500' },
  data: { label: 'Data', color: 'bg-slate-500' },
  log: { label: 'Log', color: 'bg-amber-500' },
  spare: { label: 'Spare', color: 'bg-yellow-500' },
}

/** Physical disk item shown when group is expanded */
function DiskItem({ 
  disk, 
  allDisks = [],
  showNestedMembers = false,
  nested = false,
  memberInfo,
}: { 
  disk: StorageItem
  allDisks?: StorageItem[]
  showNestedMembers?: boolean
  nested?: boolean
  memberInfo?: ArrayMember  // Tier info from array_members
}) {
  const showUUIDs = React.useContext(ShowUUIDsContext)
  const isRaid = disk.data.type === 'RAID'
  const memberPaths = disk.data.members || []
  const raidLevel = disk.data.raid_level || 'raid'
  
  // Find actual disk objects for member paths
  const memberDisks = showNestedMembers && isRaid
    ? memberPaths.map(path => allDisks.find(d => d.data.device === path)).filter(Boolean) as StorageItem[]
    : []
  
  // Format RAID level for display (raid0 -> RAID0) - no space for better centering
  const raidBadgeText = raidLevel.toUpperCase()
  
  // Get tier info from memberInfo prop - support multiple roles
  const tierRoles = memberInfo?.roles || (memberInfo?.role ? [memberInfo.role] : [])
  const tierLabel = memberInfo?.label || memberInfo?.tier
  // Filter to only roles we have config for, and dedupe
  const displayRoles = tierRoles
    .filter(r => TIER_ROLE_CONFIG[r])
    .filter((r, i, arr) => arr.indexOf(r) === i)
  
  return (
    <div className={cn(
      "rounded-lg border bg-muted/30",
      isRaid && "border-blue-500/30",
      nested ? "py-1.5 px-2" : "pt-3 px-3 pb-4"
    )}>
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0 flex-1">
          <HardDrive className={cn(
            "shrink-0",
            nested ? "h-3.5 w-3.5" : "h-5 w-5",
            isRaid ? "text-blue-500" : "text-muted-foreground"
          )} />
          <div className="min-w-0 flex-1">
            <p className={cn("font-medium truncate", nested ? "text-xs" : "text-sm")}>{disk.title}</p>
            <div className={cn("flex items-center gap-1.5 flex-wrap", nested ? "mt-0.5" : "mt-1")}>
              {/* Tier role badges - show all roles this device serves */}
              {displayRoles.map(role => {
                const config = TIER_ROLE_CONFIG[role]
                return (
                  <Badge 
                    key={role}
                    className={cn(
                      "shrink-0 px-1.5 py-0",
                      nested ? "text-[8px]" : "text-[10px]",
                      config.color
                    )}
                  >
                    {config.label}
                  </Badge>
                )
              })}
              <span className={cn("text-muted-foreground truncate", nested ? "text-[10px]" : "text-xs")}>
                {disk.data.device} • {disk.data.size} • {disk.data.transport || disk.data.type}
                {tierLabel && displayRoles.length === 0 && ` • ${tierLabel}`}
              </span>
            </div>
            {/* UUID line - only shown when toggle is on */}
            {showUUIDs && (disk.data.uuid || disk.data.wwn || disk.data.serial) && (
              <p className={cn("text-muted-foreground/70 font-mono truncate", nested ? "text-[9px] mt-0.5" : "text-[10px] mt-1")}>
                {disk.data.uuid || disk.data.wwn || disk.data.serial}
              </p>
            )}
          </div>
        </div>
        <Badge
          className={cn(
            "shrink-0 min-w-[4.5rem] justify-center leading-none",
            nested 
              ? "text-[10px] px-1.5 py-1 min-w-[4.5rem]" 
              : "text-xs px-2 py-1",
            disk.data.smart_status === 'PASSED' && 'bg-green-500',
            disk.data.smart_status === 'FAILED' && 'bg-red-500',
            disk.data.smart_status === 'WARNING' && 'bg-yellow-500',
            disk.data.smart_status === 'UNKNOWN' && 'bg-gray-400',
            disk.data.smart_status === 'NO_ACCESS' && 'bg-orange-400',
            disk.data.smart_status === 'N/A' && 'bg-blue-500',
          )}
        >
          {isRaid ? raidBadgeText : (disk.data.smart_status || 'UNKNOWN')}
        </Badge>
      </div>
      
      {/* Nested member disks for MD arrays */}
      {showNestedMembers && isRaid && memberDisks.length > 0 && (
        <div className="mt-1.5 -mx-1 space-y-1">
          {memberDisks.map(memberDisk => (
            <DiskItem 
              key={memberDisk.id} 
              disk={memberDisk} 
              nested={true}
            />
          ))}
        </div>
      )}
      
      {/* Fallback: show member paths if disks not found */}
      {showNestedMembers && isRaid && memberDisks.length === 0 && memberPaths.length > 0 && (
        <div className="mt-1.5 -mx-1 text-xs text-muted-foreground">
          <span className="font-medium">Members:</span> {memberPaths.join(', ')}
        </div>
      )}
    </div>
  )
}

/** 
 * Compact disk group card.
 * Header: semantic name + mount point (for single fs) + disk count
 * Body: usage bar(s)
 * Footer: small expand link for physical disks
 */
function DiskGroupSection({ group, allDisks }: { group: DiskGroup; allDisks: StorageItem[] }) {
  const [isOpen, setIsOpen] = useState(false)
  const { customNames, onRename } = useContext(CustomNamesContext)
  
  const isSingleFs = group.filesystems.length === 1
  const primaryFs = group.filesystems[0]
  
  // Count MD arrays vs regular disks for layout decisions
  const mdArrays = group.disks.filter(d => d.data.type === 'RAID')
  const nonMdDisks = group.disks.filter(d => d.data.type !== 'RAID')
  // Use full width for single MD or when MDs have nested members (to prevent stacking)
  const useFullWidth = mdArrays.length === 1 || (mdArrays.length > 0 && mdArrays.length <= 2)
  
  // Build device -> memberInfo map for tier badges
  const memberInfoMap = useMemo(() => {
    const map = new Map<string, ArrayMember>()
    if (group.arrayMembers) {
      for (const member of group.arrayMembers) {
        if (member.device) {
          map.set(member.device, member)
        }
      }
    }
    return map
  }, [group.arrayMembers])
  
  // Get member info for a disk
  const getMemberInfo = (disk: StorageItem): ArrayMember | undefined => {
    return memberInfoMap.get(disk.data.device || '')
  }
  
  // Calculate tier summary for header
  const tierSummary = useMemo(() => {
    if (!group.arrayMembers || group.arrayMembers.length === 0) return null
    const roleCounts: Record<string, number> = {}
    for (const member of group.arrayMembers) {
      const role = member.role || 'data'
      roleCounts[role] = (roleCounts[role] || 0) + 1
    }
    // Format: "10 cache + 5 data" or "2 meta + 2 cache + 7 data"
    const parts = Object.entries(roleCounts)
      .filter(([, count]) => count > 0)
      .sort(([a], [b]) => {
        const order = ['cache', 'metadata', 'log', 'data', 'spare']
        return order.indexOf(a) - order.indexOf(b)
      })
      .map(([role, count]) => `${count} ${role}`)
    return parts.length > 1 ? parts.join(' + ') : null
  }, [group.arrayMembers])
  
  // Reference this storage item in chat
  const handleMention = () => {
    // Create a clean slug from the semantic name for the mention
    const slug = group.semanticName.replace(/\s+/g, '_')
    
    // Primary filesystem info for context
    const primaryFs = group.filesystems[0]
    const mountInfo = primaryFs ? `${primaryFs.mountpoint} (${primaryFs.fstype})` : ''
    
    // Keep context concise - just the key info
    const usageInfo = group.filesystems.map(fs => 
      `${fs.mountpoint}: ${fs.percent}% used (${fs.used}/${fs.size})`
    ).join(', ')
    
    openChat({
      title: group.semanticName,
      type: 'storage',
      context: `${group.semanticName} - ${mountInfo}\n${group.diskCount} disks, ${usageInfo}`,
      itemId: slug,
      newConversation: false,  // @ tag just adds mention to current chat
      useSpecialist: false,
    })
  }
  
  return (
    <div className="rounded-lg border bg-card text-card-foreground shadow-sm">
      {/* Header row - sticky when expanded, -top-8 to offset main padding, py-3 to match sidebar height */}
      <div className={cn(
        "px-4 py-3 rounded-t-lg",
        isOpen && "sticky -top-8 z-10 bg-card"
      )}>
        <div className="flex items-center justify-between">
          {/* Left: icon + name + warnings + mount point */}
          <div className="flex items-center gap-1.5 min-w-0">
            <HardDrive className="h-4 w-4 text-blue-500 shrink-0" />
            <EditableName
              id={group.id}
              defaultName={group.semanticName}
              customNames={customNames}
              onRename={onRename}
            />
            {group.hasWarnings && (
              <AlertCircle className="h-3.5 w-3.5 text-yellow-500 shrink-0" />
            )}
            {isSingleFs && (
              <span className="text-muted-foreground text-sm ml-1 truncate">
                {primaryFs.mountpoint}
              </span>
            )}
          </div>
          {/* Right: array profile + disk count/tier summary + @ mention button */}
          <div className="flex items-center gap-2 shrink-0">
            {group.arrayProfile && group.arrayProfile !== 'single' && (
              <Badge variant="outline" className="text-xs px-1.5 py-0">
                {group.arrayProfile}
              </Badge>
            )}
            <span className="text-xs text-muted-foreground">
              {tierSummary 
                ? `${group.diskCount} disks: ${tierSummary}`
                : `${group.diskCount} ${group.diskCount === 1 ? 'disk' : 'disks'}`
              }
            </span>
            <button
              type="button"
              onClick={handleMention}
              className="text-muted-foreground hover:text-blue-500 font-medium text-sm px-1"
              title={`Reference ${group.semanticName} in chat`}
            >
              @
            </button>
          </div>
        </div>
      </div>
      
      {/* Usage bars - grid layout for alignment */}
      <div className="px-4 pb-2">
        {isSingleFs ? (
          // Single filesystem - simple flex row with details below
          <div className="space-y-0.5">
            <div className="flex items-center gap-2 text-sm">
              <FilesystemUsageBar fs={primaryFs} showName={false} />
            </div>
            {/* Filesystem details line - show metadata first, then data */}
            <div className="text-[11px] text-muted-foreground pl-0.5">
              {primaryFs.fstype.toUpperCase()}
              {(group.dataProfile || group.metadataProfile) ? (
                <>
                  {group.metadataProfile && <span> • meta: {group.metadataProfile}</span>}
                  {group.dataProfile && <span> • data: {group.dataProfile}</span>}
                </>
              ) : group.arrayProfile && group.arrayProfile !== 'single' && (
                <span> • {group.arrayProfile}</span>
              )}
            </div>
          </div>
        ) : (
          // Multiple filesystems - each FS with its own details below
          <div className="space-y-1">
            {group.filesystems.map((fs, idx) => (
              <div key={fs.id} className="space-y-0">
                {/* Filesystem row */}
                <div 
                  className="grid gap-x-3 items-center text-sm"
                  style={{ gridTemplateColumns: 'auto 1fr auto auto' }}
                >
                  <FilesystemUsageBar fs={fs} showName={true} />
                </div>
                {/* FS type details below this filesystem - metadata first, then data */}
                <div className="text-[11px] text-muted-foreground pl-5">
                  {fs.fstype.toUpperCase()}
                  {/* Show meta/data profiles for primary FS, or just fstype for others */}
                  {idx === 0 && (group.dataProfile || group.metadataProfile) ? (
                    <>
                      {group.metadataProfile && <span> • meta: {group.metadataProfile}</span>}
                      {group.dataProfile && <span> • data: {group.dataProfile}</span>}
                    </>
                  ) : idx === 0 && group.arrayProfile && group.arrayProfile !== 'single' && (
                    <span> • {group.arrayProfile}</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
      
      {/* Compact expand row - no dividers */}
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className={cn(
          "w-full flex items-center justify-center gap-1 py-1 text-xs",
          "text-muted-foreground hover:text-foreground hover:bg-muted/30 transition-colors"
        )}
      >
        {isOpen ? (
          <ChevronDown className="h-3 w-3" />
        ) : (
          <ChevronRight className="h-3 w-3" />
        )}
        <span>{isOpen ? 'Hide' : 'Show'} {group.diskCount === 1 ? 'disk' : 'disks'}</span>
      </button>
      
      {/* Expanded: physical disks - with nested MD members */}
      {isOpen && (
        <div className="px-4 pb-3 pt-1 space-y-3">
          {mdArrays.length > 0 && nonMdDisks.length > 0 ? (
            // Mixed: show non-MD disks first, then MD arrays with nested members
            <>
              {/* Non-RAID disks */}
              <div>
                <div className="flex items-center gap-2 mb-1.5">
                  <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                    Direct Disks
                  </span>
                  <span className="text-xs text-muted-foreground">
                    ({nonMdDisks.length})
                  </span>
                </div>
                <div className={cn(
                  "grid gap-2",
                  useFullWidth ? "grid-cols-1" : "grid-cols-1 lg:grid-cols-2"
                )}>
                  {nonMdDisks.map((disk) => (
                    <DiskItem key={disk.id} disk={disk} allDisks={allDisks} showNestedMembers={true} memberInfo={getMemberInfo(disk)} />
                  ))}
                </div>
              </div>
              {/* MD arrays with nested members */}
              <div>
                <div className="flex items-center gap-2 mb-1.5">
                  <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                    RAID Arrays
                  </span>
                  <span className="text-xs text-muted-foreground">
                    ({mdArrays.length})
                  </span>
                </div>
                <div className={cn(
                  "grid gap-2",
                  useFullWidth ? "grid-cols-1" : "grid-cols-1 lg:grid-cols-2"
                )}>
                  {mdArrays.map((disk) => (
                    <DiskItem key={disk.id} disk={disk} allDisks={allDisks} showNestedMembers={true} memberInfo={getMemberInfo(disk)} />
                  ))}
                </div>
              </div>
            </>
          ) : mdArrays.length > 0 ? (
            // Only MD arrays
            <div className={cn(
              "grid gap-2",
              useFullWidth ? "grid-cols-1" : "grid-cols-1 lg:grid-cols-2"
            )}>
              {mdArrays.map((disk) => (
                <DiskItem key={disk.id} disk={disk} allDisks={allDisks} showNestedMembers={true} memberInfo={getMemberInfo(disk)} />
              ))}
            </div>
          ) : group.disks.length > 0 ? (
            // Only regular disks
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-2">
              {group.disks.map((disk) => (
                <DiskItem key={disk.id} disk={disk} allDisks={allDisks} showNestedMembers={true} memberInfo={getMemberInfo(disk)} />
              ))}
            </div>
          ) : (
            <p className="text-xs text-muted-foreground italic">
              No disk info - device mapping not found
            </p>
          )}
        </div>
      )}
    </div>
  )
}

type SortOption = 'name' | 'type' | 'size' | 'transport'

/** Parse size string to bytes for sorting */
function parseSizeToBytes(size: string): number {
  if (!size) return 0
  const match = size.match(/^([\d.]+)\s*([KMGTP]?)i?B?$/i)
  if (!match) return 0
  const num = parseFloat(match[1])
  const unit = (match[2] || '').toUpperCase()
  const multipliers: Record<string, number> = { '': 1, 'K': 1024, 'M': 1024**2, 'G': 1024**3, 'T': 1024**4, 'P': 1024**5 }
  return num * (multipliers[unit] || 1)
}

/** Extract numeric ID from device name for sorting (e.g., sda -> 0, sdb -> 1, nvme0n1 -> 0) */
function getDeviceIdNumber(device: string): number {
  const name = device.replace('/dev/', '')
  // MD devices: md122 -> 122
  const mdMatch = name.match(/^md(\d+)/)
  if (mdMatch) return parseInt(mdMatch[1], 10)
  // NVMe: nvme0n1 -> 0
  const nvmeMatch = name.match(/^nvme(\d+)/)
  if (nvmeMatch) return parseInt(nvmeMatch[1], 10)
  // SATA: sda -> 0, sdb -> 1, sdz -> 25, sdaa -> 26
  const sdMatch = name.match(/^sd([a-z]+)/)
  if (sdMatch) {
    const letters = sdMatch[1]
    let num = 0
    for (let i = 0; i < letters.length; i++) {
      num = num * 26 + (letters.charCodeAt(i) - 96)
    }
    return num - 1
  }
  return 0
}

/** All physical devices section with sorting */
function AllDevicesSection({ disks }: { disks: StorageItem[] }) {
  const [sortBy, setSortBy] = useState<SortOption>('name')
  const [groupByType, setGroupByType] = useState(true)
  const [groupMdDevices, setGroupMdDevices] = useState(true)
  
  // Physical disks only (exclude RAID arrays for counting)
  const physicalDisks = disks.filter(d => d.data.type !== 'RAID')
  
  const healthyCount = physicalDisks.filter(d => d.data.smart_status === 'PASSED').length
  const warningCount = physicalDisks.filter(d => 
    d.data.smart_status === 'WARNING' || d.data.smart_status === 'FAILED'
  ).length
  
  // Get all MD arrays and their member devices
  const mdArrays = disks.filter(d => d.data.type === 'RAID')
  const mdMemberDevices = new Set(
    mdArrays.flatMap(md => md.data.members || [])
  )
  
  // Filter out disks that are MD members if grouping is enabled
  const filteredDisks = groupMdDevices 
    ? disks.filter(d => !mdMemberDevices.has(d.data.device || ''))
    : disks
  
  // Sort disks
  const sortedDisks = [...filteredDisks].sort((a, b) => {
    switch (sortBy) {
      case 'type':
        return (a.data.type || '').localeCompare(b.data.type || '')
      case 'size':
        return parseSizeToBytes(b.data.size || '') - parseSizeToBytes(a.data.size || '')
      case 'transport':
        return (a.data.transport || '').localeCompare(b.data.transport || '')
      case 'name':
      default:
        return getDeviceIdNumber(a.data.device || '') - getDeviceIdNumber(b.data.device || '')
    }
  })
  
  // Group by type if enabled
  const groupedDisks = groupByType ? {
    'NVMe': sortedDisks.filter(d => d.data.type === 'NVMe'),
    'SSD': sortedDisks.filter(d => d.data.type === 'SSD'),
    'HDD': sortedDisks.filter(d => d.data.type === 'HDD'),
    'RAID': sortedDisks.filter(d => d.data.type === 'RAID'),
  } : null
  
  // Count physical disks shown (non-MD-members)
  const shownPhysicalDisks = physicalDisks.filter(d => !mdMemberDevices.has(d.data.device || ''))
  const hiddenMdMembers = physicalDisks.length - shownPhysicalDisks.length
  const summary = warningCount > 0
    ? `${physicalDisks.length} disks${hiddenMdMembers > 0 ? ` (${hiddenMdMembers} in MD arrays)` : ''} • ${healthyCount} healthy • ${warningCount} warning`
    : `${physicalDisks.length} disks${hiddenMdMembers > 0 ? ` (${hiddenMdMembers} in MD arrays)` : ''} • ${healthyCount} healthy`
  
  return (
    <Collapsible
      defaultOpen={false}
      stickyHeader={true}
      title={
        <div className="flex items-center gap-2">
          <Database className="h-5 w-5 text-muted-foreground" />
          <span>All Physical Devices</span>
          {warningCount > 0 && (
            <Badge className="bg-yellow-500 text-xs">{warningCount} warning</Badge>
          )}
        </div>
      }
      summary={summary}
    >
      {disks.length === 0 ? (
        <p className="text-muted-foreground">No disks discovered</p>
      ) : (
        <div className="space-y-3">
          {/* Sort/Group controls */}
          <div className="flex items-center gap-4 text-xs">
            <div className="flex items-center gap-2">
              <span className="text-muted-foreground">Sort:</span>
              {(['name', 'type', 'size', 'transport'] as SortOption[]).map(opt => (
                <button
                  key={opt}
                  onClick={() => setSortBy(opt)}
                  className={cn(
                    "px-2 py-0.5 rounded",
                    sortBy === opt ? "bg-primary text-primary-foreground" : "hover:bg-muted"
                  )}
                >
                  {opt === 'name' ? 'ID#' : opt.charAt(0).toUpperCase() + opt.slice(1)}
                </button>
              ))}
            </div>
            <button
              onClick={() => setGroupByType(!groupByType)}
              className={cn(
                "px-2 py-0.5 rounded",
                groupByType ? "bg-primary text-primary-foreground" : "hover:bg-muted"
              )}
            >
              Group by type
            </button>
            <button
              onClick={() => setGroupMdDevices(!groupMdDevices)}
              className={cn(
                "px-2 py-0.5 rounded",
                groupMdDevices ? "bg-primary text-primary-foreground" : "hover:bg-muted"
              )}
            >
              Group MD
            </button>
          </div>
          
          {/* Disk list */}
          {groupByType && groupedDisks ? (
            // Grouped view
            Object.entries(groupedDisks).map(([type, typeDisks]) => {
              if (typeDisks.length === 0) return null
              
              // For RAID type when groupMD is on, show nested members
              const showNested = type === 'RAID' && groupMdDevices
              // For RAID with nested members, use full width
              const useFullWidthRaid = showNested && typeDisks.length <= 3
              
              return (
                <div key={type}>
                  <div className="flex items-center gap-2 mb-1.5">
                    <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                      {type}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      ({typeDisks.length})
                    </span>
                  </div>
                  <div className={cn(
                    "grid gap-2",
                    useFullWidthRaid ? "grid-cols-1" : "grid-cols-1 lg:grid-cols-2"
                  )}>
                    {typeDisks.map((disk) => (
                      <DiskItem 
                        key={disk.id} 
                        disk={disk} 
                        allDisks={disks}
                        showNestedMembers={showNested}
                      />
                    ))}
                  </div>
                </div>
              )
            })
          ) : (
            // Flat view
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-2">
              {sortedDisks.map((disk) => (
                <DiskItem 
                  key={disk.id} 
                  disk={disk} 
                  allDisks={disks}
                  showNestedMembers={groupMdDevices && disk.data.type === 'RAID'}
                />
              ))}
            </div>
          )}
        </div>
      )}
    </Collapsible>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Unmounted Volumes Section
// ─────────────────────────────────────────────────────────────────────────────

/** Generate default mount command based on filesystem type */
function generateMountCommand(fstype: string, uuid: string, mountpoint: string): string {
  switch (fstype) {
    case 'bcachefs':
      return `sudo mount.bcachefs UUID=${uuid} ${mountpoint}`
    case 'btrfs':
      return `sudo mount -t btrfs UUID=${uuid} ${mountpoint}`
    case 'ext4':
      return `sudo mount -t ext4 UUID=${uuid} ${mountpoint}`
    case 'xfs':
      return `sudo mount -t xfs UUID=${uuid} ${mountpoint}`
    case 'zfs':
      return `# ZFS pools are typically imported, not mounted:\nsudo zpool import <pool-name>`
    default:
      return `sudo mount UUID=${uuid} ${mountpoint}`
  }
}

function UnmountedVolumeCard({ volume }: { volume: StorageItem }) {
  const [expanded, setExpanded] = useState(false)
  const [copied, setCopied] = useState(false)
  const [mountpoint, setMountpoint] = useState(() => {
    // Suggest mount point based on label
    const label = volume.data.label || 'volume'
    const safeName = label.replace(/[^a-zA-Z0-9_-]/g, '_')
    return `/mnt/${safeName}`
  })
  const [customCommand, setCustomCommand] = useState('')
  
  const deviceCount = volume.data.device_count || 1
  const devices = volume.data.devices || []
  const uuid = volume.data.uuid || ''
  const fstype = volume.data.fstype || 'auto'
  
  // Generate or use custom command
  const mountCommand = customCommand || generateMountCommand(fstype, uuid, mountpoint)
  
  const copyToClipboard = async () => {
    try {
      await navigator.clipboard.writeText(mountCommand)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch (err) {
      console.error('Failed to copy:', err)
    }
  }
  
  return (
    <Card className="border-dashed border-muted-foreground/30 bg-muted/20">
      <CardContent className="p-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <HardDriveDownload className="h-6 w-6 text-muted-foreground" />
            <div>
              <h3 className="font-medium text-muted-foreground">{volume.title}</h3>
              <p className="text-xs text-muted-foreground/70">
                {fstype} • {deviceCount} device{deviceCount > 1 ? 's' : ''} • UUID: {uuid.slice(0, 8)}...
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="text-muted-foreground">
              Unmounted
            </Badge>
            <Button 
              size="sm" 
              variant="outline" 
              className="gap-1"
              onClick={() => setExpanded(!expanded)}
            >
              <FolderPlus className="h-4 w-4" />
              Mount
              {expanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
            </Button>
          </div>
        </div>
        
        {/* Show first few devices */}
        {devices.length > 0 && !expanded && (
          <div className="mt-2 pt-2 border-t border-muted-foreground/20">
            <p className="text-xs text-muted-foreground/60">
              Devices: {devices.slice(0, 4).join(', ')}{devices.length > 4 ? ` +${devices.length - 4} more` : ''}
            </p>
          </div>
        )}
        
        {/* Mount Configuration Panel */}
        {expanded && (
          <div className="mt-4 pt-4 border-t border-muted-foreground/20 space-y-4">
            {/* Mount Point */}
            <div className="space-y-2">
              <Label htmlFor={`mountpoint-${volume.id}`} className="text-xs text-muted-foreground">
                Mount Point
              </Label>
              <Input
                id={`mountpoint-${volume.id}`}
                value={mountpoint}
                onChange={(e) => {
                  setMountpoint(e.target.value)
                  setCustomCommand('') // Reset custom command when mountpoint changes
                }}
                placeholder="/mnt/volume"
                className="h-8 text-sm bg-background"
              />
            </div>
            
            {/* Mount Command */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label htmlFor={`command-${volume.id}`} className="text-xs text-muted-foreground flex items-center gap-1">
                  <Terminal className="h-3 w-3" />
                  Mount Command
                </Label>
                <Button 
                  size="sm" 
                  variant="ghost" 
                  className="h-6 px-2 text-xs gap-1"
                  onClick={copyToClipboard}
                >
                  {copied ? <Check className="h-3 w-3 text-green-500" /> : <Copy className="h-3 w-3" />}
                  {copied ? 'Copied!' : 'Copy'}
                </Button>
              </div>
              <textarea
                id={`command-${volume.id}`}
                value={mountCommand}
                onChange={(e) => setCustomCommand(e.target.value)}
                className="w-full h-20 px-3 py-2 text-xs font-mono bg-zinc-900 text-zinc-100 rounded-md border border-muted-foreground/20 resize-none"
                placeholder="Custom mount command..."
              />
              <p className="text-xs text-muted-foreground/50">
                Edit the command above if needed, then copy and run in terminal.
              </p>
            </div>
            
            {/* All Devices */}
            {devices.length > 0 && (
              <div className="space-y-1">
                <Label className="text-xs text-muted-foreground">All Devices ({devices.length})</Label>
                <div className="text-xs text-muted-foreground/60 font-mono bg-muted/50 p-2 rounded max-h-24 overflow-auto">
                  {devices.join('\n')}
                </div>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function UnmountedSection({ volumes, show, onToggle }: { 
  volumes: StorageItem[]
  show: boolean
  onToggle: () => void 
}) {
  if (volumes.length === 0) {
    return null
  }
  
  return (
    <div className="space-y-3">
      <button
        onClick={onToggle}
        className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
      >
        {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
        <span>{show ? 'Hide' : 'Show'} {volumes.length} unmounted volume{volumes.length > 1 ? 's' : ''}</span>
      </button>
      
      {show && (
        <div className="space-y-3">
          {volumes.map(volume => (
            <UnmountedVolumeCard key={volume.id} volume={volume} />
          ))}
        </div>
      )}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Main Component
// ─────────────────────────────────────────────────────────────────────────────

// Context for UUID visibility
const ShowUUIDsContext = React.createContext(false)

export function Storage() {
  const [storage, setStorage] = useState<StorageItem[]>([])
  const [loading, setLoading] = useState(true)
  const [scanning, setScanning] = useState(false)
  const [showUnmounted, setShowUnmounted] = useState(false)
  const [showUUIDs, setShowUUIDs] = useState(false)
  const [customNames, setCustomNames] = useState<Record<string, string>>(() => loadCustomNames())

  // Handle renaming a volume/filesystem
  const handleRename = useCallback((id: string, name: string) => {
    setCustomNames(prev => {
      const updated = { ...prev }
      if (name) {
        updated[id] = name
      } else {
        delete updated[id]
      }
      saveCustomNames(updated)
      return updated
    })
  }, [])

  useEffect(() => {
    loadStorage()
  }, [])

  const loadStorage = async () => {
    try {
      const data = await api.getDiscoveries('storage')
      setStorage(data.discoveries || [])
    } catch (error) {
      console.error('Failed to load storage:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleScan = async () => {
    setScanning(true)
    try {
      await api.scanDiscoveries('storage')
      await loadStorage()
    } catch (error) {
      console.error('Scan failed:', error)
    } finally {
      setScanning(false)
    }
  }

  // Process storage data
  const { diskGroups, disks, unmountedVolumes, stats } = useMemo(() => {
    // Include both physical disks (disk-*) and MD RAID arrays (md-*)
    const allDisks = storage.filter(s => s.name.startsWith('disk-') || s.name.startsWith('md-'))
    const rawFilesystems = storage.filter(s => s.name.startsWith('fs-'))
    
    // Get unmounted volumes
    const unmounted = storage.filter(s => s.name.startsWith('unmounted-'))
    
    // Deduplicate filesystems (merge btrfs subvolume mounts like /home and /btrfs/home)
    const dedupedFilesystems = deduplicateFilesystems(rawFilesystems)
    
    // Create disk groups - one per filesystem with proper semantic names
    const groups = createDiskGroups(dedupedFilesystems, rawFilesystems, allDisks)
    
    // Count unique filesystems across all groups
    const totalFs = groups.reduce((sum: number, g: DiskGroup) => sum + g.filesystems.length, 0)
    
    // Count critical filesystems
    const criticalFs = groups.reduce((sum: number, g: DiskGroup) => 
      sum + g.filesystems.filter((f: FilesystemEntry) => f.severity === 'critical').length, 0
    )
    
    // Physical disks only (exclude RAID arrays)
    const physicalDisks = allDisks.filter(d => d.data.type !== 'RAID')
    
    return {
      diskGroups: groups,
      disks: allDisks,
      unmountedVolumes: unmounted,
      stats: {
        totalDisks: physicalDisks.length,
        healthyDisks: physicalDisks.filter(d => d.data.smart_status === 'PASSED').length,
        totalFs,
        criticalFs,
        unmountedCount: unmounted.length,
      }
    }
  }, [storage])

  if (loading) {
    return <div className="flex items-center justify-center h-64">Loading...</div>
  }

  return (
    <CustomNamesContext.Provider value={{ customNames, onRename: handleRename }}>
    <ShowUUIDsContext.Provider value={showUUIDs}>
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold flex items-center gap-2">
            <HardDrive className="h-8 w-8" />
            Storage
          </h1>
          <p className="text-muted-foreground">
            Filesystems and disk health
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => setShowUUIDs(!showUUIDs)}
            className={cn(
              "text-xs px-2 py-1 rounded border transition-colors",
              showUUIDs 
                ? "bg-primary text-primary-foreground border-primary" 
                : "text-muted-foreground border-muted hover:border-foreground"
            )}
          >
            {showUUIDs ? 'Hide UUIDs' : 'Show UUIDs'}
          </button>
          <Button onClick={handleScan} disabled={scanning}>
            <RefreshCw className={cn("h-4 w-4 mr-2", scanning && "animate-spin")} />
            {scanning ? 'Scanning...' : 'Scan'}
          </Button>
        </div>
      </div>

      {/* Overview Stats */}
      <Card>
        <CardContent className="p-4">
          <div className="flex items-center gap-8 flex-wrap">
            <div className="flex items-center gap-2">
              <Folder className="h-5 w-5 text-muted-foreground" />
              <span className="font-medium">{stats.totalFs} Filesystems</span>
            </div>
            <div className="flex items-center gap-2">
              <HardDrive className="h-5 w-5 text-muted-foreground" />
              <span className="font-medium">{stats.totalDisks} Physical Disks</span>
            </div>
            <div className="flex items-center gap-2">
              <CheckCircle className="h-5 w-5 text-green-500" />
              <span className="font-medium text-green-600">{stats.healthyDisks} Healthy</span>
            </div>
            {stats.criticalFs > 0 && (
              <div className="flex items-center gap-2">
                <AlertCircle className="h-5 w-5 text-red-500" />
                <span className="font-medium text-red-600">{stats.criticalFs} Critical</span>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Disk Groups - each shows filesystems with usage bars, expand for physical disks */}
      <div className="space-y-4">
        {diskGroups.length === 0 ? (
          <Card>
            <CardContent className="p-6">
              <p className="text-muted-foreground text-center">
                No filesystems discovered. Click Scan to detect storage.
              </p>
            </CardContent>
          </Card>
        ) : (
          diskGroups.map((group) => (
            <DiskGroupSection key={group.id} group={group} allDisks={disks} />
          ))
        )}
        
        {/* All Physical Devices (collapsed by default) */}
        <AllDevicesSection disks={disks} />
        
        {/* Unmounted Volumes */}
        <UnmountedSection 
          volumes={unmountedVolumes} 
          show={showUnmounted} 
          onToggle={() => setShowUnmounted(!showUnmounted)} 
        />

        {/* AI Analysis Panel */}
        <AIAnalysisPanel
          type="storage"
          title="Storage"
          canAnalyze={storage.length > 0}
          buildContext={() => {
            const parts = [`## Storage Analysis Context\n`]
            parts.push(`- ${stats.totalFs} filesystems`)
            parts.push(`- ${stats.totalDisks} physical disks`)
            parts.push(`- ${stats.healthyDisks} healthy (SMART passed)`)
            if (stats.criticalFs > 0) parts.push(`- ${stats.criticalFs} critical issues\n`)
            
            // Include disk groups summary
            diskGroups.forEach(g => {
              parts.push(`### ${g.semanticName}`)
              g.filesystems.forEach(f => {
                parts.push(`- ${f.mountpoint}: ${f.percent}% used (${f.fstype})`)
              })
            })
            
            return parts.join('\n')
          }}
          researchQuestion="Analyze my storage configuration, identify any space or health issues, and suggest optimizations."
        />
      </div>
    </div>
    </ShowUUIDsContext.Provider>
    </CustomNamesContext.Provider>
  )
}
