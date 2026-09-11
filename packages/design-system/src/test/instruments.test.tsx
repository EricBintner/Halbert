import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'

import { TactileMeter } from '../primitives/TactileMeter'
import { SegmentedBar, type SegmentItem } from '../primitives/SegmentedBar'
import { DataGridRow } from '../primitives/DataGridRow'
import { DriveCassette } from '../primitives/DriveCassette'
import { StorageTierGroup } from '../primitives/StorageTierGroup'

describe('TactileMeter', () => {
  it('renders with meter role and correct ARIA values', () => {
    render(
      <TactileMeter
        value={45.5}
        label="Root Volume"
        sub="/ · btrfs"
      />
    )

    const meter = screen.getByRole('meter')
    expect(meter).toHaveAttribute('aria-valuenow', '45.5')
    expect(meter).toHaveAttribute('aria-valuemin', '0')
    expect(meter).toHaveAttribute('aria-valuemax', '100')
    expect(screen.getByText('Root Volume')).toBeInTheDocument()
    expect(screen.getByText('/ · btrfs')).toBeInTheDocument()
    expect(screen.getByText('45.5%')).toBeInTheDocument()
  })

  it('clamps out-of-range values between 0 and 100', () => {
    const { rerender } = render(<TactileMeter value={150} label="Overload" />)
    expect(screen.getByRole('meter')).toHaveAttribute('aria-valuenow', '100')
    expect(screen.getByText('100.0%')).toBeInTheDocument()

    rerender(<TactileMeter value={-25} label="Underload" />)
    expect(screen.getByRole('meter')).toHaveAttribute('aria-valuenow', '0')
    expect(screen.getByText('0.0%')).toBeInTheDocument()
  })

  it('defaults to vibrant telemetry blue tone', () => {
    const { container } = render(<TactileMeter value={50} />)
    expect(container.querySelector('.hb-tactile-meter--telemetry')).toBeInTheDocument()
  })

  it('resolves auto tones: telemetry (<75), warning (75-89), critical (>=90)', () => {
    const { container, rerender } = render(<TactileMeter value={50} tone="auto" />)
    expect(container.querySelector('.hb-tactile-meter--telemetry')).toBeInTheDocument()

    rerender(<TactileMeter value={80} tone="auto" />)
    expect(container.querySelector('.hb-tactile-meter--warning')).toBeInTheDocument()

    rerender(<TactileMeter value={95} tone="auto" />)
    expect(container.querySelector('.hb-tactile-meter--critical')).toBeInTheDocument()
  })

  it('allows explicit tone overrides (critical fault, neutral, data series)', () => {
    const { container, rerender } = render(<TactileMeter value={30} tone="critical" />)
    expect(container.querySelector('.hb-tactile-meter--critical')).toBeInTheDocument()

    rerender(<TactileMeter value={30} tone="neutral" />)
    expect(container.querySelector('.hb-tactile-meter--neutral')).toBeInTheDocument()

    rerender(<TactileMeter value={30} tone="data-blue" />)
    expect(container.querySelector('.hb-tactile-meter--data-blue')).toBeInTheDocument()
  })

  it('renders honest offline state without displaying a plausible-looking number', () => {
    const { container } = render(
      <TactileMeter
        value={45}
        label="Drive Sensor"
        offline
      />
    )

    expect(screen.getByText('[Sensor offline]')).toBeInTheDocument()
    expect(container.querySelector('.is-offline')).toBeInTheDocument()
    // In offline state, fill bar is not rendered
    expect(container.querySelector('.hb-tactile-meter__fill')).toBeNull()
    // Meter aria-valuenow should be undefined
    const meter = screen.getByRole('meter')
    expect(meter).not.toHaveAttribute('aria-valuenow')
  })

  it('renders scale tick marks at specified positions', () => {
    const { container } = render(
      <TactileMeter value={50} ticks={[25, 50, 75, 90]} />
    )

    const ticks = container.querySelectorAll('.hb-tactile-meter__tick')
    expect(ticks.length).toBe(4)
    expect(ticks[0]).toHaveStyle({ left: '25%' })
    expect(ticks[3]).toHaveClass('hb-tactile-meter__tick--critical')
  })
})

