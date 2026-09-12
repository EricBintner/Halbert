# PKT-OTHER-P6a — Guarded localStorage accessor (11 sites)

Tier: **sonnet**   Milestone: **M4**   Effort: **S**
Collision lane: **none (file-disjoint)**   Merge order: **n/a**
Verified against: halbert `main` @ `fbd725e9` (2026-09-11)

---

## 1. Packet

**OTHER-P6a** — Guarded localStorage accessor (11 sites).

## 2. User problem

The Halbert dashboard has 22 unguarded `localStorage.getItem/setItem/removeItem` calls across 8 frontend files. The most critical is `contexts/DebugContext.tsx:37`, where `localStorage.getItem('halbert_debug_mode')` runs inside a `useState` initializer of `DebugProvider` — the provider that wraps the entire app at `App.tsx:113`. When storage throws (Tauri webview with storage disabled, Safari/private mode, a user "block all cookies" setting), the exception escapes during mount and the whole dashboard renders nothing: no chat, no conversation, a blank window with no recoverable path. The registry counts 11 accessor sites; the blast radius of just the DebugContext one is total dashboard failure. The remaining sites (`ShellModeContext.tsx` — base-shell persistence; `lib/peerApi.ts` — peer bearer token read at every peer call; `pages/Services.tsx`, `pages/Network.tsx`, `pages/Storage.tsx` — cache/custom-name persistence) each fail with an uncaught exception in the middle of an event handler or render. One site is already correctly guarded (`components/legal/CloudDisclosureModal.tsx:66` wraps setItem in try/catch) and one file hand-rolls the guard (`lib/apiBase.ts:33-55` does `typeof localStorage === 'undefined'` plus try/catch inline) — proof the failure mode is real and already known, but there is no single accessor so each site repeats (or forgets) the dance. Deep-eval OTHER-P6 (group4 file, line ~383-397) confirms: ACCEPT the guarded localStorage accessor, S effort, ship now, prevents a total dashboard crash; the rest of OTHER-P6 (settings reload table, projected-view diff, probe cache) is RESHAPE'd out of this unit.

## 3. What to build

One new module `src/lib/safeStorage.ts` plus migration of all unguarded sites, and a colocated test `src/lib/safeStorage.test.ts`.

**`src/lib/safeStorage.ts`** — a tiny module exporting three functions:
- `safeGetItem(key: string): string | null` — returns `localStorage.getItem(key)`, or `null` if storage is unavailable or throws. Wraps in try/catch AND a `typeof localStorage === 'undefined'` probe (the apiBase.ts pattern), because some environments throw on access, others leave the global undefined.
- `safeSetItem(key: string, value: string): boolean` — attempts `localStorage.setItem`; returns `true` on success, `false` on throw/quota/unavailable. Never throws.
- `safeRemoveItem(key: string): void` — attempts `localStorage.removeItem`; swallows any throw.

No wrapper class, no caching, no events. Add a short header comment in the house style (see `lib/apiBase.ts` header for tone): why this exists (Tauri webview with storage disabled takes the whole dashboard down at mount when a provider initializer throws) and the contract (callers treat `null` from get as "no stored value", treat `false` from set as "not persisted; in-memory state still updated").

**Migrate every site** (22 call expressions across these files — grep `localStorage\.(getItem|setItem|removeItem)` under `src/` excluding `*.test.*`):
1. `contexts/DebugContext.tsx:37,48` — `useState(() => safeGetItem('halbert_debug_mode') === 'true')`; `setDebugMode` calls `safeSetItem(...)` and proceeds with `setIsDebugMode` regardless of the boolean (debug mode stays on for the session even if persistence failed). This is the crash site; the initializer must not throw.
2. `contexts/ShellModeContext.tsx:67,109,123,142,161` — `safeGetItem(STORAGE_KEY)` in the initializer; each `localStorage.setItem(STORAGE_KEY, next)` becomes `safeSetItem(STORAGE_KEY, next)`. State transitions proceed even when persistence fails.
3. `lib/peerApi.ts:146,151,156` — `safeGetItem('halbert:peer-token')` (returns null → caller treats as unpaired, existing behavior), `safeSetItem`, `safeRemoveItem`.
4. `pages/Services.tsx:153,162,164` — JSON cache read/write via safe accessors. Note these sites do `JSON.parse(localStorage.getItem(KEY) || '{}')` — keep the `|| '{}'` fallback shape with `safeGetItem`.
5. `pages/Network.tsx:155,164,166` — same cache pattern as Services.
6. `pages/Storage.tsx:154,164` — custom-names load/save via safe accessors.
7. `lib/apiBase.ts:35-36,51-52` — replace the hand-rolled try/catch + `typeof` probe with the shared helpers (behavior preserved: hydrate returns null, set/remove failures are non-fatal). This is the deduplication win, not a behavior change.
8. `components/legal/CloudDisclosureModal.tsx:65-66` — already guarded; swap to `safeSetItem` for uniformity. Behavior identical.

