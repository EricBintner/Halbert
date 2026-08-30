# 7. Accessibility Audit

## Summary

The timeline has excellent ARIA (`role="feed"`, `aria-posinset`/`aria-setsize`, day headings), and the `LiveRegion` implementation follows MDN guidance exactly. However, several interactive components in the live turn and composer are inaccessible to keyboard and screen-reader users.

---

## 7.1 `agentError` Banner Not Announced

**Priority:** P1
**Effort:** Trivial
**Impact:** Medium — screen-reader users don't know errors exist

### Location
**File:** `AgentChat.tsx` L1045-1054

### Problem
The error banner is rendered visually but never sent through `announce`. Screen-reader users don't know a retry button exists unless they manually explore the DOM.

### Current Code
```typescript
{agentError && !isStreaming && (
  <div className="flex justify-center">
    <div className="bg-error/10 border border-error/30 rounded-lg px-4 py-2 flex items-center gap-2">
      <span className="text-sm text-error">{agentError}</span>
      <button type="button" aria-label="Retry" onClick={handleReset} className="p-1 hover:bg-error/20 rounded">
        <RotateCcw className="h-4 w-4 text-error" aria-hidden="true" />
      </button>
    </div>
  </div>
)}
```

### Recommended Fix
Add a `useEffect` to announce errors:
```typescript
useEffect(() => {
  if (agentError) {
    announce(agentError, { assertive: true });
  }
}, [agentError]);
```

---

## 7.2 State Transitions Not Announced

**Priority:** P2
**Effort:** Small
**Impact:** Medium — screen-reader users can't follow the agent's progress

### Location
**File:** `useAgentStream.ts` — only `awaiting_confirmation` is announced (L385)

### Problem
The `onStateChange` callback is called when the state transitions (e.g., `planning -> searching`), but it only logs to console. Screen-reader users hear nothing when the agent moves from "Planning" to "Searching" to "Executing."

Only `awaiting_confirmation` is announced: `announce('Waiting for your approval', { assertive: true })`.

### Recommended Fix
Announce meaningful state transitions in the `onStateChange` handler in `AgentChat`:

```typescript
const handleStateChange = useCallback((newState: AgentState) => {
  const messages: Record<AgentState, string> = {
    idle: '',
    planning: 'Planning response',
    searching: 'Searching knowledge base',
    reading: 'Reading files',
    executing: 'Executing tool',
    observing: 'Observing results',
    reflecting: 'Reflecting on results',
    responding: 'Responding',
    awaiting_confirmation: 'Waiting for your approval',
    error: 'Error occurred',
  };
  const msg = messages[newState];
  if (msg) {
    announce(msg, { assertive: newState === 'awaiting_confirmation' || newState === 'error' });
  }
}, [announce]);
```

Note: Don't announce every token — only state transitions, which happen infrequently.

