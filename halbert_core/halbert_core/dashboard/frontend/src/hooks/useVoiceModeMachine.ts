// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * Voice Mode state machine — the O6 7-state reducer + thin React wrapper.
 *
 * The reducer is pure and DOM-free (plan Decision 6, same as the
 * packages/design-system voice engine) and pins the transition matrix of
 * spec doc 15 §4 as corrected by plan doc 16 §1.2:
 *
 *   - `listening` is entered locally on wake (tap / push-to-talk); the mic
 *     is live before any turn starts.
 *   - `thinking` begins on end-of-speech (`vad_end`, manual or WS VAD).
 *   - `speaking` requires a real `speech_segment` from the agent turn SSE
 *     stream (plan: `modality_resolved` === 'voice'|'mixed' AND the first
 *     segment; `modality_resolved` alone is never enough, and a stray
 *     segment outside `thinking`/`speaking` must not start playback).
 *   - `turn_complete` (stream ended) lands in `listening`, not `standby`:
 *     spec §4's "Speaking -> Listening: continuous multi-turn" edge keeps
 *     the mic live for a follow-up, and the hook's 30s inactivity timer
 *     decays the settled state to `standby` (the "Turn Complete +
 *     Inactivity Timeout (30s)" edge — the timer deliberately lives in the
 *     hook, not in the pure reducer).
 *   - The O5 acoustic-wake seam is absorbed here: an `acoustic_wake` event
 *     (produced by `acousticWakeEvent()` in `voiceModeEvents.ts` when a
 *     proactive acoustic anomaly hits severity >= 2) forces wake from ANY
 *     state, including `standby` and `error` — full brightness on the mark
 *     while the anomaly lasts.
 *
 * `standby_timeout` is an internal event only the hook dispatches (from
 * its timer); it is part of the union so the decay stays an ordinary,
 * testable reducer transition.
 */
import { useCallback, useEffect, useReducer, useRef } from 'react'
import type {
  ResponseModality,
  SpeechSegmentEvent,
} from './useAgentStream'
import type { VoiceVisualState } from '@halbert/design-system'

// -----------------------------------------------------------------------------
// Types
// -----------------------------------------------------------------------------

export type VoiceModeState =
  | 'standby'
  | 'listening'
  | 'recognized'
  | 'thinking'
  | 'speaking'
  | 'interrupted'
  | 'error'

export type VoiceModeEvent =
  | { type: 'wake' } // tap / push-to-talk (acoustic anomalies use 'acoustic_wake')
  | { type: 'vad_end' } // manual or WS VAD end-of-speech
  | { type: 'speaker_recognized'; name: string; role: string; confidence: number }
  | { type: 'modality_resolved'; modality: ResponseModality }
  | { type: 'speech_segment'; segment: SpeechSegmentEvent }
  | { type: 'turn_complete' }
  | { type: 'interrupt' } // barge-in or mark tap during speaking
  | { type: 'error'; message: string }
  | { type: 'dismiss' }
  | { type: 'acoustic_wake'; soundClass: string; severity: number; urgency: 'urgent' | 'critical' }
  | { type: 'standby_timeout' } // internal: fired by the hook's 30s inactivity timer

/** Every machine state, exported for exhaustive-matrix tests and callers. */
export const VOICE_MODE_STATES = [
  'standby',
  'listening',
  'recognized',
  'thinking',
  'speaking',
  'interrupted',
  'error',
] as const satisfies readonly VoiceModeState[]

/** Inactivity after which the hook decays a settled state to standby (spec §4). */
export const STANDBY_TIMEOUT_MS = 30_000

// -----------------------------------------------------------------------------
// Pure reducer
// -----------------------------------------------------------------------------

/**
 * The spec §4 transition matrix, verbatim. Unspecified state×event
 * combinations are deliberate no-ops: the machine never invents a
 * transition the diagram (or the plan's stream mapping) does not name.
 */
