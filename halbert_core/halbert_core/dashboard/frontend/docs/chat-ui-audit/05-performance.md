# 5. Performance Concerns

---

## C1. Token-by-Token React State = O(n^2) String Concatenation

**Priority:** P1
**Effort:** Small
**Impact:** High — perf + battery for long responses

### Location
**File:** `useAgentStream.ts` L486 (response), L490 (thinking)

### Current Code
```typescript
case 'response_chunk':
  console.log('[AGENT] response_chunk:', JSON.stringify(event.content));
  setResponse(r => r + (event.content as string));
  return prev;

case 'thinking':
  setThinking(t => t + (event.content as string));
  return prev;
```

### Problem
Every `response_chunk` event calls `setResponse(r => r + chunk)`. For a 2000-token reply:

1. **String concatenation:** 2000 concatenations of growing strings. JavaScript strings are immutable, so each `r + chunk` creates a new string of length `len(r) + len(chunk)`. The total work is O(n^2) where n is the final response length.

2. **React re-renders:** 2000 `setResponse` calls = 2000 React re-renders of the component tree that depends on `response`. Each re-render triggers `MessageContent` to re-parse the entire response string.

3. **Regex re-parsing:** `MessageContent.tsx` (L21-33) runs a code-block regex on the full response string on every render:
   ```typescript
   const codeBlockRegex = /```(\w+)?\n?([\s\S]*?)```/g;
   ```
   This is O(n) per render, O(n^2) total across all tokens.

4. **Console logging:** The `console.log` on L485 adds overhead on every token, including `JSON.stringify` of the content.

### Industry Standard
Buffer chunks in a ref and flush to React state once per `requestAnimationFrame` (~60fps). The user sees no visual difference; CPU usage drops by ~10x.

