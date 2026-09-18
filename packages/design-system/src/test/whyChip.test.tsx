// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { WhyChip, type ProvenanceRef } from '../primitives/WhyChip'

const refs: ProvenanceRef[] = [
  { type: 'log_cursor', ref: 'journal:2026-07-14T04:00Z', label: 'Journal window' },
  { type: 'path_lines', ref: '/etc/ssh/sshd_config.d/50-custom.conf:3', label: 'Config line' },
  { type: 'memory_id', ref: 'mem-0042', label: 'Recalled note', url: 'https://example.com/mem-0042' },
]

afterEach(() => vi.restoreAllMocks())

describe('WhyChip', () => {
  it('renders nothing when there is no provenance to cite', () => {
    const { container } = render(<WhyChip provenance={[]} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('names the trigger by how many sources it carries', () => {
    render(<WhyChip provenance={refs} />)
    expect(screen.getByRole('button', { name: /3 sources/i })).toBeInTheDocument()
  })

  it('uses the singular for one source', () => {
    render(<WhyChip provenance={[refs[0]]} />)
    expect(screen.getByRole('button', { name: /^1 source$/i })).toBeInTheDocument()
  })

  it('reports whether the popover is open', async () => {
    render(<WhyChip provenance={refs} />)
    const trigger = screen.getByRole('button', { name: /3 sources/i })

    expect(trigger).toHaveAttribute('aria-expanded', 'false')
    await userEvent.click(trigger)
    expect(trigger).toHaveAttribute('aria-expanded', 'true')
  })

  it('lists every ref by its label once opened', async () => {
    render(<WhyChip provenance={refs} />)
    await userEvent.click(screen.getByRole('button', { name: /3 sources/i }))

    expect(screen.getByText('Evidence and sources')).toBeInTheDocument()
    for (const ref of refs) {
      expect(screen.getByText(ref.label)).toBeInTheDocument()
      expect(screen.getByText(ref.ref)).toBeInTheDocument()
    }
  })

  it('falls back to the raw ref when a label is missing', async () => {
    render(<WhyChip provenance={[{ type: 'snapshot_id', ref: 'SNAP-20260714-02', label: '' }]} />)
    await userEvent.click(screen.getByRole('button', { name: /1 source/i }))
    expect(screen.getAllByText('SNAP-20260714-02').length).toBeGreaterThan(0)
  })

  it('hands an expandable ref to onExpand and closes', async () => {
    const onExpand = vi.fn()
    render(<WhyChip provenance={refs} onExpand={onExpand} />)
    await userEvent.click(screen.getByRole('button', { name: /3 sources/i }))
    await userEvent.click(screen.getByText('Config line'))

    expect(onExpand).toHaveBeenCalledWith(refs[1])
    expect(screen.queryByText('Evidence and sources')).not.toBeInTheDocument()
  })

  it('opens an unexpandable ref by url without handing over the opener', async () => {
    const open = vi.spyOn(window, 'open').mockImplementation(() => null)
    render(<WhyChip provenance={refs} onExpand={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: /3 sources/i }))
    await userEvent.click(screen.getByText('Recalled note'))

    expect(open).toHaveBeenCalledWith('https://example.com/mem-0042', '_blank', 'noopener,noreferrer')
  })

  it('closes on Escape, so the popover is not a keyboard trap', async () => {
    render(<WhyChip provenance={refs} />)
    await userEvent.click(screen.getByRole('button', { name: /3 sources/i }))
    expect(screen.getByText('Evidence and sources')).toBeInTheDocument()

    await userEvent.keyboard('{Escape}')
    expect(screen.queryByText('Evidence and sources')).not.toBeInTheDocument()
  })

  it('closes when the backdrop is clicked', async () => {
    render(<WhyChip provenance={refs} />)
    const trigger = screen.getByRole('button', { name: /3 sources/i })
    await userEvent.click(trigger)
    await userEvent.click(trigger)
    expect(screen.queryByText('Evidence and sources')).not.toBeInTheDocument()
  })

  it('keeps the count glyph out of the accessibility tree', () => {
    render(<WhyChip provenance={refs} />)
    const trigger = screen.getByRole('button', { name: /3 sources/i })
    expect(trigger.querySelector('svg[aria-hidden="true"]')).not.toBeNull()
  })
})
