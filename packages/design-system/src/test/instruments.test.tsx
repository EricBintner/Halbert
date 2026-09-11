import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'

import { TactileMeter } from '../primitives/TactileMeter'
import { SegmentedBar, type SegmentItem } from '../primitives/SegmentedBar'

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

  it('defaults to calm neutral graphite tone (avoiding pseudo-meaning traffic lights)', () => {
    const { container } = render(<TactileMeter value={50} />)
    expect(container.querySelector('.hb-tactile-meter--neutral')).toBeInTheDocument()
  })

  it('allows explicit tone overrides (critical fault, data series)', () => {
    const { container, rerender } = render(<TactileMeter value={30} tone="critical" />)
    expect(container.querySelector('.hb-tactile-meter--critical')).toBeInTheDocument()

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
