# OSS-pass-2 remediation — the opus residuals, closed

Branch `fix/remediation-opus-batch-2`, worktree
`.claude/worktrees/remediation-opus-2`, cut from `main` at `749bf9bb`.
**Not merged.** Nine commits, four of them the sonnet batch this branch
absorbed.

The twelve opus packets landed on 2026-09-09 (`55ecef87`). What this batch
covers is the list that handoff called "Left" — plus one gap the sonnet
session escalated to opus rather than force-fit, which turned out to be the
most consequential thing here.

## Baseline

`main` at `749bf9bb` is fully green: **8569 passed, 18 skipped, 6 xfailed,
0 failed** in about five minutes, with

```
cd <worktree>/halbert_core && arch -arm64 /Volumes/4TB-BAD/Halbert/.venv/bin/python -m pytest tests/ -q -p no:randomly
```

Note against the previous handoff: the `test_vision_tools` region-capture
failure it recorded as environmental did **not** reproduce — it passed in
every run here, including the baseline. It reads the real display geometry,
so it is host-state dependent rather than reliably broken.

End of batch: **8652 passed, 0 failed.** Every delta is a new test.

## What landed

| | Commit | |
|---|---|---|
| **A07-G8** — the yield primitive | `e7bcd05f` | R-01's last non-gated item |
| **A11-G12** — the entitlement spike | `5a1248cc` | Measured; the answer is an account action |
| Sonnet batch absorbed | `aa294aa9` | R-15 + R-13, zero conflicts |
| **R-12** — Phase A and both wirings | `43dfd249` | The packet closes |
| **A02-G3** — the RECOVERY arm | `77998a3a` | Escalated to opus by the sonnet session |

### A07-G8 — a command can be let go of

Stop and steer were the only two verbs a running tool could hear, and they
answer different questions. Stop ends the command; steer waits for the batch
boundary, which during a five-minute backup is five minutes away. Nothing on
any surface said so, and pressing stop out of impatience took the steer with
it (A07-G3).

The background registry the origin's fix hands a process to is one this tree
already owns: a pool session with an open block is never reaped and never
re-acquired. `tools/yield_signal.py` is the bit that was missing and nothing
else — one flag per session, raised by `request_steer`, consumed by the tool
that is running, and gone when that execution ends so a steer between two
tool calls cannot make the *next* command detach on arrival.

Two things the `run_block` restructure had to not quietly change, both
pinned: EOF on the fanout queue is not a deadline and must not take the
ETX-then-kill ladder, and a yielded block is exempt from its caller's
timeout but not from time — `YIELDED_MAX_SECONDS` keeps three `tail -f`s
from taking a cap-3 pool down for the life of the process, which is R04-F3
arriving by another door.

`steer_accepted` now carries `yielded`, backend-only until a consumer
renders it. The finding was not only that the steer waited; it was that
nothing said it was waiting.

### R-12 — the session tree, connected

`move_leaf` shipped with a docstring that says it outright: *"T1 ships the
primitive unwired: no caller in this repo uses it yet."* The rotation writer
shipped the same way. Both were built, tested and merged; neither was ever
called. That is the cross-cutting defect the whole pass exists to stop
recreating, and it survived two packets inside the tree doing the auditing.

Phase A first, because `move_leaf` could not be trusted with a tree whose
typed columns nothing wrote — and **bug 1 and the T2 rewire turn out to be
one change, not two**. `move_leaf` stamps parent and edge exactly when the
column is NULL, so while `_open_new_thread` wrote provenance to `metadata`
only, the first real move would have stamped whatever thread happened to be
the leaf at that moment, permanently, with the path projection reading the
column and `_predecessor_id` reading the metadata and the two disagreeing
forever. Routing the switch through `move_leaf` writes the column at the one
moment the answer is known and mints the dividers in the same transaction.
The successor is created `paused` and opened *by* the move: with the
one-leaf index there is no instant at which two rows may claim to be the
leaf.

