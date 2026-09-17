// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { useEffect, useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { apiUrl } from '@/lib/apiBase'

const API_BASE = apiUrl('/api')

/** The window the preview reads. The spec's week (§15) — the API accepts
 *  1–30 and the copy reads the window back off the response, so this is the
 *  spec's number, not a placeholder for a control. */
const PREVIEW_DAYS = 7
const PREVIEW_ITEMS = 20
/** Below the hover-intent threshold: a deliberate hover still feels instant,
 *  while a sweep across the rungs asks the log for nothing. */
const PREVIEW_DEBOUNCE_MS = 200

export interface PresenceRung {
  level: number
  name: string
  says: string
  why: string
  classifiable: boolean   // every class this rung newly admits is one I can describe something as today
}

interface PreviewItem {
  attempt_id: string
  ts: string
  source: string
  verdict: 'said' | 'shown' | 'held'
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
 * beneath. Copy comes from the API — the curve is data (D8). The preview
 * reads the shadow log at the hovered or dragged level, so the person can
 * see the machine's judgement before trusting it. Nothing here changes live
 * behaviour in slice 1: the level is read by the shadow lane only, and the
 * proactivity card below still governs what is heard (D1, D11).
 *
 * The fine adjust writes once, when the drag ends: a range input's onChange
 * fires per step, and each write is a config save. The dragged value lives
 * in ``draft`` until the saved ``level`` catches up.
 */
export function PresenceCard({ level, saving, onChange }: Props) {
  const [rungs, setRungs] = useState<PresenceRung[]>([])
  const [rungsFailed, setRungsFailed] = useState(false)
  const [hover, setHover] = useState<number | null>(null)
  const [draft, setDraft] = useState<number | null>(null)
  const [preview, setPreview] = useState<Preview | null>(null)
  const [previewError, setPreviewError] = useState<string | null>(null)

  useEffect(() => {
    fetch(`${API_BASE}/being/presence/rungs`)
      .then((r) => (r.ok ? r.json() : null))
      .then((body) => { setRungs(body?.rungs ?? []); setRungsFailed(!body?.rungs) })
      .catch(() => { setRungs([]); setRungsFailed(true) })
  }, [])

  // The drag's value until the save round-trips; cleared when it does.
  useEffect(() => { setDraft(null) }, [level])

  const sliderValue = draft ?? level
  const shown = hover ?? sliderValue

  useEffect(() => {
    const controller = new AbortController()
    const timer = setTimeout(() => {
      fetch(`${API_BASE}/being/presence/preview?level=${shown}&days=${PREVIEW_DAYS}&limit=${PREVIEW_ITEMS}`,
            { signal: controller.signal })
        .then((r) => {
          if (r.ok) return r.json()
          throw new Error(r.status === 503
            ? "I can't read the log — the attunement engine isn't installed here."
            : 'I could not read the log just now.')
        })
        .then((body) => { setPreview(body); setPreviewError(null) })
        .catch((err) => {
          if (err?.name === 'AbortError') return
          setPreview(null)
          setPreviewError(err?.message || 'I could not read the log just now.')
        })
    }, PREVIEW_DEBOUNCE_MS)
    return () => { clearTimeout(timer); controller.abort() }
  }, [shown])

  const current = [...rungs].reverse().find((r) => r.level <= shown) ?? null

  const commit = () => {
    if (draft !== null && draft !== level) onChange({ presence: draft })
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Presence</CardTitle>
        <CardDescription>How much I bring up on my own. Nothing here changes what you hear yet — it changes what the preview shows.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          <Label id="presence-rungs-label">How present</Label>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-7" aria-labelledby="presence-rungs-label">
            {rungs.map((r) => (
              <Button
                key={r.name}
                variant={current?.name === r.name ? 'default' : 'outline'}
                aria-pressed={current?.name === r.name}
                onClick={() => onChange({ presence: r.level })}
                onMouseEnter={() => setHover(r.level)}
                onMouseLeave={() => setHover(null)}
                onFocus={() => setHover(r.level)}
                onBlur={() => setHover(null)}
                disabled={saving}
                className="h-auto flex-col items-start whitespace-normal text-left"
              >
                <span className="capitalize">
                  {r.name}
                  {!r.classifiable && <span className="font-normal text-muted-foreground"> (not yet)</span>}
                </span>
                <span className="text-xs font-normal text-muted-foreground">{r.says}</span>
              </Button>
            ))}
          </div>
          {rungsFailed && <p className="text-xs text-muted-foreground">I could not read the levels just now; the fine adjust below still works.</p>}
          {current && <p className="text-xs text-muted-foreground">{current.why}{!current.classifiable && " Not yet: nothing I do is described as what this rung admits."}</p>}
        </div>

        <div className="space-y-2">
          <Label htmlFor="presence-fine">Fine adjust: {sliderValue}</Label>
          <input
            id="presence-fine"
            type="range"
            min={0}
            max={10}
            step={1}
            value={sliderValue}
            onChange={(e) => setDraft(Number(e.target.value))}
            onPointerUp={commit}
            onKeyUp={commit}
            onBlur={commit}
            className="w-full"
            aria-valuetext={`${sliderValue}${current ? `, ${current.name}` : ''}`}
          />
        </div>

        <div className="space-y-1 rounded-md border p-3">
          <p className="text-sm">
            {preview
              ? `Over the last ${preview.days} days at ${preview.level}, I would have said ${preview.said}, shown ${preview.shown}, and held ${preview.held}${preview.budget_per_day != null ? `, up to ${preview.budget_per_day} a day` : ''}.`
              : previewError || 'No preview yet.'}
          </p>
          {preview && preview.unclassified > 0 && (
            <p className="text-xs text-muted-foreground">{preview.unclassified} rows I can't place, and haven't counted.</p>
          )}
          {preview && preview.undated > 0 && (
            <p className="text-xs text-muted-foreground">{preview.undated} rows carry no readable time, and haven't counted.</p>
          )}
          {preview && preview.truncated && (
            <p className="text-xs text-muted-foreground">Only the newest rows were read; the oldest days may be under-counted.</p>
          )}
          {preview && preview.items.length > 0 && (
            <ul className="mt-2 max-h-48 space-y-1 overflow-auto text-xs">
              {preview.items.map((i) => {
                const disagrees = (i.verdict === 'said') !== (i.live_outcome === 'speak')
                return (
                  <li key={i.attempt_id} className="flex justify-between gap-2">
                    <span className="text-muted-foreground">{new Date(i.ts).toLocaleString()}</span>
                    <span>{i.source}</span>
                    <span className="capitalize">{i.verdict}</span>
                    {disagrees && (
                      <span className="text-muted-foreground">{i.live_outcome === 'speak' ? 'I said it' : 'I stayed quiet'}</span>
                    )}
                  </li>
                )
              })}
            </ul>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