**`src/lib/safeStorage.test.ts`** — vitest, colocated like the other lib tests (`apiBase.test.ts`, `slashCommands.test.ts`). Cover: (a) normal get/set/remove roundtrip; (b) `getItem` throwing (spy on `Storage.prototype.getItem` with `vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new DOMException('denied') })`) → `safeGetItem` returns null, `safeSetItem` returns false, `safeRemoveItem` does not throw; (c) `typeof localStorage === 'undefined'` path — harder in jsdom; skip if not mockable, the try/catch covers it; (d) DebugProvider smoke: render `DebugProvider` with `getItem` mocked to throw and assert children render (the mount-crash regression test — this is the one that pins the actual bug).

Files changed: 1 new lib module + 1 new test + 8 touched files. No colour, no UI surface, no model naming, no emoji involved — pure resilience plumbing.

## 4. What NOT to build

- NOT building the settings reload plan (`dashboard/settings_reload_plan.py`, projected-view diff) — that is the other half of OTHER-P6, RESHAPE'd to a separate follow-up unit (M effort, ship next), not this one.
- NOT building the subprocess probe cache in `development.py` — deferred per RESHAPE ("opportunistic, only if the file is open anyway").
- NOT building a generic storage abstraction with namespaces, TTL, serialization, or change events — three functions only; anything more invites scope creep and second-system effect.
- NOT adding an in-memory fallback store (Map-backed polyfill) — the contract is "persistence may silently not happen"; session state already lives in React state and a fake persistent layer would lie to callers about durability.
- NOT touching `sessionStorage` sites (none flagged), NOT auditing cookies/IndexedDB.
- NOT changing any UX copy, and NOT surfacing a "storage disabled" banner or notification — silent degradation is the spec; a banner is a product decision for the founder, not this packet.
- NOT migrating test files' localStorage use (`apiBase.test.ts`'s `localStorage.removeItem` in its cleanup hook is fine — tests run in jsdom where storage exists).

## 5. Target files
- `halbert_core/halbert_core/dashboard/frontend/src/contexts/DebugContext.tsx`

## 6. Dependencies

None — may dispatch immediately.

## 7. Effort

**S** — S — one small new module (~40 lines including header comment and types), one colocated test file, and mechanical one-line edits at 22 call sites across 8 files. No design decisions remain: the guard pattern is already proven in-repo (`lib/apiBase.ts:33-55` hand-rolls exactly this), the deep-eval verdict is ACCEPT-ship-now, and there is no dependency on any other unit. The only judgment calls are naming (`safeStorage.ts` per the deep-eval text) and whether DebugProvider's smoke test lives in the lib test or a context test — both trivial. A cold session can finish this in one sitting including the test run.

## 8. UX rationale

No user-facing surface changes — this packet is invisible when it works. The user-visible outcome is an absence: the dashboard no longer renders a blank window in a Tauri webview with storage disabled or in a private-mode browser; it opens normally with debug mode off and shell mode at default. Persistence failures degrade silently per the existing pattern in `apiBase.ts` (override applies for the page load, just not across reloads). No new copy, no banner, no indicator, no emoji, no colour (nothing visual at all), no model naming — Halbert's frame is untouched because nothing is said. Debug mode and shell-mode choices still persist exactly as before in the normal case; in the disabled-storage case the app simply doesn't remember, which is the correct subtractive behavior.

## 9. Acceptance criteria

