# Halbert Data Visualization Specification & Opportunity Catalog

**Date:** 2026-09-11  
**Status:** Design Standard & Architectural Specification  
**Scope:** Desktop Application (`halbert-dashboard`), `@halbert/design-system`, and Shared Telemetry  
**References:**
- [`documentation/design/BRAND-GUIDELINES-AND-AESTHETIC.md`](BRAND-GUIDELINES-AND-AESTHETIC.md) — The 5 Pillars, Colour Law, and Typography Triad
- [`documentation/design/BRAND-AESTHETIC-STYLEGUIDE-AND-STORYBOOK-PLAN.md`](BRAND-AESTHETIC-STYLEGUIDE-AND-STORYBOOK-PLAN.md) — Design System roadmap
- [`shared-tokens/tokens.css`](../../shared-tokens/tokens.css) — Single source of truth for color, space, and borders
- [Nivo Data Visualization Library](https://nivo.rocks/) — React + D3 component system benchmark

---

## 1. Executive Summary & Design Philosophy

Halbert's founding premise is that the computer is not an external appliance managed through corporate SaaS forms; **it is an embodied machine with a voice, speaking directly in the first person grounded in measured telemetry**.

Every chart, gauge, sparkline, and meter in Halbert is an instrument plate on that machine. We reject two prevailing software conventions:
1. **Generic Corporate SaaS Dashboards:** Floating rounded white cards, arbitrary soft pastel palettes, generic blue progress bars, and uncalibrated metrics that look like an invoicing portal.
2. **Cyberpunk / Sci-Fi Neon Tropes:** Pitch-black canvases with radioactive lime/magenta lines and fake jitter animations that signal *toy* rather than a mission-critical operating instrument.

Instead, Halbert draws from the golden age of industrial graphic design: **Dieter Rams at Braun, Marcello Nizzoli and Ettore Sottsass at Olivetti, Massimo Vignelli’s Unigrid, and the 1975 NASA Graphics Standards Manual**.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                   THE FIVE PILLARS OF HALBERT DATA VIZ                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  1. DAYLIGHT & PAPER ──────▶ Warm unbleached linen canvas (#F7F4EE).        │
│                              Recessed data trays (#EFECE4 / #E6E2D8).       │
│                                                                             │
│  2. LETTERPRESS ACCENT ────▶ Single Olivetti Vermilion (#E05338) for focal  │
│                              thresholds. Muted sage/ochre for status bands. │
│                                                                             │
│  3. STRICT UNIGRID ────────▶ Absolute baseline grid alignment. Bar charts   │
│                              NEVER drift based on arbitrary label lengths.  │
│                                                                             │
│  4. INSTRUMENT TACTILITY ──▶ Machined hairline borders, scale tick marks,   │
│                              tabular figures, and calibrated ranges.        │
│                                                                             │
│  5. COMPUTATIONAL HONESTY ─▶ Zero vanity metrics. No fake bezier smoothing  │
│                              that hides spikes. Dark sensors state offline. │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. The Defect Anatomy: Storage Page Case Study ("The Mess")

The Storage page (`Storage.tsx`) exemplifies why ad-hoc progress bars without a graphic design system break down under real-world systems administration data.

### 2.1 The Root Cause in Code
In `Storage.tsx` (lines 682–732 and 1008–1055), filesystem capacity is rendered using a generic Radix `<Progress>` component nested inside an uncalibrated layout:

```tsx
// Current Broken Layout in Storage.tsx:
<div 
  className="grid gap-x-3 items-center text-sm"
  style={{ gridTemplateColumns: 'auto 1fr auto auto' }}
>
  {/* Column 1: Variable text length pushes the entire row */}
  <div className="flex items-center gap-1.5">
    <Folder className="h-3.5 w-3.5 text-info shrink-0" />
    <EditableName id={`fs-${fs.mountpoint}`} defaultName={shortName} />
    <span className="text-muted-foreground text-xs">{fs.mountpoint}</span>
  </div>

  {/* Column 2: The progress bar starts wherever Column 1 ended */}
  <Progress value={fs.percent} className="h-2" />

  {/* Column 3: Used / Size */}
  <span className="text-muted-foreground text-right text-xs">{fs.used}/{fs.size}</span>

  {/* Column 4: Percent Badge */}
  <Badge>{fs.percent}%</Badge>
</div>
```

### 2.2 Why This Breaks Visually
1. **Unstable Horizontal Baseline:** Because Column 1 has width `auto`, its width is dictated by the character length of the volume name and mount path. A short label like `Root (/)` produces a 120px column; a long label like `Virtual Machines (/var/lib/libvirt/images)` produces a 340px column. Across rows, and across cards, the left edge of the bar chart wildly steps back and forth.
2. **Card Divergence:** Single-filesystem disks use an entirely different layout (`showName={false}`, flex row with no label column) so the bar starts flush against the card padding, whereas multi-filesystem cards start indented.
3. **Data Collapse:** A filesystem is not a monolithic container with a simple percentage. Modern filesystems (Btrfs, ZFS, Bcachefs) have data redundancy profiles (RAID1, DUP, single), metadata allocations, snapshot reserves, and tiered caching (NVMe write buffer vs. spinning rust). A single flat bar hides whether a full disk is running out of block space or running out of metadata allocations.

### 2.3 The Graphic Design Solution for Storage
To achieve Vignelli-level typographic and visual order:
- **Separation of Label & Gauge Zones:** Labels, mount points, and drive paths belong on a dedicated header or fixed-width tabular column. The meter runs across a consistent, predictable coordinate space.
- **Segmented Capacity Gauges:** Replace the single progress fill with a multi-segment tactile meter:
  `[ System / OS | User Data | Snapshots / Reserves | Free Headroom ]`
- **Hierarchical Drive & Pool Visualization:** Multi-disk arrays (Bcachefs foreground/promote tiers, Btrfs subvolumes, ZFS vdevs) need a structural diagram showing physical drives feeding into logical pools.

```
CURRENT (Chaotic Drift):
[Root /] ──────────────── [======    ] 120GB/500GB [24%]
[Virtual Machines /var/lib/libvirt/images] ── [====    ] 800GB/2TB [40%]
[Home /home] ──────────── [========  ] 450GB/1TB [45%]

REDESIGNED (Vignelli Fixed Baseline & Multi-Segment Meter):
┌─────────────────────────────────────────────────────────────────────────────┐
│ Home Array  bcachefs · 3 drives (2 NVMe cache + 1 HDD data)     [Healthy]   │
├─────────────────────────────────────────────────────────────────────────────┤
│ /home                     Data: 450 GB · Meta: 12 GB · Free: 538 GB (1.0 TB) │
│ ┌──────────────────────┬──────┬───────────────────────────────┐ 46.2%       │
│ │██████████████████████│▒▒▒▒▒▒│                               │             │
│ └──────────────────────┴──────┴───────────────────────────────┘             │
│  ▲ Data (RAID1)         ▲ Meta ▲ Available Headroom                         │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Application-Wide Data Visualization Audit & Opportunities

Every primary page in Halbert has deep telemetry that is currently trapped in text numbers or raw tables. Below is the domain-by-domain blueprint for graphic design transformation.

### 3.1 Domain Map & Opportunity Matrix

| Domain Page | Current Implementation | Data Viz Opportunity | Recommended Technique |
|---|---|---|---|
| **Storage** (`Storage.tsx`) | Ad-hoc `<Progress>` bars with staggered text baselines | Segmented capacity bars, tier visualizer, Baobab/DaisyDisk disk usage treemap | Fixed Grid Gauge + `@nivo/treemap` |
| **System Dashboard** (`Dashboard.tsx`) | 4px static progress lines under text totals | 1m / 5m telemetry sparklines, circular mechanical dial meters, load distribution ribbons | Tactile Dial Meter + `@nivo/line` |
| **Fleet Compute** (`Compute.tsx` / `NodeFleetCockpit.tsx`) | Plain text rows (`CPU 12.4%`, `RAM 45.1%`, `Temp 65C`) | Multi-node resource matrix, cluster heatmap, node link & latency topology | `@nivo/heatmap` + `@nivo/network` |
| **GPU & Accelerators** (`GPU.tsx`) | Stacked generic progress bars for load, temp, power | VRAM allocation breakdown (weights/cache/free), power envelope meter, thermal headroom | Segmented VRAM Bar + Bullet Meter (`@nivo/bullet`) |
| **Network** (`Network.tsx`) | Text tables of interfaces, IP addresses, listening ports | Real-time Rx/Tx throughput ribbon/sparkline, open port distribution chart, interface topology | Dual-direction area chart + `@nivo/chord` |
| **Backups** (`Backups.tsx`) | Collapsible cards with text run logs | Execution history timeline / Gantt ribbon, snapshot retention accumulation curve | Timeline Ribbon + `@nivo/stream` |
| **Containers** (`Containers.tsx`) | Status badge cards with text CPU/memory strings | Container host share treemap (who is using what % of host RAM/CPU), restart matrix | `@nivo/treemap` + Activity Dot Matrix |
| **Memory / RAG** (`Memory.tsx`) | Plain text badge entry counts (`1,240 items`) | Vector collection distribution, token budget vs. memory consumption, embedding density | Polar / Radial Bar (`@nivo/radial-bar`) |
| **Hardware Sensors** (`hwmon` telemetry) | Tabular lists of temperatures and RPMs | Multi-zone thermal map, fan speed curves (RPM vs. Temp), voltage rail stability bands | Tactile Gauge Strip + Sensor Matrix |

---

## 4. Deep Dives by Domain

### 4.1 Storage & Filesystems (`Storage.tsx`)
Storage is the physical backbone of the machine. The interface must communicate capacity, health, and structure simultaneously.

#### Opportunities:
1. **Unified Baseline Storage Gauge:** Standardize all storage usage on a shared component where labels sit above the meter or in a fixed-width typographic gutter (minimum 180px, tabular mono mountpoint).
2. **Multi-Segment Drive Allocation:** Show the breakdown of blocks:
   - *Active File Data* (Solid slate/ink)
   - *Metadata & Journal* (Fine diagonal hatch or secondary tint)
   - *Snapshots & CoW clones* (Muted terracotta)
   - *Free unallocated headroom* (Recessed linen ground)
3. **Array & Pool Topology Map:** For Btrfs/ZFS/Bcachefs pools, display the physical drives feeding into the pool, showing individual drive health, temperature, and tier assignment (e.g. Foreground SSD Write Cache vs. Background HDD Storage).
4. **Interactive Space Treemap (baobab / WinDirStat style):** Implement a summonable or embedded `@nivo/treemap` to visualize directory space consumption down to major folders, allowing the user to spot runaway logs or VM images instantly.

---

### 4.2 System Dashboard & Vitals (`Dashboard.tsx`, `Layout.tsx`)
The primary dashboard currently displays snapshot percentages (e.g., `CPU Usage: 45.2%`) with a static 4px line. Systems administration decisions require **velocity and trajectory**, not just instantaneous snapshots.

#### Opportunities:
1. **Telemetry History Sparklines (1m, 5m, 1h):** Replace the static 4px progress line with an honest, continuous sparkline area chart. A 45% CPU reading that is dropping from 99% requires different attention than a 45% reading that has spiked from 2%.
2. **The Halbert Dial / Arch Gauge:** A modernist semi-circular or horizontal dial meter inspired by 1960s Braun audio equipment and aerospace avionics:
   - Clear mechanical tick marks at 25%, 50%, 75%, 90%.
   - Single vermilion needle or calibrated arc fill.
   - Tabular digital readout centered in the dial plate.
3. **Core Load Heatmap:** For multi-core CPUs (e.g. 16 or 32 threads), a 4x4 or 8x4 matrix of micro-cells showing individual thread saturation, making it immediately visible if a single thread is bottlenecked.

```
BRAUN-INSPIRED TACTILE METER (Dashboard Vitals):
┌────────────────────────────────────────────────────────┐
│ CPU LOAD                                  42.8%        │
│ 0      25      50      75      90     100 %            │
│ ├───┼───┼───┼───┼───┼───┼───┼───┼───┼───┤              │
│ [███████████████████░░░░░░░░░░░░░░░░░░░░]              │
│ 1m trend:  ▂▃▅▄▃▂  · Peak: 88.4% · 16 Cores Nominal   │
└────────────────────────────────────────────────────────┘
```

---

### 4.3 GPU & AI Accelerators (`GPU.tsx`)
As local AI execution becomes a core system responsibility, GPU and accelerator monitoring is paramount.

#### Opportunities:
1. **VRAM Topology Breakdown:** When running local LLMs (via Ollama, llama.cpp, or vLLM), VRAM is divided into distinct structures. A segmented horizontal bar must visualize:
   `[ Model Weights (Q4/Q8) | KV Cache Context Window | OS Display Surface | Free Headroom ]`
   This immediately explains to the user *why* an 8B model fits while a 14B model OOMs.
2. **Power Envelope vs. TDP Limit:** Render a bullet chart (`@nivo/bullet`) comparing current power draw (W) against nominal TDP and peak power envelope, showing throttling headroom.
3. **Thermal Throttling Headroom Meter:** Display current temperature against the GPU's known throttling ceiling (e.g. 84°C for NVIDIA, 100°C junction for AMD), highlighting the safety margin.

---

### 4.4 Fleet Compute Cockpit (`Compute.tsx` / `NodeFleetCockpit.tsx`)
In a federated multi-node environment, an administrator needs to assess the health of 5–50 nodes at a glance without reading dozens of text rows.

#### Opportunities:
1. **Cluster Resource Heatmap (`@nivo/heatmap`):** A matrix where rows are nodes (e.g. `halbert-primary`, `worker-01`, `storage-box`) and columns are vitals (`CPU`, `RAM`, `Disk I/O`, `Network`, `Temp`). Color saturation instantly reveals hotspots.
2. **Node Topology & Latency Graph (`@nivo/network`):** A radial or force-directed graph showing the mesh connections between the primary desktop node and satellite instances, with edge thickness/color indicating latency and throughput.
3. **Miniature Node Instrument Cards:** Integrate micro-gauges (sparkline + radial memory arc) directly into the `FleetNodeCard` header.

---

### 4.5 Network Interfaces & Traffic (`Network.tsx`)
Currently, `Network.tsx` is an inventory of interfaces, MAC addresses, and ports.

#### Opportunities:
1. **Bi-Directional Throughput Ribbon:** Real-time stream or mirrored area chart showing Inbound (Rx) vs. Outbound (Tx) traffic with smooth tabular updates.
2. **Port Allocation Map:** A categorical visualization of open listening ports:
   - System / Privileged (< 1024)
   - User Services (Docker, databases, Web)
   - Dynamic / Ephemeral
3. **Interface Hierarchy Tree:** Visual representation of physical NICs bonding into `bond0`, feeding into bridge `br0`, and branching into container veth interfaces.

---

### 4.6 Backups & Storage Snapshots (`Backups.tsx`)
#### Opportunities:
1. **Backup Execution Ribbon (Timeline):** A continuous horizontal timeline showing scheduled runs across the last 30 days:
   - Green tick = clean run with duration and size
   - Amber tick = run succeeded with warnings
   - Red tick = failed run
2. **Snapshot Growth vs. Retention Curve:** Area chart showing total snapshot disk consumption over time against the configured retention window (e.g. hourly for 24h, daily for 7d, weekly for 4w).

---

## 5. Visual Language & Graphic Design Standards for Charts

Every chart component must obey Halbert's design tokens and aesthetic laws.

### 5.1 Color Mapping & Palette Hierarchy
All colors must resolve to tokens in `/shared-tokens/tokens.css`. Never use raw hex or arbitrary Tailwind blues/purples in charts.

| Chart Element | CSS Token | Purpose / Role |
|---|---|---|
| **Chart Ground** | `var(--color-surface)` / `var(--color-surface-sunken)` | Clean paper ground; sunken tray for recessed meters |
| **Grid Lines & Axes** | `var(--color-border-subtle)` / `var(--color-border)` | Crisp 1px hairline scale marks; never heavy |
| **Primary Data Series** | `var(--color-ink)` (#242220) | Main trendline, high-contrast primary metric |
| **Focal Accent** | `var(--color-accent)` (#E05338) | Peak values, critical threshold crossing, active selection |
| **Nominal Status** | `var(--color-status-nominal)` (#2D5A27) | Healthy capacity, normal temperatures, successful jobs |
| **Warning Status** | `var(--color-status-warning)` (#8F5B1E) | Approaching capacity (>75%), elevated thermals |
| **Critical Status** | `var(--color-status-critical)` (#9E2A2B) | Capacity critical (>90%), throttling, failed jobs |
| **Secondary Series** | `var(--color-ink-tertiary)` (#66635F) | Background comparisons, previous period averages |

### 5.2 Typography in Data Visualization
Halbert enforces a strict typography triad:
- **Headings & Metric Labels:** `Space Grotesk` (Modernist Sans) — crisp, geometric, high-legibility.
- **Values, Scales, Ticks & Tooltips:** `JetBrains Mono` with `tabular-nums` — numbers must NEVER cause layout shifts or reflows as values tick up and down.
- **Contextual Explanations:** Serif display reserved for editorial narrative only, never on axes or tick marks.

### 5.3 Tactile Instrument Styling
1. **No Round Candy Corners:** Chart bars should have square or micro-rounded (1px–2px) caps, mimicking physical scale bars, not pill buttons.
2. **Calibrated Ticks:** Where axes exist, provide real scale ticks with human-readable engineering units (`GB`, `MB/s`, `°C`, `W`, `RPM`).
3. **Instrument Tooltips:** Custom HTML tooltips formatted as miniature recessed metal plates with hairline borders:
   - Header with label in Space Grotesk
   - Key-value metrics in tabular mono with units
   - Status badge indicator

---

## 6. Technical Tooling: React + D3 with Nivo (`nivo.rocks`)

### 6.1 Evaluation of Nivo
The user recommended `https://nivo.rocks/`. An architectural assessment confirms it is an exceptional fit for Halbert:

- **Built on D3 + React:** Leverages D3’s mathematical scales, shapes, and layouts with React’s declarative rendering and lifecycle management.
- **Modular Packaging:** Nivo is not a monolithic bloated dependency. Each chart type is its own package (`@nivo/bar`, `@nivo/line`, `@nivo/treemap`, `@nivo/bullet`, `@nivo/heatmap`), allowing Halbert to import only what is used.
- **Deep Theming Engine:** Nivo exposes a top-level `theme` configuration that allows complete override of fonts, axis lines, grid strokes, and tooltips, enabling a 100% match with Halbert’s Olivetti/Daylight palette.
- **Dual SVG / Canvas Rendering:** Offers SVG for crisp, resolution-independent vector rendering, and Canvas for high-frequency real-time telemetry (e.g. 60fps streaming network packets).
- **Superior to Recharts:** Halbert currently has `recharts` in `package.json`, but it is unused (0 imports in `src/`). Recharts defaults to generic SaaS aesthetics, has poor treemap/bullet support, and clunky responsive containers. Nivo provides the exact editorial, high-design sophistication Halbert requires.

### 6.2 The Two-Tier Data Viz Architecture

To maintain performance, prevent bundle bloat, and keep standard UI fast, Halbert should adopt a **Two-Tier Architecture**:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     HALBERT DATA VIZ ARCHITECTURE                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  TIER 1: LIGHTWEIGHT INSTRUMENT PRIMITIVES  (@halbert/design-system)        │
│  • Pure React + SVG, 0 external dependencies                                │
│  • Used for inline table rows, card headers, compact widgets                │
│  • Components:                                                              │
│    - <TactileMeter /> (Horizontal calibrated gauge with ticks)              │
│    - <SegmentedBar /> (Multi-category storage/memory allocation)            │
│    - <Sparkline /> (Compact trendline for CPU/RAM history)                  │
│    - <RadialDial /> (Avionics-style circular dial)                          │
│                                                                             │
│  TIER 2: ADVANCED ANALYTICAL VISUALIZATIONS (Nivo: React + D3)              │
│  • Modular `@nivo/*` packages for rich interactive exploration              │
│  • Used in full-page diagnostics, deep dives, and modal inspectors          │
│  • Components:                                                              │
│    - <StorageTreemap /> (`@nivo/treemap` for disk usage breakdown)          │
│    - <TelemetryStream /> (`@nivo/line` / `@nivo/stream` for time-series)    │
│    - <FleetHeatmap /> (`@nivo/heatmap` for multi-node status matrix)        │
│    - <PowerBullet /> (`@nivo/bullet` for TDP/throttling headroom)           │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 6.3 Canonical Nivo Halbert Theme Configuration
When implementing Nivo charts, this theme object binds Nivo directly to Halbert's design tokens:

```typescript
// halbert_core/dashboard/frontend/src/lib/chartTheme.ts
export const halbertNivoTheme = {
  background: 'transparent',
  text: {
    fontFamily: 'Space Grotesk, sans-serif',
    fontSize: 12,
    fill: 'var(--color-ink)',
    outlineWidth: 0,
    outlineColor: 'transparent',
  },
  axis: {
    domain: {
      line: {
        stroke: 'var(--color-border)',
        strokeWidth: 1,
      },
    },
    ticks: {
      line: {
        stroke: 'var(--color-border)',
        strokeWidth: 1,
      },
      text: {
        fontFamily: 'JetBrains Mono, monospace',
        fontSize: 10,
        fill: 'var(--color-ink-tertiary)',
      },
    },
    legend: {
      text: {
        fontFamily: 'Space Grotesk, sans-serif',
        fontSize: 11,
        fontWeight: 600,
        fill: 'var(--color-ink-secondary)',
      },
    },
  },
  grid: {
    line: {
      stroke: 'var(--color-border-subtle)',
      strokeWidth: 1,
      strokeDasharray: '2 2',
    },
  },
  tooltip: {
    container: {
      background: 'var(--color-surface)',
      color: 'var(--color-ink)',
      fontFamily: 'Space Grotesk, sans-serif',
      fontSize: 12,
      borderRadius: '2px',
      border: '1px solid var(--color-border)',
      boxShadow: 'var(--shadow-sm)',
      padding: '8px 12px',
    },
  },
}
```

---

## 7. Implementation Roadmap & Execution Plan

### Phase 1: Storage Page Redesign & Tier 1 Primitives (Immediate Priority)
- **Goal:** Fix the layout mess on the Storage page.
- **Tasks:**
  1. Build `<SegmentedBar />` and `<TactileMeter />` in `@halbert/design-system`.
  2. Refactor `Storage.tsx`:
     - Eliminate the variable `gridTemplateColumns: 'auto 1fr auto auto'`.
     - Standardize layout on a rigid two-tier structure: Title/Mount header above a full-width calibrated gauge.
     - Implement multi-segment capacity breakdown (Data vs. Meta vs. Free).
  3. Verify against WCAG contrast rules with `scripts/check_contrast.py`.

### Phase 2: System Vitals & Dashboard Transformation
- **Goal:** Upgrade the Dashboard and navigation rail from static numbers to dynamic instruments.
- **Tasks:**
  1. Implement `<Sparkline />` in `@halbert/design-system` for 1m/5m telemetry trends.
  2. Replace 4px progress lines on `Dashboard.tsx` with calibrated tactile meters and sparklines.
  3. Add thread/core load heatmap on CPU inspector.

### Phase 3: GPU & AI Accelerator Visualizer
- **Goal:** Provide first-class telemetry for local inference hardware.
- **Tasks:**
  1. Build VRAM memory topology bar (Model weights, KV cache, system, headroom).
  2. Build power and thermal headroom bullet meters (`@nivo/bullet`).
  3. Integrate into `GPU.tsx`.

### Phase 4: Fleet & Network Analytical Charts (Nivo Integration)
- **Goal:** High-density multi-node and network traffic analysis.
- **Tasks:**
  1. Install modular Nivo packages (`@nivo/heatmap`, `@nivo/treemap`, `@nivo/line`).
  2. Deprecate and remove unused `recharts` dependency.
  3. Build `FleetHeatmap` for `Compute.tsx` / `NodeFleetCockpit.tsx`.
  4. Build `NetworkThroughputStream` for `Network.tsx`.
  5. Build interactive Disk Space Treemap for storage deep dive.

---

## 8. Summary Checklist for Any New Visualization

Before any new data visualization merges into Halbert, it must pass these criteria:
- [ ] **Baseline Alignment:** Does the chart align to a fixed vertical grid, completely independent of text label lengths?
- [ ] **Token Adherence:** Are all colors derived from `tokens.css` with 0 hardcoded hex values?
- [ ] **Typography Triad:** Are titles in Space Grotesk and all numerical readings/scales in JetBrains Mono with tabular figures?
- [ ] **Computational Honesty:** Does the chart represent real measured telemetry without fake smoothing, and explicitly show `[Sensor offline]` if unmeasured?
- [ ] **Design Restraint:** Is the Vermilion accent reserved for focal/critical conditions, rather than used as decorative wallpaper?
