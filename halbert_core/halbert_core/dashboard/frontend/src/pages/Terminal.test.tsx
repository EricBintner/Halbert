// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * FE-15: Terminal.tsx (the AI-enhanced xterm.js terminal page) had zero
 * test coverage. xterm itself is mocked the same way TerminalTile.test.tsx
 * mocks it (a fake Terminal/FitAddon/WebLinksAddon) — jsdom has no canvas,
 * and the real xterm.js measures glyphs on one at construction time.
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'

const { instances, FakeXTerm } = vi.hoisted(() => {
  class FakeXTerm {
    static instances: FakeXTerm[] = []
    lines: string[] = []
    disposed = false
    constructor(public options: Record<string, unknown>) {
      FakeXTerm.instances.push(this)
    }
    open() {}
    writeln(data: string) { this.lines.push(data) }
    dispose() { this.disposed = true }
    loadAddon() {}
  }
  return { instances: FakeXTerm.instances, FakeXTerm }
})

vi.mock('@xterm/xterm', () => ({ Terminal: FakeXTerm }))
vi.mock('@xterm/addon-fit', () => ({ FitAddon: class { fit() {} } }))
vi.mock('@xterm/addon-web-links', () => ({ WebLinksAddon: class {} }))

import { Terminal } from './Terminal'

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response
}

function renderTerminal() {
  const calls: Array<{ url: string; init?: RequestInit }> = []
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url, init })
    return jsonResponse({ output: 'total 0', exit_code: 0 })
  })
  vi.stubGlobal('fetch', fetchMock)
  const utils = render(<Terminal />)
  return { ...utils, calls }
}

describe('Terminal page', () => {
  beforeEach(() => {
    instances.length = 0
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('mounts the xterm instance and shows Connected once the (simulated) connection completes', async () => {
    renderTerminal()
    await waitFor(() => expect(instances).toHaveLength(1))
    expect(await screen.findByText('● Connected')).toBeInTheDocument()
  })

  it('disposes the xterm instance on unmount', async () => {
    const { unmount } = renderTerminal()
    await waitFor(() => expect(instances).toHaveLength(1))
    unmount()
    expect(instances[0].disposed).toBe(true)
  })

  it('toggles the AI panel with the AI On/Off button', async () => {
    const user = userEvent.setup()
    renderTerminal()
    // The panel header is Halbert itself — never 'AI Assistant' or a persona name.
    expect(screen.getByText('Halbert')).toBeInTheDocument()
    expect(screen.queryByText('AI Assistant')).not.toBeInTheDocument()
    expect(screen.queryByText('Coder')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /AI On/i }))
    expect(screen.queryByText('Halbert')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /AI Off/i }))
    expect(screen.getByText('Halbert')).toBeInTheDocument()
  })

  it('previews a slash command in the AI panel as it is typed, without running it', async () => {
    const user = userEvent.setup()
    const { calls } = renderTerminal()
    await waitFor(() => expect(instances).toHaveLength(1))

    const input = screen.getByPlaceholderText(/Enter command/i)
    await user.type(input, '/explain')

    expect(await screen.findByText(/get an explanation of the last command output/i)).toBeInTheDocument()
    // Typing the preview must not itself execute anything.
    expect(calls).toHaveLength(0)
  })

  it('quick-action buttons fill the input without executing', async () => {
    const user = userEvent.setup()
    const { calls } = renderTerminal()
    const input = screen.getByPlaceholderText(/Enter command/i) as HTMLTextAreaElement

    await user.click(screen.getByRole('button', { name: '/dryrun' }))
    expect(input.value).toBe('/dryrun ')
    expect(calls).toHaveLength(0)
  })

  it('running a command POSTs to /api/terminal/exec and writes the output to the terminal', async () => {
    const user = userEvent.setup()
    const { calls } = renderTerminal()
    await waitFor(() => expect(instances).toHaveLength(1))

    const input = screen.getByPlaceholderText(/Enter command/i)
    await user.type(input, 'ls{Enter}')

    await waitFor(() => {
      const exec = calls.find((c) => c.url === '/api/terminal/exec')
      expect(exec).toBeTruthy()
      expect(JSON.parse(exec!.init!.body as string)).toEqual({ command: 'ls' })
    })

    await waitFor(() => expect(instances[0].lines).toContain('total 0'))
    // The input clears once the command is submitted.
    expect((input as HTMLTextAreaElement).value).toBe('')
  })

  it('a non-zero exit code offers to explain or fix the error', async () => {
    const user = userEvent.setup()
    const fetchMock = vi.fn(async () => jsonResponse({ output: 'not found', exit_code: 127 }))
    vi.stubGlobal('fetch', fetchMock)
    render(<Terminal />)
    await waitFor(() => expect(instances).toHaveLength(1))

    const input = screen.getByPlaceholderText(/Enter command/i)
    await user.type(input, 'nosuchcommand{Enter}')

    expect(await screen.findByRole('button', { name: /Explain Error/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Suggest Fix/i })).toBeInTheDocument()
  })

  it('the run button is disabled until there is a non-whitespace command', async () => {
    const user = userEvent.setup()
    const { container } = renderTerminal()
    // Icon-only submit button (Play/Loader2, no accessible name) — the
    // one <button className="px-4"> next to the input.
    const submit = container.querySelector('button.px-4') as HTMLButtonElement
    expect(submit).toBeTruthy()
    expect(submit).toBeDisabled()

    const input = screen.getByPlaceholderText(/Enter command/i)
    await user.type(input, '   ')
    expect(submit).toBeDisabled()

    await user.type(input, 'ls')
    expect(submit).not.toBeDisabled()
  })
})
