// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import * as React from 'react'
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { Button } from '../primitives/Button'
import { StatusBadge } from '../primitives/StatusBadge'
import { Input } from '../primitives/Input'
import { Select } from '../primitives/Select'
import { ParametricSlider } from '../primitives/ParametricSlider'
import { HalbertMark } from '../primitives/HalbertMark'

describe('Button', () => {
  it('does not fire while loading, and reports it as busy', async () => {
    const onClick = vi.fn()
    render(<Button loading onClick={onClick}>Apply</Button>)
    const button = screen.getByRole('button', { name: /apply/i })

    expect(button).toHaveAttribute('aria-busy', 'true')
    expect(button).toBeDisabled()

    await userEvent.click(button)
    expect(onClick).not.toHaveBeenCalled()
  })

  it('still blocks activation when asChild removes the disabled attribute', async () => {
    // asChild targets an <a>, which has no `disabled` — the guard must hold.
    const onClick = vi.fn()
    render(
      <Button asChild loading onClick={onClick}>
        <a href="#apply">Apply</a>
      </Button>,
    )
    const link = screen.getByRole('link', { name: /apply/i })
    expect(link).toHaveAttribute('aria-disabled', 'true')

    await userEvent.click(link)
    expect(onClick).not.toHaveBeenCalled()
  })

  it('merges className onto the child rather than replacing it', () => {
    render(
      <Button asChild className="from-parent">
        <a href="#x" className="from-child">Go</a>
      </Button>,
    )
    const link = screen.getByRole('link', { name: /go/i })
    expect(link).toHaveClass('from-child')
    expect(link).toHaveClass('hb-btn')
  })
})

describe('StatusBadge', () => {
  it('renders a text label, never colour alone', () => {
    render(<StatusBadge tone="critical">Critical</StatusBadge>)
    expect(screen.getByText('Critical')).toBeInTheDocument()
  })

  it('only becomes a live region when asked', () => {
    const { rerender } = render(<StatusBadge tone="nominal">Nominal</StatusBadge>)
    expect(screen.queryByRole('status')).not.toBeInTheDocument()

    rerender(<StatusBadge tone="nominal" live>Nominal</StatusBadge>)
    expect(screen.getByRole('status')).toBeInTheDocument()
  })
})

describe('Input', () => {
  it('associates its label, so it is reachable by accessible name', async () => {
    render(<Input label="ARC maximum" />)
    const input = screen.getByLabelText('ARC maximum')
    await userEvent.type(input, '48')
    expect(input).toHaveValue('48')
  })

  it('wires the hint through aria-describedby', () => {
    render(<Input label="Port" hint="Between 1024 and 65535" />)
    expect(screen.getByLabelText('Port')).toHaveAccessibleDescription('Between 1024 and 65535')
  })

  it('marks invalid and announces the error', () => {
    render(<Input label="Port" error="Port 22 is already bound" />)
    const input = screen.getByLabelText('Port')
    expect(input).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByRole('alert')).toHaveTextContent('Port 22 is already bound')
    expect(input).toHaveAccessibleDescription('Port 22 is already bound')
  })

  it('hides the label visually while keeping it for assistive tech', () => {
    render(<Input label="Search" hideLabel />)
    expect(screen.getByLabelText('Search')).toBeInTheDocument()
  })
})

describe('Select', () => {
  it('selects by visible option text', async () => {
    const onChange = vi.fn()
    render(
      <Select
        label="Voice"
        onChange={onChange}
        defaultValue="first_person"
        options={[
          { value: 'first_person', label: 'First person' },
          { value: 'the_computer', label: 'The computer' },
          { value: 'hybrid', label: 'Hybrid' },
        ]}
      />,
    )
    await userEvent.selectOptions(screen.getByLabelText('Voice'), 'hybrid')
    expect(onChange).toHaveBeenCalled()
    expect(screen.getByLabelText('Voice')).toHaveValue('hybrid')
  })
})

