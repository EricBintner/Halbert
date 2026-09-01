// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * VoiceMode (O7): the full-screen voice surface. Every collaborator is
 * stubbed at its module boundary (the hooks, the audio clients, the
 * design-system sources) so these tests pin the COMPOSITION contract —
 * state -> source switching on the mark, tap handling per machine state,
 * the TTS session-id subscription lifecycle, the turn submission path
 * shared by keyboard and (future) STT, and the being-event wake seam.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, act, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { VoiceMode, STATUS_POLL_MS } from './VoiceMode'
import {
  AudioReactiveHalbertMark,
  createMediaStreamAnalyserSource,
  createNodeAnalyserSource,
} from '@halbert/design-system'
import type { AudioEnergySource } from '@halbert/design-system'
import type { SpeechSegmentEvent, ModalityInfo } from '@/hooks/useAgentStream'

// ---------------------------------------------------------------------------
// Module-boundary stubs
// ---------------------------------------------------------------------------

const MIC_STREAM = { '0': 'mic-stream' }

const h = vi.hoisted(() => {
  return {
    machine: null as null | { state: string; dispatch: ReturnType<typeof vi.fn>; visualState: string },
    agent: null as null | {
      session: { speechSegments?: SpeechSegmentEvent[]; modality?: ModalityInfo | null } | null
      isStreaming: boolean
      sendMessage: ReturnType<typeof vi.fn>
    },
    agentOptions: null as null | { onError?: (message: string) => void },
    beingEvents: [] as Array<Record<string, unknown>>,
    identity: null as null | { display_name: string },
    tts: [] as Array<{ url: string; out: unknown; connect: ReturnType<typeof vi.fn>; cancel: ReturnType<typeof vi.fn>; close: ReturnType<typeof vi.fn> }>,
    uplinks: [] as Array<{ start: ReturnType<typeof vi.fn>; stop: ReturnType<typeof vi.fn>; state: string; getStream: () => unknown }>,
    uplinkOptions: [] as Array<{ onError?: (message: string) => void }>,
  }
})

vi.mock('@/hooks/useVoiceModeMachine', () => ({
  useVoiceModeMachine: () => h.machine,
}))

vi.mock('@/hooks/useAgentStream', () => ({
  useAgentStream: (opts: unknown) => {
    h.agentOptions = opts as { onError?: (message: string) => void }
    return h.agent
  },
}))

// isAcousticEvent is re-implemented here (not mocked away) so the REAL
// acousticWakeEvent seam in voiceModeEvents runs against these events.
vi.mock('@/hooks/useBeingEvents', () => ({
  useBeingEvents: () => ({ events: h.beingEvents }),
  isAcousticEvent: (e: { type?: string; category?: string }) =>
    e.type === 'acoustic' || e.category === 'acoustic',
}))

vi.mock('@/hooks/useHostIdentity', () => ({
  useHostIdentity: () => ({ identity: h.identity, loading: false, error: null }),
}))

vi.mock('@/lib/ttsPlayback', () => ({
  ttsStreamUrl: (sid: string) => `tts://${sid}`,
  TtsPlaybackClient: class {
    url: string
    out = { node: 'tts-out' }
    connect = vi.fn()
    cancel = vi.fn()
    close = vi.fn()
    constructor(url: string) {
      this.url = url
      h.tts.push(this)
    }
  },
}))

vi.mock('@/lib/pcmCapture', () => ({
  PcmUplink: class {
    started = false
    start = vi.fn(async () => {
      this.started = true
    })
    stop = vi.fn(() => {
      this.started = false
    })
    get state() {
      return this.started ? 'running' : 'stopped'
    }
    getStream() {
      return this.started ? MIC_STREAM : null
    }
    constructor(opts: unknown) {
      h.uplinks.push(this)
      h.uplinkOptions.push(opts as { onError?: (message: string) => void })
    }
  },
}))

