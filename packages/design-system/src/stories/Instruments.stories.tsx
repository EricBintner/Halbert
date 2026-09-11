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

const Container = ({ children, width = 780 }: { children: React.ReactNode; width?: number }) => (
  <div
    style={{
      maxWidth: width,
      width: '100%',
      display: 'flex',
      flexDirection: 'column',
      gap: 'var(--space-6)',
      padding: 'var(--space-6)',
      backgroundColor: 'var(--color-surface)',
      border: '1px solid var(--color-border)',
      borderRadius: 'var(--radius-lg)',
      boxShadow: 'var(--shadow-subtle)',
    }}
  >
    {children}
  </div>
)

/* ----------------------------------------------------------- TactileMeter -- */

export const TactileMeterStates: StoryObj = {
  name: 'TactileMeter / Operational Thresholds',
  render: () => (
    <Container>
      <div style={{ borderBottom: '1px solid var(--color-border)', paddingBottom: 'var(--space-3)' }}>
        <h4 style={{ margin: 0, fontSize: 16, fontWeight: 600, fontFamily: 'var(--font-sans)', color: 'var(--color-ink)' }}>
          Precision Telemetry Gauges
        </h4>
        <p style={{ margin: '4px 0 0', fontSize: 13, color: 'var(--color-ink-secondary)', lineHeight: 1.5 }}>
          Calibrated horizontal gauges with rigid baseline alignment, illuminated telemetry fills, tabular figures, and honest degraded states.
        </p>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-5)' }}>
        <TactileMeter
          label="System Drive"
          sub="/ · ext4 (nvme0n1p2)"
          value={34.2}
          tone="telemetry"
          valueLabel="34.2 GB / 100.0 GB (34.2%)"
        />

        <TactileMeter
          label="Backup Volume"
          sub="/mnt/backup · zfs"
          value={78.5}
          tone="telemetry"
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
      </div>
    </Container>
  ),
}

export const TactileMeterSizes: StoryObj = {
  name: 'TactileMeter / Size Scale',
  render: () => (
    <Container>
      <div style={{ borderBottom: '1px solid var(--color-border)', paddingBottom: 'var(--space-3)' }}>
        <h4 style={{ margin: 0, fontSize: 16, fontWeight: 600, fontFamily: 'var(--font-sans)', color: 'var(--color-ink)' }}>
          Instrument Track Scale
        </h4>
        <p style={{ margin: '4px 0 0', fontSize: 13, color: 'var(--color-ink-secondary)', lineHeight: 1.5 }}>
          Subtle 8px micro-tracks for compact card lists up to substantial 18px primary focal meters.
        </p>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-6)' }}>
        <div>
          <p style={{ fontSize: 12, fontFamily: 'var(--font-mono)', color: 'var(--color-ink-tertiary)', letterSpacing: '0.04em', marginBottom: 10 }}>
            SIZE: SM (8px track — compact lists & cards)
          </p>
          <TactileMeter size="sm" label="CPU Core Cluster" value={42.5} />
        </div>

        <div>
          <p style={{ fontSize: 12, fontFamily: 'var(--font-mono)', color: 'var(--color-ink-tertiary)', letterSpacing: '0.04em', marginBottom: 10 }}>
            SIZE: MD (12px track — standard instrument)
          </p>
          <TactileMeter size="md" label="RAM Allocated" value={65.0} valueLabel="10.4 GB / 16.0 GB (65%)" />
        </div>

        <div>
          <p style={{ fontSize: 12, fontFamily: 'var(--font-mono)', color: 'var(--color-ink-tertiary)', letterSpacing: '0.04em', marginBottom: 10 }}>
            SIZE: LG (18px track — primary focal gauge)
          </p>
          <TactileMeter size="lg" label="Main Pool Capacity" value={88.2} valueLabel="3.5 TB / 4.0 TB (88.2%)" />
        </div>
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
    <Container width={800}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
          <span style={{ fontFamily: 'var(--font-sans)', fontWeight: 600, fontSize: 15, color: 'var(--color-ink)' }}>
            Data Pool Allocation
          </span>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--color-ink-secondary)' }}>
            btrfs · 2 Disks (1.0 TB Total)
          </span>
        </div>

        <SegmentedBar
          segments={btrfsSegments}
          total={1000}
          unit="GB"
          showLegend
          showFreeHeadroom
          size="md"
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
    <Container width={840}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
          <span style={{ fontFamily: 'var(--font-sans)', fontWeight: 600, fontSize: 15, color: 'var(--color-ink)' }}>
            Tiered Home Array
          </span>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--color-ink-secondary)' }}>
            bcachefs · 2x NVMe + 4x HDD (4.0 TB)
          </span>
        </div>

        <SegmentedBar
          segments={bcachefsTierSegments}
          total={4000}
          unit="GB"
          showLegend
          showFreeHeadroom
          size="md"
        />
      </div>
    </Container>
  ),
}

/* ---------------------------------- Two-Tier Vignelli Layout Comparison -- */

