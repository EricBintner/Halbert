// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * Voice Mode input events derived from proactive (being) SSE — the O5 seam.
 *
 * Task O6 will build `useVoiceModeMachine`, a pure 7-state reducer whose
 * input events are listed in the plan (`wake`, `vad_end`, ...). This module
 * is the ONLY piece of the acoustic wake behaviour that exists today, kept
 * pure and DOM-free (plan Decision 6) so O6 can absorb it without changes:
 *
 *   - import `acousticWakeEvent` (and `ACOUSTIC_WAKE_MIN_SEVERITY`) there,
 *   - feed it every BeingEvent arriving on useBeingEvents,
 *   - when it returns non-null, transition to the wake state from ANY
 *     current state — including standby — with full brightness and the
 *     amber-pulse visual while `severity >= ACOUSTIC_WAKE_MIN_SEVERITY`
 *     (urgency 'critical' at 3 means life-safety: smoke alarm, glass break).
 *
 * The backend contract this maps from: an acoustic anomaly finding published
 * by DetectorRunner with category 'acoustic' and a structured `data` payload
 * (sound_class, anomaly_severity 0-3, ...) built by AcousticAnomalyDetector.
 */
import type { BeingEvent } from './useBeingEvents'
import { isAcousticEvent } from './useBeingEvents'

/** Tagger anomaly_severity at or above this forces a wake (plan O5: >= 2). */
export const ACOUSTIC_WAKE_MIN_SEVERITY = 2

export interface AcousticWakeEvent {
  type: 'acoustic_wake'
  /** Tagger sound class, e.g. 'smoke_alarm' (for the wake UI subtitle). */
  soundClass: string
  /** anomaly_severity 0-3 from the structured payload. */
  severity: number
  /** 'urgent' at severity 2 (confirmed anomaly), 'critical' at 3 (life-safety). */
  urgency: 'urgent' | 'critical'
}

/**
 * Decide whether a proactive event forces the Voice Mode visual state to
 * wake. Returns the reducer input event, or null when the event is not an
 * acoustic anomaly of wake-worthy severity.
 */
export function acousticWakeEvent(event: BeingEvent): AcousticWakeEvent | null {
  if (!isAcousticEvent(event)) return null
  // No structured payload -> no severity -> not wake-worthy (a bare
  // title/severity finding event cannot be trusted to wake the screen).
  const severity = event.data?.anomaly_severity ?? 0
  if (severity < ACOUSTIC_WAKE_MIN_SEVERITY) return null
  return {
    type: 'acoustic_wake',
    soundClass: event.data?.sound_class ?? 'unknown',
    severity,
    urgency: severity >= 3 ? 'critical' : 'urgent',
  }
}
