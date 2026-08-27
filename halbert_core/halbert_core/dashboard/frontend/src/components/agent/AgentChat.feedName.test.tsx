// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * The conversation feed says who it is a conversation with.
 *
 * `Timeline` renders `role="feed"`, and a feed's accessible name is how
 * someone navigating by landmark knows what they have arrived in. It could
 * only ever say "Conversation" — true of every conversation with anything —
 * so the prop exists (`Timeline.test.tsx` pins both of its branches) and
 * nothing passed it. This is the wiring: AgentChat reads the machine's
 * identity and hands over the name.
 *
 * `display_name` is the name chosen in onboarding — what this machine is
 * CALLED. Never `hostname`, which is a DNS fact about the machine rather than
 * its identity, and never a stand-in word in place of either.
 *
 * Its own file, deliberately: `useHostIdentity` keeps its snapshot in module
 * state and holds the last good identity across a failed poll (by design — a
 * machine does not stop being itself because one request missed). A test that
 * resolves an identity therefore leaves it resolved for every test after it
 * in the same file, and AgentChat.test.tsx has tests that need the greeting's
 * unresolved state. A separate file is a separate module registry.
 */

import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { AgentChat } from './AgentChat'

vi.mock('./TerminalTile', () => ({
  TerminalTile: ({ session }: { session: { id: string } }) => <div data-testid="live-tile">{session.id}</div>,
}))

/** One stored turn, so the feed renders at all (it is the empty state otherwise). */
const PAGE = {
  has_more: false,
  current_thread: null,
  turns: [
    {
      turn_id: 't-1',
      thread_id: 'th-1',
      timestamp: 1_784_000_000,
      origin: 'human',
      user: { message_id: 1, content: 'is samba running?', timestamp: 1_784_000_000, status: 'complete' },
      assistant: { message_id: 2, content: 'smbd is active.', timestamp: 1_784_000_003, status: 'complete' },
      blocks: [],
      terminal_block_ids: [],
      diff_proposals: [],
    },
  ],
}

const IDENTITY = {
  display_name: 'Basement-NAS',
  // Deliberately different from the name, and deliberately the kind of string
  // that would look plausible in the label if the wrong field were read.
  hostname: 'basement-nas-01.lan',
  os: { name: 'Debian', version: '13', pretty: 'Debian 13', platform: 'Linux', kernel: '6.9', arch: 'x86_64' },
  uptime: { seconds: 86400, human: '1 day', boot_time: '' },
  cpu: { cores: 8, physical_cores: 8, percent: 12, temperature: null },
  memory: { total_gb: 32, used_gb: 8, percent: 25 },
  storage: { pools: [], healthy: 0, total: 0 },
  load_average: { '1min': 1, '5min': 1, '15min': 1 },
  all_healthy: true,
  first_person: 'I am Basement-NAS.',
  timestamp: '',
}

/** `identity` answers when `identity` is given; everything else is "starting". */
function routeFetch(identity: unknown | null) {
  const fetchMock = vi.fn((url: string) => {
    const path = String(url)
    if (path.includes('/api/identity')) {
      return identity
        ? Promise.resolve({ ok: true, status: 200, text: async () => '', json: async () => identity })
        : Promise.resolve({ ok: false, status: 503, text: async () => '', json: async () => ({}) })
    }
    if (path.includes('/api/agent/timeline')) {
      return Promise.resolve({ ok: true, status: 200, text: async () => '', json: async () => PAGE })
    }
    return Promise.resolve({ ok: false, status: 503, text: async () => '', json: async () => ({}) })
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe('AgentChat names the feed for the machine', () => {
  beforeEach(() => {
    Element.prototype.scrollIntoView = vi.fn() as unknown as typeof Element.prototype.scrollIntoView
    vi.spyOn(console, 'error').mockImplementation(() => {})
    vi.spyOn(console, 'warn').mockImplementation(() => {})
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('falls back to a bare "Conversation" until the identity resolves', async () => {
    // Runs first on purpose: this is the state the module store is in before
    // anything has answered, and it cannot be got back to once it has.
    routeFetch(null)
    render(<AgentChat />)

    const feed = await screen.findByRole('feed')
    expect(feed).toHaveAccessibleName('Conversation')
  })

  it('is a conversation with the name the machine was given, not its hostname', async () => {
    routeFetch(IDENTITY)
    render(<AgentChat />)

    await screen.findByRole('feed')
    await waitFor(() =>
      expect(screen.getByRole('feed')).toHaveAccessibleName('Conversation with Basement-NAS'),
    )
    // The DNS name is a fact about the machine, not what it is called. It
    // must not reach the label — including as a fallback when the name is
    // there to be read.
    expect(screen.getByRole('feed').getAttribute('aria-label')).not.toContain('basement-nas-01.lan')
  })
})
