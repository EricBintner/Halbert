// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
// Acoustic aura indicator — shows audio pipeline state in the header bar.
//
// SVG-based animation (no emoji). Polls /api/audio/status for state.
// States: idle (breathing), listening (waveform), recognized (badge),
// thinking (pulse), speaking (sync waveform).

import { useEffect, useState } from 'react'
import { apiUrl } from '@/lib/apiBase'
import { AudioLines } from 'lucide-react'
import type { SpeakerStatus } from '@/components/voice/SpeakerBadge'

type AudioState = 'idle' | 'listening' | 'recognized' | 'thinking' | 'speaking' | 'error'

interface AudioStatus {
  enabled: boolean
  available: boolean
  state: string
  // Last identified speaker (O4) — null until a speech turn has run;
  // absent on the static fallback payload (no coordinator).
  speaker?: SpeakerStatus | null
}

const STATE_COLORS: Record<AudioState, string> = {
  idle: 'text-muted-foreground',
  listening: 'text-blue-500',
  recognized: 'text-green-500',
  thinking: 'text-purple-500',
  speaking: 'text-orange-500',
  error: 'text-destructive',
}

const STATE_LABELS: Record<AudioState, string> = {
  idle: 'Idle',
  listening: 'Listening',
  recognized: 'Recognized',
  thinking: 'Thinking',
  speaking: 'Speaking',
  error: 'Error',
}

export function AcousticAuraIndicator() {
  const [state, setState] = useState<AudioState>('idle')
  const [enabled, setEnabled] = useState(false)

  useEffect(() => {
    let mounted = true
    const poll = async () => {
      try {
        const resp = await fetch(apiUrl('/api/audio/status'))
        if (resp.ok && mounted) {
          const data: AudioStatus = await resp.json()
          setEnabled(data.enabled)
          if (data.enabled && data.state) {
            setState(data.state as AudioState)
          } else {
            setState('idle')
          }
        }
      } catch {
        // Silently fail — the indicator is non-critical
      }
    }
    poll()
    const interval = setInterval(poll, 2000)
    return () => {
      mounted = false
      clearInterval(interval)
    }
  }, [])

  if (!enabled) return null

  const color = STATE_COLORS[state]
  const label = STATE_LABELS[state]
  const isAnimating = state === 'listening' || state === 'speaking'

  return (
    <div className="flex items-center gap-2" title={`Audio: ${label}`}>
      {/* Aura circle with breathing/pulse animation */}
      <div className="relative flex items-center justify-center">
        {isAnimating && (
          <div
            className={`absolute inset-0 rounded-full ${color} opacity-30`}
            style={{
              animation: 'audio-aura-pulse 1.5s ease-in-out infinite',
            }}
          />
        )}
        {state === 'idle' && (
          <div
            className={`absolute inset-0 rounded-full ${color} opacity-10`}
            style={{
              animation: 'audio-aura-breathe 3s ease-in-out infinite',
            }}
          />
        )}
        <AudioLines className={`h-4 w-4 ${color} relative z-10`} />
      </div>
      <span className={`text-xs ${color}`}>{label}</span>
      <style>{`
        @keyframes audio-aura-breathe {
          0%, 100% { transform: scale(1); opacity: 0.1; }
          50% { transform: scale(1.3); opacity: 0.2; }
        }
        @keyframes audio-aura-pulse {
          0%, 100% { transform: scale(1); opacity: 0.3; }
          50% { transform: scale(1.5); opacity: 0.5; }
        }
      `}</style>
    </div>
  )
}
