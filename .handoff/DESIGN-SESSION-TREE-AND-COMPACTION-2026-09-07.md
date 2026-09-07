# D-1 Design: Session Tree and Compaction — one continuous conversation on an append-only tree

**Date:** 2026-09-07
**Pass:** D-1 (design only — no code, no commits). Feeds the F-3 joint curated-core session.
**Source reviews:**
- `.handoff/OSS-REVIEW-HERMES-2026-09-07.md` §3 (rotation machinery), §6 (memory discipline), §7 (turn leases)
- `.handoff/OSS-REVIEW-OPENCLAW-2026-09-07.md` §1 (memory tiers), §2 (session tree + compaction)
**Lands on:** `.handoff/OPENCLAW-LIFT-PACKET-08-STORE-HARDENING-2026-09-07.md` (durability PRAGMAs, FTS fail-open, declarative column reconciliation)
**Must reconcile with:** `.handoff/OPENCLAW-LIFT-PACKET-01-MEMORY-PROMOTION-2026-09-07.md` Phase B (the curated core)

**Verified current state (re-verified in repo 2026-09-07):**
- `halbert_core/halbert_core/agents/conversation_sqlite.py` — `SCHEMA_VERSION = 4` (schema_version table, `SELECT MAX(version)`); `_THREAD_COLUMNS` / `_MESSAGE_COLUMNS` additive lists applied by `_add_missing_columns`; tables `conversations`, `messages`, `session_somatic_blocks`, `schema_version`, `compact_boundaries` (**no writers** — reserved by Plan A spec §8/§14), `terminal_blocks`, `terminal_sessions`, `open_loops`; FTS5 (`messages_fts`, porter+unicode61) with `_fts_ok` LIKE fallback. `conversations` already carries `parent_thread_id`, `merged_into`, `title_source` (default `'provisional'`), `receipt`, `status` (default `'open'`); `messages` already carries `turn_id`, `session_id`, `origin`, `status`, `blocks_json`, `visible_in_timeline`.
- `halbert_core/halbert_core/agents/threads.py` — `ThreadManager.begin_turn` (:308) resolves the thread via `thread_signals.decide`, strong-match auto-recall of a closed thread at :353-359, persists the user row `in_progress`; `end_turn` (:412) writes the assistant row and refreshes the receipt; `tick()` (:619) sweeps paused threads closed and runs the Consolidator at the end (R8, non-LLM).
- `halbert_core/halbert_core/agents/state_machine.py` — `_handle_planning` (:1900) makes the single `context.assemble(...)` call (:1939) and appends the receipt block to `context_content` (:1974-1978); `_build_messages` (:1783-1806) rides `ctx.thread_receipt_block` on `messages[0]["content"]` and glues the continuity hint to the final user message; `_turn_lock` (:324, per-event-loop `asyncio.Lock`) serializes turns with a timeout event stream (:717).
- `halbert_core/halbert_core/persona/guest_tools.py` — guest tool surface includes `new_thread` (allowed) and `recall_guest_memory` (:97); `recall_thread`/`resume_thread` are owner-only. Thread identity is therefore a guest-reachable concept.

---

## 0. The decision this document asks the founder to ratify

There are two tree-shaped problems, and the reviews solve them with two different unit shapes:

1. **Topic threads** ("hidden topic threads" — the founder directive: one seamless chat, hidden threads, recall by relevance, NO conversation list). Halbert already implements ~80% of this: threads are rows in `conversations`, topic switches pause and reopen them, receipts are per-thread rolling summaries.
2. **Context-window rotation** (a single thread outgrows the window; the transcript must compress without losing the conversation). This is what `compact_boundaries` shipped empty for, and what Hermes's `publish_compression_child` pre-solved.

The two problems interact at exactly one place — *does compaction fork the thread row, or does the thread row survive compaction?* — and the whole design hangs on the answer. Hermes forks (close parent session, publish summary child session; the turn lease walks to the lineage root). OpenClaw marks (the transcript is an append-only entry tree; compaction is an entry in the tree; the leaf moves, rows never re-parent).

