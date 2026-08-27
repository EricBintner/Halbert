// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * A terminal id the store does not know is still a fact about the turn:
 * a terminal ran here and ended. It renders as a static chip, never
 * disappears.
 */

import { render, screen } from '@testing-library/react'
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { InlineTerminals } from './InlineTerminals'
import { terminalSessionStore as store } from '../../hooks/useTerminalSessions'

vi.mock('./TerminalTile', () => ({
  TerminalTile: ({ session }: { session: { id: string } }) => <div data-testid="live-tile">{session.id}</div>,
}))

describe('InlineTerminals', () => {
  beforeEach(() => {
    store.closeAll()
    vi.stubGlobal('IntersectionObserver', class {
      observe() {}
      unobserve() {}
      disconnect() {}
    })
  })

  afterEach(() => {
    store.closeAll()
    vi.unstubAllGlobals()
  })

  it('renders a live tile for known ids and an ended chip for unknown ones, in order', () => {
    store.adopt('t-live', { command: 'htop', pid: 9 })

    const { container } = render(<InlineTerminals sessionIds={['t-gone', 't-live']} />)

    expect(screen.getByText('terminal · ended')).toBeInTheDocument()
    expect(screen.getByTestId('live-tile')).toHaveTextContent('t-live')
    const order = Array.from(container.querySelectorAll('[data-session-id], [data-terminal-origin]')).map(
      (el) => el.getAttribute('data-session-id') ?? el.getAttribute('data-terminal-origin'),
    )
    expect(order).toEqual(['t-gone', 't-live'])
  })

  it('renders chips even when the store knows none of the ids', () => {
    render(<InlineTerminals sessionIds={['a', 'b']} />)
    expect(screen.getAllByText('terminal · ended')).toHaveLength(2)
  })

  it('wraps each ended chip in its own block-level element so consecutive chips stack, not butt together', () => {
    // StaticTerminalChip's root is an inline-flex <span>; two of them as bare
    // .map() siblings sit on the same line with no gap between them. Each
    // must be wrapped so the stack's space-y-2 puts one per line.
    const { container } = render(<InlineTerminals sessionIds={['a', 'b']} />)

    const stack = container.firstElementChild!
    expect(Array.from(stack.children).map((el) => el.tagName)).toEqual(['DIV', 'DIV'])
    for (const wrapper of Array.from(stack.children)) {
      expect(wrapper.querySelector('[data-session-id]')).not.toBeNull()
    }
  })

  it('renders nothing for an empty list', () => {
    const { container } = render(<InlineTerminals sessionIds={[]} />)
    expect(container).toBeEmptyDOMElement()
  })
})