**Source:** [Tian Pan — "Streaming Tokens Meet the Screen Reader"](https://tianpan.co/blog/2026/06/29/streaming-tokens-meet-the-screen-reader) — "Do not announce every token. Use `aria-live="polite"` on a hidden announcer that only speaks on complete messages or meaningful state changes."

---

## 7.3 Composer Textarea Has No `aria-label`

**Priority:** P1
**Effort:** Trivial
**Impact:** Medium — fails WCAG accessible name requirement

### Location
**File:** `AgentChat.tsx` L1156-1169

### Problem
The textarea relies on its `placeholder` for its accessible name. When a value is present, the placeholder disappears, and the textarea has no accessible name. This fails WCAG 4.1.2 (Name, Role, Value).

### Current Code
```typescript
<textarea
  ref={inputRef}
  value={input}
  onChange={(e) => { handleInputChange(e); autoResizeTextarea(); }}
  onKeyDown={handleKeyDown}
  onPaste={handlePaste}
  placeholder={isStreaming ? "Type to queue next message..." : "Ask Halbert... (@ to mention, paste/drop images)"}
  className="..."
  rows={1}
  style={{ maxHeight: '150px' }}
/>
```

### Recommended Fix
Add an `aria-label`:
```typescript
<textarea
  ref={inputRef}
  value={input}
  onChange={(e) => { handleInputChange(e); autoResizeTextarea(); }}
  onKeyDown={handleKeyDown}
  onPaste={handlePaste}
  aria-label="Message Halbert"
  placeholder={isStreaming ? "Type to queue next message..." : "Ask Halbert... (@ to mention, paste/drop images)"}
  className="..."
  rows={1}
  style={{ maxHeight: '150px' }}
/>
```

---

## 7.4 Mention Autocomplete Is Mouse-Only

**Priority:** P2
**Effort:** Medium
**Impact:** Medium — keyboard users can't navigate mentions

### Location
**File:** `AgentChat.tsx` L1079-1097

### Problem
The mention popup has:
- No `role="listbox"` on the container
- No `role="option"` on the items
- No `aria-activedescendant` on the textarea
- No arrow-key navigation
- Only `Escape` works to dismiss it (L817-824)

Keyboard users can see the popup but can't navigate it without tabbing through each item, which is not the standard listbox interaction pattern.

### Recommended Fix
Implement proper combobox/listbox semantics:

```typescript
// Container
<div
  role="listbox"
  aria-label="Mentions"
  className="mx-4 mb-1 bg-muted border border-border rounded-md shadow-lg max-h-48 overflow-y-auto"
>
  {filteredMentionables.map((m, idx) => (
    <button
      key={m.id}
      role="option"
      aria-selected={idx === activeMentionIndex}
      className={cn(
        "w-full px-3 py-1.5 text-left hover:bg-muted flex items-center gap-2 text-xs",
        idx === activeMentionIndex && "bg-muted"
      )}
      onClick={() => insertMention(m)}
    >
      {/* ... */}
    </button>
  ))}
</div>

// On the textarea:
<textarea
  // ... existing props ...
  aria-label="Message Halbert"
  aria-expanded={showMentions}
  aria-controls="mention-listbox"
  aria-activedescendant={activeMentionId}
/>

// In handleKeyDown:
if (showMentions) {
  if (e.key === 'ArrowDown') {
    e.preventDefault();
    setActiveMentionIndex(i => Math.min(i + 1, filteredMentionables.length - 1));
    return;
  }
  if (e.key === 'ArrowUp') {
    e.preventDefault();
    setActiveMentionIndex(i => Math.max(i - 1, 0));
    return;
  }
  if (e.key === 'Enter' && activeMentionIndex >= 0) {
    e.preventDefault();
    insertMention(filteredMentionables[activeMentionIndex]);
    return;
  }
}
```

---

## 7.5 `ToolExecutionCard` Not Keyboard-Accessible

**Priority:** P1
**Effort:** Small
**Impact:** Medium — keyboard users can't expand/collapse tool cards

### Location
**File:** `ToolExecutionCard.tsx` L95-118

### Problem
The expand/collapse header is a `<div onClick={...}>` with `cursor-pointer` but:
- No `tabIndex` (not focusable)
- No `role="button"` (not semantically a button)
- No `aria-expanded` (doesn't expose expanded state)
- No keyboard handler (Enter/Space don't work)

### Current Code
```typescript
<div
  className="flex items-center justify-between p-2 cursor-pointer hover:bg-opacity-80 bg-surface"
  onClick={() => setIsExpanded(!isExpanded)}
>
  {/* ... */}
</div>
```

### Recommended Fix
Change to a `<button>` or add the necessary ARIA attributes:

```typescript
<button
  type="button"
  className="flex items-center justify-between p-2 cursor-pointer hover:bg-opacity-80 bg-surface w-full text-left"
  onClick={() => setIsExpanded(!isExpanded)}
  aria-expanded={isExpanded}
  aria-controls={`tool-content-${execution.id}`}
>
  {/* ... */}
</button>

// And on the content:
<div
  id={`tool-content-${execution.id}`}
  role="region"
  aria-label={`${execution.tool} details`}
>
  {/* ... */}
</div>
```

---

## 7.6 `ThinkingPanel` Missing `aria-expanded`

**Priority:** P3
**Effort:** Trivial
**Impact:** Low — screen-reader users don't know panel state

### Location
**File:** `ThinkingPanel.tsx` L44-64

### Problem
The toggle is a real `<button>` (good), but it doesn't expose its expanded state. The section toggles (L107-118) have the same issue.

### Current Code
```typescript
<button
  onClick={() => setIsExpanded(!isExpanded)}
  className="w-full px-4 py-2 flex items-center justify-between bg-muted hover:bg-muted transition-colors"
>
  {/* ... */}
</button>
```

### Recommended Fix
```typescript
<button
  onClick={() => setIsExpanded(!isExpanded)}
  aria-expanded={isExpanded}
  aria-controls="thinking-content"
  className="w-full px-4 py-2 flex items-center justify-between bg-muted hover:bg-muted transition-colors"
>
  {/* ... */}
</button>

// And on the content:
<div id="thinking-content" className="border-t">
  {/* ... */}
</div>
```

Apply the same pattern to `ThinkingSection` toggles (L107-118).

---

## 7.7 Emojis in ThinkingPanel

**Priority:** P3
**Effort:** Trivial
**Impact:** Low — project rule violation

### Location
**File:** `ThinkingPanel.tsx` L50-51

### Problem
The header uses `🧠` and `💭` emojis. The project rules state: "no emojis — use icon fonts or clever graphic design."

### Current Code
```typescript
<span className="text-muted-foreground">
  {isStreaming ? '🧠' : '💭'}
</span>
```

### Recommended Fix
Replace with SVG icons or icon-font glyphs. For example, using Lucide icons (already used elsewhere in the project):

```typescript
import { Brain, MessageSquare } from 'lucide-react';

<span className="text-muted-foreground">
  {isStreaming ? <Brain className="h-4 w-4" /> : <MessageSquare className="h-4 w-4" />}
</span>
```

---

## 7.8 Overflow `<pre>` Elements Not Focusable

**Priority:** P3
**Effort:** Trivial
**Impact:** Low — keyboard users can't scroll long output

### Location
- `ThinkingPanel.tsx` L81-87
- `ToolExecutionCard.tsx` L131-173

### Problem
`<pre>` elements with `overflow: auto` are not focusable by default. Keyboard users can't scroll long thinking traces or tool output without clicking inside the element (which doesn't work reliably across browsers).

### Recommended Fix
Add `tabIndex={0}` and an `aria-label`:
```typescript
<pre
  tabIndex={0}
  aria-label="Thinking content"
  ref={contentRef}
  className="p-4 text-xs text-muted-foreground whitespace-pre-wrap overflow-auto bg-muted focus:outline-none focus:ring-1 focus:ring-info"
  style={{ maxHeight }}
>
  {thinking}
</pre>
```

---

## 7.9 No Focus Management After Redaction

**Priority:** P3
**Effort:** Small
**Impact:** Low — screen-reader users are dropped on `body`

### Location
**File:** `Timeline.tsx` — "Forget this" button

### Problem
When a turn is fully forgotten, the "Forget this" button unmounts, but focus is not returned anywhere meaningful. A screen-reader user is dropped on `body`.

### Recommended Fix
Move focus to the next turn's article or to the composer:
```typescript
// After the turn is forgotten:
if (nextTurnArticleRef.current) {
  nextTurnArticleRef.current.focus();
} else {
  composerRef.current?.focus();
}
```

---

## 7.10 No `prefers-reduced-motion` Support for Pulse Animation

**Priority:** P3
**Effort:** Trivial
**Impact:** Low — vestibular disorders

### Location
**File:** `StateBadge.tsx` L99-104

### Problem
The pulse animation uses Tailwind's `animate-ping`, which is not gated on `prefers-reduced-motion`. Users with vestibular disorders may find the constant pulsing uncomfortable.

### Recommended Fix
Add a CSS media query or Tailwind variant:
```css
@media (prefers-reduced-motion: reduce) {
  .animate-ping {
    animation: none;
  }
}
```

Or use Tailwind's `motion-reduce:` variant:
```typescript
<span className={`animate-ping motion-reduce:animate-none absolute inline-flex h-full w-full rounded-full opacity-75 ${config.pulseColor}`} />
```

**Source:** [Frontend Patterns — Thinking Indicator](https://frontendpatterns.dev/thinking-indicator) — "Provide a non-animated fallback for `prefers-reduced-motion`."

---

## 7.11 No Accessible Labels on HostShell Regions

**Priority:** P3
**Effort:** Trivial
**Impact:** Low — landmark navigation

### Location
**File:** `HostShell.tsx` L61-71

### Problem
The conversation column and the context stage `<aside>` have no `aria-label`, making landmark navigation harder for screen-reader users.

### Recommended Fix
```typescript
<div
  ref={conversationRef}
  className="flex-1 min-w-0 flex flex-col bg-background border-r border-border"
  aria-label="Conversation"
>
  <AgentChat className="h-full" onOpenModelSettings={openModelSettings} />
</div>

<aside
  className="hidden md:flex w-1/2 max-w-[640px] min-w-[320px] shrink-0"
  aria-label="Context stage"
>
  <ContextStage className="w-full" onJumpToTerminal={jumpToTerminal} />
</aside>
```
