// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * SecurityTab tests: the MCP Trust Boundary settings surface. Covers the
 * Tier 1 operational-value rocker (immediate POST), the Tier 2 secrets vault
 * (locked/unlocked states, the escape-hatch modal's phrase gate, and
 * re-locking), and the per-key cloud exception tag input -- each of these
 * saves by POSTing the full `security` object to /api/settings/being
 * (merged from the current config plus the field(s) being changed).
 */
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { SecurityTab } from './SecurityTab'

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response
}

function defaultSecurity(overrides: Record<string, unknown> = {}) {
  return {
    operational_tier: 'cloud_ok',
    secret_tier: 'local_only',
    secret_tier_expiry: null,
    public_files: ['/etc/hosts', '/etc/hostname', '/etc/fstab'],
    extra_secret_keys: [],
    cloud_ok_keys: [],
    ...overrides,
  }
}

/**
 * Render the tab with /api/settings/being and the telemetry endpoint
 * routed against a mutable `security` object, so a POST's merge is
 * reflected in the config the tab re-reads (like the real backend).
 */
function renderTab(initialSecurity: Record<string, unknown> = {}) {
  let security = defaultSecurity(initialSecurity)
  const calls: Array<{ url: string; init?: RequestInit }> = []
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url, init })
    if (url === '/api/settings/being' && init?.method === 'POST') {
      const body = JSON.parse(init.body as string)
      security = { ...security, ...body.security }
      return jsonResponse({ status: 'ok', config: { security } })
    }
    if (url === '/api/settings/being') {
      return jsonResponse({ status: 'ok', config: { security } })
    }
    if (url === '/api/settings/security/telemetry') {
      return jsonResponse({
        tier_0: 12,
        tier_1: 4,
        tier_2: 3,
        total: 19,
        secret_tier: security.secret_tier,
        operational_tier: security.operational_tier,
        cloud_ok_keys_count: (security.cloud_ok_keys as string[]).length,
        secret_tier_expiry: security.secret_tier_expiry,
      })
    }
    return jsonResponse({ status: 'ok' })
  })
  vi.stubGlobal('fetch', fetchMock)
  render(<SecurityTab />)
  return { calls, getSecurity: () => security }
}

afterEach(() => vi.unstubAllGlobals())

describe('SecurityTab', () => {
  it('loads config and telemetry, and renders the locked Tier 2 state by default', async () => {
    renderTab()
    expect(await screen.findByText('LOCKED (LOCAL ONLY)')).toBeTruthy()
    expect(screen.getByRole('radio', { name: /cloud ok/i })).toHaveAttribute('aria-checked', 'true')
  })

  it('shows a failure message and drops the config when the initial load fails', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse({ detail: 'boom' }, 500)),
    )
    render(<SecurityTab />)
    expect(await screen.findByText(/Failed to load config/i)).toBeTruthy()
  })

  it('switching Tier 1 to Local Only POSTs the merged security update', async () => {
    const user = userEvent.setup()
    const { calls } = renderTab()
    await screen.findByText('LOCKED (LOCAL ONLY)')

    await user.click(screen.getByRole('radio', { name: /local only/i }))

    await waitFor(() => {
      const post = calls.find((c) => c.url === '/api/settings/being' && c.init?.method === 'POST')
      expect(post).toBeTruthy()
      const body = JSON.parse(post!.init!.body as string)
      expect(body.security.operational_tier).toBe('local_only')
    })
  })

  it('unlocking Tier 2 requires typing the exact phrase before it can be confirmed', async () => {
    const user = userEvent.setup()
    const { calls } = renderTab()
    await screen.findByText('LOCKED (LOCAL ONLY)')

    await user.click(screen.getByRole('button', { name: /unlock cloud access/i }))
    expect(screen.getByText('Expose Machine Secrets to Cloud LLMs?')).toBeTruthy()

    const confirmButton = screen.getByRole('button', { name: /i accept the risk/i })
    expect(confirmButton).toBeDisabled()

    const phraseInput = screen.getByPlaceholderText('EXPOSE SECRETS')
    await user.type(phraseInput, 'nope')
    expect(confirmButton).toBeDisabled()

    await user.clear(phraseInput)
    await user.type(phraseInput, 'EXPOSE SECRETS')
    expect(confirmButton).toBeEnabled()

    await user.click(confirmButton)

    await waitFor(() => {
      const post = calls.find((c) => c.url === '/api/settings/being' && c.init?.method === 'POST')
      expect(post).toBeTruthy()
      const body = JSON.parse(post!.init!.body as string)
      expect(body.security.secret_tier).toBe('cloud_ok_acknowledged')
      expect(body.security.phrase).toBe('EXPOSE SECRETS')
      expect(body.security.volatile_unlock).toBe(false)
      expect(typeof body.security.secret_tier_expiry).toBe('string')
    })
  })

  it('re-locking sends secret_tier local_only with no expiry', async () => {
    const user = userEvent.setup()
    const { calls } = renderTab({ secret_tier: 'cloud_ok_acknowledged' })
    expect(await screen.findByText('SECRETS EXPOSED')).toBeTruthy()

    await user.click(screen.getByRole('button', { name: /re-lock secrets immediately/i }))

    await waitFor(() => {
      const post = calls.find((c) => c.url === '/api/settings/being' && c.init?.method === 'POST')
      expect(post).toBeTruthy()
      const body = JSON.parse(post!.init!.body as string)
      expect(body.security).toMatchObject({
        secret_tier: 'local_only',
        secret_tier_expiry: null,
        volatile_unlock: false,
      })
    })
  })

  it('adding a per-key cloud exception POSTs the updated cloud_ok_keys array', async () => {
    const user = userEvent.setup()
    const { calls } = renderTab()
    await screen.findByText('LOCKED (LOCAL ONLY)')

    await user.type(screen.getByPlaceholderText(/weather_api_key/i), 'MY_KEY')
    await user.click(screen.getByRole('button', { name: /add exception/i }))

    await waitFor(() => {
      const post = calls.find((c) => c.url === '/api/settings/being' && c.init?.method === 'POST')
      expect(post).toBeTruthy()
      const body = JSON.parse(post!.init!.body as string)
      expect(body.security.cloud_ok_keys).toEqual(['MY_KEY'])
    })
  })
})
