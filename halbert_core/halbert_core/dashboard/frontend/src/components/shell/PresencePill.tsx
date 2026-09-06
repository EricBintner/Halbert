// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * PresencePill — the top-bar identity indicator.
 *
 * Replaces InstanceSwitch. Shows the entity name + body name + entity mode
 * (Singular / Independent) in a compact pill. Clicking opens a dropdown to
 * switch to another linked body (which persists the API endpoint override
 * and reloads — see lib/apiBase.ts) or to manage linked devices via Settings.
 *
 * In Singular Entity mode, switching bodies changes the dashboard data source
 * but not the conversation — same entity, same memory, same threads. In
 * Independent mode, switching bodies switches everything.
 *
 * The pill text format:
 *   Singular:    "Halbert @ desk"  (entity name @ body name)
 *   Independent: "Halbert @ desk"  (same format — the mode badge is in the dropdown)
 *
 * When a guest persona is fronting (persona/guest.py) the pill reads
 *   "Halbert · as Ada"
 * and the dropdown says who lent the face and offers to take it off. The
 * machine's own name never changes — the user must always be able to tell
 * what is holding the tools (design I4), so both names show, never one.
 *
 * The connectivity dot is emerald when the local instance is reachable,
 * amber when it's a paired remote, gray when status is unknown.
 */
import { useState, useEffect, useCallback } from 'react'
import { Monitor, Home as HomeIcon, ChevronDown, Plus, Check, X, Settings, User } from 'lucide-react'
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
import { setInstanceEndpoint, getInstanceEndpoint, apiUrl } from '@/lib/apiBase'
import { useNavigate } from 'react-router-dom'

/** The session a guest persona is fronting for — /api/instance/info. */
export interface FrontingSession {
  session_id: string
  name: string
  offered_by: string
  offered_by_name: string
  started_at: string
  seconds_until_expiry: number
  active: boolean
  end_reason: string | null
}

export interface InstanceInfo {
  /** Non-null while a borrowed face is on. */
  fronting?: FrontingSession | null
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

/** How often the pill re-reads who is speaking. */
const GUEST_POLL_MS = 10_000

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
      // The local body resolves through apiUrl(): a bare relative URL would
      // resolve against tauri://localhost in the packaged app.
      const res = await fetch(
        endpoint ? `${endpoint}/api/instance/info` : apiUrl('/api/instance/info'),
      )
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

  // A guest session begins and ends without the pill asking, and its expiry
  // is evaluated lazily on the server (persona/guest.current_guest) — so
  // something has to read. The pill is that reader: polling keeps the face
  // shown here honest, and is what notices a lapsed heartbeat in the first
  // place, which is what announces the ending.
  useEffect(() => {
    const timer = setInterval(() => { refreshInfo(activeEndpoint) }, GUEST_POLL_MS)
    return () => clearInterval(timer)
  }, [activeEndpoint, refreshInfo])

  const handleEndGuest = async () => {
    try {
      const res = await fetch(apiUrl('/api/guest/end'), { method: 'POST' })
      if (res.ok) await refreshInfo(activeEndpoint)
    } catch {
      // Non-fatal — the next poll re-reads the truth
    }
  }

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

  const fronting = currentInfo?.fronting ?? null
  const guestName = fronting?.name || ''
  const lentBy = fronting ? (fronting.offered_by_name || fronting.offered_by) : ''

  // The pill text: "Entity @ body", or "Entity · as Guest" while a borrowed
  // face is on. The machine's name stays first in both: the costume is
  // additive, never a rename (I4). The body moves into the dropdown while a
  // guest fronts so the two names fit.
  const pillText = fronting
    ? `${entityName} · as ${guestName}`
    : `${entityName} @ ${bodyName}`

  const pillTitle = fronting
    ? `${guestName} is speaking for ${entityName} — ${entityName} keeps his tools, memory and rules`
    : singular
      ? `${entityName} — Singular Entity (shared memory across bodies)`
      : `${entityName} — Independent Node (own memory)`

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          className="flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium hover:bg-accent transition-colors"
          title={pillTitle}
        >
          {/* Connectivity dot */}
          <span
            className={cn(
              'h-1.5 w-1.5 rounded-full shrink-0',
              isLocal ? 'bg-success' : 'bg-warning',
            )}
            aria-hidden="true"
          />
          <span className="hidden sm:inline truncate max-w-[160px]">{pillText}</span>
          <ChevronDown className="h-3 w-3 opacity-50 shrink-0" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-72">
        {/* A borrowed face, while one is on. Named first, because the
            question it answers — who am I talking to, and what is
            underneath — is the one the user has when they open this. */}
        {fronting && (
          <>
            <DropdownMenuLabel className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
              Guest persona
            </DropdownMenuLabel>
            <div className="px-2 pb-2 space-y-1.5">
              <div className="flex items-center gap-2">
                <User className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                <div className="min-w-0">
                  <p className="text-xs font-medium truncate">{guestName}</p>
                  <p className="text-[10px] text-muted-foreground truncate">
                    lent by {lentBy}
                  </p>
                </div>
              </div>
              <p className="text-[10px] text-muted-foreground">
                {entityName} is underneath — same tools, same memory, same rules.
              </p>
              {isLocal && (
                <Button
                  variant="outline"
                  size="sm"
                  className="w-full h-7 text-xs"
                  onClick={handleEndGuest}
                >
                  End guest session
                </Button>
              )}
            </div>
            <DropdownMenuSeparator />
          </>
        )}

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
            <p className="text-xs font-medium truncate">{entityName} @ {bodyName} (Local)</p>
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
