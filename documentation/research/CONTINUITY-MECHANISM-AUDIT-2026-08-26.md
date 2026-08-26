# Continuity Mechanisms — Empirical Audit and Verdict

**Date:** 2026-08-26
**Status:** Audit complete. Findings verified by execution, not by reading.
**Companions:** `CROSS-SESSION-CONTINUITY-RESEARCH-2026-08-26.md` (landscape),
`CONTINUITY-DESIGN-STRATEGIES-2026-08-26.md` (design strategy — §4.3 and §7.3 of that
document are **superseded** by Finding F4 below).

Answers three questions: do the memory mechanisms we have actually work; are we structurally
on par with the systems we researched; and will the planned mechanisms deliver continuity.

---

## 0. The headline

**Halbert already depends on a memory system more sophisticated than most of the frameworks
in the research doc, and wires 4 of its 58 capabilities.**

`haloysius.memory_v2` is installed (v0.2.0), functional, and ships a temporal state ledger
with automatic supersession, a consolidator, an importance scorer, a reflector, a hierarchy
index, a persona graph, a context builder with bounded reconstruction, rolling summaries and
a unified retriever. Halbert imports `PersonaMemory`, `PersonaMemoryStore`, `MemoryType`, and
a `TemporalStateLedger` reference that is never connected.

So the answer to "are we building this as sophisticated as the apps we're researching" is
not *no*. It is: **the sophistication is already installed, already working, and unused.**
The gap is wiring, not capability. That is very good news for the size of the job.

Three real defects found, all in code paths that are live or about to be:

| | Defect | Severity |
|---|---|---|
| **F1** | `MemoryWriter` → `MemoryRetrieval` is a total write/read mismatch. Everything written is unreadable forever. | dead subsystem, live wiring |
| **F2** | `sync_to_ledger()` calls `ledger.set_state()`, which does not exist on `TemporalStateLedger`. It is also never given a ledger. | double-dead |
| **F3** | Plan A does not convert the three LLM call sites to real `messages[]`. History stays prose in one user message. | quality ceiling |

---

## 1. Method

Every result below came from running the code in `.venv` (Python 3.10.9) against temp
directories. Nothing was written to live user data. Probe scripts are in the session
scratchpad. Dependency check: `chromadb 1.5.9`, `haloysius 0.2.0`, `numpy 2.2.6`,
`sentence_transformers 6.0.0`, `networkx 3.4.2`, `rank_bm25` — all present. No embed build
was running.

Existing tests first: `test_context_watermark.py`, `test_conversation_sqlite.py`,
`test_memory_adapter.py`, `test_somatic_block.py`, `test_somatic_lifecycle.py` →
**74 passed in 0.24s**.

Test coverage of the three largest memory modules:

- `memory/hybrid.py` (28 KB) — 1 test file, covering only the self-knowledge adapter surface
- `memory/retrieval.py` — **0 test files**
- `memory/writer.py` — **0 test files**

F1 lives exactly where the tests are not.

---

## 2. Question 1 — Do they work?

| Mechanism | Verdict | Evidence |
|---|---|---|
| `SqliteConversationStore` | **Works fully** | save/get 3 msgs; `get_context_window(4000)` → 3 msgs in order; FTS5 `search("nginx")` → 1 hit |
| `ContextWatermark` | **Works fully** | 85%+3h → compact; 50% → no; topic change detected; `micro_compact` truncated 900→224 chars |
| `compress_conversation_history` | **Works** | returns a 2-tuple `(messages, summary)`; `should_summarize` → True at 30 turns |
| `HybridMemorySystem` | **Works** | `store()` → uuid; `recall("samba media share")` → 5 hits, correct doc first; `consolidate` / `get_contradictions` run clean |
| Haloysius `PersonaMemoryStore` | **Works, and is good** | `smart_add` → ADD; identical re-add → **`MemoryOperation.NOOP`** (semantic dedup at write); `search` returned the right memory first for all three probes; `decay_unused`, `get_stats`, `get_by_type`, `get_recent` all functional |
| Haloysius `TemporalStateLedger` | **Works, and is exactly what we need** | see §3, F4 |
| `MemoryWriter` → `MemoryRetrieval` | **BROKEN** | see F1 |
| `state_trackers.sync_to_ledger()` | **BROKEN** | see F2 |

