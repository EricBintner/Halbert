# RESULTS — SONNET-04 Frontend Mechanical

**Packet:** `DISPATCH SONNET-04 — Frontend: dead routes, nav entry points, token ratchet, REV-08 mechanical fixes`
**Branch:** `fix/frontend-mechanical` (fresh worktree off `main` @ `f93f5ec5`)
**Date:** 2026-09-02
**Not pushed to origin** — left committed locally per the dispatching session's explicit instruction; the coordinator decides how to integrate.

Context updates applied per the dispatching session's brief (not the packet's original text):
- `ROUTE-01` (the `/api/devices` mount prefix) was already fixed by OPUS-03 before this packet started — verified with a grep of `dashboard/app.py`'s router mounts (`app.include_router(devices.router, prefix="/api", ...)`, with an explanatory comment already in place) and skipped as instructed.
- Did not touch `hooks/useAgentStream.ts`, `components/agent/AgentChat.tsx`, `MessageContent.tsx`, `ThinkingPanel.tsx` (OPUS-05 already landed fixes there).
- Got a fresh reading of `scripts/check_literal_colors.py --check` myself rather than trusting the packet's pre-Opus-batch counts (Task 3 below).

## Commits (in order)

| SHA | Subject |
|---|---|
| `aab214a7` | fix(frontend): repoint three dead API paths (ROUTE-02, ROUTE-03) |
| `886e1b9d` | feat(shell): top-bar approvals badge, nav-coverage test, drop dead Jobs page |
| `c6989455` | fix(design-system): sweep literal-colour ratchet regressions, re-baseline |
| `af16f2f8` | fix(design-system): drop half-implemented tab roles from NavRail (R08-02) |
| `6e4ef14b` | fix(settings): indexing poll leak, placebo clear-cache, debug toggle, blocklist PUTs (R08-05/R08-07) |
| `cf7face5` | chore(frontend): remove dead SendToChat/Backups affordances, delete 3 orphaned components (CC-02/FEAT-02/DS-04) |
| `fdefee02` | perf(settings): lazy-mount tab bodies, load each tab's data on first visit (U3-02/U3-04) |
| `aabb953b` | test(frontend): cover 14 untested surfaces (FE-15) |

## Task 1 — Three dead API paths

- **ROUTE-02**: `BeingTab.tsx` built `API_BASE = apiUrl('/api')` then fetched `${API_BASE}/api/persona/...` (four call sites: list, create, activate, delete) → `/api/api/persona/*`, 404. Real routes are `/api/persona/*` (`persona.py:52`, mounted with no extra prefix in `app.py:291`). Dropped the redundant `/api` segment on all four. Added `BeingTab.test.tsx` (2 tests) asserting the persona URLs are correct and that a persona-create POSTs to `/api/persona`.
- **ROUTE-03a**: `AudioSettings.tsx`'s quiet-hours load/save hit `/api/being`, which doesn't exist (`being.py` only serves `/being/events*`). Repointed both to `GET/POST /api/settings/being` (`settings.py:3052,:3070`); the POST body shape (`{quiet_hours}`) already matched `BeingConfigUpdate`. Added `AudioSettings.test.tsx` (2 tests).
- **ROUTE-03b**: `lib/peerApi.ts` built every one of its 23 fetch calls from `const API_BASE = ''`, a bare-relative-URL pattern that 404s inside the Tauri webview (`test_frontend_no_relative_urls.py:98` was failing on main). Routed all 23 through `apiUrl(...)`.
- Guard-test false positive: `StandbyController.tsx`'s `DISPLAY_REPORT_PATH` constant tripped the same guard's string-literal pattern even though it's only ever consumed via `apiUrl(DISPLAY_REPORT_PATH)` elsewhere in the same file. Allowlisted the file in `test_frontend_no_relative_urls.py` with a comment, per the packet's explicit instruction to adjust the guard rather than the component.
- `test_frontend_no_relative_urls.py`: 4/4 passing (was 1 failing on main).
- **ROUTE-01**: skipped per the context update — verified via grep that `devices.router` mounts at `prefix="/api"` in `app.py:317` with a comment documenting the fix.

