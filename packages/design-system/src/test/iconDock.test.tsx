// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { IconDock, type IconDockItem } from '../surfaces/IconDock'
import { GitHubIcon, StorybookIcon, XIcon, RedditIcon } from '../icons/brands'

const marketing: IconDockItem[] = [
  { id: 'github', label: 'GitHub', icon: GitHubIcon, href: 'https://github.com/EricBintner/Halbert' },
  { id: 'storybook', label: 'Storybook', icon: StorybookIcon, href: 'https://storybook.halbert.computer' },
  { id: 'x', label: 'X', icon: XIcon, disabled: true },
  { id: 'reddit', label: 'Reddit', icon: RedditIcon, disabled: true },
]

describe('IconDock', () => {
  it('is a navigation landmark named by its label', () => {
    render(<IconDock items={marketing} label="Elsewhere" />)
    expect(screen.getByRole('navigation', { name: 'Elsewhere' })).toBeInTheDocument()
  })

  it('names every control by its label, not its glyph', () => {
    render(<IconDock items={marketing} />)
    expect(screen.getByRole('link', { name: 'GitHub' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Storybook' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'X' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Reddit' })).toBeInTheDocument()
  })

  it('opens absolute links in a new tab without leaking the opener', () => {
    render(<IconDock items={marketing} />)
    const link = screen.getByRole('link', { name: 'GitHub' })
    expect(link).toHaveAttribute('href', 'https://github.com/EricBintner/Halbert')
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')
  })

  it('keeps relative links in the same tab', () => {
    render(<IconDock items={[{ id: 'docs', label: 'Docs', icon: GitHubIcon, href: '/docs' }]} />)
    const link = screen.getByRole('link', { name: 'Docs' })
    expect(link).not.toHaveAttribute('target')
    expect(link).not.toHaveAttribute('rel')
  })

  it('renders a disabled item as a disabled button with the coming-soon tooltip, out of the tab order', async () => {
    render(<IconDock items={marketing} />)
    const x = screen.getByRole('button', { name: 'X' })
    expect(x).toBeDisabled()
    expect(x).toHaveAttribute('title', 'X · coming soon')

    await userEvent.tab()
    expect(screen.getByRole('link', { name: 'GitHub' })).toHaveFocus()
    await userEvent.tab()
    expect(screen.getByRole('link', { name: 'Storybook' })).toHaveFocus()
    await userEvent.tab()
    expect(x).not.toHaveFocus()
  })

  it('fires the click handler of an action item', async () => {
    const onClick = vi.fn()
    render(<IconDock items={[{ id: 'go', label: 'Go', icon: GitHubIcon, onClick }]} />)
    await userEvent.click(screen.getByRole('button', { name: 'Go' }))
    expect(onClick).toHaveBeenCalledTimes(1)
  })

  it('treats an item with no target as a placeholder', () => {
    render(<IconDock items={[{ id: 'later', label: 'Later', icon: XIcon }]} />)
    expect(screen.getByRole('button', { name: 'Later' })).toBeDisabled()
  })

  it('stacks when vertical', () => {
    render(<IconDock items={marketing} orientation="vertical" />)
    expect(screen.getByRole('navigation')).toHaveClass('hb-dock', 'hb-dock--vertical')
  })

  it('hides the glyph from assistive tech', () => {
    render(<IconDock items={marketing} />)
    const link = screen.getByRole('link', { name: 'GitHub' })
    expect(link.querySelector('[aria-hidden="true"]')).not.toBeNull()
  })
})
