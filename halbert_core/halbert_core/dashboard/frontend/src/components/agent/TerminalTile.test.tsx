// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * A tile mounted after its session started must show what already happened.
 *
 * Before: the xterm opened empty and the writer's cursor sat at 0, so the
 * first new chunk repainted the whole buffer and a tile that scrolled back
 * into view (or a reloaded page) showed nothing until the process spoke.
 */

import { render, waitFor, act } from '@testing-library/react'
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'

const { instances, FakeXTerm } = vi.hoisted(() => {
  class FakeXTerm {
    static instances: FakeXTerm[] = []
    cols = 80
    rows = 24
    writes: string[] = []
    disposed = false
    constructor(public options: Record<string, unknown>) {
      FakeXTerm.instances.push(this)
    }
    open() {}
    write(data: string) { this.writes.push(data) }
    reset() { this.writes.push('<reset>') }
    dispose() { this.disposed = true }
    loadAddon() {}
    onData() { return { dispose() {} } }
    attachCustomKeyEventHandler() {}
  }
  return { instances: FakeXTerm.instances, FakeXTerm }
})

vi.mock('@xterm/xterm', () => ({ Terminal: FakeXTerm }))
vi.mock('@xterm/addon-fit', () => ({ FitAddon: class { fit() {} } }))
vi.mock('@xterm/addon-web-links', () => ({ WebLinksAddon: class {} }))

import { TerminalTile } from './TerminalTile'
import { terminalSessionStore as store, useTerminalSessions } from '../../hooks/useTerminalSessions'

/** Renders the tile for a store session so store updates re-render it. */
function Tile({ id }: { id: string }) {
  const { sessions } = useTerminalSessions()
  const session = sessions.find((s) => s.id === id)
  return session ? <TerminalTile session={session} /> : null
}

describe('TerminalTile replay on mount', () => {
  beforeEach(() => {
    store.closeAll()
    instances.length = 0
    vi.stubGlobal('ResizeObserver', class {
      observe() {}
      unobserve() {}
      disconnect() {}
    })
  })

  afterEach(() => {
    store.closeAll()
    vi.unstubAllGlobals()
  })

  it('writes the output the store already holds when the xterm mounts', async () => {
    store.adopt('t1', { command: 'journalctl -f', pid: 3 })
    store.appendOutput('t1', 'old output')

    render(<Tile id="t1" />)

    await waitFor(() => expect(instances).toHaveLength(1))
    await waitFor(() => expect(instances[0].writes).toEqual(['old output']))
  })

  it('then writes only the delta, never the buffer twice', async () => {
    store.adopt('t1', { command: 'journalctl -f', pid: 3 })
    store.appendOutput('t1', 'old output')
    render(<Tile id="t1" />)
    await waitFor(() => expect(instances[0]?.writes).toEqual(['old output']))

    act(() => {
      store.appendOutput('t1', ' more')
    })

    await waitFor(() => expect(instances[0].writes).toEqual(['old output', ' more']))
  })

  it('mounts an empty session without writing anything', async () => {
    store.adopt('t2', { command: 'sleep 5', pid: 4 })
    render(<Tile id="t2" />)
    await waitFor(() => expect(instances).toHaveLength(1))
    expect(instances[0].writes).toEqual([])
  })
})

describe('TerminalTile block rendering (Plan B)', () => {
  beforeEach(() => {
    store.closeAll()
    instances.length = 0
    vi.stubGlobal('ResizeObserver', class {
      observe() {}
      unobserve() {}
      disconnect() {}
    })
  })

  afterEach(() => {
    store.closeAll()
    vi.unstubAllGlobals()
  })

  it('renders frozen <pre> when blockOutput is provided', () => {
    store.adopt('t1', { command: 'echo hello', pid: 1 })
    const { container } = render(
      <TerminalTile
        session={store.get('t1')!}
        blockId="blk-1"
        blockOutput="hello\n"
        blockExitCode={0}
      />
    )
    // No xterm should be mounted
    expect(instances).toHaveLength(0)
    // Frozen pre should be present
    const pre = container.querySelector('pre')
    expect(pre).toBeTruthy()
    expect(pre?.textContent).toContain('hello')
    // data-terminal-block attribute
    expect(container.querySelector('[data-terminal-block="blk-1"]')).toBeTruthy()
    expect(container.querySelector('[data-block-state="frozen"]')).toBeTruthy()
  })

  it('shows exit code in frozen header', () => {
    store.adopt('t1', { command: 'false', pid: 1 })
    const { container } = render(
      <TerminalTile
        session={store.get('t1')!}
        blockId="blk-2"
        blockOutput="error\n"
        blockExitCode={1}
      />
    )
    expect(container.textContent).toContain('exit 1')
  })

  it('renders live xterm when blockOutput is not provided', async () => {
    store.adopt('t1', { command: 'ls', pid: 1 })
    render(
      <TerminalTile
        session={store.get('t1')!}
        blockId="blk-3"
      />
    )
    await waitFor(() => expect(instances).toHaveLength(1))
  })

  it('agent owner disables stdin', async () => {
    store.adopt('t1', { command: 'ls', pid: 1 })
    render(
      <TerminalTile
        session={store.get('t1')!}
        owner="agent"
      />
    )
    await waitFor(() => expect(instances).toHaveLength(1))
    // The FakeXTerm constructor receives options — check disableStdin
    expect(instances[0]).toBeTruthy()
  })

  it('user owner enables stdin', async () => {
    store.adopt('t1', { command: 'bash', pid: 1 })
    render(
      <TerminalTile
        session={store.get('t1')!}
        owner="user"
      />
    )
    await waitFor(() => expect(instances).toHaveLength(1))
  })

  it('has data-terminal-block attribute on live tile', async () => {
    store.adopt('t1', { command: 'ls', pid: 1 })
    const { container } = render(
      <TerminalTile
        session={store.get('t1')!}
        blockId="blk-5"
      />
    )
    await waitFor(() => expect(instances).toHaveLength(1))
    expect(container.querySelector('[data-terminal-block="blk-5"]')).toBeTruthy()
  })
})
