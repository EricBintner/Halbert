/**
 * API client for the Halbert dashboard backend.
 *
 * Reconstructed 2026-08-22: the original src/lib/ was never committed
 * (a bare `lib/` rule in .gitignore swallowed it). Method signatures and
 * endpoint paths were rebuilt from the consumer call sites and the
 * FastAPI route definitions.
 */

const API_BASE = ''

async function request<T = any>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
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

export interface ThinkingStep {
  type: 'thought' | 'action' | 'observation' | 'final'
  content: string
  duration_ms?: number
  tool_name?: string
  tool_args?: Record<string, any>
  tool_result?: Record<string, any>
}

export interface ChatResponse {
  response: string
  mentions_resolved?: any[]
  suggested_actions?: any[]
  debug?: any
  thinking_steps?: ThinkingStep[]
  thinking_duration_ms?: number
  used_react?: boolean
}

export interface ConfigChatResponse {
  response: string
  edit_blocks?: Array<{ search: string; replace: string }>
  proposed_content?: string
  summary?: string
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
  // Chat
  // -----------------------------------------------------------------
  sendChat(
    message: string,
    mentions: string[] = [],
    persona = 'guide',
    debug = false,
    currentPage = '',
    pageContext = '',
    history: ChatMessage[] = [],
    images: string[] = [],
  ): Promise<ChatResponse> {
    return request('/api/chat/send', {
      method: 'POST',
      body: JSON.stringify({
        message,
        mentions,
        persona,
        debug,
        current_page: currentPage,
        page_context: pageContext,
        history,
        images,
      }),
    })
  },

  async sendChatStream(
    message: string,
    mentions: string[] = [],
    persona = 'guide',
    currentPage = '',
    pageContext = '',
    history: ChatMessage[] = [],
    conversationId = '',
    onToken: (token: string) => void = () => {},
    onComplete: (fullResponse: string, thinkingSteps?: ThinkingStep[], reasoning?: string) => void = () => {},
    onError: (error: string) => void = () => {},
    onThinking?: (thinkingDelta: string) => void,
    onActivity?: (activity: { type: 'scan' | 'read' | 'plan'; data: Record<string, unknown> }) => void,
  ): Promise<void> {
    try {
      const res = await fetch(`${API_BASE}/api/chat/send/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message,
          mentions,
          persona,
          current_page: currentPage,
          page_context: pageContext,
          history,
          conversation_id: conversationId,
        }),
      })
      if (!res.ok || !res.body) {
        throw new Error(`Chat stream failed (${res.status})`)
      }
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      for (;;) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })

        const events = buffer.split('\n\n')
        buffer = events.pop() ?? ''

        for (const evt of events) {
          const line = evt.split('\n').find(l => l.startsWith('data:'))
          if (!line) continue
          let data: any
          try {
            data = JSON.parse(line.slice(5).trim())
          } catch {
            continue
          }
          if (data.error) {
            onError(String(data.error))
            return
          }
          if (data.done) {
            onComplete(data.full_response ?? '', data.thinking_steps, data.reasoning)
            return
          }
          if (data.token) {
            onToken(data.token)
          }
          if (data.reasoning && onThinking) {
            onThinking(data.reasoning)
          }
          if (data.activity && onActivity) {
            onActivity(data.activity)
          }
        }
      }
    } catch (err) {
      onError(err instanceof Error ? err.message : String(err))
    }
  },

  sendConfigChat(
    message: string,
    filePath: string,
    fileContent: string,
    history: ChatMessage[] = [],
    images: string[] = [],
  ): Promise<ConfigChatResponse> {
    return request('/api/chat/config', {
      method: 'POST',
      body: JSON.stringify({
        message,
        file_path: filePath,
        file_content: fileContent,
        history,
        images,
      }),
    })
  },

  // -----------------------------------------------------------------
  // Models / personas
  // -----------------------------------------------------------------
  getModels() {
    return request('/api/chat/models')
  },

  selectModel(modelId: string) {
    return request(`/api/chat/models/select?model_id=${encodeURIComponent(modelId)}`, {
      method: 'POST',
    })
  },

  getLoadedModels() {
    return request('/api/chat/models/loaded')
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
