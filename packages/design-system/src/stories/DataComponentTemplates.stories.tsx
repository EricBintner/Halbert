// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import * as React from 'react'
import type { Meta, StoryObj } from '@storybook/react'

import { TactileMeter } from '../primitives/TactileMeter'
import { SegmentedBar, type SegmentItem } from '../primitives/SegmentedBar'
import { DataGridRow } from '../primitives/DataGridRow'

const meta: Meta = {
  title: 'Instruments/Templates',
  parameters: {
    docs: {
      description: {
        component:
          'Skeletal data visualization component templates enforcing strict Vignelli Unigrid columnar alignment. All data paths start at the exact same horizontal coordinate, and right-hand tabular metrics line up to the pixel without pills.',
      },
    },
  },
}

export default meta

/** Clean industrial status pip (no pills) */
const StatusIndicator = ({
  tone,
  label,
}: {
  tone: 'nominal' | 'warning' | 'critical' | 'telemetry'
  label: string
}) => {
  const color =
    tone === 'critical'
      ? 'var(--color-status-critical)'
      : tone === 'warning'
        ? 'var(--color-data-amber)'
        : tone === 'telemetry'
          ? 'var(--color-data-blue)'
          : 'var(--color-data-green)'
  return (
    <div style={{ display: 'inline-flex', alignItems: 'center', gap: 7 }}>
      <span
        style={{
          width: 6,
          height: 6,
          borderRadius: '50%',
          backgroundColor: color,
          flexShrink: 0,
        }}
      />
      <span
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 11,
          fontWeight: 600,
          color,
          letterSpacing: '0.06em',
          textTransform: 'uppercase',
        }}
      >
        {label}
      </span>
    </div>
  )
}

/** Clean tabular percentage or status readout (no pills) */
const MetricStatus = ({
  value,
  tone = 'nominal',
}: {
  value: string
  tone?: 'nominal' | 'warning' | 'critical' | 'telemetry'
}) => {
  const color =
    tone === 'critical'
      ? 'var(--color-status-critical)'
      : tone === 'warning'
        ? 'var(--color-data-amber)'
        : 'var(--color-ink)'
  return (
    <span
      style={{
        fontFamily: 'var(--font-mono)',
        fontSize: 13,
        fontWeight: tone === 'critical' ? 700 : 600,
        color,
        fontVariantNumeric: 'tabular-nums',
        letterSpacing: '-0.01em',
        textAlign: 'right',
      }}
    >
      {value}
    </span>
  )
}

const CardContainer = ({
  children,
  title,
  subtitle,
  status,
  width = 880,
}: {
  children: React.ReactNode
  title: string
  subtitle?: string
  status?: React.ReactNode
  width?: number
}) => (
  <div
    style={{
      maxWidth: width,
      width: '100%',
      display: 'flex',
      flexDirection: 'column',
      backgroundColor: 'var(--color-surface)',
      border: '1px solid var(--color-border)',
      borderRadius: 'var(--radius-lg)',
      boxShadow: 'var(--shadow-subtle)',
      overflow: 'hidden',
    }}
  >
    {/* Card Header Plate */}
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: 'var(--space-4) var(--space-6)',
        borderBottom: '1px solid var(--color-border)',
        backgroundColor: 'var(--color-surface-subtle)',
      }}
    >
      <div style={{ minWidth: 0 }}>
        <h3
          style={{
            margin: 0,
            fontSize: 16,
            fontWeight: 600,
            fontFamily: 'var(--font-sans)',
            color: 'var(--color-ink)',
            letterSpacing: '-0.01em',
          }}
        >
          {title}
        </h3>
        {subtitle && (
          <p
            style={{
              margin: '3px 0 0',
              fontSize: 12,
              fontFamily: 'var(--font-mono)',
              color: 'var(--color-ink-tertiary)',
            }}
          >
            {subtitle}
          </p>
        )}
      </div>
      {status && <div style={{ flexShrink: 0 }}>{status}</div>}
    </div>

    {/* Card Body Tray */}
    <div
      style={{
        padding: 'var(--space-5) var(--space-6)',
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--space-4)',
      }}
    >
      {children}
    </div>
  </div>
)

/* ------------------------------------------------ 1. Storage Pool Template -- */

