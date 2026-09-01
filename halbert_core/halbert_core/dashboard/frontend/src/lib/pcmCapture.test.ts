// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * pcmCapture (O7): the browser microphone uplink to /api/audio/stream.
 * These tests pin the pure conversion math (Float32 -> s16le, the
 * downsampler's frame emission), the worklet-vs-ScriptProcessorNode
 * backend selection, and the PcmUplink lifecycle — against stubbed
 * getUserMedia / AudioContext / WebSocket globals, the same approach as
 * ttsPlayback.test.ts (jsdom has no Web Audio or sockets).
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import {
  Downsampler16k,
  PcmUplink,
  PCM_CAPTURE_WORKLET_SOURCE,
  TARGET_SAMPLE_RATE,
  FRAME_SAMPLES,
  floatToS16le,
  workletSupported,
} from './pcmCapture'

// ---------------------------------------------------------------------------
// Stubs: AudioContext / AudioWorkletNode / WebSocket / getUserMedia
// ---------------------------------------------------------------------------

interface StubProcessor {
  onaudioprocess: ((ev: { inputBuffer: { getChannelData: (c: number) => Float32Array } }) => void) | null
  connect: ReturnType<typeof vi.fn>
  disconnect: ReturnType<typeof vi.fn>
}

class StubAudioContext {
  static instances: StubAudioContext[] = []
  /** Whether the NEXT constructed context exposes audioWorklet.addModule. */
  static withWorklet = true

  state: 'suspended' | 'running' = 'suspended'
  sampleRate = 48_000
  closed = false
  destination = { node: 'destination' }
  audioWorklet: { addModule: ReturnType<typeof vi.fn> } | undefined
  gains: Array<{ gain: { value: number }; connect: ReturnType<typeof vi.fn>; disconnect: ReturnType<typeof vi.fn> }> = []
  processors: StubProcessor[] = []
  streamSources: Array<{ stream: unknown; connect: ReturnType<typeof vi.fn>; disconnect: ReturnType<typeof vi.fn> }> = []
  resume = vi.fn(() => Promise.resolve())

  constructor() {
    StubAudioContext.instances.push(this)
    if (StubAudioContext.withWorklet) {
      this.audioWorklet = { addModule: vi.fn(async () => {}) }
    }
  }

  createGain() {
    const gain = { gain: { value: 1 }, connect: vi.fn(), disconnect: vi.fn() }
    this.gains.push(gain)
    return gain
  }

  createScriptProcessor(_bufferSize: number, _inCh: number, _outCh: number): StubProcessor {
    const processor: StubProcessor = { onaudioprocess: null, connect: vi.fn(), disconnect: vi.fn() }
    this.processors.push(processor)
    return processor
  }

  createMediaStreamSource(stream: unknown) {
    const source = { stream, connect: vi.fn(), disconnect: vi.fn() }
    this.streamSources.push(source)
    return source
  }

  close() {
    this.closed = true
  }
}

class StubAudioWorkletNode {
  static instances: StubAudioWorkletNode[] = []

  port = { onmessage: null as ((ev: { data: Float32Array }) => void) | null }
  connect = vi.fn()
  disconnect = vi.fn()

  constructor(
    public ctx: StubAudioContext,
    public name: string,
    public options: unknown,
  ) {
    StubAudioWorkletNode.instances.push(this)
  }
}

class StubWebSocket {
  static CONNECTING = 0
  static OPEN = 1
  static CLOSING = 2
  static CLOSED = 3
  static instances: StubWebSocket[] = []

  binaryType = 'blob'
  readyState = StubWebSocket.CONNECTING
  sent: ArrayBuffer[] = []
  closedByClient = false
  onopen: (() => void) | null = null
  onclose: (() => void) | null = null
  onerror: (() => void) | null = null

  constructor(public url: string) {
    StubWebSocket.instances.push(this)
  }

  send(data: ArrayBuffer): void {
    this.sent.push(data)
  }

  /** Test-side: finish the handshake. */
  open(): void {
    this.readyState = StubWebSocket.OPEN
    this.onopen?.()
  }

  /** Test-side: the server dropped the connection. */
  serverClose(): void {
    this.readyState = StubWebSocket.CLOSED
    this.onclose?.()
  }

  close(): void {
    this.readyState = StubWebSocket.CLOSED
    this.closedByClient = true
    this.onclose?.()
  }
}

class StubMediaStream {
  stopped = false
  tracks = [{ stop: vi.fn(() => { this.stopped = true }) }]
  getTracks() {
    return this.tracks
  }
}

let mediaStream: StubMediaStream
let getUserMedia: ReturnType<typeof vi.fn>

beforeEach(() => {
  StubAudioContext.instances = []
  StubAudioContext.withWorklet = true
  StubAudioWorkletNode.instances = []
  StubWebSocket.instances = []
  mediaStream = new StubMediaStream()
  getUserMedia = vi.fn(async () => mediaStream)
  vi.stubGlobal('AudioContext', StubAudioContext)
  vi.stubGlobal('AudioWorkletNode', StubAudioWorkletNode)
  vi.stubGlobal('WebSocket', StubWebSocket)
  vi.stubGlobal('navigator', { mediaDevices: { getUserMedia } })
  vi.stubGlobal('URL', {
    createObjectURL: vi.fn(() => 'blob:stub'),
    revokeObjectURL: vi.fn(),
  })
})

afterEach(() => {
  vi.unstubAllGlobals()
})

// ---------------------------------------------------------------------------
// floatToS16le — the frame conversion math
// ---------------------------------------------------------------------------

describe('floatToS16le', () => {
  it('converts full-scale floats to little-endian int16', () => {
    const bytes = floatToS16le(new Float32Array([0, -1, 1, 0.5]))
    const view = new DataView(bytes)
    expect(bytes.byteLength).toBe(8)
    expect(view.getInt16(0, true)).toBe(0)
    expect(view.getInt16(2, true)).toBe(-32768)
    expect(view.getInt16(4, true)).toBe(32767)
    expect(view.getInt16(6, true)).toBe(16384)
  })

  it('clamps out-of-range floats instead of wrapping', () => {
    const view = new DataView(floatToS16le(new Float32Array([1.5, -1.5, 2])))
    expect(view.getInt16(0, true)).toBe(32767)
    expect(view.getInt16(2, true)).toBe(-32768)
    expect(view.getInt16(4, true)).toBe(32767)
  })

  it('rounds to nearest using the x32768 convention the decoder divides by', () => {
    const view = new DataView(floatToS16le(new Float32Array([0.0000153, -0.0000305])))
    // 0.0000153 * 32768 = 0.501 -> 1; -0.0000305 * 32768 = -1.0 -> -1
    expect(view.getInt16(0, true)).toBe(1)
    expect(view.getInt16(2, true)).toBe(-1)
  })
})

// ---------------------------------------------------------------------------
// Downsampler16k — pure resampling + frame emission
// ---------------------------------------------------------------------------

describe('Downsampler16k', () => {
  it('is the identity at the target rate, emitting fixed frames', () => {
    const frames: Float32Array[] = []
    const d = new Downsampler16k(16_000, (f) => frames.push(f), 3)
    d.push(new Float32Array([1, 2, 3, 4, 5, 6, 7, 8, 9]))
    expect(frames.map((f) => Array.from(f))).toEqual([
      [1, 2, 3],
      [4, 5, 6],
      [7, 8, 9],
    ])
  })

  it('carries pending samples across push() calls without seams', () => {
    const frames: Float32Array[] = []
    const d = new Downsampler16k(16_000, (f) => frames.push(f), 3)
    d.push(new Float32Array([1, 2, 3, 4, 5, 6])) // one frame + 3 pending
    d.push(new Float32Array([7, 8, 9, 10])) // completes the second frame
    expect(frames.map((f) => Array.from(f))).toEqual([
      [1, 2, 3],
      [4, 5, 6],
      [7, 8, 9],
    ])
  })

  it('keeps every 3rd sample from a 48kHz graph across buffer seams', () => {
    const out: number[] = []
    const d = new Downsampler16k(48_000, (f) => out.push(...Array.from(f)), 5)
    d.push(new Float32Array([0, 1, 2, 3, 4, 5])) // outputs at input pos 0, 3
    d.push(new Float32Array([6, 7, 8, 9])) // next outputs at (global) 6, 9
    d.push(new Float32Array([10, 11, 12])) // next output at (global) 12
    expect(out).toEqual([0, 3, 6, 9, 12])
  })

  it('interpolates halfway between samples from a 32kHz graph', () => {
    const frames: Float32Array[] = []
    const d = new Downsampler16k(32_000, (f) => frames.push(f), 3)
    d.push(new Float32Array([0, 10, 20, 30, 40, 50]))
    // Outputs land at input positions 0, 2, 4.
    expect(frames.map((f) => Array.from(f))).toEqual([[0, 20, 40]])
  })

  it('upsamples cleanly when the graph runs below the target rate', () => {
    const frames: Float32Array[] = []
    const d = new Downsampler16k(8_000, (f) => frames.push(f), 8)
    // 8k stream 0,4,0,4... -> 16k outputs interpolate each gap.
    d.push(new Float32Array([0, 4]))
    d.push(new Float32Array([0, 4]))
    d.push(new Float32Array([0, 4]))
    expect(frames.map((f) => Array.from(f))).toEqual([[0, 2, 4, 2, 0, 2, 4, 2]])
  })
})

// ---------------------------------------------------------------------------
// Worklet source + backend selection
// ---------------------------------------------------------------------------

describe('worklet source and fallback selection', () => {
  it('registers the processor the uplink instantiates, targeted at 16kHz', () => {
    expect(PCM_CAPTURE_WORKLET_SOURCE).toContain("registerProcessor('halbert-pcm-capture'")
    expect(PCM_CAPTURE_WORKLET_SOURCE).toContain(`${TARGET_SAMPLE_RATE}`)
  })

  it('workletSupported is true only when addModule exists', () => {
    expect(workletSupported({ audioWorklet: { addModule: async () => {} } })).toBe(true)
    expect(workletSupported({ audioWorklet: {} })).toBe(false)
    expect(workletSupported({})).toBe(false)
    expect(workletSupported(null)).toBe(false)
  })
})

// ---------------------------------------------------------------------------
// PcmUplink lifecycle
// ---------------------------------------------------------------------------

describe('PcmUplink', () => {
  it('captures with the 16kHz mono AEC constraints and connects to the stream WS', async () => {
    const uplink = new PcmUplink()
    await uplink.start()

    expect(getUserMedia).toHaveBeenCalledWith({
      audio: {
        channelCount: 1,
        sampleRate: TARGET_SAMPLE_RATE,
        echoCancellation: true,
        noiseSuppression: true,
      },
    })
    const ws = StubWebSocket.instances[0]
    expect(ws.url).toBe('ws://localhost:3000/api/audio/stream')
    expect(uplink.state).toBe('running')
    expect(uplink.getStream()).toBe(mediaStream)
  })

  it('uses the AudioWorklet path when available (Blob URL module)', async () => {
    const uplink = new PcmUplink()
    await uplink.start()

    const ctx = StubAudioContext.instances[0]
    expect(ctx.audioWorklet?.addModule).toHaveBeenCalledWith('blob:stub')
    expect(StubAudioWorkletNode.instances).toHaveLength(1)
    expect(StubAudioWorkletNode.instances[0].name).toBe('halbert-pcm-capture')
    expect(ctx.processors).toHaveLength(0) // no ScriptProcessorNode fallback
  })

  it('converts worklet frames to s16le and sends them as binary WS frames', async () => {
    const uplink = new PcmUplink({ frameSamples: 4 })
    await uplink.start()
    const ws = StubWebSocket.instances[0]
    ws.open()

    // The worklet posts a finished frame through its MessagePort.
    StubAudioWorkletNode.instances[0].port.onmessage?.({
      data: new Float32Array([0, -1, 1, 0.5]),
    })

    expect(ws.sent).toHaveLength(1)
    const view = new DataView(ws.sent[0])
    expect(view.getInt16(0, true)).toBe(0)
    expect(view.getInt16(2, true)).toBe(-32768)
    expect(view.getInt16(4, true)).toBe(32767)
    expect(view.getInt16(6, true)).toBe(16384)
  })

  it('buffers frames until the socket opens, then flushes in order', async () => {
    const uplink = new PcmUplink({ frameSamples: 1 })
    await uplink.start()
    const ws = StubWebSocket.instances[0]
    const port = StubAudioWorkletNode.instances[0].port
    port.onmessage?.({ data: new Float32Array([0.25]) })
    port.onmessage?.({ data: new Float32Array([-0.25]) })
    expect(ws.sent).toHaveLength(0) // still CONNECTING

    ws.open()
    expect(ws.sent).toHaveLength(2)
    expect(new DataView(ws.sent[0]).getInt16(0, true)).toBe(8192)
    expect(new DataView(ws.sent[1]).getInt16(0, true)).toBe(-8192)
  })

  it('falls back to ScriptProcessorNode when AudioWorklet is unavailable', async () => {
    StubAudioContext.withWorklet = false
    const uplink = new PcmUplink({ frameSamples: 2 })
    await uplink.start()

    const ctx = StubAudioContext.instances[0]
    expect(StubAudioWorkletNode.instances).toHaveLength(0)
    expect(ctx.processors).toHaveLength(1)

    // ScriptProcessor input buffers go through the same downsampler + frame
    // path on the main thread (48kHz input, every 3rd sample kept).
    const ws = StubWebSocket.instances[0]
    ws.open()
    ctx.processors[0].onaudioprocess?.({
      inputBuffer: {
        getChannelData: () => new Float32Array([0, 0.1, 0.2, 0.9, 0.8, 0.7, 0, 0.1, 0.2]),
      },
    })
    expect(ws.sent).toHaveLength(1)
    const view = new DataView(ws.sent[0])
    expect(view.getInt16(0, true)).toBe(0) // input position 0 -> 0.0
    expect(view.getInt16(2, true)).toBe(29491) // input position 3 -> 0.9
  })

  it('routes the capture tap through a zero gain so nothing plays locally', async () => {
    const uplink = new PcmUplink()
    await uplink.start()
    const ctx = StubAudioContext.instances[0]
    const sink = ctx.gains[0]
    expect(sink.gain.value).toBe(0)
    expect(sink.connect).toHaveBeenCalledWith(ctx.destination)
  })

  it('reports onError and tears down when the server drops the socket', async () => {
    const onError = vi.fn()
    const uplink = new PcmUplink({ onError })
    await uplink.start()
    StubWebSocket.instances[0].serverClose()

    expect(onError).toHaveBeenCalledTimes(1)
    expect(uplink.state).toBe('stopped')
    expect(mediaStream.stopped).toBe(true)
    expect(StubAudioContext.instances[0].closed).toBe(true)
  })

  it('reports onError when getUserMedia is denied', async () => {
    getUserMedia.mockRejectedValue(new Error('Permission denied'))
    const onError = vi.fn()
    const uplink = new PcmUplink({ onError })
    await uplink.start()

    expect(onError).toHaveBeenCalledWith(expect.stringContaining('Permission denied'))
    expect(uplink.state).toBe('stopped')
    // No half-built graph survives the failure.
    expect(StubWebSocket.instances).toHaveLength(0)
  })

  it('stop() stops tracks, closes the socket and context, and is idempotent', async () => {
    const uplink = new PcmUplink()
    await uplink.start()
    uplink.stop()
    uplink.stop()

    const ws = StubWebSocket.instances[0]
    expect(ws.closedByClient).toBe(true)
    expect(mediaStream.stopped).toBe(true)
    expect(StubAudioContext.instances[0].closed).toBe(true)
    expect(uplink.state).toBe('stopped')
    expect(uplink.getStream()).toBe(null)
  })

  it('start() while running is a no-op (one capture graph per uplink)', async () => {
    const uplink = new PcmUplink()
    await uplink.start()
    await uplink.start()
    expect(getUserMedia).toHaveBeenCalledTimes(1)
    expect(StubWebSocket.instances).toHaveLength(1)
  })

  it('uses the default frame size of 100ms at 16kHz', () => {
    expect(FRAME_SAMPLES).toBe(1600)
  })
})
