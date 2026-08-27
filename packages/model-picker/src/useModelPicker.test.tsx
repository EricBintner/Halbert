// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { act, renderHook, waitFor } from '@testing-library/react'
import { providerDescriptor } from './types'
import type {
  AppRole,
  DiscoveredModel,
  EndpointTestResult,
  ModelCapabilities,
  ModelPickerTransport,
  PickerConfig,
  SavedEndpoint,
} from './types'
import { useModelPicker } from './useModelPicker'
import type { UseModelPickerOptions } from './useModelPicker'

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

const EXTRA: SavedEndpoint = {
  id: 'ep-extra',
  name: 'Second local runtime',
  provider: 'lm-studio',
  url: 'http://localhost:1234',
}

// Host-supplied slots: the package never knows these names, so the fixtures
// deliberately share no vocabulary with any real host.
const ROLES: AppRole[] = [
  { id: 'primary', label: 'Primary', description: 'Answers ordinary turns.' },
  { id: 'sight', label: 'Sight', description: 'Reads images.', requiresVision: true },
  { id: 'tooling', label: 'Tooling', description: 'Calls tools.', requiresTools: true },
]

const clone = <T,>(value: T): T => JSON.parse(JSON.stringify(value)) as T

function offering(
  id: string,
  endpoint: SavedEndpoint,
  capabilities: ModelCapabilities,
): DiscoveredModel {
  return {
    id,
    name: id,
    endpointId: endpoint.id,
    provider: endpoint.provider,
    isLocal: providerDescriptor(endpoint.provider).isLocal,
    capabilities,
  }
}

function defaultCatalogue(): Record<string, DiscoveredModel[]> {
  return {
    [LOCAL.id]: [
      // {} means "the host could not determine this"; `false` means it did
      // determine it and the answer was no. modelsForRole must treat them
      // differently.
      offering('local-plain', LOCAL, {}),
      offering('local-sight', LOCAL, { vision: true }),
      offering('local-tools', LOCAL, { tools: true }),
      offering('local-known-plain', LOCAL, { vision: false, tools: false }),
    ],
    [HOSTED.id]: [offering('hosted-any', HOSTED, { tools: true, vision: true })],
    [EXTRA.id]: [offering('extra-plain', EXTRA, {})],
  }
}

type TransportMethod =
  | 'loadConfig'
  | 'saveConfig'
  | 'listModels'
  | 'testEndpoint'
  | 'testModel'
  | 'discoverLocal'

interface FakeTransport extends ModelPickerTransport {
  stored: PickerConfig
  catalogue: Record<string, DiscoveredModel[]>
  calls: Record<TransportMethod, number>
  /** Every patch handed to `saveConfig`, in order, captured before merging. */
  patches: Partial<PickerConfig>[]
  /** Every endpoint handed to `listModels`, in order, as it was at the call. */
  listed: SavedEndpoint[]
  /** Set a method to a message to make it reject with that message. */
  reject: Partial<Record<TransportMethod, string>>
  /** Endpoint ids whose listing rejects while the rest stay reachable. */
  rejectListFor: Set<string>
  /** Opens the gate held shut by `deferLoad`. */
  releaseLoad: () => void
}

interface FakeOptions {
  config?: Partial<PickerConfig>
  catalogue?: Record<string, DiscoveredModel[]>
  /** Hold `loadConfig` open so the pending state can be observed. */
  deferLoad?: boolean
  withTestModel?: boolean
  withDiscoverLocal?: boolean
}

