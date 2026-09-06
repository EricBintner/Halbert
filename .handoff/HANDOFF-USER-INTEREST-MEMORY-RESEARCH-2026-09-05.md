# HANDOFF: The user-interest half — research and UX planning requested

**Date**: 2026-09-05 · **Status**: ANSWERED 2026-09-05 (fable; §Answers below) — research and UX positions, no implementation tasked; the build stays deferred per `CD-5`. Founder calls in §Ratify.
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
| The store of record | Haloysius `memory_v2/observation_store.py` | Live but **empty on a Halbert install**: its only writer is Haloysius's own consolidation, which Halbert never runs. Categories `preference / fact / relationship / pattern / correction`, FTS5, content-hash dedup on `save()` that also un-stales a duplicate; no delete, no confidence/actor/reason columns. Ratified as the cross-session store by `MEM-01`. Haloysius treats it as the FTS index over confirmed `PersonaMemory` rows, which is where confidence and provenance live. |
| The wrapper Halbert already constructs | `PersonaMemoryStore` | Live, at `cognition_wiring.py:278`, `routes/memory.py:228`, `haloysius_memory_adapter.py:72`. |
| Recall | `recall_memory` tool | Registered in `tools/executor.py` — **but it reads the change ledger only** (`tools/recall_memory.py`), never memory_v2. Nothing in Halbert reads `PersonaMemoryStore` or `ObservationStore` into a turn (`routes/agent.py` passes `memory_service=None` on purpose). The reader is as missing as the writer. |
| **The writer** | — | **Missing.** No `remember`-shaped tool is registered. Halbert can read what it never wrote. |
| Research ingestion | `rag/ingestion.py` `add_url`, `POST /api/rag/add` | Live, unbound to any interest model. |
| Scope binding | skills `knowledge_scope` → `resolve_retrieval_scope()` | Half live: `resolve_retrieval_scope()` reads `scope` and `role` only; `knowledge_scope` is parsed and composed but consumed nowhere outside `skills/`. |

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

---

## Answers (2026-09-05)

Research and UX positions for the five question sets, grounded in the code on
`fix/observation-sink` and the spine. Five readers took one set each; a sixth
read them against each other and against the decided rows. Where the readers
disagreed, the position below picks one and says why. Nothing here tasks a
build; the gate in §Sequencing stands.

### 0. Verdict on the requirement's wording

The requirement asks Halbert to *learn from the user, keep long-term memories
of favourites and topics, use them in discussion in the short term, keep
compressed memories recallable later, including downloaded research stored in
RAG.* It should be built in a different shape from its wording, in two places:

1. **"Learn from the user" splits by who selects.** A *stated* favourite
   ("remember that I prefer…") can be any topic and needs no inference. An
   *inferred* interest can only be what Halbert can name deterministically —
   and intake's vocabulary is the sysadmin one (`intake/signals.py`: storage,
   backup, service, network, security, config, the alias table, file paths).
   Arithmetic over threads can see "samba came up on four days this month"; it
   can never see "vintage ThinkPads". So v1 inference covers **what this admin
   works on**, said in those words, and hobby or cultural interests are
   **explicit-only** — unless a user-editable noun file under
   `~/.config/halbert/` is tasked so a person can teach the deterministic layer
   new words (still no model). Reaching for a model to close that gap is
   rejected: it is a selecting model call, and `CD-3`'s rule transfers.
2. **"Downloaded research stored in RAG"** is already true on paper — a JSONL
   that nothing on the ratified retrieval path reads. What honours the spine
   is a small writer with provenance, an honest delete, and citations that
   open (§4).

"Keep compressed memories recallable later" needs no new mechanism: the
compressed form of an interest is its canonical one-line content plus evidence
pointers (thread ids); the conversations themselves are already compressed
into receipts, and `recall_thread` over the evidence ids is the recall.

### 1. Capture — how something becomes a remembered interest

**Policy: two write paths, both with deterministic selection; no model-chosen
write, ever.** `MEM-06` already answers the principle — a stored fact about
the person needs a reason that is a human utterance or a self-naming rule.
Haloysius's own `update_user_knowledge` auto-applies a model-picked value with
the reason "Learned from conversation" and a confidence the model invented;
that is exactly the failure the brief names, and Halbert registers none of it
today.

