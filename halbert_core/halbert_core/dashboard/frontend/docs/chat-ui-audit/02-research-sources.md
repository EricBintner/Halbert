# 2. Research Sources

This audit was informed by web research across three dimensions: technical implementation patterns, design best practices, and real-world implementations. All sources are listed below with URLs and key insights.

---

## Technical Implementation Patterns

### Streaming Text Rendering

**OpenAI — "Streaming API responses"**
- URL: https://developers.openai.com/api/docs/guides/streaming-responses
- Insight: OpenAI returns typed SSE lifecycle events (`response.created`, `response.output_text.delta`, `response.completed`, `error`) rather than raw byte deltas. The client should listen for events by `type` and never assume every chunk is displayable text.
- Relevance to Halbert: Halbert's SSE protocol already uses typed events (`response_chunk`, `thinking`, `tool_start`, etc.), which is the right approach. The gap is in client-side buffering — Halbert flushes every chunk to React state immediately.

**Vercel AI SDK — "Stream Protocol"**
- URL: https://github.com/vercel/ai/blob/main/content/docs/04-ai-sdk-ui/50-stream-protocol.mdx
- Insight: The SDK distinguishes text streams (plain text chunks) from data streams (structured chunks for tool calls, sources, files). The runtime normalizes each chunk into UI state, and a terminal `finish` or `abort` chunk changes message status from `streaming` to `sent` or `cancelled`.
- Relevance to Halbert: Halbert's protocol is similar but lacks explicit lifecycle markers (`message-start`, `message-end`). The `response_complete` event serves as `message-end`, but there's no `message-start` — the UI infers it from the first `response_chunk`.

**The Frontend Casebook — "Streaming Tokens Without Layout Thrash"**
- URL: https://anmshpndy.com/cases/streaming-tokens-ui-buffer/
- Insight: LLMs emit 30-80 tokens/second but the screen only refreshes at ~60 Hz. Writing each token to the DOM as it arrives causes wasted reflows. Accumulate chunks and flush once per `requestAnimationFrame` frame to cut CPU usage without visibly slower rendering.
- Relevance to Halbert: This is the single highest-impact performance fix. Halbert currently does `setResponse(r => r + chunk)` on every token, causing one React re-render per token. Buffering with rAF would reduce renders by ~10x.

### State Machine Design

**Anthropic — "Building Effective AI Agents"**
- URL: https://www.anthropic.com/engineering/building-effective-agents
- Insight: Anthropic recommends simple, explicit state machines over magic agent frameworks. Workflows and agents should both name their current phase so the UI can render the right affordances without inspecting raw message streams.
- Relevance to Halbert: Halbert already has a good state machine (`idle -> planning -> searching -> reading -> executing -> observing -> reflecting -> responding -> error`). The gap is in surfacing state detail — the user sees "Searching" but not what is being searched.

**Stately — "Thinking in State Machines"**
- URL: https://stately.ai/docs/packages/agent/thinking-in-state-machines
- Insight: Common agent loops already contain implicit states (`classifying`, `drafting`, `reviewing`, `awaitingHuman`). Surfacing them as explicit machine states makes the system resumable, testable, and lets the UI show "thinking / using tool / waiting for you" rather than a generic spinner.
- Relevance to Halbert: Halbert's states are already explicit and surfaced via `StateBadge`. The `awaiting_confirmation` state is well-handled with a dialog. The gap is that state transitions are not announced to screen readers.

**1agents — "Chat UI & Real-time Protocol"**
- URL: https://deepwiki.com/scottzx/1agents/3.2-chat-ui-and-real-time-protocol
- Insight: Their `reducer.ts` maps backend `BridgeEvent` types (`text_delta`, `thinking_delta`, `tool_call`, `turn_state`) to UI state. `turn_state` events (`running`, `completed`, `failed`) drive the typing indicator and status icons.
- Relevance to Halbert: Halbert's `handleEvent` reducer in `useAgentStream.ts` follows the same pattern. The gap is that `error` events don't transition the turn state to `failed` — they only set `session.error` without stopping the stream.

### Error Handling and Recovery

