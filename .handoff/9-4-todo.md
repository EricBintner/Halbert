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
