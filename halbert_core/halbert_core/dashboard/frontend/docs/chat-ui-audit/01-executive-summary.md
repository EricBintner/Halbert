# 1. Executive Summary

## Context

The Halbert chat UI is a React 18 + Vite + Tailwind desktop application that provides a conversational interface to an AI agent. The agent streams responses over SSE (Server-Sent Events), executes tools, proposes diffs, and maintains a persisted conversation timeline. The UI uses an Olivetti-inspired dark aesthetic.

This audit was triggered after a series of bugs were fixed (agent stuck in "idle", extra scroll space, StateBadge crashes on unknown states). Rather than continue fixing issues reactively, this is a proactive end-to-end review.

## Key Findings

### 3 P0 bugs (fix immediately)

1. **Auto-scroll yanks users back down** — scrolling up to read an old answer while the agent is streaming causes the viewport to jump back to the bottom on every token. This is the single most disruptive UX issue. (`AgentChat.tsx` L445-448)

2. **Confirmation stream cannot be cancelled** — when the agent is responding to a confirmed action, the Stop button does nothing. The `AbortController` for `confirmAction` is never stored in `eventSourceRef`, so `isStreaming` stays true forever. (`useAgentStream.ts` L873-930)

3. **Error events don't stop streaming** — if the backend sends an `error` SSE event without a subsequent `session_ended`, the UI keeps showing a pulsing "responding" state indefinitely. (`useAgentStream.ts` L520-523)

### 1 high-impact performance issue

**Token-by-token React state updates cause O(n^2) string concatenation.** Every `response_chunk` event triggers a full React re-render and a full re-parse of the entire response string. For a 2000-token reply, this is 2000 growing concatenations and 2000 regex re-parses. The industry standard is to buffer chunks in a ref and flush to React state once per `requestAnimationFrame` (~60fps). (`useAgentStream.ts` L486, `MessageContent.tsx` L21-33)

### 7 accessibility gaps

The timeline has excellent ARIA (`role="feed"`, `aria-posinset`), but several interactive components are inaccessible:
- Error banner not announced to screen readers
- State transitions (Planning -> Searching) not announced
- Composer textarea has no `aria-label`
- Mention autocomplete is mouse-only (no listbox semantics, no arrow keys)
- ToolExecutionCard expand/collapse is not keyboard-operable
- ThinkingPanel missing `aria-expanded`
- Emojis in ThinkingPanel violate project rules

### 2 strategic architecture opportunities

1. **Typed message "parts" model** — replace flat string `response`/`thinking` with arrays of typed parts (`{ type: 'text' }`, `{ type: 'reasoning' }`, `{ type: 'tool_call' }`). This is how Vercel AI SDK, Anthropic's API, and Claude.ai all model messages. It enables lossless round-tripping, richer rendering, and future features like branching.

2. **Evaluate `assistant-ui` primitives** — an open-source library of unstyled, accessible React primitives (`ThreadPrimitive`, `ComposerPrimitive`, `MessagePrimitive`) that handles streaming, auto-scroll, message branches, tool-call rendering, and keyboard shortcuts. Could eliminate most of the accessibility and scroll bugs for free.

## What's Already Good

The codebase has several genuinely strong patterns that should be preserved:
- SSE via `fetch` + `ReadableStream` (correct for POST bodies)
- `role="feed"` timeline with proper ARIA positioning
- Single `LiveRegion` with polite/assertive split (follows MDN guidance)
- Scoped terminal subscriptions (prevents N-row re-renders)
- Message queue for "type while busy"
- Redaction-aware timeline with real exit-code checking

## Recommendation

Fix the 3 P0 bugs and the rAF buffering issue first — these are small changes with high impact. Then work through the P1 accessibility fixes. The streaming markdown renderer (P2) is the biggest visual quality improvement. The strategic architecture items should be planned as a separate initiative, not mixed into the tactical fixes.
