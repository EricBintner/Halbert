// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import * as React from 'react'
import type { Meta, StoryObj } from '@storybook/react'

import { TactileMeter } from '../primitives/TactileMeter'
import { SegmentedBar } from '../primitives/SegmentedBar'
import { SlopeChart } from '../charts/SlopeChart'
import { DotPlot } from '../charts/DotPlot'
import { StatusMatrix, type MatrixItem, type MatrixState } from '../charts/StatusMatrix'
import { RangeBar } from '../charts/RangeBar'
import { LifespanBars, type Lifespan } from '../charts/LifespanBars'
import { EstimateInterval } from '../charts/EstimateInterval'
import { Sparkline } from '../charts/Sparkline'
import { Waterfall } from '../charts/Waterfall'

const meta: Meta = {
  title: 'Instruments/Vocabulary',
  tags: ['autodocs'],
  parameters: {
    layout: 'fullscreen',
    docs: {
      description: {
        component:
          'One form per data job. Every figure below uses a real reading from the machine ' +
          'this design system was built on, except where a plate says the telemetry is not ' +
          'collected yet. Before adding a chart, check its job is not already covered here.',
      },
    },
  },
}
export default meta

// ── shared chrome ───────────────────────────────────────────────────────────

const Page = ({ children }: { children: React.ReactNode }) => (
  <div
    style={{
      background: 'var(--color-canvas)',
      minHeight: '100%',
      padding: 'var(--space-6) var(--space-4)',
      fontFamily: 'var(--font-sans)',
    }}
  >
    <div style={{ maxWidth: 1100, margin: '0 auto', display: 'grid', gap: 'var(--space-4)' }}>
      {children}
    </div>
  </div>
)

const Grid = ({ children }: { children: React.ReactNode }) => (
  <div
    style={{
      display: 'grid',
      gridTemplateColumns: 'repeat(auto-fit, minmax(330px, 1fr))',
      gap: 'var(--space-4)',
    }}
  >
    {children}
  </div>
)

type Readiness = 'live' | 'needs-collection' | 'blocked'

const READINESS: Record<Readiness, { text: string; token: string }> = {
  live: { text: 'DATA LIVE', token: 'var(--color-status-nominal)' },
  'needs-collection': { text: 'NEEDS COLLECTION', token: 'var(--color-status-warning)' },
  blocked: { text: 'BLOCKED', token: 'var(--color-status-critical)' },
}

const Plate = ({
  job,
  name,
  why,
  readiness,
  note,
  children,
}: {
  job: string
  name: string
  why: string
  readiness: Readiness
  note?: string
  children: React.ReactNode
}) => {
  const r = READINESS[readiness]
  return (
    <section
      style={{
        background: 'var(--color-surface)',
        border: '1px solid var(--color-line)',
        borderRadius: 'var(--radius-md)',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
      }}
    >
      <header style={{ padding: 'var(--space-4) var(--space-4) var(--space-3)' }}>
        <div
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 10,
            letterSpacing: '.13em',
            textTransform: 'uppercase',
            color: 'var(--color-ink-tertiary)',
          }}
        >
          {job}
        </div>
        <h3
          style={{
            margin: '5px 0 6px',
            fontFamily: 'var(--font-sans)',
            fontSize: 17,
            fontWeight: 600,
            color: 'var(--color-ink)',
          }}
        >
          {name}
        </h3>
        <p style={{ margin: 0, fontSize: 13.5, lineHeight: 1.5, color: 'var(--color-ink-secondary)' }}>
          {why}
        </p>
      </header>

      <div
        style={{
          background: 'var(--color-surface-subtle)',
          borderBlock: '1px solid var(--color-line)',
          padding: 'var(--space-4)',
          flex: 1,
          display: 'flex',
          alignItems: 'center',
        }}
      >
        <div style={{ width: '100%', minWidth: 0 }}>{children}</div>
      </div>

      <footer
        style={{
          padding: 'var(--space-3) var(--space-4)',
          display: 'flex',
          gap: 'var(--space-3)',
          alignItems: 'center',
          flexWrap: 'wrap',
        }}
      >
        <span
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 10,
            letterSpacing: '.08em',
            padding: '3px 8px',
            borderRadius: 3,
            border: `1px solid ${r.token}`,
            color: r.token,
          }}
        >
          {r.text}
        </span>
        {note && (
          <span style={{ fontSize: 12.5, color: 'var(--color-ink-tertiary)' }}>{note}</span>
        )}
      </footer>
    </section>
  )
}

