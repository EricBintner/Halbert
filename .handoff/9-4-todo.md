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

### C3 — Aggregate StatusLight in the top bar ✅ DONE (`733f408c`)

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

### C4 — Label the elision ✅ DONE (`733f408c`)

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

### C5 — Mount `NodeFleetCockpit` ✅ DONE (`733f408c`, at `/bodies`)

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

**Investigated 2026-09-04, not fixed.** Two dead ends ruled out, so the next
person starts ahead of where I did:

* **It is not a misfire.** `job_defaults` already sets
  `misfire_grace_time: 60` (`scheduler/executor.py:196`) — far more slack than
  a 0.3 s schedule needs.
* **The likely contributor is teardown.** Both the `executor` and
  `guarded_executor` fixtures end with `ex.stop(wait=False)`
  (`tests/test_scheduler_executor.py:70`). Eleven tests in the file each start
  a `BackgroundScheduler` with its own `ThreadPoolExecutor`, and none waits for
  the previous one to finish shutting down. In a full-suite run that is a
  growing pile of half-stopped schedulers competing for the same CPU as five
  thousand other tests.

Whoever takes this: reproduce **under load**, not in isolation — it has never
failed alone — and try `stop(wait=True)` in the fixtures before touching the
test's timings. Lengthening a timeout makes the symptom go away without
establishing what was slow, which is how a flake becomes permanent.

**Tier: sonnet · Effort: med.** Task chip: `task_b28f415d`.

### D2b — `module_invoke` StrictMode flake (frontend)

**What.** `hooks/useAgentStream.strictmode.test.tsx`, "records one module
invocation per module_invoke event", fails intermittently in full parallel runs
and has never failed in isolation.

**Why it matters.** Same reason as D2, and it is now a **second sighting across
two sessions** — which is what promotes it from noise to a defect.

**Where to start.** `useAgentStream` batches streamed text through
`requestAnimationFrame` and commits once per frame, and holds buffers in module
state. Either module state leaking between test files, or an assertion that
depends on a frame having been committed.

**Tier: sonnet · Effort: med.** Task chip: `task_a1d8024f`.

### D3 — Stale ROADMAP status rows ✅ DONE (LEDGER-1 by a concurrent session at `a3f9adea`; TERM-1 here)

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

## E. The change ledger — what six review rounds left

*Added 2026-09-04 by the session that built `LEDGER-1`, and relabelled from D to E on merge: two sessions appended a section D to the same file on the same day, so `D1` named two different items. Its own items are now `E1`–`E9`; nothing outside this file referenced them. Sections A–C came from the
config-continuity and CLI threads; this is the memory thread, which those explicitly
do not cover. Where an item is already in A–C it is cross-referenced, not restated.*

**Read this first if you are picking up any D item.** The ledger's value is entirely in
being trustworthy, and the fastest way to destroy it is a plausible-looking entry nobody
can falsify. Six review rounds produced one rule that outranks the rest: **a reason is
recorded at the instant of the write or it is `UNRECORDED` forever.** No pass may fill it
in afterwards, no model may infer one, and no code may substitute something reasonable.
`MEM-06` states it; `state_store.record_state` enforces it by making `reason` and `actor`
keyword-only with no default. If a D item ever seems to want a backfill, that is the sign
the item is wrong, not the rule.

### E1 — `run_command` is the last real hole

**Cross-reference: this is §A1.** Do not plan it twice. Recorded here only so the ledger
thread's own inventory is complete: it is the largest remaining gap in the promise, and
`ROADMAP.md`'s `LEDGER-1` row now names it as such. A config changed through the terminal,
by a package manager, or by a service rewriting its own file is still invisible.

### E2 — Diff-apply records on a route production cannot reach

**What.** `dashboard/routes/agent.py`'s diff-apply path records both planes correctly, and
production never gets there: the only production writer of a pending diff sets
`"file_path": None` (`agents/state_machine.py:3075`, "filled by frontend or tool context"),
and `_apply_target` rejects a diff with no path. The recording is exercised only by tests.

