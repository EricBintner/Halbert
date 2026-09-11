# Halbert Data Visualization: Scrutiny, Reverse-Engineering & Best Practices Audit

**Date:** 2026-09-11  
**Author:** Systems Architect & UI Lead  
**Status:** Architectural Scrutiny & Hardening Specification  
**Target:** [`documentation/design/DATA-VISUALIZATION-SPEC-AND-OPPORTUNITIES.md`](DATA-VISUALIZATION-SPEC-AND-OPPORTUNITIES.md), `halbert-dashboard`, `@halbert/design-system`, and Backend Telemetry  
**References:**
- Edward Tufte, *The Visual Display of Quantitative Information* (Data-ink ratio, Lie Factor)
- William S. Cleveland & Robert McGill, *Graphical Perception: Theory, Experimentation, and Application*
- Stephen Few, *Information Dashboard Design* & *Show Me the Numbers*
- WCAG 2.1 / 2.2 Guidelines: 1.4.1 (Use of Color), 1.4.3 (Contrast Minimum), 1.4.11 (Non-text Contrast)
- Halbert Brand Standard: [`documentation/design/BRAND-GUIDELINES-AND-AESTHETIC.md`](BRAND-GUIDELINES-AND-AESTHETIC.md)

---

## 1. Executive Summary & Purpose

A data visualization plan that merely catalogues attractive chart concepts is an invitation to failure. In a systems administration application like Halbert, naive visual implementations routinely commit severe engineering and perceptual errors:
- Graphs crash because D3 color interpolators fail on CSS custom properties.
- Dashboards lag or flicker because animation loops fire on every 3-second telemetry poll.
- Charts mislead the operator because axes truncate baselines or hide critical throttling spikes.
- Designs fail in production because the backend driver or kernel telemetry does not actually expose the promised data breakdown.

This document subjects [`DATA-VISUALIZATION-SPEC-AND-OPPORTUNITIES.md`](DATA-VISUALIZATION-SPEC-AND-OPPORTUNITIES.md) to **rigorous reverse-engineering and scrutiny**. We systematically audit:
1. **Backend Telemetry Reality vs. Fantasy:** What the kernel, `psutil`, `lsblk`, and `nvidia-smi` actually emit vs. what was envisioned.
2. **Technical Tooling Pitfalls (Nivo + D3 in Tauri/React 18):** CSS variable resolution traps, `ResponsiveContainer` dimension collapse, and bundle bloat.
3. **Data Visualization Best Practices & Rookie Mistakes:** Baseline integrity, perceptual uniformity, color-blind accessibility, animation fatigue, and small-multiples calibration.
4. **Storage Page Layout Reconstruction:** Mathematical and structural re-engineering of `Storage.tsx` to permanently solve the horizontal alignment defect.

---

## 2. Backend Telemetry Reality Check (Honesty of State Gate)

Halbert's 5th brand pillar is **Honesty of State**: *Zero vanity metrics. Every pixel traces to real telemetry. If a sensor is dark or a breakdown is unmeasured, state it honestly.*

