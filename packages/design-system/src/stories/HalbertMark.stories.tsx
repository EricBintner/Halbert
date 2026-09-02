// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import type { Meta, StoryObj } from '@storybook/react'

import { HalbertMark } from '../primitives/HalbertMark'

const meta: Meta<typeof HalbertMark> = {
  title: 'Primitives/HalbertMark',
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
      description: 'Explicit line count (3, 4, 5, 6, 7, 8, 10)',
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
}
export default meta

export const Playground: StoryObj<typeof HalbertMark> = {}

export const OpticalTiers: StoryObj = {
  render: () => {
    const LINE_COUNTS: Array<{ count: 10 | 8 | 7 | 6 | 5 | 4 | 3; label: string; desc: string; candidate?: string }> = [
      { count: 10, label: '10 Lines', desc: '100% detail · N=9 (original display)' },
      { count: 8, label: '8 Lines', desc: '80% detail · N=7 (high-detail candidate)', candidate: '8-line alternative' },
      { count: 7, label: '7 Lines', desc: '70% detail · N=6 (proposed unified primary)', candidate: 'Proposed Primary' },
      { count: 6, label: '6 Lines', desc: '60% detail · N=5 (previous medium tier)' },
      { count: 5, label: '5 Lines', desc: '50% detail · N=4 (intermediate)' },
      { count: 4, label: '4 Lines', desc: '40% detail · N=3 (proposed micro/small mark)', candidate: 'Proposed Micro' },
      { count: 3, label: '3 Lines', desc: '30% detail · N=2 (previous 3-line micro)' },
    ]

    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 48, fontFamily: 'var(--font-sans)', maxWidth: 1200 }}>
        
        {/* Section 1: Candidate Head-to-Head Comparison */}
        <div style={{ background: 'var(--color-surface, #FFFFFF)', padding: 24, borderRadius: 12, border: '1px solid var(--color-hairline, rgba(26,25,24,0.08))' }}>
          <h3 style={{ margin: '0 0 4px 0', fontSize: 18, fontWeight: 700, color: 'var(--color-ink, #1A1918)' }}>
            Candidate Replacement Focus: 7-Line vs 10/8/6 &amp; 4-Line vs 3
          </h3>
          <p style={{ margin: '0 0 24px 0', fontSize: 13, color: 'var(--color-ink-secondary, #5E5B56)' }}>
            Comparing the proposed <strong>7-line</strong> primary replacement and <strong>4-line</strong> micro replacement against their surrounding counterparts.
          </p>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 20 }}>
            {/* 7 Lines Focus */}
            <div style={{ background: 'var(--color-canvas, #F7F5F0)', padding: 20, borderRadius: 8, border: '2px solid var(--color-accent, #D34E24)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                <span style={{ fontWeight: 700, fontSize: 15, color: 'var(--color-accent, #D34E24)' }}>7 Lines (Candidate)</span>
                <span style={{ fontSize: 11, fontFamily: 'var(--font-mono)', background: 'var(--color-accent, #D34E24)', color: '#FFF', padding: '2px 6px', borderRadius: 4 }}>
                  Proposed Primary
                </span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 16 }}>
                <HalbertMark size={110} lines={7} tone="accent" />
                <HalbertMark size={64} lines={7} tone="accent" />
                <HalbertMark size={32} lines={7} tone="accent" />
              </div>
              <p style={{ margin: 0, fontSize: 12, color: 'var(--color-ink-secondary, #5E5B56)', lineHeight: 1.4 }}>
                Balanced rhythm: 1 spine + 6 U-curves. Ample breathing room at 48px/32px while retaining full fingerprint intricacy at display sizes.
              </p>
            </div>

            {/* 8 Lines Focus */}
            <div style={{ background: 'var(--color-canvas, #F7F5F0)', padding: 20, borderRadius: 8, border: '1px solid var(--color-hairline, rgba(26,25,24,0.12))' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                <span style={{ fontWeight: 700, fontSize: 15, color: 'var(--color-ink, #1A1918)' }}>8 Lines (Candidate)</span>
                <span style={{ fontSize: 11, fontFamily: 'var(--font-mono)', background: 'var(--color-surface-subtle, #EFECE4)', color: 'var(--color-ink-secondary)', padding: '2px 6px', borderRadius: 4 }}>
                  N=7 Alternative
                </span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 16 }}>
                <HalbertMark size={110} lines={8} tone="accent" />
                <HalbertMark size={64} lines={8} tone="accent" />
                <HalbertMark size={32} lines={8} tone="accent" />
              </div>
              <p style={{ margin: 0, fontSize: 12, color: 'var(--color-ink-secondary, #5E5B56)', lineHeight: 1.4 }}>
                1 spine + 7 U-curves. Slightly denser than 7 lines; higher optical density for larger screens (≥96px).
              </p>
            </div>

            {/* 4 Lines Focus */}
            <div style={{ background: 'var(--color-canvas, #F7F5F0)', padding: 20, borderRadius: 8, border: '2px solid var(--color-accent, #D34E24)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                <span style={{ fontWeight: 700, fontSize: 15, color: 'var(--color-accent, #D34E24)' }}>4 Lines (Candidate)</span>
                <span style={{ fontSize: 11, fontFamily: 'var(--font-mono)', background: 'var(--color-accent, #D34E24)', color: '#FFF', padding: '2px 6px', borderRadius: 4 }}>
                  Proposed Micro
                </span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 16 }}>
                <HalbertMark size={64} lines={4} tone="accent" />
                <HalbertMark size={32} lines={4} tone="accent" />
                <HalbertMark size={24} lines={4} tone="accent" />
                <HalbertMark size={16} lines={4} tone="accent" />
              </div>
              <p style={{ margin: 0, fontSize: 12, color: 'var(--color-ink-secondary, #5E5B56)', lineHeight: 1.4 }}>
                1 spine + 3 U-curves. Retains the triple concentric nest down to 16px favicon without collapsing into 3 lines.
              </p>
            </div>
          </div>
        </div>

        {/* Section 2: Complete Line Count Matrix */}
        <div>
          <h3 style={{ margin: '0 0 8px 0', fontSize: 18, fontWeight: 700, color: 'var(--color-ink, #1A1918)' }}>
            Complete Line Progression (10 → 8 → 7 → 6 → 5 → 4 → 3)
          </h3>
          <p style={{ margin: '0 0 24px 0', fontSize: 13, color: 'var(--color-ink-secondary, #5E5B56)' }}>
            All variations rendered at identical scale tiers with mathematically calibrated pitch and stroke weight.
          </p>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 16 }}>
            {LINE_COUNTS.map(({ count, label, desc, candidate }) => (
              <div
                key={count}
                style={{
                  background: candidate ? 'var(--color-surface, #FFFFFF)' : 'var(--color-surface-subtle, #EFECE4)',
                  padding: 16,
                  borderRadius: 10,
                  border: candidate ? '2px solid var(--color-accent, #D34E24)' : '1px solid var(--color-hairline, rgba(26,25,24,0.08))',
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  gap: 16,
                }}
              >
                <div style={{ textAlign: 'center' }}>
                  <div style={{ fontWeight: 700, fontSize: 14, color: 'var(--color-ink, #1A1918)' }}>{label}</div>
                  <div style={{ fontSize: 10, color: 'var(--color-ink-tertiary, #8C877D)', fontFamily: 'var(--font-mono)' }}>{desc}</div>
                </div>

                {/* 120px */}
                <div style={{ display: 'flex', justifyContent: 'center' }}>
                  <HalbertMark size={110} lines={count} tone="accent" />
                </div>

                {/* 48px */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <HalbertMark size={48} lines={count} tone="accent" />
                  <HalbertMark size={48} lines={count} tone="ink" />
                </div>

                {/* 32px & 24px & 16px */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <HalbertMark size={32} lines={count} tone="accent" />
                  <HalbertMark size={24} lines={count} tone="accent" />
                  <HalbertMark size={16} lines={count} tone="accent" />
                </div>

                {/* Badge style at 36px */}
                <div style={{ marginTop: 4 }}>
                  <HalbertMark size={36} lines={count} tone="badge" />
                </div>
              </div>
            ))}
          </div>
        </div>

      </div>
    )
  },
}
