// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import * as React from 'react'
import type { Meta, StoryObj } from '@storybook/react'

import { HalbertMark } from '../primitives/HalbertMark'
import { ParametricSlider } from '../primitives/ParametricSlider'

interface FieldArgs {
  /** Rendered size of the mark, in pixels. */
  markSize: number
  /** How far the edge leans, as a percentage of the field's width. 0 is a vertical edge. */
  tilt: number
}

const FIELD_HEIGHT = 240

/**
 * The vermilion field: everything to the right of one straight edge.
 *
 * `split` sweeps that edge from just off the right of the frame (0, all paper)
 * to just off the left (100, all vermilion). The right-hand points run well
 * past the frame so the polygon stays simple at every position — pinned at
 * 100% they cross the frame's own edge and the shape folds over on itself.
 */
function wedge(split: number, tilt: number): string {
  const top = (100 + tilt) * (1 - split / 100)
  return `polygon(${top}% 0%, 400% 0%, 400% 100%, ${top - tilt}% 100%)`
}

/** Both copies sit in the same centred box, so they land on the same pixels. */
function MarkLayer({ size, ink, clipPath }: { size: number; ink: string; clipPath?: string }) {
  return (
    <div
      aria-hidden="true"
      style={{
        position: 'absolute',
        inset: 0,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        color: ink,
        clipPath,
      }}
    >
      <HalbertMark size={size} lines={7} tone="current" />
    </div>
  )
}

/**
 * Nothing below the slider, and nothing that grows or shrinks with its value:
 * a caption that rewrapped between one line and two moved the whole field on
 * every drag, which is the one thing a demo of a moving edge cannot do.
 */
function InversionDemo({ markSize, tilt }: FieldArgs) {
  const [split, setSplit] = React.useState(50)
  const clip = wedge(split, tilt)

  return (
    // A definite width, not a percentage: the centred story layout shrink-wraps
    // its child, so `min(540px, 100%)` resolves its 100% against a parent whose
    // width is the content — and the field collapses to the slider's label.
    <div style={{ width: 540, maxWidth: '100%', display: 'grid', gap: 'var(--space-5)' }}>
      <div
        role="img"
        aria-label="The Halbert mark across the edge between the paper field and the vermilion field"
        style={{
          position: 'relative',
          height: FIELD_HEIGHT,
          overflow: 'hidden',
          borderRadius: 'var(--radius-lg)',
          border: '1px solid var(--color-line)',
          background: 'var(--color-canvas)',
        }}
      >
        <div style={{ position: 'absolute', inset: 0, background: 'var(--color-accent)', clipPath: clip }} />
        <MarkLayer size={markSize} ink="var(--color-ink)" />
        <MarkLayer size={markSize} ink="var(--color-ink-on-accent)" clipPath={clip} />
      </div>

      <ParametricSlider
        label="Vermilion field"
        value={split}
        onValueChange={setSplit}
        formatValue={(v) => `${v}%`}
      />
    </div>
  )
}

const meta: Meta<FieldArgs> = {
  title: 'Brand/Stroke inversion',
  tags: ['autodocs'],
  parameters: {
    layout: 'centered',
    docs: {
      description: {
        component: [
          'Paper and vermilion are two grounds, and no single ink is legible on both. The mark is drawn',
          'twice — once in `--color-ink`, once in `--color-ink-on-accent` clipped to the vermilion — so each',
          'copy is a licensed pair and the seam falls exactly on the colour change.',
        ].join('\n'),
      },
    },
  },
  args: { markSize: 116, tilt: 60 },
  argTypes: {
    markSize: {
      control: { type: 'range', min: 32, max: 200, step: 4 },
      description: 'Rendered size of the mark, in pixels',
    },
    tilt: {
      control: { type: 'range', min: 0, max: 120, step: 5 },
      description: "How far the edge leans, as a percentage of the field's width. 0 is a vertical edge",
    },
  },
}
export default meta
type Story = StoryObj<FieldArgs>

export const Inversion: Story = {
  render: (args) => <InversionDemo {...args} />,
}
