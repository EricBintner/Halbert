/**
 * API client for the Halbert dashboard backend.
 *
 * Reconstructed 2026-08-22: the original src/lib/ was never committed
 * (a bare `lib/` rule in .gitignore swallowed it). Method signatures and
 * endpoint paths were rebuilt from the consumer call sites and the
 * FastAPI route definitions.
 */

import { apiBase, apiUrl } from './apiBase'

async function request<T = any>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${apiBase()}${path}`, {
    headers: options.body ? { 'Content-Type': 'application/json' } : undefined,
    ...options,
  })
  if (!res.ok) {
    const detail = await res.text().catch(() => '')
    throw new Error(`API ${options.method ?? 'GET'} ${path} failed (${res.status}): ${detail}`)
  }
  return res.json()
}

export interface ChatMessage {
  role: string
  content: string
}

export interface AgentStreamResult {
  /** Final committed response text (structured JSON stripped by backend).
   * Empty when the stream ended without a response_complete content field —
   * callers should fall back to their onToken accumulation. */
  response: string
  /** Accumulated thinking deltas, when the agent emitted any. */
  reasoning?: string
  /** Last config-edit diff the agent proposed during the stream, if any. */
  diff?: {
    diffId: string
    editBlocks: Array<{ search: string; replace: string }>
  } | null
  sessionId: string
  /** Set when the agent finished normally (response_complete/session_ended). */
  completed?: boolean
  cancelled?: boolean
  /** Set on failure — callers should render this instead of proceeding. */
  error?: string
}

export const api = {
  // -----------------------------------------------------------------
  // Discoveries
  // -----------------------------------------------------------------
  getDiscoveries(type?: string) {
    const qs = type ? `?type=${encodeURIComponent(type)}` : ''
    return request(`/api/discoveries/${qs}`)
  },

  getDiscoveryStats() {
    return request('/api/discoveries/stats')
  },

  scanDiscoveries(scanType?: string) {
    return request('/api/discoveries/scan', {
      method: 'POST',
      body: JSON.stringify(scanType ? { scan_type: scanType } : {}),
    })
  },

  analyzeDiscoveries(analysisType: string, deep = false) {
    return request(`/api/discoveries/analyze/${encodeURIComponent(analysisType)}`, {
      method: 'POST',
      body: JSON.stringify({ deep }),
    })
  },

  getMentionables() {
    return request('/api/discoveries/mentionables')
  },

  getBackupStatuses() {
    return request('/api/discoveries/backup/statuses')
  },

  getBackupLogs(backupName: string) {
    return request(`/api/discoveries/backup/${encodeURIComponent(backupName)}/logs`)
  },

  getBackupHistory(backupName: string, limit = 50) {
    return request(`/api/discoveries/backup/${encodeURIComponent(backupName)}/history?limit=${limit}`)
  },

  // -----------------------------------------------------------------
  // Conversations
  // -----------------------------------------------------------------
  listConversations() {
    return request('/api/conversations')
  },

  createConversation(name?: string) {
    return request('/api/conversations', {
      method: 'POST',
      body: JSON.stringify({ name }),
    })
  },

  getConversation(id: string) {
    return request(`/api/conversations/${encodeURIComponent(id)}`)
  },

  renameConversation(id: string, name: string) {
    return request(`/api/conversations/${encodeURIComponent(id)}`, {
      method: 'PATCH',
      body: JSON.stringify({ name }),
    })
  },

  deleteConversation(id: string) {
    return request(`/api/conversations/${encodeURIComponent(id)}`, { method: 'DELETE' })
  },

  addMessageToConversation(
    conversationId: string,
    role: string,
    content: string,
    mentions: string[] = [],
    reasoning?: string,
  ) {
    return request(`/api/conversations/${encodeURIComponent(conversationId)}/messages`, {
      method: 'POST',
      body: JSON.stringify({ role, content, mentions, reasoning }),
    })
  },

  // -----------------------------------------------------------------
  // Agent chat (legacy /api/chat/* retired — T4b.1)
  //
  // Conversation traffic goes through the agent state machine at
  // /api/agent/message (SSE). sendAgentStream() maps the agent's typed
  // event stream onto the callback contract the panels were built on.
  // -----------------------------------------------------------------
  async sendAgentStream(
    message: string,
    opts: {
      sessionId?: string
      images?: string[]
      onToken?: (token: string) => void
      onThinking?: (delta: string) => void
      onActivity?: (activity: {
        type: 'scan' | 'read' | 'plan'
        data: Record<string, unknown>
      }) => void
      onDiffProposed?: (diff: {
        diffId: string
        editBlocks: Array<{ search: string; replace: string }>
        blockCount: number
      }) => void
      onError?: (error: string) => void
    } = {},
  ): Promise<AgentStreamResult> {
    const {
      images,
      onToken,
      onThinking,
      onActivity,
      onDiffProposed,
      onError,
    } = opts
    const sessionId = opts.sessionId || crypto.randomUUID()

    let fullResponse = ''
    let reasoning = ''
    let diff: AgentStreamResult['diff'] = null
    let completed = false
    let cancelled = false

    // Performance tweaks from Settings > AI > Performance Tweaks
    // (same localStorage source as useAgentStream.ts).
    let maxTokens = 8192
    let temperature = 0.7
    try {
      const tweaks = localStorage.getItem('halbert_gpu_tweaks')
      if (tweaks) {
        const parsed = JSON.parse(tweaks)
        if (parsed.maxTokens) maxTokens = parsed.maxTokens
        if (parsed.temperature) temperature = parsed.temperature
      }
    } catch {
      /* defaults are fine */
    }

    const fail = (msg: string): AgentStreamResult => {
      onError?.(msg)
      return {
        response: '',
        error: msg,
        reasoning: reasoning || undefined,
        diff,
        sessionId,
      }
    }

    let res: Response
    try {
      res = await fetch(apiUrl('/api/agent/message'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message,
          session_id: sessionId,
          images,
          max_tokens: maxTokens,
          temperature,
        }),
      })
    } catch (err) {
      return fail(err instanceof Error ? err.message : 'Connection error')
    }
    if (!res.ok || !res.body) {
      return fail(`Agent request failed (HTTP ${res.status})`)
    }

    try {
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      for (;;) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() ?? '' // keep incomplete line

        for (const line of lines) {
          if (!line.startsWith('data:')) continue
          let data: any
          try {
            data = JSON.parse(line.slice(5).trim())
          } catch {
            continue // partial event; stays impossible here but tolerate
          }

          switch (data.type) {
            case 'response_chunk':
              onToken?.(data.content ?? '')
              break
            case 'thinking':
              reasoning += data.content ?? ''
              onThinking?.(data.content ?? '')
              break
            case 'scan_start':
              onActivity?.({
                type: 'scan',
                data: { source: data.source, query: data.query },
              })
              break
            case 'context_loaded':
              onActivity?.({
                type: 'read',
                data: {
                  source: data.source,
                  label: data.label,
                  count: data.count,
                },
              })
              break
            case 'plan':
              onActivity?.({ type: 'plan', data: { steps: data.steps } })
              break
            case 'diff_proposed': {
              const editBlocks = data.edit_blocks || []
              diff = { diffId: data.diff_id, editBlocks }
              onDiffProposed?.({
                diffId: data.diff_id,
                editBlocks,
                blockCount:
                  data.block_count ?? editBlocks.length ?? 0,
              })
              break
            }
            case 'response_complete':
              // The backend strips structured-action blocks (module
              // invocation JSON) from the committed text — adopt it.
              if (typeof data.content === 'string' && data.content) {
                fullResponse = data.content
              }
              completed = true
              break
            case 'session_ended':
              completed = true
              break
            case 'cancelled':
              cancelled = true
              completed = true
              break
            case 'error':
              return fail(String(data.message || 'Agent error'))
          }
        }
      }
    } catch (err) {
      return fail(err instanceof Error ? err.message : 'Stream error')
    }

    return {
      response: fullResponse,
      reasoning: reasoning || undefined,
      diff,
      sessionId,
      completed,
      cancelled,
    }
  },

  // -----------------------------------------------------------------
  // Models / personas
  // -----------------------------------------------------------------
  getLoadedModelStatus() {
    // Was /api/chat/models/loaded — moved to the settings router with the
    // chat retirement (T4b.1). Same response shape.
    return request('/api/settings/model/loaded')
  },

  getPersonaNames() {
    return request('/api/persona/list')
  },

  // -----------------------------------------------------------------
  // Services / terminal
  // -----------------------------------------------------------------
  controlService(serviceName: string, action: string) {
    return request(`/api/services/services/${encodeURIComponent(serviceName)}/control`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
  },

  executeCommand(command: string) {
    return request('/api/terminal/exec', {
      method: 'POST',
      body: JSON.stringify({ command }),
    })
  },

  checkCommandSafety(command: string) {
    return request('/api/terminal/check-safety', {
      method: 'POST',
      body: JSON.stringify({ command }),
    })
  },

  // -----------------------------------------------------------------
  // Agent conversations (Phase 36 agent path)
  // -----------------------------------------------------------------
  listAgentConversations() {
    return request('/api/agent/conversations')
  },

  getAgentConversation(conversationId: string) {
    return request(`/api/agent/conversations/${encodeURIComponent(conversationId)}`)
  },

  deleteAgentConversation(conversationId: string) {
    return request(`/api/agent/conversations/${encodeURIComponent(conversationId)}`, {
      method: 'DELETE',
    })
  },

  // -----------------------------------------------------------------
  // "Why" annotations
  // NOTE: no backend endpoint exists for this yet (verified 2026-08-22;
  // the WhyBrain/WhyOverlay UI is live but persistence was never built).
  // Planned to be backed by the knowledge layer in Phase 2.
  // -----------------------------------------------------------------
  saveWhy(itemId: string, itemName: string, itemType: string, why: string) {
    return request('/api/why', {
      method: 'POST',
      body: JSON.stringify({ item_id: itemId, item_name: itemName, item_type: itemType, why }),
    })
  },
}
