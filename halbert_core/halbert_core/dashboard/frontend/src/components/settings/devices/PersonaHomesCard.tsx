// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * PersonaHomesCard — the Settings → Devices home of "Be someone else".
 *
 * The old PresencePill carried this in its dropdown; the pill's split
 * (HANDOFF-NODE-LIST-RAIL-DESIGN-2026-09-07 §5R.3 N1) moved it here, per
 * the founder: a user connects a persona home in Settings, and the
 * personas it offers appear in a list. The chat's become tool already told
 * users "Homes are added in Settings" — this is that Settings.
 *
 * Not a primary feature, and dressed accordingly: until a home is
 * connected, the entire surface is one muted line. The top bar shows
 * nothing at all (GuestPresenceIndicator renders only while a guest
 * fronts). A home's token is the peer token of the other machine — reveal
 * it there (Settings → Devices → identity, Advanced) and paste it here.
 */
import { useCallback, useEffect, useState } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { User, X } from 'lucide-react'
import { apiUrl } from '@/lib/apiBase'
import type { InstanceInfo } from '@/lib/instanceInfo'

/** A home this machine knows — GET /api/guest/homes. The token is never
 * returned by the backend, so it is not here either. */
interface GuestHome {
  base_url: string
  label: string
  profile: string
}

/** A persona this machine could wear, in some home it knows. */
interface AvailablePersona {
  persona_id: string
  name: string
  home_label: string
  base_url: string
}

/** What GET /api/guest/available answers. One home being unreachable must
 * not hide the others — failures are reported per home, not raised. */
interface AvailableCatalogue {
  personas: AvailablePersona[]
  unreachable: Array<{ home: string; error: string }>
}

/** The door: one muted line, easily missed, by design. */
function AddHomeDoor({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="text-xs text-muted-foreground/60 hover:text-muted-foreground transition-colors"
    >
      Add a persona home…
    </button>
  )
}

/** Connect a home: its base URL, a label to call it by, and its peer
 * token. Lives below the persona list it feeds. */
function AddHomeForm({ onAdded }: { onAdded: () => void }) {
  const [baseUrl, setBaseUrl] = useState('')
  const [label, setLabel] = useState('')
  const [token, setToken] = useState('')
  const [error, setError] = useState('')

  const submit = async () => {
    try {
      const res = await fetch(apiUrl('/api/guest/homes'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ base_url: baseUrl, label, token, profile: 'default' }),
      })
      if (!res.ok) {
        setError((await res.json().catch(() => null))?.detail || 'That did not work.')
        return
      }
      onAdded()
    } catch {
      setError('That did not work.')
    }
  }

  return (
    <div className="space-y-2">
      <div className="grid gap-2 sm:grid-cols-3">
        <div className="space-y-1">
          <Label htmlFor="persona-home-url" className="text-xs">Base URL</Label>
          <Input
            id="persona-home-url"
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            placeholder="http://h2:8002"
            className="h-8 text-xs font-mono"
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="persona-home-label" className="text-xs">Label</Label>
          <Input
            id="persona-home-label"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="H2"
            className="h-8 text-xs"
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="persona-home-token" className="text-xs">Token</Label>
          <Input
            id="persona-home-token"
            type="password"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            placeholder="its peer token"
            className="h-8 text-xs"
          />
        </div>
      </div>
      {error && <p className="text-xs text-destructive">{error}</p>}
      <Button
        size="sm"
        className="h-7 text-xs"
        disabled={!baseUrl.trim()}
        onClick={() => { setError(''); submit() }}
      >
        Add
      </Button>
    </div>
  )
}