**Vercel — "Troubleshooting: Abort and resumable streams"**
- URL: https://ai-sdk.dev/docs/troubleshooting/abort-breaks-resumable-streams
- Insight: Client-side `stop()` closes the HTTP connection, but if the abort signal is passed through to the model, it also cancels server generation. Resumable streaming requires two separate signals: disconnect (resume allowed) and explicit cancel (stop endpoint).
- Relevance to Halbert: Halbert's `cancel()` calls `eventSourceRef.current?.close()` which aborts the fetch. This is a hard cancel, not a disconnect. For now this is fine, but if resume support is added later, the signals need to be separated.

**Vercel — "AI SDK UI: Chatbot Resume Streams"**
- URL: https://ai-sdk.dev/docs/ai-sdk-ui/chatbot-resume-streams
- Insight: A `resume` mode lets the client reconnect to an active stream after page reload. The server must keep the producer running and expose a `GET /api/chat/[id]/stream` endpoint that hands back the live stream if an `activeStreamId` exists.
- Relevance to Halbert: Not currently needed for a local desktop app, but worth noting if the app is ever deployed as a web service.

**AI/TLDR — "Handling Mid-Stream LLM Errors & Dropped Connections"**
- URL: https://ai-tldr.dev/learn/llm-apis/streaming-structured-outputs/handle-streaming-errors/
- Insight: Track whether you saw the terminal event; if not, the response is incomplete. For prose, keep partial text and show a "connection lost — retry/continue" marker. For structured output or tool-call arguments, discard partials and retry the whole call.
- Relevance to Halbert: Halbert has a 5-minute data timeout that aborts and sets `error`, but there's no `sawTerminal` tracking. If the stream closes without `response_complete` or `session_ended`, the partial text is kept but no recovery UI is shown.

### Optimistic UI Patterns

**AI/TLDR — "Optimistic UI for AI Apps: Make Slow Feel Fast"**
- URL: https://ai-tldr.dev/learn/building-ai-apps/ai-ux-patterns/optimistic-ui-ai-apps/
- Insight: An optimistic chat update has three phases: predict (user message), show (instantly render), and reconcile (swap temp ID for real ID or roll back on failure). Echoing the user's message is risk-free and bridges the dead time before the first token.
- Relevance to Halbert: Halbert already does optimistic UI for user messages (`setLiveUser` before `sendMessage`). The gap is in diff apply/reject — optimistic state is updated but never rolled back on server failure.

**Ably — "Optimistic updates"**
- URL: https://ably.com/docs/ai-transport/features/optimistic-updates.md
- Insight: The client inserts the message into the conversation tree before the server confirms, using a client-generated `codec-message-id`. The server echo is then reconciled by that ID so there is no flash or position change.
- Relevance to Halbert: Halbert uses `id: 'user-' + Date.now()` for optimistic user messages, which is reconciled when the turn is folded into the timeline. This works but `Date.now()` is not guaranteed unique under rapid double-send; `crypto.randomUUID()` would be safer.

### Scroll Behavior

**TanStack — "Chat UIs Are Lists Until They Aren't"**
- URL: https://tanstack.com/blog/tanstack-virtual-chat
- Insight: Chat lists should be end-anchored: the end of the list is the stable edge. Use `anchorTo: 'end'` and `followOnAppend: true` with a `scrollEndThreshold` so the viewport follows new output only when the user is already near the bottom. Use stable message IDs as keys.
- Relevance to Halbert: Halbert's auto-scroll has no proximity check. This is the root cause of the P0 scroll bug.

**MUI X — "Scrolling"**
- URL: https://mui.com/x/react-chat/behavior/scrolling/
- Insight: Auto-scroll is gated by a configurable buffer (default 150 px). When the user scrolls beyond the buffer, auto-scroll pauses and a floating "jump-to-latest" affordance appears. The same buffer defines the `onReachBottom` callback zone.
- Relevance to Halbert: Halbert should adopt the same pattern — a 100-150px proximity buffer, a floating "Jump to latest" button, and re-enable auto-scroll on click.

**HelloFrontend — "Building Chat UIs That Don't Annoy Users"**
- URL: https://hellofrontend.com/frontend-ai-interview/chat-ui-patterns
- Insight: The "pinned-to-bottom" rule: if the user is within ~60 px of the bottom, auto-scroll; otherwise, leave them. A 60 px buffer accounts for iOS momentum scroll and sub-pixel rounding.
- Relevance to Halbert: For desktop, 100px is a more appropriate threshold than 60px since there's no momentum scroll.

---

## Design Best Practices

### Conversation Design