describe('ParametricSlider', () => {
  function Harness(props: Partial<React.ComponentProps<typeof ParametricSlider>> = {}) {
    const [value, setValue] = React.useState(48)
    return (
      <ParametricSlider
        label="ARC maximum"
        min={0}
        max={64}
        step={1}
        value={value}
        onValueChange={setValue}
        formatValue={(v) => `${v} GB`}
        ariaValueText={(v) => `${v} gigabytes, ${64 - v} gigabytes headroom`}
        preview={(v) => `${64 - v} GB left for everything else`}
        cautionAbove={56}
        {...props}
      />
    )
  }

  it('is a native range input, which is what makes it keyboard-operable', () => {
    // The keyboard contract (arrows, Home/End, PageUp/PageDown) is delegated to
    // the platform rather than reimplemented, so the meaningful assertion is
    // that we really did use a native range. jsdom does not implement arrow-key
    // stepping on range inputs — a bare <input type="range"> is unmoved by
    // {ArrowRight} there too — so simulating arrows here would test jsdom, not
    // this component.
    render(<Harness />)
    const slider = screen.getByLabelText('ARC maximum')
    expect(slider.tagName).toBe('INPUT')
    expect(slider).toHaveAttribute('type', 'range')
    expect(slider).toHaveAttribute('min', '0')
    expect(slider).toHaveAttribute('max', '64')
    expect(slider).toHaveAttribute('step', '1')
    expect(slider).not.toBeDisabled()
  })

  it('announces a meaningful value, not a bare number', () => {
    render(<Harness />)
    expect(screen.getByLabelText('ARC maximum')).toHaveAttribute(
      'aria-valuetext',
      '48 gigabytes, 16 gigabytes headroom',
    )
  })

  it('propagates changes and re-announces the new headroom', () => {
    render(<Harness />)
    const slider = screen.getByLabelText('ARC maximum')

    fireEvent.change(slider, { target: { value: '60' } })

    expect(slider).toHaveValue('60')
    expect(slider).toHaveAttribute('aria-valuetext', '60 gigabytes, 4 gigabytes headroom')
    expect(screen.getByText('4 GB left for everything else')).toBeInTheDocument()
  })

  it('describes the consequence, not just the number', () => {
    render(<Harness />)
    expect(screen.getByLabelText('ARC maximum')).toHaveAccessibleDescription(
      '16 GB left for everything else',
    )
  })

  it('does not make the preview a live region', () => {
    // It changes on every arrow keypress; a live region here would be a torrent.
    const { container } = render(<Harness />)
    expect(container.querySelector('[aria-live]')).toBeNull()
  })

  it('flags values past the caution threshold, and only past it', () => {
    const { container } = render(<Harness />)
    const root = container.querySelector('.hb-slider') as HTMLElement
    expect(root).not.toHaveClass('is-caution')

    fireEvent.change(screen.getByLabelText('ARC maximum'), { target: { value: '60' } })
    expect(root).toHaveClass('is-caution')
  })

  it('survives a zero-width range without producing NaN', () => {
    const { container } = render(<Harness min={10} max={10} value={10} />)
    const input = container.querySelector('.hb-slider__input') as HTMLElement
    expect(input.style.getPropertyValue('--hb-slider-pct')).toBe('0%')
  })
})

describe('HalbertMark', () => {
  it('renders with default size 48 and resolves auto density to medium', () => {
    const { container } = render(<HalbertMark data-testid="mark" />)
    const svg = container.querySelector('svg')
    expect(svg).toBeInTheDocument()
    expect(svg).toHaveAttribute('width', '48')
    expect(svg).toHaveAttribute('height', '48')
    expect(svg).toHaveClass('hb-mark--medium')
  })

  it('automatically scales density to small for icon sizes <= 24', () => {
    const { container } = render(<HalbertMark size={16} />)
    const svg = container.querySelector('svg')
    expect(svg).toHaveClass('hb-mark--small')
  })

  it('automatically scales density to display for sizes > 64', () => {
    const { container } = render(<HalbertMark size={128} />)
    const svg = container.querySelector('svg')
    expect(svg).toHaveClass('hb-mark--display')
  })

  it('respects explicit density override', () => {
    const { container } = render(<HalbertMark size={128} density="small" />)
    const svg = container.querySelector('svg')
    expect(svg).toHaveClass('hb-mark--small')
  })

  it('renders badge variant with background tile', () => {
    const { container } = render(<HalbertMark tone="badge" />)
    const rect = container.querySelector('rect')
    expect(rect).toBeInTheDocument()
    expect(rect).toHaveAttribute('fill', 'var(--color-accent, #D34E24)')
  })

  it('supports explicit line counts: 7 lines, 4 lines, 8 lines', () => {
    const { container: c7 } = render(<HalbertMark lines={7} />)
    expect(c7.querySelector('svg')).toHaveClass('hb-mark--7lines')

    const { container: c4 } = render(<HalbertMark lines={4} />)
    expect(c4.querySelector('svg')).toHaveClass('hb-mark--4lines')

    const { container: c8 } = render(<HalbertMark lines={8} />)
    expect(c8.querySelector('svg')).toHaveClass('hb-mark--8lines')
  })

  it('falls back to density/auto resolution when `lines` is not a supported count', () => {
    // The type only allows 3|4|5|6|7|8|10, but a caller crossing a JS boundary
    // (or a stale prop) could still hand us something else. resolveLineCount
    // must fall through to the density/auto branch rather than rendering
    // nothing, and that branch always returns a real key into
    // CONFIG_BY_LINE_COUNT — so this exercises the never-taken `|| CONFIG_BY_LINE_COUNT[6]`
    // fallback path deliberately, rather than removing it.
    const invalidLines = 9 as unknown as 7
    const { container } = render(<HalbertMark size={128} lines={invalidLines} />)
    const svg = container.querySelector('svg')
    expect(svg).toBeInTheDocument()
    expect(svg).toHaveClass('hb-mark--display')
  })
})

