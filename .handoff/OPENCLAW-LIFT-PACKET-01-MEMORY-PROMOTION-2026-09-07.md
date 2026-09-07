# OPENCLAW-LIFT-PACKET-01 — Recall-driven promotion store + curated core for Halbert-owned memory

**Series:** OpenClaw lift program (master plan: `OPENCLAW-LIFT-MASTER-PLAN-2026-09-07.md`)
**Source research:** `.handoff/OSS-REVIEW-OPENCLAW-2026-09-07.md` §1 (Memory / continuity)
**OpenClaw source of record:** `/Volumes/Thunderbolt/AI/openclaw` — `extensions/memory-core/src/short-term-promotion{,-record}.ts`, `memory-budget.ts`, `extensions/active-memory/trigger-recall.ts`, `extensions/memory-lancedb/auto-recall.ts`
**Executor tier:** Phase A pure + thin wiring — small-model friendly. Phase B touches the R9 memory fence — review required before dispatch. Phase C is a recorded decision, not work.
**Status:** PHASE A READY TO DISPATCH; PHASE B GATED ON REVIEW

---

## Objective

OpenClaw's memory blueprint's single most transferable idea: **memory earns durability by being *useful*, not by being written confidently.** Every recall records signals; a deterministic ranker decides what graduates into the small always-present curated core. This packet builds that loop for the memory Halbert actually owns:

1. A **promotion signal store**: record what recall actually surfaced (thread auto-recalls, `recall_memory` tool calls) with recall count, query diversity, and recency.
2. A **curated core**: a small, budget-capped, always-injected block of promoted facts — the only new injection path into the agent prompt, built deterministic and Halbert-owned.
3. **Recall-loop hygiene**: recalled content can never re-enter as promotion input ("a fact recalled a hundred times stays one fact").

## Verified current state (do not re-derive; verified 2026-09-07)

**Read this carefully — the memory landscape is split and the split is deliberate:**

- **memory_v2 is NOT in this repo.** It is the external Haloysius package (`/Volumes/4TB-BAD/Haloysius/src/haloysius/memory_v2/`), editable-installed into `.venv`. Its store is JSON + MiniLM embeddings, not SQLite. Its search results feed only Haloysius's thought promotion inside `advance_turn` — **they never enter a Halbert prompt.** Any memory_v2 change is a cross-repo change to Haloysius and is OUT OF SCOPE for this packet.
- **Halbert's thread/conversation memory (wired):** `agents/threads.py` `ThreadManager` over `agents/conversation_sqlite.py` `SqliteConversationStore` (schema_version table, currently 4, additive-column migrations `_ADDITIVE_COLUMNS`, FTS5 with LIKE fallback). Strong-match **auto-recall of a closed thread fires in `begin_turn`** (threads.py:353-359), gated by `thread_signals.decide` → `recall_gate.classify`. Recalled receipts render via `ctx.thread_receipt_block` (state_machine.py:1784-1785) riding `messages[0]`.
- **Halbert's state ledger (wired):** `continuity/state_store.py` `StateStore` (supersession rows, `valid_to`, partial unique index for one open row per (subject,predicate)); `continuity/recall.py` `recall_state` — one read shared by the HTTP route and the **`recall_memory` tool** (`tools/recall_memory.py`, registered in `tools/executor.py:262-264`, prompted for at agent_prompts.py:785). `continuity/recall_gate.py` `classify`/`MatchStrength`/`GateResult` decides silent-inject trustworthiness.
- **Halbert's Consolidator (wired, non-LLM):** `continuity/consolidation.py` `Consolidator.consolidate()` — batches closed threads by domain (≥3 in 7 days), records recurring entities into `StateStore` as durable facts. Runs at the end of every idle `ThreadManager.tick()` (threads.py:655-661). **The LLM pass is deliberately gated off** pending the R5 eval harness.
- **The R9 fence:** `context/adapters.py` `create_agent_context_assembler()` (line 472) sets `memory_service=None` with the comment "the agent path must not reach ChromaDB-backed HybridMemorySystem"; `routes/agent.py:164-166` re-states it. The assembler's `_retrieve_memory` block (assembler.py:780-831, "## Remembered Information") is dead on the agent path. **Phase B deliberately touches this fence — with a new curated source, not the fenced ChromaDB hybrid.**
- `continuity/freshness.py` `decide` — built, no production caller (deliberately kept out of recall). `Compact_boundaries` table ships with no writers.
- `memory_writer` references in `scheduler/autonomous_tasks.py` are never satisfied (MemoryWriter was removed 2026-08-26, audit F1) — dead params, not a wiring target.

