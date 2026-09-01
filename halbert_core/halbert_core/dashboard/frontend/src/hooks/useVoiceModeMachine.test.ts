// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * Tests for the O6 voice-mode state machine (useVoiceModeMachine).
 *
 * The core contract is an exhaustive state×event transition matrix pinned
 * to spec doc 15 §4 (mermaid diagram) as corrected by plan doc 16 §1.2:
 * `listening` is entered locally on wake/PTT, `thinking` on end-of-speech,
 * `speaking` on the first speech segment of a voice/mixed turn, and
 * `standby` is reached after the hook's 30s inactivity timer (not in the
 * reducer). The matrix is table-driven: every cell is asserted, so an
 * undocumented transition cannot slip in silently.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import {
  voiceModeReducer,
  useVoiceModeMachine,
  visualStateFor,
  VOICE_MODE_STATES,
  STANDBY_TIMEOUT_MS,
} from './useVoiceModeMachine'
import type { VoiceModeState, VoiceModeEvent } from './useVoiceModeMachine'
import type { VoiceVisualState } from '@halbert/design-system'
import type { SpeechSegmentEvent } from './useAgentStream'

const ALL_STATES: VoiceModeState[] = [
  'standby',
  'listening',
  'recognized',
  'thinking',
  'speaking',
  'interrupted',
  'error',
]

const SEGMENT: SpeechSegmentEvent = {
  text: 'Storage is at sixty percent.',
  role: 'persona',
  prosody: { rate: 1, volume: 0.8, whisper: false },
}

/** One representative payload per parameterised event type. */
function eventFor(type: VoiceModeEvent['type']): VoiceModeEvent {
  switch (type) {
    case 'wake':
      return { type: 'wake' }
    case 'vad_end':
      return { type: 'vad_end' }
    case 'speaker_recognized':
      return { type: 'speaker_recognized', name: 'Eric', role: 'admin', confidence: 0.98 }
    case 'modality_resolved':
      return { type: 'modality_resolved', modality: 'voice' }
    case 'speech_segment':
      return { type: 'speech_segment', segment: SEGMENT }
    case 'turn_complete':
      return { type: 'turn_complete' }
    case 'interrupt':
      return { type: 'interrupt' }
    case 'error':
      return { type: 'error', message: 'mic ingress disconnect' }
    case 'dismiss':
      return { type: 'dismiss' }
    case 'acoustic_wake':
      return { type: 'acoustic_wake', soundClass: 'smoke_alarm', severity: 3, urgency: 'critical' }
    case 'standby_timeout':
      return { type: 'standby_timeout' }
  }
}

const EVENT_TYPES = [
  'wake',
  'vad_end',
  'speaker_recognized',
  'modality_resolved',
  'speech_segment',
  'turn_complete',
  'interrupt',
  'error',
  'dismiss',
  'acoustic_wake',
  'standby_timeout',
] as const

/**
 * The spec §4 transition matrix (rows = current state, cols = event type).
 * Every unspecified cell is a deliberate no-op; the explicit cells below
 * comment which spec edge (or plan-corrected behaviour) they pin.
 */
const TRANSITIONS: Record<VoiceModeState, Partial<Record<VoiceModeEvent['type'], VoiceModeState>>> = {
  standby: {
    wake: 'listening', // Standby -> Listening: wake word / screen tap / PTT
    acoustic_wake: 'listening', // O5 seam: forced wake from ANY state, incl. standby
  },
  listening: {
    vad_end: 'thinking', // Listening -> Thinking: voice activity ceases
    speaker_recognized: 'recognized', // Listening -> Recognized: biometric match
    error: 'error', // Listening -> Error: mic failure / ingress disconnect
    acoustic_wake: 'listening', // already awake; stays listening (no darker state to escape)
    standby_timeout: 'standby', // hook timer: 30s without events after a settled state
  },
  recognized: {
    vad_end: 'thinking', // Recognized -> Thinking: confirmed identity, continue turn
    speaker_recognized: 'recognized', // repeat match: hold the badge
    wake: 'recognized', // re-tap while mic live: keep the identity badge
    error: 'error',
    acoustic_wake: 'listening', // forced wake drops the parked badge, mic live
    standby_timeout: 'standby',
  },
  thinking: {
    speech_segment: 'speaking', // Thinking -> Speaking: first segment of a voice/mixed turn
    turn_complete: 'listening', // stream ended (text-only turn): back to live listening
    error: 'error', // Thinking -> Error: LLM timeout / tool exception
    acoustic_wake: 'listening', // alarm overrides the turn visually (O5: any state)
    // no standby_timeout: a turn is in flight — thinking never decays
  },
  speaking: {
    interrupt: 'interrupted', // Speaking -> Interrupted: barge-in / mark tap
    speech_segment: 'speaking', // subsequent segments of the same utterance
    turn_complete: 'listening', // Speaking -> Listening: continuous multi-turn
    error: 'error',
    acoustic_wake: 'listening', // alarm overrides playback visually (O5: any state)
    // no standby_timeout: audio is actively playing — speaking never decays
  },
  interrupted: {
    wake: 'listening', // back to Listening posture (spec §4.1 row 6) on the next wake
    vad_end: 'thinking', // the new utterance that caused the barge-in is captured
    turn_complete: 'listening', // the interrupted turn ended during the lull
    error: 'error',
    acoustic_wake: 'listening',
    standby_timeout: 'standby',
  },
  error: {
    dismiss: 'standby', // Error -> Standby: user dismissal
    wake: 'listening', // explicit retry: user acts, mic live again
    acoustic_wake: 'listening',
    standby_timeout: 'standby', // auto: dims to standby-level (spec §4.1 row 7)
  },
}

