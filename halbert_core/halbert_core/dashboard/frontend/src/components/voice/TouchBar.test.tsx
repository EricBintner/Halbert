// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * TouchBar (O7): the three touch controls of spec doc 15 §6.2 — push to
 * talk, the on-screen keyboard, and the return edge to the conversation
 * (the navigation itself is O8's; this bar only reports the taps).
 *
 * The third control is labelled 'Conversation': 'Host Canvas' is a banned
 * label (shell review §9.1 ruling #9), so the test pins its absence too.
 */

import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { TouchBar } from './TouchBar'

describe('TouchBar', () => {
  it('renders the three §6.2 controls', () => {
    render(
      <TouchBar onPushToTalk={vi.fn()} onKeyboard={vi.fn()} onHostCanvas={vi.fn()} />,
    )
    expect(screen.getByRole('button', { name: 'Tap to speak' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Open keyboard' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Open the conversation' })).toBeTruthy()
  })

  it('names the return edge Conversation, never the banned Host Canvas', () => {
    const { container } = render(
      <TouchBar onPushToTalk={vi.fn()} onKeyboard={vi.fn()} onHostCanvas={vi.fn()} />,
    )
    const button = screen.getByRole('button', { name: 'Open the conversation' })
    expect(button.textContent).toContain('Conversation')
    expect(container.textContent ?? '').not.toMatch(/host canvas/i)
    expect(container.innerHTML).not.toMatch(/host canvas/i)
  })

  it('dispatches each handler on tap', async () => {
    const user = userEvent.setup()
    const onPushToTalk = vi.fn()
    const onKeyboard = vi.fn()
    const onHostCanvas = vi.fn()
    render(
      <TouchBar
        onPushToTalk={onPushToTalk}
        onKeyboard={onKeyboard}
        onHostCanvas={onHostCanvas}
      />,
    )

    await user.click(screen.getByRole('button', { name: 'Tap to speak' }))
    await user.click(screen.getByRole('button', { name: 'Open keyboard' }))
    await user.click(screen.getByRole('button', { name: 'Open the conversation' }))

    expect(onPushToTalk).toHaveBeenCalledTimes(1)
    expect(onKeyboard).toHaveBeenCalledTimes(1)
    expect(onHostCanvas).toHaveBeenCalledTimes(1)
  })

  it('meets the 44px touch-target minimum on every button', () => {
    render(
      <TouchBar onPushToTalk={vi.fn()} onKeyboard={vi.fn()} onHostCanvas={vi.fn()} />,
    )
    for (const name of ['Tap to speak', 'Open keyboard', 'Open the conversation']) {
      const button = screen.getByRole('button', { name }) as HTMLElement
      expect(button.className).toContain('h-12')
    }
  })

  it('is a labelled navigation landmark', () => {
    render(
      <TouchBar onPushToTalk={vi.fn()} onKeyboard={vi.fn()} onHostCanvas={vi.fn()} />,
    )
    expect(screen.getByRole('navigation', { name: 'Voice controls' })).toBeTruthy()
  })

  it('uses design tokens (vermilion accent on the dark surface), no raw classes', () => {
    const { container } = render(
      <TouchBar onPushToTalk={vi.fn()} onKeyboard={vi.fn()} onHostCanvas={vi.fn()} />,
    )
    const html = container.innerHTML
    for (const banned of ['text-white', 'orange-500', 'purple-500', 'bg-black', '#D34E24']) {
      expect(html).not.toContain(banned)
    }
    expect(html).toContain('text-vermilion')
    expect(html).toContain('text-canvas')
  })
})
