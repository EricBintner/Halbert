# Continuity — Handoff for After Plan A

**Date:** 2026-08-26
**Reads first:** this file → `CONTINUITY-WIRING-PLAN-2026-08-26.md` (Phases 1–2 only; its
Phases 3–4 are **superseded by this document**) →
`documentation/research/CONTINUITY-MECHANISM-AUDIT-2026-08-26.md`.
**Branch:** `feat/continuity-wiring` (worktree
`~/.config/superpowers/worktrees/Halbert/continuity-wiring`), 6 commits, suite 1265/0.
**Precondition:** do not start Phase 3 until Plan A is merged. Phase 2 is the exception —
it belongs inside Plan A and is described here so the next session can fold it in.

---

## 1. Founder decisions taken 2026-08-26 (these revise earlier documents)

### D1 — Haloysius has no cross-session understanding. Continuity is built in Halbert.

> *"I think Haloysius doesn't need any sort of cross session understanding so we can build it
> all here."*

The boundary this draws:

| | Haloysius | Halbert |
|---|---|---|
| Owns | the mind's **present** state: cognition ticks, drives, worries, emotional state, persona, the state-tracker protocol | memory **across time**: threads, receipts, recall, open loops, machine-state history, consolidation |
| Knows about sessions | no | yes |
| Knows about threads | no | yes |

Haloysius stays a dependency for *personality and present state*. It is not part of the
continuity read path or write path.

**What D1 changes, concretely:**

1. **Drop the Haloysius semantic recall tier.** The wiring plan's Phase 3 Task 9 proposed
   using `PersonaMemoryStore.search()` as the weak-match tier behind FTS5. Cancelled. Recall
   stays Halbert-owned. If a semantic tier is wanted later, build it in Halbert over the
   receipts we already index.

2. **Drop the episodic line written at thread close.** Spec §8 currently says a
   voice-rendered first-person line, tagged `[thread_id, *domains]`, is written to Haloysius
   for every closed thread of ≥3 turns. That is session data flowing into Haloysius, which
   D1 forbids — and it was already the R1 violation flagged in the audit (a write path whose
   read path was deferred). **This is a change to the approved spec and needs the founder's
   sign-off before Plan A implements it.** Recommendation: cut it. Nothing reads it, D1 says
   it does not belong there, and removing it deletes a whole write path rather than fixing it.

3. **Migrate the state ledger into Halbert's own store.** This revises Phase 1, which I
   shipped earlier today — see §2.

### D2 — "Abstain-and-probe", explained

Poor jargon on my part. The behaviour:

When Halbert is asked about current machine state and the only support it has is an old
memory, it must not answer from the memory. It runs the check.

- **Not this:** *"The share is mounted at //nas/media."* — true on 14 Jul, possibly false now.
- **This:** *"We set that up on 14 Jul — checking now."* → reads the ledger or runs
  `systemctl status`, then answers from what it just observed.

"Abstain" = do not assert from stale memory. "Probe" = go look. It matters because Halbert
**is** the machine: looking costs a ledger read or one command, which no cloud agent can do.
It is the concrete form of the re-observability rule — memory holds intent, rationale and
commitments; the machine holds current state.

**Still an open product question (§6 Q1):** is that extra sentence the behaviour you want
everywhere, only for state older than some age, or only when the answer would drive an action?

---

## 2. Revising Phase 1: move the ledger into Halbert's store

Phase 1 wired Halbert's four state trackers to Haloysius's `TemporalStateLedger`, which now
records to `~/.local/share/halbert/state_ledger.db`. It works and is tested. Under D1 it is
still the wrong home, for a reason that was already in my own design doc and that I did not
apply to my own work: **§4.7 said "three tables, not a ninth store," and a separate SQLite
file with its own connection is a ninth store.**

The right end state: machine-state triples become a table in the **same** database Plan A
made the store of record, so a receipt, an open loop and a state triple share one file, one
WAL, one lock, one backup — and can be joined.

**Cost is small, and Phase 1 is not wasted.** The trackers now call a single seam:

```python
_record(ledger, persona_id, subject, predicate, obj, source)
```

Swapping the backing implementation is one function plus a schema addition. The tests in
`tests/test_state_trackers_ledger.py` assert behaviour (supersession, provenance, fail-soft),
not the backing class, so they carry over almost unchanged.

**Task R1 — port the ledger (do after Plan A merges).**

- Add to the Plan A schema:

```sql
CREATE TABLE IF NOT EXISTS state_triples (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    subject     TEXT NOT NULL,
    predicate   TEXT NOT NULL,
    object      TEXT NOT NULL,
    source      TEXT NOT NULL,
    confidence  REAL NOT NULL DEFAULT 1.0,
    valid_from  REAL NOT NULL,
    valid_to    REAL,
    thread_id   TEXT
);
CREATE INDEX IF NOT EXISTS idx_state_current
    ON state_triples(subject, predicate, valid_to);
```

- Store methods `record_state`, `current_state`, `state_history`, `invalidate_state`, with the
  same semantics Phase 1 pinned: `record_state` closes the previous open triple for the same
  `(subject, predicate)` by setting `valid_to`.
- Point `_record()` at the store. Drop `default_ledger_path()` and `_default_ledger()`.
- Keep every assertion in `tests/test_state_trackers_ledger.py`; replace only the `ledger`
  fixture.
- Note the gain D1 buys: `thread_id` on the triple. A state change becomes traceable to the
  conversation that caused it — provenance the Haloysius ledger could not express because it
  has no idea what a thread is.

---

## 3. What Plan A has actually built (verified 2026-08-26)

