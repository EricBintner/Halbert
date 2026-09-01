// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * VoiceHud — the /voice-hud route: the floating companion panel (P4).
 *
 * This page is loaded by the Rust `show_voice_hud` command into a second
 * Tauri webview: a 480x72 borderless, always-on-top, transparent,
 * non-activating window (src-tauri/src/floating_panel.rs). It renders the
 * existing VoiceCompanionPill on a fully transparent surface — no shell
 * chrome (Layout’s HUD full-bleed exception) — so on macOS the pill
 * floats over whatever the sysadmin is working in. This is NOT the /voice
 * screen: the HUD is the Siri-style desktop companion — small,
 * glanceable, transient — not the full voice surface.
 *
 * DATA PATH (plan §6 Task P4 wrinkle — option a, BroadcastChannel relay):
 * the HUD is a separate webview = a separate JS context, so its own
 * useAgentStream has no turn and sees nothing. The main window’s
 * conversation surface publishes live speech segments over `hudChannel`
 * (src/lib/hudChannel.ts, fed by useHudSpeechPublisher in AgentChat);
 * useHudSpeech subscribes here. Limits: the HUD mirrors speech only while
 * the conversation surface is mounted; before the first relay message it
 * renders nothing (transient by design).
 *
 * Dismissal: Esc/Space are swallowed by the Rust CGEventTap, which hides
 * the window itself (it may be 'Unavailable' without Accessibility trust —
 * hence this page also provides the mouse fallback: a small dismiss
 * affordance shown only while the pill is visible, wired to the Rust
 * `hide_voice_hud` command). When the relayed turn ends (isActive ->
 * false) the HUD dismisses itself the same way: a window left visible
 * but empty would keep the Esc/Space tap armed (eating the user’s keys
 * in their IDE) and block clicks over the IDE with an invisible panel.
 *
 * Rust-side follow-ups noted (not added here, per the task contract):
 * the `voice-hud:hotkey` “interrupt” event is emitted only to the HUD
 * webview, but TTS playback lives in the MAIN window’s JS context — a
 * Space press can only dismiss the pill, not pause the voice, until the
 * event also reaches the main window.
 */

import { useCallback, useEffect, useRef } from 'react'
import { X } from 'lucide-react'
import { VoiceCompanionPill } from '@/components/audio'
import { Button } from '@/components/ui/button'
import { useHudSpeech } from '@/hooks/useHudSpeech'
import { hideVoiceHud, isTauriShell } from '@/lib/voiceHud'

export function VoiceHud() {
  const speech = useHudSpeech()
  const segments = speech?.segments ?? []
  const isActive = speech?.isActive ?? false
  const wasActiveRef = useRef(false)

  // The Rust window is created with transparent(true); the shell’s
  // `body { bg-background }` would paint an opaque bar behind the pill.
  useEffect(() => {
    document.body.classList.add('voice-hud-surface')
    return () => document.body.classList.remove('voice-hud-surface')
  }, [])

  const dismiss = useCallback(async () => {
    if (!isTauriShell()) return
    try {
      await hideVoiceHud()
    } catch (err) {
      // The window may already be gone (hidden by the Esc tap); a failed
      // hide must never take the pill surface down with it.
      console.warn('[Halbert] voice HUD: hide failed:', err)
    }
  }, [])

  // Self-dismiss at turn end — see the header: an empty-but-visible HUD
  // keeps the Esc/Space tap armed and blocks clicks over the IDE.
  useEffect(() => {
    if (wasActiveRef.current && !isActive) {
      void dismiss()
    }
    wasActiveRef.current = isActive
  }, [isActive, dismiss])

  const showPill = isActive && segments.length > 0

  return (
    <div className="h-screen w-full bg-transparent" data-testid="voice-hud-surface">
      <div className="flex h-full items-center justify-center px-1">
        {showPill ? (
          <>
            <VoiceCompanionPill segments={segments} isActive={isActive} />
            {/* Mouse fallback for the Esc tap (which needs Accessibility
                trust). Only present while the pill is, so an idle window
                never floats an invisible click target. */}
            <Button
              variant="ghost"
              size="icon"
              className="h-5 w-5 shrink-0"
              onClick={() => void dismiss()}
              title="Dismiss the voice companion"
              aria-label="Dismiss the voice companion"
              data-testid="hud-dismiss"
            >
              <X className="h-3 w-3" />
            </Button>
          </>
        ) : null}
      </div>
    </div>
  )
}
