# Chart Vocabulary Wiring — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Put the first two chart primitives onto live product surfaces, replacing two places where a trend is currently drawn as a ratio.

**Architecture:** Slice 1 is frontend-only. Both charts consume data the API already returns, so no scanner, route or schema changes. `SlopeChart` replaces the Load meter in `HostVitals`; `DotPlot` goes above the per-volume meters on the Storage page as an overview. The per-volume meters stay — the dot plot answers "which is fullest", the meters answer "how full is this one".

**Tech Stack:** React 18, TypeScript, Vitest + Testing Library, `@halbert/design-system` (workspace-linked).

---

## Validation of the prior build order

The build order proposed in `Instruments/Vocabulary` was checked against the code. Two items were wrong and are corrected here.

| Claim | Verdict | Evidence |
|---|---|---|
| SlopeChart needs no backend work | **Confirmed** | `/api/identity` (`routes/system.py:253`) returns `load_average` with all three horizons; `useHostIdentity.ts:51` types it; `HostVitals.tsx:101` already receives it |
| DotPlot needs no backend work | **Confirmed** | `deduplicateFilesystems()` (`Storage.tsx:439`) already produces `{label, percent}` per volume |
| RangeBar needs no backend work | **Confirmed** | GPU discovery carries `unified_memory_gb`, `gpu_memory_ceiling_gb`, `gpu_memory_in_use_gb` |
| LifespanBars needs no backend work | **WRONG** | `/api/state/history` (`routes/state.py:81`) requires a `subject` query param and returns one key's history. No listing endpoint exists. Needs a new route — moved out of slice 1 |
| `percpu=True` is one keyword argument | **WRONG** | `_cpu_percent()` (`routes/system.py:219`) carries per-thread priming state (`_cpu_primed_threads`). psutil keeps a separate accumulator for the per-core call, so it needs its own primed wrapper — roughly 10 lines, not one |
| StatusMatrix is blocked on a status enum | **Confirmed, and now specified** | Two scanner paths write `status`: `launchd.py:76-84` emits real run state (Exit code / Not running / Running (PID n)); `launchd.py:166-180` emits *enable mode* (Disabled / Keep-alive / Runs at load / Manual start). They answer different questions and share one field |

**The finding that changes the ordering:** `HostVitals.tsx:101-105` is the vocabulary's thesis sitting in production —

```tsx
<Meter
  label="Load"
  percent={cpu.cores ? (load['1min'] / cpu.cores) * 100 : 0}
  detail={`${load['1min'].toFixed(2)} ${load['5min'].toFixed(2)} ${load['15min'].toFixed(2)}`}
/>
```

Three horizons collapsed into a ratio of the first, with the other two printed as a string. That makes Task 1 both the cheapest change and the most persuasive one.

---

## File structure

| File | Responsibility |
|---|---|
| `halbert_core/halbert_core/dashboard/frontend/src/components/shell/HostVitals.tsx` | Modify: Load meter → `SlopeChart` |
| `halbert_core/halbert_core/dashboard/frontend/src/components/shell/HostVitals.test.tsx` | Create: pins that all three horizons render |
| `halbert_core/halbert_core/dashboard/frontend/src/pages/Storage.tsx` | Modify: add `DotPlot` overview above the volume list |
| `halbert_core/halbert_core/dashboard/frontend/src/pages/Storage.dotplot.test.tsx` | Create: pins the overview against the summary counts |

`packages/design-system` is **not** modified — both components shipped in `5b311ac5`.

---

### Task 1: Load slope in HostVitals

**Files:**
- Modify: `halbert_core/halbert_core/dashboard/frontend/src/components/shell/HostVitals.tsx:100-105`
- Test: `halbert_core/halbert_core/dashboard/frontend/src/components/shell/HostVitals.test.tsx` (create)

- [ ] **Step 1: Write the failing test**

Create `halbert_core/halbert_core/dashboard/frontend/src/components/shell/HostVitals.test.tsx`:

