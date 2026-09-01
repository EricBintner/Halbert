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
 *
 * State sync: the HUD can be hidden by the Rust Esc/Space tap or by the
 * HUD page's own turn-end self-dismiss — neither path updates this
 * button. On mount we poll `getVoiceHudStatus` to pick up the real
 * window state, and the toggle handler updates from the response. A
 * full event-listener sync (Rust -> frontend) is a future follow-up;
 * the one-way poll covers the common case.
 */

import { useEffect, useState } from 'react'
import { AppWindow } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { getVoiceHudStatus, isTauriShell, toggleVoiceHud } from '@/lib/voiceHud'

export function VoiceHudSummonButton() {
  const [visible, setVisible] = useState(false)
  const [pending, setPending] = useState(false)

  // Sync with the real window state on mount — the HUD may have been
  // hidden by the Rust tap or self-dismiss while this button was unmounted.
  useEffect(() => {
    if (!isTauriShell()) return
    let cancelled = false
    getVoiceHudStatus()
      .then((status) => { if (!cancelled) setVisible(status.visible) })
      .catch((err) => { /* best-effort: stay at default false */
        if (!cancelled) console.warn('[Halbert] voice HUD status poll failed:', err)
      })
    return () => { cancelled = true }
  }, [])

  if (!isTauriShell()) return null

  const onClick = async () => {
    if (pending) return // guard against concurrent clicks
    setPending(true)
    try {
      const status = await toggleVoiceHud()
      setVisible(status.visible)
    } catch (err) {
      // The HUD is best-effort: a failed summon must not break the top bar.
      console.warn('[Halbert] voice HUD toggle failed:', err)
    } finally {
      setPending(false)
    }
  }

  return (
    <Button
      variant="ghost"
      size="icon"
      className="h-7 w-7"
      onClick={() => void onClick()}
      disabled={pending}
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