export function PersonaHomesCard() {
  const [homes, setHomes] = useState<GuestHome[] | null>(null)
  const [catalogue, setCatalogue] = useState<AvailableCatalogue | null>(null)
  const [frontingName, setFrontingName] = useState<string | null>(null)
  const [showAdd, setShowAdd] = useState(false)

  const refresh = useCallback(async () => {
    try {
      const res = await fetch(apiUrl('/api/guest/homes'))
      const list: GuestHome[] = res.ok ? (await res.json()).homes || [] : []
      setHomes(list)
      if (list.length === 0) return
      // The personas are across the network — one fetch per refresh, and
      // only once there is a home to ask.
      const [avail, info] = await Promise.all([
        fetch(apiUrl('/api/guest/available')),
        fetch(apiUrl('/api/instance/info')),
      ])
      if (avail.ok) setCatalogue(await avail.json())
      const data: InstanceInfo | null = info.ok ? await info.json() : null
      setFrontingName(data?.fronting?.name ?? null)
    } catch {
      // Non-fatal: an empty surface beats a broken tab.
      setHomes([])
    }
  }, [])

  useEffect(() => { refresh() }, [refresh])

  const become = async (persona: AvailablePersona) => {
    try {
      // The name and the home, so a name in two houses is not a guess.
      await fetch(apiUrl('/api/guest/become'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: persona.name, base_url: persona.base_url }),
      })
    } catch {
      // Non-fatal — the next poll of /api/instance/info tells the truth
    }
  }

  const forget = async (home: GuestHome) => {
    try {
      await fetch(
        apiUrl(`/api/guest/homes?base_url=${encodeURIComponent(home.base_url)}`),
        { method: 'DELETE' },
      )
      await refresh()
    } catch {
      // Non-fatal — the list still shows what the last read knew
    }
  }

  // Loading: render nothing rather than flash a door that may not belong.
  if (homes === null) return null

  // Until a home is connected, the whole feature is one muted line.
  if (homes.length === 0) {
    if (!showAdd) return <AddHomeDoor onClick={() => setShowAdd(true)} />
    return (
      <div className="rounded-lg border border-border p-3 space-y-1">
        <p className="text-xs font-medium">Connect a persona home</p>
        <AddHomeForm onAdded={() => { setShowAdd(false); refresh() }} />
      </div>
    )
  }

  return (
    <Card>
      <CardHeader className="space-y-1.5">
        <CardTitle className="text-sm">Be someone else</CardTitle>
        <CardDescription>
          Personas this machine can wear, lent by the homes connected below.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {frontingName ? (
          // The old pill's rule, kept: wearing one face and being offered
          // another reads as a costume rack. End the session from the top
          // bar to become someone else.
          <p className="text-xs text-muted-foreground">
            {frontingName} is speaking right now — end the session from the
            top bar to become someone else.
          </p>
        ) : (
          <div className="space-y-1">
            {(catalogue?.personas ?? []).map((p) => (
              <button
                key={`${p.base_url}:${p.persona_id}`}
                type="button"
                onClick={() => become(p)}
                className="flex w-full items-center gap-2 rounded px-1 py-0.5 text-left text-xs hover:bg-accent"
              >
                <User className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                <span className="truncate">Be {p.name}</span>
                <span className="ml-auto text-[10px] text-muted-foreground truncate">
                  {p.home_label}
                </span>
              </button>
            ))}
            {(catalogue?.unreachable ?? []).map((u) => (
              <p key={u.home} className="text-[10px] text-muted-foreground/70">
                {u.home} did not answer
              </p>
            ))}
          </div>
        )}

        <div className="space-y-1 pt-1 border-t border-border">
          {homes.map((home) => (
            <div key={home.base_url} className="flex items-center gap-2 text-[10px] text-muted-foreground">
              <span className="font-medium text-foreground/80 truncate">{home.label || home.base_url}</span>
              <span className="truncate">{home.base_url}</span>
              <button
                type="button"
                aria-label={`Forget ${home.label || home.base_url}`}
                onClick={() => forget(home)}
                className="ml-auto p-0.5 rounded hover:bg-destructive/10 hover:text-destructive transition-colors"
              >
                <X className="h-3 w-3" />
              </button>
            </div>
          ))}
        </div>

        {showAdd ? (
          <AddHomeForm onAdded={() => { setShowAdd(false); refresh() }} />
        ) : (
          <AddHomeDoor onClick={() => setShowAdd(true)} />
        )}
      </CardContent>
    </Card>
  )
}