// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * InstanceSwitch — top-bar dropdown for switching between Halbert instances.
 *
 * When multiple Halbert instances are running (e.g., host on :8000, home on :8001),
 * this component lets the user switch the frontend's API target without opening
 * a new browser tab. Selecting an instance calls setInstanceEndpoint() which
 * updates the apiBase for all subsequent fetches.
 */

import { useState, useEffect, useCallback } from 'react'
import { Monitor, Home as HomeIcon, ChevronDown, Plus, Check, X } from 'lucide-react'
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
  role === 'home' ? <HomeIcon className="h-4 w-4" /> : <Monitor className="h-4 w-4" />

const roleColor = (role: 'host' | 'home') =>
  role === 'home'
    ? 'text-amber-600 dark:text-amber-400'
    : 'text-slate-600 dark:text-slate-300'

export function InstanceSwitch() {
  const [currentInfo, setCurrentInfo] = useState<InstanceInfo | null>(null)
  const [paired, setPaired] = useState<PairedInstance[]>(loadPairedInstances)
  const [activeEndpoint, setActiveEndpoint] = useState<string | null>(getInstanceEndpoint())
  const [showAddForm, setShowAddForm] = useState(false)
  const [newLabel, setNewLabel] = useState('')
  const [newEndpoint, setNewEndpoint] = useState('http://localhost:8001')
  const [newRole, setNewRole] = useState<'host' | 'home'>('home')

  // Fetch current instance info
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
    // Reload the page to re-render all components with new API target
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

  const currentLabel = currentInfo?.display_name || 'Halbert'
  const currentRole = currentInfo?.role || 'host'

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="sm" className="h-7 gap-1.5 px-2 text-xs">
          <span className={cn('flex items-center gap-1.5', roleColor(currentRole))}>
            {roleIcon(currentRole)}
          </span>
          <span className="font-medium hidden sm:inline">{currentLabel}</span>
          <ChevronDown className="h-3 w-3 opacity-50" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-72">
        <DropdownMenuLabel className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
          Switch Halbert Instance
        </DropdownMenuLabel>
        <DropdownMenuSeparator />

        {/* Local instance */}
        <DropdownMenuItem
          onClick={() => handleSwitch(null)}
          className="flex items-center gap-2 cursor-pointer"
        >
          <span className={cn('flex-shrink-0', roleColor(currentRole))}>
            {roleIcon(currentRole)}
          </span>
          <div className="flex-1 min-w-0">
            <p className="text-xs font-medium truncate">{currentLabel} (Local)</p>
            <p className="text-[10px] text-muted-foreground truncate">
              {currentInfo?.scene_context || 'Local instance'}
            </p>
          </div>
          {!activeEndpoint && <Check className="h-3 w-3 text-success" />}
        </DropdownMenuItem>

        {/* Paired instances */}
        {paired.map((inst) => (
          <DropdownMenuItem
            key={inst.endpoint}
            onClick={() => handleSwitch(inst.endpoint)}
            className="flex items-center gap-2 cursor-pointer"
          >
            <span className={cn('flex-shrink-0', roleColor(inst.role))}>
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
            <span className="text-xs">Pair / Connect Another Instance...</span>
          </DropdownMenuItem>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
