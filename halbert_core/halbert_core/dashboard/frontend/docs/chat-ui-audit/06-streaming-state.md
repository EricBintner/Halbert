# 6. Streaming & State Machine

---

## 6.1 State Machine Overview

Halbert's agent state machine is defined in `useAgentStream.ts`:

```
idle -> planning -> searching -> reading -> executing -> observing -> reflecting -> responding -> idle
                                    |                                              |
                                    +--> error <----------------------------------+
```

Plus the special state `awaiting_confirmation` which pauses the loop until the user approves or rejects a tool execution.

### What's Good

- States are explicit and surfaced via `StateBadge` — not inferred from token text
- The `awaiting_confirmation` state is well-handled with a `ConfirmationDialog`
- The state machine is richer than most AI chat UIs (ChatGPT has ~3 states, Claude has ~4)
- The recent fix to start at `planning` instead of `idle` eliminates the "dead time" gap before the first SSE event

### What's Missing

---

## D1. No "Submitted" State Distinct from "Planning"

**Priority:** P2
**Effort:** Small
**Impact:** Low — mostly cosmetic

### Problem
The industry standard (Vercel AI SDK, Frontend Patterns) distinguishes `submitted` (message sent, waiting for first SSE event) from `thinking`/`planning` (backend is actively processing).

Halbert's recent fix to start at `planning` instead of `idle` partially addresses this, but it means the user can't distinguish "I just hit Enter and the request is in flight" from "the agent is actively planning a response."

### Industry Standard
Vercel AI SDK's `useChat` returns `status: 'submitted' | 'streaming' | 'ready' | 'error'`. The `submitted` state shows a thinking indicator before the first token arrives.

