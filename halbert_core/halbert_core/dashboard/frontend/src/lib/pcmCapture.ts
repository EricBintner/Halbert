// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * pcmCapture (O7) — the browser microphone uplink to /api/audio/stream.
 *
 * Plan doc 16 Decision 1 — the browser is the voice-mode audio terminal:
 *
 *   getUserMedia(16kHz, AEC) ─▶ source node ─┬─▶ AudioWorklet ─▶ WS /api/audio/stream
 *                                           │                     ─▶ WebRtcIngress ─▶ VAD/ASR
 *                                           └─▶ getAnalyserTap() ─▶ createNodeAnalyserSource
 *                                                 (the mark's visualizer)
 *
 * ONE capture graph, ONE AudioContext serves both consumers:
 * `getAnalyserTap()` exposes the source node of the uplink's own context,
 * so the mark's energy source is built with the existing
 * `createNodeAnalyserSource(tap)` — no second context rendering the same
 * MediaStream (the cross-context consumption class that breaks on
 * WebKitGTK). `getStream()` still exposes the raw MediaStream for callers
 * that need the stream itself.
 *
 * Frames are 16kHz s16le mono — the wire contract of /api/audio/stream —
 * produced by resampling whatever rate the AudioContext actually runs at
 * (browsers honor the 16kHz getUserMedia constraint only loosely; the
 * context is typically 44.1/48kHz). Worklet processors run in a separate
 * scope, so the processor is inlined as a Blob URL (no Vite config change)
 * and carries its own copy of the resampling loop; `Downsampler16k` is the
 * main-thread twin used by the ScriptProcessorNode fallback for WebKitGTK,
 * where AudioWorklet is unavailable (plan §8 risk 1).
 */

import { wsUrl } from './apiBase'

/** The ingress wire rate: 16kHz s16le mono (webrtc_ingress.SAMPLE_RATE). */
export const TARGET_SAMPLE_RATE = 16_000

/** 100ms of 16kHz audio per WebSocket frame (3200 bytes). */
export const FRAME_SAMPLES = 1600

/**
 * Cap on frames buffered while the WS handshake completes (drop-oldest).
 * The server-side ingress drops-oldest under load, but that cannot help a
 * queue growing on the client — 100 frames is 10 seconds of audio, far
 * past anything a healthy handshake should bank.
 */
export const MAX_QUEUED_FRAMES = 100

/** The AudioWorklet processor name registered by PCM_CAPTURE_WORKLET_SOURCE. */
export const PCM_CAPTURE_PROCESSOR_NAME = 'halbert-pcm-capture'

// -----------------------------------------------------------------------------
// Pure conversion math (DOM-free, plan Decision 6)
// -----------------------------------------------------------------------------

/**
 * Convert one frame of Float32 samples to an s16le little-endian buffer.
 * The x32768 scale matches the decoder convention (ttsPlayback divides by
 * 32768), with clamping so out-of-range floats cannot wrap.
 */
export function floatToS16le(samples: Float32Array): ArrayBuffer {
  const out = new ArrayBuffer(samples.length * 2)
  const view = new DataView(out)
  for (let i = 0; i < samples.length; i++) {
    const v = samples[i]
    let s = Math.round(v * 32768)
    if (s > 32767) s = 32767
    else if (s < -32768) s = -32768
    view.setInt16(i * 2, s, true)
  }
  return out
}

/**
 * Linear-interpolation resampler to 16kHz that emits fixed-size frames.
 *
 * `push()` accepts input buffers at ANY rate and any length; the fractional
 * read position carries across calls (a sample that lands between two
 * buffers is interpolated from the previous buffer's last sample), and a
 * frame is emitted only when `frameSamples` samples have accumulated. This
 * is the main-thread twin of the worklet's processor loop — the algorithm
 * is deliberately identical so both paths produce the same frames.
 */
export class Downsampler16k {
  private carry = 0
  private prevLast = 0
  private frame: Float32Array
  private fill = 0
  private readonly ratio: number

  constructor(
    inputRate: number,
    private readonly onFrame: (frame: Float32Array) => void,
    frameSamples: number = FRAME_SAMPLES,
  ) {
    // A non-positive frame size would never emit (fill can never reach it).
    this.frame = new Float32Array(frameSamples > 0 ? frameSamples : 1)
    this.ratio = inputRate / TARGET_SAMPLE_RATE
  }

  push(input: Float32Array): void {
    // A non-positive rate would never advance the read position — an
    // infinite loop — so a nonsense rate drops its input instead.
    if (input.length === 0 || !(this.ratio > 0)) return
    const lastIdx = input.length - 1
    let pos = this.carry
    while (pos <= lastIdx) {
      let sample: number
      if (pos < 0) {
        // Between the previous buffer's last sample and this one.
        const frac = pos + 1
        sample = this.prevLast + (input[0] - this.prevLast) * frac
      } else if (pos >= lastIdx) {
        // Exactly the last sample: known without lookahead.
        sample = input[lastIdx]
      } else {
        const i = Math.floor(pos)
        const frac = pos - i
        sample = input[i] + (input[i + 1] - input[i]) * frac
      }
      this.append(sample)
      pos += this.ratio
    }
    this.carry = pos - input.length
    this.prevLast = input[lastIdx]
  }

  private append(sample: number): void {
    this.frame[this.fill++] = sample
    if (this.fill === this.frame.length) {
      this.onFrame(this.frame)
      this.frame = new Float32Array(this.frame.length)
      this.fill = 0
    }
  }
}

// -----------------------------------------------------------------------------
// AudioWorklet processor (inlined; runs in the worklet scope)
// -----------------------------------------------------------------------------

/**
 * The processor source, loaded via `audioWorklet.addModule(blobUrl)`. Same
 * resampling loop as Downsampler16k, written against the worklet globals
 * (`sampleRate`, `AudioWorkletProcessor`, `registerProcessor`). Posts each
 * finished Float32 frame to the main thread through its MessagePort.
 */
export const PCM_CAPTURE_WORKLET_SOURCE = `
// Inlined by pcmCapture.ts (Blob URL): resample the capture graph to
// ${TARGET_SAMPLE_RATE}Hz and post fixed Float32 frames to the main thread.
class HalbertPcmCaptureProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super()
    const frameSamples =
      (options && options.processorOptions && options.processorOptions.frameSamples) ||
      ${FRAME_SAMPLES}
    this.frame = new Float32Array(frameSamples)
    this.fill = 0
    this.ratio = sampleRate / ${TARGET_SAMPLE_RATE}
    this.carry = 0
    this.prevLast = 0
  }
  process(inputs) {
    const input = inputs[0] && inputs[0][0]
    if (!input || input.length === 0) return true
    const lastIdx = input.length - 1
    let pos = this.carry
    while (pos <= lastIdx) {
      let sample
      if (pos < 0) {
        sample = this.prevLast + (input[0] - this.prevLast) * (pos + 1)
      } else if (pos >= lastIdx) {
        sample = input[lastIdx]
      } else {
        const i = Math.floor(pos)
        const frac = pos - i
        sample = input[i] + (input[i + 1] - input[i]) * frac
      }
      this.frame[this.fill++] = sample
      if (this.fill === this.frame.length) {
        this.port.postMessage(this.frame)
        this.frame = new Float32Array(this.frame.length)
        this.fill = 0
      }
      pos += this.ratio
    }
    this.carry = pos - input.length
    this.prevLast = input[lastIdx]
    return true
  }
}
registerProcessor('${PCM_CAPTURE_PROCESSOR_NAME}', HalbertPcmCaptureProcessor)
`

// -----------------------------------------------------------------------------
// Backend selection
// -----------------------------------------------------------------------------

/**
 * True when the context can host an AudioWorklet. WebKitGTK (Tauri on
 * Linux) is the motivating fallback: `audioWorklet.addModule` is missing or
 * inert there, and a ScriptProcessorNode keeps the uplink alive.
 */
export function workletSupported(
  context: { audioWorklet?: { addModule?: unknown } } | null | undefined,
): boolean {
  return typeof context?.audioWorklet?.addModule === 'function'
}

// -----------------------------------------------------------------------------
// The uplink
// -----------------------------------------------------------------------------

export interface PcmUplinkOptions {
  /** Defaults to `wsUrl('/api/audio/stream')`. */
  url?: string
  /** Samples per emitted frame (default 100ms at 16kHz). */
  frameSamples?: number
  /** Mic / transport failure report — Voice Mode routes this to the
   * machine's `error` state. Never called for an explicit `stop()`. */
  onError?: (message: string) => void
}

export type PcmUplinkStatus = 'idle' | 'starting' | 'running' | 'stopped'

/**
 * One capture session: getUserMedia -> AudioContext -> (worklet | script
 * processor) -> s16le frames over the /api/audio/stream WebSocket.
 *
 * Failures never throw out of `start()`; they tear the session down and
 * report through `onError` (a half-built graph must not leak a live mic).
 * The server closing the socket (1013 while the pipeline boots, or any
 * later drop) is a failure: there is no auto-reconnect — the user's next
 * push-to-talk rebuilds the uplink, the same policy as TtsPlaybackClient.
 */
export class PcmUplink {
  private status: PcmUplinkStatus = 'idle'
  private ws: WebSocket | null = null
  private ctx: AudioContext | null = null
  private stream: MediaStream | null = null
  private sourceNode: MediaStreamAudioSourceNode | null = null
  private tapNode: AudioWorkletNode | ScriptProcessorNode | null = null
  private sink: GainNode | null = null
  private downsampler: Downsampler16k | null = null
  private frameQueue: ArrayBuffer[] = []

  constructor(private readonly opts: PcmUplinkOptions = {}) {}

  /** 'running' once frames are flowing; 'stopped' after stop() or failure. */
  get state(): PcmUplinkStatus {
    return this.status
  }

  /** The capture stream, for callers that need the MediaStream itself.
   * Null before start() completes and after stop(). The mark's visualizer
   * should NOT use this (a second context consuming one stream — the
   * WebKitGTK fragility class); use `getAnalyserTap()` instead. */
  getStream(): MediaStream | null {
    return this.stream
  }

  /** A node carrying the live mic signal in the uplink's OWN AudioContext —
   * the source node itself. Feed it to the design system's
   * `createNodeAnalyserSource(tap)` so the mark visualizes exactly what is
   * being uplinked on the same rendering thread (Decision 1: one capture
   * graph, one context). Null before start() completes and after stop(). */
  getAnalyserTap(): AudioNode | null {
    return this.sourceNode
  }

  async start(): Promise<void> {
    if (this.status === 'running' || this.status === 'starting') return
    this.status = 'starting'
    try {
      const media = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          sampleRate: TARGET_SAMPLE_RATE,
          echoCancellation: true,
          noiseSuppression: true,
        },
      })
      if (this.status !== 'starting') {
        // stop() ran while the permission prompt was up.
        media.getTracks().forEach((t) => t.stop())
        return
      }
      this.stream = media

      const ctx = new AudioContext()
      this.ctx = ctx
      // The uplink begins from a user gesture (push-to-talk); a suspended
      // context would silently swallow every worklet callback.
      if (ctx.state === 'suspended') {
        void ctx.resume?.().catch?.(() => {})
      }

      const ws = new WebSocket(this.opts.url ?? wsUrl('/api/audio/stream'))
      ws.binaryType = 'arraybuffer'
      ws.onopen = () => this.flushQueue()
      ws.onclose = () => {
        if (this.status === 'running' || this.status === 'starting') {
          this.fail('microphone uplink disconnected')
        }
      }
      this.ws = ws

      const source = ctx.createMediaStreamSource(media)
      this.sourceNode = source

      if (workletSupported(ctx)) {
        const blob = new Blob([PCM_CAPTURE_WORKLET_SOURCE], {
          type: 'application/javascript',
        })
        const blobUrl = URL.createObjectURL(blob)
        try {
          await ctx.audioWorklet.addModule(blobUrl)
        } finally {
          URL.revokeObjectURL(blobUrl)
        }
        const node = new AudioWorkletNode(ctx, PCM_CAPTURE_PROCESSOR_NAME, {
          processorOptions: { frameSamples: this.opts.frameSamples ?? FRAME_SAMPLES },
        })
        node.port.onmessage = (ev: MessageEvent) => {
          // Structured clone already delivered a fresh array; no copy needed.
          this.sendFrame(ev.data as Float32Array)
        }
        this.tapNode = node
      } else {
        // WebKitGTK: ScriptProcessorNode + the main-thread downsampler.
        const node = ctx.createScriptProcessor(4096, 1, 1)
        this.downsampler = new Downsampler16k(
          ctx.sampleRate,
          (f) => this.sendFrame(f),
          this.opts.frameSamples ?? FRAME_SAMPLES,
        )
        node.onaudioprocess = (ev: AudioProcessingEvent) => {
          this.downsampler?.push(ev.inputBuffer.getChannelData(0))
        }
        this.tapNode = node
      }

      source.connect(this.tapNode)
      // Both tap nodes must sit in a live graph to be pulled; route them
      // through a zero gain so nothing the mic hears plays out loud.
      const sink = ctx.createGain()
      sink.gain.value = 0
      this.tapNode.connect(sink)
      sink.connect(ctx.destination)
      this.sink = sink

      this.status = 'running'
    } catch (err) {
      this.fail(err instanceof Error ? err.message : String(err))
    }
  }

  /** Tear the session down (idempotent). No onError: this is voluntary. */
  stop(): void {
    this.teardown()
    this.status = 'stopped'
  }

  // -------------------------------------------------------------------
  // Internals
  // -------------------------------------------------------------------

  private sendFrame(frame: Float32Array): void {
    const bytes = floatToS16le(frame)
    const ws = this.ws
    if (!ws) return
    if (ws.readyState === WebSocket.OPEN) {
      ws.send(bytes)
    } else if (ws.readyState === WebSocket.CONNECTING) {
      // The handshake wins the race sometimes; frames queue in order and
      // flush on open — bounded drop-oldest, because the server-side
      // drop-oldest cannot reach a queue growing on this side.
      this.frameQueue.push(bytes)
      if (this.frameQueue.length > MAX_QUEUED_FRAMES) {
        this.frameQueue.shift()
      }
    }
    // CLOSING/CLOSED: the transport is gone; frames are dropped.
  }

  private flushQueue(): void {
    if (!this.ws) return
    for (const bytes of this.frameQueue) {
      if (this.ws.readyState !== WebSocket.OPEN) break
      this.ws.send(bytes)
    }
    this.frameQueue = []
  }

  private fail(message: string): void {
    this.teardown()
    this.status = 'stopped'
    this.opts.onError?.(message)
  }

  private teardown(): void {
    if (this.ws) {
      this.ws.onopen = null
      this.ws.onclose = null
      this.ws.onerror = null
      try {
        this.ws.close()
      } catch {
        // close() on an already-dead socket is harmless but can throw in
        // some stubs; the transport is going away regardless.
      }
      this.ws = null
    }
    if (this.tapNode) {
      try {
        this.tapNode.disconnect()
      } catch {
        /* best-effort */
      }
      this.tapNode = null
    }
    try {
      this.sink?.disconnect()
    } catch {
      /* best-effort */
    }
    this.sink = null
    try {
      this.sourceNode?.disconnect()
    } catch {
      /* best-effort */
    }
    this.sourceNode = null
    this.downsampler = null
    try {
      this.ctx?.close()
    } catch {
      // close() on an already-closed context throws in some engines'
      // typings; swallow it (same policy as TtsPlaybackClient).
    }
    this.ctx = null
    this.stream?.getTracks().forEach((t) => t.stop())
    this.stream = null
    this.frameQueue = []
  }
}
