// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * VoiceHudSummonButton (P4) — the top-bar entry for the floating HUD.
 *
 * The graceful-degradation contract is the core of this suite: the button
 * must not exist at all in a plain browser (there is no overlay window to
 * summon), and a failed invoke must not break the top bar.
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

  it('toggles the HUD through the Rust status + show commands', async () => {
    vi.stubGlobal('__TAURI_INTERNALS__', {})
    invokeMock.mockImplementation(async (cmd: string) =>
      cmd === 'get_voice_hud_status'
        ? { visible: false, hotkey_tap: 'Inactive' }
        : { visible: true, hotkey_tap: 'Active' },
    )

    render(<VoiceHudSummonButton />)
    act(() => {
      screen.getByRole('button').click()
    })

    await waitFor(() => {
      expect(invokeMock).toHaveBeenNthCalledWith(1, 'get_voice_hud_status')
      expect(invokeMock).toHaveBeenNthCalledWith(2, 'show_voice_hud')
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
    act(() => {
      screen.getByRole('button').click()
    })

    await waitFor(() => {
      expect(invokeMock).toHaveBeenNthCalledWith(2, 'hide_voice_hud')
    })
  })

  it('survives a failed invoke without breaking the top bar', async () => {
    vi.stubGlobal('__TAURI_INTERNALS__', {})
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    invokeMock.mockRejectedValue(new Error('no window'))

    render(<VoiceHudSummonButton />)
    act(() => {
      screen.getByRole('button').click()
    })

    await waitFor(() => {
      expect(warn).toHaveBeenCalled()
    })
    expect(screen.getByRole('button')).toBeInTheDocument()
  })
})