**This design recommends the OpenClaw unit shape with the Hermes transaction discipline**: the thread row is permanent and never re-parented; compaction is append-only *entries* (a summary message row + a `compact_boundaries` row) inside the same thread; the atomic close+publish transaction, the watermark, and the anti-thrash counters are kept from Hermes, adapted to marker-shaped rotation. §1.3 gives the reasoning. The alternative (Hermes segment rotation, verbatim) is costed in §7, Q1.

## 1. Data model

### 1.1 The tree is over two existing row kinds, not a new node table

The reference implementations both use a parent column on the node row. Halbert's nodes already exist:

- **Thread nodes** = `conversations` rows. `parent_thread_id` already records topic-switch provenance (`_open_new_thread(..., from_thread_id=...)`).
- **Entry nodes** = `messages` rows, ordered by `id` within a thread. Entries include user rows, assistant rows (with `blocks_json` for tool results — tool results ride the assistant row, they are not separate rows), and — new — **compaction entries** and **branch-summary entries**, both plain message rows distinguished by `role='system'` plus a `metadata.kind` marker, both persisted *once* and then free.

**No separate node table.** A third table would duplicate id space and force every existing join (`terminal_blocks.thread_id`, `open_loops.thread_id`, `receipts_fts`, promotion signals keyed on thread entities, `redact_message`/`_scrub_thread_entities` walking message ids) to learn a second address space. The parent-column approach wins on Halbert's actual constraint: thread id is the join anchor for five other subsystems.