export function voiceModeReducer(s: VoiceModeState, e: VoiceModeEvent): VoiceModeState {
  switch (e.type) {
    // O5 seam absorbed: an acoustic anomaly at wake-worthy severity forces
    // wake from ANY state — standby (the important one: screen asleep),
    // but also error, and over any in-flight visual (the alarm outranks
    // the current turn's visual; actual audio ducking is O3/O7's job).
    case 'acoustic_wake':
      return 'listening'

    // Standby -> Listening: wake word / screen tap / push-to-talk. While
    // already engaged the mic is live, so wake is a no-op (interrupt owns
    // the "tap the mark during speaking" path; thinking/speaking have a
    // turn in flight).
    case 'wake':
      switch (s) {
        case 'standby':
        case 'interrupted': // dampened back to the Listening posture
        case 'error': // explicit retry
          return 'listening'
        case 'listening':
          return 'listening'
        case 'recognized':
          return 'recognized' // identity badge already held; keep it
        case 'thinking':
        case 'speaking':
          return s
      }
      return s

    // Listening/Recognized -> Thinking: voice activity ceases. From
    // `interrupted` it is the barge-in utterance being captured (§4.1 row 6:
    // "new user utterance captured").
    case 'vad_end':
      switch (s) {
        case 'listening':
        case 'recognized':
        case 'interrupted':
          return 'thinking'
        default:
          return s
      }

    // Listening -> Recognized: Speaker biometric match (CAM++). Only the
    // states where the mic is actually producing speech can match.
    case 'speaker_recognized':
      switch (s) {
        case 'listening':
        case 'recognized': // repeat match: hold the badge
          return 'recognized'
        default:
          return s
      }

    // The modality decision alone changes no state (plan §1.2: speaking
    // needs modality_resolved 'voice'|'mixed' AND the first speech_segment;
    // a 'text' turn simply runs out to turn_complete). O7 reads the
    // modality from useAgentStream directly to wire the audio source.
    case 'modality_resolved':
      return s

    // First (and subsequent) segment of a voice/mixed turn -> Speaking.
    // Strictly gated: a segment that arrives in any other state (stale
    // stream, playback outside a turn, standby) must not start speaking.
    case 'speech_segment':
      switch (s) {
        case 'thinking':
        case 'speaking':
          return 'speaking'
        default:
          return s
      }

    // Turn ended (useAgentStream.isStreaming went false). Spec names
    // "Speaking -> Standby: Turn Complete + Inactivity Timeout (30s)" as
    // two steps: the reducer takes the first half (continuous multi-turn
    // keeps listening live), and the hook's timer completes the decay.
    case 'turn_complete':
      switch (s) {
        case 'thinking':
        case 'speaking':
        case 'interrupted': // the interrupted turn ended during the lull
          return 'listening'
        default:
          return s
      }

    // Barge-in (WS VAD detects speech during playback) or the mark tap
    // during speaking: cut playback, capture the new utterance, dampen
    // back toward the Listening posture (§4.1 row 6). Gated to speaking —
    // `interrupt` is defined as a speaking-state event.
    case 'interrupt':
      return s === 'speaking' ? 'interrupted' : s

    // Mic failure / ingress disconnect / LLM timeout / tool exception.
    // Ignored in standby: a background failure must not flash the dimmed
    // screen awake (the acoustic_wake path exists for real reasons to
    // wake); an error while already in error just holds.
    case 'error':
      switch (s) {
        case 'listening':
        case 'recognized':
        case 'thinking':
        case 'speaking':
        case 'interrupted':
          return 'error'
        default:
          return s
      }

    // Error -> Standby: user dismissal (the only dismissal edge the spec
    // names — dismissing a live session is the standby controller's job).
    case 'dismiss':
      return s === 'error' ? 'standby' : s

    // Internal: the hook's 30s inactivity timer fired after the machine
    // settled (post-turn listening, a parked recognition badge, the
    // post-barge-in lull, or error's auto-dim per §4.1 row 7 "dims to
    // standby-level").
    case 'standby_timeout':
      switch (s) {
        case 'listening':
        case 'recognized':
        case 'interrupted':
        case 'error':
          return 'standby'
        default:
          return s
      }
  }
}

