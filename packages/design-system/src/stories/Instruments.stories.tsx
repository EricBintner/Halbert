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
  name: 'TactileMeter / Operational Thresholds',
  render: () => (
    <Container>
      <TactileMeter
        label="System Drive"
        sub="/ · ext4 (nvme0n1p2)"
        value={34.2}
        valueLabel="34.2 GB / 100.0 GB (34.2%)"
      />

      <TactileMeter
        label="Backup Volume"
        sub="/mnt/backup · zfs"
        value={78.5}
        valueLabel="785 GB / 1.0 TB (78.5%)"
      />

      <TactileMeter
        label="Root Filesystem (Critical Threshold)"
        sub="/ · btrfs (nvme0n1p3)"
        value={94.8}
        valueLabel="948 GB / 1.0 TB (94.8%)"
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
  { id: 'data', label: 'File Data', value: 480, tone: 'data-blue', detail: 'RAID1' },
  { id: 'meta', label: 'Metadata & Journal', value: 36, tone: 'data-purple', pattern: 'hatched', detail: 'DUP' },
  { id: 'snap', label: 'CoW Snapshots', value: 96, tone: 'data-teal' },
  { id: 'sys',  label: 'System Reserve', value: 28, tone: 'data-amber' },
]

export const SegmentedBarStorageBtrfs: StoryObj = {
  name: 'SegmentedBar / Btrfs Pool Allocation (Categorical Palette)',
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
  { id: 'fg', label: 'Foreground NVMe Cache', value: 320, tone: 'data-amber', detail: 'fast write tier' },
  { id: 'data', label: 'Rotational HDD Data', value: 2400, tone: 'data-blue', detail: 'cold tier' },
  { id: 'meta', label: 'Replicated Metadata', value: 80, tone: 'data-purple', pattern: 'hatched' },
  { id: 'snap', label: 'Historical Snapshots', value: 300, tone: 'data-teal' },
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
            { id: 'cache', label: 'Foreground Cache', value: 420, tone: 'data-amber' },
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
  { id: 's1', label: 'Cobalt / Blue', value: 24, tone: 'data-blue', detail: 'Series 1' },
  { id: 's2', label: 'Teal / Copper', value: 20, tone: 'data-teal', detail: 'Series 2' },
  { id: 's3', label: 'Emerald / Green', value: 18, tone: 'data-green', detail: 'Series 3' },
  { id: 's4', label: 'Amber / Marigold', value: 15, tone: 'data-amber', detail: 'Series 4' },
  { id: 's5', label: 'Iris / Amethyst', value: 13, tone: 'data-purple', detail: 'Series 5' },
  { id: 's6', label: 'Vermilion / Focal', value: 10, tone: 'data-orange', detail: 'Series 6' },
]

export const CategoricalDataPaletteShowcase: StoryObj = {
  name: 'Palette / Categorical Data Series Showcase',
  render: () => (
    <Container width={720}>
      <div>
        <h4 style={{ margin: 0, fontSize: 14, fontFamily: 'var(--font-sans)', color: 'var(--color-ink)' }}>
          Olivetti / Vignelli Categorical Data Palette
        </h4>
        <p style={{ margin: '4px 0 12px', fontSize: 12, color: 'var(--color-ink-secondary)' }}>
          Six distinct chromatic series with wide hue separation and stepped luminance. Designed for multi-category disk topologies, memory allocations, and cluster metrics without muddiness or isoluminance clash.
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
          { token: '--color-data-blue', name: 'Cobalt / Blue', desc: 'Primary data series · Vignelli Subway Blue', bg: 'var(--color-data-blue)' },
          { token: '--color-data-teal', name: 'Copper / Teal', desc: 'Secondary series · Oceanic Copper-Oxide', bg: 'var(--color-data-teal)' },
          { token: '--color-data-green', name: 'Emerald / Green', desc: 'Tertiary series · Crisp Botanical Leaf', bg: 'var(--color-data-green)' },
          { token: '--color-data-amber', name: 'Amber / Marigold', desc: 'Quaternary series · Warm Goldenrod', bg: 'var(--color-data-amber)' },
          { token: '--color-data-purple', name: 'Iris / Amethyst', desc: 'Quinary series · Mid-Century Violet', bg: 'var(--color-data-purple)' },
          { token: '--color-data-orange', name: 'Vermilion / Focal', desc: 'Focal series · Signature Olivetti Orange', bg: 'var(--color-data-orange)' },
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
            </div>
          </div>
        ))}
      </div>
    </Container>
  ),
}
