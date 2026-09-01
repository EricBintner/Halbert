// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * StandbyController (P1) — the in-app half of spec doc 15 §5.2's multi-tier
 * standby policy: an idle kiosk surface must not glow in a dark room.
 *
 *   - Tier 1 (30s idle): ultra-dim breathing — a near-black veil drops the
 *     mark (and everything else) to ~10% effective opacity. The mark keeps
 *     breathing: the machine's `standby` visual is already the idle source,
 *     this only dims it — plus the room clock (spec §5.2 tier 1).
 *   - Tier 2 (10min idle): software blackout — pure #000000 with
 *     `cursor: none`, everything hidden. Instant wake on any input.
 *   - Tier 3 (hardware backlight dimming / DPMS) is NOT this component's
 *     job — see the P2 report contract below.
 *
 * Machine wiring (the coherent choice, documented): tier 1 keys off the SAME
 * idle signal as O6 — the hook's 30s `standby_timeout` decay and this
 * controller's idle clock both start from the last machine event, so the dim
 * lands with the machine entering `standby`. The controller is the visual
 * layer only and never dispatches machine events. Restoration is dual:
 * any window pointermove / pointerdown / touchstart / keydown resets the
 * idle clock here, and any machine event that leaves `standby` (wake,
 * acoustic_wake, a turn starting) resets it through the `machineState` prop —
 * so a machine `wake` restores the visual without the controller touching
 * the reducer. While the machine is out of `standby` the tier is pinned
 * full: a live mic or an in-flight turn is by definition not idle (a long
 * speaking turn never dims), and entering `standby` is an automatic decay,
 * not activity, so it deliberately does NOT reset the clock — the dim lands
 * exactly when the machine decays.
 *
 * The tier is announced through `onTierChange` so the page can STOP
 * RENDERING the mark at `black`: under the opaque veil it is invisible, but
 * its rAF physics loop would otherwise composite at 60fps all night on the
 * fanless N150. Unmounting is the cancel-by-construction (the mark's own
 * cleanup stops its loop) and it remounts with an instant static first
 * paint on wake — deliberately no `paused` prop is added to the
 * design-system component.
 *
 * P2 contract (plan doc 16 §6 Task P2 — screen power daemon, greenfield):
 * at every tier transition this controller fire-and-forgets
 *
 *     POST /api/system/display   {"idle_seconds": <number>}
 *
 * where `idle_seconds` is the age of the last interaction / machine event at
 * the moment of the transition: 30 entering tier 1, 600 entering tier 2, and
 * 0 on any wake (the "screen is awake again" report). P2's daemon maps this
 * onto tier 3 — backlight to 0% via /sys/class/backlight or DPMS sleep past
 * 15 idle minutes or during quiet hours — and uses the 0 report to raise the
 * panel before TTS begins. The endpoint does not exist until P2 lands, so
 * the POST is failure-silent (404 and network errors swallowed); P2 should
 * treat an unknown-shape body as a no-op, not an error.
 *
 * Quiet hours are deliberately NOT computed here: the engine's
 * `should_speak_proactively` gates proactive speech server-side, and the
 * controller has no display-only use for `GET /api/audio/config`'s
 * `privacy.quiet_hours` (a display-only poll on a battery-conscious kiosk
 * buys nothing) — so it is not read at all.
 */

import { useEffect, useRef, useState } from 'react'
import { apiUrl } from '@/lib/apiBase'
import type { VoiceModeState } from '@/hooks/useVoiceModeMachine'

/** Idle after which tier 1 (ultra-dim breathing + room clock) engages. */
export const TIER1_IDLE_MS = 30_000
/** Total idle after which tier 2 (software blackout, cursor hidden) engages. */
export const TIER2_IDLE_MS = 600_000

/** Cadence the idle clock is evaluated at (tier boundaries land within 1s). */
const IDLE_TICK_MS = 1_000
/** Cadence the room clock re-renders at while dimmed. */
const CLOCK_TICK_MS = 15_000

/** The endpoint P2 implements; see the module doc's contract block. */
export const DISPLAY_REPORT_PATH = '/api/system/display'

export type StandbyTier = 'full' | 'dim' | 'black'

/** HH:MM, 24h — the room clock's only job is "what time is it" at a glance. */
function formatRoomClock(date: Date): string {
  return `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`
}

/** Events that count as user presence (spec §5.2: instant wake on touch). */
const ACTIVITY_EVENTS = ['pointermove', 'pointerdown', 'touchstart', 'keydown'] as const

export interface StandbyControllerProps {
  /** The voice machine state (O6). Anything but `standby` is a live session:
   * the tier pins full and every transition into a live state resets idle. */
  machineState: VoiceModeState
  /** Notified on every tier change (including the mount-time 'full'). The
   * page uses this to STOP RENDERING the mark at `black`: under the opaque
   * veil it is invisible, but its rAF loop would still composite at 60fps
   * all night — unmounting it cancels the loop by construction (its own
   * cleanup) and it remounts with an instant static first paint on wake. */
  onTierChange?: (tier: StandbyTier) => void
}

/**
 * Renders the standby veil over the voice surface. At `full` the veil is
 * transparent and inert; at `dim` it is a 90%-black layer with the room
 * clock; at `black` it is opaque with the cursor hidden. Transitions fade
 * (restore fades back up over 1s — instant enough for a kiosk, gentle
 * enough for a dark room).
 */
