# 9-4-TODO — everything left on this thread of work

**Date**: 2026-09-04
**Covers**: the work arising from `.handoff/REVIEW-CONFIG-CONTINUITY-2026-09-04.md`,
`.handoff/STRATEGY-CLI-IN-CONVERSATION-2026-09-04.md`, and the six merges that
followed them (`844bff4a`, `9418e106`, `c8ce601c`, `a8227d72` and parents).
**Not covered**: the rest of `ROADMAP.md`. That document is the planning spine
and already holds twenty-one workstreams; this one is the todo for *this*
thread, cross-referenced to it rather than duplicating it.

---

## 0. How to read this

Each item states **what**, **why it matters**, **where**, and a **definition of
done** specific enough to argue with. Then a tier and an effort level.

### The tiers

| Tier | When |
|---|---|
| **fable** | Mechanical and specified. Renames, doc corrections, deleting a routed page, moving a call site. No judgement required; the definition of done is checkable by grep. |
| **sonnet** | Ordinary implementation against a clear spec, with tests. The shape is decided; the work is doing it correctly and not breaking neighbours. |
| **opus** | Design judgement, a cross-cutting invariant, or a safety property. Anything where getting it *plausible* is easy and getting it *right* is the whole job. |
| **ultracode** | Fan-out. Several genuinely independent pieces that want doing at once, each with its own verification. |

### The effort levels

| Effort | Meaning |
|---|---|
| **med** | An afternoon. One or two files, tests obvious. |
| **high** | A day. Several files, a seam to design, neighbours to check. |
| **xhigh** | Multi-day. Cross-cutting, or the correctness argument is the hard part. |
| **max** | Reserve for work where being wrong is expensive and the verification is itself a project. |

### One standing instruction for whoever picks these up

Every test written on this thread was checked by **breaking the thing it
guards** and watching it fail. That discipline exists because this codebase
has repeatedly shipped green suites over unreachable features:
`ToolExecutionCard`'s tests supplied their own props; an "e2e" promotion test
never ran a command; a vocabulary assertion could not see the word it forbade.
Assume any test you did not watch fail is not testing what its name says.

---

## A. The write path — finishing what Phase 0 started

### A1 — `run_command` is outside the ledger entirely

**What.** `ToolExecutor._write_file` now records on both planes and refuses a
write to a file that changed underneath it (merged `9418e106`). `run_command`
does not. A model that runs `echo "1.2.3.4 host" >> /etc/hosts`, or
`sed -i`, or `defaults write`, or `launchctl load`, changes the machine and the
change ledger holds nothing.

**Why it matters.** LEDGER-1's premise is that the ledger answers *why any
config is the way it is*. `run_command` is the most-used tool in the registry.
Every finding in the config-continuity review about empty surfaces has this as
a contributing cause, and the write guard's protection is trivially
side-stepped by phrasing the write as a shell command instead of a tool call.

**Where.** `halbert_core/tools/executor.py:_run_command`; the pool path in
`streaming/agent_pool.py` already produces a block with the command text.

**The hard part, and why this is not sonnet.** You cannot record "what file
changed" from a command string without either (a) parsing shell, which is a
losing game, or (b) observing the filesystem. (b) is the right answer and it
already half-exists: the config watcher notices changes on disk. So the honest
design is probably *not* "make `run_command` record" but "make the watcher's
observation join to the turn that caused it" — the command ran inside a turn,
the watcher fires within seconds, and `current_turn` (added in `f8cd5cad`) is
in scope for exactly that window. That is a design decision with a race in it.

**Definition of done.** A `run_command` that modifies a watched file produces a
ledger row naming the turn, with a reason that does not pretend to be the
model's stated intent unless the model stated one. A `run_command` that
modifies an *unwatched* file is honestly absent rather than silently missing —
`recall_memory` should be able to say "I do not watch that path".

**Tier: opus · Effort: xhigh.** Depends on: nothing. Unblocks: the honesty of
every config surface.

### A2 — What a compare-and-swap refusal should offer

**What.** Today every write path refuses a drifted write and explains. There is
no "overwrite anyway".