We reverse-engineered the actual backend telemetry collectors in `halbert_core` to test the viability of the proposed visualizations:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     BACKEND TELEMETRY FEASIBILITY MATRIX                    │
├──────────────────────┬──────────────────────┬──────────┬────────────────────┤
│ Proposed Visualizer  │ Required Data        │ Emitted? │ Gap / Reality      │
├──────────────────────┼──────────────────────┼──────────┼────────────────────┤
│ Storage Multi-       │ Btrfs/Bcachefs/ZFS   │ YES      │ `storage.py` scans │
│ Segment Allocation   │ Data vs Meta vs Free │          │ `btrfs fi df` &    │
│                      │                      │          │ `bcachefs usage`.  │
├──────────────────────┼──────────────────────┼──────────┼────────────────────┤
│ Disk Space Treemap   │ Directory tree size  │ NO       │ Running `du` at    │
│ (Baobab/DaisyDisk)   │ breakdown            │          │ runtime kills disk │
│                      │                      │          │ I/O. Must be gated.│
├──────────────────────┼──────────────────────┼──────────┼────────────────────┤
│ 1m / 5m Telemetry    │ Rolling historical   │ NO       │ `/api/status` emits│
│ Sparklines           │ time-series buffer   │          │ instantaneous float│
│                      │                      │          │ scalar only.       │
├──────────────────────┼──────────────────────┼──────────┼────────────────────┤
│ GPU VRAM Topology    │ Weights vs KV Cache  │ NO (At   │ `nvidia-smi` only  │
│ Breakdown            │ vs Display vs Free   │ Driver)  │ reports total used/│
│                      │                      │          │ free per PID.      │
├──────────────────────┼──────────────────────┼──────────┼────────────────────┤
│ GPU Power Envelope   │ Current W, Power     │ YES      │ `gpu_tools.py`     │
│ Bullet Chart         │ Limit (TDP) W        │          │ emits both fields. │
├──────────────────────┼──────────────────────┼──────────┼────────────────────┤
│ Fleet Multi-Node     │ Satellite CPU, RAM,  │ YES      │ `peerApi.ts` &     │
│ Resource Heatmap     │ Temp, Uptime         │          │ `fleet.py` emit it.│
├──────────────────────┼──────────────────────┼──────────┼────────────────────┤
│ Network Rx/Tx Stream │ Historical byte/sec  │ NO       │ Interface stats are│
│ Graph                │ rate buffer          │          │ cumulative counters│
└──────────────────────┴──────────────────────┴──────────┴────────────────────┘
```

### Critical Telemetry Gaps & How to Fix Them:

#### Gap 1: The Sparkline "Cold Start" Trap (Dashboard Vitals)
- **The Defect:** `halbert_core/dashboard/routes/system.py` computes `_cpu_percent()` on demand. It stores zero historical samples. If the frontend attempts to render a 1-minute sparkline, it will only have 1 data point on initial page load, remaining empty or looking like a flat dot until the user has stayed on the page for 60 seconds.
- **The Fix:** Add a lightweight in-memory ring buffer (`collections.deque(maxlen=60)`) in `system.py` updated by a background 1-second asyncio ticker. Expose `cpu.history_1m: float[]` and `memory.history_1m: float[]` in the `/api/status` response. The sparkline renders complete immediately upon load.

#### Gap 2: The GPU "Driver vs. Runtime" Boundary (GPU VRAM)
- **The Defect:** Operating system GPU drivers (`nvidia-smi`, Metal IOKit, ROCm `rocm-smi`) know how many megabytes a process has allocated; **they have zero semantic awareness of whether those bytes are LLM weights, KV cache tensors, or framebuffer surfaces**. Claiming to show "Model Weights vs. KV Cache" from GPU driver telemetry is impossible.
- **The Fix:** Adhere strictly to the *Honesty Gate*:
  1. *Hardware Layer (Driver telemetry):* Display `[ System / Xorg / Display | Halbert / Ollama Process | Free VRAM ]`.
  2. *Application Layer (Inference Engine API):* Only when an active Ollama/vLLM integration reports its internal memory breakdown via engine API (`/api/ps`) may the UI slice the process memory into weights vs. context. Otherwise, label the block honestly as `Process Allocation (PID 12345)`.

#### Gap 3: The Disk Treemap I/O Trap (Storage Page)
- **The Defect:** A full-disk directory treemap requires recursive file tree traversal (`du -x /` or `os.scandir`). On a multi-terabyte SSD or spinning array, this takes minutes and saturates disk queue depth, locking up user workloads.
- **The Fix:** NEVER run recursive disk audits during routine background discovery polls. An interactive treemap must be an **on-demand, user-initiated action** ("Scan Disk Usage") with progressive streaming results, targetable to specific mount points (e.g. `/var/log` or `/home`), or integrated with pre-indexed file finders.

---

## 3. Technical Tooling Stress-Test: Nivo + D3 in React 18 / Tauri

While Nivo is visually superior to Recharts, deploying Nivo into Halbert's stack exposes four specific technical landmines that must be engineered around.

### Landmine 1: The D3 Color Interpolation Crash (CSS Variables)
- **The Failure:** Halbert's single source of truth for color is `/shared-tokens/tokens.css`. Developers naturally pass CSS variables into chart configurations:
  ```typescript
  // ROOKIE MISTAKE:
  <ResponsiveBar colors="var(--color-accent)" ... />
  ```
  Nivo passes colors to D3 color routines (e.g. `d3.color()`, `d3.interpolateRgb()`, or `.darker()`). D3 expects valid color strings (`#E05338`, `rgb(224, 83, 56)`). When given `'var(--color-accent)'`, `d3.color()` returns `null`. Nivo then executes `d3Color.darker()` on `null`, throwing an unhandled runtime error:
  `TypeError: Cannot read properties of null (reading 'darker')`.
