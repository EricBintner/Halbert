// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * The wiring, not the widget.
 *
 * StatusStrip and groupInspections both have their own unit tests, and unit
 * tests of a component nobody mounts are exactly how the whole Plan B block
 * surface came to be green in CI and unreachable in the product. This drives
 * the real AgentChat with a real stream.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AgentChat } from './AgentChat'

const IDENTITY = {
  display_name: 'Test-Host', hostname: 'test-host.local',
  os: { name: 'macOS', version: '26.5.1', pretty: 'macOS 26.5.1', platform: 'Darwin', kernel: '25.5.0', arch: 'arm64' },
  uptime: { seconds: 86400, human: '1 day', boot_time: '' },
  cpu: { cores: 8, physical_cores: 8, percent: 12, temperature: null },
  memory: { total_gb: 32, used_gb: 8, percent: 25 },
  storage: { pools: [], healthy: 0, total: 0 },
  load_average: { '1min': 1, '5min': 1, '15min': 1 },
  all_healthy: true, first_person: 'I am Test-Host.', timestamp: '',
}

const jsonResponse = (body: unknown) => ({ ok: true, status: 200, json: async () => body } as Response)

/** `hold` keeps the stream open after the events, so a turn can be observed
 *  genuinely mid-flight. A stream that simply stops is not the same thing:
 *  the hook folds the finished turn away, and the tool that never completed
 *  goes with it. */
function sseBody(events: Array<Record<string, unknown>>, hold?: Promise<void>) {
  const text = events.map((e) => `data: ${JSON.stringify(e)}\n`).join('')
  const chunks = [new TextEncoder().encode(text)]
  return {
    getReader: () => ({
      read: async () => {
        const value = chunks.shift()
        if (value) return { done: false, value }
        if (hold) await hold
        return { done: true, value: undefined }
      },
    }),
  }
}

const ev = (type: string, extra: Record<string, unknown> = {}) => ({
  type, session_id: 'turn-1', timestamp: 0, ...extra,
})

/** A turn that opens a read and stops there — the read is still running. */
const MID_READ = [
  ev('session_started'),
  ev('state_change', { state: 'executing' }),
  ev('tool_start', { tool: 'read_file', args: { path: '/etc/fstab' }, execution_id: 'e1' }),
]

/** The same read, finished, plus two more. */
const THREE_READS_DONE = [
  ev('session_started'),
  ...['e1', 'e2', 'e3'].flatMap((id, i) => [
    ev('tool_start', { tool: 'read_file', args: { path: `/etc/f${i}` }, execution_id: id }),
    ev('tool_complete', { execution_id: id, success: true, result: 'x' }),
  ]),
  ev('response_complete', { response: 'done' }),
  ev('session_ended'),
]

function mount(events: Array<Record<string, unknown>>, hold?: Promise<void>) {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    const u = String(url)
    if (u.includes('/api/identity')) return jsonResponse(IDENTITY)
    if (u.includes('/api/instance/info')) return jsonResponse({ variant: 'sysadmin' })
    if (u.includes('/api/agent/message')) {
      return { ok: true, status: 200, statusText: 'OK', body: sseBody(events, hold) } as unknown as Response
    }
    return jsonResponse({ data: {} })
  }))
  return render(<AgentChat />)
}

beforeEach(() => {
  Element.prototype.scrollIntoView = vi.fn()
  HTMLCanvasElement.prototype.getContext = vi.fn() as never
})
afterEach(() => vi.unstubAllGlobals())

async function ask(text: string) {
  const box = await screen.findByRole('textbox')
  await userEvent.type(box, text)
  await userEvent.keyboard('{Enter}')
}

describe('AgentChat — the two layers', () => {
  it('reports a running read on the strip and not in the transcript', async () => {
    let release!: () => void
    mount(MID_READ, new Promise<void>((r) => { release = r }))
    await ask('why is samba down?')

    await waitFor(() => {
      expect(document.querySelector('[data-status-strip]')).toBeTruthy()
    })
    expect(screen.getByText('Reading /etc/fstab')).toBeTruthy()
    // Two places for one step would show it twice and leave the box behind
    // when it ended. The strip keeps nothing; the feed keeps everything.
    expect(screen.queryByText('read_file')).toBeNull()
    release()
  })

  it('folds the finished reads into one line and clears the strip', async () => {
    mount(THREE_READS_DONE)
    await ask('why is samba down?')

    await waitFor(() => {
      expect(screen.getByText(/Looked at 3 files/)).toBeTruthy()
    })
    // Nothing is running any more, so the ephemeral layer holds nothing.
    expect(document.querySelector('[data-status-strip]')).toBeNull()
  })
})