**Why it matters.** It is a fully-built, fully-tested feature that has never run, sitting
in a subsystem whose entire point is that its records are complete. Worse, its tests pass,
so nothing signals the gap — the failure mode this thread kept finding, in its most
comfortable disguise.

**Where.** `agents/state_machine.py:3075` (the `None`), `dashboard/routes/agent.py`
`_write_file` / `_apply_target`, `halbert_core/tests/test_provenance_remaining_write_paths.py`
`TestDiffApplyProvenance`.

**Definition of done.** Either a production diff carries a real `file_path` and a test
drives the route the way production does; or the recording is deleted as dead code and the
`LEDGER-1` row stops listing diff apply as a write path. **Deciding which is the work** —
do not wire it just because it is wireable.

**Tier: sonnet · Effort: med.** Depends on: nothing. If the answer is "delete", **fable · med**.

### E3 — Erasure cannot reach the approver's own copies

**What.** `forget_request` clears the reason from the ledger and erases the matching audit
records. The approver's words also live in `findings.db` under
`proposals.execution_result`, and in the approval decision history. Neither is reached.
`ERASURE_LIMITS` (`continuity/provenance.py`) names both, and the `POST /api/state/forget`
response returns that text verbatim — so the product is honest about the gap, which is why
this is a todo and not a defect.

**Why it matters.** "Forget that" is a privacy affordance. Honest-about-the-gap is the
right interim state, but the gap is real: a person who asks Halbert to forget why they
changed something has that sentence survive in two other stores.

**Where.** `continuity/provenance.py` (`forget_request`, `ERASURE_LIMITS`),
`findings/proposal_generator.py` (`_record_result`, which persists `execution_result`),
`approval/engine.py` (decision history).

**Definition of done.** Either `forget_request` reaches both stores and `ERASURE_LIMITS`
shrinks accordingly, or a ratified decision says approval history is deliberately exempt
(it is arguably a governance record, not a private one) and `ERASURE_LIMITS` says *that*
instead of merely listing them.

**Tier: opus · Effort: high.** This is a privacy contract, not a fan-out. The
implementation is small; deciding whether an approval's justification is the user's to
delete is the job. Depends on: nothing.

### E4 — Nothing retires a row for a file that no longer exists

**What.** `invalidate_state` has no production caller. The watcher's `DIGEST_ABSENT`
handling covers watched paths *going forward*; nothing retires rows already open. A
`file:` row stays open and projectable forever, whatever happens to the file.

**Why it matters.** It is the difference between a ledger and a graveyard. It also feeds
the vault: `VaultProjector` enumerates via `current_state()`, so a stale row becomes a
confident note about a path that is gone. This was not theoretical — before the 2026-09-03
cleanup, all 80 open `file:` rows pointed at paths that did not exist, and asking Halbert
what it remembered about ssh returned twelve pytest temp directories.

**Where.** `continuity/state_store.py` (`invalidate_state`), `continuity/vault.py`
(the enumeration and its docstring, which already flags this), a new CLI command
alongside `vault-rebuild`.

**Definition of done.** A `halbert ledger-sweep` that closes rows whose `file:` subject no
longer exists, with an explicit reason (`"sweep: file no longer on disk"`) and a `--dry-run`
that prints what it would close. **Not** a liveness check inside the projector: that puts
filesystem I/O into something whose stated invariant is being a pure function of the
ledger, and a permission-denied stat is indistinguishable from absent for exactly the
`/etc` files this exists for.

**Tier: sonnet · Effort: med.** Depends on: nothing.

### E5 — `_write_txn` distinguishes two errors by matching a message string

**What.** `BEGIN IMMEDIATE` raises `sqlite3.OperationalError` both for a nested
transaction (a borrowed `conn=`) and for a busy database. Conflating them lost data
silently — a write reported as recorded and gone on close — so `state_store.py:403` now
re-raises unless the message contains `"within a transaction"`.

**Why it matters.** It is correct today and fragile by construction. SQLite could reword
that message; the code would then treat a nested transaction as a busy database and start
raising on the borrowed-connection path that `StateStore(conn=...)` is documented to
support. A string comparison is standing in for an error code.

**Where.** `continuity/state_store.py:394-404`, with the regression tests in
`tests/test_state_store.py::TestABusyDatabaseIsNotABorrowedTransaction`.

