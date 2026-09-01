// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * voiceHud — the frontend bridge to the Tauri floating voice HUD (P4).
 *
 * The Rust contract (src-tauri/src/floating_panel.rs, registered in
 * src-tauri/src/lib.rs):
 *
 *  - `show_voice_hud`       lazily creates the 480x72 borderless,
 *                           always-on-top, transparent, non-activating
 *                           overlay window loading this SPA at /voice-hud,
 *                           then arms the Esc/Space hotkey tap. Returns
 *                           VoiceHudStatus.
 *  - `hide_voice_hud`       hides the window and disarms the tap.
 *  - `get_voice_hud_status` reads the status without touching the window.
 *
 *  - VoiceHudStatus is `{ visible: boolean, hotkey_tap: 'Active' |
 *    'Inactive' | 'Unavailable' | 'Unsupported' }` — the hotkey_tap field
 *    tells the frontend whether Esc/Space interception is armed
 *    ('Unavailable' means the app is not trusted for Accessibility).
 *
 * The window is created with `transparent(true)` (macos-private-api), so
 * the /voice-hud page must cooperate with a fully transparent background.
 *
 * Browser degradation: a plain browser has no Tauri IPC and no overlay
 * window to summon. `isTauriShell()` is the gate — callers hide their
 * entry points when it is false and treat any invoke failure as a no-op,
 * never a crash.
 */

import { invoke } from '@tauri-apps/api/core'

export type VoiceHudHotkeyTapState = 'Active' | 'Inactive' | 'Unavailable' | 'Unsupported'

export interface VoiceHudStatus {
  visible: boolean
  hotkey_tap: VoiceHudHotkeyTapState
}

/**
 * Whether this SPA is running inside the Tauri desktop shell. Tauri v2
 * injects `window.__TAURI_INTERNALS__` into every webview before any
 * frontend code runs; a plain browser never has it.
 */
export function isTauriShell(): boolean {
  return typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window
}

/** Show (and lazily create) the floating voice HUD window. */
export function showVoiceHud(): Promise<VoiceHudStatus> {
  return invoke<VoiceHudStatus>('show_voice_hud')
}

/** Hide the floating voice HUD and disarm the Esc/Space tap. */
export function hideVoiceHud(): Promise<VoiceHudStatus> {
  return invoke<VoiceHudStatus>('hide_voice_hud')
}

/** Read the HUD lifecycle status without showing or hiding it. */
export function getVoiceHudStatus(): Promise<VoiceHudStatus> {
  return invoke<VoiceHudStatus>('get_voice_hud_status')
}

/** Show the HUD if hidden, hide it if shown. */
export async function toggleVoiceHud(): Promise<VoiceHudStatus> {
  const status = await getVoiceHudStatus()
  return status.visible ? hideVoiceHud() : showVoiceHud()
}
