// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import * as React from 'react'
import type { Meta, StoryObj } from '@storybook/react'

import { HalbertMark, halbertMarkGeometry, HALBERT_MARK_UNITS } from '../primitives/HalbertMark'
import { IconDock, type IconDockItem } from '../surfaces/IconDock'
import { GitHubIcon, StorybookIcon, XIcon, RedditIcon } from '../icons/brands'
import { useId, useMeasuredWidth } from '../lib'

/**
 * The mark's stroke is a ground, not a background.
 *
 * This page is a technique, not an exported component: the field below is
 * assembled here from the pieces that do ship — the mark geometry, the icon
 * dock, the tokens. The marketing site runs the same three layers at full
 * viewport, against a scrolling camera.
 */

const MARK = halbertMarkGeometry(7)

const DOCK_ITEMS: IconDockItem[] = [
  { id: 'github', label: 'GitHub', icon: GitHubIcon, href: 'https://github.com/EricBintner/Halbert' },
  { id: 'storybook', label: 'Storybook', icon: StorybookIcon, href: 'https://storybook.halbert.computer' },
  { id: 'x', label: 'X', icon: XIcon, disabled: true },
  { id: 'reddit', label: 'Reddit', icon: RedditIcon, disabled: true },
]

/* React's useId yields ":r0:", and a colon cannot appear inside url(#…). */
const cssSafeId = (id: string) => id.replace(/:/g, '')

/* The decorative copy must not hand assistive tech or the tab key a second set
 * of the same controls. aria-hidden takes it out of the tree; inert takes its
 * links out of the tab order. */
const DECORATIVE = { inert: '' } as unknown as React.HTMLAttributes<HTMLDivElement>

interface FieldArgs {
  /** Width of the mark, as a percentage of the field's width. */
  markScale: number
  /** Horizontal centre of the mark, as a percentage of the field's width. */
  markX: number
  /** Vertical nudge from the centred position, in pixels. */
  markY: number
}

/**
 * Where the mark sits vertically when `markY` is 0.
 *
 * The lanes fan outward as they descend, so the interesting band — several
 * lanes wide, still vertical — is around 0.30 of the way down the square.
 * Anchoring that band to the middle of the field keeps one set of args
 * working at any field height, which is what lets the anatomy panels below
 * reuse the args from the overlay above.
 */
const LANE_BAND = 0.3

type Layer = 'composite' | 'ink' | 'mask'

function StrokeField({
  markScale,
  markX,
  markY,
  height,
  layer = 'composite',
  children,
}: FieldArgs & { height: number; layer?: Layer; children?: React.ReactNode }) {
  const ref = React.useRef<HTMLDivElement>(null)
  const width = useMeasuredWidth(ref)
  const maskId = `halbert-stroke-mask-${cssSafeId(useId())}`

  // useMeasuredWidth is honest about not having measured yet, so the first
  // paint has no width to scale against. Draw nothing rather than a degenerate
  // SVG; the real geometry lands on the next frame.
  const measured = width > 0
  // Sized against the field, not in absolute pixels: the story canvas, the
  // docs page and a phone are three different widths, and a fixed size that
  // frames well on one of them overruns another.
  const size = (width * markScale) / 100
  const left = (width * markX) / 100 - size / 2
  const top = height / 2 - size * LANE_BAND + markY
  const transform = `translate(${left} ${top}) scale(${size / HALBERT_MARK_UNITS})`

  const strokes = (stroke: string) => (
    <g
      transform={transform}
      fill="none"
      stroke={stroke}
      strokeWidth={MARK.strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d={MARK.d} />
    </g>
  )

  return (
    <div
      ref={ref}
      style={{
        position: 'relative',
        height,
        overflow: 'hidden',
        borderRadius: 'var(--radius-lg)',
        border: '1px solid var(--color-line)',
        background: layer === 'mask' ? 'var(--color-surface-subtle)' : 'var(--color-canvas)',
      }}
    >
      {measured && layer !== 'ink' && (
        <svg
          width={width}
          height={height}
          viewBox={`0 0 ${width} ${height}`}
          style={{ position: 'absolute', inset: 0 }}
          aria-hidden="true"
        >
          <defs>
            {/* White here is a mask channel, not a colour: in a luminance mask
             * it means "fully opaque". No palette value belongs in a mask. */}
            <mask id={maskId} maskUnits="userSpaceOnUse" x={0} y={0} width={width} height={height}>
              {strokes('white')}
            </mask>
          </defs>
          {strokes(layer === 'mask' ? 'var(--color-ink)' : 'var(--color-accent)')}
        </svg>
      )}

      {layer !== 'mask' && (
        <div style={{ position: 'absolute', inset: 0, color: 'var(--color-ink)' }}>{children}</div>
      )}

      {measured && layer === 'composite' && (
        <div
          {...DECORATIVE}
          aria-hidden="true"
          style={{
            position: 'absolute',
            inset: 0,
            pointerEvents: 'none',
            color: 'var(--color-ink-on-accent)',
            WebkitMaskImage: `url(#${maskId})`,
            maskImage: `url(#${maskId})`,
          }}
        >
          {children}
        </div>
      )}
    </div>
  )
}

/**
 * The specimen that crosses the stroke: the wordmark as the folio bar sets it,
 * and the links dock. Centred rather than pinned to the corners, so the
 * crossing holds at any width — a corner-pinned copy misses the mark entirely
 * on a wide canvas, which is the one thing this page must not do.
 */
function FieldContent() {
  return (
    <div
      style={{
        position: 'absolute',
        inset: 0,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 'var(--space-6)',
      }}
    >
      <span
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 'var(--space-3)',
          fontFamily: 'var(--font-mono)',
          fontSize: 14,
          fontWeight: 700,
          letterSpacing: 'var(--tracking-label)',
        }}
      >
        <HalbertMark size={22} lines={6} tone="current" />
        HALBERT
      </span>

      <IconDock items={DOCK_ITEMS} label="Halbert elsewhere" />
    </div>
  )
}

