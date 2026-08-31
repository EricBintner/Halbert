// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * D-5: `/model` in the composer.
 *
 * The parser has its own unit tests. These cover the wiring the parser cannot
 * see: that a command never reaches the backend, that it moves the same pin
 * the pill shows, and that ordinary input is still sent.
 *
 * The pin surface exists on the sysadmin variant; a home/home-light variant
 * is a pure client of the workstation's compute endpoint (S3), carries no
 * model control at all, and answers `/model` by saying so — those are the
 * tests at the bottom.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AgentChat } from './AgentChat'

const ENDPOINT = {
  id: 'ep1', name: 'Local', provider: 'ollama',
  url: 'http://localhost:11434', api_key: '',
}

function jsonResponse(body: unknown) {
  return { ok: true, status: 200, json: async () => body } as Response
}

// The empty-state greeting reads host identity on mount and will throw on a
// partial shape, taking the whole component down with it.
const IDENTITY = {
  display_name: 'Test-Host',
  hostname: 'test-host.local',
  os: { name: 'macOS', version: '26.5.1', pretty: 'macOS 26.5.1', platform: 'Darwin', kernel: '25.5.0', arch: 'arm64' },
  uptime: { seconds: 86400, human: '1 day', boot_time: '' },
  cpu: { cores: 8, physical_cores: 8, percent: 12, temperature: null },
  memory: { total_gb: 32, used_gb: 8, percent: 25 },
  storage: { pools: [], healthy: 0, total: 0 },
  load_average: { '1min': 1, '5min': 1, '15min': 1 },
  all_healthy: true,
  first_person: 'I am Test-Host.',
  timestamp: '',
}

let fetchMock: ReturnType<typeof vi.fn>

// The variant each test's instance reports. Most of the suite runs as
// sysadmin — the one variant where the pin surface exists. The home tests at
// the bottom switch this before rendering.
let instanceVariant = 'sysadmin'

