// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * C3 (busy-mode unification): the client-side message queue is gone —
 * the backend owns busy semantics. A message typed while the agent is
 * streaming is sent to the server IMMEDIATELY as a mid-turn arrival
 * (it steers the running turn, or `/stop` claims the generation), and the
 * server's own verdict (`steer_accepted` / `stop_declined`) renders as a
 * chip where the old "Queued:" chips pretended to hold a queue.
 *
 * The R11-02 guarantee the old queue tests protected survives by
 * construction now: an arrival is not a turn, so it can never fold away a
 * turn that is parked on the user (waiting on a confirmation or an
 * undecided diff). Pinned here:
 *
 *  - typed-while-busy goes to the server immediately (a second
 *    /api/agent/message POST), not into a local queue;
 *  - the server's verdict renders (steer chip, stop-declined chip);
 *  - a turn parked on a confirmation keeps its dialog while an arrival
 *    lands — and the dialog is still answerable;
 *  - images keep the whole-turn path: an image send while busy is a turn
 *    (queued server-side), not a steer.
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
/** What the server answers for a mid-turn arrival (per-test). */
let arrivalEvents: Array<Record<string, unknown>>

beforeEach(() => {
  arrivalEvents = [ev('steer_accepted', { reason: 'steer', replaced: false, demoted: false })]
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
      // C3: typed-while-busy arrivals. The server's honest verdict —
      // steer_accepted, or a declined stop — is what the chips render.
      return { ok: true, status: 200, statusText: 'OK', body: sseBody(arrivalEvents) } as unknown as Response
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

describe('AgentChat — mid-turn arrivals replace the client queue (C3)', () => {
  it('sends typed-while-busy text to the server immediately and renders its verdict', async () => {
    render(<AgentChat />)
    await screen.findByRole('textbox')

    await type('restart samba')
    await waitFor(() => expect(sends()).toHaveLength(1))

    // Typed while the first turn is still streaming: this goes to the
    // server NOW (no local queue), as the second POST.
    await type('and check the logs after')
    await waitFor(() => expect(sends()).toHaveLength(2))

    // The server's verdict renders as a chip — the presentation of
    // server truth the old "Queued:" chips never were.
    expect(
      await screen.findByText(/Steered the running turn: and check the logs after/)
    ).toBeInTheDocument()
  })

  it('keeps the confirmation dialog while an arrival lands — the arrival is not a turn', async () => {
    render(<AgentChat />)
    await screen.findByRole('textbox')

    await type('restart samba')
    await waitFor(() => expect(sends()).toHaveLength(1))

    // Typed while the first turn is still streaming: sent immediately.
    await type('and check the logs after')
    await waitFor(() => expect(sends()).toHaveLength(2))

    releaseFirstTurn()
    await screen.findByText(/Confirmation Required/i)

    // The arrival never started a turn of its own, so the parked turn's
    // dialog survives (R11-02, now by construction), and it is still
    // answerable.
    expect(screen.queryByText(/Confirmation Required/i)).toBeInTheDocument()
    const reject = await screen.findByRole('button', { name: /cancel|reject|no/i })
    await userEvent.click(reject)
    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([u]) => String(u).includes('/api/agent/confirm'))).toBe(true),
      { timeout: 3000 },
    )
  })

  it('renders a declined stop verdict when the server declines it', async () => {
    // The server declined the stop (the turn completed first): the chip
    // says so with the server's own reason.
    arrivalEvents = [ev('stop_declined', { reason: 'turn completed, stop declined' })]
    render(<AgentChat />)
    await screen.findByRole('textbox')

    await type('restart samba')
    await waitFor(() => expect(sends()).toHaveLength(1))

    await type('/stop')
    await waitFor(() => expect(sends()).toHaveLength(2))
    expect(
      await screen.findByText(/Stop declined — turn completed, stop declined/)
    ).toBeInTheDocument()
  })
})