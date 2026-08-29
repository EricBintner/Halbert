# Halbert UI/UX Audit — Handoff for Investigation

**Date:** 2026-08-29
**From:** Cascade (home-automation work session)
**To:** Next AI session
**Status:** Investigation request — no code changes yet

---

## 1. Objective

Investigate the Halbert dashboard UI and produce a **concrete redesign plan** that makes it intuitive for end users. The current UI has grown organically across many phases and is now a sprawling collection of pages and a massive Settings file. We want it to feel like a cohesive product, not a "wall of settings."

**The deliverable is a design document with:**
- Current state inventory (what exists, what's broken, what's redundant)
- Information architecture proposal (how pages should be grouped/merged)
- Specific component-level recommendations (what to simplify, what to hide behind progressive disclosure)
- Priority-ordered implementation plan

**Do NOT write code yet.** This is a research and design task only.

---

## 2. Current State

### 2.1 Navigation Structure

The sidebar (`Layout.tsx:57-97`) has 5 sections with 14 nav items:

| Section | Items |
|---------|-------|
| Overview | Dashboard, Home |
| System | Services, Storage, Backups, Apps, Security |
| Network | Network, Sharing |
| Development | Containers, GPU, Development |
| Utility | Approvals, Settings |

### 2.2 Dual-Mode Shell

The app has two modes (`Layout.tsx:451-456`):
- **Browsing mode** — sidebar + page content (the 14 pages above)
- **Engaged mode** — `HostShell` (chat interface takes over full screen)

A mode switcher toggles between them. Events from browsing pages (`halbert:open-chat`, `halbert:send-to-chat`, `halbert:run-command`) flip to engaged mode with context.

### 2.3 The Settings Problem

`Settings.tsx` is **3,105 lines** in a single file. It contains these tabs:

| Tab | Content | Lines (approx) |
|-----|---------|-----------------|
| (Main/General) | System profile, model settings, indexing, knowledge sources | ~1-2684 |
| Safety | Custom AI rules, guardrails | ~2687-2963 |
| Alerts | Alert rules | ~2966-3005 |
| Being | Personality/character config (delegates to `BeingSettings`) | ~3008-3011 |
| Security | MCP trust boundary (delegates to `SecuritySettings`) | ~3014-3016 |
| Vision | Screen capture, webcam, redaction (delegates to `VisionSettings`) | ~3019-3021 |
| About | Version info | ~3024-3083 |

The file has 3 sub-components defined inline (`VisionSettings`, `SecuritySettings`, `BeingSettings`) plus the main `Settings` component. It handles:
- System profile scanning
- Model configuration (LLM/Ollama endpoints)
- SourcePrep indexing controls
- Knowledge source management (docs URLs, trending repos)
- Custom AI rules
- Alert rules
- Personality/character settings
- MCP trust boundary security
- Vision/screen capture config
- About/version info

### 2.4 Other Pages

Each nav item is a separate page in `src/pages/`:

| Page | Purpose | Notes |
|------|---------|-------|
| `Dashboard.tsx` | System overview (CPU, memory, disk, discoveries) | 383 lines |
| `Home.tsx` | Home Assistant panel (new in Phase 1) | 100 lines |
| `Terminal.tsx` | Terminal session manager | |
| `Services.tsx` | Systemd service browser | |
| `Storage.tsx` | Disk/partition management | |
| `Backups.tsx` | Backup management | |
| `Apps.tsx` | App store / package management | |
| `Security.tsx` | Security findings and scan results | Separate from Settings > Security tab |
| `Network.tsx` | Network interfaces and config | |
| `Sharing.tsx` | File sharing / SMB / NFS | |
| `Containers.tsx` | Docker/Podman container management | |
| `GPU.tsx` | GPU status and info | |
| `Development.tsx` | Dev environment management | |
| `Approvals.tsx` | Pending tool approval queue | |
| `Settings.tsx` | The 3,105-line megafile | See above |

### 2.5 Frontend Tech Stack

- React 18 + TypeScript
- Vite build
- TailwindCSS + shadcn/ui components
- lucide-react icons
- react-router-dom for SPA routing
- Custom contexts: DebugContext, ScanContext, PageContext, ShellModeContext

