// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * AboutYouCard — Settings → Knowledge → "What I remember about you".
 *
 * RQ-5. It sits beside "what Halbert knows about itself" because it is the
 * mirror of it: the same page, the other subject. A person who can inspect
 * what the machine believes about the machine should not have to go
 * somewhere else to inspect what it believes about them.
 *
 * Three rules this component exists to hold, all of them visible:
 *
 * - **Two verbs, named apart** (RQ-6). "Stop using this" keeps the record
 *   and stops it being used; "Forget" destroys it. One button labelled
 *   "delete" that did the reversible thing would be a lie, and one that did
 *   the irreversible thing without saying so would be worse.
 * - **A statement of reach, before the click.** Erasure reaches two planes
 *   of several. The limits come from the API rather than being written here
 *   so the sentence a person reads is the one the code can actually keep,
 *   and they read it in the confirm dialog, not after.
 * - **No confidence number, ever.** The engine derives one from provenance.
 *   Showing it would invite a person to weigh something the system cannot
 *   justify numerically. How it was learned, and when, is what they can
 *   actually check — so that is what the row shows.
 *
 * Empty is the normal state and is dressed as such: one muted line, no
 * call to action. Nothing here should read as an invitation to feed it.
 */
import { useCallback, useEffect, useState } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { RefreshCw } from 'lucide-react'
import { apiUrl } from '@/lib/apiBase'

/** One remembered thing. Deliberately carries no confidence field. */
export interface RememberedItem {
  memory_id: string
  topic: string
  /** "You told me" / "Noticed across 3 conversations…" — never a score. */
  learned: string
  /** YYYY-MM-DD, or '' when the row never carried a date. */
  when: string
  /** The person's own words, which is what MEM-06 requires it to be. */
  reason: string
  status: string
  forgotten: boolean
}

interface AboutYouResponse {
  status: string
  items: RememberedItem[]
  count: number
  /** What forgetting does not reach. Read from the API, not written here. */
  limits: string
}

const BASE = apiUrl('/api/memory/about-you')

/** A row, and its two verbs. */
function Row({
  item,
  busy,
  onStopUsing,
  onRememberAgain,
  onForget,
}: {
  item: RememberedItem
  busy: boolean
  onStopUsing: () => void
  onRememberAgain: () => void
  onForget: () => void
}) {
  return (
    <li className="flex items-start justify-between gap-4 py-3 border-b border-border last:border-b-0">
      <div className="min-w-0">
        <div className={`text-sm ${item.forgotten ? 'text-muted-foreground line-through' : ''}`}>
          {item.topic}
        </div>
        <div className="text-xs text-muted-foreground mt-0.5">
          {item.learned}
          {item.when ? ` · ${item.when}` : ''}
        </div>
        {/* Their words, quoted. The reason is why this is here at all, and a
            person checking the list needs to recognise having said it. */}
        {item.reason ? (
          <div className="text-xs text-muted-foreground/70 mt-1 italic truncate">
            “{item.reason}”
          </div>
        ) : null}
      </div>
      <div className="flex items-center gap-2 shrink-0">
        {item.forgotten ? (
          <Button variant="ghost" size="sm" disabled={busy} onClick={onRememberAgain}>
            Remember again
          </Button>
        ) : (
          <Button variant="ghost" size="sm" disabled={busy} onClick={onStopUsing}>
            Stop using this
          </Button>
        )}
        <Button variant="ghost" size="sm" disabled={busy} onClick={onForget}>
          Forget
        </Button>
      </div>
    </li>
  )
}

