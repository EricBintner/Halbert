// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { SpeakerBadge, type SpeakerStatus } from './SpeakerBadge'

function makeSpeaker(overrides: Partial<SpeakerStatus> = {}): SpeakerStatus {
  return {
    name: 'Eric',
    role: 'admin',
    confidence: 0.93,
    ...overrides,
  }
}

describe('SpeakerBadge', () => {
  it('renders nothing when speaker is null', () => {
    const { container } = render(<SpeakerBadge speaker={null} />)
    expect(container.firstChild).toBeNull()
  })

  it('renders the recognized speaker name, role, and confidence', () => {
    render(<SpeakerBadge speaker={makeSpeaker()} />)
    expect(screen.getByText('Eric')).toBeTruthy()
    expect(screen.getByText('admin')).toBeTruthy()
    // confidence arrives as a 0..1 float; the badge shows a percentage
    expect(screen.getByText('93%')).toBeTruthy()
  })

  it('is accessible: the container is labelled with the speaker name', () => {
    const { container } = render(<SpeakerBadge speaker={makeSpeaker()} />)
    const badge = container.firstChild as HTMLElement
    expect(badge.getAttribute('aria-label')?.includes('Eric')).toBe(true)
  })

  it('shows an honest placeholder for a match with no profile', () => {
    // Server encodes "identified but not enrolled' as an empty name and
    // role 'unknown' — the badge must not invent a person.
    render(<SpeakerBadge speaker={makeSpeaker({ name: '', role: 'unknown', confidence: 0.81 })} />)
    expect(screen.getByText('Unknown speaker')).toBeTruthy()
    expect(screen.getByText('81%')).toBeTruthy()
  })

  it('does not show a percentage for an unidentified turn (confidence 0)', () => {
    render(<SpeakerBadge speaker={makeSpeaker({ name: '', role: 'unknown', confidence: 0 })} />)
    expect(screen.getByText('Unknown speaker')).toBeTruthy()
    expect(screen.queryByText('0%')).toBeNull()
  })

  it('rounds fractional confidence to a whole percentage without trailing zeros', () => {
    render(<SpeakerBadge speaker={makeSpeaker({ confidence: 0.755 })} />)
    expect(screen.getByText('76%')).toBeTruthy()
  })

  it('uses design tokens (ink/accent) not raw color classes', () => {
    const { container } = render(<SpeakerBadge speaker={makeSpeaker()} />)
    const badge = container.firstChild as HTMLElement
    for (const banned of ['orange-500', 'purple-500', 'bg-black', 'text-white']) {
      expect(badge.outerHTML).not.toContain(banned)
    }
    expect(badge.className).toContain('ink')
  })

  it('renders a single pill (compact enough for the Voice Mode top bar)', () => {
    const { container } = render(<SpeakerBadge speaker={makeSpeaker()} />)
    const badge = container.firstChild as HTMLElement
    expect(badge.className).toContain('rounded-full')
  })
})
