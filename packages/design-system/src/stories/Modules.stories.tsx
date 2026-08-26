// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import * as React from 'react'
import type { Meta, StoryObj } from '@storybook/react'

import { AppWindow } from '../surfaces/AppWindow'
import { MetricCard } from '../surfaces/MetricCard'
import { StatusBadge } from '../primitives/StatusBadge'
import { Button } from '../primitives/Button'

const meta: Meta = {
  title: 'Modules/Vitals',
  parameters: { layout: 'padded' },
}
export default meta

/**
 * A live vitals plate on a 1s tick. Values wander within plausible bounds so the
 * tabular-figure rule is visible in motion: the numbers change without the
 * layout reflowing.
 */
function useTick(seed: number, spread: number, period = 1000) {
  const [value, setValue] = React.useState(seed)
  React.useEffect(() => {
    const id = setInterval(() => {
      setValue((v) => {
        const next = v + (Math.random() - 0.5) * spread
        return Math.max(seed - spread * 2, Math.min(seed + spread * 2, next))
      })
    }, period)
    return () => clearInterval(id)
  }, [seed, spread, period])
  return value
}

export const VitalsModule: StoryObj = {
  name: 'Live vitals (1s tick)',
  render: () => {
    const temp = useTick(45, 3)
    const load = useTick(0.15, 0.08)
    const mem = useTick(18.2, 0.6)

    const tempTone = temp > 70 ? 'critical' : temp > 58 ? 'warning' : 'nominal'

    return (
      <div style={{ maxWidth: 620 }}>
        <AppWindow
          title="System Vitals"
          meta="updates every 1s"
          live
          footer="all readings from hwmon · nothing simulated in production"
        >
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))', gap: 'var(--space-2)' }}>
            <MetricCard
              label="CPU temp"
              value={`${temp.toFixed(1)}°C`}
              sub={tempTone === 'nominal' ? 'Nominal · fans idle' : 'Climbing'}
              tone={tempTone}
              bar={(temp / 100) * 100}
            />
            <MetricCard label="Load avg" value={load.toFixed(2)} sub="1 min" bar={load * 100} />
            <MetricCard label="Memory" value={`${mem.toFixed(1)} GB`} sub="of 64.0 GB" bar={(mem / 64) * 100} />
            <MetricCard label="Fan speed" value="—" offline />
          </div>
        </AppWindow>
      </div>
    )
  },
}

export const ProactiveEvent: StoryObj = {
  name: 'Proactive event card',
  render: () => (
    <div style={{ maxWidth: 520 }}>
      <AppWindow title="Proactive Events" meta="1 active" live>
        <div style={{ display: 'grid', gap: 'var(--space-3)' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 'var(--space-3)' }}>
            <strong style={{ fontSize: 13 }}>/dev/sda1 logged 3 read errors this morning</strong>
            <StatusBadge tone="warning">Attention</StatusBadge>
          </div>

          <p style={{ margin: 0, fontSize: 12, color: 'var(--color-ink-secondary)', lineHeight: 1.5 }}>
            Pending sectors: 3. Reallocated: 0. I&rsquo;d schedule an extended SMART self-test before
            this becomes a restore.
          </p>

          {/* The Four Whys, which any unprompted statement must be able to answer. */}
          <dl
            style={{
              margin: 0,
              display: 'grid',
              gridTemplateColumns: 'auto 1fr',
              gap: '2px var(--space-3)',
              fontFamily: 'var(--font-mono)',
              fontSize: 10,
            }}
          >
            {[
              ['Why now', '3 errors between 07:58 and 08:04'],
              ['Why care', 'pending sectors precede reallocation'],
              ['Why so', 'smartctl -A /dev/sda1'],
              ['Why trust', 'journald 2026-08-26 07:58 → 08:04'],
            ].map(([term, detail]) => (
              <React.Fragment key={term}>
                <dt style={{ color: 'var(--color-status-telemetry)', textTransform: 'uppercase', letterSpacing: 'var(--tracking-label)' }}>
                  {term}
                </dt>
                <dd style={{ margin: 0, color: 'var(--color-ink-tertiary)' }}>{detail}</dd>
              </React.Fragment>
            ))}
          </dl>

          <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
            <Button variant="primary" size="sm">Run extended test</Button>
            <Button variant="outline" size="sm">Snooze 7d</Button>
            <Button variant="ghost" size="sm">Dismiss</Button>
          </div>
        </div>
      </AppWindow>
    </div>
  ),
}
