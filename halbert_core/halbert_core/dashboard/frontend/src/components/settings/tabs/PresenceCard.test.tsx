// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { PresenceCard } from './PresenceCard'

const rungs = {
  status: 'ok',
  rungs: [
    { level: 0, name: 'mute', says: "I'll only speak for what can't wait.", why: 'Nothing interrupts you.', classifiable: true, admits: [], channel: {} },
    { level: 3, name: 'morning', says: "I'll give you the morning.", why: 'The default.', classifiable: true, admits: [], channel: {} },
    { level: 6, name: 'recall', says: "I'll bring things back up.", why: 'Not lost.', classifiable: false, admits: [], channel: {} },
    { level: 10, name: 'think', says: "I'll talk when I have a thought.", why: 'Company, bounded.', classifiable: false, admits: [], channel: {} },
  ],
}
const preview = { status: 'ok', level: 3, days: 7, said: 2, shown: 1, held: 4, unclassified: 0, undated: 0, budget_per_day: 3, truncated: false, items: [] }

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => ({
    ok: true,
    json: async () => (String(url).includes('/presence/rungs') ? rungs : preview),
  })))
})

describe('PresenceCard', () => {
  it('renders the rungs as the primary control with their copy', async () => {
    render(<PresenceCard level={3} saving={false} onChange={() => {}} />)
    expect(await screen.findByText("I'll give you the morning.")).toBeTruthy()
    expect(screen.getByText('The default.')).toBeTruthy()
  })

  it('marks rungs nothing can yet be described as, and still lets them be chosen', async () => {
    render(<PresenceCard level={3} saving={false} onChange={() => {}} />)
    const recall = await screen.findByRole('button', { name: /recall/i })
    expect(recall.getAttribute('data-classifiable')).toBe('false')
  })

  it('choosing a rung saves its level', async () => {
    const onChange = vi.fn()
    render(<PresenceCard level={3} saving={false} onChange={onChange} />)
    fireEvent.click(await screen.findByRole('button', { name: /think/i }))
    expect(onChange).toHaveBeenCalledWith({ presence: 10 })
  })

  it('the fine adjust saves the exact level', async () => {
    const onChange = vi.fn()
    render(<PresenceCard level={3} saving={false} onChange={onChange} />)
    const slider = await screen.findByRole('slider')
    fireEvent.change(slider, { target: { value: '5' } })
    expect(onChange).toHaveBeenCalledWith({ presence: 5 })
  })

  it('shows the preview counts for the current level', async () => {
    render(<PresenceCard level={3} saving={false} onChange={() => {}} />)
    await waitFor(() => expect(screen.getByText(/said 2/i)).toBeTruthy())
    expect(screen.getByText(/shown 1/i)).toBeTruthy()
    expect(screen.getByText(/held 4/i)).toBeTruthy()
  })
})
