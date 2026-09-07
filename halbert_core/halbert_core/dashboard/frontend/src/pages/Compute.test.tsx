// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * The shared compute view — health grid for all linked nodes.
 *
 * Formerly the "Bodies" page. Renamed to Compute per the revised rail
 * design (HANDOFF-NODE-LIST-RAIL-DESIGN §5R). Terminology updated from
 * "bodies" to "nodes" per founder ruling.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { Compute } from './Compute'

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(async () => ({
    ok: true, status: 200, json: async () => [],
  })))
})
afterEach(() => vi.unstubAllGlobals())

describe('Compute page', () => {
  it('renders the shared compute view', async () => {
    render(<Compute />)
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /shared compute/i })).toBeTruthy()
    })
  })

  it('does not call a machine a body or a satellite', async () => {
    const { container } = render(<Compute />)
    await waitFor(() => expect(screen.getByRole('heading', { name: /shared compute/i })).toBeTruthy())

    expect(container.textContent).not.toMatch(/\bsatellite/i)
    expect(container.textContent).not.toMatch(/\bbody\b/i)
    expect(container.textContent).not.toMatch(/\bbodies\b/i)
  })

  it('says what to do when there are no other nodes yet', async () => {
    render(<Compute />)
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /link a node/i })).toBeTruthy()
    })
  })
})
