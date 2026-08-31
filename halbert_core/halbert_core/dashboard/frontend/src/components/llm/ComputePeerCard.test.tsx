// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * The compute-peer settings card — the AI tab's whole surface on a
 * home variant (U6 S3 frontend / W15).
 *
 * An HA node has no model picker: the workstation's own configuration
 * governs which model answers. These tests pin the contract that replaces
 * the picker — the link surface and nothing else:
 *
 *  - the saved link is reported read-only, both slots resolving to the peer
 *  - "Test Connection" probes the backend's peer health route and shows the
 *    read-only model list the workstation advertises
 *  - "Use This Peer" persists the link through the pairing route
 *  - no model selection control ever appears on the card
 */
import { describe, it, expect, afterEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ComputePeerCard } from './ComputePeerCard'

const PEER_ENDPOINT = {
  id: 'ep-peer',
  name: 'Compute Peer',
  provider: 'peer',
  url: 'peer://desktop.lan:8000',
  api_key: 'tok-1',
}

function llmConfig(linked: boolean) {
  const slot = linked
    ? { enabled: true, endpoint_id: 'ep-peer', model: 'auto' }
    : { enabled: false, endpoint_id: '', model: '' }
  return {
    saved_endpoints: linked ? [PEER_ENDPOINT] : [],
    chat_model: slot,
    specialist_model: slot,
    vision_model: { enabled: false, endpoint_id: '', model: '' },
    secure_model: { enabled: false, endpoint_id: '', model: '' },
  }
}

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as Response
}

interface ProbeAnswer {
  data?: { ok: boolean; message: string; models: string[]; url: string }
  error?: { code?: string; message: string }
}

interface Options {
  linked?: boolean
  probe?: ProbeAnswer
  linkStatus?: number
}

/**
 * Render the card with the endpoints it touches routed, recording every
 * fetch. `linked` decides what the saved model configuration answers with.
 */
function renderCard({ linked = false, probe, linkStatus = 200 }: Options = {}) {
  const calls: Array<{ url: string; init?: RequestInit }> = []
  // Mutable so the link route can flip the configuration, the way the real
  // backend does: the card re-reads the link after persisting it.
  let nowLinked = linked
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url, init })
    if (url === '/llm/config') {
      return jsonResponse({
        data: { llm_config: llmConfig(nowLinked), chat_capable_providers: ['peer'] },
      })
    }
    if (url === '/compute/peer-probe') {
      if (probe?.error) return jsonResponse(probe)
      return jsonResponse({ data: probe?.data ?? {
        ok: true,
        message: 'Peer peer://desktop.lan:8000 answered the health probe.',
        models: ['m-alpha', 'm-beta'],
        url: 'peer://desktop.lan:8000',
      } })
    }
    if (url === '/api/peers/compute-peer') {
      if (linkStatus !== 200) return jsonResponse({ detail: 'forbidden' }, linkStatus)
      nowLinked = true
      return jsonResponse({
        status: 'linked',
        endpoint_id: 'ep-peer',
        url: 'peer://desktop.lan:8000',
        model: 'auto',
        slots: ['chat_model', 'specialist_model'],
      })
    }
    return jsonResponse({ data: {} })
  })
  vi.stubGlobal('fetch', fetchMock)
  render(<ComputePeerCard />)
  return { calls }
}

afterEach(() => vi.unstubAllGlobals())

const addressInput = () => screen.getByLabelText(/workstation address/i)
const testButton = () => screen.getByRole('button', { name: /test connection/i })
const linkButton = () => screen.getByRole('button', { name: /use this peer/i })

