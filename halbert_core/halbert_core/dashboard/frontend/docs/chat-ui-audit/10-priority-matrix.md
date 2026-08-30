# 10. Priority Matrix & Action Plan

All findings from the audit, sorted by priority. Each item includes the file, effort estimate, and impact rating.

---

## P0 — Fix Immediately

These are bugs that break core functionality or cause significant user frustration.

| # | Item | File | Lines | Effort | Impact |
|---|------|------|-------|--------|--------|
| B1 | User-scroll-aware auto-scroll | `AgentChat.tsx` | L444-448 | Small | High — fixes #1 UX complaint |
| B2 | `confirmAction` cancellable | `useAgentStream.ts` | L873-930 | Small | High — fixes stuck-state bug |
| B3 | `error` events stop streaming | `useAgentStream.ts` | L520-523 | Trivial | High — fixes stuck-state bug |

### B1: User-Scroll-Aware Auto-Scroll
- **Problem:** Scrolling up to read an old answer while streaming causes the viewport to jump back on every token.
- **Fix:** Add `onScroll` handler tracking `isAtBottom`, only `scrollIntoView` when true, show floating "Jump to latest" button when false.
- **Threshold:** 100px for desktop.
- **Depends on:** None. Also enables F7 (floating "Jump to latest" button).

### B2: `confirmAction` Cancellable
- **Problem:** During a confirmation stream, the Stop button does nothing and `isStreaming` stays true forever.
- **Fix:** Create an `AbortController` in `confirmAction`, store it in `eventSourceRef.current`, pass `signal` to `fetch`.

### B3: Error Events Stop Streaming
- **Problem:** If the backend sends `error` without `session_ended`, the UI keeps pulsing "responding" indefinitely.
- **Fix:** Call `setIsStreaming(false)` in the `error` event handler (via `queueMicrotask` or a ref to avoid calling it inside `setSession`).

---

## P1 — Fix Soon

These are issues that significantly affect performance, accessibility, or user experience.

| # | Item | File | Lines | Effort | Impact |
|---|------|------|-------|--------|--------|
| C1 | rAF-buffered streaming | `useAgentStream.ts` | L486, L490 | Small | High — perf + battery |
| E1 | Announce `agentError` | `AgentChat.tsx` | L1045-1054 | Trivial | Medium — a11y |
| E3 | `aria-label` on textarea | `AgentChat.tsx` | L1156-1169 | Trivial | Medium — a11y |
| E5 | Keyboard-enable ToolExecutionCard | `ToolExecutionCard.tsx` | L95-118 | Small | Medium — a11y |
| B4 | Wire `onRunCommand` in HostShell | `HostShell.tsx` | L65 | Small | Medium — dead feature |

### C1: rAF-Buffered Streaming
- **Problem:** Every token triggers a React re-render and a full string concatenation. O(n^2) for long responses.
- **Fix:** Buffer chunks in refs (`responseBufferRef`, `thinkingBufferRef`), flush to React state once per `requestAnimationFrame`.
- **Bonus:** Remove `console.log` on L485.
- **Enables:** C2 and C3 become less critical (memoization is effective when content changes ~60fps instead of per-token).

### E1: Announce `agentError`
- **Problem:** Error banner is visual-only; screen-reader users don't know it exists.
- **Fix:** `useEffect(() => { if (agentError) announce(agentError, { assertive: true }) }, [agentError])`

### E3: `aria-label` on Textarea
- **Problem:** Textarea relies on `placeholder` for accessible name, which disappears when a value is present.
- **Fix:** Add `aria-label="Message Halbert"`.

### E5: Keyboard-Enable ToolExecutionCard
- **Problem:** Expand/collapse header is a `<div onClick>` — not focusable, not keyboard-operable.
- **Fix:** Change to `<button>` with `aria-expanded` and `aria-controls`.