vi.mock('@halbert/design-system', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>()
  return {
    ...actual,
    AudioReactiveHalbertMark: vi.fn(() => null),
    createMediaStreamAnalyserSource: vi.fn((stream: unknown) => ({ kind: 'mic', stream })),
    createNodeAnalyserSource: vi.fn((node: unknown) => ({ kind: 'tts', node })),
  }
})

// ---------------------------------------------------------------------------
// Harness
// ---------------------------------------------------------------------------

const SEGMENT: SpeechSegmentEvent = {
  text: 'Storage is at sixty percent.',
  role: 'persona',
  prosody: { rate: 1, volume: 0.8, whisper: false },
}

type StubResponse = { ok: boolean; status?: number; json: () => Promise<unknown> }

const fetchMock = vi.fn(async (): Promise<StubResponse> => ({
  ok: false,
  status: 503,
  json: async () => ({}),
}))

function setMachine(state: string, visualState: string) {
  h.machine = { state, dispatch: vi.fn(), visualState }
}

function setAgent(overrides: Partial<NonNullable<typeof h.agent>> = {}) {
  h.agent = {
    session: null,
    isStreaming: false,
    sendMessage: vi.fn(),
    ...overrides,
  }
}

/** Render with the current stub state; re-render after mutating `h`.
 * Every rerender builds a FRESH element — React bails out of re-rendering
 * when handed the identical element reference. */
function mount(props: { onExitToCanvas?: () => void } = {}) {
  const make = () => <VoiceMode {...props} />
  const view = render(make())
  return {
    view,
    dispatch: () => h.machine!.dispatch,
    markProps: () => vi.mocked(AudioReactiveHalbertMark).mock.lastCall?.[0] as Record<string, unknown>,
    rerender: () => view.rerender(make()),
  }
}

function dispatchedTypes(): string[] {
  return h.machine!.dispatch.mock.calls.map((c) => (c[0] as { type: string }).type)
}

