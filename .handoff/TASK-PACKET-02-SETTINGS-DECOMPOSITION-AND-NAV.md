# Task Packet 02: Settings Megafile Decomposition & Navigation Consolidation

**Target Model:** **GLM-5.3 medium** (reassigned 2026-08-30; Batch U3 — runs together with TASK-08/REV-08/REV-11 as one ultracode workflow; tab extraction parallelizes cleanly across fan-out agents)  
**Domain:** Frontend Architecture, React Component Decomposition, Information Architecture, and Daylight Design System Alignment  
**Target Date:** 2026-08-29  
**Status:** Ready for Implementation  
**Verified 2026-08-30:** `Settings.tsx` is currently **3,283 lines** (not 3,105/3,273 as stated below); `pages/Security.tsx` still exists (278 lines); `Layout.tsx` nav is 5 sections (~14 items).  
**Governing Documents:**
- [`.handoff/HALBERT-UI-REDESIGN-PLAN.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/HALBERT-UI-REDESIGN-PLAN.md)
- [`.handoff/HALBERT-UI-REDESIGN-INVESTIGATION-REQUEST.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/HALBERT-UI-REDESIGN-INVESTIGATION-REQUEST.md)
- [`documentation/design/SETTINGS-REDESIGN-2026-08-27.md`](file:///Volumes/4TB-BAD/Halbert/documentation/design/SETTINGS-REDESIGN-2026-08-27.md)
- [`documentation/design/BRAND-GUIDELINES-AND-AESTHETIC.md`](file:///Volumes/4TB-BAD/Halbert/documentation/design/BRAND-GUIDELINES-AND-AESTHETIC.md)

---

## 1. Executive Summary & Objective

Halbert's UI currently suffers from severe navigation sprawl (14 top-level items in the sidebar) and extreme code bloat in [`Settings.tsx`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/pages/Settings.tsx) (3,105 lines). Furthermore, a confusing route overlap exists between `pages/Security.tsx` (system diagnostics/findings) and `Settings > Security` (MCP trust gates).

This task packet details the complete refactor to:
1. Decompose `Settings.tsx` into 6 clean, modular, lazy-loaded tab components under `src/components/settings/`.
2. Consolidate the 14-item navigation menu in `Layout.tsx` down to 4 primary domain pillars.
3. Rename and reconcile `pages/Security.tsx` to `pages/Findings.tsx`.
4. Ensure all newly extracted components strictly follow Daylight design tokens.

---

## 2. Detailed Task Breakdown & Implementation Steps

### Task 2.1: Decompose `Settings.tsx` into Modular Tab Components
Create the directory `halbert_core/halbert_core/dashboard/frontend/src/components/settings/` and extract the sub-tabs from `Settings.tsx`:

1. **`GeneralSettings.tsx`:** Host system profile, daemon status, system paths, telemetry toggles.
2. **`ModelsSettings.tsx`:** Wrapper around vendored `@prep/ui` `UnifiedLLMSettings` component + performance dials.
3. **`SecuritySettings.tsx`:** Wrapper around the newly built `SecurityComponents.tsx` (live telemetry bar, mechanical switches, volatile unlock).
4. **`BeingSettings.tsx`:** Persona selection, voice parameters, autonomy dials, and prompt customization.
5. **`VisionSettings.tsx`:** Desktop screen capture consent, camera zone permissions, OCR toggles.
6. **`IntegrationsSettings.tsx`:** Home Assistant URL/Token config, Wyoming Voice link, SourcePrep daemon endpoint.

### Task 2.2: Refactor `Settings.tsx` into Master Coordinator
- **File:** [`halbert_core/halbert_core/dashboard/frontend/src/pages/Settings.tsx`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/pages/Settings.tsx)
  1. Replace the 3,105-line monolith with a clean master-detail coordinator (<300 lines).
  2. Implement URL query parameter tab binding (`?tab=models`, `?tab=security`, etc.) with browser history support.
  3. Lazy-load non-active tabs with `React.lazy` and `Suspense` fallback indicators.

### Task 2.3: Consolidate Sidebar Navigation in `Layout.tsx`
- **File:** [`halbert_core/halbert_core/dashboard/frontend/src/components/Layout.tsx`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/components/Layout.tsx)
  1. Refactor navigation links from 14 items across 5 sections into 4 primary domains:
     - **Being & Ambient Home:** Dashboard (`/`), Sentient Home (`/home`), Memory & Timeline (`/memory`).
     - **Intelligence & Findings:** Findings Engine (`/findings`), Alerts (`/alerts`), Proactive Chronicle (`/timeline`).
     - **Sovereign Host Controls:** Services (`/services`), Storage & Backups (`/storage`), Terminal (`/terminal`).
     - **Settings & Architecture:** Settings Hub (`/settings`).
  2. Maintain instance-specific visibility (e.g. hide host storage/services when `instance == "home"`).

### Task 2.4: Rename `pages/Security.tsx` to `pages/Findings.tsx`
- **Files:**
  - Rename `halbert_core/halbert_core/dashboard/frontend/src/pages/Security.tsx` → `pages/Findings.tsx`
  - Update route in `halbert_core/halbert_core/dashboard/frontend/src/App.tsx`:
    - Map `/findings` → `<Findings />`
    - Add legacy redirect from `/security` → `/findings`

---

## 3. Verification & Test Plan

1. **TypeScript Build Verification:**
   ```bash
   npm --prefix halbert_core/halbert_core/dashboard/frontend run build
   ```
2. **Component Test Suite:**
   ```bash
   npm --prefix halbert_core/halbert_core/dashboard/frontend test
   ```
3. **Manual Flow Checks:**
   - Navigating to `/settings?tab=security` loads the Security tab without rendering background tabs.
   - Switching instances via `InstanceSwitch.tsx` updates sidebar routes cleanly.
   - Navigating to `/findings` renders the system diagnostics and blast-radius cards.
