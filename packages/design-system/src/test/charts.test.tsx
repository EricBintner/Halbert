// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'

import { SlopeChart } from '../charts/SlopeChart'
import { DotPlot } from '../charts/DotPlot'
import { StatusMatrix, type MatrixState } from '../charts/StatusMatrix'
import { RangeBar } from '../charts/RangeBar'
import { LifespanBars } from '../charts/LifespanBars'
import { EstimateInterval, wilsonInterval } from '../charts/EstimateInterval'
import { Sparkline } from '../charts/Sparkline'
import { Waterfall } from '../charts/Waterfall'
import { seriesTone, thresholdTone, SERIES_ORDER } from '../charts/foundation'

/** Every chart names itself on the element carrying the role. */
function accessibleName(container: HTMLElement): string | null {
  const node = container.querySelector('[role="img"]')
  return node ? node.getAttribute('aria-label') : null
}

describe('chart foundation', () => {
  it('assigns series in fixed order and never invents a hue', () => {
    expect(SERIES_ORDER).toHaveLength(5)
    expect(seriesTone(0)).toBe('data-1')
    expect(seriesTone(4)).toBe('data-5')
    // Past the order the honest answer is the neutral, not a generated colour.
    expect(seriesTone(5)).toBe('data-neutral')
    expect(seriesTone(99)).toBe('data-neutral')
  })

  it('keeps the threshold ladder in one place', () => {
    expect(thresholdTone(10)).toBe('telemetry')
    expect(thresholdTone(80)).toBe('warning')
    expect(thresholdTone(95)).toBe('critical')
    expect(thresholdTone(NaN)).toBe('neutral')
  })
})

describe('SlopeChart', () => {
  const load = [
    { label: '1 min', value: 14.0 },
    { label: '5 min', value: 16.8 },
    { label: '15 min', value: 13.76 },
  ]

  it('joins the horizons and names every reading', () => {
    const { container } = render(<SlopeChart points={load} reference={20} referenceLabel="20 cores" />)
    expect(container.querySelector('.hb-slope__line')).toBeInTheDocument()
    expect(container.querySelectorAll('.hb-slope__node')).toHaveLength(3)
    expect(accessibleName(container)).toBe('1 min 14.0, 5 min 16.8, 15 min 13.8')
  })

  it('marks only the readings above the warning line', () => {
    const { container } = render(<SlopeChart points={load} warnAbove={16} />)
    expect(container.querySelectorAll('.hb-slope__node--warning')).toHaveLength(1)
  })

  it('says the sensor is dark rather than drawing a flat zero', () => {
    const { container } = render(<SlopeChart points={load} offline />)
    expect(accessibleName(container)).toBe('[Sensor offline]')
    expect(screen.getByText('SENSOR OFFLINE')).toBeInTheDocument()
    expect(container.querySelector('.hb-slope__line')).not.toBeInTheDocument()
  })
})

describe('DotPlot', () => {
  const vols = [
    { id: 'a', label: 'TimeMachine', value: 94 },
    { id: 'b', label: 'Root', value: 11 },
  ]

  it('places every peer on one shared axis', () => {
    const { container } = render(<DotPlot items={vols} />)
    expect(container.querySelectorAll('.hb-dotplot__dot')).toHaveLength(2)
    expect(accessibleName(container)).toBe('TimeMachine 94%, Root 11%')
  })

  it('takes its pigment from the threshold, not the series order', () => {
    const { container } = render(<DotPlot items={vols} />)
    expect(container.querySelector('.hb-dotplot__dot--critical')).toBeInTheDocument()
    expect(container.querySelector('.hb-dotplot__dot--telemetry')).toBeInTheDocument()
  })

  it('renders a peer with no reading as absent, not as zero', () => {
    const { container } = render(
      <DotPlot items={[{ id: 'x', label: 'GPU temp', value: 0, offline: true }]} />,
    )
    expect(screen.getByText('NO READING')).toBeInTheDocument()
    expect(container.querySelector('.hb-dotplot__dot')).not.toBeInTheDocument()
  })
})

describe('StatusMatrix', () => {
  const states: MatrixState[] = [
    { key: 'running', label: 'Running', tone: 'nominal' },
    { key: 'exited', label: 'Exited', tone: 'critical' },
  ]
  const items = [
    { id: '1', label: 'a.service', state: 'running' },
    { id: '2', label: 'b.service', state: 'running' },
    { id: '3', label: 'c.service', state: 'exited' },
  ]

  it('draws one mark per item and counts each state in the legend', () => {
    const { container } = render(<StatusMatrix items={items} states={states} />)
    expect(container.querySelectorAll('.hb-matrix__cell')).toHaveLength(3)
    expect(accessibleName(container)).toBe('3 items — 2 running, 1 exited')
    expect(screen.getByText('2')).toBeInTheDocument()
    expect(screen.getByText('1')).toBeInTheDocument()
  })

  it('omits states nothing is in, rather than showing a zero row', () => {
    const { container } = render(
      <StatusMatrix items={[items[0]]} states={states} />,
    )
    expect(container.querySelectorAll('.hb-matrix__legend li')).toHaveLength(1)
  })

  it('names each item on hover without drawing text on the mark', () => {
    const { container } = render(<StatusMatrix items={items} states={states} />)
    const cell = container.querySelector('.hb-matrix__cell')!
    expect(cell.querySelector('title')?.textContent).toBe('a.service — running')
    // the mark itself carries no rendered label
    expect(cell.tagName.toLowerCase()).toBe('rect')
  })
})

