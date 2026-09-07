# OPENCLAW-LIFT-PACKET-08 — Conversation-store hardening: darwin durability, FTS fail-open, declarative columns

**Series:** Hermes-derived packet 3 of 4 (master plan: `OPENCLAW-LIFT-MASTER-PLAN-2026-09-07.md`)
**Source research:** `.handoff/OSS-REVIEW-HERMES-2026-09-07.md` §3
**Hermes source of record:** `/Volumes/Thunderbolt/AI/OSS/hermes-agent/hermes_state_wal.py` (darwin PRAGMAs, trust-the-returned-row), `hermes_state_fts.py` (`_enter_fts_fail_open`), `hermes_state_schema.py` (`_reconcile_columns`), `hermes_state_search.py` (gap-fill)
**Executor tier:** All three tasks small-model friendly — pure DB plumbing with strong test shapes. Best first packet for a small executor.
**Status:** READY TO DISPATCH

---

## Objective

Hermes's state machinery is Halbert's conversation store after years of real corruption incidents. This packet takes the three cheap, permanent, incident-proven pieces — deliberately **not** the WAL ops manual, the cross-process permits, or the repair ladder (single-process Halbert doesn't need them; see the synthesis anti-patterns):

1. **Two darwin durability PRAGMAs** — Apple's `fsync` guarantees neither ordering nor landing; a launchd-style shutdown can corrupt "durable" checkpoints. Two lines prevent a real corruption class on Halbert's only platform.
2. **FTS fail-open contract** — a corrupt derived index must never block canonical writes: breadcrumb + trigger-drop atomically, LIKE fallback keeps serving, and nobody may reinstall triggers over an unknown gap.
3. **Declarative column reconciliation** — parse the reference schema in-memory, `ALTER TABLE ADD COLUMN` everything missing, on every open. Kills the "migration reordering skipped a column" class and the "additive column without NOT NULL DEFAULT hid whole histories" trap Hermes documented.

Bonus (same edit surface): the **searchable-compacted-rows visibility rule** — archived/compacted rows stay searchable; only rewound rows hide.

## Verified current state (do not re-derive; verified 2026-09-07)

- `halbert_core/halbert_core/agents/conversation_sqlite.py` — `SqliteConversationStore`; `SCHEMA_VERSION = 4` via a `schema_version` table (`SELECT MAX(version)`); additive-column migrations (`_add_missing_columns`, `_THREAD_COLUMNS`, `_MESSAGE_COLUMNS`); FTS5 (`messages_fts`, porter+unicode61) with graceful LIKE fallback (`_fts_ok`); tables: `conversations`, `messages`, `receipts_fts`, `session_somatic_blocks`, `compact_boundaries` (no writers), `terminal_blocks`, `terminal_sessions`, `open_loops`.
- `halbert_core/halbert_core/continuity/state_store.py` — `state_triples` with a partial unique index and immediate transactions; its own additive-column pattern (`_ADDITIVE_COLUMNS`), pre-provenance table renamed aside.
- Known trap (from the repo's own comments): `CREATE TABLE IF NOT EXISTS` is a no-op on existing tables and the read path fails soft to empty — the silent-blank defect class.
- Halbert is single-process for DB access today (core + dashboard in one process; fleet proxy goes over HTTP to satellites).

## Out-of-scope guards

- Do NOT adopt WAL-vs-DELETE fallback machinery, NFS/SMB/ZFS detection, fd-permit read pools, or the repair ladder — multi-process/multi-filesystem concerns Halbert doesn't have. Record them as future triggers ("if a second process ever opens the DB file directly").
- Do NOT touch the `compact_boundaries` table's no-writers status (that's the session-tree deep pass, not this packet).
- Do NOT change the `schema_version` ladder's existence — reconciliation *complements* it: version-gate row backfills and PK surgery as today; column adds become automatic.

---

## Phase A — all tasks, one branch

**Branch:** `feat/store-hardening` off `main`.

### Task A1: darwin durability PRAGMAs

**Files:**
- Modify: `halbert_core/halbert_core/agents/conversation_sqlite.py` (connection factory)
- Modify: `halbert_core/halbert_core/continuity/state_store.py` (same)
- Test: `halbert_core/tests/agents/test_store_pragmas.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Hermes-documented darwin fact: Apple fsync(2) guarantees neither ordering nor
platter landing, and a shutdown observed corrupting 'durable' checkpoints
(hermes_state_wal.py:93-111). On darwin: checkpoint_fullfsync=1 and
synchronous=FULL, refusing to lower below FULL."""
import sys
import pytest
from halbert_core.halbert_core.agents.conversation_sqlite import SqliteConversationStore

@pytest.mark.skipif(sys.platform != "darwin", reason="darwin-only durability")
def test_darwin_pragmas_set(tmp_path):
    store = SqliteConversationStore(tmp_path / "conv.db")
    conn = store._connect_readwrite() if hasattr(store, "_connect_readwrite") else store._conn
    assert conn.execute("PRAGMA checkpoint_fullfsync").fetchone()[0] == 1
    assert conn.execute("PRAGMA synchronous").fetchone()[0] == 2  # FULL
```

(If the store's connection attribute differs, adapt the accessor — the test's assertion set is the contract, not the attribute name. Note the adaptation in the handoff.)

- [ ] **Step 2: Run, verify failure.** **Step 3: Implement** — in each connection factory, after open: `conn.execute("PRAGMA journal_mode=WAL")` if not already (keep existing behavior), then on darwin (`sys.platform == "darwin"`): `PRAGMA checkpoint_fullfsync=1` and `PRAGMA synchronous=FULL`, with a one-line comment citing the Hermes rationale. Do not gate behind config; this is platform truth, not preference.

- [ ] **Step 4: Run, verify pass** (and the full conversation-store suite). **Step 5: Commit:** `fix(store): darwin fsync barriers — checkpoint_fullfsync and synchronous=FULL on both stores`

### Task A2: FTS fail-open contract

**Files:**
- Modify: `halbert_core/halbert_core/agents/conversation_sqlite.py` (the FTS write path)
- Test: `halbert_core/tests/agents/test_fts_fail_open.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Hermes contract (hermes_state_fts.py:310): a corrupt derived index never
blocks canonical writes. On FTS write failure: (1) atomically persist a stale
breadcrumb AND drop the sync triggers in ONE transaction — once triggers are
absent the index has a gap of unknown extent, so nobody may reinstall them
without a full rebuild; (2) the canonical row write still succeeds; (3) search
falls back to LIKE (existing _fts_ok path) and keeps serving."""
import sqlite3
from halbert_core.halbert_core.agents.conversation_sqlite import SqliteConversationStore

def test_canonical_write_survives_fts_corruption(tmp_path, monkeypatch):
    store = SqliteConversationStore(tmp_path / "conv.db")
    store._corrupt_fts_for_test()  # helper this task adds: drop/damage the shadow table so inserts through triggers raise
    msg_id = store.append_message(thread_id="t1", role="user", content="hello world")  # adapt to the store's real API
    assert msg_id is not None                      # canonical write succeeded
    assert store.fts_degraded is True               # breadcrumb persisted
    hits = store.search("hello")                    # LIKE fallback serves
    assert any("hello world" in str(h) for h in hits)

def test_triggers_not_reinstalled_over_unknown_gap(tmp_path):
    store = SqliteConversationStore(tmp_path / "conv.db")
    store._corrupt_fts_for_test()
    store.append_message(thread_id="t1", role="user", content="second")
    with pytest.raises(RuntimeError, match="full rebuild"):
        store._reinstall_fts_triggers()  # must refuse while degraded

def test_full_rebuild_clears_degraded(tmp_path):
    store = SqliteConversationStore(tmp_path / "conv.db")
    store._corrupt_fts_for_test()
    store.append_message(thread_id="t1", role="user", content="third")
    store.rebuild_fts()
    assert store.fts_degraded is False
    assert store.search("third")  # FTS serving again
```

- [ ] **Step 2: Run, verify failure.** **Step 3: Implement** — in the FTS write path: catch `sqlite3.OperationalError`/`DatabaseError` from trigger-fired inserts; in one transaction set the `fts_degraded` flag (a `store_meta`-style row or module-level table) and `DROP TRIGGER` the sync triggers; retry the canonical write; log one structured `fts_fail_open` line (never raise into the caller). `_reinstall_fts_triggers`/`rebuild_fts` enforce the contract above. The test-corruption helper is test-only but ships in the module behind a leading underscore with a docstring saying so (it is how the contract is pinned).

- [ ] **Step 4: Run, verify pass** (conversation store suite + new suite). **Step 5: Commit:** `fix(store): FTS fail-open contract — corrupt index never blocks canonical writes`

### Task A3: Declarative column reconciliation

**Files:**
- Modify: `halbert_core/halbert_core/agents/conversation_sqlite.py` (`_add_missing_columns` → reconcile)
- Test: `halbert_core/tests/agents/test_column_reconciliation.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Hermes _reconcile_columns (hermes_state_schema.py:641): SCHEMA_SQL is the
single source of truth; column additions need no version-gated migration and
reordering can never skip a column. Also the Hermes trap: a reconciler-added
column without NOT NULL DEFAULT hid whole histories until an unconditional
backfill ran — so reconciled columns backfill at the same open."""
import sqlite3
from halbert_core.halbert_core.agents import conversation_sqlite as cs

def test_missing_columns_added_on_open(tmp_path):
    # a DB created by an older schema: drop a column the current schema expects
    db = tmp_path / "conv.db"
    store = cs.SqliteConversationStore(db)
    store.close()
    conn = sqlite3.connect(db)
    # simulate an older store: recreate messages without one additive column
    cols_before = [r[1] for r in conn.execute("PRAGMA table_info(messages)")]
    victim = [c for c in cols_before if c not in ("id",)][0]
    conn.execute("ALTER TABLE messages RENAME TO messages_old")
    cols = [c for c in cols_before if c != victim]
    conn.execute(f"CREATE TABLE messages AS SELECT {', '.join(cols)} FROM messages_old")
    conn.execute("DROP TABLE messages_old")
    conn.commit(); conn.close()
    store2 = cs.SqliteConversationStore(db)  # reconciliation on open
    conn = sqlite3.connect(db)
    cols_after = [r[1] for r in conn.execute("PRAGMA table_info(messages)")]
    assert victim in cols_after

def test_reconciled_column_backfilled_not_null_default(tmp_path):
    db = tmp_path / "conv.db"
    store = cs.SqliteConversationStore(db)
    store.append_message(thread_id="t1", role="user", content="x")
    store.close()
    # (the store's own schema is current; assert the invariant the Hermes trap names:)
    conn = sqlite3.connect(db)
    for (name, notnull, dflt) in conn.execute(
            "SELECT name, notnull, dflt_value FROM pragma_table_info('messages')"):
        if dflt is None and not notnull:
            assert name in ("content", "created_at"), f"column {name} has neither NOT NULL nor DEFAULT — the silent-blank trap"
    conn.close()
```

- [ ] **Step 2: Run, verify failure.** **Step 3: Implement** — in the open path, replace the enumerated `_add_missing_columns` lists with reconciliation: parse the reference `CREATE TABLE` DDL via `sqlite3.connect(":memory:")`, compare `PRAGMA table_info` per table, `ALTER TABLE ADD COLUMN` each missing column **with its DEFAULT/NOT NULL clause from the reference DDL** so no silent-blank column can be introduced. Keep the `schema_version` ladder for row backfills (out of scope here). Also apply the **visibility rule** if the store's search filters rows: compacted/archived rows remain searchable, only explicitly rewound rows hide — verify the current predicate and fix if narrower.

- [ ] **Step 4: Run the FULL store suite + agents suite** (this touches every open). **Step 5: Commit:** `refactor(store): declarative column reconciliation from the reference schema`

## Verification gates (whole packet)

- `cd halbert_core && arch -arm64 ../.venv/bin/python -m pytest tests/agents tests/continuity -q` — green, twice (second run proves reconciliation is idempotent on an already-current DB).
- An open of an OLD-shape DB (the A3 test) upgrades in place with zero data loss — assert a pre-inserted row survives reconciliation.
- No behavior change to callers: reconciliation and the fail-open path are internal; only `fts_degraded`/`rebuild_fts` are new public surface.

## Executor gotchas

- Standard set: arch-arm64 pytest; `wt_pytest.py` in worktrees (and note — the venv editable-install trap makes DB-file tests especially sneaky in worktrees: the module under test may come from the main tree; use the wrapper); pathspec commits; no co-author trailers.
- `SqliteConversationStore`'s exact method names (`append_message` shape, search signature) must be read before writing tests — the test sketches above mark adaptation points; do not invent a different API.
- Do not add `CREATE INDEX` statements in this packet; index work belongs to whatever search-performance pass exists.
- If the store is opened from multiple threads today, keep every new write-path branch inside the store's existing locking idiom (the fail-open trigger-drop transaction must not race a concurrent insert — if the store has no lock, take one around the corrupt-recovery path and say so in the handoff).