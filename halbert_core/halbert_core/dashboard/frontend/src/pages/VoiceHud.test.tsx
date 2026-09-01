// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * VoiceHud page (P4) — the floating companion window’s route.
 *
 * The page is fed by the hudChannel relay (a second webview = a second JS
 * context, so it can never see the main window’s useAgentStream). Covers:
 * renders nothing before the first relayed message, renders the pill from
 * relayed speech, the mouse-fallback dismiss (Rust `hide_voice_hud`), the
 * self-dismiss at turn end (an invisible-but-visible window would eat the
 * user’s Esc/Space through the armed hotkey tap), and plain-browser
 * degradation — a missing Tauri IPC must never crash the pill surface.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, act } from '@testing-library/react'
import { invoke } from '@tauri-apps/api/core'
import { VoiceHud } from './VoiceHud'
import { createHudSpeechPublisher, type HudSpeechPublisher } from '@/lib/hudChannel'
import { installFakeBroadcastChannel } from '@/test/fakeBroadcastChannel'
import type { SpeechSegmentEvent } from '@/hooks/useAgentStream'

vi.mock('@tauri-apps/api/core', () => ({ invoke: vi.fn() }))

const invokeMock = vi.mocked(invoke)

function segment(text: string): SpeechSegmentEvent {
  return { text, role: 'persona', prosody: { rate: 1, volume: 1, whisper: false } }
}

let publisher: HudSpeechPublisher

/** Simulate the main window publishing a live speech state. */
function relay(text: string, isActive: boolean): void {
  act(() => {
    publisher.publish({ segments: [segment(text)], isActive })
  })
}

beforeEach(() => {
  installFakeBroadcastChannel()
  publisher = createHudSpeechPublisher()
  invokeMock.mockReset()
  invokeMock.mockResolvedValue({ visible: false, hotkey_tap: 'Inactive' })
})

afterEach(() => {
  vi.unstubAllGlobals()
  publisher.close()
})

describe('VoiceHud page', () => {
  it('renders nothing before the first relayed message', () => {
    render(<VoiceHud />)

    expect(screen.queryByTestId('voice-hud-surface')).toBeInTheDocument()
    expect(screen.queryByTestId('hud-dismiss')).not.toBeInTheDocument()
    expect(screen.queryByText(/./)).toBeNull()
  })

  it('marks the body transparent for the Tauri overlay window', () => {
    const view = render(<VoiceHud />)

    expect(document.body.classList.contains('voice-hud-surface')).toBe(true)

    view.unmount()

    expect(document.body.classList.contains('voice-hud-surface')).toBe(false)
  })

  it('renders the pill from relayed speech', () => {
    render(<VoiceHud />)
    relay('hello from the turn', true)

    expect(screen.getByText('hello from the turn')).toBeInTheDocument()
    expect(screen.getByTestId('hud-dismiss')).toBeInTheDocument()
  })

  it('clears the pill when the turn goes inactive', () => {
    render(<VoiceHud />)
    relay('speaking', true)
    relay('speaking', false)

    expect(screen.queryByText('speaking')).not.toBeInTheDocument()
    expect(screen.queryByTestId('hud-dismiss')).not.toBeInTheDocument()
  })
})

describe('VoiceHud dismissal', () => {
  it('dismiss affordance invokes the Rust hide command', async () => {
    vi.stubGlobal('__TAURI_INTERNALS__', {})
    render(<VoiceHud />)
    relay('speaking', true)

    act(() => {
      screen.getByTestId('hud-dismiss').click()
    })

    await waitFor(() => {
      expect(invokeMock).toHaveBeenCalledWith('hide_voice_hud')
    })
  })

  it('self-dismisses through Rust when the turn ends', async () => {
    vi.stubGlobal('__TAURI_INTERNALS__', {})
    render(<VoiceHud />)
    relay('speaking', true)
    relay('speaking', false)

    await waitFor(() => {
      expect(invokeMock).toHaveBeenCalledWith('hide_voice_hud')
    })
  })

  it('degrades gracefully in a plain browser: no invoke, no crash', async () => {
    // No __TAURI_INTERNALS__: isTauriShell() is false.
    render(<VoiceHud />)
    relay('speaking', true)

    act(() => {
      screen.getByTestId('hud-dismiss').click()
    })
    relay('speaking', false)

    // Give any (wrongly fired) invoke a chance to surface.
    await act(async () => {
      await Promise.resolve()
    })

    expect(invokeMock).not.toHaveBeenCalled()
    expect(screen.getByTestId('voice-hud-surface')).toBeInTheDocument()
  })
})