function fakeTransport(options: FakeOptions = {}): FakeTransport {
  let openGate = () => {}
  const gate: Promise<void> = options.deferLoad
    ? new Promise<void>((resolve) => {
        openGate = resolve
      })
    : Promise.resolve()

  const guard = async (method: TransportMethod) => {
    fake.calls[method] += 1
    const failure = fake.reject[method]
    if (failure) throw new Error(failure)
  }

  const fake: FakeTransport = {
    stored: {
      endpoints: [LOCAL, HOSTED],
      assignments: {},
      chatCapableProviders: ['ollama'],
      ...options.config,
    },
    catalogue: options.catalogue ?? defaultCatalogue(),
    calls: {
      loadConfig: 0,
      saveConfig: 0,
      listModels: 0,
      testEndpoint: 0,
      testModel: 0,
      discoverLocal: 0,
    },
    patches: [],
    listed: [],
    reject: {},
    rejectListFor: new Set<string>(),
    releaseLoad: () => openGate(),

    async loadConfig() {
      await gate
      await guard('loadConfig')
      return clone(fake.stored)
    },

    async saveConfig(patch) {
      await guard('saveConfig')
      fake.patches.push(clone(patch))
      fake.stored = { ...fake.stored, ...clone(patch) }
      return clone(fake.stored)
    },

    async listModels(endpoint) {
      fake.calls.listModels += 1
      fake.listed.push(clone(endpoint))
      const failure = fake.reject.listModels
      if (failure || fake.rejectListFor.has(endpoint.id)) {
        throw new Error(failure ?? `cannot reach ${endpoint.name}`)
      }
      return clone(fake.catalogue[endpoint.id] ?? [])
    },

    async testEndpoint(endpoint) {
      await guard('testEndpoint')
      return { ok: true, message: `reached ${endpoint.name}` }
    },
  }

  if (options.withTestModel !== false) {
    fake.testModel = async (endpoint, model) => {
      await guard('testModel')
      return { ok: true, message: `${endpoint.name} answered as ${model}` }
    }
  }

  if (options.withDiscoverLocal !== false) {
    fake.discoverLocal = async () => {
      await guard('discoverLocal')
      return {
        ollama: { running: true, url: LOCAL.url, models: ['local-plain'] },
        lmStudio: { running: false, url: EXTRA.url, models: [] },
      }
    }
  }

  return fake
}

async function mount(
  transport: FakeTransport,
  overrides: Partial<UseModelPickerOptions> = {},
) {
  const onError = vi.fn()
  const view = renderHook(() =>
    useModelPicker({
      transport,
      roles: ROLES,
      autoDiscover: false,
      onError,
      ...overrides,
    }),
  )
  await waitFor(() => expect(view.result.current.loading).toBe(false))
  return { result: view.result, onError }
}

const assigned = (endpointId: string, model: string) => ({
  endpointId,
  model,
  enabled: true,
})

