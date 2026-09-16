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
      options: ['medium', 'display'],
      description: 'Tine density — Voice Mode defaults to medium (6 tines)',
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

export const IdleBreathing: Story = { args: { size: 512, state: 'idle' } }

export const Listening: Story = {
  args: { size: 512, state: 'listening', source: speech },
}

export const Speaking: Story = {
  args: { size: 512, state: 'speaking', source: speech, sensitivity: 1.2 },
}

/** Entering `recognized` strums every string, spine first. Loops so the
 * strum repeats every couple of seconds. */
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
  args: { size: 512, state: 'listening', source: speech },
  decorators: [
    (StoryFn) => (
      <div style={{ background: '#000', padding: 48 }}>
        <StoryFn />
      </div>
    ),
  ],
}

/** The kiosk conversation as a loop: listening, recognized (strum),
 * thinking (contract + bulges), speaking — 2.5 s each. */
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

/** A level burst on one tine: silent, then `level` for `holdMs`. Each
 * button strikes a string through the same onset path a voice uses. */
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
  start(): void {}
  stop(): void {}
  readEnergies(out: Float32Array): number {
    const now = performance.now()
    for (let k = 0; k < out.length; k++) out[k] = now < this.until[k] ? this.level[k] : 0
    return out.length
  }
}

/** Pluck one string at a time and watch its pitch and sustain: the spine
 * quivers fast and dies in a quarter second, the outer arc swings slowly
 * for over a second. Strum walks all of them spine-first. */
export const PluckLab: Story = {
  render: () => {
    const count = tineCount('medium')
    const source = React.useMemo(() => new ManualPluckSource(count), [count])
    const [state, setState] = React.useState<VoiceVisualState>('speaking')
    const [level, setLevel] = React.useState(0.4)
    const ladder = STRING_LADDER.medium
    const label = (k: number) =>
      k === 0 ? 'spine' : k === count - 1 ? 'outer arc' : `lane ${k}`
    const strumOnce = () => {
      setState('recognized')
      setTimeout(() => setState('speaking'), 400)
    }
    return (
      <div style={{ display: 'grid', gap: 16, justifyItems: 'center' }}>
        <AudioReactiveHalbertMark size={512} state={state} source={source} />
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', justifyContent: 'center' }}>
          {ladder.map((s, k) => (
            <button key={k} type="button" onClick={() => source.strike(k, level)}>
              {label(k)} {s.frequencyHz.toFixed(1)} Hz / {s.decaySeconds.toFixed(2)} s
            </button>
          ))}
          <button type="button" onClick={strumOnce}>
            Strum
          </button>
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

/** Live microphone (user gesture starts the AudioContext). */
export const LiveMicrophone: Story = {
  render: () => {
    const [source, setSource] = React.useState<AudioEnergySource | null>(null)
    const [error, setError] = React.useState<string | null>(null)
    return (
      <div style={{ display: 'grid', gap: 16, justifyItems: 'center' }}>
        <AudioReactiveHalbertMark size={512} state="listening" source={source} />
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
