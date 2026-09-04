# Fable packet — Memory ecosystem, steps 5b to 11

> **STATUS 2026-09-02, end of day: MOSTLY EXECUTED. Read this before planning from it.**
>
> Steps **6, 7a, 5b, 8 and 7b are built and committed** on `feat/ledger-provenance`
> (13 commits; suite 5,345 passed / 0 failed across both roots, Haloysius integrity 119).
> The step-by-step sections below are kept as the record of *what was asked for*, not as
> a description of outstanding work.
>
> **Update 2026-09-04: fully resolved.** Step 5c is built (reduced — the panel shows the
> recorded reason, actor and time; the ledger stores digests, so before/after content was
> never possible). Step 9 is **cut**, not deferred. Step 10 (Doubt Queue) remains deferred,
> and its case is stronger now that step 9 is cut. Nothing here is outstanding work.
>
> **Cut or deferred on evidence, not on schedule** — steps 9, 11a and 11b. Do not
> re-plan them from this document: see
> [`NOTE-MEMORY-STEPS-CUT-AND-DEFERRED-2026-09-02.md`](NOTE-MEMORY-STEPS-CUT-AND-DEFERRED-2026-09-02.md),
> which records why 11a would have produced a silent green and why two of 11b's
> proposed thresholds could not have come from the scorer they name.
>
> **The ten invariants below still bind**, and are the most durable part of this
> document. One of them was violated by the first implementation and caught in review:
> a failed ledger read rendered as "nothing was recorded". Fixed in `eb68d968`.
>
> **This work has had almost no external review.** A Fable review was commissioned and
> 14 of its 15 agents failed on usage credits; only `recall-abstention` completed, and
> its verifiers did not run.

**Date:** 2026-09-02
**Branch:** `feat/ledger-provenance`
**Design doc:** `Haloysius/docs/HANDOFF-SELF-HEALING-MEMORY-ECOSYSTEM.md` (rev. 3)
**Build order:** `.handoff/HANDOFF-MEMORY-ECOSYSTEM-BUILD-ORDER-2026-09-02.md`
**ROADMAP row:** `LEDGER-1`. **Decisions:** `MEM-01`..`MEM-06` in `DECISIONS.md`.

---

## What is already done — do not rebuild it

