// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * PresencePill — the top-bar identity indicator.
 *
 * Replaces InstanceSwitch. Shows the entity name + body name + entity mode
 * (Singular / Independent) in a compact pill. Clicking opens a dropdown to
 * switch to another paired body (which changes the API endpoint and reloads)
 * or to manage linked devices via Settings.
 *
 * In Singular Entity mode, switching bodies changes the dashboard data source
 * but not the conversation — same entity, same memory, same threads. In
 * Independent mode, switching bodies switches everything.
 *
 * The pill text format:
 *   Singular:    "Halbert @ desk"  (entity name @ body name)
 *   Independent: "Halbert @ desk"  (same format — the mode badge is in the dropdown)
 *
 * The connectivity dot is emerald when the local instance is reachable,
 * amber when it's a paired remote, gray when status is unknown.
 */
import { useState, useEffect, useCallback } from 'react'
import { Monitor, Home as HomeIcon, ChevronDown, Plus, Check, X, Settings } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuLabel,
} from '@/components/ui/dropdown-menu'
import { setInstanceEndpoint, getInstanceEndpoint } from '@/lib/apiBase'
import { useNavigate } from 'react-router-dom'

export interface InstanceInfo {
  persona_id: string
  scene_context: string
  role: 'host' | 'home'
  variant: string
  display_name: string
  port: number
  features: {
    home: boolean
    gpu: boolean
    development: boolean
    wyoming_port: number
  }
  data_dir: string
  config_dir: string
  body_name: string
  singular: boolean
}

interface PairedInstance {
  label: string
  endpoint: string
  role: 'host' | 'home'
}

const STORAGE_KEY = 'halbert:paired-instances'

function loadPairedInstances(): PairedInstance[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    return JSON.parse(raw)
  } catch {
    return []
  }
}

function savePairedInstances(instances: PairedInstance[]): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(instances))
}

const roleIcon = (role: 'host' | 'home') =>
  role === 'home' ? <HomeIcon className="h-3.5 w-3.5" /> : <Monitor className="h-3.5 w-3.5" />

