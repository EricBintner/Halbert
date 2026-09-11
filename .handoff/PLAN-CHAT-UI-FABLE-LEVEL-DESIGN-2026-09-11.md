# FABLE-LEVEL DESIGN: Chat UI Modernization & Stacked Terminal

**Date**: 2026-09-11
**Status**: **Phase 2 backend BUILT and committed (`fbd725e9`)** — the structured-field reasoning feed, `(kind, text)` stream contract, and `StreamEvent.thinking_complete` are live. Remaining: the Phase 2 *frontend* borderless ThinkingPanel redesign (§2.6), Phase 4 (§3, **gated on founder confirmation of the §3.1 detached-spawn split**), and the frontend-only Phases 1/3/5.
**Supersedes**: `PLAN-CHAT-UI-REFINED-2026-09-11.md` (the "refined" plan) — this document is the *design* for the two phases that plan deferred, plus the corrections that plan's own grounding missed.
**Audience**: the owner AI that will build the rest. Read this before touching `agent.py`, `events.py`, `state_machine.py`, or `terminal_bridge.py`.

> **What's already done (do not rebuild):** `agent.py:_stream_turn` now reads `delta.reasoning_content` / `message.thinking` / `thinking_delta` and yields `('thinking'|'response', text)`; `state_machine.py` routes them to `StreamEvent.thinking` / `response_chunk` and emits `thinking_complete(duration_ms)`; `events.py` has the `thinking_complete` factory; `states.py` `StateContext` has `thinking_chunks` + `thinking_started_at`. Peer/non-streaming paths still yield bare strings (state machine treats non-tuples as response — back-compat preserved). Committed `fbd725e9`; 30 streaming tests + 42 state-machine tests pass.

---

## 0. What this document is

The refined plan (`PLAN-CHAT-UI-REFINED-2026-09-11.md`) is correct on Phases 1, 3, and 5 — those are frontend-only and ready. It correctly deferred Phase 2 (thinking) and Phase 4 (background processes) as "needs design." This document is that design, written out so the builder does not have to re-derive it.

