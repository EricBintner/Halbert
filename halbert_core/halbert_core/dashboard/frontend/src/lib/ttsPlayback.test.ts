// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * TtsPlaybackClient (O3): the browser half of the TTS egress pipe. The
 * server streams begin / binary s16le PCM / end (or cancelled) frames over
 * /api/audio/tts; this file checks the scheduling math (gapless playback,
 * correct sample counts and start times), the protocol handling, and the
 * teardown paths — against stubbed AudioContext/WebSocket globals, since
 * jsdom has neither.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { TtsPlaybackClient, ttsStreamUrl } from './ttsPlayback'
import { setInstanceEndpoint } from './apiBase'

// ---------------------------------------------------------------------------
// Web Audio stubs
// ---------------------------------------------------------------------------

interface ScheduledSource {
  buffer: { length: number; sampleRate: number; data: Float32Array } | null
  connectedTo: unknown[]
  startAt: number | null
  stopped: boolean
  onended: (() => void) | null
}

class StubAudioContext {
  static instances: StubAudioContext[] = []
  /** State the NEXT constructed context starts in. 'suspended' by default:
   * Chrome's no-gesture state, the case connect() must rescue. */
  static nextState: 'suspended' | 'running' = 'suspended'
  currentTime = 0
  closed = false
  state: 'suspended' | 'running' = StubAudioContext.nextState
  resume = vi.fn(() => Promise.resolve())
  destination = { node: 'destination' }
  sources: ScheduledSource[] = []

  constructor() {
    StubAudioContext.instances.push(this)
  }

  createBuffer(_channels: number, length: number, sampleRate: number) {
    const data = new Float32Array(length)
    return {
      length,
      sampleRate,
      data,
      getChannelData: (_channel: number) => data,
    }
  }

  createBufferSource() {
    const source: ScheduledSource = {
      buffer: null,
      connectedTo: [],
      startAt: null,
      stopped: false,
      onended: null,
    }
    this.sources.push(source)
    return {
      set buffer(b: ScheduledSource['buffer']) {
        source.buffer = b
      },
      connect: (node: unknown) => source.connectedTo.push(node),
      start: (when: number) => {
        if (source.startAt !== null) throw new Error('already started')
        source.startAt = when
      },
      stop: () => {
        source.stopped = true
      },
      set onended(cb: () => void) {
        source.onended = cb
      },
    }
  }

  createGain() {
    return { node: 'gain', connect: vi.fn(), disconnect: vi.fn() }
  }

  close() {
    this.closed = true
  }
}

// ---------------------------------------------------------------------------
// WebSocket stub
// ---------------------------------------------------------------------------

class StubWebSocket {
  static instances: StubWebSocket[] = []
  static readonly OPEN = 1
  static readonly CLOSED = 3
  binaryType = 'blob'
  readyState: number = StubWebSocket.OPEN
  closed = false
  /** Text frames the client sent (the barge-in control frame). */
  sentText: string[] = []
  onmessage: ((ev: { data: unknown }) => void) | null = null
  onclose: (() => void) | null = null

  constructor(public url: string) {
    StubWebSocket.instances.push(this)
  }

  send(text: string): void {
    this.sentText.push(text)
  }

  close() {
    this.readyState = StubWebSocket.CLOSED
    this.closed = true
    this.onclose?.()
  }

  /** Test-side: deliver one server frame as the browser would. */
  receive(data: unknown): void {
    this.onmessage?.({ data })
  }
}

function pcm(...samples: number[]): ArrayBuffer {
  const buf = new ArrayBuffer(samples.length * 2)
  const view = new DataView(buf)
  samples.forEach((s, i) => view.setInt16(i * 2, s, true))
  return buf
}

// Clients are created and connected one at a time in these tests, so the
// latest stub WebSocket / AudioContext belong to the latest client.
function makeClient(url = 'ws://localhost/api/audio/tts?session_id=s1'): TtsPlaybackClient {
  return new TtsPlaybackClient(url)
}

function wsOf(): StubWebSocket {
  return StubWebSocket.instances[StubWebSocket.instances.length - 1]
}

function ctxOf(): StubAudioContext {
  return StubAudioContext.instances[StubAudioContext.instances.length - 1]
}

/** begin + one PCM chunk + end, the minimal complete turn. */
function feedTurn(ws: StubWebSocket, sampleRate = 22050): void {
  ws.receive(JSON.stringify({ type: 'begin', sample_rate: sampleRate, format: 's16le' }))
  ws.receive(pcm(0, -32768, 32767, 16384))
  ws.receive(JSON.stringify({ type: 'end' }))
}

beforeEach(() => {
  StubAudioContext.instances = []
  StubAudioContext.nextState = 'suspended'
  StubWebSocket.instances = []
  vi.stubGlobal('AudioContext', StubAudioContext)
  vi.stubGlobal('WebSocket', StubWebSocket)
})