- **The Rule & Architectural Solution:**
  1. For SVG elements with direct CSS styling, use CSS class names.
  2. For D3 scales and Nivo color props, use a token resolution bridge that extracts computed hex/rgb values from the DOM:
     ```typescript
     // halbert_core/dashboard/frontend/src/lib/tokens.ts
     const tokenCache = new Map<string, string>();
     export function getTokenColor(tokenVar: string): string {
       if (typeof window === 'undefined') return '#000000';
       const cached = tokenCache.get(tokenVar);
       if (cached) return cached;
       const val = getComputedStyle(document.documentElement)
         .getPropertyValue(tokenVar)
         .trim();
       if (val) tokenCache.set(tokenVar, val);
       return val || '#000000';
     }
     ```
  3. Listen to theme toggle events to invalidate `tokenCache`.

### Landmine 2: `ResponsiveContainer` Dimension Collapse in Flexbox & Grid
- **The Failure:** Nivo’s `Responsive*` components (`ResponsiveBar`, `ResponsiveLine`, `ResponsiveTreemap`) measure their parent container’s bounding box via `ResizeObserver`.
  If the parent container is in a CSS Grid or Flexbox row without a fixed height or without `min-width: 0`, the calculation produces height = 0px (collapsing the chart completely) or enters an infinite layout cycle (chart resizes -> parent expands -> chart resizes).
- **The Rule:** Every container wrapping a Nivo responsive chart must explicitly declare:
  1. A concrete height class (e.g., `className="h-48 w-full min-w-0"` or `style={{ height: 240 }}`).
  2. `min-width: 0` on any flex/grid parent to allow shrink-to-fit behavior.

### Landmine 3: Animation Churn & Telemetry Re-render Storms
- **The Failure:** By default, Nivo enables animated transitions (`animate={true}`) with spring physics (`@react-spring/web`).
  In a desktop app where telemetry polls every 2–5 seconds, re-triggering spring physics on every poll forces continuous CPU/GPU rasterization, causing visible jitter and noticeable battery drain on portable laptops.
- **The Rule:** 
  - For real-time telemetry streams and polled vitals, set `animate={false}` or use a very tight linear duration (`motionConfig="fast"`).
  - Save spring physics exclusively for user-driven interactions (e.g. expanding an accordion or toggling a filter).

### Landmine 4: Bundle Weight & Dependency Overhead
- **The Failure:** Installing the entire `nivo` umbrella pulls dozens of D3 packages and animation runtimes into the desktop frontend.
- **The Rule:**
  - Enforce Halbert's **Two-Tier Architecture**:
    - **Tier 1 Primitives (`@halbert/design-system`):** 90% of dashboard usage (progress bars, status meters, sparklines) MUST be written as zero-dependency React SVG components.
    - **Tier 2 Analytical (`@nivo/*`):** Only install the specific packages needed: `@nivo/core`, `@nivo/treemap`, and `@nivo/heatmap`.
  - Remove the dead `recharts` dependency from `frontend/package.json` to prevent dual-library overhead.

---

## 4. Best Practices in Data Visualization: Avoiding Rookie Mistakes

