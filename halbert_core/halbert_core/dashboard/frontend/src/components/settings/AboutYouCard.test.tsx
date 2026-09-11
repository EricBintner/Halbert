// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * "What I remember about you" — the surface a person retracts things from.
 *
 * The assertions that matter here are the ones about what is NOT shown and
 * what is NOT claimed: no confidence number, no single "delete" button
 * standing for two different verbs, and never "nothing is recorded about
 * you" when the truth is that the store could not be read.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AboutYouCard } from './AboutYouCard'

const LIMITS =
  'This removes the interest from the persona memory store … It does NOT ' +
  'reach: the conversation messages the interest was learned from …'

const STATED = {
  memory_id: 'interest_vintage-thinkpads',
  topic: 'vintage thinkpads',
  learned: 'You told me',
  when: '2026-09-10',
  reason: 'remember that I collect vintage thinkpads',
  status: 'active',
  forgotten: false,
}

const STOPPED = { ...STATED, status: 'forget_requested', forgotten: true }

function ok(items: unknown[], status = 'ok') {
  return { ok: true, json: async () => ({ status, items, count: items.length, limits: LIMITS }) }
}

function report(extra: Record<string, unknown> = {}) {
  return {
    ok: true,
    json: async () => ({ complete: true, memory: true, observations: 1, errors: [], limits: LIMITS, ...extra }),
  }
}

let fetchMock: ReturnType<typeof vi.fn>

