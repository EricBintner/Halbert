# 9. Architecture Opportunities

These are strategic, longer-term changes that would improve the codebase's maintainability and enable future features. They should be planned as separate initiatives, not mixed into the tactical fixes.

---

## G1. Typed Message "Parts" Model

**Priority:** Strategic
**Effort:** Large
**Impact:** High — enables richer rendering, branching, and lossless round-tripping

### Current Architecture

Halbert models messages as flat fields on the session object:

```typescript
interface AgentSession {
  response: string;      // The assistant's text response, accumulated token by token
  thinking: string;      // The assistant's reasoning trace, accumulated token by token
  toolExecutions: ToolExecution[];  // Tool calls and results
  diffProposals: DiffProposal[];    // Diff proposals
  provenance: ProvenanceModule[];   // Source citations
  // ...
}
```

This works for rendering, but it has limitations:
- **Lossy:** When a turn is folded into the timeline, the relationship between text, thinking, tool calls, and diffs is flattened. The timeline stores them as separate arrays on the turn object.
- **No branching:** There's no way to represent "this turn has two possible responses" (e.g., regenerate creates a branch).
- **No interleaving:** The API can interleave `thinking`, `text`, and `tool_use` blocks, but Halbert's model forces them into separate fields.
- **No round-tripping:** When sending the conversation back to the API, the assistant message must be reconstructed from the flat fields, which may lose information.

### Industry Standard

Vercel AI SDK, Anthropic's API, and Claude.ai all model messages as arrays of typed parts:

```typescript
interface Message {
  id: string;
  role: 'user' | 'assistant';
  parts: MessagePart[];
}

type MessagePart =
  | { type: 'text'; content: string }
  | { type: 'reasoning'; content: string }
  | { type: 'tool_call'; id: string; tool: string; args: Record<string, unknown> }
  | { type: 'tool_result'; id: string; result: unknown; error?: string }
  | { type: 'source'; citation: Citation }
  | { type: 'diff'; id: string; status: 'pending' | 'applied' | 'rejected' }
  | { type: 'error'; message: string };
```