**Edge typing — deviation from Hermes, deliberate.** Hermes packs four edge types (continuation/branch/delegate/tool) into one `parent_session_id` column distinguished by JSON markers. Halbert instead adds one additive column (packet-08 reconciliation makes column adds free, and the founder's "no legacy support" posture means no marker-parsing shim is ever needed):

```sql
-- conversations, additive (M1):
edge_kind           TEXT NOT NULL DEFAULT 'root'
  -- root | continuation (auto topic switch) | branch (explicit new_thread tool)
  -- | delegate (future: subagent sessions) | merged (merged_into already exists)
```

A typed column is indexable (`WHERE edge_kind='delegate'`), checkable by `CHECK` constraint, and legible in `PRAGMA table_info` dumps. The JSON-marker trick exists in Hermes because its schema predates typed edges; Halbert has no such history to preserve. Where the deviation costs anything (porting Hermes queries verbatim), the mapping is mechanical: `edge_kind IS NOT 'root'` ≡ `parent_session_id IS NOT NULL`.

### 1.2 The leaf: one open row, made structural

Today the leaf is *derived*: `current_open_thread()` (:1314) picks the `status='open'` row, and correctness rests on writer discipline (`_pause_thread`, `_reopen_thread`). The tree makes the leaf a load-bearing invariant — every topic switch is a leaf move — so make it structural:

```sql
CREATE UNIQUE INDEX IF NOT EXISTS idx_one_open_leaf
  ON conversations(status) WHERE status='open';
-- scope note: if guest/owner get separate leaves (§7 Q3), the predicate
-- gains a persona scope column; design the index after that decision.
```

Topic switching, auto-reopen, explicit `new_thread`, and `resume_thread` all become one primitive: **move_leaf(old, new, edge)** — a single transaction that sets old `status='paused'`, sets new `status='open'`, stamps `parent_thread_id`/`edge_kind` on the child, and (§2.3) mints the branch-summary entry if one is due. The partial unique index turns "two open threads" from a logic bug into a constraint violation at the exact commit that caused it. `merged_into` stays as-is (merge is a terminal supersession edge, already append-only in effect).

### 1.3 Compaction stays inside the thread row — `compact_boundaries` becomes the rotation ledger

Hermes's `publish_compression_child` answers "how do readers never see an ended parent with a missing child?" by making the parent and child *different session rows* swapped in one transaction. In Halbert the same guarantee is cheaper: the thread row never ends, and the compaction is a **cut point** recorded on the append-only ledger:

```sql
-- compact_boundaries, gains writers and columns (M1):
ALTER ... ADD COLUMN coverage_end_id   INTEGER;      -- watermark: messages.id of the last row folded into the summary
ALTER ... ADD COLUMN generation        INTEGER NOT NULL DEFAULT 1;
ALTER ... ADD COLUMN unresolved_request TEXT NOT NULL DEFAULT '';  -- latestUnresolvedUserRequest, carried across generations
ALTER ... ADD COLUMN trigger_detail    TEXT NOT NULL DEFAULT '';   -- 'window' | 'turn_cap' | 'manual' (+ existing trigger col)
-- summary_message_id (already shipped) points at the persisted summary entry:
-- a messages row, role='system', metadata.kind='compaction_summary',
-- visible_in_timeline=1, context_included=1 (§1.4), content = structured summary (§4.2).
```

**Why markers, not segment rotation.** (a) *Redaction identity*: `redact_message`, `forget_request`, `_scrub_thread_entities` and the `_is_founding_user_row` guard all address messages by `(thread_id, message_id)`; re-parenting tail messages into a child row either clones ids (breaking the audit trail) or rewrites `conversation_id` on live rows (violating append-only and the FTS fail-open contract's "canonical rows never mutate after write" posture). (b) *Lease stability*: with marker compaction, the lineage root is *always the thread id* — there is no walk. Hermes needs the walk precisely because rotation forks the row; not forking makes the walk unnecessary (§3.3). (c) *Guest memory*: `recall_guest_memory` and the receipt/FTS recall paths key on thread id; a forked thread row would silently split a guest's "same subject" across two ids.

With markers, the Hermes reader race — "reader sees boundary but no summary" — is closed by writing **the summary message row and the boundary row in one SQLite transaction** (§3.1), which is atomically visible or not at all. Same incident lesson, smaller mechanism.

### 1.4 Supersession vs append-only for the receipt columns

The doctrine split, stated once so nothing drifts:

- **Append-only (canonical fact):** `messages` rows, `compact_boundaries` rows, `open_loops` rows, branch-summary entries. Never updated after insert (existing `update_message` is restricted to `status`/thread-reassignment at turn end — kept, it finalizes an `in_progress` row, which is a lifecycle stamp, not content mutation).
- **Derived projections (rebuildable, mutable):** `conversations.receipt`, `receipt_updated_at`, `entities_json`, `topic_domains`, `title`, `messages_fts`, `receipts_fts`. These may be superseded in place **because they are recomputable from the append-only layer** — the same status FTS has under packet 08's fail-open contract. The receipt is a *cache of a branch summary*, not the branch summary itself; the persisted, never-rewritten form is the branch-summary entry row (§2.3).
- **Title** upgrades to the Hermes provenance CAS ladder (`provisional < refined < user`): `title_source` already exists with default `'provisional'`; `update_thread` becomes a compare-and-swap — `UPDATE conversations SET title=?, title_source=? WHERE id=? AND title_source IN (<lower ranks>)` — so an LLM-refined title never clobbers a founder-typed one.

## 2. Context as projection of a path

### 2.1 What the assembler sees

Today: `_handle_planning` makes one `context.assemble(...)` call (:1939) and the conversation travels as `ctx.conversation_history` + `ctx.thread_receipt_block` riding `messages[0]` (:1784-1785). Under the tree, conversation history becomes the **path projection**:

```
path(leaf) = walk conversations.parent_thread_id from the open leaf to root
projection(path) =
    [ compact summary entries (latest boundary per thread on path, newest wins) ]
  + [ branch-summary entries along the path (one per edge crossing, minted once) ]
  + [ messages of the leaf thread with id > latest boundary.coverage_end_id,
      context_included=1, in id order ]
```

Three concrete seams change:

1. **`ThreadManager._history`** (threads.py, feeds `TurnContext.history`) — reads `latest boundary for thread → summary entry + rows above coverage_end_id` instead of the raw recent window. One read-site swap; the receipt row `_history` writes today is *replaced by* the persisted summary/branch entries (the `_split_receipt_row` dance in the assembler — threads.py:119-121 comment — goes away; the entries are already rows of the right shape).
2. **The receipt block** (`ctx.thread_receipt_block`, state_machine.py:1784) — narrows to *path receipts*: the receipts of ancestor threads on the path (already what auto-recall surfaces), **not** the compaction summary (which is a message entry now, riding the array in position — better for prefix-cache-adjacent behavior than growing `messages[0]`). The `## Earlier in this subject` header and the fence/defang rules (threads.py:107-148, `_defang_continuity`) apply to summary and branch-summary entries unchanged — they are model-facing renderings of untrusted stored text, and the receipt block's "joins the leading instructions, defanged on the way in" rule extends verbatim.
3. **The continuity hint** (`_continuity_tail`, glued to the final user message :1802-1805) — untouched. OpenClaw's `latestUnresolvedUserRequest` lives on the *boundary row* (§4.3), not in the hint; the hint stays about *which thread* we're in.

### 2.2 `context_included` — the display/context split

OpenClaw's `excludeFromContext` separates "what the dashboard shows" from "what the model sees." Halbert already has the display half (`visible_in_timeline`, default 1). Add the other half as its own column rather than reusing metadata, because the projection query filters on it every turn:

```sql
-- messages, additive (M1):
context_included INTEGER NOT NULL DEFAULT 1
```

First consumers: branch-summary entries (visible? yes — a subtle divider; in-context? see §2.3), steering/interruption marker rows if the interrupt-algebra packet lands (persisted facts that must not re-enter the prompt as user speech), and any row a future redaction keeps visible-but-withheld. The timeline never gains a conversation list — per the founder directive, hidden threads stay hidden; the only new UI affordance is optional and is a §7 question (Q4).

### 2.3 Branch summaries: minted once, persisted as entries

OpenClaw: returning to a topic generates a branch summary *once*, persisted as an entry ("The user explored a different conversation branch before returning here"). Halbert mapping — and this is the piece that turns "hidden topic threads" from pause/resume into a tree:

- **When `move_leaf` crosses away from a thread that has turns since its last branch-summary entry**, the same transaction refreshes the thread's receipt (existing `_refresh_receipt`) **and inserts one branch-summary entry message** into the *departed* thread: `role='system'`, `metadata.kind='branch_summary'`, `visible_in_timeline=1`, `context_included=0` in the departed thread (it describes the departure; the departing thread's own replay doesn't need it), content built from the receipt by deterministic template — **no LLM** (tiered-sensitivity rule: never a model where a template suffices; receipts are already deterministic).
- **When the leaf returns** (auto-reopen or `resume_thread`), one corresponding entry lands in the *returned-to* thread with `context_included=1`: "you explored <other receipt title> in between; you are back on <this receipt title>" — rendered defanged, template-built, minted once per edge crossing (keyed by `(from_thread, to_thread, boundary message id)` in metadata so a crash between the two inserts retries idempotently).
- Subsequent visits are **free**: auto-recall already surfaces the receipt via FTS (`begin_turn`:353-359); the entries just make the path honest.

### 2.4 Layering vs the curated core (the F-3 statement)

Three context sources, three layers, explicitly distinct so F-3 can place them:

| Layer | Content | Written by | Injection |
|---|---|---|---|
| **Transcript (this design)** | path projection: summary entries, branch entries, live tail | turn lifecycle, rotation transaction | message array |
| **Curated core (packet 01 Phase B)** | promoted durable facts, `## What I remember`, ~2k chars | promotion gates only — deterministic | `messages[0]` tier named `curated` |
| **RAG/world/intake** | external retrieval, observations | existing assembler sources | assembled `context_content` |

Rules: compaction **cannot write** the curated core (summaries are lossy transcript compression, never promoted fact); a thread-close event is a **promotion signal source** (§5.2), not content. The R9 fence (`context/adapters.py`:472, `routes/agent.py`:164-166) is untouched — the transcript projection is not a memory service and does not route through `memory_service`.

## 3. The rotation transaction

### 3.1 Atomic close+publish, adapted to markers

Hermes `publish_compression_child` (:close parent + publish child + stamp parent, one transaction). Halbert's equivalent, one `BEGIN IMMEDIATE` on the conversation store:

```
TXN rotate(thread_id, summary_text, coverage_end_id, unresolved, trigger):
  1. INSERT messages (role='system', kind='compaction_summary',
                    context_included=1, turn_id=NULL)           -> summary_message_id
  2. INSERT compact_boundaries (..., summary_message_id, coverage_end_id,
                                generation = prev.generation + 1, unresolved_request)
  3. UPDATE conversations SET compact_streak = compact_streak + 1,
                              compact_last_at = ?, receipt = <refreshed>
     WHERE id = thread_id
  COMMIT
```

Readers either see both rows or neither — the ended-parent-with-missing-child race cannot exist because there is no parent close. The summarization itself runs **before** the transaction, off-lock (it is slow LLM work; the store lock is held only for the commit, matching the existing `_locked` decorator's discipline — threads.py:222).

### 3.2 The watermark tail-clone

Hermes takes a watermark at compression start and column-clones messages appended *during* summarization into the child. With marker compaction nothing is cloned:

- **Watermark** `W = SELECT MAX(id) FROM messages WHERE conversation_id=?` taken before summarization begins (under a read, no lock needed — ids are monotonic).
- Summarize rows `id <= W` (restricted to `turn_id` groups fully inside the range — §4.1).
- `coverage_end_id = W`.
- Rows appended during summarization (`id > W`) are simply part of the live tail; the projection (§2.1) includes them by construction.

The clone exists in Hermes to move late rows across the parent/child fork. No fork, no clone — the watermark becomes pure metadata. *Deviation, logged:* if Q1 (§7) ever flips to segment rotation, this section is the one that reverts to Hermes verbatim, clone included.

### 3.3 Lineage-rooted turn leases vs `_turn_lock`

Hermes keys the turn lease to the transcript owner and walks to the lineage root so every rotation segment serializes under one identity. Halbert's facts: single-process store, `_turn_lock` is an in-process per-loop `asyncio.Lock` (:324-357), and marker compaction never changes the thread id. Therefore:

- **Lease key = `TurnContext.thread_id`, unchanged.** Under marker compaction the thread id *is* the lineage root — stable across rotations by construction. `_turn_lock` stays; nothing about the lock's acquire/timeout paths (:466, :717-741) changes in M1-M3.
- **Rotation must not run inside a live turn's lock window for its own thread.** Compaction triggers evaluate at `end_turn`/idle-tick time (after `end_turn` releases), never mid-turn — same discipline Hermes applies (compression demotes interrupts; here, turn boundaries only, §4.1).
- **Record, don't build:** if a second process ever attaches to the DB (the packet-08 out-of-scope guard's trigger), adopt Hermes's persisted lease keyed by lineage root at that time; the schema already has room (`conversations.metadata` or a `leases` table). Designing for it now would be the multi-instance receipt-matrix anti-pattern.

### 3.4 Persisted anti-thrash counters

In-process rotation counters evaporate on restart and thrash resumes — Hermes's fix is counters on the session row. Additive on `conversations` (M1):

```sql
compact_streak         INTEGER NOT NULL DEFAULT 0   -- rotations since last user turn on this thread
compact_cooldown_until REAL                          -- merge-max on set
compact_last_at        REAL
```

Policy (deterministic, no LLM): never rotate a thread with a turn in flight; never rotate twice within `cooldown_until` (set to `now + min(2^streak * 60s, 6h)` on rotation, merge-max); reset `compact_streak` on any `origin='human'` append to the thread. These four lines are the entire anti-thrash machine; they live on the row so a crash/restart resumes the same cooldown.

## 4. Compaction mechanics

### 4.1 Cut points at turn boundaries

OpenClaw's first rule: never cut between an assistant message and its tool results. Halbert makes this cheap: tool results ride the assistant row (`blocks_json`), so a turn is exactly a `turn_id` group of rows. The cut-point selector walks `turn_id` groups (using the id-window bounding the PERF NOTE at conversation_sqlite.py:130-143 prescribes — never the unbounded `list_turns` GROUP BY) and cuts only *between* groups. Legacy rows with `turn_id IS NULL` fall back to the `COALESCE(turn_id, 'm'||id)` key already used by `_TURN_KEY`, which is one row per group — always cut-safe.

### 4.2 Iterative summary structure

Port OpenClaw's structure (`packages/agent-core/src/harness/compaction/`) as the summary entry's content template:

```
## Earlier in this subject (compacted, generation N)
Goal: …
Constraints: …
Progress: …
Decisions: …
Next steps: …
Unresolved request: <latestUnresolvedUserRequest>
Files touched: <exact paths, carried across generations>
Errors seen: <exact error text, verbatim>
```

Rules lifted verbatim: **preserve exact file paths and error text**; file-operations lists extract from the assistant rows' `blocks_json` (terminal blocks already carry `command`/`cwd` — the file-operation extraction reads `terminal_blocks` by `thread_id + id <= coverage_end_id`, it does not re-parse prose); each generation's summary folds the *previous generation's summary* plus the new range (iterative, so generation N is a fixed-size object regardless of thread length); a binary-searched size fits the remaining window budget per the context-budget rules `context_budget` already enforces. The previous generation's entry row stays in the store (append-only; searchable per packet 08's visibility rule — §4.4) but drops out of the projection (`context_included` remains 1; the projection simply takes *latest boundary only*).

**Where the LLM sits:** summarization is utility-slot work (the model-pick deep pass's slot trio), gated by the R5 harness per the Hermes eval blueprint — scorecard before enable. Until un-gated, the trigger fires the *flush* path only (§4.5) and writes no boundary. This keeps today's `compact_boundaries`-has-no-writers posture honest rather than accidentally shipping it.

### 4.3 Unresolved-request carryforward

`latestUnresolvedUserRequest` persists on the boundary row (`unresolved_request` column, §1.3). Extraction is deterministic-first: last `origin='human'` row whose turn group has no `status='complete'` assistant row — that is computable from existing columns with zero model calls. If the eval-gated summarizer is enabled it may *refine* the string, but the deterministic value is always what's stored; the model's refinement rides `metadata` where it can be compared, never trusted. A mid-request compaction can then resume the ask from the projection alone — the `## Earlier` entry carries the ask verbatim.

### 4.4 Searchable compacted rows

Packet 08's bonus rule, restated as a projection rule here: **compaction changes what the model sees, never what search sees.** FTS indexing is unaffected by boundaries (triggers fire on insert; old rows stay indexed); receipt FTS (`receipts_fts`) covers the receipt which refreshes across rotations; `context_included` is the only visibility knob compaction touches, and only via "latest boundary wins" in the projection. Search excludes rows only when `visible_in_timeline=0` (the rewound/forgotten path) — unchanged.

### 4.5 Pre-compaction flush

OpenClaw's flush ("compaction can never erase unwritten facts") maps onto Halbert's existing deterministic pieces rather than a silent LLM flush turn: before any boundary write, (a) refresh the thread receipt, (b) snapshot open loops for the thread (`open_loops` rows are already durable — the flush asserts they exist for any `Next steps:` the summary asserts), (c) record the thread's entities as promotion-signal candidates (§5.2). The LLM-dependent "flush memories you haven't written" turn stays out — the Consolidator (tick-end, non-LLM) is the write path, and Halbert's durable facts live in `state_store`, not in the transcript, so there is nothing an LLM flush could save that the ledger doesn't already hold. *Deviation from OpenClaw, justified by the tier split:* their daily note *is* the durable store; ours isn't.

## 5. Interactions

### 5.1 Guest persona

- **Thread identity is guest-visible** (`new_thread` allowed, `recall_guest_memory` guest-facing). Under the tree, guest threads are ordinary nodes with persona provenance on the row (existing `user_id`/metadata; no schema change needed — verify at dispatch that guest threads carry a stable persona marker, add `persona TEXT` additive column if they don't).
- **Edges stay inside persona scope**: a guest topic switch mints continuation edges among guest threads; the recall/branch-summary machinery already resolves through `search_receipts`, which the guest surface keys to guest-owned threads via `recall_guest_memory` — the tree adds no cross-persona path because the projection only walks `parent_thread_id` chains, and `move_leaf` refuses a parent in a different persona scope (one `CHECK` in the transaction; the guest persona's "execute-level deny" posture gets one more deterministic gate, not a judgment call).
- **Leaves**: open question Q3 (§7) — one global open thread vs one per persona scope. The partial unique index (§1.2) is written after that answer.

### 5.2 Packet 01 promotion signals

Packet 01 A2 wires two signal sites (thread auto-recall admit, `recall_memory` results). The tree adds a third and a fourth, both fail-soft per the "memory failures never eat a turn" rule:

1. **Thread close events** (tick sweep, threads.py:619+): a closed thread's `(subject, predicate)`-shaped entity keys get a recency-weighted signal — *durable things keep coming from repeatedly lived subjects*. Thread-close is the strongest "this subject mattered" evidence the system produces.
2. **Compaction boundaries**: entities carried in `Files touched:`/`Decisions:` sections are candidates-by-survival — they survived a lossy pass. Recorded as signals with provenance `compaction_survivor`, distinct from `recalled_content` (the recall-loop hygiene rule — packet 01's `provenance` guard — is *not* violated: boundary content is transcript, not recalled core output; but to stay strictly inside the second-guess doc's alignment rule, signal keys remain `(subject, predicate)` claim-shaped, never thread ids or message ids).

## 6. Migration plan

| Packet | Contents | Lands independently? | Atomic units |
|---|---|---|---|
| **T1 — schema (additive)** | `edge_kind`, title-CAS update path, `context_included`, `persona` (if needed), compact counter columns, boundary writer columns (`coverage_end_id`, `generation`, `unresolved_request`), one-leaf partial unique index. Zero reader/writer behavior change. | Yes — merges with or right after packet 08 (same reconciliation machinery; packet 08's declarative `_reconcile_columns` supersedes the `_add_missing_columns` list growth) | One release; index creation is the only blocking statement |
| **T2 — projection readers** | `_history` reads boundaries; branch-summary minting inside `move_leaf`; receipt block narrowed to path receipts; `## Earlier` entry rendering through existing defang. Old-shape DBs (no boundaries) project identically to today — the boundary lookup is empty and the window is the tail. | Yes, after T1 | `move_leaf` transaction is one commit; dual-projection comparison mode (build both projections, diff, log, serve old) ships dark behind a config flag and is deleted at T3 |
| **T3 — rotation writer** | trigger evaluation at end_turn/idle-tick, watermark, atomic rotate TXN, anti-thrash counters, flush. **Default off**; enable requires the R5 compaction-eval scorecard (Hermes §9 blueprint: question-bank invariance + ceiling arm). | Yes, after T2, flagged | The rotation TXN (§3.1) is the atomic unit; flag flip is a config change, not a migration |
| **T4 — leaves & persona scope** | per-persona leaves (if Q3 answers yes), guest-scope edge gate, UI divider affordance (if Q4 answers yes) | Yes, after T2 | index swap on `idx_one_open_leaf` |

**Test strategy for a tree migration on a live store** (all patterns already exist in-repo or in packet 08):
- *Old-shape open*: T1's reconciliation test extends packet 08's A3 shape — a Plan-A-era DB (schema_version 4, no tree columns) opens, reconciles, inserts turn rows, and `current_open_thread()` returns the same answer before and after.
- *Golden projections*: fixed fixture DB → exact projection array, byte-stable (OpenClaw golden-trace pattern, review §11), run pre-T1 and per-packet.
- *Dual-run shadow*: T2's dark mode logs projection diffs on every turn of the founder's own dogfood DB; zero diffs for N days is the merge gate (attunement program's "Halbert is the primary consumer" posture — the founder's machine is the test corpus).
- *Crash-injection*: kill between rotate-TXN steps (test-only commit hook), assert no half-rotated state after reopen; kill between branch-summary insert and leaf move, assert idempotent retry (entry keyed in metadata, §2.3).
- *Order-sensitivity*: per the worktree-venv memory note, run the suite twice forward and once shuffled; DB-file tests use `wt_pytest.py` in worktrees.
- *No downgrade games*: schema_version ladder stays, and per OpenClaw §2's rule a future-version file hard-refuses — the founder's "no legacy support" posture means never write a down-migration.

## 7. Open questions (founder) and F-3 agenda changes

**Founder questions:**
1. **Marker vs segment rotation** — ratify §1.3 (thread row permanent, boundary ledger) over Hermes's forked-session shape. The cost if reversed: message re-parenting breaks redaction identity and guest thread memory; the benefit if reversed: Hermes queries port verbatim. Recommendation: markers; **this is the one decision T3's writer depends on.**
2. **Compaction LLM gating** — ok to ship T3 dark with no summarizer until the R5 compaction eval exists (scorecard-first), or is a deterministic-only compaction (receipt-concatenation as summary, no model) acceptable as v0? The tiered-sensitivity rule suggests deterministic v0 is actually preferabale; Hermes/OpenClaw both went LLM. Founder call.
3. **One leaf or per-persona leaves** — can a guest session's open thread and the owner's open thread coexist? Recommendation: per-persona leaves (two rows, index gains scope); the global-leaf alternative makes guest/owner interleaving mute each other's topic state.
4. **UI affordance at topic switch** — strictly nothing, or a subtle divider entry in the timeline (the branch-summary entry rows already exist as data; rendering them is a frontend toggle)? The founder directive bans the conversation *list*, not necessarily the divider. Recommendation: render divider, no list.
5. **Title CAS ladder** — accepting `provisional < refined < user` implies a user title-edit path someday; is that in scope now (small) or recorded (free)?

**F-3 agenda items this design changes:**
1. **Injection order is decided here, ratify there**: transcript projection entries ride the message array (positional), curated core rides `messages[0]` with identity/receipt block. F-3 needs only the budget split (receipt block + curated core share the `messages[0]` cap at :889 — the count-then-clip path needs a two-tenant budget) and the **double-injection guard**: a paused thread's receipt (path) and its promoted facts (core) can say the same thing twice — rule: curated entries sourced from a thread currently on the projection path are elided from the core block for that turn (deterministic keying on claim keys, per the second-guess doc's claim-keyed alignment).
2. **Frozen-snapshot vs per-turn core** (already on F-3 via Hermes inputs) now has a second voter: the projection is *positionally* stable (entries are rows) but the receipt block mutates on every leaf move, busting prefix cache at `messages[0]` either way — which weakens the frozen-snapshot argument and strengthens per-turn rendering. Bring this data point.
3. **Thread-close as signal source** (§5.2) lands in packet 01's A2 wiring list — F-3 should confirm the four signal sites as one set so the promotion store's schema ships once.
4. **`compact_boundaries` is now spoken for** — packet 08's out-of-scope guard ("do NOT touch the no-writers status") transfers to this program; F-3 should note packet 08 and T1 merge order (08 first, T1 rebases onto reconciliation).

*Design complete; no code changed. Next gate: founder review of §7 Q1–Q5, then F-3.*
