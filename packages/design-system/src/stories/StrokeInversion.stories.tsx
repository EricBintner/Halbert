// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import * as React from 'react'
import type { Meta, StoryObj } from '@storybook/react'

import { HalbertMark } from '../primitives/HalbertMark'
import { ParametricSlider } from '../primitives/ParametricSlider'
import { useMeasuredWidth } from '../lib'

/**
 * Two grounds, one mark, two inks.
 *
 * The page is a technique rather than an exported component: a field split
 * between paper and vermilion, with the mark drawn twice so each half wears
 * the ink its ground licenses.
 */

interface FieldArgs {
  /** Rendered size of the mark, in pixels. */
  markSize: number
  /** How far the edge leans, as a percentage of the field's width. 0 is a vertical edge. */
  tilt: number
}

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

const FIELD_HEIGHT = 200

/**
 * Which ground the mark is standing on, worked out rather than guessed.
 *
 * The slider's preview is the half of it that says what the setting *does*, so
 * a threshold picked by eye would be the one dishonest line on a page about
 * honest pairs. The edge leans, so it meets the mark's box at two different
 * x positions; the mark is crossed when that span overlaps the box at all.
 */
function stateOf(split: number, tilt: number, markSize: number, width: number): string {
  const top = (100 + tilt) * (1 - split / 100)
  const halfW = width > 0 ? (markSize / 2 / width) * 100 : 0
  const halfH = (markSize / 2 / FIELD_HEIGHT) * 100
  const atMarkTop = top - (tilt * (50 - halfH)) / 100
  const atMarkBottom = top - (tilt * (50 + halfH)) / 100

  if (atMarkBottom > 50 + halfW) return 'The mark is clear of the edge, drawn in ink on paper.'
  if (atMarkTop < 50 - halfW) return 'The mark is clear of the edge, drawn in on-accent ink on vermilion.'
  return 'The edge crosses the mark. Each half wears the ink its ground licenses.'
}

function InversionDemo({ markSize, tilt }: FieldArgs) {
  const [split, setSplit] = React.useState(50)
  const fieldRef = React.useRef<HTMLDivElement>(null)
  const width = useMeasuredWidth(fieldRef)
  const clip = wedge(split, tilt)
  const state = (value: number) => stateOf(value, tilt, markSize, width)

  return (
    <div style={{ width: 'min(460px, 100%)', display: 'grid', gap: 'var(--space-5)' }}>
      <div
        ref={fieldRef}
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
        ariaValueText={(v) => `${v} percent vermilion. ${state(v)}`}
        preview={state}
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
          'Paper and vermilion are two grounds, and no single ink is legible on both. Ink on the accent',
          'measures 4.30:1 and fails; on-accent ink on paper is worse. A mark that lies across the edge',
          'between them therefore cannot be drawn once.',
          '',
          'So it is drawn twice. One copy in `--color-ink`, a second in `--color-ink-on-accent` clipped to',
          'exactly the vermilion region, laid on the same pixels. Each copy is then a licensed pair, and the',
          'seam falls precisely on the colour change. Drag the slider and watch the mark hand itself over.',
          '',
          'Switch the toolbar to After hours. The accent lifts, `--color-ink-on-accent` flips to the dark',
          'ground, and the inverted half goes dark instead of light. The technique does not change; the',
          'tokens carry it.',
          '',
          'The marketing site runs this at full viewport, where the clip is the mark itself at hero scale',
          'and the content crossing it is the folio bar and the links dock. The mechanism is the one here.',
        ].join('\n'),
      },
    },
  },
  args: { markSize: 96, tilt: 60 },
  argTypes: {
    markSize: {
      control: { type: 'range', min: 32, max: 160, step: 4 },
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

/** Drag the slider to sweep the vermilion across the mark. */
export const Inversion: Story = {
  render: (args) => <InversionDemo {...args} />,
}