- **Explicit.** A `remember` tool registered in `tools/executor.py` beside
  `recall_memory`. The executor accepts the call only when the turn's user
  message matches a short deterministic phrase list ("remember that", "note
  that", "keep in mind") **and** the recorded `reason` is a substring of that
  message; otherwise it is refused — a model calling `remember` on a paraphrase
  ("you seem to like…") collapses back into model-chosen writes. `actor` is the
  user plus `speaker_role`; the writer refuses below `member` on a home body.
  `request_id` = the turn. Content passes through `redact_text` first; a Tier-2
  credential is refused with the template answer, never stored. The reply
  echoes the stored sentence verbatim — that echo is the confirmation and the
  first chance to correct.
- **Inferred, as a candidate.** The Consolidator (`continuity/consolidation.py`,
  already idle-tick, `MEM-04`) gains one rule over columns that exist
  (`entities_json`, `topic_domains`, `updated_at`): an entity or domain named on
  **≥ 3 distinct days in 30 days across ≥ 3 non-ephemeral closed threads**. Not
  the current 7-day / 3-thread rule — three threads about samba in one evening
  is a job, not an interest; distinct days are the chat analogue of "that grey
  van, three times this week". The candidate is written with origin
  `inferred`, a self-naming reason ("appeared on 4 days in 30 across 5
  threads"), the thread ids as evidence, and **status `candidate`: it is never
  injected into a prompt until a person confirms it.**
- **Who confirms.** The person, either in conversation or in the list (§2).
  The conversational form is one aside inside a solicited reply, phrased about
  the work, never the person's taste — "samba has come up on four days this
  month; worth remembering as something you work on?" — offered **once**, then
  the list only; unanswered candidates expire at 30 days and are never
  re-raised on the same evidence. This aside is the single exception to §3's
  "never volunteer a fact about the person", and because it initiates in
  miniature it obeys the proactivity dial: Off never, Quiet list-only,
  Balanced and Assertive once. It inherits C2's constraints (solicited turn,
  B4 suppression, one per thread per 24 h) and cannot ship before B4a exists.
  The "yes" turn becomes the `MEM-06` reason for the promotion.
- **Category.** `preference`, with origin carried as a field (§5) — not
  `pattern`, which `observation_store.py` defines as a temporal habit.

Rejected: registering `update_user_knowledge` as-is; a background extraction
model call; and a `StateStore` provenance row for user facts (one reader
proposed it; `MEM-02` reserves the ledger for the machine as its one subject,
and `CD-5` already put favourites in memory_v2).

### 2. Transparency — seeing and editing what is remembered

**Lenses invariant 5 splits.** It governs *directives* — skills, lenses,
`being.yml` — where the file *is* the mechanism, so an editable file with its
source directory shown is right. A remembered fact is *data* (invariant 9),
governed by the four-whys law instead: inspectable in the UI, with who / when
/ how it was learned shown, edited through the store, forgotten with a reach
statement. A file-primary copy of user facts is `MEM-03`'s fifth authority and
a plane `forget` cannot reach; the existing vault refuses write-back on
purpose. A read-only projection is permitted later and is never the edit path.

**Surface, minimal and honest.** One Settings section in the centre panel
under Identity & Voice, titled in plain words ("What I remember about you";
the API path must not say "observations" — that word now means the world
stream). A list grouped by category; each row shows the content, how it was
learned (*stated by you* / *inferred from N conversations over W days* /
*corrected by you*), when, and the message it came from; a Forget action;
forgotten rows behind "Show forgotten" with "Remember again". The same rows
answer "what do you remember about me" in conversation through a deterministic
tool; "forget that" in conversation is staged and confirmed, never executed
from the reply. Edit is not in-place text editing (a hand-edited row has no
source): edit = forget the old row + record the new one as stated-by-you, both
provenanced; memory_v2's `correction` category exists for exactly this. The
unmounted ChromaDB `pages/Memory.tsx` is not this surface and must not be
mounted as a stopgap: it browses the machine's own index and its Clear is a
hard delete on the wrong store.

**"Forget that you know this about me."** A Halbert orchestrator in
`continuity/` mirroring `forget_request`: reach every plane it can, report
per plane, set `complete=False` on any miss, and keep `ERASURE_LIMITS` honest
about the rest. The label is only honest once deletion exists: today
`ObservationStore` has `mark_stale` only (text and FTS row stay on disk), so v1
either reads "Stop using" or ships after the upstream delete. Precedents
already in the tree: `forget_request`'s per-plane report, the timeline's
"Forget this turn" (`redactMessage`), Devices' revoke-vs-Permanently-Forget
pair.

A `stale_reason` convention is needed and none exists: `forgotten_by_user:<turn>`,
`lapsed:<date>`, `superseded_by:<memory_id>`. `save()` un-stales any duplicate
today, so a forgotten fact resurrects the next time the same sentence is
written; until Haloysius respects the `forgotten_by_user` tombstone, the
Halbert writer must check it before every save.

### 3. Recall — surfacing a favourite without reading as surveillance

**The line is attribution, not volume.** The surveillance reading comes from
an unexplained claim about the person; the intuition reading comes from an
explained use. Rule: a remembered fact **never** appears as a sentence whose
subject is the person's taste; it may **colour** an answer (the example
chosen, the default offered), and when it does, one clause whose subject is
the answer says so with its date ("— you said in March you prefer X"). Every
injection, used or not, shows a `memory_recalled` chip with the row's date and
source turn and a *not this / forget* action — the same pattern that ships for
recalled threads. Visibility rides on the chip, never on the model choosing to
mention it.