## Task 2 — Nav entry points

`Layout.tsx`'s `navSections` on current `main` (post shell-redesign merge `941cc14b`) already has Approvals under "Findings & Approvals" and GPU/Containers/Development/Network/Sharing/Apps under a new "Workloads" section — the re-railing part of this task landed before this packet started. What was still missing:

- **Top-bar pending-approvals badge**: added a `ShieldAlert` button next to the Settings gear that polls `getPendingApprovals()` every 5s (matching `Approvals.tsx`'s own cadence) and shows a `destructive`-variant count badge once there's something pending (hidden at zero). Click navigates to `/approvals` with the same center-panel auto-show behavior as rail navigation.
- **Nav-coverage test** (`Layout.navCoverage.test.tsx`, 3 tests): reads `App.tsx`'s own `<Route path="...">` list via Vite's `?raw` import and asserts every route has either a rail entry or a documented exemption (`/security` redirect, `/settings`, `/voice`, `/voice-hud`). Exported `navSections` from `Layout.tsx` for the test to check against. This project had never referenced `vite/client`'s ambient types, so added `src/vite-env.d.ts` (needed for the `?raw` import's types; benefits the whole project going forward).
- **Badge test** (`Layout.approvalsBadge.test.tsx`, 2 tests).
- **ORPHAN-01**: `pages/Jobs.tsx` deleted (unrouted, unimported). `pages/Memory.tsx` left as-is — its routing decision is tied to whether the ChromaDB memory page is kept, which is SONNET-05's call (`RAG-21`), and SONNET-05 hadn't run yet at dispatch time.