Systems administration interfaces carry high operational consequences. A misinterpreted graph can lead an administrator to unmount the wrong pool or ignore thermal runaway. We review the foundational literature (Tufte, Cleveland, Few) and establish strict rules for Halbert.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    DATA VIZ ROOKIE MISTAKES & HALBERT RULES                 │
├───────────────────────┬──────────────────────┬──────────────────────────────┤
│ Rookie Mistake        │ Why It Fails         │ Halbert Enforced Rule        │
├───────────────────────┼──────────────────────┼──────────────────────────────┤
│ Truncated Bar Baseline│ High Lie Factor.     │ Bar charts ALWAYS start at   │
│ (Y-axis starts at 80%)│ Exaggerates small deltas 0. Line charts can bound     │
│                       │ to look like crises. │ ranges if labeled.           │
├───────────────────────┼──────────────────────┼──────────────────────────────┤
│ Pie & Donut Charts for│ Human perception is  │ BANNED for resource breakdown│
│ >3 Resource Slices    │ terrible at comparing│ Use stacked horizontal bars  │
│                       │ angles and arc areas.│ or ranked bar lists.         │
├───────────────────────┼──────────────────────┼──────────────────────────────┤
│ Color Alone for State │ Fails ~8% of men with│ Color alone fails WCAG 1.4.1.│
│ (Red vs Green dots)   │ color blindness      │ Must pair with icon, shape,  │
│                       │ (deuteranopia).      │ or text badge.               │
├───────────────────────┼──────────────────────┼──────────────────────────────┤
│ Rainbow / Jet Heatmap │ Creates false visual │ Use perceptually uniform     │
│ Colormaps             │ boundaries where no  │ single-hue or two-tone       │
│                       │ data cliff exists.   │ lightness ramps.             │
├───────────────────────┼──────────────────────┼──────────────────────────────┤
│ Dual Independent      │ Misleads users on    │ BANNED. Use small multiples  │
│ Y-Axes on One Chart   │ correlation & scale. │ (stacked sparklines).        │
├───────────────────────┼──────────────────────┼──────────────────────────────┤
│ Bezier Spline Faking  │ Interpolation curves │ Telemetry charts use linear  │
│                       │ invent peaks/valleys │ segments. Zero invented data.│
│                       │ that never happened. │                              │
├───────────────────────┼──────────────────────┼──────────────────────────────┤
│ Floating Distant      │ Forces eye-darting   │ Use direct inline labels and │
│ Legends               │ across the screen.   │ tabular numeric gutters.     │
└───────────────────────┴──────────────────────┴──────────────────────────────┘
```

### 4.1 Cleveland & McGill Perceptual Hierarchy
Cleveland and McGill's empirical research established how accurately human eyes decode different graphical encodings (from most accurate to least accurate):
1. **Position along a common scale** (e.g. aligned bar charts, scatter points) — *Most accurate*
2. **Position along non-aligned scales** (e.g. small multiples)
3. **Length / Direction / Angle** (e.g. bar length, pie slices)
4. **Area** (e.g. bubble charts, treemaps)
5. **Volume / Curvature**
6. **Shading and Color Saturation** — *Least accurate (good for pattern spotting, bad for quantitative evaluation)*

**Halbert Design Mandate:**
- Critical metrics (storage capacity, CPU load, memory headroom) must ALWAYS use **Position along a common aligned scale** (horizontal calibrated bars).
- Shading/heatmaps are reserved exclusively for exploratory matrices (cluster node heatmap, CPU core matrix) where finding the anomaly is the goal, followed by numeric inspection.

### 4.2 WCAG 2.1 Accessibility & Color-Blind Safety
- **WCAG 1.4.1 (Use of Color):** In `shared-tokens/tokens.css`, status tones carry strict luminance differences:
  - `--color-status-nominal` (Sage #2D5A27) vs. `--color-status-critical` (Vermilion #9E2A2B).
  - In greyscale / monochromatic vision, nominal and critical must retain distinguishable contrast against the surface.
  - In code: Any metric bar that changes color based on threshold must also render the numerical value and a textual status (`[Nominal]`, `[Warning]`, `[Critical]`).
- **WCAG 1.4.11 (Non-Text Contrast):** Graphical elements (chart bars, active indicator ticks, grid boundaries) must maintain at least **3:1 contrast** against their adjacent background. Halbert's `--color-border` and `--color-ink` clear this floor on all licensed surfaces (verified by `scripts/check_contrast.py`).

---

## 5. Storage Page Reverse-Engineering & Structural Blueprint

The user identified the Storage page as the prime example of layout breakdown:
> *"the storge page is amess because the bar chards begin wherever the text endsa and its inconsistant."*

### 5.1 Exact Technical Dissection of the Defect
In `Storage.tsx`:
- When a disk has **multiple filesystems**:
  Each row is rendered inside:
  `<div className="grid gap-x-3 items-center text-sm" style={{ gridTemplateColumns: 'auto 1fr auto auto' }}>`
  - Column 1 contains: `<Folder />`, `<EditableName />`, and `<span className="text-muted-foreground text-xs">{fs.mountpoint}</span>`.
  - Because `gridTemplateColumns` is set to `auto` for Column 1, Column 1's width depends on the string length of the name and path:
    - Row A: `Root` + `/` -> Width = 110px. Bar starts at pixel 122.
    - Row B: `Virtual Machines` + `/var/lib/libvirt/images` -> Width = 310px. Bar starts at pixel 322.
  - Within the **same card**, the progress bars begin 200px apart!
- When a disk has a **single filesystem**:
  The developer used:
  `<div className="flex items-center gap-2 text-sm"><FilesystemUsageBar fs={primaryFs} showName={false} /></div>`
  - Because `showName={false}`, Column 1 is omitted entirely.
  - The bar starts flush at pixel 0 of the card container!
- **Result:** Complete visual incoherence across the entire storage interface.

```
THE CURRENT BROKEN LAYOUT (Variable auto column pushes the meter):