| Step | State | Commit |
|:--|:--|:--|
| 1. Ratification rows | `MEM-01`..`MEM-06` written, pending founder sign-off | `64d63526` |
| 2. `reason`/`actor`/`request_id` on `StateStore` + `why()` + 7 call sites | **Done** | `46241c94` |
| 3. Provenance as first-class audited fields | **Done** | `4ae71934` |
| 4. Both live write paths on both planes | **Done** | `b343171d` |
| 5a. `GET /api/state/{why,history,by-request}` | **Done** | `e3bc1848` |
| 6. `EventLog` append/verify/**erase** serialised | **Done** (upstream) | `7b1ddc0`, `b3cce58` |
| 7a. Provenance on every remaining write path | **Done** | `0476629b` |
| 5b. `recall_memory` over the ledger | **Done** | `a6022520` |
| 8. Markdown vault projector | **Done** | `0d88da8c` |
| 7b. "forget that" across both planes | **Done** | `ba9a3e3a` |
| — a failed read must not read as "nothing recorded" | **Fixed after review** | `eb68d968` |
| — five further review rounds | **Fixed** | `0ea21032`, `a91714f4`, `2386d54d`, `b25e647b`, `1424bbe4`, `a6b5e353`, `82f25ff2` |

Suite at the time of writing: **5,345 passed**. It has moved since — see `ROADMAP.md`
for the current gate rather than trusting a count in a handoff. Run it as
`arch -arm64 /Volumes/4TB-BAD/Halbert/.venv/bin/python ./wt_pytest.py halbert_core/tests tests -q`
from the worktree root — naming the interpreter explicitly rather than relying on an
activated venv, because the shebang otherwise resolves to a system python with no
haloysius and no pytest-asyncio, which turns seven async tests into silent skips.

New API you will build on:

- `halbert_core/continuity/state_store.py` — `record_state(..., *, reason, actor,
  request_id=None)`, `invalidate_state(..., *, reason, actor)`,
  `why(subject, predicate) -> StateWhy`, `by_request(request_id)`. Constants
  `UNRECORDED`, `ACTOR_USER`, `ACTOR_AGENT`, `ACTOR_SYSTEM`.
- `halbert_core/continuity/provenance.py` — `record_file_change(...)` writes both
  planes from one call; `content_digest()`; `FILE_CONTENT_PREDICATE`.
- `halbert_core/obs/audit.py` — `write_audit(..., reason=, actor=, before_sha256=,
  after_sha256=)`.

---

## Ten invariants. Breaking any one of these is worse than not doing the work

1. **`reason` is never filled by a model after the fact.** Permitted values: a human
   utterance from the causing turn, a deterministic rule that names itself
   (`"tracker: disk sweep"`), or `UNRECORDED`. A model may state its own reason for a
   write *it is making now*; it may never invent one for a write that already happened.
   `UNRECORDED` renders as *unknown* and is never later filled in. A fabricated reason is
   unfalsifiable, projects onward as provenance, and everything downstream then reads it
   as evidence. This is `MEM-06`, and the same honesty constraint as `INTEG-05`.
2. **Join on `request_id`, never on an event seq.** Seq is not unique under the unfixed
   concurrent append — 8 concurrent appends all take seq 0 — so a seq-keyed join can
   silently point at the wrong record.
3. **Records carry digests, not content.** A record must say *what* changed without
   becoming a second copy that `erase()` would then have to reach.
4. **The vault is a projection with no authority.** Rebuildable from the stores at any
   time; never read back as truth. Two acceptance tests, both required: delete the whole
   vault directory, rebuild, byte-compare; and `erase(seq)` deletes the projected note and
   any referencing `_doubt_queue/` item in the same operation, with a rebuild afterwards
   never resurrecting the fact. This is `MEM-03`. (As built: the doubt-queue half is
   deferred with step 10, so the second test is stated against `VaultProjector.forget`.)
5. **The vault is keyed on `persona_id`, not `body_name`.** `body_name` is a location
   label and keys nothing anywhere — zero hits in Haloysius. The design doc had this
   backwards before rev. 3; do not reintroduce it.
6. **Background work registers on Halbert's APScheduler**, gated by the 60 s turn-lock
   heartbeat — never on `haloysius.background`. This is `MEM-04`.
7. **Do not build a macOS idle probe.** `IdleDetector`/`BackgroundDaemon`/`TaskScheduler`
   have zero importers in either tree. Adopting them would manufacture a macOS blocker
   rather than remove one. If you find yourself writing `ioreg`, stop and re-read `MEM-04`.
8. **Deterministic before model.** The contradiction pass is deterministic first;
   `record()` already supersedes by construction and `smart_add` already dedups
   semantically. A model is for synthesis only, on the LLM slot, never the chat slot, and
   never where a template suffices.
9. **The Haloysius lock goes *inside* `EventLog`**, covering `append`, `verify` **and**
   `erase` — three call sites. Do not port Halbert's `flock`: that is a module-private
   helper at two hand-written sites and protects the audit directory only.
10. **Never splat an unvetted dict into `write_audit`.** `reason`/`actor` are named
    keyword-only parameters, so `**result_dict` binds them exactly as an explicit keyword
    would. Pinned by
    `test_splatting_an_untrusted_dict_binds_its_reason_to_the_parameter`.

---

## Step 5b — let the agent answer from the ledger

`recall_memory` is **not a tool**. It is routed to `SEARCHING`
(`agents/state_machine.py:161`, `_SEARCH_ROUTED_TOOLS`) and substituted by generic search
(`:167`, `_SUBSTITUTED_BY_SEARCH`), with an observation at `:2310-2320` telling the model
the substitution happened so it does not report an empty search as an empty memory.

To make "why is X configured this way" answerable in conversation:

1. Build a real `recall_memory` tool over `StateStore.why()` / `state_history()`.
   Reuse the route logic in `dashboard/routes/state.py`; do not duplicate the query.
2. Remove `recall_memory` from both `_SEARCH_ROUTED_TOOLS` and `_SUBSTITUTED_BY_SEARCH`,
   and delete the substitution observation for it (leave `search_discoveries` alone).
3. Register it in the tool registry and update `tools/safety.py:401`, which currently
   classifies it with the search family.
4. The prompt must tell the model the tool exists, and that an empty answer means
   **"not recorded"**, never "nothing changed".

**Acceptance:** in a real turn — change a config through the editor with a stated reason,
then ask "why is /etc/… configured this way" and get value, predecessor, actor, timestamp
and reason, with no generic search in the trace.

**Watch for:** the abstain path. `StateWhy.found == False` must produce "I have no record
of that", not a hedged guess assembled from search results. That regression is the whole
reason the substitution observation exists today.

## Step 5c — config-diff reads the ledger

The dashboard config-diff shows before/after from its own state. Point it at
`GET /api/state/why?path=…`: `superseded.object` and `current.object` are the digests, and
`current.reason` / `current.actor` / `current.valid_from` are the sentence under the diff.
Use `/api/state/by-request` to pull the matching audit record for the unified diff text.

## Step 6 — [Haloysius] the single upstream item

Repo: `/Volumes/4TB-BAD/Haloysius`. `src/haloysius/integrity/` is committed (`b893c42`).

1. Move the lock **inside** `EventLog`: `append` (`eventlog.py:252-276`), `verify()`, and
   `erase()` (`:313-343`). `erase()` is itself an unlocked read-modify-write that
   `os.replace()`s a whole shard and can silently destroy a concurrent append — a hazard
   named in neither `INTEG-06` nor `INTEG-07`; see `MEM-05`.
2. Add the concurrency regression test the package does not have (grep for
   thread/concurrent over `integrity/tests/` returns nothing). Reproduction: 8 threads ×
   6 appends to a fresh log gives `ok=False, checked=48, problems=84`.
3. Do **not** move the custody lock upstream. `identity.py` performs no file I/O and holds
   no key on disk; `<keys>/.custody.lock` in Halbert's `crypto/storage.py` is its correct
   and final home. `MEM-05` corrects `INTEG-07` on this.

**Not a prerequisite for steps 5b/5c.** It hard-gates step 7.

## Step 7 — build the `erase()` call path

`EventLog.erase()` has **zero callers outside its own tests, in either tree**. "Forget
that" is an unbuilt feature, not a broken one, and it must exist before any plane stores a
verbatim provenance quote.

- Implement as a `request_id`-keyed fan-out: erase the log record, close or redact the
  ledger row, and (once step 8 lands) delete the projected note and any `_doubt_queue/`
  item — one operation.
- Extend write coverage to the remaining `LEDGER-1` paths: approval execution
  (`dashboard/routes/approvals.py`), diff apply, watcher-observed change. Use
  `record_file_change()`; do not hand-roll a second recorder.
- **Honesty clause, required:** `memory_v2` writes plaintext to disk
  (`memory_v2/store.py:139-150`) and is outside `erase()`'s reach entirely. The
  user-facing copy must state what erasure actually covers. Precedent: `INTEG-05`.
- Say "unrecoverable from the log and unbrute-forceable from the commitment", never
  "unrecoverable" flat — `_rewrite` is mkstemp + `os.replace` and does not overwrite the
  old shard's blocks.

## Steps 8–11 — vault, dream cycle, Doubt Queue, tuning

Full specs in the build order doc; the invariants above bind all four. Order is
deliberate and reversing it wastes work:

- **8. Vault projector.** After steps 2–4 and 7, not before: projecting earlier yields a
  beautiful empty vault that must be rebuilt once the write paths land.
- **9. Dream cycle, deterministic.** Before the Doubt Queue: a curation UI built first is
  designed against imagined content.
- **10. Doubt Queue + curation UI.** Needs real contradictions, which only exist after 9
  has run over a populated ledger.
- **11. Scope-cut tier, in this internal order.** (a) Carry `blocks_json` through
  `conversation_sqlite.recent_messages` and `threads.py:953` so block-typed turns reach
  the window, add the >5-turn recency gate, **then** route production compaction through
  `should_compact`. `micro_compact` is already called in production
  (`assembler.py:1293`) and truncates **zero** blocks, because the thread store flattens
  `content` to TEXT on write (`conversation_sqlite.py:825-828`); routing the trigger first
  ships a trigger over a pass that does nothing, and the failure is silent with green unit
  tests. (b) Extend `continuity/recall_eval.py` — today an FTS5 hit@k/MRR harness with no
  threshold or sweep code — to score `MemoryEpistemicScore.composite` and sweep it.

---

## Two things found during steps 1–5 that were not in any plan

1. **The dashboard editor recorded nothing.** `/api/editor/file` and `/backup/restore`
   write config files, escalating through pkexec or sudo, and left no trace on either
   plane. The build order assumed both already called `write_audit`; neither did. Fixed in
   `b343171d`. **Assume other write paths are in the same state — verify before trusting
   any "already audited" claim in a plan, including this one.**
2. **`default_state_db_path()` hardcoded `~/.local/share/halbert`** instead of resolving
   through `utils.paths.data_dir()`, so the ledger ignored `HALBERT_DATA_DIR` and a second
   instance would have written into the first one's history. Fixed in `b343171d`; the
   default path is unchanged. Worth checking the other stores against `CFG-1` for the same
   bug.

## Working notes

- Use a worktree; the main tree has concurrent sessions in it. Run tests with
  `arch -arm64 ./wt_pytest.py` from the worktree root — plain pytest silently resolves
  `halbert_core` to the **main** tree via the shared venv's editable install.
- Commit with pathspecs, never `git add -A` in the main tree.
- No `Co-Authored-By` or generation-attribution trailers (`CLAUDE.md`).
- `MEM-01`..`MEM-05` are **pending** founder ratification. If the founder rules against
  one, the affected steps change — check before building on `MEM-03` or `MEM-04`.
