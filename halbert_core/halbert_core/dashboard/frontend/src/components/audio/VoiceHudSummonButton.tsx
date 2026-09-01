// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * VoiceHudSummonButton — summon/dismiss the floating voice HUD (P4).
 *
 * Entry point (documented choice): a top-bar button beside the Voice Mode
 * entry, so both voice surfaces share the corner of the shell. Clicking
 * toggles the Rust overlay window (`toggleVoiceHud`: status -> show/hide).
 *
 * Renders only inside the Tauri shell — a plain browser has no overlay
 * window to summon, and the button hiding (not erroring) is the graceful
 * degradation contract.
 */

import { useState } from 'react'
import { AppWindow } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { isTauriShell, toggleVoiceHud } from '@/lib/voiceHud'

export function VoiceHudSummonButton() {
  const [visible, setVisible] = useState(false)

  if (!isTauriShell()) return null

  const onClick = async () => {
    try {
      const status = await toggleVoiceHud()
      setVisible(status.visible)
    } catch (err) {
      // The HUD is best-effort: a failed summon must not break the top bar.
      console.warn('[Halbert] voice HUD toggle failed:', err)
    }
  }

  return (
    <Button
      variant="ghost"
      size="icon"
      className="h-7 w-7"
      onClick={() => void onClick()}
      title={
        visible
          ? 'Hide the floating voice companion'
          : 'Show the floating voice companion'
      }
      aria-label={
        visible
          ? 'Hide the floating voice companion'
          : 'Show the floating voice companion'
      }
      aria-pressed={visible}
      data-testid="hud-summon-button"
    >
      <AppWindow className="h-4 w-4" />
    </Button>
  )
}
