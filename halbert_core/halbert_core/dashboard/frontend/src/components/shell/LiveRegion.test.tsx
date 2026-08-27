// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * Two live regions for the shell (design §11): a polite status region for
 * "Pulled in earlier work" / "New subject", and an assertive alert region
 * used for exactly one thing — blocked on approval. announce() is a
 * module-level function so a hook deep in the conversation can speak
 * without threading a callback through five components; each region clears
 * and re-sets so the same sentence said twice is announced twice.
 */

import { render, screen, waitFor, act } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { LiveRegion } from './LiveRegion'
import { announce, subscribeAnnouncements, lastAnnouncement, lastAlert } from '../../lib/announce'

describe('LiveRegion', () => {
  it('is a visually hidden polite status region', () => {
    render(<LiveRegion />)
    const region = screen.getByRole('status')
    expect(region).toHaveAttribute('aria-live', 'polite')
    expect(region).toHaveAttribute('aria-atomic', 'true')
    expect(region.className).toContain('sr-only')
    expect(region).toHaveTextContent('')
  })

  it('also has a visually hidden assertive alert region, empty by default', () => {
    render(<LiveRegion />)
    const alert = screen.getByRole('alert')
    expect(alert).toHaveAttribute('aria-live', 'assertive')
    expect(alert).toHaveAttribute('aria-atomic', 'true')
    expect(alert.className).toContain('sr-only')
    expect(alert).toHaveTextContent('')
  })

  it('routes an assertive announcement to the alert region only', async () => {
    render(<LiveRegion />)
    act(() => {
      announce('Waiting for your approval', { assertive: true })
    })
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Waiting for your approval'))
    expect(screen.getByRole('status')).toHaveTextContent('')
    expect(lastAlert()).toBe('Waiting for your approval')
  })

  it('speaks what announce() is given', async () => {
    render(<LiveRegion />)
    act(() => {
      announce('Pulled in earlier work: Samba share setup')
    })
    await waitFor(() =>
      expect(screen.getByRole('status')).toHaveTextContent('Pulled in earlier work: Samba share setup'),
    )
    expect(lastAnnouncement()).toBe('Pulled in earlier work: Samba share setup')
    expect(screen.getByRole('alert')).toHaveTextContent('')
  })

  it('re-announces an identical sentence by clearing first', async () => {
    render(<LiveRegion />)
    const seen: string[] = []
    const unsubscribe = subscribeAnnouncements((text) => seen.push(text))

    act(() => {
      announce('New subject')
    })
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('New subject'))
    act(() => {
      announce('New subject')
    })
    // The region empties between the two so assistive tech sees a change.
    expect(screen.getByRole('status')).toHaveTextContent('')
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('New subject'))

    expect(seen).toEqual(['New subject', 'New subject'])
    unsubscribe()
  })
})
