# Review Packet 08: UI/UX Redesign, Settings Megafile Decomposition & Daylight Design System

**Review Level:** **Fable Level Review**  
**Domain:** Frontend Architecture, Design System Tokens, Component Decomposition, Information Architecture, and Marketing Web Suite  
**Target Date:** 2026-08-29  
**Status:** Ready for Frontend Architectural & Visual Review  

---

## 1. Executive Summary & Review Scope

Halbert's user interface has experienced explosive growth, resulting in two distinct areas requiring architectural stabilization:
1. **Frontend Sprawl & Megafile Technical Debt:** The main dashboard grew to 14 top-level sidebar items across 5 fragmented sections, while `Settings.tsx` ballooned into a **3,105-line megafile** containing dozens of heterogeneous state slices (LLM models, MCP trust boundaries, vision consent, being personality, and indexing parameters).
2. **Daylight Mid-Century Modern Design System:** A formalized design language (inspired by Dieter Rams, Olivetti, and 1970s NASA graphics) was specified in `BRAND-GUIDELINES-AND-AESTHETIC.md` and prototyped across 5 marketing website editions (`web-v2` through `web-v6`). The newly redesigned Security Settings Tab (`SecurityComponents.tsx`) serves as the first fully compliant dashboard implementation of this design system.

The comprehensive plan (`.handoff/HALBERT-UI-REDESIGN-PLAN.md`) defines:
- Decomposing the 14 navigation items into 4 primary domains (**Being / Ambient Home**, **Intelligence & Findings**, **Sovereign Host Controls**, **Settings & Architecture**).
- Decomposing `Settings.tsx` into 6 isolated, lazy-loaded tab components.
- Reconciling redundant pages (e.g. merging `Security.tsx` system findings into Intelligence & Findings).

The reviewing model (**Fable**) must review the decomposition blueprint, evaluate React component state isolation, audit Tailwind/token styling, and verify responsiveness and accessibility (ARIA).

---

## 2. Planning & Design Documents (Past 2 Weeks)