**Source:** [The Frontend Casebook — "Streaming Tokens Without Layout Thrash"](https://anmshpndy.com/cases/streaming-tokens-ui-buffer/)

> LLMs emit 30-80 tokens/second but the screen only refreshes at ~60 Hz. Writing each token to the DOM as it arrives causes wasted reflows. Accumulate chunks and flush once per `requestAnimationFrame` frame to cut CPU usage without visibly slower rendering.

### Recommended Fix
Add a buffer ref and a rAF flush loop in the stream reader:

```typescript
// In useAgentStream.ts
const responseBufferRef = useRef('');
const thinkingBufferRef = useRef('');
const rafRef = useRef<number | null>(null);

const scheduleFlush = useCallback(() => {
  if (rafRef.current !== null) return; // Already scheduled
  rafRef.current = requestAnimationFrame(() => {
    if (responseBufferRef.current) {
      setResponse(r => r + responseBufferRef.current);
      responseBufferRef.current = '';
    }
    if (thinkingBufferRef.current) {
      setThinking(t => t + thinkingBufferRef.current);
      thinkingBufferRef.current = '';
    }
    rafRef.current = null;
  });
}, []);

// In handleEvent:
case 'response_chunk':
  responseBufferRef.current += event.content as string;
  scheduleFlush();
  return prev;

case 'thinking':
  thinkingBufferRef.current += event.content as string;
  scheduleFlush();
  return prev;

// Cleanup on stream end:
// In the stream reader, after the while loop:
if (rafRef.current !== null) {
  cancelAnimationFrame(rafRef.current);
  rafRef.current = null;
}
// Final flush
if (responseBufferRef.current) {
  setResponse(r => r + responseBufferRef.current);
  responseBufferRef.current = '';
}
if (thinkingBufferRef.current) {
  setThinking(t => t + thinkingBufferRef.current);
  thinkingBufferRef.current = '';
}
```

Also remove the `console.log` on L485, or gate it behind a debug flag.

---

## C2. `MessageContent` Re-Parses Entire Response on Every Render

**Priority:** P2
**Effort:** Small
**Impact:** Medium — compounds with C1

### Location
**File:** `MessageContent.tsx` L19-41

### Current Code
```typescript
export function MessageContent({ content, onRunCommand }: MessageContentProps) {
  const parts: Array<{ type: 'text' | 'code', content: string, lang?: string }> = [];
  const codeBlockRegex = /```(\w+)?\n?([\s\S]*?)```/g;
  let lastIndex = 0;
  let match;

  while ((match = codeBlockRegex.exec(content)) !== null) {
    if (match.index > lastIndex) {
      parts.push({ type: 'text', content: content.slice(lastIndex, match.index) });
    }
    let codeContent = match[2].trim();
    codeContent = codeContent.replace(/^`+|`+$/g, '').trim();
    parts.push({ type: 'code', content: codeContent, lang: match[1] || 'bash' });
    lastIndex = match.index + match[0].length;
  }

  if (lastIndex < content.length) {
    parts.push({ type: 'text', content: content.slice(lastIndex) });
  }
  // ...
```

### Problem
The parsing logic runs on every render with no memoization. During streaming, this means the full response string is regex-parsed on every token. Combined with C1 (one render per token), this is O(n) per render and O(n^2) total.

### Recommended Fix
Wrap the parse in `useMemo`:

```typescript
export function MessageContent({ content, onRunCommand }: MessageContentProps) {
  const parts = useMemo(() => {
    const result: Array<{ type: 'text' | 'code', content: string, lang?: string }> = [];
    const codeBlockRegex = /```(\w+)?\n?([\s\S]*?)```/g;
    let lastIndex = 0;
    let match;

    while ((match = codeBlockRegex.exec(content)) !== null) {
      if (match.index > lastIndex) {
        result.push({ type: 'text', content: content.slice(lastIndex, match.index) });
      }
      let codeContent = match[2].trim();
      codeContent = codeContent.replace(/^`+|`+$/g, '').trim();
      result.push({ type: 'code', content: codeContent, lang: match[1] || 'bash' });
      lastIndex = match.index + match[0].length;
    }

    if (lastIndex < content.length) {
      result.push({ type: 'text', content: content.slice(lastIndex) });
    }

    if (result.length === 0) {
      result.push({ type: 'text', content });
    }

    return result;
  }, [content]);

  // ... render parts ...
}
```

With the rAF buffering from C1, `content` only changes ~60 times/second instead of once per token, so `useMemo` will be effective.

---

## C3. `parseThinkingSections` Not Memoized

**Priority:** P3
**Effort:** Trivial
**Impact:** Low — only affects long reasoning traces

### Location
**File:** `ThinkingPanel.tsx` L40, L133-189

### Problem
`parseThinkingSections(thinking)` is called on every render with no memoization. For long reasoning traces (which can be thousands of tokens), this runs the section-parsing regex on every token change.

### Recommended Fix
```typescript
const sections = useMemo(
  () => parseThinkingSections(thinking),
  [thinking]
);
```

With the rAF buffering from C1, `thinking` only changes ~60 times/second, making this memoization effective.

---

## C4. `useTimeline` Has No `AbortController`

**Priority:** P3
**Effort:** Small
**Impact:** Low — wasted network requests on unmount

### Location
**File:** `useTimeline.ts` L238-267, L280-315, L317-349

### Problem
Initial and paging requests are not cancellable on unmount. The `cancelled` flag prevents state writes after unmount, but a slow request will continue to the server, consuming bandwidth and server resources.

### Recommended Fix
Use `AbortController` for each request:
```typescript
const abortControllerRef = useRef<AbortController | null>(null);

const loadLatest = useCallback(async () => {
  abortControllerRef.current?.abort();
  const controller = new AbortController();
  abortControllerRef.current = controller;

  try {
    const res = await fetch(apiUrl('/api/timeline?limit=20'), {
      signal: controller.signal,
    });
    // ... process response ...
  } catch (err) {
    if (err.name === 'AbortError') return;
    // ... handle error ...
  }
}, []);

// Cleanup on unmount:
useEffect(() => {
  return () => abortControllerRef.current?.abort();
}, []);
```

---

## C5. `inFlight` Flag Is Shared Across All Load Variants

**Priority:** P3
**Effort:** Small
**Impact:** Low — UI feels unresponsive in edge cases

### Location
**File:** `useTimeline.ts` — `inFlight` state

### Problem
A single `inFlight` flag is shared across `loadLatest`, `loadOlder`, and `loadAround`. While `loadLatest` waits, a `loadOlder` or `loadAround` will be ignored, which can make the UI feel unresponsive if the user clicks "Load earlier" while the initial load is still in progress.

### Recommended Fix
Use separate flags for each load variant, or use a queue that processes requests in order.
