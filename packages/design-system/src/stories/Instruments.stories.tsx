// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import * as React from 'react'
import type { Meta, StoryObj } from '@storybook/react'

import { TactileMeter } from '../primitives/TactileMeter'
import { SegmentedBar, type SegmentItem } from '../primitives/SegmentedBar'

const meta: Meta = {
  title: 'Instruments/Meters',
  parameters: {
    docs: {
      description: {
        component:
          'Precision data visualization meters designed for telemetry, filesystem capacity, and hardware headroom. Follows the Braun / Olivetti instrument language with fixed-baseline alignment and honest degraded states.',
      },
    },
  },
}

export default meta

const Container = ({ children, width = 540 }: { children: React.ReactNode; width?: number }) => (
  <div
    style={{
      maxWidth: width,
      width: '100%',
      display: 'flex',
      flexDirection: 'column',
      gap: 'var(--space-4)',
      padding: 'var(--space-4)',
      backgroundColor: 'var(--color-surface)',
      border: '1px solid var(--color-border)',
      borderRadius: 'var(--radius-md)',
    }}
  >
    {children}
  </div>
)

/* ----------------------------------------------------------- TactileMeter -- */

export const TactileMeterStates: StoryObj = {
  name: 'TactileMeter / Operational Thresholds (Calm Graphite Default)',
  render: () => (
    <Container>
      <TactileMeter
        label="System Drive"
        sub="/ · ext4 (nvme0n1p2)"
        value={34.2}
        valueLabel="34.2 GB / 100.0 GB (34.2%) · Calm ink"
      />

      <TactileMeter
        label="Backup Volume (High Normal Load)"
        sub="/mnt/backup · zfs"
        value={78.5}
        valueLabel="785 GB / 1.0 TB (78.5%) · 215 GB free"
      />

      <TactileMeter
        label="Exhausted Root Volume (Hardware / Capacity Fault)"
        sub="/ · btrfs (nvme0n1p3)"
        value={95.8}
        tone="critical"
        valueLabel="958 GB / 1.0 TB (95.8%) · CRITICAL ALARM"
      />

      <TactileMeter
        label="Detached Volume Sensor"
        sub="/mnt/external · unmounted"
        value={0}
        offline
      />
    </Container>
  ),
}

export const TactileMeterSizes: StoryObj = {
  name: 'TactileMeter / Size Scale',
  render: () => (
    <Container>
      <div>
        <p style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--color-ink-tertiary)', marginBottom: 6 }}>SIZE: SM (6px track — compact lists & cards)</p>
        <TactileMeter size="sm" label="CPU Core Cluster" value={42.5} />
      </div>

      <div>
        <p style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--color-ink-tertiary)', marginBottom: 6 }}>SIZE: MD (10px track — standard instrument)</p>
        <TactileMeter size="md" label="RAM Allocated" value={65.0} valueLabel="10.4 GB / 16.0 GB (65%)" />
      </div>

      <div>
        <p style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--color-ink-tertiary)', marginBottom: 6 }}>SIZE: LG (16px track — primary focal gauge)</p>
        <TactileMeter size="lg" label="Main Pool Capacity" value={88.2} valueLabel="3.5 TB / 4.0 TB (88.2%)" />
      </div>
    </Container>
  ),
}

/* ----------------------------------------------------------- SegmentedBar -- */

const btrfsSegments: SegmentItem[] = [
  { id: 'data', label: 'File Data', value: 580, tone: 'data-blue', detail: 'RAID1' },
  { id: 'meta', label: 'Metadata & Journal', value: 48, tone: 'data-purple', pattern: 'hatched', detail: 'DUP' },
  { id: 'snap', label: 'CoW Snapshots', value: 112, tone: 'data-teal' },
]

export const SegmentedBarStorageBtrfs: StoryObj = {
  name: 'SegmentedBar / Btrfs Pool Allocation (Cool Non-Alarm Palette)',
  render: () => (
    <Container>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
          <span style={{ fontFamily: 'var(--font-sans)', fontWeight: 600, fontSize: 13, color: 'var(--color-ink)' }}>
            Data Pool Allocation
          </span>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--color-ink-secondary)' }}>
            btrfs · 2 Disks (1.0 TB Total)
          </span>
        </div>

        <SegmentedBar
          segments={btrfsSegments}
          total={1000}
          unit="GB"
          showLegend
          showFreeHeadroom
        />
      </div>
    </Container>
  ),
}

