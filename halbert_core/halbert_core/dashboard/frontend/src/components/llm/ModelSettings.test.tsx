// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * D-6 host wrapper around the model-picker package.
 *
 * Most of the picker's own behaviour (assignment, listing, testing) is
 * already covered by packages/model-picker's own test suite; these tests
 * cover only what this file adds on top of it:
 *
 *  - the three Halbert roles, with the vision slot's "Auto: inherit from the
 *    chat model" copy when it is unassigned (D-4/UI-SPEC Q3)
 *  - the LEG-MOD-02 cloud disclosure gate carried over from the deleted
 *    EndpointManager: a cloud-provider endpoint must not be saved until the
 *    user accepts, a local one needs no gate at all
 *  - the "add a provider" control this file hands the drawer, since the
 *    package auto-offers only the engines it discovered on this machine
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ModelSettings, needsDisclosure } from './ModelSettings'

function emptyLlmConfig() {
  return {
    saved_endpoints: [],
    chat_model: { enabled: false, endpoint_id: '', model: '' },
    specialist_model: { enabled: false, endpoint_id: '', model: '' },
    vision_model: { enabled: false, endpoint_id: '', model: '' },
    secure_model: { enabled: false, endpoint_id: '', model: '' },
  }
}

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response
}

/** Routes the handful of endpoints ModelSettings/the picker touch on mount. */
function makeRouter(llmConfig: ReturnType<typeof emptyLlmConfig>) {
  return vi.fn(async (url: string, init?: RequestInit) => {
    if (url === '/llm/config' && (!init || init.method === undefined)) {
      return jsonResponse({ data: { llm_config: llmConfig, chat_capable_providers: ['ollama', 'anthropic', 'openai'] } })
    }
    if (url === '/llm/config' && init?.method === 'PUT') {
      const body = JSON.parse(String(init.body))
      Object.assign(llmConfig, body.llm_config)
      return jsonResponse({ data: { llm_config: llmConfig, chat_capable_providers: ['ollama', 'anthropic', 'openai'] } })
    }
    if (url === '/api/llm/discover') {
      return jsonResponse({ data: { ollama: { running: false, url: 'http://localhost:11434', models: [] }, lm_studio: { running: false, url: 'http://localhost:1234', models: [] } } })
    }
    if (url === '/api/llm/proxy/models') {
      return jsonResponse({ data: { models: [], model_details: [] } })
    }
    if (url === '/api/legal/cloud-disclosure') {
      return jsonResponse({
        title: 'Cloud Model Data Flow Disclosure',
        summary: 'Enabling cloud models sends prompts to the provider.',
        what_is_sent: ['Prompts'],
        what_is_not_sent: ['Nothing else'],
        provider_policies: {},
        privacy_doc: 'PRIVACY.md',
      })
    }
    throw new Error(`unrouted fetch: ${init?.method ?? 'GET'} ${url}`)
  })
}

describe('needsDisclosure', () => {
  it('is true for every known cloud provider', () => {
    for (const provider of ['openai', 'anthropic', 'google', 'azure-openai', 'openai-compatible'] as const) {
      expect(needsDisclosure({ provider, url: 'https://x' })).toBe(true)
    }
  })

  it('is false for local ollama and lm-studio', () => {
    expect(needsDisclosure({ provider: 'ollama', url: 'http://localhost:11434' })).toBe(false)
    expect(needsDisclosure({ provider: 'lm-studio', url: 'http://localhost:1234' })).toBe(false)
  })

  it('is true for an ollama endpoint pointed at Ollama Cloud', () => {
    expect(needsDisclosure({ provider: 'ollama', url: 'https://ollama.com' })).toBe(true)
    expect(needsDisclosure({ provider: 'ollama', url: 'https://my-account.ollama.com' })).toBe(true)
  })

  it('does not throw on an unparseable url', () => {
    expect(needsDisclosure({ provider: 'ollama', url: 'not a url' })).toBe(false)
  })
})

