// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import * as React from 'react'
import type { Meta, StoryObj } from '@storybook/react'

import { contrast, grade, GRADE_TONE, resolveToken, type Grade } from './contrast'

const meta: Meta = {
  title: 'Design Tokens/Overview',
  parameters: { layout: 'fullscreen', controls: { disable: true } },
}
export default meta

/* ----------------------------------------------------------------- shared -- */

function Section({ title, note, children }: { title: string; note?: string; children: React.ReactNode }) {
  return (
    <section style={{ marginBottom: 'var(--space-12)' }}>
      <h2 style={{ fontFamily: 'var(--font-display)', fontSize: 22, letterSpacing: 'var(--tracking-display)', margin: 0 }}>
        {title}
      </h2>
      {note && (
        <p style={{ color: 'var(--color-ink-secondary)', fontSize: 13, maxWidth: '68ch', marginTop: 'var(--space-2)' }}>
          {note}
        </p>
      )}
      <div style={{ marginTop: 'var(--space-4)' }}>{children}</div>
    </section>
  )
}

function useResolved(token: string): string {
  const [value, setValue] = React.useState('')
  React.useEffect(() => {
    // Re-read after paint so the theme decorator's attribute has landed.
    const id = requestAnimationFrame(() => setValue(resolveToken(token)))
    return () => cancelAnimationFrame(id)
  })
  return value
}

/* ------------------------------------------------------------- swatches --- */

function Swatch({ token }: { token: string }) {
  const value = useResolved(token)
  return (
    <div style={{ border: '1px solid var(--color-line)', borderRadius: 'var(--radius-md)', overflow: 'hidden' }}>
      <div style={{ background: `var(${token})`, height: 56 }} />
      <div style={{ padding: 'var(--space-2)', background: 'var(--color-surface)' }}>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--color-ink)' }}>{token}</div>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--color-ink-tertiary)' }}>
          {value || '—'}
        </div>
      </div>
    </div>
  )
}

function SwatchGrid({ tokens }: { tokens: string[] }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(190px, 1fr))', gap: 'var(--space-3)' }}>
      {tokens.map((token) => (
        <Swatch key={token} token={token} />
      ))}
    </div>
  )
}

export const ColorPalette: StoryObj = {
  render: () => (
    <>
      <Section
        title="Surfaces — the archival paper ramp"
        note="canvas is the page, surface is an elevated plate, surface-subtle is a recessed tray. surface-muted is a disabled ground: WCAG 1.4.3 exempts disabled controls, so nothing readable belongs on it."
      >
        <SwatchGrid tokens={['--color-canvas', '--color-surface', '--color-surface-subtle', '--color-surface-muted']} />
      </Section>

      <Section
        title="Ink"
        note="The universal text ramp. ink-ghost sits below the text floor deliberately — it is for disabled controls and decorative rules, never for text that must be read."
      >
        <SwatchGrid
          tokens={['--color-ink', '--color-ink-secondary', '--color-ink-tertiary', '--color-ink-ghost', '--color-ink-on-accent']}
        />
      </Section>

      <Section
        title="The letterpress stroke"
        note="accent is the identity: marks, rules, dots, and display type at 24px/700 or larger. accent-strong is the interactive shade — the one licensed for button fills and small accent text. The stroke you see is not the stroke you press."
      >
        <SwatchGrid
          tokens={['--color-accent', '--color-accent-strong', '--color-accent-hover', '--color-accent-active', '--color-accent-tint', '--color-focus-ring']}
        />
      </Section>

      <Section title="Telemetry" note="Four pigments, one meaning each. Never used for variety.">
        <SwatchGrid
          tokens={[
            '--color-status-nominal',
            '--color-status-warning',
            '--color-status-critical',
            '--color-status-telemetry',
          ]}
        />
      </Section>
    </>
  ),
}

/* -------------------------------------------------------------- contrast -- */

const INK_SURFACES = ['--color-canvas', '--color-surface', '--color-surface-subtle']
const ACCENT_SURFACES = ['--color-canvas', '--color-surface']

