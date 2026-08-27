// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type {
  AppRole,
  DiscoveredModel,
  EndpointTestResult,
  LocalDiscovery,
  ModelPickerTransport,
  ModelSelection,
  PickerConfig,
  ProviderId,
  RoleAssignment,
  SavedEndpoint,
  Tier,
} from './types'

const EMPTY_CONFIG: PickerConfig = {
  endpoints: [],
  assignments: {},
  chatCapableProviders: [],
}

export interface UseModelPickerOptions {
  transport: ModelPickerTransport
  /** The host's slots, in display order. */
  roles: AppRole[]
  /**
   * Probe local ports on mount. Off for hosts with no server side; the picker
   * then falls back to manual endpoint entry.
   */
  autoDiscover?: boolean
  /** Surfaced instead of thrown, so a dead endpoint never blanks the UI. */
  onError?: (message: string) => void
}

export interface UseModelPickerResult {
  config: PickerConfig
  roles: AppRole[]
  loading: boolean
  error: string | null

  /** Every model across every endpoint that has been listed so far. */
  models: DiscoveredModel[]
  modelsByEndpoint: Record<string, DiscoveredModel[]>
  /** Endpoint ids currently being listed. */
  listing: string[]

  discovery: LocalDiscovery | null
  discovering: boolean

  /** Endpoints whose provider the host's chat runtime can actually call. */
  chatCapableEndpoints: SavedEndpoint[]
  isChatCapable: (provider: ProviderId) => boolean
  /** Models valid for a role, after its capability filters. */
  modelsForRole: (roleId: string) => DiscoveredModel[]
  assignmentFor: (roleId: string) => RoleAssignment | undefined
  endpointFor: (endpointId: string) => SavedEndpoint | undefined

  /** Per-turn pin. Held in memory only — it must not outlive the session. */
  selection: ModelSelection
  setSelection: (next: ModelSelection) => void
  pinModel: (model: string, endpointId?: string) => void
  pinTier: (tier: Tier) => void
  clearPin: () => void
  /** True while a pin is in force, i.e. the host's router is bypassed. */
  isPinned: boolean

  refresh: () => Promise<void>
  refreshModels: (endpointId: string) => Promise<void>
  discoverLocal: () => Promise<void>
  assignRole: (roleId: string, endpointId: string, model: string) => Promise<void>
  clearRole: (roleId: string) => Promise<void>
  saveEndpoint: (endpoint: SavedEndpoint) => Promise<void>
  deleteEndpoint: (endpointId: string) => Promise<void>
  testEndpoint: (endpointId: string) => Promise<EndpointTestResult>
  testModel: (roleId: string) => Promise<EndpointTestResult>
  testing: string | null
  testResults: Record<string, EndpointTestResult>
}

function message(e: unknown): string {
  return e instanceof Error ? e.message : String(e)
}

/**
 * The picker's entire behaviour, with no markup and no styling.
 *
 * Hosts that want the stock components pass this result to them; hosts with
 * their own design language can ignore the components and render from here.
 */