```tsx
// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'

import { HostVitals } from './HostVitals'

const IDENTITY = {
  display_name: 'Macky-Mac',
  hostname: 'macky-mac',
  all_healthy: true,
  os: { pretty: 'macOS 26.5.1', kernel: 'Darwin 25.5.0', arch: 'arm64' },
  cpu: { percent: 26.7, cores: 20, temperature: null },
  memory: { percent: 29.1, used_gb: 37.2, total_gb: 128 },
  storage: { pools: [] },
  uptime: { human: '8 days', seconds: 764166 },
  load_average: { '1min': 14.0, '5min': 16.8, '15min': 13.76 },
}

beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response(JSON.stringify(IDENTITY), { status: 200 })),
  )
})
afterEach(() => {
  vi.unstubAllGlobals()
})

describe('HostVitals load reading', () => {
  it('draws all three horizons, not a ratio of the first', async () => {
    const { container } = render(<HostVitals />)

    // The slope names every reading it draws, on the node carrying the role.
    await waitFor(() => {
      const chart = container.querySelector('.hb-slope [role="img"]')
      expect(chart).toBeTruthy()
      expect(chart!.getAttribute('aria-label')).toBe('1 min 14.00, 5 min 16.80, 15 min 13.76')
    })
  })

  it('marks the horizon that crossed the core count', async () => {
    const { container } = render(<HostVitals />)
    // warnAbove is 20 * 0.75 = 15. Of 14.00 / 16.80 / 13.76, only 16.80 clears it.
    await waitFor(() => {
      expect(container.querySelectorAll('.hb-slope__node--warning')).toHaveLength(1)
    })
  })

  it('still names the machine and its uptime', async () => {
    render(<HostVitals />)
    expect(await screen.findByText('Macky-Mac')).toBeInTheDocument()
    expect(screen.getByText(/up 8 days/)).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd halbert_core/halbert_core/dashboard/frontend && npx vitest run src/components/shell/HostVitals.test.tsx`

Expected: FAIL — the first two tests fail because `.hb-slope` does not exist in the tree (the Load row is a local `Meter`). The third test passes already.

- [ ] **Step 3: Replace the Load meter with the slope**

In `HostVitals.tsx`, add the import beside the existing ones:

```tsx
import { SlopeChart } from '@halbert/design-system'
```

Replace the Load `<Meter>` block (currently lines 100–105) with:

```tsx
        {/* Load is three readings across three horizons, not one ratio: the
            join is what says whether the machine is climbing or recovering. */}
        <div className="space-y-1">
          <div className="flex items-baseline justify-between">
            <span className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
              Load
            </span>
            <span className="text-[10px] font-mono text-muted-foreground">
              {cpu.cores} cores
            </span>
          </div>
          <SlopeChart
            points={[
              { label: '1 min', value: load['1min'] },
              { label: '5 min', value: load['5min'] },
              { label: '15 min', value: load['15min'] },
            ]}
            reference={cpu.cores || undefined}
            referenceLabel={cpu.cores ? `${cpu.cores} cores` : undefined}
            warnAbove={cpu.cores ? cpu.cores * 0.75 : undefined}
            digits={2}
          />
        </div>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd halbert_core/halbert_core/dashboard/frontend && npx vitest run src/components/shell/HostVitals.test.tsx`

Expected: PASS, 3 tests.

Note: the accessible name is formatted with the same `digits` prop as the drawn readings (`SlopeChart.tsx:78`), so `digits={2}` gives `14.00 / 16.80 / 13.76`. Changing `digits` changes this assertion.

- [ ] **Step 5: Verify the whole frontend suite and types**

Run: `cd halbert_core/halbert_core/dashboard/frontend && npx tsc --noEmit && npm test`

Expected: typecheck silent; 1113 tests pass (1110 before, 3 added).

- [ ] **Step 6: Commit**

```bash
git add halbert_core/halbert_core/dashboard/frontend/src/components/shell/HostVitals.tsx \
        halbert_core/halbert_core/dashboard/frontend/src/components/shell/HostVitals.test.tsx
git commit -m "feat(vitals): load average is a slope, not a ratio of its first horizon

The rail drew a meter of load['1min'] over the core count and printed the
other two horizons as a detail string, so the one thing three readings can
say — whether the machine is climbing or recovering — was the one thing the
instrument could not. SlopeChart joins them against the core count."
```

---

### Task 2: Volume overview on the Storage page

**Files:**
- Modify: `halbert_core/halbert_core/dashboard/frontend/src/pages/Storage.tsx` (import block, and the summary strip near line 1832)
- Test: `halbert_core/halbert_core/dashboard/frontend/src/pages/Storage.dotplot.test.tsx` (create)

- [ ] **Step 1: Write the failing test**

Create `halbert_core/halbert_core/dashboard/frontend/src/pages/Storage.dotplot.test.tsx`:

```tsx
// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'

import { VolumeOverview } from './Storage'

const VOLUMES = [
  { id: 'a', label: 'TimeMachine', mountpoint: '/Volumes/TimeMachineStudio', percent: 94 },
  { id: 'b', label: 'Root', mountpoint: '/', percent: 11 },
  { id: 'c', label: 'LLM_Models', mountpoint: '/Volumes/LLM_Models', percent: 81 },
]

describe('VolumeOverview', () => {
  it('puts every volume on one shared axis', () => {
    const { container } = render(<VolumeOverview volumes={VOLUMES} />)
    expect(container.querySelectorAll('.hb-dotplot__dot')).toHaveLength(3)
  })

  it('orders fullest first so the pressure reads top-down', () => {
    const { container } = render(<VolumeOverview volumes={VOLUMES} />)
    const name = container.querySelector('[role="img"]')!.getAttribute('aria-label')!
    expect(name.indexOf('TimeMachine')).toBeLessThan(name.indexOf('LLM_Models'))
    expect(name.indexOf('LLM_Models')).toBeLessThan(name.indexOf('Root'))
  })

  it('takes each dot\'s pigment from the threshold, not the series order', () => {
    const { container } = render(<VolumeOverview volumes={VOLUMES} />)
    expect(container.querySelector('.hb-dotplot__dot--critical')).toBeInTheDocument()
    expect(container.querySelector('.hb-dotplot__dot--warning')).toBeInTheDocument()
    expect(container.querySelector('.hb-dotplot__dot--telemetry')).toBeInTheDocument()
  })

  it('renders nothing for a single volume, where there is nothing to compare', () => {
    const { container } = render(<VolumeOverview volumes={[VOLUMES[0]]} />)
    expect(container.querySelector('.hb-dotplot')).not.toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd halbert_core/halbert_core/dashboard/frontend && npx vitest run src/pages/Storage.dotplot.test.tsx`

Expected: FAIL — `VolumeOverview is not exported from './Storage'`.

- [ ] **Step 3: Add the component**

In `Storage.tsx`, extend the design-system import to include `DotPlot`:

```tsx
import { TactileMeter, type TactileMeterTone, SegmentedBar, type SegmentItem, DataGridRow, DriveCassette, type DrivePartitionItem, StorageTierGroup, DotPlot } from '@halbert/design-system'
```

Add this component just above `function deduplicateFilesystems` (around line 439):

```tsx
/**
 * VolumeOverview — every mounted volume on one fill axis.
 *
 * The per-volume meters below answer "how full is this one"; each has its own
 * track, so comparing them costs the reader seven numbers held in their head.
 * This answers "which is fullest" for free. One volume has nothing to compare,
 * so it renders nothing rather than a one-dot chart.
 */
export function VolumeOverview({
  volumes,
}: {
  volumes: Array<{ id: string; label: string; mountpoint: string; percent: number }>
}) {
  const items = React.useMemo(
    () =>
      [...volumes]
        .sort((a, b) => b.percent - a.percent)
        .map((v) => ({ id: v.id, label: v.label, value: v.percent })),
    [volumes],
  )

  if (items.length < 2) return null

  return (
    <div className="px-4 py-3">
      <div className="mb-2 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
        Fill across volumes
      </div>
      <DotPlot items={items} unit="%" aria-label="Fill percentage across mounted volumes" />
    </div>
  )
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd halbert_core/halbert_core/dashboard/frontend && npx vitest run src/pages/Storage.dotplot.test.tsx`

Expected: PASS, 4 tests.

- [ ] **Step 5: Mount it under the summary strip**

Find the summary strip containing `{stats.totalFs} Filesystems` (around line 1832) and locate the closing `</div>` of the element that wraps that row. Immediately after that closing tag, add:

```tsx
            <VolumeOverview
              volumes={filesystems.map((fs) => ({
                id: fs.id,
                label: getShortName(fs.mountpoint),
                mountpoint: fs.mountpoint,
                percent: fs.percent,
              }))}
            />
```

`filesystems` is the deduplicated `FilesystemEntry[]` already in scope on that component; if the local binding has a different name at that point, use whichever variable feeds the per-volume rows.

- [ ] **Step 6: Verify the whole frontend suite and types**

Run: `cd halbert_core/halbert_core/dashboard/frontend && npx tsc --noEmit && npm test`

Expected: typecheck silent; 1117 tests pass.

- [ ] **Step 7: Look at it in the running app**

