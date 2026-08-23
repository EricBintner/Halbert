# Halbert Component Architecture & Catalog

**Version:** 1.0.0  
**Date:** 2026-08-23  
**Status:** Approved Component Architecture Specification  
**Reads with:** `documentation/design/DESIGN-SYSTEM-SPEC.md`, `documentation/design/USER-JOURNEY-METHODOLOGY.md`  

---

## 1. Component System Overview & Audit

Halbert's UI is divided into two target deliverables that share the same underlying visual tokens and component philosophies:
1. **Core Desktop App (Tauri + React + Radix UI + Tailwind):** The conversational host interface, summonable domain modules, and approval gates.
2. **Marketing Experience (`marketing/web/` - Vite + React 19 + Tailwind 4 + GSAP):** The single-page scrollytelling introduction featuring animated CLI/IDE demonstrators.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       HALBERT COMPONENT HIERARCHY                           │
│                                                                             │
│  [ LAYOUTS & STAGES ]                                                       │
│  • EngagedWorkspace  • BrowsingGrid  • AmbientTrayHUD  • MarketingHeroStage │
│                                                                             │
│  [ ORGANISMS ]                                                              │
│  • TerminalFrame     • DesktopWindow    • AgentSpine   • ConfigDiffInspector│
│  • VitalsMatrix      • ApprovalGate     • EvidenceDrawer • TheBeingHero     │
│                                                                             │
│  [ MOLECULES ]                                                              │
│  • PromptBar         • WhyChip          • TelemetryGauge • ToolCard         │
│  • DiffLine          • RationaleCard    • WaitlistCapture • BreadcrumbTrail │
│                                                                             │
│  [ ATOMS ]                                                                  │
│  • Button            • Badge            • Input          • Hairline         │
│  • StatusPip         • IconMark         • HotkeyBadge    • SurfaceCard      │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Existing Component Audit & Migration Map

A review of existing components in `halbert_core/dashboard/frontend/src/components/` identifies necessary upgrades to align with the Daylight Mid-Century Design System:

| Existing Component | Current Location | Current State / Deficit | Modernization & Harmonization Action |
|---|---|---|---|
| `AgentChat.tsx` | `src/components/agent/` | Heavy dark backgrounds; chat bubbles disconnected from domain modules | Refactor into `AgentSpine.tsx` using daylight canvas (`#F7F5F0`), inline `WhyChip` anchors, and dynamic module summoning events. |
| `DiffBlock.tsx` | `src/components/agent/` | Monolithic diff display lacking AST context & blast-radius estimates | Upgrade to `ConfigDiffInspector.tsx` with side-by-side AST view, drop-in precedence resolution, and direct approval triggers. |
| `ThinkingPanel.tsx` | `src/components/agent/` | Generic pulsing loader with vague text | Convert to `ToolExecutionCard.tsx` with clear 1960s mechanical status pill, live elapsed timer, and SourcePrep retrieval tags. |
| `ConfirmationDialog.tsx` | `src/components/agent/` | Generic modal alert without dry-run consequence preview | Replace with `ApprovalGate.tsx` featuring inline blast radius, diff preview, and rollback manifest summary. |
| `SidePanel.tsx` | `src/components/` | 92KB mega-component acting as traditional multi-tab dashboard | Deconstruct into autonomous, summonable domain modules (`VitalsModule`, `StorageSensorsModule`, `EvidenceDrawer`). |
| `WhyOverlay.tsx` | `src/components/ui/` | Modal overlay that obscures conversation context | Refactor into `WhyCard.tsx` popover anchored directly to the inline `WhyChip`. |

---

## 3. Atoms (Foundational Elements)

### 3.1 `Button`
The primary interaction element. Replaces generic shadcn styling with vintage tactile buttons.

- **Variants:**
  - `primary`: Background `--color-accent` (`#D34E24`), text `#FFFFFF`, hover `--color-accent-hover` (`#B83E18`), shadow `0 2px 8px rgba(211,78,36,0.25)`.
  - `secondary`: Background `#FFFFFF`, border `1px solid var(--color-hairline-strong)`, text `--color-ink`, hover `bg-surface-subtle`.
  - `ghost`: Transparent background, hover `bg-surface-subtle`, text `--color-ink-secondary`.
  - `destructive`: Background `--color-status-error` (`#C83E2D`), text `#FFFFFF`.
- **Props:** `variant`, `size` (`sm` 32px, `md` 40px, `lg` 48px), `iconLeft`, `iconRight`, `loading`, `disabled`.

### 3.2 `WhyChip`
The signature interaction atom. Represents Halbert's Law of Four Whys in compact form.

