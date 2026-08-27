// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * A context chip is a control, not a styled div: it has a name a screen
 * reader can say, a separate remove button with its own name, a title that
 * says why it is here (the match terms), and the thread chip sits on the
 * telemetry tokens rather than a palette colour.
 */

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import { ContextBar, ContextPill, type ContextItem } from './ContextBar'

const THREAD: ContextItem = {
  id: 'thread:th-0',
  type: 'thread',
  label: 'pulled in: Samba share setup · 2026-07-14',
}

describe('ContextPill', () => {
  it('is a button with an accessible name', () => {
    render(<ContextPill item={THREAD} onClick={() => {}} />)
    expect(
      screen.getByRole('button', { name: 'earlier subject: pulled in: Samba share setup · 2026-07-14' }),
    ).toBeInTheDocument()
  })

  it('renders the thread chip on telemetry tokens, never a palette colour', () => {
    const { container } = render(<ContextPill item={THREAD} />)
    const pill = container.firstElementChild as HTMLElement
    expect(pill.className).toContain('bg-status-telemetry-bg')
    expect(pill.className).toContain('border-status-telemetry-line')
    expect(pill.className).not.toMatch(/\b(?:bg|text|border)-(?:blue|purple|violet|indigo|sky)-\d+\b/)
    expect(pill.className).toContain('text-[11px]')
  })

  it('shows its hint as the title — the chip\'s "why now" — and no title without one', () => {
    render(<ContextPill item={{ ...THREAD, hint: 'matched: samba, share' }} onClick={() => {}} />)
    expect(screen.getByRole('button', { name: /^earlier subject:/ })).toHaveAttribute('title', 'matched: samba, share')

    render(<ContextPill item={{ ...THREAD, id: 'thread:th-1' }} onClick={() => {}} />)
    const plain = screen.getAllByRole('button', { name: /^earlier subject:/ })[1]
    expect(plain).not.toHaveAttribute('title')
  })

  it('offers a sibling remove button with its own name', async () => {
    const onRemove = vi.fn()
    const onClick = vi.fn()
    render(<ContextPill item={THREAD} onRemove={onRemove} onClick={onClick} />)

    await userEvent.click(
      screen.getByRole('button', { name: 'Drop pulled in: Samba share setup · 2026-07-14 from context' }),
    )

    expect(onRemove).toHaveBeenCalledTimes(1)
    expect(onClick).not.toHaveBeenCalled()
  })
})

describe('ContextBar', () => {
  it('renders one pill per item and a labelled collapse control', async () => {
    const onRemoveItem = vi.fn()
    render(
      <ContextBar
        items={[THREAD, { id: 'f1', type: 'file', label: '/etc/samba/smb.conf', tokens: 120 }]}
        onRemoveItem={onRemoveItem}
      />,
    )

    expect(screen.getByRole('button', { name: /^earlier subject:/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'file: /etc/samba/smb.conf' })).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Drop /etc/samba/smb.conf from context' }))
    expect(onRemoveItem).toHaveBeenCalledWith('f1')

    const collapse = screen.getByRole('button', { name: 'Collapse context' })
    expect(collapse).toHaveAttribute('aria-expanded', 'true')
    await userEvent.click(collapse)
    expect(screen.getByRole('button', { name: 'Expand context' })).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByRole('button', { name: /^earlier subject:/ })).not.toBeInTheDocument()
  })
})