| Document | Purpose | Key Themes |
|---|---|---|
| [`.handoff/HALBERT-UI-REDESIGN-PLAN.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/HALBERT-UI-REDESIGN-PLAN.md) | Master UI/UX Redesign Specification | 4 primary domains, `Settings.tsx` decomposition, dual-mode shell |
| [`.handoff/HALBERT-UI-REDESIGN-INVESTIGATION-REQUEST.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/HALBERT-UI-REDESIGN-INVESTIGATION-REQUEST.md) | Investigation request for UI cleanup | Audit of 3,105-line file, sidebar clutter, redundant routes |
| [`documentation/design/SETTINGS-REDESIGN-2026-08-27.md`](file:///Volumes/4TB-BAD/Halbert/documentation/design/SETTINGS-REDESIGN-2026-08-27.md) | Settings information architecture | Master-detail layout, progressive disclosure, token mapping |
| [`documentation/design/BRAND-GUIDELINES-AND-AESTHETIC.md`](file:///Volumes/4TB-BAD/Halbert/documentation/design/BRAND-GUIDELINES-AND-AESTHETIC.md) | Design philosophy & brand laws | Daylight linen canvas, vermilion budget, tactile physical instruments |
| [`documentation/design/DESIGN-SYSTEM-SPEC.md`](file:///Volumes/4TB-BAD/Halbert/documentation/design/DESIGN-SYSTEM-SPEC.md) | Design tokens & component specs | Space Grotesk / JetBrains Mono typography, border radiuses, shadows |
| [`documentation/design/APP-AESTHETIC-AUDIT-AND-REFINEMENT-PLAN-2026-08-28.md`](file:///Volumes/4TB-BAD/Halbert/documentation/design/APP-AESTHETIC-AUDIT-AND-REFINEMENT-PLAN-2026-08-28.md) | Desktop shell refinement | Native macOS titlebar integration, padding rhythm, tab ergonomics |

---

## 3. Git History & Code Commits (Past Week: Aug 22 – Aug 29)

| Commit | Date | Summary | Key Files Changed |
|---|---|---|---|
| `9d4488e1` | 2026-08-24 | Feat(marketing-v2): create alternate Swiss drafting style site | `marketing/web-v2/*` |
| `d93c12ec` | 2026-08-24 | Feat(marketing-v3): build retro serif medium blue edition | `marketing/web-v3/*` |
| `b95b1a44` | 2026-08-24 | Feat(marketing-v4): build minimalist utility-first edition | `marketing/web-v4/*` |
| `cb22e8a6` / `c26b8efd` | 2026-08-24 | Feat(marketing-v5): 1960s Scientific American print ad edition | `marketing/web-v5/*` |
| `8e77d14d` | 2026-08-24 | Feat(marketing-v6): experimental parallax edition with CMYK bleed | `marketing/web-v6/*` |
| `ac8462c5` | 2026-08-24 | Feat(themes): add dynamic dev theme picker with 6 color sets | `marketing/shared-tokens/` |
| `361fe8ac` | 2026-08-29 | Docs: UI/UX redesign investigation request | `.handoff/HALBERT-UI-REDESIGN-INVESTIGATION-REQUEST.md` |
| `082e8d3b` | 2026-08-29 | Redesign security tab per Daylight Mid-Century Modern spec | `components/SecurityComponents.tsx`, `pages/Settings.tsx` |
| `92ccf9e1` | 2026-08-29 | Add per-key cloud escape hatch card to Security settings tab | `components/SecurityComponents.tsx` |
| `67b174e0` / `b3f39c5e` | 2026-08-29 | Fix scrutiny issues & security tab polishing (ARIA, live telemetry) | `components/SecurityComponents.tsx` |

---

## 4. Key Files & Architectural Components

- **Dashboard Pages & Components:**
  - [`halbert_core/halbert_core/dashboard/frontend/src/pages/Settings.tsx`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/pages/Settings.tsx) (Megafile to decompose)
  - [`halbert_core/halbert_core/dashboard/frontend/src/components/SecurityComponents.tsx`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/components/SecurityComponents.tsx) (Design-system reference implementation)
  - [`halbert_core/halbert_core/dashboard/frontend/src/components/Layout.tsx`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/components/Layout.tsx) (Navigation sidebar)
  - [`halbert_core/halbert_core/dashboard/frontend/src/pages/Security.tsx`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/pages/Security.tsx) (Overlapping findings page)
- **Marketing Websites & Design Tokens:**
  - `marketing/web-v5/` (DDB 1960s Print Edition)
  - `marketing/web-v6/` (Parallax Bleed Edition)
  - `marketing/shared-tokens/tokens.css`

---

## 5. Incomplete Work & Open Items

1. **`Settings.tsx` Decomposition:** Break down `Settings.tsx` into individual domain components under `src/components/settings/`:
   - `GeneralSettings.tsx` (Host profile, daemon status)
   - `ModelsSettings.tsx` (Unified LLM Picker integration)
   - `SecuritySettings.tsx` (Extracted `SecurityComponents.tsx` wrapper)
   - `BeingSettings.tsx` (Personality, Voice, Senses)
   - `VisionSettings.tsx` (Screen capture, camera consent)
   - `IntegrationsSettings.tsx` (Home Assistant, Wyoming, SourcePrep)
2. **Sidebar Navigation Consolidation:** Refactor `Layout.tsx` to group routes under the 4 primary domains defined in `.handoff/HALBERT-UI-REDESIGN-PLAN.md`.
3. **Resolution of `Security.tsx` Route Overlap:** Rename or merge `pages/Security.tsx` (which displays host finding cards and blast radius) to `pages/Findings.tsx` to eliminate user confusion with `Settings > Security`.

---

## 6. Review Directives for Fable

- **Component Decoupling:** Review the decomposition plan to ensure tab sub-components do not perform redundant API requests when not active (implement proper tab-level lazy mounting and cache invalidation).
- **Design System Token Conformance:** Check that all UI elements use token classes (`bg-linen-light`, `text-vermilion-base`, `font-mono`) rather than hardcoded hex color values or generic Tailwind blues/purples.
- **Accessibility & Keyboard Navigation:** Verify ARIA tab roles, keyboard focus outlines, and screen reader announcements across newly created form controls.
- **Verification Command:** Run `npm --prefix halbert_core/halbert_core/dashboard/frontend run build` and `npm --prefix halbert_core/halbert_core/dashboard/frontend test`.