```
┌──────────────────────────────────────────────┐
│ [ ● 42d ]  [ ⚠ 3 Read Errors ]  [ SSH:2222 ] │ ◄ Inset tactile pill with status pip
└──────────────────────────────────────────────┘
```

- **Visuals:** Height `24px`, padding `0 8px`, border-radius `9999px`, font-size `0.75rem` (`12px`), font-weight `600`, tracking `+0.02em`.
- **States:**
  - `nominal`: Background `#EEF6F2`, border `1px solid #C2E0D1`, text `#2D7A56`.
  - `attention`: Background `#FDF8F0`, border `1px solid #F3DBB3`, text `#C4781C`.
  - `critical`: Background `#FDF2F0`, border `1px solid #F5C2BC`, text `#C83E2D`.
  - `info`: Background `#F0F6F9`, border `1px solid #BFD8E6`, text `#386C8A`.
- **Interactivity:** Clicking summons the corresponding `WhyCard` popover or summons the domain module into the right context pane.

### 3.3 `StatusPip`
A micro-indicator showing real-time heartbeat and system states.
- **Sizes:** `6px` / `8px` / `10px`.
- **Animation:** Gentle ambient pulse (`scale 1.0 -> 1.15 -> 1.0`, opacity `0.9 -> 1.0 -> 0.9` over `3s`).

---

## 4. Molecules (Composed Units)

### 4.1 `PromptBar`
The universal conversational command bar.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ > ask halbert or type a system command...             [⌘K Modules]  [⏎ Send]│
└─────────────────────────────────────────────────────────────────────────────┘
```

- **Styling:** Background `#FFFFFF`, border `1px solid var(--color-hairline-strong)`, border-radius `14px`, inner padding `12px 16px`, shadow `0 4px 16px -2px rgba(26,25,24,0.06)`.
- **Features:**
  - Prefix prompt symbol `>` in Olivetti Vermilion (`#D34E24`).
  - Auto-resizing textarea with hotkey triggers (`Enter` to submit, `Shift+Enter` for newline).
  - Attached hotkey pills (`Cmd+K` module picker, `Tab` autocomplete suggestion).

### 4.2 `ToolExecutionCard`
Visual representation of Halbert's active sensory inspections and memory recalls.

```
┌──────────────────────────────────────────────────────────┐
│ ⚙ Checking vitals via read_sensors…               700ms │
│ └─ CPU 45°C · load 0.15 · /dev/nvme0n1 healthy          │
└──────────────────────────────────────────────────────────┘
```

- **Container:** Background `#EFECE4`, border `1px solid #DFD9CD`, border-radius `8px`, padding `10px 14px`.
- **Typography:** Tool name in `JetBrains Mono` (`13px`, `#5E5B56`), output result in `#1A1918`.
- **Progress:** Subtle vermilion hairline progress bar along the bottom border during active execution.

### 4.3 `TelemetryGauge`
Precision mid-century dial / bar displaying CPU, memory, or thermal physiology.

- **Presentation:** Minimalist horizontal pill track with calibrated tick marks at 25%, 50%, 75%, 100%.
- **Colors:** Value fill dynamically shifts from botanical green (`#2D7A56`) to amber ochre (`#C4781C`) to terracotta red (`#C83E2D`).

---

## 5. Organisms (High-Order Interactive Systems)

### 5.1 `TerminalFrame` (`TerminalFrame.jsx`)
The centerpiece of both the marketing hero and the product's console mode.

```
┌──────────────────────────────────────────────────────────────┐
│ [•] [•] [•]  halbert — ubuntu-server-01               ● LIVE │ ◄ 42px Warm Titlebar
├──────────────────────────────────────────────────────────────┤
│                                                              │
│ > how are you doing?                                         │ ◄ Prompt in bold graphite
│                                                              │
│   [ ⚙ read_sensors ] CPU 45°C · load 0.15 · nvme0n1 OK       │ ◄ Tool Result Pill
│                                                              │
│ I'm ubuntu-server-01. I've been up 42 days.                  │ ◄ Typewriter Agent Speech
│ My primary drive logged three read errors this morning.      │
│ I'd keep an eye on that drive. Want a SMART test?            │
│                                                              │
│ [ Run SMART Test ]  [ Show Storage Health ]  [ Snooze 24h ]  │ ◄ Inline Action Suggestions
└──────────────────────────────────────────────────────────────┘
```

**Props Interface:**
```typescript
interface TerminalFrameProps {
  title?: string;
  hostname?: string;
  statusText?: string;
  isLive?: boolean;
  script?: CliScript;
  autoPlay?: boolean;
  loop?: boolean;
  theme?: 'daylight' | 'paper-dark';
  className?: string;
  onActionSelect?: (actionId: string) => void;
}
```