Six of eight mechanisms work. Two are broken. Neither broken one has a test.

### F1 — The file memory writes into a void

`MemoryWriter._append_jsonl()` writes whatever dict it is handed, adding only `ts`. It
imposes no schema. `MemoryRetrieval.retrieve_from()` scores relevance on
`entry.get('text','') + ' ' + entry.get('summary','')` (`retrieval.py:104`). An entry with
neither key scores `0.0`, and the guard is `if score > 0`. It is therefore **never
returned**.

The only real writer is `scheduler/executor.py:_log_outcome()`, whose payload is
`{job_id, success, output, error, confidence, execution_time_s, retry_count, ts}` —
no `text`, no `summary`. Measured with that exact payload:

```
retrieve_from('runtime', 'nginx')           -> 0 hits
retrieve_from('runtime', 'nginx restarted') -> 0 hits
retrieve_from('runtime', 'j1')              -> 0 hits
```

Same content under a `text` key → **1 hit**. The reader is fine; the contract is not.

`write_action_outcome()` returns `True`. The file grows. `build_context()` returns 2
characters. Nine typed `write_*` methods, none of which document or enforce the two keys
that make an entry retrievable.

**Mitigating fact:** `~/.local/share/halbert/memory` holds **0 entries**. The subsystem has
never been used in production, so nothing is lost. It is dead code with live wiring in
`main.py:496,522,541,1735,1738`, `scheduler/executor.py:550`, and the dashboard's
`/api/memory/stats` and `/api/memory/search` endpoints — all of which would return empty
results indefinitely the moment anything did use it.

The scoring itself is fine, incidentally — case-insensitive with sane token overlap.
`'Samba'`, `'samba'`, `'samba media'`, `'media share'`, `'guest'` all hit correctly when the
key is right. The tokenizer is not the problem. The contract is.

### F2 — The state ledger is wired to a method that does not exist

`state_trackers.py` gives all four trackers (disk, service, resources, admin presence) a
`sync_to_ledger()` that calls:

```python
self._ledger.set_state(subject=..., predicate=..., object=...)
```

`TemporalStateLedger` has no `set_state`. Verified: `hasattr(led,'set_state') → False`. Its
actual surface is `record / get_current / get_current_by_priority / get_history / invalidate
/ clear_persona / close`.

It never gets that far. `register_halbert_state_trackers(ledger=None)` is called with **no
argument** at both call sites (`cognition_wiring.py:186` and `:217`), so `self._ledger is
None` and every `sync_to_ledger()` returns immediately. Were a ledger ever passed, the call
would raise `AttributeError` into the `except Exception` that logs a warning and continues.

This is the single most consequential dead seam in the codebase, because of F4.

### F3 — Plan A keeps history as prose

All three LLM call sites still send one user message:

```
state_machine.py:669   messages=[{"role": "user", "content": prompt}]
state_machine.py:1280  messages=[{"role": "user", "content": prompt}]
state_machine.py:1294  messages=[{"role": "user", "content": prompt}]
```

The foundational research's E-3 calls for "build real `messages[]` at three call sites."
Plan A does not do it — spec §7 routes history through
`build_response_prompt(query, context, observations, history, continuity)`, i.e. flattened
into the tail of that single user message. Searching all 27 Plan A tasks for `messages=[`
returns only A10's `num_ctx` test, still single-message.

