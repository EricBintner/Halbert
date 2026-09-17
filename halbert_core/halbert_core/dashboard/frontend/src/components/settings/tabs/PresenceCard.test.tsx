// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { PresenceCard } from './PresenceCard'

const rungs = {
  status: 'ok',
  rungs: [
    { level: 0, name: 'mute', says: "I'll only speak for what can't wait.", why: 'Nothing interrupts you.', classifiable: true },
    { level: 3, name: 'morning', says: "I'll give you the morning.", why: 'The default.', classifiable: true },
    { level: 6, name: 'recall', says: "I'll bring things back up.", why: 'Not lost.', classifiable: false },
    { level: 10, name: 'think', says: "I'll talk when I have a thought.", why: 'Company, bounded.', classifiable: false },
  ],
}
const preview = { status: 'ok', level: 3, days: 7, said: 2, shown: 1, held: 4, unclassified: 0, undated: 0, budget_per_day: 3, truncated: false, items: [] }

let fetchMock: ReturnType<typeof vi.fn>

beforeEach(() => {
  fetchMock = vi.fn(async (url: string) => ({
    ok: true,
    status: 200,
    json: async () => (String(url).includes('/presence/rungs') ? rungs : preview),
  }))
  vi.stubGlobal('fetch', fetchMock)
})

const lastPreviewUrl = () =>
  String(fetchMock.mock.calls.map((c) => String(c[0])).filter((u) => u.includes('/presence/preview')).pop() ?? '')

describe('PresenceCard', () => {
  it('renders the rungs as the primary control with their copy', async () => {
    render(<PresenceCard level={3} saving={false} onChange={() => {}} />)
    expect(await screen.findByText("I'll give you the morning.")).toBeTruthy()
    expect(screen.getByText('The default.')).toBeTruthy()
  })

  it('says on its face which rungs nothing can yet be described as, and still lets them be chosen', async () => {
    render(<PresenceCard level={3} saving={false} onChange={() => {}} />)
    const recall = await screen.findByRole('button', { name: /recall/i })
    expect(recall.textContent).toContain('(not yet)')
    expect(recall.hasAttribute('disabled')).toBe(false)
  })

  it('marks the saved rung for a screen reader, and keeps the mark there while another is hovered', async () => {
    render(<PresenceCard level={3} saving={false} onChange={() => {}} />)
    const morning = await screen.findByRole('button', { name: /morning/i })
    const think = await screen.findByRole('button', { name: /think/i })
    expect(morning.getAttribute('aria-pressed')).toBe('true')
    expect(think.getAttribute('aria-pressed')).toBe('false')

    fireEvent.mouseEnter(think)          // hovering asks about a rung; it does not select one
    expect(morning.getAttribute('aria-pressed')).toBe('true')
    expect(think.getAttribute('aria-pressed')).toBe('false')
  })

  it('choosing a rung saves its level', async () => {
    const onChange = vi.fn()
    render(<PresenceCard level={3} saving={false} onChange={onChange} />)
    fireEvent.click(await screen.findByRole('button', { name: /think/i }))
    expect(onChange).toHaveBeenCalledWith({ presence: 10 })
  })

  it('the fine adjust writes once, when the drag ends', async () => {
    const onChange = vi.fn()
    render(<PresenceCard level={3} saving={false} onChange={onChange} />)
    const slider = await screen.findByRole('slider')
    fireEvent.change(slider, { target: { value: '4' } })
    fireEvent.change(slider, { target: { value: '5' } })
    expect(onChange).not.toHaveBeenCalled()          // a drag is not a save
    fireEvent.pointerUp(slider)
    fireEvent.blur(slider)                           // the backstop must not write again
    expect(onChange).toHaveBeenCalledTimes(1)
    expect(onChange).toHaveBeenCalledWith({ presence: 5 })
  })

  it('snaps back when a save ends without changing the level', async () => {
    const { rerender } = render(<PresenceCard level={3} saving={false} onChange={() => {}} />)
    fireEvent.change(await screen.findByRole('slider'), { target: { value: '7' } })
    expect(screen.getByText(/Fine adjust: 7/)).toBeTruthy()

    rerender(<PresenceCard level={3} saving={true} onChange={() => {}} />)
    rerender(<PresenceCard level={3} saving={false} onChange={() => {}} />)   // refused: the level never arrived
    expect(screen.getByText(/Fine adjust: 3/)).toBeTruthy()
  })

  it('hovering a rung previews it without choosing it', async () => {
    const onChange = vi.fn()
    render(<PresenceCard level={3} saving={false} onChange={onChange} />)
    fireEvent.mouseEnter(await screen.findByRole('button', { name: /think/i }))
    await waitFor(() => expect(lastPreviewUrl()).toContain('level=10'))
    expect(onChange).not.toHaveBeenCalled()
  })

  it('reaches the preview from the keyboard too', async () => {
    render(<PresenceCard level={3} saving={false} onChange={() => {}} />)
    fireEvent.focus(await screen.findByRole('button', { name: /mute/i }))
    await waitFor(() => expect(lastPreviewUrl()).toContain('level=0'))
  })

  it('shows the preview counts for the current level, by name', async () => {
    render(<PresenceCard level={3} saving={false} onChange={() => {}} />)
    await waitFor(() => expect(screen.getByText(/at morning/i)).toBeTruthy())
    expect(screen.getByText(/said 2/i)).toBeTruthy()
    expect(screen.getByText(/shown 1/i)).toBeTruthy()
    expect(screen.getByText(/held 4/i)).toBeTruthy()
  })

  it('says so in its own words when it cannot read the log, and keeps the fine adjust', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 503, json: async () => ({}) })))
    render(<PresenceCard level={3} saving={false} onChange={() => {}} />)
    expect(await screen.findByRole('slider')).toBeTruthy()
    await waitFor(() => expect(screen.getByText(/the part of me that keeps it isn't installed/i)).toBeTruthy())
    expect(screen.getByText(/could not read the levels/i)).toBeTruthy()
  })

  it("never puts the platform's own wording on the surface", async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('Failed to fetch') }))
    render(<PresenceCard level={3} saving={false} onChange={() => {}} />)
    await waitFor(() => expect(screen.getByText(/could not read the log just now/i)).toBeTruthy())
    expect(screen.queryByText(/Failed to fetch/)).toBeNull()
  })
})