**Source:** [Vercel AI SDK — Chatbot](https://ai-sdk.dev/docs/ai-sdk-ui/chatbot)

### Recommendation
This is a minor improvement. The current behavior (showing "Planning" with a pulse animation) is good enough for most users. Defer unless there's a need to show a distinct "connecting..." state.

---

## D2. No Human-Readable Detail for States

**Priority:** P2
**Effort:** Medium
**Impact:** Medium — improves trust and transparency

### Problem
The user sees "Searching" but not *what* is being searched. "Reading" but not *which file*. "Executing" but not *which command*.

The `ScanBlock` component shows a source and query for scan operations, but not all states produce a scan. The `ToolExecutionCard` shows the tool name and arguments, but only after the tool has started — during the "executing" state before the tool call arrives, the user sees only "Executing."

### Industry Standard
Cursor, Claude, and GitHub Copilot CLI all show status lines like:
- "Reading /etc/nginx/nginx.conf..."
- "Running `git status`..."
- "Searching 1,247 files for 'useEffect cleanup'..."

These collapse or fade when the operation completes.

**Sources:**
- [GitHub Copilot CLI architecture](https://deepwiki.com/github/copilot-cli/6-architecture-and-technical-details)
- [Cursor vs Windsurf product analyses](https://cadence.withremote.ai/blog/cursor-vs-windsurf-vs-continue)

### Recommendation
The backend already sends `scan_start` events with source/query data. Extend this pattern:

1. Have the backend send a `status_detail` field with `state_change` events (e.g., `status_detail: "Reading nginx.conf"` or `status_detail: "Running git status"`)
2. Display it as a subtitle in `StateBadge` or in a separate status line below the badge
3. When the state transitions, the detail updates; when the turn completes, the detail fades

This is a backend+frontend change, so it requires coordination.

---

## D3. No Streaming Markdown Rendering

**Priority:** P2
**Effort:** Medium
**Impact:** High — visual quality of responses

### Problem
`MessageContent` only handles plain text + fenced code blocks. No inline bold, italic, links, lists, tables, or Mermaid diagrams. The regex-based parser (L21-33) splits on ` ``` ` markers and treats everything else as plain text.

Additionally, partially streamed code blocks "snap" — a partially streamed opening ` ``` ` doesn't match the regex until the closing backticks arrive, so the text suddenly re-flows from plain text to a code block.

### Industry Standard
ChatGPT and Claude both render full markdown during streaming, with incremental re-parsing that handles partial syntax gracefully. ChatGPT uses a custom markdown renderer; Claude uses `react-markdown` with `remark-gfm`.

**Sources:**
- [Reverse Engineering ChatGPT Web](https://performance.dev/chatgpt) — ChatGPT uses CodeMirror 6 for code blocks
- [Anthropic — Thinking with tool use](https://platform.claude.com/docs/en/build-with-claude/thinking-tool-workflows) — Claude renders rich content blocks

### Recommendation
Adopt `react-markdown` with `remark-gfm` for GitHub-Flavored Markdown (tables, strikethrough, task lists). For streaming, use a streaming-aware approach:

1. **Option A: `react-markdown` with re-parse on every flush.** With the rAF buffering from C1, the re-parse happens ~60 times/second, not once per token. This is simple and works well for most response lengths.

2. **Option B: `marked` with `streaming: true`.** The `marked` library has a streaming mode that handles partial markdown gracefully (e.g., unclosed code blocks render as code blocks, not plain text).

3. **Option C: `react-markdown` + custom code block component.** Use `react-markdown` for prose and a custom `CodeBlock` component (already exists) for code. This gives syntax highlighting and the "Run in Terminal" button.

Recommended: Option C, since `CodeBlock` already exists and works well.

```typescript
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

export function MessageContent({ content, onRunCommand }: MessageContentProps) {
  const memoizedContent = useMemo(() => content, [content]); // With rAF, this changes ~60fps

  return (
    <div className="space-y-2 min-w-0 overflow-hidden">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          code({ inline, className, children, ...props }) {
            const match = /language-(\w+)/.exec(className || '');
            if (!inline && match) {
              return (
                <CodeBlock
                  code={String(children)}
                  lang={match[1]}
                  onRun={onRunCommand}
                  compact
                />
              );
            }
            return <code className={className} {...props}>{children}</code>;
          },
        }}
      >
        {memoizedContent}
      </ReactMarkdown>
    </div>
  );
}
```

**Dependencies:** `react-markdown` (already in the ecosystem), `remark-gfm`.

---

## D4. No Reconnection / Resume on Network Drop

**Priority:** P3 (for local desktop app)
**Effort:** Large
**Impact:** Low for local, high for web deployment

### Problem
A dropped stream is fatal. The `catch` handler sets `session.error` and stops, but there's no automatic retry and no manual "reconnect" button (only a "Retry" button that resets the entire session).

### Industry Standard
Vercel AI SDK supports `resume: true` to reconnect to an in-flight stream after page reload, backed by a server-side stream ID and a resume endpoint.

**Source:** [Vercel AI SDK — Chatbot Resume Streams](https://ai-sdk.dev/docs/ai-sdk-ui/chatbot-resume-streams)

### Recommendation
Defer this until the app is deployed beyond localhost. For local dev, the 5-minute timeout + manual retry is sufficient. If the app is ever deployed as a web service, implement:
1. Server-side stream ID persistence
2. A `GET /api/agent/stream/:id/resume` endpoint
3. Client-side `resume` logic that reconnects to the active stream

---

## D5. `eventSourceRef.current` Is a Type System Lie

**Priority:** P3
**Effort:** Trivial
**Impact:** Low — code clarity, not correctness

### Location
**File:** `useAgentStream.ts` L870

### Current Code
```typescript
eventSourceRef.current = { close: () => { stopTimeoutCheck(); controller.abort(); } } as EventSource;
```

### Problem
The ref is typed as `EventSource` but stores a fake `{ close }` object. This works because the only method used is `.close()`, but it's a type-system escape hatch that can confuse future maintainers. If someone tries to access `.readyState` or `.url` on the ref, they'll get `undefined`.

### Recommended Fix
Change the ref type to an interface that matches what's actually stored:

```typescript
interface ClosableStream {
  close: () => void;
}

const eventSourceRef = useRef<ClosableStream | null>(null);
```

---

## D6. No Token Usage / Cost Display

**Priority:** P3
**Effort:** Medium
**Impact:** Low — nice to have

### Problem
There's no display of token usage or estimated cost for a turn. The backend may track this, but it's not surfaced in the UI.

### Industry Standard
ChatGPT shows token usage in a collapsible details section. Cursor shows token counts and cost per turn.

### Recommendation
Defer unless the backend already exposes token usage data. If it does, add a collapsible "Details" section below each assistant turn showing input/output tokens and estimated cost.