const poolSegments: SegmentItem[] = [
  { id: 'usr', label: 'User Data', value: 2400, tone: 'data-blue', detail: 'RAID1' },
  { id: 'meta', label: 'Metadata & Journal', value: 120, tone: 'data-purple', pattern: 'hatched', detail: 'DUP' },
  { id: 'snap', label: 'Btrfs Snapshots', value: 480, tone: 'data-teal', detail: 'ro subvol' },
]

export const StoragePoolTemplate: StoryObj = {
  name: 'Template / Storage Pool & Filesystems',
  render: () => (
    <CardContainer
      title="Primary Storage Pool (Fast NVMe Array)"
      subtitle="btrfs · 2 Disks (4.0 TB Total Raw) · UUID: 8f4a-9b12-cc4e"
      status={<StatusIndicator tone="nominal" label="HEALTHY" />}
    >
      {/* Visual Alignment Guide Note */}
      <div
        style={{
          padding: '8px 12px',
          backgroundColor: 'var(--color-surface-sunken)',
          borderRadius: 'var(--radius-sm)',
          border: '1px solid var(--color-border)',
          fontSize: 12,
          color: 'var(--color-ink-secondary)',
          display: 'flex',
          justifyContent: 'space-between',
        }}
      >
        <span>
          <strong>Vignelli Alignment Proof:</strong> Mount paths align horizontally on the left; tabular metrics and percentages align on the right without pills or duplicate headers.
        </span>
        <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--color-ink-tertiary)' }}>
          Grid: 220px | 180px | 1fr | 180px | 72px
        </span>
      </div>

      {/* Row 1: Short name */}
      <DataGridRow
        title="Root Volume"
        path="/ · btrfs"
        detail="Subvolume ID 256 · Compress=zstd:1"
        metrics="142.0 GB / 500.0 GB"
        status={<MetricStatus value="28.4%" tone="nominal" />}
        meter={<TactileMeter value={28.4} tone="telemetry" size="md" />}
        titleWidth={220}
        pathWidth={180}
        metricsWidth={180}
        statusWidth={72}
      />

      {/* Row 2: Pathological very long volume label */}
      <DataGridRow
        title="Virtual Machine Disk Images & Golden Masters"
        path="/var/lib/libvirt/images"
        detail="NoCoW · Raw Sparse Images"
        metrics="820.0 GB / 1000.0 GB"
        status={<MetricStatus value="82.0%" tone="warning" />}
        meter={<TactileMeter value={82.0} tone="warning" size="md" />}
        titleWidth={220}
        pathWidth={180}
        metricsWidth={180}
        statusWidth={72}
      />

      {/* Row 3: Critical alarm volume (Proves alarm status does NOT push layout) */}
      <DataGridRow
        title="Database WAL Log Volume"
        path="/data/postgres/wal"
        detail="Direct I/O · Exhausted Storage Margin"
        metrics="958.0 GB / 1000.0 GB"
        status={<MetricStatus value="95.8% CRIT" tone="critical" />}
        meter={<TactileMeter value={95.8} tone="critical" size="md" />}
        titleWidth={220}
        pathWidth={180}
        metricsWidth={180}
        statusWidth={72}
      />

      {/* Row 4: Normal container mount */}
      <DataGridRow
        title="Container Overlay Space"
        path="/var/lib/docker/overlay2"
        detail="OverlayFS · 42 Active Containers"
        metrics="380.0 GB / 1000.0 GB"
        status={<MetricStatus value="38.0%" tone="nominal" />}
        meter={<TactileMeter value={38.0} tone="telemetry" size="md" />}
        titleWidth={220}
        pathWidth={180}
        metricsWidth={180}
        statusWidth={72}
      />

      {/* Pool Allocation Tray */}
      <div
        style={{
          marginTop: 'var(--space-2)',
          paddingTop: 'var(--space-4)',
          borderTop: '1px solid var(--color-border)',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 8 }}>
          <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--color-ink)' }}>
            Physical Pool Redundancy Breakdown
          </span>
          <span style={{ fontSize: 12, fontFamily: 'var(--font-mono)', color: 'var(--color-ink-secondary)' }}>
            3.0 TB Allocated / 1.0 TB Free Headroom
          </span>
        </div>
        <SegmentedBar
          segments={poolSegments}
          total={4000}
          unit="GB"
          showLegend
          showFreeHeadroom
          size="md"
        />
      </div>
    </CardContainer>
  ),
}

