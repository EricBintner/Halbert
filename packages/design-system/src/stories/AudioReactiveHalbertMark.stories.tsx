// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import * as React from 'react'
import type { Meta, StoryObj } from '@storybook/react'
import { AudioReactiveHalbertMark } from '../voice/AudioReactiveHalbertMark'
import type { VoiceVisualState } from '../voice/AudioReactiveHalbertMark'
import { createMediaStreamAnalyserSource, createNodeAnalyserSource } from '../voice/spectrum'
import type { AudioEnergySource } from '../voice/spectrum'
import { createSpeechBurstSource } from '../voice/demo'
import { STRING_LADDER } from '../voice/springs'
import { tineCount } from '../voice/geometry'

const meta: Meta<typeof AudioReactiveHalbertMark> = {
  title: 'Voice/AudioReactiveHalbertMark',
  tags: ['autodocs'],
  component: AudioReactiveHalbertMark,
  parameters: { layout: 'centered', backgrounds: { default: 'dark' } },
  argTypes: {
    density: {
      control: 'select',
      options: ['brand', 'medium', 'display'],
      description: 'Tine density — the voice mark is the ratified 7-line brand mark',
    },
    state: {
      control: 'select',
      options: ['idle', 'listening', 'recognized', 'thinking', 'speaking', 'error'],
    },
  },
}
export default meta
type Story = StoryObj<typeof AudioReactiveHalbertMark>

/** The shared demo voice (design doc 17): seeded syllable bursts with a
 * breath between phrases — the same source the marketing plate plays, so
 * the strings pluck here exactly as they do there. */
const speech = createSpeechBurstSource()

/** The same voice with a clap every few seconds, for the listening posture:
 * speech reads as presence, the clap as a startle. */
const speechWithClaps = createSpeechBurstSource({ seed: 3, clapEverySeconds: [5, 8] })

export const IdleBreathing: Story = { args: { size: 512, state: 'idle' } }

/** Listening never warps the lines: their ends withdraw along their own
 * paths. Speech holds a 10–15 % posture that drifts; a clap pulls them in
 * hard and lets go. */
export const Listening: Story = {
  args: { size: 512, state: 'listening', source: speechWithClaps },
}

export const Speaking: Story = {
  args: { size: 512, state: 'speaking', source: speech, sensitivity: 1.2 },
}

/** Entering `recognized` strums every string, spine first, on the still
 * withdrawn lines. Loops so the strum repeats every couple of seconds. */
export const Recognized: Story = {
  render: () => {
    const [state, setState] = React.useState<VoiceVisualState>('listening')
    React.useEffect(() => {
      const timer = setInterval(
        () => setState((s) => (s === 'listening' ? 'recognized' : 'listening')),
        1500,
      )
      return () => clearInterval(timer)
    }, [])
    return <AudioReactiveHalbertMark size={512} state={state} source={speech} />
  },
}

export const Thinking: Story = { args: { size: 512, state: 'thinking' } }
export const ErrorState: Story = { args: { size: 512, state: 'error' } }
export const OnDarkCanvas: Story = {
  args: { size: 512, state: 'listening', source: speechWithClaps },
  decorators: [
    (StoryFn) => (
      <div style={{ background: '#000', padding: 48 }}>
        <StoryFn />
      </div>
    ),
  ],
}

/** The kiosk conversation as a loop: listening (ends withdraw), recognized
 * (strum), thinking (contract + bulges), speaking (plucks) — 2.5 s each. */
export const VoiceModeLoop: Story = {
  render: () => {
    const cycle: VoiceVisualState[] = ['listening', 'recognized', 'thinking', 'speaking']
    const [index, setIndex] = React.useState(0)
    React.useEffect(() => {
      const timer = setInterval(() => setIndex((i) => (i + 1) % cycle.length), 2500)
      return () => clearInterval(timer)
    }, [])
    const state = cycle[index]
    return (
      <div style={{ display: 'grid', gap: 16, justifyItems: 'center' }}>
        <AudioReactiveHalbertMark size={512} state={state} source={speech} />
        <p style={{ fontFamily: 'monospace', textTransform: 'uppercase', opacity: 0.6 }}>{state}</p>
      </div>
    )
  },
}

/** A level burst on one tine (or all of them): silent, then `level` for
 * `holdMs`. Each button strikes through the same onset path a voice uses. */
class ManualPluckSource implements AudioEnergySource {
  private readonly until: number[]
  private readonly level: number[]
  constructor(count: number) {
    this.until = new Array(count).fill(-1)
    this.level = new Array(count).fill(0)
  }
  strike(k: number, level = 0.4, holdMs = 60): void {
    this.level[k] = level
    this.until[k] = performance.now() + holdMs
  }
  /** Every band at once for 40 ms: a clap. */
  clap(level = 0.8): void {
    for (let k = 0; k < this.until.length; k++) this.strike(k, level, 40)
  }
  /** A vowel's spread over the register for `holdMs`: someone talking.
   * The extremes (air above 4 kHz, room below 100 Hz) stay quiet, as they
   * do for a voice, so this never reads as broadband. */
  talk(holdMs = 2500): void {
    const vowel = [0, 0.15, 0.3, 0.3, 0.25, 0.1, 0.05]
    for (let k = 0; k < this.until.length; k++) {
      this.strike(k, vowel[Math.min(k, vowel.length - 1)], holdMs)
    }
  }
  start(): void {}
  stop(): void {}
  readEnergies(out: Float32Array): number {
    const now = performance.now()
    for (let k = 0; k < out.length; k++) out[k] = now < this.until[k] ? this.level[k] : 0
    return out.length
  }
}

