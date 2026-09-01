// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * SubtitleRibbon (O7): the spoken-output ribbon under the mark. It reads
 * the same SpeechSegmentEvent[] the VoiceCompanionPill does (useAgentStream
 * session.speechSegments) and shows the segment currently being spoken —
 * display text AS-IS, because pronunciation is already applied server-side
 * (apply_pronunciation in state_machine.py; no frontend lexicon, plan doc
 * 16 Task O7).
 */

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { SubtitleRibbon } from './SubtitleRibbon'
import type { SpeechSegmentEvent } from '@/hooks/useAgentStream'

function segment(overrides: Partial<SpeechSegmentEvent> = {}): SpeechSegmentEvent {
  return {
    text: "I've verified the nightly ZFS snapshot completed with zero errors.",
    role: 'persona',
    prosody: { rate: 1, volume: 0.8, whisper: false },
    ...overrides,
  }
}

describe('SubtitleRibbon', () => {
  it('renders no text while inactive, but keeps the row reserved', () => {
    const { container } = render(
      <SubtitleRibbon segments={[segment()]} active={false} />,
    )
    const row = container.firstElementChild as HTMLElement
    expect(row).toBeTruthy()
    expect(row.textContent).toBe('')
  })

  it('renders no text when active but no segments have arrived', () => {
    const { container } = render(<SubtitleRibbon segments={[]} active={true} />)
    expect((container.firstElementChild as HTMLElement).textContent).toBe('')
  })

  it('shows the latest segment (the one being spoken now)', () => {
    render(
      <SubtitleRibbon
        segments={[segment({ text: 'First segment.' }), segment({ text: 'Second segment.' })]}
        active={true}
      />,
    )
    expect(screen.getByText('Second segment.')).toBeTruthy()
    expect(screen.queryByText('First segment.')).toBeNull()
  })

  it('renders the spoken text exactly as delivered — no frontend lexicon', () => {
    // apply_pronunciation already ran server-side; the ribbon must not
    // rewrite domain terms.
    render(<SubtitleRibbon segments={[segment({ text: 'Restarting systemd and the NVMe driver.' })]} active={true} />)
    expect(screen.getByText('Restarting systemd and the NVMe driver.')).toBeTruthy()
  })

  it('marks whisper prosody with a chip', () => {
    render(
      <SubtitleRibbon
        segments={[segment({ prosody: { rate: 0.9, volume: 0.2, whisper: true } })]}
        active={true}
      />,
    )
    expect(screen.getByText('whisper', { exact: false })).toBeTruthy()
  })

  it('shows no prosody chip for ordinary speech', () => {
    render(<SubtitleRibbon segments={[segment()]} active={true} />)
    expect(screen.queryByText('whisper', { exact: false })).toBeNull()
  })

  it('is a polite live region (screen readers follow the speech)', () => {
    const { container } = render(<SubtitleRibbon segments={[segment()]} active={true} />)
    const row = container.firstElementChild as HTMLElement
    expect(row.getAttribute('role')).toBe('status')
    expect(row.getAttribute('aria-live')).toBe('polite')
  })

  it('uses canvas/ink tokens on the dark surface, not raw white classes', () => {
    const { container } = render(<SubtitleRibbon segments={[segment()]} active={true} />)
    const html = container.innerHTML
    for (const banned of ['text-white', 'orange-500', 'purple-500', 'bg-black', '#F7F5F0']) {
      expect(html).not.toContain(banned)
    }
    expect(html).toContain('text-canvas')
  })
})