Card 1 (Single Filesystem):
┌─────────────────────────────────────────────────────────────┐
│ System SSD (/dev/nvme0n1)                                   │
│ [===================              ] 45GB/100GB (45%)        │ ◄── Starts at x=0
└─────────────────────────────────────────────────────────────┘

Card 2 (Multiple Filesystems):
┌─────────────────────────────────────────────────────────────┐
│ Data Pool (Btrfs)                                           │
│ [📁 Root /]          [============        ] 120GB/500GB (24%) │ ◄── Starts at x=120
│ [📁 Virtual Machines /var/lib/libvirt/images] [====] 800GB/2TB (40%) ◄── Starts at x=310
└─────────────────────────────────────────────────────────────┘
```

### 5.2 The Re-Engineered Architecture: The Two-Tier Vignelli Layout
To permanently eliminate horizontal drift, we replace inline variable grids with a **Two-Tier Typographic & Instrument Layout**.

#### Tier 1: The Identity Gutter (Typographic Baseline)
The label, mount path, and filesystem type are placed **above the gauge** or in a **strictly fixed-width column**. They never share a flexible horizontal track with the progress bar.

#### Tier 2: The Full-Width Calibrated Instrument Track
The gauge spans 100% of the available card width. Every disk card, whether single-filesystem, multi-filesystem, or multi-disk array, starts at the exact same horizontal pixel coordinate.

```
RE-ENGINEERED TWO-TIER VIGNELLI LAYOUT (Storage Card):

┌─────────────────────────────────────────────────────────────────────────────┐
│ ▤ Data Pool  btrfs · RAID1 · 2 Disks                              [Nominal] │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│ 📁 Virtual Machines                                                         │
│    /var/lib/libvirt/images · BTRFS                    800 GB / 2.0 TB (40%) │
│    ┌────────────────────────┬─────────────────────────────────────────┐     │
│    │████████████████████████│                                         │     │
│    └────────────────────────┴─────────────────────────────────────────┘     │
│    Used: 800 GB · Free Headroom: 1.2 TB                                     │
│                                                                             │
│ 📁 User Home                                                                │
│    /home · BTRFS                                      450 GB / 2.0 TB (22%) │
│    ┌───────────────────┬──────────────────────────────────────────────┐     │
│    │███████████████████│                                              │     │
│    └───────────────────┴──────────────────────────────────────────────┘     │
│    Used: 450 GB · Free Headroom: 1.55 TB                                    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
▲                                                                       ▲
Meter start is 100% unified across all rows and cards                   Meter end
```

### 5.3 Alternative High-Density Layout: Rigid Typographic Column Grid
For dense views (e.g. server racks with 20+ volumes), a single-row layout is permissible ONLY if the label column is rigidly fixed with strict text truncation and tooltip disclosure:

```css
/* High-Density Fixed Column Layout */
.hb-storage-row {
  display: grid;
  grid-template-columns: 200px 1fr 140px 60px;
  column-gap: 16px;
  align-items: center;
}