**The dial governs initiation, not this.** Recall inside a solicited reply is
the same at Quiet, Balanced and Assertive; "Assertive" must never come to mean
"talks about me more". The one coupling: at **Off** nothing is injected —
"purely reactive" — read at the assemble call, not through `ProactiveGate`,
which is severity-keyed and would either always pass or never pass a
preference.

**A recalled interest never initiates.** Not from the scheduler, not as a
`ProactiveEvent`, not as a line in the morning report — a person-fact beside a
grey-van count is exactly the "it was watching me" reading, and a line about
someone's taste has no why-care, so it cannot be a Finding (`C2-03`). Write
the test now that the report builder yields no memory_v2-sourced line.

**RECALL-v1, testable on the prompt and the store, never on model output:**

1. Trigger: inside a solicited turn only.
2. Eligibility: an interest row (§5) with origin `stated` or
   `inferred_confirmed`, status `active`, read through the proxied
   `PersonaMemoryStore` (never a body-local `ObservationStore`, which does not
   travel under Singular Entity).
3. Selection: at most one row per turn, by overlap of the row's topic terms
   with the turn's `MessageSignals.entities ∪ detected_domains` (the thread
   auto-recall arithmetic); ties to the most recent evidence; zero overlap →
   nothing.
4. Suppression: any B4a signal, dial Off, a retraction on this thread, or one
   injection already in the last 24 h on this `thread_id` → nothing.
5. Rendering: its own dated block, one line, with the instruction "use it only
   if it changes the answer; if you do, say so in one clause with the date;
   never state it on its own; nothing else about the person is known". The
   block passes through `redact_text`.
6. Visibility: the chip, always; retract → `forgotten_by_user:<turn>`.
7. Staleness: an inferred interest lapses at 90 days without new evidence
   (a Halbert APScheduler sweep, self-naming reason, `MEM-04`); a stated one
   does not decay by time but is superseded the moment the person contradicts
   it — and memory_v2's contradiction detector cannot see "no longer
   interested in X", so negation is handled by the explicit writer.

Tests: troubleshooting turn + eligible row → no block; candidate (unconfirmed)
→ never injected; second on-topic turn within 24 h → not injected again;
report builder with eligible rows → no memory line; retract → stale, next turn
silent, later human re-mention revives, a system re-save does not; dial Off →
no injection; every injected block carries a date.

### 4. Research ingestion — what "downloaded research stored in RAG" means

**What exists is not what the words say.** Three user-directed triggers
(Settings › Knowledge "Add Custom Documentation", `POST /api/rag/add`, the
CLI) end in `RAGIngestionEngine.add_url`, which appends one JSONL line under
`data/linux/user-sources/` — repo-relative, "linux" regardless of host, no
licence, actor, reason, turn id or scope — and nothing on the ratified
retrieval path (SourcePrep; ChromaDB is eval-only) reads it. Citations cannot
open (`KNOW-1`). Delete rewrites the JSONL only. The fetch is ungated egress
(no `CAP_WEB` check). And the manifest lists that directory under a
permissive-sharealike source, so anything a user ingests is labelled as
distributable corpus by path: a latent gate bypass.