/* ------------------------------------------- 2. Host Compute Vitals Template -- */

export const HostComputeVitalsTemplate: StoryObj = {
  name: 'Template / Host Compute & Telemetry',
  render: () => (
    <CardContainer
      title="Host Telemetry & Hardware Vitals"
      subtitle="halbert-workstation · AMD Ryzen 9 7950X (16C/32T) · Linux 6.12.8-cachyos"
      status={<StatusIndicator tone="nominal" label="ONLINE" />}
    >
      <DataGridRow
        title="CPU Core Cluster Load"
        path="cpu · 16 Cores / 32 Threads"
        detail="Governer: schedutil · Boost: 5.4 GHz"
        metrics="42.5% Avg Load"
        status={<MetricStatus value="42.5%" tone="nominal" />}
        meter={<TactileMeter value={42.5} tone="telemetry" size="md" ticks={[25, 50, 75, 90]} />}
        titleWidth={220}
        pathWidth={200}
        metricsWidth={180}
        statusWidth={72}
      />

      <DataGridRow
        title="System RAM Working Set"
        path="mem · DDR5-5600 EXPO"
        detail="ZRAM active · 14.2 GB buffers"
        metrics="24.8 GB / 64.0 GB"
        status={<MetricStatus value="38.7%" tone="nominal" />}
        meter={<TactileMeter value={38.7} tone="telemetry" size="md" ticks={[25, 50, 75, 90]} />}
        titleWidth={220}
        pathWidth={200}
        metricsWidth={180}
        statusWidth={72}
      />

      <DataGridRow
        title="NVMe Dirty Writeback Buffer"
        path="pci0000:00/nvme0n1"
        detail="PCIe 4.0 x4 · Flush in progress"
        metrics="1.2 GB / 4.0 GB"
        status={<MetricStatus value="30.0%" tone="telemetry" />}
        meter={<TactileMeter value={30.0} tone="data-amber" size="md" ticks={[25, 50, 75, 90]} />}
        titleWidth={220}
        pathWidth={200}
        metricsWidth={180}
        statusWidth={72}
      />

      <DataGridRow
        title="CPU Package Thermal Ceiling"
        path="hwmon0/k10temp/Tctl"
        detail="Die Peak: 81.2°C · Ambient: 22°C"
        metrics="78.5°C / 95.0°C"
        status={<MetricStatus value="82.6% WARN" tone="warning" />}
        meter={<TactileMeter value={82.6} tone="warning" size="md" ticks={[25, 50, 75, 90]} />}
        titleWidth={220}
        pathWidth={200}
        metricsWidth={180}
        statusWidth={72}
      />
    </CardContainer>
  ),
}

/* ------------------------------------- 3. AI Accelerator & GPU VRAM Template -- */

const vramSegments: SegmentItem[] = [
  { id: 'weights', label: 'Model Weights (Q4_K_M)', value: 14.2, tone: 'data-blue', detail: 'Llama-3.3-70B' },
  { id: 'kv', label: 'KV Cache Context', value: 4.6, tone: 'data-amber', detail: '16k token context' },
  { id: 'surface', label: 'Display Compositor', value: 1.1, tone: 'data-teal', detail: 'Wayland surface' },
]