export function AboutYouCard() {
  const [items, setItems] = useState<RememberedItem[]>([])
  const [limits, setLimits] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [showForgotten, setShowForgotten] = useState(false)
  /** Why the list could not be read. Kept apart from an action's failure:
   *  the reload that follows an action would otherwise wipe the report of
   *  what that action failed to do, which is the one message a person
   *  asking for erasure most needs to see. */
  const [readError, setReadError] = useState('')
  const [actionError, setActionError] = useState('')
  const [confirming, setConfirming] = useState<RememberedItem | null>(null)
  /** What the last erase actually reached. Shown, not assumed. */
  const [report, setReport] = useState('')

  const load = useCallback(async (withForgotten: boolean) => {
    setLoading(true)
    setReadError('')
    try {
      const res = await fetch(`${BASE}?include_forgotten=${withForgotten}`)
      if (!res.ok) throw new Error(String(res.status))
      const body: AboutYouResponse = await res.json()
      setItems(body.items || [])
      setLimits(body.limits || '')
      // A store that cannot be read is not an empty store, and must never
      // be shown as one: "nothing is recorded about you" is a claim.
      if (body.status !== 'ok') {
        setReadError('I could not read what is recorded about you just now.')
      }
    } catch {
      setReadError('I could not read what is recorded about you just now.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { void load(showForgotten) }, [load, showForgotten])

  const act = useCallback(async (memoryId: string, verb: string) => {
    setBusy(true)
    setReport('')
    setActionError('')
    try {
      const res = await fetch(`${BASE}/${encodeURIComponent(memoryId)}/${verb}`, {
        method: 'POST',
      })
      const body = await res.json()
      if (!body.complete) {
        // Never a silent partial. A person who asked to be forgotten is
        // owed the list of what was not reached.
        setActionError(
          `That did not finish: ${(body.errors || []).join('; ') || 'unknown reason'}`,
        )
      } else if (verb === 'forget') {
        setReport(body.limits || '')
      }
    } catch {
      setActionError('That did not finish. Nothing was changed.')
    } finally {
      setBusy(false)
      await load(showForgotten)
    }
  }, [load, showForgotten])

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          <span>What I remember about you</span>
          <Button
            variant="ghost"
            size="sm"
            aria-label="Refresh"
            onClick={() => void load(showForgotten)}
          >
            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          </Button>
        </CardTitle>
        <CardDescription>
          Everything recorded about you, and how each one was learned. I only
          record what you ask me to remember.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {readError || actionError ? (
          <div className="text-sm text-destructive mb-3">
            {readError || actionError}
          </div>
        ) : null}

        {loading && items.length === 0 ? (
          <div className="text-sm text-muted-foreground">Reading…</div>
        ) : readError ? (
          /* An unreadable store is not an empty one. "Nothing is recorded
             about you" is a claim, and the error above is the honest
             alternative to making it falsely. */
          null
        ) : items.length === 0 ? (
          <div className="text-sm text-muted-foreground">
            Nothing is recorded about you.
          </div>
        ) : (
          <ul className="mt-1">
            {items.map((item) => (
              <Row
                key={item.memory_id}
                item={item}
                busy={busy}
                onStopUsing={() => void act(item.memory_id, 'stop-using')}
                onRememberAgain={() => void act(item.memory_id, 'remember-again')}
                onForget={() => setConfirming(item)}
              />
            ))}
          </ul>
        )}

        <div className="flex items-center justify-between mt-4">
          <button
            type="button"
            className="text-xs text-muted-foreground/70 hover:text-muted-foreground transition-colors"
            onClick={() => setShowForgotten((v) => !v)}
          >
            {showForgotten ? 'Hide forgotten' : 'Show forgotten'}
          </button>
        </div>

        {/* The reach of the erase that just happened. Kept on screen rather
            than flashed: it names things a person may still want to go and
            deal with themselves. */}
        {report ? (
          <div className="text-xs text-muted-foreground mt-3 border-t border-border pt-3">
            Forgotten. {report}
          </div>
        ) : null}
      </CardContent>

      <ConfirmDialog
        open={confirming !== null}
        onClose={() => setConfirming(null)}
        onConfirm={() => {
          const target = confirming
          setConfirming(null)
          if (target) void act(target.memory_id, 'forget')
        }}
        title={`Forget “${confirming?.topic ?? ''}”?`}
        description={
          'This destroys the record. It cannot be undone, and it will not ' +
          'appear under "Show forgotten". To keep it but stop it being ' +
          'used, close this and choose "Stop using this" instead.'
        }
        warning={limits}
        confirmText="Forget it"
        variant="destructive"
        loading={busy}
      />
    </Card>
  )
}

export default AboutYouCard
