// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * R11-02: a queued message must not walk over a turn that is waiting on you.
 *
 * Typing while the agent is streaming queues the message, and the queue
 * drains on `!isStreaming`. But a turn that stops on
 * `tool_confirmation_required` is not finished — it is parked, holding a
 * dialog the user has to answer. The drain had no parked-turn guard (the
 * fold effect twenty lines above it does), so it folded the live turn away
 * and started a new one: the ConfirmationDialog vanished and the approval
 * was silently dropped.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AgentChat } from './AgentChat'

const ENDPOINT = {
  id: 'ep1', name: 'Local', provider: 'ollama',
  url: 'http://localhost:11434', api_key: '',
}

const IDENTITY = {
  display_name: 'Test-Host',
  hostname: 'test-host.local',
  os: { name: 'macOS', version: '26.5.1', pretty: 'macOS 26.5.1', platform: 'Darwin', kernel: '25.5.0', arch: 'arm64' },
  uptime: { seconds: 86400, human: '1 day', boot_time: '' },
  cpu: { cores: 8, physical_cores: 8, percent: 12, temperature: null },
  memory: { total_gb: 32, used_gb: 8, percent: 25 },
  storage: { pools: [], healthy: 0, total: 0 },
  load_average: { '1min': 1, '5min': 1, '15min': 1 },
  all_healthy: true,
  first_person: 'I am Test-Host.',
  timestamp: '',
}

function jsonResponse(body: unknown) {
  return { ok: true, status: 200, json: async () => body } as Response
}

function sseBody(events: Array<Record<string, unknown>>) {
  const text = events.map((e) => `data: ${JSON.stringify(e)}\n`).join('')
  const chunks = [new TextEncoder().encode(text)]
  return {
    getReader: () => ({
      read: async () => {
        const value = chunks.shift()
        return value ? { done: false, value } : { done: true, value: undefined }
      },
    }),
  }
}

const ev = (type: string, extra: Record<string, unknown> = {}) => ({
  type, session_id: 'turn-1', timestamp: 0, ...extra,
})

/** A turn that stops on a confirmation and waits for the user. */
const PARKED_TURN = [
  ev('session_started'),
  ev('state_change', { state: 'executing' }),
  ev('tool_confirmation_required', {
    execution_id: 'act-1',
    tool: 'run_command',
    description: 'Restart the samba service',
    risk_level: 'high',
  }),
]

let fetchMock: ReturnType<typeof vi.fn>
/** Resolves the first agent turn's stream so we control its timing. */
let releaseFirstTurn: () => void

beforeEach(() => {
  Element.prototype.scrollIntoView = vi.fn()
  HTMLCanvasElement.prototype.getContext = vi.fn() as never

  let firstTurnGate: Promise<void>
  firstTurnGate = new Promise((resolve) => { releaseFirstTurn = resolve as () => void })
  let turn = 0

  fetchMock = vi.fn(async (url: string) => {
    const u = String(url)
    if (u.includes('/api/identity')) return jsonResponse(IDENTITY)
    if (u.includes('/api/instance/info')) return jsonResponse({ variant: 'sysadmin' })
    if (u.includes('/llm/config')) {
      return jsonResponse({ data: {
        llm_config: {
          saved_endpoints: [ENDPOINT],
          chat_model: { enabled: true, endpoint_id: 'ep1', model: 'model-alpha' },
          specialist_model: { enabled: false, endpoint_id: '', model: '' },
          vision_model: { enabled: false, endpoint_id: '', model: '' },
          secure_model: { enabled: false, endpoint_id: '', model: '' },
        },
        chat_capable_providers: ['ollama'],
      } })
    }
    if (u.includes('/api/agent/confirm')) {
      // Answering the dialog resumes the turn, which then ends.
      return { ok: true, status: 200, statusText: 'OK', body: sseBody([
        ev('state_change', { state: 'responding' }),
        ev('response_complete', { response: 'not restarting it then' }),
        ev('session_ended'),
      ]) } as unknown as Response
    }
    if (u.includes('/api/agent/message')) {
      turn += 1
      if (turn === 1) {
        await firstTurnGate
        return { ok: true, status: 200, statusText: 'OK', body: sseBody(PARKED_TURN) } as unknown as Response
      }
      return { ok: true, status: 200, statusText: 'OK', body: sseBody([ev('session_ended')]) } as unknown as Response
    }
    return jsonResponse({ data: {} })
  })
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => vi.unstubAllGlobals())

function sends() {
  return fetchMock.mock.calls.filter(([u]) => String(u).includes('/api/agent/message'))
}

async function type(text: string) {
  const box = await screen.findByRole('textbox')
  await userEvent.clear(box)
  await userEvent.type(box, text)
  await userEvent.keyboard('{Enter}')
}

describe('AgentChat — the message queue and a parked turn', () => {
  it('keeps the confirmation dialog when a message was queued behind it', async () => {
    render(<AgentChat />)
    await screen.findByRole('textbox')

    await type('restart samba')
    await waitFor(() => expect(sends()).toHaveLength(1))

    // Typed while the first turn is still streaming: this queues.
    await type('and check the logs after')

    releaseFirstTurn()
    await screen.findByText(/Confirmation Required/i)

    // The queue drains on !isStreaming, which a parked turn also satisfies.
    await new Promise((r) => setTimeout(r, 400))

    expect(screen.queryByText(/Confirmation Required/i)).toBeInTheDocument()
    expect(sends()).toHaveLength(1)
  })

  it('sends the queued message once the confirmation is answered', async () => {
    render(<AgentChat />)
    await screen.findByRole('textbox')

    await type('restart samba')
    await waitFor(() => expect(sends()).toHaveLength(1))
    await type('and check the logs after')

    releaseFirstTurn()
    const reject = await screen.findByRole('button', { name: /cancel|reject|no/i })
    await userEvent.click(reject)

    await waitFor(() => expect(sends().length).toBeGreaterThan(1), { timeout: 3000 })
  })
})