describe('SegmentedBar', () => {
  const testSegments: SegmentItem[] = [
    { id: 'data', label: 'Data', value: 400, tone: 'data-blue', detail: 'RAID1' },
    { id: 'meta', label: 'Metadata', value: 50, tone: 'data-purple', pattern: 'hatched' },
  ]

  it('renders segments with proportional widths based on total', () => {
    const { container } = render(
      <SegmentedBar
        segments={testSegments}
        total={1000}
        unit="GB"
      />
    )

    const segments = container.querySelectorAll('.hb-segmented-bar__segment')
    expect(segments.length).toBe(2)
    // 400/1000 = 40%
    expect(segments[0]).toHaveStyle({ width: '40%' })
    expect(segments[0]).toHaveClass('hb-segmented-bar__segment--data-blue')
    // 50/1000 = 5%
    expect(segments[1]).toHaveStyle({ width: '5%' })
    expect(segments[1]).toHaveClass('is-hatched')
  })

  it('renders tabular legend with computed free headroom', () => {
    render(
      <SegmentedBar
        segments={testSegments}
        total={1000}
        unit="GB"
        showFreeHeadroom
      />
    )

    expect(screen.getByText('Data')).toBeInTheDocument()
    expect(screen.getByText('(RAID1)')).toBeInTheDocument()
    expect(screen.getByText('400.0 GB')).toBeInTheDocument()
    expect(screen.getByText('(40%)')).toBeInTheDocument()

    expect(screen.getByText('Metadata')).toBeInTheDocument()
    expect(screen.getByText('50.0 GB')).toBeInTheDocument()

    // Free: 1000 - 450 = 550 GB (55%)
    expect(screen.getByText('Free Headroom')).toBeInTheDocument()
    expect(screen.getByText('550.0 GB')).toBeInTheDocument()
    expect(screen.getByText('(55%)')).toBeInTheDocument()
  })

  it('renders offline state properly', () => {
    const { container } = render(
      <SegmentedBar
        segments={testSegments}
        total={1000}
        offline
      />
    )

    expect(container.querySelector('.is-offline')).toBeInTheDocument()
    expect(container.querySelector('.hb-segmented-bar__offline-strip')).toBeInTheDocument()
    expect(container.querySelectorAll('.hb-segmented-bar__segment').length).toBe(0)
  })
})

describe('DataGridRow', () => {
  it('renders all 5 grid slots with strict columnar structure', () => {
    const { container } = render(
      <DataGridRow
        icon={<span data-testid="test-icon">📁</span>}
        title="Root Volume"
        path="/ · btrfs"
        detail="RAID1 · Subvol 256"
        metrics="142 GB / 500 GB"
        status={<span data-testid="test-badge">28.4%</span>}
        meter={<TactileMeter value={28.4} size="md" />}
      />
    )

    expect(screen.getByTestId('test-icon')).toBeInTheDocument()
    expect(screen.getByText('Root Volume')).toBeInTheDocument()
    expect(screen.getByText('/ · btrfs')).toBeInTheDocument()
    expect(screen.getByText('RAID1 · Subvol 256')).toBeInTheDocument()
    expect(screen.getByText('142 GB / 500 GB')).toBeInTheDocument()
    expect(screen.getByTestId('test-badge')).toBeInTheDocument()
    expect(screen.getByRole('meter')).toBeInTheDocument()

    const grid = container.querySelector('.hb-data-row__grid')
    expect(grid).toBeInTheDocument()
  })

  it('applies custom title and path widths', () => {
    const { container } = render(
      <DataGridRow
        title="Database Array"
        path="/var/lib/postgresql"
        titleWidth={240}
        pathWidth={220}
      />
    )

    const row = container.querySelector('.hb-data-row') as HTMLElement
    expect(row.style.getPropertyValue('--data-row-title-width')).toBe('240px')
    expect(row.style.getPropertyValue('--data-row-path-width')).toBe('220px')
  })
})