export function StandbyController({ machineState, onTierChange }: StandbyControllerProps) {
  const [tier, setTier] = useState<StandbyTier>('full')
  const [clock, setClock] = useState(() => formatRoomClock(new Date()))

  /** Age of the last interaction / machine event (the idle origin). */
  const lastActivityRef = useRef(Date.now())

  // evaluate() is rewritten every render so the interval and the listeners
  // always see fresh props; it only touches refs and one state setter.
  const evaluateRef = useRef<() => void>(() => undefined)
  evaluateRef.current = (): void => {
    const idle = Date.now() - lastActivityRef.current
    const active = machineState !== 'standby'
    const next: StandbyTier = active
      ? 'full'
      : idle >= TIER2_IDLE_MS
        ? 'black'
        : idle >= TIER1_IDLE_MS
          ? 'dim'
          : 'full'
    // Identical state bails out — the 1s tick never repaints a held tier.
    setTier((prev) => (prev === next ? prev : next))
  }

  // Presence detection: window-level listeners (the kiosk surface is the
  // whole screen) plus the 1s evaluation tick that walks the tier ladder.
  // `visibilitychange` is a presence event too: an occluded/minimized Tauri
  // window throttles the 1s tick AND restoring the window fires no pointer
  // or key event in-page — without this the screen can come back already
  // blacked out, needing a tap to wake.
  useEffect(() => {
    const onActivity = (): void => {
      lastActivityRef.current = Date.now()
      evaluateRef.current()
    }
    for (const type of ACTIVITY_EVENTS) {
      window.addEventListener(type, onActivity, { passive: true })
    }
    const onVisibility = (): void => {
      if (!document.hidden) onActivity()
    }
    document.addEventListener('visibilitychange', onVisibility)
    const ticker = setInterval(() => evaluateRef.current(), IDLE_TICK_MS)
    return () => {
      clearInterval(ticker)
      document.removeEventListener('visibilitychange', onVisibility)
      for (const type of ACTIVITY_EVENTS) {
        window.removeEventListener(type, onActivity)
      }
    }
  }, [])

  // Any machine event that leaves standby is presence (a wake, an acoustic
  // anomaly, a turn): reset the idle clock. The effect keys on the state
  // VALUE: transitions among live states (listening -> thinking -> speaking
  // -> listening) each reset, and no-op events in standby change nothing —
  // the machine already treats those as non-activity for its own decay.
  useEffect(() => {
    if (machineState === 'standby') return
    lastActivityRef.current = Date.now()
    evaluateRef.current()
  }, [machineState])

  // The room clock only runs while it is on screen, and re-reads the wall
  // clock the moment the veil dims in (the mount-time value may be stale).
  useEffect(() => {
    if (tier !== 'dim') return
    setClock(formatRoomClock(new Date()))
    const ticker = setInterval(() => setClock(formatRoomClock(new Date())), CLOCK_TICK_MS)
    return () => clearInterval(ticker)
  }, [tier])

  // Tier changes are announced to the page (which stops rendering the mark
  // under the blackout veil — unmounting cancels the mark's rAF loop by
  // construction). Runs on mount too ('full'), which is a harmless no-op
  // for the page's own state mirror.
  const onTierChangeRef = useRef(onTierChange)
  onTierChangeRef.current = onTierChange
  useEffect(() => {
    onTierChangeRef.current?.(tier)
  }, [tier])

  // -------------------------------------------------------------------------
  // P2 report — POST /api/system/display {"idle_seconds": n} (see module doc)
  // -------------------------------------------------------------------------

  const reportedTierRef = useRef<StandbyTier | null>(null)
  useEffect(() => {
    const previous = reportedTierRef.current
    reportedTierRef.current = tier
    // Skip mount (no transition yet) and re-renders that held the tier.
    if (previous === null || previous === tier) return
    const idleSeconds = Math.max(0, Math.round((Date.now() - lastActivityRef.current) / 1000))
    void fetch(apiUrl(DISPLAY_REPORT_PATH), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ idle_seconds: idleSeconds }),
    }).catch(() => {
      // Fire-and-forget by contract: until P2 lands this route 404s, and a
      // dead backend must never surface as an error on the kiosk screen.
    })
  }, [tier])

  // The veil's ONE background is in the base class (`bg-black`); the tiers
  // modulate only opacity — 90% at tier 1 dims the mark beneath to ~10%
  // effective, 100% at tier 2 is the pure blackout. Never stack a base and
  // an override background: their cascade order is not guaranteed.
  const veil =
    tier === 'full'
      ? 'pointer-events-none opacity-0'
      : tier === 'dim'
        ? 'pointer-events-none opacity-90'
        : 'cursor-none opacity-100'

  return (
    <div
      data-testid="standby-veil"
      aria-hidden={tier === 'full'}
      className={`fixed inset-0 z-50 flex items-center justify-center bg-black transition-opacity duration-1000 ${veil}`}
    >
      {tier === 'dim' && (
        <time
          data-testid="standby-clock"
          // Decorative: the wall time is ambient, not content to announce.
          aria-hidden="true"
          className="text-8xl font-light tabular-nums tracking-tight text-canvas/50"
        >
          {clock}
        </time>
      )}
    </div>
  )
}

export default StandbyController
