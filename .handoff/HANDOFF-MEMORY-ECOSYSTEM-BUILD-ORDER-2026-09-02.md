# Memory Ecosystem — Verified Build Order

> **HISTORICAL, 2026-09-04. This is the plan, not the state.**
>
> All eleven steps are resolved: 1–8 built, 9 cut, 10 deferred, 11a/11b cut on evidence.
> `LEDGER-1` is **Landed**, not "Missing"; `MEM-01`..`MEM-05` are **ratified**, not pending;
> the Haloysius lock **shipped** (`7b1ddc0`); and `erase()` now has a live caller
> (`forget_request` → `erase_audit_by_request` → `EventLog.erase_many`), so every
> "harmless today only because erase() has no callers" risk note below is **inverted**.
> The "[start here]" tag on step 2 and the "live cost of delay" warning are both spent.
>
> Current state lives in `ROADMAP.md` (`LEDGER-1`) and
> [`NOTE-MEMORY-STEPS-CUT-AND-DEFERRED-2026-09-02.md`](NOTE-MEMORY-STEPS-CUT-AND-DEFERRED-2026-09-02.md).
> Kept because the *reasoning* about why this order was chosen still holds, and it is the
> only record of it.

**Date:** 2026-09-02
**Design doc:** `Haloysius/docs/HANDOFF-SELF-HEALING-MEMORY-ECOSYSTEM.md` (rev. 3)
**ROADMAP row:** `LEDGER-1` — Change ledger ("I remember why"), currently *Missing*
**Method:** 16 adversarial reviewers refuting 8 load-bearing claims, then 3 independent
build-order proposals (dependency-first, risk-first, visible-result-first) and a judge.
Not one claim survived unchanged; one was refuted outright.

---

## The two questions, answered

**"Is most of this work for Haloysius?" — No. Roughly 90 % is Halbert's.**

Excluding everything already built and wired — `TemporalStateLedger.record()` with
auto-closing `valid_to`, Halbert's `StateStore`, `integrity.EventLog`, `memory_v2`
epistemic scoring / `ObservationStore` / the deterministic consolidation engine,
`background/{idle_detector,scheduler,daemon}`, Halbert's APScheduler and turn-lock
heartbeat, and the flock-protected audit chain — the genuinely new work splits:

| Repo | Days | Deliverables |
|:---|---:|---:|
| **Haloysius** | 2–3 | 1 |
| **Halbert** | 28–32 | 10 |

**Why it looked inverted.** Halbert imports Haloysius, so Haloysius names are all over the
design — `EventLog`, `memory_v2`, `TemporalStateLedger`, `IdleDetector`, `consolidation.py`.
They appear there as **already-built primitives being consumed**, not as things to write.
Reading the dependency direction as the work direction is the error. The asymmetry also
follows from the split itself: everything genuinely new needs threads, receipts, a
dashboard and the host machine, and only Halbert has those.

**The entire Haloysius ask** is one change set: move the lock inside `EventLog` — covering
`append`, `verify` **and** `erase` — and add the concurrency regression test the package
does not have. It is *not* "two bug fixes", and it is not a prerequisite: see step 6.
(Committing the then-untracked module was a third item; a concurrent session landed it as
`b893c42` mid-review.)

**"Which repo starts first?" — Halbert.** First task: land the five ratification rows
below (an afternoon, no code), then edit
[state_store.py](halbert_core/halbert_core/continuity/state_store.py).

---

## Step 1 — Ratify five rows (a decision, not a build)

`DECISIONS.md` plus `ROADMAP.md:33` (`LEDGER-1`). These gate which file gets edited, so
they come first and cost hours, not days.