**Why it matters.** For `/etc/fstab` the refusal is almost certainly right. For
a dotfile, or for a file the person has *just* looked at in another window, an
unconditional refusal is an obstruction. The safe default was chosen because it
is cheap to loosen and expensive to have skipped — but leaving it forever is a
decision by inaction.

**Where.** `continuity/write_guard.py` returns a `GuardResult` with enough
detail to render a choice; `routes/editor.py` answers 409; `tools/executor.py`
and `tools/write_config.py` return a refusal string to the model.

**Definition of done.** A stated policy, written down, covering: whether the
*model* may ever override (recommendation: no — it cannot see the other
change), whether the *person* may (recommendation: yes, from the editor, with
the current content shown), and whether the answer differs by path sensitivity.
Then the affordance for whichever cases say yes.

**Tier: opus · Effort: med.** The implementation is small; the policy is the
work. **This one needs the founder before it is built.**

### A3 — Reconcile the two backup stores

**What.** `write_config` does `shutil.copy2(path, path + ".bak")` — one
generation, overwritten on every write, dropped inside the system config
directory. `routes/editor.py` keeps timestamped generations under the config
dir with metadata. Review findings **F8** and **F9**.

**Why it matters.** Three consequences, in order of severity. The agent's
second write destroys the rollback point for its first. `.bak` files land in
`/etc/samba/` and similar, outside any store Halbert tracks or prunes. And any
"backup count" surface reports zero for every file the *agent* changed — the
files most likely to need rolling back.

**Where.** `tools/write_config.py:156,180,216` (the writes) and `:62-67` (the
rollback branch that reads `<path>.bak` and must move with them);
`routes/editor.py:91` (`get_backup_dir`).

**Also fix while there (F9).** `get_backup_dir` encodes a path as
`path.replace("/", "_")`, so `/etc/foo_bar` and `/etc/foo/bar` share a
directory. Record the true path in the metadata JSON; the encoding cannot be
reversed.

**Definition of done.** One backup store. `write_config`'s rollback reads it.
Existing `<path>.bak` files are left on disk unread — per the standing rule
there are no users and no migration to write. A test that writes the same file
twice through the agent and restores the *first* version.

**Tier: sonnet · Effort: high.** Depends on: nothing (0c landed, so there is
one config dir). Unblocks: **B1**, **B3**.

---

## B. The config-continuity surface — the original handoff, unblocked

The watcher now runs on this body (`c8ce601c`), so the ledger will accumulate
real `file:` rows for the first time. Everything below was blocked on that and
is not any more.

### B1 — `GET /api/state/recent-configs`

**What.** The read the "Recent & Managed Configs" surface needs: which files
this body has touched, most recent first, each with its last actor, reason,
timestamp, digest and backup count.

**Why it matters.** It is the whole point of the original handoff. It was
blocked twice over — the ledger was empty, and the backup count could not be
answered honestly.

**Where.** `dashboard/routes/state.py`, **not** `editor.py` and **not** a new
`/api/continuity` prefix (review **F15**). `state.py` is already the ledger
read surface (`/why`, `/history`, `/by-request`) and already has the error
contract this needs.

**Definition of done.** The route inherits `state.py`'s contract: **503 when
the ledger cannot be read, never a 200 with an empty list** — "I could not
look" and "there is nothing recorded" are different answers and the module's
own docstring says so. An empty ledger returns `[]` and the *client* renders
"nothing recorded yet", never "no configs are managed". Backup count is honest
after **A3** or absent before it — not zero.

**Tier: sonnet · Effort: med.** Depends on: **A3** for the backup count.

### B2 — `RecentConfigsDock.tsx`

**What.** The surface itself: a list of recently touched configs with relative
timestamps, actor badges and the recorded reason, with two actions per row.

**Why it matters.** This is the founder's original insight — that a system
administrator remembers *files*, not conversations — made real.

**Where.** New component; docked in `Layout.tsx` or `AgentChat.tsx`.

**Definition of done.** "Edit in Monaco" opens `ConfigEditor` for that path.
"Jump to Chat" calls `loadAround(turn_id)` — which **works now**: ledger rows
carry `turn_id` since `f8cd5cad`. An empty state that says nothing has been
recorded yet, in those words.