export const AcceleratorVramTemplate: StoryObj = {
  name: 'Template / GPU & AI Accelerator Memory',
  render: () => (
    <CardContainer
      title="NVIDIA GeForce RTX 4090 (24 GB VRAM)"
      subtitle="pci:0000:01:00.0 · Driver: 565.77 · CUDA 12.7 · Compute 8.9"
      status={<StatusIndicator tone="nominal" label="INFERENCE ACTIVE" />}
    >
      {/* VRAM Segmentation Tray */}
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 8 }}>
          <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--color-ink)' }}>
            VRAM Memory Topology Breakdown
          </span>
          <span style={{ fontSize: 12, fontFamily: 'var(--font-mono)', color: 'var(--color-ink-secondary)' }}>
            19.9 GB Allocated / 4.1 GB Free Headroom (82.9%)
          </span>
        </div>
        <SegmentedBar
          segments={vramSegments}
          total={24.0}
          unit="GB"
          showLegend
          showFreeHeadroom
          size="md"
        />
      </div>

      <div style={{ height: 1, backgroundColor: 'var(--color-border)', margin: 'var(--space-2) 0' }} />

      {/* Aligned Telemetry Rows */}
      <DataGridRow
        title="Tensor Core Execution"
        path="nvml/engine/tensor"
        detail="FP8 Matrix Math · Batch=1"
        metrics="88.4% Load"
        status={<MetricStatus value="88.4%" tone="nominal" />}
        meter={<TactileMeter value={88.4} tone="telemetry" size="md" />}
        titleWidth={220}
        pathWidth={180}
        metricsWidth={180}
        statusWidth={72}
      />

      <DataGridRow
        title="Board Power Envelope"
        path="nvml/power/draw"
        detail="TDP Limit: 450W · Peak: 385W"
        metrics="315.0W / 450.0W"
        status={<MetricStatus value="70.0%" tone="nominal" />}
        meter={<TactileMeter value={70.0} tone="data-orange" size="md" />}
        titleWidth={220}
        pathWidth={180}
        metricsWidth={180}
        statusWidth={72}
      />

      <DataGridRow
        title="GPU Hotspot Temperature"
        path="nvml/thermal/hotspot"
        detail="Throttling Limit: 105.0°C"
        metrics="74.0°C / 105.0°C"
        status={<MetricStatus value="70.5%" tone="nominal" />}
        meter={<TactileMeter value={70.5} tone="telemetry" size="md" />}
        titleWidth={220}
        pathWidth={180}
        metricsWidth={180}
        statusWidth={72}
      />
    </CardContainer>
  ),
}

/* ------------------------------------- 4. Federated Cluster Fleet Matrix -- */

export const ClusterFleetMatrixTemplate: StoryObj = {
  name: 'Template / Federated Cluster Node Matrix',
  render: () => (
    <CardContainer
      title="Federated Cluster Node Health Matrix"
      subtitle="Mesh: WireGuard · 4 Nodes Online · 1 Node Degraded · Latency Floor: 0.4ms"
      status={<StatusIndicator tone="warning" label="1 NODE DEGRADED" />}
    >
      <DataGridRow
        title="halbert-primary"
        path="192.168.1.10 · Primary"
        detail="16 Cores · 64 GB RAM"
        metrics="CPU: 24.5% · RAM: 58.2%"
        status={<MetricStatus value="ONLINE" tone="nominal" />}
        meter={<TactileMeter value={24.5} tone="telemetry" size="md" />}
        titleWidth={220}
        pathWidth={180}
        metricsWidth={180}
        statusWidth={72}
      />

      <DataGridRow
        title="halbert-storage-vault"
        path="192.168.1.15 · NAS"
        detail="8 Cores · 32 GB RAM · 48 TB Raw"
        metrics="CPU: 8.2% · RAM: 82.0%"
        status={<MetricStatus value="ONLINE" tone="nominal" />}
        meter={<TactileMeter value={8.2} tone="telemetry" size="md" />}
        titleWidth={220}
        pathWidth={180}
        metricsWidth={180}
        statusWidth={72}
      />

      {/* Critical Degraded Worker Node */}
      <DataGridRow
        title="halbert-worker-inference-01"
        path="192.168.1.20 · Worker"
        detail="32 Cores · 128 GB RAM · 2x RTX 4090"
        metrics="CPU: 97.4% · RAM: 94.1%"
        status={<MetricStatus value="CRITICAL" tone="critical" />}
        meter={<TactileMeter value={97.4} tone="critical" size="md" />}
        titleWidth={220}
        pathWidth={180}
        metricsWidth={180}
        statusWidth={72}
      />

      <DataGridRow
        title="halbert-edge-relay"
        path="192.168.1.50 · Edge Gateway"
        detail="4 Cores · 8 GB RAM · 2.5 GbE WAN"
        metrics="CPU: 12.0% · RAM: 32.5%"
        status={<MetricStatus value="ONLINE" tone="nominal" />}
        meter={<TactileMeter value={12.0} tone="telemetry" size="md" />}
        titleWidth={220}
        pathWidth={180}
        metricsWidth={180}
        statusWidth={72}
      />
    </CardContainer>
  ),
}

