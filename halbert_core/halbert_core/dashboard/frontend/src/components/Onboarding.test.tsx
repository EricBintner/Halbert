// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * Onboarding machine roles: the wizard probes the machine while the
 * welcome screen is up, pre-checks the suggested roles on the configure
 * step, and POSTs a `roles` list — never the dead `user_type` single
 * select. The user's toggles always win over the suggestion.
 */
import { describe, it, expect, afterEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Onboarding } from './Onboarding'

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as Response
}

const PROBE = {
  signals: { has_display: true },
  suggestion: {
    roles: ['server'],
    scores: { workstation: -2, server: 8, home_automation_hub: 0 },
    reasons: ['no desktop session — it runs headless'],
    reasoning: 'I found no desktop session — it runs headless. I look like a server.',
  },
}

function stubFetch(overrides: Record<string, unknown> = {}) {
  const calls: Array<{ url: string; init?: RequestInit }> = []
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url, init })
    if (url.includes('/api/settings/onboarding/status')) {
      return jsonResponse({ onboarding_complete: false, suggested_name: 'Macky-Mac' })
    }
    if (url.includes('/api/settings/onboarding/probe')) {
      return jsonResponse(overrides.probe ?? PROBE)
    }
    if (url.includes('/api/settings/onboarding/complete')) {
      return jsonResponse({ status: 'complete', profile_summary: 'I am Macky-Mac.' })
    }
    return jsonResponse({}, 404)
  }))
  return calls
}

function postedJson(calls: Array<{ url: string; init?: RequestInit }>, urlPart: string) {
  const call = calls.find(c => c.url.includes(urlPart) && c.init?.method === 'POST')
  return call ? JSON.parse(String(call.init?.body)) : null
}

afterEach(() => vi.unstubAllGlobals())

describe('Onboarding machine roles', () => {
  it('asks what the computer is for, not what kind of user you are', async () => {
    stubFetch()
    render(<Onboarding open onComplete={() => {}} />)
    await userEvent.click(await screen.findByRole('button', { name: /get started/i }))

    expect(await screen.findByText('What is this computer for?')).toBeTruthy()
    expect(screen.queryByText(/primarily use this computer/i)).toBeNull()
    expect(screen.getByText('Workstation')).toBeTruthy()
    expect(screen.getByText('Server')).toBeTruthy()
    expect(screen.getByText('Home Hub')).toBeTruthy()
  })

  it('pre-checks the probe suggestion and shows its reasoning', async () => {
    stubFetch()
    render(<Onboarding open onComplete={() => {}} />)
    await userEvent.click(await screen.findByRole('button', { name: /get started/i }))

    await waitFor(() => {
      const serverChip = screen.getByText('Server').closest('button')
      expect(serverChip?.className).toContain('border-primary')
    })
    expect(await screen.findByText(/I look like a server/)).toBeTruthy()
  })

  it('lets the user override the suggestion and POSTs roles, never user_type', async () => {
    const calls = stubFetch()
    render(<Onboarding open onComplete={() => {}} />)
    await userEvent.click(await screen.findByRole('button', { name: /get started/i }))
    await waitFor(() => {
      expect(screen.getByText('Server').closest('button')?.className).toContain('border-primary')
    })

    // The suggestion said server; the user says workstation instead.
    await userEvent.click(screen.getByText('Server'))
    await userEvent.click(screen.getByText('Workstation'))
    await userEvent.click(screen.getByRole('button', { name: /scan system/i }))

    await waitFor(() => {
      const body = postedJson(calls, '/onboarding/complete')
      expect(body).not.toBeNull()
      expect(body.roles).toEqual(['workstation'])
      expect('user_type' in body).toBe(false)
    })
  })

  it('sends the optional note as notes', async () => {
    const calls = stubFetch()
    render(<Onboarding open onComplete={() => {}} />)
    await userEvent.click(await screen.findByRole('button', { name: /get started/i }))
    await waitFor(() => screen.getByText('Server'))
    await userEvent.type(screen.getByLabelText(/anything else/i), 'it also serves media')
    await userEvent.click(screen.getByRole('button', { name: /scan system/i }))

    await waitFor(() => {
      expect(postedJson(calls, '/onboarding/complete')?.notes).toBe('it also serves media')
    })
  })

  it('still completes when the probe fails — the chips just start empty', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      if (url.includes('/api/settings/onboarding/probe')) throw new Error('probe down')
      if (url.includes('/api/settings/onboarding/status')) {
        return jsonResponse({ onboarding_complete: false, suggested_name: 'Macky-Mac' })
      }
      if (url.includes('/api/settings/onboarding/complete')) {
        return jsonResponse({ status: 'complete' })
      }
      return jsonResponse({}, 404)
    }))
    render(<Onboarding open onComplete={() => {}} />)
    await userEvent.click(await screen.findByRole('button', { name: /get started/i }))
    await userEvent.click(await screen.findByText('Workstation'))
    expect(screen.getByRole('button', { name: /scan system/i })).toBeTruthy()
  })
})