**Tier: sonnet · Effort: high.** Depends on: **B1**.

### B3 — A rollback that can find the last thing Halbert did

**What.** One-click "Rollback Change" on `DiffBlock.tsx` and on timeline turns.

**Why it matters.** Backups are per-file directories, so "undo the last thing
Halbert did" currently requires scanning every directory and comparing
timestamps. The ledger already *is* the global index: `state_triples` ordered
by `valid_from DESC`, each row carrying `request_id`, `turn_id` and the digest
that was superseded.

**Where.** A read over the ledger plus the reconciled backup store; button on
`DiffBlock.tsx`.

**The trap.** The ledger stores **digests, not content** (this is why
`82f25ff2` refused to render config-diff as before/after). So the ledger says
*what* to roll back to and the backup store must supply the *bytes*. A row with
no corresponding backup must say so rather than offering a button that fails.

**Tier: sonnet · Effort: high.** Depends on: **A3**.

### B4 — Prompt hydration through the seam that already exists

**What.** Review **F14**. The original handoff proposed injecting a continuity
block when the agent is asked about a file. Two corrections stand.

**Why it matters, and what not to build.** The proposed block ended
`Current sha256: 8f1a2b… (verified intact on disk)`. `recall_state` does not
verify anything on disk, deliberately — `82f25ff2`: *"a recall that silently
probed the filesystem would stop being a ledger read while still answering like
one"*. Either drop the clause or make drift a separately labelled line sourced
from a probe that says it is a probe.

**Where.** `AgentPromptBuilder.build_planning_prompt(..., continuity=...)`
already exists, is tested (`tests/test_agent_prompts_continuity.py`), places
the block immediately before `## Current Task`, and has per-voice preambles and
a `tools_supported=False` variant. It currently carries *thread* continuity.
Extend that; do not invent an injection point.

**The judgement call.** Push-hydration partly duplicates `recall_memory`, which
already answers on demand. Injecting on every file mention spends tokens every
turn to save a tool call on some turns. That may well be right for a steward —
but it is a trade, and the original handoff did not acknowledge it. A middle
path: hydrate only when the user's message contains a path the ledger knows.

**Tier: opus · Effort: high.** Depends on: nothing.

### B5 — Micro-compaction: fold it in or cut it

**What.** Review **F11**. The original handoff proposed building micro-
compaction from `open-claude-code`'s `context-manager.mjs`.

**Why it matters.** It is already owned twice. `compact_boundaries` exists in
the conversation schema with the comment *"compaction stays default-off until a
later plan"*, and there is a separate three-tier compression system with its
own routes. Building a third would give Halbert three answers to one question.

**Definition of done.** Either ~30 lines writing into the existing
`compact_boundaries` seam using the truncation rule from the OSS repo
(truncate `tool_result` blocks past a turn boundary, never `text` or
`thinking`) — **or** an explicit cut, recorded, in the manner of `82f25ff2`'s
"Step 9 is CUT rather than deferred".

**Tier: sonnet · Effort: med.** Or **fable · med** if the decision is to cut.

---

## C. The conversation surface — what the CLI work left

### C1 — `YourShellRegion` is written and mounted nowhere

**What.** The admin's own shell, pinned in the tasks column: a real xterm, a
watched/unwatched toggle, an unhooked badge when OSC 133 markers are missing,
and a stage-a-command input.

**Why it matters.** It is the user half of TERM-1. The agent half is real —
the pool produces blocks, commands promote, tasks render. The person's own
shell is a `ShellLauncher` button and nothing else, and the founder's recorded
direction is that user shells *stay* but are **watched by the AI**.

**Where.** `components/agent/YourShellRegion.tsx`; the slot is already there —
`TasksColumn`'s `yourShell` prop, currently filled by `ShellLauncher`.

**The unfinished part.** Its terminal mount point is a bare `div` with a
comment saying *"the parent fills this with an xterm instance"*. No parent
does. Whoever picks this up is writing that parent.

**Definition of done.** A real shell in the right column that the agent can
read blocks from; watched toggle round-trips to the backend; the unhooked badge
appears when the rc files are not installed. `ShellLauncher` stays or is
absorbed — but **the ability to open a shell must not disappear**, which is
what nearly happened when the accordion was deleted.

