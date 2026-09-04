// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * The present tense, on its own layer.
 *
 * open-claude-code writes tool progress to stderr and transcript content to
 * stdout — two streams with genuinely different lifetimes. In a terminal the
 * progress scrolls past and is gone; the transcript is what you scroll back
 * through. That separation is what makes "quiet" safe: nothing is hidden
 * while it happens, it just does not earn a permanent row afterwards.
 *
 * Halbert rendered both in one layer, so a 200ms read deposited a bordered
 * box in the conversation forever. This is the other layer.
 */

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { StatusStrip, describeExecution } from './StatusStrip'
import type { ToolExecution } from '../../hooks/useAgentStream'

const running = (over: Partial<ToolExecution> = {}): ToolExecution => ({
  executionId: 'e1', tool: 'read_file', args: { path: '/etc/fstab' },
  status: 'running', ...over,
})

describe('describeExecution', () => {
  it('says what is being done, not which function is doing it', () => {
    expect(describeExecution(running())).toBe('Reading /etc/fstab')
  })

  it('shows a command as the command', () => {
    expect(describeExecution(running({ tool: 'run_command', args: { command: 'smbstatus' } })))
      .toBe('smbstatus')
  })

  it('names the directory being listed', () => {
    expect(describeExecution(running({ tool: 'list_directory', args: { path: '/srv' } })))
      .toBe('Listing /srv')
  })

  it('falls back to the tool name rather than inventing a sentence', () => {
    // A tool this does not know about gets its own name. Guessing a verb for
    // it would be a label that is wrong rather than plain.
    expect(describeExecution(running({ tool: 'gpu_architecture', args: {} })))
      .toBe('gpu_architecture')
  })
})

describe('StatusStrip', () => {
  it('shows nothing at all when nothing is running', () => {
    const { container } = render(<StatusStrip executions={[]} />)
    // Not an empty bar: a persistent empty row is furniture, and the strip
    // exists precisely to avoid leaving things behind.
    expect(container.firstChild).toBeNull()
  })

  it('shows nothing when every call has finished', () => {
    const { container } = render(
      <StatusStrip executions={[running({ status: 'success' })]} />
    )
    expect(container.firstChild).toBeNull()
  })

  it('says what is happening right now', () => {
    render(<StatusStrip executions={[running()]} />)
    expect(screen.getByText('Reading /etc/fstab')).toBeTruthy()
  })

  it('reports the newest call when several are in flight', () => {
    render(<StatusStrip executions={[
      running({ executionId: 'a', args: { path: '/etc/fstab' } }),
      running({ executionId: 'b', tool: 'run_command', args: { command: 'smbstatus' } }),
    ]} />)

    expect(screen.getByText('smbstatus')).toBeTruthy()
    expect(screen.queryByText('Reading /etc/fstab')).toBeNull()
  })

  it('says how many others are in flight behind it', () => {
    render(<StatusStrip executions={[
      running({ executionId: 'a' }),
      running({ executionId: 'b' }),
      running({ executionId: 'c' }),
    ]} />)

    expect(screen.getByText(/\+2 more/)).toBeTruthy()
  })

  it('is a polite live region, not an alert', () => {
    // It changes several times a turn. Announcing each one assertively would
    // interrupt a screen-reader user mid-sentence, repeatedly.
    render(<StatusStrip executions={[running()]} />)
    const region = screen.getByRole('status')
    expect(region.getAttribute('aria-live')).toBe('polite')
  })
})