### 2.6 Design System

- `HalbertMark` brand component exists
- `PageHeader`, `StatusBadge`, `DataVersionCard` domain components exist in `src/components/domain/`
- Color system uses CSS variables (bg-background, text-muted-foreground, etc.)
- Dark mode supported
- Typography was recently refined (commit `48a5d2a2`)

---

## 3. Key Concerns to Investigate

### 3.1 Settings is a Megafile

3,105 lines in one file is unmaintainable. The tabs cover wildly different domains (personality, security, vision, AI rules, knowledge sources, model config). Should these be split into separate pages? Should some be moved to their relevant domain pages (e.g., vision settings under a Vision page, security settings under the Security page)?

### 3.2 Navigation Redundancy

There's a `Security` nav item (security findings page) AND a `Security` tab in Settings (MCP trust boundary). These are different things but confusingly named. Similar overlap may exist elsewhere.

### 3.3 Information Hierarchy

14 top-level nav items is a lot. Some pages might be sub-tabs of others (e.g., GPU could be under Development, Backups could be under Storage, Approvals could be a notification badge rather than a full page).

### 3.4 Progressive Disclosure

Most settings are shown at once. Consider what should be:
- **Default visible** — things users touch daily (chat, dashboard, home)
- **One click away** — things users configure occasionally (model, personality, HA connection)
- **Two clicks away** — things users set once and forget (trust boundary, vision config, AI rules)

### 3.5 The "Wall of Settings" Problem

The Settings page dumps everything into tabs, but even within a tab there are many cards with many controls. Consider:
- Collapsible sections
- Search/filter within settings
- "Setup wizard" flows for first-time configuration
- Contextual settings (show relevant settings on the page they affect)

### 3.6 Mobile/Small Screen

The sidebar is 240px (`w-60`). On small screens this may be too wide. Check if there's a responsive collapse.

### 3.7 Onboarding Flow

There's an `Onboarding` component that runs on first launch. How does it connect to the rest of the UI? Does it pre-configure things that then appear in Settings?

---

## 4. What to Read

### Primary files:
- `halbert_core/halbert_core/dashboard/frontend/src/components/Layout.tsx` — nav structure, shell mode, header
- `halbert_core/halbert_core/dashboard/frontend/src/pages/Settings.tsx` — the 3,105-line megafile
- `halbert_core/halbert_core/dashboard/frontend/src/App.tsx` — routing
- `halbert_core/halbert_core/dashboard/frontend/src/pages/Dashboard.tsx` — landing page
- `halbert_core/halbert_core/dashboard/frontend/src/pages/Home.tsx` — new HA panel
- `halbert_core/halbert_core/dashboard/frontend/src/components/Onboarding.tsx` — first-run flow

### Supporting:
- `halbert_core/halbert_core/dashboard/frontend/src/components/domain/` — shared domain components
- `halbert_core/halbert_core/dashboard/frontend/src/components/ui/` — shadcn/ui primitives
- `halbert_core/halbert_core/dashboard/frontend/src/components/shell/` — HostShell (engaged mode)
- `halbert_core/halbert_core/dashboard/frontend/src/contexts/` — app contexts

### Backend routes (to understand what data the UI can access):
- `halbert_core/halbert_core/dashboard/routes/` — all API route modules

---

## 5. Expected Output

Produce a document at `.handoff/HALBERT-UI-REDESIGN-PLAN.md` with:

1. **Current State Audit** — inventory of all pages, their sizes, what they do, overlap/redundancy
2. **Proposed Information Architecture** — new nav structure, what merges/splits, what becomes sub-pages
3. **Settings Restructuring Plan** — how to break up the 3,105-line file, what becomes its own page
4. **Progressive Disclosure Strategy** — what's default-visible vs hidden
5. **Component-Level Recommendations** — specific UI patterns to adopt (collapsible sections, contextual settings, search)
6. **Implementation Priority** — what to do first, what can wait

Keep recommendations concrete and actionable. Reference specific files and line numbers.
