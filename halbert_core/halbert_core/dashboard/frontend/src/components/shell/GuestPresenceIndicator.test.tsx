// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * GuestPresenceIndicator — the top bar's guest-persona half of the old
 * PresencePill (§5R.3 N1).
 *
 * The rail's EntityNodeBlock owns node navigation now; this component owns
 * the one thing the rail deliberately does not: who is speaking when that
 * someone is not the machine. It renders NOTHING while no guest fronts —
 * the top bar stays exactly as §6.2 enumerates it — and appears on its own
 * the moment a face goes on, because it polls /api/instance/info and a
 * session can begin without it asking (chat's become tool, another home
 * lending a face, a pull from Settings).
 *
 * The old pill's node-switching tests (W1-02 / W4-03) live with the rail
 * now; the ones here are the fronting behaviours the pill already had,
 * plus the two the split adds: idle means invisible, and node switching is
 * gone from this surface entirely.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { GuestPresenceIndicator } from './GuestPresenceIndicator'
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
  {
    id: 'webcam:desk', label: 'Desk webcam', kind: 'webcam', owner: 'halbert',
    statement:
      'Macky stops recording what you say and what Desk webcam sees. It keeps ' +
      'recording what the machine and the rest of the house are doing. Life ' +
      'safety still reaches Macky.',
  },
  {
    id: 'mic:local:study', label: 'study', kind: 'mic', owner: 'halbert',
    statement: 'Macky stops recording what you say and what study sees. …',
  },
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
    if (path.endsWith('/api/guest')) {
      return Promise.resolve({ ok: true, json: async () => ({ fronting, private_sources: handedOver }) })
    }
    return Promise.resolve({ ok: true, json: async () => ({ ...INFO, fronting }) })
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function stubIdleFetch() {
  const fetchMock = vi.fn().mockImplementation(() =>
    Promise.resolve({ ok: true, json: async () => ({ ...INFO, fronting: null }) }),
  )
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function mount() {
  return render(<GuestPresenceIndicator />)
}

describe('GuestPresenceIndicator', () => {
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

  it('reads who is fronting through the resolved API base (Tauri webview)', async () => {
    window.__HALBERT_API_BASE__ = 'http://127.0.0.1:8042'
    const fetchMock = stubIdleFetch()
    mount()

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith('http://127.0.0.1:8042/api/instance/info'),
    )
  })

  it('renders nothing while no guest fronts', async () => {
    const fetchMock = stubIdleFetch()
    const { container } = mount()

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('/api/instance/info')),
    )
    // Idle means invisible: no identity text (the rail owns that), no
    // empty trigger, nothing at all.
    expect(container.innerHTML).toBe('')
  })

  it('carries none of the old pill\'s node-switching UI', async () => {
    stubFrontingFetch()
    mount()
    await screen.findByText('Macky · as Ada')

    expect(screen.queryByText(/Link Another Device/i)).toBeNull()
    expect(screen.queryByText(/Manage Linked Devices/i)).toBeNull()
    expect(screen.queryByText(/Independent Node|Singular Entity/i)).toBeNull()
  })

  describe('a guest persona fronting', () => {
    it('shows both names, never the guest alone', async () => {
      stubFrontingFetch()
      mount()

      // I4: the machine's own name stays, so the user can tell what is
      // holding the tools. "Ada" alone would be the failure.
      expect(await screen.findByText('Macky · as Ada')).toBeInTheDocument()
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

    it('ending the session takes the face off — and the indicator with it', async () => {
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
      // No guest, no indicator: the top bar returns to §6.2's inventory.
      await waitFor(() => expect(screen.queryByText(/Macky · as Ada/)).toBeNull())
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
      // Server-written and scoped to a source, not the component's own copy:
      // handing over the desk webcam does not stop the patio camera.
      expect(said).toHaveTextContent(/what Desk webcam sees/i)
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

    it('keeps hand-over and end-session to the local machine', async () => {
      // Handing a source over is require_local_admin, and so is ending the
      // session from here: pointed at another node, the face is shown (the
      // transparency guarantee follows the view) but the controls are not.
      const user = userEvent.setup()
      setInstanceEndpoint('http://x:8001')
      stubFrontingFetch()
      mount()
      await screen.findByText('Macky · as Ada')

      await user.click(screen.getByRole('button', { name: /Macky/ }))
      await screen.findByText(/lent by the study tablet/)

      expect(screen.queryByRole('button', { name: /end guest session/i })).toBeNull()
      expect(screen.queryByLabelText(/Hand Desk webcam to Ada/i)).toBeNull()
    })
  })
})