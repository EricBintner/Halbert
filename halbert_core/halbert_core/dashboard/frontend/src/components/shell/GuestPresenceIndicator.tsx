// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * GuestPresenceIndicator — who is speaking when it is not the machine.
 *
 * The top-bar half of the old PresencePill that survives the rail redesign
 * (HANDOFF-NODE-LIST-RAIL-DESIGN-2026-09-07, §5R.3 N1). The pill's other
 * half — node switching, the hand-maintained paired-instances list, the
 * "Link Another Device" form — is gone: the rail's EntityNodeBlock owns
 * nodes, and pairing lives in Settings → Devices. "Be someone else" moved
 * to Settings too, where homes are connected (persona/guest_homes.py).
 *
 * Renders NOTHING while no guest fronts — the top bar keeps only what §6.2
 * enumerates (brand, voice, audio, progress pills, approvals badge, gear).
 * A session can begin without this component asking — the chat's become
 * tool, another home lending a face, Settings — so it polls
 * /api/instance/info and appears on its own when `fronting` shows up. That
 * polling is also what notices a lapsed heartbeat first, which is what
 * announces the ending.
 *
 * While a borrowed face is on, the indicator reads "Halbert · as Ada": both
 * names, never one, because the machine's own name must not disappear
 * behind a borrowed face (design I4) — the user can always tell what is
 * holding the tools. Handing private sources over and ending the session
 * are local-admin controls, so they render only for the machine sitting in
 * front of the user, not for a node the dashboard happens to be pointed at.
 */
import { useState, useEffect, useCallback } from 'react'
import { ChevronDown, User } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuLabel,
} from '@/components/ui/dropdown-menu'
import { apiUrl, getInstanceEndpoint } from '@/lib/apiBase'
import type { InstanceInfo, FrontingSession } from '@/lib/instanceInfo'

/** Something the user can hand to a guest for the rest of its session. */
export interface PrivateSource {
  id: string
  label: string
  kind: string
  owner: 'halbert' | 'guest' | 'drop'
  /** What handing THIS source over means, written by the server. The pill
   * used to carry its own copy of this sentence and the two had already
   * drifted — ours said "what it sees" with no source named, which reads as
   * every camera. One author, scoped to the source. */
  statement: string
}

/** How often the indicator re-reads who is speaking. */
const GUEST_POLL_MS = 10_000