### 5.2 `DesktopWindow` (`DesktopWindow.jsx`)
Mockup container representing the Tauri desktop application.

```
┌────────────────────────────────────────────────────────────────────────┐
│ (x) (-) (+)   Halbert — Host Intelligence OS           [v2026.8] [ ⚙ ] │
├───────────────────────────────────┬────────────────────────────────────┤
│ CONVERSATION SPINE (50%)          │ SUMMONED CONTEXT MODULE (50%)      │
│                                   │                                    │
│ [Agent Dialogue Stream]           │ [Live Vitals / Config Diff View]   │
│                                   │                                    │
│ > Why is SSH on port 2222?        │ File: /etc/ssh/sshd_config.d/      │
│                                   │ - Port 22                          │
│ Halbert: "I moved SSH on July 14  │ + Port 2222                        │
│ to avoid scan noise."             │ [View Rationale]  [Rollback Diff]  │
│                                   │                                    │
│ [Prompt Input Bar]                │ [Pin Module] [Dismiss Module]      │
└───────────────────────────────────┴────────────────────────────────────┘
```

### 5.3 `ApprovalGate` (`ApprovalGate.tsx`)
The safety-first autonomy container for destructive operations.

- **Contents:**
  1. **Operation Header:** Target file/daemon (`/etc/fstab`), risk tier (`HIGH RISK`), privilege requirement (`sudo / polkit`).
  2. **Atomic Diff:** Syntax-highlighted unified diff showing precise line changes.
  3. **Blast Radius Estimate:** Services impacted, downtime risk, and dependency cascade.
  4. **Rollback Guarantee:** Pre-computed rollback manifest and snapshot ID.
  5. **Actions:** `[Approve & Execute (Polkit)]` (Vermilion), `[Dry-Run Only]`, `[Cancel]`.

### 5.4 `ConfigDiffInspector` (`ConfigDiffInspector.tsx`)
AST-aware configuration diff viewer with precedence resolution.

- Visualizes drop-in glob precedence (e.g. `10-default.conf` vs `50-custom.conf` vs `99-cloud-init.conf`).
- Highlights active overriding keys vs shadowed keys with intuitive strikethroughs and provenance tooltips.

---

## 6. Layout Templates & Stages

### 6.1 `EngagedWorkspace` (Desktop App Default)
- Two-column CSS Grid / Flexbox layout with draggable splitter.
- Left column: Persistent conversational timeline with date dividers.
- Right column: Context stage with dynamic module transitions driven by GSAP `--ease-smooth`.

### 6.2 `MarketingHeroStage` (Marketing Page)
- 2-column split on desktop (`1200px` container): Left column editorial value prop + waitlist form; right column live animated `TerminalFrame`.
- Fully responsive: Stacks gracefully on tablet and mobile viewports (`<768px`) with sticky conversation highlights.

---

## 7. Component Summary Table

| Component Name | Type | Target Environment | Primary Props / APIs |
|---|---|---|---|
| `Button` | Atom | Shared | `variant, size, icon, loading, disabled` |
| `WhyChip` | Atom | Shared | `status, severity, label, count, onClick` |
| `StatusPip` | Atom | Shared | `state ('live'\|'idle'\|'alert'), size, pulse` |
| `PromptBar` | Molecule | Desktop App | `value, onChange, onSubmit, hotkeysEnabled` |
| `ToolExecutionCard` | Molecule | Shared | `toolName, args, status, durationMs, result` |
| `TelemetryGauge` | Molecule | Desktop App | `label, value, min, max, unit, status` |
| `DiffLine` | Molecule | Desktop App | `type ('add'\|'del'\|'same'), lineNo, content` |
| `WaitlistCapture` | Molecule | Marketing Web | `onSubmit, placeholder, buttonText, successMessage` |
| `TerminalFrame` | Organism | Shared | `title, script, autoPlay, loop, theme` |
| `DesktopWindow` | Organism | Shared | `title, activeTab, leftPane, rightPane` |
| `ApprovalGate` | Organism | Desktop App | `target, riskLevel, diff, blastRadius, onApprove` |
| `ConfigDiffInspector`| Organism | Desktop App | `filePath, original, modified, precedenceGraph` |
| `VitalsMatrix` | Organism | Desktop App | `cpu, memory, disk, network, uptime` |
| `EvidenceDrawer` | Organism | Desktop App | `logStream, sourcePrepCitations, rawTelemetry` |