// -----------------------------------------------------------------------------
// Visual-state mapping (mark component vocabulary)
// -----------------------------------------------------------------------------

/**
 * VoiceVisualState has no 'standby'/'interrupted': standby breathes idle,
 * and `interrupted` reads as `listening` on the mark — spec §4.1 row 6
 * calls the barge-in visual "instant dampening back to Listening posture",
 * so the mark returns to the live, reactive listening shape immediately
 * rather than freezing at thinking.
 */
export function visualStateFor(state: VoiceModeState): VoiceVisualState {
  switch (state) {
    case 'standby':
      return 'idle'
    case 'interrupted':
      return 'listening'
    default:
      return state
  }
}

// -----------------------------------------------------------------------------
// Hook (thin React glue)
// -----------------------------------------------------------------------------

interface UseVoiceModeMachineResult {
  /** Current machine state. */
  state: VoiceModeState
  /** Stable dispatch. Timer bookkeeping is transparent to the caller. */
  dispatch: (event: VoiceModeEvent) => void
  /** Current state mapped onto the mark component's vocabulary. */
  visualState: VoiceVisualState
}

/**
 * React wrapper over `voiceModeReducer`: a stable dispatch plus the 30s
 * standby timer. The timer arms when the machine settles — on
 * `turn_complete` (listening, or a re-recognition during the follow-up),
 * after an `interrupt` (the post-barge-in lull), and on entering `error`
 * (§4.1 row 7 auto-dim) — and every event
 * resets it; only a `standby_timeout` it itself fires can complete the
 * decay to standby.
 */
export function useVoiceModeMachine(): UseVoiceModeMachineResult {
  const [state, rawDispatch] = useReducer(voiceModeReducer, 'standby')

  // Refs mirror the reducer state so the dispatch wrapper can compute the
  // next state synchronously (the reducer is pure) and manage the timer
  // without depending on effect timing.
  const stateRef = useRef<VoiceModeState>(state)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const armedRef = useRef(false)

  useEffect(() => {
    return () => {
      if (timerRef.current !== null) clearTimeout(timerRef.current)
    }
  }, [])

  // apply() holds ALL of the bookkeeping (mirror + timer) so the timer
  // callback can route through the exact same path as a user event —
  // calling rawDispatch directly would leave stateRef/armedRef stale.
  const applyRef = useRef<(event: VoiceModeEvent) => void>(() => undefined)
  applyRef.current = (event: VoiceModeEvent): void => {
    const next = voiceModeReducer(stateRef.current, event)
    stateRef.current = next

    // Any event resets the timer.
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current)
      timerRef.current = null
    }

    // Arm on settle; keep armed across no-op events in a settled state
    // (e.g. a second `wake` while listening), disarm everywhere else. A
    // no-op that never settled (e.g. `interrupt` in listening, `error` in
    // standby) must not start the clock on a live or dimmed screen.
    const settled =
      next === 'listening' || next === 'recognized' || next === 'interrupted' || next === 'error'
    armedRef.current = settled
      ? event.type === 'turn_complete' ||
        next === 'interrupted' || // only reachable via a real interrupt
        next === 'error' || // only reachable via a real error event
        armedRef.current
      : false

    if (armedRef.current) {
      timerRef.current = setTimeout(() => {
        timerRef.current = null
        applyRef.current({ type: 'standby_timeout' })
      }, STANDBY_TIMEOUT_MS)
    }

    rawDispatch(event)
  }

  const dispatch = useCallback((event: VoiceModeEvent): void => {
    applyRef.current(event)
  }, [])

  return { state, dispatch, visualState: visualStateFor(state) }
}