// ── real readings ───────────────────────────────────────────────────────────

const VOLUMES = [
  { id: 'tm', label: 'TimeMachine', value: 94 },
  { id: 'data', label: 'Data', value: 93 },
  { id: 'llm', label: 'LLM_Models', value: 81 },
  { id: 'bad', label: '4TB-BAD', value: 73 },
  { id: 'tb', label: 'Thunderbolt', value: 29 },
  { id: 'root', label: 'Root', value: 11 },
  { id: 'spin', label: 'SpinningDisks', value: 7 },
]

/**
 * Three buckets, not six.
 *
 * The live `status` field mixes run state with enable mode — "Manual start"
 * and "Keep-alive enabled" say how a service is configured, not whether it is
 * up. Encoding both here would spend six pigments on two different questions
 * and bury the one that matters. Enable mode belongs in the table beside this.
 *
 * The emphasis is deliberate: benign states stay quiet so the single failure
 * is the only saturated mark on screen.
 */
const SERVICE_STATES: MatrixState[] = [
  { key: 'running', label: 'Running', tone: 'nominal' },
  { key: 'stopped', label: 'Not running', tone: 'neutral' },
  { key: 'exited', label: 'Exited non-zero', tone: 'critical' },
]

const SERVICES: MatrixItem[] = (() => {
  const plan: Array<[string, number]> = [
    ['running', 41],
    ['stopped', 51],
    ['exited', 1],
  ]
  const out: MatrixItem[] = []
  plan.forEach(([state, n]) => {
    for (let i = 0; i < n; i++) {
      out.push({ id: `${state}-${i}`, label: `${state}.service ${i + 1}`, state })
    }
  })
  // interleave so the one failure is not parked in a corner
  return out
    .map((v, i) => ({ v, k: (i * 37) % out.length }))
    .sort((a, b) => a.k - b.k)
    .map(({ v }) => v)
})()

const NOW = 1_787_800_000
const BELIEFS: Lifespan[] = [
  { id: 'b1', label: 'samba', from: NOW - 86400 * 9, to: NOW - 86400 * 5 },
  { id: 'b2', label: 'share', from: NOW - 86400 * 8, to: null },
  { id: 'b3', label: 'nvme0n1', from: NOW - 86400 * 7, to: null },
  { id: 'b4', label: 'frigate', from: NOW - 86400 * 6, to: NOW - 86400 * 2 },
  { id: 'b5', label: 'ollama', from: NOW - 86400 * 4, to: null },
  { id: 'b6', label: 'timemachine', from: NOW - 86400 * 3, to: NOW - 86400 * 1 },
]

const CPU_HISTORY = [
  18, 22, 19, 26, 31, 24, 20, 23, 29, 41, 38, 27, 24, 21, 25, 33, 46, 39, 30, 27,
  25, 22, 26, 34, 29, 24, 21, 19, 23, 27,
]

// ── the catalogue ───────────────────────────────────────────────────────────

