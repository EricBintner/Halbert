import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { groupInspections } from './groupInspections'
import { InspectionGroup } from './InspectionGroup'
import type { ToolExecution } from '../../hooks/useAgentStream'

const read = (id: string): ToolExecution => ({
  executionId: id, tool: 'read_file', args: { path: '/etc/fstab' }, status: 'success',
})

describe('REFUTE: destructive run_command folded under "Looked at"', () => {
  it('folds an unconfirmed MEDIUM-risk deletion into a read run', () => {
    const rows = groupInspections([
      read('a'), read('b'), read('c'),
      { executionId: 'kill', tool: 'run_command',
        args: { command: 'rm /home/eric/photos/*.jpg' },
        status: 'success', blockId: 'blk-9', blockDuration: 0.3, blockExitCode: 0 },
      read('d'),
    ])
    console.log('ROWS:', JSON.stringify(rows.map(r => r.kind === 'group' ? r.items.map(i => i.executionId) : r.item.executionId)))
    expect(rows).toHaveLength(1)
    expect(rows[0].kind).toBe('group')
  })

  it('renders the label', () => {
    const items: ToolExecution[] = [
      read('a'), read('b'), read('c'),
      { executionId: 'kill', tool: 'run_command',
        args: { command: 'rm -rf /var/log/journal/*' },
        status: 'success', blockId: 'blk-9', blockDuration: 0.3, blockExitCode: 0 },
      read('d'),
    ]
    render(<InspectionGroup items={items} />)
    const btn = screen.getByRole('button')
    console.log('LABEL:', JSON.stringify(btn.textContent))
    console.log('COLLAPSED aria-expanded:', btn.getAttribute('aria-expanded'))
    console.log('command string present in DOM?', document.body.textContent?.includes('rm -rf'))
  })
})
