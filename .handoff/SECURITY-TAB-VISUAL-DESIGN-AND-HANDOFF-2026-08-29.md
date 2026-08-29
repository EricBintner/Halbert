# Halbert Security Tab: Visual Design Review & Design System Specification

**Date:** 2026-08-29  
**Status:** Active Design Review & Component Specification  
**Target:** `halbert_core/halbert_core/dashboard/frontend/src/pages/Settings.tsx` & `.handoff/`  
**Reads With:**
- [`documentation/design/BRAND-GUIDELINES-AND-AESTHETIC.md`](file:///Volumes/4TB-BAD/Halbert/documentation/design/BRAND-GUIDELINES-AND-AESTHETIC.md) — Colour Law, Surface Licence, and the Vermilion Budget
- [`documentation/design/DESIGN-SYSTEM-SPEC.md`](file:///Volumes/4TB-BAD/Halbert/documentation/design/DESIGN-SYSTEM-SPEC.md) — Token Foundations and Spatial Grid
- [`documentation/design/SETTINGS-REDESIGN-2026-08-27.md`](file:///Volumes/4TB-BAD/Halbert/documentation/design/SETTINGS-REDESIGN-2026-08-27.md) — Settings Information Architecture & Master-Detail Navigation
- [`documentation/design/APP-AESTHETIC-AUDIT-AND-REFINEMENT-PLAN-2026-08-28.md`](file:///Volumes/4TB-BAD/Halbert/documentation/design/APP-AESTHETIC-AUDIT-AND-REFINEMENT-PLAN-2026-08-28.md) — Desktop App Shell & Typography Harmonization
- [`.handoff/SECURITY-REVIEW-REQUEST-2026-08-29.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/SECURITY-REVIEW-REQUEST-2026-08-29.md) — Original Review Request

---

## 1. Executive Summary & Review Intent

This document reviews the proposed UX improvements for the **MCP Trust Boundary & Security Settings** through the lens of Halbert’s evolving **Daylight Mid-Century Modern Design System** (inspired by Dieter Rams / Braun, Olivetti, Vignelli's Unigrid, and the 1975 NASA Graphic Standards).

While Halbert does not yet have a single unified component library package across all views, every new surface must strictly adhere to the brand laws and design tokens established in `BRAND-GUIDELINES-AND-AESTHETIC.md` and `/shared-tokens/tokens.css`.

This review evaluates:
1. **Visual Language Alignment:** Eliminating generic SaaS tropes (blue buttons, harsh red alerts, unbounded textareas) in favor of machined physical instruments.
2. **The Vermilion Budget & Status Pigments:** Enforcing strict color law across nominal, warning, and critical states.
3. **Typography Hierarchy:** Applying the triad (Modernist Sans `Space Grotesk`, Tabular Mono `JetBrains Mono`, and Micro-Labels).
4. **Concrete Component Specs:** Detailed component anatomy for the 6 requested security features.

---

## 2. Visual Design Review & Design System Alignment

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      DESIGN SYSTEM ALIGNMENT AUDIT                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  [ PILLAR 1: DAYLIGHT & PAPER ] ──▶ Base canvas: Warm linen (#F7F4EE).      │
│                                     Plates: #FFFFFF with 1px hairline.      │
│                                     Data trays: Recessed bone (#EFECE4).    │
│                                                                             │
│  [ PILLAR 2: VERMILION BUDGET ] ──▶ Vermilion (#D34E24) used ONLY for the   │
│                                     single active focus/CTA.                │
│                                     Critical danger uses Terracotta Crimson.│
│                                                                             │
│  [ PILLAR 3: TYPOGRAPHIC TRIAD ] ─▶ Headers: Space Grotesk (Sans).          │
│                                     Keys/Paths/Numbers: JetBrains (Mono).   │
│                                     Labels: Uppercase mono micro-captions.  │
│                                                                             │
│  [ PILLAR 4: INSTRUMENT TACTILITY]▶ Physical 3-state rocker segment pills. │
│                                     Machined tag chips with 1px borders.    │
│                                                                             │
│  [ PILLAR 5: HONESTY OF STATE ] ──▶ Live telemetry counts on every tier.   │
│                                     Explicit text + icon (never color only).│
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.1 Audit Findings & Corrections for the Proposal

| Feature Area | Initial Proposal / Current Code | Design System Rule / Correction |
|---|---|---|
| **Tier 1 Routing Picker** | 3 standard shadcn buttons in a row with default/outline variants. | **Mechanical Segmented Rocker:** A recessed tray (`bg-surface-subtle`) holding a 3-segment pill control. Active state uses elevated surface (`bg-surface shadow-sm text-ink font-medium`). |
| **Tier 2 Danger State** | Generic Tailwind `border-destructive bg-destructive/10`. | **Terracotta Crimson Plate:** Uses `--color-status-critical` (`#C83E2D`) with tinted ground (`#FDF2F0`). Never use Vermilion for danger/error (Brand Rule §3.2). |
| **Key & File Lists** | Unbounded `<textarea>` with save on blur. | **Machined Chip Array & Recessed Input Tray:** Active paths/keys rendered as tabular mono tags (`font-mono text-xs bg-surface border border-line`) with explicit removal triggers. |
| **Telemetry Summary** | Static prose paragraphs. | **Instrument Header Plate:** A horizontal recessed telemetry plate with tabular mono numbers (`font-mono tabular-nums font-semibold`), giving immediate sensory feedback on classified values. |
| **Typography on Keys/Paths** | Rendered in default sans body font. | **Strict Tabular Mono:** All file paths (`/etc/hosts`), config keys (`API_KEY`), counts (`12`), and entropy values (`4.8 bits`) must render in `font-mono`. |
| **Escape Hatch Friction** | Simple two-button toggle. | **Physical Shutter Modal:** High-friction modal requiring phrase typing (`EXPOSE SECRETS`) + session TTL toggle, framed with a terracotta critical border. |

---

## 3. Design System Token Mapping (Security Surface)

All components in the Security tab must reference standard tokens rather than hardcoded hex values:

```css
/* Surface Taxonomy */
--hb-canvas:           var(--color-canvas);          /* #F7F4EE — Base background */
--hb-plate:            var(--color-surface);         /* #FFFFFF — Elevated card surface */
--hb-tray:             var(--color-surface-subtle);  /* #EFECE4 — Recessed container / inputs */
--hb-border:           var(--color-border);          /* #E2DDD3 — 1px hairline boundaries */

/* Typography */
--hb-font-heading:     var(--font-sans);             /* Space Grotesk */
--hb-font-body:        var(--font-sans);             /* Space Grotesk / Inter */
--hb-font-mono:        var(--font-mono);             /* JetBrains Mono (Paths, Keys, Telemetry) */

/* Status & Accents */
--hb-accent:           var(--color-accent);          /* #D34E24 — Single primary action */
--hb-accent-strong:    var(--color-accent-strong);   /* #B83E18 — Active button fill (AA safe) */
--hb-nominal:          var(--color-status-nominal);  /* #2D7A56 — Eames Forest Green (Tier 0 / Safe) */
--hb-nominal-bg:       #EEF6F2;
--hb-warning:          var(--color-status-warning);  /* #C4781C — Braun Amber (Tier 1 Guarded) */
--hb-warning-bg:       #FDF8F0;
--hb-critical:         var(--color-status-critical); /* #C83E2D — Terracotta Crimson (Tier 2 Unlocked) */
--hb-critical-bg:      #FDF2F0;
--hb-telemetry:        var(--color-status-telemetry);/* #386C8A — Slate Teal */
--hb-telemetry-bg:     #F0F6F9;
```

---

## 4. Detailed Component Specifications

### 4.1 Component 1: `TrustBoundaryTelemetryBar` (The Scope Instrument)
Replaces the static 3-paragraph text with a live, compact telemetry plate at the top of the tab.

* **Container:** `bg-surface-subtle border border-border rounded-lg p-4`
* **Layout:** Flex row with 3 diagnostic meters + action drawer trigger.
* **Meters:**
  1. **Tier 0 (Public):** `[Icon: Globe]` `font-mono font-bold text-foreground` `84` / `<span className="font-mono text-xs text-muted-foreground">PUBLIC</span>`
  2. **Tier 1 (Operational):** `[Icon: Sliders]` `font-mono font-bold text-foreground` `28` / `<span className="font-mono text-xs text-muted-foreground">OPERATIONAL</span>`
  3. **Tier 2 (Secrets):** `[Icon: ShieldCheck]` `font-mono font-bold text-foreground` `12` / `<span className="font-mono text-xs text-muted-foreground">PROTECTED</span>`
* **Right Action:** Subtle outline button `[ 👁️ Preview AI Response ]` opening a simulation drawer.

---

### 4.2 Component 2: `Tier1RockerControl` (Mechanical Segmented Switch)
Replaces three disconnected buttons with a cohesive segmented rocker switch.

```tsx
<div className="bg-surface-subtle p-1 rounded-lg border border-border inline-flex w-full grid grid-cols-3 gap-1">
  <button className="flex flex-col items-center py-2 px-3 rounded-md bg-surface text-foreground font-medium shadow-xs border border-border/60 transition-all">
    <span className="font-sans text-sm font-semibold">Cloud OK</span>
    <span className="font-mono text-[11px] text-muted-foreground">Raw to cloud</span>
  </button>
  <button className="flex flex-col items-center py-2 px-3 rounded-md text-muted-foreground hover:text-foreground transition-all">
    <span className="font-sans text-sm font-semibold">Local Only</span>
    <span className="font-mono text-[11px] text-muted-foreground">Describe only</span>
  </button>
  <button className="flex flex-col items-center py-2 px-3 rounded-md text-muted-foreground hover:text-foreground transition-all">
    <span className="font-sans text-sm font-semibold">Redact</span>
    <span className="font-mono text-[11px] text-muted-foreground">Strip value</span>
  </button>
</div>
```

---

### 4.3 Component 3: `Tier2StateCard` (Dual-State Physical Vault)
Implements dynamic visual state transformation based on `secret_tier`.

#### State A: Locked & Secure (`local_only`)
* **Card Surface:** `bg-surface border border-border`
* **Badge:** `<Badge className="bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border border-emerald-500/20 font-mono text-xs">🔒 LOCKED (LOCAL ONLY)</Badge>`
* **Description:** Crisp sans typography explaining metadata-only guarantees.
* **Escape Hatch Trigger:** Low-contrast subtle disclosure button `[ Unlock Cloud Access... ]` with amber warning pip.

#### State B: Compromised / Unlocked (`cloud_ok_acknowledged`)
* **Card Surface:** `bg-critical-bg/40 border-2 border-critical shadow-sm`
* **Badge:** `<Badge className="bg-critical text-white font-mono text-xs animate-pulse">⚠️ SECRETS EXPOSED TO CLOUD</Badge>`
* **Action Bar:** Prominent primary button: `[ 🔒 Re-lock Secrets Immediately ]` with `bg-accent-strong text-white font-semibold`.

---

### 4.4 Component 4: `EscapeHatchConfirmationModal` (High-Friction Shutter)
A modal dialog triggered when attempting to unlock Tier 2.

* **Backdrop:** `bg-black/40 backdrop-blur-xs`
* **Header:** Icon `AlertOctagon` in Terracotta Crimson (`text-critical`), Title: *"Expose Machine Secrets to Cloud LLMs?"*
* **Content:**
  - Clear explanation: *"This will transmit raw passwords, private keys, and API tokens to external inference vendor logging pipelines."*
  - **TTL Selection Radio Group:**
    - `(•) 1 Hour (Recommended — auto-relocks)`
    - `( ) Until Halbert restarts`
    - `( ) Permanent (Dangerous)`
  - **Phrase Input:**
    - Label: `To proceed, type EXPOSE SECRETS below:`
    - Input: `font-mono tracking-wide border-critical/50 focus:border-critical focus:ring-critical`
* **Buttons:**
  - Cancel: `[ Cancel & Keep Locked ]` (Default focused)
  - Confirm: `[ I Accept the Risk — Expose Secrets ]` (Disabled until exact phrase is entered, styled in `bg-critical text-white`).

---

### 4.5 Component 5: `MachinedTagInput` (For `public_files`, `extra_secret_keys`, `cloud_ok_keys`)
Replaces multi-line textareas with tag lists and autocomplete.

* **Container:** `bg-surface-subtle border border-border rounded-lg p-3 space-y-2`
* **Chip Elements:**
  ```tsx
  <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-surface border border-border text-xs font-mono shadow-2xs">
    <span className="text-foreground">/etc/hosts</span>
    <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" title="File verified on host" />
    <button className="text-muted-foreground hover:text-foreground ml-1">✕</button>
  </div>
  ```
* **Input Row:**
  - Combobox/Input with `font-mono text-xs placeholder:font-sans placeholder:text-muted-foreground bg-surface border border-input rounded-md px-3 py-1.5`
  - Subtle `[ + Add ]` button.

---

## 5. UI Layout Mockup (Daylight Alignment)

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│  SYSTEM & SECURITY  ▶  MCP TRUST BOUNDARY                                              │
├────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                        │
│  ┌─ 📊 TELEMETRY SCOPE ──────────────────────────────────────────────────────────────┐ │
│  │  84 Tier 0 (Public)   ·   28 Tier 1 (Operational)   ·   12 Tier 2 (Protected)     │ │
│  │                                                   [ 👁️ Preview AI Response ]       │ │
│  └────────────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                        │
│  ┌─ TIER 1 — OPERATIONAL VALUES ─────────────────────────────────────────────────────┐ │
│  │  Machine context, open ports, firewall rules, and internal IP addresses.           │ │
│  │                                                                                    │ │
│  │  ┌─────────────────────────┬─────────────────────────┬──────────────────────────┐  │ │
│  │  │  [●] Cloud OK           │  [ ] Local Only         │  [ ] Redact              │  │ │
│  │  │      Raw value to cloud │      Describe only      │      Strip value         │  │ │
│  │  └─────────────────────────┴─────────────────────────┴──────────────────────────┘  │ │
│  │  ℹ️ 28 operational values will be accessible to cloud models for maximum reasoning. │ │
│  └────────────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                        │
│  ┌─ TIER 2 — SECRETS & CREDENTIALS ───────────────────────── [ 🔒 LOCKED (LOCAL ONLY) ] ┐ │
│  │  Passwords, private keys, tokens, and authorization headers.                      │ │
│  │  Deterministic metadata only (length, charset, entropy). No LLM in the boundary.   │ │
│  │                                                                                    │ │
│  │  ┌─ ⚠️ Advanced Override ────────────────────────────────────────────────────────┐ │ │
│  │  │  Allow cloud models to read raw secrets in plaintext.                         │ │ │
│  │  │  [ Unlock Cloud Access... ]                                                   │ │ │
│  │  └───────────────────────────────────────────────────────────────────────────────┘ │ │
│  └────────────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                        │
│  ┌─ PER-KEY CLOUD ESCAPE HATCH (0 Active Exceptions) ────────────────────────────────┐ │
│  │  Allow specific non-critical keys to bypass Tier 2 without unlocking all secrets.  │ │
│  │  ┌────────────────────────────────────────────────────────┬─────────────────────┐  │ │
│  │  │ Add key name (e.g. WEATHER_API_KEY)                    │ [ + Add Exception ] │  │ │
│  │  └────────────────────────────────────────────────────────┴─────────────────────┘  │ │
│  └────────────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                        │
│  ┌─ FILE & KEY CLASSIFICATION ───────────────────────────────────────────────────────┐ │
│  │  Public Files (Tier 0 Floor):                                                      │ │
│  │  [ /etc/hosts 🟢 ✕ ] [ /etc/hostname 🟢 ✕ ] [ /etc/fstab 🟢 ✕ ]  [ + Add Path ]   │ │
│  │                                                                                    │ │
│  │  Extra Secret Keys (Tier 2 Enforcement):                                           │ │
│  │  [ serial ✕ ] [ license_key ✕ ] [ activation_code ✕ ]             [ + Add Key ]    │ │
│  └────────────────────────────────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 6. Implementation Roadmap for Frontend Engineers

1. **Step 1: Extract Tokens & Subcomponents**
   - Create `SecurityTelemetryBar.tsx`
   - Create `SegmentedRocker.tsx`
   - Create `MachinedTagList.tsx`
   - Create `EscapeHatchModal.tsx`
2. **Step 2: Refactor `SecuritySettings` in `Settings.tsx`**
   - Replace raw textareas with `MachinedTagList`.
   - Replace 3-button Tier 1 row with `SegmentedRocker`.
   - Wire the modal to handle typed-phrase confirmation + TTL expiry.
3. **Step 3: Connect Live Telemetry Endpoints**
   - Hook into `GET /api/settings/security/telemetry` or calculate from live config inventory.