**Definition of done.** On Python 3.11+, `sqlite3.Error.sqlite_errorname` gives
`SQLITE_BUSY` / `SQLITE_ERROR` directly — verified absent on this interpreter (3.10). So:
use the error name where available and fall back to the string, with a test that pins both
branches. Or record a decision that Halbert's floor moves to 3.11 (`ENV-01` is already open
on exactly that question) and use the attribute unconditionally.

**Tier: sonnet · Effort: med.** Depends on: `ENV-01` if the clean version is wanted.

### E6 — `state_dir()` ignores `HALBERT_DATA_DIR`

**What.** `utils/paths.py`'s `state_dir()` reads only `XDG_STATE_HOME`. Its siblings
`data_dir()` and `log_dir()` both honour the `HALBERT_*` override. So two instances sharing
a `HALBERT_DATA_DIR` still share one state directory.

**Why it matters.** `CFG-1` is the row that says there is one config and data story. This
is the same bug the ledger path had before `b343171d`, in the one resolver nobody fixed.

**Where.** `halbert_core/utils/paths.py`, plus whatever writes under `state_subdir(...)`.

**Definition of done.** `state_dir()` honours `HALBERT_STATE_DIR` then `HALBERT_DATA_DIR`
then XDG, matching its siblings; a test asserts two instances with different
`HALBERT_DATA_DIR` values get different state directories.

**Tier: fable · Effort: med.** Mechanical, and the definition of done is checkable.
Depends on: nothing. Check callers first — something may rely on the current path.

### E7 — The Doubt Queue

**Status: deferred, and the case is stronger than when it was first deferred.**

It curates contradictions produced by the dream cycle, and the dream cycle is **cut**, not
deferred — of its two remaining checks, duplicate open triples is now structurally
impossible (the partial unique index enforces one open row per key at the storage layer, so
a job to detect what the schema forbids has no work), and file-digest drift duplicates what
the freshness/PROBE path is for. Building a curation UI against content nothing produces is
the "beautiful empty vault" failure with a nicer frontend.

**Do not start this without first answering: what produces a contradiction?** If that has a
real answer, it is a new design, and this entry is the wrong description of it.

**Tier: opus · Effort: xhigh** *if the premise is ever re-established.* Otherwise leave.

### E8 — The Fable review is owed on seven dimensions

**What.** A Fable-tier review of the ledger work was commissioned and 14 of its 15 agents
failed on usage credits. Only `recall-abstention` completed, and its own verifiers did not
run — its single finding was verified by hand instead, and was real (a failed ledger read
rendered as "nothing was recorded").

**Why it matters.** Seven dimensions were never reviewed by that tier: provenance
integrity, data loss, concurrency, erasure honesty, vault projection, test quality, and
coherence. Later self-review at a lower tier covered the same ground and found 42 confirmed
defects across two rounds, so the work is not unreviewed — but it has not had the tier that
was asked for.

**Where.** The workflow can resume from cache: the completed dimension replays instantly
and only the failed agents re-run, so a top-up costs one run rather than two.

**Tier: fable · Effort: high.** This is the review itself, not code. Budget for the finding
count: the two lower-tier rounds produced 13 and 29 confirmed defects respectively.

### E9 — Two items deliberately cut, recorded so nobody re-plans them

Both were cut **on evidence**, not on schedule, and the evidence is in
`.handoff/NOTE-MEMORY-STEPS-CUT-AND-DEFERRED-2026-09-02.md`:

- **Micro-compaction (was step 11a).** Nothing in production emits a tool_result block in
  either vocabulary, so the plumbing work would leave `micro_compact` truncating zero
  blocks while *looking* live. **See also §B5**, which reaches the same fold-it-in-or-cut-it
  decision from the config-continuity side — the two should be decided together, once.
- **Epistemic thresholds (was step 11b).** `grep -rn '\.composite' halbert_core/` returns
  zero hits: the proposed 0.85 / 0.40 are thresholds on a knob nothing reads. Two of the
  design doc's numbers could not have come from the scorer they name — the Phase-72 floor
  gate makes 0.31–0.43 a dead band, and 0.85 is unreachable with `cross_reference_count=0`.

