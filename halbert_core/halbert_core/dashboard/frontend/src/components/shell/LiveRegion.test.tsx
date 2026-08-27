// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * Two live regions for the shell (design §11): a polite status region for
 * "Pulled in earlier work" / "New subject", and an assertive alert region
 * used for exactly one thing — blocked on approval. announce() is a
 * module-level function so a hook deep in the conversation can speak
 * without threading a callback through five components; each region clears
 * and re-sets so the same sentence said twice is announced twice, and
 * queues so two sentences said at once are both heard.
 */

import { render, screen, waitFor, act } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { LiveRegion } from './LiveRegion'
import { announce, subscribeAnnouncements, lastAnnouncement, lastAlert } from '../../lib/announce'

/**
 * Everything the region ever held, in order, as a screen reader would see it
 * — one entry per content change, consecutive duplicates collapsed.
 *
 * Reading `textContent` after the fact cannot catch a sentence that was in
 * the region for 150ms and then replaced, which is exactly what these tests
 * are about; watching for mutations can.
 */
function transcriptOf(region: HTMLElement) {
  const said: string[] = []
  const observer = new MutationObserver(() => {
    const text = region.textContent ?? ''
    if (text !== said[said.length - 1]) said.push(text)
  })
  observer.observe(region, { childList: true, characterData: true, subtree: true })
  return { said, spoken: () => said.filter((t) => t !== ''), stop: () => observer.disconnect() }
}

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
    const transcript = transcriptOf(screen.getByRole('status'))

    act(() => {
      announce('New subject')
    })
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('New subject'))
    act(() => {
      announce('New subject')
    })
    await waitFor(() => expect(transcript.said).toHaveLength(3))

    // The region empties between the two so assistive tech sees a change.
    // Asserted over what the region actually held rather than by reading it
    // at one instant: the clear is now the first half of the second
    // announcement's turn, not a side effect of announce() itself.
    expect(transcript.said).toEqual(['New subject', '', 'New subject'])
    expect(seen).toEqual(['New subject', 'New subject'])
    transcript.stop()
    unsubscribe()
  })

  it('speaks both sentences when two arrive in the same tick', async () => {
    // What `/model` does every time: the note in the stream is announced from
    // the command handler, and the pill's switch announcement follows in the
    // same commit. A region that only remembers the latest sentence drops the
    // one the user can see on screen and reads the other, so the two disagree.
    render(<LiveRegion />)
    const transcript = transcriptOf(screen.getByRole('status'))

    act(() => {
      announce('Back to automatic routing.')
      announce('Routing automatically: the guide will answer the next turn.')
    })

    await waitFor(() => expect(transcript.spoken()).toHaveLength(2))
    expect(transcript.spoken()).toEqual([
      'Back to automatic routing.',
      'Routing automatically: the guide will answer the next turn.',
    ])
    transcript.stop()
  })

  it('keeps a burst from becoming a backlog, ending on the newest', async () => {
    // A queue that never drops turns a flurry into minutes of narration the
    // user has to sit through before hearing anything current. The cap is
    // four; the last sentence is the one describing the screen they are on,
    // so it is always among the survivors and always last.
    render(<LiveRegion />)
    const transcript = transcriptOf(screen.getByRole('status'))

    act(() => {
      for (let i = 1; i <= 9; i += 1) announce(`Sentence ${i}`)
    })

    await waitFor(() => expect(transcript.spoken()).toContain('Sentence 9'))
    const spoken = transcript.spoken()
    expect(spoken.length).toBeLessThanOrEqual(5)
    expect(spoken[spoken.length - 1]).toBe('Sentence 9')
    // In order, and no sentence read twice.
    expect([...spoken].sort()).toEqual([...spoken])
    transcript.stop()
  })

  it('queues the alert region separately from the status region', async () => {
    // One blocked-on-approval alert must not wait behind the commentary, and
    // must not be dropped by it either.
    render(<LiveRegion />)
    const status = transcriptOf(screen.getByRole('status'))
    const alert = transcriptOf(screen.getByRole('alert'))

    act(() => {
      announce('Pulled in earlier work: Samba share setup')
      announce('Waiting for your approval', { assertive: true })
    })

    await waitFor(() => expect(alert.spoken()).toEqual(['Waiting for your approval']))
    await waitFor(() =>
      expect(status.spoken()).toEqual(['Pulled in earlier work: Samba share setup']),
    )
    status.stop()
    alert.stop()
  })
})