const bcachefsTierSegments: SegmentItem[] = [
  { id: 'fg', label: 'Foreground NVMe Cache', value: 420, tone: 'data-orange', detail: 'active write buffer' },
  { id: 'data', label: 'Rotational HDD Data', value: 2600, tone: 'data-blue', detail: 'bulk storage' },
  { id: 'meta', label: 'Replicated Metadata', value: 90, tone: 'data-purple', pattern: 'hatched' },
  { id: 'snap', label: 'Historical Snapshots', value: 340, tone: 'data-teal' },
]

export const SegmentedBarTieredStorage: StoryObj = {
  name: 'SegmentedBar / Tiered Cache (Bcachefs)',
  render: () => (
    <Container width={620}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
          <span style={{ fontFamily: 'var(--font-sans)', fontWeight: 600, fontSize: 13, color: 'var(--color-ink)' }}>
            Tiered Home Array
          </span>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--color-ink-secondary)' }}>
            bcachefs · 2x NVMe + 4x HDD (4.0 TB)
          </span>
        </div>

        <SegmentedBar
          segments={bcachefsTierSegments}
          total={4000}
          unit="GB"
          showLegend
          showFreeHeadroom
        />
      </div>
    </Container>
  ),
}

/* ---------------------------------- Two-Tier Vignelli Layout Comparison -- */

export const TwoTierVignelliStorageCard: StoryObj = {
  name: 'Two-Tier Vignelli Storage Layout (Solution to Alignment Defect)',
  render: () => (
    <Container width={680}>
      <div style={{ borderBottom: '1px solid var(--color-border)', paddingBottom: 'var(--space-3)', marginBottom: 'var(--space-2)' }}>
        <h4 style={{ margin: 0, fontSize: 14, fontFamily: 'var(--font-sans)', color: 'var(--color-ink)' }}>
          Two-Tier Vignelli Alignment Proof
        </h4>
        <p style={{ margin: '4px 0 0', fontSize: 12, color: 'var(--color-ink-secondary)' }}>
          Regardless of the length of the mount point or label, the gauge track begins and ends at the exact same horizontal coordinate across every disk.
        </p>
      </div>

      {/* Item 1: Short name */}
      <div style={{ padding: 'var(--space-2) 0', borderBottom: '1px solid var(--color-border-subtle)' }}>
        <TactileMeter
          label="Root Volume"
          sub="/ · BTRFS"
          value={28.4}
          valueLabel="142 GB / 500 GB (28.4%) · 358 GB free"
        />
      </div>

      {/* Item 2: Very long pathological name */}
      <div style={{ padding: 'var(--space-2) 0', borderBottom: '1px solid var(--color-border-subtle)' }}>
        <TactileMeter
          label="Virtual Machine Disk Images & Backups"
          sub="/var/lib/libvirt/images/qemu/production-storage · EXT4"
          value={82.1}
          valueLabel="1.64 TB / 2.0 TB (82.1%) · 360 GB free"
        />
      </div>

      {/* Item 3: Multi-category segment */}
      <div style={{ padding: 'var(--space-2) 0' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 6 }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
            <span style={{ fontWeight: 600, fontSize: 13, color: 'var(--color-ink)' }}>Home Array</span>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--color-ink-tertiary)' }}>/home · BCACHEFS</span>
          </div>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--color-ink-secondary)' }}>
            46.2% Allocated
          </span>
        </div>
        <SegmentedBar
          segments={[
            { id: 'user', label: 'User Data', value: 1800, tone: 'data-blue' },
            { id: 'cache', label: 'Foreground Cache', value: 420, tone: 'data-orange' },
            { id: 'meta', label: 'Metadata', value: 80, tone: 'data-purple', pattern: 'hatched' },
          ]}
          total={5000}
          unit="GB"
        />
      </div>
    </Container>
  ),
}