describe('voiceModeReducer — exhaustive transition matrix', () => {
  it('covers all 7 states', () => {
    expect([...VOICE_MODE_STATES].sort()).toEqual([...ALL_STATES].sort())
    for (const s of ALL_STATES) expect(TRANSITIONS[s]).toBeDefined()
  })

  it('maps every state×event cell exactly as the table says', () => {
    for (const state of ALL_STATES) {
      for (const type of EVENT_TYPES) {
        const expected = TRANSITIONS[state][type] ?? state // unspecified = no-op
        const next = voiceModeReducer(state, eventFor(type))
        expect(next, `transition ${state} --${type}--> ${next}`).toBe(expected)
      }
    }
  })

  it('keeps standby dark: a stray speech_segment must not enter speaking', () => {
    expect(voiceModeReducer('standby', { type: 'speech_segment', segment: SEGMENT })).toBe('standby')
    expect(voiceModeReducer('standby', { type: 'turn_complete' })).toBe('standby')
    expect(voiceModeReducer('standby', { type: 'dismiss' })).toBe('standby')
    expect(voiceModeReducer('standby', { type: 'error', message: 'x' })).toBe('standby')
  })

  it('does not enter speaking from listening on speech_segment (thinking is required first)', () => {
    expect(voiceModeReducer('listening', { type: 'speech_segment', segment: SEGMENT })).toBe('listening')
  })

  it('absorbs the O5 acoustic_wake seam: forced wake from ANY state including standby', () => {
    for (const state of ALL_STATES) {
      expect(
        voiceModeReducer(state, { type: 'acoustic_wake', soundClass: 'glass_break', severity: 3, urgency: 'critical' }),
      ).toBe('listening')
      expect(
        voiceModeReducer(state, { type: 'acoustic_wake', soundClass: 'smoke_alarm', severity: 2, urgency: 'urgent' }),
      ).toBe('listening')
    }
  })
})

describe('voiceModeReducer — documented conflicts and choices', () => {
  it('modality_resolved alone never enters speaking (plan: segment + modality both required)', () => {
    for (const modality of ['text', 'voice', 'mixed', 'deferred'] as const) {
      expect(voiceModeReducer('thinking', { type: 'modality_resolved', modality })).toBe('thinking')
      expect(voiceModeReducer('listening', { type: 'modality_resolved', modality })).toBe('listening')
    }
  })

  it('wake during thinking/speaking is a no-op (interrupt owns the speaking tap; turn in flight)', () => {
    expect(voiceModeReducer('thinking', { type: 'wake' })).toBe('thinking')
    expect(voiceModeReducer('speaking', { type: 'wake' })).toBe('speaking')
  })

  it('interrupt only bites during speaking (barge-in is a speaking-state event)', () => {
    expect(voiceModeReducer('speaking', { type: 'interrupt' })).toBe('interrupted')
    expect(voiceModeReducer('thinking', { type: 'interrupt' })).toBe('thinking')
    expect(voiceModeReducer('listening', { type: 'interrupt' })).toBe('listening')
    expect(voiceModeReducer('standby', { type: 'interrupt' })).toBe('standby')
  })

  it('error is ignored while in standby (dimmed screen must not flash awake; acoustic_wake exists for that)', () => {
    expect(voiceModeReducer('standby', { type: 'error', message: 'x' })).toBe('standby')
  })

  it('dismiss only leaves error (the only dismissal edge the spec names)', () => {
    expect(voiceModeReducer('error', { type: 'dismiss' })).toBe('standby')
    expect(voiceModeReducer('listening', { type: 'dismiss' })).toBe('listening')
    expect(voiceModeReducer('speaking', { type: 'dismiss' })).toBe('speaking')
  })

  it('vad_end from interrupted starts a new turn (the barge-in utterance is captured)', () => {
    expect(voiceModeReducer('interrupted', { type: 'vad_end' })).toBe('thinking')
  })
})