describe('ModelSettings', () => {
  let fetchMock: ReturnType<typeof makeRouter>

  beforeEach(() => {
    fetchMock = makeRouter(emptyLlmConfig())
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders the three Halbert roles', async () => {
    render(<ModelSettings />)
    expect(await screen.findByText('Chat (Guide)')).toBeInTheDocument()
    expect(screen.getByText('Specialist')).toBeInTheDocument()
    expect(screen.getByText('Vision')).toBeInTheDocument()
  })

  it('shows the auto-inherit copy for an unassigned vision slot, never a model name', async () => {
    render(<ModelSettings />)
    await screen.findByText('Chat (Guide)')
    expect(screen.getByText(/Auto: inherit from the chat model/)).toBeInTheDocument()
  })

  it('gates a new cloud endpoint behind the disclosure modal before saving it', async () => {
    const user = userEvent.setup()
    render(<ModelSettings />)
    // Waited for by the control this test actually needs, not by a proxy for
    // it. 'Chat (Guide)' is a role label and renders early; the "Add a
    // provider" select lives in the drawer's providers region, which opens
    // from an effect gated on the picker having FINISHED loading. The two are
    // separate commits, and under a loaded machine (a full parallel run) the
    // gap between them is wide enough that a synchronous get lands in it.
    await user.selectOptions(await screen.findByLabelText(/add a provider/i), 'openai')

    const card = screen.getByRole('group', { name: /openai/i })
    await user.clear(within(card).getByLabelText(/address/i))
    await user.type(within(card).getByLabelText(/address/i), 'https://api.openai.test')
    await user.type(within(card).getByLabelText('Key'), 'sk-test')
    await user.click(within(card).getByRole('button', { name: /add/i }))

    expect(await screen.findByText(/Enable OpenAI cloud models\?/i)).toBeInTheDocument()
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === 'PUT')).toBe(false)

    await user.click(screen.getByRole('button', { name: /i understand, enable cloud models/i }))

    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([, init]) => init?.method === 'PUT')).toBe(true)
    })
    const [, putInit] = fetchMock.mock.calls.find(([, init]) => init?.method === 'PUT')!
    const body = JSON.parse(String(putInit!.body))
    expect(body.llm_config.saved_endpoints[0].url).toBe('https://api.openai.test')
  })

  it('never saves a declined cloud endpoint', async () => {
    const user = userEvent.setup()
    render(<ModelSettings />)
    // See the sibling test above: the select is a later commit than the
    // role labels, so it has to be waited for on its own account.
    await user.selectOptions(await screen.findByLabelText(/add a provider/i), 'anthropic')
    const card = screen.getByRole('group', { name: /anthropic/i })
    await user.type(within(card).getByLabelText(/address/i), 'https://api.anthropic.com')
    await user.type(within(card).getByLabelText('Key'), 'sk-ant')
    await user.click(within(card).getByRole('button', { name: /add/i }))

    await screen.findByText(/Enable Anthropic cloud models\?/i)
    await user.click(screen.getByRole('button', { name: /^cancel$/i }))

    await waitFor(() => {
      expect(screen.queryByText(/Enable Anthropic cloud models\?/i)).not.toBeInTheDocument()
    })
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === 'PUT')).toBe(false)
  })

  it('saves a local Ollama endpoint with no disclosure gate', async () => {
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      if (url === '/api/llm/discover') {
        return jsonResponse({ data: { ollama: { running: true, url: 'http://localhost:11434', version: '0.5', models: [] }, lm_studio: { running: false, url: 'http://localhost:1234', models: [] } } })
      }
      return makeRouter(emptyLlmConfig())(url, init)
    })

    const user = userEvent.setup()
    render(<ModelSettings />)
    await screen.findByText('Chat (Guide)')
    // The providers accordion auto-opens itself when there are no saved
    // endpoints yet, so it does not need a click here.

    const card = await screen.findByRole('group', { name: /local ollama|ollama/i })
    await user.click(within(card).getByRole('button', { name: /add/i }))

    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([, init]) => init?.method === 'PUT')).toBe(true)
    })
    expect(screen.queryByText(/enable.*cloud models\?/i)).not.toBeInTheDocument()
  })
})