export function useModelPicker(
  options: UseModelPickerOptions,
): UseModelPickerResult {
  const { transport, roles, autoDiscover = true, onError } = options

  const [config, setConfig] = useState<PickerConfig>(EMPTY_CONFIG)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [modelsByEndpoint, setModelsByEndpoint] = useState<
    Record<string, DiscoveredModel[]>
  >({})
  const [listing, setListing] = useState<string[]>([])
  const [discovery, setDiscovery] = useState<LocalDiscovery | null>(null)
  const [discovering, setDiscovering] = useState(false)
  const [selection, setSelection] = useState<ModelSelection>({ tier: 'auto' })
  const [testing, setTesting] = useState<string | null>(null)
  const [testResults, setTestResults] = useState<
    Record<string, EndpointTestResult>
  >({})

  // Late results from an unmounted picker must not set state.
  const alive = useRef(true)
  useEffect(() => {
    alive.current = true
    return () => {
      alive.current = false
    }
  }, [])

  // `transport` and `onError` are read through refs so that a host writing the
  // ordinary idiom — an object literal or an arrow function in the options —
  // does not produce a new identity every render, re-firing the mount effect
  // and looping loadConfig forever. The refs always hold the latest value, so
  // behaviour is unchanged; only the identity is stabilised.
  const transportRef = useRef(transport)
  const onErrorRef = useRef(onError)
  useEffect(() => {
    transportRef.current = transport
    onErrorRef.current = onError
  })

  // The endpoint list as of *now*, so a callback created in an earlier render
  // does not act on a stale copy after a save.
  const endpointsRef = useRef<SavedEndpoint[]>(config.endpoints)
  useEffect(() => {
    endpointsRef.current = config.endpoints
  }, [config.endpoints])

  const fail = useCallback((e: unknown) => {
    const msg = message(e)
    if (alive.current) setError(msg)
    onErrorRef.current?.(msg)
  }, [])

  // ── Loading ────────────────────────────────────────────────────────────

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const next = await transportRef.current.loadConfig()
      if (!alive.current) return
      setConfig(next)
      setError(null)
    } catch (e) {
      fail(e)
    } finally {
      if (alive.current) setLoading(false)
    }
  }, [fail])

  /** List one endpoint's models. Takes the endpoint itself, never an id. */
  const listEndpoint = useCallback(
    async (endpoint: SavedEndpoint) => {
      const endpointId = endpoint.id
      setListing((ids) => (ids.includes(endpointId) ? ids : [...ids, endpointId]))
      try {
        const found = await transportRef.current.listModels(endpoint)
        if (!alive.current) return
        setModelsByEndpoint((prev) => ({ ...prev, [endpointId]: found }))
      } catch (e) {
        // One unreachable endpoint must not empty the others.
        if (alive.current) {
          setModelsByEndpoint((prev) => ({ ...prev, [endpointId]: [] }))
        }
        fail(e)
      } finally {
        if (alive.current) {
          setListing((ids) => ids.filter((id) => id !== endpointId))
        }
      }
    },
    [fail],
  )

  const refreshModels = useCallback(
    async (endpointId: string) => {
      // Read through the ref rather than the captured array: after a save the
      // render has not necessarily flushed, and listing the pre-edit copy
      // probes the abandoned url with the old key and files the answer under
      // the edited endpoint's id.
      const endpoint = endpointsRef.current.find((e) => e.id === endpointId)
      if (!endpoint) return
      await listEndpoint(endpoint)
    },
    [listEndpoint],
  )

  const discoverLocal = useCallback(async () => {
    const discover = transportRef.current.discoverLocal
    if (!discover) return
    setDiscovering(true)
    try {
      const found = await discover.call(transportRef.current)
      if (alive.current) setDiscovery(found)
    } catch (e) {
      fail(e)
    } finally {
      if (alive.current) setDiscovering(false)
    }
  }, [fail])

  useEffect(() => {
    void refresh()
  }, [refresh])

  useEffect(() => {
    if (autoDiscover) void discoverLocal()
  }, [autoDiscover, discoverLocal])

  // List every configured endpoint once the config arrives.
  useEffect(() => {
    for (const endpoint of config.endpoints) {
      if (!(endpoint.id in modelsByEndpoint)) void refreshModels(endpoint.id)
    }
    // modelsByEndpoint is deliberately absent: including it would re-run this
    // on every listing and loop.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [config.endpoints, refreshModels])

  // ── Derived ────────────────────────────────────────────────────────────

  const models = useMemo(
    () => Object.values(modelsByEndpoint).flat(),
    [modelsByEndpoint],
  )

  const isChatCapable = useCallback(
    (provider: ProviderId) => config.chatCapableProviders.includes(provider),
    [config.chatCapableProviders],
  )

  const chatCapableEndpoints = useMemo(
    () => config.endpoints.filter((e) => isChatCapable(e.provider)),
    [config.endpoints, isChatCapable],
  )

  const modelsForRole = useCallback(
    (roleId: string) => {
      const role = roles.find((r) => r.id === roleId)
      if (!role) return []
      return models.filter((m) => {
        if (!isChatCapable(m.provider)) return false
        // `undefined` means the host could not determine the capability;
        // only an explicit `false` disqualifies a model. Treating unknown as
        // "no" empties the dropdown for every provider that cannot be
        // inspected, which is worse than offering a model that may not fit.
        if (role.requiresVision && m.capabilities.vision === false) return false
        if (role.requiresTools && m.capabilities.tools === false) return false
        return true
      })
    },
    [roles, models, isChatCapable],
  )

  const assignmentFor = useCallback(
    (roleId: string) => config.assignments[roleId],
    [config.assignments],
  )

  const endpointFor = useCallback(
    (endpointId: string) => config.endpoints.find((e) => e.id === endpointId),
    [config.endpoints],
  )

  // ── Writes ─────────────────────────────────────────────────────────────

  const apply = useCallback(
    async (patch: Partial<PickerConfig>) => {
      try {
        const next = await transportRef.current.saveConfig(patch)
        if (alive.current) {
          // Synchronously, not via the effect: callers act on the result in
          // the same tick, before React has flushed anything.
          endpointsRef.current = next.endpoints
          setConfig(next)
          setError(null)
        }
      } catch (e) {
        fail(e)
      }
    },
    [fail],
  )

  const assignRole = useCallback(
    async (roleId: string, endpointId: string, model: string) => {
      await apply({
        assignments: {
          ...config.assignments,
          [roleId]: { endpointId, model, enabled: Boolean(model && endpointId) },
        },
      })
    },
    [apply, config.assignments],
  )

  const clearRole = useCallback(
    async (roleId: string) => {
      await apply({
        assignments: {
          ...config.assignments,
          [roleId]: { endpointId: '', model: '', enabled: false },
        },
      })
    },
    [apply, config.assignments],
  )

  const saveEndpoint = useCallback(
    async (endpoint: SavedEndpoint) => {
      const exists = config.endpoints.some((e) => e.id === endpoint.id)
      const endpoints = exists
        ? config.endpoints.map((e) => (e.id === endpoint.id ? endpoint : e))
        : [...config.endpoints, endpoint]
      await apply({ endpoints })
      // The endpoint we were handed is authoritative; looking it back up would
      // race the render that has not happened yet.
      await listEndpoint(endpoint)
    },
    [apply, config.endpoints, listEndpoint],
  )

  const deleteEndpoint = useCallback(
    async (endpointId: string) => {
      // Roles pointing at a deleted endpoint would otherwise stay "enabled"
      // against an endpoint that no longer exists.
      const assignments = { ...config.assignments }
      for (const [roleId, a] of Object.entries(assignments)) {
        if (a.endpointId === endpointId) {
          assignments[roleId] = { endpointId: '', model: '', enabled: false }
        }
      }
      await apply({
        endpoints: config.endpoints.filter((e) => e.id !== endpointId),
        assignments,
      })
      setModelsByEndpoint((prev) => {
        const next = { ...prev }
        delete next[endpointId]
        return next
      })
    },
    [apply, config.endpoints, config.assignments],
  )

  // ── Tests ──────────────────────────────────────────────────────────────

  const testEndpoint = useCallback(
    async (endpointId: string): Promise<EndpointTestResult> => {
      const endpoint = endpointFor(endpointId)
      if (!endpoint) {
        return { ok: false, message: 'Endpoint not found' }
      }
      setTesting(endpointId)
      try {
        const result = await transportRef.current.testEndpoint(endpoint)
        if (alive.current) {
          setTestResults((prev) => ({ ...prev, [endpointId]: result }))
        }
        return result
      } catch (e) {
        const result = { ok: false, message: message(e) }
        if (alive.current) {
          setTestResults((prev) => ({ ...prev, [endpointId]: result }))
        }
        return result
      } finally {
        if (alive.current) setTesting(null)
      }
    },
    [endpointFor],
  )

  const testModel = useCallback(
    async (roleId: string): Promise<EndpointTestResult> => {
      const assignment = assignmentFor(roleId)
      const endpoint = assignment ? endpointFor(assignment.endpointId) : undefined
      if (!assignment?.model || !endpoint) {
        return { ok: false, message: 'Assign a model first' }
      }
      const probe = transportRef.current.testModel
      if (!probe) {
        return transportRef.current.testEndpoint(endpoint)
      }
      setTesting(roleId)
      try {
        const result = await probe.call(transportRef.current, endpoint, assignment.model)
        if (alive.current) {
          setTestResults((prev) => ({ ...prev, [roleId]: result }))
        }
        return result
      } catch (e) {
        const result = { ok: false, message: message(e) }
        if (alive.current) {
          setTestResults((prev) => ({ ...prev, [roleId]: result }))
        }
        return result
      } finally {
        if (alive.current) setTesting(null)
      }
    },
    [assignmentFor, endpointFor],
  )

  // ── Per-turn pin ───────────────────────────────────────────────────────

  const pinModel = useCallback((model: string, endpointId?: string) => {
    setSelection({ model, endpointId, tier: undefined })
  }, [])

  const pinTier = useCallback((tier: Tier) => {
    setSelection(
      tier === 'auto' ? { tier: 'auto' } : { tier, model: undefined },
    )
  }, [])

  const clearPin = useCallback(() => setSelection({ tier: 'auto' }), [])

  const isPinned = Boolean(
    selection.model || (selection.tier && selection.tier !== 'auto'),
  )

  return {
    config,
    roles,
    loading,
    error,
    models,
    modelsByEndpoint,
    listing,
    discovery,
    discovering,
    chatCapableEndpoints,
    isChatCapable,
    modelsForRole,
    assignmentFor,
    endpointFor,
    selection,
    setSelection,
    pinModel,
    pinTier,
    clearPin,
    isPinned,
    refresh,
    refreshModels,
    discoverLocal,
    assignRole,
    clearRole,
    saveEndpoint,
    deleteEndpoint,
    testEndpoint,
    testModel,
    testing,
    testResults,
  }
}
