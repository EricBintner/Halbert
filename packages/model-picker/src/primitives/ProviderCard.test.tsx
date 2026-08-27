// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import type { ReactElement } from 'react'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import type {
  ModelPickerTransport,
  PickerConfig,
  SavedEndpoint,
} from '../types'
import { useModelPicker } from '../useModelPicker'
import { ProviderCard } from './ProviderCard'
import type { ProviderCardProps } from './ProviderCard'

const LOCAL: SavedEndpoint = {
  id: 'ep-local',
  name: 'Local runtime',
  provider: 'ollama',
  url: 'http://localhost:11434',
}

const HOSTED: SavedEndpoint = {
  id: 'ep-hosted',
  name: 'Hosted vendor',
  provider: 'openai',
  url: 'https://api.example.invalid/v1',
  apiKey: 'opaque',
}

const clone = <T,>(value: T): T => JSON.parse(JSON.stringify(value)) as T

interface FakeTransport extends ModelPickerTransport {
  stored: PickerConfig
  /** Set to a message to make every config write reject with it. */
  rejectSave: string | null
}

function fakeTransport(endpoints: SavedEndpoint[] = []): FakeTransport {
  const fake: FakeTransport = {
    stored: {
      endpoints,
      assignments: {},
      chatCapableProviders: ['ollama', 'openai'],
    },
    rejectSave: null,

    async loadConfig() {
      return clone(fake.stored)
    },

    async saveConfig(patch) {
      if (fake.rejectSave) throw new Error(fake.rejectSave)
      fake.stored = { ...fake.stored, ...clone(patch) }
      return clone(fake.stored)
    },

    async listModels() {
      return []
    },

    async testEndpoint(endpoint) {
      return { ok: true, message: `reached ${endpoint.name}` }
    },
  }
  return fake
}

/**
 * The card against the real hook, because the defect under test is entirely a
 * matter of when the hook publishes a failure. `picker-error` is the test's
 * only reliable "the write has settled" signal — the card itself renders none.
 */
function Host({
  transport,
  ...rest
}: Omit<ProviderCardProps, 'picker'> & { transport: ModelPickerTransport }) {
  const picker = useModelPicker({ transport, roles: [], autoDiscover: false })
  if (picker.loading) return <p>Loading</p>
  return (
    <>
      <ProviderCard picker={picker} {...rest} />
      <p data-testid="picker-error">{picker.error ?? ''}</p>
    </>
  )
}

async function mount(ui: ReactElement) {
  render(ui)
  await waitFor(() => expect(screen.queryByText('Loading')).toBeNull())
  // The hook lists every configured endpoint once the config lands; settling
  // that here keeps its state updates inside act.
  await act(async () => {})
}

const button = (name: string) => screen.getByRole('button', { name })
const pickerError = () => screen.getByTestId('picker-error').textContent

describe('ProviderCard write callbacks', () => {
  it('reports a save that landed', async () => {
    const transport = fakeTransport()
    const onSaved = vi.fn()
    await mount(
      <Host transport={transport} provider="ollama" onSaved={onSaved} />,
    )

    await act(async () => {
      fireEvent.click(button('Add'))
    })

    await waitFor(() => expect(onSaved).toHaveBeenCalledTimes(1))
    expect(transport.stored.endpoints).toHaveLength(1)
    expect(onSaved.mock.calls[0][0]).toMatchObject({ url: LOCAL.url })
    expect(pickerError()).toBe('')
  })

  it('reports no save when the write failed', async () => {
    const transport = fakeTransport()
    transport.rejectSave = 'storage unavailable'
    const onSaved = vi.fn()
    await mount(
      <Host transport={transport} provider="ollama" onSaved={onSaved} />,
    )

    await act(async () => {
      fireEvent.click(button('Add'))
    })

    await waitFor(() => expect(pickerError()).toBe('storage unavailable'))
    expect(transport.stored.endpoints).toHaveLength(0)
    expect(onSaved).not.toHaveBeenCalled()
  })

  it('reports a removal that landed', async () => {
    const transport = fakeTransport([clone(LOCAL)])
    const onDeleted = vi.fn()
    await mount(
      <Host transport={transport} endpoint={LOCAL} onDeleted={onDeleted} />,
    )

    fireEvent.click(button('Remove'))
    await act(async () => {
      fireEvent.click(button('Confirm remove'))
    })

    await waitFor(() => expect(onDeleted).toHaveBeenCalledWith(LOCAL.id))
    expect(transport.stored.endpoints).toHaveLength(0)
  })

  it('reports no removal when the write failed', async () => {
    const transport = fakeTransport([clone(LOCAL)])
    const onDeleted = vi.fn()
    await mount(
      <Host transport={transport} endpoint={LOCAL} onDeleted={onDeleted} />,
    )
    transport.rejectSave = 'storage unavailable'

    fireEvent.click(button('Remove'))
    await act(async () => {
      fireEvent.click(button('Confirm remove'))
    })

    await waitFor(() => expect(pickerError()).toBe('storage unavailable'))
    expect(transport.stored.endpoints).toHaveLength(1)
    expect(onDeleted).not.toHaveBeenCalled()
  })
})

describe('ProviderCard removal confirm', () => {
  it('warns and waits for a second press before removing anything', async () => {
    const transport = fakeTransport([clone(LOCAL)])
    const onDeleted = vi.fn()
    await mount(
      <Host transport={transport} endpoint={LOCAL} onDeleted={onDeleted} />,
    )

    fireEvent.click(button('Remove'))

    expect(screen.getByRole('status')).toHaveTextContent(
      'Removing this endpoint also clears every role pointing at it.',
    )
    expect(transport.stored.endpoints).toHaveLength(1)
    expect(onDeleted).not.toHaveBeenCalled()

    fireEvent.click(button('Cancel'))

    expect(button('Remove')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Confirm remove' })).toBeNull()
    expect(transport.stored.endpoints).toHaveLength(1)
    expect(onDeleted).not.toHaveBeenCalled()
  })
})

describe('ProviderCard key field', () => {
  it('names the reveal toggle for what pressing it will do', async () => {
    const transport = fakeTransport([clone(HOSTED)])
    await mount(<Host transport={transport} endpoint={HOSTED} />)

    const key = screen.getByLabelText('Key')
    expect(key).toHaveAttribute('type', 'password')
    expect(button('Show the key')).toHaveAttribute('aria-pressed', 'false')

    fireEvent.click(button('Show the key'))

    expect(key).toHaveAttribute('type', 'text')
    const hide = button('Hide the key')
    expect(hide).toHaveAttribute('aria-pressed', 'true')
    expect(hide).toHaveAttribute('aria-controls', key.id)
  })
})
