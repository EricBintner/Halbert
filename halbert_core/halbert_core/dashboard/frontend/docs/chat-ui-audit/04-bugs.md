# 4. Bugs & Correctness Issues

These are things that are broken or will break under real use. Each is documented with the file, line numbers, root cause, industry standard, and recommended fix.

---

## B1. Auto-Scroll Yanks Users Back Down

**Priority:** P0
**Effort:** Small
**Impact:** High — fixes the single most disruptive UX issue

### Location
**File:** `AgentChat.tsx` L444-448

### Current Code
```typescript
const tailTurnId = turns.length > 0 ? turns[turns.length - 1].turnId : null;
useEffect(() => {
  if (anchored) return;
  messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
}, [tailTurnId, anchored, liveUser, response, session?.toolExecutions]);
```

### Problem
The scroll effect fires on every `response` change (every token), every `toolExecutions` change, and every `liveUser` change — with no "is the user near the bottom?" guard. If the user scrolls up to read an old answer while the agent is streaming, they get yanked back down on every token.

The `anchored` flag only applies when the user has navigated to an older turn via a thread chip — it does not track free scrolling within the message container.

### Industry Standard
ChatGPT, Claude, MUI X Chat, and Continue.dev all gate auto-scroll on a proximity check. The pattern is:

1. Track `isAtBottom` state via an `onScroll` handler: `scrollHeight - scrollTop - clientHeight < threshold`
2. Only call `scrollIntoView` when `isAtBottom` is true
3. When the user scrolls past the threshold, show a floating "Jump to latest" button
4. Re-enable auto-scroll when the user clicks the button or scrolls back to the bottom

The threshold is typically 60-150px. For desktop (no momentum scroll), 100px is appropriate.

