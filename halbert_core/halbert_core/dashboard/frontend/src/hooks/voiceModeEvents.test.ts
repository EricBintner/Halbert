// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * Tests for the O5 wake seam (voiceModeEvents).
 *
 * acousticWakeEvent() is the pure contract Task O6's useVoiceModeMachine
 * reducer will absorb: it decides, from a proactive (being) SSE event,
 * whether an acoustic anomaly forces the visual state to wake.
 */
import { describe, it, expect } from 'vitest'
import type { BeingEvent } from './useBeingEvents'
import { acousticWakeEvent, ACOUSTIC_WAKE_MIN_SEVERITY } from './voiceModeEvents'

function acousticEvent(severity: number, over: Partial<BeingEvent> = {}): BeingEvent {
  return {
    id: 'evt-1',
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
      anomaly_severity: severity,
      source: 'ambient',
      timestamp: '2026-08-31T12:00:00Z',
    },
    ...over,
  }
}

describe('ACOUSTIC_WAKE_MIN_SEVERITY', () => {
  it('is severity 2 (confirmed anomaly) per the plan', () => {
    expect(ACOUSTIC_WAKE_MIN_SEVERITY).toBe(2)
  })
})

describe('acousticWakeEvent', () => {
  it('wakes with critical urgency at severity 3 (life-safety)', () => {
    expect(acousticWakeEvent(acousticEvent(3))).toEqual({
      type: 'acoustic_wake',
      soundClass: 'smoke_alarm',
      severity: 3,
      urgency: 'critical',
    })
  })

  it('wakes with urgent urgency at severity 2 (confirmed anomaly)', () => {
    expect(acousticWakeEvent(acousticEvent(2))).toEqual({
      type: 'acoustic_wake',
      soundClass: 'smoke_alarm',
      severity: 2,
      urgency: 'urgent',
    })
  })

  it('does not wake at severity 1 or 0', () => {
    expect(acousticWakeEvent(acousticEvent(1))).toBeNull()
    expect(acousticWakeEvent(acousticEvent(0))).toBeNull()
  })

  it('does not wake for non-acoustic events', () => {
    const configFinding: BeingEvent = {
      id: 'evt-2',
      type: 'finding',
      severity: 'warning',
      title: 'SSH port conflict',
      body: 'two services want 22',
      created_at: '2026-08-31T12:00:00Z',
      category: 'config',
    }
    expect(acousticWakeEvent(configFinding)).toBeNull()
  })

  it('does not wake when the structured payload is missing (category alone is not enough)', () => {
    const noData = acousticEvent(3)
    delete (noData as Partial<BeingEvent>).data
    expect(acousticWakeEvent(noData)).toBeNull()
  })

  it('accepts type "acoustic" (future direct publishers) as well as the category', () => {
    const typed: BeingEvent = acousticEvent(2, { type: 'acoustic', category: undefined })
    expect(acousticWakeEvent(typed)?.urgency).toBe('urgent')
  })
})
