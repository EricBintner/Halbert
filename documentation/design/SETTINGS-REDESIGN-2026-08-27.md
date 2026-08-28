# Settings & Navigation Redesign

**Date:** 2026-08-27
**Branch:** `feat/settings-redesign`
**Worktree:** `~/.config/superpowers/worktrees/Halbert/settings-redesign`
**Status:** Planning — awaiting approval before implementation

---

## 1. Problem Statement

Two coupled UI problems in the Halbert dashboard frontend:

### 1.1 Settings page is a 2,680-line monolith

`pages/Settings.tsx` is **114 KB / 2,680 lines**. It contains:

| Tab | Lines | Notes |
|-----|-------|-------|
| system | 1281–1395 | System info + GPU tweaks |
| ai | 1396–1489 | Delegates to `<ModelSettings/>` + `<CompressionSettings/>` |
| knowledge | 1490–2040 | **551 lines** — RAG sources, indexes, custom docs, suggestions, freshness |
| personas | 2041–2190 | **ORPHAN — no trigger, dead code** |
| safety | 2191–2553 | 363 lines — policy + tool permissions |
| alerts | 2554–2595 | 42 lines |
| being | 2596–2600 | Delegates to `<BeingSettings/>` (defined at line 78, ~470 lines) |
| about | 2601–2680 | Legal notices, links |

Plus ~690 lines of state declarations and handlers (lines 548–1237) hoisted into the parent `Settings()` component — **~30 `useState` calls** all live in the parent, even though most are used by exactly one tab.

### 1.2 Seven tabs crammed into a horizontal grid

```tsx
<TabsList className="grid w-full grid-cols-7">
```

Seven equal-width tabs in a single row. On any viewport under ~1200px the labels truncate or wrap. There is no hierarchy, no grouping, no search. The orphan `personas` content (line 2041) has no trigger — it renders nothing but the code is still shipped.

### 1.3 Nav menu is a flat 14-item list

`components/Layout.tsx` defines 14 top-level routes with comment-based grouping but no visual grouping:

```tsx
const navigation = [
  // Overview
  { name: 'Dashboard', ... },
  // Essential System Health
  { name: 'Services', ... },
  { name: 'Storage', ... },
  ...
  // Utility
  { name: 'Settings', ... },
]
```

No section headers, no collapsible groups, no command palette. The comments are aspirational; the rendered UI is a flat list.

---

## 2. Research Findings (Condensed)

Full research covered macOS System Settings, VS Code, Linear, Raycast, Cursor, GitHub, Notion, Vercel, Cloudflare, plus real React/shadcn codebases (Multica, Voicebox).

### 2.1 Layout pattern: vertical sidebar wins

Every app with 7+ settings categories uses a **vertical left sidebar + content pane** (macOS, VS Code, Linear, Cursor, Vercel). Horizontal top tabs work for 3–4 categories; at 7 they crowd. The sidebar pattern also scales to sub-pages without layout changes.

### 2.2 Information architecture: 5–6 top-level groups is the ceiling

Common groupings across apps:

| Cluster | Typical contents |
|---------|-----------------|
| Account / General | Profile, Appearance, Notifications |
| System | Hardware, Storage, Network, Updates |
| AI / Intelligence | Models, Knowledge, Safety, Rules |
| Advanced / Admin | API keys, Integrations, Danger zone |

Halbert's 7 tabs map cleanly onto 3 groups (see §3.1).

### 2.3 Component decomposition: one file per tab + shared primitives

**Multica** (shadcn/Radix stack, same as Halbert): one component per tab (`AccountTab.tsx`, `PreferencesTab.tsx`, ...), tab keys mapped to files via a constant array.

**Voicebox**: shared `SettingSection` + `SettingRow` primitives — label/description on the left, control on the right, consistent control-width tiers (`sm:w-48`, `sm:w-72`, `sm:w-96`).

**Radix Tabs lazy-loading caveat**: all `TabsContent` children mount even when inactive. Fix: `{tab === "ai" && <AITab />}` conditional rendering, or `React.lazy` + `Suspense`.

### 2.4 Navigation: sectioned sidebar + command palette

**Linear/Vercel/GitHub**: sectioned sidebar with group headers, collapsible groups.

