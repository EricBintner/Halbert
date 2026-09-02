# DISPATCH SONNET-04 — Frontend: dead routes, nav entry points, token ratchet, REV-08 mechanical fixes

**Owner:** a Sonnet session. **Effort:** medium; all items are line-targeted.
**Parent:** `.handoff/HANDOFF-STATE-OF-WORK-2026-09-01.md` §6.5. Evidence ids: `ROUTE-02`, `ROUTE-03` (F15), `peerApi` (pytest triage), `R08-01..07`, `FE-10`/`R08-04` (F19/F24), `U3-04`, `U3-02`, `CC-02`, `FEAT-02`, `NAV-01`, `ORPHAN-01`, `FE-15` in `.handoff/audit-2026-09-01/AUDIT-FINDINGS-DETAIL.md`.

## Shared rules
- Fresh worktree off main (`-b fix/frontend-mechanical`). `git branch --show-current` before every commit. No trailers.
- Frontend checks from `halbert_core/halbert_core/dashboard/frontend`: `npx vitest run`, `npx tsc --noEmit`; from the repo root: `arch -arm64 .venv/bin/python scripts/check_literal_colors.py --check` and `scripts/check_contrast.py` (CI runs both; the ratchet is currently RED on main). Python: `arch -arm64 /Volumes/4TB-BAD/Halbert/.venv/bin/python wt_pytest.py halbert_core/tests/test_frontend_no_relative_urls.py`.
- Founder rules: colours only from the shared tokens (`text-success/-warning/-error/-info`, `bg-muted`, `text-muted-foreground`, …), never hardcoded; no emoji in UI; never write "Sovereign" on a user-facing surface; never name AI models in UI copy.
- Do not touch `hooks/useAgentStream.ts`, `components/agent/AgentChat.tsx`, `MessageContent.tsx`, `ThinkingPanel.tsx` (OPUS-05), nor `PeerPairingModal.tsx`/`DiscoveredPeerCard.tsx` logic (OPUS-03; you may only replace literal colour classes there — coordinate).
- Never edit `MASTER-TODO.md`; results → `.handoff/RESULTS-SONNET-04-<date>.md`.

## Task 1 — Three dead API paths (P1, one line each + a test)
- `ROUTE-02`: `components/settings/tabs/BeingTab.tsx:21` sets `API_BASE = apiUrl('/api')` then `:59, :73, :92, :108` fetch `${API_BASE}/api/persona/...` → `/api/api/persona/*` 404 (real routes `/api/persona/*`, `routes/persona.py:52`). Fix the four fetches; add a BeingTab vitest asserting the URL.
- `ROUTE-03`: `components/audio/AudioSettings.tsx:73` and `:108` hit `/api/being`, which does not exist (`routes/being.py` only serves `/being/events*`); the config endpoints are `GET/POST /api/settings/being` (`settings.py:3052, :3070`). Repoint both; verify the POST body `{quiet_hours}` matches what `settings.py:3070` accepts; test.
- `lib/peerApi.ts:122` `const API_BASE = ''` → 9 bare `fetch('/api/peers|fleet…')` at `:151-229` bypass `apiBase` → 404 inside the Tauri webview (`test_frontend_no_relative_urls.py:98` fails on main). Use `apiUrl(...)`. The second hit, `StandbyController.tsx:76`, is a false positive (consumed via `apiUrl(DISPLAY_REPORT_PATH)` at `:200`) — adjust the guard test's allowlist rather than the component.
(`ROUTE-01`, the backend `/devices` mount prefix, belongs to OPUS-03 — but if they have not started, the one-line `prefix="/api"` at `dashboard/app.py:306` plus a mounted-route test through `create_app()` is yours; say so in results.)