**What the "curated core" maps onto:** nothing exists yet — there is no always-in-context memory block on the agent path. That absence is exactly what this packet fills.

## Out-of-scope guards

- **No changes to the Haloysius repo.** If a task seems to require memory_v2 internals, STOP and record it in the master plan as a cross-repo item.
- **No LLM anywhere.** The Consolidator's LLM gate stays off. OpenClaw's plan-based LLM consolidation is recorded as a Phase C decision for when the R5 eval harness un-gates it.
- **Do not un-fence the ChromaDB hybrid** (`create_wired_context_assembler` stays without production callers). The curated core is a *new, deterministic* source — never `HybridMemorySystem`.
- **Do not turn recall into a chat UI.** Curated core renders as one bounded context block, same style as the existing thread receipt block. No memory items in the conversation stream.

---

## Phase A — promotion signal store (pure + thin wiring)

**Branch:** `feat/memory-promotion` off `main`.

### Task A1: The signal store

**Files:**
- Create: `halbert_core/halbert_core/continuity/promotion.py`
- Test: `halbert_core/tests/continuity/test_promotion.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Recall-driven promotion, lifted from OpenClaw short-term-promotion-record.ts +
short-term-promotion.ts: memory graduates because it kept being USEFUL (recalled),
not because it was written confidently. Pure and deterministic."""
import time
import pytest

from halbert_core.halbert_core.continuity.promotion import (
    PromotionSignals, PromotionStore, rank_candidates, PromotionCandidate,
)

def _recalled(query="how is the scanner set up", days=0, score=0.8):
    return {"event": "recall", "query": query, "days_ago": days, "score": score}

def test_counts_and_query_diversity():
    store = PromotionStore()
    key = ("subject:scanner", "predicate:config")
    store.record_recall(key, query="how is the scanner set up")
    store.record_recall(key, query="how is the scanner set up")  # same query: count rises, diversity doesn't
    store.record_recall(key, query="scanner keeps dropping off wifi")
    sig = store.signals(key)
    assert sig.recall_count == 3
    assert sig.query_diversity == 2
    assert sig.recall_days == 1  # all same day

def test_multi_day_recurrence_counts():
    store = PromotionStore()
    key = ("subject:printer", "predicate:state")
    store.record_recall(key, query="printer status", days_ago=3)
    store.record_recall(key, query="printer offline again", days_ago=1)
    assert store.signals(key).recall_days == 2

def test_recalled_content_cannot_reenter():
    # the recall-loop rule: entries derived from recalled content never produce signals
    store = PromotionStore()
    key = ("subject:door", "predicate:code")
    store.record_recall(key, query="door code", provenance="recalled_content")
    assert store.signals(key) is None

def test_ranking_uses_utility_not_confidence():
    often_used_low_score = PromotionCandidate(
        key=("subject:a", "predicate:p"), signals=PromotionSignals(recall_count=7, query_diversity=4, recall_days=3, avg_score=0.5))
    written_once_high_score = PromotionCandidate(
        key=("subject:b", "predicate:p"), signals=PromotionSignals(recall_count=1, query_diversity=1, recall_days=1, avg_score=0.95))
    ranked = rank_candidates([often_used_low_score, written_once_high_score], limit=1)
    assert ranked[0].key == ("subject:a", "predicate:p")

def test_gates_block_noise():
    one_hit = PromotionCandidate(
        key=("subject:c", "predicate:p"), signals=PromotionSignals(recall_count=1, query_diversity=1, recall_days=1, avg_score=0.9))
    assert rank_candidates([one_hit], limit=5) == []  # min recall count not met

def test_decay_is_a_ranking_multiplier_never_a_delete():
    store = PromotionStore()
    key = ("subject:old", "predicate:p")
    store.record_recall(key, query="old thing", days_ago=45)
    ranked = rank_candidates([PromotionCandidate(key=key, signals=store.signals(key))], limit=5)
    # still present, ranked lower than a fresh equal signal would be
    assert ranked and ranked[0].key == key
```

- [ ] **Step 2: Run, verify failure.** `cd halbert_core && arch -arm64 ../.venv/bin/python -m pytest tests/continuity/test_promotion.py -q`

- [ ] **Step 3: Implement `promotion.py`**

