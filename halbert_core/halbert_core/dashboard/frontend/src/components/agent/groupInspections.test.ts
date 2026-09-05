// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * A run of inspection calls is one line, not six boxes.
 *
 * Five reads and a grep before one command produced six stacked bordered
 * rows in the feed, each one a heading over an empty body. The reads are how
 * Halbert got to the answer, not the answer.
 *
 * What may NOT be folded away is the point of the rule: anything that failed,
 * anything that ran long enough to be promoted, anything that wrote, and
 * anything an admin asked to forget.
 */

import { describe, it, expect } from 'vitest'
import { groupInspections, INSPECTION_TOOLS } from './groupInspections'
import type { ToolExecution } from '../../hooks/useAgentStream'

const ex = (over: Partial<ToolExecution> & { executionId: string }): ToolExecution => ({
  tool: 'read_file',
  args: { path: '/etc/fstab' },
  status: 'success',
  ...over,
})

const ids = (rows: ReturnType<typeof groupInspections>) =>
  rows.map((r) => (r.kind === 'group' ? r.items.map((i) => i.executionId) : r.item.executionId))

describe('groupInspections', () => {
  it('leaves a lone inspection call alone', () => {
    // One card is not a wall. Folding it would hide a step and save nothing.
    const rows = groupInspections([ex({ executionId: 'a' })])
    expect(rows).toHaveLength(1)
    expect(rows[0].kind).toBe('single')
  })

  it('folds a run of consecutive inspections into one row', () => {
    const rows = groupInspections([
      ex({ executionId: 'a' }),
      ex({ executionId: 'b', tool: 'list_directory' }),
      ex({ executionId: 'c', tool: 'recall_memory' }),
    ])

    expect(rows).toHaveLength(1)
    expect(rows[0].kind).toBe('group')
    expect(ids(rows)).toEqual([['a', 'b', 'c']])
  })

  it('a failure breaks the run and stands on its own', () => {
    const rows = groupInspections([
      ex({ executionId: 'a' }),
      ex({ executionId: 'b', status: 'error', error: 'no such file' }),
      ex({ executionId: 'c' }),
    ])

    // A 40ms read that failed is more interesting than a 4s one that did not.
    expect(ids(rows)).toEqual(['a', 'b', 'c'])
  })

  it('a command that was promoted is never folded away', () => {
    const rows = groupInspections([
      ex({ executionId: 'a' }),
      ex({ executionId: 'b', tool: 'run_command', args: { command: 'npm run build' },
           blockId: 'blk-1', blockDuration: 9.5, blockExitCode: 0 }),
      ex({ executionId: 'c' }),
    ])

    expect(ids(rows)).toEqual(['a', 'b', 'c'])
  })

  it('a quiet successful command folds in with the reads around it', () => {
    const rows = groupInspections([
      ex({ executionId: 'a' }),
      ex({ executionId: 'b', tool: 'run_command', args: { command: 'id' },
           blockId: 'blk-1', blockDuration: 0.1, blockExitCode: 0,
           blockReadOnly: true }),
    ])

    expect(rows).toHaveLength(1)
    expect(ids(rows)).toEqual([['a', 'b']])
  })

  it('a command that failed quietly is still not folded', () => {
    const rows = groupInspections([
      ex({ executionId: 'a' }),
      ex({ executionId: 'b', tool: 'run_command', args: { command: 'id' },
           blockId: 'blk-1', blockDuration: 0.1, blockExitCode: 1,
           blockReadOnly: true }),
    ])

    expect(ids(rows)).toEqual(['a', 'b'])
  })

  it('a command with no block yet is not folded', () => {
    // Still running, or the pool fell back to the subprocess path. Either way
    // nothing has said it was quick, and assuming it was would hide a command
    // that is still going.
    const rows = groupInspections([
      ex({ executionId: 'a' }),
      ex({ executionId: 'b', tool: 'run_command', args: { command: 'sleep 100' } }),
    ])

    expect(ids(rows)).toEqual(['a', 'b'])
  })

  it('a write is never an inspection', () => {
    const rows = groupInspections([
      ex({ executionId: 'a' }),
      ex({ executionId: 'b', tool: 'write_file', args: { path: '/etc/hosts' } }),
      ex({ executionId: 'c' }),
    ])

    expect(ids(rows)).toEqual(['a', 'b', 'c'])
  })

  it('a running inspection is not folded while it runs', () => {
    // The group is a summary of what happened. A call still in flight has not
    // happened yet, and burying it would hide the only thing moving.
    const rows = groupInspections([
      ex({ executionId: 'a' }),
      ex({ executionId: 'b', status: 'running' }),
    ])

    expect(ids(rows)).toEqual(['a', 'b'])
  })

  it('splits into several groups around what breaks them', () => {
    const rows = groupInspections([
      ex({ executionId: 'a' }), ex({ executionId: 'b' }),
      ex({ executionId: 'x', tool: 'write_file' }),
      ex({ executionId: 'c' }), ex({ executionId: 'd' }),
    ])

    expect(ids(rows)).toEqual([['a', 'b'], 'x', ['c', 'd']])
  })

  it('every tool it folds is a tool that exists', () => {
    // The handoff's tier list named grep_search, list_dir, check_drift and
    // systemctl_action — Cursor's vocabulary, present in neither Halbert nor
    // the OSS repo it cited. Half the map would never have matched.
    const real = new Set([
      'read_file', 'list_directory', 'recall_memory', 'recall_thread',
      'read_log_tail', 'get_service_status', 'list_running_services',
      'check_process', 'check_disk_space', 'get_system_load',
      'get_network_info', 'get_cpu_info', 'get_memory_info', 'get_disk_usage',
      'get_process_list', 'web_search', 'terminal_blocks', 'run_command',
      'self_knowledge_all', 'self_conversations',
    ])
    for (const tool of INSPECTION_TOOLS) {
      expect(real.has(tool), `${tool} is not a registered Halbert tool`).toBe(true)
    }
  })

  // What the command DID, not what it cost. Every one of these returns in
  // milliseconds with exit 0, and every one of them was folding into a row
  // headed "Looked at" — over a docstring in this very module saying an
  // action is not an inspection whatever it cost.
  const DESTRUCTIVE = [
    'rm -rf /tmp/victim',
    'echo pwned > /tmp/wiped.txt',
    'git push --force',
    'systemctl stop nginx',
    'mkfs.ext4 /dev/sda1',
  ]

  it.each(DESTRUCTIVE)('a fast successful write is never folded: %s', (command) => {
    const rows = groupInspections([
      ex({ executionId: 'a' }),
      ex({ executionId: 'b', tool: 'run_command', args: { command },
           blockId: 'blk-1', blockDuration: 0.05, blockExitCode: 0,
           blockReadOnly: false }),
      ex({ executionId: 'c' }),
    ])

    // The write stands alone, between the two reads. Asserted as the whole
    // shape rather than "b is somewhere", so a fold that merged everything
    // into one row could not pass it.
    expect(ids(rows)).toEqual(['a', 'b', 'c'])
  })

  it('a command nobody classified is not folded', () => {
    // Undefined is not "no". An older row, or a fallback to the subprocess
    // path, has no verdict — and folding on the absence of a judgement is
    // how the destructive cases above got in.
    const rows = groupInspections([
      ex({ executionId: 'a' }),
      ex({ executionId: 'b', tool: 'run_command', args: { command: 'id' },
           blockId: 'blk-1', blockDuration: 0.1, blockExitCode: 0 }),
    ])

    expect(ids(rows)).toEqual(['a', 'b'])
  })
})
