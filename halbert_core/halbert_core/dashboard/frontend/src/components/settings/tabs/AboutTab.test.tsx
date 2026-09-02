// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * AboutTab (FE-15): a pure presentation surface — version text, the two
 * developer-tools/legal-notices buttons wired to their callback props, and
 * the two external links. No network, no context. Locks down that the
 * callbacks actually fire and the links point where they say they do.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AboutTab } from './AboutTab'

function renderTab() {
  const onOpenComponentLibrary = vi.fn()
  const onOpenLegalNotices = vi.fn()
  render(
    <AboutTab
      onOpenComponentLibrary={onOpenComponentLibrary}
      onOpenLegalNotices={onOpenLegalNotices}
    />,
  )
  return { onOpenComponentLibrary, onOpenLegalNotices }
}

describe('AboutTab', () => {
  it('renders the version and section headings', () => {
    renderTab()
    expect(screen.getByText('About Halbert')).toBeTruthy()
    expect(screen.getByText('Development Build')).toBeTruthy()
    expect(screen.getByText('Developer Tools')).toBeTruthy()
    expect(screen.getByText('Legal & Third-Party Notices')).toBeTruthy()
  })

  it('clicking View Component Library calls onOpenComponentLibrary', async () => {
    const user = userEvent.setup()
    const { onOpenComponentLibrary, onOpenLegalNotices } = renderTab()
    await user.click(screen.getByRole('button', { name: /view component library/i }))
    expect(onOpenComponentLibrary).toHaveBeenCalledTimes(1)
    expect(onOpenLegalNotices).not.toHaveBeenCalled()
  })

  it('clicking View Legal Notices calls onOpenLegalNotices', async () => {
    const user = userEvent.setup()
    const { onOpenComponentLibrary, onOpenLegalNotices } = renderTab()
    await user.click(screen.getByRole('button', { name: /view legal notices/i }))
    expect(onOpenLegalNotices).toHaveBeenCalledTimes(1)
    expect(onOpenComponentLibrary).not.toHaveBeenCalled()
  })

  it('the GitHub and Documentation links open in a new tab safely', () => {
    renderTab()
    const github = screen.getByRole('link', { name: /github/i })
    expect(github).toHaveAttribute('href', 'https://github.com')
    expect(github).toHaveAttribute('target', '_blank')
    expect(github).toHaveAttribute('rel', 'noopener noreferrer')

    const docs = screen.getByRole('link', { name: /documentation/i })
    expect(docs).toHaveAttribute('href', '/docs')
    expect(docs).toHaveAttribute('target', '_blank')
    expect(docs).toHaveAttribute('rel', 'noopener noreferrer')
  })
})