const CHECKS: Array<{ fg: string; grounds: string[]; floor: number; note: string }> = [
  { fg: '--color-ink', grounds: INK_SURFACES, floor: 7, note: 'body & headings' },
  { fg: '--color-ink-secondary', grounds: INK_SURFACES, floor: 7, note: 'prose & metadata' },
  { fg: '--color-ink-tertiary', grounds: INK_SURFACES, floor: 4.5, note: 'captions & labels' },
  { fg: '--color-ink-ghost', grounds: INK_SURFACES, floor: 3, note: 'non-text only' },
  { fg: '--color-accent', grounds: ACCENT_SURFACES, floor: 3, note: 'non-text mark' },
  { fg: '--color-accent-strong', grounds: ACCENT_SURFACES, floor: 4.5, note: 'fills & small accent text' },
  { fg: '--color-focus-ring', grounds: INK_SURFACES, floor: 3, note: 'focus ring' },
  { fg: '--color-status-nominal', grounds: [...ACCENT_SURFACES, '--color-status-nominal-bg'], floor: 4.5, note: 'nominal' },
  { fg: '--color-status-warning', grounds: [...ACCENT_SURFACES, '--color-status-warning-bg'], floor: 4.5, note: 'warning' },
  { fg: '--color-status-critical', grounds: [...ACCENT_SURFACES, '--color-status-critical-bg'], floor: 4.5, note: 'critical' },
  { fg: '--color-status-telemetry', grounds: [...ACCENT_SURFACES, '--color-status-telemetry-bg'], floor: 4.5, note: 'telemetry' },
  { fg: '--color-ink-on-accent', grounds: ['--color-accent-strong', '--color-accent-hover', '--color-accent-active'], floor: 4.5, note: 'text on a fill' },
]