afterEach(() => {
  vi.unstubAllGlobals()
  setInstanceEndpoint(null)
})

// ---------------------------------------------------------------------------
// PCM scheduling math
// ---------------------------------------------------------------------------

describe('TtsPlaybackClient scheduling', () => {
  it('converts s16le to float samples with the right count', () => {
    const client = makeClient()
    client.connect()
    const ws = wsOf()
    ws.receive(JSON.stringify({ type: 'begin', sample_rate: 22050, format: 's16le' }))
    ws.receive(pcm(0, -32768, 32767, 16384))

    const ctx = ctxOf()
    expect(ctx.sources).toHaveLength(1)
    const [source] = ctx.sources
    expect(source.buffer?.length).toBe(4)
    expect(source.buffer?.sampleRate).toBe(22050)
    expect(Array.from(source.buffer!.data)).toEqual([
      0,
      -1,
      32767 / 32768,
      0.5,
    ])
  })

  it('schedules chunks gaplessly in arrival order', () => {
    const client = makeClient()
    client.connect()
    const ws = wsOf()
    ws.receive(JSON.stringify({ type: 'begin', sample_rate: 10000, format: 's16le' }))
    // 100 samples at 10kHz = 10ms per chunk.
    ws.receive(new ArrayBuffer(200))
    ws.receive(new ArrayBuffer(200))
    ws.receive(new ArrayBuffer(200))

    const starts = ctxOf().sources.map((s) => s.startAt)
    expect(starts).toEqual([0, 0.01, 0.02])
  })

  it('never schedules in the past: late chunks start at currentTime', () => {
    const client = makeClient()
    client.connect()
    const ws = wsOf()
    const ctx = ctxOf()
    ctx.currentTime = 5
    ws.receive(JSON.stringify({ type: 'begin', sample_rate: 10000, format: 's16le' }))
    ws.receive(new ArrayBuffer(200)) // 10ms chunk

    expect(ctx.sources[0].startAt).toBe(5)
  })

  it('routes every source through the shared out gain node', () => {
    const client = makeClient()
    client.connect()
    const ws = wsOf()
    feedTurn(ws)

    const ctx = ctxOf()
    const out = client.out
    expect(out).not.toBeNull()
    expect(ctx.sources.every((s) => s.connectedTo.includes(out))).toBe(true)
  })

  it('ignores binary frames that arrive before begin', () => {
    const client = makeClient()
    client.connect()
    const ws = wsOf()
    ws.receive(pcm(1, 2))
    expect(ctxOf().sources).toHaveLength(0)
  })
})

// ---------------------------------------------------------------------------
// Protocol handling
// ---------------------------------------------------------------------------