### B4: Wire `onRunCommand` in HostShell
- **Problem:** "Run in Terminal" buttons in code blocks are inert because `onRunCommand` is not passed.
- **Fix:** Wire the callback in `HostShell.tsx` or remove the button from `CodeBlock` when the prop is `undefined`.

---

## P2 — Plan for Near Term

These are improvements that would noticeably improve the product quality.

| # | Item | File | Lines | Effort | Impact |
|---|------|------|-------|--------|--------|
| D3 | Streaming markdown rendering | `MessageContent.tsx` | L19-41 | Medium | High — visual quality |
| C2 | Memoize MessageContent parse | `MessageContent.tsx` | L21-33 | Small | Medium — perf |
| D2 | Human-readable state detail | `useAgentStream.ts` + backend | — | Medium | Medium — UX |
| E2 | Announce state transitions | `AgentChat.tsx` | — | Small | Medium — a11y |
| E4 | Keyboard-navigable mentions | `AgentChat.tsx` | L1079-1097 | Medium | Medium — a11y |
| B5 | Diff apply/reject feedback | `useAgentStream.ts` | L966-996 | Small | Medium — correctness |
| F2 | Copy response button | `AgentChat.tsx` | — | Small | Medium — convenience |
| F7 | Floating "Jump to latest" button | `AgentChat.tsx` | — | Small | Medium — scroll UX |

### D3: Streaming Markdown Rendering
- **Problem:** Only plain text + fenced code blocks. No bold, italic, links, lists, tables.
- **Fix:** Adopt `react-markdown` with `remark-gfm`, using the existing `CodeBlock` component for code rendering.
- **Dependencies:** `react-markdown`, `remark-gfm` (check if already in the project).

### C2: Memoize MessageContent Parse
- **Problem:** Code-block regex runs on every render with no memoization.
- **Fix:** Wrap the parse in `useMemo` keyed on `content`.
- **Depends on:** C1 (rAF buffering) makes this effective — without buffering, `content` changes per-token and `useMemo` doesn't help.

### D2: Human-Readable State Detail
- **Problem:** "Searching" but not what is being searched. "Reading" but not which file.
- **Fix:** Backend sends `status_detail` with `state_change` events; frontend displays it as a subtitle in `StateBadge`.
- **Requires:** Backend coordination.

### E2: Announce State Transitions
- **Problem:** State transitions (Planning -> Searching -> Executing) are silent to screen readers.
- **Fix:** Announce meaningful transitions via `announce` in the `onStateChange` handler.

### E4: Keyboard-Navigable Mentions
- **Problem:** Mention popup has no listbox semantics, no arrow-key navigation.
- **Fix:** Add `role="listbox"`, `role="option"`, `aria-activedescendant`, and arrow-key handlers.

### B5: Diff Apply/Reject Feedback
- **Problem:** Optimistic state update with no rollback on server failure.
- **Fix:** Return a promise, revert on failure, surface an error via `announce`.

### F2: Copy Response Button
- **Problem:** No way to copy a full assistant response.
- **Fix:** Add a copy button in a hover-revealed action bar below the response.

### F7: Floating "Jump to Latest" Button
- **Problem:** No floating button when the user scrolls up during streaming (only when `anchored`).
- **Fix:** Part of B1 — the floating button appears whenever `!isAtBottom && !anchored`.

---

## P3 — Nice to Have

These are small improvements that polish the product but aren't critical.

