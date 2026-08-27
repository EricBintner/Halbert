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

  it('carries a failed tool block\'s status and error through, not just its exit code', async () => {
    // A non-run_command tool (read_file) fails: state_machine._tool_block
    // never sets `exit` for it, only `status`/`error` — a consumer that
    // derives pass/fail from `exit` alone would render this as a silent
    // success. See state_machine.py:614-638, 1664-1666.
    mockFetch({
      has_more: false,
      current_thread: null,
      turns: [
        {
          turn_id: 't-1',
          thread_id: 'th-1',
          timestamp: 1_784_000_000,
          origin: 'human',
          user: null,
          assistant: null,
          blocks: [
            { tool: 'read_file', args: { path: '/etc/no-such' }, result: null, exit: null, execution_id: 'x2', status: 'error', error: 'ENOENT' },
            // The staged-but-superseded shape carries no execution_id or error key at all.
            { tool: 'run_command', args: { command: 'reboot' }, result: 'not run — superseded', exit: null, status: 'superseded' },
          ],
          terminal_block_ids: [],
          diff_proposals: [],
        },
      ],
    })

    const page = await api.getTimeline({})
    expect(page.turns[0].blocks[0]).toEqual({
      tool: 'read_file',
      args: { path: '/etc/no-such' },
      result: null,
      exit: null,
      executionId: 'x2',
      status: 'error',
      error: 'ENOENT',
    })
    expect(page.turns[0].blocks[1]).toEqual({
      tool: 'run_command',
      args: { command: 'reboot' },
      result: 'not run — superseded',
      exit: null,
      executionId: undefined,
      status: 'superseded',
      error: undefined,
    })
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