Also closed: bug 3 (`_reopen_thread` trusted the caller's `from_thread_id`,
which `new_thread` was already fixed not to — and the one-leaf index turned
that from a logic bug into "could not resume" on a perfectly resumable
thread); G5 (a turn cut before a token streamed wrote nothing at all, so the
next history was two bare user rows and a local model had every reason to
stage the deletion again); G2 (`compact_boundaries.unresolved_request`
shipped `NOT NULL DEFAULT ''` and every writer wrote the default).

**Wiring the rotation writer found what being unwired had hidden.** The
module reads `m["id"]`; the store's row shape is `m["message_id"]`. A real
caller would have got an empty `covered_message_ids` and `coverage_end_id`
0 — a rotation that writes a summary, hides nothing, and leaves the thread
holding every turn it just claimed to fold. Silent, because the isinstance
guard drops the rows rather than raising. This is the argument for wiring a
module the day it is written, in one line.

One consequence worth stating on its own: a merge says the split was
spurious, so the divider announcing it describes something that did not
happen. It is hidden inside `merge_thread`'s own transaction, matched on the
crossing key's `from->to@boundary` shape so a divider to a third subject is
untouched — **hidden, not deleted**, per the standing directive that
superseded rows stay on disk.

Nine existing tests in `test_threads.py` pinned the pre-wiring truth and now
assert the new one. The one worth reading before you trust it: the
no-predecessor refusal used to be simulated by clearing `metadata`, which no
longer produces a row with no recorded predecessor — it produces one with a
*better* record of the same predecessor. The fixture now clears the typed
column too, so the invariant ("no predecessor, no merge") is still pinned
rather than quietly weakened. Reciprocity is still enforced; there is still
no "most recently paused thread" fallback.

### A02-G3 — the arm that measures what the machine actually does

The sonnet session stopped here and said why: retrieval is per *question*,
and `Arm.policy(thread, region) -> Retained` returns one text for the whole
bank. It escalated rather than force-fit, and it was right to.

The seam it wanted is one layer down. A policy is handed no questions; the
*answerer* is where a question is seen, and `_run_arm` already builds one.
`Arm` gains an optional `answerer` and the policy contract is untouched —
additive, `None` being exactly what every arm had. The region-scoping
sentinel still holds and is re-run against the new seam, because retrieval
runs over the region, which is the same slice the policy saw.

**The measurement changes a decision.** On the committed corpus:

| arm | recall | retained |
|---|---:|---:|
| NO_CONSOLIDATION (ceiling) | 1.000 | ~283 |
| CONSOLIDATOR_DETERMINISTIC | 0.000 | ~20 |
| **CONSOLIDATOR_DETERMINISTIC+RECOVERY** | **1.000** | **~93** |
| TRUNCATE_OLDEST | 0.500 | ~141 |

The 0.000 row is the one the founder was going to read as "the deterministic
pass loses everything". It does not. Production never destroys the region —
the Consolidator only *adds* durable facts, the raw turns stay in the store,
and `recall_gate` reaches them by FTS — and the shipped behaviour answers
every question at a third of the ceiling's tokens, beating the cheap
baseline on both axes at once.

The committed scorecard's finding 2 said the LLM pass "must beat
TRUNCATE_OLDEST". **The bar is now a row that costs nothing and asks
nobody**, which is materially harder and quite possibly unbeatable. Finding
2 is corrected and the new row gets its own, because a scorecard still
pointing at TRUNCATE_OLDEST would be arguing for a model against the wrong
opponent. `SCORECARD-2026-09-11.md` is committed (UTC-dated, by the module's
own convention).

## The entitlement spike — `.handoff/SPIKE-SECURE-ENCLAVE-ENTITLEMENT-2026-09-10.md`

Five signing configurations, measured, with the OS's own words for each
refusal. Three results that change the plan:

