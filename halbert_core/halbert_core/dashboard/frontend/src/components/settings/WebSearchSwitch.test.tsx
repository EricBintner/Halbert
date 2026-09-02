// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * C3-08: web search is a visible switch, off by default. The card reads
 * GET /api/settings/web-search on mount, renders a role="switch" bound to
 * the saved setting, PUTs {enabled} on toggle, and says so when a
 * being.yml override pins the effective value away from the setting.
 */
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { WebSearchSwitch } from './WebSearchSwitch'

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response
}

function renderSwitch(initial: { enabled: boolean; effective: boolean }) {
  let state = { ...initial }
  const calls: Array<{ url: string; init?: RequestInit }> = []
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url, init })
    if (url === '/api/settings/web-search' && init?.method === 'PUT') {
      const body = JSON.parse(init.body as string) as { enabled: boolean }
      state = { enabled: body.enabled, effective: body.enabled }
      return jsonResponse({ status: 'ok', ...state })
    }
    if (url === '/api/settings/web-search') return jsonResponse({ status: 'ok', ...state })
    return jsonResponse({}, 404)
  })
  vi.stubGlobal('fetch', fetchMock)
  render(<WebSearchSwitch />)
  return { calls }
}

afterEach(() => vi.unstubAllGlobals())

describe('WebSearchSwitch', () => {
  it('loads the setting and renders an off switch with the egress label', async () => {
    const { calls } = renderSwitch({ enabled: false, effective: false })
    const sw = await screen.findByRole('switch')
    await waitFor(() => expect(sw.getAttribute('aria-checked')).toBe('false'))
    expect(screen.getByText(/Web search \(sends query text to a search engine\)/)).toBeTruthy()
    expect(calls.filter((c) => c.init?.method === 'PUT')).toHaveLength(0)
    expect(calls[0].url).toBe('/api/settings/web-search')
  })

  it('PUTs {enabled: true} on toggle and reflects the saved state', async () => {
    const user = userEvent.setup()
    const { calls } = renderSwitch({ enabled: false, effective: false })
    const sw = await screen.findByRole('switch')
    await waitFor(() => expect(sw.hasAttribute('disabled')).toBe(false))

    await user.click(sw)

    await waitFor(() => expect(sw.getAttribute('aria-checked')).toBe('true'))
    const puts = calls.filter((c) => c.init?.method === 'PUT')
    expect(puts).toHaveLength(1)
    expect(JSON.parse(puts[0].init!.body as string)).toEqual({ enabled: true })
  })

  it('renders on when the setting is on', async () => {
    renderSwitch({ enabled: true, effective: true })
    const sw = await screen.findByRole('switch')
    await waitFor(() => expect(sw.getAttribute('aria-checked')).toBe('true'))
    expect(screen.queryByText(/pinned off/i)).toBeNull()
  })

  it('says when being.yml pins the effective value off', async () => {
    renderSwitch({ enabled: true, effective: false })
    await screen.findByRole('switch')
    expect(await screen.findByText(/pinned off by being\.yml/i)).toBeTruthy()
  })

  it('leaves the switch disabled and shows an error when the setting cannot be read', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({}, 500)))
    render(<WebSearchSwitch />)
    const sw = await screen.findByRole('switch')
    await waitFor(() => expect(screen.getByText(/could not read the web search setting/i)).toBeTruthy())
    expect(sw.hasAttribute('disabled')).toBe(true)
  })
})
