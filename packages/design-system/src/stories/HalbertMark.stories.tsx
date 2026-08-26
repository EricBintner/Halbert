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
    tone: 'accent',
  },
  argTypes: {
    density: {
      control: 'select',
      options: ['auto', 'display', 'medium', 'compact', 'small'],
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
  render: () => (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 32 }}>
      <div>
        <h4 style={{ margin: '0 0 8px 0', fontFamily: 'var(--font-mono)', fontSize: 13, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--color-ink-secondary)' }}>
          Tier 1: Display (100% detail · 10 concentric paths · for &gt;= 96px)
        </h4>
        <div style={{ display: 'flex', alignItems: 'center', gap: 24 }}>
          <HalbertMark size={140} density="display" tone="accent" />
          <HalbertMark size={140} density="display" tone="ink" />
          <HalbertMark size={140} density="display" tone="badge" />
        </div>
      </div>

      <div>
        <h4 style={{ margin: '0 0 8px 0', fontFamily: 'var(--font-mono)', fontSize: 13, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--color-ink-secondary)' }}>
          Tier 2: Medium (60% detail · 6 concentric paths · for 32px - 96px)
        </h4>
        <div style={{ display: 'flex', alignItems: 'center', gap: 24 }}>
          <HalbertMark size={64} density="medium" tone="accent" />
          <HalbertMark size={48} density="medium" tone="accent" />
          <HalbertMark size={32} density="medium" tone="accent" />
          <HalbertMark size={48} density="medium" tone="ink" />
          <HalbertMark size={48} density="medium" tone="badge" />
        </div>
      </div>

      <div>
        <h4 style={{ margin: '0 0 8px 0', fontFamily: 'var(--font-mono)', fontSize: 13, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--color-ink-secondary)' }}>
          Tier 3: Small / Micro (30% detail · 3 concentric paths · for 16px - 24px favicon)
        </h4>
        <div style={{ display: 'flex', alignItems: 'center', gap: 24 }}>
          <HalbertMark size={24} density="small" tone="accent" />
          <HalbertMark size={16} density="small" tone="accent" />
          <HalbertMark size={24} density="small" tone="ink" />
          <HalbertMark size={24} density="small" tone="badge" />
          <HalbertMark size={16} density="small" tone="badge" />
        </div>
      </div>
    </div>
  ),
}
