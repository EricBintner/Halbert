# Continuous Conversation & Watched Terminals — Handoff

**Date:** 2026-08-26 (end of the Fable session)
**Branch:** `feat/continuous-conversation` — worktree at
`~/.config/superpowers/worktrees/Halbert/continuous-conversation` (created from `01ed50c`).
**Read first:** this file → the spec → Plan A's header.

**Update 2026-08-26, later the same day:** the amendments below are no longer a manual
step — they are folded into the task text (Plan A is now 33 tasks) and the execution run
has been launched. See "Where this actually stands" at the end of this file.

## What exists now

| Artifact | Path | State |
|---|---|---|
| Review of what was actually built (terminals, orchestrator) | `.handoff/TERMINAL-AND-ORCHESTRATOR-REVIEW-2026-08-26.md` + `-APPENDIX.md` (A: code + OSS audits), `-APPENDIX-B.md` (continuity patterns in Claude Code / Warp / Halbert's dormant modules), `-APPENDIX-C.md` (five critics vs design v0) | committed `01ed50c` |
| **Design spec v1** (approved by the founder, folded through five adversarial reviews) | `documentation/design/continuous-conversation-and-watched-terminals-2026-08-26.md` | committed `01ed50c` |
| **Plan A** — conversation floor + hidden threads (33 tasks, TDD, full code, amendments folded in) | `.handoff/CONTINUOUS-CONVERSATION-PLAN-A-2026-08-26.md` | amended `ab17736`; **executing** |
| Plan A binding contracts (schema, signatures, events, tools, API, ordering) | `.handoff/plan-a-exec/plan-a-contracts.md` | this commit |
| Plan A verifier verdict (dry-run applied to a scratch worktree: backend 1265 pass / 5 fail = 4 baseline + 1 fixture; frontend 88/88; tsc clean) | `.handoff/plan-a-exec/plan-a-verifier-verdict.md` | this commit |
| Plan A tasks as JSON (33 entries; the workflow reads task text from per-task files split out of this) | `.handoff/plan-a-exec/plan-a-tasks.json` | regenerated `ab17736` |
| Execution workflow (implementer → spec review → quality review per task, fix loops, hard stop on BLOCKED, final whole-branch review) | `.handoff/plan-a-exec/execute-plan-a.js` | reworked `6c90faa`; **launched** |
| The planner / fixer workflow scripts that produced Plan A (for regeneration) | `.handoff/plan-a-exec/plan-a-writers.workflow.js`, `plan-a-fixers.workflow.js` | this commit |

No application code has changed on this branch. Every change so far is documentation and
tooling. Baseline in the worktree: backend 1119 passed / 4 pre-existing failures
(`tests/test_tool_calling_bridge.py`, `tests/test_phase_d_integration.py` — model-client
vision fallback, unrelated); frontend 45/45; `npx tsc --noEmit` clean; `node_modules`
installed in the worktree's frontend.

## Founder decisions taken today (all recorded in the spec §15 and in memory)

1. Hybrid thread brain: zero-LLM signals hint, the model decides via `new_thread` /
   `recall_thread`; deterministic auto-recall on a strong match.
2. **Day dividers only** in the timeline — no titled thread dividers, no session list; one
   "pulled in: X · date" chip at most.
3. Commands staged in the composer **plus** a "stage into my shell" action.
4. User shells stay and are **watched** by the AI (OSC 133 block boundaries); agent
   **reuses** an idle terminal; the terminal is "generally owned by the agent".
5. Notifications = subtle indicator light with fill/outline (ADA); notify-only, no
   autonomous continuation.
6. The right column lists **tasks** (Running / Finished N › / Clear), not terminal sessions,
   following Claude Code's background-task model (spec §9.5a); the admin's shell is its own
   pinned "Your shell" region, never a task.

## What is left, in order

### 1. Execute Plan A (next session)

Preconditions: the SourcePrep embed job (`scripts/staged_knowledge_embed.py --stage 3`) may
still be running — never call `mcp__prep__*` tools or start builds while it is. Use the
worktree, not `/Volumes/4TB-BAD/Halbert` (other sessions edit `main` concurrently).

Option A — the prepared workflow (subagent-driven, sequential, reviewed):

```
Workflow({
  scriptPath: "<worktree>/.handoff/plan-a-exec/execute-plan-a.js",
  args: {
    worktree: "/Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation",
    planPath: ".handoff/CONTINUOUS-CONVERSATION-PLAN-A-2026-08-26.md",
    taskDir: "<dir of one A1.md ... A20.md split from plan-a-tasks.json>",
    baseSha: "<git rev-parse HEAD in the worktree before starting>",
    startAt: 0,
    mechanical: ["A1","A1b","A2","A3","A4","A7","A8","A10","A12c","A12d","A14","A15","A16","A19"],
    context: "<the spec §3–§8 summary>",
    tasks: [{id, title} for each of the 33 tasks]
  }
})
```

The task *text* is not passed through args — 630KB of markdown would have to sit in the
launching context. Split `plan-a-tasks.json` into one `<id>.md` per task, point `taskDir`
at that directory, and every agent reads its own task file. `mechanical` lists the task ids
whose implementer and fixer agents run on the cheap model tier; reviewers always inherit
the session model.

It stops and returns `{stoppedAt, reason}` when an implementer reports BLOCKED /
NEEDS_CONTEXT or a review cannot be resolved; fix the cause, then relaunch with
`startAt: <index>` (or `resumeFromRunId`).

Option B — by hand with `superpowers:executing-plans` (batch with checkpoints). Each task
already contains the failing test, the exact commands, the expected output, and the commit.

Definition of done for Plan A (spec §14): `tests/test_thread_e2e.py` green ("second message
sees the first", `new_thread` pauses, `tick()` closes with an indexed receipt, a later
"as we did…" message gets a `Pulled in:` hint with no tool call); frontend timeline renders
stored turns with roles and day headers; the dropdown/"New Conversation"/session footer are
gone; terminal tiles from earlier turns no longer vanish; the blank-tile bug is fixed;
full suites green except the 4 baseline failures; `tsc` clean; literal-colour ratchet
unchanged.

### 2. Plan B — terminal sessions, blocks, watched shell, pool, tasks column, light

**Status update (2026-09-02, SONNET-05/DOC-01):** written
(`.handoff/CONTINUOUS-CONVERSATION-PLAN-B-2026-08-27.md`) and executed —
merged `0ba316b2`, B1–B22 — since this section was written. It landed as
primitives, not wiring: see the status update on that plan doc, or
`.handoff/HANDOFF-STATE-OF-WORK-2026-09-01.md` §6.4, for what actually
reaches production. The rest of this section is kept as the original spec
pointer, not a live TODO.

Not yet written. Write it with the same method (contracts → four planners → verifier) from
spec §9.1–9.3, 9.5–9.9 and §11's terminal/a11y items. Its contracts must define:
`streaming/shell_integration.py` (bash `--rcfile` / zsh `ZDOTDIR` bootstrap emitting OSC 133
A/B/C/D + OSC 7; byte-state-machine parser carrying partial sequences; alt-screen and
password-prompt detection; `remote` tagging), `streaming/agent_pool.py` (`TerminalPool`,
PTY-backed `bash --norc --noprofile`, ECHO off, markers, ETX-then-kill timeout, fallback to
the subprocess path at cap), `TerminalSessionManager` kinds/caps/TTLs (user never reaped
while attached; user shells **unsandboxed**; pool keeps today's `run_command` posture),
`PTYSession` single reader task fanning out to all queues + replay on attach,
`terminal_blocks` / `terminal_sessions` tables + `messages.origin='terminal'` ledger rows
(redacted via `streaming/redact.py`, capped digest in the hint, `terminal_blocks` fetch
tool, per-session unwatched toggle), `POST /api/terminal/sessions/{id}/stage` (only at an
empty prompt), tile = block / card = task (`TerminalAccordionDock` → Tasks column with
Running / Finished / Clear + "Your shell" region), `StatusLight` primitive (5 states, token +
fill/outline + glyph + text, one 220 ms transition, forced-colours safe), PTY key ownership
(Ctrl+\` escape hatch, Cmd+B guard), `Sheet` below `md`, token fixes (`TerminalTile.tsx:181`
hex, `:199` violet, `check_literal_colors.py` `-[#hex]` pattern), and the tests in spec §13.

### 3. Plan C — background, proactive, multi-window

Not yet written. From spec §9.4, §10, §12: `run_command(background=true)` + `tasks` table
mirroring Claude Code's model (§9.5a) + `task_output`/`task_stop` tools + `origin=task-notification`
rows (notify-only); proactive findings and the morning report as `origin=proactive` rows in
paused threads gated by the dial; persistent timeline SSE for multi-window;
`/timeline/search?q=`; thread export.

### 4. Spec 2 (later design)

Sub-agents as hidden child threads / task cards (`parent_thread_id` exists); memory index +
notes tools; user typing into agent sessions and sudo into agent commands; tabs for user
shells; OS-sandboxed agent pool; semantic recall tier via Haloysius memory_v2; opt-in
LLM-authored summaries (the `compact_boundaries` table lands in Plan A, default off); Dream
Cycle; "reply here" on an old turn.

## Things worth knowing before touching code

- The audit's four load-bearing facts, re-verified by hand: `routes/agent.py:686` passes no
  `conversation_history`; `useAgentStream.ts:523` mints a session per message;
  `AgentChat.tsx:666` renders only the last turn's assistant block; `TerminalTile.tsx:62-133`
  never replays `session.output` after its async mount.
- Physical column `conversation_id` **is** the thread id (contracts §1) — do not rename.
- `session_id` stays per turn for cancel/confirm/streaming; `thread_id` is added to
  `StateContext` and used for messages, receipts, somatic blocks, diff proposals.
- The hint goes at the **tail** of the prompt (Ollama truncates the head); `num_ctx` is
  computed once per model (Plan A task A10).
- `memory.store_interaction` comes off the agent path (receipts + the Haloysius line replace
  it) — otherwise every turn becomes a global memory once the vector adapter is fixed.
- No new Chroma collection: FTS5 (`porter unicode61` + alias table) is the recall index
  (the-being §9 keeps Chroma eval-only).
- Legacy stores: `routes/conversations.py` (JSON, `~/.config/halbert/conversations`) and the
  JSON `ConversationStore` (`~/.halbert/conversations`) are migrated once and deleted in
  A12; `agents/handlers/*` is dead code and deleted.
- Tests must run with `/Volumes/4TB-BAD/Halbert/.venv/bin/python` from `halbert_core/`.
- Commit messages: subject + body only, no Co-Authored-By or generated-with trailers; use
  pathspec adds (concurrent sessions leave unrelated files dirty on `main`).

## Memory notes written this session (in `~/.claude/projects/-Volumes-4TB-BAD-Halbert/memory/`)

`halbert-terminal-orchestrator-audit-2026-08-26.md`, `halbert-continuity-direction-2026-08-26.md`,
`halbert-terminal-direction-2026-08-26.md` (the founder's decisions, the OSS repo locations and
SourcePrep ids, and how to apply them).

## Where this actually stands (2026-08-26, later the same day)

The fixer workflow that was still running when the section above was written **had
finished its Fix phase**: all three agents wrote their amended parts to that session's
scratchpad (`plan_S_amended.md`, `plan_MD_amended.md`, `plan_F_amended.md`) and were
stopped before returning them, so the assembler saw an empty result file, printed
"fixers not finished", and committed the un-amended 27-task plan with the amendments left
as a header section.

Those amended parts were recovered and assembled. Plan A is now **33 tasks** with every
verifier issue and coverage gap folded into the task text — there is no amendments section
to apply while executing. The six added tasks:

| Task | What it closes |
|---|---|
| A6c | `ThreadManager.merge_back` + the grace-window `resume_thread` merge (spec §5 "Merge") |
| A6d | Retraction notes — hidden system rows the next turn's hint surfaces (spec §6) |
| A8b | Conversation budget bucket for six raw turns + the receipt slot in the assembler (spec §7) |
| A9d | `tools_supported` on the LLM clients; the no-tools continuity preamble variant (spec §7) |
| A11b | `POST /api/agent/message/{id}/redact` + `store.redact_message` (spec §5 "Forget") |
| A17b | The per-turn "Forget this" control in the timeline |

Caveat carried in the plan header: those six were written *after* the sandbox dry-run, so
unlike the other 27 their code has never been executed. Their stated expected outputs are
targets, not measurements.

Commits on the branch: `ab17736` (amended plan + regenerated task JSON), `6c90faa`
(execution script reads task text from disk, cheap tier per task). The execution run was
launched from `6c90faa` with `startAt: 0` and the mechanical list above.
