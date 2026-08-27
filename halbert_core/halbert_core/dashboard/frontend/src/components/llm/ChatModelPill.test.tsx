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
import { useState } from 'react'
import { useModelPicker } from '@halbert/model-picker'
import type { ModelSelection } from '@halbert/model-picker'
import { HALBERT_MODEL_ROLES, modelPickerTransport } from '@/lib/halbertModelRoles'
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


/** Mirrors how AgentChat owns the picker and hands it to the pill. */
function Harness({ onSelected }: { onSelected?: (s: ModelSelection) => void }) {
  const picker = useModelPicker({
    transport: modelPickerTransport,
    roles: HALBERT_MODEL_ROLES,
  })
  const [open, setOpen] = useState(false)
  return (
    <>
      {/* AgentChat's `/model specialist` handler: it pins through this same
          picker without the popover ever opening. */}
      <button type="button" onClick={() => picker.pinTier('specialist')}>
        pin by command
      </button>
      <ChatModelPill
        picker={picker}
        open={open}
        onOpenChange={setOpen}
        onSelected={onSelected}
      />
    </>
  )
}

beforeEach(() => {
  fetchMock = route()
  vi.stubGlobal('fetch', fetchMock)
})
afterEach(() => vi.unstubAllGlobals())

describe('ChatModelPill', () => {
  it('shows the configured chat model without being asked', async () => {
    render(<Harness />)
    expect(await screen.findByText('model-a')).toBeInTheDocument()
  })

  it('exposes the trigger as a combobox for assistive tech', async () => {
    render(<Harness />)
    const trigger = await screen.findByRole('combobox')
    expect(trigger).toHaveAttribute('aria-expanded', 'false')
    expect(trigger).toHaveAttribute('aria-haspopup', 'listbox')
  })

  it('reports a pinned model upward so it can ride on the next send', async () => {
    const onSelectionChange = vi.fn()
    render(<Harness onSelected={onSelectionChange} />)

    await userEvent.click(await screen.findByRole('combobox'))
    await userEvent.click(await screen.findByRole('option', { name: /model-b/ }))

    await waitFor(() => expect(onSelectionChange).toHaveBeenCalled())
    const calls = onSelectionChange.mock.calls
    expect(calls[calls.length - 1][0]).toMatchObject({ model: 'model-b' })
  })

  it('never writes a pin to the stored configuration', async () => {
    // A pin governs this conversation only. Persisting it would silently
    // change the default for every future session.
    render(<Harness />)
    await userEvent.click(await screen.findByRole('combobox'))
    await userEvent.click(await screen.findByRole('option', { name: /model-b/ }))

    const writes = fetchMock.mock.calls.filter(
      ([, init]) => (init as RequestInit | undefined)?.method === 'PUT',
    )
    expect(writes).toEqual([])
  })

  it('marks the pill offline when the local engine is not running', async () => {
    vi.stubGlobal('fetch', route(false))
    render(<Harness />)
    const trigger = await screen.findByRole('combobox')
    await waitFor(() =>
      expect(trigger.getAttribute('aria-label')).toMatch(/not running/i),
    )
  })

  it('closes the popover after a selection', async () => {
    render(<Harness />)
    const trigger = await screen.findByRole('combobox')
    await userEvent.click(trigger)
    expect(trigger).toHaveAttribute('aria-expanded', 'true')

    await userEvent.click(await screen.findByRole('option', { name: /model-b/ }))
    await waitFor(() => expect(trigger).toHaveAttribute('aria-expanded', 'false'))
  })
})


/**
 * A guide on the local runtime and a specialist at a paid cloud vendor — the
 * arrangement where naming the wrong slot costs the user money.
 */
const CLOUD_ENDPOINT = {
  id: 'ep2', name: 'Hosted', provider: 'anthropic',
  url: 'https://api.example.invalid', api_key: 'opaque',
}

function routeWithSpecialist() {
  return vi.fn(async (url: string, init?: RequestInit) => {
    const u = String(url)
    if (u.includes('/llm/config')) {
      return jsonResponse({ data: {
        llm_config: {
          ...config(),
          saved_endpoints: [ENDPOINT, CLOUD_ENDPOINT],
          specialist_model: { enabled: true, endpoint_id: 'ep2', model: 'model-cloud' },
        },
        chat_capable_providers: ['ollama', 'anthropic'],
      } })
    }
    if (u.includes('/api/llm/discover')) {
      return jsonResponse({ data: {
        ollama: { running: true, url: ENDPOINT.url, version: '1.2.3', models: ['model-a'] },
        lm_studio: { running: false, url: 'http://localhost:1234', models: [] },
      } })
    }
    if (u.includes('proxy/models')) {
      const body = JSON.parse(String(init?.body ?? '{}'))
      const models = body.provider === 'anthropic' ? ['model-cloud'] : ['model-a', 'model-b']
      return jsonResponse({ data: {
        models, model_details: models.map((name) => ({ name })),
      } })
    }
    return jsonResponse({ data: {} })
  })
}

const liveRegion = (container: HTMLElement) =>
  container.querySelector('[data-model-picker-live]')

const tierBadge = (container: HTMLElement) =>
  container.querySelector('[data-model-picker-trigger] [data-part="tier"]')

async function pinTier(name: RegExp) {
  await userEvent.click(await screen.findByRole('combobox'))
  await userEvent.click(await screen.findByRole('button', { name }))
}