Run the dashboard (`preview_start` with `halbert-backend` then `halbert-dashboard`), open `/storage`, and confirm: seven dots on one axis, fullest at the top, two red and one orange at 94 / 93 / 81, and the per-volume meters unchanged beneath.

- [ ] **Step 8: Commit**

```bash
git add halbert_core/halbert_core/dashboard/frontend/src/pages/Storage.tsx \
        halbert_core/halbert_core/dashboard/frontend/src/pages/Storage.dotplot.test.tsx
git commit -m "feat(storage): one axis for the volumes, above the per-volume meters

Seven meters in seven tracks cannot be compared without reading seven
numbers. The dot plot answers which volume is fullest before anything is
read; the meters stay for reading one volume."
```

---

## Sequenced backlog — everything not in slice 1

Each of these is its own plan. They are ordered by cost, and each names the single change that unblocks it.

### B1 · RangeBar on the GPU page — no backend work
The GPU discovery already carries `unified_memory_gb` (128), `gpu_memory_ceiling_gb` (96) and `gpu_memory_in_use_gb` (0.93). `GPU.tsx` currently shows a flat meter that reads 0.7% and discards the ceiling — the number that decides whether a model fits. Same shape as slice 1: frontend only.

### B2 · Service run state, then the StatusMatrix
`status` carries two different answers. `launchd.py:76-84` emits run state; `launchd.py:166-180` emits enable mode. Add to `data`:
- `run_state`: `'running' | 'stopped' | 'failed' | 'unknown'` — `unknown` for the plist path, which genuinely does not know
- `enable_mode`: `'keep_alive' | 'at_load' | 'manual' | 'disabled' | null`

Keep `status` as the human string. The matrix charts `run_state`; `enable_mode` becomes a table column. Do not collapse them into one scale.

### B3 · Per-core CPU, then the core heatmap
`_cpu_percent()` (`routes/system.py:219`) primes psutil per thread before trusting `interval=None`. psutil keeps a separate accumulator for the per-core call, so add a sibling `_cpu_percent_per_core()` with the same priming discipline and its own primed-thread set — do not add `percpu=True` to the existing call. Expose as `cpu.per_core: float[]`.

### B4 · Status history ring buffer, then sparklines
`/api/status` returns instants. Add a background 1-second sampler writing into `collections.deque(maxlen=60)` and expose `cpu.history_1m` and `memory.history_1m`. Until then `Sparkline` must be passed `empty` so it shows a dashed rule rather than inventing a trend.

### B5 · A listing endpoint for the state ledger, then LifespanBars
**Corrected from the original build order.** `/api/state/history` answers for one subject. LifespanBars needs many rows with their windows — a new route returning `subject, predicate, object, valid_from, valid_to` with a limit. Note before building a form on them: `confidence` is 1.0 and `source` is `thread_close` on all 444 rows, so neither dimension carries information yet.

### B6 · Attunement outcomes endpoint, then EstimateInterval
`attunement.db` holds 8 outcomes and no route exposes them. Needs an endpoint returning counts per subject. When wiring, prefer passing explicit `low`/`high` from the exact Clopper–Pearson interval the `ATN-3` rule specifies; the component's Wilson default is a reasonable fallback, not the specified statistic.

### B7 · Turn stage timings, then the Waterfall
Stage entry and exit are not stamped. Needs durations recorded per turn against the existing `AgentState` machine.

### B8 · A writer for `timeline.db`, then the event raster
The schema has been ready for weeks and the table has **zero rows** — the open half of `MIND-1`. The raster is worth building the day something writes to it and worthless the day before. Do not start with the chart.

---

## Self-review

**Spec coverage.** Slice 1 covers the two forms the vocabulary marked zero-backend and confirmed as such. `LifespanBars` was demoted to B5 because the validation disproved its readiness. Everything else in the vocabulary appears in B1–B8 with its unblocking change named.

**Placeholders.** None: every step carries the code or the exact command. Two steps flag a locate-by-context edit (Task 2 Step 5, the summary strip; Task 1 Step 3, the Load block) with the line numbers observed on 2026-09-18 — treat those numbers as hints and match on the surrounding code, which is quoted.

**Type consistency.** `VolumeOverview` takes `{id, label, mountpoint, percent}` in both the test and the component; the call site maps `FilesystemEntry` into that shape. `SlopeChart` props (`points`, `reference`, `referenceLabel`, `warnAbove`, `digits`) match the shipped signature in `packages/design-system/src/charts/SlopeChart.tsx`. `DotPlot` items are `{id, label, value}` as shipped.
