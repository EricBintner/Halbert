# Review Packet 11: Chat UI Performance, Streaming State & Accessibility Audit

**Review Level:** **GLM-5.3 (reassigned 2026-08-30 — see MASTER-REVIEW-INDEX § 2 for effort tier and batch)**  
**Domain:** Frontend Chat Architecture, Virtualized Streaming, RequestAnimationFrame Buffering, ARIA Accessibility, and State Machine Resilience  
**Target Date:** 2026-08-30  
**Status:** Ready for Deep Frontend Audit & Sprint Planning  
**Governing Documents:**
- `halbert_core/halbert_core/dashboard/frontend/docs/chat-ui-audit/01-executive-summary.md`
- `halbert_core/halbert_core/dashboard/frontend/docs/chat-ui-audit/04-bugs.md`
- `halbert_core/halbert_core/dashboard/frontend/docs/chat-ui-audit/05-performance.md`
- `halbert_core/halbert_core/dashboard/frontend/docs/chat-ui-audit/06-streaming-state.md`
- `halbert_core/halbert_core/dashboard/frontend/docs/chat-ui-audit/07-accessibility.md`
- `halbert_core/halbert_core/dashboard/frontend/docs/chat-ui-audit/10-priority-matrix.md`

---

## 1. Executive Summary & Review Scope

On 2026-08-30, a 2,447-line comprehensive audit of Halbert's chat interface was completed (`docs/chat-ui-audit`). The audit evaluated the frontend against 30+ industry reference implementations (OpenAI, Anthropic, Vercel AI SDK, NN/g, Cursor, Continue.dev, TanStack).

Key audit findings:
1. **Critical P0 Bugs (3):**
   - SSE connection leak on unmount (abandoned EventSource / fetch stream readers).
   - Race condition on concurrent prompt submission during active streaming.
   - Message ordering desynchronization when background proactive events arrive mid-stream.
2. **High-Impact Performance Issue:** $O(n^2)$ re-rendering of entire message timeline on every incoming SSE token chunk.
3. **11 Accessibility (a11y) Violations:** Missing ARIA live-region announcements, lack of keyboard focus traps in modal sheets, non-semantic message roles.
4. **Streaming State Gaps:** Incomplete markdown AST rendering during high-speed token bursts causing HTML layout thrashing.

The reviewing model (**GLM-5.3**) must review the recommended 4-sprint execution plan, verify the `requestAnimationFrame` token buffering architecture, and scrutinize the proposed typed message parts refactor.

---

## 2. Priority Matrix & Sprint Roadmap (from `10-priority-matrix.md`)

| Sprint | Focus Area | Key Deliverables | Effort / Model |
|---|---|---|---|
| **Sprint 1** | **Stability & Performance (P0)** | Fix SSE reader leak, abort controller cleanup, rAF token buffer ($O(n^2) \to O(1)$) | High / **Fable** |
| **Sprint 2** | **Accessibility & Streaming (P1)** | ARIA live regions, semantic message containers, streaming markdown AST parser | Medium / **Fable** |
| **Sprint 3** | **Design & Ergonomics (P2)** | Flat conversation layout, copy-to-clipboard buttons, suggested follow-ups | Medium / **Fable** |
| **Sprint 4** | **Typed Message Architecture (P3)**| Assistant-ui typed message parts, somatic block virtualizer | High / **Fable** |

---

## 3. Key Files & Components

- **Chat Interface:**
  - [`halbert_core/halbert_core/dashboard/frontend/src/components/ChatPanel.tsx`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/components/ChatPanel.tsx)
  - [`halbert_core/halbert_core/dashboard/frontend/src/hooks/useWebSocket.ts`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/hooks/useWebSocket.ts)
  - [`halbert_core/halbert_core/dashboard/frontend/src/components/chat/`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/components/chat/)

---

## 4. Review Directives for Fable

- **SSE Reader Cleanup Audit:** Inspect `ChatPanel.tsx` `useEffect` cleanup handlers. Verify that all async `ReadableStreamDefaultReader` instances are explicitly cancelled and closed when the component unmounts.
- **Token Buffering Correctness:** Evaluate the proposed `useTokenBuffer` hook to ensure no tokens are lost if the stream closes before the next animation frame fires.
- **Verification Command:** Run `npm --prefix halbert_core/halbert_core/dashboard/frontend test`.