1. **The Enclave is not the gate; the keychain is.** `errSecMissingEntitlement`
   arrived identically for a Secure Enclave key and for a plain
   generic-password item with a `.userPresence` ACL. So *"fall back to a
   biometry-gated HMAC" is not a fallback* — it needs the same entitlement.
   That option does not exist, and planning around it would have cost a
   cycle to find out.
2. **Signing the entitlement without a profile does not degrade, it fails to
   launch.** AMFI kills the process at exec: "No matching profile found."
3. **The route is ordinary.** Six Developer-ID apps in `/Applications` ship
   an `embedded.provisionprofile` carrying `keychain-access-groups`, one of
   them with `ProvisionsAllDevices` and an 18-year life.

So A11-G12's residual is **not blocked on engineering**. It is blocked on
one action in the founder's Apple Developer account: an App ID with Keychain
Sharing, then a macOS *Developer ID* provisioning profile. Nothing regresses
while it waits — `accept_profile` still has no route caller, so no grant is
being recorded on a promise the code cannot keep.

## What is left, and why

- **A07-G11** (auto-continue) — FD-1 says no. Closed by decision, not by
  time.
- **R-14 Phase D** (the promotion consumer) — FD-22, and the memory memo now
  gives it a better reason than "unreviewed": the design behind it was
  wrong.
- **A17-G19** — closed; the OSV preflight was built after being deferred
  (`c9e70623`).
- **The OS re-auth handler** — the spike above. An account action, then
  packaging, then the code.
- **A02-G15** (fingerprint-skip replay) — still the sonnet batch's
  explicitly deferred low/optional item. Untouched here.

Nothing else in the fifteen-packet remediation plan is open. **R-03
(scheduler durability + heartbeat liveness) was never started by anyone** —
it is the last sonnet-tier packet, its checklist is in the tier-assignment
doc, and it is dispatchable today.

## Things a reviewer should look at first

Three judgment calls, each defensible and each mine rather than the plan's:

1. **`YIELDED_MAX_SECONDS = 1800`.** A policy number I chose. It is the same
   class as the existing `DEFAULT_TIMEOUT`, not a security posture, but it
   is a default nobody ratified.
2. **Hiding the retracted divider in `merge_thread`.** Follows from "a merge
   says the split was spurious", and hides rather than deletes per the
   standing directive — but it is a behaviour the packet did not name.
3. **`retained_tokens` for a retrieving arm** is the base text plus the
   *mean* retrieved per question. A per-question cost has no single honest
   number; the mean is the least dishonest one, and the alternative (report
   only the base) would publish a recall with its cost hidden.

## Conventions this batch followed

Red-first throughout: 13 of R-12's 18 tests failed before the change, 9 of
A07-G8's 20, and the recovery arm's suite failed at import. The pre-change
tree was checked out to prove it rather than assumed. Commits are
pathspec-scoped, no attribution trailers. The sonnet branch was merged into
this branch rather than to `main`, so `main` is untouched and there is one
branch to review.

---

# Addendum — the parallel R-12, and what comparing them found

A sonnet session implemented R-12 Phase A **and both wirings** independently,
in parallel with this branch, on `fix/remediation-sonnet-batch-1`
(`27df496a`…`8afc5dfb`, rebased onto `fdafafcb`). Two complete
implementations of the same packet now exist. That is a coordination failure
worth recording rather than smoothing over — but the duplicate work turned
out to be worth something, because running each implementation against the
other's tests is a sharper instrument than either suite alone.

The R-15/R-13 half of that branch is byte-identical to what this one merged
(clean rebase, new SHAs only), so there is no divergence there.

## What the comparison found

**My 18 R-12 tests against their implementation: 16 pass.**
**Their R-12 tests against mine: the four real differences below.**

### One real defect here, now fixed (`19daaa84`)

