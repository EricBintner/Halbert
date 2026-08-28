# Continuous Conversation, Hidden Threads, and Watched Terminals — Design

**Date:** 2026-08-26
**Status:** Design v1 — approved in outline by the founder, folded through five adversarial
reviews, awaiting the founder's read before the implementation plans.
**Supersedes:** the draft direction in `.handoff/TERMINAL-AND-ORCHESTRATOR-REVIEW-2026-08-26.md`
Part 4 (v0). The "Continuous Orchestrator Mind" in
`documentation/sovereign-host-vision/CONTINUOUS-ORCHESTRATOR-AND-SESSION-ENGINE.md` and the
terminal sections of `STREAMING-TERMINALS-AND-UI-ORCHESTRATION.md` are the ancestors; where
they disagree with this document, this document wins.
**Evidence base:** `.handoff/TERMINAL-AND-ORCHESTRATOR-REVIEW-2026-08-26.md` and its
appendices A (code + OSS audits), B (continuity patterns in Claude Code, Warp, and Halbert's
dormant modules), C (five critics against v0). Every `file:line` below was verified on
2026-08-26.

---

## 1. Problem

Halbert has one conversation *surface* but no conversation. `routes/agent.py:686` calls
`agent.process()` with no `conversation_history`; `useAgentStream.ts:523` mints a fresh
session id per message; `AgentChat.tsx:666` renders an assistant block only for the last
user message. Every message is a new, empty context. Three conversation stores exist and the
agent path writes to none. The sub-agent, affinity-router, SQLite+FTS5 store, summarisation
cascade and watermark modules are all committed with zero production callers.

Terminals: the pipe from `executor.py` through `terminal_bridge.py` to the xterm tile and the
accordion dock is real, but tiles survive one turn, a tile mounted onto existing output is
blank (`TerminalTile.tsx:62-133` never replays `session.output`), agent commands are
read-only subprocess mirrors, there is no command-boundary mechanism of any kind, the 60 s
idle reaper kills a quiet shell, and the admin's own `+ New Terminal` shell is sandboxed
while the agent's commands are not.

## 2. Founder direction and invariants

Direction (2026-08-26):

- "One seamless chat without the need to click into a list of conversations." A list of
  past sessions "seems like we are bolting on parts."
- "A hidden set of sessions under the hood, like Halbert remembers we discussed Samba config
  6 weeks ago and can pull that context back" — and so lingering context does not bleed when
  the topic changes. "Much of this work isn't massive context, so if there's some way to
  modularize the context then that might be the solution."
- Multi-task management is secondary ("users already have Warp and CC").
- Terminals: keep user-facing shells but make them **watched** — "Halbert can see it and know
  what you entered and can see the results." Tabs are a next iteration. "The terminal is
  generally owned by the agent." "The agent should reuse a terminal window if it's not running
  a long task." Notifications are "a colored indicator light (fills and outlines too for
  ADA)", with a subtle one-click way back to the associated hidden session.
- Chosen: hybrid thread brain (signals hint, model decides); **day dividers only** as the
  visible segmentation; commands are staged in the composer **plus** a "stage into my shell"
  action.

Invariants carried forward: commands are staged, never executed by UI (`05c38e3`); one surface
reached via `lib/hostConversation.ts`; the engaged surface is labelled with the onboarding
`ai_name`, never "Sovereign" or a raw hostname; never name an AI model anywhere; canonical
design tokens only (`/shared-tokens/tokens.css`, `scripts/check_contrast.py`,
`scripts/check_literal_colors.py`); one personality — threads and children are buffers, not
minds; LLM-authored summaries are opt-in; ChromaDB stays eval-only (`the-being.md` §9);
never touch the running embed build.

## 3. Model

| Term | Definition |
|---|---|
| **Timeline** | The one visible surface. Every turn, forever, in time order, paged. The only visible structure is a **day divider** per calendar day and a sticky one-line *current topic* label at the top of the scroll region. No thread list, no thread titles in the scroll. |
| **Thread** | A hidden working buffer: a contiguous run of turns on one subject. Row in the `threads` table. Status `open \| paused \| closed \| merged`. Exactly one thread is `open` at any time (exception: a proactive thread is created `paused`, §10). |
| **Turn** | One user message and everything the agent did in response (assistant text, tool blocks, terminal blocks, diff proposals), keyed by the per-turn `session_id` the state machine already uses for cancel/confirm/streaming. |
| **Working context** | What the model sees on a turn: the `<continuity>` hint (≤ ~120 tokens), the open thread's **receipt-of-older-turns**, the last 6 raw turns of the open thread, any recalled receipt, the watched-shell digest, and the existing retrieval sources. |
| **Receipt** | The structured, deterministic summary of a thread: title, date range, turn count, domains, canonical entities, first user line, last assistant status line, commands run with exit codes, files written, and one "next step / unresolved" line. ≤ 1,500 characters. Optionally augmented by an LLM-authored 9-heading summary (opt-in). Recall returns receipts and snippets, never a transcript. |
| **Block** | One command in a terminal session: `command, cwd, started, ended, exit, owner user\|agent, interactive, redacted, output_head (≤20 lines), output_tail (≤4 KB)`. Tiles render blocks; task cards render tasks. |
| **Session (terminal)** | One PTY. `kind: user \| agent-pool \| oneshot`. Contains blocks. The agent's pool sessions are an implementation detail and are never listed in the UI. |
| **Task** | A unit of work with a lifecycle and a result that runs outside — or outlives — the turn: a background command, a long-running in-turn command (promoted at 2 s), a sub-agent (child thread, spec 2), or a scheduled/proactive job. Owns 0..n blocks and belongs to a thread. Tasks are what the right column lists; blocks never appear there without a task. The admin's own shell is *not* a task. |