describe('visualStateFor', () => {
  it('maps the 7 machine states onto the mark vocabulary (no standby/interrupted there)', () => {
    const mapping: Record<VoiceModeState, VoiceVisualState> = {
      standby: 'idle',
      listening: 'listening',
      recognized: 'recognized',
      thinking: 'thinking',
      speaking: 'speaking',
      interrupted: 'listening', // §4.1 row 6: instant dampening back to Listening posture
      error: 'error',
    }
    for (const [state, visual] of Object.entries(mapping)) {
      expect(visualStateFor(state as VoiceModeState)).toBe(visual)
    }
  })
})

describe('useVoiceModeMachine — 30s standby timer', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('starts in standby and never arms the timer there', () => {
    const { result } = renderHook(() => useVoiceModeMachine())
    expect(result.current.state).toBe('standby')

    act(() => {
      result.current.dispatch({ type: 'turn_complete' })
    })
    expect(result.current.state).toBe('standby')

    act(() => {
      vi.advanceTimersByTime(STANDBY_TIMEOUT_MS + 1_000)
    })
    expect(result.current.state).toBe('standby')
  })

  it('decays to standby 30s after turn_complete (via listening)', () => {
    const { result } = renderHook(() => useVoiceModeMachine())

    act(() => {
      // Drive to speaking the way the streams do, then end the turn.
      result.current.dispatch({ type: 'wake' })
      result.current.dispatch({ type: 'vad_end' })
      result.current.dispatch({ type: 'speaker_recognized', name: 'Eric', role: 'admin', confidence: 0.98 })
      result.current.dispatch({ type: 'speech_segment', segment: SEGMENT })
    })
    expect(result.current.state).toBe('speaking')

    act(() => {
      result.current.dispatch({ type: 'turn_complete' })
    })
    expect(result.current.state).toBe('listening')

    act(() => {
      vi.advanceTimersByTime(STANDBY_TIMEOUT_MS - 1_000)
    })
    expect(result.current.state).toBe('listening')

    act(() => {
      vi.advanceTimersByTime(1_000)
    })
    expect(result.current.state).toBe('standby')
  })

  it('resets the timer on any event: a wake inside the window keeps the machine alive', () => {
    const { result } = renderHook(() => useVoiceModeMachine())

    act(() => {
      result.current.dispatch({ type: 'wake' })
      result.current.dispatch({ type: 'vad_end' })
      result.current.dispatch({ type: 'speech_segment', segment: SEGMENT })
      result.current.dispatch({ type: 'turn_complete' })
    })
    expect(result.current.state).toBe('listening')

    act(() => {
      vi.advanceTimersByTime(20_000)
    })

    act(() => {
      result.current.dispatch({ type: 'wake' }) // second PTT tap within the window
    })
    expect(result.current.state).toBe('listening')

    act(() => {
      vi.advanceTimersByTime(29_000) // 29s after the reset, past the original deadline
    })
    expect(result.current.state).toBe('listening')

    act(() => {
      vi.advanceTimersByTime(1_000)
    })
    expect(result.current.state).toBe('standby')
  })

  it('disarms when the machine leaves the settled state before the timer fires', () => {
    const { result } = renderHook(() => useVoiceModeMachine())

    act(() => {
      result.current.dispatch({ type: 'wake' })
      result.current.dispatch({ type: 'vad_end' })
      result.current.dispatch({ type: 'speech_segment', segment: SEGMENT })
      result.current.dispatch({ type: 'turn_complete' })
    })

    act(() => {
      vi.advanceTimersByTime(10_000)
    })

    act(() => {
      result.current.dispatch({ type: 'vad_end' }) // second turn begins
    })
    expect(result.current.state).toBe('thinking')

    act(() => {
      vi.advanceTimersByTime(60_000)
    })
    expect(result.current.state).toBe('thinking')
  })

  it('decays interrupted -> standby after 30s (post-barge-in lull dims the idle mic)', () => {
    const { result } = renderHook(() => useVoiceModeMachine())

    act(() => {
      result.current.dispatch({ type: 'wake' })
      result.current.dispatch({ type: 'vad_end' })
      result.current.dispatch({ type: 'speech_segment', segment: SEGMENT })
      result.current.dispatch({ type: 'interrupt' })
    })
    expect(result.current.state).toBe('interrupted')

    act(() => {
      vi.advanceTimersByTime(STANDBY_TIMEOUT_MS)
    })
    expect(result.current.state).toBe('standby')
  })

  it('decays error -> standby after 30s (auto-dim per §4.1 row 7) and dismiss goes immediately', () => {
    const { result } = renderHook(() => useVoiceModeMachine())

    act(() => {
      result.current.dispatch({ type: 'wake' })
      result.current.dispatch({ type: 'error', message: 'ingress disconnect' })
    })
    expect(result.current.state).toBe('error')

    const second = renderHook(() => useVoiceModeMachine())
    act(() => {
      second.result.current.dispatch({ type: 'wake' })
      second.result.current.dispatch({ type: 'error', message: 'ingress disconnect' })
      second.result.current.dispatch({ type: 'dismiss' })
    })
    expect(second.result.current.state).toBe('standby')

    act(() => {
      vi.advanceTimersByTime(STANDBY_TIMEOUT_MS)
    })
    expect(result.current.state).toBe('standby')
  })

  it('keeps reducing from the true base after the timer fires (stale-mirror regression)', () => {
    const { result } = renderHook(() => useVoiceModeMachine())

    act(() => {
      result.current.dispatch({ type: 'wake' })
      result.current.dispatch({ type: 'vad_end' })
      result.current.dispatch({ type: 'speech_segment', segment: SEGMENT })
      result.current.dispatch({ type: 'turn_complete' })
    })

    act(() => {
      vi.advanceTimersByTime(STANDBY_TIMEOUT_MS)
    })
    expect(result.current.state).toBe('standby')

    // From standby, vad_end is a no-op. If the timer's internal dispatch
    // had bypassed the bookkeeping, the mirror would still say 'listening'
    // and this would wrongly enter thinking.
    act(() => {
      result.current.dispatch({ type: 'vad_end' })
    })
    expect(result.current.state).toBe('standby')
  })

  it('clears the timer on unmount (no pending timer survives the cleanup)', () => {
    const { result, unmount } = renderHook(() => useVoiceModeMachine())

    act(() => {
      result.current.dispatch({ type: 'wake' })
      result.current.dispatch({ type: 'vad_end' })
      result.current.dispatch({ type: 'speech_segment', segment: SEGMENT })
      result.current.dispatch({ type: 'turn_complete' })
    })
    // The settle armed exactly one pending standby timer.
    expect(vi.getTimerCount()).toBe(1)

    unmount()
    // Deleting the useEffect cleanup leaves the fake timer alive; React 18
    // no longer warns on setState-after-unmount, so the surviving callback
    // is the only observable difference.
    expect(vi.getTimerCount()).toBe(0)
    act(() => {
      vi.advanceTimersByTime(STANDBY_TIMEOUT_MS + 1_000)
    })
    expect(result.current.state).toBe('listening')
  })

  it('does not arm the timer on a plain wake (standby PTT press keeps listening alive)', () => {
    const { result } = renderHook(() => useVoiceModeMachine())

    act(() => {
      result.current.dispatch({ type: 'wake' })
    })
    expect(result.current.state).toBe('listening')
    // The 30s clock belongs to settled turns / errors, not a fresh PTT
    // session — arming here would dim a live mic the user just opened.
    expect(vi.getTimerCount()).toBe(0)

    act(() => {
      vi.advanceTimersByTime(STANDBY_TIMEOUT_MS + 1_000)
    })
    expect(result.current.state).toBe('listening')
  })

  it('does not arm the timer on a stale turn_complete in a fresh listening session', () => {
    const { result } = renderHook(() => useVoiceModeMachine())

    act(() => {
      result.current.dispatch({ type: 'wake' })
    })
    // A late/stale turn_complete — e.g. a previous turn's stream-end racing a
    // new push-to-talk, or O7 dispatching on isStreaming false at mount —
    // no-ops in the reducer and must not start the dim clock on the live mic.
    act(() => {
      result.current.dispatch({ type: 'turn_complete' })
    })
    expect(result.current.state).toBe('listening')
    expect(vi.getTimerCount()).toBe(0)

    act(() => {
      vi.advanceTimersByTime(STANDBY_TIMEOUT_MS + 1_000)
    })
    expect(result.current.state).toBe('listening')
  })

  it('exposes visualStateFor-derived visual state that follows the machine', () => {
    const { result } = renderHook(() => useVoiceModeMachine())

    expect(result.current.visualState).toBe('idle')

    act(() => {
      result.current.dispatch({ type: 'wake' })
    })
    expect(result.current.visualState).toBe('listening')

    act(() => {
      result.current.dispatch({ type: 'interrupt' }) // no-op in listening
      result.current.dispatch({ type: 'vad_end' })
    })
    expect(result.current.visualState).toBe('thinking')

    act(() => {
      result.current.dispatch({ type: 'error', message: 'x' })
    })
    expect(result.current.visualState).toBe('error')
  })
})