describe('TactileMeter Grid Alignment', () => {
  it('applies labelWidth style and renders statusBadge in dedicated slot', () => {
    const { container } = render(
      <TactileMeter
        value={92.5}
        label="Root Volume"
        sub="/ · btrfs"
        labelWidth={220}
        statusBadge={<span data-testid="crit-badge">CRITICAL</span>}
      />
    )

    const meter = container.querySelector('.hb-tactile-meter') as HTMLElement
    expect(meter).toHaveClass('hb-tactile-meter--has-label-width')
    expect(meter.style.getPropertyValue('--meter-label-width')).toBe('220px')
    expect(screen.getByTestId('crit-badge')).toBeInTheDocument()
    expect(container.querySelector('.hb-tactile-meter__status')).toBeInTheDocument()
  })

  it('renders inBarLeft and inBarRight overlays inside meter track', () => {
    const { container } = render(
      <TactileMeter
        value={45.0}
        size="thick"
        inBarLeft={<span data-testid="in-bar-path">/ · btrfs</span>}
        inBarRight={<span data-testid="in-bar-metrics">142 GB / 500 GB</span>}
      />
    )

    expect(container.querySelector('.hb-tactile-meter--thick')).toBeInTheDocument()
    expect(screen.getByTestId('in-bar-path')).toBeInTheDocument()
    expect(screen.getByTestId('in-bar-metrics')).toBeInTheDocument()
    expect(container.querySelector('.hb-tactile-meter__in-bar')).toBeInTheDocument()
  })
})

describe('DataGridRow Variants', () => {
  it('renders variant="in-bar" with spacious two-tier layout', () => {
    const { container } = render(
      <DataGridRow
        variant="in-bar"
        title="Root Volume"
        detail="Subvol 256 · zstd:3"
        status={<span data-testid="status-indicator">● HEALTHY</span>}
        meter={
          <TactileMeter
            value={28.4}
            size="thick"
            inBarLeft="/ · btrfs"
            inBarRight="142 GB / 500 GB"
          />
        }
      />
    )

    expect(container.querySelector('.hb-data-row--in-bar')).toBeInTheDocument()
    expect(screen.getByText('Root Volume')).toBeInTheDocument()
    expect(screen.getByText('· Subvol 256 · zstd:3')).toBeInTheDocument()
    expect(screen.getByTestId('status-indicator')).toBeInTheDocument()
    expect(screen.getByText('/ · btrfs')).toBeInTheDocument()
    expect(screen.getByText('142 GB / 500 GB')).toBeInTheDocument()
  })

  it('renders variant="dual-deck" with lower subdeck', () => {
    const { container } = render(
      <DataGridRow
        variant="dual-deck"
        title="System RAM"
        metrics="24.8 GB / 64.0 GB"
        status={<span>38.7%</span>}
        path="mem · DDR5"
        detail="Dual Channel"
      />
    )

    expect(container.querySelector('.hb-data-row--dual-deck')).toBeInTheDocument()
    expect(screen.getByText('System RAM')).toBeInTheDocument()
    expect(screen.getByText('24.8 GB / 64.0 GB')).toBeInTheDocument()
    expect(screen.getByText('mem · DDR5')).toBeInTheDocument()
    expect(screen.getByText('Dual Channel')).toBeInTheDocument()
  })
})

describe('SegmentedBar In-Segment Labels', () => {
  it('renders labels directly inside colored segments on thick tracks', () => {
    const segments = [
      { id: 'data', label: 'User Data', value: 300, tone: 'data-blue' as const },
      { id: 'meta', label: 'Metadata', value: 50, tone: 'data-teal' as const },
    ]

    const { container } = render(
      <SegmentedBar
        segments={segments}
        total={500}
        size="thick"
        showInSegmentLabels
      />
    )

    expect(container.querySelector('.hb-segmented-bar--thick')).toBeInTheDocument()
    const inSegmentLabels = container.querySelectorAll('.hb-segmented-bar__segment-label')
    expect(inSegmentLabels.length).toBeGreaterThanOrEqual(2)
  })
})

