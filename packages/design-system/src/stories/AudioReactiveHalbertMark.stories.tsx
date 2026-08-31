// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import * as React from 'react'
import type { Meta, StoryObj } from '@storybook/react'
import { AudioReactiveHalbertMark } from '../voice/AudioReactiveHalbertMark'
import {
  SyntheticEnergySource,
  createMediaStreamAnalyserSource,
  createNodeAnalyserSource,
} from '../voice/spectrum'
import type { AudioEnergySource } from '../voice/spectrum'

const meta: Meta<typeof AudioReactiveHalbertMark> = {
  title: 'Voice/AudioReactiveHalbertMark',
  component: AudioReactiveHalbertMark,
  parameters: { layout: 'centered', backgrounds: { default: 'dark' } },
}
export default meta
type Story = StoryObj<typeof AudioReactiveHalbertMark>

/** Vowel-ish formant sweep: energy walks from chest (outer) to air (inner). */
const formantSweep = new SyntheticEnergySource((t, out) => {
  for (let k = 0; k < 10; k++) {
    const center = 4.5 + 4 * Math.sin(t * 0.9)
    out[k] = Math.exp(-((k - center) ** 2) / 3) * (0.55 + 0.45 * Math.sin(t * 6 + k))
  }
})

export const IdleBreathing: Story = { args: { size: 512, state: 'idle' } }

export const Listening: Story = {
  args: { size: 512, state: 'listening', source: formantSweep },
}

export const Speaking: Story = {
  args: { size: 512, state: 'speaking', source: formantSweep, sensitivity: 1.2 },
}

export const Thinking: Story = { args: { size: 512, state: 'thinking' } }
export const ErrorState: Story = { args: { size: 512, state: 'error' } }
export const OnDarkCanvas: Story = {
  args: { size: 512, state: 'listening', source: formantSweep },
  decorators: [
    (StoryFn) => (
      <div style={{ background: '#000', padding: 48 }}>
        <StoryFn />
      </div>
    ),
  ],
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