export function GuestPresenceIndicator() {
  const [currentInfo, setCurrentInfo] = useState<InstanceInfo | null>(null)
  // The endpoint is constant for this component's life: switching nodes
  // reloads the page, so there is nothing to track.
  const activeEndpoint = getInstanceEndpoint()
  const isLocal = !activeEndpoint
  // What the user could hand over, and what they already have. Loaded only
  // while a guest fronts — there is nothing to hand over otherwise.
  const [sources, setSources] = useState<PrivateSource[]>([])
  const [handedOver, setHandedOver] = useState<Record<string, string>>({})

  const refreshInfo = useCallback(async (endpoint: string | null) => {
    try {
      // The local machine resolves through apiUrl(): a bare relative URL
      // would resolve against tauri://localhost in the packaged app.
      const res = await fetch(
        endpoint ? `${endpoint}/api/instance/info` : apiUrl('/api/instance/info'),
      )
      if (res.ok) {
        setCurrentInfo(await res.json())
      }
    } catch {
      // Non-fatal — may be offline
    }
  }, [])

  useEffect(() => {
    refreshInfo(activeEndpoint)
    // A guest session begins and ends without this component asking, and
    // its expiry is evaluated lazily on the server (persona/guest.py).
    const timer = setInterval(() => { refreshInfo(activeEndpoint) }, GUEST_POLL_MS)
    return () => clearInterval(timer)
  }, [activeEndpoint, refreshInfo])

  const loadPrivateSources = useCallback(async () => {
    try {
      const [cat, status] = await Promise.all([
        fetch(apiUrl('/api/guest/private/sources')),
        fetch(apiUrl('/api/guest')),
      ])
      setSources(cat.ok ? (await cat.json()).sources || [] : [])
      // Cleared on failure, not left standing. A stale tick beside a source
      // name says "this is handed over" about a session that may have ended,
      // which is the one thing this control must never say wrongly.
      setHandedOver(status.ok ? (await status.json()).private_sources || {} : {})
    } catch {
      setSources([])
      setHandedOver({})
    }
  }, [])

  const handleHandOver = async (src: PrivateSource, give: boolean) => {
    const path = give ? '/api/guest/private/assign' : '/api/guest/private/release'
    try {
      const res = await fetch(apiUrl(path), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source_id: src.id }),
      })
      if (res.ok) setHandedOver((await res.json()).private_sources || {})
    } catch {
      // Non-fatal — the next open re-reads the truth
    }
  }

  const fronting: FrontingSession | null = currentInfo?.fronting ?? null
  useEffect(() => {
    if (fronting && isLocal) {
      loadPrivateSources()
    } else {
      // No guest, or a machine that is not this one: nothing is handed
      // over, and the ticks must not outlive the session they described.
      setSources([])
      setHandedOver({})
    }
  }, [fronting?.session_id, isLocal, loadPrivateSources])

  const handleEndGuest = async () => {
    try {
      const res = await fetch(apiUrl('/api/guest/end'), { method: 'POST' })
      if (res.ok) await refreshInfo(activeEndpoint)
    } catch {
      // Non-fatal — the next poll re-reads the truth
    }
  }

  // Idle means invisible: no identity text (the rail owns that), no empty
  // trigger waiting to be useful. The top bar stays as §6.2 enumerates it.
  if (!fronting) return null

  const entityName = currentInfo?.display_name || 'Halbert'
  const guestName = fronting.name
  const lentBy = fronting.offered_by_name || fronting.offered_by

  // I4: the machine's own name stays first — the costume is additive, never
  // a rename. "Ada" alone would be the failure.
  const pillText = `${entityName} · as ${guestName}`
  const pillTitle =
    `${guestName} is speaking for ${entityName} — ${entityName} keeps his tools, memory and rules`

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          className="flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium hover:bg-accent transition-colors"
          title={pillTitle}
        >
          <User className="h-3 w-3 text-muted-foreground shrink-0" />
          <span className="hidden sm:inline truncate max-w-[160px]">{pillText}</span>
          <ChevronDown className="h-3 w-3 opacity-50 shrink-0" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-72">
        {/* The borrowed face, named first, because the question it answers —
            who am I talking to, and what is underneath — is the one the user
            has when they open this. */}
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
                {fronting.home?.label ? ` · home: ${fronting.home.label}` : ''}
              </p>
            </div>
          </div>
          <p className="text-[10px] text-muted-foreground">
            {entityName} is underneath — same tools, same memory, same rules.
          </p>
          {isLocal && sources.length > 0 && (
            <div className="space-y-1 pt-1">
              <p className="text-[10px] font-medium">What {guestName} may have</p>
              {Object.keys(handedOver).length === 0 && sources[0] && (
                /* The private-mode review's P6, in front of the click that
                   makes it true. A toggle labelled "private" with no stated
                   scope is a promise the system cannot keep — the cameras,
                   the microphone and the house sensors do not stop.
                   Server-written, and each row's own sentence is on its
                   tooltip, because handing over the desk webcam does not
                   stop the patio camera. */
                <p className="text-[10px] text-muted-foreground">
                  {sources[0].statement}
                </p>
              )}
              {sources.map((src) => (
                <label
                  key={src.id}
                  title={src.statement}
                  className="flex items-center gap-2 text-[11px]"
                >
                  <input
                    type="checkbox"
                    aria-label={`Hand ${src.label} to ${guestName}`}
                    checked={handedOver[src.id] === 'guest'}
                    onChange={(e) => handleHandOver(src, e.target.checked)}
                  />
                  <span className="truncate">{src.label}</span>
                </label>
              ))}
            </div>
          )}
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
      </DropdownMenuContent>
    </DropdownMenu>
  )
}