beforeEach(() => {
  instanceVariant = 'sysadmin'
  // jsdom implements neither, and AgentChat uses both on mount.
  Element.prototype.scrollIntoView = vi.fn()
  HTMLCanvasElement.prototype.getContext = vi.fn() as never

  fetchMock = vi.fn(async (url: string) => {
    const u = String(url)
    if (u.includes('/api/identity')) return jsonResponse(IDENTITY)
    if (u.includes('/api/instance/info')) return jsonResponse({ variant: instanceVariant })
    if (u.includes('/llm/config')) {
      return jsonResponse({ data: {
        llm_config: {
          saved_endpoints: [ENDPOINT],
          chat_model: { enabled: true, endpoint_id: 'ep1', model: 'model-alpha' },
          specialist_model: { enabled: false, endpoint_id: '', model: '' },
          vision_model: { enabled: false, endpoint_id: '', model: '' },
          secure_model: { enabled: false, endpoint_id: '', model: '' },
        },
        chat_capable_providers: ['ollama'],
      } })
    }
    if (u.includes('/api/llm/discover')) {
      return jsonResponse({ data: {
        ollama: { running: true, url: ENDPOINT.url, version: '1.0', models: ['model-alpha', 'model-beta'] },
        lm_studio: { running: false, url: 'http://localhost:1234', models: [] },
      } })
    }
    if (u.includes('proxy/models')) {
      return jsonResponse({ data: {
        models: ['model-alpha', 'model-beta'],
        model_details: [{ name: 'model-alpha' }, { name: 'model-beta' }],
      } })
    }
    return jsonResponse({ data: {} })
  })
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => vi.unstubAllGlobals())

function sends() {
  return fetchMock.mock.calls.filter(([u]) => String(u).includes('/api/agent/message'))
}

async function type(text: string) {
  const box = await screen.findByRole('textbox')
  await userEvent.clear(box)
  await userEvent.type(box, text)
  await userEvent.keyboard('{Enter}')
}

describe('AgentChat /model command', () => {
  it('does not send a command to the agent', async () => {
    render(<AgentChat />)
    await screen.findByRole('combobox')
    await type('/model auto')
    await waitFor(() => expect(screen.getByText(/automatic routing/i)).toBeInTheDocument())
    expect(sends()).toHaveLength(0)
  })

  it('still sends ordinary input', async () => {
    render(<AgentChat />)
    await screen.findByRole('combobox')
    await type('what is my disk usage')
    await waitFor(() => expect(sends()).toHaveLength(1))
  })

  it('sends input that merely starts with a slash but is not /model', async () => {
    // /models and /help belong to nobody yet; claiming them would swallow them.
    render(<AgentChat />)
    await screen.findByRole('combobox')
    await type('/models please')
    await waitFor(() => expect(sends()).toHaveLength(1))
  })

  it('pins a uniquely matching model and says so', async () => {
    render(<AgentChat />)
    await screen.findByRole('combobox')
    await waitFor(() => expect(fetchMock.mock.calls.some(([u]) => String(u).includes('proxy/models'))).toBe(true))

    await type('/model beta')
    await waitFor(() => expect(screen.getByText(/Pinned to model-beta/i)).toBeInTheDocument())
  })

  it('opens the picker instead of guessing when the query is ambiguous', async () => {
    render(<AgentChat />)
    const trigger = await screen.findByRole('combobox')
    await waitFor(() => expect(fetchMock.mock.calls.some(([u]) => String(u).includes('proxy/models'))).toBe(true))

    await type('/model model-')
    await waitFor(() => expect(trigger).toHaveAttribute('aria-expanded', 'true'))
    expect(sends()).toHaveLength(0)
  })

  it('reports a query that matches nothing rather than failing silently', async () => {
    render(<AgentChat />)
    await screen.findByRole('combobox')
    await type('/model nothing-like-this')
    await waitFor(() =>
      expect(screen.getByText(/No configured model matches/i)).toBeInTheDocument(),
    )
  })

  it('prints a status card for /model status', async () => {
    render(<AgentChat />)
    await screen.findByRole('combobox')
    await type('/model status')
    await waitFor(() =>
      expect(screen.getByLabelText(/active model status/i)).toBeInTheDocument(),
    )
    expect(sends()).toHaveLength(0)
  })

  it('never writes a pin to the stored configuration', async () => {
    render(<AgentChat />)
    await screen.findByRole('combobox')
    await waitFor(() => expect(fetchMock.mock.calls.some(([u]) => String(u).includes('proxy/models'))).toBe(true))
    await type('/model beta')
    await waitFor(() => expect(screen.getByText(/Pinned to model-beta/i)).toBeInTheDocument())

    const writes = fetchMock.mock.calls.filter(
      ([, init]) => (init as RequestInit | undefined)?.method === 'PUT',
    )
    expect(writes).toEqual([])
  })
})

describe('AgentChat /model on a peer-governed (home) variant', () => {
  beforeEach(() => {
    instanceVariant = 'home'
  })

  it('carries no model control in the composer', async () => {
    render(<AgentChat />)
    await screen.findByRole('textbox')
    // The variant arrives after mount; wait for the pill to be gone rather
    // than asserting against the one render pass before the info lands.
    await waitFor(() => expect(screen.queryByRole('combobox')).not.toBeInTheDocument())
  })

  it('answers /model by naming the workstation, and never reaches the agent', async () => {
    render(<AgentChat />)
    await screen.findByRole('textbox')
    await waitFor(() => expect(screen.queryByRole('combobox')).not.toBeInTheDocument())

    await type('/model auto')
    await waitFor(() =>
      expect(screen.getByText(/governed by the paired workstation/i)).toBeInTheDocument(),
    )
    expect(sends()).toHaveLength(0)
  })

  it('still sends ordinary input', async () => {
    render(<AgentChat />)
    await screen.findByRole('textbox')
    await type('is the front door locked')
    await waitFor(() => expect(sends()).toHaveLength(1))
  })
})