```python
"""Recall-driven promotion store (OpenClaw short-term-promotion pattern).

Design rules lifted from the review:
- promotion signals are USAGE facts (recall count, distinct queries, distinct days,
  average gate score) — never write-time confidence;
- decay multiplies ranking and never deletes;
- content derived from recalled material never re-enters (provenance guard) —
  "a fact recalled one hundred times stays one fact";
- hard gates (min recall count, min diversity) keep one-off trivia out.
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field
from datetime import date

HALF_LIFE_DAYS = 30.0
MIN_RECALL_COUNT = 3
_MIN_QUERY_DIVERSITY = 2

@dataclass
class PromotionSignals:
    recall_count: int = 0
    query_diversity: int = 0
    recall_days: int = 0
    avg_score: float = 0.0
    last_recalled_days_ago: float = 0.0

@dataclass(frozen=True)
class PromotionCandidate:
    key: tuple[str, str]
    signals: PromotionSignals

def _signal_score(s: PromotionSignals) -> float:
    utility = math.log1p(s.recall_count)
    diversity = s.query_diversity / 5.0
    spread = s.recall_days / 5.0
    recency = math.exp(-math.log(2) / HALF_LIFE_DAYS * s.last_recalled_days_ago)
    return 0.5 * utility + 0.2 * diversity + 0.2 * spread + 0.1 * recency

def rank_candidates(candidates, limit: int) -> list:
    eligible = [
        c for c in candidates
        if c.signals.recall_count >= MIN_RECALL_COUNT
        and c.signals.query_diversity >= _MIN_QUERY_DIVERSITY
    ]
    ranked = sorted(eligible, key=lambda c: _signal_score(c.signals), reverse=True)
    return ranked[:limit]

class PromotionStore:
    """In-process signal accumulator; snapshots persist to the continuity DB (A2).
    Queries are stored as sha256 so chatty loops can't inflate diversity with
    trivially different strings, and raw user text never lands in the store."""
    def __init__(self):
        self._signals: dict[tuple[str, str], PromotionSignals] = {}
        self._queries: dict[tuple[str, str], set[str]] = {}
        self._days: dict[tuple[str, str], set[date]] = {}
        self._scores: dict[tuple[str, str], list[float]] = {}

    def record_recall(self, key, query: str, *, days_ago: float = 0.0, score: float = 0.0,
                      provenance: str = "agent_query") -> None:
        if provenance == "recalled_content":
            return  # recall-loop hygiene: never re-enter
        sig = self._signals.setdefault(key, PromotionSignals())
        sig.recall_count += 1
        import hashlib
        self._queries.setdefault(key, set()).add(hashlib.sha256(query.encode()).hexdigest()[:16])
        self._days.setdefault(key, set()).add(date.today())
        self._scores.setdefault(key, []).append(score)
        sig.query_diversity = len(self._queries[key])
        sig.recall_days = len(self._days[key])
        sig.avg_score = sum(self._scores[key]) / len(self._scores[key])
        sig.last_recalled_days_ago = days_ago

    def signals(self, key) -> PromotionSignals | None:
        return self._signals.get(key)
```

- [ ] **Step 4: Run, verify pass. Commit:**

```bash
git add halbert_core/halbert_core/continuity/promotion.py halbert_core/tests/continuity/test_promotion.py
git commit -m "feat(continuity): recall-driven promotion signal store with decay-as-ranking and loop hygiene"
```

### Task A2: Persist signals; wire the two live recall sites

**Files:**
- Modify: `halbert_core/halbert_core/continuity/promotion.py` — add SQLite persistence (new table `promotion_signals` in the continuity state DB via the same additive pattern used by `StateStore`: see `state_store.py` `_ADDITIVE_COLUMNS` — a brand-new table with `CREATE TABLE IF NOT EXISTS` is fine; only *column adds to existing tables* must follow the additive pattern).
- Modify: `agents/threads.py` — in `begin_turn`'s strong-match auto-recall path (~353-359), after `recall_gate.classify` admits a receipt, record a signal per recalled receipt's key entities with the gate score.
- Modify: `halbert_core/halbert_core/tools/recall_memory.py` — after `recall_state` returns results, record a signal per returned subject with `query=<user's tool args query>` and the tool's own match strength.
- Test: `halbert_core/tests/continuity/test_promotion_wiring.py` — a recalled thread produces persisted signals; a `recall_memory` call produces persisted signals; same-day repeat of the same query does not inflate diversity.

- [ ] **Step 1:** Write the wiring tests first (against a temp DB / monkeypatched store). **Step 2:** Implement the three wiring points — each is a few lines; keep them fail-soft (signal recording must never raise into the turn path — wrap in `try/except` with a debug log, per the "memory failures never eat a turn" rule). **Step 3:** Run the continuity + threads + tools suites. **Step 4:** Commit: `feat(continuity): record recall signals at the thread auto-recall and recall_memory sites`

---

## Phase B — the curated core (GATED: touches the R9 fence — needs review + founder sign-off on injection)