.hb-storage-row__label {
  width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
```
In this model, the meter starts at exactly pixel 216 on every card and every row across the entire interface.

---

## 6. Concrete Implementation Blueprint for `@halbert/design-system`

To operationalize this plan without adding heavy external dependencies, we specify two new Tier 1 components for `@halbert/design-system`:

### 6.1 Component 1: `<TactileMeter />`
A precision horizontal gauge with mechanical tick marks, tabular readouts, and honest threshold states:

```tsx
// packages/design-system/src/primitives/TactileMeter.tsx
import * as React from 'react';
import { cx } from '../lib';

export interface TactileMeterProps extends React.HTMLAttributes<HTMLDivElement> {
  value: number; // 0 - 100
  label?: string;
  sub?: string;
  unit?: string;
  ticks?: number[]; // default: [25, 50, 75, 90]
  tone?: 'nominal' | 'warning' | 'critical';
  offline?: boolean;
}

export function TactileMeter({
  value,
  label,
  sub,
  unit = '%',
  ticks = [25, 50, 75, 90],
  tone,
  offline = false,
  className,
  ...props
}: TactileMeterProps) {
  const clamped = Math.max(0, Math.min(100, value));
  const resolvedTone = tone || (clamped >= 90 ? 'critical' : clamped >= 75 ? 'warning' : 'nominal');

  return (
    <div className={cx('hb-tactile-meter', offline && 'is-offline', className)} {...props}>
      {(label || sub) && (
        <div className="hb-tactile-meter__header">
          {label && <span className="hb-tactile-meter__label">{label}</span>}
          {sub && <span className="hb-tactile-meter__sub">{sub}</span>}
          <span className="hb-tactile-meter__value">
            {offline ? '[Offline]' : `${clamped.toFixed(1)}${unit}`}
          </span>
        </div>
      )}

      {/* The Track */}
      <div className="hb-tactile-meter__track" role="meter" aria-valuenow={clamped} aria-valuemin={0} aria-valuemax={100}>
        <div
          className={cx('hb-tactile-meter__fill', `hb-tactile-meter__fill--${resolvedTone}`)}
          style={{ width: `${offline ? 0 : clamped}%` }}
        />

        {/* Precision Mechanical Tick Marks */}
        {ticks.map((t) => (
          <div
            key={t}
            className={cx('hb-tactile-meter__tick', t >= 90 && 'hb-tactile-meter__tick--critical')}
            style={{ left: `${t}%` }}
          />
        ))}
      </div>
    </div>
  );
}
```

### 6.2 Component 2: `<SegmentedBar />`
A multi-category resource allocation bar for filesystems (Data / Meta / Snapshots / Free) and VRAM:

```tsx
// packages/design-system/src/primitives/SegmentedBar.tsx
import * as React from 'react';
import { cx } from '../lib';

export interface SegmentItem {
  id: string;
  label: string;
  value: number; // raw value (e.g. GB)
  colorClass: string; // e.g. 'bg-ink' or 'bg-status-warning'
  hatchPattern?: boolean;
}

export interface SegmentedBarProps extends React.HTMLAttributes<HTMLDivElement> {
  total: number;
  segments: SegmentItem[];
  unit?: string;
  showLegend?: boolean;
}

export function SegmentedBar({
  total,
  segments,
  unit = 'GB',
  showLegend = true,
  className,
  ...props
}: SegmentedBarProps) {
  const sumUsed = segments.reduce((acc, s) => acc + s.value, 0);
  const free = Math.max(0, total - sumUsed);

  return (
    <div className={cx('hb-segmented-bar', className)} {...props}>
      <div className="hb-segmented-bar__track">
        {segments.map((seg) => {
          const pct = total > 0 ? (seg.value / total) * 100 : 0;
          if (pct <= 0) return null;
          return (
            <div
              key={seg.id}
              className={cx('hb-segmented-bar__segment', seg.colorClass, seg.hatchPattern && 'is-hatched')}
              style={{ width: `${pct}%` }}
              title={`${seg.label}: ${seg.value} ${unit} (${pct.toFixed(1)}%)`}
            />
          );
        })}
      </div>

      {showLegend && (
        <div className="hb-segmented-bar__legend">
          {segments.map((seg) => (
            <div key={seg.id} className="hb-segmented-bar__legend-item">
              <span className={cx('hb-segmented-bar__bullet', seg.colorClass)} />
              <span className="hb-segmented-bar__legend-label">{seg.label}</span>
              <span className="hb-segmented-bar__legend-val">{seg.value} {unit}</span>
            </div>
          ))}
          <div className="hb-segmented-bar__legend-item hb-segmented-bar__legend-item--free">
            <span className="hb-segmented-bar__bullet bg-border" />
            <span className="hb-segmented-bar__legend-label">Free Headroom</span>
            <span className="hb-segmented-bar__legend-val">{free.toFixed(1)} {unit}</span>
          </div>
        </div>
      )}
    </div>
  );
}
```

---

## 7. Actionable Guardrails for Code Reviews

Every PR introducing or altering a data visualization in Halbert must be verified against this gate:

1. **Alignment Verification:** Does any meter or chart shift horizontally when a text label changes length? (If yes, reject).
2. **Telemetry Backing Check:** Does every segment of a visualization trace to a real measured property in backend discovery/telemetry? (If guessing or faking sub-components, reject).
3. **No Canvas-CSS Variable Blindness:** If using Nivo or Canvas, are color properties properly converted from tokens via `getTokenColor()` rather than passing unparsed `var(...)` strings into D3?
4. **Contrast Gate:** Run `python3 scripts/check_contrast.py` — every chart fill and label must pass WCAG AA floors against the paper canvas.
5. **No Animation Churn:** Polled real-time telemetry must have motion animations disabled or set to instantaneous linear updates.
