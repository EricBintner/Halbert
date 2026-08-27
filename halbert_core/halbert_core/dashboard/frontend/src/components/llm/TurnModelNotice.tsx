// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * D-3: what answered this turn, and why.
 *
 * Two cases earn a line in the stream, and only two. An escalation to the
 * specialist, because the user did not ask for it and may be paying for it.
 * And a fallback, because "the model you pinned answered" and "something else
 * answered instead" must never look alike.
 *
 * De-escalation is deliberately silent — a banner for every ordinary turn is
 * noise, and the turn footer already carries the model name.
 */
import { useState } from 'react'
import type { TurnModelInfo } from '@/hooks/useAgentStream'

export function TurnModelNotice({ turn }: { turn: TurnModelInfo }) {
  const [showWhy, setShowWhy] = useState(false)

  if (turn.fallbackFrom) {
    return (
      <div
        role="status"
        className="flex flex-wrap items-center gap-2 rounded-lg border border-warning/40 bg-warning/10 px-3 py-2 text-xs"
      >
        <span aria-hidden="true">⚠️</span>
        <span className="text-foreground">
          <span className="font-mono">{turn.fallbackFrom}</span> was unavailable.{' '}
          <span className="font-mono">{turn.model}</span> answered instead.
        </span>
      </div>
    )
  }

  if (!turn.escalated) return null

  return (
    <div className="flex flex-wrap items-center gap-2 border-l-2 border-info/50 pl-3 py-1 text-xs text-muted-foreground">
      <span aria-hidden="true">🔀</span>
      <span>
        Escalated to the specialist —{' '}
        <span className="font-mono text-foreground">{turn.model}</span>
      </span>
      {turn.reason && (
        <button
          type="button"
          onClick={() => setShowWhy((v) => !v)}
          aria-expanded={showWhy}
          className="underline underline-offset-2 hover:text-foreground transition-colors"
        >
          Why?
        </button>
      )}
      {showWhy && turn.reason && (
        <span className="basis-full text-muted-foreground">{turn.reason}</span>
      )}
    </div>
  )
}
