// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * VoiceMode (O7) — the full-screen voice surface (spec doc 15 §6.1).
 *
 * The screen that composes what O1–O6 and O9 built:
 *
 *   - O6 `useVoiceModeMachine` owns the 7-state posture; this page feeds it
 *     from the agent turn stream (`speech_segment` / `modality_resolved` /
 *     `turn_complete`), the being-event acoustic wake (O5), speaker
 *     recognition (O4 via /api/audio/status), and the touch gestures.
 *   - O3 `TtsPlaybackClient` plays the turn's Piper PCM; its `out` gain is
 *     the mark's speaking source.
 *   - O7 `PcmUplink` (lib/pcmCapture) captures the mic to /api/audio/stream;
 *     its MediaStream is the mark's listening source (Decision 1: one
 *     capture graph feeds both the uplink and the visualization).
 *   - O9 `OnScreenKeyboard` and the (future) STT observation channel share
 *     ONE submission path, `submitTurn` — a fresh session id per turn,
 *     exactly what useAgentStream mints per send and what the TTS egress
 *     hub keys on.
 *
 * Session-id contract (the one wire that must not drift): the backend's
 * TTS hub relays `self.ctx.session_id` audio, and `_speak_to_tts_egress`
 * synthesizes ONLY when a subscriber is already connected for that id.
 * useAgentStream mints a fresh id per `sendMessage` call, so this page
 * mints the id itself, connects `TtsPlaybackClient(ttsStreamUrl(sid))`
 * BEFORE `sendMessage(text, sid)`, and rebuilds the client (close ->
 * connect, no auto-reconnect per O3) on every turn.
 *
 * v1 input reality: the STT observation channel is not live (the status
 * endpoint answers WHO spoke, never WHAT was said — pipeline.get_status
 * documents this), so the keyboard is the working input path; a manual
 * end-of-speech with no transcript is an empty turn that completes
 * immediately so the machine cannot park in `thinking` with nothing in
 * flight.
 *
 * Routing is deliberately absent (O8 mounts this page at /voice and wires
 * the Host Canvas edge); `onExitToCanvas` is the seam O8 fills.
 *
 * The dark `bg-black` canvas is the deliberate, scoped divergence from
 * the daylight palette (plan doc 16 Decision 5): the mark is
 * `tone="accent"` vermilion, which reads on black, and text resolves to
 * canvas/ink tokens.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  AudioReactiveHalbertMark,
  createMediaStreamAnalyserSource,
  createNodeAnalyserSource,
} from '@halbert/design-system'
import type { AudioEnergySource } from '@halbert/design-system'
import { Volume2, VolumeX } from 'lucide-react'
import { useVoiceModeMachine } from '@/hooks/useVoiceModeMachine'
import type { VoiceModeState } from '@/hooks/useVoiceModeMachine'
import { useAgentStream } from '@/hooks/useAgentStream'
import type { ModalityInfo, SpeechSegmentEvent } from '@/hooks/useAgentStream'
import { useBeingEvents } from '@/hooks/useBeingEvents'
import { useHostIdentity } from '@/hooks/useHostIdentity'
import { acousticWakeEvent } from '@/hooks/voiceModeEvents'
import { SpeakerBadge } from '@/components/voice/SpeakerBadge'
import type { SpeakerStatus } from '@/components/voice/SpeakerBadge'
import { OnScreenKeyboard } from '@/components/voice/OnScreenKeyboard'
import { SubtitleRibbon } from '@/components/voice/SubtitleRibbon'
import { TouchBar } from '@/components/voice/TouchBar'
import { PcmUplink } from '@/lib/pcmCapture'
import { TtsPlaybackClient, ttsStreamUrl } from '@/lib/ttsPlayback'
import { apiUrl } from '@/lib/apiBase'

/** Coarse-state hydration cadence — the same 2s poll as AcousticAuraIndicator. */
export const STATUS_POLL_MS = 2_000

const EMPTY_SEGMENTS: SpeechSegmentEvent[] = []

