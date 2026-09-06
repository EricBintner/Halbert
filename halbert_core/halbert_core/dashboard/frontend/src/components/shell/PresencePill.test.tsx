// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * PresencePill — the top-bar identity indicator.
 *
 * The pill's own info fetch must go through the resolved API base: a bare
 * relative URL resolves against tauri://localhost in the packaged app and
 * the pill shows the fallback body name regardless of the backend. And a
 * body switch persists, so the pill that mounts after the reload reports
 * the switched-to body as active (W1-02 / W4-03).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { PresencePill } from './PresencePill'
import { setInstanceEndpoint } from '@/lib/apiBase'

const INFO = {
  persona_id: 'p',
  scene_context: 'desk',
  role: 'host',
  variant: 'workstation',
  display_name: 'Macky',
  port: 8000,
  features: { home: false, gpu: false, development: false, wyoming_port: 0 },
  data_dir: '',
  config_dir: '',
  body_name: 'desk',
  singular: true,
}

const FRONTING = {
  session_id: 's1',
  name: 'Ada',
  offered_by: 'peer-1',
  offered_by_name: 'the study tablet',
  started_at: '2026-09-06T10:00:00+00:00',
  seconds_until_expiry: 55,
  active: true,
  end_reason: null,
}

/** Instance info with a guest fronting; POST /api/guest/end answers ok and
 * the next info read has the face off. */
function stubFrontingFetch() {
  let fronting: typeof FRONTING | null = FRONTING
  const fetchMock = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
    if (String(url).endsWith('/api/guest/end')) {
      expect(init?.method).toBe('POST')
      fronting = null
      return Promise.resolve({ ok: true, json: async () => ({ status: 'ok' }) })
    }
    return Promise.resolve({ ok: true, json: async () => ({ ...INFO, fronting }) })
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function stubInfoFetch() {
  const fetchMock = vi.fn().mockImplementation(() =>
    Promise.resolve({
      ok: true,
      json: async () => ({
        persona_id: 'p',
        scene_context: 'desk',
        role: 'host',
        variant: 'workstation',
        display_name: 'Macky',
        port: 8000,
        features: { home: false, gpu: false, development: false, wyoming_port: 0 },
        data_dir: '',
        config_dir: '',
        body_name: 'desk',
        singular: true,
      }),
    }),
  )
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function mount() {
  return render(
    <MemoryRouter>
      <PresencePill />
    </MemoryRouter>,
  )
}

describe('PresencePill', () => {
  beforeEach(() => {
    localStorage.clear()
    setInstanceEndpoint(null)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    delete window.__HALBERT_API_BASE__
    setInstanceEndpoint(null)
    localStorage.clear()
  })

  it('fetches the local body through the resolved API base (Tauri webview)', async () => {
    window.__HALBERT_API_BASE__ = 'http://127.0.0.1:8042'
    const fetchMock = stubInfoFetch()
    mount()

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith('http://127.0.0.1:8042/api/instance/info'),
    )
    expect(await screen.findByText('Macky @ desk')).toBeInTheDocument()
  })

  it('fetches the switched-to body after a reload', async () => {
    // The switch happened on the previous page load; the override outlived it.
    setInstanceEndpoint('http://x:8001')
    const fetchMock = stubInfoFetch()
    mount()

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith('http://x:8001/api/instance/info'),
    )
  })

  describe('a guest persona fronting', () => {
    it('shows both names, never the guest alone', async () => {
      stubFrontingFetch()
      mount()

      // I4: the machine's own name stays, so the user can tell what is
      // holding the tools. "Ada" alone would be the failure.
      expect(await screen.findByText('Macky · as Ada')).toBeInTheDocument()
    })

    it('reads Macky @ desk again once the face is off', async () => {
      stubInfoFetch()
      mount()
      expect(await screen.findByText('Macky @ desk')).toBeInTheDocument()
    })

    it('names who lent the face and offers to take it off', async () => {
      const user = userEvent.setup()
      stubFrontingFetch()
      mount()
      await screen.findByText('Macky · as Ada')

      await user.click(screen.getByRole('button', { name: /Macky/ }))

      expect(await screen.findByText(/lent by the study tablet/)).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /end guest session/i })).toBeInTheDocument()
    })

    it('ending the session takes the face off', async () => {
      const user = userEvent.setup()
      const fetchMock = stubFrontingFetch()
      mount()
      await screen.findByText('Macky · as Ada')

      await user.click(screen.getByRole('button', { name: /Macky/ }))
      await user.click(screen.getByRole('button', { name: /end guest session/i }))

      await waitFor(() =>
        expect(fetchMock).toHaveBeenCalledWith(
          expect.stringContaining('/api/guest/end'),
          expect.objectContaining({ method: 'POST' }),
        ),
      )
      expect(await screen.findByText('Macky @ desk')).toBeInTheDocument()
    })
  })
})
