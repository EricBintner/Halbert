// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * A reloaded turn renders the same as it did live.
 *
 * Live, a fast command settles into `$ smbstatus · exit 1 · 0.3s`. The stored
 * turn carried only the tool block, so after a refresh the same turn came
 * back as a generic card with the raw result underneath. The server now joins
 * the terminal block's result onto the tool block by execution id; this is
 * the frontend half of that join.
 */

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { blockFromServer } from '../../types/timeline'
import { executionFromBlock } from './Timeline'
import { ToolExecutionCard } from './ToolExecutionCard'

const fromServer = {
  tool: 'run_command',
  args: { command: 'smbstatus' },
  result: 'Exit code 1\nno shares',
  exit: 1,
  execution_id: 'exec-1',
  status: 'success',
  block_id: 'blk-1',
  duration: 0.34,
  output_head: 'no shares',
  output_tail: 'no shares',
}

describe('a stored block keeps its terminal result', () => {
  it('parses the hydrated fields off the wire', () => {
    const block = blockFromServer(fromServer)

    expect(block.blockId).toBe('blk-1')
    expect(block.duration).toBe(0.34)
    expect(block.outputHead).toBe('no shares')
    expect(block.outputTail).toBe('no shares')
  })

  it('leaves a block the server did not hydrate alone', () => {
    const block = blockFromServer({
      tool: 'read_file', args: { path: '/etc/fstab' }, result: 'x', execution_id: 'e1',
    })

    expect(block.blockId).toBeUndefined()
    expect(block.duration).toBeUndefined()
  })

  it('carries them onto the execution the card renders', () => {
    const exec = executionFromBlock(blockFromServer(fromServer), 'fallback')

    expect(exec.blockId).toBe('blk-1')
    expect(exec.blockExitCode).toBe(1)
    expect(exec.blockDuration).toBe(0.34)
    expect(exec.blockOutputHead).toBe('no shares')
  })

  it('renders as the one-liner it was live, not as a generic card', () => {
    render(
      <ToolExecutionCard execution={executionFromBlock(blockFromServer(fromServer), 'f')} />
    )

    expect(screen.getByText(/\$ smbstatus · exit 1/)).toBeTruthy()
    expect(screen.getByText(/0\.3s/)).toBeTruthy()
    expect(screen.queryByText('run_command')).toBeNull()
  })

  it('a still-running block reports no duration rather than zero', () => {
    const block = blockFromServer({ ...fromServer, duration: null, exit: null })
    const exec = executionFromBlock(block, 'f')

    // 0.0s would read as "it finished instantly".
    expect(exec.blockDuration).toBeUndefined()
  })
})