**Tier: sonnet · Effort: high.** Depends on: nothing.

### C2 — Retire the legacy `/terminal` page

**What.** `pages/Terminal.tsx` is still routed at `App.tsx:120`.

**Why it matters.** `HALBERT-CLEANUP-AND-WIRING-PLAN-2026-08-27` calls it
*"the best single deletion in the frontend"*: it advertises an "AI-enhanced
shell with /explain /dryrun", reports "● Connected to local shell" while
connecting to nothing, and answers every slash command from
`simulateAIResponse` with a hardcoded string after a fake 1000 ms think —
`/fix` returns the same three suggestions regardless of what failed. It is a
page that lies about being connected.

**Where.** `App.tsx:7,120`, `pages/Terminal.tsx`, the `/terminal` nav entry in
`Layout.tsx`, and `SPA_ROUTES` in `dashboard/app.py` (`test_spa_routes.py`
keeps the two in step and will fail if you forget).

**Definition of done.** Route, page, nav entry and SPA allowlist entry gone
together. The real terminal lives in the conversation and the tasks column.

**Tier: fable · Effort: med.** Depends on: **C1**, so the shell has somewhere
to be first.

### C3 — Aggregate StatusLight in the top bar

**What.** TERM-1's last row. `ContextStage` already takes an
`aggregateStatusLight` prop for the mobile sheet toggle; nothing passes one,
and there is none in the desktop top bar.

**Why it matters.** With the tasks column now mounted, a long-running command
is visible only if the right column is open. The aggregate light is how the
machine says "something is running" when you are not looking at it.

**Definition of done.** One light in the top bar reflecting the worst state
across running tasks (`needs_attention` > `error` > `running` > idle), and the
same node passed into `ContextStage` for the mobile sheet.

**Tier: sonnet · Effort: med.** Depends on: nothing (`useTasks` from
`4a862fee` already derives the state).

### C4 — Label the elision

**What.** Strategy doc T7, partially done. `8cb65c85` fixed a short block
printing its output twice; the elision between head and tail is still a bare
`…`.

**Why it matters.** A reader cannot tell "this is all of it" from "there is
more, and I am not showing you". `open-claude-code` gets this right with
`[output truncated at 1MB]`.

**Definition of done.** The host sends how much was elided (it has the full
output; head/tail are slices) and the card renders `… 4,812 lines elided …`.
Requires a field on the completion payload — the frontend cannot compute it
from head and tail alone.

**Tier: sonnet · Effort: med.**

### C5 — Mount `NodeFleetCockpit`

**What.** The all-bodies health view: a grid of paired machines with CPU, RAM,
temperature, uptime and services, with per-card *Inspect* and *Switch active
context*. Written, tested, imported by nothing.

**Why it matters.** The founder's described model is bodies grouped by
identity, switchable per tab. `PresencePill` does the switching; Settings ›
Linked Devices does the management; there is no *see them all at once*.

**Where.** New route (suggest `/bodies`), nav entry in `Layout.tsx`, and the
matching `SPA_ROUTES` entry in `dashboard/app.py`.

**A note on a false lead, so nobody repeats it.** I initially flagged this as
blocked on a commercial decision, having found "Multi-Host Server Fleet
Cockpit" listed as a paid tier in
`documentation/legal/OPEN-CORE-AND-DISTRIBUTION-STRATEGY.md`. **The founder has
confirmed that document is brainstorming and not a constraint.** It is an
ordinary wiring gap. Treat that whole document as unratified unless told
otherwise.

**Vocabulary.** The nav entry and headings use **Body**, not Node — the
alignment doc's terminology table lists node, instance, host-as-noun and
satellite under *avoid*. The component's internal `node_id` field names are
fine; it is the noun on screen that matters. `EntityIdentityCard` was fixed in
`df929ea8`; the cockpit's own strings ("Pair a Satellite") have not been.

**Tier: sonnet · Effort: med.**

---

## D. Found on the way, not fixed

These are not part of any phase. They were noticed while doing something else,
and each one is the kind of thing that stays invisible until it costs a day.

