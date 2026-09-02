# Memory ecosystem — what was cut, and why

**Date:** 2026-09-02
**Branch:** `feat/ledger-provenance`
**Supersedes** the corresponding rows of `.handoff/HANDOFF-FABLE-MEMORY-ECOSYSTEM-2026-09-02.md`.

Steps 6, 7a, 5b, 8 and 7b are built and committed. Three items in that packet
were **not** built, and two of them should not be. Each verdict below is a
verification result, not a scheduling decision — so nobody re-plans them from
the packet without seeing the evidence first.

---

## CUT — step 11a, "make micro-compaction non-inert"

The packet said: carry `blocks_json` through, add a recency gate, then route
production compaction through `should_compact`.

**The premise is false, and doing it would produce a silent green.**
`grep -rn 'ToolResultBlock(' --include=*.py` over the tree returns exactly one
production hit — `StateContext.add_tool_result_block` (`agents/states.py:324`) —
whose only callers are two tests. Nothing in production emits a tool_result
block in *either* vocabulary: `_tool_block` persists
`{tool, args, result, exit, execution_id, status, error}` with no `type` key
(`state_machine.py:938-946`), while `_truncate_block` matches only a
`ToolResultBlock` or `block.get('type') == 'tool_result'`
(`watermark.py:118-123`).

So after step (1) `micro_compact` would still truncate zero blocks while
*looking* live — exactly the failure mode the packet's invariants exist to
prevent. The work it was meant to do is already done twice elsewhere:
observations are capped at 500 chars (`assembler.py:617-618`) and persisted
block results at 4000 (`state_machine.py:928-929`).

Step (3) is also a deliberate reversal: `assembler.py:1262-1267` states that the
summarisation branch was removed because *the thread receipt is that summary and
a better one*.

**If this is ever revisited**, the real first question is whether block-typed
tool results should exist on the thread path at all — not how to compact them.

## CUT — step 11b, "sweep the epistemic thresholds"

**`grep -rn '\.composite' halbert_core/` returns zero hits.** Nothing in Halbert
reads `MemoryEpistemicScore.composite`, so 0.85 and 0.40 would be thresholds on
a knob attached to nothing, and the first real consumer would change what the
right number is. Reaching the scorer at all needs `haloysius.memory_v2`, which
costs ~3.4 s and pulls torch/transformers into a suite that currently runs 5,332
tests in ~350 s.

Two findings from the attempt are worth keeping, and are the reason this is a
note rather than a silent skip:

- the Phase-72 floor gate at `epistemic_score.py:259-261` makes **0.31–0.43 a
  dead band** — no score can land there, so a 0.40 boundary is arbitrary within it;
- **0.85 is unreachable with `cross_reference_count = 0`**, which is every
  memory Halbert writes today.

So the numbers in the design doc's OQ3 are not merely unmeasured; two of them
could not have been produced by the scorer they name. Leave OQ3 open, and re-ask
it when something actually consumes a composite.

## DEFERRED — step 9, the dream cycle

Two live blockers, one procedural and one empirical.

`MEM-04` is still `pending` founder ratification, and it is the decision that
puts the job on Halbert's APScheduler rather than `haloysius.background`.

More importantly, **there is nothing for it to work on yet.** A read-only query
of the live ledger returned 188 rows: 186 `entity` (93 open) and 2
`content_sha256`, with subjects only `thread:` and `file:`. Not one
`service_status`, `disk_health` or `cpu_load` row. A staleness detector would
have literally no input, and the digest-drift check would have two rows.

The 93 zero-duration `entity` rows are also **one code defect**, not 93 facts:
four loops write a collection into a single-valued key, so each write supersedes
the last. Filed as its own concern below rather than left to surface as 93
identical doubt-queue items.

When it is built, keep it to two checks — duplicate open triples (0 today, but a
real tripwire, since five production paths each construct their own `StateStore`
over one file) and file-digest drift. Drop the staleness class.

## DEFERRED — `_doubt_queue/` and step 10

Zero hits for `doubt_queue` anywhere in the tree. It is step 10, and step 10
does not exist. The vault deliberately does **not** create an empty
`_doubt_queue/` to make a test look complete.

## DEFERRED — step 5c, config-diff reads the ledger

Frontend work. The backend it needs is done: `GET /api/state/why?path=…` returns
`current` and `superseded` with reason, actor and timestamp, and
`/api/state/by-request` joins to the audit record for the diff text.

---

## New concerns found while building

| Concern | Evidence |
|:---|:---|
| Thread-close writes a collection into a single-valued key | `agents/threads.py` records `ran_command` / `file_written` / `entity` in a loop against one `(subject, predicate)`, so each iteration supersedes the last. 93 of the live ledger's 186 `entity` rows have zero duration. The subject should carry the item, or the predicate should be indexed. |
| No turn→request join exists | `grep -n request_id` over `agents/threads.py`, `conversation_sqlite.py` and `receipt.py` returns nothing, and no production caller of `record_file_change` passes `thread_id`. So `state_triples.thread_id` is always NULL, and a user saying "forget that" in conversation has no `request_id` to act on. `POST /api/state/forget` is therefore reachable from the why/config-diff panel but **not** from the timeline. |
| `invalidate_state` has no production callers | Harmless today, but the vault enumerates via `current_state()`, which returns only open triples. The first production caller silently makes those facts unprojectable. Named in `vault.py`'s docstring. |
| The agent's own file write records nothing | `ToolExecutor._write_file` (`executor.py:767-786`) opens, writes and returns a string — no audit, no ledger. `WriteConfig` is never registered on the `ToolExecutor` at all. So "ask the agent to change a config, then ask why" correctly answers *no record*, which will look like a broken tool. The acceptance path runs through the dashboard editor. |
