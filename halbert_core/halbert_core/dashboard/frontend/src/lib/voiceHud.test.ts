// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * voiceHud — the Tauri invoke bridge for the floating voice HUD (P4).
 *
 * Pins the exact Rust command names registered in src-tauri/src/lib.rs
 * (`show_voice_hud` / `hide_voice_hud` / `get_voice_hud_status` — see
 * floating_panel.rs) and the plain-browser degradation contract: the
 * shell detection reads window.__TAURI_INTERNALS__, never throws.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { invoke } from '@tauri-apps/api/core'
import {
  getVoiceHudStatus,
  hideVoiceHud,
  isTauriShell,
  showVoiceHud,
  toggleVoiceHud,
} from './voiceHud'

vi.mock('@tauri-apps/api/core', () => ({ invoke: vi.fn() }))

const invokeMock = vi.mocked(invoke)

beforeEach(() => {
  invokeMock.mockReset()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('isTauriShell', () => {
  it('is false in a plain browser', () => {
    expect(isTauriShell()).toBe(false)
  })

  it('is true inside a Tauri webview', () => {
    vi.stubGlobal('__TAURI_INTERNALS__', {})
    expect(isTauriShell()).toBe(true)
  })
})

describe('hud commands', () => {
  it('calls the registered Rust command names', async () => {
    vi.stubGlobal('__TAURI_INTERNALS__', {})
    invokeMock.mockResolvedValue({ visible: true, hotkey_tap: 'Active' })

    await showVoiceHud()
    expect(invoke).toHaveBeenLastCalledWith('show_voice_hud')

    await hideVoiceHud()
    expect(invoke).toHaveBeenLastCalledWith('hide_voice_hud')

    await getVoiceHudStatus()
    expect(invoke).toHaveBeenLastCalledWith('get_voice_hud_status')
  })

  it('returns the Rust status payload', async () => {
    invokeMock.mockResolvedValue({ visible: false, hotkey_tap: 'Unavailable' })
    await expect(getVoiceHudStatus()).resolves.toEqual({
      visible: false,
      hotkey_tap: 'Unavailable',
    })
  })
})

describe('toggleVoiceHud', () => {
  it('shows the HUD when it is hidden', async () => {
    invokeMock.mockImplementation(async (cmd: string) =>
      cmd === 'get_voice_hud_status'
        ? { visible: false, hotkey_tap: 'Inactive' }
        : { visible: true, hotkey_tap: 'Active' },
    )

    const status = await toggleVoiceHud()

    expect(status.visible).toBe(true)
    expect(invokeMock).toHaveBeenNthCalledWith(1, 'get_voice_hud_status')
    expect(invokeMock).toHaveBeenNthCalledWith(2, 'show_voice_hud')
  })

  it('hides the HUD when it is visible', async () => {
    invokeMock.mockImplementation(async (cmd: string) =>
      cmd === 'get_voice_hud_status'
        ? { visible: true, hotkey_tap: 'Active' }
        : { visible: false, hotkey_tap: 'Inactive' },
    )

    const status = await toggleVoiceHud()

    expect(status.visible).toBe(false)
    expect(invokeMock).toHaveBeenNthCalledWith(2, 'hide_voice_hud')
  })
})
