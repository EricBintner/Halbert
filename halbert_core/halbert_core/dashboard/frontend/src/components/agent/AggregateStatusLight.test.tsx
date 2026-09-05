// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * One light for "is the machine doing anything".
 *
 * With the tasks column mounted, a long-running command is visible only when
 * the right column is open. The aggregate light is how the machine says
 * something is running when you are not looking at it — the last row of
 * TERM-1.
 */

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { AggregateStatusLight, worstState } from './AggregateStatusLight'
import type { TaskCardData } from './TasksColumn'

const task = (over: Partial<TaskCardData> = {}): TaskCardData => ({
  taskId: 't', title: 'npm run build', threadTopic: '', state: 'running',
  blockId: 'b', threadId: 'b', ...over,
})

describe('worstState', () => {
  it('is nothing when nothing is running', () => {
    expect(worstState([])).toBeNull()
  })

  it('reports running when something is', () => {
    expect(worstState([task()])).toBe('running')
  })

  it('lets a task waiting on input outrank one merely running', () => {
    // A command that needs an answer is the one thing the reader has to act
    // on; a command that is simply working needs nothing from them.
    expect(worstState([task(), task({ state: 'needs_attention' })])).toBe('needs_attention')
  })

  it('lets an error outrank a running task', () => {
    expect(worstState([task(), task({ state: 'error' })])).toBe('error')
  })

  it('puts needs_attention above error', () => {
    // Both want the reader, but only one is waiting on them right now.
    expect(worstState([task({ state: 'error' }), task({ state: 'needs_attention' })]))
      .toBe('needs_attention')
  })

  it('ignores finished tasks', () => {
    expect(worstState([task({ state: 'done_unseen' })])).toBeNull()
  })
})

describe('AggregateStatusLight', () => {
  it('renders nothing when nothing is running', () => {
    const { container } = render(<AggregateStatusLight tasks={[]} />)
    // Not a dim placeholder: a permanent grey dot in the top bar is
    // furniture, and it trains the eye to stop seeing the spot.
    expect(container.firstChild).toBeNull()
  })

  it('says how many, so one light can stand for several', () => {
    render(<AggregateStatusLight tasks={[task({ taskId: 'a' }), task({ taskId: 'b' })]} />)
    expect(screen.getByText('2')).toBeTruthy()
  })

  it('does not put a count on a single task', () => {
    render(<AggregateStatusLight tasks={[task()]} />)
    expect(screen.queryByText('1')).toBeNull()
  })

  it('names what it is for, for anyone not looking at colour', () => {
    render(<AggregateStatusLight tasks={[task()]} />)
    expect(screen.getByLabelText(/1 task running/i)).toBeTruthy()
  })
})