describe('useModelPicker', () => {
  it('loads the configuration on mount and stays loading until it resolves', async () => {
    const transport = fakeTransport({ deferLoad: true })
    const { result } = renderHook(() =>
      useModelPicker({ transport, roles: ROLES, autoDiscover: false }),
    )

    expect(result.current.loading).toBe(true)
    expect(result.current.config.endpoints).toEqual([])

    transport.releaseLoad()

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(transport.calls.loadConfig).toBe(1)
    expect(result.current.config.endpoints).toHaveLength(2)
    expect(result.current.error).toBeNull()
  })

  it('reports a failing configuration load instead of throwing', async () => {
    const transport = fakeTransport()
    transport.reject.loadConfig = 'the settings store is unavailable'
    const { result, onError } = await mount(transport)

    expect(result.current.error).toBe('the settings store is unavailable')
    expect(onError).toHaveBeenCalledWith('the settings store is unavailable')
    expect(result.current.config).toEqual({
      endpoints: [],
      assignments: {},
      chatCapableProviders: [],
    })
  })

  it('loads the configuration once however often a fresh inline onError arrives', async () => {
    // Writing the handler inline in the options object is the ordinary host
    // idiom, and it hands the hook a new function identity on every render.
    const transport = fakeTransport()
    const handlers: ReturnType<typeof vi.fn>[] = []
    const view = renderHook(() => {
      const onError = vi.fn()
      handlers.push(onError)
      return useModelPicker({ transport, roles: ROLES, autoDiscover: false, onError })
    })
    await waitFor(() => expect(view.result.current.models).toHaveLength(5))

    for (let i = 0; i < 4; i += 1) view.rerender()

    expect(handlers.length).toBeGreaterThan(4)
    expect(transport.calls.loadConfig).toBe(1)
    expect(transport.calls.listModels).toBe(2)
  })

  it('loads the configuration once however often a fresh transport object arrives', async () => {
    const transport = fakeTransport()
    const listedBy: string[] = []
    let nextTag = 'first'
    const view = renderHook(() => {
      const tag = nextTag
      return useModelPicker({
        // A wrapper literal around a stable client: identical behaviour, new
        // identity every render.
        transport: {
          ...transport,
          listModels: (endpoint: SavedEndpoint) => {
            listedBy.push(tag)
            return transport.listModels(endpoint)
          },
        },
        roles: ROLES,
        autoDiscover: false,
      })
    })
    await waitFor(() => expect(view.result.current.models).toHaveLength(5))

    nextTag = 'latest'
    for (let i = 0; i < 4; i += 1) view.rerender()

    expect(transport.calls.loadConfig).toBe(1)

    // Stabilising the identity must not pin the first transport in place.
    await act(async () => {
      await view.result.current.refreshModels(LOCAL.id)
    })
    expect(listedBy[listedBy.length - 1]).toBe('latest')
  })

  it('reports an error to the onError the host passed most recently', async () => {
    const transport = fakeTransport()
    const handlers: ReturnType<typeof vi.fn>[] = []
    const view = renderHook(() => {
      const onError = vi.fn()
      handlers.push(onError)
      return useModelPicker({ transport, roles: ROLES, autoDiscover: false, onError })
    })
    await waitFor(() => expect(view.result.current.models).toHaveLength(5))
    view.rerender()

    const first = handlers[0]
    const latest = handlers[handlers.length - 1]
    expect(latest).not.toBe(first)

    transport.reject.saveConfig = 'the settings store rejected the write'
    await act(async () => {
      await view.result.current.assignRole('primary', LOCAL.id, 'local-plain')
    })

    expect(latest).toHaveBeenCalledWith('the settings store rejected the write')
    expect(first).not.toHaveBeenCalled()
  })

  it('lists models for every configured endpoint once the configuration arrives', async () => {
    const transport = fakeTransport()
    const { result } = await mount(transport)

    await waitFor(() => expect(result.current.models).toHaveLength(5))
    expect(result.current.modelsByEndpoint[LOCAL.id]).toHaveLength(4)
    expect(result.current.modelsByEndpoint[HOSTED.id]).toHaveLength(1)
    expect(result.current.listing).toEqual([])
  })

  it('keeps the other endpoints listed when one endpoint fails to list', async () => {
    const transport = fakeTransport()
    transport.rejectListFor.add(HOSTED.id)
    const { result, onError } = await mount(transport)

    await waitFor(() => {
      expect(result.current.modelsByEndpoint[LOCAL.id]).toHaveLength(4)
      expect(result.current.modelsByEndpoint[HOSTED.id]).toEqual([])
    })
    expect(onError).toHaveBeenCalled()
  })

  it('omits models from providers the host cannot chat with', async () => {
    const transport = fakeTransport()
    const { result } = await mount(transport)
    await waitFor(() => expect(result.current.models).toHaveLength(5))

    const offered = result.current.modelsForRole('primary')
    expect(offered.map((m) => m.id).sort()).toEqual([
      'local-known-plain',
      'local-plain',
      'local-sight',
      'local-tools',
    ])
    expect(offered.every((m) => m.provider === 'ollama')).toBe(true)
  })

  it('hides a model known to lack vision from a role that requires it', async () => {
    const transport = fakeTransport()
    const { result } = await mount(transport)
    await waitFor(() => expect(result.current.models).toHaveLength(5))

    expect(result.current.modelsForRole('sight').map((m) => m.id)).not.toContain(
      'local-known-plain',
    )
    expect(result.current.modelsForRole('sight').map((m) => m.id)).toContain(
      'local-sight',
    )
  })

  it('still offers a model whose vision support is unknown', async () => {
    // A provider the host cannot inspect — lm-studio, openai-compatible, or an
    // Ollama too old to report capabilities — reports nothing. Excluding those
    // empties the dropdown entirely, which is the worse failure.
    const transport = fakeTransport()
    const { result } = await mount(transport)
    await waitFor(() => expect(result.current.models).toHaveLength(5))

    expect(result.current.modelsForRole('sight').map((m) => m.id)).toContain(
      'local-plain',
    )
  })

  it('hides a model known to lack tools from a role that requires them', async () => {
    const transport = fakeTransport()
    const { result } = await mount(transport)
    await waitFor(() => expect(result.current.models).toHaveLength(5))

    expect(result.current.modelsForRole('tooling').map((m) => m.id)).not.toContain(
      'local-known-plain',
    )
    expect(result.current.modelsForRole('tooling').map((m) => m.id)).toContain(
      'local-tools',
    )
  })

  it('still offers a model whose tool support is unknown', async () => {
    const transport = fakeTransport()
    const { result } = await mount(transport)
    await waitFor(() => expect(result.current.models).toHaveLength(5))

    expect(result.current.modelsForRole('tooling').map((m) => m.id)).toContain(
      'local-plain',
    )
  })

  it('drops an unusable provider from a role even when its capabilities are unknown', async () => {
    // Unknown capabilities pass the capability filter, so the provider gate is
    // the only thing keeping a model the chat runtime cannot call out of a slot.
    const transport = fakeTransport({ config: { endpoints: [LOCAL, HOSTED, EXTRA] } })
    const { result } = await mount(transport)
    await waitFor(() => expect(result.current.models).toHaveLength(6))

    expect(result.current.chatCapableEndpoints.map((e) => e.id)).toEqual([LOCAL.id])
    const offered = result.current.modelsForRole('sight').map((m) => m.id)
    expect(offered).not.toContain('extra-plain')
    expect(offered).toContain('local-plain')
  })

  it('saves the merged assignments and adopts the configuration the host returns', async () => {
    const transport = fakeTransport({
      config: { assignments: { tooling: assigned(LOCAL.id, 'local-tools') } },
    })
    const { result } = await mount(transport)

    await act(async () => {
      await result.current.assignRole('primary', LOCAL.id, 'local-plain')
    })

    expect(transport.patches[transport.patches.length - 1]?.assignments).toEqual({
      tooling: assigned(LOCAL.id, 'local-tools'),
      primary: assigned(LOCAL.id, 'local-plain'),
    })
    expect(result.current.assignmentFor('primary')).toEqual(
      assigned(LOCAL.id, 'local-plain'),
    )
    expect(result.current.assignmentFor('tooling')).toEqual(
      assigned(LOCAL.id, 'local-tools'),
    )
  })

  it('disables the slot when a role is cleared', async () => {
    const transport = fakeTransport({
      config: { assignments: { primary: assigned(LOCAL.id, 'local-plain') } },
    })
    const { result } = await mount(transport)

    await act(async () => {
      await result.current.clearRole('primary')
    })

    expect(result.current.assignmentFor('primary')).toEqual({
      endpointId: '',
      model: '',
      enabled: false,
    })
  })

  it('clears any role that pointed at a deleted endpoint', async () => {
    const transport = fakeTransport({
      config: {
        assignments: {
          primary: assigned(LOCAL.id, 'local-plain'),
          tooling: assigned(HOSTED.id, 'hosted-any'),
        },
      },
    })
    const { result } = await mount(transport)

    await act(async () => {
      await result.current.deleteEndpoint(LOCAL.id)
    })

    expect(result.current.config.endpoints.map((e) => e.id)).toEqual([HOSTED.id])
    expect(result.current.assignmentFor('primary')).toEqual({
      endpointId: '',
      model: '',
      enabled: false,
    })
    expect(result.current.assignmentFor('tooling')).toEqual(
      assigned(HOSTED.id, 'hosted-any'),
    )
    expect(result.current.modelsByEndpoint[LOCAL.id]).toBeUndefined()
  })

  it('appends an endpoint that has not been saved before', async () => {
    const transport = fakeTransport()
    const { result } = await mount(transport)

    await act(async () => {
      await result.current.saveEndpoint(EXTRA)
    })

    expect(result.current.config.endpoints.map((e) => e.id)).toEqual([
      LOCAL.id,
      HOSTED.id,
      EXTRA.id,
    ])
    await waitFor(() =>
      expect(result.current.modelsByEndpoint[EXTRA.id]).toHaveLength(1),
    )
  })

  it('replaces an endpoint that shares an id with a saved one', async () => {
    const transport = fakeTransport()
    const { result } = await mount(transport)

    await act(async () => {
      await result.current.saveEndpoint({ ...LOCAL, name: 'Renamed runtime' })
    })

    expect(result.current.config.endpoints).toHaveLength(2)
    expect(result.current.endpointFor(LOCAL.id)?.name).toBe('Renamed runtime')
  })

  it('re-lists the endpoint as edited rather than the copy it replaced', async () => {
    const transport = fakeTransport()
    const { result } = await mount(transport)
    await waitFor(() => expect(result.current.models).toHaveLength(5))

    const moved: SavedEndpoint = {
      ...LOCAL,
      url: 'http://localhost:23456',
      apiKey: 'rotated',
    }
    transport.catalogue[LOCAL.id] = [offering('relocated-offering', moved, {})]

    await act(async () => {
      await result.current.saveEndpoint(moved)
    })

    // Listing the pre-edit copy would probe the abandoned url with the old key
    // and file the answer under the edited endpoint's id.
    const last = transport.listed[transport.listed.length - 1]
    expect(last?.url).toBe(moved.url)
    expect(last?.apiKey).toBe('rotated')
    expect(result.current.modelsByEndpoint[LOCAL.id]?.map((m) => m.id)).toEqual([
      'relocated-offering',
    ])
  })

  it('records the result of an endpoint test', async () => {
    const transport = fakeTransport()
    const { result } = await mount(transport)

    let outcome: EndpointTestResult | undefined
    await act(async () => {
      outcome = await result.current.testEndpoint(LOCAL.id)
    })

    expect(outcome?.ok).toBe(true)
    expect(result.current.testResults[LOCAL.id]?.ok).toBe(true)
    expect(result.current.testing).toBeNull()
  })

  it('turns a thrown endpoint test into a failed result', async () => {
    const transport = fakeTransport()
    transport.reject.testEndpoint = 'connection refused'
    const { result } = await mount(transport)

    let outcome: EndpointTestResult | undefined
    await act(async () => {
      outcome = await result.current.testEndpoint(LOCAL.id)
    })

    expect(outcome).toEqual({ ok: false, message: 'connection refused' })
    expect(result.current.testResults[LOCAL.id]).toEqual({
      ok: false,
      message: 'connection refused',
    })
  })

  it('falls back to the endpoint test when the transport has no model test', async () => {
    const transport = fakeTransport({
      withTestModel: false,
      config: { assignments: { primary: assigned(LOCAL.id, 'local-plain') } },
    })
    const { result } = await mount(transport)

    let outcome: EndpointTestResult | undefined
    await act(async () => {
      outcome = await result.current.testModel('primary')
    })

    expect(transport.calls.testEndpoint).toBe(1)
    expect(outcome?.ok).toBe(true)
  })

  it('pins a model and drops any tier that was in force', async () => {
    const transport = fakeTransport()
    const { result } = await mount(transport)

    act(() => result.current.pinTier('specialist'))
    act(() => result.current.pinModel('local-plain', LOCAL.id))

    expect(result.current.isPinned).toBe(true)
    expect(result.current.selection).toEqual({
      model: 'local-plain',
      endpointId: LOCAL.id,
      tier: undefined,
    })
  })

  it('releases the pin when the tier goes back to automatic', async () => {
    const transport = fakeTransport()
    const { result } = await mount(transport)

    act(() => result.current.pinModel('local-plain', LOCAL.id))
    act(() => result.current.pinTier('auto'))

    expect(result.current.isPinned).toBe(false)
    expect(result.current.selection).toEqual({ tier: 'auto' })
  })

  it('returns to automatic routing when the pin is cleared', async () => {
    const transport = fakeTransport()
    const { result } = await mount(transport)

    act(() => result.current.pinTier('vision'))
    act(() => result.current.clearPin())

    expect(result.current.isPinned).toBe(false)
    expect(result.current.selection).toEqual({ tier: 'auto' })
  })

  it('never probes for local engines when discovery is switched off', async () => {
    const transport = fakeTransport()
    const { result } = await mount(transport, { autoDiscover: false })

    expect(transport.calls.discoverLocal).toBe(0)
    expect(result.current.discovery).toBeNull()
  })

  it('probes for local engines when discovery is switched on', async () => {
    const transport = fakeTransport()
    const { result } = await mount(transport, { autoDiscover: true })

    await waitFor(() => expect(result.current.discovery).not.toBeNull())
    expect(transport.calls.discoverLocal).toBe(1)
    expect(result.current.discovering).toBe(false)
  })

  it('tolerates a transport that cannot discover local engines', async () => {
    const transport = fakeTransport({ withDiscoverLocal: false })
    const { result, onError } = await mount(transport, { autoDiscover: true })

    await act(async () => {
      await result.current.discoverLocal()
    })

    expect(result.current.discovery).toBeNull()
    expect(result.current.discovering).toBe(false)
    expect(result.current.error).toBeNull()
    expect(onError).not.toHaveBeenCalled()
  })

  it('keeps the per-turn pin out of every saved configuration', async () => {
    const transport = fakeTransport()
    const { result } = await mount(transport)

    act(() => result.current.pinModel('pin-only-choice', LOCAL.id))
    await act(async () => {
      await result.current.assignRole('primary', LOCAL.id, 'local-plain')
    })
    await act(async () => {
      await result.current.clearRole('primary')
    })
    await act(async () => {
      await result.current.saveEndpoint({ ...LOCAL, name: 'Renamed runtime' })
    })
    await act(async () => {
      await result.current.deleteEndpoint(HOSTED.id)
    })

    expect(transport.patches.length).toBeGreaterThan(0)
    for (const patch of transport.patches) {
      expect(Object.keys(patch).sort()).not.toContain('selection')
      expect(JSON.stringify(patch)).not.toContain('pin-only-choice')
    }
    expect(result.current.isPinned).toBe(true)
    expect(JSON.stringify(transport.stored)).not.toContain('pin-only-choice')
  })
})