export function PresencePill() {
  const [currentInfo, setCurrentInfo] = useState<InstanceInfo | null>(null)
  const [paired, setPaired] = useState<PairedInstance[]>(loadPairedInstances)
  const [activeEndpoint, setActiveEndpoint] = useState<string | null>(getInstanceEndpoint())
  const [showAddForm, setShowAddForm] = useState(false)
  const [newLabel, setNewLabel] = useState('')
  const [newEndpoint, setNewEndpoint] = useState('http://localhost:8001')
  const [newRole, setNewRole] = useState<'host' | 'home'>('home')
  const navigate = useNavigate()

  const refreshInfo = useCallback(async (endpoint: string | null) => {
    try {
      const base = endpoint || ''
      const res = await fetch(`${base}/api/instance/info`)
      if (res.ok) {
        const data = await res.json()
        setCurrentInfo(data)
      }
    } catch {
      // Non-fatal — may be offline
    }
  }, [])

  useEffect(() => {
    refreshInfo(activeEndpoint)
  }, [activeEndpoint, refreshInfo])

  const handleSwitch = (endpoint: string | null) => {
    setInstanceEndpoint(endpoint)
    setActiveEndpoint(endpoint)
    refreshInfo(endpoint)
    window.location.reload()
  }

  const handleAddInstance = () => {
    if (!newLabel.trim() || !newEndpoint.trim()) return
    const updated = [...paired, { label: newLabel, endpoint: newEndpoint, role: newRole }]
    setPaired(updated)
    savePairedInstances(updated)
    setShowAddForm(false)
    setNewLabel('')
    setNewEndpoint('http://localhost:8001')
  }

  const handleRemoveInstance = (endpoint: string) => {
    const updated = paired.filter((p) => p.endpoint !== endpoint)
    setPaired(updated)
    savePairedInstances(updated)
  }

  const entityName = currentInfo?.display_name || 'Halbert'
  const bodyName = currentInfo?.body_name || (currentInfo?.role === 'home' ? 'home' : 'workstation')
  const singular = currentInfo?.singular ?? false
  const isLocal = !activeEndpoint

  // The pill text: "Entity @ body"
  const pillText = `${entityName} @ ${bodyName}`

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          className="flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium hover:bg-accent transition-colors"
          title={singular
            ? `${entityName} — Singular Entity (shared memory across bodies)`
            : `${entityName} — Independent Node (own memory)`}
        >
          {/* Connectivity dot */}
          <span
            className={cn(
              'h-1.5 w-1.5 rounded-full shrink-0',
              isLocal ? 'bg-success' : 'bg-amber-500',
            )}
            aria-hidden="true"
          />
          <span className="hidden sm:inline truncate max-w-[160px]">{pillText}</span>
          <ChevronDown className="h-3 w-3 opacity-50 shrink-0" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-72">
        <DropdownMenuLabel className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
          {singular ? 'Singular Entity — one Halbert, many bodies' : 'Independent Node'}
        </DropdownMenuLabel>
        <DropdownMenuSeparator />

        {/* Local instance */}
        <DropdownMenuItem
          onClick={() => handleSwitch(null)}
          className="flex items-center gap-2 cursor-pointer"
        >
          <span className="flex-shrink-0 text-muted-foreground">
            {roleIcon(currentInfo?.role || 'host')}
          </span>
          <div className="flex-1 min-w-0">
            <p className="text-xs font-medium truncate">{pillText} (Local)</p>
            <p className="text-[10px] text-muted-foreground truncate">
              {currentInfo?.scene_context || 'This machine'}
            </p>
          </div>
          {isLocal && <Check className="h-3 w-3 text-success" />}
        </DropdownMenuItem>

        {/* Paired instances */}
        {paired.map((inst) => (
          <DropdownMenuItem
            key={inst.endpoint}
            onClick={() => handleSwitch(inst.endpoint)}
            className="flex items-center gap-2 cursor-pointer"
          >
            <span className="flex-shrink-0 text-muted-foreground">
              {roleIcon(inst.role)}
            </span>
            <div className="flex-1 min-w-0">
              <p className="text-xs font-medium truncate">{inst.label}</p>
              <p className="text-[10px] text-muted-foreground truncate">{inst.endpoint}</p>
            </div>
            {activeEndpoint === inst.endpoint && <Check className="h-3 w-3 text-success" />}
            <button
              onClick={(e) => { e.stopPropagation(); handleRemoveInstance(inst.endpoint) }}
              className="ml-auto flex-shrink-0 p-0.5 rounded hover:bg-destructive/10 text-muted-foreground hover:text-destructive"
              aria-label={`Remove ${inst.label}`}
            >
              <X className="h-3 w-3" />
            </button>
          </DropdownMenuItem>
        ))}

        <DropdownMenuSeparator />

        {/* Manage linked devices — navigates to Settings > Devices */}
        <DropdownMenuItem
          onClick={() => navigate('/settings?tab=devices')}
          className="flex items-center gap-2 cursor-pointer"
        >
          <Settings className="h-4 w-4" />
          <span className="text-xs">Manage Linked Devices...</span>
        </DropdownMenuItem>

        {/* Add new instance */}
        {showAddForm ? (
          <div className="p-2 space-y-2">
            <input
              type="text"
              placeholder="Label (e.g., Home Server)"
              value={newLabel}
              onChange={(e) => setNewLabel(e.target.value)}
              className="w-full px-2 py-1 text-xs rounded border border-border bg-background"
            />
            <input
              type="text"
              placeholder="http://host:port"
              value={newEndpoint}
              onChange={(e) => setNewEndpoint(e.target.value)}
              className="w-full px-2 py-1 text-xs rounded border border-border bg-background font-mono"
            />
            <div className="flex gap-1">
              <Button
                size="sm"
                variant="outline"
                className="h-6 text-[10px] flex-1"
                onClick={() => setNewRole('home')}
              >
                Home
              </Button>
              <Button
                size="sm"
                variant="outline"
                className="h-6 text-[10px] flex-1"
                onClick={() => setNewRole('host')}
              >
                Host
              </Button>
              <Button
                size="sm"
                className="h-6 text-[10px]"
                onClick={handleAddInstance}
                disabled={!newLabel.trim() || !newEndpoint.trim()}
              >
                Add
              </Button>
            </div>
          </div>
        ) : (
          <DropdownMenuItem
            onClick={() => setShowAddForm(true)}
            className="flex items-center gap-2 cursor-pointer"
          >
            <Plus className="h-4 w-4" />
            <span className="text-xs">Link Another Device...</span>
          </DropdownMenuItem>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