/** The universal mark-tap action, labelled for what it does in this state.
 * (Distinct from the TouchBar's "Tap to speak" button so the two controls
 * stay individually addressable.) */
function markTapLabel(state: VoiceModeState): string {
  switch (state) {
    case 'speaking':
      return 'Interrupt speech'
    case 'listening':
    case 'recognized':
      return 'Submit speech'
    case 'thinking':
      return 'Working'
    default:
      return 'Tap the mark to speak'
  }
}

export interface VoiceModeProps {
  /** O8 wires this to the Host Canvas transition; until then the edge is
   * a dead tap by design (routing is not this page's job). */
  onExitToCanvas?: () => void
}

export function VoiceMode({ onExitToCanvas }: VoiceModeProps) {
  const { state, dispatch, visualState } = useVoiceModeMachine()
  const [keyboardOpen, setKeyboardOpen] = useState(false)
  const [muted, setMuted] = useState(false)
  const [speaker, setSpeaker] = useState<SpeakerStatus | null>(null)
  const [micStream, setMicStream] = useState<MediaStream | null>(null)
  const [ttsOut, setTtsOut] = useState<GainNode | null>(null)

  // Refs mirror the latest values for stable event handlers (the machine's
  // dispatch is stable; its state is not, inside a callback closure).
  const stateRef = useRef<VoiceModeState>(state)
  stateRef.current = state
  const mutedRef = useRef(muted)
  mutedRef.current = muted

  const uplinkRef = useRef<PcmUplink | null>(null)
  const ttsRef = useRef<TtsPlaybackClient | null>(null)

  // -------------------------------------------------------------------------
  // Agent turn stream -> machine events
  // -------------------------------------------------------------------------

  const handleStreamError = useCallback(
    (message: string) => dispatch({ type: 'error', message }),
    [dispatch],
  )
  const streamOptions = useMemo(
    () => ({ onError: handleStreamError }),
    [handleStreamError],
  )
  const agent = useAgentStream(streamOptions)

  // isStreaming falling = the turn ended (response_complete / session_ended
  // / error already dispatched separately). O6: turn_complete lands the
  // machine in listening — the 30s timer owns the decay to standby.
  const wasStreamingRef = useRef(false)
  useEffect(() => {
    if (wasStreamingRef.current && !agent.isStreaming) {
      dispatch({ type: 'turn_complete' })
    }
    wasStreamingRef.current = agent.isStreaming
  }, [agent.isStreaming, dispatch])

  // New speech segments (voice delivery) -> speaking. Only segments the
  // effect has not seen dispatch; a new turn's session resets the count.
  const speechSegments = agent.session?.speechSegments ?? EMPTY_SEGMENTS
  const dispatchedSegmentsRef = useRef(0)
  useEffect(() => {
    for (let i = dispatchedSegmentsRef.current; i < speechSegments.length; i++) {
      dispatch({ type: 'speech_segment', segment: speechSegments[i] })
    }
    dispatchedSegmentsRef.current = speechSegments.length
  }, [speechSegments, dispatch])

  // The modality decision is informational (O6: it changes no state alone;
  // speaking needs the first segment), but the machine event exists so the
  // full turn mapping stays in one place.
  const modality: ModalityInfo | null = agent.session?.modality ?? null
  const lastModalityRef = useRef<ModalityInfo | null>(null)
  useEffect(() => {
    if (modality && modality !== lastModalityRef.current) {
      lastModalityRef.current = modality
      dispatch({ type: 'modality_resolved', modality: modality.modality })
    } else if (!modality) {
      lastModalityRef.current = null
    }
  }, [modality, dispatch])

  // -------------------------------------------------------------------------
  // Being events (O5 acoustic wake) + speaker recognition (O4)
  // -------------------------------------------------------------------------

  const { events: beingEvents } = useBeingEvents()
  // One dispatch per event id: the being-event list is cumulative (up to
  // 100), so re-rendering after any later event must not re-fire an old
  // anomaly's wake — that would stomp a turn already speaking.
  const wokenEventIdsRef = useRef<Set<string>>(new Set())
  useEffect(() => {
    for (const event of beingEvents) {
      if (wokenEventIdsRef.current.has(event.id)) continue
      const wake = acousticWakeEvent(event)
      if (wake) {
        wokenEventIdsRef.current.add(event.id)
        dispatch(wake)
      }
    }
  }, [beingEvents, dispatch])

  // Poll /api/audio/status for the last identified speaker (the same
  // pattern as AcousticAuraIndicator; SSE carries the realtime stream).
  useEffect(() => {
    let mounted = true
    const poll = async () => {
      try {
        const resp = await fetch(apiUrl('/api/audio/status'))
        if (!resp.ok) return
        const parsed = (await resp.json()) as { speaker?: SpeakerStatus | null }
        if (mounted) setSpeaker(parsed.speaker ?? null)
      } catch {
        // The badge is non-critical; a failed poll is not an error state.
      }
    }
    void poll()
    const timer = setInterval(poll, STATUS_POLL_MS)
    return () => {
      mounted = false
      clearInterval(timer)
    }
  }, [])

  // A NEW identification (name|role|confidence) dispatches
  // speaker_recognized — the 2s poll repeats the same observation and must
  // not re-fire it.
  const lastSpeakerKeyRef = useRef<string | null>(null)
  useEffect(() => {
    if (!speaker) {
      lastSpeakerKeyRef.current = null
      return
    }
    const key = `${speaker.name}|${speaker.role}|${speaker.confidence}`
    if (key === lastSpeakerKeyRef.current) return
    lastSpeakerKeyRef.current = key
    dispatch({
      type: 'speaker_recognized',
      name: speaker.name,
      role: speaker.role,
      confidence: speaker.confidence,
    })
  }, [speaker, dispatch])

  // -------------------------------------------------------------------------
  // Mic capture (push-to-talk)
  // -------------------------------------------------------------------------

  const ensureUplink = useCallback(async () => {
    const existing = uplinkRef.current
    if (existing && existing.state === 'running') return
    existing?.stop() // a stopped/failed uplink is rebuilt, not reused
    const uplink = new PcmUplink({
      onError: (message) => dispatch({ type: 'error', message }),
    })
    uplinkRef.current = uplink
    await uplink.start()
    if (uplink.state === 'running') {
      setMicStream(uplink.getStream())
    }
  }, [dispatch])

  const beginPushToTalk = useCallback(async () => {
    dispatch({ type: 'wake' })
    if (mutedRef.current) return
    await ensureUplink()
  }, [dispatch, ensureUplink])

  const toggleMute = useCallback(() => {
    if (mutedRef.current) {
      setMuted(false)
      // Restore capture only when the machine is actually in a mic
      // posture; unmuting at standby must not open a surprise mic.
      const s = stateRef.current
      if (s === 'listening' || s === 'recognized' || s === 'interrupted') {
        void ensureUplink()
      }
    } else {
      setMuted(true)
      uplinkRef.current?.stop()
      setMicStream(null)
    }
  }, [ensureUplink])

  // -------------------------------------------------------------------------
  // Turn submission — one path for keyboard and (future) STT
  // -------------------------------------------------------------------------

  const submitTurn = useCallback(
    (text: string) => {
      const trimmed = text.trim()
      if (!trimmed) return
      const sessionId = crypto.randomUUID()
      // Subscribe BEFORE the turn starts: the egress hub synthesizes only
      // when a subscriber exists for this session id, and the id is
      // per-turn — so every turn rebuilds the client (close -> connect;
      // O3 has no auto-reconnect by design).
      ttsRef.current?.close()
      const client = new TtsPlaybackClient(ttsStreamUrl(sessionId))
      client.connect()
      ttsRef.current = client
      setTtsOut(client.out)
      // The keyboard enters the machine exactly as a spoken turn does:
      // wake (standby -> listening) then end-of-speech (-> thinking).
      // Both are no-ops where the machine is already past those postures.
      dispatch({ type: 'wake' })
      dispatch({ type: 'vad_end' })
      agent.sendMessage(trimmed, sessionId)
    },
    [agent.sendMessage, dispatch],
  )

  const endOfSpeech = useCallback(() => {
    dispatch({ type: 'vad_end' })
    // v1: the STT observation channel is not live, so a manual
    // end-of-speech has no transcript to submit — the empty turn
    // completes immediately rather than parking the machine in `thinking`
    // with nothing in flight. When STT lands, the transcript submission
    // slots in right here (submitTurn(transcript)).
    dispatch({ type: 'turn_complete' })
  }, [dispatch])

  const handleMarkTap = useCallback(() => {
    switch (stateRef.current) {
      case 'speaking':
        ttsRef.current?.cancel()
        dispatch({ type: 'interrupt' })
        break
      case 'standby':
      case 'interrupted': // dampened back to the listening posture
      case 'error': // explicit retry
        void beginPushToTalk()
        break
      case 'listening':
      case 'recognized':
        endOfSpeech()
        break
      default:
        break // thinking: a turn is in flight; the tap is a no-op
    }
  }, [beginPushToTalk, dispatch, endOfSpeech])

  // -------------------------------------------------------------------------
  // Mark energy sources (Decision 1)
  // -------------------------------------------------------------------------

  const micSource = useMemo<AudioEnergySource | null>(
    () => (micStream ? createMediaStreamAnalyserSource(micStream) : null),
    [micStream],
  )
  const speakingSource = useMemo<AudioEnergySource | null>(
    () => (ttsOut ? createNodeAnalyserSource(ttsOut) : null),
    [ttsOut],
  )
  const markSource: AudioEnergySource | null =
    state === 'listening' || state === 'recognized' || state === 'interrupted'
      ? micSource
      : state === 'speaking'
        ? speakingSource
        : null

  // -------------------------------------------------------------------------
  // Teardown
  // -------------------------------------------------------------------------

  useEffect(() => {
    return () => {
      uplinkRef.current?.stop()
      ttsRef.current?.close()
    }
  }, [])

  // -------------------------------------------------------------------------
  // Layout (spec §6.1)
  // -------------------------------------------------------------------------

  const { identity } = useHostIdentity()

  return (
    <div className="flex h-screen w-full flex-col bg-black text-canvas">
      <header className="flex items-center justify-between gap-4 px-6 py-4">
        <SpeakerBadge speaker={speaker} />
        <span className="truncate text-sm uppercase tracking-wide text-canvas/60">
          {identity?.display_name ?? ''}
        </span>
        <button
          type="button"
          onClick={toggleMute}
          aria-label={muted ? 'Unmute microphone' : 'Mute microphone'}
          className="flex h-12 w-12 items-center justify-center rounded-full border border-hairline text-canvas/70 transition-colors hover:bg-canvas/10 focus:outline-none focus-visible:ring-2 focus-visible:ring-focus"
        >
          {muted ? (
            <VolumeX className="h-5 w-5" aria-hidden="true" />
          ) : (
            <Volume2 className="h-5 w-5" aria-hidden="true" />
          )}
        </button>
      </header>

      <main className="relative flex flex-1 items-center justify-center">
        <button
          type="button"
          onClick={handleMarkTap}
          aria-label={markTapLabel(state)}
          className="flex items-center justify-center rounded-full focus:outline-none focus-visible:ring-2 focus-visible:ring-focus"
        >
          <AudioReactiveHalbertMark
            size={512}
            tone="accent"
            state={visualState}
            source={markSource}
          />
        </button>
      </main>

      <SubtitleRibbon segments={speechSegments} active={state === 'speaking'} />

      <TouchBar
        onPushToTalk={() => void beginPushToTalk()}
        onKeyboard={() => setKeyboardOpen(true)}
        onHostCanvas={onExitToCanvas ?? (() => undefined)}
      />

      {keyboardOpen && (
        <OnScreenKeyboard
          onSend={(text) => {
            setKeyboardOpen(false)
            submitTurn(text)
          }}
          onDismiss={() => setKeyboardOpen(false)}
          onMic={() => {
            setKeyboardOpen(false)
            void beginPushToTalk()
          }}
        />
      )}
    </div>
  )
}

export default VoiceMode
