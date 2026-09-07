// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * PersonaHomesCard — Settings → Devices' guest-persona surface.
 *
 * "Be someone else" lived in the old PresencePill's dropdown; the pill's
 * split (§5R.3 N1) moved it here, where the founder wants it: a user
 * connects a persona home in Settings, and the personas it offers appear
 * in a list. Not a primary feature — until a home is connected, the whole
 * surface is one muted line, and the top bar shows nothing at all.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { PersonaHomesCard } from './PersonaHomesCard'

const INFO_IDLE = {
  persona_id: 'p', scene_context: 'desk', role: 'host', variant: 'workstation',
  display_name: 'Macky', port: 8000,
  features: { home: false, gpu: false, development: false, wyoming_port: 0 },
  data_dir: '', config_dir: '', body_name: 'desk', singular: true,
  fronting: null,
}

const INFO_FRONTING = {
  ...INFO_IDLE,
  fronting: {
    home: { base_url: 'http://h2:8002', persona_id: 'marnie-7', label: 'H2' },
    session_id: 's1', name: 'Ada', offered_by: 'peer-1',
    offered_by_name: 'the study tablet',
    started_at: '2026-09-06T10:00:00+00:00', seconds_until_expiry: 55,
    active: true, end_reason: null,
  },
}

const HOMES = [
  { base_url: 'http://h2:8002', label: 'H2', profile: 'default' },
  { base_url: 'http://h3:8003', label: 'H3', profile: 'h3' },
]

const PERSONAS = [
  { persona_id: 'marnie-7', name: 'Marnie', home_label: 'H2', base_url: 'http://h2:8002' },
  { persona_id: 'ada-1', name: 'Ada', home_label: 'H3', base_url: 'http://h3:8003' },
]

/** One stub for the card's whole API surface. Each route is overridable by
 * the test through the `routes` argument; the defaults describe a machine
 * with both homes connected and both answering. */
function stubGuestApi(overrides: Record<string, unknown> = {}) {
  const routes: Record<string, (init?: RequestInit) => unknown> = {
    '/api/guest/homes': () => ({ homes: HOMES }),
    '/api/guest/available': () => ({ personas: PERSONAS, unreachable: [] }),
    '/api/instance/info': () => INFO_IDLE,
    ...overrides,
  }
  const calls: Array<{ url: string; init?: RequestInit }> = []
  const fetchMock = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
    const path = String(url)
    calls.push({ url: path, init })
    for (const [suffix, answer] of Object.entries(routes)) {
      // DELETE carries its argument in the query string, not the path.
      if (path.split('?')[0].endsWith(suffix)) {
        const data = answer(init)
        const ok = data instanceof Error ? false : true
        return Promise.resolve({
          ok,
          json: async () => (data instanceof Error ? { detail: data.message } : data),
        })
      }
    }
    return Promise.resolve({ ok: true, json: async () => ({}) })
  })
  vi.stubGlobal('fetch', fetchMock)
  return { calls }
}

function mount() {
  return render(<PersonaHomesCard />)
}

describe('PersonaHomesCard', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('keeps itself to one muted line until a home is connected', async () => {
    stubGuestApi({ '/api/guest/homes': () => ({ homes: [] }) })
    mount()

    await screen.findByText(/Add a persona home/i)
    // The feature is not a primary one: no card, no persona list, nothing
    // but the door, until the user connects a home.
    expect(screen.queryByText(/Be someone else/i)).toBeNull()
    expect(screen.queryByRole('button', { name: /Be /i })).toBeNull()
  })

  it('lists the personas the connected homes offer', async () => {
    stubGuestApi()
    mount()

    expect(await screen.findByText(/Be someone else/i)).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: /Be Marnie/ })).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: /Be Ada/ })).toBeInTheDocument()
  })

  it('reports a home that did not answer', async () => {
    stubGuestApi({
      '/api/guest/available': () => ({
        personas: [PERSONAS[0]],
        unreachable: [{ home: 'H3', error: 'did not answer' }],
      }),
    })
    mount()

    expect(await screen.findByText(/Be Marnie/)).toBeInTheDocument()
    expect(await screen.findByText(/H3 did not answer/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Be Ada/ })).toBeNull()
  })

  it('wears a persona on click — name and home, so a name in two houses is not a guess', async () => {
    const user = userEvent.setup()
    const { calls } = stubGuestApi()
    mount()
    await user.click(await screen.findByRole('button', { name: /Be Marnie/ }))

    const become = calls.find((c) => c.url.endsWith('/api/guest/become'))
    expect(become, 'POST /api/guest/become was never called').toBeTruthy()
    expect(become!.init?.method).toBe('POST')
    expect(JSON.parse(become!.init!.body as string)).toEqual({
      name: 'Marnie',
      base_url: 'http://h2:8002',
    })
  })

  it('does not offer other faces while one is already on', async () => {
    stubGuestApi({ '/api/instance/info': () => INFO_FRONTING })
    mount()

    // The old pill's rule, kept: wearing one face and being offered another
    // reads as a costume rack; end the session from the top bar instead.
    expect(await screen.findByText(/Ada is speaking/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Be Marnie/ })).toBeNull()
    expect(screen.queryByRole('button', { name: /Be Ada/ })).toBeNull()
  })

  it('connects a home and then shows its personas', async () => {
    const user = userEvent.setup()
    const { calls } = stubGuestApi({ '/api/guest/homes': () => ({ homes: [] }) })
    mount()

    await user.click(await screen.findByText(/Add a persona home/i))
    await user.type(screen.getByLabelText(/Base URL/i), 'http://h2:8002')
    await user.type(screen.getByLabelText(/Label/i), 'H2')
    await user.type(screen.getByLabelText(/Token/i), 'secret')

    const added = vi.fn()
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      const path = String(url)
      calls.push({ url: path, init })
      if (path.endsWith('/api/guest/homes') && init?.method === 'POST') {
        added(JSON.parse(init.body as string))
        return Promise.resolve({ ok: true, json: async () => ({ status: 'ok' }) })
      }
      if (path.endsWith('/api/guest/homes')) return Promise.resolve({ ok: true, json: async () => ({ homes: HOMES.slice(0, 1) }) })
      if (path.endsWith('/api/guest/available')) return Promise.resolve({ ok: true, json: async () => ({ personas: [PERSONAS[0]], unreachable: [] }) })
      if (path.endsWith('/api/instance/info')) return Promise.resolve({ ok: true, json: async () => INFO_IDLE })
      return Promise.resolve({ ok: true, json: async () => ({}) })
    }))

    await user.click(screen.getByRole('button', { name: /^Add$/ }))

    await waitFor(() => expect(added).toHaveBeenCalled())
    expect(added.mock.calls[0][0]).toEqual({
      base_url: 'http://h2:8002',
      label: 'H2',
      token: 'secret',
      profile: 'default',
    })
    // The list follows the connection: the home's personas show up.
    expect(await screen.findByRole('button', { name: /Be Marnie/ })).toBeInTheDocument()
  })

  it('forgets a home', async () => {
    const user = userEvent.setup()
    const { calls } = stubGuestApi()
    mount()

    await user.click(await screen.findByRole('button', { name: /Forget H2/i }))

    const forget = calls.find((c) => c.url.includes('/api/guest/homes?') && c.init?.method === 'DELETE')
    expect(forget, 'DELETE /api/guest/homes was never called').toBeTruthy()
    expect(forget!.url).toContain('base_url=')
  })
})