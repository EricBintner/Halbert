// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * D-2: the in-chat model control.
 *
 * The package's own suite covers the pill and popover mechanics. These cover
 * what this wrapper adds: that it reports a pin upward so it can ride on the
 * next send, that a pin is never written to the stored configuration, and that
 * the health of the endpoint reaches the user.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ChatModelPill } from './ChatModelPill'

function jsonResponse(body: unknown) {
  return { ok: true, status: 200, json: async () => body } as Response
}

const ENDPOINT = {
  id: 'ep1', name: 'Local', provider: 'ollama',
  url: 'http://localhost:11434', api_key: '',
}

function config(overrides: Record<string, unknown> = {}) {
  return {
    saved_endpoints: [ENDPOINT],
    chat_model: { enabled: true, endpoint_id: 'ep1', model: 'model-a' },
    specialist_model: { enabled: false, endpoint_id: '', model: '' },
    vision_model: { enabled: false, endpoint_id: '', model: '' },
    ...overrides,
  }
}

let fetchMock: ReturnType<typeof vi.fn>

function route(ollamaRunning = true) {
  return vi.fn(async (url: string) => {
    const u = String(url)
    if (u.includes('/llm/config')) {
      return jsonResponse({ data: { llm_config: config(), chat_capable_providers: ['ollama'] } })
    }
    if (u.includes('/api/llm/discover')) {
      return jsonResponse({ data: {
        ollama: { running: ollamaRunning, url: ENDPOINT.url, version: '1.2.3', models: ['model-a', 'model-b'] },
        lm_studio: { running: false, url: 'http://localhost:1234', models: [] },
      } })
    }
    if (u.includes('proxy/models')) {
      return jsonResponse({ data: {
        models: ['model-a', 'model-b'],
        model_details: [{ name: 'model-a' }, { name: 'model-b' }],
      } })
    }
    return jsonResponse({ data: {} })
  })
}

beforeEach(() => {
  fetchMock = route()
  vi.stubGlobal('fetch', fetchMock)
})
afterEach(() => vi.unstubAllGlobals())

describe('ChatModelPill', () => {
  it('shows the configured chat model without being asked', async () => {
    render(<ChatModelPill onSelectionChange={() => {}} />)
    expect(await screen.findByText('model-a')).toBeInTheDocument()
  })

  it('exposes the trigger as a combobox for assistive tech', async () => {
    render(<ChatModelPill onSelectionChange={() => {}} />)
    const trigger = await screen.findByRole('combobox')
    expect(trigger).toHaveAttribute('aria-expanded', 'false')
    expect(trigger).toHaveAttribute('aria-haspopup', 'listbox')
  })

  it('reports a pinned model upward so it can ride on the next send', async () => {
    const onSelectionChange = vi.fn()
    render(<ChatModelPill onSelectionChange={onSelectionChange} />)

    await userEvent.click(await screen.findByRole('combobox'))
    await userEvent.click(await screen.findByRole('option', { name: /model-b/ }))

    await waitFor(() => expect(onSelectionChange).toHaveBeenCalled())
    const calls = onSelectionChange.mock.calls
    expect(calls[calls.length - 1][0]).toMatchObject({ model: 'model-b' })
  })

  it('never writes a pin to the stored configuration', async () => {
    // A pin governs this conversation only. Persisting it would silently
    // change the default for every future session.
    render(<ChatModelPill onSelectionChange={() => {}} />)
    await userEvent.click(await screen.findByRole('combobox'))
    await userEvent.click(await screen.findByRole('option', { name: /model-b/ }))

    const writes = fetchMock.mock.calls.filter(
      ([, init]) => (init as RequestInit | undefined)?.method === 'PUT',
    )
    expect(writes).toEqual([])
  })

  it('marks the pill offline when the local engine is not running', async () => {
    vi.stubGlobal('fetch', route(false))
    render(<ChatModelPill onSelectionChange={() => {}} />)
    const trigger = await screen.findByRole('combobox')
    await waitFor(() =>
      expect(trigger.getAttribute('aria-label')).toMatch(/not running/i),
    )
  })

  it('closes the popover after a selection', async () => {
    render(<ChatModelPill onSelectionChange={() => {}} />)
    const trigger = await screen.findByRole('combobox')
    await userEvent.click(trigger)
    expect(trigger).toHaveAttribute('aria-expanded', 'true')

    await userEvent.click(await screen.findByRole('option', { name: /model-b/ }))
    await waitFor(() => expect(trigger).toHaveAttribute('aria-expanded', 'false'))
  })
})
