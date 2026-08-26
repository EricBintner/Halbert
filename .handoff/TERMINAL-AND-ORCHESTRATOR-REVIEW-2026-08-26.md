# Terminal sessions and the conversation orchestrator — review

**Date:** 2026-08-26
**Asked:** (1) Did we get terminal sessions inline in the conversation, parking into
a right-panel accordion when scrolled off screen, click-to-expand? (2) Did we build
the meta-level orchestrator that is aware of conversations, delegates, and moves
between conversations like memories? Then: refine the design and build it out,
using the local checkouts of open-claude-code and Warp for insight.

**Method.** Five parallel read-only audits (Halbert terminal code, Halbert
orchestration code, the planning corpus, `/Volumes/Thunderbolt/AI/OSS/open-claude-code`,
`/Volumes/Thunderbolt/AI/OSS/warp`), 316 tool calls, every claim below carries a
`file:line`. The four load-bearing claims were re-verified by hand against source.
The SourcePrep daemon was **not** used: `scripts/staged_knowledge_embed.py --stage 3`
(PID 56552) was pegging ~9 cores the whole time, and the memory rule says never touch
the daemon during a build. Both OSS repos are registered in the daemon
(open-claude-code `4c7c7f1f…`, warp `59d91ed5…`) for later, quieter sessions.
Tests: vitest 18/18, backend bridge 23/23, agent-unit sweep 122/122 — all with
`/Volumes/4TB-BAD/Halbert/.venv`; the miniconda `python` on PATH lacks pytest-asyncio
and fails 19 of them for environment reasons only. `tsc --noEmit` is clean.