`unresolved_request` keyed on `origin = 'human'` alone — and `origin`
**defaults to `'human'`** for any caller that does not name it, so an
assistant row appended without one, the A16-G5 marker included, came back as
the question the machine had been asked. Production was safe (`end_turn`
names it), but the predicate was wrong. Their six store-level cases are
adopted verbatim; the fourth is the one that caught it.

### One test of mine that passed for the wrong reason, now tightened

`test_a_return_mints_a_return_row` asserted only "some branch row exists on
the thread returned to", which the *departure* row from the earlier switch
already satisfies. It was not a test of the return at all. It now asserts
the side and forces a real reopen past the grace window — inside it,
`resume_thread` takes `merge_back` and there is no crossing to record.

### Two things theirs did better, now taken (`19daaa84`, `1b40c0c2`)

- **`_predecessor_id` prefers the typed column**, metadata as fallback. The
  old order had to be that way because nothing wrote the column; now that
  every creation stamps it, the column is the better record.
- **`branch` vs `continuation`.** Design §1.1 carries both words. A model
  declaring a new subject has branched; a conversation drifting into one by
  itself, and a return, are continuations. I had been stamping `branch` on
  everything, which throws away the distinction the column exists for.
- Also taken: `get_or_open_thread(edge_kind=…)` so the degraded path opens a
  thread that knows its origin, and the peer store now speaks `move_leaf`
  and `unresolved_request`.

### Three things this branch has that theirs lacks

- **A topic switch mints no divider in theirs.** Only the reopen does. That
  is half of design §2.3 missing — and the opus batch commit that built the
  minting is literally *"a topic switch leaves two sentences behind, minted
  once"* (`b017e65e`). Verified by test, not by reading.
- **The retracted divider.** A merge says the split was spurious; theirs
  leaves the divider announcing it. (Theirs has less need of it, having
  minted fewer.)
- **The `create_thread` log** that reports a one-leaf-index violation as
  "thread already exists", sending the reader after a duplicate id that does
  not exist.

## Three rulings this needs

**1. Which implementation.** Recommend this branch: it now carries
everything theirs had that was better, plus the three above. But it is a
recommendation, not a fact — read the two `_reopen_thread`s side by side
before taking it.

**2. The rotation threshold.** Mine gates at `HISTORY_ROWS * 3` rows before
even asking `plan_rotation`; theirs calls it every turn and lets its guards
decide, which with `keep_recent=10` rotates roughly six turns into a
conversation. My argument is that rotation sets `visible_in_timeline = 0`,
and the timeline and FTS search both filter on it — so an early rotation
hides turns the user has just had. `recent_messages` does *not* filter it,
so the model's replayed history is unaffected either way. A tuning constant,
but a user-visible one.

**3. `move_leaf` and `BEGIN IMMEDIATE`.** Theirs changed it; I did not,
because the audit **refuted** that bug and the packet's STOP conditions say
a refuted item must not be silently re-opened. The refuter measured the
stated mechanism and found it does not occur (legacy isolation mode opens no
transaction for a SELECT). **But there is an independent justification the
commit does not state**: the two SELECTs run in autocommit, so between
reading `old.status == 'open'` and the UPDATE another connection can change
it. Narrow — `move_leaf` runs under `ThreadManager._lock`, so only two store
instances on one file can reach it — and real. Worth doing for that reason,
under that reason, rather than under the refuted one.

**And one smaller call: the cancelled-turn marker.** Mine writes the A16-G5
marker for any non-`complete` status; theirs carves out `cancelled` on the
grounds that "the user already knows they cancelled it". Note what
`cancelled` actually means here — `state_machine.py:1028` writes it for a
**superseded** turn, not a user cancellation (the stop button writes
`interrupted`). And the harm G5 describes is not that the user is confused;
it is that the *model* reads two consecutive user rows and re-stages the
first. A superseded turn produces exactly that shape. I think the marker
belongs there, but it is one row of transcript either way.