/* --------------------------------- 5. Hardware Environmental Sensor Matrix -- */

export const HardwareSensorsTemplate: StoryObj = {
  name: 'Template / Environmental Hardware Sensors',
  render: () => (
    <CardContainer
      title="Hardware Environmental & Thermal Sensors"
      subtitle="Chassis Telemetry via hwmon / it8688 / k10temp / drivetemp"
      status={<StatusIndicator tone="nominal" label="ALL SENSORS NORMAL" />}
    >
      <DataGridRow
        title="Samsung 990 PRO (Boot NVMe)"
        path="hwmon2 · nvme0n1"
        detail="Composite Sensor · Critical: 70°C"
        metrics="42.0°C / 70.0°C"
        status={<MetricStatus value="60.0%" tone="nominal" />}
        meter={<TactileMeter value={60.0} tone="telemetry" size="md" />}
        titleWidth={240}
        pathWidth={160}
        metricsWidth={180}
        statusWidth={72}
      />

      <DataGridRow
        title="Crucial T700 PCIe 5.0 (Scratch Pool)"
        path="hwmon3 · nvme1n1"
        detail="Active Heatsink · Warning: 65°C"
        metrics="64.2°C / 75.0°C"
        status={<MetricStatus value="85.6% WARN" tone="warning" />}
        meter={<TactileMeter value={85.6} tone="warning" size="md" />}
        titleWidth={240}
        pathWidth={160}
        metricsWidth={180}
        statusWidth={72}
      />

      <DataGridRow
        title="CPU VRM Power Delivery Stage"
        path="hwmon1 · it8688/temp2"
        detail="16+2 Power Phases · Limit: 105°C"
        metrics="54.0°C / 105.0°C"
        status={<MetricStatus value="51.4%" tone="nominal" />}
        meter={<TactileMeter value={51.4} tone="telemetry" size="md" />}
        titleWidth={240}
        pathWidth={160}
        metricsWidth={180}
        statusWidth={72}
      />

      <DataGridRow
        title="Chassis Front Intake Fan Array"
        path="hwmon1 · it8688/fan1"
        detail="3x 140mm PWM Fans · Max: 1800 RPM"
        metrics="1120 RPM / 1800 RPM"
        status={<MetricStatus value="62.2%" tone="nominal" />}
        meter={<TactileMeter value={62.2} tone="telemetry" size="md" />}
        titleWidth={240}
        pathWidth={160}
        metricsWidth={180}
        statusWidth={72}
      />
    </CardContainer>
  ),
}

/* ------------------------------------------------------------- 6. Thick Bar Scenarios -- */

/* Scenario A: Integrated Avionics Track (Recommended) */
export const ScenarioA_IntegratedAvionics: StoryObj = {
  name: 'Scenario A: Integrated Avionics (Recommended)',
  render: () => (
    <CardContainer
      title="Scenario A: Integrated Avionics Track (Recommended)"
      subtitle="28px thick track · Machine path (left) & metrics (right) integrated directly inside gauge · Zero upper cramping"
      status={<StatusIndicator tone="nominal" label="RECOMMENDED" />}
    >
      <DataGridRow
        variant="in-bar"
        title="Primary System Root"
        detail="Subvolume ID 256 · Compression: zstd:3 · RAID1"
        status={<MetricStatus value="● HEALTHY" tone="nominal" />}
        meter={
          <TactileMeter
            value={28.4}
            tone="telemetry"
            size="thick"
            inBarLeft="/ · btrfs"
            inBarRight="142.0 GB / 500.0 GB · 28.4%"
            ticks={[25, 50, 75, 90]}
          />
        }
      />

      <DataGridRow
        variant="in-bar"
        title="Application & Container Storage"
        detail="Subvolume ID 257 · Docker Root & Overlay2 Pool"
        status={<MetricStatus value="● HEALTHY" tone="nominal" />}
        meter={
          <TactileMeter
            value={38.7}
            tone="telemetry"
            size="thick"
            inBarLeft="/var/lib/docker · btrfs"
            inBarRight="77.4 GB / 200.0 GB · 38.7%"
            ticks={[25, 50, 75, 90]}
          />
        }
      />

      <DataGridRow
        variant="in-bar"
        title="Local LLM Model Weights & Artifacts"
        detail="Subvolume ID 258 · Direct I/O Cache · High Throughput"
        status={<MetricStatus value="▲ WARN" tone="warning" />}
        meter={
          <TactileMeter
            value={82.0}
            tone="warning"
            size="thick"
            inBarLeft="/models · btrfs"
            inBarRight="1.64 TB / 2.00 TB · 82.0%"
            ticks={[25, 50, 75, 90]}
          />
        }
      />

      <DataGridRow
        variant="in-bar"
        title="Scratch NVMe High-Speed Swap Pool"
        detail="Subvolume ID 259 · Critical Capacity Ceiling Reached"
        status={<MetricStatus value="■ CRIT" tone="critical" />}
        meter={
          <TactileMeter
            value={95.8}
            tone="critical"
            size="thick"
            inBarLeft="/scratch · btrfs"
            inBarRight="958.0 GB / 1.00 TB · 95.8%"
            ticks={[25, 50, 75, 90]}
          />
        }
      />
    </CardContainer>
  ),
}

