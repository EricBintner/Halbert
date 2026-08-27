// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * Implements @halbert/model-picker's ModelPickerTransport against Halbert's
 * own routes. This is the one place that knows both shapes:
 *
 *  - the package's PickerConfig / SavedEndpoint / DiscoveredModel types
 *  - Halbert's llm_config schema and its `{data: ...} | {error: {code,
 *    message}}` response envelope (dashboard/routes/llm.py)
 *
 * Halbert's slot keys (`chat_model` / `specialist_model` / `vision_model`)
 * are used directly as AppRole ids — see the FRONTEND handoff's mapping
 * notes — so no id translation happens here beyond snake_case/camelCase.
 */

import type {
  DiscoveredModel,
  EndpointTestResult,
  LocalDiscovery,
  ModelCapabilities,
  ModelPickerTransport,
  PickerConfig,
  ProviderId,
  RoleAssignment,
  SavedEndpoint,
} from '@halbert/model-picker'
import { providerDescriptor } from '@halbert/model-picker'
import { apiUrl } from './apiBase'

interface RawEndpoint {
  id: string
  name: string
  provider: string
  url: string
  api_key?: string
}

interface RawSlot {
  enabled: boolean
  endpoint_id: string
  model: string
}

interface RawLlmConfig {
  saved_endpoints: RawEndpoint[]
  chat_model: RawSlot
  specialist_model: RawSlot
  vision_model: RawSlot
}

async function unwrap(response: Response): Promise<any> {
  let json: any
  try {
    json = await response.json()
  } catch {
    throw new Error(`Request failed (HTTP ${response.status})`)
  }
  if (json?.error) {
    throw new Error(json.error.message || json.error.code || 'Request failed')
  }
  return json?.data ?? json
}

function postJson(path: string, body: unknown): Promise<Response> {
  return fetch(apiUrl(path), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

function toSavedEndpoint(ep: RawEndpoint): SavedEndpoint {
  return {
    id: ep.id,
    name: ep.name,
    provider: ep.provider as ProviderId,
    url: ep.url,
    ...(ep.api_key ? { apiKey: ep.api_key } : {}),
  }
}

/**
 * An absent `ep.apiKey` means the object never carried the key — a card for a
 * provider with `needsApiKey: false` renders no key field — not "clear it", so
 * only a real string is sent and `storedKey` fills the rest. Emitting
 * `api_key: ''` for the absent case erased the saved key, because
 * `saved_endpoints` is a list and PUT /llm/config replaces it whole.
 */
function fromSavedEndpoint(ep: SavedEndpoint): RawEndpoint {
  return {
    id: ep.id,
    name: ep.name,
    provider: ep.provider,
    url: ep.url,
    // Omitted when the caller does not carry a key — a card for a provider
    // with no key field never sees one, and must not be able to erase it.
    // PUT /llm/config carries the stored key forward for an absent field, and
    // clears it only for an explicit empty string.
    ...(typeof ep.apiKey === 'string' ? { api_key: ep.apiKey } : {}),
  }
}

function toRoleAssignment(slot: RawSlot): RoleAssignment {
  return { endpointId: slot.endpoint_id, model: slot.model, enabled: slot.enabled }
}

function fromRoleAssignment(a: RoleAssignment): RawSlot {
  return { enabled: a.enabled, endpoint_id: a.endpointId, model: a.model }
}

function toPickerConfig(payload: {
  llm_config: RawLlmConfig
  chat_capable_providers: string[]
}): PickerConfig {
  const llm = payload.llm_config
  return {
    endpoints: (llm.saved_endpoints || []).map(toSavedEndpoint),
    assignments: {
      chat_model: toRoleAssignment(llm.chat_model),
      specialist_model: toRoleAssignment(llm.specialist_model),
      vision_model: toRoleAssignment(llm.vision_model),
    },
    chatCapableProviders: (payload.chat_capable_providers || []) as ProviderId[],
  }
}

/**
 * Capability hints from `model_details`. The backend does not yet run every
 * model through `model/capabilities.py` (that is D-4) — for now this maps
 * whatever fields a proxy route already reports, and stays a no-op subset
 * once D-4 adds the rest.
 */
function capabilitiesFromDetail(detail: Record<string, unknown>): ModelCapabilities {
  const caps: ModelCapabilities = {}
  if (typeof detail.vision === 'boolean') caps.vision = detail.vision
  if (typeof detail.tool_use === 'boolean') caps.tools = detail.tool_use
  if (typeof detail.reasoning === 'boolean') caps.reasoning = detail.reasoning
  if (typeof detail.context_tokens === 'number' && detail.context_tokens > 0) {
    caps.contextWindow = detail.context_tokens
  }
  return caps
}

export function createModelPickerTransport(): ModelPickerTransport {
  return {
    async loadConfig(): Promise<PickerConfig> {
      const res = await fetch(apiUrl('/llm/config'))
      return toPickerConfig(await unwrap(res))
    },

    async saveConfig(patch: Partial<PickerConfig>): Promise<PickerConfig> {
      const llm_config: Record<string, unknown> = {}
      if (patch.endpoints) {
        llm_config.saved_endpoints = patch.endpoints.map(fromSavedEndpoint)
      }
      if (patch.assignments) {
        for (const [roleId, assignment] of Object.entries(patch.assignments)) {
          llm_config[roleId] = fromRoleAssignment(assignment)
        }
      }
      const res = await fetch(apiUrl('/llm/config'), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ llm_config }),
      })
      return toPickerConfig(await unwrap(res))
    },

    async listModels(endpoint: SavedEndpoint): Promise<DiscoveredModel[]> {
      const res = await postJson('/api/llm/proxy/models', {
        provider: endpoint.provider,
        url: endpoint.url,
        ...(endpoint.apiKey ? { api_key: endpoint.apiKey } : {}),
      })
      const data = await unwrap(res)
      const details: Record<string, unknown>[] =
        data.model_details && data.model_details.length
          ? data.model_details
          : (data.models || []).map((name: string) => ({ name }))
      const isLocal = providerDescriptor(endpoint.provider).isLocal
      return details.map((d) => ({
        id: d.name as string,
        name: d.name as string,
        endpointId: endpoint.id,
        provider: endpoint.provider,
        isLocal,
        capabilities: capabilitiesFromDetail(d),
      }))
    },

    async testEndpoint(endpoint: SavedEndpoint): Promise<EndpointTestResult> {
      const res = await postJson('/api/llm/proxy/test', {
        provider: endpoint.provider,
        url: endpoint.url,
        ...(endpoint.apiKey ? { api_key: endpoint.apiKey } : {}),
      })
      const data = await unwrap(res)
      return { ok: !!data.success, message: data.message || '', models: data.models }
    },

    async testModel(endpoint: SavedEndpoint, model: string): Promise<EndpointTestResult> {
      const res = await postJson('/api/llm/proxy/test-model', {
        provider: endpoint.provider,
        url: endpoint.url,
        model,
        ...(endpoint.apiKey ? { api_key: endpoint.apiKey } : {}),
      })
      const data = await unwrap(res)
      return { ok: !!data.success, message: data.message || '' }
    },

    async discoverLocal(): Promise<LocalDiscovery> {
      const res = await fetch(apiUrl('/api/llm/discover'))
      const data = await unwrap(res)
      return { ollama: data.ollama, lmStudio: data.lm_studio }
    },
  }
}