beforeEach(() => {
  fetchMock = vi.fn().mockResolvedValue(ok([STATED]))
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('the list', () => {
  it('shows what is remembered and how it was learned', async () => {
    render(<AboutYouCard />)
    expect(await screen.findByText('vintage thinkpads')).toBeInTheDocument()
    expect(screen.getByText(/You told me/)).toBeInTheDocument()
  })

  it("quotes the person's own words", async () => {
    render(<AboutYouCard />)
    expect(
      await screen.findByText(/remember that I collect vintage thinkpads/),
    ).toBeInTheDocument()
  })

  it('shows no confidence number', async () => {
    // The engine derives one from provenance. Showing it invites a person to
    // weigh something the system cannot justify numerically.
    render(<AboutYouCard />)
    await screen.findByText('vintage thinkpads')
    expect(document.body.textContent).not.toMatch(/0\.\d|\d+%/)
  })

  it('says nothing is recorded when the list is genuinely empty', async () => {
    fetchMock.mockResolvedValue(ok([]))
    render(<AboutYouCard />)
    expect(await screen.findByText(/Nothing is recorded about you/)).toBeInTheDocument()
  })

  it('does NOT say that when the store could not be read', async () => {
    // An unreadable store is not an empty store. "Nothing is recorded about
    // you" is a claim, and making it falsely is the one thing this surface
    // must never do.
    fetchMock.mockResolvedValue(ok([], 'unavailable'))
    render(<AboutYouCard />)
    expect(await screen.findByText(/could not read/)).toBeInTheDocument()
  })

  it('reports a failed fetch rather than showing an empty list', async () => {
    fetchMock.mockRejectedValue(new Error('offline'))
    render(<AboutYouCard />)
    expect(await screen.findByText(/could not read/)).toBeInTheDocument()
    expect(screen.queryByText(/Nothing is recorded about you/)).toBeNull()
  })
})

describe('the two verbs', () => {
  it('offers them under different names', async () => {
    // RQ-6. One button labelled "delete" doing the reversible thing is a
    // lie; doing the irreversible thing without saying so is worse.
    render(<AboutYouCard />)
    expect(await screen.findByRole('button', { name: 'Stop using this' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Forget' })).toBeInTheDocument()
  })

  it('stop-using posts to its own endpoint and needs no confirmation', async () => {
    render(<AboutYouCard />)
    await userEvent.click(await screen.findByRole('button', { name: 'Stop using this' }))
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/interest_vintage-thinkpads/stop-using'),
        expect.objectContaining({ method: 'POST' }),
      )
    })
  })

  it('forget asks first, and does not post until confirmed', async () => {
    render(<AboutYouCard />)
    await userEvent.click(await screen.findByRole('button', { name: 'Forget' }))
    expect(
      fetchMock.mock.calls.filter((c) => String(c[0]).includes('/forget')),
    ).toHaveLength(0)
    expect(await screen.findByText(/Forget .vintage thinkpads/)).toBeInTheDocument()
  })

  it('the confirmation states what erasure does not reach', async () => {
    // The four-whys law: forgotten with a statement of reach, and a person
    // reads it before the click, not after.
    render(<AboutYouCard />)
    await userEvent.click(await screen.findByRole('button', { name: 'Forget' }))
    expect(await screen.findByText(/does NOT.*reach/s)).toBeInTheDocument()
  })

  it('the confirmation points at the reversible verb, by name', async () => {
    // Named, not gestured at. "Choose the other button" would be a weaker
    // sentence and RQ-6 is specifically that the two verbs are named apart.
    // Queried as a description rather than by text, because the row button
    // carries the same words -- which is the point.
    render(<AboutYouCard />)
    await userEvent.click(await screen.findByRole('button', { name: 'Forget' }))
    const dialog = await screen.findByText(/This destroys the record/)
    expect(dialog.textContent).toMatch(/Stop using this/)
  })

  it('confirming posts to forget', async () => {
    fetchMock.mockImplementation((_url: string, init?: RequestInit) =>
      Promise.resolve(init?.method === 'POST' ? report() : ok([STATED])),
    )
    render(<AboutYouCard />)
    await userEvent.click(await screen.findByRole('button', { name: 'Forget' }))
    await userEvent.click(await screen.findByRole('button', { name: 'Forget it' }))
    await waitFor(() => {
      expect(
        fetchMock.mock.calls.filter((c) => String(c[0]).includes('/forget')),
      ).toHaveLength(1)
    })
  })

  it('shows the reach again after the erase', async () => {
    fetchMock.mockImplementation((_url: string, init?: RequestInit) =>
      Promise.resolve(init?.method === 'POST' ? report() : ok([STATED])),
    )
    render(<AboutYouCard />)
    await userEvent.click(await screen.findByRole('button', { name: 'Forget' }))
    await userEvent.click(await screen.findByRole('button', { name: 'Forget it' }))
    expect(await screen.findByText(/Forgotten\./)).toBeInTheDocument()
  })

  it('says so when a verb could not finish', async () => {
    // Never a silent partial: a clean tick over a job half done is the
    // overclaim this whole mechanism exists to avoid.
    fetchMock.mockImplementation((_url: string, init?: RequestInit) =>
      Promise.resolve(
        init?.method === 'POST'
          ? report({ complete: false, errors: ['observations: disk full'] })
          : ok([STATED]),
      ),
    )
    render(<AboutYouCard />)
    await userEvent.click(await screen.findByRole('button', { name: 'Stop using this' }))
    expect(await screen.findByText(/did not finish.*disk full/)).toBeInTheDocument()
  })
})

describe('show forgotten', () => {
  it('asks the API for them', async () => {
    render(<AboutYouCard />)
    await screen.findByText('vintage thinkpads')
    await userEvent.click(screen.getByRole('button', { name: 'Show forgotten' }))
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('include_forgotten=true'),
      )
    })
  })

  it('offers "Remember again" on a stopped row, not "Stop using this"', async () => {
    fetchMock.mockResolvedValue(ok([STOPPED]))
    render(<AboutYouCard />)
    expect(await screen.findByRole('button', { name: 'Remember again' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Stop using this' })).toBeNull()
  })

  it('remember-again posts to its own endpoint', async () => {
    fetchMock.mockImplementation((_url: string, init?: RequestInit) =>
      Promise.resolve(init?.method === 'POST' ? report() : ok([STOPPED])),
    )
    render(<AboutYouCard />)
    await userEvent.click(await screen.findByRole('button', { name: 'Remember again' }))
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/remember-again'),
        expect.objectContaining({ method: 'POST' }),
      )
    })
  })
})
