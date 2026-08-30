# 8. Design & UX Recommendations

These are not bugs — they're design decisions that could improve the user experience. Each is documented with the current state, the industry trend, and a recommendation.

---

## F1. Flat Layout vs. Bubbles

**Priority:** P3 (design decision)
**Effort:** Medium
**Impact:** Low — aesthetic preference

### Current State
User messages are right-aligned colored bubbles. Assistant messages are left-aligned bordered cards. This creates visual asymmetry.

### Industry Trend
ChatGPT, Claude, and MUI X Chat all use a flat layout — no bubbles, just tonal background shifts and left-edge status markers. This matches the "continuous page" aesthetic.

**Source:** [MUI X Chat — Look and Feel](https://mui.com/x/react-chat/customization/look-and-feel/) — "Flat/compact: no bubbles, stacked messages with inline sender info."

### Recommendation
This is a design call, not a bug. The current bubble layout works, but a flat layout would be more consistent with the Olivetti typewriter aesthetic — a clean, continuous dark column of prose. If pursued:
- Remove the colored bubble backgrounds
- Use subtle tonal shifts (`bg-zinc-900` vs `bg-zinc-950`) to separate turns
- Add a left-edge status marker (colored bar) for each turn
- Keep the sender label inline at the top of each turn

---

## F2. No "Copy Response" Button

**Priority:** P2
**Effort:** Small
**Impact:** Medium — convenience feature expected by users

### Current State
Code blocks have a Copy button, but prose responses do not. There's no way to copy a full assistant response without selecting all the text manually.

### Industry Standard
Every major AI chat (ChatGPT, Claude, Cursor) has a copy button on each response, usually in a hover-revealed action bar below the response.

### Recommendation
Add a copy action to the assistant message area:

```typescript
import { Check, Copy } from 'lucide-react';

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  return (
    <button
      type="button"
      aria-label="Copy response"
      onClick={() => {
        navigator.clipboard.writeText(text);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      }}
      className="p-1 text-muted-foreground hover:text-foreground rounded transition-colors"
    >
      {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
    </button>
  );
}
```

Place it in a hover-revealed action bar below the assistant response, alongside future actions (regenerate, thumbs up/down).

---

## F3. No Regenerate / Edit / Branch

**Priority:** P3 (defer — requires backend support)
**Effort:** Large
**Impact:** Medium — power user feature

### Current State
No way to regenerate a response, edit a prior user message, or branch a conversation.

### Industry Standard
ChatGPT and Claude both support:
- **Edit user message** — modifies the message and regenerates from that point
- **Regenerate** — re-runs the assistant turn with the same input
- **Branch** — creates a new conversation branch from a specific turn

### Recommendation
Defer. These features require backend support for turn branching and versioning. The current timeline is append-only with redaction, not branching. Plan this as part of the strategic "typed message parts" architecture work.

---

## F4. No Suggested Prompts in Empty State

**Priority:** P3
**Effort:** Small
**Impact:** Low — onboarding improvement

### Current State
The empty state (`HostGreeting`) shows a greeting but no tappable suggested prompts.

### Industry Standard
NN/g and Google Conversation Design both recommend showing 3-4 suggested prompt chips to demonstrate capability.

**Sources:**
- [NN/g — 10 Guidelines for Designing AI Chatbots](https://www.nngroup.com/articles/ai-chatbots-design-guidelines/) — "Show capability upfront, offer suggested questions as buttons."
- [Google — Conversation Design](https://developers.google.com/assistant/conversation-design/learn-about-conversation)

### Recommendation
Add clickable prompt chips to `HostGreeting`:

```typescript
const SUGGESTED_PROMPTS = [
  "What can you help me with?",
  "Search my notes for ...",
  "Run a shell command",
  "Read a file and summarize it",
];

<div className="flex flex-wrap gap-2 mt-4">
  {SUGGESTED_PROMPTS.map(prompt => (
    <button
      key={prompt}
      onClick={() => onPromptClick(prompt)}
      className="px-3 py-1.5 text-xs rounded-full border border-border bg-muted hover:bg-muted/80 text-foreground transition-colors"
    >
      {prompt}
    </button>
  ))}
</div>
```

---

## F5. No Image Size Limit

**Priority:** P3
**Effort:** Trivial
**Impact:** Low — safety

### Current State
`processImageFile` checks that the file is an image but does not check the file size. A 20MB PNG will be base64-encoded and sent, potentially freezing the UI.

### Recommendation
See B8 in [Bugs & Correctness Issues](./04-bugs.md) for the fix.

---

## F6. No Line Length Cap on Wide Screens

**Priority:** P3
**Effort:** Trivial
**Impact:** Low — readability

### Current State
The chat column is `flex-1` with no `max-width`. On a wide screen, the line length can exceed 100 characters, which is uncomfortable for reading.

### Industry Standard
Smashing Magazine recommends 40-80 characters per line for comfortable reading. ChatGPT and Claude both cap message width.

**Source:** [Smashing Magazine — 8 Simple Typography Tips](https://www.smashingmagazine.com/2009/04/8-simple-ways-to-improve-typography-in-your-designs/)

### Recommendation
Add a `max-width` to the message content:
```typescript
<div className="max-w-3xl mx-auto w-full">
  {/* messages */}
</div>
```

Or use `max-w-[75ch]` for a character-based measure.

---

## F7. No "Jump to Latest" Floating Button

**Priority:** P1 (tied to B1)
**Effort:** Small
**Impact:** Medium — scroll UX

### Current State
There's a "Back to latest" control when `anchored` is true (L666-677), but this only applies when the user has navigated to an older turn via a thread chip. There's no floating button when the user has simply scrolled up during streaming.

### Recommendation
See B1 in [Bugs & Correctness Issues](./04-bugs.md) for the fix. The floating "Jump to latest" button should appear whenever the user is not at the bottom, not just when `anchored`.

---

## F8. No Keyboard Shortcut to Focus Composer

**Priority:** P3
**Effort:** Trivial
**Impact:** Low — power user convenience

### Current State
There's no global keyboard shortcut to focus the composer. The user must click the textarea.

### Industry Standard
ChatGPT uses `/` to focus the composer. Cursor uses `Cmd+K` for inline chat.

### Recommendation
Add a global key listener in `HostShell`:
```typescript
useEffect(() => {
  const handler = (e: KeyboardEvent) => {
    if (e.key === '/' && document.activeElement?.tagName !== 'TEXTAREA' && document.activeElement?.tagName !== 'INPUT') {
      e.preventDefault();
      // Focus the composer
      window.dispatchEvent(new CustomEvent('halbert:focus-composer'));
    }
  };
  window.addEventListener('keydown', handler);
  return () => window.removeEventListener('keydown', handler);
}, []);
```

---

## F9. No Document Title Update for Active Thread

**Priority:** P3
**Effort:** Trivial
**Impact:** Low — browser tab identification

### Current State
The document title doesn't update when switching threads. On a desktop app (Tauri), this affects the window title.

### Recommendation
Update `document.title` when the active thread changes:
```typescript
useEffect(() => {
  if (threadName) {
    document.title = `${threadName} — Halbert`;
  } else {
    document.title = 'Halbert';
  }
}, [threadName]);
```

---

## F10. No Collapsible "Read More" for Long Responses

**Priority:** P3
**Effort:** Medium
**Impact:** Low — readability of long responses

### Current State
Long assistant responses are rendered in full, which can create walls of text.

### Industry Standard
NN/g recommends putting the answer first, then providing detail on demand via collapsible sections or "Read more."

**Source:** [NN/g — Less Chat, More Answer](https://www.nngroup.com/articles/less-chat-more-answer/)

### Recommendation
This is primarily a backend/prompt concern (the model should be instructed to be concise), but the UI can support it by rendering `<details>`/`<summary>` elements for long sections once full markdown rendering is implemented (see D3).
