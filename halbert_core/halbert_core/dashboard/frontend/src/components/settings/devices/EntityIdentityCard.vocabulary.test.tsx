// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * The mode names are ratified; the noun for a machine is "body".
 *
 * Two different rules, and conflating them is how this screen came to
 * contradict the other one.
 *
 * DECISIONS.md 2026-09-01 sets the UI strings literally: "Singular Entity /
 * Independent Node / Linked Devices". CORE-CONCEPTS §terminology lists
 * `node`, `instance`, `host` (as the noun) and `satellite` under avoid -- but
 * that cell sits in the **Physical device** row. It bans calling a machine a
 * node. It does not rename a mode.
 *
 * The previous version of this file asserted `not.toMatch(/\bnode/i)` over
 * the whole card, which bans the ratified mode name too. It passed only
 * because the component had been changed to match it.
 *
 * Retired terms are banned repo-wide by `src/vocabulary.guard.test.ts`, not
 * here. Sixteen per-component assertions were green while two screens
 * disagreed; one guard over every file is the point.
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
  it('uses the ratified names for the two entity modes', () => {
    render(<EntityIdentityCard state={STATE} onRefresh={() => {}} />)

    expect(screen.getByText('Singular Entity')).toBeTruthy()
    expect(screen.getByText('Independent Node')).toBeTruthy()
  })

  it('calls the machine a body', () => {
    const { container } = render(
      <EntityIdentityCard state={STATE} onRefresh={() => {}} />
    )
    // The description under the mode, and the label for the device name.
    expect(container.textContent).toMatch(/this body keeps its own memory/i)
  })
})
