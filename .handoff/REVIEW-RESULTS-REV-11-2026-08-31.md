# Review Results — REV-11: Chat UI Performance, Streaming State & Accessibility (2026-08-31)

Reviewer: GLM-5.3 (adversarial pass with verification)
Packet: `.handoff/REVIEW-PACKET-11-CHAT-UI-PERFORMANCE-AND-ACCESSIBILITY.md` (2026-08-29)
Scope: the packet's still-open items + the NEW code that landed since (rAF token buffer `useTokenBuffer` / commit 7fad824b; ARIA work in AgentChat/useAgentStream / commit c5cd65ce), audited for defects the new code may have introduced.

Verification performed on this branch:
- `npx vitest run` — **451/451 pass** (matches baseline)
- `npx tsc --noEmit` — **clean**
- Backend cross-checks: `routes/agent.py` (message SSE, cancel endpoint), `agents/state_machine.py` (`cancel_session`, `_turn_status`, `_settle_turn`) to verify frontend lifecycle claims end to end.

---

## 1. Verdicts per area

| Area | Verdict |
|---|---|
| **rAF token buffering (`useTokenBuffer`)** | **PASS.** The hook is clean: flush-on-end covers stream close, cancel and error paths (`flushNow` at `useAgentStream.ts:365-368, 964, 1040, 1061, 1069`); `set` drops the buffered draft so a committed `response_complete` text never carries stream leftovers; `clear` resets both so no draft leaks across turns; a pending frame is cancelled at unmount. Backgrounded-tab rAF throttling (the packet's "tokens lost if the stream closes before the next frame" concern) is covered by the synchronous flush at stream end. Contract pinned by `useTokenBuffer.test.ts` (320 lines). No defects found in the hook itself. |
| **Streaming state / SSE lifecycle (`useAgentStream`)** | **DEFECTS.** The buffer integration is correct, but the surrounding lifecycle has one high-severity defect (stray abort + cancel POST on every completed turn, F1), one functional defect (queued-message auto-send bypasses the parked-turn guards, F2), and one dev-mode defect class left behind by the very commit that claimed to fix it (F3). |
| **Accessibility (AgentChat + new ARIA work)** | **MIXED.** The 11 ARIA gaps addressed in c5cd65ce are genuinely fixed: a queued, two-channel live region (`LiveRegion.tsx` + `lib/announce.ts`), a real combobox/listbox mention popup with `aria-activedescendant`, feed semantics (`role="feed"`, `aria-posinset`/`aria-setsize`, day-label-describedby), per-state announcements, assertive error/confirmation. Residual out-of-file items 7.6–7.11 remain open (see worklist), and the new combobox has one minor `aria-expanded` mismatch (F11). |
| **Performance (beyond the buffer)** | **MOSTLY RESOLVED.** The O(n²) per-token re-render is fixed at the source (commits per frame, not per token). C2/C3 remain open in reduced form: per-frame O(n) re-parse of the growing text in `MessageContent`/`ThinkingPanel` (F12). Stored turns are already protected by `TurnArticle` memoization. |
| **useTimeline (C4/C5)** | **STILL OPEN.** No request abort anywhere; single shared `inFlight` boolean makes concurrent-variant clicks silent no-ops (F10). |

The packet's third P0 ("message ordering desync when background proactive events arrive mid-stream") was **not reproduced**: events are dispatched in strict SSE arrival order from the single reader loop (`useAgentStream.ts:951-960`), and nothing reorders them; no desync path found in the reviewed code.

---

## 2. Findings (most severe first)

### F1 — Every normally-completed turn aborts the SSE stream and POSTs cancel for itself — CONFIRMED
**File:** `halbert_core/halbert_core/dashboard/frontend/src/hooks/useAgentStream.ts:379-390`

The cleanup effect depends on `[isStreaming]`, so its cleanup runs at **every** `isStreaming` transition — including the normal **true→false** one at stream end. That cleanup (a) calls `source.close()`, aborting the fetch while the stream is still draining, and (b) sees the captured `isStreaming === true` and a still-set `sessionIdRef.current`, so it **POSTs `/api/agent/cancel/<sid>` for the session that just completed normally**. The comment above the effect considers only the false→true direction; the true→false direction was missed. The request firing is deterministic from the code; both harms are real:

1. **Dropped end-of-turn events.** The abort kills `reader.read()` mid-drain; any event emitted after `response_complete` that has not yet been read (`session_ended`, late `terminal_complete`, `task_completed`) is silently dropped.
2. **A fully-streamed reply persisted as "cancelled".** On the backend the turn lock is held through the whole unwind: `active_sessions.pop` happens only in `_settle_turn` (`state_machine.py:727`), *after* `end_turn`'s persistence writes. The stray cancel arrives in that window → `cancel_session` raises the `cancelled` flag (`state_machine.py:1261`) → `_turn_status` (`state_machine.py:880-888`) names the turn `cancelled`. Timing-dependent (frontend POST vs. end_turn writes), but the window is milliseconds on both sides and exists on **every** turn.

**Scenario:** admin asks a normal question; the reply streams to completion; the frontend's own cleanup fires a cancel for the turn; if it lands mid-`end_turn`, the Timeline later shows a `cancelled` marker under a complete reply and downstream thread receipts record the turn as cancelled.

**Fix:** make the effect unmount-only — `deps: []` with an `isStreamingRef` read inside the cleanup — or have the stream-end paths (`response_complete` / loop-exit / `cancel()`) null out `sessionIdRef.current` (or the source) so the cleanup has nothing to cancel. The unmount case the effect was written for keeps working either way.

### F2 — Queued-message auto-send bypasses the parked-turn guards — CONFIRMED
**File:** `halbert_core/halbert_core/dashboard/frontend/src/components/agent/AgentChat.tsx:552-583`

The fold effect (`AgentChat.tsx:490-497`) deliberately refuses to fold a turn that is parked on `pendingConfirmation`/`awaiting_confirmation` or an undecided diff proposal — the ConfirmationDialog and Apply/Reject controls must survive. The queued-message drain effect has **no such guard**: it fires whenever `!isStreaming && messageQueue.length > 0`.

**Scenario:** the admin types a follow-up while the agent is streaming (message queued, `AgentChat.tsx:890-897`); the turn ends parked on a tool approval — the SSE stream is already closed (`state_machine.py` `cancel_session` docstring: a paused turn's stream has closed), so `isStreaming` is false with the confirmation dialog on screen; 100 ms later the queue timeout fires: `foldLiveTurn()` folds the parked turn (which the fold effect exists to prevent), `sendMessage` replaces the session via `initSession` (clearing `pendingConfirmation`), the `ConfirmationDialog` unmounts, and the pending approval is silently dropped — it is never answered, confirmed, or rejected, server-side or on screen.

**Fix:** gate the queue drain on the same parked-turn conditions as the fold effect (park the queue while a confirmation or pending proposal is showing; drain once resolved or explicitly dismissed).

### F3 — Side effects remain inside the `setSession` updater, contradicting commit 7fad824b's own claim — CONFIRMED (dev/StrictMode)
**File:** `halbert_core/halbert_core/dashboard/frontend/src/hooks/useAgentStream.ts:488-510` (model_selected: `announce` + `setTurnModel`), `:557-575` (response_complete: `setProvenance`/`setResponse`/`setIsStreaming`/`onComplete`), `:577-579`, `:581-586` (module_invoke), `:588-595` (error: `onError` + `setIsStreaming`), `:603-606`, and the tool callbacks at `:526`, `:544`, `:554`.

Commit 7fad824b's message says it moved "the state_change callback and the completion flush out of the setSession updater, where StrictMode double-invocation would double-announce progress and re-flush the buffers" — but only those two moved. `main.tsx` wraps the app in `React.StrictMode`, and React 18 double-invokes state updaters in dev, so every remaining in-updater side effect runs twice:

- `announce` for a model fallback (`:495-499`) — the sentence is spoken **twice** (exactly what the file's own comment at `:434-436` says must not happen);
- `setModuleInvocations(prev => [...prev, …])` (`:582`) — the invocation is enqueued twice and renders **duplicated**;
- `options.onError` (`:590`) — fired twice.

**Fix:** hoist all of these out of the updater exactly as `:437-451` already does for the confirmation announcement, the chunk pushes and the flush. The pure updater should only ever compute the next `session`.

### F4 — Timeout error message points at a settings panel that no longer exists — CONFIRMED
**File:** `halbert_core/halbert_core/dashboard/frontend/src/hooks/useAgentStream.ts:884`

The connection-timeout error tells the admin: *"Try increasing timeout in Settings > AI > Performance Tweaks."* — but the comment three lines up (`:866-868`) states "The old GPU Tweaks localStorage override was removed; httpx on the backend handles retry/timeout policy," and grep confirms no Tweaks UI remains anywhere in the frontend. A user-facing error that sends the admin hunting for a nonexistent control.

**Fix:** drop the sentence ("Connection timed out after N min." is complete), or point at a real control.

### F5 — ThinkingPanel: no `aria-expanded`/`aria-controls` on either toggle, and emoji in the UI — CONFIRMED (audit 7.6/7.7, still open)
**File:** `halbert_core/halbert_core/dashboard/frontend/src/components/agent/ThinkingPanel.tsx:44-64` (outer toggle), `:107-118` (per-section toggle)

Both disclosure buttons toggle content with no `aria-expanded` and no `aria-controls`, and the header carries 🧠/💭 as the only distinguishing icon — unlabelled for assistive tech and a violation of the founder no-emoji rule. The codebase's own newer components (`ToolExecutionCard.tsx:96-122`, AgentChat) use real `<button>`s with `aria-expanded`/`aria-controls` and lucide icons with `aria-hidden`, so the pattern is established in-repo.

**Fix:** `aria-expanded` + `aria-controls` → an id'd content region on both toggles; replace the emoji with a lucide icon (`aria-hidden`) or plain text.

### F6 — StateBadge pulse ignores `prefers-reduced-motion` — CONFIRMED (audit 7.10, still open)
**File:** `halbert_core/halbert_core/dashboard/frontend/src/components/agent/StateBadge.tsx:100-103`

`animate-ping` runs unconditionally for every active state. The codebase already knows the fix — AgentChat's streaming caret uses `motion-reduce:animate-none` (`AgentChat.tsx:1166`). Vestibular users get a continuously pinging dot for the whole turn.

**Fix:** add `motion-reduce:animate-none` to the ping span (or `motion-safe:` on the animation).

### F7 — Focus dropped after a successful "Forget this" — CONFIRMED (audit 7.9, still open)
**File:** `halbert_core/halbert_core/dashboard/frontend/src/components/agent/Timeline.tsx:350-365` (`confirm`), `:440-496` (controls row)

On success, `pending`/`confirming` reset and `failure` stays null, so the controls row — which holds the **focused** Forget button — unmounts and focus falls to `<body>`. A screen-reader user who just executed an irreversible privacy action loses their place in the feed and hears nothing further (the live region said "Turn forgotten" before the focus drop).

**Fix:** on success, move focus deliberately — to the article (`role="article"` element) or the redaction marker text.

### F8 — HostShell conversation column is not a landmark — CONFIRMED (audit 7.11, still open)
**File:** `halbert_core/halbert_core/dashboard/frontend/src/components/shell/HostShell.tsx:75-79`

The conversation wrapper is a plain `<div>` with `aria-label="Conversation"` — `aria-label` on a div with no role exposes no landmark, so the label is dead. The sibling `<aside aria-label="Context stage">` (`:88`) *is* a labelled complementary landmark, making the asymmetry concrete: a screen-reader user can jump to the context stage but not to the conversation.

**Fix:** `role="region"` on the conversation wrapper (or a `<main>`/`<section>` element).

### F9 — Scrollable `<pre>` blocks are not keyboard-reachable — CONFIRMED (audit 7.8, still open)
**Files:** `ThinkingPanel.tsx:81-87` (`overflow-auto`), `ToolExecutionCard.tsx:140, 159, 169` (`overflow-x-auto`), `domain/CodeBlock.tsx:245, 316` (`overflow-x-auto`)

None carry `tabIndex="0"`, so keyboard users cannot scroll clipped output at all. This is where the timeline's own design docs live — inaccessible to the keyboard.

**Fix:** `tabIndex={0}` + a focus-visible ring on every scrollable `<pre>`.

### F10 — useTimeline: no request abort, and one `inFlight` flag for all load variants — CONFIRMED (audits C4/C5, still open)
**File:** `halbert_core/halbert_core/dashboard/frontend/src/hooks/useTimeline.ts:199, 280-349`

- **C4:** nothing aborts. The initial load only sets a `cancelled` flag (`:238-267`); `loadOlder`/`loadAround`/`loadLatest` have no cancellation at all — requests run to completion after the consumer is gone.
- **C5:** `loadOlder`, `loadAround` and `loadLatest` share one `inFlight` boolean. **Scenario:** the admin clicks "Load earlier" (slow request in flight), then clicks the thread chip or "Back to latest" — `loadLatest` returns `false` immediately and silently, so `retryLoad` announces nothing and the click looks dead.

**Fix:** an `AbortController` per request passed through `api.getTimeline`, and per-variant in-flight tracking (or a queued intent) so a later-named load supersedes rather than silently no-ops.

### F11 — `aria-expanded` claims a mention popup that is not rendered — CONFIRMED (new code, minor)
**File:** `halbert_core/halbert_core/dashboard/frontend/src/components/agent/AgentChat.tsx:1371`

`aria-expanded={showMentions}` is true whenever an `@` filter is active, but the listbox renders only when `filteredMentionables.length > 0` (`:1271`). With a filter matching nothing, a screen reader is told "expanded" while `aria-controls` is `undefined` and no popup exists.

**Fix:** `aria-expanded={showMentions && filteredMentionables.length > 0}` — or keep the listbox mounted with a "no matches" option, which also removes the popup's layout push.

### F12 — PLAUSIBLE (minor): `handleEvent`/`sendMessage` identity churns every render
**File:** `useAgentStream.ts:840, 979`

`handleEvent` depends on `options`, and AgentChat passes a fresh object literal each render (`AgentChat.tsx:332-348`), so `handleEvent`, `sendMessage` and `confirmAction` change identity on every render. Harmless today (AgentChat correctly reads them through `foldInputs`, refreshed per commit), but it is one `useEffect` dependency away from a re-subscribe loop, and `useCallback` currently buys nothing.

**Fix:** store `options` in a ref inside the hook (`optionsRef.current = options`) and depend on the ref, making the callbacks stable.

---

## 3. Resolved from the packet (verified in this pass)

1. **SSE reader leak / abort cleanup (P0 #1)** — resolved. The fetch wrapper's `close()` aborts the reader; the backend's `aclosing` explicitly runs `process()`'s finally on client disconnect so the turn lock is always released (`routes/agent.py:1480-1509`).
2. **O(n²) per-token re-render (perf P0)** — resolved by `useTokenBuffer` (7fad824b), verified end to end including stream-close-before-frame, cancel, error and background-tab cases.
3. **Concurrent prompt submission race (P0 #2)** — resolved at the connection level: a second send closes the old source (abort → backend generator close unwinds the superseded turn), and the backend queues on the turn lock (`agent.py:1429-1434`). The queued-message UX path has its own defect (F2), but the connection/state race the packet described is handled.
4. **Message ordering desync on mid-stream proactive events (P0 #3)** — not reproduced; events are handled in strict arrival order in one reader loop.
5. **11 ARIA gaps in AgentChat/useAgentStream** — resolved by c5cd65ce (live regions with queueing, combobox listbox with `aria-activedescendant`, feed semantics, state announcements, assertive error/confirmation).
6. **7.5 ToolExecutionCard clickable div** — resolved: a real `<button>` with `aria-expanded`/`aria-controls` (`ToolExecutionCard.tsx:96-122`).
7. **Timeline feed `aria-busy` tracking streaming rather than loading** — resolved by the correct split: the streaming scroll container carries `aria-busy={isStreaming}` (`AgentChat.tsx:1028`) while the feed's own `aria-busy={loading}` stays scoped to paging (`Timeline.tsx:613`).

---

## 4. Confirmed still-open worklist

Ordered by severity; items F1–F4 and F11 are new from this review, the rest are carried from the prior audit.

| # | Item | Where |
|---|---|---|
| 1 | F1 — unmount-only cleanup effect; stop the stray abort + cancel POST on every completed turn | `useAgentStream.ts:379-390` |
| 2 | F2 — gate the queued-message drain on the parked-turn guards (confirmation / pending proposal) | `AgentChat.tsx:552-583` |
| 3 | F3 — hoist remaining side effects out of the `setSession` updater (StrictMode double-announce / duplicate module invocation) | `useAgentStream.ts:488-606` |
| 4 | F4 — remove the dead "Settings > AI > Performance Tweaks" instruction from the timeout error | `useAgentStream.ts:884` |
| 5 | F5 / audit 7.6-7.7 — ThinkingPanel `aria-expanded`/`aria-controls`; replace emoji | `ThinkingPanel.tsx:44-64, 107-118` |
| 6 | F7 / audit 7.9 — move focus after a successful redaction | `Timeline.tsx:350-365` |
| 7 | F6 / audit 7.10 — `motion-reduce` on the StateBadge ping | `StateBadge.tsx:100-103` |
| 8 | F8 / audit 7.11 — give the HostShell conversation column a landmark role | `HostShell.tsx:75-79` |
| 9 | F9 / audit 7.8 — `tabIndex={0}` on scrollable `<pre>`s | `ThinkingPanel.tsx:81`, `ToolExecutionCard.tsx:140/159/169`, `CodeBlock.tsx:245/316` |
| 10 | F10 / audits C4+C5 — AbortController per timeline request; per-variant in-flight tracking | `useTimeline.ts:280-349` |
| 11 | F11 — `aria-expanded` false when the mention listbox has no options | `AgentChat.tsx:1371` |
| 12 | F12 / audits C2+C3 — memoize `MessageContent`/`ThinkingPanel` and/or `useMemo` the parse work (per-frame O(n) over the growing text, now bounded to ~60 fps by the token buffer) | `MessageContent.tsx:19-41`, `ThinkingPanel.tsx:40, 133-189` |
| 13 | F13 (minor) — stabilize `handleEvent`/`sendMessage` via an options ref | `useAgentStream.ts:840, 979` |

---

## 5. Summary counts

- **CONFIRMED findings:** 11 (F1–F4, F5–F11) — F1 high, F2/F3/F4 medium, F5–F11 low.
- **PLAUSIBLE findings:** 1 (F12/F13, minor code-hygiene).
- **Resolved from packet:** 7 items (§3).
- **Still open (prior audit + new):** 13 worklist items (§4).

The rAF token buffer itself — the packet's central deliverable — is correct and well-tested; the defects that remain live in the surrounding streaming lifecycle, not in the buffer.