**Anthropic — "MCP Apps Design Guidelines"**
- URL: https://claude.com/docs/connectors/building/mcp-apps/design-guidelines
- Insight: Treat embedded apps as natural extensions of the chat flow, not separate surfaces. Avoid nested scrolling or drill-in navigation that breaks the conversation.
- Relevance to Halbert: Halbert's inline tool cards and thinking panel are good examples of this principle. The context stage (right pane) is a separate surface but is supplementary, not required for the conversation.

**Nielsen Norman Group — "10 Guidelines for Designing Your Site's AI Chatbots"**
- URL: https://www.nngroup.com/articles/ai-chatbots-design-guidelines/
- Insight: Show capability upfront, offer suggested questions as buttons, use progressive disclosure, and don't autoscroll users to the end of long responses.
- Relevance to Halbert: The empty state (`HostGreeting`) shows a greeting but no tappable suggested prompts. Adding 3-4 prompt chips would demonstrate capability.

**Google — "Conversation Design"**
- URL: https://developers.google.com/assistant/conversation-design/learn-about-conversation
- Insight: Apply Grice's Cooperative Principle (truth, quantity, relevance, manner). The assistant should answer first, then offer to elaborate. Use brief, plain-language responses.
- Relevance to Halbert: This is a backend/prompt concern, not a UI concern, but the UI should support it by rendering concise answers with expandable details.

### Visual Feedback During AI Processing

**Frontend Patterns — "AI Streaming UI: Loading and Errors"**
- URL: https://frontendpatterns.dev/guides/managing-ai-response-states
- Insight: AI generation has more states than a typical REST call (idle, submitted, thinking, streaming, complete, stopped, error) and each needs its own UI treatment. Skipping the "thinking" and "stopped" states is a common mistake.
- Relevance to Halbert: Halbert has rich states but doesn't distinguish "submitted" (waiting for first SSE event) from "planning" (backend is actively planning). The recent fix to start at `planning` instead of `idle` partially addresses this.

**Frontend Patterns — "Thinking Indicator"**
- URL: https://frontendpatterns.dev/thinking-indicator
- Insight: Thinking indicators fill the anxious gap between prompt submission and the first token. They should be accessible, distinct from generic loaders, and respect reduced motion.
- Relevance to Halbert: Halbert's `StateBadge` pulse animation is the thinking indicator. It respects `prefers-reduced-motion`? No — it uses Tailwind's `animate-ping` which is not gated on reduced motion. This should be fixed.

**UX Patterns for Developers — "AI Loading States"**
- URL: https://uxpatterns.dev/patterns/ai-intelligence/ai-loading-states
- Insight: Reserve space for the upcoming response with a streaming placeholder. Use a status label that explains what the assistant is doing: "Thinking...", "Searching...", "Reading file...". Always expose a stop/cancel control while streaming.
- Relevance to Halbert: Halbert has the status label (StateBadge) and the stop control. The gap is the lack of detail — "Searching" but not what is being searched.

### Accessibility

**Tian Pan — "When Streaming Tokens Meet the Screen Reader"**
- URL: https://tianpan.co/blog/2026/06/29/streaming-tokens-meet-the-screen-reader
- Insight: Naively wrapping a streaming response in an `aria-live` region creates a stuttering, overlapping wall of noise for screen reader users because every token triggers a DOM mutation and announcement attempt.
- Relevance to Halbert: Halbert does NOT wrap streaming text in an aria-live region (good). The `LiveRegion` is separate and only announces discrete events. This is the correct pattern.

**MDN — "ARIA Live Regions"**
- URL: https://developer.mozilla.org/en-US/docs/Web/Accessibility/ARIA/Guides/Live_regions
- Insight: Start with an empty live region and populate it in a separate step. Use `role="status"` for non-critical updates and `role="alert"` for critical ones. Keep the markup stable: add the live-region element to the DOM on mount, before any content changes.
- Relevance to Halbert: Halbert's `LiveRegion.tsx` follows this exactly — one polite `status` and one assertive `alert`, mounted at the top of `HostShell`.

**Craig Abbott — "Web Chat Accessibility Considerations"**
- URL: https://www.craigabbott.co.uk/blog/2023/web-chat-accessibility-considerations/
- Insight: Mark each message with `role="article"` and an `aria-label` identifying the sender and time. Ensure all interactive elements are keyboard operable with visible focus rings.
- Relevance to Halbert: The timeline uses `role="article"` with `aria-posinset`/`aria-setsize` (excellent). The gap is in the live turn — the composer textarea, mention popup, and tool cards lack proper ARIA.

