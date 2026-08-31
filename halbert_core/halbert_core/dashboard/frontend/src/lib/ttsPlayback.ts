// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * TtsPlaybackClient (O3) — the browser half of the TTS egress pipe.
 *
 * When a voice turn is spoken, the backend streams the agent's actual Piper
 * PCM over the /api/audio/tts WebSocket:
 *
 *   {"type":"begin","sample_rate":22050,"format":"s16le"}   (text frame)
 *   <binary s16le mono chunks>                              (binary frames)
 *   {"type":"end"} | {"type":"cancelled"}                   (text frame)
 *
 * Chunks are decoded and scheduled gaplessly on one AudioContext timeline
 * (`nextStart` advances as chunks are scheduled at max(currentTime,
 * nextStart)), so segments and turns play back-to-back without drift.
 *
 * `out` is the visualizer tap: every source connects through it, so
 * `createNodeAnalyserSource(client.out)` from @halbert/design-system sees
 * the real spoken output (Decision 1 — the browser is the audio terminal).
 */

import { wsUrl } from './apiBase'

/** Absolute /api/audio/tts URL for a turn's session id (ws/wss scheme). */
export function ttsStreamUrl(sessionId: string): string {
  return `${wsUrl('/api/audio/tts')}?session_id=${encodeURIComponent(sessionId)}`
}

export class TtsPlaybackClient {
  private ctx: AudioContext | null = null
  private outNode: GainNode | null = null
  private ws: WebSocket | null = null
  private nextStart = 0
  /** 0 until the turn's begin frame names the Piper model's sample rate. */
  private sampleRate = 0
  private sources = new Set<AudioBufferSourceNode>()
  private finished = false
  private onDone: (() => void) | undefined

  constructor(private readonly url: string) {}

  /** Tap point for the visualizer: `createNodeAnalyserSource(client.out)`.
   * Null before connect() and after close(); null in environments with no
   * Web Audio (playback degrades to protocol handling only). */
  get out(): GainNode | null {
    return this.outNode
  }

  /** Open the WebSocket and prepare the playback graph.
   *
   * `onDone` fires exactly once per streamed turn — after `end`, after
   * `cancelled`, or when the socket closes (a later `begin` on the same
   * connection re-arms it: the server streams many turns per socket).
   * Idempotent: a second call while connected does nothing (React 18
   * StrictMode double-invokes effects). */
  connect(onDone?: () => void): void {
    if (this.ws) return
    this.onDone = onDone
    this.finished = false
    try {
      this.ctx = new AudioContext()
      this.outNode = this.ctx.createGain()
      this.outNode.connect(this.ctx.destination)
      // Chrome starts contexts suspended outside a user gesture; without a
      // resume every scheduled source is silently dead. Idempotent, and
      // failure just leaves the browser's own gesture policy in charge.
      if (this.ctx.state === 'suspended') {
        this.ctx.resume().catch(() => {})
      }
    } catch {
      // No Web Audio (unsupported browser, torn-down jsdom): stay silent,
      // keep the socket so the session state still tracks.
      this.ctx = null
      this.outNode = null
    }
    const ws = new WebSocket(this.url)
    ws.binaryType = 'arraybuffer'
    ws.onmessage = (ev: MessageEvent) => this.handleFrame(ev.data)
    ws.onclose = () => this.finish()
    this.ws = ws
  }

  /** Stop every scheduled source and reset the timeline (barge-in). */
  cancel(): void {
    for (const source of this.sources) {
      try {
        source.stop()
      } catch {
        // stop() throws on a source that never started or already ended.
      }
    }
    this.sources.clear()
    this.nextStart = 0
    // Late binary frames after a cancel belong to the cancelled turn; the
    // next turn's begin frame re-arms the rate.
    this.sampleRate = 0
  }

  /** Tear down the socket, the sources, and the AudioContext. */
  close(): void {
    this.cancel()
    this.ws?.close()
    this.ws = null
    try {
      this.ctx?.close()
    } catch {
      // close() on an already-closed context is harmless but throws in
      // some engines' typings; swallow it.
    }
    this.ctx = null
    this.outNode = null
  }

  // ------------------------------------------------------------------
  // Internals
  // ------------------------------------------------------------------

  private handleFrame(data: unknown): void {
    if (typeof data === 'string') {
      this.handleJsonFrame(data)
    } else if (data instanceof ArrayBuffer && this.sampleRate > 0) {
      this.schedulePcm(data, this.sampleRate)
    }
    // Binary frames before begin (or after cancel) have no defined rate.
  }

  private handleJsonFrame(text: string): void {
    let frame: { type?: string; sample_rate?: number }
    try {
      frame = JSON.parse(text)
    } catch {
      return
    }
    switch (frame.type) {
      case 'begin':
        this.sampleRate = Number(frame.sample_rate) || 0
        // A new turn on the same connection: re-arm the once-per-turn
        // onDone (the socket itself stays open across turns).
        this.finished = false
        break
      case 'end':
        this.finish()
        break
      case 'cancelled':
        this.cancel()
        this.finish()
        break
      default:
        break
    }
  }

  /** Decode one s16le mono chunk and schedule it gaplessly. */
  private schedulePcm(bytes: ArrayBuffer, sampleRate: number): void {
    const ctx = this.ctx
    const out = this.outNode
    if (!ctx || !out) return

    const view = new DataView(bytes)
    const count = Math.floor(bytes.byteLength / 2)
    if (count === 0) return

    const buffer = ctx.createBuffer(1, count, sampleRate)
    const channel = buffer.getChannelData(0)
    for (let i = 0; i < count; i++) {
      channel[i] = view.getInt16(i * 2, true) / 32768
    }

    const source = ctx.createBufferSource()
    source.buffer = buffer
    source.connect(out)
    const start = Math.max(ctx.currentTime, this.nextStart)
    source.start(start)
    this.nextStart = start + count / sampleRate
    this.sources.add(source)
    source.onended = () => {
      this.sources.delete(source)
    }
  }

  private finish(): void {
    if (this.finished) return
    this.finished = true
    this.onDone?.()
  }
}