**Sources:**
- [TanStack — "Chat UIs Are Lists Until They Aren't"](https://tanstack.com/blog/tanstack-virtual-chat)
- [MUI X — "Chat Scrolling"](https://mui.com/x/react-chat/behavior/scrolling/)
- [HelloFrontend — "Building Chat UIs That Don't Annoy Users"](https://hellofrontend.com/frontend-ai-interview/chat-ui-patterns)

### Recommended Fix
```typescript
const [isAtBottom, setIsAtBottom] = useState(true);
const scrollContainerRef = useRef<HTMLDivElement>(null);

const handleScroll = useCallback(() => {
  const el = scrollContainerRef.current;
  if (!el) return;
  const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
  setIsAtBottom(distanceFromBottom < 100);
}, []);

useEffect(() => {
  if (anchored || !isAtBottom) return;
  messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
}, [tailTurnId, anchored, isAtBottom, liveUser, response, session?.toolExecutions]);

// In the JSX:
<div
  ref={scrollContainerRef}
  onScroll={handleScroll}
  className="flex-1 overflow-y-auto ..."
>
  {/* messages */}
  <div ref={messagesEndRef} />
</div>

{/* Floating "Jump to latest" button */}
{!isAtBottom && !anchored && (
  <button
    onClick={() => {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
      setIsAtBottom(true);
    }}
    className="..."
  >
    Jump to latest
  </button>
)}
```

---

## B2. `confirmAction` Stream Cannot Be Cancelled

**Priority:** P0
**Effort:** Small
**Impact:** High — fixes a stuck-state bug

### Location
**File:** `useAgentStream.ts` L873-930

### Current Code
```typescript
const confirmAction = useCallback((actionId: string, confirmed: boolean) => {
  if (!sessionIdRef.current) return;

  // Close existing connection
  eventSourceRef.current?.close();

  setIsStreaming(true);
  setSession(prev => prev ? { ...prev, pendingConfirmation: null } : null);

  const url = apiUrl(`/api/agent/confirm/${sessionIdRef.current}`);

  fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action_id: actionId, confirmed })
  }).then(response => {
    // ... reads the stream ...
  }).catch(err => {
    console.error('Confirmation error:', err);
    setIsStreaming(false);
    setSession(prev => prev ? { ...prev, error: String(err) } : null);
  });
}, [handleEvent]);
```

### Problem
`confirmAction` creates a `fetch` call but never creates an `AbortController` and never stores anything in `eventSourceRef.current`. The `cancel()` function (L932-934) reads `eventSourceRef.current?.close()` — so during a confirmation stream:

1. The Stop button does nothing (there's nothing to abort)
2. `isStreaming` stays `true` forever (the stream is not cancellable)
3. The user is stuck watching a confirmation response with no way to stop it

Compare with `sendMessage` (L870) which correctly stores the controller:
```typescript
eventSourceRef.current = { close: () => { stopTimeoutCheck(); controller.abort(); } } as EventSource;
```

### Recommended Fix
Add an `AbortController` to `confirmAction` and store it in `eventSourceRef.current`:

```typescript
const confirmAction = useCallback((actionId: string, confirmed: boolean) => {
  if (!sessionIdRef.current) return;

  eventSourceRef.current?.close();

  setIsStreaming(true);
  setSession(prev => prev ? { ...prev, pendingConfirmation: null } : null);

  const controller = new AbortController();
  const url = apiUrl(`/api/agent/confirm/${sessionIdRef.current}`);

  // Store the controller so cancel() can abort it
  eventSourceRef.current = {
    close: () => { controller.abort(); }
  } as EventSource;

  fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action_id: actionId, confirmed }),
    signal: controller.signal,
  }).then(response => {
    // ... existing stream reading logic ...
  }).catch(err => {
    if (err.name === 'AbortError') return; // User cancelled, not an error
    console.error('Confirmation error:', err);
    setIsStreaming(false);
    setSession(prev => prev ? { ...prev, error: String(err) } : null);
  });
}, [handleEvent]);
```

---

## B3. Error Events Don't Stop Streaming

**Priority:** P0
**Effort:** Trivial
**Impact:** High — fixes a stuck-state bug

### Location
**File:** `useAgentStream.ts` L520-523

### Current Code
```typescript
case 'error':
  const errorMsg = event.message as string;
  options.onError?.(errorMsg);
  return { ...prev, error: errorMsg };
```

### Problem
If the backend sends an `error` SSE event without a subsequent `session_ended`, the UI keeps showing a pulsing "responding" state indefinitely. The `error` handler sets `session.error` but doesn't call `setIsStreaming(false)`.

The stream reader loop (L855-858) only calls `setIsStreaming(false)` when the stream ends naturally (`done === true`). If the backend sends an error event but keeps the connection open, the UI is stuck.

### Recommended Fix
Add `setIsStreaming(false)` in the error handler. Since `handleEvent` is a `setSession` updater and can't call `setIsStreaming` directly, use the `options.onError` callback or a ref:

```typescript
case 'error':
  const errorMsg = event.message as string;
  options.onError?.(errorMsg);
  // Stop streaming — the error is terminal
  // This needs to be called outside the setSession updater,
  // so use a ref or schedule it
  queueMicrotask(() => setIsStreaming(false));
  return { ...prev, error: errorMsg };
```

Alternatively, handle this in the `onError` callback in `AgentChat`:
```typescript
const { sendMessage, ... } = useAgentStream({
  onError: (err) => {
    announce(err, { assertive: true });
    // setIsStreaming is handled inside the hook
  },
  // ...
});
```

The cleanest approach is to have the hook handle it internally, since the hook owns `isStreaming`.

---

## B4. `onRunCommand` Is Dead in HostShell

**Priority:** P1 (was P2, but it's a completely dead feature)
**Effort:** Small
**Impact:** Medium — "Run in Terminal" buttons in code blocks are inert

### Location
**File:** `HostShell.tsx` L65

### Current Code
```typescript
<AgentChat className="h-full" onOpenModelSettings={openModelSettings} />
```

### Problem
`AgentChat` accepts an `onRunCommand` prop and passes it down to `Timeline` and `MessageContent` (L912, L997, L428). `MessageContent` passes it to `CodeBlock` as the `onRun` prop. But `HostShell` never provides `onRunCommand`, so it's `undefined` in the main shell.

The "Run in Terminal" buttons in code blocks render but do nothing when clicked.

### Recommended Fix
Either wire `onRunCommand` through `HostShell`:
```typescript
const handleRunCommand = useCallback((command: string) => {
  // Dispatch to the terminal store or open a new terminal
  window.dispatchEvent(new CustomEvent('halbert:run-command', { detail: command }));
}, []);

<AgentChat
  className="h-full"
  onOpenModelSettings={openModelSettings}
  onRunCommand={handleRunCommand}
/>
```

Or, if the feature is not ready, remove the `onRun` button from `CodeBlock` when the prop is `undefined` to avoid showing dead UI.

---

## B5. Diff Apply/Reject Are Fire-and-Forget

**Priority:** P2
**Effort:** Small
**Impact:** Medium — correctness and user trust

### Location
**File:** `useAgentStream.ts` L966-996

### Current Code
```typescript
const applyDiff = useCallback((diffId: string) => {
  if (!sessionIdRef.current) return;

  // Optimistically update local state
  setSession(prev => prev ? {
    ...prev,
    diffProposals: prev.diffProposals.map(d =>
      d.id === diffId ? { ...d, status: 'applied' as const } : d
    ),
  } : null);

  // Send to backend
  fetch(apiUrl(`/api/agent/diff/${sessionIdRef.current}/${diffId}/apply`), { method: 'POST' })
    .catch(err => console.error('Apply diff error:', err));
}, []);
```

### Problem
The optimistic state update happens immediately, but the backend call is fire-and-forget. If the server rejects (e.g., file was modified, permission denied, diff conflict), there's:
- No rollback of the optimistic state
- No error banner
- No user feedback
- The diff shows as "applied" when it actually wasn't

The same issue applies to `rejectDiff` (L982-996).

### Recommended Fix
Return a promise, revert on failure, and surface an error:

```typescript
const applyDiff = useCallback(async (diffId: string) => {
  if (!sessionIdRef.current) return;

  // Save previous state for rollback
  const previousStatus = session?.diffProposals.find(d => d.id === diffId)?.status;

  // Optimistically update
  setSession(prev => prev ? {
    ...prev,
    diffProposals: prev.diffProposals.map(d =>
      d.id === diffId ? { ...d, status: 'applied' as const } : d
    ),
  } : null);

  try {
    const res = await fetch(
      apiUrl(`/api/agent/diff/${sessionIdRef.current}/${diffId}/apply`),
      { method: 'POST' }
    );
    if (!res.ok) throw new Error(`Apply failed: ${res.status}`);
  } catch (err) {
    // Rollback
    setSession(prev => prev ? {
      ...prev,
      diffProposals: prev.diffProposals.map(d =>
        d.id === diffId ? { ...d, status: previousStatus ?? 'pending' } : d
      ),
      error: `Failed to apply diff: ${String(err)}`,
    } : null);
  }
}, [session]);
```

---

## B6. SSE Parser Silently Swallows Malformed Events

**Priority:** P3
**Effort:** Low
**Impact:** Low — content may be missing with no indication

### Location
**File:** `useAgentStream.ts` L845-854 (sendMessage), L909-917 (confirmAction)

### Current Code
```typescript
for (const line of lines) {
  if (line.startsWith('data: ')) {
    try {
      const data = JSON.parse(line.slice(6)) as StreamEvent;
      handleEvent(data);
    } catch (err) {
      // Ignore parse errors for partial data
    }
  }
}
```

### Problem
JSON parse errors are caught and silently ignored. A malformed or multi-line `data:` event is dropped without `onError` firing. The user sees nothing wrong but content may be missing.

The SSE spec allows multi-line data via consecutive `data:` lines, which this parser doesn't handle — it would try to parse each line independently and fail.

### Recommended Fix
Log parse failures and surface a warning if consecutive errors exceed a threshold:

```typescript
let parseErrorCount = 0;

for (const line of lines) {
  if (line.startsWith('data: ')) {
    try {
      const data = JSON.parse(line.slice(6)) as StreamEvent;
      handleEvent(data);
      parseErrorCount = 0;
    } catch (err) {
      parseErrorCount++;
      console.warn('SSE parse error:', line, err);
      if (parseErrorCount > 5) {
        options.onError?.('Stream corruption detected — some content may be missing');
      }
    }
  }
}
```

---

## B7. Queued Auto-Send Race Condition

**Priority:** P3
**Effort:** Small
**Impact:** Low — requires rapid double-action to trigger

### Location
**File:** `AgentChat.tsx` L451-480

### Problem
The queued auto-send uses a 100ms `setTimeout` that calls `handleModelCommand` and `foldLiveTurn`. `foldLiveTurn` is safe via ref, but `handleSend` does not await the fold. A second fast action (e.g., the user manually sending while the queue is processing) can race the state machine.

### Recommended Fix
Use a ref guard to prevent concurrent send operations, or await `foldLiveTurn` before calling `sendMessage`.

---

## B8. Image Attachments Not Size-Limited

**Priority:** P3
**Effort:** Trivial
**Impact:** Low — safety, not correctness

### Location
**File:** `AgentChat.tsx` L489-507

### Problem
`processImageFile` checks that the file is an image (`file.type.startsWith('image/')`) but does not check the file size. A pasted/dropped 20MB PNG will be base64-encoded and sent, which can:
- Freeze the UI during base64 encoding
- Exceed backend payload limits
- Consume excessive memory

### Recommended Fix
```typescript
const MAX_IMAGE_SIZE = 5 * 1024 * 1024; // 5MB

const processImageFile = (file: File): Promise<AttachedImage> => {
  return new Promise((resolve, reject) => {
    if (!file.type.startsWith('image/')) {
      reject(new Error('Not an image file'));
      return;
    }
    if (file.size > MAX_IMAGE_SIZE) {
      reject(new Error(`Image too large (${(file.size / 1024 / 1024).toFixed(1)}MB). Maximum is 5MB.`));
      return;
    }
    // ... existing logic ...
  });
};
```