### Information Density and Layout

**MUI X Chat — "Look and Feel"**
- URL: https://mui.com/x/react-chat/customization/look-and-feel/
- Insight: Two layout variants: bubbles (colored, right-aligned for user) and flat/compact (no bubbles, stacked messages with inline sender info). Flat layout is preferred for AI assistants.
- Relevance to Halbert: Halbert uses a hybrid — user messages are right-aligned colored bubbles, assistant messages are left-aligned bordered cards. A fully flat layout would be more consistent with the Olivetti aesthetic.

**Smashing Magazine — "8 Simple Typography Tips"**
- URL: https://www.smashingmagazine.com/2009/04/8-simple-ways-to-improve-typography-in-your-designs/
- Insight: Keep line length between 40-80 characters, use adequate line height, and control measure for comfortable reading.
- Relevance to Halbert: The chat column is `flex-1` with no `max-width`, so on a wide screen the line length can exceed 100 characters. Capping at `max-w-3xl` or `max-w-4xl` would improve readability.

**Nielsen Norman Group — "Less Chat, More Answer"**
- URL: https://www.nngroup.com/articles/less-chat-more-answer/
- Insight: Users treat AI chat like a search bar: they want quick, scannable answers, not conversations. Long answers feel like walls of text.
- Relevance to Halbert: This is primarily a backend/prompt concern, but the UI should support it by rendering markdown with headings, bullets, and collapsible sections.

### Trust and Transparency

**Nielsen Norman Group — "Explainable AI in Chat Interfaces"**
- URL: https://www.nngroup.com/articles/explainable-ai/
- Insight: Show a model identity badge so users know what they are talking to. If you display citations, make them inspectable. Avoid fake confidence scores unless they are statistically meaningful.
- Relevance to Halbert: Halbert shows a model picker in the composer (good) and has a `ConfidenceIndicator` component. The confidence indicator should be scrutinized — is the score statistically meaningful or just decorative?

**OpenAI — "Model Spec"**
- URL: https://model-spec.openai.com/2026-08-18.html
- Insight: Disclose model identity and version in a subtle, persistent header. Surface tool execution in a collapsible trace.
- Relevance to Halbert: Halbert surfaces tool execution via `ToolExecutionCard` (good) and has a collapsible `ThinkingPanel` (good). The model identity is in the composer picker, not a persistent header.

---

## Real-World Implementations

### ChatGPT

**"Reverse Engineering ChatGPT Web"**
- URL: https://performance.dev/chatgpt
- Key pattern: SSE over `fetch` (not WebSockets), ProseMirror for the composer, CodeMirror 6 for code blocks. Streaming SSR for the shell is separate from token streaming.
- What to adopt: Use a structured editor for the composer (ProseMirror or TipTap) instead of a plain textarea. Render code with a real editor, not just `<pre>` blocks.

**"The Underappreciated UX of the ChatGPT Mobile Scroll Behavior"**
- URL: https://thomasburgess.dev/blog/the-underappreciated-ux-of-the-chat-gpt-mobile-scroll-behavior/
- Key pattern: Scroll behavior is a state machine keyed by stream status, message length, keyboard state, and user position — not a constant `scrollIntoView`.
- What to adopt: Model scroll behavior as a state machine, not a simple effect.

**"What Actually Happens When ChatGPT Streams a Response?"**
- URL: https://juntao.substack.com/p/what-actually-happens-when-chatgpt
- Key pattern: The response is parsed incrementally as NDJSON chunks. The client must handle stopping the stream, boundaries between chunks, and JSON objects that span network packets.
- What to adopt: Use an incremental, line/delimiter-based stream parser. Halbert already does this with the `buffer.split('\n')` pattern.

### Claude.ai

**"How Anthropic built Artifacts" (The Pragmatic Engineer)**
- URL: https://newsletter.pragmaticengineer.com/p/how-anthropic-built-artifacts
- Key pattern: A side-by-side canvas for generated, standalone content (code, documents, webpages) separate from the chat transcript.
- What to adopt: Halbert's context stage (right pane) serves a similar purpose. The gap is that artifacts are not first-class output objects — they're just rendered inline.