describe('ComputePeerCard', () => {
  it('reports the saved link read-only, both slots resolving to the peer', async () => {
    renderCard({ linked: true })

    expect(await screen.findByText(/Linked to/i)).toBeInTheDocument()
    expect(screen.getByText(/peer:\/\/desktop\.lan:8000/i)).toBeInTheDocument()
    expect(screen.getByText(/Chat and specialist turns both resolve to this peer\./i)).toBeInTheDocument()
    expect(screen.getByText(/governs which model serves them/i)).toBeInTheDocument()
    // Read-only: the address is prefilled from the link, never a picker.
    expect(addressInput()).toHaveValue('peer://desktop.lan:8000')
  })

  it('shows the unlinked state when no peer endpoint is saved', async () => {
    renderCard({})
    expect(await screen.findByText(/No compute peer linked yet/i)).toBeInTheDocument()
    expect(screen.queryByText(/Linked to/i)).not.toBeInTheDocument()
  })

  it('never offers a model selection control', async () => {
    renderCard({})
    await screen.findByText(/No compute peer linked yet/i)
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
  })

  it('probes the peer health route from Test Connection and shows the model list', async () => {
    const user = userEvent.setup()
    const { calls } = renderCard({})

    await screen.findByText(/No compute peer linked yet/i)
    await user.type(addressInput(), 'desktop.lan:8000')
    await user.click(testButton())

    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent(/reachable/i))
    expect(screen.getByText(/The workstation serves:/i)).toBeInTheDocument()
    expect(screen.getByText(/m-alpha, m-beta/i)).toBeInTheDocument()

    const probeCall = calls.find((c) => c.url === '/compute/peer-probe')
    expect(probeCall).toBeDefined()
    expect(JSON.parse(String(probeCall!.init?.body))).toEqual({
      endpoint: 'desktop.lan:8000',
      token: '',
    })
  })

  it('reports an unreachable peer without inventing a model list', async () => {
    const user = userEvent.setup()
    renderCard({
      probe: {
        data: {
          ok: false,
          message: 'Peer peer://x:8000 did not answer the health probe.',
          models: [],
          url: 'peer://x:8000',
        },
      },
    })

    await screen.findByText(/No compute peer linked yet/i)
    await user.type(addressInput(), 'x:8000')
    await user.click(testButton())

    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent(/unreachable/i))
    expect(screen.queryByText(/The workstation serves:/i)).not.toBeInTheDocument()
  })

  it('surfaces a probe error the backend refused to make', async () => {
    const user = userEvent.setup()
    renderCard({
      probe: {
        error: {
          code: 'NOT_HOME_VARIANT',
          message: 'Compute-peer probing is a home feature.',
        },
      },
    })

    await screen.findByText(/No compute peer linked yet/i)
    await user.type(addressInput(), 'desktop.lan:8000')
    await user.click(testButton())

    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(/home feature/i),
    )
  })

  it('persists the link through the pairing route, then re-reads it', async () => {
    const user = userEvent.setup()
    const { calls } = renderCard({})

    await screen.findByText(/No compute peer linked yet/i)
    await user.type(addressInput(), 'desktop.lan:8000')
    await user.type(screen.getByLabelText(/pairing token/i), 'tok-1')
    await user.click(linkButton())

    await waitFor(() => expect(screen.getByText(/Linked to/i)).toBeInTheDocument())

    const linkCall = calls.find((c) => c.url === '/api/peers/compute-peer')
    expect(linkCall).toBeDefined()
    expect(JSON.parse(String(linkCall!.init?.body))).toEqual({
      endpoint: 'desktop.lan:8000',
      token: 'tok-1',
      name: '',
    })
  })

  it('disables both actions while no address is entered', async () => {
    renderCard({})
    await screen.findByText(/No compute peer linked yet/i)

    expect(testButton()).toBeDisabled()
    expect(linkButton()).toBeDisabled()
  })

  it('reports a failed link instead of pretending the peer was saved', async () => {
    const user = userEvent.setup()
    renderCard({ linkStatus: 403 })

    await screen.findByText(/No compute peer linked yet/i)
    await user.type(addressInput(), 'desktop.lan:8000')
    await user.click(linkButton())

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent(/Link failed/i))
    expect(screen.queryByText(/Linked to/i)).not.toBeInTheDocument()
  })
})