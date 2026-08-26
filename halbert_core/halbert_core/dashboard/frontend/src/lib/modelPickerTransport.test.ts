// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * The transport is where host-specific shape bugs live: it is the only place
 * that knows Halbert's `{data: ...} | {error: {code, message}}` envelope and
 * the `llm_config` slot schema. Every test here drives it against a mocked
 * `fetch` so the mapping is checked without a running backend.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { createModelPickerTransport } from './modelPickerTransport'

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response
}

describe('modelPickerTransport', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  describe('loadConfig', () => {
    it('maps the llm_config envelope to a PickerConfig', async () => {
      fetchMock.mockResolvedValueOnce(
        jsonResponse({
          data: {
            llm_config: {
              saved_endpoints: [
                { id: 'ep_1', name: 'Local Ollama', provider: 'ollama', url: 'http://localhost:11434', api_key: '' },
              ],
              chat_model: { enabled: true, endpoint_id: 'ep_1', model: 'guide-x' },
              specialist_model: { enabled: false, endpoint_id: '', model: '' },
              vision_model: { enabled: false, endpoint_id: '', model: '' },
            },
            chat_capable_providers: ['ollama', 'anthropic'],
          },
        }),
      )

      const transport = createModelPickerTransport()
      const config = await transport.loadConfig()

      expect(fetchMock).toHaveBeenCalledWith('/llm/config')
      expect(config.endpoints).toEqual([
        { id: 'ep_1', name: 'Local Ollama', provider: 'ollama', url: 'http://localhost:11434' },
      ])
      expect(config.assignments.chat_model).toEqual({ endpointId: 'ep_1', model: 'guide-x', enabled: true })
      expect(config.assignments.specialist_model).toEqual({ endpointId: '', model: '', enabled: false })
      expect(config.chatCapableProviders).toEqual(['ollama', 'anthropic'])
    })

    it('keeps apiKey out of a SavedEndpoint when the backend sent none', async () => {
      fetchMock.mockResolvedValueOnce(
        jsonResponse({
          data: {
            llm_config: {
              saved_endpoints: [{ id: 'ep_1', name: 'x', provider: 'ollama', url: 'http://h', api_key: '' }],
              chat_model: { enabled: false, endpoint_id: '', model: '' },
              specialist_model: { enabled: false, endpoint_id: '', model: '' },
              vision_model: { enabled: false, endpoint_id: '', model: '' },
            },
            chat_capable_providers: [],
          },
        }),
      )

      const config = await createModelPickerTransport().loadConfig()

      expect('apiKey' in config.endpoints[0]).toBe(false)
    })
  })

  describe('saveConfig', () => {
    it('sends the full endpoints array as saved_endpoints on a PUT', async () => {
      fetchMock.mockResolvedValueOnce(
        jsonResponse({
          data: {
            llm_config: {
              saved_endpoints: [{ id: 'ep_1', name: 'x', provider: 'ollama', url: 'http://h', api_key: 'k' }],
              chat_model: { enabled: false, endpoint_id: '', model: '' },
              specialist_model: { enabled: false, endpoint_id: '', model: '' },
              vision_model: { enabled: false, endpoint_id: '', model: '' },
            },
            chat_capable_providers: [],
          },
        }),
      )

      await createModelPickerTransport().saveConfig({
        endpoints: [{ id: 'ep_1', name: 'x', provider: 'ollama', url: 'http://h', apiKey: 'k' }],
      })

      const [url, init] = fetchMock.mock.calls[0]
      expect(url).toBe('/llm/config')
      expect(init.method).toBe('PUT')
      const body = JSON.parse(init.body)
      expect(body).toEqual({
        llm_config: {
          saved_endpoints: [{ id: 'ep_1', name: 'x', provider: 'ollama', url: 'http://h', api_key: 'k' }],
        },
      })
    })

    it('sends every assignment as a whole slot dict, keyed by role id', async () => {
      fetchMock.mockResolvedValueOnce(
        jsonResponse({
          data: {
            llm_config: {
              saved_endpoints: [],
              chat_model: { enabled: true, endpoint_id: 'ep_1', model: 'guide-x' },
              specialist_model: { enabled: false, endpoint_id: '', model: '' },
              vision_model: { enabled: false, endpoint_id: '', model: '' },
            },
            chat_capable_providers: [],
          },
        }),
      )

      await createModelPickerTransport().saveConfig({
        assignments: {
          chat_model: { endpointId: 'ep_1', model: 'guide-x', enabled: true },
        },
      })

      const body = JSON.parse(fetchMock.mock.calls[0][1].body)
      expect(body).toEqual({
        llm_config: {
          chat_model: { enabled: true, endpoint_id: 'ep_1', model: 'guide-x' },
        },
      })
    })

    it('throws with the server message on a PROVIDER_NOT_CHAT_CAPABLE rejection', async () => {
      fetchMock.mockResolvedValueOnce(
        jsonResponse(
          {
            error: {
              code: 'PROVIDER_NOT_CHAT_CAPABLE',
              slot: 'chat_model',
              provider: 'google',
              message: "chat_model uses provider 'google', which is not yet usable for chat",
            },
          },
          422,
        ),
      )

      await expect(
        createModelPickerTransport().saveConfig({
          assignments: { chat_model: { endpointId: 'ep_1', model: 'g', enabled: true } },
        }),
      ).rejects.toThrow(/not yet usable for chat/)
    })
  })

  describe('listModels', () => {
    it('maps model_details to DiscoveredModel[], tagging isLocal from the provider', async () => {
      fetchMock.mockResolvedValueOnce(
        jsonResponse({
          data: {
            models: ['llama3:8b'],
            model_details: [{ name: 'llama3:8b', cost_tier: '8B · Q4 · 4.7GB', context_tokens: 8192 }],
          },
        }),
      )

      const models = await createModelPickerTransport().listModels({
        id: 'ep_1',
        name: 'Local Ollama',
        provider: 'ollama',
        url: 'http://localhost:11434',
      })

      expect(models).toEqual([
        {
          id: 'llama3:8b',
          name: 'llama3:8b',
          endpointId: 'ep_1',
          provider: 'ollama',
          isLocal: true,
          capabilities: { contextWindow: 8192 },
        },
      ])
    })

    it('marks a cloud provider endpoint as not local', async () => {
      fetchMock.mockResolvedValueOnce(
        jsonResponse({ data: { models: ['claude-x'], model_details: [{ name: 'claude-x' }] } }),
      )

      const models = await createModelPickerTransport().listModels({
        id: 'ep_2',
        name: 'Anthropic',
        provider: 'anthropic',
        url: 'https://api.anthropic.com',
        apiKey: 'sk-x',
      })

      expect(models[0].isLocal).toBe(false)
      const [, init] = fetchMock.mock.calls[0]
      expect(JSON.parse(init.body)).toEqual({
        provider: 'anthropic',
        url: 'https://api.anthropic.com',
        api_key: 'sk-x',
      })
    })

    it('throws on a CONNECTION_FAILED error envelope', async () => {
      fetchMock.mockResolvedValueOnce(
        jsonResponse({ error: { code: 'CONNECTION_FAILED', message: 'Connection refused' } }),
      )

      await expect(
        createModelPickerTransport().listModels({ id: 'ep_1', name: 'x', provider: 'ollama', url: 'http://h' }),
      ).rejects.toThrow('Connection refused')
    })
  })

  describe('testEndpoint', () => {
    it('maps success/message to EndpointTestResult', async () => {
      fetchMock.mockResolvedValueOnce(
        jsonResponse({ data: { success: true, message: 'Connected to Ollama v0.5', models: ['llama3:8b'] } }),
      )

      const result = await createModelPickerTransport().testEndpoint({
        id: 'ep_1', name: 'x', provider: 'ollama', url: 'http://localhost:11434',
      })

      expect(result).toEqual({ ok: true, message: 'Connected to Ollama v0.5', models: ['llama3:8b'] })
    })
  })

  describe('testModel', () => {
    it('maps a model-level probe to EndpointTestResult', async () => {
      fetchMock.mockResolvedValueOnce(
        jsonResponse({ data: { success: true, message: 'Model responded successfully', model_status: 'ready' } }),
      )

      const result = await createModelPickerTransport().testModel!(
        { id: 'ep_1', name: 'x', provider: 'ollama', url: 'http://h' },
        'llama3:8b',
      )

      expect(result).toEqual({ ok: true, message: 'Model responded successfully' })
      const body = JSON.parse(fetchMock.mock.calls[0][1].body)
      expect(body.model).toBe('llama3:8b')
    })
  })

  describe('discoverLocal', () => {
    it('maps ollama/lm_studio to camelCase LocalDiscovery', async () => {
      fetchMock.mockResolvedValueOnce(
        jsonResponse({
          data: {
            ollama: { running: true, url: 'http://localhost:11434', version: '0.5.1', models: ['llama3:8b'] },
            lm_studio: { running: false, url: 'http://localhost:1234', models: [] },
          },
        }),
      )

      const discovery = await createModelPickerTransport().discoverLocal!()

      expect(discovery).toEqual({
        ollama: { running: true, url: 'http://localhost:11434', version: '0.5.1', models: ['llama3:8b'] },
        lmStudio: { running: false, url: 'http://localhost:1234', models: [] },
      })
    })
  })
})
