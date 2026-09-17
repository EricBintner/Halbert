// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { useEffect, useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { apiUrl } from '@/lib/apiBase'

const API_BASE = apiUrl('/api')

export interface PresenceRung {
  level: number
  name: string
  says: string
  why: string
  classifiable: boolean   // every class this rung newly admits is one I can describe something as today
  admits: string[]
  channel: Record<string, string>
}

interface PreviewItem {
  attempt_id: string
  ts: string
  source: string
  severity: string
  context_key: string | null
  impulse_class: string
  verdict: 'said' | 'shown' | 'held'
  channel: string | null
  live_outcome: string
}

interface Preview {
  level: number
  days: number
  said: number
  shown: number
  held: number
  unclassified: number
  undated: number
  budget_per_day: number | null
  truncated: boolean
  items: PreviewItem[]
}

interface Props {
  level: number
  saving: boolean
  onChange: (updates: Record<string, unknown>) => void
}

/**
 * The presence control (spec 2026-09-16 v2 §15).
 *
 * Seven named rungs are the primary control; the 0–10 fine adjust sits
 * beneath. Copy comes from the API — the curve is data. The preview reads
 * the shadow log at the hovered level, so the person can see the machine's
 * judgement before trusting it. Nothing here changes live behaviour in
 * slice 1: the level is read by the shadow lane only.
 */
export function PresenceCard({ level, saving, onChange }: Props) {
  const [rungs, setRungs] = useState<PresenceRung[]>([])
  const [hover, setHover] = useState<number | null>(null)
  const [preview, setPreview] = useState<Preview | null>(null)

  useEffect(() => {
    fetch(`${API_BASE}/being/presence/rungs`)
      .then((r) => (r.ok ? r.json() : null))
      .then((body) => setRungs(body?.rungs ?? []))
      .catch(() => setRungs([]))
  }, [])

  const shown = hover ?? level
  useEffect(() => {
    let live = true
    fetch(`${API_BASE}/being/presence/preview?level=${shown}&days=7`)
      .then((r) => (r.ok ? r.json() : null))
      .then((body) => { if (live) setPreview(body) })
      .catch(() => { if (live) setPreview(null) })
    return () => { live = false }
  }, [shown])

  const current = [...rungs].reverse().find((r) => r.level <= shown) ?? null

  return (
    <Card>
      <CardHeader>
        <CardTitle>Presence</CardTitle>
        <CardDescription>How much I bring up on my own. Nothing here changes what you hear yet — it changes what the preview shows.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          <Label>How present</Label>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-7">
            {rungs.map((r) => (
              <Button
                key={r.name}
                variant={current?.name === r.name ? 'default' : 'outline'}
                onClick={() => onChange({ presence: r.level })}
                onMouseEnter={() => setHover(r.level)}
                onMouseLeave={() => setHover(null)}
                disabled={saving}
                data-classifiable={r.classifiable ? 'true' : 'false'}
                aria-label={r.name}
                className="h-auto flex-col items-start whitespace-normal text-left"
              >
                <span className="capitalize">{r.name}</span>
                <span className="text-xs font-normal text-muted-foreground">{r.says}</span>
              </Button>
            ))}
          </div>
          {current && <p className="text-xs text-muted-foreground">{current.why}{!current.classifiable && " Not yet: nothing I do is described as what this rung admits."}</p>}
        </div>

        <div className="space-y-2">
          <Label htmlFor="presence-fine">Fine adjust: {shown}</Label>
          <input
            id="presence-fine"
            type="range"
            min={0}
            max={10}
            step={1}
            value={level}
            disabled={saving}
            onChange={(e) => onChange({ presence: Number(e.target.value) })}
            onMouseMove={(e) => setHover(Number((e.target as HTMLInputElement).value))}
            onMouseLeave={() => setHover(null)}
            className="w-full"
            aria-valuemin={0}
            aria-valuemax={10}
            aria-valuenow={level}
          />
        </div>

        <div className="space-y-1 rounded-md border p-3">
          <p className="text-sm">
            {preview
              ? `Over the last ${preview.days} days at ${preview.level}, I would have said ${preview.said}, shown ${preview.shown}, and held ${preview.held}${preview.budget_per_day != null ? `, up to ${preview.budget_per_day} a day` : ''}.`
              : 'No preview yet.'}
          </p>
          {preview && preview.unclassified > 0 && (
            <p className="text-xs text-muted-foreground">{preview.unclassified} older rows predate the presence log and are not counted.</p>
          )}
          {preview && preview.truncated && (
            <p className="text-xs text-muted-foreground">Only the newest rows were read; the oldest days may be under-counted.</p>
          )}
          {preview && preview.items.length > 0 && (
            <ul className="mt-2 max-h-48 space-y-1 overflow-auto text-xs">
              {preview.items.slice(0, 20).map((i) => (
                <li key={i.attempt_id} className="flex justify-between gap-2">
                  <span className="text-muted-foreground">{new Date(i.ts).toLocaleString()}</span>
                  <span>{i.source} · {i.impulse_class}</span>
                  <span className="capitalize">{i.verdict}{i.channel ? ` (${i.channel})` : ''}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
