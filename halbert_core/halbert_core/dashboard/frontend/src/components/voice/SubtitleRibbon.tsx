// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
// Subtitle ribbon — the spoken-output line under the mark (spec doc 15 §6.1).
//
// The Voice Mode twin of VoiceCompanionPill: it consumes the same
// SpeechSegmentEvent[] useAgentStream collects (session.speechSegments) and
// shows the segment currently being spoken — the LAST one, since segments
// are emitted and spoken in order. The text renders AS-IS: pronunciation is
// already applied server-side (apply_pronunciation in state_machine.py),
// so there is no frontend lexicon (plan doc 16 Task O7 corrects doc 15's
// Phase-2 bullet). This is spoken output only — response_chunk is LLM text
// and live STT subtitles need the not-yet-live STT observation channel.
//
// The row's height is reserved even when nothing shows, so the mark does
// not jump when speech starts. Canvas/ink tokens on the deliberately dark
// Voice Mode surface (plan Decision 5) — no raw hex, no stock palette.

import type { SpeechSegmentEvent } from '@/hooks/useAgentStream'

interface SubtitleRibbonProps {
  /** Spoken-output segments from the agent turn (useAgentStream). */
  segments: SpeechSegmentEvent[]
  /** False hides the text (Voice Mode shows it while speaking). */
  active: boolean
}

export function SubtitleRibbon({ segments, active }: SubtitleRibbonProps) {
  const segment = active && segments.length > 0 ? segments[segments.length - 1] : null

  return (
    <div
      role="status"
      aria-live="polite"
      aria-label="Spoken response"
      className="flex min-h-16 items-center justify-center gap-3 px-6 pb-2"
    >
      {segment && (
        <>
          <p className="max-w-3xl text-center text-lg leading-relaxed text-canvas/90">
            {segment.text}
          </p>
          {segment.prosody?.whisper && (
            <span className="shrink-0 rounded-full border border-hairline px-2.5 py-0.5 text-xs uppercase tracking-wide text-canvas/60">
              whisper prosody
            </span>
          )}
        </>
      )}
    </div>
  )
}