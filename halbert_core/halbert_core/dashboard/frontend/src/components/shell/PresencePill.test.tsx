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

const AVAILABLE = [
  { persona_id: 'marnie-7', name: 'Marnie', home_label: 'H2', base_url: 'http://h2:8002' },
]

const FRONTING = {
  home: { base_url: 'http://h2:8002', persona_id: 'marnie-7', label: 'H2' },
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
const CATALOGUE = [
  { id: 'webcam:desk', label: 'Desk webcam', kind: 'webcam', owner: 'halbert' },
  { id: 'mic:local:study', label: 'study', kind: 'mic', owner: 'halbert' },
]

function stubFrontingFetch() {
  let fronting: typeof FRONTING | null = FRONTING
  let handedOver: Record<string, string> = {}
  const fetchMock = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
    const path = String(url)
    if (path.endsWith('/api/guest/end')) {
      expect(init?.method).toBe('POST')
      fronting = null
      return Promise.resolve({ ok: true, json: async () => ({ status: 'ok' }) })
    }
    if (path.endsWith('/api/guest/private/sources')) {
      return Promise.resolve({ ok: true, json: async () => ({ sources: CATALOGUE }) })
    }
    if (path.endsWith('/api/guest/private/assign')) {
      const body = JSON.parse(init!.body as string)
      handedOver = { ...handedOver, [body.source_id]: 'guest' }
      return Promise.resolve({ ok: true, json: async () => ({ private_sources: handedOver }) })
    }
    if (path.endsWith('/api/guest/private/release')) {
      const body = JSON.parse(init!.body as string)
      const next = { ...handedOver }
      delete next[body.source_id]
      handedOver = next
      return Promise.resolve({ ok: true, json: async () => ({ private_sources: handedOver }) })
    }
    if (path.endsWith('/api/guest/available')) {
      return Promise.resolve({ ok: true, json: async () => ({ personas: AVAILABLE }) })
    }
    if (path.endsWith('/api/guest/become')) {
      fronting = FRONTING
      return Promise.resolve({ ok: true, json: async () => ({ status: 'ok' }) })
    }
    if (path.endsWith('/api/guest')) {
      return Promise.resolve({ ok: true, json: async () => ({ fronting, private_sources: handedOver }) })
    }
    return Promise.resolve({ ok: true, json: async () => ({ ...INFO, fronting }) })
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function stubIdleWithHomes() {
  const calls: Array<{ url: string; init?: RequestInit }> = []
  let fronting: typeof FRONTING | null = null
  const fetchMock = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
    const path = String(url)
    calls.push({ url: path, init })
    if (path.endsWith('/api/guest/available')) {
      return Promise.resolve({ ok: true, json: async () => ({ personas: AVAILABLE }) })
    }
    if (path.endsWith('/api/guest/become')) {
      fronting = FRONTING
      return Promise.resolve({ ok: true, json: async () => ({ status: 'ok' }) })
    }
    return Promise.resolve({ ok: true, json: async () => ({ ...INFO, fronting }) })
  })
  vi.stubGlobal('fetch', fetchMock)
  return { calls }
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

    it('says what handing a source over means, before the first one is handed over', async () => {
      const user = userEvent.setup()
      stubFrontingFetch()
      mount()
      await screen.findByText('Macky · as Ada')

      await user.click(screen.getByRole('button', { name: /Macky/ }))

      // P6: a toggle labelled "private" with no stated scope is a promise the
      // system cannot keep — the cameras and the house sensors do not stop.
      const said = await screen.findByText(/stops recording what you say/i)
      expect(said).toHaveTextContent(/keeps recording what the machine and the rest of the house/i)
      expect(said).toHaveTextContent(/Life safety still reaches/i)
    })

    it('hands one source over and stops repeating the statement', async () => {
      const user = userEvent.setup()
      const fetchMock = stubFrontingFetch()
      mount()
      await screen.findByText('Macky · as Ada')
      await user.click(screen.getByRole('button', { name: /Macky/ }))

      await user.click(await screen.findByLabelText(/Hand Desk webcam to Ada/i))

      await waitFor(() =>
        expect(fetchMock).toHaveBeenCalledWith(
          expect.stringContaining('/api/guest/private/assign'),
          expect.objectContaining({ method: 'POST' }),
        ),
      )
      await waitFor(() =>
        expect(screen.queryByText(/stops recording what you say/i)).toBeNull(),
      )
    })

    it('offers the microphone alongside the camera', async () => {
      const user = userEvent.setup()
      stubFrontingFetch()
      mount()
      await screen.findByText('Macky · as Ada')
      await user.click(screen.getByRole('button', { name: /Macky/ }))

      // One list across the senses: a private mode that gates one and not
      // another is worse than none.
      expect(await screen.findByLabelText(/Hand study to Ada/i)).toBeInTheDocument()
    })

    it('names the home the face came from', async () => {
      const user = userEvent.setup()
      stubFrontingFetch()
      mount()
      await screen.findByText('Macky · as Ada')

      await user.click(screen.getByRole('button', { name: /Macky/ }))

      expect(await screen.findByText(/home: H2/)).toBeInTheDocument()
    })

    it('offers the faces this machine could wear, and wears one', async () => {
      const user = userEvent.setup()
      const { calls } = stubIdleWithHomes()
      mount()
      await screen.findByText('Macky @ desk')

      // Asked only when the dropdown opens: this reaches out to every known
      // home, and the pill should not knock on the neighbours on page load.
      expect(calls.some((c) => c.url.endsWith('/api/guest/available'))).toBe(false)
      await user.click(screen.getByRole('button', { name: /Macky/ }))

      await user.click(await screen.findByRole('button', { name: /Be Marnie/ }))

      await waitFor(() =>
        expect(calls.some((c) => c.url.endsWith('/api/guest/become'))).toBe(true),
      )
      const body = JSON.parse(
        calls.find((c) => c.url.endsWith('/api/guest/become'))!.init!.body as string,
      )
      // The name and the home, so a name in two houses is not a guess.
      expect(body).toEqual({ name: 'Marnie', base_url: 'http://h2:8002' })
    })

    it('does not offer other faces while one is already on', async () => {
      const user = userEvent.setup()
      stubFrontingFetch()
      mount()
      await screen.findByText('Macky · as Ada')
      await user.click(screen.getByRole('button', { name: /Macky/ }))
      expect(screen.queryByText(/Be someone else/i)).toBeNull()
    })
  })
})
