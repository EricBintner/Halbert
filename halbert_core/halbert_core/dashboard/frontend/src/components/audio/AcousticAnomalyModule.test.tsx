// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * Tests for AcousticAnomalyModule — previously built but rendered nowhere;
 * O5 wires it into the proactive badge (and the module registry). These
 * tests pin its data contract (AcousticAnomalyData, served verbatim as the
 * ProactiveEvent ``data`` payload by the backend detector) and its severity
 * presentation.
 */
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import {
  AcousticAnomalyModule,
  type AcousticAnomalyData,
} from './AcousticAnomalyModule'

function data(over: Partial<AcousticAnomalyData> = {}): AcousticAnomalyData {
  return {
    sound_class: 'glass_breaking',
    confidence: 0.87,
    area_id: 'hall',
    decibel_level: 74,
    anomaly_severity: 2,
    source: 'ambient',
    timestamp: '2026-08-31T12:00:00Z',
    ...over,
  }
}

describe('AcousticAnomalyModule', () => {
  it('renders the structured payload fields', () => {
    render(<AcousticAnomalyModule data={data()} />)

    expect(screen.getByText('glass_breaking')).toBeTruthy()
    expect(screen.getByText('87%')).toBeTruthy()
    expect(screen.getByText('hall')).toBeTruthy()
    expect(screen.getByText('74 dB')).toBeTruthy()
    expect(screen.getByText('ambient')).toBeTruthy()
  })

  it('labels a confirmed (severity 2) anomaly as an observation with Confirm badge', () => {
    render(<AcousticAnomalyModule data={data({ anomaly_severity: 2 })} />)

    expect(screen.getByText('Acoustic Observation')).toBeTruthy()
    expect(screen.getByText('Confirm')).toBeTruthy()
  })

  it('labels severity 3 as critical and offers the emergency action', () => {
    render(<AcousticAnomalyModule data={data({ anomaly_severity: 3 })} />)

    expect(screen.getByText('Critical Acoustic Anomaly')).toBeTruthy()
    expect(screen.getByText('Critical')).toBeTruthy()
    expect(screen.getByText('Call Emergency')).toBeTruthy()
  })

  it('falls back to Unknown for a missing area', () => {
    render(<AcousticAnomalyModule data={data({ area_id: '' })} />)

    expect(screen.getByText('Unknown')).toBeTruthy()
  })
})
