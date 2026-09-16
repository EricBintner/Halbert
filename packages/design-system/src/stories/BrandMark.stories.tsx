// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import type { Meta, StoryObj } from '@storybook/react'

import { HalbertMark } from '../primitives/HalbertMark'

/**
 * The two ratified brand marks (founder, 2026-09-15):
 *
 *   Primary — 7-line: spine + 6 U-lanes, pitch 72, stroke 48, gap 24.
 *     2:1 stroke:gap, the proportion of the retired 10-line display mark
 *     (48/72 = 32/48 = 2/3 of pitch). Ratified primary 2026-09-10
 *     (MD-04); stroke width ratified 2026-09-15.
 *   Micro — 4-line: spine + 3 U-lanes, pitch 144, stroke 80, gap 64.
 *     Favicons, OS status bars, micro-icons (the 3-line tier is retired).
 *
 * This story is the reference page: what "the Halbert mark" means, with
 * the size ladder each tier is calibrated for. The line-count exploration
 * that led here lives on in Drafts/HalbertMarkTiers (kept deliberately —
 * design thinking residue, not a second source of truth).
 */
const meta: Meta<typeof HalbertMark> = {
  title: 'Brand/BrandMark',
  tags: ['autodocs'],
  component: HalbertMark,
  args: {
    size: 64,
    density: 'auto',
    lines: undefined,
    tone: 'accent',
  },
  argTypes: {
    lines: {
      control: 'select',
      options: [undefined, 10, 8, 7, 6, 5, 4, 3],
      description: 'Explicit line count. Brand: 7 (primary) / 4 (micro).',
    },
    density: {
      control: 'select',
      options: ['auto', '10', '8', '7', '6', '5', '4', '3', 'display', 'medium', 'compact', 'small'],
      description: 'Optical density tier',
    },
    tone: {
      control: 'select',
      options: ['accent', 'ink', 'canvas', 'current', 'badge'],
      description: 'Brand color tone preset',
    },
    size: {
      control: { type: 'range', min: 16, max: 256, step: 4 },
      description: 'Rendered pixel size',
    },
  },
  parameters: {
    docs: {
      description: {
        component:
          'The official Halbert brand marks. Primary: 7-line, sw 48. Micro: 4-line, sw 80. Ratified by the founder 2026-09-10 (MD-04) and 2026-09-15 (stroke weight).',
      },
    },
  },
}
export default meta

export const Playground: StoryObj<typeof HalbertMark> = {}

/* ------------------------------------------------------------------ */
/* Shared layout helpers                                               */
/* ------------------------------------------------------------------ */

const CARD = {
  background: 'var(--color-surface, #FFFFFF)',
  padding: 24,
  borderRadius: 12,
  border: '1px solid var(--color-hairline, rgba(26,25,24,0.08))',
}

const cardTitle = {
  margin: '0 0 4px 0',
  fontSize: 18,
  fontWeight: 700 as const,
  color: 'var(--color-ink, #1A1918)',
}

const cardSub = {
  margin: '0 0 24px 0',
  fontSize: 13,
  color: 'var(--color-ink-secondary, #5E5B56)',
}

const markCardHead = (name: string, tag: string) => (
  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
    <span style={{ fontWeight: 700, fontSize: 15, color: 'var(--color-accent, #D34E24)' }}>{name}</span>
    <span style={{ fontSize: 11, fontFamily: 'var(--font-mono)', background: 'var(--color-accent, #D34E24)', color: '#FFF', padding: '2px 6px', borderRadius: 4 }}>
      {tag}
    </span>
  </div>
)

const markCardFoot = (text: string) => (
  <p style={{ margin: 0, fontSize: 12, color: 'var(--color-ink-secondary, #5E5B56)', lineHeight: 1.4 }}>{text}</p>
)

/* ------------------------------------------------------------------ */
/* Story: the two official marks, side by side                         */
/* ------------------------------------------------------------------ */