**v1 = "Study this."**

- *Trigger.* User-directed: a URL that appears **verbatim** in the user's own
  turn (a `study` tool, MEDIUM egress like `web_search`, audited, joined to the
  turn) or the Settings form; plus the existing deterministic `doc_suggester`
  (discoveries × the curated registry) as a Knowledge-tab suggestion with
  dismiss — **not** on the attention list, and no "want me to read up on X?"
  from topic recurrence: it has no why-care and is not a Finding. Never
  Halbert-initiated deepening. A freshness re-fetch of already-consented URLs
  comes later on APScheduler.
- *Scope and attribution.* One `research` scope per host in the XDG data dir,
  one markdown file per document with the metadata header
  `jsonl_to_markdown` already emits, carrying url, title, fetched_at,
  content_hash, actor (user | suggestion:<key> | freshness), reason (the
  user's words or the rule name, else UNRECORDED), turn_id, scope, and licence
  as observed. Staged into the SourcePrep knowledge project as its own
  directory so the per-source cap sees it as one source; the model is told the
  scope name so an answer can say "from the page you asked me to read on
  <date>" rather than presenting it as the shipped manuals. Retrieval returns
  an id and the source URL so the why-trust chip opens — done once, as the
  `KNOW-1` "citations open" work, for corpus and research alike.
- *Licensing.* A structural opt-out with a stated reason: research is
  personal-use, per-host, never redistributed; it lives outside `data/`, in no
  manifest source, so no channel build can stage it. Licence recorded as
  observed, for display only. Honour robots.txt / `noai` / TDM signals on any
  fetch Halbert chose; a pasted URL is per-action consent, with a per-URL
  override that records the reason. **Now, with no code: remove
  `linux/user-sources/` from `linux_system_docs.paths` in `data/manifest.json`.**
- *Visibility and removal.* The existing "Custom Added" table grows into a
  Research list (title, url opens, when, who asked, why, scope, licence
  observed, Remove), counted separately from the one corpus number. One delete
  function behind the row and behind "forget what you read about X": removes
  the file, removes it from the research scope (or rebuilds the scope), purges
  any eval-index copy, and reports the planes it did not reach in
  `ERASURE_LIMITS`' voice. Add the research plane to that text when it exists.
- *Topic ↔ research.* The research record carries the turn; a stated interest
  may point at research ids as evidence. The fact "the user read X" is derived
  from the record, never written twice into memory_v2.

Reuse: `ContentExtractor`, `QualityValidator`, the source blocklist, the
markdown header, `SourcePrepClient` + `register_host_project`'s trace/build,
`current_turn`, `redact_text` at the sink (fetched text is invariant-9 data),
the MEDIUM-egress classification, `WhyChip`, `ERASURE_LIMITS`, APScheduler.
Do not reuse: the `data/linux/user-sources` location, the ChromaDB indexer
path, `quick_merge_rag.py`, the dead `force_trust` and `name` parameters, the
top-level `rag-*` CLI commands.

Side findings for their own row: `trending_discovery` sends the detected stack
to `api.github.com` on Knowledge-tab open and `rag/freshness.py` calls
HuggingFace, both ungated by `CAP_WEB` despite `TRUST-1`.

### 5. The boundary — where "the user is interested in vintage ThinkPads" sits

**An interest is a memory_v2 `PersonaMemory`, mirrored as an `ObservationStore`
`preference` row.** `StateStore` never holds a user fact (`MEM-02`: one
subject, the machine; one open row per key; host-bound). The freshness rule
("memory holds what cannot be re-derived: preferences, commitments; the
machine holds current state") and design strategies §4.8 ("admin preferences
are the only portable tier") both point at memory_v2, which is proxied to the
canonical host under Singular Entity — the `ObservationStore` is not, which is
why it is the index and not the record.

This is a change to the wording of one decided line — the lenses plan's A3
table says "fact about the user → Haloysius `ObservationStore`" — and is listed
for ratification (RQ-1) rather than applied.

**A learned interest differs from a stated one in fields, not in store.** Same
row, three explicit fields: `origin` (stated | inferred | inferred_confirmed),
`evidence` (stated: thread and turn ids; inferred: count, window, thread ids,
computed arithmetically in Halbert), `last_confirmed_at`. Confidence stays
derived from `source` (memory_v2 gives `user` 0.9, `conversation` 0.7) and is
never a bare number the UI shows — the UI shows the origin and the evidence.
Two Haloysius defects block this as it stands: `teach()` and `update_preference()`
leave `memory.source` at `conversation`, so a stated fact gets the inferred
confidence; and the contradiction detector cannot see "no longer interested".

**The row.** One `PersonaMemory` per interest through the `PersonaMemoryStore`
Halbert already constructs: type SEMANTIC; canonical content
`User is interested in: <topic>`; `source` user or conversation; tags
`interest`, the origin, the topic slug (the slug replaces content-hash dedup,
so "ThinkPads" and "vintage ThinkPads" do not fragment); keywords = topic
terms (the deterministic recall anchor); metadata with topic, origin,
evidence, first_seen_at, last_evidenced_at, last_confirmed_at, status
(candidate | active | lapsed | forget_requested), actor with `speaker_role`,
reason (the utterance or the self-naming rule, never model text), body_id.
Metadata is a free dict, so a Halbert-side dataclass and a test at the boundary
are the difference between this and the removed `MemoryWriter`'s "nothing
ever written could be read back". The derived `ObservationStore` row:
category `preference` set explicitly (the keyword classifier files "interested
in" as `fact`), the same canonical content, `source_memory_id` set so
`mark_stale_by_memory` works — written only when status is `active`.

**Forget must reach** the memory (hard delete exists), the observation row and
its FTS row (no delete exists upstream — the row outlives the fact today), the
knowledge index rebuilt from observations, the embedder index, and under
Singular Entity the canonical host's copy; it reports each and sets
`complete=False` on a miss. It does not reach the thread messages (redacted by
their own mechanism), backups, or the Consolidator's `preferred_entity` rows —
which are machine-work recurrence, not user facts, and should be documented as
such or retired (their last-entity-wins bug already keeps them out of the
vault).

### Ratify

Nine calls, none of which tasks a build:

| # | Call | Recommendation |
|---|---|---|
| RQ-1 | The boundary: `PersonaMemory` is the row of record, `ObservationStore` its derived index; `StateStore` never holds user facts; amend the lenses A3 line accordingly | yes |
| RQ-2 | A `DECISIONS` row that memory_v2 user facts may be read into a turn under RECALL-v1 (D1 forbade any Haloysius read path; `MEM-01` narrowed it without saying this) | add the row |
| RQ-3 | Capture policy: explicit writer + arithmetic candidates + person confirms; no model-chosen writes; the one confirmation aside is dial-gated | as written in §1 |
| RQ-4 | v1 inference covers what this admin works on (intake vocabulary); hobby and cultural interests are explicit-only unless a user-editable noun file is tasked | state it on the surface; task the file |
| RQ-5 | Invariant 5 splits: directives → editable file with source; facts → UI list with who/when/how and a forget that reports its reach | ratify the split |
| RQ-6 | "Forget" vs "Stop using" while `ObservationStore` has only `mark_stale`; raise `delete` + `secure_delete`, the tombstone-respecting `save()`, and `source='user'` on `teach()`/`update_preference()` as Haloysius Phase-1 items | "Stop using" until delete exists; raise all three upstream |
| RQ-7 | Research: structural licence opt-out outside `data/`; remove `linux/user-sources/` from the manifest now; pasted URL = per-action consent, anything Halbert chooses sits behind `CAP_WEB`; research is per-host | yes to all four |
| RQ-8 | Per-person facts on a home body (`W3-C03`): the row carries `speaker_role`; the writer refuses below `member` | yes, pending W3-C03 |
| RQ-9 | `C2`'s aside rule becomes a `DECISIONS` row, since lenses, capture and recall all lean on it and it lives only in a handoff | add the row |

### Corrections to the inventory above

- *Recall* is not `recall_memory`: that tool reads the change ledger only.
  Halbert has neither a writer nor a reader for user facts on the turn path.
- *Scope binding* is half live: `knowledge_scope` is parsed and never consumed.
- The `ObservationStore` on a Halbert install is empty: its only writer is
  Haloysius's consolidation, which Halbert does not run.
- `ERASURE_LIMITS` already names memory_v2's plaintext store as unreached; that
  clause stays until RQ-6 lands.