**Sources:**
- [Vercel AI SDK — Stream Protocol](https://ai-sdk.dev/v5/docs/ai-sdk-ui/stream-protocol) — typed part protocol: `text-delta`, `reasoning`, `source`, `tool-call`, `tool-result`, `finish-message`, `error`
- [Anthropic — Thinking with tool use](https://platform.claude.com/docs/en/build-with-claude/thinking-tool-workflows) — "The API returns interleaved `thinking`, `text`, and `tool_use` content blocks. Applications must echo the assistant message back verbatim."
- [Claude's Visible Extended Thinking](https://www.anthropic.com/research/visible-extended-thinking) — thinking is a distinct content block, not a separate field

### Migration Path

This is a significant refactor. A phased approach:

**Phase 1: Define the types (no behavior change)**
- Define `MessagePart` types in a new `types/message.ts`
- Define a `Message` type with `parts: MessagePart[]`
- Don't change any existing code yet

**Phase 2: Map SSE events to parts (additive)**
- In `useAgentStream.ts`, in addition to the existing `setResponse`/`setThinking`/etc., accumulate parts into a `partsRef`
- The existing fields continue to be updated for backward compatibility
- Add a `parts` field to `AgentSession`

**Phase 3: Render from parts (parallel)**
- Create a new `MessagePartsRenderer` component that renders from `parts`
- Run it alongside the existing `MessageContent` + `ToolExecutionCard` + `ThinkingPanel` stack
- Feature-flag the switch

**Phase 4: Remove the old fields (cleanup)**
- Once the parts renderer is stable, remove `response`, `thinking`, `toolExecutions`, `diffProposals`, and `provenance` from `AgentSession`
- Update the timeline to store and render from `parts`
- Update the backend to send parts-based events (if needed)

### Benefits

- **Lossless round-tripping:** The assistant message can be sent back to the API verbatim, including thinking blocks and tool results.
- **Interleaving:** Text, reasoning, and tool calls can be rendered in the order they occurred, not in separate sections.
- **Branching:** A turn can have multiple `parts` arrays (one per branch), enabling regenerate and edit.
- **Richer rendering:** Each part type can have its own renderer, making it easy to add new part types (e.g., `image`, `file`, `mermaid`).
- **Streaming:** Parts can be appended incrementally, and each part can have its own streaming state.

---

## G2. Evaluate `assistant-ui` Primitives

**Priority:** Strategic
**Effort:** Medium (evaluation) to Large (adoption)
**Impact:** High — could eliminate most accessibility and scroll bugs

### What It Is

[`assistant-ui`](https://github.com/assistant-ui/assistant-ui) is an open-source TypeScript/React library built around unstyled, accessible primitives:

- `ThreadPrimitive` — the scrollable message list with auto-scroll, end-anchoring, and keyboard navigation
- `ComposerPrimitive` — the input area with submit, cancel, and accessibility
- `MessagePrimitive` — renders a single message with role-aware content
- `ActionBarPrimitive` — hover-revealed action bar (copy, regenerate, thumbs up/down)
- `BranchPickerPrimitive` — switch between branches of a conversation

It has runtime adapters for Vercel AI SDK, LangGraph, AG-UI, and OpenCode. It handles:
- Streaming (text, reasoning, tool calls)
- Auto-scroll with user-scroll detection
- Message branches
- Tool-call rendering
- Keyboard shortcuts
- ARIA live regions

It's compatible with shadcn/ui, which the project already uses.

### What It Would Replace

Adopting `assistant-ui` would replace:
- `AgentChat.tsx` (the main chat surface) — replaced by `ThreadPrimitive` + `ComposerPrimitive`
- `useAgentStream.ts` (the streaming hook) — replaced by a runtime adapter
- `MessageContent.tsx` — replaced by `MessagePrimitive` with custom part renderers
- The auto-scroll logic in `AgentChat.tsx` — replaced by `ThreadPrimitive`'s built-in scroll behavior
- The `LiveRegion` announcement logic — replaced by `assistant-ui`'s built-in ARIA

### What It Would Not Replace

- `Timeline.tsx` — the persisted conversation history is custom and would remain
- `ToolExecutionCard.tsx` — custom tool rendering would still be needed
- `ThinkingPanel.tsx` — custom reasoning display would still be needed
- `TerminalTile` / terminal integration — completely custom
- The diff/provenance/scan components — custom

### Evaluation Steps

1. **Read the docs:** [assistant-ui.com/docs/primitives](https://www.assistant-ui.com/docs/primitives)
2. **Try the shadcn starter:** `npx shadcn@latest add "https://www.assistant-ui.com/r/assistant-ui"`
3. **Build a prototype:** Replace `AgentChat` with `ThreadPrimitive` + `ComposerPrimitive` in a branch
4. **Test with the Halbert backend:** Write a runtime adapter that maps Halbert's SSE events to `assistant-ui`'s part protocol
5. **Evaluate:** Does it handle the terminal integration? Does it handle the confirmation flow? Does it handle the diff proposals?

### Risks

- **Terminal integration:** `assistant-ui` doesn't have built-in terminal support. The terminal tiles would need to be custom part renderers.
- **Confirmation flow:** The `awaiting_confirmation` state is custom. It would need to be a custom part type or a separate UI layer.
- **Timeline:** The persisted timeline is custom and may not map cleanly to `assistant-ui`'s thread model.
- **Bundle size:** Adding another dependency increases the bundle. Evaluate the size impact.

### Recommendation

Evaluate `assistant-ui` as a potential replacement for the live turn rendering (not the timeline). If it handles the streaming, auto-scroll, and accessibility well, it could eliminate most of the P0/P1 bugs for free. If the terminal integration or confirmation flow is too difficult to adapt, stick with the current architecture and fix the bugs manually.