Raw per-reader reports: `TERMINAL-AND-ORCHESTRATOR-REVIEW-2026-08-26-APPENDIX.md`.
Second pass (after the founder's continuity direction — how real Claude Code, its docs,
Warp, and Halbert's own dormant modules support one-continuous-chat-with-hidden-threads):
`TERMINAL-AND-ORCHESTRATOR-REVIEW-2026-08-26-APPENDIX-B.md`.

---

## TL;DR

| Question | Answer |
|---|---|
| **Inline terminals + accordion dock** | **Built, for one turn.** The whole pipe is real (executor → `terminal_bridge` → SSE → store → xterm tile → IntersectionObserver dock → TetherChip). The dock is mounted (`ContextStage.tsx:63`, not orphaned by the SidePanel deletion). But tiles exist only inside the *current* turn's assistant block; the next message erases them from the conversation, and a confirmed bug leaves a tile blank whenever it mounts onto output that already arrived. Agent commands are read-only pipe mirrors, not PTYs. |
| **Conversation-aware orchestrator** | **Not built. Verdict: stubs.** No orchestrator, no delegate tool, sub-agent manager has zero production callers, three disconnected conversation stores the agent path writes to none of, and — the largest finding — **the agent receives no conversation history at all**: every message is a brand-new session with `conversation_history=[]`. Halbert's chat currently cannot remember the previous message, let alone move between conversations. |

You were right to be unsure about (2). The handoffs say "done"; the code says "merged but unreachable." Treat every "done" in the sovereign-host handoffs as "committed", not "wired".

---

## Part 1 — Feature A: terminals inline, dock on scroll

### What runs today (verified)

```
tools/executor.py:375   asyncio.create_subprocess_shell(...)           # NOT a PTY
tools/executor.py:382   publish {kind:'spawn', attach:'sse', ...}
streaming/terminal_bridge.py:86   per-agent-session pub/sub (drop-oldest @512)
agents/state_machine.py:955       _run_tool_streaming drains bus → terminal_* SSE
hooks/useAgentStream.ts:177       applyTerminalEvent → terminalSessionStore
components/agent/AgentChat.tsx:697   <InlineTerminals sessionIds=.../>
components/agent/InlineTerminals.tsx:32  useIntersectionDock(threshold .25) → TetherChip
components/shell/ContextStage.tsx:63     <TerminalAccordionDock/> (right column, max-h 55%)
components/agent/TerminalAccordionDock.tsx:157  expand → TerminalTile if store.visible (MAX_VISIBLE=3)
```

`+ New Terminal` is a real PTY (`streaming/pty.py:118 os.openpty`, `:121 os.fork`,
TIOCSWINSZ resize) over a real bidirectional WebSocket (`routes/websocket.py:61`).
That path works. Agent-run commands do not use it.

### Gaps vs. the requirement, ranked

| # | Gap | Severity | Evidence |
|---|---|---|---|
| 1 | **Tiles survive one turn only.** New session id per message, `terminalSessions: []` on init, and only the last user message renders an assistant block. Earlier tiles and chips vanish; dock rows for them keep a ⤴ jump button that silently no-ops. | HIGH | `useAgentStream.ts:523,251`; `AgentChat.tsx:666`; `HostShell.tsx:26-31` |
| 2 | **Blank tile on mount.** `mount()` runs after `terminalFontReady()` resolves (always async) and never writes `session.output`; the output effect ran earlier and bailed on `termRef.current === null`. Any tile mounted onto existing output — short commands, re-expanding a dock row, clicking a chip — stays blank until the next chunk, which for finished sessions never comes. | HIGH | `TerminalTile.tsx:62-133` vs `:138-159`; `lib/xtermTheme.ts:91-93` |
| 3 | **Tiles are not at the tool's position.** One `InlineTerminals` block after all `ToolExecutionCard`s; the card also prints the same output in a `<pre>`, so output shows twice. | MED | `AgentChat.tsx:691-697`; `ToolExecutionCard.tsx:85-92` |
| 4 | **Agent commands are mirrors, not terminals.** No stdin, no sudo prompt, no resize, no terminate. `attach:'ws'` is the designed seam, unbuilt. | MED | `executor.py:375`; `SOVEREIGN-HOST-SHELL-RESULTS:241-256` |
| 5 | **Dock accumulates stale sessions** across turns and conversations; `reset()` clears only the latest session id. | MED | `useAgentStream.ts:719-725` |
| 6 | **Auto-dock race (plausible, not reproduced).** Observer fires on `observe()`; `tool_start` triggers a smooth scroll before the tile mounts, so a tile can dock before anyone sees it; streaming text also pushes tiles off the top and docking is one-way. | MED | `useIntersectionDock.ts:49-66`; `AgentChat.tsx:340-342` |
| 7 | **Two xterms for one session** when the inline tile and an expanded dock row coexist; `MAX_VISIBLE` is enforced only in the dock. | LOW-MED | `InlineTerminals.tsx:55` |
| 8 | User shells: `max_sessions=2`, 60 s idle reaper kills a shell sitting at its prompt; WS reattach never replays the PTY buffer; a second reader starves the first. | MED (user path) | `session_manager.py:42`; `websocket.py:73-83`; `pty.py:176,197` |
| 9 | `confirmAction` SSE reader lacks the partial-line buffer `sendMessage` has → dropped `terminal_output` chunks after a confirmation. | LOW-MED | `useAgentStream.ts:682` vs `:617-619` |
| 10 | Below `md` the whole ContextStage (vitals + dock) is hidden. | LOW | `HostShell.tsx:44` |

Design-vs-code drift worth knowing: the spec says the tether is bidirectional
(scroll back restores the tile); the code is deliberately one-way because the
~20 px chip vs ~200 px tile oscillated under the observer
(`InlineTerminals.tsx:11-14`). The spec says the dock sits "below ContextBar in
SidePanel"; it now sits below HostVitals in ContextStage and ContextBar lives in
the conversation column. Neither doc was updated.

### Unreconciled founder positions the docs carry

- 2026-08-22: "Do not build the user-facing terminal. Terminal is agent-facing only."
  (`FINAL-PLAN-2026-08-22.md:329`)
- 2026-08-24/25: `+ New Shell`, `Ctrl+\`` focus, "Enter executes immediately in an
  inline terminal tile" (`STREAMING-TERMINALS-AND-UI-ORCHESTRATION.md:124,165`)
- 2026-08-26: "Commands are STAGED, never executed" (commit `05c38e3`)

The shipped code follows the middle one for the launcher and the last one for the
composer. This needs one explicit decision (see Part 5).

---

## Part 2 — Feature B: the conversation-aware orchestrator

### What exists, and why none of it runs

| Module | State | Why inert |
|---|---|---|
| `agents/subagent.py` `SubagentManager` | slot/queue bookkeeper; `spawn()` starts no task, no loop, no conversation | never constructed in production; `routes/agent.py:183-196` builds `AgentStateMachine` without it |
| `state_machine.py:542 spawn_subagent` / `:570 await_subagent_completion` | exist; the latter polls every 0.1 s for up to 300 s while the turn is parked | zero callers outside tests; PLANNING never emits it (`:719`) |
| `agents/subagents/storage_auditor.py` | deterministic three-command probe, no LLM | no importer; records a Finding, not the spec'd SomaticBlock |
| LLM tool schema (`tools/executor.py:84-185`) | `run_command, web_search, read_file, write_file, list_directory` | **no delegate / recall / memory tool; no prompt text mentions sub-agents, memory, or past conversations** |
| `agents/conversation.py` JSON store (`~/.halbert/conversations`) | behind `/api/agent/conversations` (list/get/delete only) | nothing ever writes to it — AgentChat's dropdown is permanently "No saved conversations" |
| `routes/conversations.py` JSON store (`~/.config/halbert/conversations`) | legacy `/api/conversations` | UI deleted 2026-08-26; different store from the one above |
| `agents/conversation_sqlite.py` SQLite + FTS5 | best candidate store | constructed only in tests; non-atomic save + FTS MATCH abort flagged in REVIEW-FINDINGS |
| `agents/session_affinity.py` | regex-id → FTS keyword → current-session picker | test-only; picks an id, loads nothing |
| `model/context_handoff.py` | model-swap context compressor (Phase 5) | not a conversation handoff; not on the chat path |
| `memory/hybrid.py` `HybridMemorySystem` | live in SEARCHING/RESPONDING | vector branch guarded by `hasattr(self.vectors,'add'/'search')` — the real `Index` has neither, so writes/reads silently skip; what remains is a 100-item in-process cache + self-knowledge |
| `conversation/summarization.py` `ConversationMemory` 5-tier cascade | designed | never instantiated |
| `runtime/graph.py`, `runtime/engine.py` | "Phase-1 placeholder" | reachable only via CLI `runtime-tick` |
| `agents/handlers/*` | dead, call `self.agent._create_transition_event` which does not exist | would raise if used |
| Frontend `subagentEvents`, `conversationStatus`, `somaticBlocks` | land in `useAgentStream` state | zero consumers in AgentChat |

### The finding that dominates everything else

```
routes/agent.py:686   agent.process(query=request.message, session_id=session_id, images=request.images)
state_machine.py:195  conversation_history: List[Dict] = None      # never passed
state_machine.py:221  conversation_history=conversation_history or []
useAgentStream.ts:523 const sid = sessionId || crypto.randomUUID()  # new session per message
AgentChat.tsx:538     sendMessage(input.trim())                     # no session id
```

Each user message is a fresh `StateContext` with empty history. `loadConversation`
sets local `userMessages` and calls `reset()`; nothing reaches the backend. So
"one conversation" (the 2026-08-26 cull) achieved one *surface*, not one
*conversation*: the surviving UI is a session picker over a store nobody writes,
and the agent behind it has no memory of the turn before.

This is not a Feature-B nicety; it is the floor Feature B stands on. Nothing about
"moving between conversations like memories" can be built until a conversation is
a thing the agent has.

### What the corpus intended (two generations)

- **Original concept** (`philosophy.md`, `the-being.md`, `explorations.md` A3/J1/G4):
  one lifelong first-person conversation with the machine, "sessions as days",
  no New-Chat button, history summarized hierarchically and re-hydrated as memory,
  one mind, workers report into it, modules summoned into the context region.
- **Sovereign-host layer** (`documentation/sovereign-host-vision/*`, Aug 24-25):
  a "Continuous Orchestrator Mind" with session-affinity re-anchoring, sub-agents
  forked into PTYs reporting back as Somatic Blocks, a nightly Dream Cycle. Then
  `FEASIBILITY-AND-ENGINEERING-REALITIES.md:105-132` **downgraded it**: "never run
  an LLM classifier on every keystroke", routing = regex + FTS5 only, "subagents
  are never spawned by ambient guessing" — only by an explicit tool call or button.

Your current phrasing — "an orchestrator *agent* that is aware of conversations and
can neatly delegate" — is closer to the version the docs rejected. That is a
legitimate re-decision, but it is a decision, and it reopens Q11 (user in the loop)
and the one-mind rule.

---

## Part 3 — What the two OSS checkouts actually teach

### open-claude-code (`/Volumes/Thunderbolt/AI/OSS/open-claude-code`, v2/src, ~9.8k lines .mjs)

Be careful with this one. Its ADRs claim "100% feature parity"; the code has no
background-task readback, no task notifications, no jsonl transcripts, no
resume, no memory, and its `Agent` tool ignores `allowed_tools`/`isolation`, runs
every sub-agent with `bypassPermissions`, and allows unbounded recursive spawning
(`v2/src/tools/agent.mjs:25-64`) — a privilege-escalation-by-delegation
anti-pattern. `SendMessage.receive()` has zero callers; `backgroundJobs` is a
write-only Map. Use it for *shapes*, not behaviour.

Shapes worth lifting:
- **Agent loop as async generator with continuation turns** —
  `run(null, {continuation:true})` re-enters the loop with no new human message
  (`core/agent-loop.mjs:236`). This is exactly the primitive a task notification needs.
- **Fresh-context sub-agent whose result is reduced to a text report** for the
  parent's tool_result (`tools/agent.mjs:111-127`).
- **Agent definitions as markdown + frontmatter** (name/description/model/tools/
  maxTurns, body = system prompt) (`agents/parser.mjs:87-97`). Halbert already has
  the landing spot: `SubagentHandle.agent_config_snapshot`.
- **Two-stage compaction**: micro-compact stale tool results before any full summary
  (`core/context-manager.mjs:72-113`). Do not lift its summary generator (string slicing).
- **Static/dynamic prompt split** so the cacheable prefix is stable (`core/system-prompt.mjs:91-134`).
- **Hooks receive context via env vars only, never interpolated into the command**
  (`hooks/engine.mjs:134-155`) — right for a sysadmin tool.

**The better reference is on this machine, not in that repo.** The real Claude Code
transcripts under `~/.claude/projects/<cwd-slug>/` show the actual protocol:
- one append-only `<session>.jsonl` per session; every row has `uuid`, `parentUuid`,
  `sessionId`, `isSidechain`; sub-agent transcripts are `subagents/agent-<id>.jsonl`
  + `.meta.json {agentType, description, toolUseId, spawnDepth}`;
- a finished background task appends a synthetic **user** row with
  `origin.kind = "task-notification"` carrying task id, originating tool_use id and
  an `<output-file>` path — then a normal turn runs;
- `queue-operation` rows (enqueue/dequeue/remove/popAll) for steering a running agent;
- `system/compact_boundary` rows with `compactMetadata` followed by an
  `isCompactSummary` user row — the summary is a first-class, persisted message;
- `MEMORY.md` index (one line per note) + one-topic-per-file notes with frontmatter;
  only the index is always loaded, notes are read on demand.

### Warp (`/Volumes/Thunderbolt/AI/OSS/warp`, Rust, ~5.3k files)

Warp answers both questions with one decision: **one ordered transcript per
surface**. `BlockList` (`app/src/terminal/model/blocks.rs:268`) holds terminal
blocks *and* AI exchange blocks in one sum-tree; "conversation view" vs "terminal
view" is a `TranscriptScope` filter over the same list (`block.rs:86`), not a
split pane. Warp has **no parked/minimized block state and no right-side accordion**
— Halbert's dock is ahead of it there. What Warp has that Halbert lacks is the
*model underneath* the tile:

- **Block = data, not process.** `Block` carries state
  (`BeforeExecution|Executing|Done|Background`), three timestamps, exit code,
  `was_long_running` (latched at 50 ms), `hidden`, and a per-conversation
  visibility set (`AgentViewVisibility`, `block.rs:159`). PTY lives elsewhere.
- **Agent-issued commands start hidden and auto-expand (~3 s) when they turn out
  to be long-running** (`view.rs:19055-19075, 20609-20615`). This is the rule that
  fixes Halbert's "every tiny command becomes a tile" problem.
- **Attach = control ownership, not a UI mount.** `InteractionMode::{User, Agent}`
  with `LongRunningCommandControlState::{Agent{is_blocked}, User{reason:
  Manual|Stop{auto_resume}|TransferFromAgent}}`, validated transitions, an event on
  every change; the agent can hand control to the user by tool call with a stated
  reason (`cli_controller.rs:31-155`, `interaction_mode.rs`). User prompts are
  auto-queued while the agent drives a long command (`specs/QUALITY-839`).
- **The agent never reads a byte stream.** It gets a finished block (output + exit
  code + timestamps) or a rendered *screen* snapshot: ≤1000 rows around a literal
  `<|cursor|>` marker, alt-screen aware, secrets redacted, bounded wait (2 s default,
  ≤120 s on request), user "Check now" force-refresh, `is_preempted` flag
  (`shell_command.rs:54-58,563,756`; `interaction_mode.rs:574`). Python would need
  a server-side screen model (pyte) for this.
- **Orchestrator = an ordinary conversation with four tools** — `run_agents`
  (fan-out, 30 s spawn timeout, name-keyed idempotency), `send_message`,
  `wait_for_events` (status → `WaitingForEvents`, client watchdog), lifecycle
  subscription (`run_agents.rs`, `wait_for_events.rs:22-45`). No special process.
- **Parent inbox drained into the next LLM turn** as structured inputs
  (`MessagesReceivedFromAgents` / `EventsFromAgents`), held as "awaiting echo",
  requeued ≤3 times (`orchestration_events.rs:73,260,328`).
- **Registry with three indexes**: live-per-surface, `children_by_parent`,
  `agent_id → conversation_id` (`history_model.rs:251,310,323`); 7-state
  `ConversationStatus` where `WaitingForEvents` and `TransientError` are explicitly
  non-terminal (`conversation.rs:4721`); status roll-up with precedence
  (InProgress > Blocked > Error > Cancelled > Success).
- **One idempotent `observe_child(signal)`** with kill tombstones and a persisted
  monotonic event cursor for restore (`orchestration_child_tracker.rs:134`,
  `orchestration_event_streamer.rs:280`).
- **Notification policy as a thin model over status**: fire only on
  Success/Blocked/Error; one live notification per origin; read-at-birth if the
  surface is visible; suppressed if a queued prompt will auto-continue; toast
  (ephemeral, capped) vs mailbox (persistent) vs native OS notification when the
  window is inactive, with a routable context payload (`agent_management_model.rs:352-528`).
- **Recall rows are normalized entries** whose open-action is resolved at accept
  time (already-open → joinable → restorable → transcript), with a pill bar +
  breadcrumb for the orchestrator family ordered pinned → blocked → errored →
  active → done-by-recency (`entry.rs:74`, `specs/QUALITY-567`, `specs/code-1946`).

Do **not** port: WarpUI's entity bus, the sum-tree/GPU paint pipeline, the
vte/alacritty grid, the shell-hook block-id protocol, or the cloud SSE/JOIN
machinery. Halbert is asyncio + React; the patterns transfer, the machinery does not.

---

## Part 4 — Draft direction (NOT decided; pending the Part 5 answers)

The two features are one feature. Both need the same primitive Halbert lacks:
**a conversation that exists on the backend, keyed by a stable id, that the agent
reads at the start of a turn and writes at the end.** Everything else hangs off it.

```
                       ┌─────────────────────────────────────────┐
                       │ Conversation registry (SQLite + FTS5)   │
                       │  id, parent_id, title, summary, status  │
                       │  messages[] with uuid/parent_uuid/origin│
                       └───────────┬─────────────────────────────┘
                                   │ load history / append turn
   human msg ─────┐                ▼
   task-notif ────┼──▶  AgentStateMachine.run(conversation_id, origin)
   child result ──┘        │  tools: run_command, delegate, recall_conversation,
                           │         wait_for_events, task_output, remember
                           ▼
              events: tool_start / terminal_spawn(hidden→auto-expand) /
                      subagent_event / notification / block(...)
                           ▼
              ONE ordered timeline in the UI (blocks: text, tool, terminal,
              child-conversation receipt, notification); tiles persist per
              conversation; dock = index of live terminals + children
```

Sequencing that respects what already exists:

1. **Floor** — make `/api/agent/message` load and append by `conversation_id`
   (adopt `SqliteConversationStore` after fixing the atomic-save defect); stop
   minting a session per message; keep one `AgentChat` timeline of *all* turns
   (fixes Feature-A gap #1 as a side effect). Add the transcript metadata the real
   Claude Code uses (`uuid`, `parent_uuid`, `origin`, `is_sidechain`).
2. **Feature A polish** — replay the buffer on mount (gap #2); tile at the tool's
   position, card `<pre>` suppressed when a tile exists (gap #3); hidden-until-
   long-running default (Warp); one xterm per session; store reset keyed by
   conversation; observer mount guard; port the partial-line buffer to `confirmAction`.
3. **Background tasks + task-notification continuation** — `BackgroundTask`
   registry keyed by conversation, spool file, `task_output`/`task_stop` tools,
   completion appends a system-origin user message and runs a continuation turn
   (gated by a setting — see Q4).
4. **Sub-agents as child conversations** — `spawn` creates a child row
   (`parent_id`, `spawn_depth`, narrowed tool allowlist, never more privilege than
   the parent), runs its own state machine, reduces its final text to the parent's
   tool_result; parent inbox drained at the start of its next turn (Warp), child
   receipts rendered as collapsible rows in the same accordion family as terminals.
5. **Conversations as memory** — `recall_conversation(query|id)` returns
   title + summary (never full history); summary generated by the guide model at
   turn end; `SessionAffinityRouter` (or embedding search over summaries) suggests
   a re-anchor chip; compaction boundaries persisted as messages.
6. **Only then**: PTY-backed agent commands (`attach:'ws'`, control-ownership state
   machine, pyte snapshot), Dream Cycle (opt-in), memory index file.

Invariants carried forward from founder decisions: commands staged, never executed
(`05c38e3`); one conversation surface reached via `hostConversation.ts`; label
with the onboarding `ai_name`, never "Sovereign", never a raw hostname; never name
an AI model; canonical tokens only; one personality — sub-agents are hands, not
minds; subagents spawn only from an explicit tool call or button; never touch the
running embed.

---

## Part 5 — Decisions only the founder can make

1. **What is the orchestrator?** (a) an LLM conversation with delegate/recall/wait
   tools that decides for itself when to delegate and when to pull in a past
   conversation (Warp's shape; what your wording implies; reopens FEASIBILITY §4),
   or (b) the deterministic router the docs settled on, with the LLM only ever
   delegating via an explicit tool call the user approves.
2. **Conversation model:** one continuous timeline with day dividers and no
   New-Chat (the original concept), or named sessions the user picks (what the UI
   does today)? And which store wins — the SQLite+FTS5 one is the only candidate
   with search; is legacy JSON history migrated or abandoned?
3. **User-operated shells in the conversation surface** — keep `+ New Terminal`
   (Aug 24 position) or agent-facing only (Aug 22 position)?
4. **Auto-wake:** when a background task or child finishes, does the parent turn
   run on its own (LLM cost, unattended tool calls) or only enqueue a notification
   until the next human message? The staged-not-executed posture argues default-off
   with a per-conversation opt-in.
5. **Agent commands on a real PTY** (stdin, sudo prompts, resize; accepts the
   2-session cap and reaper work) or mirrors by default with PTY on request?
6. **Are child conversations visible** in the conversation list, or only as
   collapsible receipts under the parent turn (the "one conversation" rule argues
   the latter)?
7. **Docking:** is one-way (chip until clicked) final, or should scroll-back
   restore with hysteresis?

---

## Part 6 — Things to fix regardless of the answers

- `TerminalTile` blank-mount bug (Part 1 #2) — a real defect in shipped UI.
- `confirmAction` partial-line buffer (Part 1 #9).
- `agents/handlers/*` and `agents/conversation.py:SessionStore.delete` reference
  things that don't exist — delete or fix, they are false signals.
- `HybridMemorySystem` vector guards fail against the real `Index` — interactions
  are not persisting.
- Stale prose: `TerminalAccordionDock.tsx:17` ("below the ContextBar"),
  `SOVEREIGN-HOST-SHELL-RESULTS` mount points, and the "Codebase Reality Check"
  sections in `documentation/sovereign-host-vision/SUBAGENTS-AND-TASK-DAEMONS.md`
  §5 and `CONTINUOUS-ORCHESTRATOR-AND-SESSION-ENGINE.md` §8, which now deny the
  existence of modules that exist.
- Legacy `xterm`, `xterm-addon-fit`, `xterm-addon-web-links` in `package.json:46-48`
  have no importers.
- Test invocation should be documented as `.venv` only.
