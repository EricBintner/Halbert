// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
// Speaker badge — shows the last identified speaker from /api/audio/status.
//
// A compact pill for the Voice Mode top bar (Task O7 will place it): the
// recognized speaker's name, their household role, and the identification
// confidence as a subtle whole-percentage. Renders nothing when no turn has
// produced an observation (`speaker === null` from the backend).
//
// Truthfulness: the backend sends an empty name / role "unknown" for a voice
// it heard but could not match to an enrolled profile — we label that
// "Unknown speaker" here rather than inventing a person. Colors come from
// the shared token tier (ink/accent) so the pill stays legible on the dark
// Voice Mode canvas; no raw hex or stock-palette classes (canonical palette
// rule).
//
// SVG/lucide only — no emoji per project rules.

import { User } from 'lucide-react'

type SpeakerStatus = {
  name: string
  role: string
  confidence: number
}

export type { SpeakerStatus }

interface SpeakerBadgeProps {
  /** Null/undefined when no speech turn has produced an observation. */
  speaker?: SpeakerStatus | null
}

function confidencePercent(confidence: number): string | null {
  // Never advertise a precision we don't have: 0 confidence (unidentified
  // turn) shows no number at all; otherwise a whole percentage.
  if (confidence <= 0) return null
  return `${Math.round(confidence * 100)}%`
}

export function SpeakerBadge({ speaker }: SpeakerBadgeProps) {
  if (!speaker) return null

  // The backend sends an empty name for an unmatched voice; it never sends
  // the literal "Unknown".
  const isKnown = speaker.name !== ''
  const displayName = isKnown ? speaker.name : 'Unknown speaker'
  const showRole = isKnown && speaker.role !== '' && speaker.role !== 'unknown'
  const percent = confidencePercent(speaker.confidence)

  return (
    <div
      role="status"
      aria-label={`Speaker: ${displayName}`}
      className="flex items-center gap-2 rounded-full border border-hairline bg-canvas-surface/50 px-3 py-1 text-sm text-ink-secondary"
    >
      <User className="h-3.5 w-3.5 text-vermilion" aria-hidden="true" />
      <span className="truncate">{displayName}</span>
      {showRole && (
        <span className="text-xs uppercase tracking-wide text-ink-tertiary">
          {speaker.role}
        </span>
      )}
      {percent && (
        <span
          className="text-xs tabular-nums text-ink-tertiary"
          title="Speaker identification confidence"
        >
          {percent}
        </span>
      )}
    </div>
  )
}