1. `src/lib/safeStorage.ts` exists and exports `safeGetItem`, `safeSetItem`, `safeRemoveItem` with the null/boolean/swallow contract.
2. `grep -rn "localStorage\.\(getItem\|setItem\|removeItem\)" src/ --include='*.ts' --include='*.tsx' | grep -v '\.test\.' | grep -v safeStorage.ts` returns zero hits — every production site routes through the helper.
3. `DebugProvider` mounts and renders children while `Storage.prototype.getItem` throws — pinned by the new regression test.
4. All prior behavior preserved: debug-mode flag round-trips, shell mode round-trips, peer token read/write works, Services/Network/Storage caches work in the normal (non-throwing) case.
5. `npm run typecheck` in `halbert_core/halbert_core/dashboard/frontend/` is clean.
6. No new dependencies, no changes outside `dashboard/frontend/src/`.

## 10. Verification (measured state, not model judgment)

Run from `halbert_core/halbert_core/dashboard/frontend/`:

1. `npm test -- safeStorage` — vitest must exit 0 with the new `src/lib/safeStorage.test.ts` passing, including the DebugProvider-mounts-while-getItem-throws regression test.
2. `npm test` — full frontend vitest suite exits 0 (no regressions in existing lib/component tests that exercise these contexts, e.g. `DebugTab.test.tsx`, `apiBase.test.ts`).
3. `npm run typecheck` — `tsc --noEmit` exits 0.
4. Measured grep gate: `grep -rnE "localStorage\.(getItem|setItem|removeItem)" src/ --include='*.ts' --include='*.tsx' | grep -v '\.test\.' | grep -v 'src/lib/safeStorage.ts' | wc -l` prints `0` (all 22 production sites migrated).
5. Optional runtime check via the browser-automation skill: launch the dashboard (`make dev-web`), evaluate `Storage.prototype.getItem = () => { throw new DOMException('denied') }` before reload, reload, assert the app shell renders (root element has children) instead of a blank page.

## 11. Exclusions

Split out of OTHER-P6 per its RESHAPE verdict (deep-eval group4, "If RESHAPE" line): the settings reload plan (`dashboard/settings_reload_plan.py` + declarative hot/restart table, S-M effort, "ship next") goes to a separate follow-up unit — call it OTHER-P6b — because it is backend Python, M-tier effort, and independent of the storage guard; the projected-view diff (resolved-model-per-slot before/after comparison) is deferred per RESHAPE (M effort, "can follow the basic table") and rides with OTHER-P6b or a later M5b tail unit; the subprocess probe cache in `development.py` (HM18-C14) is deferred per RESHAPE ("opportunistic, only if the file is open anyway") — M5b tail, picked up only when `development.py` is touched for another reason. Within the storage scope itself: the `typeof localStorage === 'undefined'` jsdom test branch may be dropped if not mockable (try/catch covers the real environments); no in-memory polyfill, no storage-disabled banner, no sessionStorage/IndexedDB audit — dropped as out of scope for an S-tier crash fix.

---

## OSS reference

Greenfield — no direct OSS reference; see the deep-eval.

## Repo traps

- Every Python test run needs the `arch -arm64` prefix: `arch -arm64 .venv/bin/python -m pytest halbert_core/tests`.
- From a git worktree use `arch -arm64 ./wt_pytest.py halbert_core/tests`, NEVER bare pytest (the editable install pins halbert_core to the MAIN tree).
- `main` is NOT green. Known-red baseline (2026-09-11): test_agent_model_override.py, test_agent_model_selected_event.py, test_no_model_names_in_user_facing_source.py, test_num_ctx.py (~23 failures). A failure is yours iff absent from this baseline.
- Work in a git worktree; narrow commits; concurrent sessions edit this repo.
- NEVER add Co-Authored-By or 'Generated with …' trailers. Subject + body only.
- No emoji anywhere. Colours only from shared-tokens/tokens.css (run scripts/check_contrast.py).
- Never name/recommend an AI model on any user-facing surface; connection slots, not model menus.
- Model locality: is_local_model() (model/llm_config.py:181) is the ONLY judge; :cloud tag is primary.
- Feature gating: has_capability() (capabilities.py:499); never _is_home_variant.
- Redaction: ingestion/redaction_registry.py enforced at security/display_transport.py; scrub BEFORE the model.
- Commands staged from the UI are staged, never executed.
- No users yet: no migrations/back-compat shims unasked; leave superseded data on disk, unread, never delete.
- Line references drift: re-anchor by grep before editing; a failed anchor is a rebase signal, not a spec change.
- Modify only this packet's Target files. .handoff/ is correspondence, not authority (ROADMAP.md + DECISIONS.md are the spine).
