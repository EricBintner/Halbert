// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * Regression test for ROUTE-02: BeingTab's persona calls used to build
 * `${API_BASE}/api/persona/...` where API_BASE already ends in `/api`,
 * doubling the prefix to `/api/api/persona/*` and 404ing (real routes are
 * `/api/persona/*` — persona.py:52, mounted with no extra app.py prefix).
 * This asserts every persona fetch hits the single-`/api` route.
 */
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { BeingTab } from './BeingTab'

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response
}

const beingConfig = {
  name: 'Halbert',
  archetype_id: 'balanced',
  voice_presentation: 'not_defined',
  custom_personality_prompt: '',
  voice: 'first_person',
  proactivity: 'balanced',
  quiet_hours: null,
  morning_report: { enabled: false },
  purpose: '',
  senses: { vision: {} },
  persona_id: 'default',
}

const personas = [{ id: 'default', display_name: 'Default' }]

const visionSources = [
  { id: 'screen:1', label: 'Screen 1', kind: 'screen', native: '1', enabled: true },
  { id: 'webcam:desk', label: 'Desk webcam', kind: 'webcam', native: '0', enabled: true },
  { id: 'frigate:bedroom', label: 'Bedroom', kind: 'frigate', native: 'bedroom', enabled: false },
]

function renderTab() {
  const calls: Array<{ url: string; init?: RequestInit }> = []
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url, init })
    if (url === '/api/settings/being' && init?.method === 'POST') {
      const body = JSON.parse(init.body as string)
      const vision = { ...beingConfig.senses.vision, ...(body.senses?.vision || {}) }
      return jsonResponse({ status: 'ok', config: { ...beingConfig, senses: { vision } } })
    }
    if (url === '/api/settings/being') return jsonResponse({ status: 'ok', config: beingConfig })
    if (url === '/api/vision/config') return jsonResponse({ sources: visionSources })
    if (url === '/api/persona/list') return jsonResponse({ personas, active_id: 'default' })
    if (url === '/api/persona' && init?.method === 'POST') return jsonResponse({ status: 'ok' })
    if (url.match(/^\/api\/persona\/[^/]+\/activate$/)) return jsonResponse({ status: 'ok' })
    if (url.match(/^\/api\/persona\/[^/]+$/) && init?.method === 'DELETE') {
      return jsonResponse({ status: 'ok' })
    }
    return jsonResponse({ status: 'ok' })
  })
  vi.stubGlobal('fetch', fetchMock)
  render(<BeingTab />)
  return { calls }
}

afterEach(() => vi.unstubAllGlobals())

describe('BeingTab persona routes (ROUTE-02)', () => {
  it('loads personas from /api/persona/list, never doubling the prefix', async () => {
    const { calls } = renderTab()
    await waitFor(() => expect(screen.queryByText(/Loading personality config/i)).toBeNull())
    expect(calls.some((c) => c.url === '/api/persona/list')).toBe(true)
    expect(calls.some((c) => c.url.includes('/api/api/'))).toBe(false)
  })

  it('creating a persona POSTs to /api/persona', async () => {
    const user = userEvent.setup()
    const { calls } = renderTab()
    await waitFor(() => expect(screen.queryByText(/Loading personality config/i)).toBeNull())

    await user.click(screen.getByRole('button', { name: /new persona/i }))
    await user.type(screen.getByPlaceholderText(/persona name/i), 'Second')
    await user.click(screen.getByRole('button', { name: /^create$/i }))

    await waitFor(() => {
      expect(calls.some((c) => c.url === '/api/persona' && c.init?.method === 'POST')).toBe(true)
    })
  })
})

describe('SensesSettings source picker (VIS-1)', () => {
  it('offers only the sources the machine has enabled', async () => {
    renderTab()
    await waitFor(() => expect(screen.queryByText(/Loading senses config/i)).toBeNull())

    expect(screen.getByLabelText(/Allow Screen 1/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/Allow Desk webcam/i)).toBeInTheDocument()
    // Disabled in the Vision tab: a persona must not be able to name it and
    // thereby widen past what the system allows.
    expect(screen.queryByLabelText(/Allow Bedroom/i)).toBeNull()
  })

  it('nothing selected means every enabled source, not none', async () => {
    renderTab()
    await waitFor(() => expect(screen.queryByText(/Loading senses config/i)).toBeNull())

    expect(screen.getByLabelText(/Allow Screen 1/i)).not.toBeChecked()
    expect(screen.getByText(/means every source the machine has enabled/i)).toBeInTheDocument()
  })

  it('choosing a source narrows the persona to it', async () => {
    const user = userEvent.setup()
    const { calls } = renderTab()
    await waitFor(() => expect(screen.queryByText(/Loading senses config/i)).toBeNull())

    await user.click(screen.getByLabelText(/Allow Desk webcam/i))

    const post = calls.find((c) => c.url === '/api/settings/being' && c.init?.method === 'POST')
    const body = JSON.parse(post!.init!.body as string)
    expect(body.senses.vision.sources).toEqual(['webcam:desk'])
  })
})