export const TheVocabulary: StoryObj = {
  name: 'The vocabulary',
  render: () => (
    <Page>
      <header>
        <h2
          style={{
            margin: 0,
            fontFamily: 'var(--font-sans)',
            fontSize: 24,
            fontWeight: 700,
            letterSpacing: '-0.02em',
            color: 'var(--color-ink)',
          }}
        >
          One form per data job
        </h2>
        <p
          style={{
            margin: '8px 0 0',
            maxWidth: '62ch',
            fontSize: 15,
            lineHeight: 1.6,
            color: 'var(--color-ink-secondary)',
          }}
        >
          Two families. What the machine measures is the operating system&rsquo;s data, and any
          monitor could show it. What the machine does is Halbert&rsquo;s alone, and none of it
          reached a surface before this vocabulary existed.
        </p>
      </header>

      <h3 style={{ fontFamily: 'var(--font-mono)', fontSize: 11, letterSpacing: '.14em',
                   textTransform: 'uppercase', color: 'var(--color-ink-tertiary)', margin: '12px 0 0' }}>
        Family A · what the machine measures
      </h3>

      <Grid>
        <Plate
          job="Ratio against a limit"
          name="Meter"
          why="One number, one ceiling. The bar earns its place here and, by default, nowhere else."
          readiness="live"
          note="LLM_Models"
        >
          <TactileMeter value={81} tone="auto" size="thick" ticks={[25, 50, 75, 90]}
                        aria-label="LLM_Models capacity" />
        </Plate>

        <Plate
          job="Parts of one whole"
          name="Allocation bar"
          why="Quantities that sum to a known total, where the total is the point."
          readiness="live"
          note="Document index"
        >
          <SegmentedBar
            segments={[
              { id: 'self', label: 'Self-knowledge', value: 294, tone: 'data-1' },
              { id: 'disc', label: 'Discoveries', value: 132, tone: 'data-3' },
            ]}
            total={426}
            unit="docs"
            size="thick"
            showFreeHeadroom={false}
            aria-label="Document index by collection"
          />
        </Plate>

        <Plate
          job="One measure across peers"
          name="Dot plot"
          why="Seven volumes on one axis. As seven stacked meters the comparison costs you seven numbers; here it is free."
          readiness="live"
          note="Pairs with the meter, does not replace it"
        >
          <DotPlot items={VOLUMES} unit="%" />
        </Plate>

        <Plate
          job="Many items, few states"
          name="Status matrix"
          why="A run state is not a magnitude. Ninety-three services answer 'is anything wrong' before you read a word — one saturated mark, and it is the one that failed."
          readiness="blocked"
          note="service.status is free text with the PID inside"
        >
          <StatusMatrix items={SERVICES} states={SERVICE_STATES} />
        </Plate>

        <Plate
          job="Direction across horizons"
          name="Slope"
          why="Load average arrives as three numbers. Only the join says whether the machine is climbing or recovering."
          readiness="live"
          note="14.00 / 16.80 / 13.76 against 20 cores"
        >
          <SlopeChart
            points={[
              { label: '1 min', value: 14.0 },
              { label: '5 min', value: 16.8 },
              { label: '15 min', value: 13.76 },
            ]}
            reference={20}
            referenceLabel="20 cores"
            warnAbove={16}
            digits={1}
          />
        </Plate>

        <Plate
          job="A scope inside a scope"
          name="Range bar"
          why="128 GB of unified memory, of which the GPU may address 96, of which it uses 0.93. A flat meter reads 0.7% and loses the 96."
          readiness="live"
          note="Apple M1 Ultra"
        >
          <RangeBar
            total={128}
            ceiling={96}
            used={0.93}
            unit="GB"
            caption="Apple M1 Ultra · unified"
          />
        </Plate>
      </Grid>

      <h3 style={{ fontFamily: 'var(--font-mono)', fontSize: 11, letterSpacing: '.14em',
                   textTransform: 'uppercase', color: 'var(--color-ink-tertiary)', margin: '20px 0 0' }}>
        Family B · what the machine does
      </h3>

      <Grid>
        <Plate
          job="Facts with lifespans"
          name="Lifespan bars"
          why="The state ledger stores every belief with a validity window, so a belief is an interval. Open bars are still held."
          readiness="live"
          note="444 live triples, 4,002 retired"
        >
          <LifespanBars items={BELIEFS} end={NOW} />
        </Plate>

        <Plate
          job="Estimate from a small sample"
          name="Dot with interval"
          why="Six dismissals of eight is 75% — and drawn as a bar it reads as a measurement. The whisker is what eight samples license."
          readiness="live"
          note="Guards ATN-3 from acting on noise"
        >
          <EstimateInterval
            successes={6}
            n={8}
            label="dismissal rate"
            threshold={0.5}
            thresholdLabel="coin flip"
          />
        </Plate>

        <Plate
          job="Instance through stages"
          name="Waterfall"
          why="The only useful question about a slow turn is which stage ate the seconds. Consecutive stages need a shared clock."
          readiness="needs-collection"
          note="Stage entry/exit not stamped yet"
        >
          <Waterfall
            stages={[
              { id: 'plan', label: 'PLANNING', start: 0, duration: 0.7 },
              { id: 'search', label: 'SEARCHING', start: 0.7, duration: 2.4 },
              { id: 'read', label: 'READING', start: 3.1, duration: 0.9 },
              { id: 'exec', label: 'EXECUTING', start: 4.0, duration: 0.5 },
              { id: 'resp', label: 'RESPONDING', start: 4.5, duration: 1.7 },
            ]}
          />
        </Plate>

        <Plate
          job="Measure over time"
          name="Sparkline"
          why="The reading says what it is; the line says whether it is climbing. Neither is much use alone."
          readiness="needs-collection"
          note="/api/status returns instants — needs a ring buffer"
        >
          <div style={{ display: 'grid', gap: 'var(--space-3)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-4)' }}>
              <div style={{ minWidth: 92 }}>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10,
                              color: 'var(--color-ink-tertiary)', letterSpacing: '.1em' }}>CPU</div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 21, fontWeight: 700,
                              color: 'var(--color-ink)' }}>26.7%</div>
              </div>
              <Sparkline values={CPU_HISTORY} tone="data-1" aria-label="CPU over the last minute" />
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-4)' }}>
              <div style={{ minWidth: 92 }}>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10,
                              color: 'var(--color-ink-tertiary)', letterSpacing: '.1em' }}>GPU</div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 21, fontWeight: 700,
                              color: 'var(--color-ink)' }}>0%</div>
              </div>
              <Sparkline values={[]} empty tone="data-3" aria-label="No GPU history recorded yet" />
            </div>
          </div>
        </Plate>
      </Grid>
    </Page>
  ),
}