/* Scenario B: Dual-Deck Master Bench */
export const ScenarioB_DualDeckMasterBench: StoryObj = {
  name: 'Scenario B: Dual-Deck Master Bench',
  render: () => (
    <CardContainer
      title="Scenario B: Dual-Deck Master Bench"
      subtitle="24px track · Upper deck has title & metrics · In-bar overlay shows device spec & free headroom target"
      status={<StatusIndicator tone="telemetry" label="ALTERNATIVE" />}
    >
      <DataGridRow
        variant="dual-deck"
        title="System RAM Working Set"
        metrics="24.8 GB / 64.0 GB"
        status={<MetricStatus value="38.7%" tone="nominal" />}
        meter={
          <TactileMeter
            value={38.7}
            tone="telemetry"
            size="xl"
            inBarLeft="mem · DDR5-5600 EXPO"
            inBarRight="39.2 GB Free Headroom"
            ticks={[25, 50, 75, 90]}
          />
        }
        path="ZRAM active · 14.2 GB buffers"
        detail="Memory Controller: Dual Channel (128-bit) · ECC Nominal"
      />

      <DataGridRow
        variant="dual-deck"
        title="NVMe Dirty Writeback Buffer"
        metrics="1.2 GB / 4.0 GB"
        status={<MetricStatus value="30.0%" tone="nominal" />}
        meter={
          <TactileMeter
            value={30.0}
            tone="data-amber"
            size="xl"
            inBarLeft="pci0000:00/nvme0n1"
            inBarRight="2.8 GB Buffer Room"
            ticks={[25, 50, 75, 90]}
          />
        }
        path="PCIe 4.0 x4 · Flush in progress"
        detail="Device: Samsung 990 PRO · Queue Depth: 32"
      />

      <DataGridRow
        variant="dual-deck"
        title="CPU Package Thermal Ceiling"
        metrics="78.5°C / 95.0°C"
        status={<MetricStatus value="82.6% WARN" tone="warning" />}
        meter={
          <TactileMeter
            value={82.6}
            tone="warning"
            size="xl"
            inBarLeft="hwmon0/k10temp/Tctl"
            inBarRight="16.5°C Delta to Throttle"
            ticks={[25, 50, 75, 90]}
          />
        }
        path="Die Peak: 81.2°C · Ambient: 22°C"
        detail="Cooler: Arctic Liquid Freezer III 360 · Pump: 100%"
      />
    </CardContainer>
  ),
}