It also records **four grounding findings** and **one correction to a first-pass error of my own** (§1.1 — a claim I made from grep's display-mangled output and then retracted after reading the exact bytes).

---

## 1. Grounding verdict — what I verified, and what the refined plan got wrong

I read every file the plan cites and traced the full streaming chain. The refined plan's twelve corrections are **all accurate** — I confirmed each one. The second pass then overturned my own largest first-pass claim:

### 1.1 (RETRACTED — my first-pass error) The thinking filter's skip arithmetic is actually correct

My first pass claimed an "off-by-N live bug": that the filter skips 7 chars for a 9-char ` thinking` tag, leaking `e` into the answer. **That is wrong, and I retract it.** It came from reading grep output, where the terminal renders the `<`/`>` of the tag in a way that dropped the angle brackets from what I assumed the string was.

Reading the exact bytes (via `python repr()` of the source lines, `agent.py:1469-1489`):

```python
think_start = buffer.find("<think>")       # "<think>" is 7 chars
buffer = buffer[think_start + 7:]           # skips 7 — EXACTLY the tag length. Correct.
...
think_end = buffer.find("</think>")         # "</think>" is 8 chars
buffer = buffer[think_end + 8:]             # skips 8 — EXACTLY the tag length. Correct.
```

`len("<think>") == 7`, `len("</think>") == 8`, and the skips are `+7` and `+8`. **The arithmetic is exactly right; there is no off-by-N leak.** The filter is not a correctness bug.

**Lesson recorded, per the repo's dogfood convention:** grep's human-readable output is not a safe source for byte-exact string claims about angle-bracket content; read the raw bytes before calling something a bug. I wrote a wrong "live bug" into a design document that would have sent the builder chasing a non-defect.

What *is* true about the thinking filter — and these stand:

- It is **fragile, not wrong**: hardcoded to `<think>`/`</think>` only, so `<thinking>`, `<reasoning>`, and implicit-thinking-mode models are not handled. `StreamingReasoningParser` covers those.
- It is the **wrong primary path for the structured-field case** (§1.4): the reasoning is already available as `reasoning_content`/`message.thinking`, which this filter ignores entirely.
- It is the **wrong destination**: thinking is *discarded* (dropped), never surfaced. That is the real gap Phase 2 closes.

### 1.2 The refined plan's Phase 2 "two channels" framing is right, but it under-specifies the fix

The plan says thinking must go through the SSE event bus, not the text generator. Correct. But it stops at "Fable needs to decide." This document decides (section 2). The key fact the plan did not state: **`StreamEvent.thinking` is already emitted today** — not for model reasoning, but for two unrelated things:

- `state_machine.py:4450` — a guest-persona "will not remember this turn" notice.
- `state_machine.py:4500` — the Haloysius cognition tick's `thought`.

So the `thinking` event type is already on the wire and already rendered by the frontend. Phase 2 is not "add a new event type" — it is "route *model reasoning* through the same event type, and add a completion signal with duration." That is a smaller change than the plan implies.

### 1.3 (CORRECTED) The emoji finding stands, but not for the reason I gave — the plan's regex actually fails its own geometric glyphs

My first pass said `■` (U+25A0) is "below `\u{2600}`, so it passes" and flagged `▲`/`▼` as the problem. That had the range membership backwards. Correct arithmetic: `0x25A0 < 0x25B2 < 0x25BC < 0x2600`. So `■`, `▲`, `▼` are **all below `\u{2600}`** — the plan's regex range `\u{2600}-\u{27BF}` matches **none** of them. The regex therefore does **not** flag the geometric shapes Halbert legitimately uses (`■`/`●`/`▲`/`▼`/`▾`/`▸`), which is what the plan *wanted* ("geometric shapes should pass") — but it does so by accident of range arithmetic, not by the plan's stated intent. Meanwhile:

- `✓` (U+2713, "copied") **is inside** `\u{2600}-\u{27BF}` → the regex flags it. The plan purges `📌`/`📍`/`⏹` but leaves `✓` (and `⧉`, U+29C9) in `TerminalTile.tsx`, so its own test would go **red** on the glyph it kept.
- `⧉` (U+29C9, "copy") is outside both ranges → the regex misses it entirely, though it is a pictographic glyph the no-emoji rule covers.

Net: the plan's purge list and its test regex disagree in both directions — the regex misses a glyph it should catch (`⧉`) and flags a glyph the purge keeps (`✓`). Section 4 reconciles the purge and replaces the regex with a per-glyph assertion.

### 1.4 (OSS-GROUNDED, DECISIVE) The real fix is a structured field, not tag-parsing

The refined plan's Phase 2 deferral says "replace the hand-rolled filter with `StreamingReasoningParser`." That is **half the fix, and the wrong half to lead with.** The OSS reference implementations — which this repo exists to lift from — do not parse ` thinking`/` response` tags out of text. They read a **structured reasoning field** off the stream delta.

**Hermes-agent** (`/Volumes/Thunderbolt/AI/OSS/hermes-agent`) is the reference. Its stream loop reads reasoning from the delta's own field, never from the text:

- `agent/chat_completion_helpers.py:2806` — `reasoning_text = getattr(delta, "reasoning_content", None) or getattr(delta, "reasoning", None)` (OpenAI-compatible wire).
- `agent/chat_completion_helpers.py:3017` — `elif delta_type == "thinking_delta" and getattr(delta, "thinking", ""): self._emit_reasoning(delta.thinking)` (Anthropic wire).
- `agent/chat_completion_helpers.py:479` — the token counter reads `delta` fields `"content", "reasoning_content", "reasoning"` as three *separate* fields.
- `agent/message_sanitization.py:410-535` — a whole `reasoning_content` policy layer exists because DeepSeek/Kimi **require** `reasoning_content` echo-back on assistant turns; the field is first-class, not a text artifact.

Hermes *does* still regex ` thinking(.*?) response` — but only as a **storage-boundary strip** (`chat_completion_helpers.py:1419, 1436, 2133`), a defensive cleanup for tags that leaked into `content`, never as the primary extraction path.

**Halbert's `_stream_turn` drops the structured field entirely.** Verified at `dashboard/routes/agent.py`:

- OpenAI-compatible wire (`agent.py:1420-1424`): `content = delta.get("content", "")` — **`delta.reasoning_content` is never read.**
- Ollama wire (`agent.py:1440-1444`): `content = data.get("message", {}).get("content", "")` — **`message.thinking` is never read.**

So for a DeepSeek reasoning model, the reasoning arrives in `reasoning_content` (OpenAI) or `message.thinking` (Ollama), Halbert reads neither, and the ` thinking`/` response` tag filter is operating on `content` that never contained the tags in the first place — it is **dead code for the structured-field case**.

**The correct fix is two-part, and the structured field is the primary path:**

1. **Read the structured field** in `_stream_turn` and surface it as thinking (the hermes pattern). This is the real fix — it is what the providers actually send, it is what the reference implementation does, and it replaces the fragile tag-scan for the common case.
2. **Keep tag-stripping as a fallback** for models that emit ` thinking`/` response` inside `content` (the R1-via-relay case), but replace the fragile hand-rolled loop with `StreamingReasoningParser` (which handles the tag variants and the implicit-thinking-mode case). Note: the hand-rolled loop is fragile but *not* buggy (§1.1 retraction); the reason to replace it is robustness across tag variants, not a correctness leak.

Section 2.2 is rewritten around this.

### 1.5 (second-pass) The frontend thinking pipeline is already fully wired — only the backend feed is missing

The plan's Phase 2 frames the frontend ThinkingPanel redesign as "gated on the backend decision." The second pass shows the frontend half is **already done** and the design statement should say so precisely:

- `useAgentStream.ts:575-576` — a `thinking` SSE event is routed: `appendThinking(event.content)`.
- `useAgentStream.ts:463-468` — `appendThinking` is the `push` of a dedicated `useTokenBuffer`, the same rAF-batched buffer the response uses (`:456-462`). One commit per frame, no O(n²) concat.
- `AgentChat.tsx:1173` — `{thinking && <ThinkingPanel thinking={thinking} isStreaming={isStreaming} />}`.
- `ThinkingPanel.tsx` — exists, renders "Thinking..." while streaming / "Thought Process" when done, collapsible, auto-scrolls.

So the entire `thinking → ThinkingPanel` path is live **today**, fed by the two existing `StreamEvent.thinking` emitters (cognition tick, guest notice). Phase 2's frontend work is therefore **not** "build the panel against existing events" — it is the *borderless redesign* of an already-working panel, plus handling the new `thinking_complete` duration event. The backend feed for model reasoning is the only genuinely new piece. This is a materially smaller change than the plan implies, and it means the ThinkingPanel redesign and the backend feed are **fully decoupled** — either can land first without the other.

---

## 2. Phase 2 — Borderless Streaming Thinking (the fable-level design)

### 2.1 The full chain, as it actually is

The plan's "two channels" is correct but let me name the exact nodes, because the builder needs them:

1. **`state_machine.py:4736`** calls `self.llm.stream(...)` and iterates it via `_model_stream` (`state_machine.py:2245`).
2. **`llm.stream`** is `Agent.stream` at `dashboard/routes/agent.py:1104`, which calls **`_stream_turn`** (`agent.py:1232`).
3. **`_stream_turn`** is where the hand-rolled thinking filter lives (`agent.py:1462-1502`). It `yield`s **raw text strings** — the response text with thinking tags stripped.
4. Back in `state_machine.py:4755-4756`, each yielded string is wrapped: `yield StreamEvent.response_chunk(session_id, chunk)`.
5. `response_chunk` events flow to the frontend through the SSE bus (`agent.py:1950`, `yield event.to_sse()`).

So the text generator (`_stream_turn`) yields **strings**, and the state machine wraps them into **events**. The plan's correction #6 is exactly right: you cannot `yield StreamEvent.thinking(...).to_sse()` from `_stream_turn`, because its caller (`state_machine.py:4755`) would wrap that SSE string in a `response_chunk` and corrupt the stream.

### 2.2 The design decision (Q1): read the structured field first, tag-strip as fallback

The clean fix is to make `_stream_turn` **stop discarding thinking content** and instead **surface it** to its caller, which then emits it as `StreamEvent.thinking`. The primary path is the structured field (hermes pattern); the tag-strip is a fallback.

**Step 1 — read the structured reasoning field in `_stream_turn`.** This is the real fix and the hermes pattern. In the per-wire chunk parsing:

- **OpenAI-compatible** (`agent.py:1420-1424`): read `delta.get("reasoning_content")` (and `delta.get("reasoning")` as a secondary key) alongside `delta.get("content")`. When reasoning is present, surface it as thinking; `content` stays the response.
- **Ollama** (`agent.py:1440-1444`): read `data.get("message", {}).get("thinking")` alongside `content`. Ollama's reasoning models put the thought in `message.thinking`, not in `content`.
- **Anthropic** (`agent.py:1430-1438`): the `content_block_delta` carries `delta.type == "thinking_delta"` with `delta.thinking` (hermes `chat_completion_helpers.py:3017`). Read that; `delta.type == "text_delta"` with `delta.text` is the response.

**Step 2 — keep tag-stripping as a fallback, but harden it.** For models that emit ` thinking`/` response` inside `content` (R1-via-relay), replace the fragile hand-rolled loop (`agent.py:1462-1502`) with `StreamingReasoningParser` (`utils/reasoning.py:138-246`). The parser handles the tag variants and the implicit-thinking-mode case the hand-rolled loop misses. (The hand-rolled loop's skip arithmetic is *correct* — §1.1 retraction — so this is a robustness upgrade, not a bug fix.) This is the *secondary* path, not the primary one.

**Step 3 — change `_stream_turn`'s contract.** It currently yields only response text. It must now yield *both* thinking and response, tagged so the caller can tell them apart. Two options:

- **(a) Yield a small tuple/struct** `(kind, text)` where `kind ∈ {'thinking', 'response'}`. The state machine's `_model_stream` loop then branches: `thinking` → `StreamEvent.thinking`, `response` → `StreamEvent.response_chunk`.
- **(b) Pass a callback** `on_thinking: Callable[[str], None]` into `_stream_turn`, which it invokes for each thinking delta. The state machine supplies a callback that appends to `ctx.thinking_chunks` and yields `StreamEvent.thinking`.

**(a) is recommended.** It keeps `_stream_turn` a pure generator (no callback plumbing through `stream()` → `_stream_turn` → the parser), and it makes the thinking/response split explicit at the one seam where it matters. The `_answer_from_peer` path (`agent.py:1192`) and the non-streaming fallback (`state_machine.py:4760`) both yield response-only, so they need no change — they simply never yield a `thinking` kind.

**Step 4 — the state machine wraps.** In `state_machine.py:4736-4756`, the loop becomes:

```python
async for item in self._model_stream(self.llm.stream(...)):
    kind, text = item if isinstance(item, tuple) else ('response', item)
    if kind == 'thinking':
        self.ctx.thinking_chunks.append(text)
        yield StreamEvent.thinking(self.ctx.session_id, text)
    else:
        self.ctx.response_chunks.append(text)
        yield StreamEvent.response_chunk(self.ctx.session_id, text)
```

The `isinstance` guard keeps the peer/non-streaming paths (which yield bare strings) working unchanged.

**Why the structured field is the primary path, not the tag-strip:** the providers send reasoning in a dedicated field (`reasoning_content` / `message.thinking` / `thinking_delta`), and the reference implementation reads it there. Halbert's current code reads only `content`, so for the structured-field case the tag filter is operating on text that never contained the tags — it is dead code there. Reading the field first is both correct and simpler; the tag-strip is a defensive fallback for the relay case.

### 2.3 The duration signal (Q2, and the plan's correction #7)

The plan's §6.1A wanted `duration_ms` inside the thinking event. The existing factory (`events.py:328-334`) sends only `{"content": content}`. The problem: **duration is only known when thinking ends**, not per-chunk. Two clean options:

- **(a) Add a `thinking_complete` factory** — `StreamEvent.thinking_complete(session_id, duration_ms)`, emitted once when the parser's `finalize()` returns. The frontend's ThinkingPanel transitions from "Thinking…" (streaming) to "Thought for {elapsed}" (on `thinking_complete`). This matches the warp reference pattern (`agent_block_sections.rs:117-136`) exactly: header is "Thinking..." while streaming, transforms to "Thought for {elapsed}" on finish.
- **(b) Overload `thinking` with an optional `duration_ms`** on the final chunk.

**(a) is recommended.** It keeps `thinking` a pure content event and gives the frontend an unambiguous "thinking is over" signal, which is what the auto-collapse needs. The `duration_ms` is computed in the state machine from a `time.monotonic()` stamp taken when the first thinking chunk arrives.

### 2.4 Persistence (Q3) — recommend NOT persisting for v1

The plan's Q3 asks whether to add `thinking_content` / `thinking_duration_ms` columns to SQLite. **Recommendation: do not persist thinking in v1.**

- Thinking is a *streaming affordance*. Its value is "show the user the model is working, then collapse to a one-line summary." Once the turn completes, the collapsed "Thought for {elapsed}" is the only thing worth keeping, and that is a single scalar (duration), not the thinking text.
- The standing directive is **"no migrations"** (`DECISIONS.md`; the plan's own §9). Adding columns means an idempotent `PRAGMA table_info` guard, which is exactly the kind of back-compat shim the repo avoids building unasked.
- The `response_complete` event already carries the committed answer; the thinking text is not part of the durable transcript today and there is no user need that makes it so.

If a later pass wants the collapsed summary to survive reload, the right shape is: store `thinking_duration_ms` on the turn row (one scalar, idempotent column-add), **not** the thinking text. That is a v2 decision, not v1.

### 2.5 TimelineTurn (Q4) — no change for v1

Consequence of 2.4: the `TimelineTurn` type does **not** gain `thinking?` / `thinkingDuration?` fields in v1. The live turn shows the borderless ThinkingPanel; the stored turn shows nothing (or, in v2, a "Thought for {elapsed}" line derived from the stored scalar). The timeline API is untouched.

### 2.6 The frontend half (fully decoupled — see §1.5)

The entire `thinking → ThinkingPanel` path is already live (`useAgentStream.ts:575` routes `thinking` to a dedicated rAF buffer; `AgentChat.tsx:1173` mounts `ThinkingPanel`). So Phase 2's frontend work is the **borderless redesign** of an already-working panel plus handling the new `thinking_complete` duration event — not building the panel from scratch. It can land before, after, or independently of the backend feed, because it is fed by the two existing `StreamEvent.thinking` emitters today and by model reasoning once §2.2 lands.

The redesign, per the warp reference (`agent_block_sections.rs:117-136`) and open-claude-code (`components.mjs:141-146`): header is "Thinking..." while streaming → "Thought for {elapsed}" on `thinking_complete`; defaults to collapsed when finished; borderless, dim/italic, minimal vertical space. This replaces the current bordered `ThinkingPanel` box.

### 2.7 Phase 2 acceptance criteria

1. `_stream_turn` reads the structured reasoning field (`delta.reasoning_content` / `message.thinking` / `thinking_delta`) and surfaces it as thinking — the primary fix.
2. The fragile hand-rolled ` thinking`/` response` filter is replaced by `StreamingReasoningParser` for the tag-in-content (relay) fallback, covering `<thinking>`/`<reasoning>`/implicit-thinking-mode the current filter misses. (Robustness, not a correctness leak — see §1.1 retraction.)
3. `StreamEvent.thinking` fires for model reasoning, not just the cognition tick / guest notice.
4. `StreamEvent.thinking_complete` fires once per turn with a correct `duration_ms`.
5. The borderless ThinkingPanel renders "Thinking..." → "Thought for {elapsed}" and auto-collapses on completion.
6. No SQLite schema change, no `TimelineTurn` change.

---

## 3. Phase 4 — Background Processes & Port Sniffing (the design-pass)

The refined plan correctly identified that `ProcessRegistry`, `StreamEvent.task_started`, and `StreamEvent.port_discovered` do not exist. This section decides the four open questions.

### 3.1 Q1 — spawn mechanism: split by intent (second-pass reconciliation)

The plan's Q1 asks: PTY-backed `TerminalPool` vs a new subprocess path (open-claude-code's `runBackground`). My first-pass answer was "reuse the pool, no new subprocess path." The OSS reference overturns that for the detached case, so the recommendation is **split by intent**:

The `background` flag in `executor.py:893` is currently "accepted but ignored." The decisive fact is the **invariant** in `CLAUDE.md`: "one place each thing is decided." The terminal event vocabulary is already rich — `terminal_spawn`, `terminal_output`, `terminal_complete`, `terminal_block`, `terminal_block_promote`, `terminal_needs_input` (`events.py:531-673`) — and the frontend already renders `TerminalTile` against it. That vocabulary and renderer must stay single.

But a fire-and-forget server is the wrong shape for a PTY. The OSS reference for background execution — open-claude-code's `runBackground` (`bash.mjs:119-146`) — does **not** use a PTY. It spawns a **detached subprocess**: `spawn('bash', ['-c', command], { detached: true, stdio: ['ignore', 'pipe', 'pipe'] })`, stores it in a `Map`, calls `proc.unref()`, and returns `{id, pid, command, status}` immediately. That is the fire-and-forget shape: no PTY, no interactivity, no OSC 133, just a detached process whose stdout/stderr are captured and whose `close` event flips the job to `completed`/`exited(code)`. A background server does not need a PTY, and a PTY keeps a bash session alive that the server does not use.

So the recommendation is:

- **`background=true` (fire-and-forget server)** → a detached subprocess, open-claude-code style, *not* the PTY pool. This is the one place a new subprocess path is justified, because the pool's PTY is the wrong tool for a detached server. The output still flows through the *existing* `terminal_output`/`terminal_complete` event vocabulary (the events are transport-agnostic), so the frontend's `TerminalTile`/task card still render it — only the spawn mechanism differs. `_run_command` returns `{block_id, pid, status: "running"}` immediately, and the model is told "started in the background; completion will be reported."
- **`background=false` (foreground command)** → the PTY pool, as today.

This is a refinement of the plan's Q1 answer: the plan said "reuse the pool, no new subprocess path." The OSS reference says otherwise for the detached case. The invariant ("one place each thing") is preserved because the *event vocabulary* and *frontend rendering* stay single — only the spawn mechanism gains a second, justified branch. **The builder should confirm this split with the founder before committing**, because it is the one place the plan's "no new subprocess path" is wrong.

### 3.2 Q2 — lifecycle: already exists, do not reinvent it

The plan's Q2 asks how a background task reports completion. **It already does.** The chain is:

1. `terminal_block` (spawn) → `terminal_block_promote` (long-running, >2s) → `terminal_output` (streaming) → `terminal_complete` (exit code, duration, output head/tail) → `task_completed` (task card done).

`task_completed` (`events.py:691`) already carries `{task_id, thread_id, title, exit_code, duration, tail}`. The frontend's `useAgentStream.ts:948-959` already consumes `task_completed` and calls `terminalSessionStore.completeBlock`. So the lifecycle is complete; the only missing piece is the **start** signal.

### 3.3 Q3 — port sniffing: in the PTY output path (SessionManager), not terminal_bridge

The plan's Q3 asks where port sniffing lives. **Recommendation: in the PTY output path (the session manager), where raw stdout bytes flow and OSC 133 block markers are already parsed.** `terminal_bridge.py` is the event *bus* (publish/subscribe), not the byte stream — it has no stdout to sniff. The session manager is where `is_interactive` and the OSC 133 detection already live (the plan's correction #12 confirms this), so it is the natural home for a regex over the output stream.

The sniff is a regex over each output chunk for `(localhost|127.0.0.1|0.0.0.0|::1):(\d{1,5})` (and optionally `*:PORT`), deduplicated per block, emitting `port_discovered` when a new port appears. It must be cheap (a single regex pass per chunk) and must not block the output path.

**OSS reference, and a distinction to keep straight.** openclaw has a real port subsystem (`/Volumes/Thunderbolt/AI/OSS/openclaw/src/infra/ports-probe.ts`, `ports-lsof.ts`), but it does a *different* job than this plan needs: `tryListenOnPort` **probes** whether a port is free by binding an ephemeral listener (`net.createServer().listen()`), and `ports-lsof.ts` maps listening ports to processes via `lsof`. That is "is this port available / who owns it," not "what port did this background server just open." The plan's `port_discovered` is the *latter* — it sniffs the server's own stdout for the `Listening on :8765` line. Do not lift openclaw's probe/lsof code for this; it answers a different question. The regex-over-stdout approach is the right one, and it has no direct OSS twin because the reference implementations (open-claude-code, warp) do not surface background-server ports at all — this is a Halbert-specific affordance.

### 3.4 Q4 — the new factory signatures

```python
@classmethod
def task_started(cls, session_id, *, task_id, thread_id, title, block_id) -> 'StreamEvent':
    """A background task began (Plan C). Emitted when background=true returns."""
    return cls(type="task_started", session_id=session_id,
               data={"task_id": task_id, "thread_id": thread_id,
                     "title": title, "block_id": block_id})

@classmethod
def port_discovered(cls, session_id, *, port, host, block_id) -> 'StreamEvent':
    """A listening port was sniffed in a block's output (Plan C)."""
    return cls(type="port_discovered", session_id=session_id,
               data={"port": port, "host": host, "block_id": block_id})
```

`task_started` is the symmetric twin of `task_completed` (`events.py:691`). `port_discovered` carries the port, the host it was sniffed on, and the block that produced it, so the frontend can render a "port 8765 → open" badge that opens a browser tab (staged, never executed — per the standing directive).

### 3.5 Phase 4 acceptance criteria

1. `background=true` returns immediately with a block id; the turn does not block on completion.
2. `StreamEvent.task_started` fires when a background task begins; `task_completed` fires when it ends (already wired).
3. `StreamEvent.port_discovered` fires when a listening port appears in a block's output.
4. The event vocabulary and frontend rendering stay single; the detached-spawn branch (open-claude-code style) is the one justified second spawn path, pending founder confirmation.
5. Port sniffing is a single regex pass per chunk, deduplicated, non-blocking.

---

## 4. Phase 5 correction — the emoji purge is incomplete

The refined plan's Phase 5 replaces `📌`/`📍`/`⏹` with Lucide icons, and its §6.1 correctly notes `■`/`●`/`○`/`▾`/`▸` are geometric shapes, not emoji. But it leaves two pictographic glyphs in `TerminalTile.tsx`:

- **`⧉` (U+29C9)** at `:300` and `:360` — the "copy" glyph. Replace with `<Copy className="h-3.5 w-3.5 text-muted-foreground hover:text-foreground" />` (the plan already imports `Copy` for the pin replacement; reuse it).
- **`✓` (U+2713)** at `:300` — the "copied" confirmation. Replace with a Lucide `Check` icon, or a text label "copied" for the 1.2s confirmation window.

The plan's §7.2.3 test regex `/[\u{1F000}-\u{1FFFF}]|[\u{2600}-\u{27BF}]/u` is inconsistent with this: it would flag `✓` (U+2713, inside `\u{2600}-\u{27BF}`) but not `⧉` (U+29C9, outside both ranges). The correct test is to assert **no pictographic glyphs at all** in the terminal header — either by asserting the specific Lucide SVG elements render, or by a regex that covers the actual glyphs being removed (`[\u{1F000}-\u{1FFFF}\u{2600}-\u{27BF}\u{29C0}-\u{29FF}]`). Do not trust the plan's regex as written.

---

## 5. Build order (what the owner AI should do, in order)

1. **Phase 1** (frontend, low risk) — unboxed canvas + rich markdown. Ready now.
2. **Phase 3** (frontend, low risk) — ephemeral CLI pills. Ready now.
3. **Phase 5** (frontend + minor backend) — resizable dock + the *complete* emoji purge (section 4). Ready now.
4. **Phase 2** (fullstack) — the design in section 2. The backend feed is the genuinely new piece; the frontend redesign is decoupled (§1.5/§2.6) and can land first.
5. **Phase 4** (backend-heavy) — the design in section 3. Highest risk; do it last, after the pool path is proven by Phase 5's terminal work. **Gated on founder confirmation of the §3.1 detached-spawn split.**

Phases 1, 3, 5 are independent and can land in any order. Phase 2 and Phase 4 are independent of each other but both depend on the terminal/streaming architecture being understood, so they should follow the frontend phases.

---

## 6. Standing-directive compliance (re-verified)

| Directive | How this design complies |
|-----------|--------------------------|
| No model names | ThinkingPanel shows elapsed time, never a model name |
| No Sovereign/hostname | UI headers use the onboarding name |
| Staged, never executed | Port badges open browser tabs; code blocks stage into composer |
| Colours from tokens | All new classes use `shared-tokens/tokens.css` tokens; run `check_contrast.py` + `check_literal_colors.py` |
| No emoji | Section 4 completes the purge (`📌`/`📍`/`⏹`/`⧉`/`✓` → Lucide) |
| No migrations | Phase 2 persists nothing; Phase 4 adds no schema |
| One place each thing | Phase 4 keeps the event vocabulary + frontend single; the detached-spawn branch is the one justified second spawn path (founder-confirm) |
| Commit hygiene | No Co-Authored-By, no generation trailers |

---

## 7. Verified OSS reference table (the "goldmine", grounded)

Every file below was read and verified against `/Volumes/Thunderbolt/AI/OSS/` this session. This is the concrete lift map — what to copy, what to *not* copy, and why.

| Pattern | Source (verified) | What to lift | What NOT to lift |
|---------|-------------------|--------------|------------------|
| **Structured reasoning field** | `hermes-agent/agent/chat_completion_helpers.py:2806` (`delta.reasoning_content` / `delta.reasoning`), `:3017` (`delta.thinking` for Anthropic `thinking_delta`), `:479` (three separate fields) | Read `reasoning_content`/`message.thinking`/`thinking_delta` off the stream delta — the primary Phase 2 fix | — |
| **Reasoning tag-strip (fallback)** | `hermes-agent/agent/chat_completion_helpers.py:1419, 1436, 2133` (`re.findall(r' thinking(.*?) response')` at the *storage* boundary) | Keep tag-strip as a *defensive* fallback, not the primary path | Do not make tag-strip the primary extraction (Halbert's current fragility — it misses `<thinking>`/`<reasoning>`/implicit-mode) |
| **Reasoning echo-back policy** | `hermes-agent/agent/message_sanitization.py:410-535` | The fact that DeepSeek/Kimi *require* `reasoning_content` echo-back — a first-class field, not a text artifact | The full policy layer (Halbert has no multi-provider reasoning echo problem yet) |
| **Thinking header → "Thought for {elapsed}"** | `warp/crates/warp_tui/src/agent_block_sections.rs:117-136` | The `finished_duration: Option<Duration>` → header swap, auto-collapse on finish | — |
| **Tool-call state glyphs** | `warp/crates/warp_tui/src/tool_call_labels.rs:66-97` | The `ToolCallDisplayState` enum: glyph + glyph_style per state (`○`/`■`/`●`/`✓`/`×`) | — |
| **Terminal input ownership** | `warp/crates/warp_tui/src/terminal_use.rs:37-54` | `TuiInputTarget` (Pty vs AgentEditor) — who owns input | — |
| **Background detached spawn** | `open-claude-code/v2/src/tools/bash.mjs:119-146` | `spawn(..., {detached:true, stdio:['ignore','pipe','pipe']})` + `Map` store + `proc.unref()` + immediate `{id,pid,command,status}` return | The `Map`-as-registry (Halbert has `TerminalSessionStore`); the PTY pool is the wrong tool for a detached server |
| **Markdown table/blockquote/inline-code** | `open-claude-code/v2/src/ui/markdown.mjs:134-152, 202-206, 56` | GFM table detection, `>` blockquote, backtick inline code | The ANSI rendering (Halbert renders React, not ANSI) |
| **Unboxed assistant message** | `open-claude-code/v2/src/ui/components.mjs:98-104` | `AssistantMessage` renders markdown directly, no box | — |
| **Port probe/lsof** | `openclaw/src/infra/ports-probe.ts`, `ports-lsof.ts` | **Nothing** — this answers "is a port free / who owns it," not "what port did my server open" | Do not lift for `port_discovered`; it is a different question |

**The one-line summary of the whole exercise:** the refined plan's Phase 2 was going to fix the thinking path by *replacing one tag-parser with another*. The OSS reference shows the real fix is to *read the structured field the provider already sends* — which Halbert currently drops — and keep tag-stripping only as a defensive fallback. That is the difference between "fix the symptom" and "fix the root cause," and it is exactly the kind of thing the OSS goldmine exists to catch.

**Second-pass note (honesty, recorded per the dogfood convention):** the first pass of this document asserted a "live off-by-N bug" in the thinking filter's skip arithmetic. Reading the exact bytes showed that claim was wrong — the skips match the tag lengths exactly (`+7` for `<think>`, `+8` for `</think>`). The error came from trusting grep's display-mangled output for angle-bracket content. The structured-field finding above is unaffected and stands on its own; the fragility of the hand-rolled filter (missing `<thinking>`/`<reasoning>`/implicit-mode) is the real reason to replace it, not a leak.