**Linear/Raycast/VS Code**: Cmd+K command palette as the keyboard-first alternative to deep nav. shadcn ships a `Command` primitive and `Sidebar With Command Menu` block.

### 2.5 Mobile: hamburger → Sheet drawer

Halbert already has `components/ui/sheet.tsx` (Radix Dialog-based). On narrow screens the sidebar collapses into a left `Sheet` drawer. Settings tab list follows the same pattern.

---

## 3. Proposed Design

### 3.1 Settings information architecture

Collapse 7 tabs (+ 1 dead orphan) into **3 grouped sections** in a vertical sidebar:

```
SETTINGS
├─ General
│  ├─ System          (hostname, OS, GPU tweaks)
│  ├─ Alerts          (alert rules)
│  └─ About           (legal notices, version, links)
├─ AI & Cognition
│  ├─ Models          (ModelSettings — chat/specialist/vision)
│  ├─ Knowledge       (RAG sources, indexes, custom docs, suggestions)
│  └─ Being           (personality, voice, persona model override)
└─ Safety & Control
   └─ Safety          (tool policy, permissions)
```

**Rationale:**
- "General" = things you set once and forget (system info, alerts, about).
- "AI & Cognition" = the brain — models, knowledge, personality. This is Halbert's differentiator; grouping it makes the value visible.
- "Safety & Control" = the guardrails. One tab today (Safety); room to grow (autonomy limits, approval queues).
- The orphan `personas` tab is **deleted** — it's dead code with no trigger.

### 3.2 Settings layout: vertical sidebar + content pane

```
┌─────────────────────────────────────────────────┐
│  Settings                                        │
├──────────┬──────────────────────────────────────┤
│ GENERAL  │                                      │
│  System  │   <ActiveTabContent />               │
│  Alerts  │                                      │
│  About   │                                      │
│          │                                      │
│ AI & COG │                                      │
│  Models  │                                      │
│  Knowledge│                                     │
│  Being   │                                      │
│          │                                      │
│ SAFETY   │                                      │
│  Safety  │                                      │
└──────────┴──────────────────────────────────────┘
```

