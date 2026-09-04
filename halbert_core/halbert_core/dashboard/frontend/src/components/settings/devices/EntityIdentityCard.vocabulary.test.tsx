// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * One noun for a machine, and it is not "node".
 *
 * CORE-CONCEPTS-AND-ALIGNMENT-2026-09-02 §terminology: a physical device is a
 * **Body**; `node`, `instance`, `host` (as the noun) and `satellite` are
 * listed under avoid. C1-02 puts it plainly — "`I` is the entity, bodies are
 * 'my desk body'".
 *
 * The two mode buttons sat side by side contradicting each other: one said
 * "one Halbert, many bodies" and the other was headed "Independent Node".
 * A reader choosing between them was choosing between two vocabularies.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { EntityIdentityCard } from './EntityIdentityCard'

const STATE = {
  status: 'ok',
  entity_mode: 'independent' as const,
  body_name: 'desk',
  canonical_memory_url: '',
  canonical_thread_url: '',
  devices: [],
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(async () => ({
    ok: true, status: 200, json: async () => ({}),
  })))
})
afterEach(() => vi.unstubAllGlobals())

describe('EntityIdentityCard vocabulary', () => {
  it('offers a choice between two entity modes, in one vocabulary', () => {
    render(<EntityIdentityCard state={STATE} onRefresh={() => {}} />)

    expect(screen.getByText('Singular Entity')).toBeTruthy()
    expect(screen.getByText('Independent Body')).toBeTruthy()
  })

  it('does not call a machine a node', () => {
    const { container } = render(
      <EntityIdentityCard state={STATE} onRefresh={() => {}} />
    )
    // A leading boundary only. textContent concatenates sibling elements
    // with no separator, so "Independent Node" followed by its description
    // reads as "NodeThis body keeps..." — a trailing \b never matches, and
    // the assertion passes while the word is right there on screen.
    expect(container.textContent).not.toMatch(/\bnode/i)
  })
})