function ContrastTable() {
  const [rows, setRows] = React.useState<Array<{ fg: string; bg: string; ratio: number; g: Grade; floor: number; note: string }>>([])

  React.useEffect(() => {
    const id = requestAnimationFrame(() => {
      const next = CHECKS.flatMap((check) =>
        check.grounds.map((bg) => {
          const ratio = contrast(resolveToken(check.fg), resolveToken(bg)) ?? 0
          return { fg: check.fg, bg, ratio, g: grade(ratio, check.floor), floor: check.floor, note: check.note }
        }),
      )
      setRows(next)
    })
    return () => cancelAnimationFrame(id)
  })

  const failures = rows.filter((r) => r.g === 'FAIL').length
  const short = (t: string) => t.replace('--color-', '')

  return (
    <>
      <p
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 12,
          color: failures ? 'var(--color-status-critical)' : 'var(--color-status-nominal)',
        }}
      >
        {failures
          ? `${failures} pair(s) below their floor — this must be zero`
          : `All ${rows.length} licensed pairs clear their floor in this theme.`}
      </p>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ borderCollapse: 'collapse', fontFamily: 'var(--font-mono)', fontSize: 11, width: '100%' }}>
          <thead>
            <tr style={{ textAlign: 'left', color: 'var(--color-ink-tertiary)' }}>
              {['foreground', 'on ground', 'ratio', 'floor', 'grade', 'role'].map((h) => (
                <th key={h} style={{ padding: 'var(--space-2)', borderBottom: '1px solid var(--color-line)', fontWeight: 600 }}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i} style={{ color: 'var(--color-ink-secondary)' }}>
                <td style={{ padding: 'var(--space-2)', borderBottom: '1px solid var(--color-line-subtle)' }}>{short(row.fg)}</td>
                <td style={{ padding: 'var(--space-2)', borderBottom: '1px solid var(--color-line-subtle)' }}>{short(row.bg)}</td>
                <td style={{ padding: 'var(--space-2)', borderBottom: '1px solid var(--color-line-subtle)', color: 'var(--color-ink)' }}>
                  {row.ratio.toFixed(2)}:1
                </td>
                <td style={{ padding: 'var(--space-2)', borderBottom: '1px solid var(--color-line-subtle)' }}>{row.floor}:1</td>
                <td style={{ padding: 'var(--space-2)', borderBottom: '1px solid var(--color-line-subtle)', color: GRADE_TONE[row.g], fontWeight: 600 }}>
                  {row.g}
                </td>
                <td style={{ padding: 'var(--space-2)', borderBottom: '1px solid var(--color-line-subtle)', color: 'var(--color-ink-tertiary)' }}>
                  {row.note}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}

export const ContrastAudit: StoryObj = {
  name: 'Contrast Audit (live)',
  render: () => (
    <Section
      title="Contrast audit"
      note="Computed in the browser from the resolved tokens, so it reflects what the cascade actually produced rather than what the source file says. Flip the Theme toolbar to audit dark. Each token is checked only against the grounds it is licensed for — contrast is a property of a pair, not of a colour. This mirrors scripts/check_contrast.py, which gates CI."
    >
      <ContrastTable />
    </Section>
  ),
}

/* ------------------------------------------------------------ typography -- */

export const Typography: StoryObj = {
  render: () => (
    <>
      <Section title="Fraunces — display" note="Headings and the machine's voice at rest. Never body copy, never under ~18px.">
        <p style={{ fontFamily: 'var(--font-display)', fontSize: 36, letterSpacing: 'var(--tracking-display)', margin: 0 }}>
          I am the machine.
        </p>
      </Section>

      <Section title="Space Grotesk — sans" note="UI chrome, body copy, labels, buttons.">
        <p style={{ fontFamily: 'var(--font-sans)', fontSize: 15, maxWidth: '60ch', margin: 0 }}>
          I checked my configuration and I am currently mounted with background_compression=none.
        </p>
      </Section>

      <Section
        title="JetBrains Mono — telemetry"
        note="All numbers, paths, commands, timestamps, and identifiers. Tabular figures are the point: a vitals plate updating every second must not reflow."
      >
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 15, fontVariantNumeric: 'tabular-nums' }}>
          <div>45°C · load 0.15 · 18.2 GB / 64.0 GB</div>
          <div style={{ color: 'var(--color-ink-tertiary)', fontSize: 12, marginTop: 4 }}>
            /etc/ssh/sshd_config.d/50-custom.conf:3
          </div>
        </div>
      </Section>

      <Section title="Micro-labels" note="Mono, uppercase, tracked, tertiary ink — the engraved legend on an instrument panel.">
        <div
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 10,
            textTransform: 'uppercase',
            letterSpacing: 'var(--tracking-label)',
            color: 'var(--color-ink-tertiary)',
          }}
        >
          CPU temp · Load avg · Uptime
        </div>
      </Section>
    </>
  ),
}

/* ------------------------------------------------------------- elevation -- */

export const ElevationAndHairlines: StoryObj = {
  name: 'Elevation & Hairlines',
  render: () => (
    <Section
      title="Elevation & hairlines"
      note="Plates are lifted by shadow; trays are recessed by fill and hairline, never by an inset shadow. Decorative hairlines are intentionally below 3:1 — a plate is identified by its fill and shadow too, and a 3:1 border would read as a heavy rule."
    >
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 'var(--space-4)' }}>
        {(['--shadow-subtle', '--shadow-plate', '--shadow-popover'] as const).map((token) => (
          <div
            key={token}
            style={{
              background: 'var(--color-surface)',
              border: '1px solid var(--color-line)',
              borderRadius: 'var(--radius-lg)',
              boxShadow: `var(${token})`,
              padding: 'var(--space-4)',
              fontFamily: 'var(--font-mono)',
              fontSize: 11,
            }}
          >
            {token}
          </div>
        ))}
      </div>

      <div style={{ marginTop: 'var(--space-6)', display: 'grid', gap: 'var(--space-2)' }}>
        {(['--color-line-subtle', '--color-line', '--color-line-strong'] as const).map((token) => (
          <div key={token} style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--color-ink-tertiary)', width: 170 }}>
              {token}
            </span>
            <span style={{ flex: 1, height: 1, background: `var(${token})` }} />
          </div>
        ))}
      </div>
    </Section>
  ),
}
