// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * The all-bodies view, reachable at last.
 *
 * NodeFleetCockpit was written, tested, and imported by nothing — no route,
 * no nav entry. The Presence Pill switches bodies and Settings › Linked
 * Devices manages them; there was nowhere to see them all at once.
 *
 * Vocabulary: CORE-CONCEPTS-AND-ALIGNMENT §terminology lists node, instance,
 * host-as-noun and satellite under avoid. A physical device is a **Body**.
 * Internal field names like node_id are fine; the noun on screen is not.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { Bodies } from './Bodies'

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(async () => ({
    ok: true, status: 200, json: async () => [],
  })))
})
afterEach(() => vi.unstubAllGlobals())

describe('Bodies page', () => {
  it('renders the fleet view', async () => {
    render(<Bodies />)
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /bodies/i })).toBeTruthy()
    })
  })

  it('does not call a machine a satellite or a node', async () => {
    const { container } = render(<Bodies />)
    await waitFor(() => expect(screen.getByRole('heading', { name: /bodies/i })).toBeTruthy())

    // A leading boundary only: textContent concatenates siblings with no
    // separator, so a trailing \b silently never matches.
    expect(container.textContent).not.toMatch(/\bsatellite/i)
    expect(container.textContent).not.toMatch(/\bnode/i)
  })

  it('says what to do when there are no other bodies yet', async () => {
    render(<Bodies />)
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /link a body/i })).toBeTruthy()
    })
  })
})