export const OfficialMarks: StoryObj = {
  name: 'Official marks — primary 7-line & micro 4-line',
  render: () => (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 48, maxWidth: 1200 }}>
      <div style={CARD}>
        <h3 style={cardTitle}>Ratified brand marks</h3>
        <p style={cardSub}>
          Two marks carry the brand: a <strong>7-line primary</strong> for display and UI, and a <strong>4-line micro</strong> for
          favicons and status bars. Everything else in the ladder is a drafts-stage exploration (see Drafts). Ratified by the
          founder: line counts 2026-09-10 (MD-04), stroke weights 2026-09-15.
        </p>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 20 }}>
          {/* Primary — 7-line */}
          <div
            style={{
              background: 'var(--color-canvas, #F7F5F0)',
              padding: 20,
              borderRadius: 8,
              border: '2px solid var(--color-accent, #D34E24)',
            }}
          >
            {markCardHead('7 Lines — Primary', 'Official')}
            <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 16 }}>
              <HalbertMark size={140} lines={7} tone="accent" />
              <HalbertMark size={64} lines={7} tone="accent" />
              <HalbertMark size={48} lines={7} tone="accent" />
              <HalbertMark size={32} lines={7} tone="accent" />
            </div>
            {markCardFoot(
              'Spine + 6 U-curves · pitch 72 · stroke 48 · gap 24 (2:1 stroke:gap, the retired 10-line display proportion). Use at ≥32px; the site hero animation rides this geometry.',
            )}
          </div>

          {/* Micro — 4-line */}
          <div
            style={{
              background: 'var(--color-canvas, #F7F5F0)',
              padding: 20,
              borderRadius: 8,
              border: '2px solid var(--color-accent, #D34E24)',
            }}
          >
            {markCardHead('4 Lines — Micro', 'Official')}
            <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 16 }}>
              <HalbertMark size={64} lines={4} tone="accent" />
              <HalbertMark size={32} lines={4} tone="accent" />
              <HalbertMark size={24} lines={4} tone="accent" />
              <HalbertMark size={16} lines={4} tone="accent" />
            </div>
            {markCardFoot(
              'Spine + 3 U-curves · pitch 144 · stroke 80 · gap 64. Favicons, OS status bars, micro-icons; retires the 3-line tier (≤32px, `density="small"` resolves here).',
            )}
          </div>
        </div>
      </div>

      {/* Tone variants */}
      <div style={CARD}>
        <h3 style={cardTitle}>Tone variants</h3>
        <p style={cardSub}>
          The two marks across the ratified tone presets — accent (vermilion), ink (charcoal), canvas (bone, for dark
          surfaces), and the inverted badge tile.
        </p>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 24 }}>
          {(
            [
              ['accent', 'Primary · 7-line', 7, 96],
              ['ink', 'Primary · 7-line', 7, 96],
              ['canvas', 'Primary · 7-line', 7, 96],
              ['badge', 'Primary · 7-line', 7, 96],
              ['accent', 'Micro · 4-line', 4, 64],
              ['ink', 'Micro · 4-line', 4, 64],
              ['canvas', 'Micro · 4-line', 4, 64],
              ['badge', 'Micro · 4-line', 4, 64],
            ] as const
          ).map(([tone, group, lines, size]) => (
            <div key={`${group}-${tone}`} style={{ textAlign: 'center' }}>
              <HalbertMark size={size} lines={lines} tone={tone} />
              <div style={{ fontSize: 10, fontFamily: 'var(--font-mono)', marginTop: 8, color: 'var(--color-ink-tertiary, #8C877D)' }}>
                {group} · {tone}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Size ladder */}
      <div style={CARD}>
        <h3 style={cardTitle}>Size ladder</h3>
        <p style={cardSub}>
          Primary at display sizes; micro where the primary would collapse. The 24/16px micro renders keep the triple nest
          legible where the 7-line would blur to mud.
        </p>
        <div style={{ display: 'flex', alignItems: 'flex-end', flexWrap: 'wrap', gap: 20 }}>
          {[256, 192, 140, 96, 64, 48, 32, 24, 16].map((size) => (
            <div key={size} style={{ textAlign: 'center' }}>
              <div style={{ display: 'flex', gap: 8, justifyContent: 'center', alignItems: 'flex-end', height: 256 }}>
                <HalbertMark size={size} lines={7} tone="accent" />
                {size <= 32 && <HalbertMark size={size} lines={4} tone="accent" />}
              </div>
              <div style={{ fontSize: 10, fontFamily: 'var(--font-mono)', marginTop: 8, color: 'var(--color-ink-tertiary, #8C877D)' }}>
                {size}px{size <= 32 ? ' · 7 / 4' : ''}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Spec table */}
      <div style={CARD}>
        <h3 style={cardTitle}>Specification</h3>
        <p style={cardSub}>1024 × 1024 viewBox · outer radius 432 · leg tops on the 432 circle · round caps and joins.</p>
        <table style={{ borderCollapse: 'collapse', fontSize: 13, width: '100%', maxWidth: 720 }}>
          <thead>
            <tr style={{ textAlign: 'left', borderBottom: '2px solid var(--color-hairline, rgba(26,25,24,0.12))' }}>
              <th style={{ padding: '8px 12px' }}>Mark</th>
              <th style={{ padding: '8px 12px' }}>Composition</th>
              <th style={{ padding: '8px 12px' }}>Pitch</th>
              <th style={{ padding: '8px 12px' }}>Stroke</th>
              <th style={{ padding: '8px 12px' }}>Gap</th>
              <th style={{ padding: '8px 12px' }}>Use</th>
            </tr>
          </thead>
          <tbody style={{ fontFamily: 'var(--font-mono)' }}>
            <tr style={{ borderBottom: '1px solid var(--color-hairline, rgba(26,25,24,0.08))' }}>
              <td style={{ padding: '8px 12px', fontWeight: 700 }}>Primary · 7-line</td>
              <td style={{ padding: '8px 12px' }}>spine + 6 U</td>
              <td style={{ padding: '8px 12px' }}>72</td>
              <td style={{ padding: '8px 12px' }}>48 (2:1)</td>
              <td style={{ padding: '8px 12px' }}>24</td>
              <td style={{ padding: '8px 12px' }}>≥32px · display, UI, hero animation</td>
            </tr>
            <tr>
              <td style={{ padding: '8px 12px', fontWeight: 700 }}>Micro · 4-line</td>
              <td style={{ padding: '8px 12px' }}>spine + 3 U</td>
              <td style={{ padding: '8px 12px' }}>144</td>
              <td style={{ padding: '8px 12px' }}>80</td>
              <td style={{ padding: '8px 12px' }}>64</td>
              <td style={{ padding: '8px 12px' }}>≤32px · favicons, status bars</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  ),
}

/* ------------------------------------------------------------------ */
/* Story: side-by-side with the retired marks (provenance)              */
/* ------------------------------------------------------------------ */

export const Provenance: StoryObj = {
  name: 'Provenance — retired 10-line & 3-line',
  render: () => (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 48, maxWidth: 1200 }}>
      <div style={CARD}>
        <h3 style={cardTitle}>Where the proportions come from</h3>
        <p style={cardSub}>
          The primary mark's 2:1 stroke:gap is not a new invention — it is the proportion of the retired 10-line display
          mark (sw 32 on pitch 48), carried onto the 7-line's pitch 72 as sw 48. The retired marks stay here for
          reference; they are not part of the brand system and should not be used in new work.
        </p>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 20 }}>
          <div style={{ background: 'var(--color-canvas, #F7F5F0)', padding: 20, borderRadius: 8, border: '2px solid var(--color-accent, #D34E24)' }}>
            {markCardHead('7 Lines', 'Primary')}
            <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 16 }}>
              <HalbertMark size={110} lines={7} tone="accent" />
            </div>
            {markCardFoot('pitch 72 · stroke 48 · gap 24 — official primary.')}
          </div>
          <div style={{ background: 'var(--color-canvas, #F7F5F0)', padding: 20, borderRadius: 8, border: '1px solid var(--color-hairline, rgba(26,25,24,0.12))' }}>
            {markCardHead('10 Lines', 'Retired')}
            <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 16 }}>
              <HalbertMark size={110} lines={10} tone="accent" />
            </div>
            {markCardFoot('pitch 48 · stroke 26.67 · gap 21.33 — retired display mark; source of the primary’s 2:1 feel (sw/pitch = 32/48 on the animated original).')}
          </div>
          <div style={{ background: 'var(--color-canvas, #F7F5F0)', padding: 20, borderRadius: 8, border: '1px solid var(--color-hairline, rgba(26,25,24,0.12))' }}>
            {markCardHead('4 Lines', 'Micro')}
            <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 16 }}>
              <HalbertMark size={64} lines={4} tone="accent" />
            </div>
            {markCardFoot('pitch 144 · stroke 80 · gap 64 — official micro.')}
          </div>
          <div style={{ background: 'var(--color-canvas, #F7F5F0)', padding: 20, borderRadius: 8, border: '1px solid var(--color-hairline, rgba(26,25,24,0.12))' }}>
            {markCardHead('3 Lines', 'Retired')}
            <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 16 }}>
              <HalbertMark size={64} lines={3} tone="accent" />
            </div>
            {markCardFoot('pitch 216 · stroke 116 — retired micro; replaced by the 4-line.')}
          </div>
        </div>
      </div>
    </div>
  ),
}