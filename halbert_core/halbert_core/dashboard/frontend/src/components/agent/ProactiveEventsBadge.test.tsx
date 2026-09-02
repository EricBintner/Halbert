// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * Tests for the acoustic render branch in ProactiveEventsBadge (O5 repair 3).
 *
 * Acoustic events (category "acoustic", carrying the structured payload from
 * AcousticAnomalyDetector) render the AcousticAnomalyModule card instead of
 * the generic icon+title row — while keeping the snooze/dismiss actions,
 * which the module's own decorative buttons do not provide.
 *
 * useBeingEvents is mocked (EventSource does not exist under jsdom); the
 * module's real isAcousticEvent helper is kept via importOriginal so the
 * discrimination logic itself runs in these tests too.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import type { BeingEvent } from '../../hooks/useBeingEvents'

vi.mock('../../hooks/useBeingEvents', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../hooks/useBeingEvents')>()),
  useBeingEvents: () => ({
    events: mockEvents,
    snooze: vi.fn().mockResolvedValue(true),
    dismiss: vi.fn().mockResolvedValue(true),
    propose: proposeMock,
    pendingActions: new Set<string>(),
    actionError: null,
    clearActionError: vi.fn(),
    clear: vi.fn(),
  }),
}))

import { ProactiveEventsBadge } from './ProactiveEventsBadge'

const acousticEvent: BeingEvent = {
  id: 'evt-acoustic',
  type: 'finding',
  severity: 'critical',
  title: 'Acoustic anomaly: Smoke detector alarm in kitchen',
  body: 'Detected Smoke detector alarm at 93% confidence in kitchen.',
  finding_id: 'f-1',
  created_at: '2026-08-31T12:00:00Z',
  category: 'acoustic',
  data: {
    sound_class: 'smoke_alarm',
    confidence: 0.93,
    area_id: 'kitchen',
    decibel_level: 88,
    anomaly_severity: 3,
    source: 'ambient',
    timestamp: '2026-08-31T12:00:00Z',
  },
}

const genericEvent: BeingEvent = {
  id: 'evt-generic',
  type: 'finding',
  severity: 'warning',
  title: 'SSH port conflict',
  body: 'Two services want port 22.',
  finding_id: 'f-2',
  created_at: '2026-08-31T12:05:00Z',
  category: 'config',
}

let mockEvents: BeingEvent[] = []
const proposeMock = vi.fn().mockResolvedValue(true)

function openDropdown() {
  // The unread-count span inside the button wins the accessible-name
  // computation over the title attribute, so query by title.
  fireEvent.click(screen.getByTitle('Findings'))
}

describe('ProactiveEventsBadge acoustic branch (O5)', () => {
  it('renders the AcousticAnomalyModule for acoustic events', () => {
    mockEvents = [acousticEvent]
    render(<ProactiveEventsBadge />)
    openDropdown()

    // Module card content (not the generic row markup)
    expect(screen.getByText('Critical Acoustic Anomaly')).toBeTruthy()
    expect(screen.getByText('smoke_alarm')).toBeTruthy()
    expect(screen.getByText('88 dB')).toBeTruthy()
    expect(screen.getByText('kitchen')).toBeTruthy()
    // The module's unwired action buttons stay hidden here — no dead
    // destructive "Call Emergency" on a life-safety card.
    expect(screen.queryByText('Call Emergency')).toBeNull()
  })

  it('keeps snooze/dismiss available on acoustic events', () => {
    mockEvents = [acousticEvent]
    render(<ProactiveEventsBadge />)
    openDropdown()

    expect(screen.getByText('Snooze 7d')).toBeTruthy()
    expect(screen.getByText('Dismiss')).toBeTruthy()
  })

  it('renders generic findings with the plain row, not the module', () => {
    mockEvents = [genericEvent]
    render(<ProactiveEventsBadge />)
    openDropdown()

    expect(screen.getByText('SSH port conflict')).toBeTruthy()
    expect(screen.queryByText('Acoustic Observation')).toBeNull()
    expect(screen.queryByText('Critical Acoustic Anomaly')).toBeNull()
  })

  it('shows both shapes side by side when mixed', () => {
    mockEvents = [acousticEvent, genericEvent]
    render(<ProactiveEventsBadge />)
    openDropdown()

    expect(screen.getByText('Critical Acoustic Anomaly')).toBeTruthy()
    expect(screen.getByText('SSH port conflict')).toBeTruthy()
  })

  it('carries the badge count including acoustic events', () => {
    mockEvents = [acousticEvent, genericEvent]
    render(<ProactiveEventsBadge />)

    expect(screen.getByText('2')).toBeTruthy()
  })
})

// -----------------------------------------------------------------------------
// C2-02: the row carries its why, and the finding can be proposed from here.
// -----------------------------------------------------------------------------

const findingWithWhy: BeingEvent = {
  id: 'evt-why',
  type: 'finding',
  severity: 'warning',
  title: 'Loose key permissions',
  body: 'id_rsa is mode 0644.',
  finding_id: 'f-why',
  created_at: '2026-09-02T08:00:00Z',
  category: 'security',
  why: {
    now: 'sweep found id_rsa readable by group and others',
    care: 'anyone on this machine can read your private key',
    so: 'mode 0644 on ~/.ssh/id_rsa',
    trust: ['~/.ssh/id_rsa:mode'],
  },
  affected_paths: ['~/.ssh/id_rsa'],
}

describe('ProactiveEventsBadge whys and propose (C2-02 / J3-7)', () => {
  it('is labelled Findings, not proactive events', () => {
    mockEvents = []
    render(<ProactiveEventsBadge />)
    expect(screen.getByTitle('Findings')).toBeTruthy()
    expect(screen.queryByTitle('Proactive events')).toBeNull()
  })

  it('renders why_care as the second line when present', () => {
    mockEvents = [findingWithWhy]
    render(<ProactiveEventsBadge />)
    openDropdown()
    expect(screen.getByText('Loose key permissions')).toBeTruthy()
    expect(screen.getByText('anyone on this machine can read your private key')).toBeTruthy()
    // The raw description is not shown twice over the why.
    expect(screen.queryByText('id_rsa is mode 0644.')).toBeNull()
  })

  it('falls back to the body when the event carries no why', () => {
    mockEvents = [genericEvent]
    render(<ProactiveEventsBadge />)
    openDropdown()
    expect(screen.getByText('Two services want port 22.')).toBeTruthy()
  })

  it('offers Propose fix when the finding has no proposal yet, and calls propose', () => {
    proposeMock.mockClear()
    mockEvents = [findingWithWhy]
    render(<ProactiveEventsBadge />)
    openDropdown()
    const btn = screen.getByText('Propose fix')
    fireEvent.click(btn)
    expect(proposeMock).toHaveBeenCalledTimes(1)
    expect(proposeMock.mock.calls[0][0].finding_id).toBe('f-why')
  })

  it('hides Propose fix once a proposal is linked', () => {
    mockEvents = [{ ...findingWithWhy, proposal_id: 'p-1' }]
    render(<ProactiveEventsBadge />)
    openDropdown()
    expect(screen.queryByText('Propose fix')).toBeNull()
    expect(screen.getByText('Fix proposed')).toBeTruthy()
  })

  it('does not offer Propose fix on events that are not findings', () => {
    mockEvents = [{
      ...genericEvent,
      id: 'evt-report',
      type: 'morning_report',
      finding_id: undefined,
      title: 'Morning report',
    }]
    render(<ProactiveEventsBadge />)
    openDropdown()
    expect(screen.queryByText('Propose fix')).toBeNull()
  })
})