beforeEach(() => {
  vi.clearAllMocks()
  // setup.ts's restoreAllMocks can reset vi.fn implementations between
  // tests; re-establish the design-system stubs every time.
  vi.mocked(AudioReactiveHalbertMark).mockImplementation(() => null)
  vi.mocked(createMediaStreamAnalyserSource).mockImplementation(
    ((stream: unknown) => ({ kind: 'mic', stream })) as unknown as () => AudioEnergySource,
  )
  vi.mocked(createNodeAnalyserSource).mockImplementation(
    ((node: unknown) => ({ kind: 'tts', node })) as unknown as () => AudioEnergySource,
  )
  setMachine('standby', 'idle')
  setAgent()
  h.agentOptions = null
  h.beingEvents = []
  h.identity = null
  h.tts = []
  h.uplinks = []
  h.uplinkOptions = []
  vi.stubGlobal('fetch', fetchMock)
  fetchMock.mockClear()
  fetchMock.mockResolvedValue({ ok: false, status: 503, json: async () => ({}) })
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

// ---------------------------------------------------------------------------
// Layout (spec §6.1)
// ---------------------------------------------------------------------------

describe('VoiceMode layout', () => {
  it('renders the 512px accent mark, the touch bar, and the mute control', () => {
    mount()
    const props = vi.mocked(AudioReactiveHalbertMark).mock.lastCall?.[0] as Record<string, unknown>
    expect(props.size).toBe(512)
    expect(props.tone).toBe('accent')
    expect(screen.getByRole('button', { name: 'Tap the mark to speak' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Tap to speak' })).toBeTruthy() // TouchBar
    expect(screen.getByRole('button', { name: 'Host canvas' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Mute microphone' })).toBeTruthy()
  })

  it('hides the speaker badge until recognition arrives, then shows it', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({ speaker: { name: 'Eric', role: 'admin', confidence: 0.93 } }),
    })
    const { view } = mount()
    expect(view.container.textContent).not.toContain('Eric')

    await waitFor(() => expect(view.container.textContent).toContain('Eric'))
    expect(view.container.textContent).toContain('93%')
  })

  it('labels the area with the host display name, never the hostname', () => {
    h.identity = { display_name: 'Attic Sentinel' }
    const { view } = mount()
    expect(view.container.textContent).toContain('Attic Sentinel')
  })

  it('is the deliberately dark canvas with token text (plan Decision 5)', () => {
    const { view } = mount()
    const html = view.container.innerHTML
    expect(html).toContain('bg-black')
    for (const banned of ['text-white', 'orange-500', 'purple-500', '#F7F5F0', '#D34E24']) {
      expect(html).not.toContain(banned)
    }
  })

  it('creates no TTS subscription before the first turn', () => {
    mount()
    expect(h.tts).toHaveLength(0)
  })
})

// ---------------------------------------------------------------------------
// Mark source switching (Decision 1)
// ---------------------------------------------------------------------------

describe('mark source switching', () => {
  it('standby breathes idle: no source', () => {
    mount()
    expect(mountMarkSource()).toBe(null)
  })

  it('listening visualizes the mic stream the uplink captures', async () => {
    const user = userEvent.setup()
    const m = mount()
    await user.click(screen.getByRole('button', { name: 'Tap the mark to speak' }))

    // PTT started capture; the machine woke to listening.
    setMachine('listening', 'listening')
    m.rerender()

    expect(createMediaStreamAnalyserSource).toHaveBeenCalledWith(MIC_STREAM)
    expect(mountMarkSource()).toEqual({ kind: 'mic', stream: MIC_STREAM })
  })

  it('speaking visualizes the TTS playback tap', async () => {
    const user = userEvent.setup()
    setMachine('standby', 'idle')
    const m = mount()
    await sendChip(user, m)

    setMachine('speaking', 'speaking')
    m.rerender()

    expect(createNodeAnalyserSource).toHaveBeenCalledWith(h.tts[0].out)
    expect(mountMarkSource()).toEqual({ kind: 'tts', node: h.tts[0].out })
  })

  it('thinking and standby fall back to idle breathing', async () => {
    const user = userEvent.setup()
    const m = mount()
    await user.click(screen.getByRole('button', { name: 'Tap the mark to speak' }))

    setMachine('thinking', 'thinking')
    m.rerender()
    expect(mountMarkSource()).toBe(null)

    setMachine('standby', 'idle')
    m.rerender()
    expect(mountMarkSource()).toBe(null)
  })

  it('interrupted keeps the mic posture (barge-in dampens, mic stays live)', async () => {
    const user = userEvent.setup()
    const m = mount()
    await user.click(screen.getByRole('button', { name: 'Tap the mark to speak' }))

    setMachine('interrupted', 'listening')
    m.rerender()
    expect(mountMarkSource()).toEqual({ kind: 'mic', stream: MIC_STREAM })
  })
})

function mountMarkSource(): unknown {
  const props = vi.mocked(AudioReactiveHalbertMark).mock.lastCall?.[0] as Record<string, unknown>
  return props.source
}

// ---------------------------------------------------------------------------
// Mark tap handling (spec §6.2(1))
// ---------------------------------------------------------------------------

describe('mark tap handling', () => {
  it('speaking: cancels TTS playback and interrupts the machine', async () => {
    const user = userEvent.setup()
    setMachine('speaking', 'speaking')
    const m = mount()
    await sendChip(user, m) // a turn ran; a TTS client exists

    await user.click(screen.getByRole('button', { name: 'Interrupt speech' }))
    expect(h.tts[0].cancel).toHaveBeenCalledTimes(1)
    expect(h.machine!.dispatch).toHaveBeenCalledWith({ type: 'interrupt' })
  })

  it('standby: wakes the machine and starts push-to-talk capture', async () => {
    const user = userEvent.setup()
    mount()
    await user.click(screen.getByRole('button', { name: 'Tap the mark to speak' }))
    expect(h.machine!.dispatch).toHaveBeenCalledWith({ type: 'wake' })
    expect(h.uplinks).toHaveLength(1)
    expect(h.uplinks[0].start).toHaveBeenCalledTimes(1)
  })

  it('listening: submits the turn — vad_end now, turn_complete when v1 STT is absent', async () => {
    const user = userEvent.setup()
    setMachine('listening', 'listening')
    mount()
    await user.click(screen.getByRole('button', { name: 'Submit speech' }))
    expect(h.machine!.dispatch).toHaveBeenCalledWith({ type: 'vad_end' })
    // v1: the STT observation channel is not live; a manual end-of-speech
    // with no transcript is an empty turn that completes immediately so the
    // machine cannot park in `thinking` with nothing in flight.
    expect(h.machine!.dispatch).toHaveBeenCalledWith({ type: 'turn_complete' })
  })

  it('thinking: a tap is a no-op (a turn is already in flight)', async () => {
    const user = userEvent.setup()
    setMachine('thinking', 'thinking')
    mount()
    await user.click(screen.getByRole('button', { name: 'Working' }))
    expect(h.machine!.dispatch).not.toHaveBeenCalled()
  })

  it('error: the tap is an explicit retry (wake)', async () => {
    const user = userEvent.setup()
    setMachine('error', 'error')
    mount()
    await user.click(screen.getByRole('button', { name: 'Tap the mark to speak' }))
    expect(h.machine!.dispatch).toHaveBeenCalledWith({ type: 'wake' })
  })
})

// ---------------------------------------------------------------------------
// Turn submission: one path for keyboard and (future) STT
// ---------------------------------------------------------------------------

describe('turn submission', () => {
  it('subscribes TTS with the turn session id BEFORE sending the message', async () => {
    const user = userEvent.setup()
    setMachine('standby', 'idle')
    const m = mount()
    await sendChip(user, m)

    expect(h.tts).toHaveLength(1)
    expect(h.tts[0].connect).toHaveBeenCalledTimes(1)
    expect(h.agent!.sendMessage).toHaveBeenCalledTimes(1)

    const [text, sid] = h.agent!.sendMessage.mock.calls[0] as [string, string]
    expect(text).toBe('System Vitals')
    expect(h.tts[0].url).toBe(`tts://${sid}`) // same id the backend keys on
    // The TTS subscription precedes the send() call — hub synthesis is
    // gated on having a subscriber for the session (tts_egress.py).
    expect(h.tts[0].connect.mock.invocationCallOrder[0]).toBeLessThan(
      h.agent!.sendMessage.mock.invocationCallOrder[0],
    )
  })

  it('walks the machine into thinking: wake then vad_end', async () => {
    const user = userEvent.setup()
    setMachine('standby', 'idle')
    const m = mount()
    await sendChip(user, m)
    expect(h.machine!.dispatch).toHaveBeenCalledWith({ type: 'wake' })
    expect(h.machine!.dispatch).toHaveBeenCalledWith({ type: 'vad_end' })
  })

  it('replaces the TTS subscription per turn (fresh id, old client closed)', async () => {
    const user = userEvent.setup()
    setMachine('standby', 'idle')
    const m = mount()
    await sendChip(user, m)
    await sendChip(user, m, 'Check Storage')

    expect(h.tts).toHaveLength(2)
    expect(h.tts[0].close).toHaveBeenCalledTimes(1)
    expect(h.tts[1].close).not.toHaveBeenCalled()
    expect(h.tts[0].url).not.toBe(h.tts[1].url)
    const [, sid2] = h.agent!.sendMessage.mock.calls[1] as [string, string]
    expect(h.tts[1].url).toBe(`tts://${sid2}`)
  })

  it('closes the keyboard after a send', async () => {
    const user = userEvent.setup()
    const m = mount()
    await sendChip(user, m)
    expect(screen.queryByRole('dialog', { name: 'On-screen keyboard' })).toBeNull()
  })

  it('dispatches turn_complete when the agent stream ends', () => {
    const m = mount()
    h.agent!.isStreaming = true
    m.rerender()
    expect(dispatchedTypes()).not.toContain('turn_complete')

    h.agent!.isStreaming = false
    m.rerender()
    expect(h.machine!.dispatch).toHaveBeenCalledWith({ type: 'turn_complete' })
  })

  it('dispatches a speech_segment per NEW segment only', () => {
    const m = mount()
    h.agent!.session = { speechSegments: [SEGMENT] }
    m.rerender()
    h.agent!.session = { speechSegments: [SEGMENT, { ...SEGMENT, text: 'Second.' }] }
    m.rerender()
    expect(h.machine!.dispatch).toHaveBeenCalledWith({ type: 'speech_segment', segment: SEGMENT })
    expect(h.machine!.dispatch).toHaveBeenCalledWith({
      type: 'speech_segment',
      segment: { ...SEGMENT, text: 'Second.' },
    })
    // No re-dispatch on a re-render with the same segments.
    const before = h.machine!.dispatch.mock.calls.length
    m.rerender()
    expect(h.machine!.dispatch.mock.calls.length).toBe(before)
    // A new turn resets the count: its first segment dispatches once.
    h.agent!.session = { speechSegments: [] }
    m.rerender()
    h.agent!.session = { speechSegments: [{ ...SEGMENT, text: 'Next turn.' }] }
    m.rerender()
    expect(h.machine!.dispatch).toHaveBeenCalledWith({
      type: 'speech_segment',
      segment: { ...SEGMENT, text: 'Next turn.' },
    })
  })

  it('dispatches modality_resolved once per turn decision', () => {
    const m = mount()
    const modality: ModalityInfo = { modality: 'voice', speechText: 's', displayText: 'd' }
    h.agent!.session = { modality }
    m.rerender()
    m.rerender() // same object identity: no duplicate
    expect(h.machine!.dispatch).toHaveBeenCalledWith({ type: 'modality_resolved', modality: 'voice' })
    expect(dispatchedTypes().filter((t) => t === 'modality_resolved')).toHaveLength(1)
  })

  it('routes agent stream errors into the machine', () => {
    mount()
    expect(h.agentOptions?.onError).toBeTypeOf('function')
    act(() => h.agentOptions!.onError!('LLM timeout'))
    expect(h.machine!.dispatch).toHaveBeenCalledWith({ type: 'error', message: 'LLM timeout' })
  })
})

/** Click a quick-intent chip through the real OnScreenKeyboard (O9). */
async function sendChip(
  user: ReturnType<typeof userEvent.setup>,
  _m: ReturnType<typeof mount>,
  chip = 'System Vitals',
) {
  await user.click(screen.getByRole('button', { name: 'Open keyboard' }))
  await user.click(screen.getByRole('button', { name: chip }))
}

// ---------------------------------------------------------------------------
// Being-event wake (O5) and speaker recognition (O4)
// ---------------------------------------------------------------------------

describe('being events and speaker recognition', () => {
  it('an acoustic anomaly at wake severity dispatches acoustic_wake', () => {
    const m = mount()
    h.beingEvents = [
      {
        id: 'f1',
        type: 'finding',
        category: 'acoustic',
        severity: 'critical',
        title: 'Glass break',
        body: '',
        created_at: '2026-08-31T00:00:00Z',
        data: { anomaly_severity: 3, sound_class: 'glass_break' },
      },
    ]
    m.rerender()
    expect(h.machine!.dispatch).toHaveBeenCalledWith({
      type: 'acoustic_wake',
      soundClass: 'glass_break',
      severity: 3,
      urgency: 'critical',
    })
  })

  it('does not re-fire an old anomaly when a later being event arrives', () => {
    // The being-event list is cumulative; a new morning report must not
    // re-dispatch the earlier glass-break wake and stomp a speaking turn.
    const m = mount()
    h.beingEvents = [
      {
        id: 'f1',
        type: 'finding',
        category: 'acoustic',
        severity: 'critical',
        title: 'Glass break',
        body: '',
        created_at: '2026-08-31T00:00:00Z',
        data: { anomaly_severity: 3, sound_class: 'glass_break' },
      },
    ]
    m.rerender()
    expect(dispatchedTypes().filter((t) => t === 'acoustic_wake')).toHaveLength(1)

    h.beingEvents = [
      ...h.beingEvents,
      {
        id: 'f2',
        type: 'morning_report',
        severity: 'info',
        title: 'Morning report',
        body: '',
        created_at: '2026-08-31T07:00:00Z',
      },
    ]
    m.rerender()
    expect(dispatchedTypes().filter((t) => t === 'acoustic_wake')).toHaveLength(1)
  })

  it('ignores non-acoustic and low-severity events', () => {
    const m = mount()
    h.beingEvents = [
      {
        id: 'f2',
        type: 'finding',
        severity: 'info',
        title: 'Morning report',
        body: '',
        created_at: '2026-08-31T00:00:00Z',
      },
    ]
    m.rerender()
    expect(dispatchedTypes()).not.toContain('acoustic_wake')
  })

  it('polls /api/audio/status and dispatches speaker_recognized once per observation', async () => {
    vi.useFakeTimers()
    const speaker = { name: 'Eric', role: 'admin', confidence: 0.9 }
    fetchMock.mockResolvedValue({ ok: true, json: async () => ({ speaker }) })
    const m = mount()

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    expect(h.machine!.dispatch).toHaveBeenCalledWith({
      type: 'speaker_recognized',
      name: 'Eric',
      role: 'admin',
      confidence: 0.9,
    })

    // The next poll repeats the same observation: no duplicate dispatch.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(STATUS_POLL_MS)
    })
    const recognized = dispatchedTypes().filter((t) => t === 'speaker_recognized')
    expect(recognized).toHaveLength(1)
    void m
  })
})

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------

describe('lifecycle', () => {
  it('mute stops capture and clears the mic source; unmute restarts it', async () => {
    const user = userEvent.setup()
    const m = mount()
    await user.click(screen.getByRole('button', { name: 'Tap the mark to speak' }))
    const uplink = h.uplinks[0]

    await user.click(screen.getByRole('button', { name: 'Mute microphone' }))
    expect(uplink.stop).toHaveBeenCalledTimes(1)
    // The machine is now live-listening (PTT woke it) — muting cleared the
    // mic source, so the mark breathes without input.
    setMachine('listening', 'listening')
    m.rerender()
    expect(mountMarkSource()).toBe(null)

    // Unmute restores capture because the machine is in a mic posture.
    await user.click(screen.getByRole('button', { name: 'Unmute microphone' }))
    expect(h.uplinks).toHaveLength(2)
    expect(h.uplinks[1].start).toHaveBeenCalledTimes(1)
    setMachine('listening', 'listening')
    m.rerender()
    expect(mountMarkSource()).toEqual({ kind: 'mic', stream: MIC_STREAM })
  })

  it('a push-to-talk tap while muted wakes the visual but not the mic', async () => {
    const user = userEvent.setup()
    const m = mount()
    await user.click(screen.getByRole('button', { name: 'Mute microphone' }))
    await user.click(screen.getByRole('button', { name: 'Tap the mark to speak' }))
    expect(h.machine!.dispatch).toHaveBeenCalledWith({ type: 'wake' })
    expect(h.uplinks).toHaveLength(0)
    void m
  })

  it('mic failure routes into the machine error state', async () => {
    const user = userEvent.setup()
    setMachine('standby', 'idle')
    mount()
    await user.click(screen.getByRole('button', { name: 'Tap the mark to speak' }))
    expect(h.uplinkOptions).toHaveLength(1)

    // The page hands PcmUplink an onError callback; a capture failure (mic
    // permission denied, ingress drop) dispatches the machine error event.
    act(() => h.uplinkOptions[0].onError!('Permission denied'))
    expect(h.machine!.dispatch).toHaveBeenCalledWith({
      type: 'error',
      message: 'Permission denied',
    })
  })

  it('unmount closes the TTS client and stops the uplink', async () => {
    const user = userEvent.setup()
    const m = mount()
    await user.click(screen.getByRole('button', { name: 'Tap the mark to speak' }))
    await sendChip(user, m)

    m.view.unmount()
    expect(h.uplinks[0].stop).toHaveBeenCalledTimes(1)
    expect(h.tts[0].close).toHaveBeenCalledTimes(1)
  })
})
