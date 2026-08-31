// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import { VoiceCompanionPill } from './VoiceCompanionPill'
import type { SpeechSegmentEvent } from '@/hooks/useAgentStream'

const SEGMENT_ADVANCE_MS = 3500

function makeSegment(text: string, whisper = false): SpeechSegmentEvent {
  return {
    text,
    role: 'PERSONA',
    prosody: { rate: 1.0, volume: 1.0, whisper },
  }
}

describe('VoiceCompanionPill', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('renders nothing when inactive', () => {
    const { container } = render(
      <VoiceCompanionPill segments={[makeSegment('hello')]} isActive={false} />,
    )
    expect(container.firstChild).toBeNull()
  })

  it('renders nothing when segments is empty', () => {
    const { container } = render(
      <VoiceCompanionPill segments={[]} isActive={true} />,
    )
    expect(container.firstChild).toBeNull()
  })

  it('renders the first segment on mount', () => {
    render(
      <VoiceCompanionPill
        segments={[makeSegment('first'), makeSegment('second'), makeSegment('third')]}
        isActive={true}
      />,
    )
    expect(screen.getByText('first')).toBeTruthy()
    expect(screen.getByText('1/3')).toBeTruthy()
  })

  it('cycles through segments on an interval', () => {
    render(
      <VoiceCompanionPill
        segments={[makeSegment('first'), makeSegment('second'), makeSegment('third')]}
        isActive={true}
      />,
    )
    expect(screen.getByText('first')).toBeTruthy()

    act(() => { vi.advanceTimersByTime(SEGMENT_ADVANCE_MS) })
    expect(screen.getByText('second')).toBeTruthy()
    expect(screen.getByText('2/3')).toBeTruthy()

    act(() => { vi.advanceTimersByTime(SEGMENT_ADVANCE_MS) })
    expect(screen.getByText('third')).toBeTruthy()
    expect(screen.getByText('3/3')).toBeTruthy()

    // wraps back to first
    act(() => { vi.advanceTimersByTime(SEGMENT_ADVANCE_MS) })
    expect(screen.getByText('first')).toBeTruthy()
  })

  it('does not cycle when only one segment', () => {
    render(
      <VoiceCompanionPill segments={[makeSegment('only')]} isActive={true} />,
    )
    expect(screen.getByText('only')).toBeTruthy()
    act(() => { vi.advanceTimersByTime(SEGMENT_ADVANCE_MS * 3) })
    expect(screen.getByText('only')).toBeTruthy()
  })

  it('resets to first segment when reactivated', () => {
    const { rerender } = render(
      <VoiceCompanionPill
        segments={[makeSegment('first'), makeSegment('second')]}
        isActive={true}
      />,
    )
    act(() => { vi.advanceTimersByTime(SEGMENT_ADVANCE_MS) })
    expect(screen.getByText('second')).toBeTruthy()

    rerender(
      <VoiceCompanionPill
        segments={[makeSegment('first'), makeSegment('second')]}
        isActive={false}
      />,
    )
    rerender(
      <VoiceCompanionPill
        segments={[makeSegment('first'), makeSegment('second')]}
        isActive={true}
      />,
    )
    expect(screen.getByText('first')).toBeTruthy()
  })

  it('shows whisper badge for whisper segments', () => {
    render(
      <VoiceCompanionPill
        segments={[makeSegment('psst', true)]}
        isActive={true}
      />,
    )
    expect(screen.getByText('whisper')).toBeTruthy()
  })

  it('uses design tokens (vermilion) not raw color classes', () => {
    const { container } = render(
      <VoiceCompanionPill segments={[makeSegment('hello')]} isActive={true} />,
    )
    const pill = container.firstChild as HTMLElement
    expect(pill.className).toContain('vermilion')
    expect(pill.className).not.toContain('orange-500')
    expect(pill.className).not.toContain('purple-500')
  })
})
