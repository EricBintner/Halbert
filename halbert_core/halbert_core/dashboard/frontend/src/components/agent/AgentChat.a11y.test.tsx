// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * The chat's a11y contract, as a screen reader meets it.
 *
 * The shell owns the one live region of each kind (lib/announce.ts); this
 * surface's half of the contract is to SAY the right things through it at
 * the moments a person who cannot see the screen otherwise has no signal:
 * that a message went somewhere (sent, or queued behind the busy agent),
 * that the agent moved through its states, that it finished, was stopped,
 * or failed. A feed is not a live region — articles appear silently — so
 * none of these announcements is redundant with the timeline.
 *
 * The other half is the composer's combobox: the mention popup must be a
 * real listbox with a real active option, because a popup that can be seen
 * but not reached with the keyboard is decoration, not a control.
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { AgentChat } from './AgentChat'
import { subscribeAnnouncements } from '../../lib/announce'

/** One SSE body: every event as a `data:` line, delivered in one chunk. */
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

/** An SSE body that delivers one chunk, then never resolves: a held stream. */
function heldBody(chunk: string) {
  const encoded = new TextEncoder().encode(chunk)
  let sent = false
  return {
    getReader: () => ({
      read: async () => {
        if (sent) return new Promise<{ done: boolean; value?: undefined }>(() => {})
        sent = true
        return { done: false, value: encoded }
      },
    }),
  }
}

const PAGE = {
  has_more: false,
  current_thread: null,
  turns: [],
}

/** One `response_chunk` as a `data:` line, ready for a held stream. */
const chunkLine = (content: string) =>
  `data: ${JSON.stringify({ type: 'response_chunk', session_id: 's', timestamp: 0, content })}\n`

function ev(type: string, extra: Record<string, unknown> = {}) {
  return { type, session_id: 's', timestamp: 0, ...extra }
}

/**
 * The usual routes: a reachable (empty) timeline, mentionables, and — per
 * test — whatever the agent stream should answer.
 */