describe('ChatModelPill on a tier pin', () => {
  beforeEach(() => vi.stubGlobal('fetch', routeWithSpecialist()))

  it('names the tier’s own model, not the chat model', async () => {
    // The pin routes the turn to the specialist slot. Reading the chat slot
    // instead has the pill promise a local model while a cloud one bills.
    render(<Harness />)
    expect(await screen.findByText('model-a')).toBeInTheDocument()

    await pinTier(/^Specialist$/)

    expect(await screen.findByText('model-cloud')).toBeInTheDocument()
    expect(screen.queryByText('model-a')).not.toBeInTheDocument()
  })

  it('drops the local badge when the pinned tier is a cloud model', async () => {
    const { container } = render(<Harness />)
    await waitFor(() =>
      expect(container.querySelector('[data-model-picker-trigger]'))
        .toHaveAttribute('data-local', 'true'),
    )

    await pinTier(/^Specialist$/)

    await waitFor(() =>
      expect(container.querySelector('[data-model-picker-trigger]'))
        .not.toHaveAttribute('data-local'),
    )
    expect(await screen.findByText('Anthropic')).toBeInTheDocument()
  })

  it('falls back to the chat model when the pinned tier has none', async () => {
    // Matches resolve_turn_model: an unconfigured tier uses the guide rather
    // than refusing the turn, so the pill must not claim nothing will answer.
    render(<Harness />)
    await pinTier(/^Vision$/)

    expect(await screen.findByText('model-a')).toBeInTheDocument()
  })
})

describe('ChatModelPill tier badge', () => {
  beforeEach(() => vi.stubGlobal('fetch', routeWithSpecialist()))

  it('shows automatic routing while nothing is pinned', async () => {
    const { container } = render(<Harness />)
    await screen.findByText('model-a')
    expect(tierBadge(container)).toHaveTextContent('⚡ Auto: Guide')
  })

  it('shows a pinned tier as locked to it', async () => {
    const { container } = render(<Harness />)
    await pinTier(/^Specialist$/)
    await waitFor(() =>
      expect(tierBadge(container)).toHaveTextContent('🔒 Pin: Specialist'),
    )
  })

  it('shows the vision tier in its own form', async () => {
    const { container } = render(<Harness />)
    await pinTier(/^Vision$/)
    await waitFor(() => expect(tierBadge(container)).toHaveTextContent('👁️ Vision'))
  })
})

describe('ChatModelPill switch announcement', () => {
  beforeEach(() => vi.stubGlobal('fetch', routeWithSpecialist()))

  it('announces a switch made without the popover', async () => {
    // The popover is torn down the moment a selection commits, so an
    // announcement living inside it is never read. This one follows the
    // selection, whether a click, a slash command or a tier button set it.
    const { container } = render(<Harness />)
    await screen.findByText('model-a')
    expect(liveRegion(container)?.textContent).toBe('')

    await userEvent.click(screen.getByRole('button', { name: /pin by command/ }))

    await waitFor(() =>
      expect(liveRegion(container)).toHaveTextContent(
        'Switched to the Specialist tier: model-cloud on Anthropic will answer the next turn.',
      ),
    )
  })

  it('keeps the announcement out of sight but not out of earshot', async () => {
    const { container } = render(<Harness />)
    await screen.findByText('model-a')

    expect(liveRegion(container)).toHaveAttribute('aria-live', 'polite')
    expect(liveRegion(container)).toHaveClass('sr-only')
  })

  it('survives the popover closing on commit', async () => {
    const { container } = render(<Harness />)
    await pinTier(/^Specialist$/)

    expect(await screen.findByRole('combobox')).toHaveAttribute('aria-expanded', 'false')
    await waitFor(() =>
      expect(liveRegion(container)).toHaveTextContent(/Specialist tier/),
    )
  })
})


describe('ChatModelPill on a layered host', () => {
  it('names the model in force, not the one being edited', async () => {
    // The drawer edits the global layer; a workspace file or a session pin can
    // override it. Showing the editable value would have the pill name a model
    // that is not answering — the one question the pill exists to answer.
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      const u = String(url)
      if (u.includes('/llm/config')) {
        return jsonResponse({ data: {
          llm_config: { ...config(), chat_model: { enabled: true, endpoint_id: 'ep1', model: 'model-global' } },
          chat_capable_providers: ['ollama'],
          effective: {
            llm_config: { ...config(), chat_model: { enabled: true, endpoint_id: 'ep1', model: 'model-inforce' } },
            overridden_slots: { chat_model: 'workspace' },
          },
        } })
      }
      if (u.includes('/api/llm/discover')) {
        return jsonResponse({ data: {
          ollama: { running: true, url: ENDPOINT.url, version: '1.2.3', models: ['model-global', 'model-inforce'] },
          lm_studio: { running: false, url: 'http://localhost:1234', models: [] },
        } })
      }
      if (u.includes('proxy/models')) {
        return jsonResponse({ data: {
          models: ['model-global', 'model-inforce'],
          model_details: [{ name: 'model-global' }, { name: 'model-inforce' }],
        } })
      }
      return jsonResponse({ data: {} })
    }))

    render(<Harness />)
    expect(await screen.findByText('model-inforce')).toBeInTheDocument()
    expect(screen.queryByText('model-global')).not.toBeInTheDocument()
  })
})
