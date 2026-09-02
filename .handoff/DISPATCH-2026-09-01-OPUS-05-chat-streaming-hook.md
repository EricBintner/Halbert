# DISPATCH OPUS-05 — Chat streaming hook: the stray cancel, parked-turn guards, StrictMode purity (REV-11)

**Owner:** an Opus session. **Effort:** medium; small surface, subtle React lifecycle. **Why Opus:** REV-11 F1 can flip a fully streamed reply to "cancelled" in the store, and the fixes interact with the queue and confirmation flows.
**Parent:** `.handoff/HANDOFF-STATE-OF-WORK-2026-09-01.md` §6.5. Evidence ids (area F19, F20-verified): `R11-01..14`, `CUA-04..09`, `U3-15/17/22/23`. Report: `REVIEW-RESULTS-REV-11-2026-08-31.md`; audit plan: `halbert_core/halbert_core/dashboard/frontend/docs/chat-ui-audit/README.md` (P0/P1 sprints done; P2/P3 remain).

## Shared rules
- Fresh worktree off main (`-b fix/chat-streaming-rev11`). `git branch --show-current` before every commit. No trailers.
- `npx vitest run` and `npx tsc --noEmit` in `halbert_core/halbert_core/dashboard/frontend` (699/699 and clean on main today). Root `scripts/check_literal_colors.py --check` is RED on main independent of you (SONNET-04 fixes it) — do not add literal colours.
- No emoji in UI (`R11-05` removes one); never name AI models in UI copy; colours from tokens.
- Files you own: `src/hooks/useAgentStream.ts`, `src/hooks/useTokenBuffer.ts`, `src/hooks/useTimeline.ts`, `src/components/agent/AgentChat.tsx`, `MessageContent.tsx`, `ThinkingPanel.tsx`, `StateBadge.tsx` (behaviour only), `src/store/**` where the session/turn status lives, and their tests. Do NOT edit `Layout.tsx`, `NavRail.tsx`, `BeingTab.tsx`, `AudioSettings.tsx`, `peerApi.ts`, `SendToChat.tsx` (SONNET-04) or `VoiceMode.tsx` (OPUS-02).
- Backend: if the fix for F1 needs the server side, the path that names a fully streamed turn "cancelled" is `agents/state_machine.py:871-896` — OPUS-01 owns that file; write the test and hand them the change.

## Task 1 — `R11-01`: every completed turn aborts its own stream and POSTs cancel (P1)
`src/hooks/useAgentStream.ts:379-390`: `useEffect(() => { const source = eventSourceRef.current; return () => { source?.close(); if (sessionIdRef.current && isStreaming) fetch(apiUrl(`/api/agent/cancel/${sessionIdRef.current}`), {method:'POST'}) } }, [isStreaming])` — the cleanup runs on the true→false transition with the captured `isStreaming === true`, so a normal completion fires the abort + cancel POST; the backend can then persist the reply as cancelled. Fix: make the effect unmount-only (`[]` deps, read an `isStreamingRef` in cleanup) or null `sessionIdRef`/`source` on the normal end paths (`response_complete`, loop exit, explicit `cancel()`). Tests: no cancel POST after a normal completion; exactly one on unmount mid-stream. No existing test references `/api/agent/cancel` (grep over `*.test.ts(x)` is empty) — add the guard.

## Task 2 — `R11-02`: queued auto-send drops pending approvals (P2)
`AgentChat.tsx:561-592` drains `messageQueue` on `!isStreaming && messageQueue.length > 0`, calls `foldLiveTurn()` (`:583`) and `sendMessage` (`:589`) with no `pendingConfirmation` / `awaiting_confirmation` / pending `diffProposal` check — the guard exists twice elsewhere in the file (`:499-506`, `:385-386`) but not here. Park the queue while a turn is parked; drain after resolution. Test: queue a message, end the turn on `tool_confirmation_required`, assert the `ConfirmationDialog` survives.

## Task 3 — `R11-03`: side effects inside the `setSession` updater (P2)
Inside the updater: `:495-499` `announce(fallback)`, `:501` `setTurnModel`, `:527` `onToolStart`, `:545` `onToolComplete`, `:555` `onConfirmationRequired`, `:566-574` `setProvenance/setResponse/setIsStreaming/onComplete`, `:578`, `:582` `setModuleInvocations`, `:590` `onError`, `:594`, `:604-605`. Hoist every side effect into the pre-updater block (`:434-460`) so the updater is pure. Test under `StrictMode`: `module_invoke` renders once, fallback announces once. `R11-13`: `handleEvent`/`sendMessage`/`confirmAction` identity churns on every render (options literal) — memoize.

## Task 4 — Perf and a11y residuals (P3, batch into one or two commits)
- `R11-12`/audit C2-C3: `MessageContent` and `ThinkingPanel` re-parse the whole text every frame — memoize by content; `CUA-04` D3: adopt `react-markdown` + `remark-gfm` with `CodeBlock` for fences (`MessageContent.tsx` is a 65-line regex renderer; no markdown dep in `package.json`).
- `R11-10`/C4-C5: `useTimeline` has no request abort and one shared `inFlight` flag.
- `R11-04`: timeout error text points at a removed "Settings › AI › Performance Tweaks" panel.
- `R11-05`/E6-E7: `ThinkingPanel` toggles lack `aria-expanded`/`aria-controls`; emoji in the header.
- `R11-06`/E10: `StateBadge` pulse ignores `prefers-reduced-motion`.
- `R11-07`/E9: focus dropped to `<body>` after a successful "Forget this".
- `R11-08`/E11: HostShell conversation column is not a landmark.
- `R11-09`/E8: scrollable `<pre>` blocks not keyboard-reachable.
- `R11-11`: composer `aria-expanded` claims a mention popup that is not rendered.
- `CUA-05` D2 human-readable `status_detail` in `StateBadge`; `CUA-06` B5 diff apply/reject has no failure rollback; `CUA-07` F2 copy-response button.

## Task 5 — Out of scope, note only
`CUA-08` P3 items (silent SSE parse errors, image size limit, reconnect/resume, token usage, regenerate/edit, focus shortcut, document.title, read-more) and `CUA-09` strategic (typed message "parts" model, assistant-ui evaluation) — list as open in results.

## Results
`.handoff/RESULTS-OPUS-05-<date>.md`: commits per finding, tests added, any backend change handed to OPUS-01, `vitest`/`tsc` output.