| Proposed row | Substance |
|:---|:---|
| **MEM-01** | **D1 narrowed and finally recorded.** Cross-session *continuity* — threads, receipts, recall, open loops, machine-state history, consolidation — is Halbert's. Identity and semantic memory stay in Haloysius `memory_v2`, a ratified store of record whose `ObservationStore` is explicitly cross-session. **D1 is in no decision row today** — it lives only in `.handoff/HANDOFF-CONTINUITY-AFTER-PLAN-A-2026-08-26.md §1`, and the design doc was asking the founder to ratify a split the log does not contain. |
| **MEM-02** | `halbert_core.continuity.StateStore` is **the** machine-state change ledger; Haloysius `TemporalStateLedger` is retired from Halbert's path (it stays correct and in use inside Haloysius). Not a coin flip: `LEDGER-1` is a Halbert row; `StateStore` carries `thread_id` and no `persona_id`; it is already wired from `agents/threads.py:768-793` and `integrations/state_trackers.py`; `TemporalStateLedger` is persona-keyed and would inherit `PERS-02`'s two live persona sources of truth. |
| **MEM-03** | The Markdown vault is a **rebuildable projection with no authority** — justified by erasure reach, not by store arithmetic. `DECISIONS.md:25` assigns *ownership*, it does not cap artifacts (the same row keeps ChromaDB; the audit log, key store, scheduler history and peer credentials are separately ratified). The objection to a file-primary vault is that it would be a fifth **authority**. |
| **MEM-04** | The dream cycle registers on **Halbert's APScheduler** (`register_proactive_jobs()`, `dashboard/app.py:174`), gated by the 60 s turn-lock heartbeat (`app.py:274`, `:640`) — never on `haloysius.background`. Quiet hours become a Halbert policy choice. This is where the "macOS idle blocker" is **deleted rather than paid for**. |
| **MEM-05** | **Correct `INTEG-07`** (`DECISIONS.md:57`). Replace "Both also belong upstream in Haloysius" with: only the append/verify/**erase** lock belongs upstream. The custody lock does not — `haloysius.integrity.identity` performs no file I/O and holds no key on disk (the `SigningBackend` seam keeps custody consumer-side), so `<keys>/.custody.lock` in `crypto/storage.py` is the correct and final home. |

**Unblocks:** everything. Removes fork risk from all ten build steps, kills the macOS idle
work outright, and stops anyone re-homing `memory_v2`'s `ObservationStore` into
`halbert_core` and creating a real fifth authority.

---

## Step 2 — `reason` / `actor` / `request_id` on `StateStore` **[start here]**

`halbert_core/halbert_core/continuity/state_store.py`

- Add `reason`, `actor`, `request_id` to `_SCHEMA` (`:41-52`) and to the `StateTriple`
  dataclass (`:64-77`).
- `record_state()` (`:136`): `reason` and `actor` become **mandatory parameters with no
  default**; `request_id` optional. Carry all three into the INSERT (`:167-172`).
- Add `why(subject, predicate)` returning the open triple **together with the triple it
  superseded**, so one query answers *what is true, since when, who changed it, and why*.
- Fix the 7 live call sites in the same commit: `integrations/state_trackers.py:37` (widen
  the `_record` funnel), `agents/threads.py:781/787/793`,
  `continuity/consolidation.py:100/112`.
- No users → **recreate `state_ledger.db`, do not migrate** it.
- Extend `halbert_core/tests/test_state_store.py`: assert `record_state()` cannot be called
  without a reason.

**Why first.** This is the only genuinely un-retrofittable item in the design. A reason
exists exactly once — at the instant of the write — and is destroyed if not captured.
Verified absent from both the schema and the signature. The window is at its narrowest
today: 7 call sites in 4 files, one a generic funnel covering most future writers. Every
later phase adds more. Zero dependency on either named blocker.

`state_triples` already yields before/after for free — the closed row *is* the before value
— so `LEDGER-1`'s four requirements reduce to two columns plus a join key.

### The permitted values are the point

A `reason` may be **(a)** a human utterance from the causing turn, **(b)** a deterministic
rule that names itself (`"tracker: disk sweep"`, `"policy: permissions remediation"`), or
**(c)** the sentinel `unrecorded`, which renders as *unknown* and **is never backfilled by
a model, ever**.

This is the project's largest risk. A plausible fabricated rationale is strictly worse than
a blank: unfalsifiable, it survives into the vault as if it were provenance, gets cited in
the Doubt Queue, and the dream cycle then reasons over it as evidence. There is no
migration back. A `NOT NULL` constraint that says nothing about what fills it is exactly
what invites the LLM backfill under schedule pressure. Same honesty constraint `INTEG-05`
imposes on the integrity surface.

**Live cost of delay:** the 7 call sites are appending unprovenanced triples on production
paths *today*, and nothing errors.

---

## Step 3 — Promote provenance to first-class audited fields

`halbert_core/halbert_core/obs/audit.py` — add `reason`, `actor`, `before_sha256`,
`after_sha256` to `AUDITED_FIELDS` (`:68`) and to `write_audit`'s signature (`:200`).

Today `AUDITED_FIELDS` is `{ts, tool, mode, request_id, ok, summary, shadowed}`; everything
else — including `path` — rides `**extra`, where a model-supplied string can collide and
get quarantined under `shadowed` (`INTEG-09`). Provenance fields must not be shadowable.
Sibling commit to step 2; no dependency between them.

---

## Step 4 — Wire the two live write paths

- `halbert_core/halbert_core/tools/write_config.py`: the apply branch already computes the
  unified diff into `preview` and discards it into outputs only (`:63`). Pass it plus a
  caller-supplied reason into `write_audit`, and add the `record_state()` call that is
  **entirely absent today**, carrying the `req.request_id` it already holds.
- `halbert_core/halbert_core/dashboard/routes/editor.py` `write_file_content()` — the single
  choke point for both sudo and non-sudo editor saves.

**Join on `request_id`, never on `event_seq`.** Under the unfixed append race 8 concurrent
appends all take seq 0, so a seq-keyed join silently points at the wrong record — and it
would needlessly make the ledger wait on the upstream lock. `request_id` is already stamped
on every audit record and decouples the two tracks entirely.

These two paths are the founder's own hands on the machine: the agent editing a config, and
the dashboard editor saving a file. Both already call `write_audit`.

---

## Step 5 — Read surface **[first observable milestone]**

- Expose `StateStore.why()` as `GET /api/state/why?path=…`.
- Un-substitute `recall_memory`: remove it from `_SUBSTITUTED_BY_SEARCH`
  (`agents/state_machine.py:167`) so it answers from the ledger. It is wired here rather
  than earlier because it currently never executes — routed to `SEARCHING` and substituted
  by generic search — and wiring it before the ledger has records only replaces one empty
  answer with another.
- Render before/after from the ledger in the dashboard config-diff.

**Change a config, ask "why is X configured this way", get value, predecessor, actor,
timestamp and reason.** That is the literal definition-of-done sentence of `LEDGER-1`,
reached in about a week using only pieces that already ship. Nothing here is discarded
later: the vault, the Doubt Queue and the dream cycle all read through this same `why()`.

---

## Step 6 — [Haloysius] The only upstream work item

1. Move the lock **inside** `EventLog`: `append` (`eventlog.py:252-276`), `verify()`, and
   `erase()` (`:313-343`) under one lock.
2. Add the concurrency regression test the package does not have (grep for
   thread/concurrent over `integrity/tests/` returns nothing).

*(A third item — committing the then-untracked `src/haloysius/integrity/`, an unlisted
predecessor task nobody had scheduled — was done by a concurrent session as `b893c42`
while this review ran. The upstream baseline now exists.)*

**Deferrable to exactly here and no further.** Halbert's audit path is already safe — the
`flock` at `obs/audit.py:159-197`, with `EventLog` constructed at only two sites, both
inside it — so steps 1–5 are genuinely unblocked and treating this as a phase-0 gate would
idle a week against a handled defect.

But it hard-gates step 7: chain corruption on a signed append-only log is not repairable,
and `erase()` under a duplicate-seq log clears only the **first** matching record, leaving
other plaintext copies on disk while the acceptance test goes green.

**Three call sites, not two.** `erase()` is itself an unlocked read-modify-write that
`os.replace()`s a whole shard and can silently destroy a concurrent append — a hazard named
nowhere in `DECISIONS.md` or the design doc, harmless today only because `erase()` has zero
callers. Do **not** accept "port Halbert's flock upstream" as satisfying this: that lock is
a module-private helper at two hand-written sites and protects the audit log only. It must
go inside the object. This is a lock, not a registration — the subtractive contract is
untouched.

---

## Step 7 — Remaining write paths, and build the `erase()` call path

- Extend coverage to the rest of `LEDGER-1`: approval execution
  (`dashboard/routes/approvals.py`), diff apply, watcher-observed change.
- **Build "forget that" as a `request_id`-keyed fan-out**: erase the log record, close or
  redact the ledger row, and (once step 8 lands) delete the projected note and any
  `_doubt_queue/` item — in one operation.
- Honesty clause: `memory_v2` writes plaintext to disk (`memory_v2/store.py:139-150`) and
  is outside `erase()`'s reach, so the user-facing copy must state what erasure actually
  covers. Binding precedent: `INTEG-05` ("no memory verified badge").

**`EventLog.erase()` has zero callers in either tree** — only `test_eventlog.py` invokes it.
Every proposal assumed this was done and none of them was right. It must exist before any
plane stores a verbatim provenance quote.

---

## Step 8 — Markdown vault as a pure projection

Rebuildable from scratch, no authority, never read back as truth, **keyed on `persona_id`**.

Two acceptance tests: delete the whole vault directory, rebuild, byte-compare; and
`erase(seq)` deletes the projected note and any referencing `_doubt_queue/` item in the same
operation, with a rebuild afterwards never resurrecting the fact.

Deliberately here, not first, despite being the most photogenic step: projecting before
steps 2–4 and 7 yields a beautiful empty vault that must be rebuilt once `reason`/`actor`
and the write paths land — the one outcome the "nothing thrown away" constraint forbids.

**Keyed on `persona_id`, not `body_name`.** The design doc had this backwards.
`PersonaMemoryStore` stores under `state_dir("personas", persona_id)`, `body_name` keys
nothing anywhere in either tree (zero hits in Haloysius), and the only erase surface is
persona-scoped. Halbert is the only possible host: a file watcher has no `None`-fallback so
it cannot be a Haloysius seam, and it would breach the two-hard-dependency subtractive
contract outright.

---

## Step 9 — Dream cycle, deterministic first

Register a **deterministic** contradiction pass as a job on Halbert's existing APScheduler
via `register_proactive_jobs()` (`dashboard/app.py:174`), gated by the existing 60 s
turn-lock heartbeat. Call Haloysius's already-built deterministic engine
(`memory_v2/consolidation.py`); Halbert owns registration, policy and the quiet-hours
ruling. **No model in this step.**

Runs *before* the Doubt Queue: a curation UI built first is designed against imagined
content. Deterministic-first also means the loop is observable and debuggable before any
model touches memory.

---

## Step 10 — Doubt Queue and curation UI

Plus transcript grounding and model escalation for what the deterministic pass cannot
resolve alone. Needs real contradictions, which only exist after step 9 has run over a
populated ledger. Fully reversible — read-side surface, so a wrong call costs a re-run, not
lost data.

Carry over Warp's one verified liftable clause: a saved answer records the id of the
suggestion that produced it, so the queue never re-raises a doubt the human already
answered.

---

## Step 11 — Scope-cut tier (absorb schedule pressure here)

**(a) Make micro-compaction non-inert — in this order.** Carry `blocks_json` through
`conversation_sqlite.recent_messages` and `threads.py:953` so block-typed turns survive into
the window; add the >5-turn recency gate; **then** route production compaction through
`should_compact`.

Order matters. `micro_compact` is already called in production (`assembler.py:1293`) but
truncates **zero** blocks, because the thread store flattens `content` to TEXT on write
(`conversation_sqlite.py:825-828`) and `micro_compact` skips non-list content
(`watermark.py:106-108`). Routing `should_compact` first ships a trigger over a pass that
does nothing, and the failure is silent with green unit tests. Note also that ours has **no
recency gate** — unlike the 5-turn rule it was modelled on — so it truncates the newest tool
result too; that is an open MAJOR, not a design choice.

**(b) Thresholds and tiering.** `halbert_core/continuity/recall_eval.py` is today an FTS5
hit@k / MRR receipt harness with no threshold or sweep code. Extend it to score
`MemoryEpistemicScore.composite`, sweep the values, and scope the pointer index as a
**tiering policy** — small stable set inlined into the cacheable prefix, long tail listed as
paths — measured against that harness. The archived upstream Claude Code bundle already
ships exactly this split in production, so there is working prior art in the same repo the
design cites as evidence against it.

Last because both are tuning, and tuning needs a populated ledger and a running dream cycle
to tune against.

---

## Risks, in order

1. **`reason` gets filled by a model asked to invent one after the fact, and nothing can
   tell the difference.** Enforced at the signature in step 2, or not at all.
2. **Silent and live right now:** four tracker call sites are appending unprovenanced
   triples on production paths. Every sprint spent on blockers first is another sprint of
   history that can never answer the question it exists to answer.
3. **`EventLog.erase()` is an unlocked read-modify-write that Halbert's flock does not
   cover.** Harmless only because it has no callers; step 7 creates the hazard the moment it
   wires "forget that".
