// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
// Modality handoff badge — shows the engine's delivery modality decision.
//
// Displays a small badge in the conversation area indicating whether the
// response was delivered as text, voice, or mixed. For voice turns, shows
// the spoken word count and whether the response was redacted (multi-occupant)
// or whispered (quiet hours).
//
// SVG icons only (no emoji per project rules).

import { Mic, Monitor, MicVocal } from 'lucide-react'
import type { ModalityInfo } from '@/hooks/useAgentStream'

interface ModalityHandoffBadgeProps {
  modality: ModalityInfo | null
}

export function ModalityHandoffBadge({ modality }: ModalityHandoffBadgeProps) {
  if (!modality || modality.modality === 'text' || modality.modality === 'deferred') {
    return null
  }

  const isVoice = modality.modality === 'voice'
  const isMixed = modality.modality === 'mixed'
  const wordCount = modality.speechText
    ? modality.speechText.split(/\s+/).filter(Boolean).length
    : 0

  const icon = isVoice ? (
    <Mic className="h-3.5 w-3.5" />
  ) : isMixed ? (
    <MicVocal className="h-3.5 w-3.5" />
  ) : (
    <Monitor className="h-3.5 w-3.5" />
  )

  const label = isVoice ? 'Voice' : isMixed ? 'Mixed' : 'Text'

  return (
    <div className="inline-flex items-center gap-1.5 rounded-full border border-border bg-muted/50 px-2 py-0.5 text-xs text-muted-foreground">
      {icon}
      <span>{label}</span>
      {wordCount > 0 && (
        <span className="text-muted-foreground/70">
          {wordCount} spoken
        </span>
      )}
    </div>
  )
}