Branch `feat/continuous-conversation`, 8 commits past the plan docs. **A1, A1b and A2 are
done; A3 onward is not** (`thread_manager.py` and `migrations.py` do not exist yet).

**Usable now:**
- Thread-aware `SqliteConversationStore` with WAL, append-only messages, column-additive
  migration. Thread columns: `status, receipt, receipt_updated_at, topic_domains,
  entities_json, last_active, stale, ephemeral, parent_thread_id, merged_into, recalled_json,
  unread, paused_at, turns_since_pause, title_source`.
- API: `create_thread, update_thread, get_thread, list_threads, current_open_thread,
  list_messages, recent_messages, list_turns, append_message, update_message,
  mark_in_progress_interrupted, search`.
- `agents/receipt.py` — the nine-line deterministic receipt, plus `receipt_one_liner`.

**Worth knowing, because it shapes the rest.** The A2 review caught a **receipt-forgery**
hole: an embedded newline in a title, entity or file path could forge an extra labelled line
— including a fake `Open loop:` — into a receipt that is injected verbatim into the prompt.
Fixed by routing every field through `_clip`, capping entities at 12 and file paths at 80
chars. That is write-path antipoisoning, found independently, and it sets the standard: **any
field this plan adds to a receipt or a hint must be clipped and newline-stripped on the way
in.**

---

## 4. Phase 2 — still open, now a modification rather than an authoring

All three amendments remain unimplemented. A2 shipping changes their cost: N1 now edits built
code and its tests instead of shaping a task being written.

**N1 — date-stamp `Last said`.** `receipt.py:213` renders `f"Last said: {last_said or 'none'}"`
with no date, and `receipt_one_liner` quotes `Started with / Last said / Open loop` straight
into the recall hint. So an undated present-tense claim about mutable state goes directly into
the prompt weeks later. Render `Last said (YYYY-MM-DD):` using the timestamp of the message the
sentence came from, and update the `test_lines` and `test_one_liner` expectations. Add to the
`<continuity>` component: *"Recalled details are past observations with dates. Verify current
state before asserting it."*

**N2 — `open_loops` as rows.** Unchanged from the wiring plan §Task 7: the table, the insert
at receipt build, the `add_open_loop / list_open_loops / close_open_loop` helpers, and one
hint line when open loops exist in the thread's domains. The extractor already exists in the
built `receipt.py`; only the row write is missing. This is the single genuinely new capability
in the whole programme — the parity matrix has every surveyed system except Nūr scoring zero
on it.

**N3 — record thread state at close.** Now targets Halbert's own `record_state` (§2 Task R1)
rather than the Haloysius ledger, and gains `thread_id`. Source the triples from the receipt's
`Files written` and `Commands` lines plus canonical entities — never from `Last said` prose.
Skip `ephemeral` threads and `origin=terminal` content.

---

## 5. Revised phases after Plan A merges

Ordered by leverage. Every one of these is wiring, deleting, or a small table — there is no
large build left in this programme.

| | Task | Depends on | Size |
|---|---|---|---|
| **R1** | Port the state ledger into the Plan A store (§2) | Plan A merged | small |
| **R2** | N1 + N2 + N3 (§4) | R1 for N3 | small |
| **R3** | Cut the Haloysius episodic line from the spec and the plan (D1.2) | founder sign-off | deletion |
| **R4** | Scope as a property of the query — `domains` argument on receipt search, defaulting to the open thread's domains; `scope_crossed` telemetry; never a user-visible refusal | Plan A A3 | small |
| **R5** | Cumulative eval harness — recall precision at N=10/100/500, no LLM in the loop | Plan A A3 | medium |
| **R6** | Real `messages[]` at `state_machine.py:669,1280,1294` | Plan A A9 | medium |
| **R7** | Abstain-and-probe (D2) — prefer `current_state()` over a command; probe rather than assert | R1, founder answer to Q1 | medium |
| **R8** | Consolidation at idle — cross-thread abstraction into durable preference facts, scheduled into low-load windows | R5 (measure first) | medium |
| **R9** | Fence `HybridMemorySystem` off the agent path with a test so it cannot drift back | Plan A A9a | small |

**R5 before R8 is deliberate.** Consolidation is the one place we would be adding capability
rather than connecting it, and ECHO's result is the caution: strong retrieval metrics with
worse end-to-end answers than a simpler baseline. Measure precision under load first, then
decide whether consolidation earns its cost.

---

## 6. Open questions for the founder

1. **Abstain-and-probe scope (D2).** Everywhere, only for state older than some threshold, or
   only when the answer would drive an action? This decides R7's size and how chatty Halbert
   feels day to day.
2. **The episodic line (D1.2).** Confirm it is cut from spec §8. It is an approved-spec change,
   so it should not be made silently.
3. **Which model slot runs consolidation (R8)?** Not the chat slot. An `llm_config` question.
4. **Does the ledger port (R1) happen before or after Plan A merges?** Recommendation: after —
   it touches the same file Plan A is actively editing, and the current Haloysius-backed
   version works in the meantime.

---

## 7. State of the branches

| Branch | State |
|---|---|
| `main` | research docs committed (`84dc18d`); other sessions active — always use pathspec-scoped commits |
| `feat/continuity-wiring` | Phase 1 complete, 6 commits, suite 1265/0. Ready to merge or to hold until Plan A lands |
| `feat/continuous-conversation` | Plan A through A2; A3+ outstanding |

`feat/continuity-wiring` touches `integrations/state_trackers.py`, `memory/`,
`routes/{memory,persona}.py`, `scheduler/executor.py` and `Halbert/main.py`. Plan A touches
`agents/`, `routes/agent.py` and the frontend. **No file overlap**, so the two branches merge
cleanly in either order.

---

*End of handoff.*