/* --------------------------------- Categorical Data Visualization Palette -- */

const allSeriesSegments: SegmentItem[] = [
  { id: 's1', label: 'Cobalt / Blue', value: 38, tone: 'data-blue', detail: 'Series 1 · Primary Data' },
  { id: 's2', label: 'Oceanic / Teal', value: 24, tone: 'data-teal', detail: 'Series 2 · Secondary / Snapshots' },
  { id: 's3', label: 'Amethyst / Purple', value: 16, tone: 'data-purple', pattern: 'hatched', detail: 'Series 3 · Metadata / Journal' },
  { id: 's4', label: 'Vermilion / Orange', value: 12, tone: 'data-orange', detail: 'Series 4 · Active Cache / Focal' },
  { id: 's5', label: 'Graphite / Neutral', value: 10, tone: 'data-neutral', detail: 'Base · Reserved / Overhead' },
]

export const CategoricalDataPaletteShowcase: StoryObj = {
  name: 'Palette / Categorical Data Series Showcase',
  render: () => (
    <Container width={720}>
      <div>
        <h4 style={{ margin: 0, fontSize: 14, fontFamily: 'var(--font-sans)', color: 'var(--color-ink)' }}>
          Disciplined Categorical Data Palette
        </h4>
        <p style={{ margin: '4px 0 12px', fontSize: 12, color: 'var(--color-ink-secondary)' }}>
          Research-grounded 4-tone cool qualitative palette + neutral graphite, following Tufte and Brewer principles. Eliminates muddy hues, pseudo-semantic traffic lights, and isoluminance collisions.
        </p>
      </div>

      <div style={{ padding: 'var(--space-3)', backgroundColor: 'var(--color-surface-subtle)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--color-border)' }}>
        <p style={{ margin: '0 0 8px', fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--color-ink-tertiary)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
          MULTI-SERIES ALLOCATION METER
        </p>
        <SegmentedBar
          segments={allSeriesSegments}
          total={100}
          unit="%"
          showLegend
          showFreeHeadroom={false}
          size="md"
        />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 'var(--space-2)', marginTop: 'var(--space-2)' }}>
        {[
          { token: '--color-data-blue', name: 'Cobalt / Blue', desc: 'Series 1 · Primary Payload & Filesystem Data', bg: 'var(--color-data-blue)' },
          { token: '--color-data-teal', name: 'Oceanic / Teal', desc: 'Series 2 · Secondary Pools & Snapshots', bg: 'var(--color-data-teal)' },
          { token: '--color-data-purple', name: 'Amethyst / Purple', desc: 'Series 3 · Metadata, Journals & Indexes', bg: 'var(--color-data-purple)' },
          { token: '--color-data-orange', name: 'Vermilion / Orange', desc: 'Series 4 · Active NVMe Cache & Focal Tier', bg: 'var(--color-data-orange)' },
          { token: '--color-data-neutral', name: 'Graphite / Neutral', desc: 'Base · Reserved Capacity & System Overhead', bg: 'var(--color-data-neutral)' },
        ].map((item) => (
          <div
            key={item.token}
            style={{
              padding: '8px 10px',
              borderRadius: 'var(--radius-sm)',
              border: '1px solid var(--color-border)',
              backgroundColor: 'var(--color-surface)',
              display: 'flex',
              alignItems: 'center',
              gap: 10,
            }}
          >
            <div style={{ width: 24, height: 24, borderRadius: 'var(--radius-sm)', backgroundColor: item.bg, flexShrink: 0, border: '1px solid rgba(0,0,0,0.1)' }} />
            <div style={{ minWidth: 0 }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--color-ink)' }}>{item.name}</div>
              <div style={{ fontSize: 10, fontFamily: 'var(--font-mono)', color: 'var(--color-ink-tertiary)' }}>{item.token}</div>
              <div style={{ fontSize: 11, color: 'var(--color-ink-secondary)', marginTop: 2 }}>{item.desc}</div>
            </div>
          </div>
        ))}
      </div>
    </Container>
  ),
}
