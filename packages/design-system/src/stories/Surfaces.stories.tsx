// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import * as React from 'react'
import type { Meta, StoryObj } from '@storybook/react'

import { AppWindow } from '../surfaces/AppWindow'
import { MetricCard } from '../surfaces/MetricCard'

const meta: Meta<typeof AppWindow> = {
  title: 'Surfaces/AppWindow',
  component: AppWindow,
}
export default meta

const Note = ({ children }: { children: React.ReactNode }) => (
  <p style={{ color: 'var(--color-ink-secondary)', fontSize: 13, maxWidth: '68ch', marginTop: 0 }}>{children}</p>
)

export const Plate: StoryObj<typeof AppWindow> = {
  args: {
    title: 'Proactive Events',
    meta: '2 active',
    live: true,
    children: 'Plate body',
    footer: 'last swept 03:02',
  },
  render: (args) => (
    <div style={{ maxWidth: 460 }}>
      <AppWindow {...args} />
    </div>
  ),
}

export const Collapsible: StoryObj = {
  render: () => (
    <div style={{ maxWidth: 460, display: 'grid', gap: 'var(--space-4)' }}>
      <Note>
        Rendered as a <code>&lt;section&gt;</code> with <code>aria-labelledby</code>, so a
        screen-reader user can navigate a dashboard by its plates. The toggle reports{' '}
        <code>aria-expanded</code> and owns <code>aria-controls</code>.
      </Note>
      <AppWindow title="System Vitals" meta="updates every 5s" collapsible live>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 'var(--space-2)' }}>
          <MetricCard label="CPU temp" value="45°C" sub="Nominal · fans idle" tone="nominal" bar={38} />
          <MetricCard label="Load avg" value="0.15" sub="0.22 · 0.18 over 5 / 15 min" bar={9} />
        </div>
      </AppWindow>
      <AppWindow title="Storage" meta="collapsed by default" collapsible defaultCollapsed>
        <MetricCard label="Pool" value="4.1 TB" sub="of 8.0 TB" bar={51} />
      </AppWindow>
    </div>
  ),
}

export const Metrics: StoryObj = {
  name: 'MetricCard/States',
  render: () => (
    <>
      <Note>
        The gauge is exposed as a <code>role=&quot;meter&quot;</code> labelled by the metric, and
        out-of-range readings are clamped rather than overflowing. An unreadable sensor renders{' '}
        <code>[Sensor offline]</code> — never a plausible-looking zero, per the Computational Honesty
        Gate.
      </Note>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: 'var(--space-3)' }}>
        <MetricCard label="CPU temp" value="45°C" sub="Nominal · fans idle" tone="nominal" bar={38} />
        <MetricCard label="Memory" value="18.2 GB" sub="of 64.0 GB" bar={28} />
        <MetricCard label="Root volume" value="91%" sub="4.2 GB free — tightening" tone="warning" bar={91} />
        <MetricCard label="/dev/sda1" value="3 pending" sub="Reallocated: 0" tone="critical" bar={100} />
        <MetricCard label="Fan speed" value="0 RPM" offline />
        <MetricCard label="Uptime" value="42 days" sub="14 hours" />
      </div>
    </>
  ),
}
