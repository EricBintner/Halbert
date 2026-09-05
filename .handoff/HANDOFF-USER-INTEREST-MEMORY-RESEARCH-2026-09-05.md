# HANDOFF: The user-interest half — research and UX planning requested

**Date**: 2026-09-05 · **Status**: OPEN — research brief, no implementation tasked
**Decision that opened it**: `CD-5` sub-question, decided 2026-09-05 — **deferred, with
this document so it cannot be dropped silently again**
**Rows**: `MEM-01` (`ObservationStore` is the store of record); no implementation row yet

## Why this document exists

There is a founder requirement of record, quoted from the original nerd-scopes
document (:354–355):

> learn from the user, keep long-term memories of favourites and topics, use them
> in discussion in the short term, keep compressed memories recallable later,
> including downloaded research stored in RAG.

It has two halves. The **observation half** — what Halbert finds worth remarking
on about the world — is the Observation Lenses plan, and branch 1 has shipped its
foundation. The **user-interest half** — what Halbert remembers about *the person* —
has never been tasked. Rev 1 of the lenses review cut it silently; rev 2 caught
that and carried it as D9; `CD-5` has now deferred it deliberately.

Deferred is not dropped. This document is the difference.

## What already exists (verified 2026-09-05)

| Piece | Where | State |
|---|---|---|
| The store of record | Haloysius `memory_v2/observation_store.py` | Live. Categories `preference / fact / relationship / pattern / correction`, FTS5, content-hash dedup on `save()`. Ratified as the cross-session store by `MEM-01`. |
| The wrapper Halbert already constructs | `PersonaMemoryStore` | Live, at `cognition_wiring.py:278`, `routes/memory.py:228`, `haloysius_memory_adapter.py:72`. |
| Recall | `recall_memory` tool | Registered in `tools/executor.py`. |
| **The writer** | — | **Missing.** No `remember`-shaped tool is registered. Halbert can read what it never wrote. |
| Research ingestion | `rag/ingestion.py` `add_url`, `POST /api/rag/add` | Live, unbound to any interest model. |
| Scope binding | skills `knowledge_scope` → `resolve_retrieval_scope()` | Live. |

So the storage question is answered and the retrieval question is answered. **What
is missing is a writer, and — more importantly — the judgment about when to use it.**

## What is being asked for

Research and UX planning, not an implementation plan. The questions below are the
deliverable; answering them is what this document wants back.

### 1. Capture — how does something become a remembered interest?

- Explicitly only ("remember that I prefer…"), inferred from conversation, or both?
- If inferred, what is the evidence bar? A single mention is noise; the recurrence
  argument that `CD-3` settled for observations may or may not transfer to chat.
- Who confirms? A silently-inferred preference that turns out wrong is worse than
  no preference, because the user cannot see why Halbert is behaving oddly.
- **Constraint already decided**: `CD-3` ruled that *observation* selection is
  arithmetic, never a model's choice. Whether the same rule should bind preference
  capture is an open and non-obvious question — chat has no recurrence count.

### 2. Transparency — how does the user see and edit what is remembered?

- Standing directive: every behavioural directive exists as an editable file on
  disk, inspectable in the UI, with its source shown (lenses invariant 5).
  `ObservationStore` is a SQLite store, not files. Does the directive extend to it?
- What is the surface? A list, a per-item why, an undo?
- How does someone say "forget that you know this about me", and does it reach
  every plane? (See the erasure work: `ERASURE_LIMITS` now names the event ledger
  as unreachable; memory_v2's plaintext store is already named there too.)

### 3. Recall — when does a remembered favourite surface without being creepy?

This is the hardest question and the one most likely to sink the feature.

- Volunteering "you liked X" unprompted reads as surveillance; using it silently to
  shape an answer reads as intuition. Where is the line, and does it move with the
  proactivity dial?
- Does a recalled interest ever *initiate*, or only colour a solicited turn? The
  lenses plan drew that line hard for remarks (`C2`: an aside inside a solicited
  reply, never a Halbert-initiated interrupt). The same reasoning probably applies.
- What is the failure mode when the memory is stale — an interest someone has moved
  on from — and what decays it?

### 4. Research ingestion — what does "downloaded research stored in RAG" mean?

- What triggers it: the user asking Halbert to read something, Halbert deciding a
  topic is worth deepening, or a periodic sweep?
- How is it scoped and attributed, so a later answer can say where it came from?
- What are the licensing bounds? The corpus licensing gate already governs what may
  enter the RAG index; ad-hoc user-directed ingestion needs to respect the same
  policy engine or explicitly opt out of it with a reason.
- How does the user see what has been ingested, and remove it?

### 5. The boundary question

`MEM-01` splits the stores by shape. Two are now clear:

- **Machine-state history** (what the house and the machine did) → `TimelineStore`,
  the event ledger.
- **Current state** (what is true now, why, since when) → `StateStore`.
- **Facts about the user** (preference, relationship, correction) → memory_v2
  `ObservationStore`.

Where does "the user is interested in vintage ThinkPads" sit — a `preference`, or
something with no home yet? And does a *learned* interest differ in kind from a
*stated* one, in storage or only in confidence?

## What this document is not asking for

- Not an implementation plan, and not code. If the research concludes the feature
  should be shaped differently from the requirement's wording, say so.
- Not a decision on whether to build it. That is the founder's, and `CD-5` has
  already deferred the build until the observation half has been used.

## Sequencing

Nothing here starts before C1a has shipped and a week of Noticed sections has been
read — the same gate `CD-1` put on lenses. The reason is the same: the observation
half is about to produce real output, and real output should inform what is worth
remembering about the person reading it.