describe('DriveCassette', () => {
  it('renders physical drive hardware identity, diagnostics, and in-bar gauge', () => {
    const { container } = render(
      <DriveCassette
        device="/dev/nvme0n1"
        label="nvme.u2_01"
        model="Samsung PM9A3 3.84 TB"
        transport="PCIe 4.0 x4 NVMe"
        size="3.84 TB"
        used="1.20 TB"
        percent={31.2}
        smartStatus="PASSED"
        temperature={38}
        roles={['Write', 'Foreground']}
      />
    )

    expect(container.querySelector('.hb-drive-cassette')).toBeInTheDocument()
    expect(screen.getByText('/dev/nvme0n1')).toBeInTheDocument()
    expect(screen.getByText('nvme.u2_01')).toBeInTheDocument()
    expect(screen.getByText('Samsung PM9A3 3.84 TB')).toBeInTheDocument()
    expect(screen.getByText('PCIe 4.0 x4 NVMe')).toBeInTheDocument()
    expect(screen.getByText('38°C')).toBeInTheDocument()
    expect(screen.getByText('PASSED')).toBeInTheDocument()
    expect(screen.getByText('Write')).toBeInTheDocument()
    expect(screen.getByText('Foreground')).toBeInTheDocument()
  })

  it('renders nested partitions when partitions array is supplied', () => {
    const partitions = [
      { id: 'p1', device: '/dev/nvme0n1p1', mountpoint: '/boot/efi', fstype: 'vfat', size: '1.0 GB', used: '96 MB', percent: 9.4 },
      { id: 'p2', device: '/dev/nvme0n1p2', mountpoint: '/', fstype: 'bcachefs', size: '1.8 TB', used: '142 GB', percent: 7.9 },
    ]

    const { container } = render(
      <DriveCassette
        device="/dev/nvme0n1"
        model="Samsung 990 PRO 2.0 TB"
        size="2.0 TB"
        partitions={partitions}
      />
    )

    expect(container.querySelector('.hb-drive-cassette__partition-block')).toBeInTheDocument()
    expect(screen.getByText('/dev/nvme0n1p1')).toBeInTheDocument()
    expect(screen.getByText('→ /boot/efi')).toBeInTheDocument()
    expect(screen.getByText('/dev/nvme0n1p2')).toBeInTheDocument()
    expect(screen.getByText('→ /')).toBeInTheDocument()
  })
})

describe('StorageTierGroup', () => {
  it('renders tier cassette container with title, role badge, and member drive cassettes', () => {
    const { container } = render(
      <StorageTierGroup
        title="Tier 01: Foreground Write Cache"
        subtitle="Target: foreground · 2x NVMe U.2 Mirror"
        roleLabel="WRITE CACHE"
        capacity="7.68 TB Raw"
        status={<span data-testid="tier-status">● NOMINAL</span>}
      >
        <DriveCassette device="/dev/nvme0n1" label="nvme.u2_01" size="3.84 TB" />
        <DriveCassette device="/dev/nvme1n1" label="nvme.u2_02" size="3.84 TB" />
      </StorageTierGroup>
    )

    expect(container.querySelector('.hb-tier-group')).toBeInTheDocument()
    expect(screen.getByText('Tier 01: Foreground Write Cache')).toBeInTheDocument()
    expect(screen.getByText('Target: foreground · 2x NVMe U.2 Mirror')).toBeInTheDocument()
    expect(screen.getByText('WRITE CACHE')).toBeInTheDocument()
    expect(screen.getByText('7.68 TB Raw')).toBeInTheDocument()
    expect(screen.getByTestId('tier-status')).toBeInTheDocument()
    expect(screen.getByText('/dev/nvme0n1')).toBeInTheDocument()
    expect(screen.getByText('/dev/nvme1n1')).toBeInTheDocument()
  })
})


