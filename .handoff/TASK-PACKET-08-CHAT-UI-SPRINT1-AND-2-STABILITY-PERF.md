# Task Packet 08: Chat UI Sprint 1 & 2 Execution (Stability, Performance & A11y)

**Target Model:** **Fable Level**  
**Domain:** React Frontend Performance, Token Buffering, SSE Reader Cleanup, and ARIA Live Regions  
**Target Date:** 2026-08-30  
**Status:** Ready for Implementation  
**Governing Documents:**
- `halbert_core/halbert_core/dashboard/frontend/docs/chat-ui-audit/04-bugs.md`
- `halbert_core/halbert_core/dashboard/frontend/docs/chat-ui-audit/05-performance.md`
- `halbert_core/halbert_core/dashboard/frontend/docs/chat-ui-audit/07-accessibility.md`
- `halbert_core/halbert_core/dashboard/frontend/docs/chat-ui-audit/10-priority-matrix.md`

---

## 1. Executive Summary & Objective

This packet executes **Sprint 1 (Stability & Performance)** and **Sprint 2 (Accessibility & Streaming)** from the comprehensive Chat UI Audit (`docs/chat-ui-audit`). 

Key fixes:
1. **P0 SSE Reader Leak Fix:** Prevent abandoned fetch stream readers and dangling EventSource connections when users navigate away during active streaming.
2. **$O(n^2) \to O(1)$ Token Buffering:** Implement `requestAnimationFrame` token chunk buffering in `useTokenBuffer` so incoming high-frequency SSE tokens do not trigger quadratic React re-renders.
3. **Accessibility Compliance:** Add `role="feed"`, `aria-busy`, and `aria-live="polite"` regions for screen readers.

---

## 2. Detailed Task Breakdown & Implementation Steps

### Task 8.1: Implement SSE AbortController Cleanup & Lock Guard
- **File:** [`halbert_core/halbert_core/dashboard/frontend/src/components/ChatPanel.tsx`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/components/ChatPanel.tsx)
  1. Attach an `AbortController` ref to the active SSE fetch stream.
  2. In the `useEffect` unmount cleanup, call `abortController.abort()` and explicitly release stream readers.
  3. Add a submission mutex: disable prompt submission while `isStreaming == true` to eliminate race conditions.

### Task 8.2: Implement `useTokenBuffer` ($O(1)$ Token Buffering)
- **File:** `halbert_core/halbert_core/dashboard/frontend/src/hooks/useTokenBuffer.ts`
  1. Buffer incoming SSE token chunks in a mutable queue.
  2. Flush the queue to React state on each animation frame (`requestAnimationFrame`) or on stream termination.
  3. This caps DOM re-renders to 60 FPS regardless of LLM generation speed.

### Task 8.3: Add ARIA Live Regions & Semantic Roles
- **File:** [`halbert_core/halbert_core/dashboard/frontend/src/components/ChatPanel.tsx`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/components/ChatPanel.tsx)
  1. Add `role="feed"` and `aria-busy={isStreaming}` to the message list container.
  2. Implement an invisible `aria-live="polite"` announcement container for incoming agent turns.

---

## 3. Verification & Test Plan

1. **Frontend Component Tests:**
   ```bash
   npm --prefix halbert_core/halbert_core/dashboard/frontend test
   ```
2. **Build Verification:**
   ```bash
   npm --prefix halbert_core/halbert_core/dashboard/frontend run build
   ```