/** Strike one string at a time and watch its pitch and sustain (speaking),
 * or switch to listening and clap: the lines withdraw their ends, hard for
 * the clap, gently while "talking", and slide back out afterwards. */
export const PluckLab: Story = {
  render: () => {
    const count = tineCount()
    const source = React.useMemo(() => new ManualPluckSource(count), [count])
    const [state, setState] = React.useState<VoiceVisualState>('speaking')
    const [level, setLevel] = React.useState(0.4)
    const ladder = STRING_LADDER.brand
    const label = (k: number) =>
      k === 0 ? 'spine' : k === count - 1 ? 'outer arc' : `lane ${k}`
    const strumOnce = () => {
      const back = state
      setState('recognized')
      setTimeout(() => setState(back), 400)
    }
    return (
      <div style={{ display: 'grid', gap: 16, justifyItems: 'center' }}>
        <AudioReactiveHalbertMark size={512} state={state} source={source} />
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', justifyContent: 'center' }}>
          <label>
            State{' '}
            <select value={state} onChange={(e) => setState(e.target.value as VoiceVisualState)}>
              <option value="speaking">speaking</option>
              <option value="listening">listening</option>
              <option value="idle">idle</option>
              <option value="thinking">thinking</option>
            </select>
          </label>
          <button type="button" onClick={() => source.clap()}>
            Clap
          </button>
          <button type="button" onClick={() => source.talk()}>
            Talk 2.5 s
          </button>
          <button type="button" onClick={strumOnce}>
            Strum
          </button>
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', justifyContent: 'center' }}>
          {ladder.map((s, k) => (
            <button key={k} type="button" onClick={() => source.strike(k, level)}>
              {label(k)} {s.frequencyHz.toFixed(1)} Hz / {s.decaySeconds.toFixed(2)} s
            </button>
          ))}
        </div>
        <label>
          Strike level {level.toFixed(2)}{' '}
          <input
            type="range"
            min={0.05}
            max={1}
            step={0.05}
            value={level}
            onChange={(e) => setLevel(Number(e.target.value))}
          />
        </label>
      </div>
    )
  },
}

/** Live microphone (user gesture starts the AudioContext). Clap. */
export const LiveMicrophone: Story = {
  render: () => {
    const [source, setSource] = React.useState<AudioEnergySource | null>(null)
    const [state, setState] = React.useState<VoiceVisualState>('listening')
    const [error, setError] = React.useState<string | null>(null)
    return (
      <div style={{ display: 'grid', gap: 16, justifyItems: 'center' }}>
        <AudioReactiveHalbertMark size={512} state={state} source={source} />
        <div style={{ display: 'flex', gap: 8 }}>
          <button
            onClick={async () => {
              try {
                const stream = await navigator.mediaDevices.getUserMedia({
                  audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
                })
                setSource(createMediaStreamAnalyserSource(stream))
              } catch (e) {
                setError(String(e))
              }
            }}
          >
            Enable microphone
          </button>
          <label>
            State{' '}
            <select value={state} onChange={(e) => setState(e.target.value as VoiceVisualState)}>
              <option value="listening">listening</option>
              <option value="speaking">speaking</option>
            </select>
          </label>
        </div>
        {error && <p role="alert">{error}</p>}
      </div>
    )
  },
}

/** Pure test tones through a quiet gain: sweep 80 Hz - 6 kHz and watch the
 * resonance walk from the outermost arc (sub-bass) to the center spine
 * (brilliance) — a manual validation of the log-scale band mapping. */
export const OscillatorTestTones: Story = {
  render: () => {
    const [freq, setFreq] = React.useState(220)
    const [source, setSource] = React.useState<AudioEnergySource | null>(null)
    const ctxRef = React.useRef<AudioContext | null>(null)
    const oscRef = React.useRef<OscillatorNode | null>(null)
    const start = () => {
      const ctx = new AudioContext()
      const osc = ctx.createOscillator()
      osc.frequency.value = freq
      const gain = ctx.createGain()
      gain.gain.value = 0.15 // audible but quiet in Storybook
      osc.connect(gain)
      gain.connect(ctx.destination)
      osc.start()
      ctxRef.current = ctx
      oscRef.current = osc
      setSource(createNodeAnalyserSource(gain))
    }
    React.useEffect(
      () => () => {
        oscRef.current?.stop()
        void ctxRef.current?.close()
      },
      [],
    )
    return (
      <div style={{ display: 'grid', gap: 16, justifyItems: 'center' }}>
        <AudioReactiveHalbertMark size={512} state="speaking" source={source} />
        <label>
          Tone: {freq} Hz{' '}
          <input
            type="range"
            min={80}
            max={6000}
            value={freq}
            onChange={(e) => {
              const f = Number(e.target.value)
              setFreq(f)
              if (oscRef.current) oscRef.current.frequency.value = f
            }}
          />
        </label>
        <button onClick={start}>Start tone</button>
      </div>
    )
  },
}