| # | Item | File | Lines | Effort | Impact |
|---|------|------|-------|--------|--------|
| B6 | SSE parser error logging | `useAgentStream.ts` | L845-854 | Low | Low |
| B7 | Queued auto-send race | `AgentChat.tsx` | L451-480 | Small | Low |
| B8 | Image size limit | `AgentChat.tsx` | L489-507 | Trivial | Low |
| C3 | Memoize `parseThinkingSections` | `ThinkingPanel.tsx` | L40 | Trivial | Low |
| C4 | `AbortController` in `useTimeline` | `useTimeline.ts` | — | Small | Low |
| C5 | Separate `inFlight` flags | `useTimeline.ts` | — | Small | Low |
| D1 | "Submitted" state | `useAgentStream.ts` | — | Small | Low |
| D4 | Reconnection / resume | `useAgentStream.ts` | — | Large | Low (local) |
| D5 | Fix `eventSourceRef` type | `useAgentStream.ts` | L870 | Trivial | Low |
| D6 | Token usage display | — | — | Medium | Low |
| E6 | `aria-expanded` on ThinkingPanel | `ThinkingPanel.tsx` | L44-64 | Trivial | Low |
| E7 | Remove emojis from ThinkingPanel | `ThinkingPanel.tsx` | L50-51 | Trivial | Low |
| E8 | Focusable `<pre>` elements | `ThinkingPanel.tsx`, `ToolExecutionCard.tsx` | — | Trivial | Low |
| E9 | Focus management after redaction | `Timeline.tsx` | — | Small | Low |
| E10 | `prefers-reduced-motion` for pulse | `StateBadge.tsx` | L99-104 | Trivial | Low |
| E11 | `aria-label` on HostShell regions | `HostShell.tsx` | L61-71 | Trivial | Low |
| F1 | Flat layout vs bubbles | — | — | Medium | Low |
| F3 | Regenerate / edit / branch | — | — | Large | Medium |
| F4 | Suggested prompts in empty state | `HostGreeting.tsx` | — | Small | Low |
| F6 | Line length cap | `AgentChat.tsx` | — | Trivial | Low |
| F8 | Keyboard shortcut to focus composer | `HostShell.tsx` | — | Trivial | Low |
| F9 | Document title update | — | — | Trivial | Low |
| F10 | Collapsible "Read more" | — | — | Medium | Low |

---

## Strategic — Plan Separately

These are large architectural changes that should be planned as separate initiatives.

| # | Item | Effort | Impact |
|---|------|--------|--------|
| G1 | Typed message "parts" model | Large | High — enables branching, lossless round-tripping, richer rendering |
| G2 | Evaluate `assistant-ui` primitives | Medium (eval) to Large (adopt) | High — could eliminate most P0/P1 bugs for free |

---

## Recommended Execution Order

### Sprint 1: P0 Fixes (1-2 days)
1. B1: User-scroll-aware auto-scroll (+ F7 floating button)
2. B2: `confirmAction` cancellable
3. B3: `error` events stop streaming

### Sprint 2: P1 Fixes (2-3 days)
4. C1: rAF-buffered streaming
5. E1: Announce `agentError`
6. E3: `aria-label` on textarea
7. E5: Keyboard-enable ToolExecutionCard
8. B4: Wire `onRunCommand` in HostShell

### Sprint 3: P2 Fixes (3-5 days)
9. D3: Streaming markdown rendering (biggest visual improvement)
10. C2: Memoize MessageContent parse
11. E2: Announce state transitions
12. E4: Keyboard-navigable mentions
13. B5: Diff apply/reject feedback
14. F2: Copy response button

### Sprint 4: P3 Polish (ongoing)
15. Pick from the P3 table based on user feedback

### Strategic Initiative (separate)
16. G1: Typed message "parts" model
17. G2: Evaluate `assistant-ui` primitives

---

## Verification

After each sprint, verify the fixes by:

1. **Manual testing:** Send a message, scroll up during streaming, verify auto-scroll pauses. Send a confirmation, verify Stop works. Trigger an error, verify streaming stops.
2. **Accessibility testing:** Run axe-core or Lighthouse accessibility audit. Test with VoiceOver (macOS).
3. **Performance testing:** Send a long prompt that generates a 2000+ token response. Verify the UI doesn't jank. Check CPU usage in Activity Monitor.
4. **Browser preview:** Use the `browser_preview` tool to interact with the running app and verify the fixes visually.