**Scope decision recorded in the master plan.** The design: a small (default 2,000-char) always-injected `## What I remember` block assembled from top-ranked promoted facts, rendered by the ContextAssembler as a *new* deterministic source named `curated` — NOT by re-enabling `memory_service`. Budget-capped with marker-delimited, oldest-first eviction (OpenClaw `memory-budget.ts` pattern): every machine-written entry carries a provenance marker; only machine-written sections evict; human edits (if the vault projection ever feeds this) are sacrosanct.

**Files (planned):**
- Create: `halbert_core/halbert_core/continuity/curated.py` — `build_curated_core(store, budget_chars)`, `render_curated_block(core)`, marker-delimited eviction.
- Modify: `halbert_core/halbert_core/context/assembler.py` — new `curated` source tier in `assemble()` reading from `build_curated_core` (deterministic; no service object; fails to empty block).
- Modify: `halbert_core/halbert_core/context/adapters.py` — thread the curated provider through `create_agent_context_assembler()` with the fence comment updated to state the new rule: *"the agent path must not reach ChromaDB-backed HybridMemorySystem; the curated core is the only sanctioned memory injection and is deterministic."*
- Tests: `halbert_core/tests/continuity/test_curated.py` (pure: budget fit, marker eviction, empty-store → empty block) + an assembler-level test asserting the block renders and that `memory_service` remains None.

**Do not start until the review checkpoint passes.** The R9 fence is a ratified decision with comments in two files; Phase B edits both comment sites and must update the record (DECISIONS.md entry) in the same commit, per house rules.

---

## Phase C — recorded decisions, not work (carry to the deep pass)

1. **Recall-intent escalation lane** — Halbert already has a deterministic lane-1 analogue (thread auto-recall + `recall_memory`). OpenClaw's lane-2 (a real retrieval subagent on recall-intent phrasing) is a design decision about spending agent turns on memory; belongs with the prompted-heartbeat decision (PACKET-03 Phase C), not here.
2. **Plan-based consolidation** — applies only when the Consolidator's LLM pass is un-gated by the R5 eval harness. When that happens, port OpenClaw's contract (model returns `{action, prior_text}` operations; code applies and validates; append-only fallback) rather than free-form rewriting. Recorded for that future.
3. **Cross-repo (Haloysius)**: promotion of Haloysius-side persona memories is now governed by `/Volumes/4TB-BAD/Haloysius/.handoff/HANDOFF-OPENCLAW-MEMORY-PROMOTION-SECOND-GUESS-2026-09-07.md` — a decision document (no work authorized) recommending Option A (fix the pre-existing `.access()` strengthen-on-retrieval feedback loop via a retrieval-event table) → B (claim-keyed signal store + query diversity) → C (curated core, founder review). **Alignment note for this packet's design:** the second-guess doc's verdict is that promotion signals must be **claim-keyed, not memory-ID-keyed**. This packet keys signals on `(subject, predicate)` ledger keys, which is claim-shaped — keep it that way; do not introduce memory-row IDs as signal keys in any Phase B work. Phase B's review checkpoint must also answer the coexistence question: Halbert's curated core and Haloysius's (if Option C is ever approved) must not double-inject the same claims into a prompt.

## Verification gates (whole packet)

- `cd halbert_core && arch -arm64 ../.venv/bin/python -m pytest tests/continuity tests/agents tests/tools -q` — pass, no regressions in thread auto-recall or recall_memory behavior.
- Fail-soft proof: with the promotion DB unwritable (read-only dir in a test), a recalled thread and a recall_memory call both still succeed.
- The R9 fence is intact until Phase B review: `git diff main..HEAD` must show zero changes to `context/adapters.py` fence comments or `routes/agent.py:164-166` while only Phase A is merged.

## Executor gotchas

- Test invocation: `cd halbert_core && arch -arm64 ../.venv/bin/python -m pytest tests/ -q` from the MAIN checkout. From worktrees use `arch -arm64 ./wt_pytest.py` — plain pytest silently tests the main tree (venv MetaPathFinder pins `halbert_core`).
- Haloysius is an external editable dependency — never edit anything under `/Volumes/4TB-BAD/Haloysius` from this packet.
- Conversation DB column additions must use the `_ADDITIVE_COLUMNS` pattern (`CREATE TABLE IF NOT EXISTS` is a no-op on existing tables and the read path fails soft to empty — the silent-blank trap). A brand-new `promotion_signals` table does not hit this.
- Imports: use `halbert_core.halbert_core.…` absolute paths in new test files exactly as shown; `threads.py` mixes relative and absolute imports — match whichever its neighbors use at your edit site.
- Pathspec commits; no Co-Authored-By trailers.