/* Scenario C: Cockpit Master HUD */
export const ScenarioC_CockpitMasterHUD: StoryObj = {
  name: 'Scenario C: Cockpit Master HUD',
  render: () => (
    <CardContainer
      title="Scenario C: Cockpit Master HUD"
      subtitle="32px chunky cassette track · Volume title & status unified inside gauge · Monospace specs below"
      status={<StatusIndicator tone="telemetry" label="ALTERNATIVE" />}
    >
      <DataGridRow
        variant="in-bar"
        title="Primary System Root"
        meter={
          <TactileMeter
            value={28.4}
            tone="telemetry"
            size="hero"
            inBarLeft={
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                <span style={{ color: 'var(--color-ink-tertiary)' }}>[ROOT]</span>
                <strong>Primary System Root</strong>
                <span style={{ opacity: 0.7 }}>(/)</span>
              </span>
            }
            inBarRight="142.0 GB / 500.0 GB · 28.4% NOMINAL"
            ticks={[25, 50, 75, 90]}
          />
        }
        subdeck="dev: /dev/nvme0n1p2 · fs: btrfs · subvol: 256 · comp: zstd:3 · scrub: PASSED (3d ago)"
      />

      <DataGridRow
        variant="in-bar"
        title="Docker Container Volumes"
        meter={
          <TactileMeter
            value={38.7}
            tone="telemetry"
            size="hero"
            inBarLeft={
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                <span style={{ color: 'var(--color-ink-tertiary)' }}>[DOCK]</span>
                <strong>Container Volumes</strong>
                <span style={{ opacity: 0.7 }}>(/var/lib/docker)</span>
              </span>
            }
            inBarRight="77.4 GB / 200.0 GB · 38.7% NOMINAL"
            ticks={[25, 50, 75, 90]}
          />
        }
        subdeck="dev: /dev/nvme0n1p3 · fs: btrfs · subvol: 257 · overlay2 backend · 24 running containers"
      />

      <DataGridRow
        variant="in-bar"
        title="Scratch Swap Pool"
        meter={
          <TactileMeter
            value={95.8}
            tone="critical"
            size="hero"
            inBarLeft={
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                <span style={{ color: 'var(--color-status-critical)' }}>[WARN]</span>
                <strong>Scratch Swap Pool</strong>
                <span style={{ opacity: 0.7 }}>(/scratch)</span>
              </span>
            }
            inBarRight="958.0 GB / 1.00 TB · 95.8% CRITICAL"
            ticks={[25, 50, 75, 90]}
          />
        }
        subdeck="dev: /dev/nvme1n1p1 · fs: btrfs · subvol: 259 · automatic vacuum triggered"
      />
    </CardContainer>
  ),
}

/* Scenario D: Multi-Category In-Segment Micro-Chips */
export const ScenarioD_SegmentedInBarLabels: StoryObj = {
  name: 'Scenario D: Segmented Multi-Category (For Dataviz)',
  render: () => (
    <CardContainer
      title="Scenario D: Segmented Multi-Category In-Bar Labels"
      subtitle="32px segmented track · Micro-labels embedded inside slices · Eliminates legend cross-referencing"
      status={<StatusIndicator tone="nominal" label="DATAVIZ BEST PRACTICE" />}
    >
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 8 }}>
          <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--color-ink)' }}>
            NVIDIA RTX 4090 — 24 GB VRAM Allocation
          </span>
          <span style={{ fontSize: 12, fontFamily: 'var(--font-mono)', color: 'var(--color-ink-secondary)' }}>
            19.9 GB Allocated / 4.1 GB Free (82.9%)
          </span>
        </div>
        <SegmentedBar
          segments={vramSegments}
          total={24.0}
          unit="GB"
          size="thick"
          showInSegmentLabels
          showLegend
          showFreeHeadroom
        />
      </div>

      <div style={{ height: 1, backgroundColor: 'var(--color-border)', margin: 'var(--space-4) 0' }} />

      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 8 }}>
          <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--color-ink)' }}>
            Storage Pool Allocation Topology (btrfs data pool)
          </span>
          <span style={{ fontSize: 12, fontFamily: 'var(--font-mono)', color: 'var(--color-ink-secondary)' }}>
            356.0 GB Used / 144.0 GB Free (71.2%)
          </span>
        </div>
        <SegmentedBar
          segments={[
            { id: 'data', label: 'Active User Data', value: 280.0, tone: 'data-blue', detail: 'Single device' },
            { id: 'meta', label: 'Filesystem Metadata', value: 48.0, tone: 'data-teal', detail: 'DUP profile' },
            { id: 'snaps', label: 'Read-Only Snapshots', value: 28.0, tone: 'data-purple', detail: '14 subvolume snaps' },
          ]}
          total={500.0}
          unit="GB"
          size="thick"
          showInSegmentLabels
          showLegend
          showFreeHeadroom
        />
      </div>
    </CardContainer>
  ),
}

