# STRATEGY: CLI in the conversation — quiet when fast, present when working

**Date**: 2026-09-04
**Follows**: `.handoff/REVIEW-CONFIG-CONTINUITY-2026-09-04.md` (commit `cc8094f9`)
**Spec of record**: `.handoff/plan-b-exec/plan-b-contracts.md` §7, §10, §12, §13
**Question asked**: lift what we can from open-claude-code for how the UI handles CLI
mid-conversation — fast commands should stay quiet, running commands should persist;
and revisit the founder's proposal that persisted CLI panels scroll up with the
conversation and pop out into a side list of active terminals.

---

## 1. Headline

**The founder's proposal is already built.** Terminals flow inline in the
conversation, dock to the right column when scrolled out of view, leave a clickable
tether chip behind, and list in a right-column accordion. That is
`InlineTerminals` + `useIntersectionDock` + `TetherChip` + `TerminalAccordionDock`,
all live and mounted today.

**The quiet/persistent distinction is fully specified and fully written — and
completely unwired.** `plan-b-contracts.md` §13 specifies exactly the behaviour
described in the request:

> - Short block (completed < 2 s): one-line result (`$ smbstatus · exit 1 · 0.3 s`,
>   expandable to `<pre>` with `output_head/tail`).
> - Live + long-running (> 2 s): live xterm while it is the session's current open block.
> - Frozen once complete: `<pre>` from `output_head/tail` (no xterm, no socket).

`ToolExecutionCard.tsx` implements all three branches. **None of them can ever
render**, because every branch is gated on a `blockId` prop that no caller passes.

**open-claude-code cannot teach us this.** It has no fast/slow distinction, no
persistent panel, and no live terminal at all. The behaviour described in the
request is Claude Code proper, not this reimplementation. There is exactly one idea
worth lifting, and it is architectural rather than visual (§3).

So this is not a design task. It is a **wiring task with five specific
disconnections**, plus one genuinely new rule (§6.2) the spec leaves implicit.

---

## 2. What open-claude-code actually does

Checked line by line at `/Volumes/Thunderbolt/AI/OSS/open-claude-code/v2/src`.

### 2.1 Progress is one line on stderr, always

```js
// ui/repl.mjs:114-116
case 'tool_progress':
    process.stderr.write(`${renderToolProgress(event.tool, event.status || 'running')}\n`);
    break;
```

```js
// ui/ink-app.mjs:144-147
export function renderToolProgress(toolName, status) {
    const icon = status === 'running' ? c('yellow', '>>') : c('green', '>>');
    return `${icon} ${c('yellow', toolName)} ${c('dim', status)}`;
}
```

`>> Bash running`. The **tool name**, never the command. No duration, no exit code,
no threshold, no grouping. A 200 ms command and a 20 minute command print the
identical line.

### 2.2 Results are hidden by default — via an env var, not a heuristic