/**
 * A labelled panel in the anatomy diagram.
 *
 * The illustration is decorative: three panels showing the same specimen would
 * otherwise put three identically named navigation landmarks in the tree and
 * twelve duplicate links in the tab order. The caption carries the meaning,
 * and the working copy is the Overlay story above.
 */
function Caption({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <p
        style={{
          margin: '0 0 var(--space-2)',
          fontFamily: 'var(--font-mono)',
          fontSize: 11,
          letterSpacing: 'var(--tracking-label)',
          textTransform: 'uppercase',
          color: 'var(--color-ink-tertiary)',
        }}
      >
        {label}
      </p>
      <div {...DECORATIVE} aria-hidden="true">
        {children}
      </div>
    </div>
  )
}

const meta: Meta<FieldArgs> = {
  title: 'Brand/Stroke inversion',
  tags: ['autodocs'],
  parameters: {
    layout: 'padded',
    controls: { expanded: true },
    docs: {
      description: {
        component: [
          "The mark's stroke is a ground, not a background. Anything that crosses it — the wordmark, a",
          'nav label, an icon — flips to the on-accent ink for exactly the pixels the stroke covers, so one',
          'element reads correctly on paper and on vermilion at the same time.',
          '',
          'It is drawn three times over: the stroke itself in the identity shade, the content in ink, and a',
          'second copy of that content in `--color-ink-on-accent`, masked to the stroke. The masked copy is',
          'decorative — `aria-hidden` and `inert` — so its duplicate controls never reach a screen reader or',
          'the tab order.',
          '',
          'Switch the toolbar to After hours. The accent lifts, `--color-ink-on-accent` flips to the dark',
          'ground, and the inverted copy goes dark instead of light. Nothing in the technique changes; the',
          'tokens carry it.',
          '',
          'The mask draws from `halbertMarkGeometry()`, the same path data the `HalbertMark` component',
          'renders, so the stroke a visitor sees and the stroke that does the cutting cannot drift apart.',
          '',
          'The accessibility panel reports contrast here as *incomplete* rather than passing, and it is right',
          'to: no automated check can resolve a colour pair when the ground is an SVG that changes under every',
          'glyph. That is the argument for the technique rather than against it. One ink over two grounds',
          'would have to lose on one of them; drawing the content twice makes each copy a licensed pair —',
          'ink on canvas, on-accent ink on the accent — so contrast holds by construction instead of by',
          'measurement.',
        ].join('\n'),
      },
    },
  },
  args: { markScale: 72, markX: 50, markY: 0 },
  argTypes: {
    markScale: {
      control: { type: 'range', min: 20, max: 400, step: 2 },
      description: "Width of the mark, as a percentage of the field's width. Past roughly 250 the lanes stop reading as a mark and become one vermilion ground with a curved edge, which is the scale the marketing hero runs at",
    },
    markX: {
      control: { type: 'range', min: -20, max: 120, step: 1 },
      description: "Horizontal centre of the mark, as a percentage of the field's width",
    },
    markY: {
      control: { type: 'range', min: -240, max: 240, step: 4 },
      description: 'Vertical nudge from the centred position, in pixels',
    },
  },
}
export default meta
type Story = StoryObj<FieldArgs>

/**
 * Drag the mark across the field and watch the glyphs and the wordmark flip as
 * each lane passes under them.
 */
export const Overlay: Story = {
  render: (args) => (
    <StrokeField {...args} height={320}>
      <FieldContent />
    </StrokeField>
  ),
}

/** The three layers, pulled apart. */
export const Anatomy: Story = {
  parameters: { controls: { disable: true } },
  render: (args) => {
    const height = 190
    return (
      <div style={{ display: 'grid', gap: 'var(--space-6)' }}>
        <Caption label="1 — the content, in ink">
          <StrokeField {...args} height={height} layer="ink">
            <FieldContent />
          </StrokeField>
        </Caption>
        <Caption label="2 — the stroke, as a mask">
          <StrokeField {...args} height={height} layer="mask" />
        </Caption>
        <Caption label="3 — composite: a second copy in on-accent ink, cut to that mask">
          <StrokeField {...args} height={height}>
            <FieldContent />
          </StrokeField>
        </Caption>
      </div>
    )
  },
}
