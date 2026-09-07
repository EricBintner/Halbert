// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * EntityNodeBlock — entity name + node buttons at the top of the left rail.
 *
 * The rail is the single source of truth for "which machine am I looking at"
 * (HANDOFF-NODE-LIST-RAIL-DESIGN-2026-09-07, §3). This block replaces the
 * top-bar PresencePill's node-switching half:
 *
 * - The entity name is a *label*, not a button (§5R.1 Q6): the node button IS
 *   the landing page, and a second adjacent clickable going to the same place
 *   is the "Dashboard > Dashboard" trap this design exists to kill.
 * - The first button is always the node serving this dashboard (resolved from
 *   /api/instance/info — when an endpoint override is active, that IS the
 *   remote node). The rest come from /api/devices, revoked devices excluded
 *   (§5R.2: the endpoint returns them).
 * - Clicking the active node's button navigates to `/` — the node's landing
 *   page. Clicking any other node switches the API endpoint and reloads;
 *   the post-reload route fallback lives in `lib/routeCapabilities.ts` and is
 *   applied by the shell, not here.
 * - Peer buttons carry a presence dot derived from `last_seen` (§5R.1 Q3):
 *   seen within the last few minutes = filled, anything older = hollow. The
 *   serving node gets no dot — its reachability is self-evident: it served
 *   the page. No live probing from the rail; that is /compute's job.
 *
 * Multi-ENTITY grouping (Scenario C, Halbert + Halley blocks) is deliberately
 * not here: /api/devices carries no per-device persona_id, so it cannot be
 * built yet (§5R.3 N2). When peer records gain persona_id + display_name,
 * this component groups; until then every peer renders in the one block.
 *
 * Guest persona indication is NOT here either — that is the top bar's other
 * half of the old pill, kept as its own component (§5R.3 N1).
 */
import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Monitor, Home as HomeIcon } from 'lucide-react'
import { cn } from '@/lib/utils'
import { apiUrl, setInstanceEndpoint } from '@/lib/apiBase'
import { listDevices, type DeviceInfo } from '@/lib/peerApi'

/** The subset of /api/instance/info this block renders. */
interface ServingNodeInfo {
  display_name: string
  body_name: string
  role: 'host' | 'home'
  singular: boolean
}

/** A peer counts as recently-seen if last_seen is within this window. */
export const PRESENCE_WINDOW_MS = 5 * 60_000

/** How often the device list (and with it the presence dots) refreshes. */
export const DEVICES_REFRESH_MS = 60_000

function servingLabel(info: ServingNodeInfo): string {
  return info.body_name || (info.role === 'home' ? 'home' : 'workstation')
}

/** Text + dot state for a peer's presence, from its last_seen timestamp. */
function peerPresence(lastSeen: string | null): { recent: boolean; text: string } {
  if (!lastSeen) return { recent: false, text: 'never seen online' }
  const t = Date.parse(lastSeen)
  if (Number.isNaN(t)) return { recent: false, text: 'never seen online' }
  const ago = Date.now() - t
  if (ago <= PRESENCE_WINDOW_MS) return { recent: true, text: 'online now' }
  const mins = Math.round(ago / 60_000)
  return {
    recent: false,
    text: mins < 120 ? `last seen ${mins} min ago` : `last seen ${Math.round(mins / 60)} h ago`,
  }
}

export function EntityNodeBlock() {
  const navigate = useNavigate()
  const [info, setInfo] = useState<ServingNodeInfo | null>(null)
  const [peers, setPeers] = useState<DeviceInfo[]>([])

  // Who is serving this dashboard. Fetched once: switching nodes reloads the
  // page, so this component is remounted against the new node anyway.
  useEffect(() => {
    let cancelled = false
    fetch(apiUrl('/api/instance/info'))
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => { if (!cancelled && data) setInfo(data) })
      .catch(() => { /* offline race — the label keeps its fallback */ })
    return () => { cancelled = true }
  }, [])

  // The linked nodes. Refreshed slowly and on window focus — presence should
  // recover when the user comes back to the dashboard without a reload.
  const refreshDevices = useCallback(async () => {
    try {
      const state = await listDevices()
      setPeers(state.devices.filter((d) => !d.revoked && d.endpoint))
    } catch {
      // Non-fatal — the block just shows the serving node alone.
    }
  }, [])

  useEffect(() => {
    refreshDevices()
    const interval = setInterval(refreshDevices, DEVICES_REFRESH_MS)
    window.addEventListener('focus', refreshDevices)
    return () => {
      clearInterval(interval)
      window.removeEventListener('focus', refreshDevices)
    }
  }, [refreshDevices])

  const switchTo = (endpoint: string) => {
    setInstanceEndpoint(endpoint)
    // The fallback route (if the current page is unsupported on the target)
    // is applied by the shell after this reload, from routeCapabilities.ts.
    window.location.reload()
  }

  const entityName = info?.display_name || 'Halbert'
  const roleIcon = info?.role === 'home'
    ? <HomeIcon className="h-3.5 w-3.5" />
    : <Monitor className="h-3.5 w-3.5" />
  // The entity mode, carried where identity now lives. The old top-bar pill
  // said this in its tooltip; the pill is gone (§5R.3 N1), so the label says
  // it here — the ratified mode names (DECISIONS.md 2026-09-01).
  const modeTitle = info
    ? info.singular
      ? `${entityName} — Singular Entity (shared memory across machines)`
      : `${entityName} — Independent Node (own memory)`
    : entityName

  return (
    <div className="px-3 pt-3 pb-2 space-y-1.5" data-testid="entity-node-block">
      {/* Entity label — a name, not a button (Q6). */}
      <div className="text-sm font-semibold tracking-tight truncate" title={modeTitle}>
        {entityName}
      </div>

      <div className="flex flex-wrap gap-1" role="group" aria-label="Nodes">
        {/* Serving node — always active: this page's API is its API. */}
        <button
          type="button"
          aria-current="true"
          title="Serving this dashboard — click for its landing page"
          onClick={() => navigate('/')}
          className={cn(
            'flex items-center gap-1.5 rounded-md border border-border bg-accent px-2 py-1',
            'text-xs font-medium text-foreground hover:bg-accent/80 transition-colors',
          )}
        >
          <span className="text-muted-foreground shrink-0">{roleIcon}</span>
          <span className="truncate max-w-[140px]">
            {info ? servingLabel(info) : 'this machine'}
          </span>
        </button>

        {/* Linked nodes — presence dot + click to switch. */}
        {peers.map((peer) => {
          const presence = peerPresence(peer.last_seen)
          return (
            <button
              key={peer.node_id}
              type="button"
              title={`Switch to ${peer.node_name} — ${presence.text}`}
              onClick={() => switchTo(peer.endpoint as string)}
              className={cn(
                'flex items-center gap-1.5 rounded-md border border-border px-2 py-1',
                'text-xs text-muted-foreground hover:bg-accent hover:text-foreground transition-colors',
              )}
            >
              <span
                aria-hidden="true"
                className={cn(
                  'h-1.5 w-1.5 rounded-full shrink-0',
                  presence.recent
                    ? 'bg-success'
                    : 'border border-muted-foreground bg-transparent',
                )}
              />
              <span className="shrink-0 opacity-60">
                {peer.role === 'home'
                  ? <HomeIcon className="h-3.5 w-3.5" />
                  : <Monitor className="h-3.5 w-3.5" />}
              </span>
              <span className="truncate max-w-[140px]">{peer.node_name}</span>
            </button>
          )
        })}
      </div>
    </div>
  )
}
