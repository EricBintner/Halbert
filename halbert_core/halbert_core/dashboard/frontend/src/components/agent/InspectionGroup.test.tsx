// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { InspectionGroup, summarise } from './InspectionGroup'
import type { ToolExecution } from '../../hooks/useAgentStream'

const ex = (tool: string, id: string): ToolExecution => ({
  executionId: id, tool, args: { path: `/etc/${id}` }, status: 'success',
})

describe('summarise', () => {
  it('counts what was looked at, not which functions ran', () => {
    // "3 read_file, 2 recall_memory" is the machine's vocabulary. The reader
    // wants to know that three files and two memories were consulted.
    expect(summarise([ex('read_file', 'a'), ex('read_file', 'b'), ex('recall_memory', 'c')]))
      .toBe('2 files · 1 memory')
  })

  it('says memories, not memorys', () => {
    expect(summarise([ex('recall_memory', 'a'), ex('recall_memory', 'b')])).toBe('2 memories')
  })

  it('folds everything it has no better word for into checks', () => {
    expect(summarise([ex('check_disk_space', 'a'), ex('get_system_load', 'b')]))
      .toBe('2 checks')
  })
})

describe('InspectionGroup', () => {
  const items = [ex('read_file', 'a'), ex('read_file', 'b'), ex('recall_memory', 'c')]

  it('is one line until asked', () => {
    render(<InspectionGroup items={items} />)

    expect(screen.getByText(/Looked at 2 files · 1 memory/)).toBeTruthy()
    // The steps are still there; they are just not the loudest thing.
    expect(screen.queryByText('/etc/a')).toBeNull()
  })

  it('shows every step when opened', () => {
    render(<InspectionGroup items={items} />)
    fireEvent.click(screen.getByRole('button'))

    expect(screen.getAllByText('read_file')).toHaveLength(2)
    expect(screen.getByText('recall_memory')).toBeTruthy()
  })

  it('reports how many it is standing in for', () => {
    const { container } = render(<InspectionGroup items={items} />)
    expect(container.querySelector('[data-inspection-group="3"]')).toBeTruthy()
  })
})