export const TwoTierVignelliStorageCard: StoryObj = {
  name: 'Two-Tier Vignelli Storage Layout (Solution to Alignment Defect)',
  render: () => (
    <Container width={860}>
      <div style={{ borderBottom: '1px solid var(--color-border)', paddingBottom: 'var(--space-3)', marginBottom: 'var(--space-2)' }}>
        <h4 style={{ margin: 0, fontSize: 16, fontWeight: 600, fontFamily: 'var(--font-sans)', color: 'var(--color-ink)' }}>
          Two-Tier Vignelli Alignment Proof
        </h4>
        <p style={{ margin: '4px 0 0', fontSize: 13, color: 'var(--color-ink-secondary)', lineHeight: 1.5 }}>
          Regardless of the length of the mount point or label, the gauge track begins and ends at the exact same horizontal coordinate across every disk.
        </p>
      </div>

      {/* Item 1: Short name */}
      <div style={{ padding: 'var(--space-4) 0', borderBottom: '1px solid var(--color-border-subtle)' }}>
        <TactileMeter
          label="Root Volume"
          sub="/ · BTRFS"
          value={28.4}
          valueLabel="142 GB / 500 GB (28.4%) · 358 GB free"
          size="md"
        />
      </div>

      {/* Item 2: Very long pathological name */}
      <div style={{ padding: 'var(--space-4) 0', borderBottom: '1px solid var(--color-border-subtle)' }}>
        <TactileMeter
          label="Virtual Machine Disk Images & Backups"
          sub="/var/lib/libvirt/images/qemu/production-storage · EXT4"
          value={82.1}
          valueLabel="1.64 TB / 2.0 TB (82.1%) · 360 GB free"
          size="md"
        />
      </div>

      {/* Item 3: Multi-category segment */}
      <div style={{ padding: 'var(--space-4) 0' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 10 }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
            <span style={{ fontWeight: 600, fontSize: 15, color: 'var(--color-ink)' }}>Home Array</span>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--color-ink-tertiary)' }}>/home · BCACHEFS</span>
          </div>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--color-ink-secondary)', fontVariantNumeric: 'tabular-nums' }}>
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
          size="md"
        />
      </div>
    </Container>
  ),
}

/* --------------------------------- Categorical Data Visualization Palette -- */

const allSeriesSegments: SegmentItem[] = [
  { id: 's1', label: 'Cobalt / Blue', value: 28, tone: 'data-blue', detail: 'Series 1 · Primary Data' },
  { id: 's2', label: 'Marigold / Gold', value: 20, tone: 'data-amber', detail: 'Series 2 · Active Cache' },
  { id: 's3', label: 'Cyan / Teal', value: 18, tone: 'data-teal', detail: 'Series 3 · Secondary Pools' },
  { id: 's4', label: 'Amethyst / Purple', value: 14, tone: 'data-purple', pattern: 'hatched', detail: 'Series 4 · Metadata / Journal' },
  { id: 's5', label: 'Emerald / Green', value: 12, tone: 'data-green', detail: 'Series 5 · Snapshots' },
  { id: 's6', label: 'Coral / Orange', value: 8, tone: 'data-orange', detail: 'Series 6 · Focal Tier' },
]

export const CategoricalDataPaletteShowcase: StoryObj = {
  name: 'Palette / Categorical Data Series Showcase',
  render: () => (
    <Container width={880}>
      <div>
        <h4 style={{ margin: 0, fontSize: 16, fontWeight: 600, fontFamily: 'var(--font-sans)', color: 'var(--color-ink)' }}>
          High-Separation Categorical Data Palette
        </h4>
        <p style={{ margin: '4px 0 16px', fontSize: 13, color: 'var(--color-ink-secondary)', lineHeight: 1.5 }}>
          Six vivid, high-separation chromatic hues + slate neutral across the full 360° color spectrum. Zero muddy tones, zero brown, zero isoluminance collisions.
        </p>
      </div>

      <div style={{ padding: 'var(--space-4)', backgroundColor: 'var(--color-surface-subtle)', borderRadius: 'var(--radius-md)', border: '1px solid var(--color-border)' }}>
        <p style={{ margin: '0 0 10px', fontSize: 12, fontFamily: 'var(--font-mono)', color: 'var(--color-ink-tertiary)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
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

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(230px, 1fr))', gap: 'var(--space-3)', marginTop: 'var(--space-3)' }}>
        {[
          { token: '--color-data-blue', name: 'Cobalt / Blue', desc: 'Series 1 · Primary Payload & Main Storage', bg: 'var(--color-data-blue)' },
          { token: '--color-data-amber', name: 'Marigold / Gold', desc: 'Series 2 · Active Write Cache & Throughput', bg: 'var(--color-data-amber)' },
          { token: '--color-data-teal', name: 'Cyan / Teal', desc: 'Series 3 · Secondary Pools & Data Volumes', bg: 'var(--color-data-teal)' },
          { token: '--color-data-purple', name: 'Amethyst / Purple', desc: 'Series 4 · Metadata, Journals & Indexes', bg: 'var(--color-data-purple)' },
          { token: '--color-data-green', name: 'Emerald / Green', desc: 'Series 5 · Historical Snapshots & Backups', bg: 'var(--color-data-green)' },
          { token: '--color-data-orange', name: 'Coral / Orange', desc: 'Series 6 · Focal Tier & Ephemeral Buffers', bg: 'var(--color-data-orange)' },
          { token: '--color-data-neutral', name: 'Slate / Graphite', desc: 'Base · Reserved Capacity & System Overhead', bg: 'var(--color-data-neutral)' },
        ].map((item) => (
          <div
            key={item.token}
            style={{
              padding: '12px 14px',
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--color-border)',
              backgroundColor: 'var(--color-surface)',
              display: 'flex',
              alignItems: 'center',
              gap: 12,
            }}
          >
            <div style={{ width: 28, height: 28, borderRadius: 'var(--radius-sm)', backgroundColor: item.bg, flexShrink: 0, border: '1px solid rgba(0,0,0,0.1)' }} />
            <div style={{ minWidth: 0 }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--color-ink)' }}>{item.name}</div>
              <div style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--color-ink-tertiary)' }}>{item.token}</div>
              <div style={{ fontSize: 12, color: 'var(--color-ink-secondary)', marginTop: 2, lineHeight: 1.35 }}>{item.desc}</div>
            </div>
          </div>
        ))}
      </div>
    </Container>
  ),
}
