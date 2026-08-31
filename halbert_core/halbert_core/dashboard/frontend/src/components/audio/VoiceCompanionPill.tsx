// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
// Voice companion pill — shows the active speech segment being spoken.
//
// A compact pill that appears during voice delivery, showing the text being
// spoken, the prosody state (whisper/normal), and a live waveform animation.
// Renders below the conversation bubble during SPEAKING state.
//
// SVG animation only (no emoji per project rules).

import { useEffect, useRef, useState } from 'react'
import { Volume2, VolumeX, Waves } from 'lucide-react'
import type { SpeechSegmentEvent } from '@/hooks/useAgentStream'

const SEGMENT_ADVANCE_MS = 3500

interface VoiceCompanionPillProps {
  segments: SpeechSegmentEvent[]
  isActive: boolean
}

export function VoiceCompanionPill({ segments, isActive }: VoiceCompanionPillProps) {
  const [currentIdx, setCurrentIdx] = useState(0)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }

    if (!isActive || segments.length <= 1) {
      setCurrentIdx(0)
      return
    }

    timerRef.current = setInterval(() => {
      setCurrentIdx((idx) => (idx + 1) % segments.length)
    }, SEGMENT_ADVANCE_MS)

    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current)
        timerRef.current = null
      }
    }
  }, [isActive, segments.length])

  if (!isActive || segments.length === 0) {
    return null
  }

  const segment = segments[Math.min(currentIdx, segments.length - 1)]
  if (!segment) return null

  const isWhisper = segment.prosody.whisper
  const volume = segment.prosody.volume

  return (
    <div className="flex items-center gap-2 rounded-lg border border-vermilion/30 bg-vermilion/5 px-3 py-1.5 text-sm">
      {/* Volume icon — whisper shows muted, normal shows active */}
      {isWhisper || volume < 0.3 ? (
        <VolumeX className="h-4 w-4 text-vermilion/60" />
      ) : (
        <Volume2 className="h-4 w-4 text-vermilion" />
      )}

      {/* Waveform animation */}
      <Waves className="h-4 w-4 text-vermilion animate-pulse" />

      {/* Truncated spoken text */}
      <span className="flex-1 truncate text-muted-foreground">
        {segment.text}
      </span>

      {/* Segment counter */}
      {segments.length > 1 && (
        <span className="text-xs text-muted-foreground/60">
          {currentIdx + 1}/{segments.length}
        </span>
      )}

      {/* Whisper badge */}
      {isWhisper && (
        <span className="rounded bg-info/20 px-1.5 py-0.5 text-xs text-info">
          whisper
        </span>
      )}
    </div>
  )
}
