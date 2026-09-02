// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * The web-search switch (C3-08 / C3-16): the one outbound setting the
 * agent path has today, shown where it can be seen and turned off.
 *
 * Self-contained on purpose: it owns its GET/PUT against
 * /api/settings/web-search so the System tab's props and Settings.tsx's
 * per-tab loaders do not grow for one boolean. The backend answers with
 * both the saved setting (`enabled`) and what the capability registry
 * resolved (`effective`); they differ only when being.yml pins the
 * capability, and the card says so rather than showing a switch that
 * silently does nothing.
 */
import { useEffect, useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { apiUrl } from '@/lib/apiBase'
import { Globe } from 'lucide-react'

interface WebSearchState {
  enabled: boolean
  effective: boolean
}

const READ_ERROR = 'Could not read the web search setting.'
const SAVE_ERROR = 'Could not save the web search setting.'

function parseState(data: unknown): WebSearchState | null {
  if (!data || typeof data !== 'object') return null
  const d = data as Record<string, unknown>
  if (typeof d.enabled !== 'boolean') return null
  return {
    enabled: d.enabled,
    effective: typeof d.effective === 'boolean' ? d.effective : d.enabled,
  }
}

export function WebSearchSwitch() {
  const [state, setState] = useState<WebSearchState | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      try {
        const res = await fetch(apiUrl('/api/settings/web-search'))
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const parsed = parseState(await res.json())
        if (!parsed) throw new Error('unexpected response')
        if (!cancelled) setState(parsed)
      } catch (err) {
        console.error('Failed to load web search setting:', err)
        if (!cancelled) setError(READ_ERROR)
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [])

  const toggle = async (enabled: boolean) => {
    setBusy(true)
    setError(null)
    try {
      const res = await fetch(apiUrl('/api/settings/web-search'), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const parsed = parseState(await res.json())
      if (!parsed) throw new Error('unexpected response')
      setState(parsed)
    } catch (err) {
      console.error('Failed to save web search setting:', err)
      setError(SAVE_ERROR)
    } finally {
      setBusy(false)
    }
  }

  const pinnedOff = state !== null && state.enabled && !state.effective

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Globe className="h-5 w-5" />
          Network
        </CardTitle>
        <CardDescription>
          What may leave this machine. Everything here is off until you turn it on.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        <div className="flex items-center justify-between gap-4">
          <div>
            <Label htmlFor="web-search-toggle">Web search (sends query text to a search engine)</Label>
            <p className="text-xs text-muted-foreground mt-1">
              When on, the assistant may look things up on the web; the search text is sent to the
              configured search engine. Off by default.
            </p>
          </div>
          <Switch
            id="web-search-toggle"
            checked={state?.enabled ?? false}
            onCheckedChange={toggle}
            disabled={state === null || busy}
          />
        </div>
        {pinnedOff && (
          <p className="text-xs text-warning">
            Pinned off by being.yml (capabilities: web: false); the switch has no effect until that
            override is removed.
          </p>
        )}
        {error && <p className="text-xs text-error">{error}</p>}
      </CardContent>
    </Card>
  )
}