describe('TtsPlaybackClient protocol', () => {
  it('begin + chunks + end plays the audio and reports done once', () => {
    const client = makeClient()
    const onDone = vi.fn()
    client.connect(onDone)
    feedTurn(wsOf())

    expect(ctxOf().sources).toHaveLength(1)
    expect(onDone).toHaveBeenCalledTimes(1)
  })

  it('cancelled stops the scheduled sources and reports done', () => {
    const client = makeClient()
    const onDone = vi.fn()
    client.connect(onDone)
    const ws = wsOf()
    ws.receive(JSON.stringify({ type: 'begin', sample_rate: 22050, format: 's16le' }))
    ws.receive(new ArrayBuffer(200))
    ws.receive(new ArrayBuffer(200))
    ws.receive(JSON.stringify({ type: 'cancelled' }))

    const ctx = ctxOf()
    expect(ctx.sources.every((s) => s.stopped)).toBe(true)
    expect(onDone).toHaveBeenCalledTimes(1)
  })

  it('a late chunk after cancelled is not scheduled', () => {
    const client = makeClient()
    client.connect()
    const ws = wsOf()
    ws.receive(JSON.stringify({ type: 'begin', sample_rate: 22050, format: 's16le' }))
    ws.receive(JSON.stringify({ type: 'cancelled' }))
    ws.receive(pcm(1, 2, 3))

    expect(ctxOf().sources).toHaveLength(0)
  })

  it('cancel() stops the queue and resets the schedule', () => {
    const client = makeClient()
    client.connect()
    const ws = wsOf()
    const ctx = ctxOf()
    ws.receive(JSON.stringify({ type: 'begin', sample_rate: 10000, format: 's16le' }))
    ws.receive(new ArrayBuffer(200))
    ws.receive(new ArrayBuffer(200))

    client.cancel()

    expect(ctx.sources.every((s) => s.stopped)).toBe(true)
    // The next turn's first chunk starts at currentTime, not behind it.
    ctx.currentTime = 3
    ws.receive(JSON.stringify({ type: 'begin', sample_rate: 10000, format: 's16le' }))
    ws.receive(new ArrayBuffer(200))
    const last = ctx.sources[ctx.sources.length - 1]
    expect(last.startAt).toBe(3)
    expect(last.stopped).toBe(false)
  })

  it('cancel() sends the barge-in control frame so the hub aborts synthesis', () => {
    // Without the frame, the server keeps synthesizing the silenced turn
    // and its next `begin` re-arms the client into playing the rest.
    const client = makeClient()
    client.connect()
    const ws = wsOf()
    ws.receive(JSON.stringify({ type: 'begin', sample_rate: 22050, format: 's16le' }))
    ws.receive(new ArrayBuffer(200))

    client.cancel()

    expect(ws.sentText).toEqual([JSON.stringify({ type: 'cancel' })])
  })

  it('a server `cancelled` frame does NOT echo the control frame back (no loop)', () => {
    // hub.cancel() answers the control frame with `cancelled`; echoing it
    // again would ping-pong forever.
    const client = makeClient()
    client.connect()
    const ws = wsOf()
    ws.receive(JSON.stringify({ type: 'begin', sample_rate: 22050, format: 's16le' }))
    ws.receive(new ArrayBuffer(200))
    ws.receive(JSON.stringify({ type: 'cancelled' }))

    expect(ws.sentText).toEqual([])
    expect(ctxOf().sources.every((s) => s.stopped)).toBe(true)
  })

  it('cancel() on a dead socket skips the control frame without throwing', () => {
    const client = makeClient()
    client.connect()
    const ws = wsOf()
    ws.readyState = StubWebSocket.CLOSED
    expect(() => client.cancel()).not.toThrow()
    expect(ws.sentText).toEqual([])
  })

  it('close() tears down the socket and the AudioContext', () => {
    const client = makeClient()
    client.connect()
    const ws = wsOf()
    const ctx = ctxOf()
    ws.receive(JSON.stringify({ type: 'begin', sample_rate: 22050, format: 's16le' }))
    ws.receive(new ArrayBuffer(200))

    client.close()

    expect(ws.closed).toBe(true)
    expect(ctx.closed).toBe(true)
    expect(ctx.sources.every((s) => s.stopped)).toBe(true)
    expect(client.out).toBeNull()
  })

  it('survives an environment without AudioContext', () => {
    vi.unstubAllGlobals()
    vi.stubGlobal('WebSocket', StubWebSocket)
    const client = makeClient()
    expect(() => client.connect()).not.toThrow()
    const ws = wsOf()
    expect(() => feedTurn(ws)).not.toThrow()
    expect(client.out).toBeNull()
  })

  it('resumes a suspended context (autoplay policy)', () => {
    // Chrome starts AudioContexts suspended outside a user gesture; without
    // the resume, every scheduled source is silently dead.
    const client = makeClient()
    client.connect()
    expect(ctxOf().state).toBe('suspended')
    expect(ctxOf().resume).toHaveBeenCalledTimes(1)
    // A context that is already running is left alone.
    StubAudioContext.nextState = 'running'
    const second = makeClient()
    second.connect()
    expect(ctxOf().state).toBe('running')
    expect(ctxOf().resume).toHaveBeenCalledTimes(0)
  })

  it('reports onDone once per turn across turns on one connection', () => {
    const client = makeClient()
    const onDone = vi.fn()
    client.connect(onDone)
    const ws = wsOf()
    feedTurn(ws) // turn 1: begin -> PCM -> end
    feedTurn(ws) // turn 2 on the same socket: begin re-arms onDone
    expect(onDone).toHaveBeenCalledTimes(2)
    // ...and the second turn's audio actually scheduled.
    expect(ctxOf().sources.length).toBeGreaterThanOrEqual(2)
  })

  it('ignores a second connect() while already connected', () => {
    // React 18 StrictMode double-invokes effects; the client must not open
    // a second socket (or a second AudioContext) for it.
    const client = makeClient()
    client.connect()
    client.connect()
    expect(StubWebSocket.instances).toHaveLength(1)
    expect(StubAudioContext.instances).toHaveLength(1)
    // close() nulls the socket, so connect() after close() works again.
    client.close()
    client.connect()
    expect(StubWebSocket.instances).toHaveLength(2)
  })
})

// ---------------------------------------------------------------------------
// URL helper
// ---------------------------------------------------------------------------

describe('ttsStreamUrl', () => {
  it('builds a ws url from the page origin', () => {
    expect(ttsStreamUrl('s1')).toBe(
      'ws://localhost:3000/api/audio/tts?session_id=s1',
    )
  })

  it('follows the instance endpoint override', () => {
    setInstanceEndpoint('http://192.168.1.5:8000/')
    expect(ttsStreamUrl('s 1')).toBe(
      'ws://192.168.1.5:8000/api/audio/tts?session_id=s%201',
    )
  })

  it('upgrades https origins to wss', () => {
    setInstanceEndpoint('https://halbert.example')
    expect(ttsStreamUrl('s1')).toBe(
      'wss://halbert.example/api/audio/tts?session_id=s1',
    )
  })
})
