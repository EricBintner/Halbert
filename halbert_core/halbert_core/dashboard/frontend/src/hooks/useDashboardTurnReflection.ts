// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * C4 (turn-event tee), the first consumer: the voice HUD reflecting a
 * turn it did not post.
 *
 * Today a turn's events reach exactly one HTTP response — the SSE of
 * whoever posted it — so a voice screen in the room goes dark while the
 * owner asks something at the dashboard. The state machine now publishes
 * a REDUCED event set (state transitions, statuses, tool/block markers,
 * the busy-mode verdicts — never the token stream) to a process-wide tee,
 * and app.py bridges the tee onto the authenticated /ws fan-out as
 * `{'type': 'turn_event'}` frames. This hook subscribes there and tracks
 * whether a NON-VOICE turn is running (and which phase it is in).
 *
 * Two rules from the design, held here:
 *
 *  - observe-only: the frames carry no verb, and this hook asks for
 *    nothing — it cannot steer or stop the turn it watches;
 *  - privacy by construction: the reduced payloads carry no content, so
 *    there is nothing here to render beyond "the machine is working" —
 *    the words being typed at the dashboard never reach this page.
 */
import { useEffect, useState } from 'react'
import { wsUrl } from '../lib/apiBase'

export interface DashboardTurnReflection {
  /** True while a turn from another surface (dashboard/terminal) runs. */
  active: boolean
  /** The last reduced phase the running turn reported (e.g. 'planning'). */
  phase: string | null
}

/** Reconnect delay after the socket drops (the tee is best-effort). */
const RECONNECT_MS = 5_000

export function useDashboardTurnReflection(): DashboardTurnReflection {
  const [active, setActive] = useState(false)
  const [phase, setPhase] = useState<string | null>(null)

  useEffect(() => {
    let closed = false
    let socket: WebSocket | null = null
    let retry: ReturnType<typeof setTimeout> | null = null

    const connect = () => {
      if (closed) return
      try {
        socket = new WebSocket(wsUrl('/ws'))
      } catch {
        return // no bridge to listen to — the HUD simply does not reflect
      }
      socket.onmessage = (ev) => {
        let msg: { type?: string; data?: Record<string, unknown> }
        try {
          msg = JSON.parse(String(ev.data))
        } catch {
          return
        }
        if (msg.type !== 'turn_event' || !msg.data) return
        const data = msg.data
        // This page IS the voice surface — its own turns already live
        // here in full; the reflection is for the other surfaces' turns.
        if (data.channel === 'voice') return
        switch (data.event) {
          case 'turn_started':
            setActive(true)
            setPhase('working')
            break
          case 'state_change':
            if (typeof data.to === 'string') setPhase(data.to)
            break
          case 'turn_ended':
            setActive(false)
            setPhase(null)
            break
        }
      }
      socket.onclose = () => {
        if (closed) return
        // Best-effort observation, never delivery: drop the frame's
        // worth of state quietly and try again shortly.
        retry = setTimeout(connect, RECONNECT_MS)
      }
    }

    connect()
    return () => {
      closed = true
      if (retry) clearTimeout(retry)
      socket?.close()
    }
  }, [])

  return { active, phase }
}