describe('RangeBar', () => {
  it('keeps all three scopes instead of collapsing to one ratio', () => {
    const { container } = render(<RangeBar total={128} ceiling={96} used={0.93} unit="GB" />)
    expect(accessibleName(container)).toBe(
      '0.9 GB in use of a 96.0 GB ceiling, within 128.0 GB total',
    )
    expect(container.querySelector('.hb-range__ceiling')).toBeInTheDocument()
    expect(container.querySelector('.hb-range__used')).toBeInTheDocument()
  })

  it('keeps a hairline of the used mark visible when the share is tiny', () => {
    const { container } = render(<RangeBar total={128} ceiling={96} used={0.01} />)
    const used = container.querySelector('.hb-range__used') as SVGRectElement
    expect(Number(used.getAttribute('width'))).toBeGreaterThan(0)
  })
})

describe('LifespanBars', () => {
  const now = 1_000_000
  const items = [
    { id: '1', label: 'samba', from: now - 900, to: now - 400 },
    { id: '2', label: 'share', from: now - 800, to: null },
  ]

  it('distinguishes a belief still held from one retired', () => {
    const { container } = render(<LifespanBars items={items} end={now} />)
    expect(container.querySelectorAll('.hb-lifespan__bar--open')).toHaveLength(1)
    expect(container.querySelectorAll('.hb-lifespan__bar--closed')).toHaveLength(1)
    expect(accessibleName(container)).toBe('2 beliefs, 1 still held, 1 retired')
  })

  it('caps a closed belief where it was retired', () => {
    const { container } = render(<LifespanBars items={items} end={now} />)
    expect(container.querySelectorAll('.hb-lifespan__cap')).toHaveLength(1)
  })
})

describe('EstimateInterval', () => {
  it('computes an interval that stays inside 0..1 at small n', () => {
    const [lo, hi] = wilsonInterval(6, 8)
    expect(lo).toBeGreaterThan(0)
    expect(hi).toBeLessThanOrEqual(1)
    // eight samples license almost nothing — the width is the whole point
    expect(hi - lo).toBeGreaterThan(0.4)
  })

  it('does not claim a range it cannot support at n = 0', () => {
    expect(wilsonInterval(0, 0)).toEqual([0, 1])
  })

  it('shows the estimate and its width together', () => {
    const { container } = render(<EstimateInterval successes={6} n={8} label="dismissal rate" />)
    expect(container.querySelector('.hb-estimate__point')).toBeInTheDocument()
    expect(container.querySelector('.hb-estimate__whisker')).toBeInTheDocument()
    expect(accessibleName(container)).toMatch(/^75% from 8 samples, plausible range/)
  })

  it('accepts a stricter interval from the caller', () => {
    const { container } = render(
      <EstimateInterval successes={6} n={8} low={0.35} high={0.97} />,
    )
    expect(accessibleName(container)).toBe('75% from 8 samples, plausible range 35% to 97%')
  })
})

describe('Sparkline', () => {
  it('draws the line and marks the newest sample', () => {
    const { container } = render(<Sparkline values={[1, 4, 2, 6]} aria-label="CPU" />)
    expect(container.querySelector('.hb-spark__line')).toBeInTheDocument()
    expect(container.querySelector('.hb-spark__end')).toBeInTheDocument()
  })

  it('refuses to fabricate a trend from no history', () => {
    const { container } = render(<Sparkline values={[]} empty />)
    expect(container.querySelector('.hb-spark__line')).not.toBeInTheDocument()
    expect(container.querySelector('.hb-spark__empty')).toBeInTheDocument()
    expect(accessibleName(container)).toBe('No history recorded yet')
  })

  it('treats a single sample as no trend', () => {
    const { container } = render(<Sparkline values={[42]} />)
    expect(container.querySelector('.hb-spark__line')).not.toBeInTheDocument()
  })
})

describe('Waterfall', () => {
  const stages = [
    { id: 'p', label: 'PLANNING', start: 0, duration: 0.7 },
    { id: 's', label: 'SEARCHING', start: 0.7, duration: 2.4 },
    { id: 'r', label: 'RESPONDING', start: 3.1, duration: 1.7 },
  ]

  it('names the stage that ate the time', () => {
    const { container } = render(<Waterfall stages={stages} />)
    expect(accessibleName(container)).toBe('4.8s total, longest stage SEARCHING at 2.4s')
    expect(container.querySelectorAll('.hb-waterfall__bar')).toHaveLength(3)
  })

  it('assigns stage pigments from the series order', () => {
    const { container } = render(<Waterfall stages={stages} />)
    expect(container.querySelector('.hb-waterfall__bar--data-1')).toBeInTheDocument()
    expect(container.querySelector('.hb-waterfall__bar--data-3')).toBeInTheDocument()
  })
})