- Sidebar: `w-56`, sticky, section headers in muted text, items as full-width text-left buttons.
- Content pane: `flex-1`, scrollable, renders only the active tab (conditional mount).
- Deep links preserved: `/settings?tab=ai` still works (the model picker's "All models…" link depends on it).
- Search bar at top of sidebar (filters tab labels; future: search within tab content).

### 3.3 Settings component decomposition

```
src/
├─ pages/
│  └─ Settings.tsx                 # ~150 lines — shell, sidebar, route param, section rendering
├─ components/
│  └─ settings/
│     ├─ SettingsSidebar.tsx       # Sectioned nav list, search filter
│     ├─ primitives/
│     │  ├─ SettingsSection.tsx    # Card wrapper: title + description + children
│     │  ├─ SettingsRow.tsx        # Label/description left, control right
│     │  ├─ SettingsSwitch.tsx     # SettingsRow + toggle
│     │  └─ SettingsSelect.tsx     # SettingsRow + select dropdown
│     └─ tabs/
│        ├─ SystemTab.tsx          # ~120 lines (was 1281–1395)
│        ├─ AlertsTab.tsx          # ~50 lines (was 2554–2595)
│        ├─ AboutTab.tsx           # ~90 lines (was 2601–2680)
│        ├─ ModelsTab.tsx          # ~100 lines (was 1396–1489 — thin wrapper)
│        ├─ KnowledgeTab.tsx       # ~560 lines (was 1490–2040 — biggest, own state)
│        ├─ BeingTab.tsx           # ~480 lines (was BeingSettings 78–547 + 2596–2600)
│        └─ SafetyTab.tsx          # ~370 lines (was 2191–2553)
```

**Key rules:**
- Each tab owns its own `useState`/`useEffect`. No state hoisted to parent.
- `pages/Settings.tsx` only owns: active tab (from URL), sidebar, and conditional rendering.
- Shared primitives (`SettingsSection`, `SettingsRow`) replace the repeated `<Card><CardHeader><CardTitle>` boilerplate.
- Conditional mount: `{tab === 'knowledge' && <KnowledgeTab />}` — fixes the Radix "all tabs mount" problem.

### 3.4 Navigation redesign: sectioned sidebar

Group the 14 flat items into **5 sections** with headers:

```
OVERVIEW
  Dashboard

SYSTEM
  Services
  Storage
  Backups
  Security

NETWORK
  Network
  Sharing

DEVELOPMENT
  Containers
  GPU
  Development

UTILITY
  Approvals
  Settings
```

Implementation in `Layout.tsx`:
- Change `navigation` from a flat array to a grouped structure: `{ section: string, items: NavItem[] }[]`.
- Render section headers as muted, uppercase, small text.
- Use existing `components/ui/collapsible.tsx` for collapsible groups (optional, default expanded).
- Active item highlight unchanged (NavLink).

### 3.5 Command palette (Cmd+K)

Add a shadcn `CommandDialog` bound to `Cmd/Ctrl+K`:
- Lists all 14 nav routes + 7 settings tabs.
- Keyboard-first navigation for power users.
- This is the escape hatch for a long nav list — users don't need to scan sections if they can type.

**Note:** Check if `components/ui/command.tsx` exists; if not, add it from shadcn (it's a thin wrapper over `cmdk`).

### 3.6 Mobile / responsive

| Breakpoint | Nav | Settings sidebar |
|------------|-----|-----------------|
| `lg+` (≥1024px) | Full sidebar with labels | Inline left sidebar |
| `md` (768–1023px) | Icon-only rail (collapse labels) | Inline left sidebar (narrower, `w-48`) |
| `<md` (<768px) | Hamburger → left `Sheet` drawer | Tab list collapses to a `Sheet side="bottom"` picker |

Halbert already has `components/ui/sheet.tsx` — no new dependency.

---

## 4. Implementation Plan

### Phase 1: Settings component split (no visual change yet)
**Goal:** Break the 2,680-line file into tab files without changing the UI.

1. Create `components/settings/primitives/` (SettingsSection, SettingsRow, SettingsSwitch, SettingsSelect).
2. Extract each tab's JSX + state into `components/settings/tabs/<Tab>.tsx`.
3. Move `BeingSettings()` into `tabs/BeingTab.tsx`.
4. Delete the orphan `personas` TabsContent (dead code).
5. `pages/Settings.tsx` becomes a thin shell that imports and renders tab components.
6. Keep the horizontal `grid-cols-7` tabs for now — visual change comes in Phase 2.
7. Run existing tests (`Settings.tabs.test.tsx` must still pass).

**Verification:** `tsc --noEmit` clean, `vitest run` passes, visual diff = zero.

### Phase 2: Settings sidebar layout
**Goal:** Replace horizontal tabs with vertical sectioned sidebar.

1. Create `components/settings/SettingsSidebar.tsx` — sectioned nav with 3 groups.
2. Restyle `pages/Settings.tsx` to a two-column layout (sidebar + content).
3. Add conditional tab mounting (`{tab === 'x' && <XTab />}`).
4. Add search filter in sidebar (filters tab labels).
5. Update `Settings.tabs.test.tsx` if needed (tab roles may change from `tab` to `button` or nav items).

**Verification:** Deep links (`/settings?tab=ai`) still work. Visual review.

### Phase 3: Navigation sectioning
**Goal:** Group the 14 flat nav items into 5 sections.

1. Refactor `navigation` array in `Layout.tsx` to grouped structure.
2. Render section headers.
3. Optional: collapsible groups via `collapsible.tsx`.

**Verification:** All 14 routes still reachable. Active highlight works.

### Phase 4: Command palette
**Goal:** Add Cmd+K fast path.

1. Add `components/ui/command.tsx` (shadcn Command primitive) if not present.
2. Create `components/CommandPalette.tsx` — lists nav routes + settings tabs.
3. Bind to `Cmd/Ctrl+K` in `Layout.tsx`.

**Verification:** Cmd+K opens, typing filters, Enter navigates.

### Phase 5: Mobile responsive
**Goal:** Degrade gracefully on narrow screens.

1. Nav: hamburger → `Sheet` drawer on `<md`.
2. Settings sidebar: `Sheet side="bottom"` picker on `<md`.
3. Icon-only rail on `md`.

**Verification:** Test at 375px, 768px, 1024px, 1440px.

---

## 5. What Does NOT Change

- Backend API endpoints — no backend work in this redesign.
- The `llm_config` store, model picker, persona model override — all preserved.
- Deep link contract: `/settings?tab=<tab>` continues to work.
- `Settings.tabs.test.tsx` — the tab-addressability test stays valid (may need selector updates).
- Existing extracted components (`components/llm/`, `components/domain/`, `components/legal/`) — these are already separate and stay as-is.

## 6. Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| State that's shared across tabs (e.g. `systemInfo` used by System + AI) | Pass via props or a small `SettingsContext` if needed; most state is tab-local |
| Radix Tabs `forceMount` behavior changes | We're moving away from Tabs to a custom sidebar nav, so this becomes moot |
| Test breakage from role changes (tab → nav item) | Update test selectors; the addressability contract is what matters, not the ARIA role |
| Nav grouping hides items users expect at top | Command palette (Phase 4) is the escape hatch; Dashboard stays first |
| `personas` orphan deletion breaks something | Verified: no trigger exists (line 2041 has no matching `TabsTrigger`), so it renders nothing today |

## 7. Decisions (Resolved)

1. **About location** → Moves to the avatar dropdown *and* the native macOS app-name menu (`Halbert ▸ About Halbert` in the menu bar). Removed from the settings sidebar. This matches Notion/GitHub convention plus the native macOS pattern.
2. **Nav groups** → Always expanded. Section headers only, no collapse state. Simpler, no persisted UI state.
3. **Settings sidebar width:** `w-56` (224px) — matches macOS. (Open for reviewer to challenge.)
4. **Section headers in nav:** uppercase muted text (Linear style). (Open for reviewer to challenge.)

## 8. Open Questions (For External Review)

1. **Command palette scope (Phase 4):** Navigation only (jump to pages/settings tabs) vs. nav + actions (also trigger "Start deep scan", "Rebuild index", "New conversation"). Nav-only is simpler; nav+actions is more useful but requires wiring each action to its backend endpoint.
2. **Settings search:** filter tab labels only (Phase 2), or also search within tab content (future)?
3. **Is the 3-group settings IA (General / AI & Cognition / Safety) the right grouping?** Reviewer may suggest alternatives.
4. **Should "Alerts" stay under General, or move to Safety & Control?** Alerts are rule configuration (General) but conceptually relate to safety monitoring.

---

## 8. File Inventory

### New files
- `components/settings/SettingsSidebar.tsx`
- `components/settings/primitives/SettingsSection.tsx`
- `components/settings/primitives/SettingsRow.tsx`
- `components/settings/primitives/SettingsSwitch.tsx`
- `components/settings/primitives/SettingsSelect.tsx`
- `components/settings/tabs/SystemTab.tsx`
- `components/settings/tabs/AlertsTab.tsx`
- `components/settings/tabs/AboutTab.tsx`
- `components/settings/tabs/ModelsTab.tsx`
- `components/settings/tabs/KnowledgeTab.tsx`
- `components/settings/tabs/BeingTab.tsx`
- `components/settings/tabs/SafetyTab.tsx`
- `components/CommandPalette.tsx` (Phase 4)
- `components/ui/command.tsx` (Phase 4, if not present)

### Modified files
- `pages/Settings.tsx` — gutted to ~150-line shell
- `components/Layout.tsx` — grouped nav + command palette binding + mobile drawer

### Deleted
- Orphan `personas` TabsContent block (lines 2041–2190 in current Settings.tsx)

---

## 9. Sources

- macOS System Settings: 9to5Mac, Macworld
- VS Code: code.visualstudio.com/docs/configure/settings; github.com/microsoft/vscode
- Linear: linear.app/changelog/2024-12-18-personalized-sidebar
- Raycast: manual.raycast.com/settings
- Cursor: cursor.fan/ide-settings
- GitHub: github.blog/changelog/2022-02-02-redesign-of-githubs-settings-pages
- Notion: notion.com/help
- Vercel: vercel.com/changelog/dashboard-navigation-redesign-rollout
- Cloudflare: developers.cloudflare.com/fundamentals/user-profiles
- shadcn: shadcn.io/blocks/sidebar-with-command-menu; shadcn.io/ui/drawer
- Code examples: github.com/multica-ai/multica; github.com/jamiepine/voicebox
- Radix Tabs: github.com/radix-ui/primitives/discussions/3941