export const NotACharts: StoryObj = {
  name: 'When it is not a chart',
  render: () => (
    <Page>
      <header>
        <h2 style={{ margin: 0, fontFamily: 'var(--font-sans)', fontSize: 22, fontWeight: 700,
                     color: 'var(--color-ink)' }}>
          Two answers that are not charts
        </h2>
        <p style={{ margin: '8px 0 0', maxWidth: '62ch', fontSize: 15, lineHeight: 1.6,
                    color: 'var(--color-ink-secondary)' }}>
          Nobody opens the app inventory asking which app is biggest. They open it looking for one
          row. Charting an inventory is how a dashboard ends up with forty bars nobody reads.
        </p>
      </header>
      <Grid>
        <Plate
          job="Inventory with attributes"
          name="Table"
          why="38 scriptable apps, 172 formulas, 20 interfaces. Sorted, filterable, with state chips in it."
          readiness="live"
          note="Deliberately not a chart"
        >
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--color-ink-secondary)' }}>
            {[
              ['en0', '192.168.86.22', 'up'],
              ['lo0', '127.0.0.1', 'up'],
              ['en1', '—', 'down'],
              ['bridge0', '—', 'down'],
            ].map(([n, a, s]) => (
              <div
                key={n}
                style={{
                  display: 'grid',
                  gridTemplateColumns: '1fr 1fr auto',
                  gap: 'var(--space-3)',
                  padding: '6px 0',
                  borderBottom: '1px solid var(--color-line)',
                  alignItems: 'center',
                }}
              >
                <span style={{ color: 'var(--color-ink)' }}>{n}</span>
                <span>{a}</span>
                <span
                  style={{
                    width: 7,
                    height: 7,
                    borderRadius: '50%',
                    background:
                      s === 'up' ? 'var(--color-status-nominal)' : 'var(--color-data-neutral)',
                  }}
                  aria-label={s}
                />
              </div>
            ))}
          </div>
        </Plate>

        <Plate
          job="A single fact"
          name="Stat tile"
          why="Uptime, core count, TOPS. A one-bar bar chart is a worse way to print a number."
          readiness="live"
          note="Deliberately not a chart"
        >
          <div style={{ display: 'flex', gap: 'var(--space-6)', flexWrap: 'wrap' }}>
            {[
              ['UPTIME', '8.8', 'days'],
              ['GPU CORES', '48', ''],
              ['NEURAL ENGINE', '22', 'TOPS'],
            ].map(([k, v, u]) => (
              <div key={k}>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '.1em',
                              color: 'var(--color-ink-tertiary)' }}>{k}</div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 26, fontWeight: 700,
                              color: 'var(--color-ink)', lineHeight: 1.1 }}>
                  {v}
                  {u && (
                    <span style={{ fontSize: 12, fontWeight: 500, marginLeft: 4,
                                   color: 'var(--color-ink-secondary)' }}>{u}</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </Plate>
      </Grid>
    </Page>
  ),
}
