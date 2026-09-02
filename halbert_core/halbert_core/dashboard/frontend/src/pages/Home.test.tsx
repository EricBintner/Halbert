// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * Home page (FE-15): on mount it checks /api/home/status and, only when
 * connected, loads /api/home/entities. Not connected renders the
 * HomeConnectionForm; connected renders the entity browser with a working
 * Refresh. Asserts the real route paths (no extra /api prefix, no stale
 * hardcoded host) and that entities are not fetched when disconnected.
 */
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Home } from './Home'

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response
}

const ENTITY = {
  entity_id: 'light.kitchen',
  state: 'on',
  attributes: { friendly_name: 'Kitchen Light' },
  last_changed: '2026-08-30T12:00:00Z',
}

function renderHome({ connected = false, entities = [ENTITY] as typeof ENTITY[] } = {}) {
  const calls: Array<{ url: string }> = []
  const fetchMock = vi.fn(async (url: string) => {
    calls.push({ url })
    if (url === '/api/home/status') return jsonResponse({ connected })
    if (url === '/api/home/entities') return jsonResponse({ entities })
    return jsonResponse({}, 404)
  })
  vi.stubGlobal('fetch', fetchMock)
  render(<Home />)
  return { calls }
}

afterEach(() => vi.unstubAllGlobals())

describe('Home', () => {
  it('checks /api/home/status on mount and shows the connection form when not connected', async () => {
    const { calls } = renderHome({ connected: false })
    expect(await screen.findByText('Connect to Home Assistant')).toBeTruthy()
    expect(calls.some((c) => c.url === '/api/home/status')).toBe(true)
    // Not connected: entities must not be fetched.
    expect(calls.some((c) => c.url === '/api/home/entities')).toBe(false)
  })

  it('loads entities and shows the Connected banner when connected', async () => {
    const { calls } = renderHome({ connected: true })
    expect(await screen.findByText('Connected')).toBeTruthy()
    expect(screen.getByText('Home')).toBeTruthy()
    expect(calls.some((c) => c.url === '/api/home/entities')).toBe(true)
    expect(await screen.findByText('Kitchen Light')).toBeTruthy()
  })

  it('Refresh re-checks status and reloads entities', async () => {
    const user = userEvent.setup()
    const { calls } = renderHome({ connected: true })
    await screen.findByText('Connected')
    calls.length = 0

    await user.click(screen.getByRole('button', { name: /refresh/i }))

    await waitFor(() => {
      expect(calls.some((c) => c.url === '/api/home/status')).toBe(true)
      expect(calls.some((c) => c.url === '/api/home/entities')).toBe(true)
    })
  })

  it('a failed status check falls back to the connection form, not a crash', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new Error('network down')
      }),
    )
    render(<Home />)
    expect(await screen.findByText('Connect to Home Assistant')).toBeTruthy()
  })

  it('completing the connection form switches to the connected view and loads entities', async () => {
    const user = userEvent.setup()
    const calls: Array<{ url: string; init?: RequestInit }> = []
    // Mirrors the real backend: status flips to connected only after the
    // config POST succeeds, same mutable-state approach as DevicesTab.test.tsx.
    let configured = false
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, init })
      if (url === '/api/home/config') {
        configured = true
        return jsonResponse({ status: 'ok' })
      }
      if (url === '/api/home/status') return jsonResponse({ connected: configured })
      if (url === '/api/home/entities') return jsonResponse({ entities: [ENTITY] })
      return jsonResponse({}, 404)
    })
    vi.stubGlobal('fetch', fetchMock)
    render(<Home />)

    await screen.findByText('Connect to Home Assistant')
    await user.type(screen.getByLabelText(/home assistant url/i), 'http://homeassistant.local:8123')
    await user.type(screen.getByLabelText(/access token/i), 'sometoken')
    await user.click(screen.getByRole('button', { name: /^connect$/i }))

    // handleConnected() calls loadEntities(), which hits the real route.
    expect(await screen.findByText('Connected')).toBeTruthy()
    await waitFor(() => {
      expect(calls.some((c) => c.url === '/api/home/entities')).toBe(true)
    })
  })
})