## 4. Turn pipeline (`POST /api/agent/message`)

All of this runs under the state machine's **turn lock** (§12).

1. **Persist the user message** immediately with `status=in_progress` in the currently open
   thread (so a crash never loses what the admin said).
2. **Signals, zero-LLM** (existing `intake` extended, `session_affinity`, `watermark`):
   - `detected_domains` / canonical entities via the alias table (§6);
   - anaphora and past-reference cues (`we discussed`, `last week`, `remember when`,
     `did that work`, `any luck`, `still`, bare `that`/`it` with no other signal);
   - gap since `thread.last_active` vs the 2 h gate;
   - FTS5 over **receipts** (not raw messages) for candidate threads, top-2 with scores;
   - watched-shell blocks since the last turn (§9.6).
3. **Resolve the thread** (§5): reopen a paused thread on strong match; auto-open a new one
   only when gap > 2 h **and** domains are non-empty **and** disjoint from the open thread's
   **and** no anaphora cue; otherwise keep the open thread and, if the gap is > 2 h, mark it
   `stale` for the hint.
4. **Deterministic recall on strong match** (§6): inject the matched receipt as
   `retrieved_context[0]` with `source='thread'` and emit `thread_recalled`. No model call.
5. **Build the hint** and the history: receipt-of-older-turns + last 6 raw turns of the open
   thread (bypassing the assembler's own re-summarisation), placed **immediately before the
   query** (tail of the prompt — Ollama truncates the head), and also passed to the RESPONDING
   prompt, which today never sees history (`agent_prompts.py:253-330`).
6. **Run the state machine** with `conversation_history`, `thread_id` on `StateContext`, and
   the two meta-tools available (§7). `new_thread` / `recall_thread` are handled inline in
   PLANNING: no loop increment, no tool card, then PLANNING re-runs once.
7. **After `response_complete`**: finalise the turn row; append the assistant turn; update
   `last_active` (human/assistant origins only) and the thread's domain/entity sets; refresh the
   receipt (extractive, zero cost). If the thread switched mid-turn, the *old* thread is paused
   from stored rows only (the current turn belongs to the new thread). Side effects that write
   memory (Haloysius line, opt-in LLM summary) never run inline — the tick runs them
   (`state_machine.py:1154-1201` pattern) after the grace window.

## 5. Thread lifecycle

```
            strong match / "same topic"                 grace window elapsed
  ┌────────── reopen ◄──────────┐                     ┌──────► closed
  │                             │                     │
open ── new_thread / auto-open ──► paused ────────────┤
  ▲                             │                     └──────► merged (merge-back)
  └──────── proactive reply ────┘
```

- **`new_thread(title, reason)`** (model) or **auto-open** (§4.3) *pauses* the open thread and
  opens a new one. Nothing is compacted, indexed or written to memory yet.
- **Soft landing:** for exactly one turn after a switch, the previous thread's last 3 raw turns
  stay in the working context, so a spurious split costs nothing visible.
- **Grace window:** 30 minutes or 5 turns of the new thread, whichever first. During it a
  paused thread can be **reopened** (strong match, or the admin says "no, same topic" and the
  model calls `resume_thread`) — no `(2)` duplicates ever. After it, the tick closes the thread:
  builds the final receipt, indexes it in FTS5, and records machine-state triples
  (commands, files, entities) to Halbert's own state store (R2-N3).
  ~~The Haloysius episodic line was cut per founder decision D1.2 (2026-08-26):
  Haloysius has no cross-session understanding, so session data does not flow into it.~~
- **Merge:** "same topic" within the grace window moves the new thread's turns back into the
  previous thread and marks the new one `merged` (its rows stay, its receipt is dropped).
- **Stale:** gap > 2 h without a domain shift does **not** close anything; the hint gains
  `resuming after 2h` and the open-loop line. Live terminal sessions spawned by a thread keep it
  from auto-closing.
- **Titles** are server-side only (never in the scroll): provisional = first user message
  truncated to 60 characters; refined from the receipt at pause/close (top entity + verb); the
  model may name a thread only when it opens one.
- **Pending confirmation at switch:** a staged HIGH-risk command in `AWAITING_CONFIRMATION`
  is auto-rejected when its thread pauses (same path as `confirm_action(confirmed=False)`,
  `state_machine.py:399-415`) and recorded in the receipt as "not run — superseded".
- **Forget / redact:** per turn, "forget this" replaces `content` and `blocks_json` with
  `[redacted by admin]`, rewrites the FTS row, regenerates the receipt, and writes a Haloysius
  retraction event. A thread may be marked `ephemeral` ("don't remember this"): kept in RAM for
  the working context, never written to FTS receipts or Haloysius. Rows are otherwise never
  deleted.

## 6. Recall

**Index.** SQLite FTS5 over receipts (and messages for snippets), tokenizer
`porter unicode61`. An **alias table** in `intake/signals.py` canonicalises entities at index
and query time: `smb | cifs | "file share" | "windows share" → samba`; `nfs | exports → nfs`;
`wg | wireguard | vpn → wireguard`; `certbot | letsencrypt | acme → tls`; `zpool | zfs → zfs`;
`smbd | nmbd → samba`; the domain keyword lists gain `samba, smb, nfs, cups, wireguard, vpn,
scanner`. No Chroma collection is added (the-being §9). A semantic tier via Haloysius
`memory_v2.search` is deferred.

**Strong match** (deterministic, injects the receipt, no model call) := the open thread is
excluded and either (a) a past-reference/anaphora cue is present **and** the top FTS hit scores
above threshold, or (b) ≥ 2 canonical entities/domains of the message overlap a paused or
closed thread. Strong match to a **paused** thread reopens it; to a **closed** thread injects
its receipt into the open thread.

**Weak match** := any single hit. The hint lists up to two candidates with dates and match
terms; the model may call `recall_thread`.

**`recall_thread(query?, thread_id?)`** returns up to 3 candidates when scores are close
(`{title, date, receipt, matching_messages ≤ 5 FTS snippets, match_terms}`), so the model can
ask "the Jul 14 Samba one or the Jun 30 NAS one?". "No earlier thread matched" is a normal
result. Recalls are persisted on the open thread (`recalled_thread_ids` with status
`accepted | retracted`); a retracted recall is excluded from compaction and adds a system-origin
observation the next PLANNING sees.

**Visible trace:** exactly one chip in the ContextBar — `pulled in: Samba config · Jul 14` —
a real button (click scrolls the timeline to that day; hover shows the match terms as its
"why now"; × retracts). It expires when the open thread pauses.

**The "Samba, six weeks ago" flow, end to end.** Admin: "I want to add another share for the
scanner, same as we did for the media one." Signals: entities `samba, share, scanner, media`;
cue "as we did"; FTS top hit = thread `Samba media share` (Jul 14) → strong match →
receipt injected, `thread_recalled` emitted. Hint:

```
<continuity>
Thread: "Scanner share" · opened just now.
Pulled in: "Samba media share" (Jul 14, 6 weeks ago; matched samba, share, media) —
  added [media] to /etc/samba/smb.conf (path=/srv/media, guest ok=no, valid users=eric);
  ran testparm (exit 0), systemctl restart smbd (exit 0); admin confirmed mount from laptop.
</continuity>
```

Answer: "On Jul 14 we added `[media]` at `/srv/media` with `guest ok = no`, `valid users =
eric`. I'll add `[scanner]` the same way at `/srv/scanner`." + a DiffBlock for `smb.conf` +
the `testparm` block. Chip: `pulled in: Samba media share · Jul 14`.

## 7. Prompt and model tools

- **`<continuity>` component** (new prompt component, rendered through the voice renderer —
  first person / the computer / hybrid — `agent_prompts.py:48-69`): "You have one continuous
  conversation with the admin. Your working context is the current subject. Earlier subjects
  listed below may matter; call `recall_thread` when one does. Call `new_thread` when the
  subject changes; a question you can answer in one reply does not need a new thread." The
  instruction to call tools is omitted when the model has rejected tool schemas
  (`client.py:394-409` logs once per model).
- **Placement:** the hint and the thread history go at the **tail** of the PLANNING user
  message, immediately before `## Current Task`, and are passed to
  `build_response_prompt(query, context, observations, history, continuity)`.
- **Meta-tools** `new_thread(title, reason)`, `recall_thread(query?, thread_id?)`,
  `resume_thread(thread_id)` — SAFE class in `tools/safety.py`, handled inline in
  `_handle_planning` before the tool loop: mutate `ctx` (thread id, history reset or receipt
  injected, `thread_switched` flag for idempotence), emit `thread_started` /
  `thread_recalled`, no `tool_start`/`tool_complete`, no loop increment. Schemas kept short
  (≤ 60-character descriptions).
- **Budget.** `num_ctx` is set on every Ollama call (`client.py:489-495`, `agent.py:479`):
  `clamp(round_up(context_budget.total + tool_schema_tokens + 512 + num_predict, 1024), 4096,
  model_max)`, computed once per model per process so the model is not reloaded per turn;
  PLANNING `num_predict` lowered to 1,024; stream `max_tokens` subordinate to
  `num_ctx − prompt`. The conversation bucket in `intake/budget.py` is raised so 6 raw turns fit
  at MEDIUM; the assembler's `should_summarize` is bypassed when a receipt is supplied; the
  receipt gets its own slot outside the newest-first walk.
- **`memory.store_interaction`** is removed from the agent path (receipts + the Haloysius line
  replace it; otherwise every turn's Q/A becomes a global memory injected into unrelated
  threads once the vector adapter is fixed).

## 8. Storage

`SqliteConversationStore` (`agents/conversation_sqlite.py`) becomes the store of record after
these fixes, in this order: `PRAGMA journal_mode=WAL`, `busy_timeout=5000`; every write in
`with self._conn:`; `append_message()` is the only message write path (no delete-all/reinsert);
block-list content serialised as `content_to_text` + `blocks_json`; FTS query tokenised and
quoted, `MATCH` in its own `try`, the `LIKE` fallback outside it; failures logged at WARNING
and returned as `False` so the route can emit `thread_store_error` once.

Schema (additions):

- `threads` (today's `conversations`): `status, title, topic_domains, entities_json,
  receipt, receipt_updated_at, last_active, stale, ephemeral, parent_thread_id,
  merged_into, recalled_json, unread`.
- `messages`: `thread_id, session_id (per turn), origin ∈ {human, assistant, terminal,
  task-notification, proactive, system}, status ∈ {in_progress, complete, interrupted,
  cancelled}, blocks_json, terminal_block_ids, diff_proposals_json, visible_in_timeline`.
- `terminal_blocks`: the block record of §3, keyed by `block_id`, with `session_id, thread_id,
  turn_id`.
- `terminal_sessions`: `session_id, kind, owner, watched, spawned_at, ended_at, last_state`.
- `compact_boundaries` (opt-in LLM summaries): `thread_id, trigger, pre_tokens, post_tokens,
  preserved_message_ids, summary_message_id`.
- `messages_fts` and `receipts_fts` with `tokenize='porter unicode61'`.

Diff proposals move from `active_sessions` (evicted at end of turn, `state_machine.py:264`,
so apply/reject already 404) to `messages.diff_proposals_json`; the apply/reject routes read
the store.

Identity: `session_id` stays per turn for cancel, confirm, StreamEvent routing, the terminal
bridge ContextVar and `active_sessions`. `thread_id` is added to `StateContext` and used for
messages, terminal blocks, somatic blocks (`session_somatic_blocks`), diff proposals, the
Haloysius line tags, and receipts.

Redaction (`streaming/redact.py`) runs before **any** write of terminal blocks or pasted
content: `password=`, `-p<token>`, `Authorization:`, `Bearer`, `AKIA…`, `hf_…`, `ghp_…`,
`BEGIN … PRIVATE KEY` blocks; blocks carry `redacted: true`.

Migration: `migrate_json_conversations_to_sqlite` runs once, counts only successful saves, and
learns the second JSON shape in `routes/conversations.py` (`id/name/ISO timestamps`); migrated
history lands as closed threads. Then delete: the `/api/conversations` router, the JSON
`ConversationStore`, `routes/agent.py:889-926` (`/agent/conversations`), `SessionStore`, and
`agents/handlers/*` (dead; references methods that do not exist).

Memory writes: ~~the Haloysius episodic line (voice-rendered, tags `[thread_id, *domains]`)
at close for threads ≥ 3 turns;~~ **CUT per founder decision D1.2 (2026-08-26):**
Haloysius has no cross-session understanding, so session data does not flow into it.
Machine-state triples (commands, files, entities) are now recorded to Halbert's own
state store at thread close (R2-N3). `HybridMemorySystem`'s vector adapter is fixed as
a separate small task (shim `add/search/delete` over `Index` using `documents=` so both
sides embed identically) but is **not** on the thread path.

## 9. Terminals

### 9.1 Sessions and kinds

`TerminalSessionManager` gains `kind` per session and per-kind policy from config:

| kind | cap | idle policy | sandbox |
|---|---|---|---|
| `user` | 3 (tabs later) | never reaped while a client is attached; detached TTL 30 min | **none** — it is the admin's shell |
| `agent-pool` | 3 | idle TTL 15 min; never reaped while a block is open | same posture as `run_command` today: `ToolSafetyFramework` gating per block, no OS sandbox wrapper (an OS-sandboxed pool is a follow-up because a persistent wrapper fixes `writable_paths` for the session's life) |
| `oneshot` | 2 | 60 s (today's rule) | as today |

The WebSocket bridge touches attach/detach counts. `list_active` returns kind, owner,
watched, current block, block count. The frontend GETs `/api/terminal/sessions` on mount and
attaches live ones; stored block ids not in that list render as static replays.

### 9.2 Shell integration and the block parser (`streaming/shell_integration.py`)

User shells are spawned as `bash --rcfile <halbert>/shell/bashrc -i` or with
`ZDOTDIR=<halbert>/shell/zsh` (whose `.zshrc` sources the user's real `~/.zshrc` first). The
rc files add guarded precmd/preexec hooks emitting `\e]133;A\a` (prompt), `\e]133;B\a`
(input start), `\e]133;C;id=<block>;cmd=<base64>\a` (output start), `\e]133;D;<exit>\a`
(end) and `\e]7;file://<host><cwd>\a`. Other shells spawn unhooked with `watched: false` and a
badge on the *Your shell* region. The parser is a byte state machine on the master fd that carries partial sequences
across reads, attributes bytes between C and D to a block, passes everything through unchanged
to xterm.js, and:

- on `\e[?1049h` / `\e[?47h` marks the block `interactive` and stops copying output until
  `\e[?1049l` (vim, less, htop);
- on a password-prompt regex at the tail with no output for 5 s marks `needs_input` and emits
  `terminal_needs_input`;
- marks a block whose command starts with `ssh `/`mosh ` as `remote` (its inner commands are
  not parsed — they run on another host);
- produces the bounded copy (`output_head`, `output_tail`) from raw bytes, never from the
  drop-oldest bus.

### 9.3 Agent pool and `run_command`

`streaming/agent_pool.py` (`TerminalPool`). `executor._run_command`: ask the pool for a session
that is not busy (`busy` := open block) and not interactive; spawn one (up to cap) as
`bash --norc --noprofile` with job control (`set -m`), ECHO cleared on the slave before exec;
write `printf '\e]133;C;id=<block>\a'; <cmd>; printf '\e]133;D;%d;id=<block>\a' "$?"\n`;
await the block's D marker with the tool timeout; on timeout write ETX (`\x03`), grace-wait
2 s for D, else kill and evict the session and emit `terminal_complete` exit −1. Return the
same string shape the model sees today. Publish `terminal_spawn` with `attach:'ws'`,
`owner:'agent'`, `block_id`. At cap, or when the pool session is in an interactive state, fall
back to today's subprocess path. `cwd` is honoured with a `cd` inside the block; env/cwd
drift is cleared by a dock "recycle" action.

**Definitions.** `busy` = open block. `long-running` = open block older than 2 s (backend
emits `terminal_block_promote`; the tile appears only then). `interactive` = alt-screen or
`needs_input`. Interactive blocks are never reused and never copied.

### 9.4 Background commands (minimal, notify-only)

`run_command(background=true)` returns immediately with the block id and "started"; the block
becomes a **task** (a card in the Tasks column, §9.5) and continues in its own pool session
(excluded from reuse while busy); no default timeout
(config maximum 6 h); `task_stop(task_id)` sends ETX; `task_output(task_id, tail_lines)`
reads the spool. On exit the server appends a
`messages` row with `origin=task-notification` (`command, exit, duration, tail`) to the
thread that owns the turn, sets `thread.unread`, emits `task_completed`, and lights the
StatusLight. **No continuation turn runs**; the next human message sees the notification in
the hint (`Background command from "Samba share setup" finished 4 min ago: rsync … exit 0
(12m03s)`).

### 9.5 Tile = block, card = task

Inline: the `ToolExecutionCard` for a `run_command` renders **its block** — a one-line result
for short blocks (`$ smbstatus · exit 1 · 0.3 s`, expandable), a live xterm only while it is
the session's current open block and long-running, a frozen `<pre>` from
`output_head/tail` once complete (no xterm, no socket). The card's own `<pre>` result is
suppressed when a block renders. Origin anchor is `data-terminal-block`. `TerminalTile`
replays `session.output` after mount (the blank-tile bug). The IntersectionObserver gets a
mount guard and `rootMargin`; docking stays one-way; `confirmAction` gets the partial-line
buffer `sendMessage` has. Inline and the task card never both mount an xterm for one session — inline
wins and the task card says "live in conversation ⤴".

**Tasks column (replaces `TerminalAccordionDock`).** The right column's dock becomes a
*Tasks* panel modelled on the background-tasks column the founder pointed at: a **Running**
section and a collapsed **Finished N ›** section with *Clear*. One card per task: title (the
command or the sub-agent's goal), owning thread's topic, elapsed time, and a body that is
collapsible but not an accordion of sessions — for a command task the body is its block (the
live xterm while running and long-running, a frozen replay once done); for a sub-agent task
(spec 2) the body is its phases/steps and its receipt. A short in-turn command never becomes a
task (it stays an inline card); a block promoted to long-running at 2 s becomes a task
automatically, which is when its card appears. Cards carry the StatusLight (§9.9), a ⤴ to the
originating turn, *stop*, and for user-visible output *copy*. Finished cards collapse after
10 minutes; *Clear* removes finished cards from the column only (the timeline keeps
everything). `MAX_VISIBLE=3` governs live xterms only. **Your shell** is a separate pinned
region of the column (one user session in v1, a tab strip later) with its own xterm, the
*watched / unwatched* toggle and the *stage into my shell* target; it is never a task card.

`TerminalTile` is agent-owned unless `owner=user`: `disableStdin`, no cursor. The admin
typing into an agent session (take-over) is a next iteration.

### 9.5a Task model (mirrors Claude Code's background tasks)

The founder's reference is Claude Code's background-task model (the Desktop panel is its
front end); Appendix B reverse-engineered the on-disk protocol. Halbert's `tasks` table and
API follow it field for field:

| Claude Code | Halbert |
|---|---|
| task id (`<task-id>`), kind (agent / workflow / background bash) | `task_id`; `kind ∈ {command, agent, workflow, scheduled}` (`agent`/`workflow` arrive with spec 2) |
| description | `title` (the command, or the sub-agent's goal) |
| status running / completed, plus stop | `status ∈ {running, completed, failed, stopped, needs_input}`; a stop control on the card (`task_stop`) |
| originating `tool-use-id` | `turn_id` + `block_id` / child `thread_id` |
| `<output-file>` under the session's `tasks/` dir | `~/.halbert/tasks/<task_id>.output` spool; the bounded copy in `terminal_blocks` |
| completion delivered as a system-origin *message* with `<summary>` and `<result>` | the `origin=task-notification` row (§9.4) with `summary`, `exit`, `duration`, `tail`, `output_path` |
| `TaskOutput` / `TaskStop` tools | `task_output(task_id, tail_lines)` and `task_stop(task_id)` (SAFE class) |
| "the user can send it another message and resume it" | agent tasks stay addressable (mailbox, spec 2) |
| `spawnDepth`, concurrency cap | `depth` on agent tasks; per-kind caps (`SubagentManager.max_concurrent`, pool cap) |
| cost line (agents · tokens · time) | duration for every task; for agent tasks, turn count and the **model slot** (chat / specialist), never a model name |
| Running / Finished sections, Clear, expand ⤢ | Running / **Finished N ›** / *Clear* (column only); ⤢ opens the task in the timeline at its turn |

A task always belongs to a thread; its card shows the thread's topic. A task that finishes
lights the StatusLight and appends its notification row; nothing runs a turn on its own
(§9.4). Workflow tasks (spec 2) render phases and their agents as the sub-table in the
reference screenshot.

### 9.6 Watched user shell

Each closed user block (redacted, bounded) inserts a `terminal_blocks` row and a `messages`
row with `origin=terminal` in the thread open at the time it closes
(`$ cmd · exit N · 0.3 s · cwd` + ≤ 20-line tail), so FTS recall works and the agent can cite
it. Watched activity updates `thread.last_active` for the gap gate but never triggers
`new_thread`. The agent sees blocks only at the next turn, in the hint, capped at 8 blocks /
2 KB (`Since your last message you ran 23 commands in your shell (last: systemctl restart
smbd, exit 0, 2 min ago)`), and can fetch detail with a zero-risk `terminal_blocks(session_id,
n)` tool. Per-session **unwatched** toggle on the *Your shell* region suppresses both. User blocks are
visible in the *Your shell* xterm and to the agent via the hint; they are not rendered as
timeline cards in v1. The agent never
writes into a user shell. The dead `/api/terminal/history` file and the `@terminal`
mentionable are repointed at this ledger.

### 9.7 Staging into the admin's shell

Composer staging stays the default. Each proposed command also offers **stage into my
shell**: `POST /api/terminal/sessions/{id}/stage` writes the command text (no newline) to the
user PTY, allowed only when the parser sees the shell at an empty prompt (state A/B seen, no
C, no bytes typed since B); otherwise the action is disabled with "shell busy". The admin
presses Enter; the resulting block flows back through §9.6. Still staged, never executed.

### 9.8 PTY correctness

`PTYSession` gets one reader task per session fanning out to every `_read_queues` consumer
(today a second `add_reader` on the same fd starves the first, `pty.py:174-197`); attach sends
`{type:'replay', data:get_buffer()}` first and the frontend treats it as a buffer reset. Bus
overflow never affects block copies. Backend startup marks open blocks `lost`; a 4404 on
attach marks the session `ended: unknown`, not `exit −1`.

### 9.9 Indicator light

A `StatusLight` primitive (`components/agent/StatusLight.tsx`, inline SVG, 10 px), replacing
the dock's status dot, the tile's `● ■ ○` pill and the card's `⟳`. Its states are the task
states, so a task card and its inline block always show the same light:

| state | token | shape | glyph | text |
|---|---|---|---|---|
| running | `--color-status-nominal` | outline ring | — | mono elapsed timer |
| needs attention (stdin / over expected duration) | `--color-status-warning` | outline | `!` | `needs input` |
| done, unseen | `--color-status-nominal` | filled | `✓` | `exit 0` |
| error | `--color-status-critical` | filled | `✕` | `exit N` |
| blocked on approval | `--color-accent-strong` | filled | `‖` | `awaiting approval` |

No state is colour-only; SVG `fill`/`stroke` with `currentColor` survives forced-colours;
the only motion is one `var(--duration-shutter) var(--ease-shutter)` transition on state
change — no `animate-*`, no pulses (brand §5). The blocked light is the one vermilion element:
Send demotes to the outline style while an approval is pending. Placement: the task card, the
block's inline card header (on a `--color-surface` strip, not on the status-tinted body), and an
aggregate light on the engaged tab of `ModeSwitch` (precedence blocked > error > done-unseen >
needs-attention > running; `aria-label="<ai_name> — 1 running, 1 awaiting approval"`).
*done-unseen* is set when a long-running block ends while its tile is < 25 % visible or the
app is in browsing mode; cleared when the card is ≥ 50 % visible for 1 s or on click. Click =
`timeline?around=<turn>` if needed, then scroll to `[data-terminal-block]`. For a closed
thread: scroll only — a click never changes what the model knows.

## 10. Proactive channel and task notifications in the timeline

A `ProactiveEvent` that passes the gate (`proactive/gate.py`, the proactivity dial) becomes a
`messages` row with `origin=proactive` in a **new paused thread** (title from the finding,
domain as its topic), appended to storage without `agent.process()`. It renders in time order
with the StatusLight on its day's divider region and the hint gains `Waiting for you: "Read
errors on /dev/sda1" (03:12, critical)`. The admin's reply opens that thread (pausing the
current one under §5); a critical auto-open scrolls to it but never switches the open thread.
The morning report lands the same way. `ProactiveEventsBadge` moves from `ContextStage` to the
Layout header so it exists in both modes. Task notifications (§9.4) use `origin=task-notification`
in the owning thread.

## 11. Frontend

- **Timeline**: `GET /api/agent/timeline?before=<turn>|around=<turn>` (50 turns a page),
  rendering stored turns **with roles** (today `loadConversation` dumps assistant turns into
  user bubbles), tool cards as static records for past turns (diff/confirmation buttons never
  live for a dead session), terminal blocks as static replays, day dividers as
  `<header><h2>Thu, Jul 14</h2><time datetime=…></header>` (absolute after 48 h), container
  `role="feed"` with `aria-busy` while paging, each turn `role="article"`. A sticky
  *current topic* label (the open thread's provisional title, e.g. "Samba share setup") at the
  top of the scroll. `HostGreeting` only when the timeline is empty.
- Dropdown, "New Conversation", the `Session: …` footer: deleted.
- `useAgentStream` keeps minting the per-turn `session_id`; the server owns thread identity.
  New SSE: `thread_started`, `thread_recalled`, `terminal_block`, `terminal_block_promote`,
  `terminal_needs_input`, `task_completed`, `thread_store_error`.
- **ContextBar** gains `ContextType = 'thread'` on telemetry tokens
  (`bg-status-telemetry-bg text-status-telemetry border-status-telemetry-line`, add the
  missing `status.*-line` Tailwind aliases); `ContextPill` becomes a `<button>` with an
  `aria-label` and a sibling labelled remove button; minimum 11 px mono. Max one thread chip.
- **Live regions**: one visually-hidden `role="status" aria-live="polite"` in `HostShell`
  for `<command> finished, exit 0` / `Pulled in earlier work: <title>` / `New subject`; one
  `role="alert"` for blocked-on-approval only; xterm `screenReaderMode` on for the focused
  tile only.
- **Keyboard**: PTY tiles own every key except the escape hatch Ctrl+\` (via
  `attachCustomKeyEventHandler`); the tile header is the tab stop (Enter/F2 enters); read-only
  tiles set the textarea `tabIndex=-1`; `ShellModeContext`'s Cmd/Ctrl+B bails inside `.xterm`;
  no thread shortcut exists. Task cards are `<button aria-expanded>`; glyph buttons get
  `aria-label`s and lucide icons; chip copy is state-based (`live in conversation ⤴` /
  `in dock` / `exit 0`), never a session hash.
- **Narrow windows** (< `md`): `ContextStage` (vitals, Tasks column, Your shell) renders as a
  `Sheet` opened from the aggregate light; "go back to this" opens it, scrolls the timeline,
  expands the task card.
- **Tokens**: no new colour token. Fix `TerminalTile.tsx:181 bg-[#1a1b26]` →
  `bg-canvas-subtle` and `:199` violet → telemetry; extend `check_literal_colors.py` to catch
  `-[#hex]`; delete the `glow`/`pulse-subtle` keyframes; `ToolExecutionCard` labels become
  measurements (`exit 0`, never "Success"); `motion-reduce:animate-none` on remaining spinners.
- The `<continuity>` text and the sticky label follow the voice setting.

## 12. Concurrency and failure handling

- `AgentStateMachine.turn_lock` (asyncio) held for the whole of `process()`,
  `confirm_action()`, thread resolve/open/pause/append, and every out-of-turn append
  (watched-shell blocks, task notifications, proactive rows). A second `/message` during a
  turn is queued (the composer already queues) and emits `conversation_status: waiting`; the
  force-reset block at `routes/agent.py:657-669` is removed; the initial
  `_transition(PLANNING)` moves inside the `try`.
- User message stored at turn start; `interrupted` at boot for any `in_progress` row, rendered
  "(Halbert restarted here)" with expired cards. Error-banner retry never clears stored turns.
- Store failures never block a turn (WARNING + `thread_store_error` once). FTS errors → LIKE.
  Hint builder failure → empty hint. `new_thread` twice in a turn → no-op. Migration idempotent.
  Timeline endpoint degrades to empty, never 500. LLM-summary compaction skips (does not
  proceed) when the GPU advisory lock is unavailable. Multi-window: one persistent timeline SSE
  (`turn_appended`, `thread_started`, `thread_recalled`, `task_completed`) — Plan C.

## 13. Testing

Backend (`/Volumes/4TB-BAD/Halbert/.venv` only — the miniconda `python` lacks
`pytest-asyncio`): transactional save + append; FTS punctuation (`smb.conf`, `what's`);
alias canonicalisation; segmenter rules (detour, gap-only, gap+shift, anaphora); strong/weak
match thresholds; hint builder text; meta-tools inline (no loop increment); **e2e: two
`/message` calls, the second sees the first**; pause → grace → close → receipt indexed;
reopen on strong match; merge; interleaved two-`process()` calls keep their session ids;
`num_ctx` present in chat and stream payloads; RESPONDING prompt contains the receipt; OSC
parser split-sequence and interleaved-echo; ETX timeout on a pool block; reaper never kills an
attached user shell; two PTY consumers both receive every byte; replay on attach; redaction
patterns; stage-into-shell refused when not at prompt; background completion appends the
notification row and sets `unread`.

Frontend (vitest): timeline load with roles and day dividers; thread events → single chip;
`TerminalTile` replay-on-mount; tile-per-block with a reused session id; frozen block after
reuse; `StatusLight` renders each state with shape + glyph + text; ContextPill is a button.

Browser (Playwright against a live backend): tile from message 1 survives message 2 and a
reload; off-topic message → no visible change except the sticky label; a later reference →
chip appears and the answer cites the date; `prefers-reduced-motion` → no running animations;
`forced-colors: active` screenshot of the five light states; Tab into a live tile → Ctrl+\`
returns focus; Ctrl+B inside a tile does not toggle mode.

## 14. Scope and sequencing

One design, three implementation plans, in order:

- **Plan A — conversation floor and hidden threads.** §4–§8, §11 timeline/chip/live regions,
  §12 lock, `num_ctx`, migration and deletions, the blank-tile fix and terminal persistence
  per turn (so tiles stop vanishing). Ends with the e2e "second message sees the first" test
  green and "Samba six weeks ago" working on a fresh install.
- **Plan B — terminal sessions, blocks, watched shell, pool, tasks column, light.**
  §9.1–9.3, 9.5–9.9 (the Tasks column replaces `TerminalAccordionDock`; *Your shell* region),
  the StatusLight and keyboard/a11y work, redaction, stage-into-shell, token fixes.
- **Plan C — background, proactive, multi-window.** §9.4, §10, the timeline SSE, timeline
  search (`/timeline/search?q=`, results are turn anchors), thread export.

Deferred to a later design (spec 2): sub-agents as hidden child threads (`parent_thread_id`
exists for it; in the UI a sub-agent is a task card whose body is its steps and receipt); memory index/notes tools; the admin typing into agent sessions and sudo into
agent commands; tabs for user shells; an OS-sandboxed agent pool; a semantic recall tier via
Haloysius memory_v2; opt-in LLM-authored 9-heading summaries (the `compact_boundaries` table
and tick hook ship in Plan A, default off); the Dream Cycle; "reply here" on an old turn.

## 15. Decisions log

Founder: hybrid thread brain; day dividers only; composer staging plus "stage into my shell";
user shells kept and watched; agent reuses idle terminals; notifications as subtle indicator
lights with fill/outline; multi-task secondary; no session list; the right column lists
**tasks** (Running / Finished), not terminal sessions — terminals are wrapped in tasks, and
the task model follows Claude Code's background-task pattern (§9.5a). Task/terminal line
(confirmed by the founder 2026-08-26): a task is a unit of work with a
lifecycle and a result that runs outside or outlives the turn; a terminal is a place work
happens (session) or a record of it (block); a task owns 0..n blocks; the admin's shell is
not a task.

Routine decisions made in this document (say so if any is wrong): deterministic recall on
strong match, model tool for weak; `paused` with a grace window instead of hard close; no
manual thread shortcut; FTS5-only index, no new Chroma collection; user shells unsandboxed,
pool keeps today's posture; PTY-backed pool with OSC 133 markers rather than a pipe-backed
shell (one parser for both kinds, live tile for free); minimal notify-only background mode in
scope because the founder's long-running-task ask needs it; proactive findings as paused
threads in the timeline; agent never types into user shells in v1; blocked light is vermilion
with Send demoted; `store_interaction` off the agent path; Haloysius line only after the grace
window and only for threads ≥ 3 turns; the 2 h gate marks stale, never closes on its own.