**Nav decision taken:** the re-railing (System/Workloads split rather than a single flat section) was already done upstream and is a defensible split (System = sysadmin surface, Workloads = things running on the machine that aren't core services) — left as-is rather than reshaping it. Only the pending-approvals badge was actually missing and needed building.

## Task 3 — Literal-colour ratchet

Fresh `check_literal_colors.py --check` against current `main` (post-Opus-batch) reported 11 files grown past baseline (236→ various). Investigated each via `git log --follow` / `git show` before deciding sweep vs. re-baseline, per the packet's explicit instruction not to re-baseline debt away:

**True renames** (content carried over verbatim, same count — re-baselined, not swept):
- `pages/Security.tsx` (1) → `pages/Findings.tsx` (1): confirmed via `git show e7e7ad2f^:.../Security.tsx` — identical line.
- `components/prep-primitives/Button.tsx` (4) → `components/ui/button.tsx` (4): confirmed via `git show 493956ab` — the `tone="warning"` pill classes (`amber-500`/`amber-400`) were moved verbatim during a duplicate-component consolidation, not newly introduced.

**Genuine regressions** (swept to semantic tokens — `text-success/-warning/-error/-info`, the `-muted` backgrounds, and `text-vermilion-strong` for two cases with no matching status-token fit):
- `StateBadge.tsx` (12, including 7 pre-existing baseline debt): four agent states had un-migrated light-mode classes sitting next to already-migrated `dark:` tokens; converged all four onto `info`. Fully cleared to 0.
- `AcousticAnomalyModule.tsx` (9): 4-tier severity scale → info/warning/error/destructive.
- `AcousticAuraIndicator.tsx` (4): 5-state pipeline indicator → muted/vermilion-strong/success/info/warning.
- `VoiceEnrollmentModal.tsx` (3): two success confirmations → `text-success`/`bg-success-muted`.
- `DiscoveredPeerCard.tsx` (2): discovery icon → `text-info`.
- `NodeFleetCockpit.tsx` (20): online/fallback/offline status styles → success/warning/muted; a "warn" telemetry span → `text-warning`.
- `DeviceCard.tsx` (15): 5-capability badge map → vermilion-strong/info/warning/success/success.
- `VisionTab.tsx` (6): three dependency-installed indicators → success/destructive.
- `PresencePill.tsx` (1): remote-node dot → `bg-warning`.

Re-ran `--baseline`: 227→211 (dropped further after Task 4/5's deletion of `CompressionSettings.tsx`, which carried 16 tracked pre-existing violations). Diff of the baseline JSON confirmed only the expected renames/sweeps changed — no existing debt silently hidden.

**DS-10** (56 hardcoded hex colours, a separate audit from the Tailwind-class ratchet): a plain hex-literal grep across dashboard `src` finds 55 hits in 8 files. None are in a file this packet's task list touched, so per the packet ("fix the ones in files you already touch") none were changed:
- `lib/xtermTheme.ts` (40): legitimate and documented in the file's own header — xterm paints to a canvas and cannot read CSS custom properties, so the ANSI palette is necessarily literal color values.
- `contexts/DebugContext.tsx` (5): `console.log('%c...', 'color: #xxx')` devtools styling strings — not rendered UI.
- `components/agent/ConfidenceIndicator.tsx` (4): a real, fixable UI-facing case (confidence→color function) — left for whichever packet next touches that file.
- `components/agent/TetherChip.tsx` (1), `voice/StandbyController.tsx` (1): false positives — a JSDoc example ID and a comment describing what `bg-black` renders as, not actual color literals.
- `pages/VoiceMode.test.tsx` (2), `voice/SubtitleRibbon.test.tsx` (1), `voice/TouchBar.test.tsx` (1): test assertions checking literal colors do NOT appear in rendered output — the hex strings are banned-list fixtures, not violations.

## Task 4 — REV-08 residuals

- **R08-02** (NavRail a11y): `NavRail.tsx`'s `tabMode` declared `role="tablist"`/`role="tab"`/`aria-selected` with none of the WAI-ARIA Tabs pattern's required arrow-key/roving-tabindex nav or `aria-controls`/`aria-labelledby` id-linking — `Settings.tsx`'s 12 `TabsContent` panels had no real triggers wired to them (Radix's own `aria-labelledby` pointed at a trigger id that was never rendered anywhere). Went with the packet's second option — dropped the tab roles for nav semantics — rather than implementing full roving-tabindex: selecting a settings section changes which page is shown, exactly like the dashboard's primary rail already does. `NavRail` items now always get `aria-current="page"` when active (a real a11y gap the *non*-tabMode rail had too — no previous "current page" signal). `Settings.tsx`'s panels get `role="region"` + a named `aria-label`, confirmed to cleanly override Radix's own defaults by reading the installed `@radix-ui/react-tabs@1.1.13` source (`contentProps` spreads after Radix's hardcoded `role`/`aria-labelledby`). Updated `Settings.tabs.test.tsx` to assert `aria-current` instead of the roles/`aria-selected` it no longer has; added `NavRail` coverage to `packages/design-system/src/test/surfaces.test.tsx` (3 tests).
- **R08-05** (indexing poll leak): `pollIndexingStatus` returned its interval id as a cleanup closure nothing ever called — Re-index while a previous poll was ticking stacked a second interval, and unmounting Settings mid-index left the poll running forever. Tracked the id in a ref: clear any existing interval before starting a new one, and clear it in the page's own mount-effect cleanup.
- **R08-07** ×3:
  - `SystemTab.tsx`'s "Clear Cache" button waited a second and told the user the cache was cleared without calling any backend route (grepped `routes/*.py` — none exists to clear discoveries). Removed the button and the `clearing`/`handleClearDiscoveries` plumbing in `Settings.tsx`, same reasoning as FEAT-02 below.
  - `DebugTab.tsx`'s toggle was a `Label` pointed at a plain `Button` whose own visible text ("Debug ON"/"Debug OFF") describes state, not purpose. Switched to the shared `Switch` component (`role="switch" aria-checked`), the toggle idiom `AudioSettings`/`BeingTab` already use.
  - `VisionTab.tsx`'s blocklist textarea PUT the whole vision config on every keystroke. Tracks the edit in local state, commits on blur — matching `BeingTab`'s `defaultValue`+`onBlur` pattern for its own free-text fields.
- **U3-02/U3-04** (lazy tab mounting): all 12 tab bodies were static imports (all landed in `Settings.tsx`'s own bundle chunk regardless of which single tab a visit ever renders). Converted every one to `React.lazy()`, wrapped in one `<Suspense>` around `<Tabs>` (only one `TabsContent` is ever mounted at a time, so at most one lazy import is ever in flight). Verified real code-splitting with an actual `vite build` — `SystemTab`, `SafetyTab`, `VisionTab`, `KnowledgeTab`, `BeingTab`, `SecurityTab`, `DevicesTab`, `AlertsTab`, `AboutTab`, `DebugTab` all ship as separate chunks now.

  Separately, Settings' own mount effect fired seven data-loading functions together regardless of which tab was about to show — opening Settings on About still fetched System's/Alerts'/Safety's/Knowledge's data. Split the monolithic `loadSettings()` into four tab-owned loaders (`loadSystemInfoAndDiscoveries`, `loadAlertRules`, `loadPolicy`, `loadRagStatsAndIndexes`) gated behind a `loadedTabsRef`-tracked effect keyed on the active tab: a tab's data loads once, the first time it becomes active, and switching back to an already-visited tab doesn't refetch. The three post-mutation refresh call sites (add knowledge source, reindex ×2) now call `loadRagStatsAndIndexes()` directly instead of the whole `loadSettings()` — strictly more correct, since before they also silently re-fetched System/Alerts/Safety data for no reason.

  Left Settings.tsx at its current size (~920 lines) — the packet notes the shell is well over the original `<300` target and asks only for the lazy mounting, not a size reduction.
- **DS-04** (three dead component files from SETTINGS-REDESIGN Phase 1): found via a dedicated search agent, independently re-verified with grep before deletion. All three were orphaned by commit `04e49f4b` ("Phase 1 — eliminate dead code and dangerous UI"), which stripped their imports/usages from `Settings.tsx` but never deleted the underlying files:
  - `components/CompressionSettings.tsx` (376 lines) — Phase 1 commit message: "caused models.yml corruption"
  - `components/domain/ChromaDBSettings.tsx` (725 lines) — "being retired"
  - `components/domain/DatasetManager.tsx` (412 lines)
  Deleted all three, plus their dead re-export lines in `components/domain/index.ts`.

## Task 5 — Small dead affordances

- **CC-02**: `SendToChat`'s newConversation distinction (click = continue, shift+click/right-click = new conversation) was pure theater — every producer set `OpenChatEvent.newConversation`, but `Layout.tsx`'s `halbert:open-chat` handler never read it. Removed rather than wired up, per the continuity direction (one seamless chat, hidden topic threads — not a chooser between conversations). Swept every producer, not just `SendToChat.tsx` itself: `SendToChat.tsx` (the prop, both handlers, the icon/tooltip branching), `AIAnalysisPanel.tsx` (×2), `SystemItemActions.tsx` (×3), `ConfigFileButton.tsx`, `Backups.tsx`, `Services.tsx`, `Sharing.tsx`, `Network.tsx` (×2). `ConfigFileButton`'s separate `startNewChat` prop is untouched — it gates whether the open-chat event fires at all, not which conversation it opens into, so it isn't the same dead affordance.
- **FEAT-02**: `Backups.tsx`'s "Run Now"/"Run All" buttons were `alert('Would run backup: ...')` — removed (no gated run-backup route exists), same reasoning as SystemTab's "Clear Cache" placebo above.

## Task 6 — Tests for untested surfaces (best-effort, P2)

Covered all 14 files the packet named (the "9 settings tabs" count in the packet is off-by-one against what's actually on disk — 8 settings tabs were untested, matched exactly): `AboutTab`, `AlertsTab`, `DebugTab`, `KnowledgeTab`, `SafetyTab`, `SecurityTab`, `SystemTab`, `VisionTab` (settings tabs); `DiscoveredPeerCard`, `NodeFleetCockpit` (fleet); `Findings`, `Home`, `Terminal` (pages); `VoiceEnrollmentModal` (audio). 109 new tests across 14 new sibling `*.test.tsx` files. `PeerPairingModal.tsx` was deliberately left untested — it belongs to OPUS-03's pairing-logic domain, and the packet's own note ("you may only replace literal colour classes there — coordinate") reads as a boundary on that file, not just its colors.

Split the work: wrote `Terminal.test.tsx` (8 tests — xterm mocked the same way the existing `TerminalTile.test.tsx` mocks it, since jsdom has no canvas) and `KnowledgeTab.test.tsx` (24 tests — a purely presentational component, no fetch mocking needed, driven entirely through props) directly; dispatched three parallel background agents for the other 12 files, each given the actual current source of its targets to read first (not assumptions) and pointed at this repo's existing test-file conventions as style references. Verified every agent's output myself afterward: read a sample of the produced test files, ran the full frontend `vitest`/`tsc` suite, and found and fixed the one real defect (a duplicate-text query in `Findings.test.tsx` — `getByText('Secure')` collided with a `StatusBadge` rendering that exact word for one fixture finding — switched to `getAllByText('Secure')[0]`, confirmed against DOM order).

No component file was modified by any of this work — confirmed via `git status`/`git diff --stat` after every batch, both by the agents themselves and independently by me.

**One real, pre-existing bug found and deliberately left unfixed** (out of this packet's scope — flagged for a follow-up): `EntityList.tsx:54` seeds its local `entities` state from the `entities` prop only at mount (`useState(initialEntities)`, no syncing `useEffect`). On `Home.tsx`'s connect flow, `setConnected(true)` renders `EntityList` with an empty array before the async `loadEntities()` fetch resolves, so newly loaded entities never appear until something forces a full remount. Verified directly (the fetch fires, Home's own state updates, but the DOM never shows the entity). Likely fix: `useEffect(() => setEntities(initialEntities), [initialEntities])`, or drop the local copy and keep only the optimistic-toggle bookkeeping separately. `Home.test.tsx` was written to assert what `Home.tsx` actually does today rather than assert around this bug.

Two smaller observations noted (not bugs, not touched): `SecurityTab.tsx`'s `saveSecurity` merges into the raw fetched `config?.security` rather than the client-defaulted `sec` object used for rendering — fine given current backend behavior, worth eyes if the backend ever omits the `security` key entirely; `SafetyTab.tsx`'s three tool-policy handlers mix plain-object and functional-updater calls to `setPolicy` — inconsistent style, not a bug.

## Verification (final, cumulative)

Frontend (`halbert_core/halbert_core/dashboard/frontend`):
- `npx vitest run`: **86 files / 833 tests, all passing** (was 719/719 on `main` before this packet's work started; 724/724 through Task 4/5; +109 tests from Task 6 lands exactly on 833, confirming no file was missed or double-counted).
- `npx tsc --noEmit`: clean throughout, verified after every task and again at the very end.
- One flaky test observed once (`useAgentStream.strictmode.test.tsx`, unrelated to any file this packet touched — passes in isolation and on every other full run, including the final one).

Design system (`packages/design-system`): `npx vitest run` — 74/74 (was 71/71 before the new `NavRail` coverage).

Repo root:
- `scripts/check_literal_colors.py --check`: OK, 211 literal classes, none gained (fresh baseline recorded).
- `scripts/check_contrast.py`: PASSED, every licensed pair clears its WCAG floor in both themes.
- `wt_pytest.py halbert_core/tests/test_frontend_no_relative_urls.py`: 4/4 passing (was 1 failing on main before Task 1).

## Skipped / deferred

- `ROUTE-01`: skipped, already fixed by OPUS-03 (see top of this doc).
- `pages/Memory.tsx` routing decision: left to SONNET-05 (`RAG-21`), per the packet's own fallback instruction.
- `DS-10` hex-color cleanup: only listed, not fixed, per the packet's explicit scope ("fix the ones in files you already touch") — none of the 8 files with real (non-test, non-comment) hits were touched by any other task in this packet.

## Nothing pushed to origin

All eight commits above are local to the `fix/frontend-mechanical` branch in the worktree at `/Volumes/4TB-BAD/Halbert-worktrees/fix-frontend-mechanical`. No `git push` was run at any point, per the dispatching session's explicit deviation instruction.