**Tier: n/a.** Reopen only with new evidence, and put the evidence in the note.

---

## F. Sequencing

Dependencies first, then value. Nothing here is blocked on anything outside
this document except the two founder answers called out below.

| # | Item | Tier | Effort | Blocked by |
|---|---|---|---|---|
| 1 | **A2** CAS refusal policy | opus | med | **founder answer** |
| ~~2~~ | ~~**D3** stale ROADMAP rows~~ | — | — | **done** |
| 3 | **A3** reconcile the backup stores | sonnet | high | — |
| 4 | **B1** `GET /api/state/recent-configs` | sonnet | med | A3 |
| 5 | **B2** `RecentConfigsDock` | sonnet | high | B1 |
| 6 | **B3** rollback off the ledger | sonnet | high | A3 |
| 7 | **A1** `run_command` on the ledger | opus | xhigh | — |
| 8 | **C1** `YourShellRegion` | sonnet | high | — |
| 9 | **C2** retire `/terminal` | fable | med | C1 |
| ~~10~~ | ~~**C3** aggregate StatusLight~~ | — | — | **done** |
| ~~11~~ | ~~**C5** mount the cockpit~~ | — | — | **done** |
| 12 | **D1** safety read-only defaults | opus | med | — |
| 13 | **B4** prompt hydration | opus | high | — |
| ~~14~~ | ~~**C4** label the elision~~ | — | — | **done** |
| 15 | **B5** micro-compaction: fold or cut | sonnet / fable | med | — |
| 16 | **D2** scheduler flake | sonnet | med | — |
| 17 | **D4** the split config directories | fable | med | **founder answer** |
| 18 | **D5** two-machine hardware run | opus | high | — |

### The fan-out, mostly spent

Items 10, 11 and 14 — the aggregate light, the cockpit mount and the elision
label — were done sequentially on `feat/todo-obvious` and are struck through
above. **C1** (the shell region) is the one that remains, and on its own it is
not a fan-out.

Do **not** fan out **A1**, **A2**, **B4** or **D1**. Each is a judgement about
an invariant, and the failure mode of getting one plausibly-but-wrongly right
is exactly what this thread of work spent its time correcting.

### Section E is sequenced on its own terms

The table above covers A–D. **Section E (the change ledger)** arrived from the
memory thread with its own ordering and its own reasoning, including two items
its author deliberately cut. Ranking those against these would mean overriding
a judgement I did not make and cannot see the working for. Read E in its own
order; the one item that appears in both threads is **E1**, which *is* **A1**
and is cross-referenced rather than restated.

### The two founder answers, collected

1. **A2 — what should a refused write offer?** Today: refuse and explain,
   everywhere. Recommendation: the model never overrides (it cannot see the
   other change); the person may, from the editor, with the current content
   shown beside theirs.
2. **D4 — the conversations and backups under `~/.config/halbert` are now
   unread.** Move them to the Library path, or leave them?

---

## G. What this thread already landed, for context

So that whoever picks this up knows what has *just* changed underneath the
code they are reading.

| Merge | What |
|---|---|
| `844bff4a` | CLI in the conversation: pool on in production, block + promotion events, the tool card finds its block, arguments render as fields |
| `9418e106` | Look before you write: `write_guard`, `_write_file` on the record, `expected_sha256` on the editor, one `config_dir`, `turn_id` on the ledger |
| `c8ce601c` | The watcher runs on this body: platform-aware registry, one finder, macOS registry verified against this machine (135 files) |
| `a8227d72` | Roadmap correction |

And the two review documents this todo descends from:
`.handoff/REVIEW-CONFIG-CONTINUITY-2026-09-04.md` (16 findings, §15 records two
corrections to itself) and `.handoff/STRATEGY-CLI-IN-CONVERSATION-2026-09-04.md`
(§15 the audit of the build, §17 the final state).

**One thing to carry forward more than any item above.** The recurring defect
on this thread was not bugs — it was *tests that could not fail* over features
that could not run. Five separate instances. If you inherit a green suite here,
that is not yet evidence.

---
