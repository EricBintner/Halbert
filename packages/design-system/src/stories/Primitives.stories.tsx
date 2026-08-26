// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import * as React from 'react'
import type { Meta, StoryObj } from '@storybook/react'

import { Button } from '../primitives/Button'
import { StatusBadge } from '../primitives/StatusBadge'
import { Input } from '../primitives/Input'
import { Select } from '../primitives/Select'
import { ParametricSlider } from '../primitives/ParametricSlider'

const Row = ({ children }: { children: React.ReactNode }) => (
  <div style={{ display: 'flex', gap: 'var(--space-3)', alignItems: 'center', flexWrap: 'wrap' }}>{children}</div>
)

const Note = ({ children }: { children: React.ReactNode }) => (
  <p style={{ color: 'var(--color-ink-secondary)', fontSize: 13, maxWidth: '68ch', marginTop: 0 }}>{children}</p>
)

/* ---------------------------------------------------------------- Button -- */

const buttonMeta: Meta<typeof Button> = {
  title: 'Primitives/Button',
  component: Button,
  args: { children: 'Run SMART test', variant: 'primary', size: 'md' },
  argTypes: {
    variant: { control: 'select', options: ['primary', 'outline', 'ghost', 'danger'] },
    size: { control: 'select', options: ['sm', 'md', 'lg'] },
  },
}
export default buttonMeta

export const Playground: StoryObj<typeof Button> = {}

export const Variants: StoryObj = {
  render: () => (
    <>
      <Note>
        <strong>primary</strong> fills with <code>--color-accent-strong</code>, not{' '}
        <code>--color-accent</code>. The brand shade measures 4.30:1 under white and fails AA as a
        text-bearing fill. <strong>danger</strong> is a different red on purpose: vermilion means
        &ldquo;act&rdquo;, critical means &ldquo;something is wrong&rdquo;, and a vermilion delete
        button reads as encouragement.
      </Note>
      <Row>
        <Button variant="primary">Apply change</Button>
        <Button variant="outline">Preview diff</Button>
        <Button variant="ghost">Dismiss</Button>
        <Button variant="danger">Destroy snapshot</Button>
      </Row>
    </>
  ),
}

export const Sizes: StoryObj = {
  render: () => (
    <Row>
      <Button size="sm">Small</Button>
      <Button size="md">Medium</Button>
      <Button size="lg">Large</Button>
    </Row>
  ),
}

export const LoadingAndDisabled: StoryObj = {
  name: 'Loading & disabled',
  render: () => (
    <>
      <Note>
        A loading button reports <code>aria-busy</code> and refuses activation. The guard is in the
        click handler rather than relying on the <code>disabled</code> attribute, so it still holds
        when <code>asChild</code> targets an anchor that has no such attribute.
      </Note>
      <Row>
        <Button variant="primary" loading>
          Applying
        </Button>
        <Button variant="outline" loading>
          Scanning
        </Button>
        <Button variant="primary" disabled>
          Unavailable
        </Button>
        <Button asChild variant="outline">
          <a href="#somewhere">As a link (asChild)</a>
        </Button>
      </Row>
    </>
  ),
}

/* ----------------------------------------------------------- StatusBadge -- */

export const Badges: StoryObj = {
  name: 'StatusBadge/Tones',
  render: () => (
    <>
      <Note>
        Every pill carries a text label as well as a colour. Colour alone fails WCAG 1.4.1 — a pill
        that only turns amber has told a colourblind reader nothing.
      </Note>
      <Row>
        <StatusBadge tone="nominal">Nominal</StatusBadge>
        <StatusBadge tone="warning">Degraded</StatusBadge>
        <StatusBadge tone="critical">Failing</StatusBadge>
        <StatusBadge tone="telemetry">3 found</StatusBadge>
        <StatusBadge tone="neutral">Idle</StatusBadge>
      </Row>
    </>
  ),
}

/* ------------------------------------------------------------ Form fields -- */

export const FormFields: StoryObj = {
  name: 'Input & Select',
  render: () => (
    <div style={{ display: 'grid', gap: 'var(--space-5)', maxWidth: 380 }}>
      <Note>
        A label is required, and a placeholder is not a label: it disappears on focus, fails 3.3.2,
        and the ghost ink it would use is not licensed for readable text.
      </Note>
      <Input label="SSH port" mono defaultValue="2222" hint="Between 1024 and 65535" />
      <Input label="Snapshot name" defaultValue="SNAP-20260714-02" error="A snapshot by that name already exists" />
      <Input label="Disabled field" defaultValue="unavailable" disabled />
      <Select
        label="Voice"
        defaultValue="first_person"
        hint="How this machine refers to itself"
        options={[
          { value: 'first_person', label: 'First person — "I am the machine"' },
          { value: 'the_computer', label: 'The computer — "this system"' },
          { value: 'hybrid', label: 'Hybrid' },
        ]}
      />
    </div>
  ),
}

/* ------------------------------------------------------ ParametricSlider -- */

function ArcSlider() {
  const [gb, setGb] = React.useState(48)
  const total = 64
  return (
    <ParametricSlider
      label="ZFS ARC maximum"
      min={4}
      max={total}
      step={1}
      value={gb}
      onValueChange={setGb}
      cautionAbove={total - 8}
      formatValue={(v) => `${v} GB`}
      ariaValueText={(v) => `${v} gigabytes, ${total - v} gigabytes headroom`}
      preview={(v) =>
        total - v < 8
          ? `only ${total - v} GB left for everything else — too tight`
          : `${total - v} GB left for everything else`
      }
    />
  )
}

function SwappinessSlider() {
  const [value, setValue] = React.useState(10)
  return (
    <ParametricSlider
      label="Swappiness"
      min={0}
      max={100}
      step={5}
      value={value}
      onValueChange={setValue}
      cautionAbove={60}
      formatValue={(v) => String(v)}
      ariaValueText={(v) => `${v} of 100`}
      preview={(v) => (v <= 10 ? 'swap only under real pressure' : v >= 60 ? 'swaps eagerly — expect disk churn' : 'balanced')}
    />
  )
}

export const Sliders: StoryObj = {
  name: 'ParametricSlider',
  render: () => (
    <div style={{ display: 'grid', gap: 'var(--space-8)', maxWidth: 420 }}>
      <Note>
        The parametric half is the preview line: the control shows what the setting <em>does</em>, not
        just what it is. It is a native <code>&lt;input type=&quot;range&quot;&gt;</code>, so arrows,
        Home/End and PageUp/PageDown work without being reimplemented — and the preview is
        deliberately not a live region, since it changes on every keypress.
      </Note>
      <ArcSlider />
      <SwappinessSlider />
    </div>
  ),
}