function routeFetch(agentStream?: () => unknown) {
  const fetchMock = vi.fn().mockImplementation((url: string) => {
    const path = String(url)
    if (path.includes('/api/agent/message')) {
      return Promise.resolve({ ok: true, status: 200, statusText: 'OK', body: agentStream?.() ?? sseBody([]) })
    }
    if (path.includes('/api/agent/timeline')) {
      return Promise.resolve({ ok: true, status: 200, text: async () => '', json: async () => PAGE })
    }
    if (path.includes('/api/discoveries/mentionables')) {
      return Promise.resolve({
        ok: true, status: 200, text: async () => '',
        json: async () => ({
          mentionables: [
            { id: 'm-1', mention: '@logs', name: 'System logs', type: 'file' },
            { id: 'm-2', mention: '@uptime', name: 'Uptime', type: 'terminal' },
          ],
        }),
      })
    }
    return Promise.resolve({ ok: false, status: 503, text: async () => '', json: async () => ({}) })
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function heard() {
  const said: string[] = []
  const stop = subscribeAnnouncements((text) => said.push(text))
  return { said, stop }
}

describe('AgentChat speaks the streaming lifecycle', () => {
  let listener: { said: string[]; stop: () => void }

  beforeEach(() => {
    listener = heard()
    Element.prototype.scrollIntoView = vi.fn() as unknown as typeof Element.prototype.scrollIntoView
    vi.spyOn(console, 'log').mockImplementation(() => {})
    vi.spyOn(console, 'error').mockImplementation(() => {})
    vi.spyOn(console, 'warn').mockImplementation(() => {})
  })

  afterEach(() => {
    listener.stop()
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('says a send, the agent’s progress, and the finished reply — once each', async () => {
    routeFetch(() => sseBody([
      ev('state_change', { state: 'planning', previous_state: null }),
      ev('state_change', { state: 'searching', previous_state: 'planning' }),
      ev('state_change', { state: 'responding', previous_state: 'searching' }),
      ev('response_chunk', { content: 'All good.' }),
      ev('response_complete', { content: 'All good.' }),
    ]))
    render(<AgentChat />)
    const composer = await screen.findByPlaceholderText(/^Ask Halbert/)

    await userEvent.type(composer, 'check the logs{Enter}')

    await waitFor(() => expect(listener.said).toContain('Reply finished'))
    expect(listener.said.filter((s) => s === 'Message sent')).toHaveLength(1)
    expect(listener.said.filter((s) => s === 'Planning response')).toHaveLength(1)
    expect(listener.said.filter((s) => s === 'Searching knowledge base')).toHaveLength(1)
    expect(listener.said.filter((s) => s === 'Responding')).toHaveLength(1)
    expect(listener.said.filter((s) => s === 'Reply finished')).toHaveLength(1)
  })

  it('says a message is queued while the agent is busy, not sent', async () => {
    routeFetch(() => heldBody(chunkLine('working…')))
    render(<AgentChat />)
    const composer = await screen.findByPlaceholderText(/^Ask Halbert/)

    await userEvent.type(composer, 'first question{Enter}')
    // The stream is held open: the agent stays busy.
    await waitFor(() => expect(screen.getByRole('button', { name: 'Stop' })).toBeInTheDocument())

    await userEvent.type(composer, 'and while you are at it{Enter}')

    // The first question was sent; the second was queued, not sent again.
    expect(listener.said.filter((s) => s === 'Message sent')).toHaveLength(1)
    expect(listener.said.filter((s) => s === 'Message queued')).toHaveLength(1)
    expect(await screen.findByText(/Queued: and while you are at it/)).toBeInTheDocument()
  })

  it('says Stopped when the turn is cancelled, and nothing after it', async () => {
    routeFetch(() => heldBody(chunkLine('working…')))
    render(<AgentChat />)
    const composer = await screen.findByPlaceholderText(/^Ask Halbert/)

    await userEvent.type(composer, 'long question{Enter}')
    const stop = await screen.findByRole('button', { name: 'Stop' })
    await userEvent.click(stop)

    expect(listener.said).toContain('Stopped')
    // The end-of-stream announcement stays out of the way: "Stopped" is
    // the whole sentence.
    expect(listener.said).not.toContain('Reply finished')
  })

  it('leaves the error to the error announcement, not a finished reply', async () => {
    routeFetch(() => sseBody([
      ev('response_chunk', { content: 'partial' }),
      ev('error', { message: 'The model endpoint refused the connection.' }),
    ]))
    render(<AgentChat />)
    const composer = await screen.findByPlaceholderText(/^Ask Halbert/)

    await userEvent.type(composer, 'anything{Enter}')

    await waitFor(() =>
      expect(listener.said).toContain('The model endpoint refused the connection.'),
    )
    expect(listener.said).not.toContain('Reply finished')
  })

  it('does not call a turn waiting for approval finished', async () => {
    routeFetch(() => sseBody([
      ev('tool_confirmation_required', {
        execution_id: 'x-1', tool: 'shell', description: 'rm a file', risk_level: 'high',
      }),
    ]))
    render(<AgentChat />)
    const composer = await screen.findByPlaceholderText(/^Ask Halbert/)

    await userEvent.type(composer, 'clean up{Enter}')

    // The approval prompt is said once, assertively, by the hook — and the
    // stream ending does not talk over it with "Reply finished".
    await waitFor(() =>
      expect(listener.said.filter((s) => s === 'Waiting for your approval')).toHaveLength(1),
    )
    expect(listener.said).not.toContain('Reply finished')
  })
})

describe('AgentChat mention popup is a keyboard listbox', () => {
  beforeEach(() => {
    Element.prototype.scrollIntoView = vi.fn() as unknown as typeof Element.prototype.scrollIntoView
    vi.spyOn(console, 'log').mockImplementation(() => {})
    vi.spyOn(console, 'error').mockImplementation(() => {})
    vi.spyOn(console, 'warn').mockImplementation(() => {})
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('exposes listbox semantics and walks the options with the arrow keys', async () => {
    routeFetch()
    render(<AgentChat />)
    const composer = await screen.findByPlaceholderText(/^Ask Halbert/)

    await userEvent.type(composer, 'look at @')

    // The popup is a named listbox, and the composer is its combobox.
    const listbox = screen.getByRole('listbox', { name: 'Mentions' })
    expect(composer).toHaveAttribute('aria-expanded', 'true')
    expect(composer.getAttribute('aria-controls')).toBe(listbox.id)

    const options = screen.getAllByRole('option')
    expect(options).toHaveLength(2)
    // The first option is active from the moment the list opens.
    expect(options[0]).toHaveAttribute('aria-selected', 'true')
    expect(options[1]).toHaveAttribute('aria-selected', 'false')
    expect(composer.getAttribute('aria-activedescendant')).toBe(options[0].id)

    await userEvent.type(composer, '{ArrowDown}')
    expect(options[1]).toHaveAttribute('aria-selected', 'true')
    expect(composer.getAttribute('aria-activedescendant')).toBe(options[1].id)

    // Enter takes the active option, it does not send the message.
    await userEvent.type(composer, '{Enter}')
    expect(composer).toHaveValue('look at @uptime ')
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
    expect(composer).toHaveAttribute('aria-expanded', 'false')
  })

  it('does not open a listbox for text that mentions nothing', async () => {
    routeFetch()
    render(<AgentChat />)
    const composer = await screen.findByPlaceholderText(/^Ask Halbert/)

    await userEvent.type(composer, 'an ordinary question')

    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
    expect(composer).toHaveAttribute('aria-expanded', 'false')
  })
})

describe('AgentChat marks the busy conversation and names its icon buttons', () => {
  beforeEach(() => {
    Element.prototype.scrollIntoView = vi.fn() as unknown as typeof Element.prototype.scrollIntoView
    vi.spyOn(console, 'log').mockImplementation(() => {})
    vi.spyOn(console, 'error').mockImplementation(() => {})
    vi.spyOn(console, 'warn').mockImplementation(() => {})
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('flips aria-busy on the conversation while a turn is streaming', async () => {
    routeFetch(() => heldBody(chunkLine('working…')))
    const { container } = render(<AgentChat />)
    const composer = await screen.findByPlaceholderText(/^Ask Halbert/)

    const scrollRegion = container.querySelector<HTMLElement>('div[aria-busy]')
    expect(scrollRegion).not.toBeNull()
    expect(scrollRegion).toHaveAttribute('aria-busy', 'false')

    await userEvent.type(composer, 'question{Enter}')

    await waitFor(() => expect(scrollRegion).toHaveAttribute('aria-busy', 'true'))
  })

  it('gives the icon-only send button an accessible name', async () => {
    routeFetch()
    render(<AgentChat />)
    await screen.findByPlaceholderText(/^Ask Halbert/)

    expect(screen.queryByRole('button', { name: 'Send' })).not.toBeNull()
  })
})