/* Responsive Adaptive Simulation */
export const ResponsiveAdaptiveSimulation: StoryObj = {
  name: 'Responsive / Adaptive Width Simulation',
  render: () => (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 32 }}>
      <div>
        <h3 style={{ margin: '0 0 8px 0', fontSize: 15, fontWeight: 600, color: 'var(--color-ink)' }}>
          Desktop Viewport (920px Card Width)
        </h3>
        <CardContainer
          title="Storage Subvolumes (Desktop 920px)"
          subtitle="Full width: generous breathing room between human title, path, and numerical telemetry"
          status={<StatusIndicator tone="nominal" label="DESKTOP" />}
          width={920}
        >
          <DataGridRow
            variant="in-bar"
            title="Primary System Root"
            detail="Subvolume ID 256 · Compression: zstd:3"
            status={<MetricStatus value="● HEALTHY" tone="nominal" />}
            meter={
              <TactileMeter
                value={28.4}
                tone="telemetry"
                size="thick"
                inBarLeft="/ · btrfs"
                inBarRight="142.0 GB / 500.0 GB · 28.4%"
              />
            }
          />
          <DataGridRow
            variant="in-bar"
            title="Local LLM Model Weights & Artifacts"
            detail="Subvolume ID 258 · Direct I/O Cache"
            status={<MetricStatus value="▲ WARN" tone="warning" />}
            meter={
              <TactileMeter
                value={82.0}
                tone="warning"
                size="thick"
                inBarLeft="/models · btrfs"
                inBarRight="1.64 TB / 2.00 TB · 82.0%"
              />
            }
          />
        </CardContainer>
      </div>

      <div>
        <h3 style={{ margin: '0 0 8px 0', fontSize: 15, fontWeight: 600, color: 'var(--color-ink)' }}>
          Tablet / Medium Viewport (640px Card Width)
        </h3>
        <CardContainer
          title="Storage Subvolumes (Tablet 640px)"
          subtitle="Subtle adaptability: zero wrapping, Title stays pristine, in-bar chips preserve alignment"
          status={<StatusIndicator tone="nominal" label="TABLET" />}
          width={640}
        >
          <DataGridRow
            variant="in-bar"
            title="Primary System Root"
            detail="Subvolume ID 256"
            status={<MetricStatus value="● HEALTHY" tone="nominal" />}
            meter={
              <TactileMeter
                value={28.4}
                tone="telemetry"
                size="thick"
                inBarLeft="/ · btrfs"
                inBarRight="142.0 GB / 500.0 GB · 28.4%"
              />
            }
          />
          <DataGridRow
            variant="in-bar"
            title="Local LLM Model Weights"
            detail="Subvolume ID 258"
            status={<MetricStatus value="▲ WARN" tone="warning" />}
            meter={
              <TactileMeter
                value={82.0}
                tone="warning"
                size="thick"
                inBarLeft="/models · btrfs"
                inBarRight="1.64 TB / 2.00 TB · 82.0%"
              />
            }
          />
        </CardContainer>
      </div>

      <div>
        <h3 style={{ margin: '0 0 8px 0', fontSize: 15, fontWeight: 600, color: 'var(--color-ink)' }}>
          Mobile Viewport (400px Card Width)
        </h3>
        <CardContainer
          title="Storage Subvolumes (Mobile 400px)"
          subtitle="Graceful compaction: in-bar left path truncates with ellipsis, numbers remain visible"
          status={<StatusIndicator tone="nominal" label="MOBILE" />}
          width={400}
        >
          <DataGridRow
            variant="in-bar"
            title="Primary Root"
            status={<MetricStatus value="● OK" tone="nominal" />}
            meter={
              <TactileMeter
                value={28.4}
                tone="telemetry"
                size="thick"
                inBarLeft="/"
                inBarRight="142 GB (28.4%)"
              />
            }
          />
          <DataGridRow
            variant="in-bar"
            title="LLM Models"
            status={<MetricStatus value="▲ WARN" tone="warning" />}
            meter={
              <TactileMeter
                value={82.0}
                tone="warning"
                size="thick"
                inBarLeft="/models"
                inBarRight="1.64 TB (82.0%)"
              />
            }
          />
        </CardContainer>
      </div>
    </div>
  ),
}