This is not fatal — prose history works, and V-05 ("check nginx" → "it's stopped" → "start
it") will pass. What it costs:

- **Role attribution.** Models are trained on structured turns. Prior assistant text
  arriving as prose inside a user message is more likely to be read as user instruction.
- **Tool-call history cannot be represented.** `agents/blocks.py` has `ToolResultBlock`, and
  `states.py:246-267` already appends block-typed content to `conversation_history`. That
  structure is built and then flattened away at the call site.
- **`ContextWatermark.micro_compact()` becomes inert where it matters.** It truncates
  `tool_result` blocks in block-typed history — which no longer exists by the time the
  prompt is built.

Degradation is proportional to thread length and tool density. Short threads: no visible
difference. Long, tool-heavy sysadmin threads — the target use case: visible.

---

## 3. Question 2 — Are we structurally on par?

**F4 — the finding that reframes everything.** `haloysius.memory_v2` exposes 58 public
capabilities. Halbert references four.

Tested live, all instantiate and run: `get_state_ledger`, `get_consolidator`,
`get_importance_scorer`, `get_reflector`, `get_hierarchy_index`, `get_persona_graph`,
`get_memory_system`, `search_memories`, `build_context_for_chat`.

The temporal state ledger does precisely what `CONTINUITY-DESIGN-STRATEGIES` §4.3 recommended
building from scratch:

```
record(P,"sshd","port","22","thread-jul")
record(P,"sshd","port","2222","thread-aug")

get_current(P)                    -> 1 triple:  object='2222', valid_to=None
get_history(P,"sshd","port")      -> 2 triples: '22'  valid_from=... valid_to=2026-08-26T21:55:30
                                                '2222' valid_from=... valid_to=None
invalidate(P,"sshd","port")       -> 1;  get_current now 0
```

Recording the new value **automatically closed the old one's valid-time interval**. That is
ECHO's *"similarity proposes; the ledger resolves"* — supersession, bitemporal valid time,
per-triple `source` provenance, priority ranking, and a full audit trail — working, in a
dependency Halbert already ships, behind a function call.

### Parity matrix

Legend: ● present and working · ◐ partial · ○ absent · **★ available to Halbert, unwired**

| Capability | Letta | Mem0 | Zep | ECHO | StatePlane | Nūr | Claude Code | **Halbert wired today** | **After Plan A** | **Installed, unwired** |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| Multi-turn history to the model | ● | ● | ● | ● | ● | ● | ● | ○ | ◐ prose (F3) | — |
| Cross-session recall | ● | ● | ● | ● | ● | ● | ◐ | ○ | ● receipts+FTS5 | ★ `search_memories` |
| Deterministic read path | ○ | ○ | ● | ● | ◐ | ● | ○ | ○ | ● | ★ |
| Semantic dedup at write | ◐ | ○ ADD-only | ● | ● | ● | ● | ○ | ○ | ○ | **★ `smart_add`→NOOP** |
| Supersession / bitemporal | ○ | ○ | ● | ● | ◐ | ◐ | ○ | ○ | ○ | **★ `TemporalStateLedger`** |
| Provenance on artifacts | ◐ | ○ | ● | ● | ● | ◐ | ○ | ○ | ◐ receipts | ★ triple `source` |
| Importance / salience | ● | ◐ | ◐ | ◐ | ● | ● | ○ | ○ | ○ | ★ `ImportanceScorer` |
| Decay / forgetting | ● | ○ | ◐ | ● | ● | ● | ○ | ○ | ○ | ★ `decay_unused` |
| Consolidation / dreaming | ● | ○ | ○ | ◐ | ● | ● | ○ | ○ | ○ | ★ `Consolidator` |
| Reflection / self-improve | ● | ○ | ○ | ○ | ◐ | ● | ○ | ◐ REFLECTING | ◐ | ★ `Reflector` |
| Bounded reconstruction | ● | ○ | ◐ | ● | ● | ◐ | ● | ○ | ● `num_ctx` | ★ `ContextBuilder` |
| Hierarchical tiers | ● | ◐ | ◐ | ● | ● | ● | ◐ | ○ | ○ | ★ `HierarchyIndex` |
| Knowledge graph | ○ | ◐ | ● | ◐ | ◐ | ○ | ○ | ◐ hybrid, fenced | ○ | ★ `PersonaGraph` |
| Identity continuity | ● | ○ | ○ | ○ | ◐ | ● | ○ | ● Haloysius | ● | — |
| Relational continuity (open loops) | ○ | ○ | ○ | ○ | ○ | ● | ○ | ○ | ◐ prose only | ○ |
| Topic / domain scoping | ◐ | ◐ | ● | ● | ● | ● | ○ | ○ | ● threads | ★ typed retrieval |
| Compaction trigger | ● | ○ | ○ | ○ | ● | ○ | ● | ○ built, orphaned | ◐ | — |
| Audit trail | ● MemFS | ○ | ● | ● | ◐ | ● | ◐ | ○ | ◐ | ★ `get_history` |

**Read the last two columns together.** Halbert-wired-today is the weakest column in the
table. Halbert-after-Plan-A is mid-field — comparable to Mem0, behind Zep and ECHO.
Halbert-with-Haloysius-wired would be the **strongest column in the table**, matching or
beating every system surveyed on 15 of 18 rows, with only relational continuity (open loops)
genuinely absent everywhere but Nūr.

That is the honest answer to the question. Not "are we sophisticated enough" but "we
already bought the sophistication and never plugged it in."

**One caveat.** A probe run emitted `numpy not installed. Vector search disabled.` even
though numpy 2.2.6 is present — so some Haloysius code path is degrading to keyword-only
retrieval. Search still returned correct top-1 results in every probe, but semantic quality
is unconfirmed. Worth 20 minutes before relying on the semantic tier.

---

## 4. Question 3 — Will the planned mechanisms deliver continuity?

Walking the end-to-end flow Plan A will produce:

**What will work.** Second message sees the first. Thread resolution, domain tagging,
receipts, FTS5 recall, the "Samba six weeks ago" flow, `num_ctx` budgeting, the recall chip.
V-05 passes. **This is real continuity and it is the bulk of the value.** Plan A is a good
plan and it should ship as written apart from the notes in §6.

**Where it falls short of the goal, in order of impact.**

1. **Nothing is ever pushed (G1).** Recall is match-triggered. A thread closing with *"Open
   loop: monitor disk for 24h"* surfaces at hour 24 only if the admin mentions disks. The
   line is extracted into a text blob, so nothing can query what is outstanding. This is the
   one capability that is genuinely *cross-session* rather than recall-on-demand, and it is
   the row where every surveyed system except Nūr also scores zero.
2. **Stale state recalled as current.** A2's own fixture stores
   `Last said: The share mounts from the laptop at //nas/media (v3.1 client)` — a
   present-tense claim about mutable state, retrieved six weeks later as
   `retrieved_context[0]`. Unfixed, every receipt written is a future confident-and-wrong
   answer. Full analysis in `CONTINUITY-DESIGN-STRATEGIES` §4.2.
3. **No supersession (G4).** Two receipts both match `sshd`; nothing marks the older
   superseded. **F4 means this is now a wiring job, not a build.**
4. **Structure loss at the call site (F3).** Quality ceiling on long tool-heavy threads.
5. **Precision decays with N, untested (G3).** Every Plan A test runs at one or two threads.
6. **Write-only identity memory.** Plan A writes a Haloysius episodic line per closed thread
   while deferring `memory_v2.search`. **F4 kills the justification:** `search()` works
   today, tested, and returned the right memory first on all three probes.

Verdict: **the planned mechanisms will deliver continuity of content but not continuity of
truth.** Halbert will remember what was said and be unable to tell what is still so.
Items 2 and 3 are the difference, and both are now cheap.

---

## 5. Keep / Fix / Toss

### Keep as-is
- `SqliteConversationStore` — works fully; Plan A is right to make it the store of record.
- `ContextWatermark` — works fully; needs a consumer, not changes.
- `compress_conversation_history` — works; fix the caller that stringifies it.
- Plan A's receipt design — 8 of 9 fields are correct by the re-observability test.
- Haloysius `PersonaMemoryStore` — works, dedups semantically, better write policy than Mem0.

### Fix
- **F1** — one line in `retrieval.py` to fall back across common content keys, or a documented
  schema on `_append_jsonl`. Ten minutes. *(Only if the subsystem is kept — see Toss.)*
- **F2** — `set_state` → `record(persona_id, subject, predicate, object, source)`, and pass a
  real ledger at `cognition_wiring.py:186,217`. **This is the highest-leverage fix in the
  codebase**: it turns four dead tracker methods into a live, auditable, self-superseding
  record of machine state, and it is the mechanism the design strategy called for.
- **F3** — build real `messages[]` at the three call sites. Not required for Plan A to ship;
  required before long tool-heavy threads are the norm.
- The `numpy not installed` warning — confirm the semantic tier is actually semantic.

### Toss
- **`memory/retrieval.py` + `memory/writer.py`.** Zero live data, zero tests, broken
  contract, and no remaining job: Plan A owns conversation memory, Haloysius owns identity
  and semantic memory. Retiring them removes two of the eight stores and the misleading
  `/api/memory/{stats,search}` endpoints. Prefer this over fixing F1.
- **`HybridMemorySystem` on the agent path** — already the spec's decision; make it final.
  It works, but it duplicates Haloysius `memory_v2` less well and pulls in ChromaDB, which
  `the-being.md` §9 keeps eval-only. Keep the module for the eval/browser path; do not build
  the continuity layer on it.
- **The §4.3 `superseded_by` column** — superseded by F4. Use the ledger.

### Build (genuinely new)
Only two things in this entire audit are not already built somewhere:
- **`open_loops` table + row-write** — the commitment ledger (G1). Nūr is the only surveyed
  system that has this.
- **Cumulative evaluation harness** — recall precision at N=10/100/500 (G3), per ATANT's
  cumulative-mode methodology.

---

## 6. The work list

**Do now — Plan A is executing, A1 in flight, A2 next.** Schema and content decisions that
cost minutes inside tasks being written this week.

| | Item | Size |
|---|---|---|
| N1 | Date-stamp `Last said (YYYY-MM-DD):` in `build_receipt` | one string |
| N2 | Write an `open_loops` row when A2 extracts the `Open loop:` line | one insert |
| N3 | ~~`superseded_by` column~~ → **instead**: have thread close call `ledger.record(...)` for each `(subject, predicate, object)` the thread established, `source=thread_id` | small, replaces a column with a call |

**Fix next — small, high leverage, not blocking Plan A.**

| | Item | Size |
|---|---|---|
| W1 | F2: `set_state` → `record`, pass a real ledger at both call sites | ~20 lines |
| W2 | Retire `memory/writer.py` + `memory/retrieval.py` and their endpoints | deletion |
| W3 | Wire `PersonaMemoryStore.search()` as the semantic recall tier — the spec's "deferred" item, unblocked by F4 | small |
| W4 | Confirm the numpy/vector-search warning | 20 min |

**After Plan A + Plan B.**

| | Item | Size |
|---|---|---|
| W5 | F3: real `messages[]` at the three call sites | medium |
| W6 | Cumulative eval harness (N=10/100/500) | medium |
| W7 | Scope argument on recall + `scope_crossed` telemetry | small |
| W8 | Consolidation at idle — wire `get_consolidator()` + `ImportanceScorer` + `decay_unused` into the scheduler | medium |
| W9 | Abstain-and-probe policy in the responder | medium |

**The honest sizing: there is not much to build.** Two genuinely new pieces (`open_loops`,
the eval harness). Everything else is wiring something that already works, deleting something
that never did, or a one-string change. The prerequisite ordering from
`CONTINUITY-DESIGN-STRATEGIES` §7 still holds — Plan A A1–A13, then Plan B §9.2 for receipt
provenance quality — but the layer on top of it is much smaller than the foundational
research implies, because F4 means most of it is already sitting in `site-packages`.

---

## 7. Corrections to the companion document

- **§4.3** recommended building supersession as a `superseded_by` column. Superseded by F4:
  `TemporalStateLedger` already provides supersession, bitemporal valid time, provenance and
  an audit trail. Wire it.
- **§7.3 N3** changes from "add a nullable column" to "call `ledger.record()` at thread close."
- **§4.6** ("no write path without a read path") is strengthened: the read path for the
  Haloysius line is not deferred work, it is `PersonaMemoryStore.search()`, which works today.
- **§2's store inventory** gains a correction: stores 4 (`MemoryWriter`/`MemoryRetrieval`) is
  not merely underused, it is non-functional and holds no data. Retiring it takes the count
  from eight to seven at zero cost.

---

*End of document.*