**"Claude's Visible Extended Thinking"**
- URL: https://www.anthropic.com/research/visible-extended-thinking
- Key pattern: A raw "thinking" block that users can expand or collapse. Default-collapsed, balancing transparency with the risk of unpolished intermediate thoughts.
- What to adopt: Halbert's `ThinkingPanel` already does this. The gap is the lack of `aria-expanded` and the use of emojis.

**"Thinking with tool use" (Anthropic Platform docs)**
- URL: https://platform.claude.com/docs/en/build-with-claude/thinking-tool-workflows
- Key pattern: The API returns interleaved `thinking`, `text`, and `tool_use` content blocks. Applications must echo the assistant message back verbatim on the next turn.
- What to adopt: Design the message model around typed "parts" (text, reasoning, tool-call, tool-result) and preserve them losslessly across turns. This is the strategic architecture recommendation.

### Cursor / Windsurf / Continue.dev

**Continue.dev `Chat.tsx`**
- URL: https://github.com/continuedev/continue/blob/main/gui/src/pages/gui/Chat.tsx
- Key pattern: History in a normalized Redux store, different component per message step, dedicated `useAutoScroll` hook, `Cmd/Ctrl+Backspace` to cancel.
- What to adopt: Centralize auto-scroll logic in a hook. Expose a keyboard shortcut to cancel.

**Cursor / Windsurf product analyses**
- URLs: https://cadence.withremote.ai/blog/cursor-vs-windsurf-vs-continue, https://phone-stack.com/blog/cursor-vs-windsurf
- Key pattern: Agent side panel proposes multi-file diffs, user approves/rejects step-by-step. MCP server configs as first-class tool sources.
- What to adopt: Halbert already has diff proposals with apply/reject. The gap is the lack of rollback on server failure.

### Vercel AI SDK

**"AI SDK UI: Chatbot"**
- URL: https://ai-sdk.dev/docs/ai-sdk-ui/chatbot
- Key pattern: `useChat` returns `messages`, `sendMessage`, and a `status` of `submitted | streaming | ready | error`. Messages are rendered through the `parts` property.
- What to adopt: Model chat state with explicit `status` and `parts` arrays.

**"AI SDK UI: Stream Protocol"**
- URL: https://ai-sdk.dev/v5/docs/ai-sdk-ui/stream-protocol
- Key pattern: SSE with typed part protocol: `text-delta`, `reasoning`, `source`, `tool-call`, `tool-result`, `finish-message`, `error`.
- What to adopt: Implement a typed, part-based stream protocol. Halbert's protocol is close but mixes text and reasoning into separate top-level fields instead of a unified parts array.

### Open-Source Chat UI Libraries

**`assistant-ui/assistant-ui`**
- URL: https://github.com/assistant-ui/assistant-ui
- Key pattern: Unstyled, accessible React primitives (`ThreadPrimitive`, `ComposerPrimitive`, `MessagePrimitive`, `ActionBarPrimitive`) with runtime adapters. Handles streaming, auto-scroll, message branches, tool-call rendering, and keyboard shortcuts.
- What to adopt: Evaluate as a potential replacement for the hand-rolled `AgentChat` + `useAgentStream` layer. Compatible with shadcn/ui.

**`Blazity/shadcn-chatbot-kit`**
- URL: https://github.com/Blazity/shadcn-chatbot-kit
- Key pattern: shadcn/ui-compatible chat components with clear prop contracts (`messages`, `input`, `isGenerating`, `stop`).
- What to adopt: If not adopting `assistant-ui`, consider copying individual patterns from this kit.

### Terminal-Based AI Chat

**Warp — "Block Model"**
- URL: https://www.warp.dev/blog/block-model-behind-warps-agentic-development-environment
- Key pattern: The terminal is a list of structured blocks, not a byte stream. Agent "conversation blocks" sit alongside regular terminal blocks.
- What to adopt: Halbert's timeline already treats turns as structured articles. The terminal integration (`TerminalTile`, `TurnTerminals`) is a good example of mixing rich UI with terminal output.

**GitHub Copilot CLI**
- URL: https://deepwiki.com/github/copilot-cli/6-architecture-and-technical-details
- Key pattern: Three render modes (standard, alt-screen, screen-reader-friendly). Progress/status lines collapse in place once completed.
- What to adopt: Collapse transient progress lines. Halbert's `ToolExecutionCard` does this with the expand/collapse pattern, but the header is not keyboard-accessible.