### D1 — Read-only tools default to MEDIUM in `tools/safety.py`

**What.** The safety framework classifies per tool. Measured:

```
read_file           safe        list_directory      medium
recall_memory       safe        read_log_tail       medium
run_command (ls)    safe        get_service_status  medium
                                check_disk_space    medium
```

**Why it matters.** `list_directory`, `read_log_tail`, `get_service_status`
and `check_disk_space` are read-only — they look at the host and change
nothing — and they are rated *above* reading `/etc/fstab`. They are falling
through to a default rather than being classified.

Two consequences. It is noise in whatever consumes risk levels. And it means
the framework cannot serve as the authority for "is this an inspection", which
is the principled source the inspection-grouping work wanted and could not use
(`055aef68` uses an explicit list instead, checked against the real registry by
a test).

**Definition of done.** Genuinely read-only tools classify `SAFE`. Then
`groupInspections` can derive its tier from the framework instead of a hand
list, and the list can go.

**Careful.** Changing a risk level changes auditing and visibility behaviour.
Check every consumer of `RiskLevel` before moving one.

**Tier: opus · Effort: med.** Small change, cross-cutting blast radius.

### D2 — `test_scheduler_executor` real-clock flake

**What.** `test_one_time_job_runs_and_records_outcome` schedules a job 0.3 s
out against the real clock and waits 10 s. It failed twice during full-suite
runs (~5,350 tests) and passed 8/8 in isolation.

**Why it matters.** A suite that fails once in a while for reasons unrelated to
the change under test is a suite people stop reading.

**Definition of done.** Deterministic — either a generous misfire grace or a
controllable clock. Check the neighbours in the same file while there;
`test_timeout_is_enforced_off_the_main_thread` does a real `time.sleep(5)`.

**Tier: sonnet · Effort: med.** A background task chip already exists for this
(`task_b28f415d`).

### D3 — Stale ROADMAP status rows

**What.** Two rows describe a world that changed under them.

- **LEDGER-1** says *"the agent's `run_command` and `ToolExecutor._write_file`
  are outside the ledger entirely"*. `_write_file` was fixed in `9418e106`;
  `run_command` is still true (that is **A1**).
- **TERM-1** says *"TasksColumn/YourShellRegion mounted"* as an open item.
  `TasksColumn` was mounted in `4a862fee`; `YourShellRegion` is still true
  (that is **C1**).

**Why it matters.** LD-1 said "UI cannot complete it" for two days after it
stopped being true, and I nearly planned a week of work around it. A status row
that is wrong is worse than one that is missing, because it is trusted.

**Definition of done.** Both rows split into what landed and what remains, in
the manner LD-1 was corrected in `df929ea8`.

**Tier: fable · Effort: med.**

### D4 — Two config directories still hold live data

**What.** `0c` (`61073752`) made the three resolvers agree, so *new* writes go
to one place. It did not move what is already split: `being.yml`, `models.yml`,
`llm.lock` under `~/Library/Application Support/Halbert`; `backups/`,
`conversations/`, `prep_token` under `~/.config/halbert`. `being.yml.lock`
exists in **both**.

**Why it matters.** After the collapse, everything resolves to the Library
path. So `conversations/` and `backups/` under `~/.config/halbert` are now
**unread** — the data is not lost, it is simply no longer where anything looks.

**The judgement.** The standing rule is *no users, no legacy support: do not
build migrations unasked, leave old data unread, never delete*. That rule was
written for shipped versions and this is the developer's own machine, which may
hold conversations worth keeping. So: **ask before deciding**, and if the
answer is "keep them", it is a one-time move, not a migration path in the code.

**Tier: fable · Effort: med.** Blocked on: a founder answer.

### D5 — The two-machine hardware run

**What.** LD-1's last undone item: pair two real machines and drive a turn
across them.

**Why it matters.** Everything about Linked Devices is tested in-process. The
one thing no test covers is whether it works between two computers on a
network — which is the entire feature.

**Tier: opus · Effort: high.** Not because the code is hard, but because the
first real run of a distributed feature is where the assumptions surface, and
someone has to be able to tell a protocol bug from a firewall.
