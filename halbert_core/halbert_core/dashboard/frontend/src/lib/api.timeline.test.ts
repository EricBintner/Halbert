// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * The timeline wrappers: exact paths, exact query strings, and the
 * snake_case -> camelCase mapping the components rely on.
 */

import { describe, it, expect, afterEach, vi } from 'vitest'
import { api } from './api'

function mockFetch(body: unknown, ok = true) {
  const fetchMock = vi.fn().mockResolvedValue({
    ok,
    status: ok ? 200 : 500,
    text: async () => '',
    json: async () => body,
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

afterEach(() => vi.unstubAllGlobals())

describe('api.getTimeline', () => {
  it('hits /api/agent/timeline with only the params given', async () => {
    const fetchMock = mockFetch({ turns: [], has_more: false, current_thread: null })
    await api.getTimeline({ before: 't-1', limit: 10 })
    expect(fetchMock.mock.calls[0][0]).toBe('/api/agent/timeline?before=t-1&limit=10')

    await api.getTimeline({})
    expect(fetchMock.mock.calls[1][0]).toBe('/api/agent/timeline')
  })

  it('maps a server page onto TimelinePage with millisecond timestamps', async () => {
    mockFetch({
      has_more: true,
      current_thread: { thread_id: 'th-1', title: 'Samba share setup', status: 'open' },
      turns: [
        {
          turn_id: 't-1',
          thread_id: 'th-1',
          timestamp: 1_784_000_000,
          origin: 'human',
          user: { message_id: 7, content: 'is samba running?', timestamp: 1_784_000_000, status: 'complete' },
          assistant: { message_id: 8, content: 'Yes.', timestamp: 1_784_000_003, status: 'complete' },
          blocks: [{ tool: 'run_command', args: { command: 'systemctl status smbd' }, result: 'active', exit: 0, execution_id: 'x1' }],
          terminal_block_ids: ['term-9'],
          diff_proposals: [{ diff_id: 'd1', file_path: '/etc/samba/smb.conf', edit_blocks: [{ search: 'a', replace: 'b' }], status: 'pending' }],
        },
      ],
    })

    const page = await api.getTimeline({ limit: 50 })

    expect(page.hasMore).toBe(true)
    expect(page.currentThread).toEqual({ threadId: 'th-1', title: 'Samba share setup', status: 'open' })
    const turn = page.turns[0]
    expect(turn.turnId).toBe('t-1')
    expect(turn.timestamp).toBe(1_784_000_000_000)
    expect(turn.user).toEqual({ messageId: 7, content: 'is samba running?', timestamp: 1_784_000_000_000, status: 'complete' })
    expect(turn.assistant?.content).toBe('Yes.')
    expect(turn.blocks[0]).toEqual({ tool: 'run_command', args: { command: 'systemctl status smbd' }, result: 'active', exit: 0, executionId: 'x1' })
    expect(turn.terminalBlockIds).toEqual(['term-9'])
    expect(turn.diffProposals[0]).toMatchObject({ id: 'd1', filePath: '/etc/samba/smb.conf', newContent: 'b', oldContent: 'a', status: 'pending' })
  })

  it('degrades a malformed page to an empty one', async () => {
    mockFetch({})
    const page = await api.getTimeline({})
    expect(page).toEqual({ turns: [], hasMore: false, currentThread: null })
  })
})

describe('api.getCurrentThread', () => {
  it('accepts the physical conversation_id column as the thread id', async () => {
    const fetchMock = mockFetch({ conversation_id: 'th-2', title: 'ZFS scrub', status: 'paused' })
    const thread = await api.getCurrentThread()
    expect(fetchMock.mock.calls[0][0]).toBe('/api/agent/thread/current')
    expect(thread).toEqual({ threadId: 'th-2', title: 'ZFS scrub', status: 'paused' })
  })
})

describe('api.retractRecall', () => {
  it('DELETEs the recall row', async () => {
    const fetchMock = mockFetch({ ok: true })
    await api.retractRecall('th-1', 'th-0')
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/agent/thread/th-1/recall/th-0')
    expect(init.method).toBe('DELETE')
  })
})
