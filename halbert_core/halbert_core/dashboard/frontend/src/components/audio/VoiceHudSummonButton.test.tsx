// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * VoiceHudSummonButton (P4) — the top-bar entry for the floating HUD.
 *
 * The graceful-degradation contract is the core of this suite: the button
 * must not exist at all in a plain browser (there is no overlay window to
 * summon), and a failed invoke must not break the top bar.
 *
 * The button polls `get_voice_hud_status` on mount to sync with the real
 * window state (the HUD may have been hidden by the Rust Esc/Space tap or
 * by the HUD page's self-dismiss). The toggle handler calls
 * `toggleVoiceHud` which itself reads status then shows/hides.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, act } from '@testing-library/react'
import { invoke } from '@tauri-apps/api/core'
import { VoiceHudSummonButton } from './VoiceHudSummonButton'

vi.mock('@tauri-apps/api/core', () => ({ invoke: vi.fn() }))

const invokeMock = vi.mocked(invoke)

beforeEach(() => {
  invokeMock.mockReset()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('VoiceHudSummonButton', () => {
  it('renders nothing in a plain browser', () => {
    const { container } = render(<VoiceHudSummonButton />)

    expect(container.firstChild).toBeNull()
    expect(screen.queryByRole('button')).toBeNull()
  })

  it('polls status on mount and toggles the HUD through show', async () => {
    vi.stubGlobal('__TAURI_INTERNALS__', {})
    invokeMock.mockImplementation(async (cmd: string) =>
      cmd === 'get_voice_hud_status'
        ? { visible: false, hotkey_tap: 'Inactive' }
        : { visible: true, hotkey_tap: 'Active' },
    )

    render(<VoiceHudSummonButton />)

    // Mount poll picks up the real (hidden) state.
    await waitFor(() => {
      expect(invokeMock).toHaveBeenCalledWith('get_voice_hud_status')
    })

    act(() => {
      screen.getByRole('button').click()
    })

    // toggleVoiceHud reads status (hidden) then shows.
    await waitFor(() => {
      expect(invokeMock).toHaveBeenCalledWith('show_voice_hud')
    })
    await waitFor(() => {
      expect(screen.getByRole('button')).toHaveAttribute('aria-pressed', 'true')
    })
  })

  it('hides a visible HUD on the next click', async () => {
    vi.stubGlobal('__TAURI_INTERNALS__', {})
    let visible = true
    invokeMock.mockImplementation(async (cmd: string) =>
      cmd === 'get_voice_hud_status'
        ? { visible, hotkey_tap: 'Active' }
        : { visible: (visible = false), hotkey_tap: 'Inactive' },
    )

    render(<VoiceHudSummonButton />)

    // Mount poll sees the HUD is already visible.
    await waitFor(() => {
      expect(screen.getByRole('button')).toHaveAttribute('aria-pressed', 'true')
    })

    act(() => {
      screen.getByRole('button').click()
    })

    // toggleVoiceHud reads status (visible) then hides.
    await waitFor(() => {
      expect(invokeMock).toHaveBeenCalledWith('hide_voice_hud')
    })
  })

  it('survives a failed invoke without breaking the top bar', async () => {
    vi.stubGlobal('__TAURI_INTERNALS__', {})
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    invokeMock.mockRejectedValue(new Error('no window'))

    render(<VoiceHudSummonButton />)

    // Wait for the mount poll to fail.
    await waitFor(() => {
      expect(warn).toHaveBeenCalled()
    })

    act(() => {
      screen.getByRole('button').click()
    })

    await waitFor(() => {
      expect(warn).toHaveBeenCalledTimes(2)
    })
    expect(screen.getByRole('button')).toBeInTheDocument()
  })

  it('guards against concurrent clicks', async () => {
    vi.stubGlobal('__TAURI_INTERNALS__', {})
    let resolveToggle: (v: { visible: boolean; hotkey_tap: string }) => void
    const togglePromise = new Promise((r) => { resolveToggle = r })
    invokeMock.mockImplementation(async (cmd: string) =>
      cmd === 'get_voice_hud_status'
        ? { visible: false, hotkey_tap: 'Inactive' }
        : togglePromise as Promise<{ visible: boolean; hotkey_tap: string }>,
    )

    render(<VoiceHudSummonButton />)
    await waitFor(() => {
      expect(invokeMock).toHaveBeenCalledWith('get_voice_hud_status')
    })

    const button = screen.getByRole('button')
    act(() => { button.click() })
    act(() => { button.click() }) // second click while pending

    // Only one toggle call should have been dispatched.
    expect(invokeMock).toHaveBeenCalledTimes(2) // mount poll + one toggle

    // Resolve and clean up.
    act(() => { resolveToggle!({ visible: true, hotkey_tap: 'Active' }) })
  })
})