```js
// ui/repl.mjs:117-123
case 'result':
    if (process.env.SHOW_TOOL_RESULTS) {
        const display = String(event.result).slice(0, 300);
        console.log(`\x1b[36m[${event.tool}]\x1b[0m ${display}`);
    }
    break;
```

This is the closest thing in the repo to "hides noisy commands", and it is a blanket
switch: **every** tool result is suppressed unless `SHOW_TOOL_RESULTS` is set.
`thinking` is gated the same way behind `SHOW_THINKING`. There is no notion of a
command being fast, slow, interesting or boring.

### 2.3 The Ink UI is one line per tool call, forever

```js
// ui/components.mjs:114-136  (ToolMessage)
h(Text, { color: 'yellow', key: 'label' }, '[', name, '] '),
// running → spinner + "running..."
// done    → truncate(String(result), 200)
// error   → truncate(String(result), 200)
```

No card, no collapse, no persistence, no promotion. A long-running command is a
spinner that never becomes anything else.

### 2.4 The result/progress correlation is a bug we must not copy

```js
// ui/app.mjs:152-156
const idx = prev.findLastIndex(
    m => m.role === 'tool' && m.toolName === event.tool && m.toolStatus === 'running'
);
```

A completed result is matched back to its running card **by tool name**. Two
concurrent `Read` calls resolve into the wrong slot. Halbert already keys on
`executionId` (`AgentChat.tsx:1132`, `Timeline.tsx:406-407`) and must keep doing so —
grouping inspection calls (review F13) is not a licence to match by name.

### 2.5 Verdict on the OSS repo for this question

| Capability the request describes | open-claude-code | Halbert |
|---|---|---|
| Hide fast/noisy commands | ✗ (blanket env flag) | specified, written, unwired |
| Persist a running command | ✗ (spinner only) | specified, written, unwired |
| Live terminal in the conversation | ✗ | **built and live** |
| Dock on scroll + tether chip | ✗ | **built and live** |
| Side list of active terminals | ✗ | **built and live** |
| Output cap with a visible marker | ✓ 1 MB, `[output truncated at 1MB]` | head/tail, no visible marker |
| Correlate result → running card | by tool name (broken) | by `executionId` (correct) |

Halbert is ahead on six of seven rows. The repo is a useful negative control, not a
model.

---

## 3. The one idea worth lifting

**Two output streams with different lifetimes.**

`repl.mjs` writes progress to **stderr** and transcript content to **stdout**. In a
terminal those have genuinely different lifetimes: stderr scrolls past and is gone;
stdout is the record you scroll back through. The separation is not cosmetic — it
encodes *"this line is a status, not a fact about the conversation"*.

Halbert currently renders both in one layer. `ToolExecutionCard` is a transcript
element, so a 200 ms `ls` deposits a permanent bordered row in the conversation,
which is precisely the noise being complained about.

**The lift**: give Halbert the same two lifetimes.

- **Status layer (ephemeral)** — a single-line strip near the composer showing what
  is happening *right now*: `⟳ Reading /etc/fstab`, `⟳ 3 files`, `⟳ smbstatus 0.4s`.
  It is replaced continuously and leaves nothing behind.
- **Transcript layer (persistent)** — only what is worth having a record of: commands
  that ran long enough to matter, commands that failed, commands that changed
  something, and grouped summaries of everything else.

This is what makes "hide fast commands" *safe*: nothing is hidden while it is
happening — the status strip shows it — it simply does not earn a permanent row
afterwards. The user can always see what Halbert is doing; they just are not made to
scroll past it forever.

Halbert already has the components for the status layer: `ThinkingPanel`,
`ScanBlock`, `StatusLight`, and the a11y live regions in `AgentChat`. The strip is a
new composition of existing pieces, not new machinery.

---

## 4. Build-state audit

Everything below was verified against the tree at `cc8094f9`.

| Capability | Spec | Written | Wired | Evidence |
|---|---|---|---|---|
| Inline live terminal in the stream | §13 | ✓ | ✓ | `InlineTerminals.tsx`, mounted at `AgentChat.tsx:1137`, `Timeline.tsx:149` |
| Dock on scroll-out | §13 | ✓ | ✓ | `useIntersectionDock.ts`, 25% threshold, one-way by design |
| Tether chip marking the origin | §13 | ✓ | ✓ | `TetherChip.tsx`, `data-terminal-origin` stamped by `InlineTerminals` |
| Right-column list of terminals | §12 | ✓ | ✓ | `TerminalAccordionDock.tsx` via `ContextStage.tsx:73` ← `HostShell.tsx:106` |
| Static chip for terminals the page lost | — | ✓ | ✓ | `StaticTerminalChip.tsx` |
| Live xterm cap of 3 | §12 | ✓ | ✓ | `useTerminalSessions.ts:92` `MAX_VISIBLE = 3` |
| Mobile bottom sheet | §15 | ✓ | ✓ | `ContextStage.tsx` `md:hidden` branch |
| StatusLight | §11 | ✓ | ✓ | `StatusLight.tsx`, used in the card header |
| Token fixes on TerminalTile | §16 | ✓ | ✓ | `bg-canvas-subtle` at `:284`/`:318`, `status-telemetry` at `:335`/`:339` |
| `terminal_spawn` carries `block_id`/`owner` | §10 | ✓ | ✓ | `events.py:498-499` |
| `terminal_block_ids` storage | §1 | ✓ | ✓ | `conversation_sqlite.py:62`, `threads.py:393-411` |
| **Short-block one-liner (< 2 s)** | §13 | ✓ | **✗** | `ToolExecutionCard.tsx:71`, `:123-129` — gated on `blockId` |
| **Live xterm inside the card (> 2 s)** | §13 | ✓ | **✗** | `ToolExecutionCard.tsx:74-80`, `:146-152` — gated on `blockId` |
| **Frozen block output on completion** | §13 | ✓ | **✗** | `ToolExecutionCard.tsx:154-163` — gated on `blockId` |
| **`terminal_block` / `_promote` events** | §7, §10 | ✓ | **✗** | `events.py:568` factory is never called |
| **The 2 s promotion timer** | §7 | **✗** | **✗** | no timer task in `agent_pool.py`; only `started_monotonic` for duration |
| **Pool path in production** | §7 | ✓ | **✗** | `set_terminal_pool_enabled(True)` appears only in `tests/test_terminal_e2e.py:123` |
| **Tasks column** | §12 | ✓ | **✗** | `TasksColumn.tsx` is never imported outside its own test |
| Inspection-call grouping | — | ✗ | ✗ | review F13 |
| Status strip (ephemeral layer) | — | ✗ | ✗ | §3 above |

---

## 5. The disconnections

### D1 — No caller passes `blockId`, so every block branch is dead

```tsx
// AgentChat.tsx:1132
<ToolExecutionCard key={exec.executionId} execution={exec} />

// Timeline.tsx:405-408
<ToolExecutionCard
  key={block.executionId ?? `${turn.turnId}-block-${i}`}
  execution={executionFromBlock(block, `${turn.turnId}-block-${i}`)}
/>
```

Neither passes `blockId`, `blockOutput`, `blockExitCode`, `blockDuration`,
`outputHead` or `outputTail`. Inside the component:

```tsx
// ToolExecutionCard.tsx:68
const isCommandBlock = execution.tool === 'run_command' && blockId;
```

`isCommandBlock` is therefore **always false in production**. Consequences, all of
them silent:

- The `$ <cmd> · exit N` short-block line never renders (`:123-129`).
- The exit/duration subheader never renders; it falls back to `config.label`
  (`"exit 0"` / `"error"`) (`:107-112`).
- The frozen block `<pre>` never renders (`:154-163`).
- The embedded live xterm never renders (`:146-152`).
- The raw `Result` `<pre>` is never suppressed, because `suppressResult` depends on
  the same gate (`:69`).

Every one of these is a written, reviewed, tested feature that no user has ever seen.

### D2 — The pool is disabled in production, so no blocks are produced

```python
# streaming/terminal_bridge.py:136-154
# "This flag is set by the dashboard app or test setup when the pool is
#  explicitly enabled."
_pool_enabled: bool = False
def terminal_pool_wanted() -> bool:
    return _pool_enabled and terminal_stream_wanted()
```

The comment says the dashboard app sets it. The dashboard app does not.
`set_terminal_pool_enabled(True)` is called in exactly one place in the repository:
`halbert_core/tests/test_terminal_e2e.py:123`.

So `executor.py:_run_command` always falls through to the subprocess path
(`:612+`), which publishes `spawn` → `output` → `complete` with **no `block_id`**.
No `terminal_blocks` row is written, no block id reaches the turn, and D1's gate can
never be satisfied even if the props were plumbed.

### D3 — There is no promotion timer, so nothing distinguishes fast from slow

`plan-b-contracts.md` §7:

> **Long-running promotion**: when a block's `started_at` is > 2 s ago and it is still
> open, the backend emits `terminal_block_promote`. This is a timer task in the pool
> or a check in the reader loop.

Neither exists. `agent_pool.run_block` takes `started_monotonic` at `:106` and uses
it only to compute `duration` at `:195`. `StreamEvent.terminal_block(..., promote=True)`
(`events.py:568-595`) has no caller. The frontend is ready and waiting —
`useAgentStream.ts:311-323` handles both `terminal_block` and
`terminal_block_promote`, and `useTerminalSessions.ts:223-230` sets `isTaskCard` —
for events that are never sent.

**This is the direct cause of the noise being reported.** The subprocess path
publishes `spawn` the instant the command starts, so *every* `run_command` — a 200 ms
`ls` included — immediately mounts a live `TerminalTile` in the conversation and
consumes one of the three live xterm slots. The current behaviour is not "fast
commands are noisy"; it is "**all commands are maximally loud, and nothing ever gets
quieter**".

### D4 — `TasksColumn` replaced the accordion in the spec but not in the app

`TasksColumn.tsx:4` describes itself as *"right-column task list (replaces
TerminalAccordionDock)"*. `ContextStage.tsx:73` still renders
`TerminalAccordionDock`. `TasksColumn` is imported nowhere outside its own test.

The two are not equivalent. The accordion lists **terminal sessions**; the tasks
column lists **tasks** (title, owning thread topic, elapsed, exit code, and a jump
arrow to the timeline turn), with running at the top, finished collapsed below, and
"Your shell" pinned at the bottom. The tasks column is the surface that makes the
promotion in D3 meaningful — a promoted long-running command needs somewhere to *be*.

Shipping the promotion without the tasks column would promote things into a list that
does not know what a task is.


### D5 — The tests cannot catch D1, because they supply the props themselves

`ToolExecutionCard.test.tsx` is titled *"Tests for ToolExecutionCard block rendering
(Plan B: B18)"* and every block test passes `blockId="blk-1"` as a literal:

```tsx
render(
  <ToolExecutionCard
    execution={baseExecution}
    blockId="blk-1"
    blockExitCode={0}
    blockDuration={0.3}
  />
);
```

So the suite asserts, correctly and permanently, that the component renders a short
block one-liner when handed a block — while the application hands it none. Every
Plan-B branch is green in CI and unreachable in the product.

This is the fifth disconnection: the safety net is disconnected too. It is the same
defect class as commit `14f55bfc` ("the headline test for the one-open-row fix could
not fail"), and it is why D1 survived review.

**The correction is not to delete these tests** — they are correct unit tests of the
component's contract. It is to add one integration test above them that renders
through `AgentChat` or `Timeline` from a stream event, so the wiring itself has a
test that can fail.

---

## 6. The behaviour model

### 6.1 One command, five states

```
                  ┌──────────────────────────────────────────────┐
                  │ 0. STAGED   (approval pending)               │
                  │    transcript: confirmation card             │
                  └────────────────────┬─────────────────────────┘
                                       ▼
   ┌───────────────────────────────────────────────────────────────┐
   │ 1. OPENING  (t < QUIET_MS)                                    │
   │    status strip:  ⟳ $ smbstatus                               │
   │    transcript:    nothing                                     │
   └───────┬───────────────────────────────────────┬───────────────┘
           │ ends before QUIET_MS                  │ still open at QUIET_MS
           ▼                                       ▼
   ┌───────────────────────┐        ┌──────────────────────────────────────┐
   │ 2a. QUIET             │        │ 2b. PROMOTED                         │
   │  exit 0 → grouped pill│        │  transcript: live TerminalTile       │
   │  exit ≠0 → one-liner  │        │  tasks column: running task card     │
   │  transcript: 1 line   │        │  status strip: cleared               │
   └───────────────────────┘        └───────────────┬──────────────────────┘
                                                    ▼
                                    ┌──────────────────────────────────────┐
                                    │ 3. FROZEN (block closed)             │
                                    │  transcript: <pre> head/tail, xterm  │
                                    │              disposed                │
                                    │  tasks column: finished section      │
                                    └──────────────────────────────────────┘
```

Rules that fall out of this and are worth stating explicitly:

- **Nothing is hidden while it runs.** State 1 is always visible in the status strip.
  "Quiet" is a decision about the *record*, never about the *present*.
- **Failure is never quiet.** A non-zero exit promotes to a transcript line
  regardless of duration. A 40 ms command that exits 1 is more interesting than a
  4 s command that exits 0.
- **Promotion is one-way**, like docking. A command that crossed 2 s keeps its
  transcript row after it finishes; it does not retroactively become quiet.
- **Inline wins over the tasks column.** Per §13, the two never both mount an xterm
  for one session; the task card says "live in conversation ⤴".

### 6.2 The rule the spec leaves implicit: what "quiet" leaves behind

§13 defines the short block as a one-line result. It does not say what happens when
there are nine of them in a row, which is the actual complaint.

Proposed, consistent with review F13:

- Consecutive **quiet, successful** commands and consecutive **inspection tools**
  (`read_file`, `list_directory`, `recall_memory`, …) collapse into one pill:
  `⚡ 6 commands · 3 files read — 1.9 s` (click to expand into the individual
  one-liners).
- Any command that **failed**, **was promoted**, or **wrote something**
  (`side_effects = True` on its `BaseTool`) breaks the run and renders on its own.
- A **redacted** block breaks the run and renders as `RedactedToolCard`, never as an
  increment in a count (`Timeline.tsx:104-108` explains why).

Using `side_effects` rather than a hand-maintained tool list means the classification
cannot drift out of sync with the registry — which is the failure mode the review's
F4 caught in the handoff's tier lists.

### 6.3 Thresholds

| Constant | Value | Rationale |
|---|---|---|
| `QUIET_MS` | 2000 | Already the spec's number (§7, §13) and already in the component (`ToolExecutionCard.tsx:71`). Don't invent a second one. |
| `STRIP_MIN_MS` | ~150 | Below this, do not even paint the status strip — a flicker is worse than silence. |
| `MAX_VISIBLE` | 3 | Existing, `useTerminalSessions.ts:92`. Promotion must respect it: a fourth promoted command goes to the tasks column without an xterm. |
| Output drawer | > 6 lines | From the original handoff §5; keep. |

---

## 7. Implementation plan

Ordered by dependency. Each row is independently shippable and independently
verifiable.

### Phase T1 — Turn the pool on and produce blocks *(backend, unblocks everything)*

1. Call `set_terminal_pool_enabled(True)` from the dashboard app's startup, gated on
   the terminal capability (`CAP_TERMINAL`), matching how the config watcher and
   session reaper are gated (`app.py:807`, `:845`).
2. In `executor.py:_run_command`'s pool branch, emit `StreamEvent.terminal_block(...)`
   on block open, with `block_id`, `terminal_session_id`, `command`, `owner`.
3. Fix `insert_terminal_block`'s `"thread_id": None, "turn_id": None`
   (`executor.py:592-593`) — the columns exist and are indexed
   (`conversation_sqlite.py:396`, `:419-421`). This is the same missing join the
   review flagged as F12 for the ledger; fix both from the same context.
4. Keep the subprocess fallback exactly as it is. It is the non-streaming path and
   the pool's failure path.

**Verify**: a `run_command` during a streaming turn writes a `terminal_blocks` row
with a non-null `turn_id`, and the SSE stream carries a `terminal_block` event.

### Phase T2 — The promotion timer *(backend, the fast/slow split)*

1. In `agent_pool.run_block`, start a `asyncio.create_task` that sleeps `QUIET_MS`
   and, if the block is still open, publishes `terminal_block_promote`.
2. Cancel it when the D marker arrives. Cancel it on the timeout/ETX path too — the
   `released` flag discipline at `agent_pool.py:138` exists because every exit
   from that block has to clean up; the timer is one more thing that must.
3. Do not promote on the subprocess fallback: without OSC 133 markers there is no
   block, and a promotion with no block id is a task card that cannot be jumped to.

**Verify**: `sleep 3` promotes, `echo hi` does not, and a killed-on-timeout command
does not leave a stray task.

### Phase T3 — Plumb `blockId` into the card *(frontend, makes T1/T2 visible)*

1. `AgentChat.tsx:1132` — pass `blockId`/`blockOutput`/`blockExitCode`/`blockDuration`
   from the block record the stream now carries.
2. `Timeline.tsx:405-408` — same, from `TimelineToolBlock`. This needs
   `TimelineToolBlock` to carry the block fields; the type is in
   `types/timeline.ts:15-33` and the row already exists in storage.
3. Delete the raw `Arguments` `<pre>` (`ToolExecutionCard.tsx:138-143`) — the review's
   Phase 1, now trivially safe because `suppressResult` starts working at the same
   moment.
4. Add the >6-line output drawer and the copy button.
5. Use `text-status-*` tokens. Not `emerald-400`, not `Badge variant="success"`
   (review F16).

**Verify**: **the existing tests are green against props the application never
supplies.** `ToolExecutionCard.test.tsx` passes `blockId="blk-1"` explicitly in every
block test (`:29-36`, `:41-49`, `:52-60`, and on), so the whole Plan-B block surface
is covered by a suite that can never fail for the reason it exists. This is the same
class of defect as commit `14f55bfc` ("the headline test for the one-open-row fix
could not fail"), at larger scale.

The T3 acceptance gate therefore cannot be the existing unit tests. It has to be a
test that renders through `AgentChat`/`Timeline` with a real stream event, or a
Playwright run against a live backend with the pool on.

### Phase T4 — The status strip *(frontend, the ephemeral layer)*

A one-line region above the composer, driven by the existing stream events. Shows the
current tool/command and elapsed time; empty when idle. Wire it into the existing
a11y live regions rather than adding a new announcement channel
(`AgentChat.liveRegions.test.tsx` covers the current contract).

**Verify**: a 200 ms command paints nothing (below `STRIP_MIN_MS`); a 1 s command
paints and clears with no transcript row; a 3 s command paints, then hands off to the
promoted tile.

### Phase T5 — Grouping *(frontend, §6.2)*

`InspectionGroup` applied at **both** render sites, tiers keyed off `side_effects`,
redaction answered before counting, `executionId` preserved as the key.

### Phase T6 — Mount the tasks column *(frontend, closes D4)*

Replace `TerminalAccordionDock` with `TasksColumn` in `ContextStage.tsx:73`, wire
`onJumpTo` to the timeline's `loadAround(turnId)` — which now works, because T1.3
gives blocks a `turn_id`.

Keep the accordion's one genuinely better behaviour: it does not disappear when empty
(`TerminalAccordionDock.tsx:14-17` — *"an empty dock that says the nervous system is
live is the difference between 'the feature isn't there' and 'nothing is running
right now'"*). That reasoning applies just as much to a tasks column.

### Phase T7 — Output truncation marker *(small, from §2.5)*

`output_head`/`output_tail` already bound what is stored. Render the elision
explicitly — `… 4,812 lines elided …` between head and tail — rather than the current
silent `…` join (`ToolExecutionCard.tsx:83-85`). Borrowed from
`bash.mjs:84-88`'s `[output truncated at 1MB]`.

---

## 8. Sequencing against the review

The review's Phase 0 (read-before-write / digest CAS) and T1.3 both touch
`turn_id` plumbing and both want a `record_*` call site pass. Suggested order:

| # | Work | Source |
|---|---|---|
| 1 | Read-before-write / digest CAS; wire `freshness.decide()` into the write path | review F5 |
| 2 | `turn_id` on ledger rows **and** on `terminal_blocks` (one pass, two stores) | review F12 + T1.3 |
| 3 | T1 — pool on, `terminal_block` events | T1 |
| 4 | T2 — promotion timer | T2 |
| 5 | T3 — plumb `blockId`, strip the args `<pre>`, tokens | T3 + review F16 |
| 6 | T4 — status strip | T4 |
| 7 | T5 — grouping | T5 + review F13 |
| 8 | T6 — tasks column | T6 |
| 9 | Config-dir collapse, backup-store reconciliation | review F8, F9, F10 |
| 10 | Recent-configs route + dock | review F6, F7, F15 |

Items 3–8 are the answer to this request. Items 1–2 are shared prerequisites. Items
9–10 are the original handoff, unblocked.

---

## 9. Risks

- **Turning the pool on changes the production execution path for every command.**
  It runs commands in a PTY-backed bash session with OSC 133 markers instead of
  `create_subprocess_shell`. Behaviour differences to watch: `$SHELL` rc files now
  execute, the cwd is a `cd` prefix inside a subshell rather than a `cwd=` argument,
  and the pool has a session cap (a fourth concurrent command falls back). The
  fallback path exists and is exercised; the risk is that it becomes the silent
  common case again and nobody notices. Log which path each command took.
- **The 3-slot xterm cap becomes visible.** Today every command grabs a slot and
  releases it in milliseconds. After T2, three genuinely long-running commands hold
  all three slots, and the fourth promoted command must degrade gracefully to a task
  card with no live view. That path needs a test.
- **Docking is one-way by deliberate design** (`InlineTerminals.tsx:11-14` — swapping
  a 200 px tile for a 20 px chip moves the layout under the observer). A promoted tile
  appearing mid-scroll can cause the same jitter in the other direction. Promotion
  should reserve its height before mounting the tile.

---

## 10. Open questions

1. **Should a *failed* fast command promote to a live tile, or just a red one-liner?**
   §6.1 proposes a one-liner. A failure the user needs to act on might deserve more.
2. **Does the user's own shell get promoted the same way?** The watched user shell
   (§8 of the contracts) produces blocks too. A user's own 10-second command probably
   should *not* appear as a Halbert task card — or should it, given the founder's
   direction that user shells stay but are watched?
3. **Should the status strip show the command or the intent?** `⟳ $ smbstatus` versus
   `⟳ Checking the Samba shares`. The second is friendlier and matches the steward
   voice; the first is verifiable. Possibly both: intent as the label, command on
   hover.
4. **Is `TerminalAccordionDock` deleted or kept?** T6 replaces it in `ContextStage`.
   If nothing else mounts it, it and its tests become dead code.

---

## 15. Audit of the build (2026-09-04, after commits afba3c22..8cb65c85)

Re-checked every claim against the tree rather than against the commit
messages. Four things were wrong or incomplete and are now fixed; three
remain open and are stated here rather than implied.

### Fixed by the audit

**A1 — `9a8bf231` overclaimed.** It wired `blockId` and stopped, so
`isCommandBlock` became true and nothing else did. Every branch that renders
something needs more than the id:

| branch | also needs | was |
|---|---|---|
| `isShortBlock` (the one-liner) | `blockDuration` + `blockOutput` | unreachable |
| `suppressResult` | `blockOutput` | unreachable |
| frozen `<pre>` | `blockOutput` | unreachable |
| exit/duration label | `blockExitCode` | unreachable |

The completion payload carried only an exit code. `run_block` now publishes
`complete` **after** head/tail are computed and carries `duration`,
`output_head`, `output_tail`. Output must come from the payload and never
from the hosting session's scrollback: a pool session is reused across
blocks, so its buffer holds every command it has ever run. Fixed in
`7c3c3931`.

**A2 — the promotion timer could fire after its block closed.** Cancelling
in the `finally` is not enough: between the D marker and that cancel the pool
decodes, splits and redacts the output, and a timer expiring inside that
window is already scheduled. It now also checks `block_closed` on waking, and
lives in `_promote_after` so the decision is testable without racing a real
PTY — and so a fire-and-forget task nobody awaits cannot raise into asyncio's
"exception was never retrieved" at shutdown. Fixed in `f8281774`.

**A3 — `test_e2e_long_running_promotion` never ran a command.** It built a
`StreamEvent` with `promote=True` and asserted its type, so it passed for the
entire period in which the factory had no caller — while carrying the name of
the one behaviour that was missing. Replaced with a test that runs two
commands through the pool and asserts the slow one publishes exactly one
promotion and the fast one publishes none; verified it fails when the
promotion is disarmed. Fixed in `ec2870de`.

*(The first draft of that replacement was itself a false pass: it rebound
`published = []` between runs while `published.append` stayed bound to the
original list. It "passed" for the wrong reason until the disarm check
contradicted it. Prove-it-can-fail is the only step that catches this.)*

**A4 — a short block printed its output twice.** The host sends
`head` = first 20 lines and `tail` = the whole text when it fits in 4 KiB, so
for any short command the two are the same string; the card joined them
unconditionally and rendered `two shares are up\n…\ntwo shares are up`. The
bug is as old as the component and had never been seen, because nothing
supplied the output it renders. Wiring dead code is what makes its latent
bugs stop being latent. Fixed in `8cb65c85`.

### Still open, verified by grep against the tree

| Gap | Check | Result |
|---|---|---|
| **Historical timeline renders no blocks** | `TimelineToolBlock` fields in `types/timeline.ts` | no `block_id`, no duration, no output — only `terminalBlockIds` at the turn level |
| **Promotion is invisible** | files rendering `isTaskCard` | 0 |
| **Tasks column unmounted** | non-test imports of `TasksColumn` | 0 |
| **No status strip** | references to a status strip | 0 |
| **No inspection grouping** | references to `InspectionGroup` | 0 |

**The historical gap is the one that matters most**, because it makes the
same turn render two different ways. Live, a fast command shows
`$ smbstatus · exit 1 · 0.3s`; after a reload the stored turn has only the
tool-call block (`tool`, `args`, `result`, `exit`, `executionId`) and its
terminal ids render as "terminal · ended" chips. The data exists — the
`terminal_blocks` row holds `exit_code`, `output_head`, `output_tail`,
`started_at`, `ended_at`, and now `turn_id` — but the timeline route never
hydrates it.

Closing it needs a durable join from a stored tool-call block to its terminal
block. The event now carries `execution_id`; the row does not. The same
argument that put `turn_id` on the row applies: `end_turn` is the one moment
both are known, so `ctx` should record `{block_id: execution_id}` pairs and
`_anchor_blocks` should stamp both.

**Promotion having no consumer** means T2 currently has zero user-visible
effect: `terminal_block_promote` sets a flag on a block that nothing reads.
That is D4, and it is the next thing worth building — a promoted command
needs somewhere to be.

---

## 16. Second pass: the two structural gaps closed (3e9a438a, 4a862fee)

### The historical timeline now renders blocks

`terminal_blocks` gained an `execution_id` column, stamped at `end_turn` from
a pairing the drain records (the one place a block id and a tool call id are
both in scope). The timeline route joins on it and fills each `run_command`
block in with the stored exit code, duration and output. A reloaded turn now
renders the way the live one did.

Three rules that fell out and are worth keeping:

- **Join on the id, never the command.** A turn that runs the same command
  twice is ordinary, not an edge case.
- **An unfinished block reports no duration**, not `0.0` — which would read
  as "it finished instantly".
- **Hydration failure is swallowed.** The turns are the page; this is an
  improvement on top of them, and an improvement that fails must not take the
  conversation with it.

Adding the `block_executions` kwarg broke twelve tests through their fake
ThreadManagers, and *how* it broke them was the finding: `_end_turn` swallowed
the `TypeError` as "end_turn failed (non-fatal)", so twelve turns silently
went unpersisted and the only symptom was an empty list. Non-fatal to the
stream, but the turn is gone — the words the user said and the answer they got
written nowhere. That log now names the turn and the thread and says what was
lost.

### Promotion is now visible

`useTasks` derives task cards from the terminal store's promoted blocks;
`ContextStage` mounts `TasksColumn` in place of the accordion.

Two properties had to survive the swap, and one of them was nearly lost:

- The **empty state**. The accordion refused to disappear when empty because
  "Nothing running" and an absent column say different things. Preserved.
- The **shell launcher**. The accordion carried the *only* one on the page.
  `YourShellRegion` renders "No shell session" with no way to start one, so
  wiring that instead would have removed the admin's ability to open a
  terminal at all — silently, as a side effect of a layout change. A
  `ShellLauncher` now fills the column's `yourShell` slot.

Also fixed on the way: `TaskCard`'s jump passed `threadId` to a handler that
scrolls to an element, so it resolved nothing. It carries the block id now,
and `findJumpTarget` tries the inline origin first and `data-terminal-block`
second, so both kinds of id land.

`TerminalAccordionDock` is deleted rather than left orphaned.

### What is left

| Item | State |
|---|---|
| Status strip (the ephemeral layer, §3) | not built |
| Inspection grouping (§6.2, review F13) | not built |
| Output truncation marker (T7) | partial — the elision is honest now, but unlabelled |
| `YourShellRegion` proper (watched toggle, stage-into-shell, a real xterm) | written, still unmounted; its terminal mount point is a div the parent never fills |

The first two are the remaining half of the original request: *quiet when
fast* now has a record-level answer (a finished command collapses to one
line) but not a present-tense one (nothing shows what is happening while a
fast command runs, and nothing groups a run of inspection calls).