## Task 2 — Nav entry points (`R08-01`, `NAV-01`) (P1)
`Layout.tsx:70-91` `navSections` = Dashboard, Home, Findings, Services, Storage, Backups, Terminal; `App.tsx:123-134` still routes `/gpu /containers /development /network /sharing /apps /approvals` with no link anywhere (`getPendingApprovals` consumed only by `pages/Approvals.tsx`). Add an Approvals item (Intelligence & Findings section) and the promised top-bar pending-count badge polling `getPendingApprovals()`. For GPU/Containers/Development/Network/Sharing/Apps: re-rail, make sub-views, or remove the routes — founder call; default: re-rail under a "System" section. Add a Layout test asserting every `App.tsx` route has an entry point. `ORPHAN-01`: `pages/Jobs.tsx` and `pages/Memory.tsx` are not routed or imported anywhere — delete or route (default delete Jobs; route Memory only if the ChromaDB memory page is kept, see SONNET-05 `RAG-21`).

## Task 3 — Literal-colour ratchet red on main (`R08-04`/`FE-10`, `R08-03`) (P1, CI is red)
`scripts/check_literal_colors.py --check` fails: `StateBadge.tsx` 7→12, `audio/AcousticAnomalyModule.tsx` 0→9, `audio/AcousticAuraIndicator.tsx` 0→4, `audio/VoiceEnrollmentModal.tsx` 0→3, `fleet/DiscoveredPeerCard.tsx` 0→2, `fleet/NodeFleetCockpit.tsx` 0→20, `settings/devices/DeviceCard.tsx` 0→15, `settings/tabs/VisionTab.tsx` 0→6, `shell/InstanceSwitch.tsx` 0→4, `ui/button.tsx` 0→4, `pages/Findings.tsx` 0→1. VisionTab/Findings are renames (baseline still keyed to `Settings.tsx`/`Security.tsx`) — re-baseline those two; sweep the other nine to semantic tokens; then run `--baseline` and commit the regenerated `.literal-colors-baseline.json`. Do not simply re-baseline the debt away. Also `DS-10` reports 56 hardcoded hex colours in dashboard src — list them in results; fix the ones in files you already touch.

## Task 4 — REV-08 residuals (P2/P3)
- `R08-02`: `packages/design-system/src/surfaces/NavRail.tsx:123-137` declares `role=tablist/tab` with no arrow keys, roving tabindex, ids or `aria-controls`; `Settings.tsx` renders 12 `TabsContent` panels with no triggers wired. Either implement Up/Down/Home/End + roving tabindex and `aria-controls`/`aria-labelledby` pairs, or drop the tabs roles for nav semantics with `aria-current` and give each panel an `aria-label`. Update `Settings.tabs.test.tsx`.
- `R08-05`: indexing poll interval leaks on Settings unmount / stacks on Re-index.
- `R08-07`: placebo "Clear cache", Debug label targets a Button, blocklist PUT per keystroke (VisionTab).
- `U3-04`/`U3-02`: `React.lazy`/`Suspense` tab mounting (all 10 tabs statically imported; mount effect fires ~7 loaders regardless of tab); shell is 880 lines vs the packet's <300 — do the lazy mounting, leave the line count.
- `DS-04`: three dead component files from SETTINGS-REDESIGN Phase 1 remain — delete (list in evidence).

## Task 5 — Small dead affordances
- `CC-02`: `SendToChat.tsx:42` `newConversation` prop, `:95` Shift+click, `:117` right-click, `:122-125` icon + tooltip "Continue in chat (Shift+click for new)" — consumed by nothing (`Layout.tsx:242-253` ignores it). Either map it to a `new_thread` request in `hostConversation` or remove the flag, branches, icon and tooltip from all producers. Default: remove (the continuity direction is one seamless chat).
- `FEAT-02`: `pages/Backups.tsx:168-170` "Run" is `alert('Would run backup…')`. Remove the button until a gated run-backup route exists (none does).

## Task 6 — Tests for recently merged, untested surfaces (`FE-15`) (P2, as time allows)
Zero-test files worth a sibling test: `fleet/NodeFleetCockpit.tsx`, `fleet/DiscoveredPeerCard.tsx`, the 9 settings tabs without tests, `pages/Findings.tsx`, `pages/Home.tsx`, `pages/Terminal.tsx`, `audio/VoiceEnrollmentModal.tsx`.

## Results
`.handoff/RESULTS-SONNET-04-<date>.md`: per task, files + tests, `vitest`/`tsc`/ratchet/contrast output, and the nav decision you took.
