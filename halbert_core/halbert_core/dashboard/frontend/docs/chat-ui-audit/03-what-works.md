# 3. What's Working Well

Before diving into issues, it's important to document what the codebase gets right. These patterns should be preserved during any refactoring.

---

## 3.1 SSE via fetch + ReadableStream

**File:** `useAgentStream.ts` L797-868

Halbert uses `fetch()` with a `ReadableStream` reader instead of the native `EventSource` API. This is the correct choice because:

- `EventSource` only supports GET requests — Halbert needs POST to send the message body
- `fetch` + `AbortController` gives fine-grained control over cancellation
- The `ReadableStream` reader allows incremental parsing of SSE lines

The stream reader correctly handles partial lines across network frames by keeping an incomplete line in a buffer:
```typescript
buffer += decoder.decode(value, { stream: true });
const lines = buffer.split('\n');
buffer = lines.pop() || ''; // Keep incomplete line in buffer
```

This is the same pattern ChatGPT uses (per the "What Actually Happens When ChatGPT Streams a Response" analysis).

---

## 3.2 `role="feed"` Timeline with Full ARIA

**File:** `Timeline.tsx` L610-658

The timeline uses `role="feed"` with proper ARIA positioning:
- `aria-busy` during loading
- `aria-label` with the display name
- Each turn is an `article` with `aria-posinset` and `aria-setsize`
- Day dividers use `h2` headings with `time datetime` attributes

This is better ARIA than most production chat UIs. The `feed` role is semantically correct for a conversation — it tells assistive technology that this is a scrollable list of articles where new content may be appended.

---

## 3.3 Single LiveRegion with Polite/Assertive Split

**File:** `LiveRegion.tsx` (mounted in `HostShell.tsx` L59)

Halbert follows MDN's ARIA live region guidance exactly:
- One polite `role="status"` region for non-critical updates
- One assertive `role="alert"` region for critical updates
- A queue to prevent overlapping announcements
- The region is mounted at the top of the DOM, before any content changes

The `announce` helper is used consistently for thread changes, redaction events, and load failures. The gap is that it's not used for error banners or state transitions (see the Accessibility section).

---

## 3.4 Scoped Terminal Subscriptions

**File:** `Timeline.tsx` L147-150 (`TurnTerminals`)

The `TurnTerminals` component subscribes to the terminal store only when a turn owns terminals. This prevents every timeline row from re-rendering on every terminal output byte. Without this optimization, a single `echo "hello"` in a terminal would cause every turn in the timeline to re-render.

This is a performance best practice that most chat UIs miss — they either don't have terminal integration or they naively subscribe to a global store.

---

## 3.5 Message Queue for "Type While Busy"

**File:** `AgentChat.tsx` L250, L451-480

When the agent is streaming, the user can still type. The message is queued and auto-sent when streaming completes. This is a good UX pattern — it prevents the frustration of "I can't type while the agent is thinking."

The queue also correctly handles `/model` commands typed while streaming (L465: `if (handleModelCommand(nextMessage)) return;`), which prevents commands from being sent to the backend as ordinary text.

---

## 3.6 Redaction-Aware Timeline

**File:** `Timeline.tsx` L110-128, L167-180, L526-584

The timeline's redaction logic is carefully implemented:
- `executionFromBlock` checks the real `exit` code before the stored `status` to avoid marking a failed shell command as success
- Half-landed redactions are surfaced visually and via `announce`
- The "Forget this" button has clear `aria-label` and `aria-describedby` pointing to the warning text

This is a unique feature that most chat UIs don't have — the ability to selectively remove turns from the persisted conversation. The implementation handles edge cases well.

---

## 3.7 `foldInputs` Ref Pattern

**File:** `AgentChat.tsx` L334-346

The `foldInputs` ref safely closes over stale state for the fold-live-turn logic without race conditions. When `foldLiveTurn` is called, it reads from the ref, not from React state, so it always gets the latest values even if the closure was created during a previous render.

This is a well-known React pattern for avoiding stale closures, and it's applied correctly here.

---

## 3.8 `isStreaming` Cleanup Captures Correct Instance

**File:** `useAgentStream.ts` L328-339

The `useEffect` cleanup for `isStreaming` captures the `eventSourceRef.current` at effect-run time into a local variable, ensuring the correct `EventSource` instance is closed during cleanup. This was a bug fix from the previous session — without this, a new `sendMessage` call would have its `AbortController` immediately aborted by the cleanup of the previous effect.

This is a subtle but important fix that demonstrates understanding of React's effect cleanup semantics.

---

## 3.9 Terminal Side Effects Outside `setSession`

**File:** `useAgentStream.ts` L251-305, L369-379

Terminal side effects (writing to the terminal store) are deliberately run outside the `setSession` updater function. This avoids React 18 StrictMode duplication, where the updater function would be called twice in development, causing the terminal output to be written twice.

This shows awareness of React 18's StrictMode behavior and is a correct workaround.

---

## 3.10 `memo` on TurnArticle with `forgottenRef`

**File:** `Timeline.tsx` L288, L515-519

`TurnArticle` is wrapped in `memo` to prevent unnecessary re-renders when other turns change. The `forgottenRef` is used to avoid stale closures in the forget handler — it always has the latest forgotten state without triggering a re-render.

This is a correct application of `memo` + ref for performance optimization in a list of items that each have their own local state.
