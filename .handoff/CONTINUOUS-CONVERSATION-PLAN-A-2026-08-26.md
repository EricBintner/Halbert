# Continuous Conversation — Plan A: Conversation Floor and Hidden Threads

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give Halbert one persistent, continuous conversation: every message lands in a thread the agent actually reads back, threads segment hidden topics under a single timeline, and earlier work is recalled deterministically on a strong match (the "Samba, six weeks ago" flow), with the terminal tiles of past turns no longer vanishing.

**Architecture:** `SqliteConversationStore` (SQLite + FTS5, WAL) becomes the store of record; a new `ThreadManager` resolves the open thread per turn, persists turns, builds deterministic receipts, and runs the pause → grace → close lifecycle; the state machine takes a turn lock, receives thread history and a `<continuity>` hint placed at the tail of the prompt, and handles `new_thread` / `recall_thread` / `resume_thread` inline; the frontend replaces the session picker with a paged timeline grouped by day, a sticky current-topic label, and a single "pulled in" chip. Spec: `documentation/design/continuous-conversation-and-watched-terminals-2026-08-26.md` (§3–§8, §11–§14). Binding names/signatures: `.handoff/plan-a-exec/plan-a-contracts.md`.

**Tech Stack:** Python 3.10 / FastAPI / sqlite3 + FTS5 (`porter unicode61`) / pytest + pytest-asyncio (run with `/Volumes/4TB-BAD/Halbert/.venv/bin/python`); React 18 + TypeScript / Vite / vitest + jsdom / Tailwind on the canonical tokens.

**Worktree:** `~/.config/superpowers/worktrees/Halbert/continuous-conversation` (branch `feat/continuous-conversation`). Baseline at `01ed50c`: backend 1119 passed with 4 pre-existing failures in `test_tool_calling_bridge.py` / `test_phase_d_integration.py` (model-client vision fallback — leave them); frontend 45/45; `tsc --noEmit` clean.

**Task order (33 tasks):** A1 → A1b → A2 → A3 → A4 → A5 → A6 → A6b → A6c → A6d → A7 → A8 → A8b → A9a → A9b → A9c → A9d → A10 → A11 → A11b → A12a → A12b → A12c → A12d → A13 → A14 → A15 → A16 → A17 → A17b → A18 → A19 → A20. Each task commits on its own; never move to the next task with a red test that was green before.

---

## Verification status of this plan

**First pass (27 tasks).** An independent verifier applied every task to a scratch copy of the worktree by exact text anchors and ran them: backend 1265 passed / 5 failed (the 4 pre-existing + one plan-fixture bug), frontend 17 files / 88 tests green, `tsc` clean, literal-colour counts unchanged. Its verdict is kept verbatim at `.handoff/plan-a-exec/plan-a-verifier-verdict.md`.

**Second pass (this text).** Every issue and coverage gap in that verdict is now **folded into the task text below** — there is no separate amendments section to apply while executing. What changed:

| Change | Where |
|---|---|
| BLOCKING fixture fix — `_FakeResp` emits content and `done` on separate lines | A10 |
| Red/green expectations corrected (`7 failed, 13 passed`; `154 passed`; frontend 15 files / 95 tests at A18, 17 / 101 at A19) | A1b, A6b, A18, A19 |
| `compact_boundaries` table (spec §8/§14, ships default-off, no writers) | A1 |
| `scanner` added to the network domain keywords | A4 |
| **New:** `ThreadManager.merge_back` + grace-window `resume_thread` merge (spec §5 "Merge") | A6c |
| **New:** retraction notes — hidden system rows the next turn's hint surfaces | A6d |
| **New:** conversation budget bucket for six raw turns + receipt slot in the assembler (spec §7) | A8b |
| **New:** `tools_supported` on the LLM clients; the continuity preamble drops the "call recall_thread" sentence when the model rejected tool schemas (spec §7) | A9d |
| **New:** `POST /api/agent/message/{id}/redact` + `store.redact_message` (spec §5 "Forget") | A11b |
| **New:** per-turn "Forget this" button in the timeline | A17b |
| Superseded pending confirmation recorded in the receipt; `conversation_status: waiting` on a held turn lock; somatic blocks use `ctx.thread_id` | A9a |
| `thread_recalled.last_turn_id` → chip click jumps the timeline, `matched: <terms>` title, chip expiry on `thread_started` | A7, A11, A15, A16, A18 |
| Assertive `role="alert"` live region for blocked-on-approval | A17 |
| Legacy `listAgentConversations`/`getAgentConversation`/`deleteAgentConversation` deleted in A18 instead of A14, so every commit typechecks | A14, A18 |
| Line-number references dropped in favour of the exact text anchors; `_find_config_registry` no longer re-listed; A15 test header fixed | A7, A12b, A14, A15 |

The six new tasks (A6c, A6d, A8b, A9d, A11b, A17b) carry full code and tests but were written **after** the sandbox dry-run, so their code is not yet dry-run-verified — treat their expected outputs as targets, not measurements, and trust the test runs over the numbers printed here.

**Deferred to Plan B/C (not gaps):** live terminal sessions keeping a thread open; the inbound secret scrubber; task notifications in the hint.

---

### Task A1: Thread-aware SQLite store — schema migration, WAL, append/update

**Files:**
- Modify: `halbert_core/halbert_core/agents/conversation_sqlite.py` (whole file, lines 1–410 replaced)
- Modify: `halbert_core/tests/test_conversation_sqlite.py` (lines 25–137: rewrite message writes onto `append_message`)
- Modify: `halbert_core/tests/test_session_affinity.py` (lines 11–29: fixture)
- Test: `halbert_core/tests/test_thread_store.py` (new)

- [ ] **Write the failing test** — create `halbert_core/tests/test_thread_store.py`:

```python
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for the thread-aware SqliteConversationStore (Plan A: A1, A1b, A3)."""

import json
import logging
import sqlite3

import pytest

from halbert_core.agents.conversation_sqlite import SqliteConversationStore, SCHEMA_VERSION


@pytest.fixture
def store():
    s = SqliteConversationStore(":memory:")
    yield s
    s.close()


# ---------------------------------------------------------------------------
# Connection + schema
# ---------------------------------------------------------------------------

class TestConnection:
    def test_wal_and_busy_timeout_on_file_db(self, tmp_path):
        s = SqliteConversationStore(str(tmp_path / "t.db"))
        assert s._conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert s._conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
        s.close()


class TestSchema:
    def test_new_columns_and_version(self, store):
        cols = {r[1] for r in store._conn.execute("PRAGMA table_info(conversations)")}
        assert {"status", "receipt", "receipt_updated_at", "topic_domains", "entities_json",
                "last_active", "stale", "ephemeral", "parent_thread_id", "merged_into",
                "recalled_json", "unread", "paused_at", "turns_since_pause",
                "title_source"} <= cols
        mcols = {r[1] for r in store._conn.execute("PRAGMA table_info(messages)")}
        assert {"turn_id", "session_id", "origin", "status", "blocks_json",
                "terminal_block_ids", "diff_proposals_json", "visible_in_timeline"} <= mcols
        assert store._conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] == SCHEMA_VERSION
        sql = store._conn.execute("SELECT sql FROM sqlite_master WHERE name = 'messages_fts'").fetchone()[0]
        assert "porter unicode61" in sql
        assert store._conn.execute("SELECT name FROM sqlite_master WHERE name = 'receipts_fts'").fetchone() is not None
        # compact_boundaries ships in Plan A with no writers (spec §8, §14: default off)
        ccols = {r[1] for r in store._conn.execute("PRAGMA table_info(compact_boundaries)")}
        assert {"thread_id", "trigger", "pre_tokens", "post_tokens", "preserved_message_ids",
                "summary_message_id", "created_at"} <= ccols
        assert store._conn.execute("SELECT COUNT(*) FROM compact_boundaries").fetchone()[0] == 0

    def test_legacy_db_migrates_in_place(self, tmp_path):
        path = tmp_path / "legacy.db"
        raw = sqlite3.connect(str(path))
        raw.execute("CREATE TABLE conversations (id TEXT PRIMARY KEY, user_id TEXT, title TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL, metadata TEXT NOT NULL DEFAULT '{}')")
        raw.execute("CREATE TABLE messages (id INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id TEXT NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL, timestamp REAL NOT NULL, metadata TEXT NOT NULL DEFAULT '{}')")
        raw.execute("CREATE VIRTUAL TABLE messages_fts USING fts5(conversation_id UNINDEXED, content)")
        raw.execute("INSERT INTO conversations (id, title, created_at, updated_at) VALUES ('old', 'Old chat', 1.0, 1.0)")
        raw.execute("INSERT INTO messages (conversation_id, role, content, timestamp) VALUES ('old', 'user', 'edit smb.conf for the media share', 1.0)")
        raw.execute("INSERT INTO messages_fts(conversation_id, content) VALUES ('old', 'edit smb.conf for the media share')")
        raw.commit()
        raw.close()

        s = SqliteConversationStore(str(path))
        row = s._conn.execute("SELECT status, title_source, receipt FROM conversations WHERE id = 'old'").fetchone()
        assert (row["status"], row["title_source"], row["receipt"]) == ("open", "provisional", "")
        assert s._conn.execute("SELECT origin, status FROM messages").fetchone()[:] == ("human", "complete")
        assert s._conn.execute("SELECT rowid FROM messages_fts").fetchall()[0][0] == 1
        assert s._conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] == 2
        assert s._conn.execute("SELECT name FROM sqlite_master WHERE name = 'compact_boundaries'").fetchone() is not None
        assert s.search("smb.conf") == ["old"]
        s.close()
        # Reopening is idempotent
        s2 = SqliteConversationStore(str(path))
        assert s2._conn.execute("SELECT COUNT(*) FROM messages_fts").fetchone()[0] == 1
        assert s2._conn.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0] == 1
        s2.close()


# ---------------------------------------------------------------------------
# append_message / update_message
# ---------------------------------------------------------------------------

class TestAppend:
    def test_append_returns_id_and_indexes_fts(self, store):
        store.create("t1")
        mid = store.append_message("t1", "user", "check the samba share", origin="human",
                                   turn_id="turn-1", session_id="s1", status="in_progress")
        assert isinstance(mid, int)
        row = store._conn.execute("SELECT * FROM messages WHERE id = ?", (mid,)).fetchone()
        assert (row["turn_id"], row["session_id"], row["origin"], row["status"]) == ("turn-1", "s1", "human", "in_progress")
        assert row["blocks_json"] == "[]" and row["visible_in_timeline"] == 1
        assert store._conn.execute("SELECT rowid FROM messages_fts WHERE messages_fts MATCH '\"samba\"'").fetchone()[0] == mid
        assert store._conn.execute("SELECT updated_at FROM conversations WHERE id = 't1'").fetchone()[0] == row["timestamp"]

    def test_block_content_is_flattened_and_kept(self, store):
        store.create("t1")
        content = [{"type": "text", "text": "Running it"},
                   {"type": "tool_use", "id": "x", "name": "run_command", "input": {"command": "testparm"}}]
        mid = store.append_message("t1", "assistant", content, origin="assistant")
        row = store._conn.execute("SELECT content, blocks_json FROM messages WHERE id = ?", (mid,)).fetchone()
        assert row["content"] == "Running it\n[tool_use: run_command({'command': 'testparm'})]"
        assert json.loads(row["blocks_json"]) == content

    def test_failed_append_rolls_back_and_returns_none(self, store, caplog):
        store.create("t1")
        store._conn.execute("DROP TABLE messages_fts")
        store._conn.execute("CREATE TABLE messages_fts (conversation_id TEXT, content TEXT CHECK(length(content) < 5))")
        with caplog.at_level(logging.WARNING, logger="halbert.agents.conversation_sqlite"):
            assert store.append_message("t1", "user", "hello world") is None
        assert store._conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 0
        assert store._conn.in_transaction is False
        assert any("append_message failed" in r.message for r in caplog.records)
        # the store is still usable afterwards
        assert store.append_message("t1", "user", "hey") is not None


class TestUpdateMessage:
    def test_update_status_and_lists(self, store):
        store.create("t1")
        mid = store.append_message("t1", "assistant", "x", origin="assistant", status="in_progress")
        assert store.update_message(mid, status="complete",
                                    blocks=[{"tool": "run_command", "args": {"command": "ls"}, "exit": 0}],
                                    terminal_block_ids=["term-1"], diff_proposals=[{"id": "d1"}]) is True
        row = store._conn.execute("SELECT * FROM messages WHERE id = ?", (mid,)).fetchone()
        assert row["status"] == "complete"
        assert json.loads(row["blocks_json"])[0]["tool"] == "run_command"
        assert json.loads(row["terminal_block_ids"]) == ["term-1"]
        assert json.loads(row["diff_proposals_json"]) == [{"id": "d1"}]

    def test_update_content_reindexes_fts(self, store):
        store.create("t1")
        mid = store.append_message("t1", "user", "old words")
        assert store.update_message(mid, content="new samba words") is True
        assert store._conn.execute("SELECT rowid FROM messages_fts WHERE messages_fts MATCH '\"samba\"'").fetchone()[0] == mid
        assert store._conn.execute("SELECT rowid FROM messages_fts WHERE messages_fts MATCH '\"old\"'").fetchone() is None

    def test_update_thread_id_moves_row(self, store):
        store.create("t1"); store.create("t2")
        mid = store.append_message("t1", "user", "moving")
        assert store.update_message(mid, thread_id="t2") is True
        assert store._conn.execute("SELECT conversation_id FROM messages WHERE id = ?", (mid,)).fetchone()[0] == "t2"
        assert store._conn.execute("SELECT conversation_id FROM messages_fts WHERE rowid = ?", (mid,)).fetchone()[0] == "t2"

    def test_unknown_field_and_missing_row(self, store):
        store.create("t1")
        mid = store.append_message("t1", "user", "x")
        assert store.update_message(mid, role="assistant") is False
        assert store.update_message(999, status="complete") is False


class TestSave:
    def test_save_does_not_touch_messages(self, store):
        conv = store.create("t1")
        store.append_message("t1", "user", "kept")
        conv.messages = []
        conv.title = "renamed"
        assert store.save(conv) is True
        got = store.get("t1")
        assert got.title == "renamed"
        assert [m.content for m in got.messages] == ["kept"]

    def test_save_preserves_thread_columns(self, store):
        conv = store.create("t1")
        store._conn.execute("UPDATE conversations SET status = 'paused', receipt = 'r' WHERE id = 't1'")
        store._conn.commit()
        store.save(conv)
        row = store._conn.execute("SELECT status, receipt FROM conversations WHERE id = 't1'").fetchone()
        assert (row["status"], row["receipt"]) == ("paused", "r")


class TestSearchPunctuation:
    def test_dotted_and_apostrophe_queries_do_not_abort(self, store):
        store.create("t1")
        store.append_message("t1", "user", "the config lives in smb.conf")
        assert store.search("smb.conf") == ["t1"]
        assert store.search("what's") == []
        assert store.search("what's in smb.conf") == ["t1"]
```

- [ ] **Run it, expect failure:**
  `cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core && /Volumes/4TB-BAD/Halbert/.venv/bin/python -m pytest tests/test_thread_store.py -q -p no:cacheprovider`
  Expected: `ImportError: cannot import name 'SCHEMA_VERSION' from 'halbert_core.agents.conversation_sqlite'` (1 error during collection).

- [ ] **Replace `halbert_core/halbert_core/agents/conversation_sqlite.py` with this complete file:**

```python
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""SQLite + FTS5 store of record for the one continuous conversation.

``conversations`` rows are *threads* (the physical column ``conversation_id``
on ``messages`` is the thread id everywhere). ``append_message`` is the only
message write path; ``save`` upserts the thread row and never touches
messages. Every write runs inside ``with self._conn:`` so a failed write
rolls back as a unit. Failures are logged at WARNING and reported as
``None``/``False`` so a route can emit ``thread_store_error`` once.

See documentation/design/continuous-conversation-and-watched-terminals-2026-08-26.md §8.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .blocks import content_to_text
from .conversation import Conversation, Message

logger = logging.getLogger("halbert.agents.conversation_sqlite")

_DEFAULT_DB = str(Path.home() / ".halbert" / "conversations.db")

#: Bump when a migration step below must run on existing databases.
SCHEMA_VERSION = 2

# Columns added to the legacy tables. ``_ensure_schema`` applies each one
# with ``ALTER TABLE ... ADD COLUMN`` when ``PRAGMA table_info`` lacks it.
_THREAD_COLUMNS: List[Tuple[str, str]] = [
    ("status", "TEXT NOT NULL DEFAULT 'open'"),
    ("receipt", "TEXT NOT NULL DEFAULT ''"),
    ("receipt_updated_at", "REAL"),
    ("topic_domains", "TEXT NOT NULL DEFAULT '[]'"),
    ("entities_json", "TEXT NOT NULL DEFAULT '[]'"),
    ("last_active", "REAL"),
    ("stale", "INTEGER NOT NULL DEFAULT 0"),
    ("ephemeral", "INTEGER NOT NULL DEFAULT 0"),
    ("parent_thread_id", "TEXT"),
    ("merged_into", "TEXT"),
    ("recalled_json", "TEXT NOT NULL DEFAULT '[]'"),
    ("unread", "INTEGER NOT NULL DEFAULT 0"),
    ("paused_at", "REAL"),
    ("turns_since_pause", "INTEGER NOT NULL DEFAULT 0"),
    ("title_source", "TEXT NOT NULL DEFAULT 'provisional'"),
]
_MESSAGE_COLUMNS: List[Tuple[str, str]] = [
    ("turn_id", "TEXT"),
    ("session_id", "TEXT"),
    ("origin", "TEXT NOT NULL DEFAULT 'human'"),
    ("status", "TEXT NOT NULL DEFAULT 'complete'"),
    ("blocks_json", "TEXT NOT NULL DEFAULT '[]'"),
    ("terminal_block_ids", "TEXT NOT NULL DEFAULT '[]'"),
    ("diff_proposals_json", "TEXT NOT NULL DEFAULT '[]'"),
    ("visible_in_timeline", "INTEGER NOT NULL DEFAULT 1"),
]

# update_message field -> column
_MESSAGE_UPDATABLE = {
    "content": "content",
    "status": "status",
    "blocks": "blocks_json",
    "terminal_block_ids": "terminal_block_ids",
    "diff_proposals": "diff_proposals_json",
    "metadata": "metadata",
    "thread_id": "conversation_id",
}
_MESSAGE_JSON_COLUMNS = {"blocks_json", "terminal_block_ids", "diff_proposals_json", "metadata"}

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# Dropped from receipt queries so a score reflects topical words only.
_QUERY_STOPWORDS = frozenset("""
a about above actually add after again against ago all also am an and another any anything are as at
back be because been before being below between both but by can cannot check could day days did do does
doing done down during each earlier else ever everything few fine fix for from further get give go going
got had has have having he hello help her here hers hey hi him his how i if in into is it its itself just
know last let like look luck make maybe me might month months more most much must my need needed no nor not
nothing now of off ok okay on once one only or other our ours out over own please put really remember run
same see set shall she should show since so some something still such sure take tell than thank thanks
that the their theirs them then there these they thing think this those through time to today tomorrow
too try under until up us use used using very want wanted was way we week weeks well were what when where
which while who whom why will with work working works would yes yesterday yet you your yours
""".split())


def _fts_terms(query: str, *, drop_stopwords: bool = True, max_terms: int = 12) -> List[str]:
    """Lowercase alphanumeric tokens of ``query`` (deduplicated, ordered)."""
    out: List[str] = []
    for tok in _TOKEN_RE.findall((query or "").lower()):
        if drop_stopwords and (len(tok) < 2 or tok in _QUERY_STOPWORDS):
            continue
        if tok not in out:
            out.append(tok)
        if len(out) >= max_terms:
            break
    return out


def _fts_query(terms: Sequence[str]) -> str:
    """Each term quoted so FTS5 syntax characters (``.``/``'``) cannot abort a MATCH."""
    return " OR ".join(f'"{t}"' for t in terms)


def _loads(text: Any, default: Any) -> Any:
    if not text:
        return default
    try:
        value = json.loads(text)
    except Exception:
        return default
    return value if value is not None else default


class SqliteConversationStore:
    """SQLite-backed thread/message store with FTS5 search.

    Thread-safe (single connection + re-entrant lock). Best-effort: methods
    log at WARNING and return ``None``/``False``/``[]`` rather than raise.
    """

    def __init__(self, db_path: Optional[str] = None):
        self._db_path = db_path or _DEFAULT_DB
        self._lock = threading.RLock()
        self._conn: Optional[sqlite3.Connection] = None
        self._fts_ok = False
        try:
            if self._db_path != ":memory:":
                Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._ensure_schema()
        except Exception as e:
            logger.warning(f"SqliteConversationStore init failed (non-fatal): {e}")
            self._conn = None

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    @staticmethod
    def _add_missing_columns(cur: sqlite3.Cursor, table: str, columns: List[Tuple[str, str]]) -> None:
        existing = {row[1] for row in cur.execute(f"PRAGMA table_info({table})").fetchall()}
        for name, decl in columns:
            if name not in existing:
                cur.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")

    def _ensure_schema(self) -> None:
        try:
            with self._lock:
                cur = self._conn.cursor()
                # PRAGMAs first: they must run outside any transaction.
                cur.execute("PRAGMA journal_mode=WAL")
                cur.execute("PRAGMA busy_timeout=5000")
                cur.execute(
                    """CREATE TABLE IF NOT EXISTS conversations (
                        id         TEXT PRIMARY KEY,
                        user_id    TEXT,
                        title      TEXT,
                        created_at REAL NOT NULL,
                        updated_at REAL NOT NULL,
                        metadata   TEXT NOT NULL DEFAULT '{}'
                    )"""
                )
                cur.execute(
                    """CREATE TABLE IF NOT EXISTS messages (
                        id              INTEGER PRIMARY KEY AUTOINCREMENT,
                        conversation_id  TEXT NOT NULL,
                        role             TEXT NOT NULL,
                        content          TEXT NOT NULL,
                        timestamp        REAL NOT NULL,
                        metadata         TEXT NOT NULL DEFAULT '{}'
                    )"""
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_messages_conv "
                    "ON messages(conversation_id)"
                )
                cur.execute(
                    """CREATE TABLE IF NOT EXISTS session_somatic_blocks (
                        id         TEXT PRIMARY KEY,
                        session_id TEXT NOT NULL,
                        block_id   TEXT NOT NULL,
                        block_type TEXT,
                        status     TEXT,
                        created_at REAL NOT NULL,
                        metadata   TEXT NOT NULL DEFAULT '{}'
                    )"""
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_ssb_session "
                    "ON session_somatic_blocks(session_id)"
                )
                cur.execute(
                    "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)"
                )
                # Opt-in LLM summaries (spec §8, §14): the table ships in Plan A
                # with no writers — compaction stays default-off until a later plan.
                cur.execute(
                    """CREATE TABLE IF NOT EXISTS compact_boundaries (
                        id                    INTEGER PRIMARY KEY AUTOINCREMENT,
                        thread_id             TEXT NOT NULL,
                        trigger               TEXT NOT NULL,
                        pre_tokens            INTEGER,
                        post_tokens           INTEGER,
                        preserved_message_ids TEXT NOT NULL DEFAULT '[]',
                        summary_message_id    INTEGER,
                        created_at            REAL NOT NULL
                    )"""
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_compact_thread "
                    "ON compact_boundaries(thread_id)"
                )
                self._add_missing_columns(cur, "conversations", _THREAD_COLUMNS)
                self._add_missing_columns(cur, "messages", _MESSAGE_COLUMNS)
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_messages_turn ON messages(turn_id)"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_conversations_status "
                    "ON conversations(status)"
                )
                row = cur.execute("SELECT MAX(version) FROM schema_version").fetchone()
                version = int(row[0]) if row and row[0] is not None else 0
                try:
                    if version < 2:
                        # v2: porter stemming + rowid == messages.id (for snippets).
                        cur.execute("DROP TABLE IF EXISTS messages_fts")
                        cur.execute(
                            "CREATE VIRTUAL TABLE messages_fts USING fts5("
                            "conversation_id UNINDEXED, content, "
                            "tokenize='porter unicode61')"
                        )
                        cur.execute(
                            "INSERT INTO messages_fts(rowid, conversation_id, content) "
                            "SELECT id, conversation_id, content FROM messages"
                        )
                    else:
                        cur.execute(
                            "CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5("
                            "conversation_id UNINDEXED, content, "
                            "tokenize='porter unicode61')"
                        )
                    cur.execute(
                        "CREATE VIRTUAL TABLE IF NOT EXISTS receipts_fts USING fts5("
                        "thread_id UNINDEXED, title, receipt, "
                        "tokenize='porter unicode61')"
                    )
                    self._fts_ok = True
                except sqlite3.OperationalError as e:
                    logger.warning(f"FTS5 unavailable, falling back to LIKE: {e}")
                    self._fts_ok = False
                if version < SCHEMA_VERSION:
                    cur.execute("DELETE FROM schema_version")
                    cur.execute(
                        "INSERT INTO schema_version(version) VALUES (?)", (SCHEMA_VERSION,)
                    )
                self._conn.commit()
        except Exception as e:
            logger.warning(f"SqliteConversationStore schema failed: {e}")

    # ------------------------------------------------------------------
    # Legacy CRUD (Conversation dataclass shape)
    # ------------------------------------------------------------------

    def get(self, conversation_id: str) -> Optional[Conversation]:
        if self._conn is None:
            return None
        try:
            with self._lock:
                row = self._conn.execute(
                    "SELECT * FROM conversations WHERE id = ?", (conversation_id,)
                ).fetchone()
                if row is None:
                    return None
                msgs = self._conn.execute(
                    "SELECT role, content, timestamp, metadata FROM messages "
                    "WHERE conversation_id = ? ORDER BY id ASC", (conversation_id,)
                ).fetchall()
        except Exception as e:
            logger.warning(f"sqlite get failed: {e}")
            return None
        conv = Conversation(
            conversation_id=row["id"],
            user_id=row["user_id"],
            title=row["title"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            metadata=_loads(row["metadata"], {}),
        )
        conv.messages = [
            Message(
                role=m["role"],
                content=m["content"],
                timestamp=m["timestamp"],
                metadata=_loads(m["metadata"], {}),
            )
            for m in msgs
        ]
        return conv

    def create(self, conversation_id: str, user_id: Optional[str] = None) -> Conversation:
        conv = Conversation(conversation_id=conversation_id, user_id=user_id)
        self.save(conv)
        return conv

    def get_or_create(self, conversation_id: str, user_id: Optional[str] = None) -> Conversation:
        conv = self.get(conversation_id)
        return conv if conv is not None else self.create(conversation_id, user_id)

    def save(self, conversation: Conversation) -> bool:
        """Upsert the thread row only. Messages are written by ``append_message``."""
        if self._conn is None:
            return False
        cid = conversation.conversation_id
        meta = json.dumps(conversation.metadata or {})
        try:
            with self._lock, self._conn:
                self._conn.execute(
                    """INSERT INTO conversations
                       (id, user_id, title, created_at, updated_at, metadata)
                       VALUES (?, ?, ?, ?, ?, ?)
                       ON CONFLICT(id) DO UPDATE SET
                         user_id    = excluded.user_id,
                         title      = excluded.title,
                         updated_at = excluded.updated_at,
                         metadata   = excluded.metadata""",
                    (cid, conversation.user_id, conversation.title,
                     conversation.created_at, conversation.updated_at, meta),
                )
            return True
        except Exception as e:
            logger.warning(f"sqlite save failed: {e}")
            return False

    def delete(self, conversation_id: str) -> bool:
        if self._conn is None:
            return False
        try:
            with self._lock, self._conn:
                self._conn.execute(
                    "DELETE FROM conversations WHERE id = ?", (conversation_id,)
                )
                self._conn.execute(
                    "DELETE FROM messages WHERE conversation_id = ?", (conversation_id,)
                )
                if self._fts_ok:
                    self._conn.execute(
                        "DELETE FROM messages_fts WHERE conversation_id = ?",
                        (conversation_id,),
                    )
                    self._conn.execute(
                        "DELETE FROM receipts_fts WHERE thread_id = ?",
                        (conversation_id,),
                    )
            return True
        except Exception as e:
            logger.warning(f"sqlite delete failed: {e}")
            return False

    def list_conversations(
        self, user_id: Optional[str] = None, limit: int = 50, offset: int = 0
    ) -> List[Dict[str, Any]]:
        if self._conn is None:
            return []
        try:
            with self._lock:
                if user_id:
                    cur = self._conn.execute(
                        """SELECT c.id, c.title, c.user_id, c.created_at, c.updated_at,
                                  (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id) AS message_count
                           FROM conversations c WHERE c.user_id = ?
                           ORDER BY c.updated_at DESC LIMIT ? OFFSET ?""",
                        (user_id, limit, offset),
                    )
                else:
                    cur = self._conn.execute(
                        """SELECT c.id, c.title, c.user_id, c.created_at, c.updated_at,
                                  (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id) AS message_count
                           FROM conversations c
                           ORDER BY c.updated_at DESC LIMIT ? OFFSET ?""",
                        (limit, offset),
                    )
                rows = cur.fetchall()
            return [{
                "conversation_id": r["id"],
                "title": r["title"],
                "user_id": r["user_id"],
                "message_count": r["message_count"],
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
            } for r in rows]
        except Exception as e:
            logger.warning(f"sqlite list_conversations failed: {e}")
            return []

    def search(
        self, query: str, user_id: Optional[str] = None, limit: int = 20
    ) -> List[str]:
        """Full-text search over message content (+ title LIKE). Returns thread ids."""
        if self._conn is None or not query:
            return []
        results: List[str] = []
        terms = _fts_terms(query, drop_stopwords=False)
        if self._fts_ok and terms:
            try:
                with self._lock:
                    rows = self._conn.execute(
                        """SELECT DISTINCT m.conversation_id
                           FROM messages_fts m
                           JOIN conversations c ON c.id = m.conversation_id
                           WHERE messages_fts MATCH ? AND (? IS NULL OR c.user_id = ?)
                           LIMIT ?""",
                        (_fts_query(terms), user_id, user_id, limit),
                    ).fetchall()
                results = [r[0] for r in rows]
            except Exception as e:
                logger.warning(f"sqlite FTS search failed (LIKE fallback only): {e}")
        try:
            with self._lock:
                trows = self._conn.execute(
                    """SELECT id FROM conversations
                       WHERE lower(title) LIKE ? AND (? IS NULL OR user_id = ?)
                       LIMIT ?""",
                    (f"%{query.lower()}%", user_id, user_id, limit),
                ).fetchall()
            for r in trows:
                if r[0] not in results:
                    results.append(r[0])
        except Exception as e:
            logger.warning(f"sqlite title search failed: {e}")
        return results[:limit]

    # ------------------------------------------------------------------
    # Messages (append-only write path)
    # ------------------------------------------------------------------

    def append_message(
        self,
        thread_id: str,
        role: str,
        content: Any,
        *,
        origin: str = "human",
        turn_id: Optional[str] = None,
        session_id: Optional[str] = None,
        status: str = "complete",
        blocks: Optional[list] = None,
        terminal_block_ids: Optional[List[str]] = None,
        diff_proposals: Optional[list] = None,
        metadata: Optional[dict] = None,
        timestamp: Optional[float] = None,
        visible_in_timeline: bool = True,
    ) -> Optional[int]:
        """Insert one message row + its FTS row in a single transaction.

        Returns the new row id, or ``None`` (after a WARNING) when the write
        failed; nothing is left behind on failure.
        """
        if self._conn is None:
            return None
        if isinstance(content, str):
            text = content
        else:
            text = content_to_text(content)
            if blocks is None and isinstance(content, list):
                blocks = [
                    b.to_dict() if hasattr(b, "to_dict") and callable(b.to_dict) else b
                    for b in content
                ]
        ts = float(timestamp) if timestamp is not None else time.time()
        try:
            with self._lock, self._conn:
                cur = self._conn.execute(
                    """INSERT INTO messages
                       (conversation_id, role, content, timestamp, metadata, turn_id,
                        session_id, origin, status, blocks_json, terminal_block_ids,
                        diff_proposals_json, visible_in_timeline)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (thread_id, role, text, ts, json.dumps(metadata or {}), turn_id,
                     session_id, origin, status, json.dumps(blocks or []),
                     json.dumps(terminal_block_ids or []),
                     json.dumps(diff_proposals or []), 1 if visible_in_timeline else 0),
                )
                message_id = int(cur.lastrowid)
                if self._fts_ok:
                    self._conn.execute(
                        "INSERT INTO messages_fts(rowid, conversation_id, content) "
                        "VALUES (?, ?, ?)",
                        (message_id, thread_id, text),
                    )
                self._conn.execute(
                    "UPDATE conversations SET updated_at = ? WHERE id = ?", (ts, thread_id)
                )
            return message_id
        except Exception as e:
            logger.warning(f"append_message failed for thread {thread_id}: {e}")
            return None

    def update_message(self, message_id: int, **fields: Any) -> bool:
        """Update allowed columns of one message row (re-indexes FTS when needed).

        Allowed: content, status, blocks, terminal_block_ids, diff_proposals,
        metadata, thread_id.
        """
        if self._conn is None or not fields:
            return False
        sets: List[str] = []
        params: List[Any] = []
        for key, value in fields.items():
            col = _MESSAGE_UPDATABLE.get(key)
            if col is None:
                logger.warning(f"update_message: unknown field {key!r}")
                return False
            if col in _MESSAGE_JSON_COLUMNS:
                if value is None:
                    value = {} if col == "metadata" else []
                value = json.dumps(value)
            elif col == "content" and not isinstance(value, str):
                value = content_to_text(value)
            sets.append(f"{col} = ?")
            params.append(value)
        params.append(message_id)
        reindex = "content" in fields or "thread_id" in fields
        try:
            with self._lock, self._conn:
                cur = self._conn.execute(
                    f"UPDATE messages SET {', '.join(sets)} WHERE id = ?", params
                )
                if cur.rowcount == 0:
                    return False
                if reindex and self._fts_ok:
                    row = self._conn.execute(
                        "SELECT conversation_id, content FROM messages WHERE id = ?",
                        (message_id,),
                    ).fetchone()
                    self._conn.execute(
                        "DELETE FROM messages_fts WHERE rowid = ?", (message_id,)
                    )
                    self._conn.execute(
                        "INSERT INTO messages_fts(rowid, conversation_id, content) "
                        "VALUES (?, ?, ?)",
                        (message_id, row["conversation_id"], row["content"]),
                    )
            return True
        except Exception as e:
            logger.warning(f"update_message {message_id} failed: {e}")
            return False

    def mark_in_progress_interrupted(self) -> int:
        """Boot-time sweep: every ``in_progress`` row becomes ``interrupted``."""
        if self._conn is None:
            return 0
        try:
            with self._lock, self._conn:
                cur = self._conn.execute(
                    "UPDATE messages SET status = 'interrupted' WHERE status = 'in_progress'"
                )
                return int(cur.rowcount or 0)
        except Exception as e:
            logger.warning(f"mark_in_progress_interrupted failed: {e}")
            return 0

    # ------------------------------------------------------------------
    # session_somatic_blocks (C1 link)
    # ------------------------------------------------------------------

    def add_somatic_block(
        self, session_id: str, block_id: str, block_type: str = "",
        status: str = "", metadata: Optional[Dict] = None,
    ) -> bool:
        if self._conn is None:
            return False
        try:
            with self._lock, self._conn:
                self._conn.execute(
                    """INSERT OR REPLACE INTO session_somatic_blocks
                       (id, session_id, block_id, block_type, status, created_at, metadata)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (f"{session_id}:{block_id}", session_id, block_id, block_type,
                     status, time.time(), json.dumps(metadata or {})),
                )
            return True
        except Exception as e:
            logger.warning(f"add_somatic_block failed: {e}")
            return False

    def list_somatic_blocks(self, session_id: str) -> List[Dict[str, Any]]:
        if self._conn is None:
            return []
        try:
            with self._lock:
                rows = self._conn.execute(
                    "SELECT block_id, block_type, status, created_at, metadata "
                    "FROM session_somatic_blocks WHERE session_id = ? "
                    "ORDER BY created_at ASC", (session_id,),
                ).fetchall()
            return [{
                "block_id": r["block_id"], "block_type": r["block_type"],
                "status": r["status"], "created_at": r["created_at"],
                "metadata": _loads(r["metadata"], {}),
            } for r in rows]
        except Exception as e:
            logger.warning(f"list_somatic_blocks failed: {e}")
            return []

    def remove_somatic_block(self, session_id: str, block_id: str) -> bool:
        if self._conn is None:
            return False
        try:
            with self._lock, self._conn:
                self._conn.execute(
                    "DELETE FROM session_somatic_blocks WHERE session_id = ? AND block_id = ?",
                    (session_id, block_id),
                )
            return True
        except Exception as e:
            logger.warning(f"remove_somatic_block failed: {e}")
            return False

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None


# ---------------------------------------------------------------------------
# One-time migration: JSON -> SQLite (superseded by agents/migrations.py in A12)
# ---------------------------------------------------------------------------

def migrate_json_conversations_to_sqlite(
    json_store: Any, sqlite_store: SqliteConversationStore
) -> int:
    """Migrate every ``*.json`` conversation from a JSON ``ConversationStore``
    into a ``SqliteConversationStore``. Returns the number migrated.

    Idempotent: a thread that already holds messages is not re-appended.
    (Superseded by ``agents/migrations.py`` in A12, which also closes threads.)
    """
    storage_path = getattr(json_store, "storage_path", None)
    if storage_path is None or not Path(storage_path).exists():
        return 0
    n = 0
    for file_path in Path(storage_path).glob("*.json"):
        try:
            with open(file_path, "r") as f:
                data = json.load(f)
            conv = Conversation.from_dict(data)
            messages = list(conv.messages)
            conv.messages = []
            existing = sqlite_store.get(conv.conversation_id)
            if existing is not None and existing.messages:
                n += 1  # already migrated
                continue
            if not sqlite_store.save(conv):
                continue
            for m in messages:
                sqlite_store.append_message(
                    conv.conversation_id, m.role, m.content,
                    origin="assistant" if m.role == "assistant" else "human",
                    metadata=m.metadata, timestamp=m.timestamp,
                )
            n += 1
        except Exception as e:
            logger.warning(f"migration skipped {file_path}: {e}")
    logger.info(f"Migrated {n} conversations from JSON to SQLite")
    return n
```

- [ ] **Update the existing tests that relied on `save()` writing messages.** In `halbert_core/tests/test_conversation_sqlite.py` make these exact replacements:

  1. `test_create_and_get` (lines 27–30) — replace
     ```python
             conv = store.create("c1", user_id="u1")
             conv.add_message("user", "hello there")
             conv.add_message("assistant", "hi!")
             store.save(conv)
     ```
     with
     ```python
             store.create("c1", user_id="u1")
             store.append_message("c1", "user", "hello there")
             store.append_message("c1", "assistant", "hi!", origin="assistant")
     ```
  2. `test_save_replaces_messages` (lines 49–58) — replace the whole method with
     ```python
         def test_save_never_touches_messages(self, store):
             conv = store.create("c3")
             store.append_message("c3", "user", "first")
             # Re-saving with a different in-memory message list changes nothing on disk
             conv.messages = [Message(role="user", content="replaced")]
             store.save(conv)
             got = store.get("c3")
             assert len(got.messages) == 1
             assert got.messages[0].content == "first"
     ```
  3. `test_delete` (lines 61–63) — replace
     ```python
             conv = store.create("c4")
             conv.add_message("user", "x")
             store.save(conv)
     ```
     with
     ```python
             store.create("c4")
             store.append_message("c4", "user", "x")
     ```
  4. `test_list_returns_summaries` (lines 83–85) — replace
     ```python
                 c = store.create(f"c{i}", user_id="u1")
                 c.add_message("user", f"msg {i}")
                 store.save(c)
     ```
     with
     ```python
                 store.create(f"c{i}", user_id="u1")
                 store.append_message(f"c{i}", "user", f"msg {i}")
     ```
  5. `test_search_finds_by_message_content` (lines 110–113) — replace
     ```python
             c = store.create("s1")
             c.add_message("user", "how do I configure the nginx firewall")
             c.add_message("assistant", "you can use ufw to manage the firewall")
             store.save(c)
     ```
     with
     ```python
             store.create("s1")
             store.append_message("s1", "user", "how do I configure the nginx firewall")
             store.append_message("s1", "assistant", "you can use ufw to manage the firewall", origin="assistant")
     ```
  6. `test_search_finds_by_title` (line 119) — replace `c.add_message("user", "disk usage report")  # sets title` with `c.title = "disk usage report"`.
  7. `test_search_no_match` (lines 125–127) — replace
     ```python
             c = store.create("s3")
             c.add_message("user", "nothing relevant here")
             store.save(c)
     ```
     with
     ```python
             store.create("s3")
             store.append_message("s3", "user", "nothing relevant here")
     ```
  8. `test_search_multiple_matches_distinct` (lines 134–135) — replace
     ```python
             c1 = store.create("m1"); c1.add_message("user", "fix the network"); store.save(c1)
             c2 = store.create("m2"); c2.add_message("user", "network is down"); store.save(c2)
     ```
     with
     ```python
             store.create("m1"); store.append_message("m1", "user", "fix the network")
             store.create("m2"); store.append_message("m2", "user", "network is down")
     ```

  In `halbert_core/tests/test_session_affinity.py` replace the fixture body (lines 13–27) with:
  ```python
      s = SqliteConversationStore(":memory:")
      # seed conversations (append_message is the only message write path)
      s.create("disk-conv", "u1")
      s.append_message("disk-conv", "user", "my disk is filling up on /var")
      s.append_message("disk-conv", "assistant", "run du -sh /var/log", origin="assistant")

      s.create("network-conv", "u1")
      s.append_message("network-conv", "user", "the nginx firewall is blocking traffic")
      s.append_message("network-conv", "assistant", "check ufw status", origin="assistant")

      s.create("cpu-conv", "u1")
      s.append_message("cpu-conv", "user", "cpu load is very high")
  ```
  (keep the `yield s` / `s.close()` lines that follow).

- [ ] **Run tests, expect PASS:**
  `cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core && /Volumes/4TB-BAD/Halbert/.venv/bin/python -m pytest tests/test_thread_store.py tests/test_conversation_sqlite.py tests/test_session_affinity.py -q -p no:cacheprovider`
  Expected: `46 passed` (13 new + 20 + 13).

- [ ] **Commit:**
  ```
  cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation && git add halbert_core/halbert_core/agents/conversation_sqlite.py halbert_core/tests/test_thread_store.py halbert_core/tests/test_conversation_sqlite.py halbert_core/tests/test_session_affinity.py && git commit -m "feat(agents): thread-aware SQLite store with WAL and append-only messages

  conversations rows become threads (status, receipt, domains, entities,
  grace-window counters); messages gain turn/session/origin/status/blocks
  columns. Schema migrates in place via PRAGMA table_info + schema_version;
  messages_fts is rebuilt with porter unicode61 and rowid == messages.id.
  append_message is the only message write path (one transaction incl. FTS,
  None on failure); save() upserts the thread row only. FTS queries are
  tokenised and quoted so smb.conf / what's cannot abort a MATCH.
  compact_boundaries (opt-in LLM summaries, spec §8/§14) is created with no
  writers: compaction stays default-off in Plan A."
  ```

### Task A1b: Thread and turn readers on the store

**Files:**
- Modify: `halbert_core/halbert_core/agents/conversation_sqlite.py` (add module constants after `_MESSAGE_JSON_COLUMNS` (~line 76); add methods after `mark_in_progress_interrupted` and before the `# session_somatic_blocks (C1 link)` section (~line 553))
- Test: `halbert_core/tests/test_thread_store.py` (append)

- [ ] **Write the failing test** — append to `halbert_core/tests/test_thread_store.py`:

```python


# ---------------------------------------------------------------------------
# Thread + turn readers (A1b)
# ---------------------------------------------------------------------------

class TestThreadReaders:
    def test_create_get_update_thread(self, store):
        assert store.create_thread("t1", "Samba share") is True
        assert store.create_thread("t1", "dup") is False
        t = store.get_thread("t1")
        assert (t["thread_id"], t["id"], t["title"], t["status"], t["title_source"]) == ("t1", "t1", "Samba share", "open", "provisional")
        assert t["topic_domains"] == [] and t["entities_json"] == [] and t["recalled_json"] == [] and t["metadata"] == {}
        assert t["turn_count"] == 0 and t["message_count"] == 0
        assert store.update_thread("t1", status="paused", paused_at=10.0, topic_domains=["network"],
                                   entities_json=["samba"], stale=True, metadata={"k": 1}) is True
        t = store.get_thread("t1")
        assert (t["status"], t["paused_at"], t["topic_domains"], t["entities_json"], t["stale"], t["metadata"]) == ("paused", 10.0, ["network"], ["samba"], 1, {"k": 1})
        assert store.update_thread("t1", paused_at=None) is True and store.get_thread("t1")["paused_at"] is None
        assert store.update_thread("t1", bogus=1) is False
        assert store.update_thread("missing", status="open") is False
        assert store.get_thread("nope") is None

    def test_list_threads_and_current_open(self, store):
        for tid in ("a", "b", "c"):
            store.create_thread(tid, tid.upper())
        store.update_thread("a", status="closed", last_active=100.0)
        store.update_thread("b", status="paused", last_active=200.0)
        store.update_thread("c", status="open", last_active=300.0)
        assert [t["thread_id"] for t in store.list_threads()] == ["c", "b", "a"]
        assert [t["thread_id"] for t in store.list_threads(status="paused")] == ["b"]
        assert [t["thread_id"] for t in store.list_threads(status=["paused", "closed"])] == ["b", "a"]
        assert [t["thread_id"] for t in store.list_threads(limit=1)] == ["c"]
        assert store.current_open_thread()["thread_id"] == "c"
        store.update_thread("c", status="closed")
        assert store.current_open_thread() is None

    def test_recent_messages_filters_origin_and_orders(self, store):
        store.create_thread("t1", "T")
        for i in range(14):
            role = "user" if i % 2 == 0 else "assistant"
            store.append_message("t1", role, f"m{i}", origin="human" if role == "user" else "assistant")
        store.append_message("t1", "system", "from terminal", origin="terminal")
        rows = store.recent_messages("t1", limit=12)
        assert len(rows) == 12 and rows[0]["content"] == "m2" and rows[-1]["content"] == "m13"
        assert all(r["origin"] in ("human", "assistant") for r in rows)
        assert set(rows[0]) == {"role", "content", "timestamp", "origin"}
        assert store.recent_messages("nope") == []

    def test_list_messages_full_rows(self, store):
        store.create_thread("t1", "T")
        mid = store.append_message("t1", "assistant", "done", origin="assistant", turn_id="u1",
                                   blocks=[{"tool": "run_command", "args": {"command": "ls"}, "exit": 0}])
        rows = store.list_messages("t1")
        assert rows[0]["message_id"] == mid and rows[0]["thread_id"] == "t1"
        assert rows[0]["blocks"][0]["tool"] == "run_command" and rows[0]["turn_id"] == "u1"
        assert rows[0]["visible_in_timeline"] is True
        assert store.list_messages("t1", limit=0) == []

    def test_list_turns_groups_and_pages(self, store):
        store.create_thread("t1", "T")
        for i in range(5):
            store.append_message("t1", "user", f"q{i}", turn_id=f"turn-{i}", session_id=f"s{i}", timestamp=float(i * 10))
            store.append_message("t1", "assistant", f"a{i}", origin="assistant", turn_id=f"turn-{i}", session_id=f"s{i}",
                                 timestamp=float(i * 10 + 1),
                                 blocks=[{"tool": "run_command", "args": {"command": f"cmd{i}"}, "exit": 0}],
                                 terminal_block_ids=[f"term-{i}"], diff_proposals=[{"id": f"d{i}"}])
        store.append_message("t1", "system", "hidden", origin="system", turn_id="turn-4", visible_in_timeline=False)
        turns = store.list_turns(limit=50)
        assert [t["turn_id"] for t in turns] == [f"turn-{i}" for i in range(5)]
        last = turns[-1]
        assert last["user"]["content"] == "q4" and last["user"]["status"] == "complete"
        assert last["assistant"]["content"] == "a4"
        assert last["blocks"][0]["args"]["command"] == "cmd4" and last["terminal_block_ids"] == ["term-4"]
        assert last["diff_proposals"] == [{"id": "d4"}]
        assert last["timestamp"] == 40.0 and last["origin"] == "human" and last["thread_id"] == "t1"
        assert [t["turn_id"] for t in store.list_turns(limit=2)] == ["turn-3", "turn-4"]
        assert [t["turn_id"] for t in store.list_turns(before_turn_id="turn-3", limit=2)] == ["turn-1", "turn-2"]
        assert [t["turn_id"] for t in store.list_turns(around_turn_id="turn-2", limit=3)] == ["turn-1", "turn-2", "turn-3"]
        assert store.list_turns(before_turn_id="nope") == []
        assert store.list_turns(before_turn_id="turn-0") == []

    def test_list_turns_rows_without_turn_id(self, store):
        store.create_thread("t1", "T")
        mid = store.append_message("t1", "user", "legacy row")
        turns = store.list_turns()
        assert turns[0]["turn_id"] == f"m{mid}" and turns[0]["user"]["content"] == "legacy row"

    def test_mark_in_progress_interrupted(self, store):
        store.create_thread("t1", "T")
        store.append_message("t1", "user", "a", status="in_progress")
        store.append_message("t1", "user", "b", status="complete")
        assert store.mark_in_progress_interrupted() == 1
        assert [r["status"] for r in store.list_messages("t1")] == ["interrupted", "complete"]
        assert store.mark_in_progress_interrupted() == 0
```

- [ ] **Run it, expect failure:**
  `cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core && /Volumes/4TB-BAD/Halbert/.venv/bin/python -m pytest tests/test_thread_store.py -q -p no:cacheprovider`
  Expected: `7 failed, 13 passed` — every `TestThreadReaders` test fails (including `test_mark_in_progress_interrupted`, which calls `create_thread` first) with `AttributeError: 'SqliteConversationStore' object has no attribute 'create_thread'` (and `list_turns` / `recent_messages` / `list_messages`).

- [ ] **Implement.** In `conversation_sqlite.py`, insert this block immediately after the line `_MESSAGE_JSON_COLUMNS = {"blocks_json", "terminal_block_ids", "diff_proposals_json", "metadata"}`:

```python

_THREAD_JSON_LISTS = ("topic_domains", "entities_json", "recalled_json")
_THREAD_FLAGS = ("stale", "ephemeral", "unread")
_THREAD_UPDATABLE = {"title", "updated_at", "user_id", "metadata"} | {
    name for name, _ in _THREAD_COLUMNS
}

_THREAD_SELECT = """SELECT c.*,
    (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id) AS message_count,
    (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id AND m.role = 'user') AS turn_count
    FROM conversations c"""

_TURN_KEY = "COALESCE(turn_id, 'm' || id)"
_TURN_KEYS_SQL = (
    f"SELECT {_TURN_KEY} AS turn_key, MIN(id) AS first_id "
    "FROM messages WHERE visible_in_timeline = 1 GROUP BY turn_key"
)
```

  Then insert these methods into the class immediately after `mark_in_progress_interrupted` (before the `# session_somatic_blocks (C1 link)` comment block):

```python
    # ------------------------------------------------------------------
    # Threads
    # ------------------------------------------------------------------

    def create_thread(
        self,
        thread_id: str,
        title: str,
        *,
        status: str = "open",
        title_source: str = "provisional",
        created_at: Optional[float] = None,
        parent_thread_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> bool:
        """Insert a new thread row. False when the id exists or the write fails."""
        if self._conn is None:
            return False
        ts = float(created_at) if created_at is not None else time.time()
        try:
            with self._lock, self._conn:
                self._conn.execute(
                    """INSERT INTO conversations
                       (id, user_id, title, created_at, updated_at, metadata,
                        status, title_source, parent_thread_id)
                       VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?)""",
                    (thread_id, title, ts, ts, json.dumps(metadata or {}),
                     status, title_source, parent_thread_id),
                )
            return True
        except sqlite3.IntegrityError:
            logger.warning(f"create_thread: thread {thread_id} already exists")
            return False
        except Exception as e:
            logger.warning(f"create_thread failed: {e}")
            return False

    def update_thread(self, thread_id: str, **fields: Any) -> bool:
        """Update thread columns. Lists/dicts are JSON-encoded; flags coerced to 0/1."""
        if self._conn is None or not fields:
            return False
        sets: List[str] = []
        params: List[Any] = []
        for key, value in fields.items():
            if key not in _THREAD_UPDATABLE:
                logger.warning(f"update_thread: unknown field {key!r}")
                return False
            if key in _THREAD_JSON_LISTS:
                value = json.dumps(list(value or []))
            elif key == "metadata":
                value = json.dumps(value or {})
            elif key in _THREAD_FLAGS:
                value = 1 if value else 0
            sets.append(f"{key} = ?")
            params.append(value)
        params.append(thread_id)
        try:
            with self._lock, self._conn:
                cur = self._conn.execute(
                    f"UPDATE conversations SET {', '.join(sets)} WHERE id = ?", params
                )
                return cur.rowcount > 0
        except Exception as e:
            logger.warning(f"update_thread {thread_id} failed: {e}")
            return False

    @staticmethod
    def _row_to_thread(row: sqlite3.Row) -> Dict[str, Any]:
        d = dict(row)
        out: Dict[str, Any] = {"thread_id": d["id"]}
        out.update(d)
        for key in _THREAD_JSON_LISTS:
            out[key] = _loads(d.get(key), [])
        out["metadata"] = _loads(d.get("metadata"), {})
        return out

    def get_thread(self, thread_id: str) -> Optional[Dict[str, Any]]:
        if self._conn is None:
            return None
        try:
            with self._lock:
                row = self._conn.execute(
                    _THREAD_SELECT + " WHERE c.id = ?", (thread_id,)
                ).fetchone()
            return self._row_to_thread(row) if row is not None else None
        except Exception as e:
            logger.warning(f"get_thread {thread_id} failed: {e}")
            return None

    def list_threads(
        self, status: Optional[Any] = None, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Threads newest-activity-first, optionally filtered by status(es)."""
        if self._conn is None:
            return []
        statuses: List[str] = []
        if isinstance(status, str):
            statuses = [status]
        elif status:
            statuses = [str(s) for s in status]
        where = ""
        params: List[Any] = []
        if statuses:
            where = " WHERE c.status IN (" + ",".join("?" * len(statuses)) + ")"
            params.extend(statuses)
        params.append(limit)
        try:
            with self._lock:
                rows = self._conn.execute(
                    _THREAD_SELECT + where
                    + " ORDER BY COALESCE(c.last_active, c.updated_at) DESC, c.created_at DESC"
                    + " LIMIT ?",
                    params,
                ).fetchall()
            return [self._row_to_thread(r) for r in rows]
        except Exception as e:
            logger.warning(f"list_threads failed: {e}")
            return []

    def current_open_thread(self) -> Optional[Dict[str, Any]]:
        if self._conn is None:
            return None
        try:
            with self._lock:
                row = self._conn.execute(
                    _THREAD_SELECT
                    + " WHERE c.status = 'open' ORDER BY c.updated_at DESC LIMIT 1"
                ).fetchone()
            return self._row_to_thread(row) if row is not None else None
        except Exception as e:
            logger.warning(f"current_open_thread failed: {e}")
            return None

    # ------------------------------------------------------------------
    # Message readers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_message(row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "message_id": row["id"],
            "thread_id": row["conversation_id"],
            "role": row["role"],
            "content": row["content"],
            "timestamp": row["timestamp"],
            "origin": row["origin"],
            "status": row["status"],
            "turn_id": row["turn_id"],
            "session_id": row["session_id"],
            "blocks": _loads(row["blocks_json"], []),
            "terminal_block_ids": _loads(row["terminal_block_ids"], []),
            "diff_proposals": _loads(row["diff_proposals_json"], []),
            "metadata": _loads(row["metadata"], {}),
            "visible_in_timeline": bool(row["visible_in_timeline"]),
        }

    def list_messages(self, thread_id: str, *, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Every row of a thread, oldest-first, with decoded JSON columns."""
        if self._conn is None:
            return []
        sql = "SELECT * FROM messages WHERE conversation_id = ? ORDER BY id ASC"
        params: List[Any] = [thread_id]
        if limit is not None:
            sql += " LIMIT ?"
            params.append(int(limit))
        try:
            with self._lock:
                rows = self._conn.execute(sql, params).fetchall()
            return [self._row_to_message(r) for r in rows]
        except Exception as e:
            logger.warning(f"list_messages {thread_id} failed: {e}")
            return []

    def recent_messages(self, thread_id: str, limit: int = 12) -> List[Dict[str, Any]]:
        """Last ``limit`` human/assistant rows of a thread, oldest-first."""
        if self._conn is None:
            return []
        try:
            with self._lock:
                rows = self._conn.execute(
                    """SELECT role, content, timestamp, origin FROM messages
                       WHERE conversation_id = ? AND origin IN ('human', 'assistant')
                       ORDER BY id DESC LIMIT ?""",
                    (thread_id, int(limit)),
                ).fetchall()
            return [
                {"role": r["role"], "content": r["content"],
                 "timestamp": r["timestamp"], "origin": r["origin"]}
                for r in reversed(rows)
            ]
        except Exception as e:
            logger.warning(f"recent_messages {thread_id} failed: {e}")
            return []

    def _turn_first_id(self, turn_id: str) -> Optional[int]:
        row = self._conn.execute(
            f"SELECT MIN(id) FROM messages WHERE {_TURN_KEY} = ?", (turn_id,)
        ).fetchone()
        return int(row[0]) if row and row[0] is not None else None

    def list_turns(
        self,
        *,
        before_turn_id: Optional[str] = None,
        around_turn_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Timeline page: visible rows grouped by turn, newest-last.

        ``before_turn_id`` pages backwards (turns strictly older); ``around_turn_id``
        centres a page on a turn. Callers ask for ``limit + 1`` to learn ``has_more``.
        """
        if self._conn is None or limit <= 0:
            return []
        try:
            with self._lock:
                if before_turn_id is not None:
                    anchor = self._turn_first_id(before_turn_id)
                    if anchor is None:
                        return []
                    rows = self._conn.execute(
                        f"SELECT turn_key FROM ({_TURN_KEYS_SQL}) WHERE first_id < ? "
                        "ORDER BY first_id DESC LIMIT ?",
                        (anchor, limit),
                    ).fetchall()
                    keys = [r["turn_key"] for r in rows][::-1]
                elif around_turn_id is not None:
                    anchor = self._turn_first_id(around_turn_id)
                    if anchor is None:
                        return []
                    half = limit // 2
                    before = self._conn.execute(
                        f"SELECT turn_key FROM ({_TURN_KEYS_SQL}) WHERE first_id < ? "
                        "ORDER BY first_id DESC LIMIT ?",
                        (anchor, half),
                    ).fetchall()
                    after = self._conn.execute(
                        f"SELECT turn_key FROM ({_TURN_KEYS_SQL}) WHERE first_id >= ? "
                        "ORDER BY first_id ASC LIMIT ?",
                        (anchor, limit - half),
                    ).fetchall()
                    keys = [r["turn_key"] for r in before][::-1] + [r["turn_key"] for r in after]
                else:
                    rows = self._conn.execute(
                        f"SELECT turn_key FROM ({_TURN_KEYS_SQL}) "
                        "ORDER BY first_id DESC LIMIT ?",
                        (limit,),
                    ).fetchall()
                    keys = [r["turn_key"] for r in rows][::-1]
                if not keys:
                    return []
                placeholders = ",".join("?" * len(keys))
                msgs = self._conn.execute(
                    f"SELECT * FROM messages WHERE visible_in_timeline = 1 "
                    f"AND {_TURN_KEY} IN ({placeholders}) ORDER BY id ASC",
                    keys,
                ).fetchall()
            return self._group_turns(msgs)
        except Exception as e:
            logger.warning(f"list_turns failed: {e}")
            return []

    def _group_turns(self, rows: List[sqlite3.Row]) -> List[Dict[str, Any]]:
        turns: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            m = self._row_to_message(row)
            key = m["turn_id"] or f"m{m['message_id']}"
            turn = turns.get(key)
            if turn is None:
                turn = turns[key] = {
                    "turn_id": key,
                    "thread_id": m["thread_id"],
                    "timestamp": m["timestamp"],
                    "user": None,
                    "assistant": None,
                    "blocks": [],
                    "terminal_block_ids": [],
                    "diff_proposals": [],
                    "origin": m["origin"],
                }
            slot = {
                "message_id": m["message_id"],
                "content": m["content"],
                "timestamp": m["timestamp"],
                "status": m["status"],
            }
            if m["role"] == "user":
                if turn["user"] is None:
                    turn["user"] = slot
            elif turn["assistant"] is None:
                turn["assistant"] = slot
            turn["blocks"].extend(m["blocks"])
            for tid in m["terminal_block_ids"]:
                if tid not in turn["terminal_block_ids"]:
                    turn["terminal_block_ids"].append(tid)
            turn["diff_proposals"].extend(m["diff_proposals"])
        return list(turns.values())

```

- [ ] **Run tests, expect PASS:**
  `cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core && /Volumes/4TB-BAD/Halbert/.venv/bin/python -m pytest tests/test_thread_store.py tests/test_conversation_sqlite.py tests/test_session_affinity.py -q -p no:cacheprovider`
  Expected: `53 passed`.

- [ ] **Commit:**
  ```
  cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation && git add halbert_core/halbert_core/agents/conversation_sqlite.py halbert_core/tests/test_thread_store.py && git commit -m "feat(agents): thread and turn readers on the SQLite store

  create_thread/update_thread/get_thread/list_threads/current_open_thread,
  list_messages/recent_messages, and list_turns (timeline paging grouped by
  turn_id, newest-last, visible rows only)."
  ```

### Task A2: Deterministic receipts and titles

**Files:**
- Create: `halbert_core/halbert_core/agents/receipt.py`
- Test: `halbert_core/tests/test_receipt.py` (new)

- [ ] **Write the failing test** — create `halbert_core/tests/test_receipt.py`:

```python
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for agents/receipt.py — deterministic thread receipts and titles."""

from datetime import datetime

from halbert_core.agents.receipt import (
    build_receipt, first_sentence, provisional_title, receipt_one_liner, refined_title,
)

T0 = datetime(2026, 7, 14, 12, 0).timestamp()


def _thread(**kw):
    base = {"thread_id": "t1", "title": "Samba media share", "topic_domains": ["network", "config"],
            "entities_json": ["samba", "/etc/samba/smb.conf", "share"], "turn_count": 2}
    base.update(kw)
    return base


def _messages():
    return [
        {"message_id": 1, "role": "user", "origin": "human", "turn_id": "turn-1", "timestamp": T0,
         "content": "add a samba share for the media folder\nsecond line", "blocks": [], "diff_proposals": []},
        {"message_id": 2, "role": "assistant", "origin": "assistant", "turn_id": "turn-1", "timestamp": T0 + 60,
         "content": "Added [media] to smb.conf. Restarting smbd now.",
         "blocks": [{"tool": "run_command", "args": {"command": "testparm"}, "exit": 0},
                    {"tool": "write_file", "args": {"path": "/etc/samba/smb.conf"}, "exit": 0},
                    {"tool": "run_command", "args": {"command": "systemctl restart smbd"}, "result": {"exit_code": 0}}],
         "diff_proposals": []},
        {"message_id": 3, "role": "user", "origin": "human", "turn_id": "turn-2", "timestamp": T0 + 3600,
         "content": "did it mount?", "blocks": [], "diff_proposals": []},
        {"message_id": 4, "role": "assistant", "origin": "assistant", "turn_id": "turn-2", "timestamp": T0 + 3660,
         "content": "The share mounts from the laptop at //nas/media (v3.1 client). Next, verify guest access is off once the config reloads.",
         "blocks": [], "diff_proposals": [{"id": "d1", "path": "/etc/fstab"}]},
    ]


class TestBuildReceipt:
    def test_sections_in_order(self):
        r = build_receipt(_thread(), _messages())
        assert [line.split(":")[0] for line in r.splitlines()] == [
            "Title", "When", "Domains", "Entities", "Started with", "Last said",
            "Commands", "Files written", "Open loop"]

    def test_lines(self):
        lines = build_receipt(_thread(), _messages()).splitlines()
        assert lines[0] == "Title: Samba media share"
        assert lines[1] == "When: 2026-07-14..2026-07-14 · 2 turns"
        assert lines[2] == "Domains: network, config"
        assert lines[3] == "Entities: samba, /etc/samba/smb.conf, share"
        assert lines[4] == "Started with: add a samba share for the media folder second line"
        assert lines[5] == "Last said: The share mounts from the laptop at //nas/media (v3.1 client)."
        assert lines[6] == "Commands: testparm (exit 0); systemctl restart smbd (exit 0)"
        assert lines[7] == "Files written: /etc/samba/smb.conf; /etc/fstab"
        assert lines[8] == "Open loop: Next, verify guest access is off once the config reloads."

    def test_open_loop_none_recorded(self):
        msgs = _messages()
        msgs[-1]["content"] = "All done. Nothing else pending."
        assert build_receipt(_thread(), msgs).splitlines()[-1] == "Open loop: none recorded"

    def test_commands_capped_at_eight_and_unknown_exit(self):
        msgs = _messages()
        msgs[1]["blocks"] = [{"tool": "run_command", "args": {"command": f"cmd{i}"}} for i in range(10)]
        line = build_receipt(_thread(), msgs).splitlines()[6]
        assert line.startswith("Commands: cmd2 (exit ?); ") and line.count("(exit ?)") == 8

    def test_max_chars(self):
        msgs = _messages()
        msgs[0]["content"] = "x" * 400
        msgs[-1]["content"] = "y" * 900 + ". Then " + "z" * 900
        r = build_receipt(_thread(), msgs, max_chars=600)
        assert len(r) == 600 and r.endswith("…")

    def test_empty_thread(self):
        r = build_receipt(_thread(turn_count=0, topic_domains=[], entities_json=[]), [])
        assert "When: unknown" in r and "Domains: none" in r and "Started with: none" in r and "Last said: none" in r
        assert r.endswith("Commands: none\nFiles written: none\nOpen loop: none recorded")

    def test_first_sentence_never_splits_on_bare_dot(self):
        assert first_sentence("Edited smb.conf and fstab. Done.") == "Edited smb.conf and fstab."


class TestTitles:
    def test_provisional(self):
        assert provisional_title("  Add a Samba share for the media folder!!\nmore") == "Add a Samba share for the media folder"
        assert provisional_title("") == "New subject"
        assert provisional_title("x" * 80) == "x" * 60
        t = provisional_title("please configure the wireguard vpn tunnel for the laptop and phone so both work")
        assert t == "please configure the wireguard vpn tunnel for the laptop"

    def test_refined(self):
        assert refined_title(["samba", "share"], "add a samba share for the media folder") == "Add samba"
        assert refined_title(["/etc/fstab", "nfs"], "mount the nfs export") == "Mount nfs"
        assert refined_title(["zfs"], "why is this slow") == "Zfs"
        assert refined_title([], "hello there") == "hello there"

    def test_one_liner(self):
        r = build_receipt(_thread(), _messages())
        assert receipt_one_liner(r) == (
            "Started with: add a samba share for the media folder second line "
            "Last said: The share mounts from the laptop at //nas/media (v3.1 client). "
            "Open loop: Next, verify guest access is off once the config reloads.")
```

- [ ] **Run it, expect failure:**
  `cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core && /Volumes/4TB-BAD/Halbert/.venv/bin/python -m pytest tests/test_receipt.py -q -p no:cacheprovider`
  Expected: `ModuleNotFoundError: No module named 'halbert_core.agents.receipt'`.

- [ ] **Create `halbert_core/halbert_core/agents/receipt.py`:**

```python
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Deterministic thread receipts and titles (spec §3 "Receipt", §5 "Titles").

A receipt is the zero-cost, extractive summary of a thread: nine labelled
single-line sections in a fixed order, ≤ ``max_chars``. Recall returns
receipts and snippets, never transcripts.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

__all__ = [
    "build_receipt",
    "provisional_title",
    "refined_title",
    "receipt_one_liner",
    "split_sentences",
    "first_sentence",
]

# Never split on "." alone: a sentence ends only at .!? followed by whitespace.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_OPEN_LOOP_RE = re.compile(r"\b(next|try|check|verify|then|after|once)\b", re.IGNORECASE)
_WS_RE = re.compile(r"\s+")
_WRITE_TOOLS = ("write_file", "edit_file", "apply_diff", "diff", "create_file", "append_file")
_TITLE_VERBS = (
    "set up", "back up", "add", "configure", "setup", "fix", "install", "remove",
    "restart", "check", "mount", "enable", "disable", "update", "upgrade", "migrate",
    "debug", "clean", "backup", "rotate", "tune", "secure", "monitor", "move", "create",
    "delete", "reset", "expand", "replace", "test", "write", "rename", "free", "shrink",
    "grow", "swap", "share", "connect", "deploy", "build", "sync",
)
_TITLE_MAX = 60


def _date(ts: Any) -> str:
    try:
        return datetime.fromtimestamp(float(ts)).date().isoformat()
    except Exception:
        return "unknown"


def _clip(text: Any, limit: int) -> str:
    flat = _WS_RE.sub(" ", str(text or "")).strip()
    if len(flat) <= limit:
        return flat
    return flat[: limit - 1].rstrip() + "…"


def split_sentences(text: str) -> List[str]:
    flat = _WS_RE.sub(" ", (text or "")).strip()
    return [s for s in _SENTENCE_SPLIT_RE.split(flat) if s] if flat else []


def first_sentence(text: str, limit: int = 200) -> str:
    sentences = split_sentences(text)
    return _clip(sentences[0], limit) if sentences else ""


def _exit_of(block: Dict[str, Any]) -> str:
    code = block.get("exit")
    if code is None:
        result = block.get("result")
        if isinstance(result, dict):
            code = result.get("exit_code", result.get("exit"))
    return str(code) if code is not None else "?"


def _tool_name(block: Dict[str, Any]) -> str:
    return str(block.get("tool") or block.get("name") or "")


def _args_of(block: Dict[str, Any]) -> Dict[str, Any]:
    args = block.get("args")
    if args is None:
        args = block.get("input")
    return args if isinstance(args, dict) else {}


def _command_lines(blocks: Sequence[Dict[str, Any]]) -> List[str]:
    lines: List[str] = []
    for block in blocks:
        if not isinstance(block, dict) or _tool_name(block) != "run_command":
            continue
        cmd = _args_of(block).get("command")
        if not cmd:
            continue
        lines.append(f"{_clip(cmd, 80)} (exit {_exit_of(block)})")
    return lines


def _file_lines(blocks: Sequence[Dict[str, Any]], diffs: Sequence[Dict[str, Any]]) -> List[str]:
    paths: List[str] = []

    def add(path: Any) -> None:
        if path and str(path) not in paths:
            paths.append(str(path))

    for block in blocks:
        if isinstance(block, dict) and _tool_name(block) in _WRITE_TOOLS:
            args = _args_of(block)
            add(args.get("path") or args.get("file_path") or args.get("file"))
    for diff in diffs:
        if isinstance(diff, dict):
            add(diff.get("path") or diff.get("file_path") or diff.get("file"))
    return paths


def _open_loop(text: str) -> str:
    for sentence in reversed(split_sentences(text)):
        if _OPEN_LOOP_RE.search(sentence):
            return _clip(sentence, 200)
    return "none recorded"


def build_receipt(thread: Dict[str, Any], messages: List[Dict[str, Any]], *, max_chars: int = 1500) -> str:
    """Render the nine-line receipt for ``thread`` from its stored ``messages``.

    ``messages`` rows are ``SqliteConversationStore.list_messages`` dicts
    (role, content, timestamp, origin, turn_id, blocks, diff_proposals).
    """
    title = thread.get("title") or "Untitled"
    human = [m for m in messages if m.get("role") == "user" and (m.get("origin") or "human") == "human"]
    assistant = [m for m in messages if m.get("role") == "assistant"]
    stamps = [float(m["timestamp"]) for m in messages if m.get("timestamp") is not None]
    turn_keys = {
        m.get("turn_id") or f"m{m.get('message_id', i)}"
        for i, m in enumerate(messages) if m.get("role") == "user"
    }
    n_turns = len(turn_keys) or int(thread.get("turn_count") or 0)
    when = f"{_date(min(stamps))}..{_date(max(stamps))} · {n_turns} turns" if stamps else "unknown"
    domains = ", ".join(thread.get("topic_domains") or []) or "none"
    entities = ", ".join(thread.get("entities_json") or []) or "none"
    started = _clip(human[0].get("content"), 160) if human else "none"
    last_said = first_sentence(assistant[-1].get("content") or "", 200) if assistant else "none"
    blocks: List[Dict[str, Any]] = []
    diffs: List[Dict[str, Any]] = []
    for m in messages:
        blocks.extend(m.get("blocks") or [])
        diffs.extend(m.get("diff_proposals") or [])
    commands = "; ".join(_command_lines(blocks)[-8:]) or "none"
    files = "; ".join(_file_lines(blocks, diffs)[-8:]) or "none"
    open_loop = _open_loop(assistant[-1].get("content") or "") if assistant else "none recorded"
    lines = [
        f"Title: {title}",
        f"When: {when}",
        f"Domains: {domains}",
        f"Entities: {entities}",
        f"Started with: {started}",
        f"Last said: {last_said or 'none'}",
        f"Commands: {commands}",
        f"Files written: {files}",
        f"Open loop: {open_loop}",
    ]
    text = "\n".join(lines)
    if len(text) > max_chars:
        text = text[: max_chars - 1].rstrip() + "…"
    return text


def receipt_one_liner(receipt: str) -> str:
    """The three lines the hint quotes: Started with / Last said / Open loop."""
    keep = ("Started with:", "Last said:", "Open loop:")
    parts = [ln.strip() for ln in (receipt or "").splitlines() if ln.startswith(keep)]
    return " ".join(parts)


def provisional_title(first_user_content: str) -> str:
    """First line of the first user message, ≤ 60 chars, trailing punctuation stripped."""
    lines = [ln for ln in (first_user_content or "").splitlines() if ln.strip()]
    line = _WS_RE.sub(" ", lines[0]).strip() if lines else ""
    if len(line) > _TITLE_MAX:
        cut = line[:_TITLE_MAX]
        line = cut.rsplit(" ", 1)[0] if " " in cut else cut
    line = line.rstrip(" .!?:;,…")
    return line or "New subject"


def refined_title(receipt_entities: List[str], first_user_content: str) -> str:
    """Top entity + verb ("Add samba"); falls back to the provisional title."""
    entity: Optional[str] = next(
        (e for e in receipt_entities if e and not e.startswith(("/", "~", "."))), None
    ) or (receipt_entities[0] if receipt_entities else None)
    if not entity:
        return provisional_title(first_user_content)
    text = (first_user_content or "").lower()
    verb = next(
        (v for v in _TITLE_VERBS if re.search(r"\b" + re.escape(v) + r"\b", text)), None
    )
    title = f"{verb} {entity}" if verb else str(entity)
    title = title[0].upper() + title[1:]
    return title[:_TITLE_MAX]
```

- [ ] **Run tests, expect PASS:**
  `cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core && /Volumes/4TB-BAD/Halbert/.venv/bin/python -m pytest tests/test_receipt.py -q -p no:cacheprovider`
  Expected: `10 passed`.

- [ ] **Commit:**
  ```
  cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation && git add halbert_core/halbert_core/agents/receipt.py halbert_core/tests/test_receipt.py && git commit -m "feat(agents): deterministic thread receipts and titles

  build_receipt renders nine labelled lines (title, when, domains, entities,
  started with, last said, commands with exit codes, files written, open
  loop) capped at 1500 chars; provisional_title/refined_title give threads
  server-side names."
  ```

### Task A3: Receipt search and receipts_fts upserts

**Files:**
- Modify: `halbert_core/halbert_core/agents/conversation_sqlite.py` (add two helpers after `_fts_query` (~line 110); add four methods after `_group_turns`, before the `# session_somatic_blocks (C1 link)` section)
- Test: `halbert_core/tests/test_thread_store.py` (append)

- [ ] **Write the failing test** — append to `halbert_core/tests/test_thread_store.py`:

```python


# ---------------------------------------------------------------------------
# Receipts: upsert_receipt / search_receipts / search_snippets (A3)
# ---------------------------------------------------------------------------

class TestReceipts:
    def _seed(self, store):
        store.create_thread("samba", "Samba media share")
        store.update_thread("samba", status="closed", last_active=100.0)
        assert store.upsert_receipt("samba", "Samba media share",
            "Title: Samba media share\nEntities: samba, share, /etc/samba/smb.conf\n"
            "Started with: add a samba share for the media folder\nCommands: testparm (exit 0)") is True
        store.create_thread("nas", "NAS disk swap")
        store.update_thread("nas", status="paused", last_active=200.0)
        assert store.upsert_receipt("nas", "NAS disk swap",
            "Title: NAS disk swap\nEntities: zfs, nvme\nStarted with: swap the failing nvme in the zfs pool") is True

    def test_search_receipts_scores_and_terms(self, store):
        self._seed(store)
        hits = store.search_receipts("the media share on samba")
        assert [h["thread_id"] for h in hits] == ["samba"]
        hit = hits[0]
        assert hit["score"] == 1.0 and set(hit["match_terms"]) == {"media", "share", "samba"}
        assert hit["status"] == "closed" and hit["last_active"] == 100.0 and hit["title"] == "Samba media share"
        assert hit["snippet"] == "Title: Samba media share"

    def test_partial_match_scores_by_terms(self, store):
        self._seed(store)
        hits = store.search_receipts("what's the zfs pool resilver doing?")
        assert hits[0]["thread_id"] == "nas" and hits[0]["score"] == 0.667 and hits[0]["match_terms"] == ["zfs", "pool"]

    def test_punctuation_queries_do_not_abort(self, store):
        self._seed(store)
        assert store.search_receipts("smb.conf")[0]["thread_id"] == "samba"
        assert store.search_receipts("what's") == []
        assert store.search_receipts("") == []

    def test_exclude_and_limit(self, store):
        self._seed(store)
        assert [h["thread_id"] for h in store.search_receipts("samba zfs", exclude_thread_id="samba")] == ["nas"]
        assert len(store.search_receipts("samba zfs", limit=1)) == 1
        assert {h["thread_id"] for h in store.search_receipts("samba zfs")} == {"samba", "nas"}

    def test_title_like_fallback_when_fts_row_missing(self, store):
        self._seed(store)
        store._conn.execute("DELETE FROM receipts_fts")
        store._conn.commit()
        hits = store.search_receipts("nas")
        assert [h["thread_id"] for h in hits] == ["nas"] and hits[0]["match_terms"] == ["nas"]

    def test_upsert_replaces_fts_row_and_updates_columns(self, store):
        self._seed(store)
        assert store.upsert_receipt("nas", "NAS disk swap", "Title: NAS disk swap\nEntities: btrfs") is True
        assert store._conn.execute("SELECT COUNT(*) FROM receipts_fts WHERE thread_id = 'nas'").fetchone()[0] == 1
        assert store.search_receipts("btrfs")[0]["thread_id"] == "nas"
        assert store.search_receipts("nvme") == []
        t = store.get_thread("nas")
        assert t["receipt"].endswith("btrfs") and t["receipt_updated_at"] is not None

    def test_upsert_unknown_thread_is_false(self, store):
        assert store.upsert_receipt("nope", "x", "y") is False

    def test_ephemeral_and_merged_excluded(self, store):
        self._seed(store)
        store.update_thread("samba", ephemeral=True)
        assert store.search_receipts("samba") == []
        store.update_thread("samba", ephemeral=False, status="merged")
        assert store.search_receipts("samba") == []

    def test_search_snippets(self, store):
        store.create_thread("t", "T")
        store.append_message("t", "user", "edit /etc/samba/smb.conf for the media share")
        store.append_message("t", "assistant", "restarted smbd", origin="assistant")
        snips = store.search_snippets("t", "smb.conf media")
        assert len(snips) == 1 and "smb.conf" in snips[0]
        assert store.search_snippets("t", "what's") == []
        assert store.search_snippets("other", "media") == []
```

- [ ] **Run it, expect failure:**
  `cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core && /Volumes/4TB-BAD/Halbert/.venv/bin/python -m pytest tests/test_thread_store.py -q -p no:cacheprovider`
  Expected: `9 failed, 20 passed` — `AttributeError: 'SqliteConversationStore' object has no attribute 'upsert_receipt'` / `'search_receipts'` / `'search_snippets'`.

- [ ] **Implement.** In `conversation_sqlite.py`, insert immediately after the `_fts_query` function (before `def _loads`):

```python
def _term_hits(terms: Sequence[str], haystack: str) -> List[str]:
    """Terms whose crude stem (drop the last letter past 4 chars) starts a word in ``haystack``."""
    out: List[str] = []
    for t in terms:
        stem = t[:-1] if len(t) > 4 else t
        if re.search(r"\b" + re.escape(stem), haystack):
            out.append(t)
    return out


def _receipt_snippet(receipt: str, matched: Sequence[str]) -> str:
    lines = [ln for ln in (receipt or "").splitlines() if ln.strip()]
    for ln in lines:
        low = ln.lower()
        if any((t[:-1] if len(t) > 4 else t) in low for t in matched):
            return ln[:200]
    return lines[0][:200] if lines else ""


```

  Then insert these methods into the class immediately after `_group_turns` (before the `# session_somatic_blocks (C1 link)` comment block):

```python
    # ------------------------------------------------------------------
    # Receipts (FTS over receipts, not raw messages)
    # ------------------------------------------------------------------

    def upsert_receipt(self, thread_id: str, title: str, receipt: str) -> bool:
        """Store a thread's receipt and replace its ``receipts_fts`` row."""
        if self._conn is None:
            return False
        try:
            with self._lock, self._conn:
                cur = self._conn.execute(
                    "UPDATE conversations SET receipt = ?, receipt_updated_at = ? WHERE id = ?",
                    (receipt or "", time.time(), thread_id),
                )
                if cur.rowcount == 0:
                    return False
                if self._fts_ok:
                    self._conn.execute(
                        "DELETE FROM receipts_fts WHERE thread_id = ?", (thread_id,)
                    )
                    self._conn.execute(
                        "INSERT INTO receipts_fts(thread_id, title, receipt) VALUES (?, ?, ?)",
                        (thread_id, title or "", receipt or ""),
                    )
            return True
        except Exception as e:
            logger.warning(f"upsert_receipt {thread_id} failed: {e}")
            return False

    @staticmethod
    def _receipt_hit(row: sqlite3.Row, terms: Sequence[str]) -> Dict[str, Any]:
        haystack = f"{row['title'] or ''} {row['receipt'] or ''}".lower()
        matched = _term_hits(terms, haystack)
        # Two topical terms are enough for a full score; a single hit on a
        # one-word query also scores 1.0. Unverifiable FTS hits keep 0.25.
        score = min(1.0, len(matched) / max(1, min(len(terms), 3))) if matched else 0.25
        return {
            "thread_id": row["thread_id"],
            "title": row["title"] or "",
            "score": round(score, 3),
            "match_terms": matched,
            "snippet": _receipt_snippet(row["receipt"] or "", matched),
            "last_active": row["last_active"],
            "status": row["status"],
        }

    def search_receipts(
        self, query: str, *, exclude_thread_id: Optional[str] = None, limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Rank threads by receipt/title relevance to ``query``.

        Query terms are quoted and OR-joined; the MATCH runs in its own try so
        an FTS failure degrades to the title LIKE pass instead of aborting.
        """
        if self._conn is None or not query:
            return []
        terms = _fts_terms(query)
        if not terms:
            return []
        hits: Dict[str, Dict[str, Any]] = {}
        if self._fts_ok:
            try:
                with self._lock:
                    rows = self._conn.execute(
                        """SELECT r.thread_id, r.title, r.receipt,
                                  c.last_active, c.status, c.created_at
                           FROM receipts_fts r JOIN conversations c ON c.id = r.thread_id
                           WHERE receipts_fts MATCH ? AND c.status != 'merged'
                             AND c.ephemeral = 0 AND (? IS NULL OR r.thread_id != ?)
                           ORDER BY bm25(receipts_fts) LIMIT ?""",
                        (_fts_query(terms), exclude_thread_id, exclude_thread_id,
                         max(limit * 4, 20)),
                    ).fetchall()
                for r in rows:
                    hits[r["thread_id"]] = self._receipt_hit(r, terms)
            except Exception as e:
                logger.warning(f"receipt FTS search failed (LIKE fallback only): {e}")
        try:
            like_rows: List[sqlite3.Row] = []
            with self._lock:
                for term in terms[:6]:
                    like_rows.extend(self._conn.execute(
                        """SELECT id AS thread_id, title, receipt, last_active, status, created_at
                           FROM conversations
                           WHERE lower(title) LIKE ? AND status != 'merged' AND ephemeral = 0
                             AND (? IS NULL OR id != ?)
                           LIMIT ?""",
                        (f"%{term}%", exclude_thread_id, exclude_thread_id, limit),
                    ).fetchall())
            for r in like_rows:
                if r["thread_id"] not in hits:
                    hits[r["thread_id"]] = self._receipt_hit(r, terms)
        except Exception as e:
            logger.warning(f"receipt title search failed: {e}")
        ranked = sorted(
            hits.values(), key=lambda h: (-h["score"], -(h["last_active"] or 0.0))
        )
        return ranked[:limit]

    def search_snippets(self, thread_id: str, query: str, limit: int = 5) -> List[str]:
        """FTS snippets of one thread's messages matching ``query`` (best first)."""
        if self._conn is None or not self._fts_ok or not query:
            return []
        terms = _fts_terms(query)
        if not terms:
            return []
        try:
            with self._lock:
                rows = self._conn.execute(
                    """SELECT snippet(messages_fts, 1, '', '', '…', 12) AS snip
                       FROM messages_fts
                       WHERE conversation_id = ? AND messages_fts MATCH ?
                       ORDER BY bm25(messages_fts) LIMIT ?""",
                    (thread_id, _fts_query(terms), int(limit)),
                ).fetchall()
            return [r["snip"] for r in rows if r["snip"]]
        except Exception as e:
            logger.warning(f"search_snippets {thread_id} failed: {e}")
            return []

```

- [ ] **Run tests, expect PASS:**
  `cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core && /Volumes/4TB-BAD/Halbert/.venv/bin/python -m pytest tests/test_thread_store.py tests/test_conversation_sqlite.py tests/test_session_affinity.py -q -p no:cacheprovider`
  Expected: `62 passed`.

- [ ] **Commit:**
  ```
  cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation && git add halbert_core/halbert_core/agents/conversation_sqlite.py halbert_core/tests/test_thread_store.py && git commit -m "feat(agents): receipt search over receipts_fts with LIKE fallback

  upsert_receipt keeps conversations.receipt and the receipts_fts row in
  step; search_receipts tokenises + quotes the query, runs MATCH in its own
  try, scores hits by matched topical terms (2 of 3 = 1.0), and falls back
  to title LIKE; search_snippets returns per-thread FTS snippets for recall."
  ```

### Task A4: Entity aliases, canonical entities, and thread cues in intake signals

**Files:**
- Modify: `halbert_core/halbert_core/intake/signals.py` (lines 10–14 imports; 37–77 domain keywords/file-path regex; 104–120 dataclass; 153–160 analysis)
- Test: `halbert_core/tests/test_intake_signals.py` (line 11 import; append two classes)

- [ ] **Write the failing test.** In `halbert_core/tests/test_intake_signals.py` replace line 11 `from halbert_core.intake.signals import MessageSignals, analyze_message` with:
  ```python
  from halbert_core.intake.signals import (
      ENTITY_ALIASES, MessageSignals, analyze_message, canonical_entities,
  )
  ```
  and append at the end of the file:

```python


# ── Entities + thread cues (Plan A, A4) ──────────────────────────

class TestCanonicalEntities:
    def test_cifs_maps_to_samba(self):
        ents = canonical_entities("the cifs mount is broken")
        assert "samba" in ents and "cifs" not in ents and "mount" in ents

    def test_phrase_alias(self):
        ents = canonical_entities("set up a windows share for the scanner")
        assert {"samba", "share", "scanner"} <= ents

    def test_smb_conf_token_and_path(self):
        assert {"samba", "/etc/samba/smb.conf"} <= canonical_entities("edit /etc/samba/smb.conf please.")
        assert "samba" in canonical_entities("look in smb.conf.")

    def test_generic_keywords_excluded(self):
        assert canonical_entities("check the status of the service") == set()

    def test_vpn_maps_to_wireguard(self):
        assert canonical_entities("is the vpn up?") == {"wireguard"}

    def test_empty(self):
        assert canonical_entities("") == set()

    def test_alias_table_shape(self):
        assert ENTITY_ALIASES["zpool"] == "zfs" and ENTITY_ALIASES["letsencrypt"] == "tls"


class TestThreadCues:
    def test_past_reference(self):
        assert analyze_message("same as we did for the media share last week").past_reference is True
        assert analyze_message("remember when the pool degraded?").past_reference is True
        assert analyze_message("add a share").past_reference is False

    def test_anaphora_phrases(self):
        assert analyze_message("so, did that work?").anaphora is True
        assert analyze_message("any luck?").anaphora is True
        assert analyze_message("ok is it working now?").anaphora is True

    def test_bare_it_without_signals(self):
        assert analyze_message("it still fails").anaphora is True
        assert analyze_message("that again please").anaphora is True

    def test_bare_it_with_entity_is_not_anaphora(self):
        assert analyze_message("it is the samba share again").anaphora is False
        assert analyze_message("it won't mount the disk").anaphora is False

    def test_signals_carry_entities(self):
        s = analyze_message("mount the cifs share")
        assert {"samba", "share", "mount"} <= s.entities and "network" in s.detected_domains

    def test_new_domain_keywords(self):
        assert "network" in analyze_message("restart samba").detected_domains
        assert "storage" in analyze_message("zpool status").detected_domains
        assert "service" in analyze_message("edit the crontab").detected_domains
        assert "network" in analyze_message("is the vpn up").detected_domains
        s = analyze_message("the scanner is offline")
        assert "network" in s.detected_domains and "scanner" in s.entities

    def test_defaults(self):
        s = MessageSignals()
        assert s.entities == set() and s.past_reference is False and s.anaphora is False
```

- [ ] **Run it, expect failure:**
  `cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core && /Volumes/4TB-BAD/Halbert/.venv/bin/python -m pytest tests/test_intake_signals.py -q -p no:cacheprovider`
  Expected: `ImportError: cannot import name 'ENTITY_ALIASES' from 'halbert_core.intake.signals'`.

- [ ] **Implement** — edit `halbert_core/halbert_core/intake/signals.py`:

  1. Line 14: `from typing import List` → `from typing import List, Set`.
  2. In `_DOMAIN_KEYWORDS`: `"storage"` list — change `"hdd", "space", "full", "lvm", "df",` to `"hdd", "space", "full", "lvm", "df", "zpool", "smart", "smartctl",` (`zfs` is already present); `"service"` list — change `"apache", "docker", "container", "journalctl",` to `"apache", "docker", "container", "journalctl", "cron", "crontab",` (`systemd`/`journalctl` already present); `"network"` list — change `"iptables", "nftables", "netstat", "ss",` to
     ```python
             "iptables", "nftables", "netstat", "ss", "samba", "smb", "nfs",
             "cups", "wireguard", "vpn", "share", "scanner",
     ```
  3. Immediately after the `_FILE_PATH_RE = re.compile(...)` statement (line 77) insert:

```python

# ── Entity canonicalisation (spec §6 alias table) ────────────────

#: Surface form -> canonical entity. Applied at index and query time.
ENTITY_ALIASES: dict[str, str] = {
    "smb": "samba",
    "cifs": "samba",
    "smbd": "samba",
    "nmbd": "samba",
    "file share": "samba",
    "windows share": "samba",
    "exports": "nfs",
    "wg": "wireguard",
    "vpn": "wireguard",
    "certbot": "tls",
    "letsencrypt": "tls",
    "acme": "tls",
    "zpool": "zfs",
    "smb.conf": "samba",
}

_ALIAS_PHRASES = [
    (re.compile(r"\b" + re.escape(k) + r"\b"), v)
    for k, v in ENTITY_ALIASES.items() if " " in k
]
_ENTITY_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9._\-]*")

# Domain keywords too generic to count as entities for overlap scoring.
_GENERIC_KEYWORDS = frozenset({
    "etc", "df", "ss", "ip", "port", "full", "space", "status", "running", "start",
    "stop", "restart", "failed", "enabled", "process", "key", "root", "env", "conf",
    "config", "configure", "configuration", "settings", "json", "yaml", "toml", "ini",
    "environment", "profile", "drive", "volume", "storage", "service", "daemon",
    "network", "internet", "connection", "security", "permission", "password",
    "audit", "auth", "tar", "recovery", "archive",
})

# ── Thread cues (spec §4.2) ──────────────────────────────────────

PAST_REF_RE = re.compile(
    r"\b(we (discussed|did|set ?up|talked about|configured)"
    r"|last (week|month|time|tuesday|monday|wednesday|thursday|friday|saturday|sunday)"
    r"|remember when|back when|earlier|the other day"
    r"|(a )?(few )?(weeks?|days?|months?) ago|as we did|like (we did|before))\b",
    re.IGNORECASE,
)

ANAPHORA_RE = re.compile(
    r"^\s*(?:so|ok|okay|and|well)?,?\s*"
    r"(?P<phrase>did (?:that|it) work|any luck|is (?:that|it) (?:done|working|fixed)"
    r"|still (?:broken|failing|not working)|what happened with (?:that|it)"
    r"|how did (?:that|it) go)\b"
    r"|^\s*(?P<bare>that|it)\b",
    re.IGNORECASE,
)
```

  4. In `MessageSignals`, after `has_images: bool = False` add:
```python
    # Thread cues (spec §4.2 / §6)
    entities: Set[str] = field(default_factory=set)
    past_reference: bool = False
    anaphora: bool = False
```

  5. Immediately before the `# ── Analysis ──…` comment (above `def analyze_message`) insert:

```python
# ── Entities ─────────────────────────────────────────────────────

def canonical_entities(text: str) -> set[str]:
    """Canonical entities of ``text``: alias hits, non-generic domain keywords, file paths."""
    if not text:
        return set()
    lower = text.lower()
    out: set[str] = set()
    for tok in _ENTITY_TOKEN_RE.findall(lower):
        alias = ENTITY_ALIASES.get(tok.strip("._-"))
        if alias:
            out.add(alias)
    for pattern, alias in _ALIAS_PHRASES:
        if pattern.search(lower):
            out.add(alias)
    for pattern in _DOMAIN_PATTERNS.values():
        for m in pattern.finditer(text):
            kw = m.group(1).lower()
            if kw in _GENERIC_KEYWORDS:
                continue
            out.add(ENTITY_ALIASES.get(kw, kw))
    for path in _FILE_PATH_RE.findall(text):
        path = path.rstrip(".,;:")
        if len(path) > 1:
            out.add(path)
    return out


```

  6. In `analyze_message`, immediately after the `# ── Domains ──` block (after `signals.detected_domains = [...]`, before `# ── File paths ──`) insert:

```python
    # ── Entities + thread cues ───────────────────────────────────
    signals.entities = canonical_entities(text)
    signals.past_reference = bool(PAST_REF_RE.search(text))
    cue = ANAPHORA_RE.match(text)
    if cue:
        if cue.group("phrase"):
            signals.anaphora = True
        elif cue.group("bare") and not signals.entities and not signals.detected_domains:
            # bare "that"/"it" counts only when nothing else says what the message is about
            signals.anaphora = True

```

- [ ] **Run tests, expect PASS:**
  `cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core && /Volumes/4TB-BAD/Halbert/.venv/bin/python -m pytest tests/test_intake_signals.py tests/test_intake_complexity.py tests/test_intake_pipeline.py -q -p no:cacheprovider`
  Expected: `86 passed` (36 + 14 new in signals, 16, 20).

- [ ] **Commit:**
  ```
  cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation && git add halbert_core/halbert_core/intake/signals.py halbert_core/tests/test_intake_signals.py && git commit -m "feat(intake): entity aliases, canonical entities, and thread cues

  ENTITY_ALIASES maps smb/cifs/smbd/nmbd/'file share' to samba, vpn/wg to
  wireguard, certbot/letsencrypt/acme to tls, zpool to zfs. canonical_entities
  returns alias hits, non-generic domain keywords, and file paths. Domain
  keywords gain samba/smb/nfs/cups/wireguard/vpn/share/scanner (network),
  zpool/smart/smartctl (storage) and cron/crontab (service).
  MessageSignals gains entities, past_reference, and anaphora (bare that/it
  counts only when no entity or domain is present)."
  ```

### Task A5: Segmenter decisions and the continuity hint

**Files:**
- Create: `halbert_core/halbert_core/agents/thread_signals.py`
- Test: `halbert_core/tests/test_thread_signals.py` (new)

- [ ] **Write the failing test** — create `halbert_core/tests/test_thread_signals.py`:

```python
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for agents/thread_signals.py — decide() rules and build_hint() text."""

from datetime import datetime

import pytest

from halbert_core.agents.conversation_sqlite import SqliteConversationStore
from halbert_core.agents.thread_signals import (
    Candidate, ThreadDecision, build_hint, decide, format_date, relative_time,
)
from halbert_core.intake.signals import analyze_message

NOW = datetime(2026, 8, 26, 12, 0).timestamp()
SAMBA_TS = NOW - 43 * 86400  # Jul 14


@pytest.fixture
def store():
    s = SqliteConversationStore(":memory:")
    s.create_thread("samba", "Samba media share")
    s.update_thread("samba", status="closed", last_active=SAMBA_TS, topic_domains=["network", "config"],
                    entities_json=["samba", "share", "/etc/samba/smb.conf", "media"])
    s.upsert_receipt("samba", "Samba media share",
        "Title: Samba media share\nEntities: samba, share, /etc/samba/smb.conf, media\n"
        "Started with: add a samba share for the media folder\nLast said: Restarted smbd.\nOpen loop: none recorded")
    s.create_thread("nas", "NAS disk swap")
    s.update_thread("nas", status="paused", last_active=NOW - 600, paused_at=NOW - 600,
                    topic_domains=["storage"], entities_json=["zfs", "nvme", "/dev/nvme0n1"])
    s.upsert_receipt("nas", "NAS disk swap",
        "Title: NAS disk swap\nEntities: zfs, nvme, /dev/nvme0n1\nStarted with: swap the failing nvme in the zfs pool\n"
        "Last said: Resilver running.\nOpen loop: Check zpool status once the resilver finishes.")
    s.create_thread("open", "Nginx tuning")
    s.update_thread("open", status="open", last_active=NOW - 60, topic_domains=["service"], entities_json=["nginx"])
    yield s
    s.close()


def _open(store):
    return store.get_thread("open")


def _decide(store, text, now=NOW, open_thread="open"):
    ot = _open(store) if open_thread else None
    return decide(text, analyze_message(text), ot, store, now)


class TestDecide:
    def test_detour_stays(self, store):
        d = _decide(store, "check the disk space on /var")
        assert d.action == "stay" and d.stale is False and d.target_thread_id == "open" and d.strong is None

    def test_gap_only_is_stale_not_new(self, store):
        store.update_thread("open", last_active=NOW - 3 * 3600)
        d = _decide(store, "restart nginx")
        assert d.action == "stay" and d.stale is True

    def test_gap_and_shift_opens_new(self, store):
        store.update_thread("open", last_active=NOW - 3 * 3600)
        d = _decide(store, "check the disk space on /var")
        assert d.action == "open_new" and d.stale is True and d.target_thread_id is None

    def test_gap_and_shift_with_anaphora_stays(self, store):
        store.update_thread("open", last_active=NOW - 3 * 3600)
        d = _decide(store, "did that work? the ssd is full")
        assert d.action == "stay" and "anaphora" in d.cues

    def test_no_open_thread(self, store):
        d = _decide(store, "check the disk space on /var", open_thread=None)
        assert d.action == "open_new" and d.target_thread_id is None

    def test_anaphora_no_signals_strong_from_most_recent_closed(self, store):
        store.update_thread("nas", status="closed")
        store.update_thread("open", last_active=None)
        d = _decide(store, "did that work?")
        assert d.action == "stay" and d.strong is not None and d.strong.thread_id == "nas"
        assert d.strong.status == "closed" and d.strong.match_terms == ["anaphora"] and d.cues == ["anaphora"]

    def test_anaphora_ignored_when_open_thread_is_newer(self, store):
        d = _decide(store, "did that work?")
        assert d.action == "stay" and d.strong is None

    def test_strong_overlap_reopens_paused(self, store):
        d = _decide(store, "the zfs resilver on the nvme finished")
        assert d.action == "reopen" and d.target_thread_id == "nas"
        assert d.strong.strong is True and {"zfs", "nvme"} <= set(d.strong.match_terms)

    def test_cue_plus_fts_hit_recalls_closed(self, store):
        d = _decide(store, "add another share like we did for the media one")
        assert d.action == "stay" and d.strong is not None and d.strong.thread_id == "samba"
        assert d.strong.status == "closed" and {"share", "media"} <= set(d.strong.match_terms)
        assert d.cues == ["past_reference"]

    def test_weak_candidates_without_cue(self, store):
        d = _decide(store, "what about the media library")
        assert d.action == "stay" and d.strong is None
        assert d.candidates[0].thread_id == "samba" and d.candidates[0].strong is False and d.candidates[0].score == 0.5


class TestBuildHint:
    def _stay(self, **kw):
        base = dict(action="stay", target_thread_id="open", stale=False, strong=None, candidates=[], cues=[])
        base.update(kw)
        return ThreadDecision(**base)

    def test_empty_for_fresh_thread(self):
        assert build_hint({"title": "x", "turn_count": 0}, self._stay(action="open_new"), [], [], now=NOW) == ""

    def test_thread_line_and_stale(self):
        ot = {"title": "Nginx tuning", "turn_count": 3, "last_active": NOW - 3 * 3600}
        assert build_hint(ot, self._stay(stale=True), [], [], now=NOW) == (
            '<continuity>\nThread: "Nginx tuning" · 3 turns · last active 3 hours ago. (resuming after a gap)\n</continuity>')

    def test_fresh_thread_with_recall(self):
        recalled = [{"thread_id": "samba", "title": "Samba media share", "date": "Jul 14", "last_active": SAMBA_TS,
                     "match_terms": ["share", "media"],
                     "receipt": "Title: Samba media share\nStarted with: add a samba share\nLast said: Restarted smbd.\nOpen loop: none recorded"}]
        hint = build_hint({"title": "Scanner share", "turn_count": 0}, self._stay(), recalled, [], now=NOW)
        assert hint == ('<continuity>\nThread: "Scanner share" · opened just now.\n'
                        'Pulled in: "Samba media share" (Jul 14, 6 weeks ago; matched share, media) — '
                        'Started with: add a samba share Last said: Restarted smbd. Open loop: none recorded\n</continuity>')

    def test_weak_candidates_line_and_omitted_when_strong(self):
        c = Candidate("samba", "Samba media share", SAMBA_TS, 0.5, ["media"], False, "closed")
        ot = {"title": "Nginx tuning", "turn_count": 1, "last_active": NOW - 60}
        hint = build_hint(ot, self._stay(candidates=[c]), [], [], now=NOW)
        assert hint.splitlines()[2] == 'Earlier work that may matter: "Samba media share" (Jul 14; matched media)'
        strong = Candidate("nas", "NAS", NOW - 600, 1.0, ["zfs"], True, "closed")
        hint2 = build_hint(ot, self._stay(strong=strong, candidates=[strong, c]), [], [], now=NOW)
        assert "Earlier work" not in hint2

    def test_notifications_and_cap(self):
        ot = {"title": "Nginx tuning", "turn_count": 1, "last_active": NOW - 60}
        hint = build_hint(ot, self._stay(), [], [{"text": "backup finished, exit 0"}], now=NOW)
        assert hint.splitlines()[2] == "Waiting for you: backup finished, exit 0"
        recalled = [{"title": "Big", "date": "Jul 14", "last_active": SAMBA_TS, "match_terms": ["x"],
                     "receipt": "Started with: " + "w" * 2000}]
        capped = build_hint(ot, self._stay(), recalled, [], now=NOW)
        assert len(capped) <= 900 and capped.endswith("…\n</continuity>")

    def test_time_helpers(self):
        assert relative_time(NOW - 30, NOW) == "just now"
        assert relative_time(NOW - 120, NOW) == "2 minutes ago"
        assert relative_time(NOW - 86400 - 10, NOW) == "yesterday"
        assert relative_time(NOW - 3 * 86400, NOW) == "3 days ago"
        assert relative_time(SAMBA_TS, NOW) == "6 weeks ago"
        assert relative_time(NOW - 100 * 86400, NOW) == "3 months ago"
        assert relative_time(None, NOW) == "unknown"
        assert format_date(SAMBA_TS, NOW) == "Jul 14"
        assert format_date(SAMBA_TS - 400 * 86400, NOW) == "Jun 9, 2025"
```

- [ ] **Run it, expect failure:**
  `cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core && /Volumes/4TB-BAD/Halbert/.venv/bin/python -m pytest tests/test_thread_signals.py -q -p no:cacheprovider`
  Expected: `ModuleNotFoundError: No module named 'halbert_core.agents.thread_signals'`.

- [ ] **Create `halbert_core/halbert_core/agents/thread_signals.py`:**

```python
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Thread segmentation (spec §4.3, §5, §6) and the ``<continuity>`` hint (§7).

``decide`` is pure over its inputs plus two read-only store calls
(``search_receipts``, ``list_threads``); ``build_hint`` renders the
deterministic hint the prompt layer places before the current task.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..intake.signals import MessageSignals
from .receipt import receipt_one_liner

__all__ = [
    "TEMPORAL_GATE_SECONDS", "GRACE_MINUTES", "GRACE_TURNS", "STRONG_MIN_OVERLAP",
    "STRONG_MIN_SCORE", "HINT_MAX_CHARS", "Candidate", "ThreadDecision",
    "decide", "build_hint", "relative_time", "format_date",
]

#: Same 2 h gate as context/watermark.py ContextWatermark.temporal_gate_seconds.
TEMPORAL_GATE_SECONDS = 7200
GRACE_MINUTES = 30
GRACE_TURNS = 5
STRONG_MIN_OVERLAP = 2
STRONG_MIN_SCORE = 0.5
HINT_MAX_CHARS = 900
WEAK_CANDIDATES_MAX = 2
CANDIDATES_MAX = 3


@dataclass
class Candidate:
    thread_id: str
    title: str
    last_active: Optional[float]
    score: float
    match_terms: List[str]
    strong: bool
    status: str


@dataclass
class ThreadDecision:
    action: str  # "stay" | "reopen" | "open_new"
    target_thread_id: Optional[str]
    stale: bool
    strong: Optional[Candidate]
    candidates: List[Candidate] = field(default_factory=list)
    cues: List[str] = field(default_factory=list)


# ── time rendering ───────────────────────────────────────────────

def relative_time(ts: Optional[float], now: Optional[float] = None) -> str:
    """'just now' / 'N minutes ago' / 'yesterday' / 'N weeks ago' …"""
    if ts is None:
        return "unknown"
    now = time.time() if now is None else now
    delta = max(0.0, float(now) - float(ts))
    if delta < 60:
        return "just now"
    minutes = int(delta // 60)
    if delta < 3600:
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    hours = int(delta // 3600)
    if delta < 86400:
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    days = int(delta // 86400)
    if days < 2:
        return "yesterday"
    if days < 7:
        return f"{days} days ago"
    weeks = days // 7
    if days < 60:
        return f"{weeks} week{'s' if weeks != 1 else ''} ago"
    months = days // 30
    if days < 365:
        return f"{months} month{'s' if months != 1 else ''} ago"
    years = days // 365
    return f"{years} year{'s' if years != 1 else ''} ago"


def format_date(ts: Optional[float], now: Optional[float] = None) -> str:
    """'Jul 14', with the year appended when it is not the current year."""
    if ts is None:
        return "unknown date"
    now = time.time() if now is None else now
    dt = datetime.fromtimestamp(float(ts))
    label = f"{dt.strftime('%b')} {dt.day}"
    if dt.year != datetime.fromtimestamp(float(now)).year:
        label += f", {dt.year}"
    return label


# ── candidates ───────────────────────────────────────────────────

def _gather_candidates(query: str, entities: set, open_id: Optional[str], store: Any) -> List[Candidate]:
    expanded = query if not entities else f"{query} {' '.join(sorted(entities))}"
    by_id: Dict[str, Candidate] = {}
    try:
        hits = store.search_receipts(expanded, exclude_thread_id=open_id, limit=CANDIDATES_MAX)
    except Exception:
        hits = []
    for hit in hits:
        by_id[hit["thread_id"]] = Candidate(
            thread_id=hit["thread_id"],
            title=hit.get("title") or "",
            last_active=hit.get("last_active"),
            score=float(hit.get("score") or 0.0),
            match_terms=list(hit.get("match_terms") or []),
            strong=False,
            status=hit.get("status") or "closed",
        )
    if entities:
        try:
            threads = store.list_threads(status=["paused", "closed"], limit=50)
        except Exception:
            threads = []
        for t in threads:
            tid = t["thread_id"]
            if tid == open_id:
                continue
            overlap = entities & set(t.get("entities_json") or ())
            if not overlap:
                continue
            score = min(1.0, len(overlap) / STRONG_MIN_OVERLAP)
            strong = len(overlap) >= STRONG_MIN_OVERLAP
            cand = by_id.get(tid)
            if cand is None:
                by_id[tid] = Candidate(
                    thread_id=tid, title=t.get("title") or "", last_active=t.get("last_active"),
                    score=score, match_terms=sorted(overlap), strong=strong,
                    status=t.get("status") or "closed",
                )
            else:
                cand.score = max(cand.score, score)
                cand.strong = cand.strong or strong
                for term in sorted(overlap):
                    if term not in cand.match_terms:
                        cand.match_terms.append(term)
    cands = list(by_id.values())
    cands.sort(key=lambda c: (-c.score, -(c.last_active or 0.0)))
    return cands[:CANDIDATES_MAX]


def decide(query: str, signals: MessageSignals, open_thread: Optional[Dict[str, Any]], store: Any, now: float) -> ThreadDecision:
    """Resolve which thread the message belongs to (spec §4.3 rules)."""
    open_id = open_thread.get("thread_id") if open_thread else None
    cues = [name for name, on in (("past_reference", signals.past_reference), ("anaphora", signals.anaphora)) if on]
    entities = set(signals.entities or ())
    candidates = _gather_candidates(query, entities, open_id, store)

    # Bare anaphora ("did that work?") with no topical signal refers to the
    # most recent paused/closed thread when nothing in the open thread is newer.
    if signals.anaphora and not entities and not signals.detected_domains:
        try:
            recent = store.list_threads(status=["paused", "closed"], limit=1)
        except Exception:
            recent = []
        if recent:
            r = recent[0]
            open_last = float((open_thread or {}).get("last_active") or 0.0)
            if float(r.get("last_active") or 0.0) >= open_last:
                cand = Candidate(
                    thread_id=r["thread_id"], title=r.get("title") or "",
                    last_active=r.get("last_active"), score=1.0, match_terms=["anaphora"],
                    strong=True, status=r.get("status") or "closed",
                )
                candidates = [cand] + [c for c in candidates if c.thread_id != cand.thread_id]

    if cues and candidates and candidates[0].score >= STRONG_MIN_SCORE:
        candidates[0].strong = True
    candidates.sort(key=lambda c: (not c.strong, -c.score, -(c.last_active or 0.0)))
    strong = next((c for c in candidates if c.strong), None)

    if open_thread is None:
        return ThreadDecision("open_new", None, False, strong, candidates, cues)
    if strong is not None and strong.status == "paused":
        return ThreadDecision("reopen", strong.thread_id, False, strong, candidates, cues)

    last_active = open_thread.get("last_active")
    gap = (float(now) - float(last_active)) if last_active else 0.0
    stale = gap > TEMPORAL_GATE_SECONDS
    open_domains = set(open_thread.get("topic_domains") or ())
    open_entities = set(open_thread.get("entities_json") or ())
    domain_shift = (
        bool(signals.detected_domains) and bool(open_domains)
        and not (set(signals.detected_domains) & open_domains)
        and not (entities & open_entities)
    )
    if stale and domain_shift and not signals.anaphora:
        return ThreadDecision("open_new", None, stale, strong, candidates, cues)
    return ThreadDecision("stay", open_id, stale, strong, candidates, cues)


# ── hint ─────────────────────────────────────────────────────────

def build_hint(open_thread: Dict[str, Any], decision: ThreadDecision, recalled: List[Dict[str, Any]], notifications: List[Dict[str, Any]], voice: str = "first_person", *, now: Optional[float] = None) -> str:
    """Render the ``<continuity>`` block (≤ 900 chars); '' when there is nothing to say.

    ``voice`` is accepted for the prompt layer, which wraps the block through
    the voice renderer; the facts inside are voice-neutral.
    """
    now = time.time() if now is None else now
    if not open_thread:
        return ""
    title = open_thread.get("title") or "Untitled"
    turns = int(open_thread.get("turn_count") or 0)
    weak: List[Candidate] = []
    if not recalled and decision.strong is None:
        weak = [c for c in decision.candidates if not c.strong][:WEAK_CANDIDATES_MAX]
    if turns == 0 and not recalled and not weak and not notifications:
        return ""
    lines: List[str] = []
    if turns == 0:
        head = f'Thread: "{title}" · opened just now.'
    else:
        head = (f'Thread: "{title}" · {turns} turns · last active '
                f'{relative_time(open_thread.get("last_active"), now)}.')
    if decision.stale:
        head += " (resuming after a gap)"
    lines.append(head)
    for r in recalled:
        terms = ", ".join(r.get("match_terms") or []) or "recall"
        lines.append(
            f'Pulled in: "{r.get("title") or ""}" ({r.get("date") or "unknown date"}, '
            f'{relative_time(r.get("last_active"), now)}; matched {terms}) — '
            f'{receipt_one_liner(r.get("receipt") or "")}'
        )
    if weak:
        parts = [
            f'"{c.title}" ({format_date(c.last_active, now)}; matched {", ".join(c.match_terms) or "title"})'
            for c in weak
        ]
        lines.append("Earlier work that may matter: " + "; ".join(parts))
    if notifications:
        items = [str(n.get("text") or n.get("title") or "") for n in notifications]
        lines.append("Waiting for you: " + "; ".join(i for i in items if i))
    body = "\n".join(lines)
    budget = HINT_MAX_CHARS - len("<continuity>\n") - len("\n</continuity>")
    if len(body) > budget:
        body = body[: budget - 1].rstrip() + "…"
    return f"<continuity>\n{body}\n</continuity>"
```

- [ ] **Run tests, expect PASS:**
  `cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core && /Volumes/4TB-BAD/Halbert/.venv/bin/python -m pytest tests/test_thread_signals.py -q -p no:cacheprovider`
  Expected: `16 passed`.

- [ ] **Commit:**
  ```
  cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation && git add halbert_core/halbert_core/agents/thread_signals.py halbert_core/tests/test_thread_signals.py && git commit -m "feat(agents): thread segmenter decisions and the continuity hint

  decide() keeps detours in the open thread, marks gap-only as stale, opens a
  new thread only on gap + domain shift with no anaphora, reopens a paused
  thread on a strong match, and treats bare anaphora as a reference to the
  most recent paused/closed thread. build_hint renders the <continuity>
  block (thread line, pulled-in receipts, weak candidates, notifications)
  capped at 900 chars."
  ```

### Task A6: ThreadManager — begin_turn / end_turn / resume / interrupted

**Files:**
- Create: `halbert_core/halbert_core/agents/threads.py`
- Test: `halbert_core/tests/test_threads.py` (new)

- [ ] **Write the failing test** — create `halbert_core/tests/test_threads.py`:

```python
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for agents/threads.py — the hidden-thread manager."""

from datetime import datetime

import pytest

from halbert_core.agents.conversation_sqlite import SqliteConversationStore
from halbert_core.agents.threads import ThreadManager
from halbert_core.intake.signals import analyze_message

NOW = datetime(2026, 8, 26, 12, 0).timestamp()


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


@pytest.fixture
def tm():
    s = SqliteConversationStore(":memory:")
    clock = Clock(NOW)
    m = ThreadManager(s, now=clock)
    m.clock = clock
    yield m
    s.close()


def _turn(tm, text, session="s", **end):
    turn = tm.begin_turn(text, analyze_message(text), session)
    tm.end_turn(turn, assistant_text=end.get("assistant", "ok"), blocks=end.get("blocks", []),
                terminal_session_ids=end.get("terminals", []), diff_proposals=end.get("diffs", []))
    return turn


class TestBeginEndTurn:
    def test_first_turn_opens_thread_and_persists_user_row(self, tm):
        text = "add a samba share for the media folder"
        turn = tm.begin_turn(text, analyze_message(text), "sess-1")
        assert turn.decision.action == "open_new" and turn.history == [] and turn.hint == "" and turn.recalled == []
        assert turn.previous_thread_id is None and turn.session_id == "sess-1"
        assert turn.domains == ["network"] and turn.entities == ["samba", "share"]
        t = tm.current()
        assert t["thread_id"] == turn.thread_id and t["title"] == text and t["title_source"] == "provisional"
        rows = tm.store.list_messages(turn.thread_id)
        assert len(rows) == 1 and rows[0]["status"] == "in_progress" and rows[0]["turn_id"] == turn.turn_id
        assert rows[0]["session_id"] == "sess-1" and rows[0]["message_id"] == turn.user_message_id

    def test_second_turn_sees_first_exchange(self, tm):
        t1 = _turn(tm, "add a samba share for the media folder", assistant="Added [media] to smb.conf.")
        text = "now restart smbd"
        turn2 = tm.begin_turn(text, analyze_message(text), "sess-2")
        assert turn2.thread_id == t1.thread_id and turn2.decision.action == "stay"
        assert turn2.history == [
            {"role": "user", "content": "add a samba share for the media folder"},
            {"role": "assistant", "content": "Added [media] to smb.conf."},
        ]
        assert turn2.hint == ('<continuity>\nThread: "add a samba share for the media folder" · 1 turns · '
                              'last active just now.\n</continuity>')

    def test_end_turn_updates_thread_and_receipt(self, tm):
        turn = _turn(tm, "add a samba share for the media folder",
                     assistant="Done. Next, check the mount from the laptop.",
                     blocks=[{"tool": "run_command", "args": {"command": "testparm"}, "exit": 0}],
                     terminals=["term-1"], diffs=[{"id": "d1", "path": "/etc/samba/smb.conf"}])
        t = tm.store.get_thread(turn.thread_id)
        assert t["last_active"] == NOW and t["turns_since_pause"] == 1
        assert t["topic_domains"] == ["network"] and t["entities_json"] == ["samba", "share"]
        assert "Commands: testparm (exit 0)" in t["receipt"]
        assert "Files written: /etc/samba/smb.conf" in t["receipt"]
        assert "Open loop: Next, check the mount from the laptop." in t["receipt"]
        rows = tm.store.list_messages(turn.thread_id)
        assert rows[0]["status"] == "complete"
        assert rows[1]["role"] == "assistant" and rows[1]["turn_id"] == turn.turn_id and rows[1]["session_id"] == "s"
        assert rows[1]["terminal_block_ids"] == ["term-1"] and rows[1]["diff_proposals"][0]["id"] == "d1"
        assert tm.store.search_receipts("testparm")[0]["thread_id"] == turn.thread_id

    def test_history_gets_receipt_row_when_older_turns_exist(self, tm):
        for i in range(8):
            _turn(tm, f"step {i} of the samba setup", assistant=f"did step {i}")
        turn = tm.begin_turn("continue", analyze_message("continue"), "s")
        assert len(turn.history) == 13
        assert turn.history[0]["role"] == "system"
        assert turn.history[0]["content"].startswith("[Earlier in this subject: Title: step 0 of the samba setup")
        assert turn.history[1] == {"role": "user", "content": "step 2 of the samba setup"}

    def test_gap_and_shift_opens_new_thread_and_pauses_old(self, tm):
        t1 = _turn(tm, "add a samba share for the media folder", assistant="Added it.")
        tm.clock.advance(3 * 3600)
        text = "check the disk space on /var"
        turn2 = tm.begin_turn(text, analyze_message(text), "s2")
        assert turn2.thread_id != t1.thread_id and turn2.decision.action == "open_new"
        assert turn2.previous_thread_id == t1.thread_id
        old = tm.store.get_thread(t1.thread_id)
        assert old["status"] == "paused" and old["paused_at"] == NOW + 3 * 3600 and old["metadata"]["successor"] == turn2.thread_id
        assert tm.current()["thread_id"] == turn2.thread_id
        assert turn2.history[0]["role"] == "system" and "kept for one turn only" in turn2.history[0]["content"]
        assert turn2.history[1]["content"] == "add a samba share for the media folder"

    def test_strong_recall_of_closed_thread_injects_receipt(self, tm):
        t1 = _turn(tm, "add a samba share for the media folder", assistant="Added [media] at /srv/media.")
        tm.clock.advance(3 * 3600)
        t2 = _turn(tm, "check the disk space on /var")
        assert tm.store.update_thread(t1.thread_id, status="closed") is True
        text = "add another share like we did for the media one"
        turn3 = tm.begin_turn(text, analyze_message(text), "s3")
        assert turn3.thread_id == t2.thread_id and turn3.decision.action == "stay"
        assert turn3.recalled[0]["thread_id"] == t1.thread_id and turn3.recalled[0]["status"] == "accepted"
        assert turn3.hint.startswith('<continuity>\nThread: "check the disk space on /var" · 1 turns · last active just now.\n')
        assert 'Pulled in: "Add samba" (Aug 26, 3 hours ago; matched' in turn3.hint
        assert "Started with: add a samba share for the media folder" in turn3.hint
        rec = tm.store.get_thread(t2.thread_id)["recalled_json"]
        assert len(rec) == 1 and rec[0]["thread_id"] == t1.thread_id and rec[0]["status"] == "accepted"

    def test_strong_match_reopens_paused(self, tm):
        t1 = _turn(tm, "swap the failing nvme in the zfs pool", assistant="Resilver running.")
        tm.clock.advance(3 * 3600)
        t2 = _turn(tm, "add a samba share for the media folder")
        text = "the zfs resilver on the nvme finished"
        turn3 = tm.begin_turn(text, analyze_message(text), "s3")
        assert turn3.decision.action == "reopen" and turn3.thread_id == t1.thread_id
        assert tm.store.get_thread(t2.thread_id)["status"] == "paused"
        assert tm.store.get_thread(t1.thread_id)["status"] == "open"
        assert turn3.history[0] == {"role": "user", "content": "swap the failing nvme in the zfs pool"}

    def test_resume_thread(self, tm):
        t1 = _turn(tm, "add a samba share for the media folder")
        tm.clock.advance(3 * 3600)
        t2 = _turn(tm, "check the disk space on /var")
        assert tm.resume_thread(t1.thread_id, from_thread_id=t2.thread_id) is True
        assert tm.current()["thread_id"] == t1.thread_id
        assert tm.store.get_thread(t2.thread_id)["status"] == "paused"
        reopened = tm.store.get_thread(t1.thread_id)
        assert reopened["paused_at"] is None and reopened["turns_since_pause"] == 0 and "successor" not in reopened["metadata"]
        assert tm.resume_thread("nope", from_thread_id=t1.thread_id) is False
        assert tm.resume_thread(t1.thread_id, from_thread_id=t2.thread_id) is False  # already open

    def test_mark_interrupted(self, tm):
        tm.begin_turn("add a samba share", analyze_message("add a samba share"), "s")
        assert tm.mark_interrupted() == 1
        assert tm.store.list_messages(tm.current()["thread_id"])[0]["status"] == "interrupted"
```

- [ ] **Run it, expect failure:**
  `cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core && /Volumes/4TB-BAD/Halbert/.venv/bin/python -m pytest tests/test_threads.py -q -p no:cacheprovider`
  Expected: `ModuleNotFoundError: No module named 'halbert_core.agents.threads'`.

- [ ] **Create `halbert_core/halbert_core/agents/threads.py`:**

```python
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Hidden-thread manager for the one continuous conversation (spec §4–§6).

One ``ThreadManager`` per process owns thread identity: it resolves which
thread a turn belongs to, persists the user row at turn start, appends the
assistant row at turn end, refreshes receipts, and closes paused threads
after the grace window on ``tick()``. Memory side effects (Haloysius line,
LLM summaries) are ``on_thread_closed`` hooks — no-ops in Plan A.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from ..intake.signals import MessageSignals
from .conversation_sqlite import SqliteConversationStore
from .receipt import build_receipt, provisional_title, refined_title
from .thread_signals import ThreadDecision, build_hint, decide, format_date

logger = logging.getLogger("halbert.agents.threads")

__all__ = ["TurnContext", "ThreadManager", "HISTORY_ROWS"]

HISTORY_ROWS = 12
SOFT_LANDING_ROWS = 6


@dataclass
class TurnContext:
    thread_id: str
    turn_id: str
    user_message_id: Optional[int]
    history: List[Dict[str, Any]]
    hint: str
    recalled: List[Dict[str, Any]]
    decision: ThreadDecision
    session_id: str = ""
    previous_thread_id: Optional[str] = None
    domains: List[str] = field(default_factory=list)
    entities: List[str] = field(default_factory=list)


class ThreadManager:
    """Owns thread identity for every turn. Store failures never raise."""

    def __init__(self, store: SqliteConversationStore, *, now: Callable[[], float] = time.time):
        self.store = store
        self._now = now
        self.on_thread_closed: List[Callable[[Dict[str, Any]], None]] = []

    # ------------------------------------------------------------------
    # Turn boundaries
    # ------------------------------------------------------------------

    def current(self) -> Optional[Dict[str, Any]]:
        return self.store.current_open_thread()

    def begin_turn(self, query: str, signals: MessageSignals, session_id: str) -> TurnContext:
        """Resolve the thread, build history + hint, persist the user row (in_progress)."""
        now = self._now()
        open_thread = self.store.current_open_thread()
        previous_id = open_thread["thread_id"] if open_thread else None
        try:
            decision = decide(query, signals, open_thread, self.store, now)
        except Exception as e:
            logger.warning(f"thread decide failed, staying put: {e}")
            decision = ThreadDecision(
                "stay" if open_thread else "open_new", previous_id, False, None, [], []
            )

        history: List[Dict[str, Any]] = []
        if decision.action == "open_new" or open_thread is None:
            thread_id = self._open_new_thread(
                provisional_title(query), "provisional", now,
                from_thread_id=previous_id, reason="auto",
            )
            if previous_id:
                history = self._soft_landing(previous_id)
        elif decision.action == "reopen" and decision.target_thread_id:
            if self.resume_thread(decision.target_thread_id, from_thread_id=previous_id):
                thread_id = decision.target_thread_id
            else:
                thread_id = previous_id
        else:
            thread_id = previous_id
            if decision.stale:
                self.store.update_thread(thread_id, stale=True)

        thread = self.store.get_thread(thread_id) or {
            "thread_id": thread_id, "title": "", "turn_count": 0, "recalled_json": [],
        }

        recalled: List[Dict[str, Any]] = []
        strong = decision.strong
        if strong is not None and strong.status == "closed" and not self._was_retracted(thread, strong.thread_id):
            entry = self._recall_entry(strong.thread_id, strong.match_terms, now)
            if entry is not None:
                recalled.append(entry)
                self._persist_recall(thread, entry)

        if not history:
            history = self._history(thread)
        try:
            hint = build_hint(thread, decision, recalled, [], now=now)
        except Exception as e:
            logger.warning(f"hint builder failed: {e}")
            hint = ""

        turn_id = uuid.uuid4().hex
        user_message_id = self.store.append_message(
            thread_id, "user", query, origin="human", turn_id=turn_id,
            session_id=session_id, status="in_progress", timestamp=now,
        )
        return TurnContext(
            thread_id=thread_id,
            turn_id=turn_id,
            user_message_id=user_message_id,
            history=history,
            hint=hint,
            recalled=recalled,
            decision=decision,
            session_id=session_id,
            previous_thread_id=previous_id if previous_id != thread_id else None,
            domains=list(signals.detected_domains or []),
            entities=sorted(signals.entities or ()),
        )

    def end_turn(
        self,
        turn: TurnContext,
        *,
        assistant_text: str,
        blocks: list,
        terminal_session_ids: List[str],
        diff_proposals: list,
        status: str = "complete",
        thread_id_override: Optional[str] = None,
    ) -> None:
        """Finalise the turn: user row status, assistant row, thread sets, receipt."""
        now = self._now()
        thread_id = thread_id_override or turn.thread_id
        if turn.user_message_id is not None:
            fields: Dict[str, Any] = {"status": status}
            if thread_id != turn.thread_id:
                fields["thread_id"] = thread_id
            self.store.update_message(turn.user_message_id, **fields)
        if assistant_text or blocks or diff_proposals or terminal_session_ids:
            self.store.append_message(
                thread_id, "assistant", assistant_text or "", origin="assistant",
                turn_id=turn.turn_id, session_id=turn.session_id, status=status,
                blocks=list(blocks or []),
                terminal_block_ids=list(terminal_session_ids or []),
                diff_proposals=list(diff_proposals or []),
                timestamp=now,
            )
        thread = self.store.get_thread(thread_id)
        if thread is None:
            return
        domains = sorted(set(thread.get("topic_domains") or []) | set(turn.domains))
        entities = sorted(set(thread.get("entities_json") or []) | set(turn.entities))
        self.store.update_thread(
            thread_id,
            last_active=now, updated_at=now, stale=False,
            topic_domains=domains, entities_json=entities,
            turns_since_pause=int(thread.get("turns_since_pause") or 0) + 1,
        )
        self._refresh_receipt(thread_id)

    def mark_interrupted(self) -> int:
        """Boot: every ``in_progress`` row becomes ``interrupted``."""
        return self.store.mark_in_progress_interrupted()

    # ------------------------------------------------------------------
    # Thread lifecycle
    # ------------------------------------------------------------------

    def resume_thread(self, thread_id: str, *, from_thread_id: Optional[str]) -> bool:
        """Reopen a paused thread and pause ``from_thread_id``."""
        now = self._now()
        target = self.store.get_thread(thread_id)
        if target is None or target.get("status") != "paused":
            return False
        if from_thread_id and from_thread_id != thread_id:
            self._pause_thread(from_thread_id, now, successor=thread_id)
        meta = dict(target.get("metadata") or {})
        meta.pop("successor", None)
        return self.store.update_thread(
            thread_id, status="open", paused_at=None, stale=False,
            turns_since_pause=0, metadata=meta, updated_at=now,
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _open_new_thread(self, title: str, title_source: str, now: float, *, from_thread_id: Optional[str], reason: str) -> str:
        new_id = uuid.uuid4().hex
        if from_thread_id:
            self._pause_thread(from_thread_id, now, successor=new_id)
        self.store.create_thread(
            new_id, title, title_source=title_source, created_at=now,
            metadata={"reason": reason, "previous_thread_id": from_thread_id},
        )
        return new_id

    def _pause_thread(self, thread_id: str, now: float, *, successor: str) -> None:
        t = self.store.get_thread(thread_id)
        if t is None or t.get("status") != "open":
            return
        meta = dict(t.get("metadata") or {})
        meta["successor"] = successor
        fields: Dict[str, Any] = {
            "status": "paused", "paused_at": now, "stale": False,
            "metadata": meta, "updated_at": now,
        }
        fields.update(self._refined_title_fields(t))
        self.store.update_thread(thread_id, **fields)
        self._refresh_receipt(thread_id)

    def _refined_title_fields(self, t: Dict[str, Any]) -> Dict[str, Any]:
        if t.get("title_source") != "provisional":
            return {}
        entities = list(t.get("entities_json") or [])
        if not entities:
            return {}
        first_user = next(
            (m["content"] for m in self.store.list_messages(t["thread_id"], limit=4) if m["role"] == "user"),
            t.get("title") or "",
        )
        return {"title": refined_title(entities, first_user), "title_source": "receipt"}

    def _refresh_receipt(self, thread_id: str) -> str:
        t = self.store.get_thread(thread_id)
        if t is None:
            return ""
        receipt = build_receipt(t, self.store.list_messages(thread_id))
        if t.get("ephemeral"):
            return receipt
        self.store.upsert_receipt(thread_id, t.get("title") or "", receipt)
        return receipt

    def _history(self, thread: Dict[str, Any]) -> List[Dict[str, Any]]:
        rows = self.store.recent_messages(thread["thread_id"], limit=HISTORY_ROWS)
        history = [{"role": r["role"], "content": r["content"]} for r in rows]
        receipt = thread.get("receipt") or ""
        if receipt and int(thread.get("message_count") or 0) > len(rows):
            history.insert(0, {"role": "system", "content": f"[Earlier in this subject: {receipt}]"})
        return history

    def _soft_landing(self, previous_id: str) -> List[Dict[str, Any]]:
        rows = self.store.recent_messages(previous_id, limit=SOFT_LANDING_ROWS)
        if not rows:
            return []
        prev = self.store.get_thread(previous_id) or {}
        note = (f'[Previous subject "{prev.get("title") or ""}", kept for one turn only; '
                "it is not the current task]")
        return [{"role": "system", "content": note}] + [
            {"role": r["role"], "content": r["content"]} for r in rows
        ]

    @staticmethod
    def _was_retracted(thread: Dict[str, Any], recalled_thread_id: str) -> bool:
        return any(
            e.get("thread_id") == recalled_thread_id and e.get("status") == "retracted"
            for e in (thread.get("recalled_json") or [])
        )

    def _recall_entry(self, thread_id: str, match_terms: List[str], now: float) -> Optional[Dict[str, Any]]:
        t = self.store.get_thread(thread_id)
        if t is None:
            return None
        return {
            "thread_id": thread_id,
            "title": t.get("title") or "",
            "date": format_date(t.get("last_active") or t.get("created_at"), now),
            "last_active": t.get("last_active"),
            "receipt": t.get("receipt") or "",
            "match_terms": list(match_terms),
            "status": "accepted",
            "at": now,
        }

    def _persist_recall(self, thread: Dict[str, Any], entry: Dict[str, Any]) -> None:
        recalled = list(thread.get("recalled_json") or [])
        if any(e.get("thread_id") == entry["thread_id"] and e.get("status") == "accepted" for e in recalled):
            return
        recalled.append({k: entry[k] for k in ("thread_id", "title", "date", "status", "at")})
        thread["recalled_json"] = recalled
        self.store.update_thread(thread["thread_id"], recalled_json=recalled)
```

- [ ] **Run tests, expect PASS:**
  `cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core && /Volumes/4TB-BAD/Halbert/.venv/bin/python -m pytest tests/test_threads.py -q -p no:cacheprovider`
  Expected: `9 passed`.

- [ ] **Commit:**
  ```
  cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation && git add halbert_core/halbert_core/agents/threads.py halbert_core/tests/test_threads.py && git commit -m "feat(agents): ThreadManager begin_turn/end_turn over hidden threads

  begin_turn resolves the thread via decide(), persists the user row as
  in_progress, builds the 12-row history (+ receipt system row, + one-turn
  soft landing after a switch), injects a strong closed recall into
  recalled_json, and renders the continuity hint. end_turn finalises the
  user row, appends the assistant row with blocks/terminal ids/diffs, updates
  last_active/domains/entities/turns_since_pause and refreshes the receipt."
  ```

### Task A6b: ThreadManager — new_thread, tick, recall, retract_recall, singleton

**Files:**
- Modify: `halbert_core/halbert_core/agents/threads.py` (imports; `__all__`; constants; methods after `resume_thread`; module tail)
- Test: `halbert_core/tests/test_threads.py` (append)

- [ ] **Write the failing test.** In `halbert_core/tests/test_threads.py` replace the two import lines
  ```python
  from halbert_core.agents.threads import ThreadManager
  from halbert_core.intake.signals import analyze_message
  ```
  with
  ```python
  from halbert_core.agents import threads as threads_mod
  from halbert_core.agents.thread_signals import GRACE_MINUTES, GRACE_TURNS
  from halbert_core.agents.threads import ThreadManager, get_thread_manager
  from halbert_core.intake.signals import analyze_message
  ```
  and append at the end of the file:

```python


class TestNewResumeTick:
    def test_end_turn_moves_user_row_on_override(self, tm):
        t1 = _turn(tm, "add a samba share for the media folder")
        text = "and now something else"
        turn = tm.begin_turn(text, analyze_message(text), "s2")
        new_id = tm.new_thread("Other thing", "model switched", from_thread_id=turn.thread_id)
        tm.end_turn(turn, assistant_text="", blocks=[], terminal_session_ids=[], diff_proposals=[],
                    status="cancelled", thread_id_override=new_id)
        assert tm.store.list_messages(t1.thread_id)[-1]["role"] == "assistant"
        moved = tm.store.list_messages(new_id)
        assert len(moved) == 1 and moved[0]["content"] == text and moved[0]["status"] == "cancelled"
        assert tm.store.get_thread(new_id)["turns_since_pause"] == 1

    def test_new_thread_pauses_and_tick_closes_after_grace(self, tm):
        t1 = _turn(tm, "add a samba share for the media folder")
        new_id = tm.new_thread("Scanner share", "different device", from_thread_id=t1.thread_id)
        cur = tm.current()
        assert cur["thread_id"] == new_id and cur["title"] == "Scanner share" and cur["title_source"] == "model"
        assert cur["metadata"] == {"reason": "different device", "previous_thread_id": t1.thread_id}
        old = tm.store.get_thread(t1.thread_id)
        assert old["status"] == "paused" and old["paused_at"] == NOW and old["metadata"]["successor"] == new_id
        assert tm.tick() == []
        tm.clock.advance(GRACE_MINUTES * 60)
        seen = []
        tm.on_thread_closed.append(lambda t: seen.append(t["thread_id"]))
        assert tm.tick() == [t1.thread_id] and seen == [t1.thread_id]
        assert tm.store.get_thread(t1.thread_id)["status"] == "closed"
        assert tm.store.search_receipts("samba")[0]["thread_id"] == t1.thread_id
        assert tm.tick() == []

    def test_tick_closes_after_grace_turns(self, tm):
        t1 = _turn(tm, "add a samba share for the media folder")
        tm.new_thread("Scanner share", "x", from_thread_id=t1.thread_id)
        for i in range(GRACE_TURNS - 1):
            _turn(tm, f"scanner step {i}")
            assert tm.tick() == []
        _turn(tm, "scanner final step")
        assert tm.tick() == [t1.thread_id]

    def test_pause_refines_provisional_title(self, tm):
        t1 = _turn(tm, "add a samba share for the media folder")
        tm.new_thread("Scanner share", "x", from_thread_id=t1.thread_id)
        old = tm.store.get_thread(t1.thread_id)
        assert old["title"] == "Add samba" and old["title_source"] == "receipt"


class TestRecall:
    def test_recall_by_query_returns_receipt_and_snippets(self, tm):
        t1 = _turn(tm, "add a samba share for the media folder", assistant="Added [media] to /etc/samba/smb.conf.")
        new_id = tm.new_thread("Scanner share", "x", from_thread_id=t1.thread_id)
        res = tm.recall("samba media share", exclude_thread_id=new_id)
        assert len(res) == 1 and res[0]["thread_id"] == t1.thread_id and res[0]["date"] == "Aug 26"
        assert res[0]["title"] == "Add samba" and res[0]["receipt"].startswith("Title: Add samba")
        assert set(res[0]["match_terms"]) == {"samba", "media", "share"}
        assert res[0]["matching_messages"] and all("samba" in s.lower() for s in res[0]["matching_messages"])
        assert tm.recall("zzznothing") == []
        assert tm.recall() == []
        by_id = tm.recall(thread_id=t1.thread_id)
        assert by_id[0]["thread_id"] == t1.thread_id and by_id[0]["matching_messages"] == []
        assert tm.recall(thread_id="nope") == []

    def test_retract_recall_and_no_re_recall(self, tm):
        t1 = _turn(tm, "add a samba share for the media folder", assistant="Added [media] at /srv/media.")
        tm.clock.advance(3 * 3600)
        t2 = _turn(tm, "check the disk space on /var")
        tm.clock.advance(31 * 60)
        assert tm.tick() == [t1.thread_id]
        text = "add another share like we did for the media one"
        turn3 = _turn(tm, text)
        assert turn3.recalled and turn3.recalled[0]["thread_id"] == t1.thread_id
        assert tm.retract_recall(t2.thread_id, t1.thread_id) is True
        rec = tm.store.get_thread(t2.thread_id)["recalled_json"]
        assert rec[0]["status"] == "retracted" and rec[0]["at"] == tm.clock.t
        assert tm.retract_recall(t2.thread_id, t1.thread_id) is False
        assert tm.retract_recall("nope", t1.thread_id) is False
        turn4 = tm.begin_turn(text, analyze_message(text), "s4")
        assert turn4.recalled == [] and "Pulled in" not in turn4.hint


class TestSingleton:
    def test_get_thread_manager_uses_default_db(self, tmp_path, monkeypatch):
        monkeypatch.setattr(threads_mod._cs, "_DEFAULT_DB", str(tmp_path / "conv.db"))
        monkeypatch.setattr(threads_mod, "_manager", None)
        m = get_thread_manager()
        assert get_thread_manager() is m and isinstance(m, ThreadManager)
        assert (tmp_path / "conv.db").exists()
        m.store.close()
```

- [ ] **Run it, expect failure:**
  `cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core && /Volumes/4TB-BAD/Halbert/.venv/bin/python -m pytest tests/test_threads.py -q -p no:cacheprovider`
  Expected: `ImportError: cannot import name 'get_thread_manager' from 'halbert_core.agents.threads'`.

- [ ] **Implement** — edit `halbert_core/halbert_core/agents/threads.py`:

  1. Replace the import block
     ```python
     from ..intake.signals import MessageSignals
     from .conversation_sqlite import SqliteConversationStore
     from .receipt import build_receipt, provisional_title, refined_title
     from .thread_signals import ThreadDecision, build_hint, decide, format_date
     ```
     with
     ```python
     from ..intake.signals import MessageSignals
     from . import conversation_sqlite as _cs
     from .conversation_sqlite import SqliteConversationStore
     from .receipt import build_receipt, provisional_title, refined_title
     from .thread_signals import (
         GRACE_MINUTES, GRACE_TURNS, ThreadDecision, build_hint, decide, format_date,
     )
     ```
  2. Replace `__all__ = ["TurnContext", "ThreadManager", "HISTORY_ROWS"]` with `__all__ = ["TurnContext", "ThreadManager", "get_thread_manager", "HISTORY_ROWS"]`.
  3. After `SOFT_LANDING_ROWS = 6` add:
     ```python
     RECALL_SNIPPETS = 5
     RECALL_MAX = 3
     ```
  4. Insert immediately after the `resume_thread` method (before the `# Internals` section comment):

```python
    def new_thread(self, title: str, reason: str, *, from_thread_id: str) -> str:
        """Model-initiated switch: pause ``from_thread_id``, open a new thread."""
        clean = provisional_title(title or "")
        return self._open_new_thread(clean, "model", self._now(), from_thread_id=from_thread_id, reason=reason)

    def tick(self) -> List[str]:
        """Close paused threads past the grace window; returns the closed ids.

        Plan B adds the live-terminal guard: never close while a terminal
        session of this thread is open (spec §5 "Stale").
        """
        now = self._now()
        closed: List[str] = []
        for t in self.store.list_threads(status="paused", limit=200):
            paused_at = float(t.get("paused_at") or t.get("updated_at") or now)
            successor_id = (t.get("metadata") or {}).get("successor")
            successor_turns = 0
            if successor_id:
                successor = self.store.get_thread(successor_id) or {}
                successor_turns = int(successor.get("turns_since_pause") or 0)
            if (now - paused_at) >= GRACE_MINUTES * 60 or successor_turns >= GRACE_TURNS:
                self._close_thread(t, now)
                closed.append(t["thread_id"])
        return closed

    # ------------------------------------------------------------------
    # Recall
    # ------------------------------------------------------------------

    def recall(
        self,
        query: Optional[str] = None,
        thread_id: Optional[str] = None,
        *,
        exclude_thread_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Up to 3 candidates: {thread_id, title, date, receipt, matching_messages, match_terms}."""
        now = self._now()
        if thread_id:
            t = self.store.get_thread(thread_id)
            return [self._recall_result(t, query, [], now)] if t is not None else []
        if not query:
            return []
        out: List[Dict[str, Any]] = []
        for hit in self.store.search_receipts(query, exclude_thread_id=exclude_thread_id, limit=RECALL_MAX):
            t = self.store.get_thread(hit["thread_id"])
            if t is not None:
                out.append(self._recall_result(t, query, list(hit.get("match_terms") or []), now))
        return out

    def retract_recall(self, thread_id: str, recalled_thread_id: str) -> bool:
        """Mark an accepted recall on ``thread_id`` as retracted."""
        t = self.store.get_thread(thread_id)
        if t is None:
            return False
        now = self._now()
        recalled = list(t.get("recalled_json") or [])
        changed = False
        for entry in recalled:
            if entry.get("thread_id") == recalled_thread_id and entry.get("status") == "accepted":
                entry["status"] = "retracted"
                entry["at"] = now
                changed = True
        if not changed:
            return False
        return self.store.update_thread(thread_id, recalled_json=recalled)

```

  5. Insert immediately after the `_pause_thread` method (before `_refined_title_fields`):

```python
    def _close_thread(self, t: Dict[str, Any], now: float) -> None:
        thread_id = t["thread_id"]
        fields: Dict[str, Any] = {"status": "closed", "updated_at": now}
        fields.update(self._refined_title_fields(t))
        self.store.update_thread(thread_id, **fields)
        self._refresh_receipt(thread_id)
        closed = self.store.get_thread(thread_id) or t
        for hook in list(self.on_thread_closed):
            try:
                hook(closed)
            except Exception as e:
                logger.warning(f"on_thread_closed hook failed: {e}")

```

  6. Append after `_persist_recall` (end of the class) and at module level:

```python
    def _recall_result(self, t: Dict[str, Any], query: Optional[str], match_terms: List[str], now: float) -> Dict[str, Any]:
        snippets = self.store.search_snippets(t["thread_id"], query, limit=RECALL_SNIPPETS) if query else []
        return {
            "thread_id": t["thread_id"],
            "title": t.get("title") or "",
            "date": format_date(t.get("last_active") or t.get("created_at"), now),
            "receipt": t.get("receipt") or "",
            "matching_messages": snippets,
            "match_terms": list(match_terms),
        }


_manager: Optional[ThreadManager] = None


def get_thread_manager() -> ThreadManager:
    """Process-wide manager over the default conversations database."""
    global _manager
    if _manager is None:
        _manager = ThreadManager(SqliteConversationStore(_cs._DEFAULT_DB))
    return _manager
```

- [ ] **Run tests, expect PASS:**
  `cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core && /Volumes/4TB-BAD/Halbert/.venv/bin/python -m pytest tests/test_threads.py tests/test_thread_signals.py tests/test_thread_store.py tests/test_receipt.py tests/test_intake_signals.py tests/test_conversation_sqlite.py tests/test_session_affinity.py -q -p no:cacheprovider`
  Expected: `154 passed` (16 threads, 16, 29, 10, 50, 20, 13). Then run the full suite: `/Volumes/4TB-BAD/Halbert/.venv/bin/python -m pytest tests -q -p no:cacheprovider` — expected: 4 pre-existing failures only (test_tool_calling_bridge, test_phase_d_integration), everything else passes.

- [ ] **Commit:**
  ```
  cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation && git add halbert_core/halbert_core/agents/threads.py halbert_core/tests/test_threads.py && git commit -m "feat(agents): thread lifecycle, recall, and the ThreadManager singleton

  new_thread pauses the open thread (refining its provisional title) and
  opens a model-named one; tick() closes paused threads after 30 minutes or
  5 turns of the successor, rebuilds the final receipt, and runs
  on_thread_closed hooks; recall() returns up to 3 receipts with FTS
  snippets; retract_recall marks an accepted recall retracted and blocks
  automatic re-recall. get_thread_manager() serves the process."
  ```

### Task A6c: ThreadManager — merge_back and the grace-window resume

**Files:**
- Modify: `halbert_core/halbert_core/agents/conversation_sqlite.py` (add `merge_thread` after `search_snippets`, before the `# session_somatic_blocks (C1 link)` section)
- Modify: `halbert_core/halbert_core/agents/threads.py` (`begin_turn` reopen branch; replace `resume_thread`; add `merge_back`; add `_reopen_thread` / `_predecessor_id` / `_paused_predecessor` / `_within_grace` before `_close_thread`)
- Test: `halbert_core/tests/test_thread_store.py` (append), `halbert_core/tests/test_threads.py` (one edit + append)

Spec §5 "Merge": "same topic" within the grace window moves the new thread's turns back into the previous thread and marks the new one `merged` (rows stay, receipt dropped). Two paths reopen a paused thread and they differ on purpose:
- **`resume_thread`** (the model's tool, i.e. the admin said "no, same topic"): when `from_thread_id` was opened *from* `thread_id` and the grace window is still open (`turns_since_pause < GRACE_TURNS` on the new thread and `paused_at` newer than `GRACE_MINUTES`), the split was spurious → `merge_back`. Otherwise it is a plain reopen that pauses `from_thread_id`.
- **Auto-reopen on a strong match** (`begin_turn`, decision `reopen`): always a plain reopen. The open thread was a real subject of its own (the admin is jumping back, not correcting a split), so it is paused beside the target, never merged.

- [ ] **Write the failing tests.** Append to `halbert_core/tests/test_thread_store.py`:

```python

# ---------------------------------------------------------------------------
# Merge-back: merge_thread (A6c)
# ---------------------------------------------------------------------------

class TestMergeThread:
    def test_merge_moves_rows_fts_and_flags(self, store):
        store.create_thread("prev", "Samba share")
        store.update_thread("prev", status="paused", paused_at=10.0)
        store.upsert_receipt("prev", "Samba share", "Title: Samba share\nEntities: samba")
        store.create_thread("new", "Scanner share")
        store.upsert_receipt("new", "Scanner share", "Title: Scanner share\nEntities: scanner")
        a = store.append_message("prev", "user", "add the samba share", turn_id="t1")
        b = store.append_message("new", "user", "now the scanner share", turn_id="t2")
        c = store.append_message("new", "assistant", "scanner share added", origin="assistant", turn_id="t2")
        assert store.merge_thread("new", "prev", now=50.0) == 2
        assert [m["message_id"] for m in store.list_messages("prev")] == [a, b, c]
        assert store.list_messages("new") == []
        assert [r[0] for r in store._conn.execute(
            "SELECT conversation_id FROM messages_fts WHERE messages_fts MATCH '\"scanner\"' ORDER BY rowid"
        ).fetchall()] == ["prev", "prev"]
        new = store.get_thread("new")
        assert (new["status"], new["merged_into"], new["receipt"], new["paused_at"]) == ("merged", "prev", "", None)
        assert store._conn.execute("SELECT COUNT(*) FROM receipts_fts WHERE thread_id = 'new'").fetchone()[0] == 0
        prev = store.get_thread("prev")
        assert (prev["status"], prev["paused_at"], prev["turns_since_pause"], prev["updated_at"]) == ("open", None, 0, 50.0)
        assert store.search_receipts("scanner") == []
        assert store.search_snippets("prev", "scanner") and store.search_snippets("new", "scanner") == []

    def test_merge_refuses_missing_or_same_thread(self, store):
        store.create_thread("prev", "P")
        assert store.merge_thread("nope", "prev") is None
        assert store.merge_thread("prev", "prev") is None
        assert store.get_thread("prev")["status"] == "open"
```

  In `halbert_core/tests/test_threads.py` replace the opening of `test_resume_thread`
  ```python
      def test_resume_thread(self, tm):
          t1 = _turn(tm, "add a samba share for the media folder")
          tm.clock.advance(3 * 3600)
          t2 = _turn(tm, "check the disk space on /var")
          assert tm.resume_thread(t1.thread_id, from_thread_id=t2.thread_id) is True
  ```
  with
  ```python
      def test_resume_thread(self, tm):
          t1 = _turn(tm, "add a samba share for the media folder")
          tm.clock.advance(3 * 3600)
          t2 = _turn(tm, "check the disk space on /var")
          tm.clock.advance(GRACE_MINUTES * 60)  # past the grace window: plain reopen (merge cases: TestMergeBack)
          assert tm.resume_thread(t1.thread_id, from_thread_id=t2.thread_id) is True
  ```
  (the rest of the method is unchanged) and append at the end of the file:

```python

class TestMergeBack:
    def test_merge_moves_rows_and_marks_merged(self, tm):
        t1 = _turn(tm, "add a samba share for the media folder", assistant="Added [media].")
        new_id = tm.new_thread("Scanner share", "different device", from_thread_id=t1.thread_id)
        t2 = _turn(tm, "now the scanner share too", assistant="Added [scanner].")
        assert t2.thread_id == new_id
        assert tm.merge_back(new_id) == t1.thread_id
        rows = tm.store.list_messages(t1.thread_id)
        assert [r["content"] for r in rows] == ["add a samba share for the media folder", "Added [media].",
                                                "now the scanner share too", "Added [scanner]."]
        assert tm.store.list_messages(new_id) == []
        merged = tm.store.get_thread(new_id)
        assert (merged["status"], merged["merged_into"], merged["receipt"]) == ("merged", t1.thread_id, "")
        prev = tm.store.get_thread(t1.thread_id)
        assert prev["status"] == "open" and prev["paused_at"] is None and prev["turns_since_pause"] == 0
        assert "successor" not in prev["metadata"] and prev["metadata"]["merged_from"] == [new_id]
        assert prev["entities_json"] == ["samba", "scanner", "share"] and prev["last_active"] == NOW
        assert "· 2 turns" in prev["receipt"] and "Last said: Added [scanner]." in prev["receipt"]
        assert tm.current()["thread_id"] == t1.thread_id
        assert tm.store._conn.execute(
            "SELECT COUNT(*) FROM receipts_fts WHERE thread_id = ?", (new_id,)).fetchone()[0] == 0

    def test_merged_thread_excluded_from_search_and_recall(self, tm):
        t1 = _turn(tm, "add a samba share for the media folder")
        new_id = tm.new_thread("Scanner share", "x", from_thread_id=t1.thread_id)
        _turn(tm, "now the scanner share too")
        assert tm.store.search_receipts("scanner")[0]["thread_id"] == new_id
        assert tm.merge_back(new_id) == t1.thread_id
        assert [h["thread_id"] for h in tm.store.search_receipts("scanner")] == [t1.thread_id]
        hits = tm.recall("scanner share")
        assert [r["thread_id"] for r in hits] == [t1.thread_id] and hits[0]["matching_messages"]

    def test_merge_back_refused_outside_grace_or_without_predecessor(self, tm):
        first = _turn(tm, "add a samba share for the media folder")
        assert tm.merge_back(first.thread_id) is None  # nothing to merge into
        assert tm.merge_back("nope") is None
        new_id = tm.new_thread("Scanner share", "x", from_thread_id=first.thread_id)
        tm.clock.advance(GRACE_MINUTES * 60)
        assert tm.merge_back(new_id) is None  # time window elapsed
        assert tm.store.get_thread(new_id)["status"] == "open"
        assert tm.store.get_thread(first.thread_id)["status"] == "paused"
        assert tm.tick() == [first.thread_id]
        # GRACE_TURNS turns on the successor also end the window
        third_id = tm.new_thread("Printer", "x", from_thread_id=new_id)
        for i in range(GRACE_TURNS):
            _turn(tm, f"printer step {i}")
        assert tm.merge_back(third_id) is None
        assert tm.store.get_thread(new_id)["status"] == "paused"

    def test_resume_within_grace_merges(self, tm):
        t1 = _turn(tm, "add a samba share for the media folder")
        new_id = tm.new_thread("Scanner share", "model guessed a new subject", from_thread_id=t1.thread_id)
        _turn(tm, "now the scanner share too")
        assert tm.resume_thread(t1.thread_id, from_thread_id=new_id) is True
        assert tm.store.get_thread(new_id)["status"] == "merged"
        assert tm.current()["thread_id"] == t1.thread_id
        assert len(tm.store.list_messages(t1.thread_id)) == 4
        assert tm.resume_thread(t1.thread_id, from_thread_id=new_id) is False  # already open

    def test_resume_after_grace_reopens_without_merging(self, tm):
        t1 = _turn(tm, "add a samba share for the media folder")
        new_id = tm.new_thread("Scanner share", "x", from_thread_id=t1.thread_id)
        _turn(tm, "now the scanner share too")
        tm.clock.advance(GRACE_MINUTES * 60)
        assert tm.resume_thread(t1.thread_id, from_thread_id=new_id) is True
        paused = tm.store.get_thread(new_id)
        assert paused["status"] == "paused" and paused["metadata"]["successor"] == t1.thread_id
        assert len(tm.store.list_messages(t1.thread_id)) == 2 and len(tm.store.list_messages(new_id)) == 2
        assert tm.current()["thread_id"] == t1.thread_id

    def test_auto_reopen_on_strong_match_never_merges(self, tm):
        t1 = _turn(tm, "swap the failing nvme in the zfs pool", assistant="Resilver running.")
        new_id = tm.new_thread("Samba share", "x", from_thread_id=t1.thread_id)
        _turn(tm, "add a samba share for the media folder")
        text = "the zfs resilver on the nvme finished"
        turn = tm.begin_turn(text, analyze_message(text), "s3")
        assert turn.decision.action == "reopen" and turn.thread_id == t1.thread_id
        assert tm.store.get_thread(new_id)["status"] == "paused"
        assert len(tm.store.list_messages(new_id)) == 2
```

- [ ] **Run it, expect failure:**
  `cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core && /Volumes/4TB-BAD/Halbert/.venv/bin/python -m pytest tests/test_threads.py tests/test_thread_store.py -q -p no:cacheprovider`
  Expected: `6 failed, 47 passed` — `AttributeError: 'ThreadManager' object has no attribute 'merge_back'` (3 tests), `AssertionError: assert 'paused' == 'merged'` (`test_resume_within_grace_merges`), and `AttributeError: 'SqliteConversationStore' object has no attribute 'merge_thread'` (both `TestMergeThread` tests). `test_resume_after_grace_reopens_without_merging`, `test_auto_reopen_on_strong_match_never_merges` and the edited `test_resume_thread` already pass against the A6b code.

- [ ] **Implement the store side.** In `conversation_sqlite.py`, insert immediately after the end of `search_snippets` (its last lines are `logger.warning(f"search_snippets {thread_id} failed: {e}")` / `return []`), before the `# session_somatic_blocks (C1 link)` comment block:

```python

    # ------------------------------------------------------------------
    # Merge-back (spec §5 "Merge")
    # ------------------------------------------------------------------

    def merge_thread(
        self, src_thread_id: str, dst_thread_id: str, *, now: Optional[float] = None
    ) -> Optional[int]:
        """Fold thread ``src`` into thread ``dst`` in one transaction.

        Moves every message row (and its ``messages_fts`` row) of ``src`` onto
        ``dst``; marks ``src`` ``merged`` (``merged_into = dst``, receipt
        dropped, ``receipts_fts`` row deleted); reopens ``dst`` (status open,
        ``paused_at`` cleared, ``turns_since_pause`` reset). Returns the number
        of rows moved, or ``None`` when either thread is missing or the write
        failed (nothing is left half-done).
        """
        if self._conn is None or not src_thread_id or src_thread_id == dst_thread_id:
            return None
        ts = float(now) if now is not None else time.time()
        try:
            with self._lock, self._conn:
                present = self._conn.execute(
                    "SELECT COUNT(*) FROM conversations WHERE id IN (?, ?)",
                    (src_thread_id, dst_thread_id),
                ).fetchone()[0]
                if int(present) != 2:
                    return None
                cur = self._conn.execute(
                    "UPDATE messages SET conversation_id = ? WHERE conversation_id = ?",
                    (dst_thread_id, src_thread_id),
                )
                moved = int(cur.rowcount or 0)
                if self._fts_ok:
                    self._conn.execute(
                        "UPDATE messages_fts SET conversation_id = ? WHERE conversation_id = ?",
                        (dst_thread_id, src_thread_id),
                    )
                    self._conn.execute(
                        "DELETE FROM receipts_fts WHERE thread_id = ?", (src_thread_id,)
                    )
                self._conn.execute(
                    """UPDATE conversations
                       SET status = 'merged', merged_into = ?, receipt = '',
                           receipt_updated_at = NULL, paused_at = NULL, updated_at = ?
                       WHERE id = ?""",
                    (dst_thread_id, ts, src_thread_id),
                )
                self._conn.execute(
                    """UPDATE conversations
                       SET status = 'open', paused_at = NULL, stale = 0,
                           turns_since_pause = 0, updated_at = ?
                       WHERE id = ?""",
                    (ts, dst_thread_id),
                )
            return moved
        except Exception as e:
            logger.warning(f"merge_thread {src_thread_id} -> {dst_thread_id} failed: {e}")
            return None
```

- [ ] **Implement the manager side** — edit `halbert_core/halbert_core/agents/threads.py`:

  1. In `begin_turn`, replace the reopen branch
     ```python
             elif decision.action == "reopen" and decision.target_thread_id:
                 if self.resume_thread(decision.target_thread_id, from_thread_id=previous_id):
                     thread_id = decision.target_thread_id
                 else:
                     thread_id = previous_id
     ```
     with
     ```python
             elif decision.action == "reopen" and decision.target_thread_id:
                 # Auto-reopen on a strong match is always a plain reopen: the open
                 # thread was a real subject of its own, so it is paused, not merged.
                 target = self.store.get_thread(decision.target_thread_id)
                 if target is not None and self._reopen_thread(target, previous_id, now):
                     thread_id = decision.target_thread_id
                 else:
                     thread_id = previous_id
     ```
  2. Replace the whole `resume_thread` method
     ```python
         def resume_thread(self, thread_id: str, *, from_thread_id: Optional[str]) -> bool:
             """Reopen a paused thread and pause ``from_thread_id``."""
             now = self._now()
             target = self.store.get_thread(thread_id)
             if target is None or target.get("status") != "paused":
                 return False
             if from_thread_id and from_thread_id != thread_id:
                 self._pause_thread(from_thread_id, now, successor=thread_id)
             meta = dict(target.get("metadata") or {})
             meta.pop("successor", None)
             return self.store.update_thread(
                 thread_id, status="open", paused_at=None, stale=False,
                 turns_since_pause=0, metadata=meta, updated_at=now,
             )
     ```
     with

```python
    def resume_thread(self, thread_id: str, *, from_thread_id: Optional[str]) -> bool:
        """Reopen a paused thread from ``from_thread_id`` (the model's ``resume_thread``).

        When ``from_thread_id`` was opened *from* ``thread_id`` and the grace
        window is still open, the split was spurious ("no, same topic"): the
        young thread is merged back (spec §5 "Merge") instead of being paused
        beside its predecessor. Otherwise this is a plain reopen that pauses
        ``from_thread_id``.
        """
        now = self._now()
        target = self.store.get_thread(thread_id)
        if target is None or target.get("status") != "paused":
            return False
        if from_thread_id and from_thread_id != thread_id:
            source = self.store.get_thread(from_thread_id)
            if source is not None and source.get("status") == "open":
                prev = self._paused_predecessor(source)
                if prev is not None and prev["thread_id"] == thread_id and self._within_grace(prev, source, now):
                    return self.merge_back(from_thread_id) == thread_id
        return self._reopen_thread(target, from_thread_id, now)

    def merge_back(self, new_thread_id: str) -> Optional[str]:
        """Fold a young open thread back into its paused predecessor (spec §5 "Merge").

        Applies only while the grace window is open (fewer than ``GRACE_TURNS``
        turns on the new thread and the predecessor's ``paused_at`` newer than
        ``GRACE_MINUTES``). Moves the new thread's rows onto the predecessor,
        marks the new thread ``merged`` (``merged_into`` set, receipt dropped,
        receipts_fts row deleted), reopens the predecessor and refreshes its
        receipt. Returns the predecessor id, or ``None`` when nothing merged.
        """
        now = self._now()
        new = self.store.get_thread(new_thread_id)
        if new is None or new.get("status") != "open":
            return None
        prev = self._paused_predecessor(new)
        if prev is None or not self._within_grace(prev, new, now):
            return None
        prev_id = prev["thread_id"]
        if self.store.merge_thread(new_thread_id, prev_id, now=now) is None:
            return None
        meta = dict(prev.get("metadata") or {})
        meta.pop("successor", None)
        meta["merged_from"] = list(meta.get("merged_from") or []) + [new_thread_id]
        recalled = list(prev.get("recalled_json") or [])
        seen = {e.get("thread_id") for e in recalled}
        recalled.extend(e for e in (new.get("recalled_json") or []) if e.get("thread_id") not in seen)
        last_active = max(float(prev.get("last_active") or 0.0), float(new.get("last_active") or 0.0))
        self.store.update_thread(
            prev_id,
            metadata=meta,
            recalled_json=recalled,
            topic_domains=sorted(set(prev.get("topic_domains") or []) | set(new.get("topic_domains") or [])),
            entities_json=sorted(set(prev.get("entities_json") or []) | set(new.get("entities_json") or [])),
            last_active=last_active or None,
            updated_at=now,
        )
        self._refresh_receipt(prev_id)
        logger.info(f"thread {new_thread_id} merged back into {prev_id}")
        return prev_id
```

  3. Insert immediately before the `_close_thread` method (i.e. after `_pause_thread`):

```python
    def _reopen_thread(self, target: Dict[str, Any], from_thread_id: Optional[str], now: float) -> bool:
        """Plain reopen: ``target`` becomes open and ``from_thread_id`` is paused beside it."""
        thread_id = target["thread_id"]
        if target.get("status") != "paused":
            return False
        if from_thread_id and from_thread_id != thread_id:
            self._pause_thread(from_thread_id, now, successor=thread_id)
        meta = dict(target.get("metadata") or {})
        meta.pop("successor", None)
        return self.store.update_thread(
            thread_id, status="open", paused_at=None, stale=False,
            turns_since_pause=0, metadata=meta, updated_at=now,
        )

    @staticmethod
    def _predecessor_id(thread: Dict[str, Any]) -> Optional[str]:
        """The thread this one was opened from (``_open_new_thread`` records it)."""
        meta = thread.get("metadata") or {}
        return meta.get("previous_thread_id") or thread.get("parent_thread_id") or None

    def _paused_predecessor(self, thread: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """The paused thread ``thread`` was opened from; else the most recently paused one."""
        prev_id = self._predecessor_id(thread)
        prev = self.store.get_thread(prev_id) if prev_id else None
        if prev is None:
            paused = [
                t for t in self.store.list_threads(status="paused", limit=50)
                if t.get("paused_at") is not None and t["thread_id"] != thread["thread_id"]
            ]
            prev = max(paused, key=lambda t: float(t["paused_at"]), default=None)
        if prev is None or prev.get("status") != "paused":
            return None
        return prev

    @staticmethod
    def _within_grace(paused: Dict[str, Any], successor: Dict[str, Any], now: float) -> bool:
        """True while ``paused`` may still be merged into (the inverse of ``tick``'s close rule)."""
        paused_at = paused.get("paused_at")
        if paused_at is None:
            return False
        turns = int(successor.get("turns_since_pause") or 0)
        return turns < GRACE_TURNS and (float(now) - float(paused_at)) < GRACE_MINUTES * 60

```

- [ ] **Run tests, expect PASS:**
  `cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core && /Volumes/4TB-BAD/Halbert/.venv/bin/python -m pytest tests/test_threads.py tests/test_thread_store.py -q -p no:cacheprovider`
  Expected: `53 passed` (22 threads, 31 store).

- [ ] **Commit:**
  ```
  cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation && git add halbert_core/halbert_core/agents/conversation_sqlite.py halbert_core/halbert_core/agents/threads.py halbert_core/tests/test_thread_store.py halbert_core/tests/test_threads.py && git commit -m "feat(agents): merge a spurious thread split back within the grace window

  SqliteConversationStore.merge_thread moves a thread's rows and FTS entries
  onto another thread in one transaction, marks the source merged
  (merged_into, receipt dropped, receipts_fts row deleted) and reopens the
  target. ThreadManager.merge_back applies it to a young thread and its
  paused predecessor while the grace window is open (< GRACE_TURNS turns,
  paused_at < GRACE_MINUTES), merging domains/entities/recalls and
  refreshing the receipt. resume_thread merges instead of reopening when the
  thread it is called from was opened from the target inside the window;
  the strong-match auto-reopen in begin_turn stays a plain reopen."
  ```

### Task A6d: Retraction notes — hidden system rows the next turn's hint surfaces

**Files:**
- Modify: `halbert_core/halbert_core/agents/threads.py` (`TurnContext`; `begin_turn`; `retract_recall`; `_history`; new `_pending_notes`)
- Test: `halbert_core/tests/test_threads.py` (append)
- `halbert_core/halbert_core/agents/thread_signals.py` is **not** touched here: A5 already ships `build_hint(..., notes=...)` and its tests (see the step below).

Spec §6: "a retracted recall is excluded from compaction and adds a system-origin observation the next PLANNING sees". A6b's `retract_recall` only flips the `recalled_json` status. Here it also appends a hidden system row (`origin='system'`, `visible_in_timeline=0`, content `admin retracted recall of '<title>'`) to the thread; `begin_turn` collects such rows newer than the last human row into `TurnContext.notes`, which `build_hint` (already shipped, A5) renders as `Note: …` lines inside `<continuity>`. Hidden rows never enter the timeline (`list_turns` filters `visible_in_timeline`), the history (`recent_messages` keeps human/assistant only) or the receipt's turn count.

- [ ] **Write the failing tests.** Append to `halbert_core/tests/test_threads.py`:

```python

class TestRetractionNotes:
    def _retracted(self, tm):
        t1 = _turn(tm, "add a samba share for the media folder", assistant="Added [media] at /srv/media.")
        tm.clock.advance(3 * 3600)
        t2 = _turn(tm, "check the disk space on /var")
        tm.clock.advance(31 * 60)
        assert tm.tick() == [t1.thread_id]
        text = "add another share like we did for the media one"
        turn3 = _turn(tm, text)
        assert turn3.recalled[0]["thread_id"] == t1.thread_id
        assert tm.retract_recall(t2.thread_id, t1.thread_id) is True
        return t1, t2, text

    def test_retract_appends_hidden_system_row(self, tm):
        t1, t2, _ = self._retracted(tm)
        rows = tm.store.list_messages(t2.thread_id)
        note = rows[-1]
        assert (note["role"], note["origin"], note["visible_in_timeline"]) == ("system", "system", False)
        assert note["content"] == "admin retracted recall of 'Add samba'" and note["timestamp"] == tm.clock.t
        assert all(t["origin"] != "system" for t in tm.store.list_turns())
        assert all(r["origin"] != "system" for r in tm.store.recent_messages(t2.thread_id))
        assert tm.retract_recall(t2.thread_id, t1.thread_id) is False
        assert len(tm.store.list_messages(t2.thread_id)) == len(rows)

    def test_begin_turn_collects_notes_until_next_human_row(self, tm):
        t1, t2, text = self._retracted(tm)
        turn4 = tm.begin_turn(text, analyze_message(text), "s4")
        assert turn4.thread_id == t2.thread_id and turn4.recalled == []
        assert turn4.notes == ["admin retracted recall of 'Add samba'"]
        assert "\nNote: admin retracted recall of 'Add samba'\n" in turn4.hint and "Pulled in" not in turn4.hint
        assert turn4.history[0]["role"] == "user"  # hidden rows never enter the history
        tm.end_turn(turn4, assistant_text="ok", blocks=[], terminal_session_ids=[], diff_proposals=[])
        turn5 = tm.begin_turn("continue", analyze_message("continue"), "s5")
        assert turn5.notes == [] and "Note:" not in turn5.hint
```

  **Nothing is inserted into `halbert_core/tests/test_thread_signals.py`.** A5's review round already added `test_notes_line` — the exact test this task specified — plus `test_notes_sit_between_the_recall_lines_and_the_notifications`, `test_hostile_notes_are_flattened` and `test_notes_never_cost_the_notification_or_the_recall_heads`, and all four pass against the shipped `build_hint`. Leave that file untouched.

- [ ] **Run it, expect failure:**
  `cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core && /Volumes/4TB-BAD/Halbert/.venv/bin/python -m pytest tests/test_threads.py tests/test_thread_signals.py -q -p no:cacheprovider`
  Expected: exactly **2 failures**, both of them the `test_threads.py` additions above — `test_retract_appends_hidden_system_row` (`'assistant' != 'system'`: the last row is still the assistant row) and `test_begin_turn_collects_notes_until_next_human_row` (`AttributeError: 'TurnContext' object has no attribute 'notes'`). `test_notes_line` passes already: A5 ships the `notes` keyword. (Counts are a target, not a measurement — trust the run.)

- [x] **`build_hint` notes — already implemented, do NOT re-apply.** `halbert_core/halbert_core/agents/thread_signals.py` shipped this in A5 (its review round): `build_hint(open_thread, decision, recalled, notifications, voice="first_person", *, now=None, notes: Optional[List[str]] = None)` renders each note as a `Note: <text>` line after the recall / "Earlier work" lines and before `Waiting for you`, and a fresh thread carrying only notes no longer returns `""`.

  The string replacements this task originally carried are **stale and harmful**: their anchors (`if turns == 0 and not recalled and not weak and not notifications:`, the `lines.append("Earlier work that may matter: " ...)` / `if notifications:` pair) no longer exist — notification assembly moved above the early return, and the body is composed from `head_line` / `recall_lines` / `weak_line` / `note_lines` / `notif_line`. Appending `Note:` lines straight into `lines` would also bypass the priority budget (`body_budget` / `free`), push the body past `HINT_MAX_CHARS` and hit the tail-truncation backstop that eats the `Waiting for you` line.

  What is in the tree instead: each note is capped at `NOTE_ITEM_MAX = 180` then rendered through `NOTE_LINE_MAX = 200`; at most `NOTES_MAX = 3` lines render, within a `NOTES_TOTAL_MAX = 300` char allowance; and the allowance is taken *after* reserving `RECALL_LINE_MIN + 1` per recall (or weak) line, so notes never cost a recall line its head or the notification line its place. Notes that do not fit are dropped whole rather than truncating the block.

- [ ] **Implement the manager side** — edit `halbert_core/halbert_core/agents/threads.py`:

  1. In `TurnContext`, after `    entities: List[str] = field(default_factory=list)` add:
     ```python
         #: system-origin rows newer than the last human row (e.g. a retracted recall)
         notes: List[str] = field(default_factory=list)
     ```
  2. In `begin_turn`, replace
     ```python
             if not history:
                 history = self._history(thread)
             try:
                 hint = build_hint(thread, decision, recalled, [], now=now)
     ```
     with
     ```python
             if not history:
                 history = self._history(thread)
             notes = self._pending_notes(thread_id)
             try:
                 hint = build_hint(thread, decision, recalled, [], now=now, notes=notes)
     ```
     and, in the `return TurnContext(...)` at the end of `begin_turn`, replace
     ```python
                 domains=list(signals.detected_domains or []),
                 entities=sorted(signals.entities or ()),
             )
     ```
     with
     ```python
                 domains=list(signals.detected_domains or []),
                 entities=sorted(signals.entities or ()),
                 notes=notes,
             )
     ```
  3. In `retract_recall`, replace the tail
     ```python
             if not changed:
                 return False
             return self.store.update_thread(thread_id, recalled_json=recalled)
     ```
     with
     ```python
             if not changed:
                 return False
             if not self.store.update_thread(thread_id, recalled_json=recalled):
                 return False
             title = next(
                 (e.get("title") or "" for e in recalled if e.get("thread_id") == recalled_thread_id), ""
             )
             # Hidden system row: the next begin_turn surfaces it as a "Note:" line
             # (spec §6 "adds a system-origin observation the next PLANNING sees").
             self.store.append_message(
                 thread_id, "system", f"admin retracted recall of '{title or recalled_thread_id}'",
                 origin="system", status="complete", timestamp=now, visible_in_timeline=False,
             )
             return True
     ```
  4. Replace the whole `_history` method
     ```python
         def _history(self, thread: Dict[str, Any]) -> List[Dict[str, Any]]:
             rows = self.store.recent_messages(thread["thread_id"], limit=HISTORY_ROWS)
             history = [{"role": r["role"], "content": r["content"]} for r in rows]
             receipt = thread.get("receipt") or ""
             if receipt and int(thread.get("message_count") or 0) > len(rows):
                 history.insert(0, {"role": "system", "content": f"[Earlier in this subject: {receipt}]"})
             return history
     ```
     with (hidden rows count in `message_count`, so "older turns exist" is now decided from the human/assistant rows themselves):
     ```python
         def _history(self, thread: Dict[str, Any]) -> List[Dict[str, Any]]:
             rows = self.store.recent_messages(thread["thread_id"], limit=HISTORY_ROWS + 1)
             older = len(rows) > HISTORY_ROWS
             history = [{"role": r["role"], "content": r["content"]} for r in rows[-HISTORY_ROWS:]]
             receipt = thread.get("receipt") or ""
             if receipt and older:
                 history.insert(0, {"role": "system", "content": f"[Earlier in this subject: {receipt}]"})
             return history

         def _pending_notes(self, thread_id: str) -> List[str]:
             """System-origin rows newer than the thread's last human row, oldest-first."""
             notes: List[str] = []
             for m in reversed(self.store.list_messages(thread_id)):
                 if m["origin"] == "human":
                     break
                 if m["origin"] == "system" and m.get("content"):
                     notes.append(m["content"])
             notes.reverse()
             return notes
     ```

- [ ] **Run tests, expect PASS:**
  `cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core && /Volumes/4TB-BAD/Halbert/.venv/bin/python -m pytest tests/test_threads.py tests/test_thread_signals.py -q -p no:cacheprovider`
  Expected: `58 passed` (24 threads, 34 signals — A5 closed at 34 after its review round; counts are targets, trust the run). Then the whole S set:
  `/Volumes/4TB-BAD/Halbert/.venv/bin/python -m pytest tests/test_threads.py tests/test_thread_signals.py tests/test_thread_store.py tests/test_receipt.py tests/test_intake_signals.py tests/test_conversation_sqlite.py tests/test_session_affinity.py -q -p no:cacheprovider`
  Expected: `182 passed` (24 threads, 34 signals, 31, 10, 50, 20, 13 — targets, trust the run). Then the full suite: `/Volumes/4TB-BAD/Halbert/.venv/bin/python -m pytest tests -q -p no:cacheprovider` — expected: 4 pre-existing failures only (test_tool_calling_bridge, test_phase_d_integration), everything else passes.

- [ ] **Commit:**
  ```
  cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation && git add halbert_core/halbert_core/agents/threads.py halbert_core/tests/test_threads.py && git commit -m "feat(agents): surface a retracted recall to the next turn as a hidden note

  retract_recall appends a system-origin row (visible_in_timeline=0,
  'admin retracted recall of <title>') to the thread; begin_turn collects
  system rows newer than the last human row into TurnContext.notes, which
  build_hint (already shipped in A5) renders as 'Note:' lines. Hidden rows
  never reach the timeline, the model history or the receipt turn count;
  _history now decides 'older turns exist' from human/assistant rows only."
  ```

**Contract additions (planner S — verifier please propagate):**
- `SqliteConversationStore`: new `create_thread(thread_id, title, *, status="open", title_source="provisional", created_at=None, parent_thread_id=None, metadata=None) -> bool`; `list_messages(thread_id, *, limit=None) -> list[dict]` (full rows: message_id, thread_id, role, content, timestamp, origin, status, turn_id, session_id, blocks, terminal_block_ids, diff_proposals, metadata, visible_in_timeline); `search_snippets(thread_id, query, limit=5) -> list[str]`; `mark_in_progress_interrupted() -> int`; `append_message` gains trailing kwarg `visible_in_timeline: bool = True`; `update_message` also accepts `thread_id` (moves the row and its FTS entry); `save()` returns `bool`; `SCHEMA_VERSION = 2` module constant. Thread dicts (`get_thread`/`list_threads`/`current_open_thread`) carry both `thread_id` and `id`, plus `message_count` and `turn_count`; flags (`stale`/`ephemeral`/`unread`) come back as 0/1 ints. `list_turns` returns exactly `limit` turns; the route (A11) should call with `limit + 1` to compute `has_more`.
- `search_receipts` score = `min(1, matched_terms / min(len(query_terms), 3))` (0.25 for an FTS hit with no verifiable term); stopwords are dropped from receipt queries (`_QUERY_STOPWORDS`); `decide()` passes `query + " " + sorted(entities)` so aliases apply at query time.
- `intake/signals.py`: `PAST_REF_RE`, `ANAPHORA_RE` (named groups `phrase`/`bare`), `_GENERIC_KEYWORDS` (domain keywords excluded from entities). Domain-list additions: `zfs`, `systemd`, `journalctl` were already present and were not duplicated.
- `receipt.py` also exports `receipt_one_liner(receipt) -> str`, `split_sentences`, `first_sentence`.
- `thread_signals.py`: `STRONG_MIN_SCORE = 0.5`, `HINT_MAX_CHARS = 900`, `relative_time(ts, now=None)`, `format_date(ts, now=None)`; `build_hint` gains keyword-only `now: float | None = None`. Extra rule: bare anaphora with no entities/domains makes the most recent paused/closed thread a strong candidate when its `last_active` ≥ the open thread's (paused → reopen, closed → stay + inject).
- `threads.py`: `TurnContext` gains `session_id: str = ""`, `previous_thread_id: str | None = None`, `domains: list[str]`, `entities: list[str]`; `ThreadManager.on_thread_closed: list[Callable[[dict], None]]`; paused threads record their successor in `metadata["successor"]`, new threads record `metadata["reason"]`/`metadata["previous_thread_id"]`; one-turn soft landing after a switch prepends a system row plus the previous thread's last 6 rows to `history`; the singleton reads `conversation_sqlite._DEFAULT_DB` at call time (monkeypatchable via `threads._cs`).
- `agents/session_affinity.py` is left untouched: `decide()` does not reuse its keyword scoring (it scores receipts, not messages). It is dead code on the thread path — Plan C cleanup candidate (its tests still pass against the updated fixture).
- (A1) `_ensure_schema` also creates `compact_boundaries(id INTEGER PK, thread_id TEXT, trigger TEXT, pre_tokens INTEGER, post_tokens INTEGER, preserved_message_ids TEXT json '[]', summary_message_id INTEGER, created_at REAL)` + `idx_compact_thread`. No writer exists in Plan A (spec §14: ships default-off); the tick hook for LLM compaction is a later plan.
- (A4) the `network` keyword list also contains `scanner`, so `scanner` is a canonical entity and a network-domain hit (spec §6). Titles like "Scanner share" are unaffected (titles are never re-analysed).
- (A6c) `SqliteConversationStore.merge_thread(src_thread_id, dst_thread_id, *, now=None) -> int | None`: one transaction — moves `messages` + `messages_fts` rows, deletes `src`'s `receipts_fts` row, sets `src` to `status='merged', merged_into=dst, receipt=''`, and reopens `dst` (`status='open', paused_at=NULL, stale=0, turns_since_pause=0`). Returns rows moved; `None` when a thread is missing / src == dst / the write failed.
- (A6c) `ThreadManager.merge_back(new_thread_id) -> str | None` folds an *open* thread into its paused predecessor while the grace window is open (`turns_since_pause < GRACE_TURNS` on the new thread and `now - paused_at < GRACE_MINUTES * 60`; the exact complement of `tick()`'s close rule). Predecessor lookup: `metadata["previous_thread_id"]` (what `_open_new_thread` records) → `parent_thread_id` column → the most recently paused thread. Domains, entities and `recalled_json` of the merged thread fold into the predecessor; `metadata["merged_from"]` lists merged ids; `last_active` becomes the newer of the two; the predecessor's receipt is rebuilt.
- (A6c) `ThreadManager.resume_thread(thread_id, *, from_thread_id)` (the model's tool) now **merges** when `from_thread_id` is open, was opened from `thread_id`, and the window is open; otherwise it is the plain reopen (pause `from_thread_id` with `metadata["successor"]`, reopen the target). The strong-match auto-reopen in `begin_turn` uses the internal `_reopen_thread` and never merges. Planner M: after a merging `resume_thread` returns `True`, the from-thread is `merged` and its rows — including the in-flight user row — already live on the target; setting `ctx.thread_id = target` and calling `end_turn(..., thread_id_override=target)` stays correct (`update_message(thread_id=target)` on an already-moved row is a no-op move).
- (A6d) `retract_recall` additionally appends a hidden row to the thread: `role='system', origin='system', status='complete', visible_in_timeline=0`, content `admin retracted recall of '<title>'`. `TurnContext.notes: list[str]` carries system-origin rows newer than the last human row (oldest-first); `build_hint(..., notes: list[str] | None = None)` — **shipped in A5, not in this task** — renders each as `Note: <text>` after the recall / "Earlier work" lines and before `Waiting for you`, capped (`NOTE_ITEM_MAX = 180`, `NOTE_LINE_MAX = 200`, `NOTES_MAX = 3` lines, `NOTES_TOTAL_MAX = 300` chars) and budgeted before the recall lines so they cannot cost the notification line its place; a fresh thread with notes no longer yields an empty hint. `_history` decides "older turns exist" from `recent_messages(limit=HISTORY_ROWS + 1)` rather than `message_count`, so hidden rows never trigger the receipt system row.
- (A6b) `tick()` closes on time/turn count only; the spec §5 "live terminal sessions keep a thread from auto-closing" guard is Plan B (noted in the docstring).
### Task A7: Thread events, StateContext thread fields, meta-tool schemas, SAFE classification

**Files:**
- Modify: `halbert_core/halbert_core/agents/events.py` (insert after `terminal_complete`, line 514, before `heartbeat`)
- Modify: `halbert_core/halbert_core/agents/states.py` (StateContext, after the `images` field, line 192)
- Modify: `halbert_core/halbert_core/tools/safety.py` (constant after `SafetyCheckResult` line 44; `classify` lines 307-320)
- Modify: `halbert_core/halbert_core/tools/executor.py` (the `from .safety import ...` line; the end of `_register_builtins`, after the `list_directory` registration; `execute`, directly after the unknown-tool `return ExecutionResult(...)` block)
- Test: `halbert_core/tests/test_thread_events_and_tools.py`

- [ ] **Step 1: Write the failing test**

```python
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Plan A / A7: thread SSE events, StateContext thread fields, the three
thread meta-tool schemas and their SAFE classification."""

import json
import pytest

from halbert_core.agents.events import StreamEvent
from halbert_core.agents.states import StateContext
from halbert_core.tools.safety import ToolSafetyFramework, RiskLevel, THREAD_META_TOOLS
from halbert_core.tools.executor import ToolExecutor


class TestThreadEvents:
    def test_thread_started_shape(self):
        d = StreamEvent.thread_started(
            "s1", "t2", "Scanner share", reason="new subject", previous_thread_id="t1"
        ).to_dict()
        assert d["type"] == "thread_started" and d["session_id"] == "s1"
        assert d["thread_id"] == "t2" and d["title"] == "Scanner share"
        assert d["reason"] == "new subject" and d["previous_thread_id"] == "t1"
        json.dumps(d)

    def test_thread_started_defaults(self):
        d = StreamEvent.thread_started("s1", "t2", "Untitled").to_dict()
        assert d["reason"] == "" and d["previous_thread_id"] is None

    def test_thread_recalled_shape_and_copies_terms(self):
        terms = ["samba", "share"]
        d = StreamEvent.thread_recalled("s1", "t9", "Samba media share", "2026-07-14", terms, "auto").to_dict()
        terms.append("x")
        assert d["type"] == "thread_recalled" and d["thread_id"] == "t9"
        assert d["title"] == "Samba media share" and d["date"] == "2026-07-14"
        assert d["match_terms"] == ["samba", "share"] and d["mode"] == "auto"
        assert d["last_turn_id"] is None
        json.dumps(d)

    def test_thread_recalled_carries_last_turn_id(self):
        d = StreamEvent.thread_recalled(
            "s1", "t9", "Samba media share", "2026-07-14", [], "tool", last_turn_id="turn-77"
        ).to_dict()
        assert d["last_turn_id"] == "turn-77" and d["mode"] == "tool"
        json.dumps(d)

    def test_thread_store_error_and_turn_persisted(self):
        e = StreamEvent.thread_store_error("s1", "disk full").to_dict()
        assert e["type"] == "thread_store_error" and e["message"] == "disk full"
        t = StreamEvent.turn_persisted("s1", "t2", "turn-abc").to_dict()
        assert t["type"] == "turn_persisted" and t["thread_id"] == "t2" and t["turn_id"] == "turn-abc"
        sse = StreamEvent.turn_persisted("s1", "t2", "turn-abc").to_sse()
        assert sse.startswith("data: ") and sse.endswith("\n\n")
        assert json.loads(sse[6:].strip())["turn_id"] == "turn-abc"


class TestStateContextThreadFields:
    def test_defaults_and_unshared_lists(self):
        a = StateContext(session_id="a", request_id="r", user_query="q")
        b = StateContext(session_id="b", request_id="r", user_query="q")
        assert a.thread_id is None and a.continuity_hint == ""
        assert a.thread_switched is False and a.thread_manager is None
        assert a.recalled_threads == [] and a.terminal_session_ids == []
        assert a.turn_context is None
        a.recalled_threads.append({"thread_id": "t"})
        a.terminal_session_ids.append("term-1")
        assert b.recalled_threads == [] and b.terminal_session_ids == []


class TestMetaToolSchemas:
    def test_registered_short_and_shaped(self):
        schemas = {s["function"]["name"]: s["function"] for s in ToolExecutor().get_schemas()}
        assert set(THREAD_META_TOOLS) == {"new_thread", "recall_thread", "resume_thread"}
        for name in THREAD_META_TOOLS:
            assert name in schemas
            assert len(schemas[name]["description"]) <= 60, name
        assert schemas["new_thread"]["parameters"]["required"] == ["title", "reason"]
        assert set(schemas["new_thread"]["parameters"]["properties"]) == {"title", "reason"}
        assert set(schemas["recall_thread"]["parameters"]["properties"]) == {"query", "thread_id"}
        assert schemas["recall_thread"]["parameters"]["required"] == []
        assert schemas["resume_thread"]["parameters"]["required"] == ["thread_id"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("name,args", [
        ("new_thread", {"title": "x", "reason": "y"}),
        ("recall_thread", {"query": "samba"}),
        ("resume_thread", {"thread_id": "t1"}),
    ])
    async def test_execute_is_an_inline_stub(self, name, args):
        result = await ToolExecutor().execute(name, args, session_id="s")
        assert result.success is True and result.result == "handled inline"
        assert result.requires_confirmation is False
        assert result.risk_level == RiskLevel.SAFE


class TestMetaToolSafety:
    @pytest.mark.parametrize("name", ["new_thread", "recall_thread", "resume_thread"])
    def test_meta_tools_are_safe(self, name):
        r = ToolSafetyFramework().classify(name, {})
        assert r.risk_level == RiskLevel.SAFE and r.allowed is True
        assert r.requires_confirmation is False

    def test_unknown_tool_still_medium(self):
        assert ToolSafetyFramework().classify("frobnicate", {}).risk_level == RiskLevel.MEDIUM
```

- [ ] **Step 2: Run it, expect an import failure**

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core && /Volumes/4TB-BAD/Halbert/.venv/bin/python -m pytest tests/test_thread_events_and_tools.py -q -p no:cacheprovider
```
Expected: `ImportError: cannot import name 'THREAD_META_TOOLS' from 'halbert_core.tools.safety'`.

- [ ] **Step 3: Event factories** — in `agents/events.py`, insert directly after the `terminal_complete` classmethod (ends line 514) and before `def heartbeat`:

```python
    # -------------------------------------------------------------------------
    # Thread events (Plan A: continuous conversation, spec §4/§6/§12)
    # -------------------------------------------------------------------------

    @classmethod
    def thread_started(
        cls,
        session_id: str,
        thread_id: str,
        title: str,
        reason: str = "",
        previous_thread_id: Optional[str] = None,
    ) -> 'StreamEvent':
        """A new (or resumed) hidden thread became the open one this turn."""
        return cls(
            type="thread_started",
            session_id=session_id,
            data={
                "thread_id": thread_id,
                "title": title,
                "reason": reason,
                "previous_thread_id": previous_thread_id,
            },
        )

    @classmethod
    def thread_recalled(
        cls,
        session_id: str,
        thread_id: str,
        title: str,
        date: str,
        match_terms: List[str],
        mode: str,
        last_turn_id: Optional[str] = None,
    ) -> 'StreamEvent':
        """An earlier thread's receipt was pulled into this turn.

        ``mode`` is ``"auto"`` (deterministic strong match at turn start) or
        ``"tool"`` (the model called ``recall_thread``). ``last_turn_id`` is
        the recalled thread's newest turn so the chip can scroll the timeline
        to it (spec §6); None when the store could not say.
        """
        return cls(
            type="thread_recalled",
            session_id=session_id,
            data={
                "thread_id": thread_id,
                "title": title,
                "date": date,
                "match_terms": list(match_terms or []),
                "mode": mode,
                "last_turn_id": last_turn_id,
            },
        )

    @classmethod
    def thread_store_error(cls, session_id: str, message: str) -> 'StreamEvent':
        """The conversation store failed; the turn continues without it."""
        return cls(type="thread_store_error", session_id=session_id, data={"message": message})

    @classmethod
    def turn_persisted(cls, session_id: str, thread_id: str, turn_id: str) -> 'StreamEvent':
        """The user row for this turn is on disk (status=in_progress)."""
        return cls(
            type="turn_persisted",
            session_id=session_id,
            data={"thread_id": thread_id, "turn_id": turn_id},
        )

```

- [ ] **Step 4: StateContext fields** — in `agents/states.py`, after
```python
    # Phase 4: Vision/image attachments (base64-encoded)
    images: Optional[List[str]] = None
```
insert:
```python

    # Plan A: hidden threads (spec §4, §7). session_id stays per turn;
    # thread_id is the hidden working buffer this turn's rows belong to.
    thread_id: Optional[str] = None
    continuity_hint: str = ""
    thread_switched: bool = False
    thread_manager: Optional[Any] = None
    recalled_threads: List[Dict[str, Any]] = field(default_factory=list)
    # Terminal sessions this turn's tools spawned (spawn payloads seen on the
    # terminal bridge); persisted on the assistant row at end_turn.
    terminal_session_ids: List[str] = field(default_factory=list)
    # The ThreadManager.TurnContext for this turn (None when no manager is
    # wired); end_turn needs it back.
    turn_context: Optional[Any] = None
```

- [ ] **Step 5: SAFE classification** — in `tools/safety.py`, after the `SafetyCheckResult` dataclass (line 44, before `class ToolSafetyFramework`) add:
```python
# Thread meta-tools (Plan A, spec §7). PLANNING handles them inline; they
# never reach the executor's handler path, but they are registered so the
# model sees their schemas and the safety framework never treats them as
# unknown (MEDIUM) tools.
THREAD_META_TOOLS = ("new_thread", "recall_thread", "resume_thread")


```
and in `classify`, directly before the final `else:` (after the `"Search operation"` branch) add:
```python
        elif tool_name in THREAD_META_TOOLS:
            return SafetyCheckResult(
                risk_level=RiskLevel.SAFE,
                allowed=True,
                requires_confirmation=False,
                reason="Conversation thread operation (handled inline)"
            )
```

- [ ] **Step 6: Schemas + execute stub** — in `tools/executor.py` change the `from .safety import ...` line to
```python
from .safety import ToolSafetyFramework, RiskLevel, SafetyCheckResult, THREAD_META_TOOLS
```
At the end of `_register_builtins` (after the `list_directory` registration closes) add:
```python

        # Thread meta-tools (Plan A, spec §7). The schemas are what the model
        # sees; PLANNING handles the calls inline and never dispatches them
        # here, so the handler is a stub (see execute()). Descriptions stay
        # under 60 characters on purpose.
        self.register(
            "new_thread",
            self._meta_tool_inline,
            {
                "name": "new_thread",
                "description": "Start a new subject; pauses the current one",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Short title for the new subject"},
                        "reason": {"type": "string", "description": "Why the subject changed"},
                    },
                    "required": ["title", "reason"],
                },
            },
        )
        self.register(
            "recall_thread",
            self._meta_tool_inline,
            {
                "name": "recall_thread",
                "description": "Find earlier subjects by query or thread id",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Words to search earlier subjects for"},
                        "thread_id": {"type": "string", "description": "A specific earlier thread id"},
                    },
                    "required": [],
                },
            },
        )
        self.register(
            "resume_thread",
            self._meta_tool_inline,
            {
                "name": "resume_thread",
                "description": "Return to a paused earlier subject",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "thread_id": {"type": "string", "description": "The paused thread to reopen"},
                    },
                    "required": ["thread_id"],
                },
            },
        )

    async def _meta_tool_inline(self, args: Dict) -> str:
        """Stub for the thread meta-tools; the state machine handles them."""
        return "handled inline"
```
In `execute`, directly after the `if tool_name not in self.tools: return ExecutionResult(... error=f"Unknown tool: {tool_name}" ...)` block add:
```python

        # Thread meta-tools never run here: PLANNING handles them inline
        # (spec §7). Reaching this branch means a caller bypassed PLANNING;
        # answer as a side-effect-free success with no audit entry.
        if tool_name in THREAD_META_TOOLS:
            return ExecutionResult(
                success=True,
                result="handled inline",
                execution_time_ms=0,
                risk_level=RiskLevel.SAFE,
            )
```

- [ ] **Step 7: Run the tests**

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core && /Volumes/4TB-BAD/Halbert/.venv/bin/python -m pytest tests/test_thread_events_and_tools.py tests/test_state_machine.py tests/test_tool_calling_bridge.py -q -p no:cacheprovider
```
Expected: `test_thread_events_and_tools.py` and `test_state_machine.py` PASS; `test_tool_calling_bridge.py` still shows exactly its 3 baseline failures (`TestLLMClientAdapterTools::*`, "No model configured").

- [ ] **Step 8: Commit**

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation && git add halbert_core/halbert_core/agents/events.py halbert_core/halbert_core/agents/states.py halbert_core/halbert_core/tools/safety.py halbert_core/halbert_core/tools/executor.py halbert_core/tests/test_thread_events_and_tools.py && git commit -m "feat(agents): thread events, context fields, and inline meta-tool schemas

thread_started / thread_recalled (carrying the recalled thread's
last_turn_id) / thread_store_error / turn_persisted factories on StreamEvent; StateContext carries thread_id, continuity
hint, recalled threads, spawned terminal ids and the turn context;
new_thread / recall_thread / resume_thread are registered as SAFE tools
whose executor path is a no-op stub (PLANNING handles them inline)."
```

### Task A8: Continuity hint and thread history in the agent prompts

**Files:**
- Modify: `halbert_core/halbert_core/prompts/agent_prompts.py` (constants + helpers after `LAYER_3_CONSTRAINTS` line 89; `build_planning_prompt` lines 194-251 replaced; `build_response_prompt` signature line 253-259 and the `prompt = f"""## Task` line 303 edited)
- Test: `halbert_core/tests/test_agent_prompts_continuity.py`

- [ ] **Step 1: Write the failing test**

```python
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Plan A / A8: the <continuity> hint and the thread history sit at the tail
of the PLANNING prompt and immediately before the query in RESPONDING."""

from halbert_core.prompts import AgentPromptBuilder

HINT = '<continuity>\nThread: "Scanner share" · 2 turns · last active 3 minutes ago.\n</continuity>'


class TestPlanningPrompt:
    def test_continuity_sits_immediately_before_current_task(self):
        p = AgentPromptBuilder().build_planning_prompt(query="add a share", context="ctx", plan=[], continuity=HINT)
        assert p.index(HINT) < p.index("## Current Task")
        between = p[p.index(HINT) + len(HINT):p.index("## Current Task")]
        assert between.strip() == ""
        assert p.rstrip().endswith("User request: add a share")

    def test_voice_preamble_precedes_hint(self):
        p = AgentPromptBuilder(voice="first_person").build_planning_prompt(query="q", context="", continuity=HINT)
        pre = AgentPromptBuilder.CONTINUITY_PREAMBLE["first_person"]
        assert pre in p and p.index(pre) < p.index(HINT)
        assert "recall_thread" in pre and "new_thread" in pre
        p2 = AgentPromptBuilder(voice="the_computer").build_planning_prompt(query="q", context="", continuity=HINT)
        assert AgentPromptBuilder.CONTINUITY_PREAMBLE["the_computer"] in p2 and pre not in p2

    def test_preamble_drops_the_tool_instruction_when_tools_are_rejected(self):
        # spec §7: "The instruction to call tools is omitted when the model has
        # rejected tool schemas" — the client reports that as tools_supported=False.
        b = AgentPromptBuilder(voice="first_person")
        p = b.build_planning_prompt(query="q", context="", continuity=HINT, tools_supported=False)
        no_tools = AgentPromptBuilder.CONTINUITY_PREAMBLE_NO_TOOLS["first_person"]
        assert no_tools in p and HINT in p and p.index(no_tools) < p.index(HINT)
        assert "recall_thread" not in p and "new_thread" not in p
        assert "one continuous conversation" in no_tools
        # None (unknown) and True keep the full preamble
        for supported in (None, True):
            p2 = b.build_planning_prompt(query="q", context="", continuity=HINT, tools_supported=supported)
            assert AgentPromptBuilder.CONTINUITY_PREAMBLE["first_person"] in p2
        r = b.build_response_prompt(query="q", context=[], observations=[], continuity=HINT, tools_supported=False)
        assert no_tools in r and "recall_thread" not in r
        for voice in ("first_person", "the_computer", "hybrid"):
            assert "recall_thread" not in AgentPromptBuilder.CONTINUITY_PREAMBLE_NO_TOOLS[voice]
            assert "new_thread" not in AgentPromptBuilder.CONTINUITY_PREAMBLE_NO_TOOLS[voice]
        p3 = AgentPromptBuilder(voice="the_computer").build_planning_prompt(
            query="q", context="", continuity=HINT, tools_supported=False
        )
        assert AgentPromptBuilder.CONTINUITY_PREAMBLE_NO_TOOLS["the_computer"] in p3 and no_tools not in p3

    def test_no_continuity_means_no_preamble_and_sections_precede_task(self):
        p = AgentPromptBuilder().build_planning_prompt(
            query="q", context="THE CONTEXT", observations=["saw x"],
            plan=[{"step": "look", "status": "completed"}],
        )
        assert "<continuity>" not in p and "recall_thread" not in p
        assert p.index("## Available Context") < p.index("## Current Task")
        assert p.index("## Previous Observations") < p.index("## Current Task")
        assert p.index("## Instructions") < p.index("## Current Task")
        assert "- saw x" in p and "1. ● look" in p


class TestResponsePrompt:
    def test_history_then_continuity_then_query(self):
        history = [
            {"role": "user", "content": "we set up samba last week"},
            {"role": "assistant", "content": "Yes, [media] at /srv/media."},
        ]
        p = AgentPromptBuilder().build_response_prompt(
            query="add scanner", context=[], observations=[], history=history, continuity=HINT,
        )
        assert p.index("## Earlier in this conversation") < p.index(HINT) < p.index("## Task")
        assert "**user**: we set up samba last week" in p
        assert "**assistant**: Yes, [media] at /srv/media." in p
        assert p.index("**user**") < p.index("**assistant**")

    def test_history_lines_are_one_line_capped_and_flattened(self):
        from halbert_core.agents.blocks import TextBlock
        p = AgentPromptBuilder().build_response_prompt(
            query="q", context=[], observations=[],
            history=[
                {"role": "user", "content": "x" * 2000},
                {"role": "assistant", "content": [TextBlock(text="flattened text")]},
                {"role": "system", "content": "[Earlier in this subject: Title: Samba]"},
                {"role": "user", "content": "line one\n\nline two"},
            ],
        )
        line = next(l for l in p.splitlines() if l.startswith("**user**: x"))
        assert len(line) == len("**user**: ") + 500 + 1 and line.endswith("…")
        assert "**assistant**: flattened text" in p
        assert "**system**: [Earlier in this subject: Title: Samba]" in p
        assert "**user**: line one line two" in p

    def test_no_history_no_continuity_unchanged_head(self):
        p = AgentPromptBuilder().build_response_prompt(query="q", context=[], observations=[])
        assert p.startswith("## Task\nAnswer this question: q")
        assert "## Earlier in this conversation" not in p and "<continuity>" not in p
```

- [ ] **Step 2: Run it, expect failure**

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core && /Volumes/4TB-BAD/Halbert/.venv/bin/python -m pytest tests/test_agent_prompts_continuity.py -q -p no:cacheprovider
```
Expected: `TypeError: AgentPromptBuilder.build_planning_prompt() got an unexpected keyword argument 'continuity'`.

- [ ] **Step 3: Continuity component** — in `prompts/agent_prompts.py`, directly after the `LAYER_3_CONSTRAINTS` string (line 89) add:

```python

    # Continuity component (spec §7), one preamble per voice. Rendered with
    # the <continuity> hint at the TAIL of the PLANNING message and right
    # before the query in RESPONDING: Ollama truncates the head of an
    # over-long prompt, so the newest, most specific context goes last.
    CONTINUITY_PREAMBLE = {
        "first_person": (
            "You have one continuous conversation with the admin. Your working "
            "context is the current subject. Earlier subjects listed below may "
            "matter; call `recall_thread` when one does. Call `new_thread` when "
            "the subject changes; a question you can answer in one reply does "
            "not need a new thread."
        ),
        "the_computer": (
            "This system has one continuous conversation with the admin. The "
            "working context is the current subject. Earlier subjects listed "
            "below may matter; call `recall_thread` when one does. Call "
            "`new_thread` when the subject changes; a question you can answer "
            "in one reply does not need a new thread."
        ),
        "hybrid": (
            "You have one continuous conversation with the admin. Your working "
            "context is the current subject. Earlier subjects listed below may "
            "matter; call `recall_thread` when one does. Call `new_thread` when "
            "the subject changes; a question you can answer in one reply does "
            "not need a new thread."
        ),
    }

    # The same component for a model that has rejected tool schemas
    # (model/client.py falls back to a no-tools retry and the client sets
    # tools_supported=False, A9d): the instruction to call recall_thread /
    # new_thread is omitted (spec §7) — the model cannot call anything.
    CONTINUITY_PREAMBLE_NO_TOOLS = {
        "first_person": (
            "You have one continuous conversation with the admin. Your working "
            "context is the current subject. Earlier subjects listed below may "
            "matter; use them when they do."
        ),
        "the_computer": (
            "This system has one continuous conversation with the admin. The "
            "working context is the current subject. Earlier subjects listed "
            "below may matter; use them when they do."
        ),
        "hybrid": (
            "You have one continuous conversation with the admin. Your working "
            "context is the current subject. Earlier subjects listed below may "
            "matter; use them when they do."
        ),
    }

    # Longest single history line rendered into the RESPONDING prompt.
    _HISTORY_LINE_CHARS = 500

    def _continuity_section(
        self, continuity: str, tools_supported: Optional[bool] = None
    ) -> List[str]:
        """The voice preamble + the hint as prompt lines; [] when no hint.

        ``tools_supported`` is the client's flag: False (the model rejected
        tool schemas) selects the preamble without the tool instruction;
        None (unknown) and True keep the full one.
        """
        if not continuity or not continuity.strip():
            return []
        table = (
            self.CONTINUITY_PREAMBLE_NO_TOOLS
            if tools_supported is False
            else self.CONTINUITY_PREAMBLE
        )
        preamble = table.get(self.voice, table["first_person"])
        return [preamble, continuity.strip()]

    @classmethod
    def _history_section(cls, history: Optional[List[Dict[str, Any]]]) -> str:
        """Thread history as one line per row, oldest first (spec §4.5).

        RESPONDING never saw the conversation before Plan A. Block-typed
        content is flattened; each line is capped at 500 characters.
        """
        if not history:
            return ""
        try:
            from ..agents.blocks import content_to_text
        except Exception:  # pragma: no cover - import cycle guard
            def content_to_text(content: Any) -> str:
                return content if isinstance(content, str) else str(content)
        lines = ["## Earlier in this conversation"]
        for row in history:
            if not isinstance(row, dict):
                continue
            role = str(row.get("role", "user"))
            if role not in ("user", "assistant", "system"):
                continue
            content = row.get("content", "")
            text = content if isinstance(content, str) else content_to_text(content)
            text = " ".join(str(text).split())
            if len(text) > cls._HISTORY_LINE_CHARS:
                text = text[:cls._HISTORY_LINE_CHARS] + "…"
            lines.append(f"**{role}**: {text}")
        return "\n".join(lines) if len(lines) > 1 else ""
```

- [ ] **Step 4: Replace `build_planning_prompt`** (lines 194-251) with:

```python
    def build_planning_prompt(
        self,
        query: str,
        context: str,
        plan: List[Dict] = None,
        observations: List[str] = None,
        continuity: str = "",
        tools_supported: Optional[bool] = None,
    ) -> str:
        """
        Build prompt for PLANNING state.

        Section order: context, observations, instructions, plan, then the
        continuity hint and finally ``## Current Task`` with the query. The
        task moved from the head to the tail on purpose (spec §7): if the
        prompt is ever truncated it is the head that goes, and the query and
        the hint are the two things the model must still see.
        ``tools_supported=False`` drops the tool instruction from the
        continuity preamble (spec §7).
        """
        parts: List[str] = []

        if context:
            parts.extend(["## Available Context", context, ""])

        if observations:
            parts.extend([
                "## Previous Observations",
                "\n".join(f"- {obs}" for obs in observations),
                "",
            ])

        parts.extend([
            "## Instructions",
            "1. Analyze what information is needed to answer this request",
            "2. Check if the available context already answers the question",
            "3. If more information is needed, use the appropriate tools",
            "4. Create a concise plan (maximum 5 steps)",
            "5. Execute one step at a time",
            "",
        ])

        if plan:
            parts.append("## Current Plan")
            for i, step in enumerate(plan):
                status = step.get("status", "pending")
                step_text = step.get("step", "")
                status_icon = {
                    "pending": "○",
                    "in_progress": "◐",
                    "completed": "●",
                    "failed": "✗"
                }.get(status, "○")
                parts.append(f"{i+1}. {status_icon} {step_text}")
            parts.append("")

        section = self._continuity_section(continuity, tools_supported)
        if section:
            parts.extend(section)
            parts.append("")

        parts.extend(["## Current Task", f"User request: {query}"])
        return "\n".join(parts)
```

- [ ] **Step 5: `build_response_prompt`** — change the signature
```python
        observations: List[str],
        confidence: float = None,
    ) -> str:
```
to
```python
        observations: List[str],
        confidence: float = None,
        history: Optional[List[Dict[str, Any]]] = None,
        continuity: str = "",
        tools_supported: Optional[bool] = None,
    ) -> str:
```
and replace the line `        prompt = f"""## Task` with:
```python
        # Thread history, then the continuity hint, immediately before the
        # query section (spec §4.5 / §7). Empty when neither is supplied so
        # the prompt is byte-identical to the pre-Plan-A shape.
        preface_parts: List[str] = []
        history_text = self._history_section(history)
        if history_text:
            preface_parts.append(history_text)
        preface_parts.extend(self._continuity_section(continuity, tools_supported))
        preface = ("\n\n".join(preface_parts) + "\n\n") if preface_parts else ""

        prompt = f"""{preface}## Task
```
(the rest of the f-string, from `Answer this question: {query}` to `Your response (use markdown formatting):"""`, is unchanged).

- [ ] **Step 6: Run the tests**

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core && /Volumes/4TB-BAD/Halbert/.venv/bin/python -m pytest tests/test_agent_prompts_continuity.py tests/test_agent_integration.py tests/test_conversation_status_wiring.py tests/test_phase_d_integration.py -q -p no:cacheprovider
```
Expected: the first three files PASS; `test_phase_d_integration.py` shows only its baseline failure `TestModelClientExtraction::test_get_configured_model_returns_string`.

- [ ] **Step 7: Commit**

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation && git add halbert_core/halbert_core/prompts/agent_prompts.py halbert_core/tests/test_agent_prompts_continuity.py && git commit -m "feat(prompts): continuity hint and thread history at the prompt tail

build_planning_prompt(continuity=) renders the voice preamble plus the
<continuity> hint immediately before '## Current Task', which now closes
the prompt; build_response_prompt(history=, continuity=) renders the
thread history and the hint right before the query. Ollama truncates the
head of a long prompt, so the query and hint live at the tail (spec §7).
tools_supported=False selects CONTINUITY_PREAMBLE_NO_TOOLS, the preamble
without the recall_thread / new_thread instruction (spec §7)."
```

### Task A8b: Conversation bucket for six raw turns, receipt slot in the assembler

**Files:**
- Modify: `halbert_core/halbert_core/intake/budget.py` (the `ModelTier.MEDIUM` and `ModelTier.LARGE` entries of `CONTEXT_BUDGETS`)
- Modify: `halbert_core/halbert_core/context/assembler.py` (`_format_conversation` replaced; two helpers inserted directly above it)
- Test: `halbert_core/tests/test_conversation_budget_receipt_slot.py`

Context for the engineer: spec §7 asks for three budget changes. (1) The conversation bucket at MEDIUM must hold six raw turns (12 rows of ~100 tokens); today it is 800 tokens and `should_summarize` (threshold: more than 10 non-system rows) compresses them anyway. (2) When the ThreadManager supplies a receipt, it arrives as the first history row, `{"role": "system", "content": "[Earlier in this subject: <receipt>]"}` (A6 `_history`). The assembler must render it as its own `## Earlier in this subject` block before the recent turns, outside the newest-first walk, and must not run `should_summarize` / `compress_conversation_history` over the remaining rows — those rows are the thread's last turns, already chosen by the manager, and summarising them again would only lose the detail the receipt was built to keep. (3) `num_ctx` is A10. The tier totals do not change: the other MEDIUM/LARGE buckets shrink to pay for the conversation bucket (`test_intake_budget.py::TestBudgetIntegrity` asserts the fields sum to the total).

- [ ] **Step 1: Write the failing test**

```python
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Plan A / A8b: the conversation bucket fits six raw turns at MEDIUM, and
the assembler renders a thread receipt in its own slot instead of
re-summarising the history it was already built from (spec §7)."""

from halbert_core.context.assembler import ContextAssembler
from halbert_core.intake.budget import CONTEXT_BUDGETS, ModelTier

RECEIPT = (
    "Title: Samba media share\nWhen: 2026-07-14..2026-07-14, 3 turns\n"
    "Started with: set up the samba share\nLast said: restarted smbd.\n"
    "Open loop: verify the mount."
)
RECEIPT_ROW = {"role": "system", "content": f"[Earlier in this subject: {RECEIPT}]"}
PAD = "and the samba config " * 18   # ~380 chars: a realistic ~100-token row


def _turns(n, pad=""):
    rows = []
    for i in range(n):
        rows.append({"role": "user", "content": f"user message number {i} about the share {pad}".strip()})
        rows.append({"role": "assistant", "content": f"assistant reply number {i} about the share {pad}".strip()})
    return rows


def _raw_lines(out):
    return [l for l in out.splitlines() if l.startswith("**user**") or l.startswith("**assistant**")]


class TestBudget:
    def test_medium_and_large_conversation_buckets(self):
        medium = CONTEXT_BUDGETS[ModelTier.MEDIUM]
        large = CONTEXT_BUDGETS[ModelTier.LARGE]
        assert medium.conversation == 1600 and medium.total == 2000
        assert large.conversation == 2400 and large.total == 4000

    def test_six_raw_turns_and_the_receipt_fit_at_medium(self):
        budget = CONTEXT_BUDGETS[ModelTier.MEDIUM].conversation
        out, tokens = ContextAssembler()._format_conversation([RECEIPT_ROW] + _turns(6, PAD), budget)
        assert len(_raw_lines(out)) == 12, out
        assert tokens <= budget
        # the old 800-token bucket could not hold them
        out_old, _ = ContextAssembler()._format_conversation([RECEIPT_ROW] + _turns(6, PAD), 800)
        assert len(_raw_lines(out_old)) < 12


class TestReceiptSlot:
    def test_receipt_row_renders_as_its_own_block_before_the_turns(self):
        out, tokens = ContextAssembler()._format_conversation([RECEIPT_ROW] + _turns(2), 4000)
        assert out.startswith("## Earlier in this subject\n"), out
        assert "Title: Samba media share" in out and "Open loop: verify the mount." in out
        assert "[Earlier in this subject:" not in out
        assert out.index("## Earlier in this subject") < out.index("## Recent Conversation")
        assert "**system**" not in out
        assert len(_raw_lines(out)) == 4 and tokens > 0

    def test_receipt_bypasses_summarisation_for_the_remaining_rows(self):
        rows = _turns(6)  # 12 rows: above should_summarize's threshold of 10
        out_with, _ = ContextAssembler()._format_conversation([RECEIPT_ROW] + rows, 8000)
        out_without, _ = ContextAssembler()._format_conversation(rows, 8000)
        assert len(_raw_lines(out_with)) == 12              # every row raw, oldest first
        assert _raw_lines(out_with)[0].startswith("**user**: user message number 0")
        assert len(_raw_lines(out_without)) < 12            # the old path still compresses
        assert "## Earlier in this subject" not in out_without

    def test_receipt_is_cut_to_fit_a_tiny_budget(self):
        out, tokens = ContextAssembler()._format_conversation([RECEIPT_ROW], 30)
        assert out.startswith("## Earlier in this subject\n")
        assert "Title: Samba" in out
        assert tokens <= 30

    def test_no_receipt_row_is_byte_identical_to_before(self):
        rows = _turns(2)
        out, tokens = ContextAssembler()._format_conversation(rows, 4000)
        assert out.startswith("## Recent Conversation\n")
        assert len(_raw_lines(out)) == 4 and tokens > 0
        assert ContextAssembler()._format_conversation([], 4000) == ("", 0)
        assert ContextAssembler()._format_conversation(rows, 0) == ("", 0)
```

- [ ] **Step 2: Run it, expect failures**

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core && /Volumes/4TB-BAD/Halbert/.venv/bin/python -m pytest tests/test_conversation_budget_receipt_slot.py -q -p no:cacheprovider
```
Expected: `4 failed, 1 passed` — `assert medium.conversation == 1600` fails (it is 800), `test_six_raw_turns_and_the_receipt_fit_at_medium` fails on `len(_raw_lines(out)) == 12` (the 12 rows are summarised to 6 and the receipt row is rendered as `**system**: …`), the three `TestReceiptSlot` receipt tests fail on `out.startswith("## Earlier in this subject\n")`; `test_no_receipt_row_is_byte_identical_to_before` passes.

- [ ] **Step 3: Budget** — in `intake/budget.py` replace the two entries

```python
    ModelTier.MEDIUM: ContextBudget(
        tier=ModelTier.MEDIUM, total=2000,
        system_identity=100, user_rules=100, retrieval=300,
        memory=225, discovery=200, conversation=800, observations=275,
    ),
    ModelTier.LARGE: ContextBudget(
        tier=ModelTier.LARGE, total=4000,
        system_identity=150, user_rules=150, retrieval=600,
        memory=450, discovery=400, conversation=1700, observations=550,
    ),
```
with
```python
    # Plan A (spec §7): the conversation bucket holds six raw turns (12 rows
    # of ~100 tokens) at MEDIUM and LARGE. Tier totals are unchanged; the
    # other buckets pay for it. The thread receipt lives inside this bucket
    # too (context/assembler.py renders it in its own slot).
    ModelTier.MEDIUM: ContextBudget(
        tier=ModelTier.MEDIUM, total=2000,
        system_identity=75, user_rules=50, retrieval=100,
        memory=50, discovery=50, conversation=1600, observations=75,
    ),
    ModelTier.LARGE: ContextBudget(
        tier=ModelTier.LARGE, total=4000,
        system_identity=125, user_rules=100, retrieval=400,
        memory=275, discovery=250, conversation=2400, observations=450,
    ),
```
(75+50+100+50+50+1600+75 = 2000; 125+100+400+275+250+2400+450 = 4000.)

- [ ] **Step 4: Receipt slot** — in `context/assembler.py` replace the whole of `_format_conversation` (from `    def _format_conversation(` through `        return result, tokens + header_tokens`) with the two helpers and the new method:

```python
    # The ThreadManager hands the thread receipt over as the leading system
    # row of the history (agents/threads.py _history). Plan A, spec §7.
    _RECEIPT_ROW_PREFIX = "[Earlier in this subject:"

    def _split_receipt_row(self, conversation: List[Dict]) -> tuple[str, List[Dict]]:
        """(receipt text, remaining rows).

        The text is empty unless the first row is the ThreadManager's
        ``[Earlier in this subject: …]`` system row.
        """
        if not conversation:
            return "", []
        first = conversation[0]
        if not isinstance(first, dict) or first.get("role") != "system":
            return "", list(conversation)
        text = content_to_text(first.get("content", ""))
        if not text.startswith(self._RECEIPT_ROW_PREFIX):
            return "", list(conversation)
        receipt = text[len(self._RECEIPT_ROW_PREFIX):].strip()
        if receipt.endswith("]"):
            receipt = receipt[:-1].rstrip()
        return receipt, list(conversation[1:])

    def _fit_to_tokens(self, text: str, max_tokens: int) -> str:
        """Shorten ``text`` (by characters) until it counts within ``max_tokens``."""
        if max_tokens <= 0:
            return ""
        while text and self.tokens.count(text) > max_tokens:
            text = text[: max(0, int(len(text) * 0.8))].rstrip()
        return text

    def _format_conversation(
        self,
        conversation: List[Dict],
        max_tokens: int
    ) -> tuple[str, int]:
        """Format conversation history within budget.

        Uses hierarchical summarization for long conversations (Phase 72):
        - Last 6 messages kept as raw text
        - Older messages summarized via extractive summary

        Plan A (spec §7): when the ThreadManager supplied a receipt as the
        leading ``[Earlier in this subject: …]`` system row, the receipt is
        rendered as its own ``## Earlier in this subject`` block before the
        recent turns, outside the newest-first walk, and the remaining rows
        are rendered raw: they are the thread's last turns, already chosen
        by the manager, and summarising them again would only lose the
        detail the receipt was built to keep.
        """
        if max_tokens <= 0:
            return "", 0

        receipt, conversation = self._split_receipt_row(conversation)
        receipt_block = ""
        receipt_tokens = 0
        if receipt:
            receipt_header = "## Earlier in this subject\n"
            body = self._fit_to_tokens(
                receipt, max_tokens - self.tokens.count(receipt_header) - 2
            )
            if body:
                receipt_block = receipt_header + body
                receipt_tokens = self.tokens.count(receipt_block)
        else:
            # Phase 72: Use conversation summarization for long chats
            try:
                from ..conversation.summarization import should_summarize, compress_conversation_history
                if should_summarize(conversation):
                    compressed_msgs, summary = compress_conversation_history(conversation)
                    if summary:
                        # Use compressed messages with summary prefix
                        conversation = compressed_msgs
            except ImportError:
                pass  # Fall back to simple truncation if summarization unavailable

        lines = []
        tokens = 0
        header = "## Recent Conversation\n"
        header_tokens = self.tokens.count(header)
        walk_budget = max_tokens - receipt_tokens

        # Work backwards from most recent
        for msg in reversed(conversation):
            role = msg.get("role", "user")
            # content may be a string (legacy) or a list of content blocks (A1)
            content = content_to_text(msg.get("content", ""))

            # Truncate very long messages
            if len(content) > 1000:
                content = content[:1000] + "..."

            line = f"**{role}**: {content}"
            line_tokens = self.tokens.count(line) + 1  # +1 for newline

            if tokens + line_tokens + header_tokens > walk_budget:
                break

            lines.insert(0, line)
            tokens += line_tokens

        if not lines and not receipt_block:
            return "", 0

        parts: List[str] = []
        if receipt_block:
            parts.append(receipt_block)
        if lines:
            parts.append(header + "\n".join(lines))
            tokens += header_tokens
        return "\n\n".join(parts), tokens + receipt_tokens
```

- [ ] **Step 5: Run the tests**

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core && /Volumes/4TB-BAD/Halbert/.venv/bin/python -m pytest tests/test_conversation_budget_receipt_slot.py tests/test_intake_budget.py tests/test_intake_pipeline.py tests/test_agent_integration.py tests/test_conversation_status_wiring.py -q -p no:cacheprovider
```
Expected: all PASS (`5 passed` from the new file; `TestBudgetIntegrity::test_fields_sum_to_total` still passes for every tier).

- [ ] **Step 6: Commit**

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation && git add halbert_core/halbert_core/intake/budget.py halbert_core/halbert_core/context/assembler.py halbert_core/tests/test_conversation_budget_receipt_slot.py && git commit -m "feat(context): six raw turns at MEDIUM and a receipt slot in the assembler

The conversation bucket is 1600 tokens at MEDIUM and 2400 at LARGE (tier
totals unchanged). When the ThreadManager supplies a receipt as the
leading '[Earlier in this subject: …]' system row, the assembler renders
it as its own block before the recent turns, outside the newest-first
walk, and skips should_summarize for the remaining rows (spec §7)."
```

### Task A9a: Turn lock, PLANNING inside the try, terminal ids on ctx, no memory.store_interaction

**Files:**
- Modify: `halbert_core/halbert_core/agents/state_machine.py` (`__init__` after line 161; `process` lines 191-262 replaced; `confirm_action` body lines 371-438; `_emit_somatic_block` lines 510-537; `_handle_planning` prompt call lines 648-652; `_run_tool_streaming` lines 958-1005; `_handle_responding` prompt call lines 1247-1251 and memory block lines 1301-1307; `_build_simple_planning_prompt` lines 1417-1421)
- Test: `halbert_core/tests/test_state_machine_turn_lock.py`

- [ ] **Step 1: Write the failing test**

```python
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Plan A / A9a: the turn lock serialises process() calls (a queued caller
sees conversation_status=waiting first), the initial PLANNING transition is
inside the try (a dead consumer or a bad transition still cleans up), a
superseded confirmation is ended as cancelled with a "not run — superseded"
block, terminal spawn ids land on the context, somatic events carry the
thread id, prompts receive continuity/history/tools_supported, and
memory.store_interaction is gone."""

import asyncio
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from halbert_core.agents.states import AgentState, StateContext
from halbert_core.agents.state_machine import AgentStateMachine
from halbert_core.agents.llm_client import LLMResponse
from halbert_core.streaming.terminal_bridge import get_terminal_event_bus
from halbert_core.tools import ToolExecutor, ToolSafetyFramework
from halbert_core.tools.executor import ExecutionResult


class _SlowLLM:
    """Answers directly, but sleeps inside chat() so two turns would
    interleave if nothing serialised them."""

    def __init__(self, log, delay=0.05):
        self.log = log
        self.delay = delay

    async def chat(self, messages, tools=None, **kwargs):
        self.log.append("chat-start")
        await asyncio.sleep(self.delay)
        self.log.append("chat-end")
        return LLMResponse(content="done", tool_calls=[], plan=[])

    async def stream(self, messages, **kwargs):
        await asyncio.sleep(self.delay)
        yield "done"


def _agent(llm, **kw):
    return AgentStateMachine(
        llm_client=llm, tool_executor=ToolExecutor(safety=ToolSafetyFramework()), max_loops=5, **kw,
    )


def _high_risk_llm():
    llm = AsyncMock()
    tc = MagicMock()
    tc.function.name = "run_command"
    tc.function.arguments = {"command": "systemctl restart sshd"}
    llm.chat = AsyncMock(return_value=MagicMock(content="", tool_calls=[tc], plan=None))
    return llm


class _RecordingThreadManager:
    """Only end_turn: what _supersede_paused_turn needs from a ThreadManager."""

    def __init__(self):
        self.ended = []

    def end_turn(self, turn, *, assistant_text, blocks, terminal_session_ids, diff_proposals,
                 status="complete", thread_id_override=None):
        self.ended.append(dict(
            turn=turn, assistant_text=assistant_text, blocks=blocks,
            terminal_session_ids=terminal_session_ids, diff_proposals=diff_proposals,
            status=status, thread_id_override=thread_id_override,
        ))


class TestTurnLock:
    @pytest.mark.asyncio
    async def test_two_concurrent_process_calls_serialise(self):
        log = []
        agent = _agent(_SlowLLM(log))
        assert isinstance(agent.turn_lock, asyncio.Lock)
        order = []

        async def run(sid):
            async for e in agent.process("hello", session_id=sid):
                if e.type in ("session_started", "session_ended"):
                    order.append((e.type, e.session_id))

        await asyncio.wait_for(asyncio.gather(run("A"), run("B")), timeout=5)
        assert order == [
            ("session_started", "A"), ("session_ended", "A"),
            ("session_started", "B"), ("session_ended", "B"),
        ]
        # chat() never overlapped: every start is followed by its own end.
        assert log and log == ["chat-start", "chat-end"] * (len(log) // 2)
        assert not agent.turn_lock.locked()
        assert agent.current_state == AgentState.IDLE

    @pytest.mark.asyncio
    async def test_lock_released_when_turn_pauses_and_new_message_supersedes(self):
        agent = _agent(_high_risk_llm())
        async for _ in agent.process("restart sshd", session_id="first"):
            pass
        assert agent.current_state == AgentState.AWAITING_CONFIRMATION
        assert "first" in agent.active_sessions
        assert not agent.turn_lock.locked()

        # A fresh turn must not raise "Invalid transition: AWAITING_CONFIRMATION -> PLANNING".
        agent.llm = _SlowLLM([], delay=0)
        types = [e.type async for e in agent.process("something else", session_id="second")]
        assert "session_ended" in types and "error" not in types
        assert "first" not in agent.active_sessions
        assert agent.current_state == AgentState.IDLE

    @pytest.mark.asyncio
    async def test_superseded_confirmation_is_recorded_on_the_receipt(self):
        # spec §5: a staged HIGH-risk command is auto-rejected when its turn is
        # superseded and the receipt records it as "not run — superseded".
        agent = _agent(_high_risk_llm())
        async for _ in agent.process("restart sshd", session_id="first"):
            pass
        assert agent.current_state == AgentState.AWAITING_CONFIRMATION
        paused = agent.active_sessions["first"]
        tm = _RecordingThreadManager()
        paused.thread_manager = tm
        paused.turn_context = object()   # what begin_turn hands back (A9c)

        agent.llm = _SlowLLM([], delay=0)
        async for _ in agent.process("something else", session_id="second"):
            pass
        assert len(tm.ended) == 1
        end = tm.ended[0]
        assert end["status"] == "cancelled" and end["assistant_text"] == ""
        assert end["terminal_session_ids"] == [] and end["diff_proposals"] == []
        assert end["thread_id_override"] is None
        assert end["blocks"] == [{
            "tool": "run_command", "args": {"command": "systemctl restart sshd"},
            "result": "not run — superseded", "exit": None, "status": "superseded",
        }]
        assert paused.turn_context is None          # ended once, never again
        assert "first" not in agent.active_sessions

    @pytest.mark.asyncio
    async def test_second_caller_sees_waiting_status_before_the_lock(self):
        # spec §12: a second /message during a turn is queued and emits
        # conversation_status: waiting.
        agent = _agent(_SlowLLM([], delay=0.2))
        first = agent.process("one", session_id="A")
        opened = await first.__anext__()
        assert opened.type == "session_started" and agent.turn_lock.locked()

        second_events = []

        async def run_b():
            async for e in agent.process("two", session_id="B"):
                second_events.append(e)

        task = asyncio.ensure_future(run_b())
        await asyncio.sleep(0.02)
        assert second_events, "B yielded nothing while A held the lock"
        assert second_events[0].type == "conversation_status"
        assert second_events[0].session_id == "B"
        assert second_events[0].data["status"] == "waiting"
        assert len(second_events) == 1              # nothing else until A releases the lock

        async for _ in first:
            pass
        await asyncio.wait_for(task, timeout=5)
        types = [e.type for e in second_events]
        assert types[:2] == ["conversation_status", "session_started"]
        assert "session_ended" in types and "error" not in types
        assert not agent.turn_lock.locked()

    @pytest.mark.asyncio
    async def test_state_resets_to_idle_when_the_consumer_disconnects(self):
        agent = _agent(_SlowLLM([], delay=0.3))

        async def consume():
            async for _ in agent.process("hello", session_id="gone"):
                pass

        task = asyncio.ensure_future(consume())
        await asyncio.sleep(0.05)  # inside PLANNING's chat()
        assert agent.current_state == AgentState.PLANNING
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not agent.turn_lock.locked()
        assert agent.current_state == AgentState.IDLE
        assert "gone" not in agent.active_sessions

    @pytest.mark.asyncio
    async def test_process_accepts_thread_kwargs(self):
        agent = _agent(_SlowLLM([], delay=0))
        async for _ in agent.process(
            "hi", session_id="kw", thread_id="t-1",
            continuity="<continuity>x</continuity>", thread_manager=None,
        ):
            pass
        assert agent.ctx.thread_id == "t-1"
        assert agent.ctx.continuity_hint == "<continuity>x</continuity>"


class TestPromptWiring:
    @pytest.mark.asyncio
    async def test_prompts_receive_continuity_and_history(self):
        prompts = MagicMock()
        prompts.build_planning_prompt = MagicMock(return_value="plan")
        prompts.build_response_prompt = MagicMock(return_value="respond")
        agent = _agent(_SlowLLM([], delay=0), prompt_builder=prompts)
        history = [{"role": "user", "content": "earlier"}]
        async for _ in agent.process(
            "now", session_id="pw", conversation_history=history,
            continuity="<continuity>hint</continuity>",
        ):
            pass
        assert prompts.build_planning_prompt.call_args.kwargs["continuity"] == "<continuity>hint</continuity>"
        assert prompts.build_planning_prompt.call_args.kwargs["tools_supported"] is None
        rk = prompts.build_response_prompt.call_args.kwargs
        assert rk["continuity"] == "<continuity>hint</continuity>"
        assert rk["history"] == history
        assert rk["tools_supported"] is None

    @pytest.mark.asyncio
    async def test_prompts_receive_tools_supported_from_the_client(self):
        prompts = MagicMock()
        prompts.build_planning_prompt = MagicMock(return_value="plan")
        prompts.build_response_prompt = MagicMock(return_value="respond")
        llm = _SlowLLM([], delay=0)
        llm.tools_supported = False   # set by the client after a no-tools fallback (A9d)
        agent = _agent(llm, prompt_builder=prompts)
        async for _ in agent.process("now", session_id="ts"):
            pass
        assert prompts.build_planning_prompt.call_args.kwargs["tools_supported"] is False
        assert prompts.build_response_prompt.call_args.kwargs["tools_supported"] is False

    def test_simple_planning_prompt_carries_the_hint(self):
        agent = _agent(_SlowLLM([], delay=0))
        agent.ctx = StateContext(
            session_id="s", request_id="r", user_query="q", continuity_hint="<continuity>h</continuity>",
        )
        p = agent._build_simple_planning_prompt("ctx")
        assert p.index("<continuity>h</continuity>") < p.index("User query: q")


class TestTerminalSessionIds:
    @pytest.mark.asyncio
    async def test_spawn_payloads_are_collected_once_on_ctx(self):
        agent = _agent(_SlowLLM([], delay=0))
        agent.ctx = StateContext(session_id="term", request_id="r", user_query="ls")

        async def fake_execute(tool_name, args, session_id=None, confirmed=False):
            bus = get_terminal_event_bus()
            bus.publish(session_id, {"kind": "spawn", "terminal_session_id": "t-1", "command": "ls", "pid": 1})
            bus.publish(session_id, {"kind": "output", "terminal_session_id": "t-1", "data": "a\n"})
            bus.publish(session_id, {"kind": "spawn", "terminal_session_id": "t-1", "command": "ls", "pid": 1})
            bus.publish(session_id, {"kind": "complete", "terminal_session_id": "t-1", "exit_code": 0})
            return ExecutionResult(success=True, result="a")

        agent.tools.execute = fake_execute
        sink = []
        events = [e async for e in agent._run_tool_streaming("run_command", {"command": "ls"}, False, sink)]
        assert agent.ctx.terminal_session_ids == ["t-1"]
        assert [e.type for e in events].count("terminal_spawn") == 2
        assert sink[0].success is True


class TestNoMemoryStoreInteraction:
    @pytest.mark.asyncio
    async def test_store_interaction_is_never_called(self):
        memory = MagicMock()
        memory.recall = AsyncMock(return_value=[])
        memory.store_interaction = AsyncMock()
        agent = _agent(_SlowLLM([], delay=0), memory_service=memory)
        async for _ in agent.process("what is my hostname?", session_id="mem"):
            pass
        memory.store_interaction.assert_not_awaited()
        assert agent.ctx.response_chunks == ["done"]


class TestSomaticThreadId:
    @pytest.mark.asyncio
    async def test_somatic_block_event_carries_thread_id_or_session_id(self):
        # spec §8: somatic blocks are tagged with the hidden thread; the SSE
        # session_id stays per turn for routing.
        agent = _agent(_SlowLLM([], delay=0))
        block = SimpleNamespace(
            block_type="finding", id="blk-1", status="active", session_id="som",
            finding_id="f1", proposal_id=None, approval_request_id=None,
            action_id=None, reflection_id=None,
        )
        agent.ctx = StateContext(session_id="som", request_id="r", user_query="q", thread_id="t-42")
        event = await agent._emit_somatic_block(block)
        assert event.type == "somatic_block" and event.session_id == "som"
        assert event.data["thread_id"] == "t-42" and event.data["block_id"] == "blk-1"
        agent.ctx.thread_id = None
        assert (await agent._emit_somatic_block(block)).data["thread_id"] == "som"
```

- [ ] **Step 2: Run it, expect failures**

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core && /Volumes/4TB-BAD/Halbert/.venv/bin/python -m pytest tests/test_state_machine_turn_lock.py -q -p no:cacheprovider
```
Expected: `AttributeError: 'AgentStateMachine' object has no attribute 'turn_lock'`, `TypeError: process() got an unexpected keyword argument 'thread_id'`, `ValueError: Invalid transition: AgentState.AWAITING_CONFIRMATION → AgentState.PLANNING`, `KeyError: 'tools_supported'`, `KeyError: 'thread_id'` (somatic), and `assert_not_awaited` failing.

- [ ] **Step 3: Create the lock in `__init__`** — after `self.cancelled: Dict[str, bool] = {}` add:
```python

        # One turn at a time (spec §12): held for the whole of process() and
        # confirm_action(), including their cleanup. A second /message during
        # a turn waits here instead of the route force-resetting the machine.
        self.turn_lock = asyncio.Lock()
```

- [ ] **Step 4: Replace `process()`** (from `async def process(` through the end of its `finally:` block, lines 191-262) with:

```python
    async def process(
        self,
        query: str,
        session_id: str = None,
        user_id: str = None,
        conversation_history: List[Dict] = None,
        images: List[str] = None,
        thread_id: str = None,
        continuity: str = "",
        thread_manager=None,
    ) -> AsyncIterator[StreamEvent]:
        """
        Process a user query through the state machine.

        Yields StreamEvents for real-time frontend updates.

        Args:
            query: User's question/request
            session_id: Optional session ID (generated if not provided)
            user_id: Optional user ID
            conversation_history: Previous messages in conversation
            images: Optional base64 images for the vision model
            thread_id: Hidden thread this turn belongs to (Plan A); the
                ThreadManager overrides it when one is wired
            continuity: The <continuity> hint for this turn ("" when none)
            thread_manager: ThreadManager that persists the turn (may be None)
        """
        session_id = session_id or str(uuid.uuid4())
        request_id = str(uuid.uuid4())

        # A second /message during a live turn queues on the lock (the
        # route no longer force-resets the machine, A11). Tell the UI it
        # is waiting before blocking (spec §12: "emits conversation_status:
        # waiting"); the status is the plain string the badge expects.
        if self.turn_lock.locked():
            logger.info(f"Session {session_id} waiting for the current turn to finish")
            yield StreamEvent.conversation_status(
                session_id, "waiting", waiting_for="previous turn"
            )

        # One turn at a time (spec §12). Everything below, including the
        # finally, runs under the lock; asyncio.Lock is not task-bound, so
        # releasing it from the generator's cleanup is fine whichever task
        # drives the last step.
        async with self.turn_lock:
            self._supersede_paused_turn(session_id)

            # Initialize context
            self.ctx = StateContext(
                session_id=session_id,
                request_id=request_id,
                user_query=query,
                user_id=user_id,
                conversation_history=conversation_history or [],
                max_loops=self.max_loops,
                images=images,
                thread_id=thread_id,
                continuity_hint=continuity or "",
                thread_manager=thread_manager,
            )

            # Phase 3: Run intake pipeline before cognitive tick
            if self.intake is not None:
                try:
                    self.ctx.intake = self.intake.analyze(query)
                    logger.info(
                        f"Intake: intent={self.ctx.intake.intent}, "
                        f"complexity={self.ctx.intake.complexity_score}, "
                        f"model={self.ctx.intake.recommended_model}"
                    )
                except Exception as e:
                    logger.warning(f"Intake pipeline failed (non-fatal): {e}")

            # Phase D: Inject persona cognition if tick is wired
            if self.cognition_tick is not None:
                try:
                    from ..integrations.cognition_wiring import get_cognition
                    self.ctx.persona_cognition = get_cognition()
                except Exception as e:
                    logger.warning(f"Could not inject persona cognition: {e}")

            # Track active session
            self.active_sessions[session_id] = self.ctx

            logger.info(f"Starting agent processing: session={session_id}, query={query[:100]}")

            yield StreamEvent.session_started(session_id, request_id)

            try:
                # Inside the try (spec §12): an invalid transition, an
                # exception in a handler or a consumer that goes away
                # mid-turn must all reach the cleanup below, otherwise the
                # machine is stranded mid-state and the next turn cannot
                # start.
                yield await self._transition(AgentState.PLANNING)
                async for event in self._drive():
                    yield event
            finally:
                self._settle_turn(session_id)

    def _supersede_paused_turn(self, session_id: str) -> None:
        """A new message while a turn waits on a confirmation abandons it.

        The route used to force-reset the machine (routes/agent.py); now the
        machine settles itself. The staged HIGH-risk action is never run;
        when the paused turn was persisted (it carries a TurnContext) it is
        ended as ``cancelled`` with one block recording the action as
        "not run — superseded" so the receipt's Commands line carries it
        (spec §5). Any session left in active_sessions by a previous turn
        is evicted with it.
        """
        if self.current_state == AgentState.IDLE and not self.active_sessions:
            return
        for sid in list(self.active_sessions):
            old_ctx = self.active_sessions.pop(sid, None)
            if sid != session_id:
                logger.info(
                    f"Superseding session {sid} left in "
                    f"{self.current_state.value} by a new message"
                )
            self._record_superseded_turn(old_ctx)
        self.current_state = AgentState.IDLE

    def _record_superseded_turn(self, old_ctx: Optional[StateContext]) -> None:
        """End a superseded, persisted turn so its receipt records the
        staged action (spec §5). No manager or no TurnContext: nothing to do.
        Never raises."""
        if old_ctx is None:
            return
        tm = getattr(old_ctx, "thread_manager", None)
        turn = getattr(old_ctx, "turn_context", None)
        if tm is None or turn is None:
            return
        old_ctx.turn_context = None   # ended here, never again
        pending = old_ctx.pending_confirmation or {}
        blocks: List[Dict[str, Any]] = []
        if pending:
            args = pending.get("args")
            if not isinstance(args, dict):
                last = old_ctx.tool_calls[-1] if old_ctx.tool_calls else None
                args = last.args if last is not None and isinstance(last.args, dict) else {}
            blocks.append({
                "tool": str(pending.get("tool", "")),
                "args": args,
                "result": "not run — superseded",
                "exit": None,
                "status": "superseded",
            })
        try:
            tm.end_turn(
                turn,
                assistant_text="",
                blocks=blocks,
                terminal_session_ids=[],
                diff_proposals=[],
                status="cancelled",
            )
        except Exception as e:
            logger.warning(f"end_turn for a superseded turn failed (non-fatal): {e}")

    def _settle_turn(self, session_id: str) -> None:
        """Cleanup shared by process() and confirm_action().

        A turn paused on AWAITING_CONFIRMATION keeps its session so
        confirm_action() can find it. Anything else is over: the machine
        returns to IDLE (also after a mid-turn exception or disconnect,
        which used to strand it in PLANNING and break the next turn) and
        the session is evicted.
        """
        if self.current_state == AgentState.AWAITING_CONFIRMATION:
            return
        self.current_state = AgentState.IDLE
        self.active_sessions.pop(session_id, None)
        self.cancelled.pop(session_id, None)
```

- [ ] **Step 5: Lock `confirm_action()`** — its body (everything after the docstring, from `if session_id not in self.active_sessions:` to the end of the `finally:` block, lines 371-438) is wrapped: insert the line `        async with self.turn_lock:` directly after the docstring and indent the whole existing body one level (4 spaces) under it. The three early `return`s stay as they are (returning inside `async with` releases the lock). Then replace the (now indented) final
```python
            finally:
                # The paused session was kept in active_sessions only so this
                # method could find it. Evict it now unless the machine paused
                # again on another confirmation.
                if (session_id in self.active_sessions
                        and self.current_state != AgentState.AWAITING_CONFIRMATION):
                    del self.active_sessions[session_id]
```
with
```python
            finally:
                self._settle_turn(session_id)
```

- [ ] **Step 6: Pass the hint/history/tools_supported to the prompts** — `tools_supported` is the client's flag (None until a model rejects tool schemas; A9d sets it to False on `LLMClientAdapter` and `OllamaClient`), read with `getattr` so any client works. In `_handle_planning` change the `build_planning_prompt(` call to
```python
            prompt = self.prompts.build_planning_prompt(
                query=self.ctx.user_query,
                context=context_content,
                plan=[p.to_dict() for p in self.ctx.plan],
                continuity=self.ctx.continuity_hint,
                # False once the client fell back to a no-tools retry (spec
                # §7): the preamble then omits the tool instruction.
                tools_supported=getattr(self.llm, "tools_supported", None),
            )
```
in `_handle_responding` change the `build_response_prompt(` call to
```python
            prompt = self.prompts.build_response_prompt(
                query=self.ctx.user_query,
                context=self.ctx.retrieved_context,
                observations=self.ctx.observations,
                history=self.ctx.conversation_history,
                continuity=self.ctx.continuity_hint,
                tools_supported=getattr(self.llm, "tools_supported", None),
            )
```
and in `_build_simple_planning_prompt` replace
```python
        parts = [
            f"User query: {self.ctx.user_query}",
            "",
```
with
```python
        parts = []
        if self.ctx.continuity_hint:
            parts.extend([self.ctx.continuity_hint, ""])
        parts += [
            f"User query: {self.ctx.user_query}",
            "",
```

- [ ] **Step 7: Remove `memory.store_interaction`** — in `_handle_responding` replace
```python
        # Store interaction in memory (clean text, no invocation JSON)
        if self.memory:
            await self.memory.store_interaction(
                query=self.ctx.user_query,
                response=clean_response,
                session_id=self.ctx.session_id
            )
```
with
```python
        # Not stored in memory here any more (spec §7): thread receipts, and
        # the Haloysius line written when a thread closes, replace
        # memory.store_interaction. Storing every Q/A made each turn a global
        # memory that leaked into unrelated threads.
```

- [ ] **Step 8: Collect terminal ids** — add this method directly above `_run_tool_streaming` (after `_terminal_event`):
```python
    def _note_terminal_payload(self, payload: Dict[str, Any]) -> None:
        """Remember every terminal this turn spawned (persisted at end_turn)."""
        if payload.get("kind") != "spawn":
            return
        terminal_id = str(payload.get("terminal_session_id", ""))
        if terminal_id and terminal_id not in self.ctx.terminal_session_ids:
            self.ctx.terminal_session_ids.append(terminal_id)

```
then inside `_run_tool_streaming` replace
```python
                if getter in done:
                    event = self._terminal_event(self.ctx.session_id, getter.result())
```
with
```python
                if getter in done:
                    payload = getter.result()
                    self._note_terminal_payload(payload)
                    event = self._terminal_event(self.ctx.session_id, payload)
```
and
```python
            while not queue.empty():
                event = self._terminal_event(self.ctx.session_id, queue.get_nowait())
```
with
```python
            while not queue.empty():
                payload = queue.get_nowait()
                self._note_terminal_payload(payload)
                event = self._terminal_event(self.ctx.session_id, payload)
```

- [ ] **Step 8b: Somatic blocks carry the thread id** — in `_emit_somatic_block` replace
```python
            action_id=block.action_id,
            reflection_id=block.reflection_id,
        )
        try:
            from ..proactive.events import ProactiveEvent, get_event_bus
            pe = ProactiveEvent.create(
                type="somatic_block",
                severity="info",
                title=f"Block {event.data['block_type']}: {event.data['status']}",
                body=f"session={block.session_id} block={block.id}",
            )
```
with
```python
            action_id=block.action_id,
            reflection_id=block.reflection_id,
            # Somatic blocks are tagged with the hidden thread (spec §8);
            # the event's session_id stays per turn for routing. Before a
            # thread exists (no manager) the turn's session id stands in.
            thread_id=self.ctx.thread_id or self.ctx.session_id,
        )
        try:
            from ..proactive.events import ProactiveEvent, get_event_bus
            pe = ProactiveEvent.create(
                type="somatic_block",
                severity="info",
                title=f"Block {event.data['block_type']}: {event.data['status']}",
                body=(
                    f"session={block.session_id} "
                    f"thread={self.ctx.thread_id or self.ctx.session_id} block={block.id}"
                ),
            )
```
(`StreamEvent.somatic_block` passes extra kwargs through into `data`, so no factory change is needed. `SqliteConversationStore.add_somatic_block` / `session_somatic_blocks` has no caller anywhere in the worktree — `grep -rn "add_somatic_block(" halbert_core/halbert_core` prints only its definition — so there is no call site to repoint; when one is added it must pass `ctx.thread_id or ctx.session_id` as the first argument.)

- [ ] **Step 9: Run the tests**

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core && /Volumes/4TB-BAD/Halbert/.venv/bin/python -m pytest tests/test_state_machine_turn_lock.py tests/test_state_machine.py tests/test_agent_integration.py tests/test_conversation_status_wiring.py tests/test_subagent_wiring.py tests/test_tool_calling_bridge.py -q -p no:cacheprovider
```
Expected: everything PASS except the 3 baseline `TestLLMClientAdapterTools` failures.

- [ ] **Step 10: Commit**

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation && git add halbert_core/halbert_core/agents/state_machine.py halbert_core/tests/test_state_machine_turn_lock.py && git commit -m "feat(agents): turn lock, settled cleanup, terminal ids on the context

process() and confirm_action() run under AgentStateMachine.turn_lock;
the initial PLANNING transition is inside the try so a disconnect or a
bad transition still returns the machine to IDLE; a new message
supersedes a turn paused on confirmation instead of the route forcing a
reset; spawn payloads on the terminal bridge are recorded on
ctx.terminal_session_ids; prompts receive the continuity hint, the
thread history and the client's tools_supported flag; a queued second
message emits conversation_status=waiting before blocking; a superseded
confirmation is ended as cancelled with a 'not run — superseded' block;
somatic block events carry the thread id; memory.store_interaction is
removed from the agent path."
```

### Task A9b: Inline meta-tools in PLANNING (new_thread / recall_thread / resume_thread)

**Files:**
- Modify: `halbert_core/halbert_core/agents/state_machine.py` (imports lines 18-20; `TRANSITIONS[PLANNING]` lines 77-81; `_handle_planning` routing block at `if hasattr(response, 'tool_calls') and response.tool_calls:`; new `_handle_meta_tool` directly after `_already_called`)
- Test: `halbert_core/tests/test_state_machine_meta_tools.py`

- [ ] **Step 1: Write the failing test**

```python
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Plan A / A9b: new_thread / recall_thread / resume_thread are handled
inline in PLANNING: no tool card, no loop increment, PLANNING re-runs once."""

import pytest

from halbert_core.agents.states import AgentState, StateContext
from halbert_core.agents.state_machine import AgentStateMachine
from halbert_core.agents.llm_client import LLMResponse, ToolCall, FunctionCall
from halbert_core.tools import ToolExecutor, ToolSafetyFramework


class _FakeStore:
    """Only list_messages: what _last_turn_id needs from the store."""

    def __init__(self, rows_by_thread):
        self.rows = rows_by_thread

    def list_messages(self, thread_id, *, limit=None):
        return list(self.rows.get(thread_id, []))


class _FakeThreadManager:
    def __init__(self, recall_results=None, resume_ok=True, store=None):
        self.calls, self.recall_results, self.resume_ok = [], recall_results or [], resume_ok
        self.store = store

    def new_thread(self, title, reason, *, from_thread_id):
        self.calls.append(("new_thread", title, reason, from_thread_id))
        return "t-new"

    def recall(self, query=None, thread_id=None, *, exclude_thread_id=None):
        self.calls.append(("recall", query, thread_id, exclude_thread_id))
        return list(self.recall_results)

    def resume_thread(self, thread_id, *, from_thread_id):
        self.calls.append(("resume_thread", thread_id, from_thread_id))
        return self.resume_ok


class _ScriptedLLM:
    def __init__(self, responses):
        self.responses, self.prompts = list(responses), []

    async def chat(self, messages, tools=None, **kwargs):
        self.prompts.append(messages[-1]["content"])
        return self.responses.pop(0) if self.responses else LLMResponse(content="answer", tool_calls=[], plan=[])

    async def stream(self, messages, **kwargs):
        yield "answer"


def _call(name, **args):
    return LLMResponse(content="", tool_calls=[ToolCall(id="c1", function=FunctionCall(name=name, arguments=args))])


def _agent(llm):
    return AgentStateMachine(llm_client=llm, tool_executor=ToolExecutor(safety=ToolSafetyFramework()), max_loops=5)


def _planning(llm, tm, thread_id="t-open", **kw):
    agent = _agent(llm)
    agent.ctx = StateContext(session_id="s", request_id="r", user_query="now scanner share", thread_id=thread_id, **kw)
    agent.ctx.thread_manager = tm
    agent.current_state = AgentState.PLANNING
    return agent


RECALLED = {"thread_id": "t-9", "title": "Samba media share", "date": "2026-07-14",
            "receipt": "Title: Samba media share\nCommands: testparm (exit 0)",
            "matching_messages": ["added [media]"], "match_terms": ["samba", "share"]}


@pytest.mark.asyncio
async def test_new_thread_emits_thread_started_and_reenters_planning_without_loop_increment():
    tm = _FakeThreadManager()
    agent = _planning(_ScriptedLLM([_call("new_thread", title="Scanner share", reason="topic changed")]), tm,
                      thread_id="t-old", conversation_history=[{"role": "user", "content": "old"}])
    events = [e async for e in agent._handle_planning()]
    assert [e.type for e in events] == ["thread_started", "state_change"]
    assert events[0].data == {"thread_id": "t-new", "title": "Scanner share", "reason": "topic changed", "previous_thread_id": "t-old"}
    assert events[1].data["state"] == "planning" and events[1].data["previous_state"] == "planning"
    assert agent.ctx.loop_count == 0
    assert agent.ctx.thread_id == "t-new" and agent.ctx.thread_switched is True
    assert agent.ctx.conversation_history == [] and "Scanner share" in agent.ctx.continuity_hint
    assert tm.calls == [("new_thread", "Scanner share", "topic changed", "t-old")]


@pytest.mark.asyncio
async def test_second_new_thread_in_a_turn_is_a_noop_that_reflects():
    tm = _FakeThreadManager()
    agent = _planning(_ScriptedLLM([_call("new_thread", title="Again", reason="r")]), tm, thread_id="t-new")
    agent.ctx.thread_switched = True
    events = [e async for e in agent._handle_planning()]
    assert [e.type for e in events] == ["state_change"] and events[0].data["state"] == "reflecting"
    assert tm.calls == [] and agent.ctx.loop_count == 0


@pytest.mark.asyncio
async def test_full_turn_reenters_planning_exactly_once():
    tm = _FakeThreadManager()
    llm = _ScriptedLLM([_call("new_thread", title="Scanner share", reason="r")])
    agent = _agent(llm)
    events = [e async for e in agent.process("now scanner share", session_id="s-full", thread_id="t-old", thread_manager=tm)]
    types = [e.type for e in events]
    reentries = [e for e in events if e.type == "state_change" and e.data["state"] == "planning" and e.data["previous_state"] == "planning"]
    assert len(reentries) == 1 and types.count("thread_started") == 1
    assert "response_complete" in types and "session_ended" in types and "tool_start" not in types
    assert agent.ctx.loop_count <= 1
    assert any("Scanner share" in p for p in llm.prompts[1:])  # the second PLANNING pass saw the new hint


@pytest.mark.asyncio
async def test_store_failure_emits_thread_store_error_and_still_switches():
    tm = _FakeThreadManager()

    def boom(title, reason, *, from_thread_id):
        raise RuntimeError("db locked")

    tm.new_thread = boom
    agent = _planning(_ScriptedLLM([_call("new_thread", title="T", reason="r")]), tm, thread_id="t-old")
    events = [e async for e in agent._handle_planning()]
    assert [e.type for e in events] == ["thread_store_error", "thread_started", "state_change"]
    assert "db locked" in events[0].data["message"]
    assert agent.ctx.thread_switched is True and agent.ctx.thread_id != "t-old"
    # No manager at all still switches in memory.
    agent2 = _planning(_ScriptedLLM([_call("new_thread", title="T", reason="r")]), None, thread_id="t-old")
    assert [e.type async for e in agent2._handle_planning()] == ["thread_started", "state_change"]


@pytest.mark.asyncio
async def test_recall_injects_receipt_emits_thread_recalled_and_repeat_reflects():
    tm = _FakeThreadManager(
        recall_results=[RECALLED],
        store=_FakeStore({"t-9": [{"turn_id": "turn-a"}, {"turn_id": "turn-b"}, {"turn_id": None}]}),
    )
    agent = _planning(_ScriptedLLM([_call("recall_thread", query="samba share"), _call("recall_thread", query="samba share")]), tm)
    events = [e async for e in agent._handle_planning()]
    assert [e.type for e in events] == ["thread_recalled", "state_change"]
    assert events[0].data["thread_id"] == "t-9" and events[0].data["mode"] == "tool"
    assert events[0].data["match_terms"] == ["samba", "share"]
    assert events[0].data["last_turn_id"] == "turn-b"   # newest row with a turn_id
    assert tm.calls == [("recall", "samba share", None, "t-open")]
    assert agent.ctx.retrieved_context[0]["source"] == "thread" and "testparm" in agent.ctx.retrieved_context[0]["content"]
    assert agent.ctx.recalled_threads[0]["thread_id"] == "t-9"
    assert agent.ctx.loop_count == 0 and agent.ctx.thread_switched is False
    second = [e async for e in agent._handle_planning()]
    assert second[-1].data["state"] == "reflecting" and len(tm.calls) == 1


@pytest.mark.asyncio
async def test_recall_without_a_store_has_no_last_turn_id():
    tm = _FakeThreadManager(recall_results=[RECALLED])          # no .store
    agent = _planning(_ScriptedLLM([_call("recall_thread", query="samba share")]), tm)
    events = [e async for e in agent._handle_planning()]
    assert events[0].type == "thread_recalled" and events[0].data["last_turn_id"] is None
    # a recall result that already names its last turn wins over the store
    tm2 = _FakeThreadManager(recall_results=[dict(RECALLED, last_turn_id="turn-given")],
                             store=_FakeStore({"t-9": [{"turn_id": "turn-store"}]}))
    agent2 = _planning(_ScriptedLLM([_call("recall_thread", query="samba share")]), tm2)
    events2 = [e async for e in agent2._handle_planning()]
    assert events2[0].data["last_turn_id"] == "turn-given"


@pytest.mark.asyncio
async def test_recall_with_no_match_is_a_normal_observation():
    agent = _planning(_ScriptedLLM([_call("recall_thread", query="nothing")]), _FakeThreadManager(recall_results=[]))
    events = [e async for e in agent._handle_planning()]
    assert [e.type for e in events] == ["state_change"] and events[0].data["state"] == "planning"
    assert any("No earlier thread matched" in o for o in agent.ctx.observations)


@pytest.mark.asyncio
async def test_resume_switches_thread_and_injects_receipt():
    tm = _FakeThreadManager(recall_results=[{"thread_id": "t-paused", "title": "NAS setup", "date": "2026-06-30",
                                             "receipt": "Title: NAS setup", "matching_messages": [], "match_terms": []}])
    agent = _planning(_ScriptedLLM([_call("resume_thread", thread_id="t-paused")]), tm)
    events = [e async for e in agent._handle_planning()]
    assert [e.type for e in events] == ["thread_started", "state_change"]
    assert events[0].data == {"thread_id": "t-paused", "title": "NAS setup", "reason": "resumed", "previous_thread_id": "t-open"}
    assert ("resume_thread", "t-paused", "t-open") in tm.calls
    assert agent.ctx.thread_id == "t-paused" and agent.ctx.thread_switched is True
    assert agent.ctx.conversation_history[0]["role"] == "system" and "NAS setup" in agent.ctx.conversation_history[0]["content"]


@pytest.mark.asyncio
async def test_resume_failure_keeps_the_open_thread():
    agent = _planning(_ScriptedLLM([_call("resume_thread", thread_id="t-none")]), _FakeThreadManager(resume_ok=False))
    events = [e async for e in agent._handle_planning()]
    assert [e.type for e in events] == ["state_change"]
    assert agent.ctx.thread_id == "t-open" and agent.ctx.thread_switched is False
    assert any("Could not resume" in o for o in agent.ctx.observations)
```

- [ ] **Step 2: Run it, expect failures**

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core && /Volumes/4TB-BAD/Halbert/.venv/bin/python -m pytest tests/test_state_machine_meta_tools.py -q -p no:cacheprovider
```
Expected: `assert ['state_change'] == ['thread_started', 'state_change']` (PLANNING routes `new_thread` to EXECUTING today) and `ValueError: Invalid transition: AgentState.PLANNING → AgentState.PLANNING`.

- [ ] **Step 3: Import and PLANNING → PLANNING** — after `from ..streaming.terminal_bridge import get_terminal_event_bus` add
```python
from ..tools.safety import THREAD_META_TOOLS
```
and change the PLANNING entry of `TRANSITIONS` to
```python
        AgentState.PLANNING: [
            AgentState.SEARCHING, AgentState.READING,
            AgentState.EXECUTING, AgentState.REFLECTING,
            AgentState.RESPONDING, AgentState.ERROR,
            # Re-entry after an inline thread meta-tool (Plan A, spec §7).
            AgentState.PLANNING,
        ],
```

- [ ] **Step 4: Route meta-tools before `_already_called`** — in `_handle_planning` replace
```python
            tool_args = tool_call.function.arguments

            if self._already_called(tool_name, tool_args):
```
with
```python
            tool_args = tool_call.function.arguments

            if tool_name in THREAD_META_TOOLS:
                # Handled inline (spec §7): mutate the context, emit
                # thread_started / thread_recalled, run PLANNING once more
                # with the new hint. No tool card, no loop increment. The
                # identical call twice in a turn teaches the model nothing,
                # so it reflects instead; that also stops PLANNING→PLANNING
                # repeating forever.
                if self._already_called(tool_name, tool_args):
                    logger.info(f"PLANNING: {tool_name} already handled this turn")
                    self.ctx.add_observation(
                        f"{tool_name} was already handled this turn; answer with what you have."
                    )
                    yield await self._transition(AgentState.REFLECTING)
                    return
                async for event in self._handle_meta_tool(tool_name, tool_args or {}):
                    yield event
                if self.ctx.tool_calls and self.ctx.tool_calls[-1].name == tool_name:
                    yield await self._transition(AgentState.PLANNING)
                else:
                    # Nothing recorded: the call was a no-op (a second
                    # new_thread), so there is nothing new to plan on.
                    yield await self._transition(AgentState.REFLECTING)
                return

            if self._already_called(tool_name, tool_args):
```

- [ ] **Step 5: Add `_last_turn_id` and `_handle_meta_tool`** directly after `_already_called`:

```python
    def _last_turn_id(self, thread_id: Optional[str]) -> Optional[str]:
        """The newest turn_id of ``thread_id``, for thread_recalled (spec §6:
        the chip click scrolls the timeline to it). None without a store,
        without rows, or when the store fails."""
        store = getattr(self.ctx.thread_manager, "store", None)
        if store is None or not thread_id:
            return None
        try:
            rows = store.list_messages(thread_id)
        except Exception as e:
            logger.debug(f"last turn lookup for {thread_id} failed (non-fatal): {e}")
            return None
        for row in reversed(list(rows or [])):
            turn_id = row.get("turn_id") if isinstance(row, dict) else None
            if turn_id:
                return str(turn_id)
        return None

    async def _handle_meta_tool(
        self, tool_name: str, tool_args: Dict[str, Any]
    ) -> AsyncIterator[StreamEvent]:
        """Handle new_thread / recall_thread / resume_thread inline (spec §7).

        Records the call on ``ctx.tool_calls`` (status success, no event) so
        PLANNING's repeat guard can see it. A ``new_thread`` after the turn
        already switched is a no-op and records nothing.
        """
        tm = self.ctx.thread_manager
        sid = self.ctx.session_id
        args = dict(tool_args or {})

        def _record() -> None:
            self.ctx.add_tool_call(ToolCall(
                id=str(uuid.uuid4())[:8], name=tool_name, args=args,
                status="success", result="handled inline",
                started_at=time.time(), completed_at=time.time(),
            ))

        if tool_name == "new_thread":
            if self.ctx.thread_switched:
                self.ctx.add_observation(
                    "new_thread was already handled this turn; continue with the current subject."
                )
                return
            title = " ".join(str(args.get("title") or "").split())[:60]
            if not title:
                title = " ".join(self.ctx.user_query.split())[:60] or "Untitled"
            reason = str(args.get("reason") or "")
            previous = self.ctx.thread_id
            new_id: Optional[str] = None
            if tm is not None:
                try:
                    new_id = tm.new_thread(title, reason, from_thread_id=previous)
                except Exception as e:
                    logger.warning(f"new_thread store failure (non-fatal): {e}")
                    yield StreamEvent.thread_store_error(sid, f"new_thread: {e}")
            if not new_id:
                # No store (or it failed): the turn still switches subject
                # in memory so the model's decision is honoured.
                new_id = str(uuid.uuid4())
            self.ctx.thread_id = new_id
            self.ctx.thread_switched = True
            self.ctx.conversation_history = []
            self.ctx.continuity_hint = (
                f'<continuity>\nThread: "{title}" · opened just now.\n</continuity>'
            )
            self.ctx.add_observation(f'Started a new subject: "{title}".')
            _record()
            yield StreamEvent.thread_started(
                sid, new_id, title, reason=reason, previous_thread_id=previous
            )
            return

        if tool_name == "recall_thread":
            query = str(args.get("query") or "").strip() or None
            thread_id = str(args.get("thread_id") or "").strip() or None
            results: List[Dict[str, Any]] = []
            if tm is not None:
                try:
                    results = list(tm.recall(
                        query=query, thread_id=thread_id, exclude_thread_id=self.ctx.thread_id,
                    ) or [])
                except Exception as e:
                    logger.warning(f"recall_thread store failure (non-fatal): {e}")
                    yield StreamEvent.thread_store_error(sid, f"recall_thread: {e}")
            _record()
            if not results:
                self.ctx.add_observation("No earlier thread matched.")
                return
            names = []
            for r in results[:3]:
                rid = str(r.get("thread_id", ""))
                rtitle = str(r.get("title", ""))
                rdate = str(r.get("date", ""))
                self.ctx.recalled_threads.append(r)
                self.ctx.add_context(
                    source="thread",
                    content=str(r.get("receipt", "")),
                    metadata={
                        "thread_id": rid, "title": rtitle, "date": rdate,
                        "match_terms": list(r.get("match_terms") or []),
                        "matching_messages": list(r.get("matching_messages") or []),
                    },
                )
                names.append(f'"{rtitle}" ({rdate})')
                yield StreamEvent.thread_recalled(
                    sid, rid, rtitle, rdate, list(r.get("match_terms") or []), mode="tool",
                    last_turn_id=r.get("last_turn_id") or self._last_turn_id(rid),
                )
            self.ctx.add_observation(
                "Recalled earlier subjects: " + "; ".join(names)
                + ". Their receipts are in the available context."
            )
            return

        if tool_name == "resume_thread":
            target = str(args.get("thread_id") or "").strip()
            ok = False
            if tm is not None and target:
                try:
                    ok = bool(tm.resume_thread(target, from_thread_id=self.ctx.thread_id))
                except Exception as e:
                    logger.warning(f"resume_thread store failure (non-fatal): {e}")
                    yield StreamEvent.thread_store_error(sid, f"resume_thread: {e}")
            if not ok:
                _record()
                self.ctx.add_observation(
                    f"Could not resume thread {target or '(none)'}; continuing with the current subject."
                )
                return
            previous = self.ctx.thread_id
            title, receipt = "", ""
            try:
                found = list(tm.recall(thread_id=target) or [])
            except Exception as e:
                logger.warning(f"recall after resume failed (non-fatal): {e}")
                found = []
            if found:
                title = str(found[0].get("title", ""))
                receipt = str(found[0].get("receipt", ""))
            self.ctx.thread_id = target
            self.ctx.thread_switched = True
            self.ctx.conversation_history = (
                [{"role": "system", "content": f"[Earlier in this subject: {receipt}]"}] if receipt else []
            )
            if receipt:
                self.ctx.add_context(
                    source="thread", content=receipt,
                    metadata={"thread_id": target, "title": title, "resumed": True},
                )
            self.ctx.continuity_hint = (
                f'<continuity>\nThread: "{title or target}" · resumed just now.\n</continuity>'
            )
            self.ctx.add_observation(f'Resumed the earlier subject "{title or target}".')
            _record()
            yield StreamEvent.thread_started(
                sid, target, title, reason="resumed", previous_thread_id=previous
            )
            return
```

- [ ] **Step 6: Run the tests**

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core && /Volumes/4TB-BAD/Halbert/.venv/bin/python -m pytest tests/test_state_machine_meta_tools.py tests/test_state_machine_turn_lock.py tests/test_state_machine.py tests/test_tool_calling_bridge.py -q -p no:cacheprovider
```
Expected: all PASS except the 3 baseline `TestLLMClientAdapterTools` failures. (The fake manager has no `begin_turn` until A9c adds that call; A9c wraps it in try/except so `test_full_turn_reenters_planning_exactly_once` keeps passing afterwards.)

- [ ] **Step 7: Commit**

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation && git add halbert_core/halbert_core/agents/state_machine.py halbert_core/tests/test_state_machine_meta_tools.py && git commit -m "feat(agents): handle thread meta-tools inline in PLANNING

new_thread / recall_thread / resume_thread mutate the context, emit
thread_started / thread_recalled (or thread_store_error) and re-enter
PLANNING once with the new hint: no tool card, no loop increment. The
same call twice in a turn reflects instead of re-entering. thread_recalled
carries the recalled thread's newest turn_id so the chip can scroll to it."
```

### Task A9c: begin_turn / end_turn wiring (turn_persisted, auto-recall, persistence in finally)

**Files:**
- Modify: `halbert_core/halbert_core/agents/state_machine.py` (`process()`: the `yield StreamEvent.session_started(...)` line and the try's `finally:`; `confirm_action()` `finally:`; new methods after `_settle_turn`)
- Test: `halbert_core/tests/test_state_machine_turn_persistence.py`

- [ ] **Step 1: Write the failing test**

```python
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Plan A / A9c: process() calls ThreadManager.begin_turn after taking the
lock, seeds the context from the TurnContext, emits turn_persisted (and
thread_recalled for auto recalls), and calls end_turn in its finally."""

import asyncio
import pytest
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

from halbert_core.agents.states import AgentState
from halbert_core.agents.state_machine import AgentStateMachine
from halbert_core.agents.llm_client import LLMResponse, ToolCall, FunctionCall
from halbert_core.streaming.terminal_bridge import get_terminal_event_bus
from halbert_core.tools import ToolExecutor, ToolSafetyFramework
from halbert_core.tools.executor import ExecutionResult


@dataclass
class _Turn:
    thread_id: str
    turn_id: str
    user_message_id: Optional[int]
    history: List[Dict[str, Any]]
    hint: str
    recalled: List[Dict[str, Any]] = field(default_factory=list)
    decision: Any = None


class _FakeThreadManager:
    def __init__(self, hint="", history=None, recalled=None, fail_begin=False):
        self.hint, self.history, self.recalled, self.fail_begin = hint, history or [], recalled or [], fail_begin
        self.begun, self.ended = [], []

    def begin_turn(self, query, signals, session_id):
        if self.fail_begin:
            raise RuntimeError("db locked")
        self.begun.append((query, signals, session_id))
        return _Turn("t-open", f"turn-{len(self.begun)}", 1, list(self.history), self.hint, list(self.recalled))

    def end_turn(self, turn, *, assistant_text, blocks, terminal_session_ids, diff_proposals, status="complete", thread_id_override=None):
        self.ended.append(dict(turn=turn, assistant_text=assistant_text, blocks=blocks, terminal_session_ids=terminal_session_ids,
                               diff_proposals=diff_proposals, status=status, thread_id_override=thread_id_override))

    def new_thread(self, title, reason, *, from_thread_id):
        return "t-new"

    def recall(self, query=None, thread_id=None, *, exclude_thread_id=None):
        return []

    def resume_thread(self, thread_id, *, from_thread_id):
        return False


class _LLM:
    def __init__(self, responses=None, delay=0.0):
        self.responses, self.delay = list(responses or []), delay

    async def chat(self, messages, tools=None, **kwargs):
        await asyncio.sleep(self.delay)
        return self.responses.pop(0) if self.responses else LLMResponse(content="answer", tool_calls=[], plan=[])

    async def stream(self, messages, **kwargs):
        await asyncio.sleep(self.delay)
        yield "the "
        yield "answer"


def _agent(llm):
    return AgentStateMachine(llm_client=llm, tool_executor=ToolExecutor(safety=ToolSafetyFramework()), max_loops=5)


def _tool(name, **args):
    return LLMResponse(content="", tool_calls=[ToolCall(id="c1", function=FunctionCall(name=name, arguments=args))])


@pytest.mark.asyncio
async def test_context_seeded_turn_persisted_and_auto_recall():
    tm = _FakeThreadManager(
        hint='<continuity>Thread: "Scanner share"</continuity>',
        history=[{"role": "user", "content": "earlier"}],
        recalled=[{"thread_id": "t-9", "title": "Samba media share", "date": "2026-07-14",
                   "receipt": "Title: Samba media share", "match_terms": ["samba"],
                   "last_turn_id": "turn-old"}],
    )
    agent = _agent(_LLM())
    events = [e async for e in agent.process("add a share", session_id="s1", thread_manager=tm)]
    types = [e.type for e in events]
    assert types.index("session_started") < types.index("thread_recalled") < types.index("turn_persisted") < types.index("state_change")
    assert next(e for e in events if e.type == "turn_persisted").data == {"thread_id": "t-open", "turn_id": "turn-1"}
    rec = next(e for e in events if e.type == "thread_recalled").data
    assert rec["thread_id"] == "t-9" and rec["mode"] == "auto"
    assert rec["last_turn_id"] == "turn-old"
    assert tm.begun[0][0] == "add a share" and tm.begun[0][2] == "s1"
    assert tm.begun[0][1].detected_domains is not None   # a MessageSignals
    assert agent.ctx.thread_id == "t-open" and agent.ctx.continuity_hint.startswith("<continuity>")
    assert agent.ctx.conversation_history == [{"role": "user", "content": "earlier"}]
    assert agent.ctx.retrieved_context[0]["source"] == "thread"
    assert agent.ctx.recalled_threads[0]["thread_id"] == "t-9"


@pytest.mark.asyncio
async def test_begin_turn_failure_or_no_manager_still_answers():
    tm = _FakeThreadManager(fail_begin=True)
    types = [e.type async for e in _agent(_LLM()).process("hello", session_id="s3", thread_manager=tm)]
    assert "thread_store_error" in types and "turn_persisted" not in types
    assert "response_complete" in types and tm.ended == []
    types = [e.type async for e in _agent(_LLM()).process("hello", session_id="s4")]
    assert "turn_persisted" not in types and "thread_store_error" not in types and "response_complete" in types


@pytest.mark.asyncio
async def test_end_turn_receives_text_blocks_terminals_status():
    tm = _FakeThreadManager()
    agent = _agent(_LLM([_tool("run_command", command="uptime")]))

    async def fake_execute(tool_name, args, session_id=None, confirmed=False):
        get_terminal_event_bus().publish(session_id, {"kind": "spawn", "terminal_session_id": "term-7", "command": "uptime", "pid": 3})
        get_terminal_event_bus().publish(session_id, {"kind": "complete", "terminal_session_id": "term-7", "exit_code": 0})
        return ExecutionResult(success=True, result="22:50 up 1 day")

    agent.tools.execute = fake_execute
    async for _ in agent.process("how long up?", session_id="s5", thread_manager=tm):
        pass
    assert len(tm.ended) == 1
    end = tm.ended[0]
    assert end["turn"].turn_id == "turn-1" and end["assistant_text"] == "the answer"
    assert end["status"] == "complete" and end["thread_id_override"] is None
    assert end["terminal_session_ids"] == ["term-7"] and end["diff_proposals"] == []
    block = end["blocks"][0]
    assert block["tool"] == "run_command" and block["args"] == {"command": "uptime"}
    assert block["result"] == "22:50 up 1 day" and block["exit"] == 0


@pytest.mark.asyncio
async def test_thread_switch_passes_override_and_drops_meta_blocks():
    tm = _FakeThreadManager()
    agent = _agent(_LLM([_tool("new_thread", title="New", reason="r")]))
    async for _ in agent.process("new subject", session_id="s6", thread_manager=tm):
        pass
    assert tm.ended[0]["thread_id_override"] == "t-new" and tm.ended[0]["blocks"] == []


@pytest.mark.asyncio
async def test_cancelled_and_interrupted_statuses():
    tm = _FakeThreadManager()
    agent = _agent(_LLM(delay=0.3))

    async def consume_and_cancel():
        async for e in agent.process("slow", session_id="s7", thread_manager=tm):
            if e.type == "state_change" and e.data["state"] == "planning":
                agent.cancel_session("s7")

    await asyncio.wait_for(consume_and_cancel(), timeout=5)
    assert tm.ended[0]["status"] == "cancelled"

    async def consume():
        async for _ in agent.process("slow", session_id="s8", thread_manager=tm):
            pass

    task = asyncio.ensure_future(consume())
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert tm.ended[1]["status"] == "interrupted" and tm.ended[1]["assistant_text"] == ""


@pytest.mark.asyncio
async def test_paused_turn_ends_only_after_confirmation():
    tm = _FakeThreadManager()
    llm = AsyncMock()
    tc = MagicMock()
    tc.function.name = "run_command"
    tc.function.arguments = {"command": "systemctl restart sshd"}
    calls = {"n": 0}

    async def _chat(*a, **k):
        calls["n"] += 1
        return MagicMock(content="", tool_calls=[tc] if calls["n"] == 1 else [], plan=None)

    async def _stream(messages, **kwargs):
        yield "restarted"

    llm.chat, llm.stream = AsyncMock(side_effect=_chat), _stream
    agent = _agent(llm)
    events = [e async for e in agent.process("restart sshd", session_id="s9", thread_manager=tm)]
    assert agent.current_state == AgentState.AWAITING_CONFIRMATION and tm.ended == []
    confirm = next(e for e in events if e.type == "tool_confirmation_required")
    agent.tools.execute = AsyncMock(return_value=ExecutionResult(success=True, result="restarted"))
    async for _ in agent.confirm_action("s9", confirm.data["execution_id"], True):
        pass
    assert len(tm.ended) == 1
    assert tm.ended[0]["status"] == "complete" and tm.ended[0]["assistant_text"] == "restarted"
```

- [ ] **Step 2: Run it, expect failures**

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core && /Volumes/4TB-BAD/Halbert/.venv/bin/python -m pytest tests/test_state_machine_turn_persistence.py -q -p no:cacheprovider
```
Expected: `ValueError: 'turn_persisted' is not in list` and `assert len(tm.ended) == 1` failures.

- [ ] **Step 3: Call begin/end turn** — in `process()` replace
```python
            yield StreamEvent.session_started(session_id, request_id)

            try:
```
with
```python
            yield StreamEvent.session_started(session_id, request_id)

            # Plan A: persist the user row and resolve the thread before any
            # model call (spec §4.1-§4.4), under the lock so thread
            # resolve/open/pause never races another turn.
            async for event in self._begin_turn():
                yield event

            try:
```
and replace the try's `finally:` in `process()` **and** the one in `confirm_action()` (both currently just `self._settle_turn(session_id)`) with
```python
            finally:
                # end_turn before the state reset: the status is derived
                # from where the machine stopped (spec §4.7, §12).
                self._end_turn(self._turn_status(session_id))
                self._settle_turn(session_id)
```

- [ ] **Step 4: Add the methods** directly after `_settle_turn`:

```python
    async def _begin_turn(self) -> AsyncIterator[StreamEvent]:
        """Persist the user message and resolve the thread (spec §4.1-§4.4).

        Seeds ``ctx`` from the TurnContext: thread id, hint, history
        (receipt + last raw turns) and any deterministic recall, whose
        receipt goes in as ``retrieved_context[0]`` with ``source="thread"``.
        A store failure emits ``thread_store_error`` once and the turn
        carries on without persistence.
        """
        tm = self.ctx.thread_manager
        if tm is None:
            return
        sid = self.ctx.session_id
        try:
            from ..intake.signals import analyze_message
            signals = analyze_message(self.ctx.user_query)
            turn = tm.begin_turn(self.ctx.user_query, signals, sid)
        except Exception as e:
            logger.warning(f"begin_turn failed (non-fatal): {e}")
            yield StreamEvent.thread_store_error(sid, f"begin_turn: {e}")
            return

        self.ctx.turn_context = turn
        self.ctx.thread_id = turn.thread_id
        self.ctx.continuity_hint = turn.hint or ""
        self.ctx.conversation_history = list(turn.history or [])
        self.ctx.recalled_threads = list(turn.recalled or [])

        for r in self.ctx.recalled_threads:
            rid = str(r.get("thread_id", ""))
            rtitle = str(r.get("title", ""))
            rdate = str(r.get("date", ""))
            self.ctx.add_context(
                source="thread",
                content=str(r.get("receipt", "")),
                metadata={
                    "thread_id": rid, "title": rtitle, "date": rdate,
                    "match_terms": list(r.get("match_terms") or []),
                },
            )
            yield StreamEvent.thread_recalled(
                sid, rid, rtitle, rdate, list(r.get("match_terms") or []), mode="auto",
                last_turn_id=r.get("last_turn_id") or self._last_turn_id(rid),
            )

        yield StreamEvent.turn_persisted(sid, turn.thread_id, turn.turn_id)

    def _turn_status(self, session_id: str) -> str:
        """``complete`` | ``cancelled`` | ``interrupted`` for the turn ending now.

        Runs before ``_settle_turn`` resets the state: IDLE means ``_drive``
        ran to the end; anything else (an exception, the consumer going
        away) is an interrupted turn.

        ``self.cancelled`` is legacy: after A11 removes the route's
        force-reset nothing writes it any more. The live path is
        ``ctx.conversation_status`` (``cancel_session`` transitions it to
        CANCELLED); the dict check stays only for out-of-tree callers.
        """
        cancelled = bool(self.cancelled.get(session_id))
        try:
            cancelled = cancelled or (
                self.ctx.conversation_status.current() == ConversationStatus.CANCELLED
            )
        except Exception:
            pass
        if cancelled:
            return "cancelled"
        if self.current_state == AgentState.IDLE:
            return "complete"
        return "interrupted"

    @staticmethod
    def _tool_block(tc: ToolCall) -> Dict[str, Any]:
        """One persisted tool block (spec §8 messages.blocks_json)."""
        result = tc.result
        if not isinstance(result, (str, int, float, bool, dict, list, type(None))):
            result = str(result)
        if isinstance(result, str) and len(result) > 4000:
            result = result[:4000] + "…"
        exit_code: Optional[int] = None
        if tc.name == "run_command":
            text = tc.result if isinstance(tc.result, str) else ""
            m = re.match(r"Exit code (-?\d+)", text)
            if m:
                exit_code = int(m.group(1))
            elif tc.status == "success":
                exit_code = 0
        return {
            "tool": tc.name,
            "args": tc.args if isinstance(tc.args, dict) else {"value": str(tc.args)},
            "result": result,
            "exit": exit_code,
            "execution_id": tc.id,
            "status": tc.status,
            "error": tc.error,
        }

    def _end_turn(self, status: str) -> None:
        """Hand the finished turn to the ThreadManager (spec §4.7).

        Skipped while the turn is merely paused on a confirmation (the
        TurnContext stays on ctx; confirm_action's finally ends it).
        Thread meta-tool calls are not blocks. Never raises.
        """
        if self.current_state == AgentState.AWAITING_CONFIRMATION:
            return
        ctx = self.ctx
        if ctx is None:
            return
        tm = ctx.thread_manager
        turn = ctx.turn_context
        if tm is None or turn is None:
            return
        ctx.turn_context = None
        blocks = [
            self._tool_block(tc) for tc in ctx.tool_calls
            if tc.name not in THREAD_META_TOOLS
        ]
        diffs = [
            {"diff_id": diff_id, **(diff if isinstance(diff, dict) else {"value": diff})}
            for diff_id, diff in ctx.pending_diffs.items()
        ]
        try:
            tm.end_turn(
                turn,
                assistant_text="".join(ctx.response_chunks),
                blocks=blocks,
                terminal_session_ids=list(ctx.terminal_session_ids),
                diff_proposals=diffs,
                status=status,
                thread_id_override=ctx.thread_id if ctx.thread_switched else None,
            )
        except Exception as e:
            logger.warning(f"end_turn failed (non-fatal): {e}")
```

- [ ] **Step 5: Run the tests**

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core && /Volumes/4TB-BAD/Halbert/.venv/bin/python -m pytest tests/test_state_machine_turn_persistence.py tests/test_state_machine_meta_tools.py tests/test_state_machine_turn_lock.py tests/test_state_machine.py tests/test_agent_integration.py tests/test_conversation_status_wiring.py -q -p no:cacheprovider
```
Expected: all PASS.

- [ ] **Step 6: Commit**

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation && git add halbert_core/halbert_core/agents/state_machine.py halbert_core/tests/test_state_machine_turn_persistence.py && git commit -m "feat(agents): persist turns through the ThreadManager

process() calls begin_turn under the turn lock, seeds the context with
the thread id, hint, history and any deterministic recall (emitting
thread_recalled mode=auto and turn_persisted), and ends the turn in its
finally with the assistant text, tool blocks with exit codes, spawned
terminal ids, diff proposals and a complete/cancelled/interrupted
status. A turn paused on confirmation is ended by confirm_action."
```

### Task A9d: tools_supported on the LLM clients (once-per-model no-tools fallback)

**Files:**
- Modify: `halbert_core/halbert_core/model/client.py` (registry directly above `def _call_with_tool_fallback(`; the `except requests.HTTPError` branch of `_call_with_tool_fallback`)
- Modify: `halbert_core/halbert_core/agents/llm_client.py` (`OllamaClient.__init__` after `self.timeout = timeout`; `OllamaClient.chat` request block)
- Modify: `halbert_core/halbert_core/dashboard/routes/agent.py` (`LLMClientAdapter.__init__`; both `call_llm_chat(` call sites in `LLMClientAdapter.chat`; new `_note_tools_support`)
- Test: `halbert_core/tests/test_tools_supported.py`

Context for the engineer: `_call_with_tool_fallback` (model/client.py) already retries without tools when Ollama answers a `tools` payload with 400/404/422/501, but it logs every time and nothing downstream learns about it. Spec §7: the fallback "logs once per model", and the continuity preamble omits the instruction to call tools for such a model. A8 added `CONTINUITY_PREAMBLE_NO_TOOLS` and A9a passes `getattr(self.llm, "tools_supported", None)` into the prompt builder; this task makes the clients set that flag. `None` means unknown (never proven either way), `False` means the model rejected tool schemas this process. A10 edits the same three files (payload `options`), at different anchors: the ones below stay intact for A10.

- [ ] **Step 1: Write the failing test**

```python
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Plan A / A9d: a model that rejects tool schemas is remembered once per
process; the clients expose tools_supported=False so the prompt layer can
drop the tool instruction from the continuity preamble (spec §7)."""

import logging
import pytest
import requests
from unittest.mock import MagicMock, patch

import halbert_core.model.client as mc
from halbert_core.model.client import call_llm_chat, model_supports_tools

TOOLS = [{"type": "function", "function": {"name": "t", "parameters": {"type": "object", "properties": {}}}}]
MSGS = [{"role": "user", "content": "hi"}]


@pytest.fixture(autouse=True)
def _clear_registry():
    mc._TOOLS_REJECTED.clear()
    yield
    mc._TOOLS_REJECTED.clear()


def _ok(payload):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = payload
    resp.raise_for_status.return_value = None
    return resp


def _rejecting(status):
    resp = MagicMock()
    resp.status_code = status
    resp.raise_for_status.side_effect = requests.HTTPError(f"HTTP {status}", response=resp)
    return resp


class TestRegistry:
    def test_unknown_until_a_rejection(self):
        assert model_supports_tools("m:7b") is None

    def test_rejection_marks_model_retries_without_tools_and_logs_once(self, caplog):
        caplog.set_level(logging.WARNING, logger="halbert.model.client")
        with patch("halbert_core.model.client.requests.post",
                   side_effect=[_rejecting(400), _ok({"message": {"content": "a"}}),
                                _rejecting(400), _ok({"message": {"content": "b"}})]) as post:
            first = call_llm_chat(endpoint="http://localhost:11434", model="m:7b", messages=MSGS, tools=TOOLS)
            second = call_llm_chat(endpoint="http://localhost:11434", model="m:7b", messages=MSGS, tools=TOOLS)
        assert first["content"] == "a" and second["content"] == "b"
        assert model_supports_tools("m:7b") is False
        assert model_supports_tools("other") is None
        payloads = [c.kwargs["json"] for c in post.call_args_list]
        assert "tools" in payloads[0] and "tools" not in payloads[1]
        assert "tools" in payloads[2] and "tools" not in payloads[3]
        warnings = [r for r in caplog.records if "rejected tool schemas" in r.getMessage()]
        assert len(warnings) == 1

    def test_other_http_errors_still_raise(self):
        with patch("halbert_core.model.client.requests.post", side_effect=[_rejecting(500)]):
            with pytest.raises(requests.HTTPError):
                call_llm_chat(endpoint="http://localhost:11434", model="m:7b", messages=MSGS, tools=TOOLS)
        assert model_supports_tools("m:7b") is None


# --- OllamaClient (aiohttp) --------------------------------------------------

class _Resp:
    def __init__(self, status, payload):
        self.status, self._payload = status, payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def raise_for_status(self):
        if self.status >= 400:
            raise RuntimeError(f"HTTP {self.status}")

    async def json(self):
        return self._payload


class _Session:
    posted = []
    responses = []

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def post(self, url, json=None, **k):
        _Session.posted.append(json)
        return _Session.responses.pop(0)


@pytest.mark.asyncio
async def test_ollama_client_retries_without_tools_and_sets_the_flag(monkeypatch):
    from halbert_core.agents.llm_client import OllamaClient
    monkeypatch.setattr("aiohttp.ClientSession", _Session)
    _Session.posted.clear()
    _Session.responses[:] = [_Resp(400, {}), _Resp(200, {"message": {"content": "plain"}})]
    client = OllamaClient(model="m:7b")
    assert client.tools_supported is None
    out = await client.chat(MSGS, tools=TOOLS)
    assert out.content == "plain" and client.tools_supported is False
    assert "tools" in _Session.posted[0] and "tools" not in _Session.posted[1]
    # a plain call afterwards does not reset the flag
    _Session.responses[:] = [_Resp(200, {"message": {"content": "again"}})]
    assert (await client.chat(MSGS)).content == "again"
    assert client.tools_supported is False


# --- LLMClientAdapter (dashboard) -------------------------------------------

fastapi = pytest.importorskip("fastapi")


@pytest.fixture
def adapter(monkeypatch):
    monkeypatch.setattr("halbert_core.model.client.get_configured_model", lambda: "m:7b")
    monkeypatch.setattr("halbert_core.model.client.get_ollama_endpoint", lambda: "http://localhost:11434")
    monkeypatch.setattr("halbert_core.model.client.get_specialist_model", lambda: (None, None, None))
    monkeypatch.setattr("halbert_core.model.client.get_vision_model", lambda: (None, "http://localhost:11434"))
    from halbert_core.dashboard.routes.agent import LLMClientAdapter
    return LLMClientAdapter()


@pytest.mark.asyncio
async def test_adapter_learns_tools_supported_from_the_fallback(adapter):
    assert adapter.tools_supported is None
    with patch("halbert_core.model.client.requests.post", side_effect=[_ok({"message": {"content": "ok"}})]):
        await adapter.chat(MSGS, tools=TOOLS)
    assert adapter.tools_supported is None          # accepted: still unknown
    with patch("halbert_core.model.client.requests.post",
               side_effect=[_rejecting(422), _ok({"message": {"content": "ok"}})]):
        r = await adapter.chat(MSGS, tools=TOOLS)
    assert r.content == "ok" and adapter.tools_supported is False
    # a later call without tools does not flip it back
    with patch("halbert_core.model.client.requests.post", side_effect=[_ok({"message": {"content": "ok"}})]):
        await adapter.chat(MSGS, tools=None)
    assert adapter.tools_supported is False
```

- [ ] **Step 2: Run it, expect failures**

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core && /Volumes/4TB-BAD/Halbert/.venv/bin/python -m pytest tests/test_tools_supported.py -q -p no:cacheprovider
```
Expected: `ImportError: cannot import name 'model_supports_tools' from 'halbert_core.model.client'`.

- [ ] **Step 3: Registry and once-per-model logging in `model/client.py`** — insert directly above `def _call_with_tool_fallback(`:

```python
# ── Tool-schema rejection registry (Plan A, spec §7) ─────────────
#
# Models without tool calling answer a ``tools`` payload with a 4xx. The
# fallback below retries without tools and records the model here, so the
# warning is logged once per model per process and the clients can expose
# tools_supported=False: the prompt layer then drops the "call
# recall_thread / new_thread" instruction from the continuity preamble
# (AgentPromptBuilder.CONTINUITY_PREAMBLE_NO_TOOLS) for a model that
# cannot call anything.

_TOOLS_REJECTED: Dict[str, bool] = {}


def model_supports_tools(model: str) -> Optional[bool]:
    """False once ``model`` rejected tool schemas this process; None
    otherwise (unknown: nothing has proven it either way)."""
    return False if _TOOLS_REJECTED.get(model) else None


```
and in `_call_with_tool_fallback` replace
```python
    except requests.HTTPError as e:
        status = getattr(e.response, "status_code", None)
        if status not in (400, 404, 422, 501):
            raise
        logger.warning(
            f"Model {model} rejected tool schemas (HTTP {status}); "
            "retrying without tools"
        )
        return _do_llm_call(endpoint, model, messages, provider, stream, timeout, options)
```
with
```python
    except requests.HTTPError as e:
        status = getattr(e.response, "status_code", None)
        if status not in (400, 404, 422, 501):
            raise
        if not _TOOLS_REJECTED.get(model):
            # Once per model per process (spec §7); later fallbacks are silent.
            logger.warning(
                f"Model {model} rejected tool schemas (HTTP {status}); "
                "retrying without tools"
            )
        _TOOLS_REJECTED[model] = True
        return _do_llm_call(endpoint, model, messages, provider, stream, timeout, options)
```

- [ ] **Step 4: `OllamaClient` in `agents/llm_client.py`** — in `__init__` replace
```python
        self.model = model
        self.endpoint = endpoint.rstrip('/')
        self.timeout = timeout
```
with
```python
        self.model = model
        self.endpoint = endpoint.rstrip('/')
        self.timeout = timeout
        # Plan A (spec §7): False once this model rejected tool schemas and
        # chat() fell back to a no-tools retry; None until then. The state
        # machine passes it to the prompt builder.
        self.tools_supported: Optional[bool] = None
```
and in `chat` replace
```python
                ) as resp:
                    resp.raise_for_status()
                    data = await resp.json()
```
(the 20-space-indented one inside `OllamaClient.chat`; `AnthropicClient` has a 16-space one) with
```python
                ) as resp:
                    if tools and resp.status in (400, 404, 422, 501):
                        # No tool calling on this model (spec §7): retry
                        # without the schemas, remember it, log once.
                        if self.tools_supported is not False:
                            logger.warning(
                                f"Model {payload['model']} rejected tool schemas "
                                f"(HTTP {resp.status}); retrying without tools"
                            )
                        self.tools_supported = False
                        payload.pop("tools", None)
                        async with session.post(
                            f"{self.endpoint}/api/chat",
                            json=payload,
                            timeout=aiohttp.ClientTimeout(total=self.timeout)
                        ) as retry:
                            retry.raise_for_status()
                            return self._parse_response(await retry.json())
                    resp.raise_for_status()
                    data = await resp.json()
```

- [ ] **Step 5: `LLMClientAdapter` in `dashboard/routes/agent.py`** — in `__init__` replace
```python
        self.max_tokens = 8192
        self.temperature = 0.7
```
with (the whitespace-only line and `async def chat(...)` that follow stay as they are)
```python
        self.max_tokens = 8192
        self.temperature = 0.7
        # Plan A (spec §7): False once the model rejected tool schemas and
        # call_llm_chat fell back to a no-tools retry; None until then. The
        # state machine passes it to the prompt builder.
        self.tools_supported: Optional[bool] = None

    def _note_tools_support(self, model: str, tools) -> None:
        """Remember when ``model`` fell back to a no-tools retry (spec §7)."""
        from ...model.client import model_supports_tools
        if tools and model_supports_tools(model) is False:
            if self.tools_supported is not False:
                logger.info(
                    f"Model {model} answers without tools; the continuity "
                    "preamble drops the tool instruction"
                )
            self.tools_supported = False
```
In `chat`, after the main call replace
```python
                tools=tools,
            )
            return LLMResponse(
                content=result.get("content", ""),
                tool_calls=_as_tool_calls(result.get("tool_calls")),
            )
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
```
with
```python
                tools=tools,
            )
            self._note_tools_support(model, tools)
            return LLMResponse(
                content=result.get("content", ""),
                tool_calls=_as_tool_calls(result.get("tool_calls")),
            )
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
```
and in the guide fallback replace
```python
                    tools=tools,
                )
                return LLMResponse(
                    content=result.get("content", ""),
                    tool_calls=_as_tool_calls(result.get("tool_calls")),
                )
            raise
```
with
```python
                    tools=tools,
                )
                self._note_tools_support(guide_model, tools)
                return LLMResponse(
                    content=result.get("content", ""),
                    tool_calls=_as_tool_calls(result.get("tool_calls")),
                )
            raise
```

- [ ] **Step 6: Run the tests**

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core && /Volumes/4TB-BAD/Halbert/.venv/bin/python -m pytest tests/test_tools_supported.py tests/test_state_machine_turn_lock.py tests/test_agent_prompts_continuity.py tests/test_tool_calling_bridge.py tests/test_phase_d_integration.py -q -p no:cacheprovider
```
Expected: `test_tools_supported.py` (`6 passed`), `test_state_machine_turn_lock.py` and `test_agent_prompts_continuity.py` PASS; `test_tool_calling_bridge.py` still exactly its 3 baseline `TestLLMClientAdapterTools` failures; `test_phase_d_integration.py` only its baseline `test_get_configured_model_returns_string` failure.

- [ ] **Step 7: Commit**

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation && git add halbert_core/halbert_core/model/client.py halbert_core/halbert_core/agents/llm_client.py halbert_core/halbert_core/dashboard/routes/agent.py halbert_core/tests/test_tools_supported.py && git commit -m "feat(model): remember once per model that tool schemas were rejected

_call_with_tool_fallback records the model in _TOOLS_REJECTED and logs
the fallback once; model_supports_tools() exposes it. OllamaClient and
the dashboard LLMClientAdapter set tools_supported=False after a
no-tools retry so the continuity preamble can omit the instruction to
call recall_thread / new_thread (spec §7)."
```

### Task A10: num_ctx on every Ollama call (compute_num_ctx, per-model cache, PLANNING num_predict 1024)

**Files:**
- Modify: `halbert_core/halbert_core/model/client.py` (helpers directly above `_do_llm_call` line 434; Ollama payload lines 477-486)
- Modify: `halbert_core/halbert_core/agents/llm_client.py` (`OllamaClient.chat` payload lines 123-131; `OllamaClient.stream` payload lines 167-175)
- Modify: `halbert_core/halbert_core/dashboard/routes/agent.py` (`LLMClientAdapter.chat` options line 366 and the fallback call lines 382-390; `LLMClientAdapter.stream` payload lines 473-480)
- Test: `halbert_core/tests/test_num_ctx.py`

- [ ] **Step 1: Write the failing test**

```python
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Plan A / A10: options.num_ctx is set on every Ollama call, sized from the
prompt, computed once per model per process (spec §7)."""

import json
import pytest
from unittest.mock import MagicMock, patch

import halbert_core.model.client as mc
from halbert_core.model.client import compute_num_ctx, num_ctx_for_model, estimate_prompt_tokens, call_llm_chat


@pytest.fixture(autouse=True)
def _clear_cache():
    mc._NUM_CTX_CACHE.clear()
    yield
    mc._NUM_CTX_CACHE.clear()


def _response(payload):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = payload
    resp.raise_for_status.return_value = None
    return resp


def test_compute_num_ctx_clamps_and_rounds():
    assert compute_num_ctx(10, 100, None) == 4096            # floor
    assert compute_num_ctx(3000, 1024, None) == 5120         # 4536 -> 5120
    assert compute_num_ctx(4096, 1536, None) == 6144         # exact multiple stays
    assert compute_num_ctx(100_000, 1024, None) == 32768     # default ceiling
    assert compute_num_ctx(100_000, 1024, 8192) == 8192      # model_max caps
    assert compute_num_ctx(10, 10, 2048) == 4096             # floor beats a tiny model_max


def test_per_model_cache_grows_but_never_shrinks():
    assert num_ctx_for_model("m:7b", 3000, 1024) == 5120
    assert num_ctx_for_model("m:7b", 10, 10) == 5120
    assert num_ctx_for_model("m:7b", 9000, 1024) == 11264
    assert num_ctx_for_model("m:7b", 10, 10) == 11264
    assert num_ctx_for_model("other", 10, 10) == 4096


def test_estimate_counts_messages_and_tools():
    msgs = [{"role": "user", "content": "x" * 400}]
    tools = [{"type": "function", "function": {"name": "t", "parameters": {}}}]
    assert estimate_prompt_tokens(msgs, None) == 100
    assert estimate_prompt_tokens(msgs, tools) == 100 + len(json.dumps(tools)) // 4
    assert estimate_prompt_tokens([{"role": "user", "content": [{"type": "text", "text": "abcd" * 10}]}], None) > 0


def test_ollama_chat_payload_carries_num_ctx():
    with patch("halbert_core.model.client.requests.post", return_value=_response({"message": {"content": "hi"}})) as post:
        call_llm_chat(endpoint="http://localhost:11434", model="example-model:latest",
                      messages=[{"role": "user", "content": "hi"}])
    opts = post.call_args.kwargs["json"]["options"]
    assert opts == {"num_predict": 1024, "temperature": 0.7, "num_ctx": 4096}

    with patch("halbert_core.model.client.requests.post", return_value=_response({"message": {"content": "hi"}})) as post:
        call_llm_chat(endpoint="http://localhost:11434", model="example-model:latest",
                      messages=[{"role": "user", "content": "y" * 40_000}], options={"num_predict": 1024})
    assert post.call_args.kwargs["json"]["options"]["num_ctx"] == 12288   # 10000+512+1024 -> 12288

    with patch("halbert_core.model.client.requests.post", return_value=_response({"message": {"content": "hi"}})) as post:
        call_llm_chat(endpoint="http://localhost:11434", model="example-model:latest",
                      messages=[{"role": "user", "content": "hi"}], options={"num_ctx": 8192})
    assert post.call_args.kwargs["json"]["options"]["num_ctx"] == 8192   # explicit override wins


def test_openai_payload_has_no_options():
    with patch("halbert_core.model.client.requests.post",
               return_value=_response({"choices": [{"message": {"content": "ok"}}]})) as post:
        call_llm_chat(endpoint="https://api.example.test", model="hosted",
                      messages=[{"role": "user", "content": "hi"}], provider="openai")
    assert "options" not in post.call_args.kwargs["json"]


# --- streaming payloads (OllamaClient and the dashboard adapter) -------------

class _Lines:
    def __init__(self, lines):
        self._lines = list(lines)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._lines:
            raise StopAsyncIteration
        return self._lines.pop(0)


class _FakeResp:
    status = 200

    def __init__(self):
        # Content and the done flag on separate lines: the dashboard adapter
        # breaks on ``done`` before appending that line's content, so a
        # single done:true line would yield nothing.
        self.content = _Lines([
            b'{"message":{"content":"hi"},"done":false}\n',
            b'{"message":{"content":""},"done":true}\n',
        ])

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def raise_for_status(self):
        return None

    async def text(self):
        return ""

    async def json(self):
        return {"message": {"content": "hi"}}


class _FakeSession:
    captured = {}

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def post(self, url, json=None, **k):
        _FakeSession.captured["json"] = json
        return _FakeResp()


@pytest.fixture
def fake_aiohttp(monkeypatch):
    _FakeSession.captured.clear()
    monkeypatch.setattr("aiohttp.ClientSession", _FakeSession)
    return _FakeSession.captured


@pytest.mark.asyncio
async def test_ollama_client_chat_and_stream_carry_num_ctx(fake_aiohttp):
    from halbert_core.agents.llm_client import OllamaClient
    client = OllamaClient(model="example-model:latest")
    assert [c async for c in client.stream([{"role": "user", "content": "hi"}])] == ["hi"]
    assert fake_aiohttp["json"]["options"] == {"temperature": 0.7, "num_predict": 2048, "num_ctx": 4096}
    await client.chat([{"role": "user", "content": "hi"}])
    assert fake_aiohttp["json"]["options"]["num_ctx"] == 4096


fastapi = pytest.importorskip("fastapi")


@pytest.fixture
def adapter(monkeypatch):
    monkeypatch.setattr("halbert_core.model.client.get_configured_model", lambda: "example-model:latest")
    monkeypatch.setattr("halbert_core.model.client.get_ollama_endpoint", lambda: "http://localhost:11434")
    monkeypatch.setattr("halbert_core.model.client.get_specialist_model", lambda: (None, None, None))
    monkeypatch.setattr("halbert_core.model.client.get_vision_model", lambda: (None, "http://localhost:11434"))
    from halbert_core.dashboard.routes.agent import LLMClientAdapter
    return LLMClientAdapter()


@pytest.mark.asyncio
async def test_adapter_stream_has_num_ctx_and_bounded_num_predict(adapter, fake_aiohttp):
    adapter.max_tokens = 8192
    assert "".join([c async for c in adapter.stream([{"role": "user", "content": "hi"}])]) == "hi"
    opts = fake_aiohttp["json"]["options"]
    assert opts["num_ctx"] >= 4096 and opts["num_ctx"] % 1024 == 0
    assert opts["num_predict"] <= opts["num_ctx"] - 512 and opts["num_predict"] <= 8192


@pytest.mark.asyncio
async def test_adapter_planning_chat_uses_num_predict_1024(adapter):
    with patch("halbert_core.model.client.call_llm_chat") as chat:
        chat.return_value = {"content": "ok", "tool_calls": []}
        await adapter.chat([{"role": "user", "content": "plan"}], tools=[])
    assert chat.call_args.kwargs["options"]["num_predict"] == 1024
```

- [ ] **Step 2: Run it, expect failures**

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core && /Volumes/4TB-BAD/Halbert/.venv/bin/python -m pytest tests/test_num_ctx.py -q -p no:cacheprovider
```
Expected: `ImportError: cannot import name 'compute_num_ctx' from 'halbert_core.model.client'`.

- [ ] **Step 3: Helpers in `model/client.py`** — insert directly above `def _do_llm_call(` (`json`, `Dict`, `Optional`, `logger` are already available in that module):

```python
# ── num_ctx sizing (Plan A, spec §7) ─────────────────────────────
#
# Ollama's default context window is small and silently truncates the HEAD
# of the prompt. Every local call now sets options.num_ctx from the prompt
# size. The value is cached per model and only ever grows: Ollama reloads a
# model whenever num_ctx changes, so recomputing it per turn would thrash
# the GPU on every message.

_NUM_CTX_MIN = 4096
_NUM_CTX_DEFAULT_MAX = 32768
_NUM_CTX_HEADROOM = 512
_NUM_CTX_CACHE: Dict[str, int] = {}


def compute_num_ctx(
    prompt_tokens_estimate: int, num_predict: int, model_max: Optional[int]
) -> int:
    """clamp(round_up(prompt + 512 + num_predict, 1024), 4096, model_max or 32768)."""
    need = int(prompt_tokens_estimate) + _NUM_CTX_HEADROOM + int(num_predict)
    rounded = ((need + 1023) // 1024) * 1024
    ceiling = int(model_max) if model_max else _NUM_CTX_DEFAULT_MAX
    return max(_NUM_CTX_MIN, min(rounded, ceiling))


def num_ctx_for_model(
    model: str,
    prompt_tokens_estimate: int,
    num_predict: int,
    model_max: Optional[int] = None,
) -> int:
    """Per-model num_ctx: computed once, grown only when a prompt needs more."""
    wanted = compute_num_ctx(prompt_tokens_estimate, num_predict, model_max)
    cached = _NUM_CTX_CACHE.get(model)
    if cached is not None and cached >= wanted:
        return cached
    if cached is not None:
        logger.info(f"num_ctx for {model} grows {cached} -> {wanted}")
    _NUM_CTX_CACHE[model] = wanted
    return wanted


def estimate_prompt_tokens(messages: list, tools: Optional[list]) -> int:
    """~4 chars/token over every message's content plus the tool schemas."""
    total = 0
    for m in messages or []:
        content = m.get("content", "") if isinstance(m, dict) else m
        if not isinstance(content, str):
            content = json.dumps(content, default=str)
        total += len(content) // 4
    if tools:
        total += len(json.dumps(tools, default=str)) // 4
    return total


```

- [ ] **Step 4: Ollama payload in `_do_llm_call`** — replace
```python
        if options:
            payload["options"] = {
                "num_predict": options.get(
                    "num_predict", options.get("max_tokens", 1024)
                ),
                "temperature": options.get("temperature", 0.7),
            }
        logger.info(f"Calling Ollama API: {url} model={model}")
```
with
```python
        options = options or {}
        num_predict = options.get("num_predict", options.get("max_tokens", 1024))
        # Always present (spec §7): without it Ollama truncates the head.
        num_ctx = options.get("num_ctx") or num_ctx_for_model(
            model, estimate_prompt_tokens(messages, tools), num_predict, options.get("num_ctx_max"),
        )
        payload["options"] = {
            "num_predict": num_predict,
            "temperature": options.get("temperature", 0.7),
            "num_ctx": num_ctx,
        }
        logger.info(f"Calling Ollama API: {url} model={model} num_ctx={num_ctx}")
```

- [ ] **Step 5: `agents/llm_client.py` OllamaClient** — in `chat` replace the `payload = {...}` block with
```python
        from ..model.client import num_ctx_for_model, estimate_prompt_tokens
        model = self._require_model()
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "num_ctx": num_ctx_for_model(model, estimate_prompt_tokens(messages, tools), max_tokens),
            }
        }
```
and in `stream` replace its `payload = {...}` block with
```python
        from ..model.client import num_ctx_for_model, estimate_prompt_tokens
        model = self._require_model()
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "num_ctx": num_ctx_for_model(model, estimate_prompt_tokens(messages, None), max_tokens),
            }
        }
```

- [ ] **Step 6: `dashboard/routes/agent.py` LLMClientAdapter** — in `chat`, change the main call's
```python
                options={"num_predict": 2048, "temperature": 0.7},
                tools=tools,
```
to
```python
                # PLANNING answers are tool calls or a short plan: 1024 is
                # plenty and keeps num_ctx (and the model reload) small.
                options={"num_predict": 1024, "temperature": 0.7},
                tools=tools,
```
and in the guide fallback call insert `options={"num_predict": 1024, "temperature": 0.7},` between `timeout=180,` and `tools=tools,`. In `stream`, replace
```python
                else:
                    url = f"{endpoint}/api/chat"
                    payload = {
                        "model": model,
                        "messages": messages,
                        "stream": True,
                        "options": {"num_predict": max_tokens, "temperature": temperature}
                    }
```
with
```python
                else:
                    from ...model.client import num_ctx_for_model, estimate_prompt_tokens
                    url = f"{endpoint}/api/chat"
                    prompt_tokens = estimate_prompt_tokens(messages, None)
                    num_ctx = num_ctx_for_model(model, prompt_tokens, max_tokens)
                    # The reply must fit in what is left after the prompt
                    # (spec §7: max_tokens subordinate to num_ctx − prompt).
                    num_predict = max(256, min(max_tokens, num_ctx - prompt_tokens - 512))
                    payload = {
                        "model": model,
                        "messages": messages,
                        "stream": True,
                        "options": {"num_predict": num_predict, "temperature": temperature, "num_ctx": num_ctx},
                    }
```

- [ ] **Step 7: Run the tests**

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core && /Volumes/4TB-BAD/Halbert/.venv/bin/python -m pytest tests/test_num_ctx.py tests/test_tool_calling_bridge.py tests/test_phase_d_integration.py -q -p no:cacheprovider
```
Expected: `test_num_ctx.py` PASS; `test_tool_calling_bridge.py` still exactly its 3 baseline `TestLLMClientAdapterTools` failures ("No model configured", raised before any payload is built); `test_phase_d_integration.py` only its baseline `test_get_configured_model_returns_string` failure.

- [ ] **Step 8: Commit**

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation && git add halbert_core/halbert_core/model/client.py halbert_core/halbert_core/agents/llm_client.py halbert_core/halbert_core/dashboard/routes/agent.py halbert_core/tests/test_num_ctx.py && git commit -m "feat(model): size num_ctx from the prompt on every Ollama call

compute_num_ctx clamps round_up(prompt + 512 + num_predict, 1024) to
[4096, model_max or 32768]; num_ctx_for_model caches it per model and
only grows so the model is not reloaded per turn. Set in call_llm_chat,
OllamaClient.chat/stream and the dashboard adapter's stream; PLANNING
calls use num_predict 1024 and the stream's num_predict is bounded by
num_ctx minus the prompt."
```

### Task A11: Route wiring — /message without force-reset, timeline endpoints, stored diffs, no /conversations

**Files:**
- Modify: `halbert_core/halbert_core/dashboard/routes/agent.py` (helpers after `_make_llm_caller` line 256; `send_message` lines 643-723; delete `/conversations` endpoints lines 889-926; replace `apply_diff`/`reject_diff` lines 928-1002 and append the new endpoints)
- Test: `halbert_core/tests/test_agent_routes_timeline.py`

- [ ] **Step 1: Write the failing test**

```python
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Plan A / A11: /api/agent/timeline, /thread/current, recall retraction,
diff apply/reject from the store, /message hands the ThreadManager to the
state machine, and the /agent/conversations endpoints are gone."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from halbert_core.agents.conversation_sqlite import SqliteConversationStore
from halbert_core.agents.threads import ThreadManager
from halbert_core.intake.signals import analyze_message
import halbert_core.dashboard.routes.agent as agent_routes


@pytest.fixture
def tm(tmp_path):
    store = SqliteConversationStore(str(tmp_path / "threads.db"))
    manager = ThreadManager(store)
    yield manager
    store.close()


@pytest.fixture
def client(monkeypatch, tm):
    monkeypatch.setattr(agent_routes, "_thread_manager", lambda: tm)
    monkeypatch.setattr(agent_routes, "_agent_instance", None)
    app = FastAPI()
    app.include_router(agent_routes.router)
    return TestClient(app)


def _seed_turn(tm, query, answer, diff_proposals=None):
    turn = tm.begin_turn(query, analyze_message(query), f"sess-{query[:8]}")
    tm.end_turn(turn, assistant_text=answer, blocks=[], terminal_session_ids=[], diff_proposals=diff_proposals or [])
    return turn


def test_timeline_empty_and_degraded(client, tm, monkeypatch):
    assert client.get("/api/agent/timeline").json() == {"turns": [], "has_more": False, "current_thread": None}

    def boom(**kw):
        raise RuntimeError("db gone")

    monkeypatch.setattr(tm.store, "list_turns", boom)
    r = client.get("/api/agent/timeline")
    assert r.status_code == 200 and r.json()["turns"] == []
    monkeypatch.setattr(agent_routes, "_thread_manager", lambda: None)
    assert client.get("/api/agent/timeline").json() == {"turns": [], "has_more": False, "current_thread": None}
    assert client.get("/api/agent/thread/current").json() is None


def test_timeline_turns_with_roles_and_current_thread(client, tm):
    t1 = _seed_turn(tm, "hello there", "hi!")
    t2 = _seed_turn(tm, "what is my hostname?", "It is halbert.")
    body = client.get("/api/agent/timeline").json()
    assert body["has_more"] is False
    assert [t["turn_id"] for t in body["turns"]] == [t1.turn_id, t2.turn_id]
    first = body["turns"][0]
    assert first["thread_id"] == t1.thread_id
    assert first["user"]["content"] == "hello there" and first["user"]["status"] == "complete"
    assert first["assistant"]["content"] == "hi!"
    assert first["blocks"] == [] and first["terminal_block_ids"] == []
    assert body["current_thread"]["thread_id"] == t2.thread_id
    assert body["current_thread"]["status"] == "open" and isinstance(body["current_thread"]["title"], str)


def test_timeline_paging_with_limit_and_before(client, tm):
    turns = [_seed_turn(tm, f"message number {i}", f"answer {i}") for i in range(5)]
    body = client.get("/api/agent/timeline", params={"limit": 2}).json()
    assert [t["turn_id"] for t in body["turns"]] == [turns[3].turn_id, turns[4].turn_id] and body["has_more"] is True
    body = client.get("/api/agent/timeline", params={"limit": 2, "before": turns[3].turn_id}).json()
    assert [t["turn_id"] for t in body["turns"]] == [turns[1].turn_id, turns[2].turn_id] and body["has_more"] is True
    body = client.get("/api/agent/timeline", params={"limit": 2, "before": turns[1].turn_id}).json()
    assert [t["turn_id"] for t in body["turns"]] == [turns[0].turn_id] and body["has_more"] is False


def test_current_thread_and_recall_retraction(client, tm):
    old = _seed_turn(tm, "set up the samba media share", "added [media] to smb.conf")
    tm.store.update_thread(old.thread_id, status="closed")
    new = _seed_turn(tm, "unrelated: check disk space", "df says fine")
    body = client.get("/api/agent/thread/current").json()
    assert body["thread_id"] == new.thread_id and body["status"] == "open"
    assert "title" in body and "receipt" in body

    assert client.delete(f"/api/agent/thread/{new.thread_id}/recall/nope").json() == {"ok": False}
    tm.store.update_thread(new.thread_id, recalled_json=[{
        "thread_id": old.thread_id, "title": "Samba media share", "date": "2026-07-14", "status": "accepted", "at": 1.0,
    }])
    r = client.delete(f"/api/agent/thread/{new.thread_id}/recall/{old.thread_id}")
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert tm.store.get_thread(new.thread_id)["recalled_json"][0]["status"] == "retracted"


def test_diff_apply_and_reject_from_store_when_session_is_dead(client, tm, tmp_path):
    target = tmp_path / "out" / "smb.conf"
    _seed_turn(tm, "add a share", "here is the diff", diff_proposals=[
        {"diff_id": "d1", "file_path": str(target), "new_content": "[scanner]\npath=/srv/scanner\n", "status": "pending"},
        {"diff_id": "d2", "file_path": "/nowhere", "new_content": "x", "status": "pending"},
        {"diff_id": "d3", "file_path": None, "edit_blocks": [], "status": "pending"},
    ])
    r = client.post("/api/agent/diff/dead-session/d1/apply")
    assert r.status_code == 200, r.text
    assert r.json()["applied"] is True
    assert target.read_text() == "[scanner]\npath=/srv/scanner\n"
    assert client.post("/api/agent/diff/dead-session/d2/reject").json() == {"rejected": True, "diff_id": "d2"}
    stored = {d["diff_id"]: d["status"] for d in tm.store.list_turns(limit=10)[-1]["diff_proposals"]}
    assert stored == {"d1": "applied", "d2": "rejected", "d3": "pending"}
    assert client.post("/api/agent/diff/dead-session/d3/apply").status_code == 400
    assert client.post("/api/agent/diff/dead-session/none/apply").status_code == 404
    assert client.post("/api/agent/diff/dead-session/none/reject").status_code == 404


def test_message_passes_thread_manager_and_never_force_resets(client, tm, monkeypatch):
    from halbert_core.agents.events import StreamEvent
    seen = {}

    class _FakeAgent:
        def __init__(self):
            self.cancelled = {}
            self.active_sessions = {"s1": object()}
            self.llm = type("L", (), {"max_tokens": 0, "temperature": 0.0})()
            self.current_state = "planning"

        async def process(self, **kwargs):
            seen.update(kwargs)
            yield StreamEvent.session_started("s1", "r1")
            yield StreamEvent.response_complete("s1")

    fake = _FakeAgent()
    monkeypatch.setattr(agent_routes, "get_agent", lambda: fake)
    r = client.post("/api/agent/message", json={"message": "hi", "session_id": "s1"})
    assert r.status_code == 200
    assert "session_started" in r.text and "response_complete" in r.text
    assert seen["thread_manager"] is tm and seen["query"] == "hi" and seen["session_id"] == "s1"
    assert fake.cancelled == {} and fake.current_state == "planning"


def test_conversations_routes_removed_and_thread_routes_present():
    paths = {getattr(r, "path", "") for r in agent_routes.router.routes}
    assert "/api/agent/conversations" not in paths
    assert "/api/agent/conversations/{conversation_id}" not in paths
    assert {"/api/agent/timeline", "/api/agent/thread/current",
            "/api/agent/thread/{thread_id}/recall/{recalled_thread_id}"} <= paths
```

- [ ] **Step 2: Run it, expect failures**

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core && /Volumes/4TB-BAD/Halbert/.venv/bin/python -m pytest tests/test_agent_routes_timeline.py -q -p no:cacheprovider
```
Expected: `AttributeError: module 'halbert_core.dashboard.routes.agent' has no attribute '_thread_manager'` in the `client` fixture, and `assert '/api/agent/conversations' not in paths` failing.

- [ ] **Step 3: Helpers** — in `dashboard/routes/agent.py`, directly after `_make_llm_caller` (after its `return caller`, before `class LLMClientAdapter`) add:

```python
def _thread_manager():
    """The process-wide ThreadManager, or None when the store is unavailable.

    Module-level so tests can monkeypatch it; every thread endpoint degrades
    to an empty answer when this returns None (spec §12).
    """
    try:
        from ...agents.threads import get_thread_manager
        return get_thread_manager()
    except Exception as e:
        logger.warning(f"Thread manager unavailable (non-fatal): {e}")
        return None


def _thread_summary(thread: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """{thread_id, title, status} for the timeline's current_thread."""
    if not thread:
        return None
    return {
        "thread_id": thread.get("id") or thread.get("thread_id"),
        "title": thread.get("title") or "",
        "status": thread.get("status") or "open",
    }


def _active_ctx(session_id: str):
    """The live StateContext for ``session_id``, without building the agent."""
    if _agent_instance is None:
        return None
    return _agent_instance.active_sessions.get(session_id)


def _find_stored_diff(tm, diff_id: str):
    """Locate a persisted diff proposal by id (spec §8).

    Returns ``(message_id, proposals, index)`` where ``proposals`` is the
    assistant row's full diff list, or None. Scans the newest 200 turns;
    older diffs are not actionable from the UI.
    """
    if tm is None:
        return None
    try:
        turns = tm.store.list_turns(limit=200)
    except Exception as e:
        logger.warning(f"Diff lookup failed (non-fatal): {e}")
        return None
    for turn in reversed(turns):
        proposals = list(turn.get("diff_proposals") or [])
        for index, proposal in enumerate(proposals):
            if isinstance(proposal, dict) and proposal.get("diff_id") == diff_id:
                message_id = (turn.get("assistant") or {}).get("message_id")
                return None if message_id is None else (message_id, proposals, index)
    return None


```

- [ ] **Step 4: Rewrite `send_message`** — replace the whole endpoint (from `@router.post("/message")` through its `return StreamingResponse(...)`, lines 643-723) with:

```python
    @router.post("/message")
    async def send_message(request: SendMessageRequest, req: Request):
        """
        Send message to agent with SSE streaming response.

        A second message during a live turn queues on the state machine's
        turn lock (spec §12); nothing here resets the machine any more.
        """
        try:
            agent = get_agent()
        except Exception as e:
            raise HTTPException(500, f"Agent initialization failed: {e}")

        session_id = request.session_id

        # Set performance tweaks from request (from frontend Settings > AI > Performance Tweaks)
        if hasattr(agent.llm, 'max_tokens'):
            agent.llm.max_tokens = request.max_tokens or 8192
            agent.llm.temperature = request.temperature or 0.7
            logger.info(f"Set LLM tweaks: max_tokens={agent.llm.max_tokens}, temperature={agent.llm.temperature}")

        # Plan A: the state machine persists the turn and resolves the hidden
        # thread itself (begin_turn under its lock); the route only hands
        # over the manager. None means "no store": the turn still runs.
        thread_manager = _thread_manager()

        async def event_stream():
            """Generate SSE events from agent processing."""
            from ...agents.events import StreamEvent

            try:
                async for event in agent.process(
                    query=request.message,
                    session_id=session_id,
                    images=request.images,
                    thread_manager=thread_manager,
                ):
                    yield event.to_sse()
            except Exception as e:
                logger.error(f"Agent processing error: {e}")
                yield StreamEvent.error(session_id or "unknown", str(e), recoverable=False).to_sse()
            finally:
                logger.info(f"Event stream completed for session {session_id}")

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
                "Access-Control-Allow-Origin": "*",
            }
        )
```

- [ ] **Step 5: Delete the `/conversations` endpoints** — remove `list_conversations`, `get_conversation` and `delete_conversation` (from `@router.get("/conversations")` through the `raise HTTPException(500, str(e))` of `delete_conversation`, lines 889-926). The frontend wrappers are removed in Task A14.

- [ ] **Step 6: Replace `apply_diff` / `reject_diff`** (from the `# Diff Apply/Reject Endpoints (Cascade-style)` comment block to the end of the file) with:

```python
    # -------------------------------------------------------------------------
    # Diff Apply/Reject Endpoints (Cascade-style)
    #
    # Live session first, then the store (messages.diff_proposals_json,
    # spec §8): active_sessions is evicted at the end of the turn, so a diff
    # proposed a moment ago is usually only on disk by the time the admin
    # clicks Apply.
    # -------------------------------------------------------------------------

    def _write_diff(diff: Dict[str, Any], diff_id: str) -> Dict[str, Any]:
        import os
        file_path = diff.get("file_path")
        new_content = diff.get("new_content")
        if not file_path or new_content is None:
            raise HTTPException(400, "Diff has no file path or content to apply; use the editor flow")
        try:
            os.makedirs(os.path.dirname(file_path) or ".", exist_ok=True)
            with open(file_path, "w") as f:
                f.write(new_content)
        except Exception as e:
            logger.error(f"Failed to apply diff: {e}")
            raise HTTPException(500, f"Failed to apply diff: {e}")
        diff["status"] = "applied"
        logger.info(f"Applied diff {diff_id} to {file_path}")
        return {"applied": True, "diff_id": diff_id, "file_path": file_path}

    @router.post("/diff/{session_id}/{diff_id}/apply")
    async def apply_diff(session_id: str, diff_id: str):
        """Apply a proposed file change (live session, else the store)."""
        ctx = _active_ctx(session_id)
        if ctx is not None and diff_id in getattr(ctx, "pending_diffs", {}):
            return _write_diff(ctx.pending_diffs[diff_id], diff_id)
        tm = _thread_manager()
        found = _find_stored_diff(tm, diff_id)
        if found is None:
            raise HTTPException(404, "Diff not found")
        message_id, proposals, index = found
        result = _write_diff(proposals[index], diff_id)
        try:
            tm.store.update_message(message_id, diff_proposals=proposals)
        except Exception as e:
            logger.warning(f"Could not persist diff status (non-fatal): {e}")
        return result

    @router.post("/diff/{session_id}/{diff_id}/reject")
    async def reject_diff(session_id: str, diff_id: str):
        """Reject a proposed file change without writing to disk."""
        ctx = _active_ctx(session_id)
        if ctx is not None and diff_id in getattr(ctx, "pending_diffs", {}):
            ctx.pending_diffs[diff_id]["status"] = "rejected"
            logger.info(f"Rejected diff {diff_id}")
            return {"rejected": True, "diff_id": diff_id}
        tm = _thread_manager()
        found = _find_stored_diff(tm, diff_id)
        if found is None:
            raise HTTPException(404, "Diff not found")
        message_id, proposals, index = found
        proposals[index]["status"] = "rejected"
        try:
            tm.store.update_message(message_id, diff_proposals=proposals)
        except Exception as e:
            logger.warning(f"Could not persist diff status (non-fatal): {e}")
        logger.info(f"Rejected diff {diff_id}")
        return {"rejected": True, "diff_id": diff_id}

    # -------------------------------------------------------------------------
    # Timeline and threads (Plan A, spec §11)
    # -------------------------------------------------------------------------

    _EMPTY_TIMELINE: Dict[str, Any] = {"turns": [], "has_more": False, "current_thread": None}

    @router.get("/timeline")
    async def get_timeline(before: Optional[str] = None, around: Optional[str] = None, limit: int = 50):
        """One page of the timeline, newest-last, grouped by turn.

        ``before`` pages backwards from a turn id; ``around`` centres on one
        (a chip click). Degrades to an empty page, never a 500 (spec §12).
        """
        tm = _thread_manager()
        if tm is None:
            return dict(_EMPTY_TIMELINE)
        try:
            page = max(1, min(int(limit), 200))
            turns = tm.store.list_turns(
                before_turn_id=before or None, around_turn_id=around or None, limit=page + 1,
            )
            has_more = len(turns) > page
            if has_more:
                turns = turns[-page:]
            return {"turns": turns, "has_more": has_more, "current_thread": _thread_summary(tm.current())}
        except Exception as e:
            logger.warning(f"Timeline unavailable (non-fatal): {e}")
            return dict(_EMPTY_TIMELINE)

    @router.get("/thread/current")
    async def get_current_thread():
        """The open thread as a dict (plus ``thread_id``), or null."""
        tm = _thread_manager()
        if tm is None:
            return None
        try:
            thread = tm.current()
        except Exception as e:
            logger.warning(f"Current thread unavailable (non-fatal): {e}")
            return None
        if not thread:
            return None
        body = dict(thread)
        body["thread_id"] = thread.get("id") or thread.get("thread_id")
        return body

    @router.delete("/thread/{thread_id}/recall/{recalled_thread_id}")
    async def retract_recall(thread_id: str, recalled_thread_id: str):
        """Mark a pulled-in thread as retracted on ``thread_id`` (spec §6)."""
        tm = _thread_manager()
        if tm is None:
            return {"ok": False}
        try:
            return {"ok": bool(tm.retract_recall(thread_id, recalled_thread_id))}
        except Exception as e:
            logger.warning(f"retract_recall failed (non-fatal): {e}")
            return {"ok": False}
```

- [ ] **Step 7: Run the tests**

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core && /Volumes/4TB-BAD/Halbert/.venv/bin/python -m pytest tests/test_agent_routes_timeline.py tests/test_tool_calling_bridge.py tests/test_threads.py tests/test_conversation_sqlite.py -q -p no:cacheprovider
```
Expected: `test_agent_routes_timeline.py`, `test_threads.py` (A6) and `test_conversation_sqlite.py` PASS; `test_tool_calling_bridge.py` still exactly its 3 baseline failures. If the paging test fails on `has_more`, check that A6's `list_turns(before_turn_id=…)` returns the turns strictly older than the anchor, newest-last: the endpoint asks for `limit + 1` and trims the oldest.

Then the whole backend suite:
```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core && /Volumes/4TB-BAD/Halbert/.venv/bin/python -m pytest tests -q -p no:cacheprovider 2>&1 | tail -8
```
Expected: only the 4 baseline failures (3 × `TestLLMClientAdapterTools`, 1 × `test_get_configured_model_returns_string`); no new failures.

- [ ] **Step 8: Commit**

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation && git add halbert_core/halbert_core/dashboard/routes/agent.py halbert_core/tests/test_agent_routes_timeline.py && git commit -m "feat(dashboard): timeline endpoints, stored diffs, no force-reset

/message no longer resets a live turn (the state machine's turn lock
queues it) and hands the ThreadManager to process(); GET /timeline,
GET /thread/current and DELETE /thread/{id}/recall/{id} read the SQLite
store and degrade to empty; diff apply/reject fall back to the
persisted proposal when the session is gone; the /agent/conversations
endpoints are deleted."
```

### Task A11b: POST /api/agent/message/{message_id}/redact ("forget this" for one row)

**Files:**
- Modify: `halbert_core/halbert_core/agents/conversation_sqlite.py` (constant + `redact_message` directly after `mark_in_progress_interrupted`, above the `# session_somatic_blocks (C1 link)` banner)
- Modify: `halbert_core/halbert_core/dashboard/routes/agent.py` (helper + endpoint appended after `retract_recall`, at the end of the file)
- Test: `halbert_core/tests/test_agent_routes_redact.py`

Context for the engineer: spec §5 "Forget / redact": per turn, "forget this" replaces `content` and `blocks_json` with `[redacted by admin]`, rewrites the FTS row and regenerates the receipt; rows are never deleted (the Haloysius retraction event is not in Plan A — no Haloysius line is written in Plan A at all). `blocks_json` must stay valid JSON (`_loads` in the readers falls back to `[]` otherwise), so it becomes a one-element list holding a marker block when the row had blocks, and `[]` when it had none. The receipt refresh goes through the ThreadManager when it offers `refresh_receipt` (public) or `_refresh_receipt` (A6's private name), else `build_receipt` + `upsert_receipt` directly.

- [ ] **Step 1: Write the failing test**

```python
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Plan A / A11b: POST /api/agent/message/{id}/redact forgets one row —
content and blocks replaced, FTS rewritten, receipt regenerated (spec §5)."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from halbert_core.agents.conversation_sqlite import SqliteConversationStore
from halbert_core.agents.threads import ThreadManager
from halbert_core.intake.signals import analyze_message
import halbert_core.dashboard.routes.agent as agent_routes

REDACTED = "[redacted by admin]"


@pytest.fixture
def tm(tmp_path):
    store = SqliteConversationStore(str(tmp_path / "threads.db"))
    manager = ThreadManager(store)
    yield manager
    store.close()


@pytest.fixture
def client(monkeypatch, tm):
    monkeypatch.setattr(agent_routes, "_thread_manager", lambda: tm)
    monkeypatch.setattr(agent_routes, "_agent_instance", None)
    app = FastAPI()
    app.include_router(agent_routes.router)
    return TestClient(app)


def _seed(tm, query, answer, blocks=None):
    turn = tm.begin_turn(query, analyze_message(query), "sess-redact")
    tm.end_turn(turn, assistant_text=answer, blocks=blocks or [], terminal_session_ids=[], diff_proposals=[])
    return turn


def test_redact_replaces_content_blocks_fts_and_receipt(client, tm):
    turn = _seed(
        tm, "set up the samba media share", "added [media] to smb.conf and ran testparm",
        blocks=[{"tool": "run_command", "args": {"command": "testparm"},
                 "result": "Loaded services file OK.", "exit": 0}],
    )
    tid = turn.thread_id
    assistant_id = tm.store.list_turns(limit=5)[-1]["assistant"]["message_id"]
    assert "testparm" in tm.store.get_thread(tid)["receipt"]
    assert tm.store.search("testparm", None, 5) == [tid]

    r = client.post(f"/api/agent/message/{assistant_id}/redact")
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True, "thread_id": tid}

    row = tm.store.list_turns(limit=5)[-1]
    assert row["assistant"]["content"] == REDACTED
    assert row["blocks"] == [{"tool": REDACTED, "args": {}, "result": REDACTED, "exit": None, "redacted": True}]
    assert row["user"]["content"] == "set up the samba media share"      # only the one row
    assert tm.store.search("testparm", None, 5) == []                     # FTS row rewritten
    receipt = tm.store.get_thread(tid)["receipt"]
    assert "testparm" not in receipt and REDACTED in receipt              # receipt regenerated
    assert tm.store.search("samba", None, 5) == [tid]                     # the user row is untouched
    assert tm.store.list_messages(tid)[-1]["metadata"]["redacted"] is True


def test_redact_a_row_without_blocks_keeps_blocks_empty(client, tm):
    turn = _seed(tm, "hello there", "hi!")
    user_id = tm.store.list_turns(limit=5)[-1]["user"]["message_id"]
    assert client.post(f"/api/agent/message/{user_id}/redact").json() == {"ok": True, "thread_id": turn.thread_id}
    row = tm.store.list_turns(limit=5)[-1]
    assert row["user"]["content"] == REDACTED and row["assistant"]["content"] == "hi!"
    assert row["blocks"] == []
    # idempotent: redacting twice is still ok
    assert client.post(f"/api/agent/message/{user_id}/redact").status_code == 200


def test_redact_unknown_row_is_404_and_no_store_is_503(client, tm, monkeypatch):
    assert client.post("/api/agent/message/999999/redact").status_code == 404
    monkeypatch.setattr(agent_routes, "_thread_manager", lambda: None)
    assert client.post("/api/agent/message/1/redact").status_code == 503


def test_store_redact_message_returns_none_for_missing_row_or_no_connection(tm, tmp_path):
    assert tm.store.redact_message(424242) is None
    dead = SqliteConversationStore(str(tmp_path / "x" / "y" / "z" / "not-creatable.db"))
    dead._conn = None
    assert dead.redact_message(1) is None
```

- [ ] **Step 2: Run it, expect failures**

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core && /Volumes/4TB-BAD/Halbert/.venv/bin/python -m pytest tests/test_agent_routes_redact.py -q -p no:cacheprovider
```
Expected: `assert 404 == 200` for the two redact tests (the route does not exist), `AttributeError: 'SqliteConversationStore' object has no attribute 'redact_message'` for the store test; `test_redact_unknown_row_is_404_and_no_store_is_503` fails on `assert 404 == 503`.

- [ ] **Step 3: Store method** — in `agents/conversation_sqlite.py`, directly after `mark_in_progress_interrupted` (its last lines are `logger.warning(f"mark_in_progress_interrupted failed: {e}")` / `return 0`) and above the `# ------` banner that precedes `# session_somatic_blocks (C1 link)`, insert:

```python
    # ------------------------------------------------------------------
    # Forget / redact (spec §5)
    # ------------------------------------------------------------------

    REDACTED = "[redacted by admin]"

    def redact_message(self, message_id: int) -> Optional[str]:
        """"Forget this" for one row: content and blocks become the
        redaction marker, diff proposals are dropped, metadata gains
        ``redacted``, and the FTS row is rewritten so the original words are
        unsearchable. The row itself is never deleted. Returns the thread id,
        or None when the row does not exist or the write failed (WARNING).
        The caller refreshes the thread's receipt.
        """
        if self._conn is None:
            return None
        try:
            with self._lock, self._conn:
                row = self._conn.execute(
                    "SELECT conversation_id, blocks_json, metadata FROM messages WHERE id = ?",
                    (int(message_id),),
                ).fetchone()
                if row is None:
                    return None
                thread_id = row["conversation_id"]
                # blocks_json stays valid JSON: one marker block when the row
                # had blocks (the timeline still shows that something ran),
                # an empty list when it had none.
                blocks = (
                    [{"tool": self.REDACTED, "args": {}, "result": self.REDACTED,
                      "exit": None, "redacted": True}]
                    if _loads(row["blocks_json"], []) else []
                )
                metadata = _loads(row["metadata"], {})
                if not isinstance(metadata, dict):
                    metadata = {}
                metadata["redacted"] = True
                self._conn.execute(
                    """UPDATE messages
                       SET content = ?, blocks_json = ?, diff_proposals_json = '[]', metadata = ?
                       WHERE id = ?""",
                    (self.REDACTED, json.dumps(blocks), json.dumps(metadata), int(message_id)),
                )
                if self._fts_ok:
                    self._conn.execute(
                        "DELETE FROM messages_fts WHERE rowid = ?", (int(message_id),)
                    )
                    self._conn.execute(
                        "INSERT INTO messages_fts(rowid, conversation_id, content) "
                        "VALUES (?, ?, ?)",
                        (int(message_id), thread_id, self.REDACTED),
                    )
            return thread_id
        except Exception as e:
            logger.warning(f"redact_message {message_id} failed: {e}")
            return None

```

- [ ] **Step 4: Endpoint** — in `dashboard/routes/agent.py`, directly after the `retract_recall` endpoint (the file currently ends with its `return {"ok": False}`), append:

```python

    def _refresh_thread_receipt(tm, thread_id: str) -> None:
        """Regenerate a thread's receipt after a redaction (spec §5)."""
        refresh = getattr(tm, "refresh_receipt", None) or getattr(tm, "_refresh_receipt", None)
        if callable(refresh):
            refresh(thread_id)
            return
        from ...agents.receipt import build_receipt
        thread = tm.store.get_thread(thread_id)
        if thread is None:
            return
        receipt = build_receipt(thread, tm.store.list_messages(thread_id))
        tm.store.upsert_receipt(thread_id, thread.get("title") or "", receipt)

    @router.post("/message/{message_id}/redact")
    async def redact_message(message_id: int):
        """"Forget this" for one row (spec §5): content and blocks become
        "[redacted by admin]", the FTS row is rewritten and the thread's
        receipt is regenerated. Rows are never deleted."""
        tm = _thread_manager()
        if tm is None:
            raise HTTPException(503, "Thread store unavailable")
        thread_id = tm.store.redact_message(message_id)
        if thread_id is None:
            raise HTTPException(404, "Message not found")
        try:
            _refresh_thread_receipt(tm, thread_id)
        except Exception as e:
            logger.warning(f"Receipt refresh after redaction failed (non-fatal): {e}")
        return {"ok": True, "thread_id": thread_id}
```

- [ ] **Step 5: Run the tests**

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core && /Volumes/4TB-BAD/Halbert/.venv/bin/python -m pytest tests/test_agent_routes_redact.py tests/test_agent_routes_timeline.py tests/test_conversation_sqlite.py tests/test_threads.py -q -p no:cacheprovider
```
Expected: all PASS (`4 passed` from the new file).

- [ ] **Step 6: Commit**

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation && git add halbert_core/halbert_core/agents/conversation_sqlite.py halbert_core/halbert_core/dashboard/routes/agent.py halbert_core/tests/test_agent_routes_redact.py && git commit -m "feat(dashboard): redact one message row on request

POST /api/agent/message/{id}/redact replaces the row's content and
blocks with '[redacted by admin]', drops its diff proposals, rewrites
the messages_fts row and regenerates the thread receipt through the
ThreadManager. Rows are never deleted (spec §5)."
```

---

**Contract additions (planner M), for the verifier to propagate:**

- `StateContext` gains, beyond §5: `terminal_session_ids: List[str] = field(default_factory=list)` and `turn_context: Optional[Any] = None` (the `TurnContext` from `ThreadManager.begin_turn`, cleared by `_end_turn`).
- `tools/safety.py`: `THREAD_META_TOOLS = ("new_thread", "recall_thread", "resume_thread")`, imported by `tools/executor.py` and `agents/state_machine.py`.
- `AgentStateMachine.TRANSITIONS[PLANNING]` includes `PLANNING`. New methods: `_supersede_paused_turn(session_id)`, `_settle_turn(session_id)`, `_begin_turn()` (async gen), `_turn_status(session_id) -> "complete"|"cancelled"|"interrupted"`, `_tool_block(tc) -> {tool, args, result, exit, execution_id, status, error}`, `_end_turn(status)`, `_handle_meta_tool(name, args)` (async gen), `_note_terminal_payload(payload)`. A `new_thread` without a manager (or when the store fails) still switches to an in-memory uuid thread id.
- `AgentPromptBuilder.CONTINUITY_PREAMBLE: dict[voice, str]`, `_continuity_section(continuity) -> List[str]`, `_history_section(history) -> str`; `build_planning_prompt` section order is now context, observations, instructions, plan, continuity, `## Current Task` (last).
- `model/client.py`: `compute_num_ctx`, `num_ctx_for_model(model, prompt_tokens_estimate, num_predict, model_max=None)` with a monotonic per-model cache `_NUM_CTX_CACHE`, `estimate_prompt_tokens(messages, tools)`; Ollama `options` always carries `num_ctx`; `options["num_ctx"]` and `options["num_ctx_max"]` are honoured overrides.
- `ThreadManager` must expose its store as `self.store` (routes use `tm.store.list_turns`, `tm.store.update_message`, `tm.store.update_thread`, `tm.store.get_thread`); `update_thread(recalled_json=<list>)` accepts a Python list (json-encoded by the store); `TurnContext.recalled` entries have the `recall()` result shape; the A6 test file is assumed to be `tests/test_threads.py`.
- `routes/agent.py` helpers: `_thread_manager()`, `_thread_summary(thread)`, `_active_ctx(session_id)`, `_find_stored_diff(tm, diff_id)`; `GET /api/agent/thread/current` returns the thread dict with a mirrored `thread_id`, or JSON `null`.
- `recall_thread` results are appended to `ctx.recalled_threads` and injected as `retrieved_context` entries with `source="thread"`; `resume_thread` resets `conversation_history` to one system row `[Earlier in this subject: <receipt>]`.
- `StreamEvent.thread_recalled(session_id, thread_id, title, date, match_terms, mode, last_turn_id=None)` — `data.last_turn_id` is the recalled thread's newest `turn_id` (from a `last_turn_id` key on the recall result if the S part supplies one, else `AgentStateMachine._last_turn_id(thread_id)` reading `thread_manager.store.list_messages`); None without a store. Planner F may use it to scroll the timeline on chip click.
- `process()` yields `StreamEvent.conversation_status(session_id, "waiting", waiting_for="previous turn")` before it blocks on `turn_lock` when the lock is already held (spec §12). The status string is `"waiting"` (not a `ConversationStatus` member).
- `_supersede_paused_turn` → `_record_superseded_turn(old_ctx)`: an evicted AWAITING_CONFIRMATION session that has a `turn_context` is ended via `thread_manager.end_turn(turn, assistant_text="", blocks=[{tool, args, result: "not run — superseded", exit: None, status: "superseded"}], terminal_session_ids=[], diff_proposals=[], status="cancelled")`; `build_receipt` (A2) should render such a block on its Commands line as `<cmd> (not run — superseded)`.
- `_emit_somatic_block` passes `thread_id=ctx.thread_id or ctx.session_id` into the `somatic_block` event data; nothing calls `SqliteConversationStore.add_somatic_block` today.
- `AgentPromptBuilder.CONTINUITY_PREAMBLE_NO_TOOLS: dict[voice, str]`; `build_planning_prompt(..., tools_supported: Optional[bool] = None)` and `build_response_prompt(..., tools_supported: Optional[bool] = None)`; the state machine passes `getattr(self.llm, "tools_supported", None)`.
- `model/client.py`: `_TOOLS_REJECTED: Dict[str, bool]`, `model_supports_tools(model) -> Optional[bool]`; `LLMClientAdapter.tools_supported` and `OllamaClient.tools_supported` (`Optional[bool]`, default None, False after a no-tools fallback).
- `intake/budget.py`: MEDIUM `conversation=1600` (others 75/50/100/50/50/75), LARGE `conversation=2400` (others 125/100/400/275/250/450); totals unchanged. `ContextAssembler._format_conversation` renders a leading `{"role": "system", "content": "[Earlier in this subject: …]"}` row as its own `## Earlier in this subject` block and skips `should_summarize` for the remaining rows.
- `SqliteConversationStore.redact_message(message_id: int) -> Optional[str]` (returns the thread id; `REDACTED = "[redacted by admin]"` class constant); `POST /api/agent/message/{message_id}/redact -> {ok, thread_id}` (404 unknown row, 503 no store); the route calls `ThreadManager.refresh_receipt` / `_refresh_receipt` when present, else `build_receipt` + `upsert_receipt`.

---

### Task A12a: `agents/migrations.py` — both legacy JSON shapes become closed threads

**Files:**
- Create: `/Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core/halbert_core/agents/migrations.py`
- Test: `/Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core/tests/test_migrations.py`

Context for the engineer: two JSON conversation stores exist today. `agents/conversation.py::ConversationStore` writes `~/.halbert/conversations/<conversation_id>.json` with the shape `{conversation_id, user_id, title, messages:[{role, content, timestamp: float, metadata}], created_at: float, updated_at: float, metadata}`. `dashboard/routes/conversations.py` writes `~/.config/halbert/conversations/<id>.json` with the shape `{id, name, created_at: ISO str, updated_at: ISO str, persona, messages:[{id, role, content, timestamp: ISO str, mentions, tool_calls, reasoning}]}`. Both go away in A12c/A12d; this task moves their history into the SQLite thread store (A1–A3) as **closed** threads with receipts (A2), idempotently. The Python in the venv is 3.10, so `datetime.fromisoformat` does not accept a trailing `Z` — the parser below handles it.

- [ ] **Step 1: Write the failing test**

Create `halbert_core/tests/test_migrations.py`:

```python
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for the one-time JSON -> SQLite thread migration (spec §8, Plan A).

Both legacy on-disk shapes must land as closed threads with receipts, exactly
once, and a bad file must never stop the others.
"""

import json
from datetime import datetime

import pytest

from halbert_core.agents.conversation_sqlite import SqliteConversationStore
from halbert_core.agents.migrations import migrate_legacy_conversations


AGENT_CONV = {
    "conversation_id": "agent-1",
    "user_id": "u1",
    "title": "Disk usage on /var",
    "messages": [
        {"role": "user", "content": "why is /var filling up on this box",
         "timestamp": 1720000000.0, "metadata": {}},
        {"role": "assistant",
         "content": "journald is the culprit. Next, run journalctl --vacuum-size=200M.",
         "timestamp": 1720000060.0, "metadata": {}},
    ],
    "created_at": 1720000000.0,
    "updated_at": 1720000060.0,
    "metadata": {},
}

LEGACY_CONV = {
    "id": "legacy-1",
    "name": "Chat Jul 14, 10:00 AM",
    "created_at": "2026-07-14T10:00:00",
    "updated_at": "2026-07-14T10:05:00",
    "persona": "guide",
    "messages": [
        {"id": "m0", "role": "assistant",
         "content": "Hi! I'm Halbert, your system assistant.",
         "timestamp": "2026-07-14T10:00:00", "mentions": [], "tool_calls": []},
        {"id": "m1", "role": "user",
         "content": "configure the samba share for the media folder",
         "timestamp": "2026-07-14T10:01:00", "mentions": [], "tool_calls": []},
        {"id": "m2", "role": "assistant",
         "content": "I added [media] to /etc/samba/smb.conf and restarted smbd.",
         "timestamp": "2026-07-14T10:05:00Z", "mentions": [], "tool_calls": [],
         "reasoning": None},
    ],
}


def _tid(thread):
    return thread.get("thread_id") or thread.get("id")


@pytest.fixture
def store(tmp_path):
    s = SqliteConversationStore(str(tmp_path / "threads.db"))
    yield s
    s.close()


@pytest.fixture
def dirs(tmp_path):
    agent_dir = tmp_path / "agent-json"
    legacy_dir = tmp_path / "legacy-json"
    agent_dir.mkdir()
    legacy_dir.mkdir()
    (agent_dir / "agent-1.json").write_text(json.dumps(AGENT_CONV))
    (legacy_dir / "legacy-1.json").write_text(json.dumps(LEGACY_CONV))
    return agent_dir, legacy_dir


class TestBothShapes:
    def test_both_shapes_become_closed_threads(self, store, dirs):
        agent_dir, legacy_dir = dirs
        counts = migrate_legacy_conversations(
            store, agent_dir=agent_dir, legacy_dir=legacy_dir
        )
        assert counts == {"agent_json": 1, "legacy_json": 1}

        a = store.get_thread("agent-1")
        assert a is not None
        assert a["status"] == "closed"
        assert a["title"] == "Disk usage on /var"
        assert a["last_active"] == 1720000060.0

        l = store.get_thread("legacy-1")
        assert l is not None
        assert l["status"] == "closed"
        assert l["title"] == "Chat Jul 14, 10:00 AM"

        # no thread was left open by the migration
        assert store.current_open_thread() is None

    def test_messages_keep_order_roles_and_origins(self, store, dirs):
        agent_dir, legacy_dir = dirs
        migrate_legacy_conversations(store, agent_dir=agent_dir, legacy_dir=legacy_dir)

        rows = store.recent_messages("legacy-1", limit=12)
        assert [r["role"] for r in rows] == ["assistant", "user", "assistant"]
        assert [r["origin"] for r in rows] == ["assistant", "human", "assistant"]
        assert rows[1]["content"] == "configure the samba share for the media folder"

        rows = store.recent_messages("agent-1", limit=12)
        assert [r["content"][:6] for r in rows] == ["why is", "journa"]

    def test_legacy_iso_timestamps_become_floats(self, store, dirs):
        agent_dir, legacy_dir = dirs
        migrate_legacy_conversations(store, agent_dir=agent_dir, legacy_dir=legacy_dir)
        rows = store.recent_messages("legacy-1", limit=12)
        assert rows[1]["timestamp"] == datetime(2026, 7, 14, 10, 1, 0).timestamp()
        # trailing 'Z' (UTC) parses on Python 3.10 too
        assert rows[2]["timestamp"] == datetime.fromisoformat(
            "2026-07-14T10:05:00+00:00"
        ).timestamp()
        assert store.get_thread("legacy-1")["last_active"] == rows[2]["timestamp"]

    def test_receipt_built_and_indexed_for_recall(self, store, dirs):
        agent_dir, legacy_dir = dirs
        migrate_legacy_conversations(store, agent_dir=agent_dir, legacy_dir=legacy_dir)

        l = store.get_thread("legacy-1")
        assert l["receipt"].startswith("Title:")
        assert "Started with:" in l["receipt"]
        assert "samba" in l["receipt"].lower()
        assert "samba" in l["entities_json"]
        assert "network" in l["topic_domains"]

        hits = store.search_receipts("samba")
        assert [h["thread_id"] for h in hits] == ["legacy-1"]
        hits = store.search_receipts("journalctl")
        assert [h["thread_id"] for h in hits] == ["agent-1"]


class TestIdempotence:
    def test_second_run_is_a_noop(self, store, dirs):
        agent_dir, legacy_dir = dirs
        first = migrate_legacy_conversations(store, agent_dir=agent_dir, legacy_dir=legacy_dir)
        assert first == {"agent_json": 1, "legacy_json": 1}
        again = migrate_legacy_conversations(store, agent_dir=agent_dir, legacy_dir=legacy_dir)
        assert again == {"agent_json": 0, "legacy_json": 0}
        assert len(store.recent_messages("legacy-1", limit=50)) == 3
        assert len(store.recent_messages("agent-1", limit=50)) == 2

    def test_existing_thread_id_is_not_reimported(self, store, dirs):
        agent_dir, legacy_dir = dirs
        # A live thread already uses this id: leave it alone, record the file as done.
        from halbert_core.agents.conversation import Conversation
        store.save(Conversation(conversation_id="agent-1", title="live thread"))
        store.append_message("agent-1", "user", "live row", origin="human")
        counts = migrate_legacy_conversations(store, agent_dir=agent_dir, legacy_dir=legacy_dir)
        assert counts == {"agent_json": 0, "legacy_json": 1}
        assert [r["content"] for r in store.recent_messages("agent-1", limit=50)] == ["live row"]
        assert store.get_thread("agent-1")["title"] == "live thread"
        # and it stays done on the next run
        assert migrate_legacy_conversations(
            store, agent_dir=agent_dir, legacy_dir=legacy_dir
        ) == {"agent_json": 0, "legacy_json": 0}


class TestRobustness:
    def test_missing_dirs_return_zero(self, store, tmp_path):
        counts = migrate_legacy_conversations(
            store, agent_dir=tmp_path / "nope-a", legacy_dir=tmp_path / "nope-b"
        )
        assert counts == {"agent_json": 0, "legacy_json": 0}

    def test_corrupt_file_is_skipped_and_retried_later(self, store, dirs):
        agent_dir, legacy_dir = dirs
        bad = agent_dir / "broken.json"
        bad.write_text("{not json")
        counts = migrate_legacy_conversations(store, agent_dir=agent_dir, legacy_dir=legacy_dir)
        assert counts == {"agent_json": 1, "legacy_json": 1}
        assert store.get_thread("agent-1") is not None

        # fix the file: it migrates on the next run, nothing else re-runs
        fixed = dict(AGENT_CONV, conversation_id="agent-2", title="second")
        bad.write_text(json.dumps(fixed))
        counts = migrate_legacy_conversations(store, agent_dir=agent_dir, legacy_dir=legacy_dir)
        assert counts == {"agent_json": 1, "legacy_json": 0}
        assert store.get_thread("agent-2")["status"] == "closed"

    def test_empty_conversation_is_marked_done_not_counted(self, store, tmp_path):
        agent_dir = tmp_path / "a"
        agent_dir.mkdir()
        (agent_dir / "empty.json").write_text(json.dumps(
            dict(AGENT_CONV, conversation_id="empty-1", messages=[])
        ))
        counts = migrate_legacy_conversations(store, agent_dir=agent_dir, legacy_dir=tmp_path / "none")
        assert counts == {"agent_json": 0, "legacy_json": 0}
        assert store.get_thread("empty-1") is None

    def test_title_falls_back_to_provisional_from_first_user_line(self, store, tmp_path):
        agent_dir = tmp_path / "a"
        agent_dir.mkdir()
        (agent_dir / "untitled.json").write_text(json.dumps(
            dict(AGENT_CONV, conversation_id="untitled-1", title=None)
        ))
        migrate_legacy_conversations(store, agent_dir=agent_dir, legacy_dir=tmp_path / "none")
        t = store.get_thread("untitled-1")
        assert t["title"] == "why is /var filling up on this box"
        assert t["title_source"] == "provisional"

    def test_store_without_connection_is_a_noop(self, dirs):
        agent_dir, legacy_dir = dirs
        dead = SqliteConversationStore(str(agent_dir / "x" / "y" / "z" / "not-creatable.db"))
        dead._conn = None
        assert migrate_legacy_conversations(
            dead, agent_dir=agent_dir, legacy_dir=legacy_dir
        ) == {"agent_json": 0, "legacy_json": 0}
```

- [ ] **Step 2: Run it and watch it fail**

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core && /Volumes/4TB-BAD/Halbert/.venv/bin/python -m pytest tests/test_migrations.py -q -p no:cacheprovider
```

Expected: collection error containing `ModuleNotFoundError: No module named 'halbert_core.agents.migrations'` and `1 error`.

- [ ] **Step 3: Write the implementation**

Create `halbert_core/halbert_core/agents/migrations.py`:

```python
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""One-time migration of the two legacy JSON conversation stores into the
SQLite thread store (spec §8, Plan A).

Two on-disk shapes existed before Plan A:

* ``~/.halbert/conversations/*.json`` — the old ``agents/conversation.py``
  ``ConversationStore`` shape: ``conversation_id``, ``title``, ``messages``
  with float ``timestamp`` values.
* ``~/.config/halbert/conversations/*.json`` — the old
  ``dashboard/routes/conversations.py`` shape: ``id``, ``name``, ``persona``,
  ``messages`` with ISO-8601 ``timestamp`` strings.

Every file becomes one **closed** thread with a deterministic receipt so
recall can find it. Idempotent: each source path is recorded in a
``migrations_done`` table once its thread is fully written and is never read
again. Files that fail to parse are skipped (WARNING), not recorded, and
retried on the next boot. Counts only successful saves.
"""

from __future__ import annotations

import contextlib
import json
import logging
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..intake.signals import analyze_message, canonical_entities
from .blocks import content_to_text
from .conversation import Conversation
from .conversation_sqlite import SqliteConversationStore
from .receipt import build_receipt, provisional_title

logger = logging.getLogger("halbert.agents.migrations")

AGENT_JSON_DIR = Path.home() / ".halbert" / "conversations"
LEGACY_JSON_DIR = Path.home() / ".config" / "halbert" / "conversations"

_ROLE_ORIGIN = {"user": "human", "assistant": "assistant", "system": "system"}


# ---------------------------------------------------------------------------
# migrations_done bookkeeping (private store handle; same package)
# ---------------------------------------------------------------------------

def _lock_of(store: SqliteConversationStore):
    return getattr(store, "_lock", None) or contextlib.nullcontext()


def _ensure_migrations_table(store: SqliteConversationStore) -> bool:
    conn = getattr(store, "_conn", None)
    if conn is None:
        return False
    try:
        with _lock_of(store):
            with conn:
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS migrations_done ("
                    "source_path TEXT PRIMARY KEY, "
                    "thread_id   TEXT, "
                    "migrated_at REAL NOT NULL)"
                )
        return True
    except Exception as e:
        logger.warning(f"migrations_done table unavailable: {e}")
        return False


def _already_done(store: SqliteConversationStore, source_path: str) -> bool:
    with _lock_of(store):
        row = store._conn.execute(
            "SELECT 1 FROM migrations_done WHERE source_path = ?", (source_path,)
        ).fetchone()
    return row is not None


def _mark_done(store: SqliteConversationStore, source_path: str, thread_id: str) -> None:
    with _lock_of(store):
        with store._conn:
            store._conn.execute(
                "INSERT OR REPLACE INTO migrations_done "
                "(source_path, thread_id, migrated_at) VALUES (?, ?, ?)",
                (source_path, thread_id, time.time()),
            )


# ---------------------------------------------------------------------------
# Shape normalisation
# ---------------------------------------------------------------------------

def _parse_timestamp(value: Any, fallback: float) -> float:
    """float/int pass through; ISO-8601 strings (with or without a trailing
    ``Z``) become epoch seconds; anything else -> ``fallback``."""
    if isinstance(value, bool):
        return fallback
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and value.strip():
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(text).timestamp()
        except ValueError:
            pass
    return fallback


def _normalise(data: Any, file_mtime: float) -> Optional[Dict[str, Any]]:
    """Reduce either JSON shape to one record, or None if unrecognised.

    Record: ``{thread_id, title, user_id, created_at, updated_at,
    messages: [{role, content, timestamp}]}`` — messages in file order,
    empty content dropped, timestamps as floats (a missing timestamp
    inherits the previous row's).
    """
    if not isinstance(data, dict):
        return None
    if "conversation_id" in data:
        thread_id = str(data.get("conversation_id") or "").strip()
        title = data.get("title")
        user_id = data.get("user_id")
    elif "id" in data and "messages" in data:
        thread_id = str(data.get("id") or "").strip()
        title = data.get("name")
        user_id = None
    else:
        return None
    if not thread_id:
        return None

    created_at = _parse_timestamp(data.get("created_at"), file_mtime)
    updated_at = _parse_timestamp(data.get("updated_at"), created_at)

    messages: List[Dict[str, Any]] = []
    last_ts = created_at
    for raw in data.get("messages") or []:
        if not isinstance(raw, dict):
            continue
        role = str(raw.get("role") or "user").strip().lower()
        content = raw.get("content")
        if isinstance(content, list):
            content = content_to_text(content)
        content = str(content or "").strip()
        if not content:
            continue
        ts = _parse_timestamp(raw.get("timestamp"), last_ts)
        last_ts = ts
        messages.append({"role": role, "content": content, "timestamp": ts})

    if messages:
        updated_at = max(updated_at, messages[-1]["timestamp"])

    first_user = next((m["content"] for m in messages if m["role"] == "user"), "")
    title = (str(title).strip() if title else "") or provisional_title(first_user) or "Untitled"

    return {
        "thread_id": thread_id,
        "title": title,
        "user_id": user_id,
        "created_at": created_at,
        "updated_at": updated_at,
        "messages": messages,
    }


# ---------------------------------------------------------------------------
# Writing one thread
# ---------------------------------------------------------------------------

def _write_thread(store: SqliteConversationStore, rec: Dict[str, Any]) -> bool:
    """Create the thread row, append every message, close it, index its
    receipt. Returns False (after a WARNING) if any store call refused."""
    tid = rec["thread_id"]
    title = rec["title"]

    store.save(Conversation(
        conversation_id=tid,
        user_id=rec["user_id"],
        title=title,
        created_at=rec["created_at"],
        updated_at=rec["updated_at"],
    ))
    if store.get_thread(tid) is None:
        logger.warning(f"migration: thread row for {tid} was not created")
        return False

    rows: List[Dict[str, Any]] = []
    turn_id: Optional[str] = None
    for m in rec["messages"]:
        role = m["role"]
        origin = _ROLE_ORIGIN.get(role, "system")
        if role == "user" or turn_id is None:
            turn_id = str(uuid.uuid4())
        message_id = store.append_message(
            tid, role, m["content"],
            origin=origin,
            turn_id=turn_id,
            status="complete",
            timestamp=m["timestamp"],
        )
        if message_id is None:
            logger.warning(f"migration: append_message failed for thread {tid}")
            return False
        rows.append({
            "role": role, "content": m["content"], "timestamp": m["timestamp"],
            "origin": origin, "blocks": [],
        })
        if role == "assistant":
            turn_id = None

    human_text = "\n".join(m["content"] for m in rec["messages"] if m["role"] == "user")
    all_text = "\n".join(m["content"] for m in rec["messages"])
    domains = list(analyze_message(human_text).detected_domains) if human_text.strip() else []
    entities = sorted(canonical_entities(all_text))

    if not store.update_thread(
        tid,
        status="closed",
        last_active=rec["messages"][-1]["timestamp"],
        topic_domains=domains,
        entities_json=entities,
        title_source="provisional",
        updated_at=rec["updated_at"],
    ):
        logger.warning(f"migration: update_thread failed for thread {tid}")
        return False

    thread = store.get_thread(tid) or {
        "id": tid, "thread_id": tid, "title": title, "status": "closed",
        "topic_domains": domains, "entities_json": entities,
    }
    receipt = build_receipt(thread, rows)
    if not store.upsert_receipt(tid, title, receipt):
        logger.warning(f"migration: upsert_receipt failed for thread {tid}")
        return False
    return True


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _migrate_dir(store: SqliteConversationStore, directory: Path) -> int:
    if not directory.is_dir():
        return 0
    migrated = 0
    for file_path in sorted(directory.glob("*.json")):
        source = str(file_path.resolve())
        try:
            if _already_done(store, source):
                continue
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            rec = _normalise(data, file_path.stat().st_mtime)
            if rec is None:
                logger.warning(f"migration skipped {file_path}: unrecognised shape")
                continue
            if not rec["messages"]:
                _mark_done(store, source, rec["thread_id"])
                continue
            if store.get_thread(rec["thread_id"]) is not None:
                logger.info(
                    f"migration: thread {rec['thread_id']} already exists, "
                    f"leaving it and recording {file_path.name} as done"
                )
                _mark_done(store, source, rec["thread_id"])
                continue
            if _write_thread(store, rec):
                _mark_done(store, source, rec["thread_id"])
                migrated += 1
            else:
                logger.warning(f"migration of {file_path} did not complete; retrying next boot")
        except Exception as e:
            logger.warning(f"migration skipped {file_path}: {e}")
    return migrated


def migrate_legacy_conversations(
    store: SqliteConversationStore,
    *,
    agent_dir: Optional[Path] = None,
    legacy_dir: Optional[Path] = None,
) -> Dict[str, int]:
    """Migrate every legacy JSON conversation into ``store`` as a closed
    thread. Returns ``{"agent_json": n, "legacy_json": m}`` — successful
    saves only. Safe to call on every boot.

    ``agent_dir`` / ``legacy_dir`` default to the two historical locations
    and exist so tests can point at temp directories.
    """
    counts = {"agent_json": 0, "legacy_json": 0}
    if getattr(store, "_conn", None) is None:
        logger.warning("migration skipped: thread store has no connection")
        return counts
    if not _ensure_migrations_table(store):
        return counts
    counts["agent_json"] = _migrate_dir(store, Path(agent_dir or AGENT_JSON_DIR))
    counts["legacy_json"] = _migrate_dir(store, Path(legacy_dir or LEGACY_JSON_DIR))
    if counts["agent_json"] or counts["legacy_json"]:
        logger.info(
            f"Migrated legacy conversations into threads: "
            f"{counts['agent_json']} agent JSON, {counts['legacy_json']} dashboard JSON"
        )
    return counts
```

- [ ] **Step 4: Run the tests**

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core && /Volumes/4TB-BAD/Halbert/.venv/bin/python -m pytest tests/test_migrations.py -q -p no:cacheprovider
```

Expected: `12 passed`.

- [ ] **Step 5: Commit**

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation && git add halbert_core/halbert_core/agents/migrations.py halbert_core/tests/test_migrations.py && git commit -m "feat(agents): migrate both legacy JSON conversation stores into closed threads" -m "migrate_legacy_conversations reads ~/.halbert/conversations (agent shape, float timestamps) and ~/.config/halbert/conversations (dashboard shape, ISO timestamps), appends every row through append_message, closes the thread and indexes a deterministic receipt so recall can find it. Idempotent through a migrations_done table keyed by source path; bad files are skipped and retried."
```

---

### Task A12b: boot hooks in `dashboard/app.py` — migrate once, mark interrupted turns

**Files:**
- Modify: `/Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core/halbert_core/dashboard/app.py` (insert a module-level function after line 54; insert a call in `startup_event` after line 333)
- Test: `/Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core/tests/test_conversation_boot_hooks.py`

- [ ] **Step 1: Write the failing test**

Create `halbert_core/tests/test_conversation_boot_hooks.py`:

```python
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Dashboard startup runs the Plan A conversation hooks exactly once:
migrate the legacy JSON stores, then mark any in-flight turn as interrupted
(spec §12: "interrupted at boot for any in_progress row"). Never fatal."""

import inspect

import pytest

pytest.importorskip("fastapi")

from halbert_core.dashboard import app as dashboard_app  # noqa: E402


class _FakeThreadManager:
    def __init__(self):
        self.store = object()
        self.mark_calls = 0

    def mark_interrupted(self):
        self.mark_calls += 1
        return 2


def test_hooks_migrate_then_mark_interrupted(monkeypatch):
    tm = _FakeThreadManager()
    calls = []
    monkeypatch.setattr("halbert_core.agents.threads.get_thread_manager", lambda: tm)

    def fake_migrate(store):
        calls.append(("migrate", store, tm.mark_calls))
        return {"agent_json": 3, "legacy_json": 1}

    monkeypatch.setattr(
        "halbert_core.agents.migrations.migrate_legacy_conversations", fake_migrate
    )

    result = dashboard_app.run_conversation_boot_hooks()

    # migration ran once, against the manager's store, before mark_interrupted
    assert calls == [("migrate", tm.store, 0)]
    assert tm.mark_calls == 1
    assert result == {"agent_json": 3, "legacy_json": 1, "interrupted": 2}


def test_hooks_never_raise(monkeypatch):
    def boom():
        raise RuntimeError("no database")

    monkeypatch.setattr("halbert_core.agents.threads.get_thread_manager", boom)
    assert dashboard_app.run_conversation_boot_hooks() == {
        "agent_json": 0, "legacy_json": 0, "interrupted": 0,
    }


def test_mark_interrupted_failure_keeps_migration_counts(monkeypatch):
    tm = _FakeThreadManager()

    def bad_mark():
        raise RuntimeError("locked")

    tm.mark_interrupted = bad_mark
    monkeypatch.setattr("halbert_core.agents.threads.get_thread_manager", lambda: tm)
    monkeypatch.setattr(
        "halbert_core.agents.migrations.migrate_legacy_conversations",
        lambda store: {"agent_json": 1, "legacy_json": 0},
    )
    assert dashboard_app.run_conversation_boot_hooks() == {
        "agent_json": 1, "legacy_json": 0, "interrupted": 0,
    }


def test_startup_event_calls_the_hooks():
    src = inspect.getsource(dashboard_app.create_app)
    assert "run_conversation_boot_hooks()" in src
    # it runs before the identity bootstrap and the background starters
    assert src.index("run_conversation_boot_hooks()") < src.index("Bootstrap system identity")
```

- [ ] **Step 2: Run it and watch it fail**

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core && /Volumes/4TB-BAD/Halbert/.venv/bin/python -m pytest tests/test_conversation_boot_hooks.py -q -p no:cacheprovider
```

Expected: `4 failed`, each with `AttributeError: module 'halbert_core.dashboard.app' has no attribute 'run_conversation_boot_hooks'` (the last one with `assert 'run_conversation_boot_hooks()' in src` failing if the attribute error is raised later — either way 4 failures).

- [ ] **Step 3: Write the implementation**

In `halbert_core/halbert_core/dashboard/app.py`, immediately after the existing `_find_config_registry` function (it ends with `    return None`), insert ONLY the `run_conversation_boot_hooks` function below — do not re-paste `_find_config_registry`:

```python
def run_conversation_boot_hooks() -> dict:
    """Plan A boot hooks for the one continuous conversation (spec §8, §12).

    1. Migrate the two legacy JSON conversation stores into the SQLite
       thread store as closed threads (idempotent, counts successful saves).
    2. Mark every message row still ``in_progress`` from a previous process
       as ``interrupted`` so the timeline can render "(Halbert restarted here)".

    Runs synchronously at startup, before the background starters. Never
    raises: a failure here must not stop the dashboard from serving.
    """
    result = {"agent_json": 0, "legacy_json": 0, "interrupted": 0}
    try:
        from ..agents.threads import get_thread_manager
        from ..agents.migrations import migrate_legacy_conversations

        tm = get_thread_manager()
        counts = migrate_legacy_conversations(tm.store)
        result["agent_json"] = int(counts.get("agent_json", 0))
        result["legacy_json"] = int(counts.get("legacy_json", 0))
        try:
            result["interrupted"] = int(tm.mark_interrupted())
        except Exception as e:
            logger.warning(f"Could not mark interrupted turns (non-fatal): {e}")
        logger.info(
            "Conversation boot hooks: migrated %d agent JSON + %d dashboard JSON "
            "conversations, %d interrupted turn(s) marked",
            result["agent_json"], result["legacy_json"], result["interrupted"],
        )
    except Exception as e:
        logger.warning(f"Conversation boot hooks failed (non-fatal): {e}")
    return result
```

Then inside `startup_event`, after the indexing-state reset block (current lines 327–333) and before the `# Bootstrap system identity` comment, insert the call:

```python
        # Reset indexing state to prevent stuck state from hot-reload
        try:
            from .routes.settings import _reset_indexing_state
            _reset_indexing_state()
            logger.info("Indexing state reset on startup")
        except Exception as e:
            logger.warning(f"Failed to reset indexing state: {e}")

        # Plan A: one-time JSON -> SQLite conversation migration, then mark any
        # turn that was in flight when the last process died as interrupted.
        # Synchronous on purpose: the first /api/agent/message must see the
        # migrated threads and no phantom in_progress rows.
        run_conversation_boot_hooks()
        
        # Bootstrap system identity (if not already done)
```

- [ ] **Step 4: Run the tests**

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core && /Volumes/4TB-BAD/Halbert/.venv/bin/python -m pytest tests/test_conversation_boot_hooks.py tests/test_dashboard_cors.py -q -p no:cacheprovider
```

Expected: all pass (`4 passed` from the new file plus the CORS tests; `create_app()` still imports).

- [ ] **Step 5: Commit**

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation && git add halbert_core/halbert_core/dashboard/app.py halbert_core/tests/test_conversation_boot_hooks.py && git commit -m "feat(dashboard): run the conversation migration and mark interrupted turns at startup" -m "run_conversation_boot_hooks() migrates the legacy JSON stores through the thread manager's store and then marks any in_progress row as interrupted. Called synchronously in startup_event before the identity bootstrap; never raises."
```

---

### Task A12c: delete the `/api/conversations` router, its doc section, its frontend wrappers, and `/agent/conversations`

**Files:**
- Delete: `/Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core/halbert_core/dashboard/routes/conversations.py`
- Modify: `/Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core/halbert_core/dashboard/app.py` (line 231 import list; line 243 include — line numbers as of A12b's start, shifted by the A12b insertion, so match by text)
- Modify (if still present): `/Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core/halbert_core/dashboard/routes/agent.py` lines 889–926 (the three `/conversations` endpoints)
- Modify: `/Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core/halbert_core/dashboard/frontend/src/lib/api.ts` lines 94–135 (the unused `/api/conversations` wrappers)
- Modify: `/Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/documentation/API-REFERENCE.md` lines 338–376
- Test: `/Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core/tests/test_legacy_conversations_removed.py`

- [ ] **Step 1: Write the failing test**

Create `halbert_core/tests/test_legacy_conversations_removed.py`:

```python
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Plan A deletions (spec §8): the JSON conversation surfaces are gone.

The timeline (/api/agent/timeline) is the only history API; the two JSON
stores, the /api/conversations router, the /api/agent/conversations
endpoints and the dead agents/handlers package must not come back.
"""

import importlib.util

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from halbert_core.dashboard.app import create_app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    # No `with`: startup hooks (migration, background starters) must not run here.
    return TestClient(create_app())


def test_conversations_router_is_gone(client):
    assert client.get("/api/conversations").status_code == 404
    assert client.post("/api/conversations", json={"name": "x"}).status_code == 404
    assert client.get("/api/conversations/some-id").status_code == 404


def test_agent_conversations_endpoints_are_gone(client):
    assert client.get("/api/agent/conversations").status_code == 404
    assert client.get("/api/agent/conversations/some-id").status_code == 404
    assert client.delete("/api/agent/conversations/some-id").status_code == 404


def test_conversations_route_module_is_gone():
    import halbert_core.dashboard.routes  # noqa: F401  (parent package must import)
    assert importlib.util.find_spec("halbert_core.dashboard.routes.conversations") is None
```

- [ ] **Step 2: Run it and watch it fail**

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core && /Volumes/4TB-BAD/Halbert/.venv/bin/python -m pytest tests/test_legacy_conversations_removed.py -q -p no:cacheprovider
</br>
```

Expected: `test_conversations_router_is_gone` fails with `assert 200 == 404`; `test_conversations_route_module_is_gone` fails with `assert ModuleSpec(...) is None`; `test_agent_conversations_endpoints_are_gone` fails with `assert 200 == 404` unless A11 already removed the endpoints (then it passes — that is fine).

- [ ] **Step 3: Delete the router and its include**

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation && git rm -q halbert_core/halbert_core/dashboard/routes/conversations.py
```

In `halbert_core/halbert_core/dashboard/app.py` change the routes import line

```python
    from .routes import approvals, jobs, memory, settings, system, websocket, persona, discovery, terminal, alerts, rag, conversations, services, web_search, gpu, containers, development, editor, storage, downloads, agent, compression, being, modules, llm, legal, compute
```

to

```python
    from .routes import approvals, jobs, memory, settings, system, websocket, persona, discovery, terminal, alerts, rag, services, web_search, gpu, containers, development, editor, storage, downloads, agent, compression, being, modules, llm, legal, compute
```

and delete this line entirely:

```python
    app.include_router(conversations.router, prefix="/api/conversations", tags=["conversations"])  # Phase 12
```

- [ ] **Step 4: Delete the `/agent/conversations` endpoints if A11 left them**

In `halbert_core/halbert_core/dashboard/routes/agent.py`, if the block below still exists (it sits between `get_recent_sessions` and the `# Diff Apply/Reject Endpoints (Cascade-style)` banner), delete it whole — from `@router.get("/conversations")` through the `raise HTTPException(500, str(e))` of `delete_conversation`, leaving one blank line before the banner:

```python
    @router.get("/conversations")
    async def list_conversations(user_id: str = None, limit: int = 50):
        """List conversations."""
        try:
            from ...agents.conversation import get_conversation_store
            store = get_conversation_store()
            return {"conversations": store.list_conversations(user_id, limit)}
        except Exception as e:
            raise HTTPException(500, str(e))
    
    @router.get("/conversations/{conversation_id}")
    async def get_conversation(conversation_id: str):
        """Get a specific conversation."""
        try:
            from ...agents.conversation import get_conversation_store
            store = get_conversation_store()
            conv = store.get(conversation_id)
            if conv is None:
                raise HTTPException(404, "Conversation not found")
            return conv.to_dict()
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(500, str(e))
    
    @router.delete("/conversations/{conversation_id}")
    async def delete_conversation(conversation_id: str):
        """Delete a conversation."""
        try:
            from ...agents.conversation import get_conversation_store
            store = get_conversation_store()
            if store.delete(conversation_id):
                return {"deleted": True}
            raise HTTPException(404, "Conversation not found")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(500, str(e))
```

Verify nothing else in the backend references the store: `grep -rn "get_conversation_store" halbert_core/halbert_core/dashboard` must print nothing.

- [ ] **Step 5: Delete the unused frontend wrappers for `/api/conversations`**

In `halbert_core/halbert_core/dashboard/frontend/src/lib/api.ts` delete this block (it is referenced nowhere outside `api.ts`; the `/api/agent/conversations` wrappers just below the agent section are planner F's A14 and stay for now):

```ts
  // -----------------------------------------------------------------
  // Conversations
  // -----------------------------------------------------------------
  listConversations() {
    return request('/api/conversations')
  },

  createConversation(name?: string) {
    return request('/api/conversations', {
      method: 'POST',
      body: JSON.stringify({ name }),
    })
  },

  getConversation(id: string) {
    return request(`/api/conversations/${encodeURIComponent(id)}`)
  },

  renameConversation(id: string, name: string) {
    return request(`/api/conversations/${encodeURIComponent(id)}`, {
      method: 'PATCH',
      body: JSON.stringify({ name }),
    })
  },

  deleteConversation(id: string) {
    return request(`/api/conversations/${encodeURIComponent(id)}`, { method: 'DELETE' })
  },

  addMessageToConversation(
    conversationId: string,
    role: string,
    content: string,
    mentions: string[] = [],
    reasoning?: string,
  ) {
    return request(`/api/conversations/${encodeURIComponent(conversationId)}/messages`, {
      method: 'POST',
      body: JSON.stringify({ role, content, mentions, reasoning }),
    })
  },

```

so that `getBackupHistory(...)` is followed directly by the `// Agent chat (legacy /api/chat/* retired — T4b.1)` banner.

- [ ] **Step 6: Delete the doc section**

In `documentation/API-REFERENCE.md` delete from the line `## Conversations API` through the `---` that precedes `## Settings API` (the whole block below), so the `---` after the previous section is followed directly by `## Settings API`:

```markdown
## Conversations API

### List Conversations

```
GET /api/conversations
```

### Create Conversation

```
POST /api/conversations
Content-Type: application/json

{"name": "Troubleshooting disk", "persona": "guide"}
```

### Get Conversation

```
GET /api/conversations/{id}
```

### Delete Conversation

```
DELETE /api/conversations/{id}
```

### Add Message

```
POST /api/conversations/{id}/messages
Content-Type: application/json

{"role": "user", "content": "Message text", "mentions": []}
```

---
```

- [ ] **Step 7: Run the tests and the typecheck**

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core && /Volumes/4TB-BAD/Halbert/.venv/bin/python -m pytest tests/test_legacy_conversations_removed.py tests/test_dashboard_cors.py tests/test_conversation_boot_hooks.py -q -p no:cacheprovider
```

Expected: all pass (`3 passed` from the new file).

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core/halbert_core/dashboard/frontend && npx tsc --noEmit -p .
```

Expected: no output, exit 0.

- [ ] **Step 8: Commit**

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation && git add halbert_core/halbert_core/dashboard/routes/conversations.py halbert_core/halbert_core/dashboard/app.py halbert_core/halbert_core/dashboard/routes/agent.py halbert_core/halbert_core/dashboard/frontend/src/lib/api.ts documentation/API-REFERENCE.md halbert_core/tests/test_legacy_conversations_removed.py && git commit -m "refactor(dashboard): delete the JSON conversation routes" -m "The /api/conversations router, its unused frontend wrappers and doc section, and the /api/agent/conversations list/get/delete endpoints are gone. History is served by the timeline endpoint over the SQLite thread store; the migration in agents/migrations.py carried the old files across."
```

---

### Task A12d: delete the JSON `ConversationStore`/`SessionStore`, the `handlers` package, and repoint every importer

**Files:**
- Modify: `/Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core/halbert_core/agents/conversation.py` (docstring lines 3–7, imports lines 10 and 15, delete lines 203–540)
- Modify: `/Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core/halbert_core/agents/__init__.py` (lines 22–25, 30–33, 47–49, 53–55)
- Modify: `/Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core/halbert_core/agents/conversation_sqlite.py` (module docstring; the `migrate_json_conversations_to_sqlite` function at the end of the file, if still present)
- Modify: `/Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core/halbert_core/agents/session_affinity.py` (docstring lines 17–19)
- Delete: `/Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core/halbert_core/agents/handlers/` (whole package: `__init__.py`, `planning.py`, `searching.py`, `reading.py`, `executing.py`, `observing.py`, `responding.py`, plus the untracked `__pycache__`)
- Modify: `/Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core/tests/test_conversation_sqlite.py` (lines 8–11; delete `TestMigration`, lines 169–201, if still present)
- Modify: `/Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core/tests/test_session_affinity.py` (delete lines 126–140)
- Modify: `/Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core/tests/test_agent_identity.py` (delete lines 78–112)
- Test: `/Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core/tests/test_legacy_conversations_removed.py` (append)

Importers found by `grep -rn -E "ConversationStore|get_conversation_store|SessionStore|get_session_store|from \.handlers|agents\.handlers|migrate_json_conversations_to_sqlite" halbert_core tests` (worktree, before this task): `agents/__init__.py` (re-exports), `agents/conversation_sqlite.py` (docstring + the JSON migration helper), `agents/session_affinity.py` (docstring only), `tests/test_conversation_sqlite.py`, `tests/test_session_affinity.py`, `tests/test_agent_identity.py`. `routes/agent.py` was repointed in A12c. Nothing under `agents/subagents/` or `state_machine.py` imports the handlers.

- [ ] **Step 1: Write the failing test**

Append to `halbert_core/tests/test_legacy_conversations_removed.py`:

```python


def test_json_stores_are_gone_from_agents_conversation():
    import halbert_core.agents.conversation as conv

    # the records stay — the SQLite store and the history path use them
    assert hasattr(conv, "Conversation")
    assert hasattr(conv, "Message")
    for name in ("ConversationStore", "SessionStore", "Session",
                 "get_conversation_store", "get_session_store"):
        assert not hasattr(conv, name), name


def test_agents_package_no_longer_reexports_deleted_symbols():
    import halbert_core.agents as agents

    for name in ("ConversationStore", "get_conversation_store",
                 "PlanningHandler", "SearchingHandler", "ReadingHandler",
                 "ExecutingHandler", "ObservingHandler", "RespondingHandler"):
        assert name not in agents.__all__, name
        assert not hasattr(agents, name), name
    assert "Conversation" in agents.__all__
    assert "Message" in agents.__all__


def test_handlers_package_is_gone():
    import halbert_core.agents  # noqa: F401
    assert importlib.util.find_spec("halbert_core.agents.handlers") is None


def test_json_migration_helper_is_gone():
    import halbert_core.agents.conversation_sqlite as cs
    assert not hasattr(cs, "migrate_json_conversations_to_sqlite")
```

- [ ] **Step 2: Run it and watch it fail**

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core && /Volumes/4TB-BAD/Halbert/.venv/bin/python -m pytest tests/test_legacy_conversations_removed.py -q -p no:cacheprovider
```

Expected: `4 failed, 3 passed` — `AssertionError: ConversationStore`, `AssertionError: ConversationStore` (re-export), `assert ModuleSpec(name='halbert_core.agents.handlers', ...) is None`, and `assert not True` for the migration helper.

- [ ] **Step 3: Delete the handlers package**

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation && git rm -r -q halbert_core/halbert_core/agents/handlers && rm -rf halbert_core/halbert_core/agents/handlers && test ! -e halbert_core/halbert_core/agents/handlers && echo gone
```

Expected: `gone`. (The `rm -rf` matters: a leftover `__pycache__` directory would make `halbert_core.agents.handlers` importable again as an empty namespace package.)

- [ ] **Step 4: Trim `agents/__init__.py`**

Replace the `from .conversation import (...)` block, the `from .handlers import (...)` block, and the matching `__all__` entries so the file reads:

```python
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Agents module for agentic AI patterns.

Phase 21: Implements ReAct pattern for iterative reasoning.
Phase 36: Adds state machine architecture with CRAG evaluation.
"""

from .react_agent import ReActAgent, ThinkingStep, ThinkingStepType, ReActResponse
from .states import AgentState, StateContext, CRAGAction, PlanStep, ToolCall
from .events import StreamEvent
from .state_machine import AgentStateMachine
from .llm_client import (
    BaseLLMClient, OllamaClient, AnthropicClient,
    LLMResponse, get_llm_client,
)
from .metrics import (
    AgentMetricsCollector, SessionMetrics,
    get_metrics_collector, reset_metrics,
)
from .conversation import Conversation, Message
from .error_recovery import (
    ErrorRecoveryManager, ErrorType, RecoveryStrategy,
    GracefulDegradation, get_recovery_manager,
)

__all__ = [
    # Phase 21: ReAct
    'ReActAgent', 'ThinkingStep', 'ThinkingStepType', 'ReActResponse',
    # Phase 36: State Machine
    'AgentState', 'StateContext', 'CRAGAction', 'PlanStep', 'ToolCall',
    'StreamEvent', 'AgentStateMachine',
    # LLM Clients
    'BaseLLMClient', 'OllamaClient', 'AnthropicClient',
    'LLMResponse', 'get_llm_client',
    # Metrics
    'AgentMetricsCollector', 'SessionMetrics',
    'get_metrics_collector', 'reset_metrics',
    # Conversation records (the SQLite thread store is the store of record)
    'Conversation', 'Message',
    # Error Recovery
    'ErrorRecoveryManager', 'ErrorType', 'RecoveryStrategy',
    'GracefulDegradation', 'get_recovery_manager',
]
```

- [ ] **Step 5: Cut `agents/conversation.py` down to the two records**

Replace the module header (lines 1–17) with:

```python
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Conversation records

``Message`` and ``Conversation`` are the in-memory records used by the
SQLite thread store (``conversation_sqlite.py``) and by the state machine's
conversation history. The JSON-backed ``ConversationStore`` / ``SessionStore``
that used to live here were deleted in Plan A (spec §8): the SQLite store is
the store of record and ``agents/threads.py`` is the only writer.
"""

from __future__ import annotations
import logging
import time
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

logger = logging.getLogger('halbert.agents.conversation')
```

(`json` and `pathlib.Path` were only used by the deleted stores.)

Then delete everything from the line `class ConversationStore:` (line 203) to the end of the file — `ConversationStore`, `Session`, `SessionStore`, the `_session_store` / `_conversation_store` globals, `get_session_store`, `get_conversation_store`. The file now ends with `Conversation._summarize_messages`:

```python
        summary = "\n".join(summary_parts)
        
        # Truncate if too long (keep under 500 chars for summary)
        if len(summary) > 500:
            summary = summary[:500] + "..."
        
        return summary
```

Check: `grep -n "ConversationStore\|SessionStore\|get_conversation_store\|get_session_store" halbert_core/halbert_core/agents/conversation.py` prints only the docstring line.

- [ ] **Step 6: Remove the JSON migration helper from `conversation_sqlite.py`**

If the file still ends with the block below (A1 may have moved things; match by text), delete it — from the banner through the end of `migrate_json_conversations_to_sqlite`:

```python
# ---------------------------------------------------------------------------
# One-time migration: JSON -> SQLite
# ---------------------------------------------------------------------------

def migrate_json_conversations_to_sqlite(
    json_store: Any, sqlite_store: SqliteConversationStore
) -> int:
    """Migrate every ``*.json`` conversation from a JSON ``ConversationStore``
    into a ``SqliteConversationStore``. Returns the number migrated.

    Idempotent: re-saving a conversation that already exists overwrites it.
    """
    storage_path = getattr(json_store, "storage_path", None)
    if storage_path is None or not Path(storage_path).exists():
        return 0
    n = 0
    for file_path in Path(storage_path).glob("*.json"):
        try:
            with open(file_path, "r") as f:
                data = json.load(f)
            conv = Conversation.from_dict(data)
            sqlite_store.save(conv)
            n += 1
        except Exception as e:
            logger.warning(f"migration skipped {file_path}: {e}")
    logger.info(f"Migrated {n} conversations from JSON to SQLite")
    return n
```

Then fix the module docstring so it no longer names `ConversationStore` or the helper. If it is still the original one (starts `"""SQLite + FTS5 conversation store (F1).`), replace the whole docstring with:

```python
"""SQLite + FTS5 thread store (spec §8).

The store of record for the one continuous conversation: threads (the
``conversations`` table — its ``id`` is the thread id), messages with per-turn
ids and origins, ``messages_fts`` for snippets and ``receipts_fts`` for
recall. ``append_message()`` is the only message write path; ``save()`` only
upserts the thread row.

Also provides a ``session_somatic_blocks`` table linking sessions to somatic
blocks (C1), with add/list/remove helpers.

The legacy JSON stores were migrated by ``agents/migrations.py`` and deleted.
"""
```

If A1 already rewrote the docstring, only remove the sentences that mention ``ConversationStore`` / ``migrate_json_conversations_to_sqlite``. Also change the `SqliteConversationStore` class docstring's first paragraph from `Same API as ``ConversationStore``.` to `Thread-safe (single connection + write lock).` if that sentence is still there. Verify: `grep -n "ConversationStore\b\|migrate_json" halbert_core/halbert_core/agents/conversation_sqlite.py` prints only `class SqliteConversationStore` and its uses.

- [ ] **Step 7: Fix the `session_affinity.py` docstring**

Change lines 17–19 from

```python
Reuses ``intake/signals.analyze_message`` for entity/domain extraction. Works
with any store exposing ``get(id)`` and ``search(query, user_id, limit)``
(the SqliteConversationStore or the JSON ConversationStore).
```

to

```python
Reuses ``intake/signals.analyze_message`` for entity/domain extraction. Works
with any store exposing ``get(id)`` and ``search(query, user_id, limit)``
(the SqliteConversationStore).
```

- [ ] **Step 8: Update the three tests that imported deleted symbols**

`halbert_core/tests/test_conversation_sqlite.py` — replace lines 8–11

```python
from halbert_core.agents.conversation import Conversation, Message, ConversationStore
from halbert_core.agents.conversation_sqlite import (
    SqliteConversationStore, migrate_json_conversations_to_sqlite,
)
```

with

```python
from halbert_core.agents.conversation import Conversation, Message
from halbert_core.agents.conversation_sqlite import SqliteConversationStore
```

and delete the whole `TestMigration` class (and its `# Migration JSON -> SQLite` banner) if it is still present — it covered the deleted helper; the replacement coverage is `tests/test_migrations.py`:

```python
# ---------------------------------------------------------------------------
# Migration JSON -> SQLite
# ---------------------------------------------------------------------------

class TestMigration:
    def test_migrate_json_to_sqlite(self, tmp_path):
        ...
    def test_migrate_empty_dir(self, tmp_path):
        ...
```

`halbert_core/tests/test_session_affinity.py` — delete lines 126–140 (the file then ends after `test_fts_higher_than_current`):

```python
# ---------------------------------------------------------------------------
# Works with the JSON ConversationStore too (duck-typed)
# ---------------------------------------------------------------------------

def test_works_with_json_store(tmp_path):
    from halbert_core.agents.conversation import ConversationStore
    json_store = ConversationStore(storage_path=str(tmp_path))
    c = json_store.create("json-conv", "u1")
    c.add_message("user", "configure the nginx web server")
    json_store.save(c)

    router = SessionAffinityRouter(json_store)
    aff = router.route("tell me about nginx")
    assert aff.tier == "fts"
    assert aff.session_id == "json-conv"
```

`halbert_core/tests/test_agent_identity.py` — delete lines 78–112, i.e. the blank lines after `test_unknown_voice_falls_back_to_first_person` and the entire `class TestRespondingFallback:` (it tested `agents.handlers.responding.RespondingHandler._get_system_prompt`, dead code that referenced methods the state machine never had). The file then ends with:

```python
    def test_unknown_voice_falls_back_to_first_person(self):
        builder = AgentPromptBuilder()
        builder.voice = "nonsense"
        assert builder._get_identity() == AgentPromptBuilder(
            voice="first_person"
        )._get_identity()
```

`patch` stays imported (still used by `test_identity_does_not_hardcode_linux` and `test_prompt_builder_uses_platform_name`).

- [ ] **Step 9: Run the affected tests, then the whole backend suite**

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core && /Volumes/4TB-BAD/Halbert/.venv/bin/python -m pytest tests/test_legacy_conversations_removed.py tests/test_conversation_sqlite.py tests/test_session_affinity.py tests/test_agent_identity.py tests/test_migrations.py tests/test_conversation_boot_hooks.py -q -p no:cacheprovider
```

Expected: all pass (`7 passed` in `test_legacy_conversations_removed.py`).

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core && grep -rn -E "ConversationStore\b|get_conversation_store|SessionStore|get_session_store|agents\.handlers|from \.handlers|migrate_json_conversations_to_sqlite" halbert_core tests --include=*.py | grep -v "SqliteConversationStore"
```

Expected: no output.

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core && /Volumes/4TB-BAD/Halbert/.venv/bin/python -m pytest tests -q -p no:cacheprovider 2>&1 | tail -8
```

Expected: only the 4 pre-existing failures (`test_tool_calling_bridge`, `test_phase_d_integration`); every other test passes.

- [ ] **Step 10: Commit**

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation && git add halbert_core/halbert_core/agents/handlers halbert_core/halbert_core/agents/__init__.py halbert_core/halbert_core/agents/conversation.py halbert_core/halbert_core/agents/conversation_sqlite.py halbert_core/halbert_core/agents/session_affinity.py halbert_core/tests/test_conversation_sqlite.py halbert_core/tests/test_session_affinity.py halbert_core/tests/test_agent_identity.py halbert_core/tests/test_legacy_conversations_removed.py && git commit -m "refactor(agents): delete the JSON conversation stores and the dead handlers package" -m "ConversationStore, SessionStore and their singletons are gone from agents/conversation.py (Message and Conversation stay); the agents/handlers package referenced state-machine methods that never existed and had no importer besides its own re-export. The JSON->SQLite helper in conversation_sqlite.py is replaced by agents/migrations.py. Tests that exercised the deleted surfaces are removed; the removal itself is asserted in test_legacy_conversations_removed.py."
```

---

### Task A13: backend e2e — two messages, `new_thread`, grace-window close, strong recall

**Files:**
- Test: `/Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core/tests/test_thread_e2e.py`

No FastAPI TestClient fixture exists for the agent route (`test_dashboard_cors.py` builds a bare client for a settings route), so the state machine is driven directly with `thread_manager=`, exactly what `/api/agent/message` passes after A11. The fake LLM mirrors `tests/test_state_machine.py`: `chat()` returns an object with `content`, `tool_calls` (each `tool_call.function.name` / `.arguments`) and `plan`; `stream()` is an async generator. With `max_loops=2` a turn makes exactly one `chat()` call (PLANNING → SEARCHING → OBSERVING → REFLECTING → RESPONDING) plus one `stream()` call, and a meta-tool turn makes two `chat()` calls (the inline `new_thread` re-runs PLANNING once). A `ThreadManager` clock is injected so the grace window can be crossed without sleeping.

- [ ] **Step 1: Write the test**

Create `halbert_core/tests/test_thread_e2e.py`:

```python
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""End to end over the real pieces: AgentStateMachine + ThreadManager +
SqliteConversationStore on a temp database, with a scripted LLM.

Spec §13: "two /message calls, the second sees the first"; pause -> grace ->
close -> receipt indexed; strong recall injects the receipt with no model
tool call. The route is not used (no agent TestClient fixture exists); the
state machine is driven with ``thread_manager=`` exactly as the route does.
"""

from types import SimpleNamespace

import pytest

from halbert_core.agents.conversation_sqlite import SqliteConversationStore
from halbert_core.agents.state_machine import AgentStateMachine
from halbert_core.agents.thread_signals import GRACE_MINUTES
from halbert_core.agents.threads import ThreadManager
from halbert_core.prompts.agent_prompts import AgentPromptBuilder
from halbert_core.tools.executor import ToolExecutor
from halbert_core.tools.safety import ToolSafetyFramework


T0 = 1_750_000_000.0  # fixed epoch: relative dates in hints are deterministic

MSG_1 = "Set up a samba share for the family photos on the NAS"
REPLY_1 = ("I added [photos] to /etc/samba/smb.conf with path=/srv/photos and "
           "restarted smbd. Next, verify the mount from the laptop.")
MSG_2 = "Can you also make that share read-only for guests?"
REPLY_2 = "Set read only = yes under [photos] and restarted smbd."
MSG_3 = "Different topic: set up a nightly cron job that rotates the nginx logs"
REPLY_3 = "Added /etc/cron.daily/nginx-rotate calling logrotate."
MSG_4 = "Add another samba share for the scanner, same as we did for the photos one"
REPLY_4 = "Added [scanner] at /srv/scanner the same way as [photos]."

NEW_THREAD_TITLE = "Nightly nginx log rotation"


def _tool_call(name, args):
    return SimpleNamespace(function=SimpleNamespace(name=name, arguments=args))


def _plain():
    return SimpleNamespace(content="", tool_calls=None, plan=None)


class ScriptedLLM:
    """Records every prompt it is given, tagged with the current turn.

    ``script[turn]`` is a list of chat() responses handed out in order for
    that turn; when it runs dry chat() returns a plain no-tool response.
    ``replies[turn]`` is the single chunk stream() yields.
    """

    def __init__(self):
        self.turn = 0
        self.script = {}
        self.replies = {}
        self.chat_prompts = []    # (turn, prompt)
        self.stream_prompts = []  # (turn, prompt)

    async def chat(self, messages, tools=None, **kwargs):
        prompt = messages[-1]["content"]
        self.chat_prompts.append((self.turn, prompt))
        queued = self.script.get(self.turn) or []
        if queued:
            return queued.pop(0)
        return _plain()

    async def stream(self, messages, **kwargs):
        prompt = messages[-1]["content"]
        self.stream_prompts.append((self.turn, prompt))
        yield self.replies.get(self.turn, "ok")

    def planning_prompt(self, turn):
        return "\n".join(p for t, p in self.chat_prompts if t == turn)

    def responding_prompt(self, turn):
        return "\n".join(p for t, p in self.stream_prompts if t == turn)


def _tid(thread):
    return thread.get("thread_id") or thread.get("id")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def clock():
    return {"now": T0}


@pytest.fixture
def store(tmp_path):
    s = SqliteConversationStore(str(tmp_path / "threads.db"))
    yield s
    s.close()


@pytest.fixture
def tm(store, clock):
    return ThreadManager(store, now=lambda: clock["now"])


@pytest.fixture
def llm():
    return ScriptedLLM()


@pytest.fixture
def agent(llm):
    return AgentStateMachine(
        llm_client=llm,
        tool_executor=ToolExecutor(safety=ToolSafetyFramework()),
        prompt_builder=AgentPromptBuilder(),
        max_loops=2,
    )


async def _turn(agent, llm, tm, n, message, reply):
    llm.turn = n
    llm.replies[n] = reply
    events = []
    async for event in agent.process(message, session_id=f"sess-{n}", thread_manager=tm):
        events.append(event)
    types = [e.type for e in events]
    assert "session_started" in types
    assert "response_complete" in types, types
    assert "session_ended" in types
    return events


async def _three_turns(agent, llm, tm, store):
    """Two turns on the Samba subject, then a model-declared switch."""
    await _turn(agent, llm, tm, 1, MSG_1, REPLY_1)
    await _turn(agent, llm, tm, 2, MSG_2, REPLY_2)
    first_id = _tid(store.current_open_thread())
    llm.script[3] = [SimpleNamespace(
        content="",
        tool_calls=[_tool_call("new_thread", {
            "title": NEW_THREAD_TITLE, "reason": "subject changed",
        })],
        plan=None,
    )]
    ev3 = await _turn(agent, llm, tm, 3, MSG_3, REPLY_3)
    started = [e for e in ev3 if e.type == "thread_started"]
    assert len(started) == 1, [e.type for e in ev3]
    return first_id, started[0].data["thread_id"], ev3


# ---------------------------------------------------------------------------
# (1) the second message sees the first
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_second_message_sees_the_first(agent, llm, tm, store):
    ev1 = await _turn(agent, llm, tm, 1, MSG_1, REPLY_1)
    assert "turn_persisted" in [e.type for e in ev1]
    persisted = next(e for e in ev1 if e.type == "turn_persisted")
    assert persisted.data["thread_id"]
    assert persisted.data["turn_id"]

    await _turn(agent, llm, tm, 2, MSG_2, REPLY_2)

    # PLANNING on turn 2 carries the continuity hint; the thread is titled
    # from the first message, so the first exchange's text is in the prompt.
    planning_2 = llm.planning_prompt(2)
    assert "<continuity>" in planning_2, planning_2
    assert "family photos" in planning_2, planning_2
    assert planning_2.index("<continuity>") < planning_2.index("## Current Task")

    # RESPONDING on turn 2 sees the raw first exchange as history
    responding_2 = llm.responding_prompt(2)
    assert "## Earlier in this conversation" in responding_2, responding_2
    assert "/etc/samba/smb.conf" in responding_2
    assert "family photos" in responding_2

    # turn 1 did not see anything (nothing to see)
    assert "Earlier in this conversation" not in llm.responding_prompt(1)

    # storage: one open thread, four rows in order, all complete
    open_thread = store.current_open_thread()
    assert open_thread is not None and open_thread["status"] == "open"
    assert [_tid(t) for t in store.list_threads(status="open")] == [_tid(open_thread)]
    rows = store.recent_messages(_tid(open_thread), limit=12)
    assert [r["role"] for r in rows] == ["user", "assistant", "user", "assistant"]
    assert [r["content"] for r in rows] == [MSG_1, REPLY_1, MSG_2, REPLY_2]
    turns = store.list_turns(limit=10)
    assert len(turns) == 2
    assert all(t["user"]["status"] == "complete" for t in turns)
    assert all(t["assistant"]["status"] == "complete" for t in turns)
    assert turns[0]["user"]["content"] == MSG_1
    assert turns[1]["assistant"]["content"] == REPLY_2


# ---------------------------------------------------------------------------
# (2) new_thread from the model pauses the old thread and opens a new one
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_new_thread_tool_pauses_old_and_opens_new(agent, llm, tm, store):
    first_id, new_id, ev3 = await _three_turns(agent, llm, tm, store)
    types = [e.type for e in ev3]

    # handled inline: no tool card, no error, PLANNING re-ran once
    assert "tool_start" not in types
    assert "tool_complete" not in types
    assert "error" not in types
    assert len([t for t, _ in llm.chat_prompts if t == 3]) == 2

    started = next(e for e in ev3 if e.type == "thread_started")
    assert new_id != first_id
    assert started.data["title"] == NEW_THREAD_TITLE
    assert started.data["previous_thread_id"] == first_id

    old = store.get_thread(first_id)
    assert old["status"] == "paused"
    assert old["paused_at"] == T0
    new = store.get_thread(new_id)
    assert new["status"] == "open"
    assert new["title"] == NEW_THREAD_TITLE
    assert new["title_source"] == "model"
    assert [_tid(t) for t in store.list_threads(status="open")] == [new_id]

    # the switching turn belongs to the new thread; the old one keeps its four rows
    assert [r["content"] for r in store.recent_messages(new_id, limit=12)] == [MSG_3, REPLY_3]
    assert len(store.recent_messages(first_id, limit=12)) == 4


# ---------------------------------------------------------------------------
# (3) tick past the grace window closes the paused thread; recall finds it
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tick_after_grace_closes_old_thread_and_recall_finds_it(
    agent, llm, tm, store, clock
):
    first_id, new_id, _ = await _three_turns(agent, llm, tm, store)

    # inside the grace window nothing closes
    assert tm.tick() == []
    assert store.get_thread(first_id)["status"] == "paused"

    clock["now"] = T0 + GRACE_MINUTES * 60 + 60
    closed = tm.tick()
    assert closed == [first_id]

    old = store.get_thread(first_id)
    assert old["status"] == "closed"
    assert old["receipt"].startswith("Title:")
    assert "Started with:" in old["receipt"]
    assert "Open loop:" in old["receipt"]
    assert "samba" in old["receipt"].lower()
    assert old["receipt_updated_at"] is not None

    hits = store.search_receipts("samba")
    assert [h["thread_id"] for h in hits] == [first_id]
    assert hits[0]["status"] == "closed"

    recalled = tm.recall("samba")
    assert recalled, "recall('samba') found nothing"
    assert recalled[0]["thread_id"] == first_id
    assert "samba" in recalled[0]["receipt"].lower()
    assert recalled[0]["title"]
    assert recalled[0]["date"]

    # idempotent; the open thread is untouched
    assert tm.tick() == []
    assert store.get_thread(new_id)["status"] == "open"
    assert _tid(tm.current()) == new_id


# ---------------------------------------------------------------------------
# (4) a past reference pulls the closed thread in with no model tool call
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_past_reference_pulls_in_closed_thread_without_a_tool_call(
    agent, llm, tm, store, clock
):
    first_id, new_id, _ = await _three_turns(agent, llm, tm, store)
    clock["now"] = T0 + GRACE_MINUTES * 60 + 60
    assert tm.tick() == [first_id]

    ev4 = await _turn(agent, llm, tm, 4, MSG_4, REPLY_4)
    types = [e.type for e in ev4]

    # deterministic recall: no tool, no new thread, exactly one chat() call
    assert "tool_start" not in types
    assert "thread_started" not in types
    assert len([t for t, _ in llm.chat_prompts if t == 4]) == 1
    recalled = [e for e in ev4 if e.type == "thread_recalled"]
    assert len(recalled) == 1, types
    assert recalled[0].data["thread_id"] == first_id
    assert recalled[0].data["mode"] == "auto"
    assert "samba" in [t.lower() for t in recalled[0].data["match_terms"]]

    planning_4 = llm.planning_prompt(4)
    assert "<continuity>" in planning_4, planning_4
    assert "Pulled in:" in planning_4, planning_4
    assert "samba" in planning_4.lower()
    assert planning_4.index("Pulled in:") < planning_4.index("## Current Task")
    # the same block reaches RESPONDING
    assert "Pulled in:" in llm.responding_prompt(4)

    # persisted on the open thread; the closed thread stays closed (no reopen)
    open_thread = store.get_thread(new_id)
    assert open_thread["status"] == "open"
    assert [r["thread_id"] for r in open_thread["recalled_json"]] == [first_id]
    assert open_thread["recalled_json"][0]["status"] == "accepted"
    assert store.get_thread(first_id)["status"] == "closed"
    assert [r["content"] for r in store.recent_messages(new_id, limit=12)] == [
        MSG_3, REPLY_3, MSG_4, REPLY_4,
    ]

    # retracting the recall is recorded, not deleted
    assert tm.retract_recall(new_id, first_id) is True
    assert store.get_thread(new_id)["recalled_json"][0]["status"] == "retracted"
```

- [ ] **Step 2: Run it**

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core && /Volumes/4TB-BAD/Halbert/.venv/bin/python -m pytest tests/test_thread_e2e.py -q -p no:cacheprovider -x
```

Expected: `4 passed`. If a test fails, the failure names the piece that missed its contract — fix that piece (A6 for `ThreadManager`, A8 for prompt placement, A9 for `process()` wiring / inline meta-tools / `thread_recalled(mode="auto")`, A3 for `search_receipts`), not the test. Specifically:
- `"<continuity>" in planning_2` fails → A5 `build_hint` returned `""` for a thread with one completed turn, or A8 did not insert `continuity` before `## Current Task`.
- `"## Earlier in this conversation" in responding_2` fails → A8/A9 did not pass `history=ctx.conversation_history` into `build_response_prompt`.
- `thread_started` missing / `tool_start` present on turn 3 → A9 meta-tool branch is after `_already_called` or not before the tool loop.
- `paused_at == T0` fails → A6 pauses with `time.time()` instead of the injected `now`.
- `thread_recalled` missing on turn 4 → A9 does not emit `thread_recalled(mode="auto")` when `turn.recalled` is non-empty after `begin_turn`.
- `search_receipts("samba")` empty after the tick → A6 `tick()` did not `upsert_receipt`, or A3 FTS tokenisation.

Then confirm the rest of the suite is unchanged:

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core && /Volumes/4TB-BAD/Halbert/.venv/bin/python -m pytest tests -q -p no:cacheprovider 2>&1 | tail -8
```

Expected: only the 4 pre-existing failures (`test_tool_calling_bridge`, `test_phase_d_integration`).

- [ ] **Step 3: Commit**

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation && git add halbert_core/tests/test_thread_e2e.py && git commit -m "test(agents): end-to-end thread flow over the real state machine and store" -m "Two process() calls where the second sees the first (continuity in PLANNING, history in RESPONDING); a model new_thread call pauses the old thread and opens the new one with no tool card; tick() past the grace window closes the paused thread, indexes its receipt and recall finds it; a past-reference message pulls the closed thread in deterministically with no tool call and the recall is persisted and retractable."
```

---

**Contract additions (planner D):**
- `migrate_legacy_conversations(store, *, agent_dir: Path | None = None, legacy_dir: Path | None = None) -> dict` — the two keyword-only directory overrides (defaults `AGENT_JSON_DIR = ~/.halbert/conversations`, `LEGACY_JSON_DIR = ~/.config/halbert/conversations`, both module constants in `agents/migrations.py`). Creates and uses a `migrations_done (source_path TEXT PRIMARY KEY, thread_id TEXT, migrated_at REAL NOT NULL)` table through `store._conn` / `store._lock` (same package; `_lock` optional).
- `ThreadManager.store` — the public attribute holding the `SqliteConversationStore` passed to `__init__` (used by `run_conversation_boot_hooks()` in `dashboard/app.py`; planner S must assign `self.store = store`).
- `dashboard/app.py::run_conversation_boot_hooks() -> dict` — `{"agent_json", "legacy_json", "interrupted"}`, never raises; called synchronously in `startup_event` before the identity bootstrap.
- `store.update_thread(...)` must accept Python lists for `topic_domains` / `entities_json` / `recalled_json` and JSON-encode them (the migration passes lists; `get_thread` returns them decoded, per §1).
- `build_hint` renders the `Thread: "…" · n turns · …` line (non-empty hint) whenever the open thread already has ≥ 1 completed turn — "brand-new thread" in §3 means zero prior turns.
- `process()` (A9) yields `thread_recalled(..., mode="auto")` when `turn.recalled` is non-empty after `begin_turn` (spec §4.4), and `thread_started(..., previous_thread_id=<paused id>)` from the inline `new_thread` path.
- Thread dicts are read in tests through `thread.get("thread_id") or thread.get("id")`, so either key name is acceptable on `get_thread` / `list_threads` / `current_open_thread` / `ThreadManager.current()`; `search_receipts`, `recall`, `list_turns` and `recalled_json` entries use `thread_id` as specified.
- The `/api/conversations` frontend wrappers (`listConversations`, `createConversation`, `getConversation`, `renameConversation`, `deleteConversation`, `addMessageToConversation` in `src/lib/api.ts`) are deleted in A12c; the `/api/agent/conversations` wrappers remain for planner F's A14.

### Task A14: Timeline types, API wrappers, and the `useTimeline` hook

**Files:**
- Create: `halbert_core/halbert_core/dashboard/frontend/src/types/timeline.ts`
- Create: `halbert_core/halbert_core/dashboard/frontend/src/hooks/useTimeline.ts`
- Modify: `halbert_core/halbert_core/dashboard/frontend/src/lib/api.ts` (the import line; a timeline block inserted above the legacy `// Agent conversations (Phase 36 agent path)` wrappers, which stay until A18)
- Test: `halbert_core/halbert_core/dashboard/frontend/src/lib/api.timeline.test.ts`
- Test: `halbert_core/halbert_core/dashboard/frontend/src/hooks/useTimeline.test.ts`

All paths below are under the worktree `/Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core/halbert_core/dashboard/frontend`. Server timestamps are epoch **seconds** (`time.time()`); every `TimelineTurn.timestamp` on the client is epoch **milliseconds** — the mappers in `types/timeline.ts` convert once at the boundary.

- [ ] **Step 1: Write the failing API test**

`src/lib/api.timeline.test.ts`:

```ts
// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * The timeline wrappers: exact paths, exact query strings, and the
 * snake_case -> camelCase mapping the components rely on.
 */

import { describe, it, expect, afterEach, vi } from 'vitest'
import { api } from './api'

function mockFetch(body: unknown, ok = true) {
  const fetchMock = vi.fn().mockResolvedValue({
    ok,
    status: ok ? 200 : 500,
    text: async () => '',
    json: async () => body,
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

afterEach(() => vi.unstubAllGlobals())

describe('api.getTimeline', () => {
  it('hits /api/agent/timeline with only the params given', async () => {
    const fetchMock = mockFetch({ turns: [], has_more: false, current_thread: null })
    await api.getTimeline({ before: 't-1', limit: 10 })
    expect(fetchMock.mock.calls[0][0]).toBe('/api/agent/timeline?before=t-1&limit=10')

    await api.getTimeline({})
    expect(fetchMock.mock.calls[1][0]).toBe('/api/agent/timeline')
  })

  it('maps a server page onto TimelinePage with millisecond timestamps', async () => {
    mockFetch({
      has_more: true,
      current_thread: { thread_id: 'th-1', title: 'Samba share setup', status: 'open' },
      turns: [
        {
          turn_id: 't-1',
          thread_id: 'th-1',
          timestamp: 1_784_000_000,
          origin: 'human',
          user: { message_id: 7, content: 'is samba running?', timestamp: 1_784_000_000, status: 'complete' },
          assistant: { message_id: 8, content: 'Yes.', timestamp: 1_784_000_003, status: 'complete' },
          blocks: [{ tool: 'run_command', args: { command: 'systemctl status smbd' }, result: 'active', exit: 0, execution_id: 'x1' }],
          terminal_block_ids: ['term-9'],
          diff_proposals: [{ diff_id: 'd1', file_path: '/etc/samba/smb.conf', edit_blocks: [{ search: 'a', replace: 'b' }], status: 'pending' }],
        },
      ],
    })

    const page = await api.getTimeline({ limit: 50 })

    expect(page.hasMore).toBe(true)
    expect(page.currentThread).toEqual({ threadId: 'th-1', title: 'Samba share setup', status: 'open' })
    const turn = page.turns[0]
    expect(turn.turnId).toBe('t-1')
    expect(turn.timestamp).toBe(1_784_000_000_000)
    expect(turn.user).toEqual({ messageId: 7, content: 'is samba running?', timestamp: 1_784_000_000_000, status: 'complete' })
    expect(turn.assistant?.content).toBe('Yes.')
    expect(turn.blocks[0]).toEqual({ tool: 'run_command', args: { command: 'systemctl status smbd' }, result: 'active', exit: 0, executionId: 'x1' })
    expect(turn.terminalBlockIds).toEqual(['term-9'])
    expect(turn.diffProposals[0]).toMatchObject({ id: 'd1', filePath: '/etc/samba/smb.conf', newContent: 'b', oldContent: 'a', status: 'pending' })
  })

  it('degrades a malformed page to an empty one', async () => {
    mockFetch({})
    const page = await api.getTimeline({})
    expect(page).toEqual({ turns: [], hasMore: false, currentThread: null })
  })
})

describe('api.getCurrentThread', () => {
  it('accepts the physical conversation_id column as the thread id', async () => {
    const fetchMock = mockFetch({ conversation_id: 'th-2', title: 'ZFS scrub', status: 'paused' })
    const thread = await api.getCurrentThread()
    expect(fetchMock.mock.calls[0][0]).toBe('/api/agent/thread/current')
    expect(thread).toEqual({ threadId: 'th-2', title: 'ZFS scrub', status: 'paused' })
  })
})

describe('api.retractRecall', () => {
  it('DELETEs the recall row', async () => {
    const fetchMock = mockFetch({ ok: true })
    await api.retractRecall('th-1', 'th-0')
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/agent/thread/th-1/recall/th-0')
    expect(init.method).toBe('DELETE')
  })
})
```

(The legacy `listAgentConversations` / `getAgentConversation` / `deleteAgentConversation` wrappers are deleted in A18, together with the `AgentChat` code that still calls them, so that every commit typechecks; the "removed wrappers" assertion lives there.)

- [ ] **Step 2: Run it, watch it fail**

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core/halbert_core/dashboard/frontend && npx vitest run src/lib/api.timeline.test.ts
```
Expected: 5 failures — `TypeError: api.getTimeline is not a function` (three), `api.getCurrentThread is not a function`, `api.retractRecall is not a function`.

- [ ] **Step 3: Create `src/types/timeline.ts`**

```ts
// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * Timeline types (continuous conversation, Plan A).
 *
 * One conversation, stored as turns; threads are a hidden grouping the
 * server owns. The wire shape from GET /api/agent/timeline is snake_case
 * and its timestamps are epoch seconds — the mappers at the bottom are the
 * only place that shape is known. Everything client-side is camelCase and
 * milliseconds.
 */

import type { DiffProposal } from '../hooks/useAgentStream';

export interface TimelineToolBlock {
  tool: string;
  args: Record<string, unknown>;
  result?: unknown;
  exit?: number | null;
  executionId?: string;
}

export type TimelineOrigin =
  | 'human'
  | 'assistant'
  | 'terminal'
  | 'task-notification'
  | 'proactive'
  | 'system';

export type TimelineMessageStatus = 'in_progress' | 'complete' | 'interrupted' | 'cancelled';

export interface TimelineMessage {
  messageId: number;
  content: string;
  /** Epoch milliseconds. */
  timestamp: number;
  status: TimelineMessageStatus;
}

export interface TimelineTurn {
  turnId: string;
  threadId: string;
  /** Epoch milliseconds — the day divider is computed from this. */
  timestamp: number;
  origin: TimelineOrigin;
  user: TimelineMessage | null;
  assistant: { messageId: number; content: string; timestamp: number; status: string } | null;
  blocks: TimelineToolBlock[];
  terminalBlockIds: string[];
  diffProposals: DiffProposal[];
}

export interface TimelineCurrentThread {
  threadId: string;
  title: string;
  status: string;
}

export interface TimelinePage {
  turns: TimelineTurn[];
  hasMore: boolean;
  currentThread: TimelineCurrentThread | null;
}

// ---------------------------------------------------------------------------
// Wire -> client mappers
// ---------------------------------------------------------------------------

type Raw = Record<string, unknown>;

function asRecord(value: unknown): Raw | null {
  return value && typeof value === 'object' ? (value as Raw) : null;
}

/** Server seconds -> client milliseconds (already-ms values pass through). */
export function toMillis(ts: unknown): number {
  const n = typeof ts === 'number' ? ts : Number(ts ?? 0);
  if (!Number.isFinite(n) || n <= 0) return Date.now();
  return n < 1e12 ? Math.round(n * 1000) : n;
}

function messageFromServer(raw: unknown): TimelineMessage | null {
  const r = asRecord(raw);
  if (!r) return null;
  return {
    messageId: Number(r.message_id ?? r.id ?? -1),
    content: String(r.content ?? ''),
    timestamp: toMillis(r.timestamp),
    status: (r.status as TimelineMessageStatus) ?? 'complete',
  };
}

export function blockFromServer(raw: unknown): TimelineToolBlock {
  const r = asRecord(raw) ?? {};
  const exit = r.exit ?? r.exit_code;
  return {
    tool: String(r.tool ?? r.name ?? ''),
    args: asRecord(r.args) ?? {},
    result: r.result,
    exit: typeof exit === 'number' ? exit : exit == null ? null : Number(exit),
    executionId: typeof r.execution_id === 'string' ? r.execution_id
      : typeof r.executionId === 'string' ? r.executionId : undefined,
  };
}

/**
 * Stored diffs come from StateContext.pending_diffs, whose shape is
 * {file_path, edit_blocks: [{search, replace}], status}; older rows may carry
 * the diff_proposal event shape (new_content/old_content). Accept both.
 */
export function diffFromServer(raw: unknown): DiffProposal {
  const r = asRecord(raw) ?? {};
  const editBlocks = Array.isArray(r.edit_blocks)
    ? (r.edit_blocks as unknown[]).map((b) => asRecord(b) ?? {})
    : [];
  const newContent = typeof r.new_content === 'string'
    ? r.new_content
    : editBlocks.map((b) => String(b.replace ?? '')).join('\n');
  const oldContent = typeof r.old_content === 'string'
    ? r.old_content
    : editBlocks.length > 0 ? editBlocks.map((b) => String(b.search ?? '')).join('\n') : undefined;
  const status = r.status === 'applied' || r.status === 'rejected' ? r.status : 'pending';
  return {
    id: String(r.id ?? r.diff_id ?? ''),
    filePath: String(r.file_path ?? r.filePath ?? ''),
    oldContent,
    newContent,
    additions: Number(r.additions ?? 0),
    deletions: Number(r.deletions ?? 0),
    status,
  };
}

export function turnFromServer(raw: unknown): TimelineTurn {
  const r = asRecord(raw) ?? {};
  const assistant = messageFromServer(r.assistant);
  return {
    turnId: String(r.turn_id ?? r.turnId ?? ''),
    threadId: String(r.thread_id ?? r.threadId ?? ''),
    timestamp: toMillis(r.timestamp),
    origin: (r.origin as TimelineOrigin) ?? 'human',
    user: messageFromServer(r.user),
    assistant,
    blocks: Array.isArray(r.blocks) ? (r.blocks as unknown[]).map(blockFromServer) : [],
    terminalBlockIds: Array.isArray(r.terminal_block_ids)
      ? (r.terminal_block_ids as unknown[]).map(String)
      : [],
    diffProposals: Array.isArray(r.diff_proposals)
      ? (r.diff_proposals as unknown[]).map(diffFromServer)
      : [],
  };
}

/** The physical column is still `conversation_id`; accept it as the id. */
export function threadFromServer(raw: unknown): TimelineCurrentThread | null {
  const r = asRecord(raw);
  if (!r) return null;
  const threadId = r.thread_id ?? r.conversation_id ?? r.id;
  if (!threadId) return null;
  return {
    threadId: String(threadId),
    title: String(r.title ?? ''),
    status: String(r.status ?? 'open'),
  };
}

export function pageFromServer(raw: unknown): TimelinePage {
  const r = asRecord(raw) ?? {};
  return {
    turns: Array.isArray(r.turns) ? (r.turns as unknown[]).map(turnFromServer) : [],
    hasMore: !!r.has_more,
    currentThread: threadFromServer(r.current_thread),
  };
}
```

- [ ] **Step 4: Edit `src/lib/api.ts`**

Replace the import line `import { apiBase, apiUrl } from './apiBase'` (the file's only import) with:
```ts
import { apiBase, apiUrl } from './apiBase'
import {
  pageFromServer,
  threadFromServer,
  type TimelineCurrentThread,
  type TimelinePage,
} from '../types/timeline'
```

Immediately above the three-line comment block that starts with `  // -----` and reads `  // Agent conversations (Phase 36 agent path)` on its middle line, insert the block below. Leave `listAgentConversations`, `getAgentConversation` and `deleteAgentConversation` in place: `AgentChat.tsx` still calls them, and A18 deletes the callers and the wrappers in the same commit so `tsc` is green at every step.

```ts
  // -----------------------------------------------------------------------
  // Timeline (continuous conversation, Plan A): one conversation, paged.
  // -----------------------------------------------------------------------
  getTimeline(params: { before?: string; around?: string; limit?: number } = {}): Promise<TimelinePage> {
    const qs = new URLSearchParams()
    if (params.before) qs.set('before', params.before)
    if (params.around) qs.set('around', params.around)
    if (params.limit) qs.set('limit', String(params.limit))
    const suffix = qs.toString() ? `?${qs.toString()}` : ''
    return request(`/api/agent/timeline${suffix}`).then(pageFromServer)
  },

  getCurrentThread(): Promise<TimelineCurrentThread | null> {
    return request('/api/agent/thread/current').then(threadFromServer)
  },

  retractRecall(threadId: string, recalledThreadId: string): Promise<{ ok: boolean }> {
    return request(
      `/api/agent/thread/${encodeURIComponent(threadId)}/recall/${encodeURIComponent(recalledThreadId)}`,
      { method: 'DELETE' },
    )
  },
```

- [ ] **Step 5: Run the API test**

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core/halbert_core/dashboard/frontend && npx vitest run src/lib/api.timeline.test.ts
```
Expected: `Tests  5 passed (5)`.

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core/halbert_core/dashboard/frontend && npx tsc --noEmit -p .
```
Expected: no output, exit 0 (everything in this task is additive).

- [ ] **Step 6: Write the failing hook test**

`src/hooks/useTimeline.test.ts`:

```ts
// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * The stored conversation: first page on mount, older pages on demand, the
 * finished live turn appended, a jump to the window around one turn (the
 * thread chip) and back to the newest page, and everything grouped by
 * local day.
 */

import { describe, it, expect, afterEach, vi } from 'vitest'
import { renderHook, waitFor, act } from '@testing-library/react'
import { useTimeline, dayKeyOf, dayLabel, groupByDay } from './useTimeline'
import type { TimelineTurn } from '@/types/timeline'

// Thu 16 Jul 2026, local noon. Dates are built with the local constructor so
// the day keys do not depend on the machine's zone.
const NOW = new Date(2026, 6, 16, 12, 0, 0)

function localMs(y: number, m: number, d: number, h = 9): number {
  return new Date(y, m - 1, d, h).getTime()
}

function turn(id: string, timestamp: number, text: string): TimelineTurn {
  return {
    turnId: id,
    threadId: 'th-1',
    timestamp,
    origin: 'human',
    user: { messageId: 1, content: text, timestamp, status: 'complete' },
    assistant: { messageId: 2, content: `re: ${text}`, timestamp: timestamp + 2000, status: 'complete' },
    blocks: [],
    terminalBlockIds: [],
    diffProposals: [],
  }
}

function rawTurn(id: string, seconds: number, text: string) {
  return {
    turn_id: id,
    thread_id: 'th-1',
    timestamp: seconds,
    origin: 'human',
    user: { message_id: 1, content: text, timestamp: seconds, status: 'complete' },
    assistant: { message_id: 2, content: `re: ${text}`, timestamp: seconds + 2, status: 'complete' },
    blocks: [],
    terminal_block_ids: [],
    diff_proposals: [],
  }
}

function page(turns: unknown[], hasMore = false) {
  return {
    turns,
    has_more: hasMore,
    current_thread: { thread_id: 'th-1', title: 'Samba share setup', status: 'open' },
  }
}

function fetchPages(...bodies: unknown[]) {
  const fetchMock = vi.fn()
  for (const body of bodies) {
    fetchMock.mockResolvedValueOnce({ ok: true, status: 200, text: async () => '', json: async () => body })
  }
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

afterEach(() => vi.unstubAllGlobals())

describe('day grouping', () => {
  it('keys a timestamp by its local calendar day', () => {
    expect(dayKeyOf(localMs(2026, 7, 14, 23))).toBe('2026-07-14')
    expect(dayKeyOf(localMs(2026, 1, 3, 0))).toBe('2026-01-03')
  })

  it('labels today, yesterday, then absolute dates', () => {
    expect(dayLabel('2026-07-16', NOW)).toBe('Today')
    expect(dayLabel('2026-07-15', NOW)).toBe('Yesterday')
    expect(dayLabel('2026-07-14', NOW)).toBe('Tue, Jul 14')
    expect(dayLabel('2025-07-14', NOW)).toBe('Mon, Jul 14, 2025')
  })

  it('groups consecutive turns by day, oldest first', () => {
    const groups = groupByDay(
      [
        turn('a', localMs(2026, 7, 14, 9), 'one'),
        turn('b', localMs(2026, 7, 14, 17), 'two'),
        turn('c', localMs(2026, 7, 16, 8), 'three'),
      ],
      NOW,
    )
    expect(groups.map((g) => [g.dayKey, g.label, g.turns.length])).toEqual([
      ['2026-07-14', 'Tue, Jul 14', 2],
      ['2026-07-16', 'Today', 1],
    ])
  })
})

describe('useTimeline', () => {
  it('loads the first page on mount and exposes the current thread', async () => {
    const fetchMock = fetchPages(page([rawTurn('t-1', 1_784_000_000, 'one'), rawTurn('t-2', 1_784_000_100, 'two')]))

    const { result } = renderHook(() => useTimeline())

    await waitFor(() => expect(result.current.turns).toHaveLength(2))
    expect(fetchMock.mock.calls[0][0]).toBe('/api/agent/timeline?limit=50')
    expect(result.current.turns.map((t) => t.turnId)).toEqual(['t-1', 't-2'])
    expect(result.current.hasMore).toBe(false)
    expect(result.current.loading).toBe(false)
    expect(result.current.currentThread?.title).toBe('Samba share setup')
    expect(result.current.byDay).toHaveLength(1)
  })

  it('loadOlder pages backwards from the oldest turn and prepends', async () => {
    const fetchMock = fetchPages(
      page([rawTurn('t-2', 1_784_000_100, 'two'), rawTurn('t-3', 1_784_000_200, 'three')], true),
      page([rawTurn('t-1', 1_784_000_000, 'one'), rawTurn('t-2', 1_784_000_100, 'two')], false),
    )

    const { result } = renderHook(() => useTimeline())
    await waitFor(() => expect(result.current.turns).toHaveLength(2))
    expect(result.current.hasMore).toBe(true)

    await act(async () => {
      await result.current.loadOlder()
    })

    expect(fetchMock.mock.calls[1][0]).toBe('/api/agent/timeline?before=t-2&limit=50')
    expect(result.current.turns.map((t) => t.turnId)).toEqual(['t-1', 't-2', 't-3'])
    expect(result.current.hasMore).toBe(false)
  })

  it('loadOlder is a no-op when there is nothing older', async () => {
    const fetchMock = fetchPages(page([rawTurn('t-1', 1_784_000_000, 'one')], false))
    const { result } = renderHook(() => useTimeline())
    await waitFor(() => expect(result.current.turns).toHaveLength(1))

    await act(async () => {
      await result.current.loadOlder()
    })

    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('appendLive appends a new turn and replaces one with the same id', async () => {
    fetchPages(page([rawTurn('t-1', 1_784_000_000, 'one')]))
    const { result } = renderHook(() => useTimeline())
    await waitFor(() => expect(result.current.turns).toHaveLength(1))

    act(() => {
      result.current.appendLive(turn('live-1', Date.now(), 'draft'))
    })
    expect(result.current.turns.map((t) => t.turnId)).toEqual(['t-1', 'live-1'])

    act(() => {
      result.current.appendLive(turn('live-1', Date.now(), 'final'))
    })
    expect(result.current.turns).toHaveLength(2)
    expect(result.current.turns[1].user?.content).toBe('final')
    expect(result.current.byDay[result.current.byDay.length - 1].label).toBe('Today')
  })

  it('survives a failed load with an empty timeline', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('backend restarting')))
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})

    const { result } = renderHook(() => useTimeline())

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.turns).toEqual([])
    expect(warn).toHaveBeenCalled()
  })

  it('loadAround replaces the page with the window around a turn and scrolls to it', async () => {
    const fetchMock = fetchPages(
      page([rawTurn('t-9', 1_784_000_900, 'nine')], true),
      page(
        [rawTurn('t-1', 1_784_000_000, 'one'), rawTurn('t-2', 1_784_000_100, 'two'), rawTurn('t-3', 1_784_000_200, 'three')],
        true,
      ),
    )
    // jsdom has no layout: record which element was asked to scroll.
    const scrolled: Element[] = []
    Element.prototype.scrollIntoView = function (this: Element) {
      scrolled.push(this)
    }
    const article = document.createElement('article')
    article.setAttribute('data-turn-id', 't-2')
    document.body.appendChild(article)

    const { result } = renderHook(() => useTimeline())
    await waitFor(() => expect(result.current.turns).toHaveLength(1))
    expect(result.current.anchored).toBe(false)

    await act(async () => {
      await result.current.loadAround('t-2')
    })

    expect(fetchMock.mock.calls[1][0]).toBe('/api/agent/timeline?around=t-2&limit=50')
    expect(result.current.turns.map((t) => t.turnId)).toEqual(['t-1', 't-2', 't-3'])
    expect(result.current.hasMore).toBe(true)
    expect(result.current.anchored).toBe(true)
    expect(scrolled).toEqual([article])
    article.remove()
  })

  it('loadLatest returns to the newest page and clears the anchor', async () => {
    const fetchMock = fetchPages(
      page([rawTurn('t-9', 1_784_000_900, 'nine')], true),
      page([rawTurn('t-2', 1_784_000_100, 'two')], true),
      page([rawTurn('t-9', 1_784_000_900, 'nine')], true),
    )
    const { result } = renderHook(() => useTimeline())
    await waitFor(() => expect(result.current.turns).toHaveLength(1))

    await act(async () => {
      await result.current.loadAround('t-2')
    })
    expect(result.current.anchored).toBe(true)

    await act(async () => {
      await result.current.loadLatest()
    })

    expect(fetchMock.mock.calls[2][0]).toBe('/api/agent/timeline?limit=50')
    expect(result.current.turns.map((t) => t.turnId)).toEqual(['t-9'])
    expect(result.current.anchored).toBe(false)
  })
})
```

- [ ] **Step 7: Run it, watch it fail**

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core/halbert_core/dashboard/frontend && npx vitest run src/hooks/useTimeline.test.ts
```
Expected: `Error: Failed to resolve import "./useTimeline"`.

- [ ] **Step 8: Create `src/hooks/useTimeline.ts`**

```ts
// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * useTimeline — the stored conversation, paged.
 *
 * One conversation. The first page (newest 50 turns) loads on mount; older
 * pages are fetched with `before=<oldest turn id>` and prepended; the turn
 * that just finished streaming is appended locally so the page does not have
 * to refetch to show what it just watched happen. A thread chip click loads
 * the window `around=<turn id>` instead (replacing the page and scrolling to
 * that turn); `loadLatest` returns to the newest page. Turns are grouped by
 * local calendar day for the dividers.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { Dispatch, SetStateAction } from 'react';
import { api } from '@/lib/api';
import type { TimelineCurrentThread, TimelineTurn } from '@/types/timeline';

export interface TimelineDay {
  /** Local calendar day, YYYY-MM-DD. */
  dayKey: string;
  /** 'Today' | 'Yesterday' | 'Thu, Jul 14' (+ ', 2025' when not this year). */
  label: string;
  turns: TimelineTurn[];
}

export interface UseTimelineReturn {
  turns: TimelineTurn[];
  hasMore: boolean;
  /** True during the first load and while any page is in flight. */
  loading: boolean;
  loadOlder: () => Promise<void>;
  /**
   * Replace the page with the window around `turnId` (a thread chip click)
   * and scroll to that turn once it is rendered. Sets `anchored`.
   */
  loadAround: (turnId: string) => Promise<void>;
  /** Back to the newest page after a `loadAround`. Clears `anchored`. */
  loadLatest: () => Promise<void>;
  /** True while the page is a window around an earlier turn, not the newest page. */
  anchored: boolean;
  appendLive: (turn: TimelineTurn) => void;
  currentThread: TimelineCurrentThread | null;
  setCurrentThread: Dispatch<SetStateAction<TimelineCurrentThread | null>>;
  byDay: TimelineDay[];
}

const pad = (n: number) => String(n).padStart(2, '0');

/** Local calendar day of an epoch-ms timestamp, as YYYY-MM-DD. */
export function dayKeyOf(timestampMs: number): string {
  const d = new Date(timestampMs);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** 'Today' | 'Yesterday' | 'Thu, Jul 14' — with the year when it is not this year. */
export function dayLabel(dayKey: string, now: Date = new Date()): string {
  if (dayKey === dayKeyOf(now.getTime())) return 'Today';
  const yesterday = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1);
  if (dayKey === dayKeyOf(yesterday.getTime())) return 'Yesterday';
  const [y, m, d] = dayKey.split('-').map(Number);
  const date = new Date(y, m - 1, d);
  const options: Intl.DateTimeFormatOptions = { weekday: 'short', month: 'short', day: 'numeric' };
  if (y !== now.getFullYear()) options.year = 'numeric';
  return date.toLocaleDateString('en-US', options);
}

/** Group turns (already oldest-first) into consecutive local days. */
export function groupByDay(turns: TimelineTurn[], now: Date = new Date()): TimelineDay[] {
  const days: TimelineDay[] = [];
  for (const turn of turns) {
    const dayKey = dayKeyOf(turn.timestamp);
    const last = days[days.length - 1];
    if (last && last.dayKey === dayKey) {
      last.turns.push(turn);
    } else {
      days.push({ dayKey, label: dayLabel(dayKey, now), turns: [turn] });
    }
  }
  return days;
}

/** Older page in front of what is loaded, without duplicating overlaps. */
function mergeOlder(older: TimelineTurn[], current: TimelineTurn[]): TimelineTurn[] {
  const seen = new Set(current.map((t) => t.turnId));
  return [...older.filter((t) => !seen.has(t.turnId)), ...current];
}

/** Attribute selector for a turn article; ids are uuids but quote anyway. */
function turnSelector(turnId: string): string {
  return `[data-turn-id="${turnId.replace(/"/g, '\\"')}"]`;
}

export function useTimeline(pageSize = 50): UseTimelineReturn {
  const [turns, setTurns] = useState<TimelineTurn[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [anchored, setAnchored] = useState(false);
  const [currentThread, setCurrentThread] = useState<TimelineCurrentThread | null>(null);
  const inFlight = useRef(false);
  // Turn to scroll to once the page that contains it has rendered.
  const scrollTarget = useRef<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    inFlight.current = true;
    api
      .getTimeline({ limit: pageSize })
      .then((page) => {
        if (cancelled) return;
        setTurns(page.turns);
        setHasMore(page.hasMore);
        setCurrentThread(page.currentThread);
      })
      .catch((err) => {
        // The endpoint degrades to empty, never 500; a network failure is
        // the same story on this side: an empty timeline, not a broken page.
        console.warn('[TIMELINE] initial load failed:', err);
      })
      .finally(() => {
        inFlight.current = false;
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [pageSize]);

  // After a loadAround the target article exists only once React has
  // committed the new page, so the scroll waits for that commit.
  useEffect(() => {
    const target = scrollTarget.current;
    if (!target) return;
    const el = document.querySelector(turnSelector(target));
    if (!el) return;
    scrollTarget.current = null;
    el.scrollIntoView({ block: 'center' });
  }, [turns]);

  const loadOlder = useCallback(async () => {
    if (inFlight.current || !hasMore || turns.length === 0) return;
    inFlight.current = true;
    setLoading(true);
    try {
      const page = await api.getTimeline({ before: turns[0].turnId, limit: pageSize });
      setTurns((prev) => mergeOlder(page.turns, prev));
      setHasMore(page.hasMore);
    } catch (err) {
      console.warn('[TIMELINE] older page failed:', err);
    } finally {
      inFlight.current = false;
      setLoading(false);
    }
  }, [hasMore, turns, pageSize]);

  const loadAround = useCallback(async (turnId: string) => {
    if (inFlight.current || !turnId) return;
    inFlight.current = true;
    setLoading(true);
    try {
      const page = await api.getTimeline({ around: turnId, limit: pageSize });
      if (page.turns.length === 0) return; // unknown id: keep what is on screen
      scrollTarget.current = turnId;
      setTurns(page.turns);
      setHasMore(page.hasMore);
      setAnchored(true);
    } catch (err) {
      console.warn('[TIMELINE] around page failed:', err);
    } finally {
      inFlight.current = false;
      setLoading(false);
    }
  }, [pageSize]);

  const loadLatest = useCallback(async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    setLoading(true);
    try {
      const page = await api.getTimeline({ limit: pageSize });
      setTurns(page.turns);
      setHasMore(page.hasMore);
      setCurrentThread(page.currentThread);
      setAnchored(false);
    } catch (err) {
      console.warn('[TIMELINE] latest page failed:', err);
    } finally {
      inFlight.current = false;
      setLoading(false);
    }
  }, [pageSize]);

  const appendLive = useCallback((turn: TimelineTurn) => {
    setTurns((prev) => {
      const idx = prev.findIndex((t) => t.turnId === turn.turnId);
      if (idx === -1) return [...prev, turn];
      const next = prev.slice();
      next[idx] = turn;
      return next;
    });
  }, []);

  const byDay = useMemo(() => groupByDay(turns), [turns]);

  return {
    turns,
    hasMore,
    loading,
    loadOlder,
    loadAround,
    loadLatest,
    anchored,
    appendLive,
    currentThread,
    setCurrentThread,
    byDay,
  };
}

export default useTimeline;
```

- [ ] **Step 9: Run both tests**

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core/halbert_core/dashboard/frontend && npx vitest run src/hooks/useTimeline.test.ts src/lib/api.timeline.test.ts
```
Expected: `Test Files  2 passed (2)`, `Tests  15 passed (15)`.

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core/halbert_core/dashboard/frontend && npx tsc --noEmit -p .
```
Expected: no output, exit 0.

- [ ] **Step 10: Commit**

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation && git add halbert_core/halbert_core/dashboard/frontend/src/types/timeline.ts halbert_core/halbert_core/dashboard/frontend/src/hooks/useTimeline.ts halbert_core/halbert_core/dashboard/frontend/src/hooks/useTimeline.test.ts halbert_core/halbert_core/dashboard/frontend/src/lib/api.ts halbert_core/halbert_core/dashboard/frontend/src/lib/api.timeline.test.ts && git commit -m "feat(dashboard): timeline types, api wrappers and useTimeline

One conversation, paged: GET /api/agent/timeline (before= for older
pages, around= for the window a thread chip jumps to, loadLatest to come
back). The legacy per-conversation wrappers stay until AgentChat stops
calling them. Wire timestamps are seconds; the client is milliseconds
from the mapper outward. Day grouping is local calendar days: Today,
Yesterday, then absolute."
```

### Task A15: `useAgentStream` thread events (chip with `lastTurnId`, expiry on a new subject), `dismissContextItem`, and a `reset()` that keeps terminals

**Files:**
- Modify: `halbert_core/halbert_core/dashboard/frontend/src/hooks/useAgentStream.ts` (lines 98-118 interface; 140-153 return type; 236-254 initSession; 505-509 switch tail; 718-732 reset; 766-779 return)
- Modify: `halbert_core/halbert_core/dashboard/frontend/src/hooks/index.ts` (line 12-27 export list)
- Test: `halbert_core/halbert_core/dashboard/frontend/src/hooks/useAgentStream.thread.test.ts`

- [ ] **Step 1: Write the failing test**

`src/hooks/useAgentStream.thread.test.ts`:

```ts
// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * Thread events on the agent stream (Plan A).
 *
 * The server owns thread identity; the hook only mirrors what it is told:
 * which subject the turn landed in, what earlier subject was pulled in (one
 * chip, never two, carrying the recalled thread's last turn id so the chip
 * can jump there; it expires when a new subject starts), and the persisted
 * turn id. A store failure is a warning, not an error state — the turn
 * still answers.
 */

import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest'
import { renderHook, waitFor, act } from '@testing-library/react'
import { useAgentStream } from './useAgentStream'
import { terminalSessionStore as store } from './useTerminalSessions'

function sseBody(events: Array<Record<string, unknown>>) {
  const text = events.map((e) => `data: ${JSON.stringify(e)}\n`).join('')
  const chunks = [new TextEncoder().encode(text)]
  return {
    getReader: () => ({
      read: async () => {
        const value = chunks.shift()
        return value ? { done: false, value } : { done: true, value: undefined }
      },
    }),
  }
}

/** fetch that streams `events` for /api/agent/message and 200s anything else. */
function streamFetch(events: Array<Record<string, unknown>>) {
  const fetchMock = vi.fn().mockImplementation((url: string) => {
    if (String(url).includes('/api/agent/message')) {
      return Promise.resolve({ ok: true, status: 200, statusText: 'OK', body: sseBody(events) })
    }
    return Promise.resolve({ ok: true, status: 200, statusText: 'OK', json: async () => ({}) })
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

const ev = (type: string, extra: Record<string, unknown> = {}) => ({
  type,
  session_id: 'turn-1',
  timestamp: 0,
  ...extra,
})

describe('useAgentStream — thread events', () => {
  beforeEach(() => {
    store.closeAll()
    vi.spyOn(console, 'log').mockImplementation(() => {})
  })

  afterEach(() => {
    store.closeAll()
    vi.unstubAllGlobals()
  })

  it('records the subject the server started and the persisted turn id', async () => {
    streamFetch([
      ev('turn_persisted', { thread_id: 'th-1', turn_id: 't-42' }),
      ev('thread_started', { thread_id: 'th-1', title: 'Samba share setup', reason: '' }),
      ev('response_chunk', { content: 'Hello' }),
      ev('response_complete', { content: 'Hello' }),
    ])

    const { result } = renderHook(() => useAgentStream())
    act(() => {
      result.current.sendMessage('set up a samba share', 'turn-1')
    })

    await waitFor(() => expect(result.current.isStreaming).toBe(false))
    expect(result.current.session?.turnId).toBe('t-42')
    expect(result.current.session?.thread).toEqual({ threadId: 'th-1', title: 'Samba share setup' })
    expect(result.current.response).toBe('Hello')
  })

  it('keeps exactly one thread chip across repeated recalls', async () => {
    streamFetch([
      ev('thread_recalled', { thread_id: 'th-0', title: 'ZFS scrub', date: '2026-07-14', match_terms: ['zfs'], mode: 'auto', last_turn_id: 't-3' }),
      ev('context_loaded', { source: 'file', label: '/etc/fstab', count: 1 }),
      ev('thread_recalled', { thread_id: 'th-9', title: 'WireGuard tunnel', date: '2026-07-02', match_terms: ['wg'], mode: 'tool', last_turn_id: 't-7' }),
      ev('response_complete', { content: 'done' }),
    ])

    const { result } = renderHook(() => useAgentStream())
    act(() => {
      result.current.sendMessage('did that work?', 'turn-1')
    })

    await waitFor(() => expect(result.current.isStreaming).toBe(false))
    const items = result.current.session!.contextItems
    const threadChips = items.filter((i) => i.source === 'thread')
    expect(threadChips).toHaveLength(1)
    expect(threadChips[0]).toMatchObject({
      id: 'thread:th-9',
      source: 'thread',
      label: 'pulled in: WireGuard tunnel · 2026-07-02',
      count: 1,
    })
    expect(items.some((i) => i.source === 'file')).toBe(true)
    expect(result.current.session?.recalled).toEqual({
      threadId: 'th-9',
      title: 'WireGuard tunnel',
      date: '2026-07-02',
      matchTerms: ['wg'],
      lastTurnId: 't-7',
    })
  })

  it('stores the recalled thread\'s last turn id, null when the server has none', async () => {
    streamFetch([
      ev('thread_recalled', { thread_id: 'th-0', title: 'ZFS scrub', date: '2026-07-14', match_terms: ['zfs'], mode: 'auto' }),
      ev('response_complete', { content: 'done' }),
    ])

    const { result } = renderHook(() => useAgentStream())
    act(() => {
      result.current.sendMessage('hi', 'turn-1')
    })

    await waitFor(() => expect(result.current.isStreaming).toBe(false))
    expect(result.current.session?.recalled?.lastTurnId).toBeNull()
  })

  it('clears the chip when a new subject starts (the pulled-in thread expires with the paused one)', async () => {
    streamFetch([
      ev('thread_recalled', { thread_id: 'th-0', title: 'ZFS scrub', date: '2026-07-14', match_terms: ['zfs'], mode: 'auto', last_turn_id: 't-3' }),
      ev('context_loaded', { source: 'file', label: '/etc/fstab', count: 1 }),
      ev('thread_started', { thread_id: 'th-2', title: 'Scanner share', reason: 'new subject' }),
      ev('response_complete', { content: 'done' }),
    ])

    const { result } = renderHook(() => useAgentStream())
    act(() => {
      result.current.sendMessage('now something else', 'turn-1')
    })

    await waitFor(() => expect(result.current.isStreaming).toBe(false))
    expect(result.current.session?.thread).toEqual({ threadId: 'th-2', title: 'Scanner share' })
    expect(result.current.session?.recalled).toBeNull()
    expect(result.current.session?.contextItems.map((i) => i.source)).toEqual(['file'])
  })

  it('dismissContextItem drops the chip and clears the recall', async () => {
    streamFetch([
      ev('thread_recalled', { thread_id: 'th-0', title: 'ZFS scrub', date: '2026-07-14', match_terms: [], mode: 'auto' }),
      ev('response_complete', { content: 'done' }),
    ])

    const { result } = renderHook(() => useAgentStream())
    act(() => {
      result.current.sendMessage('hi', 'turn-1')
    })
    await waitFor(() => expect(result.current.session?.recalled).not.toBeNull())

    act(() => {
      result.current.dismissContextItem('thread:th-0')
    })

    expect(result.current.session?.contextItems).toEqual([])
    expect(result.current.session?.recalled).toBeNull()
  })

  it('warns once on thread_store_error and leaves the session error untouched', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    streamFetch([
      ev('thread_store_error', { message: 'database is locked' }),
      ev('thread_store_error', { message: 'database is locked' }),
      ev('response_complete', { content: 'still answered' }),
    ])

    const { result } = renderHook(() => useAgentStream())
    act(() => {
      result.current.sendMessage('hi', 'turn-1')
    })

    await waitFor(() => expect(result.current.isStreaming).toBe(false))
    expect(warn).toHaveBeenCalledTimes(1)
    expect(result.current.session?.error).toBeNull()
    expect(result.current.session?.state).not.toBe('error')
  })

  it('reset() clears local state but never forgets the terminals a turn opened', async () => {
    streamFetch([
      ev('terminal_spawn', { terminal_session_id: 'term-1', command: 'journalctl -f', pid: 12 }),
      ev('terminal_output', { terminal_session_id: 'term-1', data: 'tick' }),
      ev('response_complete', { content: 'watching' }),
    ])

    const { result } = renderHook(() => useAgentStream())
    act(() => {
      result.current.sendMessage('tail the journal', 'turn-1')
    })
    await waitFor(() => expect(result.current.isStreaming).toBe(false))
    expect(store.get('term-1')).toBeDefined()

    act(() => {
      result.current.reset()
    })

    expect(result.current.session).toBeNull()
    expect(result.current.response).toBe('')
    // One conversation: the tile from turn 1 outlives the hook's local state.
    expect(store.get('term-1')?.output).toBe('tick')
  })
})
```

- [ ] **Step 2: Run it, watch it fail**

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core/halbert_core/dashboard/frontend && npx vitest run src/hooks/useAgentStream.thread.test.ts
```
Expected: 7 failures — `expected undefined to be 't-42'`, `expected [] to have a length of 1`, `expected undefined to be null` (lastTurnId), `expected undefined to deeply equal { threadId: 'th-2', … }`, `TypeError: result.current.dismissContextItem is not a function`, `expected "warn" to be called 1 times, but got 0 times`, `expected undefined to be 'tick'`.

- [ ] **Step 3: Edit `useAgentStream.ts`**

(a) In `interface AgentSession` (lines 98-118), after `terminalSessions?: string[];` add:

```ts
  /** Subject the server put this turn in (thread_started). */
  thread?: { threadId: string; title: string } | null;
  /**
   * Earlier subject pulled into this turn (thread_recalled), one at most.
   * `lastTurnId` is that thread's most recent turn — where the chip jumps.
   */
  recalled?: {
    threadId: string;
    title: string;
    date: string;
    matchTerms: string[];
    lastTurnId: string | null;
  } | null;
  /** Server turn id once the user row is stored (turn_persisted). */
  turnId?: string | null;
```

(b) In `interface UseAgentStreamReturn` (lines 140-153), after `reset: () => void;` add:

```ts
  /** Drop a context chip locally (the server is told separately, if at all). */
  dismissContextItem: (id: string) => void;
```

(c) Immediately above `export function applyTerminalEvent` (line 177) add:

```ts
// A store failure is logged once per page load; the turn still answers and
// the timeline just will not show it after a reload (spec §12).
let storeErrorWarned = false;
```

(d) In `initSession` (lines 236-254), after `terminalSessions: [],` add:

```ts
      thread: null,
      recalled: null,
      turnId: null,
```

(e) In the `switch (event.type)` inside `handleEvent`, immediately before `default:` (line 507), add:

```ts
        // Plan A continuity: the server owns thread identity. The hook only
        // mirrors what it was told so the label and the chip can follow.
        case 'thread_started': {
          // A new subject pauses the previous one, and whatever was pulled
          // into the previous one expires with it (spec §6): no thread chip
          // survives a thread_started.
          return {
            ...prev,
            thread: {
              threadId: event.thread_id as string,
              title: (event.title as string) ?? '',
            },
            recalled: null,
            contextItems: prev.contextItems.filter((item) => item.source !== 'thread'),
          };
        }

        case 'thread_recalled': {
          const threadId = event.thread_id as string;
          const title = (event.title as string) ?? '';
          const date = (event.date as string) ?? '';
          const matchTerms = Array.isArray(event.match_terms) ? (event.match_terms as string[]) : [];
          const lastTurnId =
            typeof event.last_turn_id === 'string' && event.last_turn_id ? event.last_turn_id : null;
          // Max one thread chip: a second recall replaces the first.
          const others = prev.contextItems.filter((item) => item.source !== 'thread');
          return {
            ...prev,
            recalled: { threadId, title, date, matchTerms, lastTurnId },
            contextItems: [
              ...others,
              { id: `thread:${threadId}`, source: 'thread', label: `pulled in: ${title} · ${date}`, count: 1 },
            ],
          };
        }

        case 'turn_persisted': {
          return { ...prev, turnId: (event.turn_id as string) ?? null };
        }

        case 'thread_store_error': {
          if (!storeErrorWarned) {
            storeErrorWarned = true;
            console.warn('[AGENT] thread store error (turn still answered):', event.message);
          }
          return prev;
        }
```

(f) Replace `reset` (lines 718-732) with:

```ts
  const reset = useCallback(() => {
    cancel();
    // One conversation: terminals belong to the timeline, not to this hook's
    // local state, so a reset never clears the store (there is no "New
    // Conversation" any more — see hooks/useTerminalSessions clearOrigin,
    // which stays for the dock's own use).
    setSession(null);
    setResponse('');
    setThinking('');
    setProvenance([]);
    setModuleInvocations([]);
    sessionIdRef.current = null;
  }, [cancel]);

  const dismissContextItem = useCallback((id: string) => {
    setSession(prev => prev ? {
      ...prev,
      contextItems: prev.contextItems.filter(item => item.id !== id),
      recalled: prev.recalled && `thread:${prev.recalled.threadId}` === id ? null : prev.recalled,
    } : null);
  }, []);
```

(g) In the return object (lines 766-779) add `dismissContextItem` after `reset`:

```ts
    cancel,
    reset,
    dismissContextItem,
  };
```

- [ ] **Step 4: Run the new test plus the existing terminal test, then typecheck**

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core/halbert_core/dashboard/frontend && npx vitest run src/hooks/useAgentStream.thread.test.ts src/hooks/useAgentStream.terminal.test.ts
```
Expected: `Tests  14 passed (14)` (7 new + 7 existing).

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core/halbert_core/dashboard/frontend && npx tsc --noEmit -p .
```
Expected: no output, exit 0.

- [ ] **Step 5: Commit**

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation && git add halbert_core/halbert_core/dashboard/frontend/src/hooks/useAgentStream.ts halbert_core/halbert_core/dashboard/frontend/src/hooks/useAgentStream.thread.test.ts && git commit -m "feat(dashboard): mirror thread events on the agent stream

thread_started (which also expires any pulled-in chip: the previous
subject paused), thread_recalled (one chip, ever, carrying the recalled
thread's last turn id), turn_persisted and thread_store_error (warn
once, never an error state). reset() no longer clears the terminal
store: there is one conversation and the tiles belong to it, not to a
session."
```

### Task A16: ContextBar `thread` chip on telemetry tokens; ContextPill as a button with a "why now" title; `status.*-line` aliases

**Files:**
- Modify: `halbert_core/halbert_core/dashboard/frontend/tailwind.config.js` (lines 75-84)
- Modify: `halbert_core/halbert_core/dashboard/frontend/src/components/agent/ContextBar.tsx` (lines 10-117)
- Test: `halbert_core/halbert_core/dashboard/frontend/src/components/agent/ContextBar.test.tsx`

Token names used (from `/shared-tokens/tokens.css` lines 184-195, aliased in tailwind `colors.status`): `--color-status-telemetry` → `text-status-telemetry`, `--color-status-telemetry-bg` → `bg-status-telemetry-bg`, `--color-status-telemetry-line` → `border-status-telemetry-line` (new alias), plus `--color-status-nominal-line`, `--color-status-warning-line`, `--color-status-critical-line` for the other three new aliases. Focus ring: `--color-focus-ring` → `ring-focus`.

- [ ] **Step 1: Write the failing test**

`src/components/agent/ContextBar.test.tsx`:

```tsx
// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * A context chip is a control, not a styled div: it has a name a screen
 * reader can say, a separate remove button with its own name, a title that
 * says why it is here (the match terms), and the thread chip sits on the
 * telemetry tokens rather than a palette colour.
 */

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import { ContextBar, ContextPill, type ContextItem } from './ContextBar'

const THREAD: ContextItem = {
  id: 'thread:th-0',
  type: 'thread',
  label: 'pulled in: Samba share setup · 2026-07-14',
}

describe('ContextPill', () => {
  it('is a button with an accessible name', () => {
    render(<ContextPill item={THREAD} onClick={() => {}} />)
    expect(
      screen.getByRole('button', { name: 'earlier subject: pulled in: Samba share setup · 2026-07-14' }),
    ).toBeInTheDocument()
  })

  it('renders the thread chip on telemetry tokens, never a palette colour', () => {
    const { container } = render(<ContextPill item={THREAD} />)
    const pill = container.firstElementChild as HTMLElement
    expect(pill.className).toContain('bg-status-telemetry-bg')
    expect(pill.className).toContain('border-status-telemetry-line')
    expect(pill.className).not.toMatch(/\b(?:bg|text|border)-(?:blue|purple|violet|indigo|sky)-\d+\b/)
    expect(pill.className).toContain('text-[11px]')
  })

  it('shows its hint as the title — the chip\'s "why now" — and no title without one', () => {
    render(<ContextPill item={{ ...THREAD, hint: 'matched: samba, share' }} onClick={() => {}} />)
    expect(screen.getByRole('button', { name: /^earlier subject:/ })).toHaveAttribute('title', 'matched: samba, share')

    render(<ContextPill item={{ ...THREAD, id: 'thread:th-1' }} onClick={() => {}} />)
    const plain = screen.getAllByRole('button', { name: /^earlier subject:/ })[1]
    expect(plain).not.toHaveAttribute('title')
  })

  it('offers a sibling remove button with its own name', async () => {
    const onRemove = vi.fn()
    const onClick = vi.fn()
    render(<ContextPill item={THREAD} onRemove={onRemove} onClick={onClick} />)

    await userEvent.click(
      screen.getByRole('button', { name: 'Drop pulled in: Samba share setup · 2026-07-14 from context' }),
    )

    expect(onRemove).toHaveBeenCalledTimes(1)
    expect(onClick).not.toHaveBeenCalled()
  })
})

describe('ContextBar', () => {
  it('renders one pill per item and a labelled collapse control', async () => {
    const onRemoveItem = vi.fn()
    render(
      <ContextBar
        items={[THREAD, { id: 'f1', type: 'file', label: '/etc/samba/smb.conf', tokens: 120 }]}
        onRemoveItem={onRemoveItem}
      />,
    )

    expect(screen.getByRole('button', { name: /^earlier subject:/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'file: /etc/samba/smb.conf' })).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Drop /etc/samba/smb.conf from context' }))
    expect(onRemoveItem).toHaveBeenCalledWith('f1')

    const collapse = screen.getByRole('button', { name: 'Collapse context' })
    expect(collapse).toHaveAttribute('aria-expanded', 'true')
    await userEvent.click(collapse)
    expect(screen.getByRole('button', { name: 'Expand context' })).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByRole('button', { name: /^earlier subject:/ })).not.toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run it, watch it fail**

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core/halbert_core/dashboard/frontend && npx vitest run src/components/agent/ContextBar.test.tsx
```
Expected: 5 failures, first is `TypeError: Cannot read properties of undefined (reading 'icon')` (no `thread` entry in TYPE_CONFIG).

- [ ] **Step 3: Add the line aliases to `tailwind.config.js`**

Replace lines 75-84:

```js
        status: {
          nominal: "var(--color-status-nominal)",
          "nominal-bg": "var(--color-status-nominal-bg)",
          "nominal-line": "var(--color-status-nominal-line)",
          warning: "var(--color-status-warning)",
          "warning-bg": "var(--color-status-warning-bg)",
          "warning-line": "var(--color-status-warning-line)",
          critical: "var(--color-status-critical)",
          "critical-bg": "var(--color-status-critical-bg)",
          "critical-line": "var(--color-status-critical-line)",
          telemetry: "var(--color-status-telemetry)",
          "telemetry-bg": "var(--color-status-telemetry-bg)",
          "telemetry-line": "var(--color-status-telemetry-line)",
        },
```

Verify: `grep -c -- '-line": "var(--color-status-' tailwind.config.js` prints `4`; `grep -c -- '--color-status-telemetry-line' ../../../../shared-tokens/tokens.css` prints `1` (the variable exists; its `--hb-*` sources are on lines 148-151 / 298-301 / 345-348).

- [ ] **Step 4: Replace lines 10-117 of `ContextBar.tsx`**

```tsx
import { useState } from 'react';
import { FileText, Search, Brain, Globe, FolderOpen, MessageSquare, X, ChevronDown, ChevronUp } from 'lucide-react';

export type ContextType = 'file' | 'search' | 'memory' | 'web' | 'directory' | 'thread';

export interface ContextItem {
  id: string;
  type: ContextType;
  label: string;
  path?: string;
  preview?: string;
  tokens?: number;
  /** Why this is here, shown on hover — a thread chip's match terms ("matched: samba, share"). */
  hint?: string;
}

interface ContextPillProps {
  item: ContextItem;
  onRemove?: () => void;
  onClick?: () => void;
  isExpanded?: boolean;
}

/**
 * `noun` is the spoken prefix of the chip's accessible name ("earlier
 * subject: pulled in: Samba share setup · 2026-07-14"). The `thread` entry is
 * the only one on canonical tokens (telemetry); the older entries keep their
 * pre-existing palette classes — the literal-colour ratchet allows existing
 * debt, not new debt, so nothing here may add a palette class.
 */
const TYPE_CONFIG: Record<ContextType, { icon: typeof FileText; color: string; bg: string; noun: string }> = {
  file: { icon: FileText, color: 'text-info dark:text-info', bg: 'bg-blue-100 dark:bg-info/10 border-blue-200 dark:border-info/20', noun: 'file' },
  search: { icon: Search, color: 'text-purple-600 dark:text-purple-400', bg: 'bg-purple-100 dark:bg-purple-500/10 border-purple-200 dark:border-purple-500/20', noun: 'search' },
  memory: { icon: Brain, color: 'text-error dark:text-error', bg: 'bg-error-muted dark:bg-error/10 border-error-muted dark:border-error/20', noun: 'memory' },
  web: { icon: Globe, color: 'text-success dark:text-success', bg: 'bg-success-muted dark:bg-success/10 border-success-muted dark:border-success/20', noun: 'web' },
  directory: { icon: FolderOpen, color: 'text-warning dark:text-warning', bg: 'bg-warning-muted dark:bg-warning/10 border-warning-muted dark:border-warning/20', noun: 'directory' },
  thread: { icon: MessageSquare, color: 'text-status-telemetry', bg: 'bg-status-telemetry-bg border-status-telemetry-line', noun: 'earlier subject' },
};

export function ContextPill({ item, onRemove, onClick, isExpanded: _isExpanded }: ContextPillProps) {
  const config = TYPE_CONFIG[item.type];
  const Icon = config.icon;

  return (
    <span className={`inline-flex items-center rounded border text-[11px] font-mono ${config.bg}`}>
      <button
        type="button"
        aria-label={`${config.noun}: ${item.label}`}
        title={item.hint}
        onClick={onClick}
        className="inline-flex items-center gap-1 px-1.5 py-0.5 hover:opacity-80 transition-opacity focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
      >
        <Icon className={`h-2.5 w-2.5 ${config.color}`} aria-hidden="true" />
        <span className="text-foreground max-w-[140px] truncate">{item.label}</span>
        {item.tokens ? (
          <span className="text-muted-foreground text-[11px]">({item.tokens})</span>
        ) : null}
      </button>
      {onRemove && (
        <button
          type="button"
          aria-label={`Drop ${item.label} from context`}
          onClick={onRemove}
          className="mr-0.5 p-0.5 hover:bg-accent rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
        >
          <X className="h-2.5 w-2.5 text-muted-foreground" aria-hidden="true" />
        </button>
      )}
    </span>
  );
}

interface ContextBarProps {
  items: ContextItem[];
  onRemoveItem?: (id: string) => void;
  onItemClick?: (item: ContextItem) => void;
  className?: string;
}

export function ContextBar({ items, onRemoveItem, onItemClick, className = '' }: ContextBarProps) {
  const [isCollapsed, setIsCollapsed] = useState(false);

  if (items.length === 0) return null;

  const totalTokens = items.reduce((sum, item) => sum + (item.tokens || 0), 0);

  return (
    <div className={`border-b bg-muted/30 ${className}`}>
      <div className="flex items-center justify-between px-2 py-1">
        <div className="flex items-center gap-1.5">
          <span className="text-[11px] text-muted-foreground">Context</span>
          <span className="text-[11px] text-muted-foreground/70">
            {items.length} items • ~{totalTokens} tokens
          </span>
        </div>
        <button
          type="button"
          aria-label={isCollapsed ? 'Expand context' : 'Collapse context'}
          aria-expanded={!isCollapsed}
          onClick={() => setIsCollapsed(!isCollapsed)}
          className="p-0.5 hover:bg-accent rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
        >
          {isCollapsed ? (
            <ChevronDown className="h-2.5 w-2.5 text-muted-foreground" aria-hidden="true" />
          ) : (
            <ChevronUp className="h-2.5 w-2.5 text-muted-foreground" aria-hidden="true" />
          )}
        </button>
      </div>

      {!isCollapsed && (
        <div className="flex flex-wrap gap-1 px-2 pb-1.5">
          {items.map((item) => (
            <ContextPill
              key={item.id}
              item={item}
              onRemove={onRemoveItem ? () => onRemoveItem(item.id) : undefined}
              onClick={onItemClick ? () => onItemClick(item) : undefined}
            />
          ))}
        </div>
      )}
    </div>
  );
}
```

(`ContextPreview` at lines 119-158 is unchanged.)

- [ ] **Step 5: Run the test, the ratchet and the typecheck**

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core/halbert_core/dashboard/frontend && npx vitest run src/components/agent/ContextBar.test.tsx
```
Expected: `Tests  5 passed (5)`.

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core/halbert_core/dashboard/frontend && npx tsc --noEmit -p .
```
Expected: no output, exit 0 (`ContextType` only widened; `hint` is optional).

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation && python3 scripts/check_literal_colors.py --check
```
Expected: a line starting `OK:` (ContextBar.tsx keeps the same count of palette classes it had; the thread entry adds none).

- [ ] **Step 6: Commit**

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation && git add halbert_core/halbert_core/dashboard/frontend/tailwind.config.js halbert_core/halbert_core/dashboard/frontend/src/components/agent/ContextBar.tsx halbert_core/halbert_core/dashboard/frontend/src/components/agent/ContextBar.test.tsx && git commit -m "feat(dashboard): thread context chip on telemetry tokens

ContextPill is a button with an accessible name, an optional title that
says why the chip is here, and a sibling labelled remove button; the new
'thread' type uses the telemetry tokens only, via the status.*-line
Tailwind aliases that were missing. Minimum chip text is 11px."
```

### Task A17: `Timeline`, `CurrentTopicLabel`, `MessageContent` extraction, `announce()` + the two `LiveRegion`s in HostShell (polite status + assertive alert), read-only `DiffBlock`

**Files:**
- Create: `halbert_core/halbert_core/dashboard/frontend/src/components/agent/MessageContent.tsx`
- Create: `halbert_core/halbert_core/dashboard/frontend/src/components/agent/StaticTerminalChip.tsx`
- Create: `halbert_core/halbert_core/dashboard/frontend/src/components/agent/Timeline.tsx`
- Create: `halbert_core/halbert_core/dashboard/frontend/src/components/agent/CurrentTopicLabel.tsx`
- Create: `halbert_core/halbert_core/dashboard/frontend/src/lib/announce.ts`
- Create: `halbert_core/halbert_core/dashboard/frontend/src/components/shell/LiveRegion.tsx`
- Modify: `halbert_core/halbert_core/dashboard/frontend/src/components/agent/DiffBlock.tsx` (lines 13-35 props; 127-144 buttons)
- Modify: `halbert_core/halbert_core/dashboard/frontend/src/components/shell/HostShell.tsx` (lines 15-17 imports; 33-35 root)
- Modify: `halbert_core/halbert_core/dashboard/frontend/src/components/agent/index.ts` (append exports)
- Modify: `halbert_core/halbert_core/dashboard/frontend/src/hooks/useAgentStream.ts` (the `tool_confirmation_required` path speaks through the alert region)
- Test: `halbert_core/halbert_core/dashboard/frontend/src/components/agent/Timeline.test.tsx`
- Test: `halbert_core/halbert_core/dashboard/frontend/src/components/shell/LiveRegion.test.tsx`
- Test: `halbert_core/halbert_core/dashboard/frontend/src/hooks/useAgentStream.thread.test.ts` (one test appended)

Voice note: spec §11 says "the `<continuity>` text and the sticky label follow the voice setting". The continuity text is prose with pronouns and is voice-rendered server-side (A8). `CurrentTopicLabel` shows a thread **title** ("Samba share setup") — a noun phrase with no pronouns — so there is nothing for a voice to change; it renders the title as stored and needs no voice branch.

Token classes used (all backed by `/shared-tokens/tokens.css` via `tailwind.config.js` lines 55-90): `text-ink-secondary`, `text-ink-tertiary` (`--color-ink-secondary`, `--color-ink-tertiary`), `bg-hairline`, `border-hairline`, `border-hairline-subtle` (`--color-line`, `--color-line-subtle`), `bg-canvas-subtle`, `bg-canvas-muted` (`--color-surface-subtle`, `--color-surface-muted`), `tracking-label` (`--tracking-label`), `ring-focus` (`--color-focus-ring`). The user/assistant bubble surfaces reuse the exact classes AgentChat already uses (`bg-primary text-primary-foreground`, `bg-muted/50 border-border/50`) so live and stored turns look identical.

- [ ] **Step 1: Write the failing Timeline test**

`src/components/agent/Timeline.test.tsx`:

```tsx
// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * The stored conversation renders with roles: day dividers as headings with
 * a machine-readable date, one article per turn, static tool cards, an
 * "ended" chip for a terminal the store no longer has, and diffs that can
 * no longer be applied.
 */

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import { Timeline } from './Timeline'
import { groupByDay } from '../../hooks/useTimeline'
import type { TimelineTurn } from '../../types/timeline'

// The live tile needs xterm + a real font pipeline; the timeline test is
// about records, so the tile is a stub here.
vi.mock('./TerminalTile', () => ({
  TerminalTile: ({ session }: { session: { id: string } }) => <div data-testid="live-tile">{session.id}</div>,
}))

const NOW = new Date(2026, 6, 16, 12, 0, 0) // Thu 16 Jul 2026

function turn(id: string, timestamp: number, text: string, extra: Partial<TimelineTurn> = {}): TimelineTurn {
  return {
    turnId: id,
    threadId: 'th-1',
    timestamp,
    origin: 'human',
    user: { messageId: 1, content: text, timestamp, status: 'complete' },
    assistant: { messageId: 2, content: `Answer to ${text}`, timestamp: timestamp + 2000, status: 'complete' },
    blocks: [],
    terminalBlockIds: [],
    diffProposals: [],
    ...extra,
  }
}

const OLD = new Date(2026, 6, 14, 9, 30).getTime()
const TODAY = new Date(2026, 6, 16, 8, 0).getTime()

const TURNS = [
  turn('t-1', OLD, 'is samba running?', {
    blocks: [{ tool: 'run_command', args: { command: 'systemctl status smbd' }, result: 'active', exit: 0, executionId: 'x1' }],
    terminalBlockIds: ['term-gone'],
    diffProposals: [{ id: 'd1', filePath: '/etc/samba/smb.conf', newContent: 'b', oldContent: 'a', additions: 1, deletions: 1, status: 'pending' }],
  }),
  turn('t-2', TODAY, 'and now?', {
    user: { messageId: 5, content: 'and now?', timestamp: TODAY, status: 'interrupted' },
    assistant: null,
  }),
]

describe('Timeline', () => {
  it('renders day dividers as h2 + time and one article per turn', () => {
    const { container } = render(
      <Timeline byDay={groupByDay(TURNS, NOW)} hasMore={false} loading={false} onLoadOlder={() => {}} />,
    )

    const feed = screen.getByRole('feed')
    expect(feed).toHaveAttribute('aria-busy', 'false')

    const headings = screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent)
    expect(headings).toEqual(['Tue, Jul 14', 'Today'])

    const times = Array.from(container.querySelectorAll('header.thread-divider time')).map((t) => t.getAttribute('datetime'))
    expect(times).toEqual(['2026-07-14', '2026-07-16'])

    const articles = screen.getAllByRole('article')
    expect(articles).toHaveLength(2)
    expect(articles[0]).toHaveAttribute('data-turn-id', 't-1')
  })

  it('renders user and assistant content with their roles', () => {
    render(<Timeline byDay={groupByDay(TURNS, NOW)} hasMore={false} loading={false} onLoadOlder={() => {}} />)
    expect(screen.getByText('is samba running?')).toBeInTheDocument()
    expect(screen.getByText('Answer to is samba running?')).toBeInTheDocument()
    expect(screen.getByText('(Halbert restarted here)')).toBeInTheDocument()
  })

  it('renders static tool cards, an ended-terminal chip and a read-only diff', () => {
    render(<Timeline byDay={groupByDay(TURNS, NOW)} hasMore={false} loading={false} onLoadOlder={() => {}} />)

    expect(screen.getByText('run_command')).toBeInTheDocument()
    expect(screen.getByText('terminal · ended')).toBeInTheDocument()
    expect(screen.queryByTestId('live-tile')).not.toBeInTheDocument()
    expect(screen.getByText('/etc/samba/smb.conf')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /apply/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /reject/i })).not.toBeInTheDocument()
    expect(screen.getByText('proposed')).toBeInTheDocument()
  })

  it('offers "Load earlier" only when there is more, and marks the feed busy while paging', async () => {
    const onLoadOlder = vi.fn()
    const { rerender } = render(
      <Timeline byDay={groupByDay(TURNS, NOW)} hasMore onLoadOlder={onLoadOlder} loading={false} />,
    )
    await userEvent.click(screen.getByRole('button', { name: 'Load earlier' }))
    expect(onLoadOlder).toHaveBeenCalledTimes(1)

    rerender(<Timeline byDay={groupByDay(TURNS, NOW)} hasMore onLoadOlder={onLoadOlder} loading />)
    expect(screen.getByRole('feed')).toHaveAttribute('aria-busy', 'true')
    expect(screen.getByRole('button', { name: 'Loading…' })).toBeDisabled()

    rerender(<Timeline byDay={groupByDay(TURNS, NOW)} hasMore={false} onLoadOlder={onLoadOlder} loading={false} />)
    expect(screen.queryByRole('button', { name: 'Load earlier' })).not.toBeInTheDocument()
  })

  it('renders nothing at all for an empty, fully loaded timeline', () => {
    const { container } = render(<Timeline byDay={[]} hasMore={false} loading={false} onLoadOlder={() => {}} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('offers "Back to latest" only while anchored on an earlier window', async () => {
    const onLoadLatest = vi.fn()
    const { rerender } = render(
      <Timeline byDay={groupByDay(TURNS, NOW)} hasMore={false} loading={false} onLoadOlder={() => {}} onLoadLatest={onLoadLatest} />,
    )
    expect(screen.queryByRole('button', { name: 'Back to latest' })).not.toBeInTheDocument()

    rerender(
      <Timeline byDay={groupByDay(TURNS, NOW)} hasMore={false} loading={false} anchored onLoadOlder={() => {}} onLoadLatest={onLoadLatest} />,
    )
    await userEvent.click(screen.getByRole('button', { name: 'Back to latest' }))
    expect(onLoadLatest).toHaveBeenCalledTimes(1)
  })
})
```

- [ ] **Step 2: Write the failing LiveRegion test**

`src/components/shell/LiveRegion.test.tsx`:

```tsx
// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * Two live regions for the shell (design §11): a polite status region for
 * "Pulled in earlier work" / "New subject", and an assertive alert region
 * used for exactly one thing — blocked on approval. announce() is a
 * module-level function so a hook deep in the conversation can speak
 * without threading a callback through five components; each region clears
 * and re-sets so the same sentence said twice is announced twice.
 */

import { render, screen, waitFor, act } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { LiveRegion } from './LiveRegion'
import { announce, subscribeAnnouncements, lastAnnouncement, lastAlert } from '../../lib/announce'

describe('LiveRegion', () => {
  it('is a visually hidden polite status region', () => {
    render(<LiveRegion />)
    const region = screen.getByRole('status')
    expect(region).toHaveAttribute('aria-live', 'polite')
    expect(region).toHaveAttribute('aria-atomic', 'true')
    expect(region.className).toContain('sr-only')
    expect(region).toHaveTextContent('')
  })

  it('also has a visually hidden assertive alert region, empty by default', () => {
    render(<LiveRegion />)
    const alert = screen.getByRole('alert')
    expect(alert).toHaveAttribute('aria-live', 'assertive')
    expect(alert).toHaveAttribute('aria-atomic', 'true')
    expect(alert.className).toContain('sr-only')
    expect(alert).toHaveTextContent('')
  })

  it('routes an assertive announcement to the alert region only', async () => {
    render(<LiveRegion />)
    act(() => {
      announce('Waiting for your approval', { assertive: true })
    })
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Waiting for your approval'))
    expect(screen.getByRole('status')).toHaveTextContent('')
    expect(lastAlert()).toBe('Waiting for your approval')
  })

  it('speaks what announce() is given', async () => {
    render(<LiveRegion />)
    act(() => {
      announce('Pulled in earlier work: Samba share setup')
    })
    await waitFor(() =>
      expect(screen.getByRole('status')).toHaveTextContent('Pulled in earlier work: Samba share setup'),
    )
    expect(lastAnnouncement()).toBe('Pulled in earlier work: Samba share setup')
    expect(screen.getByRole('alert')).toHaveTextContent('')
  })

  it('re-announces an identical sentence by clearing first', async () => {
    render(<LiveRegion />)
    const seen: string[] = []
    const unsubscribe = subscribeAnnouncements((text) => seen.push(text))

    act(() => {
      announce('New subject')
    })
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('New subject'))
    act(() => {
      announce('New subject')
    })
    // The region empties between the two so assistive tech sees a change.
    expect(screen.getByRole('status')).toHaveTextContent('')
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('New subject'))

    expect(seen).toEqual(['New subject', 'New subject'])
    unsubscribe()
  })
})
```

- [ ] **Step 3: Run both, watch them fail**

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core/halbert_core/dashboard/frontend && npx vitest run src/components/agent/Timeline.test.tsx src/components/shell/LiveRegion.test.tsx
```
Expected: both files fail to load: `Failed to resolve import "./Timeline"` and `Failed to resolve import "./LiveRegion"`.

- [ ] **Step 4: Create `src/components/agent/MessageContent.tsx`** (verbatim move of AgentChat.tsx lines 132-184; AgentChat switches to this import in A18)

```tsx
// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * MessageContent — assistant text with fenced code blocks rendered as
 * runnable CodeBlocks. Shared by the live assistant block (AgentChat) and
 * the stored turns (Timeline) so a reply looks the same the moment it lands
 * and a week later.
 */

import { CodeBlock } from '../domain/CodeBlock';

export type RunCommand = (cmd: string) => Promise<{ output?: string; error?: string; exit_code?: number }>;

interface MessageContentProps {
  content: string;
  onRunCommand?: RunCommand;
}

export function MessageContent({ content, onRunCommand }: MessageContentProps) {
  const parts: Array<{ type: 'text' | 'code', content: string, lang?: string }> = [];
  const codeBlockRegex = /```(\w+)?\n?([\s\S]*?)```/g;
  let lastIndex = 0;
  let match;

  while ((match = codeBlockRegex.exec(content)) !== null) {
    if (match.index > lastIndex) {
      parts.push({ type: 'text', content: content.slice(lastIndex, match.index) });
    }
    let codeContent = match[2].trim();
    codeContent = codeContent.replace(/^`+|`+$/g, '').trim();
    parts.push({ type: 'code', content: codeContent, lang: match[1] || 'bash' });
    lastIndex = match.index + match[0].length;
  }

  if (lastIndex < content.length) {
    parts.push({ type: 'text', content: content.slice(lastIndex) });
  }

  if (parts.length === 0) {
    parts.push({ type: 'text', content });
  }

  return (
    <div className="space-y-2 min-w-0 overflow-hidden">
      {parts.map((part, i) => {
        if (part.type === 'code') {
          return (
            <CodeBlock
              key={i}
              code={part.content}
              lang={part.lang || 'bash'}
              onRun={onRunCommand}
              compact
            />
          );
        }
        return (
          <span key={i} className="whitespace-pre-wrap break-words">{part.content}</span>
        );
      })}
    </div>
  );
}

export default MessageContent;
```

- [ ] **Step 5: Create `src/components/agent/StaticTerminalChip.tsx`**

```tsx
// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * StaticTerminalChip — the record of a terminal the page no longer holds.
 *
 * A stored turn remembers the ids of the terminals it opened; after a reload
 * the live store does not have them (Plan A stores ids, not output — Plan B
 * stores blocks). The chip keeps the spot in the transcript honest: a
 * terminal ran here, and it has ended. Copy is state-based, never a hash.
 */

interface StaticTerminalChipProps {
  id: string;
  /** Command line, when known. */
  label?: string;
}

export function StaticTerminalChip({ id, label }: StaticTerminalChipProps) {
  return (
    <span
      data-session-id={id}
      title="This terminal ended before the page loaded"
      className="inline-flex items-center gap-1.5 rounded-full border border-hairline bg-canvas-subtle px-2 py-0.5 text-[11px] font-mono text-ink-secondary"
    >
      <span>terminal · ended</span>
      {label && <span className="truncate max-w-[12rem] text-ink-tertiary">{label}</span>}
    </span>
  );
}

export default StaticTerminalChip;
```

- [ ] **Step 6: Make `DiffBlock` read-only capable**

In `src/components/agent/DiffBlock.tsx`, replace lines 13-35 with:

```tsx
interface DiffBlockProps {
  filePath: string;
  oldContent?: string;
  newContent: string;
  additions?: number;
  deletions?: number;
  onApply: () => void;
  onReject: () => void;
  status?: 'pending' | 'applied' | 'rejected';
  /** A stored turn: the session is gone, so a pending diff is a record, not a choice. */
  readOnly?: boolean;
  className?: string;
}

export function DiffBlock({
  filePath,
  oldContent,
  newContent,
  additions = 0,
  deletions = 0,
  onApply,
  onReject,
  status = 'pending',
  readOnly = false,
  className = '',
}: DiffBlockProps) {
```

Replace lines 127-144 (the `{status === 'pending' && ( ... )}` fragment with the two buttons) with:

```tsx
          {status === 'pending' && readOnly && (
            <span className="text-[11px] font-mono text-ink-tertiary">proposed</span>
          )}
          {status === 'pending' && !readOnly && (
            <>
              <button
                onClick={onReject}
                className="flex items-center gap-0.5 px-1.5 py-0.5 text-[10px] text-destructive hover:bg-destructive/10 rounded transition-colors"
              >
                <X className="h-2.5 w-2.5" />
                Reject
              </button>
              <button
                onClick={onApply}
                className="flex items-center gap-0.5 px-1.5 py-0.5 text-[10px] text-success dark:text-success bg-success-muted dark:bg-success/10 hover:bg-success-muted dark:hover:bg-success/20 rounded transition-colors"
              >
                <Check className="h-2.5 w-2.5" />
                Apply
              </button>
            </>
          )}
```

- [ ] **Step 7: Create `src/components/agent/Timeline.tsx`**

```tsx
// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * Timeline — the stored conversation, oldest first, grouped by day.
 *
 * Every turn here is a record: the user's words, the reply, tool calls as
 * static cards (status read from the stored exit code), terminals as live
 * tiles while the store still has them and as an "ended" chip when it does
 * not, and diffs read-only. Nothing in a past turn can act on a session that
 * no longer exists.
 *
 * The turn in flight is NOT rendered here — AgentChat keeps its live block
 * and appends the finished turn through useTimeline.appendLive.
 *
 * Markup, per the design: a `role="feed"` container that is `aria-busy`
 * while paging, `<header><h2>{day}</h2><time datetime></header>` dividers,
 * and one `role="article"` per turn.
 */

import { useTerminalSessions } from '../../hooks/useTerminalSessions';
import type { ToolExecution } from '../../hooks/useAgentStream';
import type { TimelineDay } from '../../hooks/useTimeline';
import type { TimelineToolBlock, TimelineTurn } from '../../types/timeline';
import { ToolExecutionCard } from './ToolExecutionCard';
import { DiffBlock } from './DiffBlock';
import { InlineTerminals } from './InlineTerminals';
import { StaticTerminalChip } from './StaticTerminalChip';
import { MessageContent, type RunCommand } from './MessageContent';

interface TimelineProps {
  byDay: TimelineDay[];
  hasMore: boolean;
  loading: boolean;
  /** True while the page is a window around an earlier turn (a chip jump). */
  anchored?: boolean;
  onLoadOlder: () => void;
  /** Back to the newest page; rendered as a control only while `anchored`. */
  onLoadLatest?: () => void;
  onRunCommand?: RunCommand;
}

/**
 * A stored tool block in the shape the card renders. `block.status` is the
 * backend's own verdict (spec §8 messages.blocks_json / state_machine.py
 * _tool_block) and is authoritative when present: `exit` is only ever set
 * for `run_command` (state_machine.py:614-638), so a failed non-run_command
 * tool, or a call superseded before it ran (~line 446, `{exit: null, status:
 * "superseded"}`), would otherwise render as a green "success" card under
 * the exit-only heuristic. Only when the backend sent no status at all
 * (older, pre-status rows) does this fall back to that heuristic: exit 0 or
 * unknown reads as success.
 */
export function executionFromBlock(block: TimelineToolBlock, fallbackId: string): ToolExecution {
  const exit = block.exit;
  const status: ToolExecution['status'] =
    block.status === 'success' ? 'success'
    : block.status === 'error' || block.status === 'superseded' ? 'error'
    : exit == null || exit === 0 ? 'success' : 'error';
  return {
    executionId: block.executionId ?? fallbackId,
    tool: block.tool,
    args: block.args ?? {},
    status,
    result: block.result,
    error: block.error,
  };
}

interface TurnArticleProps {
  turn: TimelineTurn;
  liveIds: Set<string>;
  onRunCommand?: RunCommand;
}

function TurnArticle({ turn, liveIds, onRunCommand }: TurnArticleProps) {
  const liveTerminals = turn.terminalBlockIds.filter((id) => liveIds.has(id));
  const endedTerminals = turn.terminalBlockIds.filter((id) => !liveIds.has(id));
  const hasAssistantSide =
    turn.assistant !== null ||
    turn.blocks.length > 0 ||
    turn.terminalBlockIds.length > 0 ||
    turn.diffProposals.length > 0;
  const label = turn.user ? turn.user.content.slice(0, 80) : turn.origin;

  return (
    <article
      role="article"
      aria-label={label}
      data-turn-id={turn.turnId}
      data-thread-id={turn.threadId}
      className="space-y-3"
    >
      {turn.user && (
        <div className="flex justify-end">
          <div className="max-w-[80%] bg-primary text-primary-foreground px-4 py-2 rounded-lg">
            <p className="text-sm whitespace-pre-wrap break-words">{turn.user.content}</p>
          </div>
        </div>
      )}

      {turn.user?.status === 'interrupted' && (
        <p className="text-center text-[11px] font-mono text-ink-tertiary">(Halbert restarted here)</p>
      )}

      {hasAssistantSide && (
        <div className="flex justify-start">
          <div className="max-w-[85%] bg-muted/50 border border-border/50 rounded-lg p-4 space-y-3">
            {turn.blocks.map((block, i) => (
              <ToolExecutionCard
                key={block.executionId ?? `${turn.turnId}-block-${i}`}
                execution={executionFromBlock(block, `${turn.turnId}-block-${i}`)}
              />
            ))}

            {liveTerminals.length > 0 && <InlineTerminals sessionIds={liveTerminals} />}

            {endedTerminals.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {endedTerminals.map((id) => (
                  <StaticTerminalChip key={id} id={id} />
                ))}
              </div>
            )}

            {turn.diffProposals.map((diff) => (
              <DiffBlock
                key={diff.id}
                filePath={diff.filePath}
                oldContent={diff.oldContent}
                newContent={diff.newContent}
                additions={diff.additions}
                deletions={diff.deletions}
                status={diff.status}
                readOnly
                onApply={() => {}}
                onReject={() => {}}
              />
            ))}

            {turn.assistant && (
              <div className="text-sm text-foreground">
                <MessageContent content={turn.assistant.content} onRunCommand={onRunCommand} />
              </div>
            )}

            {turn.assistant?.status === 'cancelled' && (
              <p className="text-[11px] font-mono text-ink-tertiary">cancelled</p>
            )}
          </div>
        </div>
      )}
    </article>
  );
}

export function Timeline({
  byDay,
  hasMore,
  loading,
  anchored = false,
  onLoadOlder,
  onLoadLatest,
  onRunCommand,
}: TimelineProps) {
  const { sessions } = useTerminalSessions();
  const liveIds = new Set(sessions.map((s) => s.id));

  if (byDay.length === 0 && !hasMore) return null;

  return (
    <div role="feed" aria-label="Conversation" aria-busy={loading} className="space-y-2">
      {hasMore && (
        <div className="flex justify-center">
          <button
            type="button"
            onClick={onLoadOlder}
            disabled={loading}
            className="rounded-full border border-hairline bg-canvas-subtle px-3 py-1 text-[11px] font-mono text-ink-secondary hover:bg-canvas-muted disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
          >
            {loading ? 'Loading…' : 'Load earlier'}
          </button>
        </div>
      )}

      {byDay.map((day) => (
        <section key={day.dayKey} aria-label={day.label} className="space-y-4">
          <header className="thread-divider flex items-center gap-3 pt-2">
            <span className="h-px flex-1 bg-hairline" aria-hidden="true" />
            <h2 className="text-[11px] font-mono uppercase tracking-label text-ink-tertiary">{day.label}</h2>
            <time dateTime={day.dayKey} className="sr-only">{day.dayKey}</time>
            <span className="h-px flex-1 bg-hairline" aria-hidden="true" />
          </header>
          {day.turns.map((turn) => (
            <TurnArticle key={turn.turnId} turn={turn} liveIds={liveIds} onRunCommand={onRunCommand} />
          ))}
        </section>
      ))}

      {/* A chip jump replaced the page with an earlier window; the turns
          between that window and now are not on screen, so say so and offer
          the way back rather than letting the live turn append after a gap. */}
      {anchored && onLoadLatest && (
        <div className="flex justify-center pt-2">
          <button
            type="button"
            onClick={onLoadLatest}
            disabled={loading}
            className="rounded-full border border-hairline bg-canvas-subtle px-3 py-1 text-[11px] font-mono text-ink-secondary hover:bg-canvas-muted disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
          >
            Back to latest
          </button>
        </div>
      )}
    </div>
  );
}

export default Timeline;
```

- [ ] **Step 8: Create `src/components/agent/CurrentTopicLabel.tsx`**

```tsx
// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * CurrentTopicLabel — the open subject's title, pinned to the top of the
 * scroll. One quiet line; it is a bearing, not a control. Changes are
 * announced through the shell's live region (announce('New subject')), so
 * this element itself is aria-live="off".
 *
 * No voice rendering here: a title ("Samba share setup") has no pronouns,
 * so first-person / the-computer / hybrid would all print the same thing.
 * The voice setting applies to the <continuity> prose, which is rendered
 * server-side.
 */

interface CurrentTopicLabelProps {
  thread: { title: string } | null;
}

export function CurrentTopicLabel({ thread }: CurrentTopicLabelProps) {
  if (!thread || !thread.title) return null;
  return (
    <div
      aria-live="off"
      className="sticky top-0 z-10 border-b border-hairline-subtle bg-background/95 px-4 py-1 backdrop-blur"
    >
      <p data-testid="current-topic" className="truncate text-xs text-ink-secondary">
        {thread.title}
      </p>
    </div>
  );
}

export default CurrentTopicLabel;
```

- [ ] **Step 9: Create `src/lib/announce.ts`**

```ts
// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * announce — speak one short sentence through the shell's live regions.
 *
 * Module-level on purpose, like hostConversation.ts: the thing that knows a
 * subject changed is a hook several components below the shell, and a live
 * region only works when there is exactly one of each kind. Two kinds
 * (design §11): polite (the default — "Pulled in earlier work: …", "New
 * subject", "<command> finished, exit 0") and assertive, reserved for the
 * one thing that blocks the admin: waiting for their approval. Subscribers
 * are the regions (LiveRegion.tsx) and tests.
 */

export interface AnnounceOptions {
  /** Interrupt what is being read. Only for blocked-on-approval. */
  assertive?: boolean
}

type Listener = (text: string, options: AnnounceOptions) => void

const listeners = new Set<Listener>()
let lastPolite = ''
let lastAssertive = ''

export function announce(text: string, options: AnnounceOptions = {}): void {
  if (options.assertive) {
    lastAssertive = text
  } else {
    lastPolite = text
  }
  listeners.forEach((listener) => listener(text, options))
}

export function subscribeAnnouncements(listener: Listener): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

/** The most recent polite sentence, for tests and debugging. */
export function lastAnnouncement(): string {
  return lastPolite
}

/** The most recent assertive sentence, for tests and debugging. */
export function lastAlert(): string {
  return lastAssertive
}
```

- [ ] **Step 10: Create `src/components/shell/LiveRegion.tsx`**

```tsx
// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * LiveRegion — the shell's two live regions (design §11): one polite
 * `role="status"` for the running commentary, one assertive `role="alert"`
 * for blocked-on-approval only.
 *
 * Visually hidden; fed by lib/announce. Assistive tech only speaks a live
 * region when its content CHANGES, so the same sentence twice ("New subject"
 * after "New subject") would be silent the second time. Each region empties
 * first and fills a beat later, which makes every announcement a change.
 */

import { useEffect, useState } from 'react';
import { subscribeAnnouncements } from '../../lib/announce';

const REFILL_MS = 50;

export function LiveRegion() {
  const [status, setStatus] = useState('');
  const [alertText, setAlertText] = useState('');

  useEffect(() => {
    const timers: Record<'status' | 'alert', ReturnType<typeof setTimeout> | null> = {
      status: null,
      alert: null,
    };
    const unsubscribe = subscribeAnnouncements((next, { assertive }) => {
      const key = assertive ? 'alert' : 'status';
      const set = assertive ? setAlertText : setStatus;
      set('');
      const pending = timers[key];
      if (pending) clearTimeout(pending);
      timers[key] = setTimeout(() => set(next), REFILL_MS);
    });
    return () => {
      unsubscribe();
      if (timers.status) clearTimeout(timers.status);
      if (timers.alert) clearTimeout(timers.alert);
    };
  }, []);

  return (
    <>
      <div role="status" aria-live="polite" aria-atomic="true" className="sr-only">
        {status}
      </div>
      <div role="alert" aria-live="assertive" aria-atomic="true" className="sr-only">
        {alertText}
      </div>
    </>
  );
}

export default LiveRegion;
```

- [ ] **Step 11: Mount the region in `HostShell.tsx`**

Replace lines 15-17:
```tsx
import { useCallback, useRef } from 'react';
import { AgentChat } from '../agent/AgentChat';
import { ContextStage } from './ContextStage';
import { LiveRegion } from './LiveRegion';
```
Replace lines 33-35:
```tsx
  return (
    <div className="flex h-full min-h-0 min-w-0">
      {/* One polite status region and one assertive alert region for the
          whole shell (design §11). */}
      <LiveRegion />
      {/* Conversation spine */}
```

- [ ] **Step 12: Export from the agent barrel**

Append to `src/components/agent/index.ts`:

```ts
export { Timeline } from './Timeline'
export { CurrentTopicLabel } from './CurrentTopicLabel'
export { MessageContent } from './MessageContent'
export { StaticTerminalChip } from './StaticTerminalChip'
```

- [ ] **Step 12b: Speak "Waiting for your approval" through the alert region**

Today `tool_confirmation_required` (in `handleEvent`'s `switch`, `useAgentStream.ts`) builds a `ConfirmationRequest`, calls `options.onConfirmationRequired`, and stores it as `pendingConfirmation`; `AgentChat` renders `ConfirmationDialog` from that. Nothing is said to assistive tech. The hook has no access to the onboarding name (`display_name` lives in `useHostIdentity`'s module store, which is not exported and must not be polled from an event handler), so the sentence is the name-free "Waiting for your approval" — it is the one assertive announcement in the app.

First the test. Append to `src/hooks/useAgentStream.thread.test.ts`, inside the `describe('useAgentStream — thread events', …)` block, after the `reset()` test (before the block's closing `})`):

```ts
  it('says "Waiting for your approval" assertively when a confirmation is required', async () => {
    streamFetch([
      ev('tool_confirmation_required', {
        execution_id: 'x1',
        tool: 'run_command',
        description: 'rm -rf /tmp/scratch',
        risk_level: 'high',
      }),
    ])

    const { result } = renderHook(() => useAgentStream())
    act(() => {
      result.current.sendMessage('clean up', 'turn-1')
    })

    await waitFor(() => expect(result.current.session?.pendingConfirmation?.actionId).toBe('x1'))
    expect(lastAlert()).toBe('Waiting for your approval')
    expect(lastAnnouncement()).not.toBe('Waiting for your approval')
  })
```

and add to that file's imports (after the `terminalSessionStore` import line):

```ts
import { lastAlert, lastAnnouncement } from '../lib/announce'
```

Run it, watch it fail:

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core/halbert_core/dashboard/frontend && npx vitest run src/hooks/useAgentStream.thread.test.ts
```
Expected: 1 failure — `expected '' to be 'Waiting for your approval'`.

Then in `src/hooks/useAgentStream.ts`, after the import line `import { terminalSessionStore } from './useTerminalSessions';` add:

```ts
import { announce } from '@/lib/announce';
```

and in `handleEvent`, replace

```ts
      applyTerminalEvent(event);
    }

    setSession(prev => {
      if (!prev) return prev;
```

with

```ts
      applyTerminalEvent(event);
    }

    // Blocked on approval is the one thing said assertively (design §11).
    // Outside the updater: updaters must stay pure (StrictMode runs them
    // twice), and this must be said exactly once.
    if (event.type === 'tool_confirmation_required') {
      announce('Waiting for your approval', { assertive: true });
    }

    setSession(prev => {
      if (!prev) return prev;
```

Run the hook tests again:

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core/halbert_core/dashboard/frontend && npx vitest run src/hooks/useAgentStream.thread.test.ts src/hooks/useAgentStream.terminal.test.ts
```
Expected: `Tests  15 passed (15)`.

- [ ] **Step 13: Run the tests, the ratchet and the typecheck**

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core/halbert_core/dashboard/frontend && npx vitest run src/components/agent/Timeline.test.tsx src/components/shell/LiveRegion.test.tsx src/hooks/useAgentStream.thread.test.ts
```
Expected: `Test Files  3 passed (3)`, `Tests  19 passed (19)` (6 + 5 + 8).

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core/halbert_core/dashboard/frontend && npx tsc --noEmit -p .
```
Expected: no output, exit 0 (`DiffBlock.readOnly` and the `Timeline` extras are optional props; the hook change is additive).

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation && python3 scripts/check_literal_colors.py --check
```
Expected: `OK: …` (the new files contain no palette classes).

- [ ] **Step 14: Commit**

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation && git add halbert_core/halbert_core/dashboard/frontend/src/components/agent/MessageContent.tsx halbert_core/halbert_core/dashboard/frontend/src/components/agent/StaticTerminalChip.tsx halbert_core/halbert_core/dashboard/frontend/src/components/agent/Timeline.tsx halbert_core/halbert_core/dashboard/frontend/src/components/agent/Timeline.test.tsx halbert_core/halbert_core/dashboard/frontend/src/components/agent/CurrentTopicLabel.tsx halbert_core/halbert_core/dashboard/frontend/src/components/agent/DiffBlock.tsx halbert_core/halbert_core/dashboard/frontend/src/components/agent/index.ts halbert_core/halbert_core/dashboard/frontend/src/lib/announce.ts halbert_core/halbert_core/dashboard/frontend/src/components/shell/LiveRegion.tsx halbert_core/halbert_core/dashboard/frontend/src/components/shell/LiveRegion.test.tsx halbert_core/halbert_core/dashboard/frontend/src/components/shell/HostShell.tsx halbert_core/halbert_core/dashboard/frontend/src/hooks/useAgentStream.ts halbert_core/halbert_core/dashboard/frontend/src/hooks/useAgentStream.thread.test.ts && git commit -m "feat(dashboard): timeline, current-topic label and the shell live regions

Stored turns render with roles: day dividers as h2 + time, one article
per turn, static tool cards from the stored exit code, an 'ended' chip
for terminals the store no longer has, read-only diffs, and a 'Back to
latest' control while the page is a window around an earlier turn.
MessageContent moves out of AgentChat so live and stored replies share
one renderer. announce() feeds two regions mounted in HostShell: a
polite status region, and an assertive alert region that says only
'Waiting for your approval' when a confirmation is required."
```

### Task A17b: Per-turn "Forget this" — `api.redactMessage` and the redaction marker in `Timeline`

**Files:**
- Modify: `halbert_core/halbert_core/dashboard/frontend/src/lib/api.ts` (one method inserted after `retractRecall`)
- Modify: `halbert_core/halbert_core/dashboard/frontend/src/components/agent/Timeline.tsx` (created in A17: imports, and everything from `interface TurnArticleProps {` to the end of the file)
- Test: `halbert_core/halbert_core/dashboard/frontend/src/lib/api.timeline.test.ts` (one describe appended)
- Test: `halbert_core/halbert_core/dashboard/frontend/src/components/agent/Timeline.test.tsx` (one describe appended)

Spec §5: per turn, "forget this" replaces `content` and `blocks_json` with `[redacted by admin]`, rewrites the FTS row and regenerates the receipt; rows are never deleted. The page side of that: a small control on each stored turn that POSTs `/api/agent/message/{message_id}/redact` for the user row and the assistant row, and — once both calls have succeeded — shows the marker in place of the words and the tool cards. A turn appended live in this page load carries `messageId: -1` (see `turnFromSession`, A18) until the next load, so it gets no control. Backend route: `POST /api/agent/message/{message_id}/redact -> {"ok": true}` (contract listed at the end of this part for the backend planner).

- [ ] **Step 1: Write the failing API test**

Append to `src/lib/api.timeline.test.ts`:

```ts
describe('api.redactMessage', () => {
  it('POSTs the redact route for one stored row', async () => {
    const fetchMock = mockFetch({ ok: true })
    await api.redactMessage(7)
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/agent/message/7/redact')
    expect(init.method).toBe('POST')
  })
})
```

- [ ] **Step 2: Write the failing Timeline test**

In `src/components/agent/Timeline.test.tsx`, replace the first two import lines

```tsx
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
```

with

```tsx
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, afterEach, vi } from 'vitest'
```

and append at the end of the file:

```tsx
describe('Timeline — Forget this', () => {
  afterEach(() => vi.unstubAllGlobals())

  function redactFetch() {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      text: async () => '',
      json: async () => ({ ok: true }),
    })
    vi.stubGlobal('fetch', fetchMock)
    return fetchMock
  }

  it('redacts both stored rows and replaces the turn with the marker', async () => {
    const fetchMock = redactFetch()
    render(<Timeline byDay={groupByDay(TURNS, NOW)} hasMore={false} loading={false} onLoadOlder={() => {}} />)

    // Both fixture turns are stored (server ids 1/2 and 5), so both offer it.
    const buttons = screen.getAllByRole('button', { name: 'Forget this turn' })
    expect(buttons).toHaveLength(2)
    await userEvent.click(buttons[0])

    await waitFor(() => expect(screen.getAllByText('[redacted by admin]')).toHaveLength(2))
    const calls = fetchMock.mock.calls.map(([url, init]) => [String(url), (init as RequestInit).method])
    expect(calls).toEqual([
      ['/api/agent/message/1/redact', 'POST'],
      ['/api/agent/message/2/redact', 'POST'],
    ])
    expect(screen.queryByText('is samba running?')).not.toBeInTheDocument()
    expect(screen.queryByText('Answer to is samba running?')).not.toBeInTheDocument()
    expect(screen.queryByText('run_command')).not.toBeInTheDocument()
    // Terminal ids are not part of the redaction; the ended chip stays.
    expect(screen.getByText('terminal · ended')).toBeInTheDocument()
    // The row is never deleted: the article and its id remain.
    expect(screen.getAllByRole('article')[0]).toHaveAttribute('data-turn-id', 't-1')
    expect(screen.getAllByRole('button', { name: 'Forget this turn' })).toHaveLength(1)
  })

  it('offers no control for rows without a server id, and keeps the turn when the server refuses', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: false, status: 500, text: async () => 'locked', json: async () => ({}) }),
    )
    const local = turn('local-1', TODAY, 'not stored yet', {
      user: { messageId: -1, content: 'not stored yet', timestamp: TODAY, status: 'complete' },
      assistant: { messageId: -1, content: 'ok', timestamp: TODAY, status: 'complete' },
    })
    render(
      <Timeline byDay={groupByDay([TURNS[0], local], NOW)} hasMore={false} loading={false} onLoadOlder={() => {}} />,
    )

    const buttons = screen.getAllByRole('button', { name: 'Forget this turn' })
    expect(buttons).toHaveLength(1)
    expect(buttons[0].closest('article')).toHaveAttribute('data-turn-id', 't-1')

    await userEvent.click(buttons[0])
    await waitFor(() => expect(warn).toHaveBeenCalled())
    expect(screen.getByText('is samba running?')).toBeInTheDocument()
    expect(screen.queryByText('[redacted by admin]')).not.toBeInTheDocument()
  })
})
```

- [ ] **Step 3: Run both, watch them fail**

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core/halbert_core/dashboard/frontend && npx vitest run src/lib/api.timeline.test.ts src/components/agent/Timeline.test.tsx
```
Expected: `TypeError: api.redactMessage is not a function`; and twice `Unable to find an accessible element with the role "button" and name "Forget this turn"`.

- [ ] **Step 4: Add `api.redactMessage`**

In `src/lib/api.ts`, immediately after the `retractRecall` method (the `},` that follows `{ method: 'DELETE' },` / `)`), insert:

```ts
  /**
   * "Forget this": the server replaces the row's content and tool blocks
   * with "[redacted by admin]", rewrites its FTS row and regenerates the
   * thread's receipt (spec §5). Rows are never deleted.
   */
  redactMessage(messageId: number): Promise<{ ok: boolean }> {
    return request(`/api/agent/message/${encodeURIComponent(String(messageId))}/redact`, { method: 'POST' })
  },
```

- [ ] **Step 5: Edit `src/components/agent/Timeline.tsx`**

Replace the first import line

```tsx
import { useTerminalSessions } from '../../hooks/useTerminalSessions';
```

with

```tsx
import { useCallback, useState } from 'react';
import { useTerminalSessions } from '../../hooks/useTerminalSessions';
```

After `import type { TimelineToolBlock, TimelineTurn } from '../../types/timeline';` add:

```tsx
import { api } from '../../lib/api';
```

Then replace everything from `interface TurnArticleProps {` to the end of the file with:

```tsx
/** What a forgotten row reads as — the same marker the server stores. */
export const REDACTED = '[redacted by admin]';

/** Stored rows have server ids; a turn appended live carries -1 until the next load. */
export function redactableIds(turn: TimelineTurn): number[] {
  return [turn.user?.messageId, turn.assistant?.messageId].filter(
    (id): id is number => typeof id === 'number' && id >= 0,
  );
}

interface TurnArticleProps {
  turn: TimelineTurn;
  liveIds: Set<string>;
  /** True once "Forget this" went through: the words and the blocks are the marker. */
  forgotten: boolean;
  onForget?: (turn: TimelineTurn) => void;
  onRunCommand?: RunCommand;
}

function TurnArticle({ turn, liveIds, forgotten, onForget, onRunCommand }: TurnArticleProps) {
  const liveTerminals = turn.terminalBlockIds.filter((id) => liveIds.has(id));
  const endedTerminals = turn.terminalBlockIds.filter((id) => !liveIds.has(id));
  // Redaction replaces content and blocks_json (spec §5); the terminal ids
  // are not part of it, so the "ended" chips stay.
  const blocks = forgotten ? [] : turn.blocks;
  const diffs = forgotten ? [] : turn.diffProposals;
  const hasAssistantSide =
    turn.assistant !== null ||
    blocks.length > 0 ||
    turn.terminalBlockIds.length > 0 ||
    diffs.length > 0;
  const label = forgotten ? REDACTED : turn.user ? turn.user.content.slice(0, 80) : turn.origin;
  const canForget = !forgotten && onForget !== undefined && redactableIds(turn).length > 0;

  return (
    <article
      role="article"
      aria-label={label}
      data-turn-id={turn.turnId}
      data-thread-id={turn.threadId}
      className="space-y-3"
    >
      {turn.user && (
        <div className="flex justify-end">
          <div className="max-w-[80%] bg-primary text-primary-foreground px-4 py-2 rounded-lg">
            <p className="text-sm whitespace-pre-wrap break-words">{forgotten ? REDACTED : turn.user.content}</p>
          </div>
        </div>
      )}

      {turn.user?.status === 'interrupted' && (
        <p className="text-center text-[11px] font-mono text-ink-tertiary">(Halbert restarted here)</p>
      )}

      {hasAssistantSide && (
        <div className="flex justify-start">
          <div className="max-w-[85%] bg-muted/50 border border-border/50 rounded-lg p-4 space-y-3">
            {blocks.map((block, i) => (
              <ToolExecutionCard
                key={block.executionId ?? `${turn.turnId}-block-${i}`}
                execution={executionFromBlock(block, `${turn.turnId}-block-${i}`)}
              />
            ))}

            {liveTerminals.length > 0 && <InlineTerminals sessionIds={liveTerminals} />}

            {endedTerminals.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {endedTerminals.map((id) => (
                  <StaticTerminalChip key={id} id={id} />
                ))}
              </div>
            )}

            {diffs.map((diff) => (
              <DiffBlock
                key={diff.id}
                filePath={diff.filePath}
                oldContent={diff.oldContent}
                newContent={diff.newContent}
                additions={diff.additions}
                deletions={diff.deletions}
                status={diff.status}
                readOnly
                onApply={() => {}}
                onReject={() => {}}
              />
            ))}

            {turn.assistant && (
              <div className="text-sm text-foreground">
                {forgotten ? (
                  <p className="font-mono text-ink-tertiary">{REDACTED}</p>
                ) : (
                  <MessageContent content={turn.assistant.content} onRunCommand={onRunCommand} />
                )}
              </div>
            )}

            {turn.assistant?.status === 'cancelled' && (
              <p className="text-[11px] font-mono text-ink-tertiary">cancelled</p>
            )}
          </div>
        </div>
      )}

      {canForget && (
        <div className="flex justify-end">
          <button
            type="button"
            aria-label="Forget this turn"
            title="Replace this turn's words and tool output with a redaction marker, everywhere it is stored"
            onClick={() => onForget?.(turn)}
            className="rounded px-1 text-[11px] font-mono text-ink-tertiary hover:text-ink-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
          >
            Forget this
          </button>
        </div>
      )}
    </article>
  );
}

export function Timeline({
  byDay,
  hasMore,
  loading,
  anchored = false,
  onLoadOlder,
  onLoadLatest,
  onRunCommand,
}: TimelineProps) {
  const { sessions } = useTerminalSessions();
  const liveIds = new Set(sessions.map((s) => s.id));
  const [forgotten, setForgotten] = useState<ReadonlySet<string>>(() => new Set());

  // "Forget this": both stored rows are redacted server-side first; the
  // article shows the marker once the server has agreed, never before, so
  // the page never claims something is forgotten that is still on disk.
  const handleForget = useCallback(async (turn: TimelineTurn) => {
    try {
      await Promise.all(redactableIds(turn).map((id) => api.redactMessage(id)));
      setForgotten((prev) => new Set(prev).add(turn.turnId));
    } catch (err) {
      console.warn('[TIMELINE] forget failed; the turn is unchanged:', err);
    }
  }, []);

  if (byDay.length === 0 && !hasMore) return null;

  return (
    <div role="feed" aria-label="Conversation" aria-busy={loading} className="space-y-2">
      {hasMore && (
        <div className="flex justify-center">
          <button
            type="button"
            onClick={onLoadOlder}
            disabled={loading}
            className="rounded-full border border-hairline bg-canvas-subtle px-3 py-1 text-[11px] font-mono text-ink-secondary hover:bg-canvas-muted disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
          >
            {loading ? 'Loading…' : 'Load earlier'}
          </button>
        </div>
      )}

      {byDay.map((day) => (
        <section key={day.dayKey} aria-label={day.label} className="space-y-4">
          <header className="thread-divider flex items-center gap-3 pt-2">
            <span className="h-px flex-1 bg-hairline" aria-hidden="true" />
            <h2 className="text-[11px] font-mono uppercase tracking-label text-ink-tertiary">{day.label}</h2>
            <time dateTime={day.dayKey} className="sr-only">{day.dayKey}</time>
            <span className="h-px flex-1 bg-hairline" aria-hidden="true" />
          </header>
          {day.turns.map((turn) => (
            <TurnArticle
              key={turn.turnId}
              turn={turn}
              liveIds={liveIds}
              forgotten={forgotten.has(turn.turnId)}
              onForget={handleForget}
              onRunCommand={onRunCommand}
            />
          ))}
        </section>
      ))}

      {/* A chip jump replaced the page with an earlier window; the turns
          between that window and now are not on screen, so say so and offer
          the way back rather than letting the live turn append after a gap. */}
      {anchored && onLoadLatest && (
        <div className="flex justify-center pt-2">
          <button
            type="button"
            onClick={onLoadLatest}
            disabled={loading}
            className="rounded-full border border-hairline bg-canvas-subtle px-3 py-1 text-[11px] font-mono text-ink-secondary hover:bg-canvas-muted disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
          >
            Back to latest
          </button>
        </div>
      )}
    </div>
  );
}

export default Timeline;
```

- [ ] **Step 6: Run the tests, the ratchet and the typecheck**

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core/halbert_core/dashboard/frontend && npx vitest run src/lib/api.timeline.test.ts src/components/agent/Timeline.test.tsx
```
Expected: `Test Files  2 passed (2)`, `Tests  14 passed (14)` (6 + 8).

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation && python3 scripts/check_literal_colors.py --check
```
Expected: `OK: …` (only token classes were added).

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core/halbert_core/dashboard/frontend && npx tsc --noEmit -p .
```
Expected: no output, exit 0.

- [ ] **Step 7: Commit**

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation && git add halbert_core/halbert_core/dashboard/frontend/src/lib/api.ts halbert_core/halbert_core/dashboard/frontend/src/lib/api.timeline.test.ts halbert_core/halbert_core/dashboard/frontend/src/components/agent/Timeline.tsx halbert_core/halbert_core/dashboard/frontend/src/components/agent/Timeline.test.tsx && git commit -m "feat(dashboard): per-turn 'Forget this' on the timeline

Each stored turn offers one small control that POSTs the redact route
for its user and assistant rows; once the server has agreed, the words
and the tool cards read '[redacted by admin]' and the article keeps its
place (rows are never deleted, spec §5). A turn appended live in this
page load has no server ids yet and gets no control."
```

### Task A18: Rewire `AgentChat` onto the timeline (thread chip click jumps the timeline; legacy wrappers deleted)

**Files:**
- Create: `halbert_core/halbert_core/dashboard/frontend/src/lib/turnFromSession.ts`
- Modify: `halbert_core/halbert_core/dashboard/frontend/src/components/agent/AgentChat.tsx` (deletions, line numbers from the worktree before this part; the text anchors are authoritative: 17-49 imports; 71-77; 132-184; 187 and 192; 211-215; 269; 272-338; 566-570; 574-640; 642-652; 654-781; 885-903)
- Modify: `halbert_core/halbert_core/dashboard/frontend/src/lib/api.ts` (delete `listAgentConversations` / `getAgentConversation` / `deleteAgentConversation` — their last callers go in this task, so this is the commit where `tsc` allows it)
- Test: `halbert_core/halbert_core/dashboard/frontend/src/lib/turnFromSession.test.ts`
- Test: `halbert_core/halbert_core/dashboard/frontend/src/components/agent/AgentChat.test.tsx`
- Test: `halbert_core/halbert_core/dashboard/frontend/src/lib/api.timeline.test.ts` (the "removed wrappers" describe appended)

- [ ] **Step 1: Write the failing `turnFromSession` test**

`src/lib/turnFromSession.test.ts`:

```ts
// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * The live block becomes a stored turn without a refetch: everything the
 * hook accumulated during the turn is folded into one TimelineTurn.
 */

import { describe, it, expect } from 'vitest'
import { turnFromSession } from './turnFromSession'
import type { AgentSession } from '../hooks/useAgentStream'

function session(extra: Partial<AgentSession> = {}): AgentSession {
  return {
    sessionId: 'sess-1',
    state: 'idle',
    plan: [],
    currentStep: 0,
    loopCount: 0,
    confidence: 0,
    cragAction: 'PENDING',
    toolExecutions: [
      { executionId: 'x1', tool: 'run_command', args: { command: 'ls' }, status: 'success', result: 'a b' },
      { executionId: 'x2', tool: 'run_command', args: { command: 'false' }, status: 'error', error: 'exit 1' },
      { executionId: 'x3', tool: 'read_file', args: { path: '/etc/hosts' }, status: 'running' },
    ],
    pendingConfirmation: null,
    error: null,
    activeScan: null,
    contextItems: [],
    diffProposals: [{ id: 'd1', filePath: '/etc/x', newContent: 'n', additions: 1, deletions: 0, status: 'pending' }],
    terminalSessions: ['term-1'],
    thread: { threadId: 'th-1', title: 'Samba share setup' },
    recalled: null,
    turnId: 't-42',
    ...extra,
  }
}

const USER = { id: 'user-1', content: 'list the dir', timestamp: 1_784_000_000_000 }

describe('turnFromSession', () => {
  it('folds the session into a complete turn keyed by the persisted turn id', () => {
    const turn = turnFromSession(session(), USER, 'Here you go.')
    expect(turn.turnId).toBe('t-42')
    expect(turn.threadId).toBe('th-1')
    expect(turn.timestamp).toBe(USER.timestamp)
    expect(turn.origin).toBe('human')
    expect(turn.user).toEqual({ messageId: -1, content: 'list the dir', timestamp: USER.timestamp, status: 'complete' })
    expect(turn.assistant?.content).toBe('Here you go.')
    expect(turn.assistant?.status).toBe('complete')
    expect(turn.blocks).toEqual([
      { tool: 'run_command', args: { command: 'ls' }, result: 'a b', exit: 0, executionId: 'x1' },
      { tool: 'run_command', args: { command: 'false' }, result: undefined, exit: 1, executionId: 'x2' },
      { tool: 'read_file', args: { path: '/etc/hosts' }, result: undefined, exit: null, executionId: 'x3' },
    ])
    expect(turn.terminalBlockIds).toEqual(['term-1'])
    expect(turn.diffProposals[0].id).toBe('d1')
  })

  it('falls back to a local id when the store never confirmed the turn', () => {
    const turn = turnFromSession(session({ turnId: null, thread: null }), USER, 'ok')
    expect(turn.turnId).toBe('local-sess-1')
    expect(turn.threadId).toBe('')
  })

  it('marks interrupted and cancelled turns, and omits an empty reply', () => {
    const errored = turnFromSession(session({ error: 'Connection error' }), USER, '')
    expect(errored.user?.status).toBe('interrupted')
    expect(errored.assistant).toBeNull()

    const cancelled = turnFromSession(session(), USER, 'partial', { cancelled: true })
    expect(cancelled.user?.status).toBe('cancelled')
    expect(cancelled.assistant?.status).toBe('cancelled')
  })
})
```

- [ ] **Step 2: Write the failing AgentChat test**

`src/components/agent/AgentChat.test.tsx`:

```tsx
// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * One conversation: AgentChat mounts the stored timeline and the current
 * topic label, and the dropdown / "New Conversation" / "Session:" footer
 * are gone. The greeting shows only when there is nothing to show. The
 * thread chip is a real control: its title says why it is here and a click
 * loads the timeline around the recalled thread's last turn.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { AgentChat } from './AgentChat'

vi.mock('./TerminalTile', () => ({
  TerminalTile: ({ session }: { session: { id: string } }) => <div data-testid="live-tile">{session.id}</div>,
}))

/** One SSE body: every event as a `data:` line, delivered in one chunk. */
function sseBody(events: Array<Record<string, unknown>>) {
  const text = events.map((e) => `data: ${JSON.stringify(e)}\n`).join('')
  const chunks = [new TextEncoder().encode(text)]
  return {
    getReader: () => ({
      read: async () => {
        const value = chunks.shift()
        return value ? { done: false, value } : { done: true, value: undefined }
      },
    }),
  }
}

const PAGE = {
  has_more: false,
  current_thread: { thread_id: 'th-1', title: 'Samba share setup', status: 'open' },
  turns: [
    {
      turn_id: 't-1',
      thread_id: 'th-1',
      timestamp: 1_784_000_000,
      origin: 'human',
      user: { message_id: 1, content: 'is samba running?', timestamp: 1_784_000_000, status: 'complete' },
      assistant: { message_id: 2, content: 'smbd is active.', timestamp: 1_784_000_003, status: 'complete' },
      blocks: [],
      terminal_block_ids: [],
      diff_proposals: [],
    },
  ],
}

const EMPTY = { has_more: false, current_thread: null, turns: [] }

function routeFetch(timeline: unknown, events: Array<Record<string, unknown>> = []) {
  const fetchMock = vi.fn().mockImplementation((url: string) => {
    const path = String(url)
    if (path.includes('/api/agent/message')) {
      return Promise.resolve({ ok: true, status: 200, statusText: 'OK', body: sseBody(events) })
    }
    if (path.includes('/api/agent/timeline')) {
      return Promise.resolve({ ok: true, status: 200, text: async () => '', json: async () => timeline })
    }
    if (path.includes('/api/discoveries/mentionables')) {
      return Promise.resolve({ ok: true, status: 200, text: async () => '', json: async () => ({ mentionables: [] }) })
    }
    // Identity (HostGreeting) and anything else: the backend is "starting".
    return Promise.resolve({ ok: false, status: 503, text: async () => '', json: async () => ({}) })
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe('AgentChat', () => {
  beforeEach(() => {
    // jsdom has no layout; the auto-scroll effect must not throw.
    Element.prototype.scrollIntoView = vi.fn() as unknown as typeof Element.prototype.scrollIntoView
    vi.spyOn(console, 'error').mockImplementation(() => {})
  })

  afterEach(() => vi.unstubAllGlobals())

  it('renders the stored conversation with the current topic pinned', async () => {
    routeFetch(PAGE)
    render(<AgentChat />)

    await screen.findByRole('feed')
    expect(screen.getByText('is samba running?')).toBeInTheDocument()
    expect(screen.getByText('smbd is active.')).toBeInTheDocument()
    expect(screen.getByTestId('current-topic')).toHaveTextContent('Samba share setup')

    // The greeting is the empty state only.
    expect(screen.queryByText(/Reading my own vitals|cannot read my own vitals/)).not.toBeInTheDocument()
  })

  it('has no conversation dropdown, no New Conversation, no session footer', async () => {
    routeFetch(PAGE)
    render(<AgentChat />)
    await screen.findByRole('feed')

    expect(screen.queryByText('New Conversation')).not.toBeInTheDocument()
    expect(screen.queryByTitle('New conversation')).not.toBeInTheDocument()
    expect(screen.queryByText(/^Session:/)).not.toBeInTheDocument()
  })

  it('greets when the timeline is empty and nothing is in flight', async () => {
    routeFetch(EMPTY)
    render(<AgentChat />)

    await waitFor(() =>
      expect(screen.getByText(/Reading my own vitals|cannot read my own vitals/)).toBeInTheDocument(),
    )
    expect(screen.queryByRole('feed')).not.toBeInTheDocument()
    expect(screen.queryByTestId('current-topic')).not.toBeInTheDocument()
  })

  it('the thread chip shows its match terms and a click loads the timeline around the recalled turn', async () => {
    const fetchMock = routeFetch(PAGE, [
      {
        type: 'thread_recalled',
        session_id: 's',
        timestamp: 0,
        thread_id: 'th-0',
        title: 'ZFS scrub',
        date: '2026-07-14',
        match_terms: ['zfs'],
        mode: 'auto',
        last_turn_id: 't-7',
      },
      { type: 'response_complete', session_id: 's', timestamp: 0, content: 'It did.' },
    ])
    render(<AgentChat />)
    await screen.findByRole('feed')

    await userEvent.type(screen.getByPlaceholderText(/^Ask Halbert/), 'did that scrub work?{Enter}')

    const chip = await screen.findByRole('button', { name: 'earlier subject: pulled in: ZFS scrub · 2026-07-14' })
    expect(chip).toHaveAttribute('title', 'matched: zfs')

    await userEvent.click(chip)

    await waitFor(() =>
      expect(fetchMock.mock.calls.map(([url]) => String(url))).toContain('/api/agent/timeline?around=t-7&limit=50'),
    )
  })
})
```

- [ ] **Step 2b: Write the failing "removed wrappers" test**

Append to `src/lib/api.timeline.test.ts`:

```ts
describe('removed wrappers', () => {
  it('no longer exposes the per-conversation list endpoints', () => {
    const legacy = api as unknown as Record<string, unknown>
    expect(legacy.listAgentConversations).toBeUndefined()
    expect(legacy.getAgentConversation).toBeUndefined()
    expect(legacy.deleteAgentConversation).toBeUndefined()
  })
})
```

- [ ] **Step 3: Run all three, watch them fail**

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core/halbert_core/dashboard/frontend && npx vitest run src/lib/turnFromSession.test.ts src/components/agent/AgentChat.test.tsx src/lib/api.timeline.test.ts
```
Expected: `Failed to resolve import "./turnFromSession"`; AgentChat test: `Unable to find role="feed"` (and console errors from `api.listAgentConversations is not a function`); api.timeline: one failure, `expected [Function] to be undefined`.

- [ ] **Step 4: Create `src/lib/turnFromSession.ts`**

```ts
// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * turnFromSession — fold the finished live turn into a TimelineTurn.
 *
 * The server stored this turn as it happened (turn_persisted carries the
 * id); the page already watched it happen, so it appends the same turn
 * locally rather than refetching. On the next load the server's copy wins
 * by id. When the store never confirmed the turn (thread_store_error), a
 * local id keeps the transcript continuous for this page load only.
 */

import type { AgentSession, ToolExecution } from '../hooks/useAgentStream';
import type { TimelineMessageStatus, TimelineToolBlock, TimelineTurn } from '../types/timeline';

export interface LiveUserMessage {
  id: string;
  content: string;
  /** Epoch milliseconds. */
  timestamp: number;
}

function exitOf(execution: ToolExecution): number | null {
  if (execution.status === 'success') return 0;
  if (execution.status === 'error') return 1;
  return null;
}

function blockFromExecution(execution: ToolExecution): TimelineToolBlock {
  return {
    tool: execution.tool,
    args: execution.args,
    result: execution.result,
    exit: exitOf(execution),
    executionId: execution.executionId,
  };
}

export function turnFromSession(
  session: AgentSession,
  userMessage: LiveUserMessage,
  response: string,
  opts: { cancelled?: boolean } = {},
): TimelineTurn {
  const status: TimelineMessageStatus = opts.cancelled
    ? 'cancelled'
    : session.error
      ? 'interrupted'
      : 'complete';
  const now = Date.now();
  return {
    turnId: session.turnId ?? `local-${session.sessionId}`,
    threadId: session.thread?.threadId ?? '',
    timestamp: userMessage.timestamp,
    origin: 'human',
    user: { messageId: -1, content: userMessage.content, timestamp: userMessage.timestamp, status },
    assistant: response
      ? { messageId: -1, content: response, timestamp: now, status }
      : null,
    blocks: session.toolExecutions.map(blockFromExecution),
    terminalBlockIds: session.terminalSessions ?? [],
    diffProposals: session.diffProposals,
  };
}

export default turnFromSession;
```

- [ ] **Step 5: Edit `AgentChat.tsx` — imports and local types**

Replace lines 17-49 (the import block) with:

```tsx
import { useState, useRef, useEffect, useCallback } from 'react';
import { 
  Send, 
  StopCircle, 
  RotateCcw, 
  AtSign, 
  Terminal,
  Image as ImageIcon,
  X as XIcon,
  Camera,
} from 'lucide-react';
import { useAgentStream } from '../../hooks/useAgentStream';
import { useTimeline } from '../../hooks/useTimeline';
import { StateBadge } from './StateBadge';
import { PlanChecklist } from './PlanChecklist';
import { ToolExecutionCard } from './ToolExecutionCard';
import { ConfirmationDialog } from './ConfirmationDialog';
import { ThinkingPanel } from './ThinkingPanel';
import { WhyChip, type ProvenanceRef } from '../WhyChip';
import { ModuleRenderer } from '../ModuleRenderer';
import { ConfidenceIndicator } from './ConfidenceIndicator';
import { ScanBlock } from './ScanBlock';
import { ContextBar, type ContextItem, type ContextType } from './ContextBar';
import { DiffBlock } from './DiffBlock';
import { HostGreeting } from './HostGreeting';
import { InlineTerminals } from './InlineTerminals';
import { MessageContent } from './MessageContent';
import { Timeline } from './Timeline';
import { CurrentTopicLabel } from './CurrentTopicLabel';
import { cn } from '../../lib/utils';
import { api } from '../../lib/api';
import { subscribeHost } from '../../lib/hostConversation';
import { announce } from '../../lib/announce';
import { turnFromSession } from '../../lib/turnFromSession';
```

Delete lines 71-77 (`interface AgentConversation { … }`).

Delete lines 132-184 (the local `MessageContent` function and its `// Helper to render message content with code blocks` comment) — it now lives in `./MessageContent`.

Immediately before `export function AgentChat(` add:

```tsx
/** Where a context_loaded item came from -> which chip to draw. */
function contextTypeFor(source: string): ContextType {
  switch (source) {
    case 'file': return 'file';
    case 'memory': return 'memory';
    case 'thread': return 'thread';
    default: return 'search';
  }
}
```

- [ ] **Step 6: Edit `AgentChat.tsx` — state**

Replace line 187 `const [userMessages, setUserMessages] = useState<UserMessage[]>([]);` with:

```tsx
  // The turn in flight. Once it finishes it is appended to the timeline
  // (turnFromSession) and this goes back to null — never both at once.
  const [liveUser, setLiveUser] = useState<UserMessage | null>(null);
  const cancelledRef = useRef(false);
  const appendedRef = useRef<string | null>(null);
```

Delete line 192 (`const conversationDropdownRef = useRef<HTMLDivElement>(null);`).

Replace lines 211-215 (the `// Phase 59: Conversation management` block with its four `useState`s) with:

```tsx
  // One conversation, stored server-side; paged here.
  const {
    turns,
    hasMore,
    loading: timelineLoading,
    loadOlder,
    loadAround,
    loadLatest,
    anchored,
    appendLive,
    currentThread,
    setCurrentThread,
    byDay,
  } = useTimeline();
```

In the `useAgentStream` destructure (lines 232-245) add `dismissContextItem,` after `reset,`.

- [ ] **Step 7: Edit `AgentChat.tsx` — effects and handlers**

In the mount effect (lines 258-270) delete line 269 `loadConversations();`.

Delete lines 272-338 (`loadConversations`, `loadConversation`, `startNewConversation`, `deleteConversation`, and the click-outside effect) and put in their place:

```tsx
  // The finished turn becomes a stored turn. Guarded so a turn parked on a
  // confirmation prompt (stream closed, session waiting) is not appended
  // early, and so one turn is appended once.
  useEffect(() => {
    if (isStreaming || !liveUser || !session) return;
    if (session.pendingConfirmation || session.state === 'awaiting_confirmation') return;
    const turn = turnFromSession(session, liveUser, response, { cancelled: cancelledRef.current });
    if (appendedRef.current === turn.turnId) return;
    appendedRef.current = turn.turnId;
    appendLive(turn);
    setLiveUser(null);
    cancelledRef.current = false;
  }, [isStreaming, liveUser, session, response, appendLive]);

  // Thread identity is the server's; the label and the live region follow.
  useEffect(() => {
    const thread = session?.thread;
    if (!thread) return;
    if (currentThread && currentThread.threadId !== thread.threadId) {
      announce('New subject');
    }
    if (!currentThread || currentThread.threadId !== thread.threadId || currentThread.title !== thread.title) {
      setCurrentThread({ threadId: thread.threadId, title: thread.title, status: 'open' });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session?.thread]);

  useEffect(() => {
    const recalled = session?.recalled;
    if (!recalled) return;
    announce(`Pulled in earlier work: ${recalled.title}`);
  }, [session?.recalled]);

  // Dropping the thread chip retracts the recall server-side too, so the
  // next turn's hint does not pull it straight back in.
  const handleRemoveContextItem = useCallback((id: string) => {
    if (id.startsWith('thread:') && currentThread) {
      api.retractRecall(currentThread.threadId, id.slice('thread:'.length)).catch((err) => {
        console.warn('retract recall failed:', err);
      });
    }
    dismissContextItem(id);
  }, [currentThread, dismissContextItem]);

  // The thread chip is a real control (spec §6): a click scrolls the
  // timeline to where that subject last happened — the page around its last
  // turn. Other chips have nowhere to go yet.
  const handleContextItemClick = useCallback((item: ContextItem) => {
    if (item.type !== 'thread') return;
    const lastTurnId = session?.recalled?.lastTurnId;
    if (lastTurnId) void loadAround(lastTurnId);
  }, [session?.recalled, loadAround]);
```

Replace the scroll effect (was lines 340-342):

```tsx
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [turns.length, liveUser, response, session?.toolExecutions]);
```

In the queue effect (was lines 345-362) replace `setUserMessages(prev => [...prev, userMsg]);` with `setLiveUser(userMsg);`.

In `handleSend` (was lines 509-540) replace `setUserMessages(prev => [...prev, userMsg]);` with `setLiveUser(userMsg);`.

Replace `handleReset` (was lines 566-570) with:

```tsx
  // Retry after an error clears the live state only; stored turns stay.
  const handleReset = () => {
    reset();
    setAgentError(null);
    setExpandedProvenanceModules([]);
    setLiveUser(null);
  };
```

- [ ] **Step 8: Edit `AgentChat.tsx` — JSX**

Replace everything from `{/* Conversation Header */}` (was line 574) through the `<div ref={messagesEndRef} />` container's closing `</div>` (was line 781) with:

```tsx
      <CurrentTopicLabel thread={currentThread} />

      {session?.contextItems && session.contextItems.length > 0 && (
        <ContextBar
          items={session.contextItems.map(ci => ({
            id: ci.id,
            type: contextTypeFor(ci.source),
            label: ci.label,
            tokens: ci.tokens,
            // The thread chip's "why now": the terms that matched (spec §6).
            hint:
              ci.source === 'thread' && session.recalled && session.recalled.matchTerms.length > 0
                ? `matched: ${session.recalled.matchTerms.join(', ')}`
                : undefined,
          }))}
          onRemoveItem={handleRemoveContextItem}
          onItemClick={handleContextItemClick}
        />
      )}

      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
        {/* Empty state: the host introduces itself — only when there is
            nothing stored and nothing in flight. */}
        {turns.length === 0 && !liveUser && !timelineLoading && <HostGreeting onPrompt={setInput} />}

        {/* Every turn that has finished, oldest first, grouped by day. */}
        <Timeline
          byDay={byDay}
          hasMore={hasMore}
          loading={timelineLoading}
          anchored={anchored}
          onLoadOlder={loadOlder}
          onLoadLatest={loadLatest}
          onRunCommand={onRunCommand}
        />

        {/* The turn in flight: the live assistant block, exactly as before. */}
        {liveUser && (
          <div className="space-y-3" data-live-turn={session?.turnId ?? liveUser.id}>
            <div className="flex justify-end">
              <div className="max-w-[80%] bg-primary text-primary-foreground px-4 py-2 rounded-lg">
                <p className="text-sm whitespace-pre-wrap break-words">{liveUser.content}</p>
              </div>
            </div>

            {session && (
              <div className="flex justify-start">
                <div className="max-w-[85%] bg-muted/50 border border-border/50 rounded-lg p-4 space-y-3">
                  <div className="flex items-center gap-2">
                    <StateBadge state={session.state} showPulse={isStreaming} />
                    {session.loopCount > 0 && (
                      <span className="text-xs text-muted-foreground">Loop {session.loopCount}</span>
                    )}
                  </div>

                  {session.plan.length > 0 && (
                    <PlanChecklist plan={session.plan} currentStep={session.currentStep} />
                  )}

                  {/* Active Scan Visualization */}
                  {session.activeScan && (
                    <ScanBlock
                      source={session.activeScan.source}
                      query={session.activeScan.query}
                      fileCount={session.activeScan.fileCount}
                      isComplete={session.activeScan.isComplete}
                      resultsCount={session.activeScan.results}
                    />
                  )}

                  {session.toolExecutions.map((exec) => (
                    <ToolExecutionCard key={exec.executionId} execution={exec} />
                  ))}

                  {/* Terminals Halbert opened for this turn, flowing in the
                      conversation; they dock to the right column on scroll. */}
                  <InlineTerminals sessionIds={session.terminalSessions ?? []} />

                  {/* Diff Proposals */}
                  {session.diffProposals.map((diff) => (
                    <DiffBlock
                      key={diff.id}
                      filePath={diff.filePath}
                      oldContent={diff.oldContent}
                      newContent={diff.newContent}
                      additions={diff.additions}
                      deletions={diff.deletions}
                      status={diff.status}
                      onApply={() => applyDiff(diff.id)}
                      onReject={() => rejectDiff(diff.id)}
                    />
                  ))}

                  {thinking && <ThinkingPanel thinking={thinking} isStreaming={isStreaming} />}

                  {session.confidence > 0 && (
                    <ConfidenceIndicator
                      confidence={session.confidence}
                      cragAction={session.cragAction}
                      size="sm"
                    />
                  )}

                  {response && (
                    <div className="text-sm text-foreground">
                      <MessageContent content={response} onRunCommand={onRunCommand} />
                      {isStreaming && <span className="inline-block w-2 h-4 bg-muted animate-pulse motion-reduce:animate-none ml-0.5" />}
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Phase 8 extras for the turn that just finished: provenance chips,
            module invocations, and sources expanded from a chip. They belong
            to the last reply and clear on the next send. */}
        {!liveUser && !isStreaming && (provenance.length > 0 || moduleInvocations.length > 0 || expandedProvenanceModules.length > 0) && (
          <div className="flex justify-start">
            <div className="max-w-[85%] space-y-3">
              {provenance.length > 0 && (
                <WhyChip provenance={provenance} onExpand={handleProvenanceExpand} />
              )}
              {moduleInvocations.length > 0 && (
                <div className="space-y-3">
                  {moduleInvocations.map((inv, i) => (
                    <ModuleRenderer key={i} module={inv.module} props={inv.props} />
                  ))}
                </div>
              )}
              {expandedProvenanceModules.length > 0 && (
                <div className="space-y-3">
                  {expandedProvenanceModules.map((m) => (
                    <div key={m.key} className="relative">
                      <button
                        type="button"
                        aria-label="Close expanded source"
                        onClick={() => dismissExpandedModule(m.key)}
                        className="absolute right-2 top-2 z-10 p-1 rounded bg-muted/80 hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
                      >
                        <XIcon className="h-3 w-3" aria-hidden="true" />
                      </button>
                      <ModuleRenderer module={m.module} props={m.props} />
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {agentError && !isStreaming && (
          <div className="flex justify-center">
            <div className="bg-error/10 border border-error/30 rounded-lg px-4 py-2 flex items-center gap-2">
              <span className="text-sm text-error">{agentError}</span>
              <button type="button" aria-label="Retry" onClick={handleReset} className="p-1 hover:bg-error/20 rounded">
                <RotateCcw className="h-4 w-4 text-error" aria-hidden="true" />
              </button>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>
```

Replace the cancel button (was lines 885-888):

```tsx
          {isStreaming ? (
            <button
              type="button"
              aria-label="Stop"
              onClick={() => { cancelledRef.current = true; cancel(); }}
              className="p-2 bg-error hover:bg-error rounded-lg transition-colors flex-shrink-0"
            >
              <StopCircle className="h-5 w-5 text-white" aria-hidden="true" />
            </button>
          ) : (
```

Replace the footer (was lines 900-903) with:

```tsx
        <div className="mt-2 text-xs text-muted-foreground">
          <span>{isStreaming ? 'Agent working... type to queue' : 'Press Enter to send'}</span>
        </div>
```

- [ ] **Step 8b: Delete the legacy wrappers from `src/lib/api.ts`**

Their last callers (`loadConversations`, `loadConversation`, `deleteConversation`) were deleted in Step 7, so this commit is the first in which `tsc` allows it. Delete the block that starts with the three-line comment

```ts
  // -----------------------------------------------------------------
  // Agent conversations (Phase 36 agent path)
  // -----------------------------------------------------------------
```

through the closing `},` of `deleteAgentConversation` (the three methods `listAgentConversations`, `getAgentConversation`, `deleteAgentConversation`; nothing else). The timeline block inserted in A14 and `redactMessage` from A17b stay. Verify: `grep -c "AgentConversation" src/lib/api.ts` prints `0`; `grep -rn "AgentConversation" src --include=*.ts --include=*.tsx | grep -v api.timeline.test.ts` prints nothing.

- [ ] **Step 9: Typecheck, then run the whole frontend suite**

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core/halbert_core/dashboard/frontend && npx tsc --noEmit -p .
```
Expected: no output, exit 0. If tsc reports an unused import (`noUnusedLocals`), delete that import — the list above is exact for the JSX shown; `CodeBlock`, `Plus`, `ChevronDown`, `MessageSquare`, `Trash2` must all be gone.

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core/halbert_core/dashboard/frontend && npx vitest run
```
Expected: `Test Files  15 passed (15)`, `Tests  95 passed (95)` — at least 95: 45 baseline (7 files) + api.timeline 7 + useTimeline 10 + useAgentStream.thread 8 + ContextBar 5 + Timeline 8 + LiveRegion 5 + turnFromSession 3 + AgentChat 4. Read the printed total and record it in the commit body. A19 adds two files and six tests, bringing the suite to 17 files / 101 tests.

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation && python3 scripts/check_literal_colors.py --check
```
Expected: `OK: …` (AgentChat lost `placeholder-zinc-500`? No — untouched; count must not grow).

- [ ] **Step 10: Commit**

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation && git add halbert_core/halbert_core/dashboard/frontend/src/components/agent/AgentChat.tsx halbert_core/halbert_core/dashboard/frontend/src/components/agent/AgentChat.test.tsx halbert_core/halbert_core/dashboard/frontend/src/lib/turnFromSession.ts halbert_core/halbert_core/dashboard/frontend/src/lib/turnFromSession.test.ts halbert_core/halbert_core/dashboard/frontend/src/lib/api.ts halbert_core/halbert_core/dashboard/frontend/src/lib/api.timeline.test.ts && git commit -m "feat(dashboard): AgentChat is one conversation on the timeline

The dropdown, New Conversation, the per-conversation loaders and the
Session footer are deleted, and with their last callers gone so are the
listAgentConversations/getAgentConversation/deleteAgentConversation
wrappers. The stored timeline renders above the live block; when the
in-flight turn finishes it is folded into a TimelineTurn
(turnFromSession) and appended, so nothing is shown twice and nothing is
refetched. Thread events move the sticky label and speak through the
shell's live region; the thread chip shows its match terms and jumps
the timeline to the recalled thread's last turn; dropping it retracts
the recall."
```

### Task A19: `TerminalTile` replays on mount; `InlineTerminals` never drops an id

**Files:**
- Modify: `halbert_core/halbert_core/dashboard/frontend/src/components/agent/TerminalTile.tsx` (lines 98-102)
- Modify: `halbert_core/halbert_core/dashboard/frontend/src/components/agent/InlineTerminals.tsx` (lines 17-21 imports; 61-76)
- Test: `halbert_core/halbert_core/dashboard/frontend/src/components/agent/TerminalTile.test.tsx`
- Test: `halbert_core/halbert_core/dashboard/frontend/src/components/agent/InlineTerminals.test.tsx`

- [ ] **Step 1: Write the failing TerminalTile test**

`src/components/agent/TerminalTile.test.tsx`:

```tsx
// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * A tile mounted after its session started must show what already happened.
 *
 * Before: the xterm opened empty and the writer's cursor sat at 0, so the
 * first new chunk repainted the whole buffer and a tile that scrolled back
 * into view (or a reloaded page) showed nothing until the process spoke.
 */

import { render, waitFor, act } from '@testing-library/react'
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'

const { instances, FakeXTerm } = vi.hoisted(() => {
  class FakeXTerm {
    static instances: FakeXTerm[] = []
    cols = 80
    rows = 24
    writes: string[] = []
    disposed = false
    constructor(public options: Record<string, unknown>) {
      FakeXTerm.instances.push(this)
    }
    open() {}
    write(data: string) { this.writes.push(data) }
    reset() { this.writes.push('<reset>') }
    dispose() { this.disposed = true }
    loadAddon() {}
    onData() { return { dispose() {} } }
    attachCustomKeyEventHandler() {}
  }
  return { instances: FakeXTerm.instances, FakeXTerm }
})

vi.mock('@xterm/xterm', () => ({ Terminal: FakeXTerm }))
vi.mock('@xterm/addon-fit', () => ({ FitAddon: class { fit() {} } }))
vi.mock('@xterm/addon-web-links', () => ({ WebLinksAddon: class {} }))

import { TerminalTile } from './TerminalTile'
import { terminalSessionStore as store, useTerminalSessions } from '../../hooks/useTerminalSessions'

/** Renders the tile for a store session so store updates re-render it. */
function Tile({ id }: { id: string }) {
  const { sessions } = useTerminalSessions()
  const session = sessions.find((s) => s.id === id)
  return session ? <TerminalTile session={session} /> : null
}

describe('TerminalTile replay on mount', () => {
  beforeEach(() => {
    store.closeAll()
    instances.length = 0
    vi.stubGlobal('ResizeObserver', class {
      observe() {}
      unobserve() {}
      disconnect() {}
    })
  })

  afterEach(() => {
    store.closeAll()
    vi.unstubAllGlobals()
  })

  it('writes the output the store already holds when the xterm mounts', async () => {
    store.adopt('t1', { command: 'journalctl -f', pid: 3 })
    store.appendOutput('t1', 'old output')

    render(<Tile id="t1" />)

    await waitFor(() => expect(instances).toHaveLength(1))
    await waitFor(() => expect(instances[0].writes).toEqual(['old output']))
  })

  it('then writes only the delta, never the buffer twice', async () => {
    store.adopt('t1', { command: 'journalctl -f', pid: 3 })
    store.appendOutput('t1', 'old output')
    render(<Tile id="t1" />)
    await waitFor(() => expect(instances[0]?.writes).toEqual(['old output']))

    act(() => {
      store.appendOutput('t1', ' more')
    })

    await waitFor(() => expect(instances[0].writes).toEqual(['old output', ' more']))
  })

  it('mounts an empty session without writing anything', async () => {
    store.adopt('t2', { command: 'sleep 5', pid: 4 })
    render(<Tile id="t2" />)
    await waitFor(() => expect(instances).toHaveLength(1))
    expect(instances[0].writes).toEqual([])
  })
})
```

- [ ] **Step 2: Write the failing InlineTerminals test**

`src/components/agent/InlineTerminals.test.tsx`:

```tsx
// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * A terminal id the store does not know is still a fact about the turn:
 * a terminal ran here and ended. It renders as a static chip, never
 * disappears.
 */

import { render, screen } from '@testing-library/react'
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { InlineTerminals } from './InlineTerminals'
import { terminalSessionStore as store } from '../../hooks/useTerminalSessions'

vi.mock('./TerminalTile', () => ({
  TerminalTile: ({ session }: { session: { id: string } }) => <div data-testid="live-tile">{session.id}</div>,
}))

describe('InlineTerminals', () => {
  beforeEach(() => {
    store.closeAll()
    vi.stubGlobal('IntersectionObserver', class {
      observe() {}
      unobserve() {}
      disconnect() {}
    })
  })

  afterEach(() => {
    store.closeAll()
    vi.unstubAllGlobals()
  })

  it('renders a live tile for known ids and an ended chip for unknown ones, in order', () => {
    store.adopt('t-live', { command: 'htop', pid: 9 })

    const { container } = render(<InlineTerminals sessionIds={['t-gone', 't-live']} />)

    expect(screen.getByText('terminal · ended')).toBeInTheDocument()
    expect(screen.getByTestId('live-tile')).toHaveTextContent('t-live')
    const order = Array.from(container.querySelectorAll('[data-session-id], [data-terminal-origin]')).map(
      (el) => el.getAttribute('data-session-id') ?? el.getAttribute('data-terminal-origin'),
    )
    expect(order).toEqual(['t-gone', 't-live'])
  })

  it('renders chips even when the store knows none of the ids', () => {
    render(<InlineTerminals sessionIds={['a', 'b']} />)
    expect(screen.getAllByText('terminal · ended')).toHaveLength(2)
  })

  it('renders nothing for an empty list', () => {
    const { container } = render(<InlineTerminals sessionIds={[]} />)
    expect(container).toBeEmptyDOMElement()
  })
})
```

- [ ] **Step 3: Run both, watch them fail**

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core/halbert_core/dashboard/frontend && npx vitest run src/components/agent/TerminalTile.test.tsx src/components/agent/InlineTerminals.test.tsx
```
Expected: TerminalTile — `expected [] to deeply equal [ 'old output' ]` and `expected [ 'old output more' ] to deeply equal [ 'old output', ' more' ]`; InlineTerminals — `Unable to find an element with the text: terminal · ended` (twice; the empty-list test passes).

- [ ] **Step 4: Edit `TerminalTile.tsx` lines 98-102**

Replace:
```tsx
    t.open(containerRef.current!);
    fit.fit();
    term = t;
    termRef.current = t;
    fitRef.current = fit;
```
with:
```tsx
    t.open(containerRef.current!);
    fit.fit();
    // Replay what the store already holds. A tile mounted after its session
    // started — a reloaded page, a timeline turn scrolled back into view, an
    // undock — would otherwise open empty, and the incremental writer below
    // would then repaint the whole buffer on the next chunk.
    if (session.output) {
      t.write(session.output);
    }
    writtenRef.current = session.droppedChars + session.output.length;
    term = t;
    termRef.current = t;
    fitRef.current = fit;
```

- [ ] **Step 5: Edit `InlineTerminals.tsx`**

Replace lines 17-21:
```tsx
import { useState } from 'react';
import { useTerminalSessions, type TerminalSession } from '../../hooks/useTerminalSessions';
import { useIntersectionDock } from '../../hooks/useIntersectionDock';
import { TerminalTile } from './TerminalTile';
import { TetherChip } from './TetherChip';
import { StaticTerminalChip } from './StaticTerminalChip';
```

Replace lines 61-76 (`export function InlineTerminals … }`):
```tsx
export function InlineTerminals({ sessionIds }: InlineTerminalsProps) {
  const { sessions } = useTerminalSessions();
  if (sessionIds.length === 0) return null;

  const byId = new Map(sessions.map((s) => [s.id, s]));

  // An id the store does not know is a terminal that ended before this page
  // held it (reload, or a turn older than the store). It stays in the
  // transcript as a static chip; it is never dropped.
  return (
    <div className="space-y-2">
      {sessionIds.map((id) => {
        const session = byId.get(id);
        return session ? (
          <InlineTerminal key={id} session={session} />
        ) : (
          <StaticTerminalChip key={id} id={id} />
        );
      })}
    </div>
  );
}
```

- [ ] **Step 6: Run the tests, typecheck, then the whole suite**

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core/halbert_core/dashboard/frontend && npx vitest run src/components/agent/TerminalTile.test.tsx src/components/agent/InlineTerminals.test.tsx && npx tsc --noEmit -p .
```
Expected: `Tests  6 passed (6)`; tsc silent, exit 0.

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core/halbert_core/dashboard/frontend && npx vitest run
```
Expected: `Test Files  17 passed (17)`, `Tests  101 passed (101)` — at least 101 (the 95 of A18 step 9 plus these six).

- [ ] **Step 7: Commit**

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation && git add halbert_core/halbert_core/dashboard/frontend/src/components/agent/TerminalTile.tsx halbert_core/halbert_core/dashboard/frontend/src/components/agent/TerminalTile.test.tsx halbert_core/halbert_core/dashboard/frontend/src/components/agent/InlineTerminals.tsx halbert_core/halbert_core/dashboard/frontend/src/components/agent/InlineTerminals.test.tsx && git commit -m "fix(dashboard): terminal tiles replay on mount; ended terminals keep their chip

A tile mounted after its session started writes the store's buffer
first and sets the writer cursor past it, so a reload or an undock shows
the output instead of an empty screen. InlineTerminals renders a static
'terminal · ended' chip for ids the store no longer has rather than
silently dropping them from the turn."
```

### Task A20: Browser smoke for continuity (Playwright when present, checklist otherwise)

**Files:**
- Create: `halbert_core/halbert_core/dashboard/frontend/e2e/continuity.smoke.mjs`

`playwright` is not installed anywhere reachable (checked: frontend `node_modules`, repo root, global npm) and is not being added as a dependency. The script imports it dynamically; when the import fails it prints the manual checklist and exits 0. `vite.config.ts` `test.include` is `src/**/*.{test,spec}.{ts,tsx}` and `tsconfig.json` `include` is `["src"]`, so nothing under `e2e/` runs in `npm test` or is typechecked.

- [ ] **Step 1: Create `e2e/continuity.smoke.mjs`**

```js
#!/usr/bin/env node
// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * Continuity smoke — a browser walk through the continuous conversation
 * against a LIVE backend and dev server. Deliberately not part of `npm test`
 * (vitest only collects src/**) and never run in CI: it needs a model
 * answering on the other end.
 *
 * Run:
 *   # terminal 1: backend on :8000 (or HALBERT_API_PORT), then
 *   cd halbert_core/halbert_core/dashboard/frontend && npm run dev
 *   # terminal 2:
 *   node e2e/continuity.smoke.mjs                # http://localhost:5173
 *   HALBERT_UI_URL=http://localhost:4173 node e2e/continuity.smoke.mjs
 *
 * Needs the `playwright` package, which is NOT a project dependency:
 *   npm i --no-save playwright && npx playwright install chromium
 * Without it the script prints the manual checklist and exits 0.
 */

const BASE = process.argv[2] ?? process.env.HALBERT_UI_URL ?? 'http://localhost:5173'
const TURN_TIMEOUT_MS = Number(process.env.HALBERT_SMOKE_TURN_TIMEOUT_MS ?? 180_000)

const MESSAGE_1 = 'Please run `uname -a` and tell me the kernel version.'
const MESSAGE_2 = 'Unrelated: what is 2 + 2?'

const MANUAL_CHECKLIST = `
Manual continuity check (playwright not installed):

  1. Start the backend and \`npm run dev\`; open ${BASE} in a browser.
  2. There is no conversation dropdown, no "New Conversation" button and no
     "Session: …" line under the composer.
  3. Send: ${MESSAGE_1}
     - a live block appears under your bubble; when the command runs, a
       terminal tile (or an "in dock" chip) appears inside it;
     - when the reply finishes, the turn moves into the timeline under a
       "Today" divider (<h2>) and the sticky topic label shows a title.
  4. Send: ${MESSAGE_2}
     - the first turn is still on screen above the new one;
     - its terminal tile is still there (or a "terminal · ended" chip).
  5. Reload the page.
     - both turns are back, under a "Today" divider, in order;
     - the first turn shows a terminal tile or a "terminal · ended" chip;
     - the sticky topic label is back.
  6. Send: "did that kernel check work?"
     - a "pulled in: …" chip may appear in the context bar and the live
       region (VoiceOver/NVDA) says "Pulled in earlier work: …" — only when
       the earlier subject had already been paused. Not a failure if absent.
  7. Tab to a live tile, press Ctrl+\` — focus leaves the terminal.
  8. Click the "pulled in: …" chip (when one appeared): the timeline jumps
     to the recalled subject's last turn and a "Back to latest" control
     appears at the bottom; hovering the chip shows "matched: …".
  9. On any stored turn, "Forget this": both bubbles read
     "[redacted by admin]" and the turn keeps its place.
 10. Ask for something that needs confirmation (a HIGH-risk command): the
     screen reader says "Waiting for your approval" at once (the alert
     region), and the dialog opens.
`

function log(step, ok, detail = '') {
  const mark = ok ? 'PASS' : 'FAIL'
  console.log(`[${mark}] ${step}${detail ? ` — ${detail}` : ''}`)
  if (!ok) process.exitCode = 1
}

let chromium
try {
  ;({ chromium } = await import('playwright'))
} catch {
  console.log(MANUAL_CHECKLIST)
  process.exit(0)
}

const browser = await chromium.launch({ headless: true })
const context = await browser.newContext({ reducedMotion: 'reduce' })
await context.addInitScript(() => {
  // The engaged surface is the default, but pin it so a stored preference
  // on this machine cannot land the smoke on the dashboard.
  window.localStorage.setItem('halbert:shell-mode', 'engaged')
})
const page = await context.newPage()

const consoleErrors = []
page.on('console', (msg) => {
  if (msg.type() === 'error') consoleErrors.push(msg.text())
})

const composer = () => page.locator('textarea[placeholder^="Ask Halbert"], textarea[placeholder^="Type to queue"]').first()
const articles = () => page.locator('[role="feed"] article')
const tileOrChip = () => page.locator('[data-terminal-origin], [data-session-id]')

async function articleCount() {
  return (await page.locator('[role="feed"]').count()) === 0 ? 0 : articles().count()
}

async function sendAndWait(text, expectedArticles) {
  await composer().fill(text)
  await composer().press('Enter')
  // The turn is over when it has been folded into the timeline: the article
  // count reaches the expected value and the composer is idle again.
  await page.waitForFunction(
    (n) => document.querySelectorAll('[role="feed"] article').length >= n,
    expectedArticles,
    { timeout: TURN_TIMEOUT_MS },
  )
  await page.waitForSelector('textarea[placeholder^="Ask Halbert"]', { timeout: TURN_TIMEOUT_MS })
}

try {
  await page.goto(BASE, { waitUntil: 'networkidle' })
  await page.waitForSelector('textarea[placeholder^="Ask Halbert"]', { timeout: 30_000 })
  log('engaged surface loads', true, BASE)

  log('no conversation dropdown', (await page.getByText('New Conversation').count()) === 0)
  log('no session footer', (await page.getByText(/^Session:/).count()) === 0)

  const before = await articleCount()

  await sendAndWait(MESSAGE_1, before + 1)
  log('turn 1 folded into the timeline', (await articleCount()) === before + 1)
  log('day divider is an h2', (await page.locator('header.thread-divider h2').count()) > 0)
  const hadTerminal = (await tileOrChip().count()) > 0
  log('turn 1 opened a terminal (tile or chip)', hadTerminal, hadTerminal ? '' : 'model did not run a command — the reload check below is skipped for the tile')
  const topic = await page.getByTestId('current-topic').textContent().catch(() => '')
  log('sticky topic label present', !!topic && topic.trim().length > 0, topic ?? '')

  await sendAndWait(MESSAGE_2, before + 2)
  log('turn 2 folded into the timeline', (await articleCount()) === before + 2)
  log('turn 1 still on screen after turn 2', (await page.getByText('uname -a').count()) > 0)
  if (hadTerminal) {
    log('tile from turn 1 survives turn 2', (await tileOrChip().count()) > 0)
  }

  await page.reload({ waitUntil: 'networkidle' })
  await page.waitForSelector('[role="feed"] article', { timeout: 30_000 })
  const after = await articleCount()
  log('both turns are back after reload', after >= before + 2, `${after} articles`)
  log('turn 1 text persisted', (await page.getByText('uname -a').count()) > 0)
  log('turn 2 text persisted', (await page.getByText('2 + 2').count()) > 0)
  if (hadTerminal) {
    const chip = await page.getByText('terminal · ended').count()
    const tile = await page.locator('[data-terminal-origin]').count()
    log('terminal from turn 1 is a tile or an ended chip after reload', chip + tile > 0)
  }
  log('sticky topic label back after reload', (await page.getByTestId('current-topic').count()) > 0)
  log('polite live region exists', (await page.locator('[role="status"][aria-live="polite"]').count()) === 1)
  log('assertive alert region exists', (await page.locator('[role="alert"][aria-live="assertive"]').count()) === 1)

  log('no console errors', consoleErrors.length === 0, consoleErrors.slice(0, 3).join(' | '))
} catch (err) {
  log('smoke aborted', false, err instanceof Error ? err.message : String(err))
} finally {
  await browser.close()
}
```

- [ ] **Step 2: Verify it is inert without playwright and outside `npm test`**

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core/halbert_core/dashboard/frontend && node e2e/continuity.smoke.mjs; echo "exit=$?"
```
Expected: the manual checklist is printed, then `exit=0`.

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core/halbert_core/dashboard/frontend && npx vitest run 2>&1 | grep -c continuity; npx tsc --noEmit -p .; echo "tsc=$?"
```
Expected: `0` (vitest never collects it) and `tsc=0`.

- [ ] **Step 3: (Optional, live backend) run it for real**

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation/halbert_core/halbert_core/dashboard/frontend && npm i --no-save playwright && npx playwright install chromium && node e2e/continuity.smoke.mjs
```
Expected: every line starts with `[PASS]`; "turn 1 opened a terminal" may be `[FAIL]` when the model answers without running a command — rerun with a more explicit MESSAGE_1 if so. `npm i --no-save` leaves `package.json` and the lockfile untouched; confirm with `git status --short` before committing.

- [ ] **Step 4: Commit**

```
cd /Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation && git add halbert_core/halbert_core/dashboard/frontend/e2e/continuity.smoke.mjs && git commit -m "test(dashboard): browser smoke for the continuous conversation

Walks two turns and a reload against a live backend: the first turn and
its terminal survive the second and the reload, dividers are headings,
the topic label and both live regions exist. Uses playwright when it is
installed and prints the manual checklist otherwise; never part of
npm test."
```

**Contract additions (planner F)** — for the verifier to propagate:
- `FE/types/timeline.ts` also exports `TimelineMessage`, `TimelineMessageStatus`, `TimelineOrigin`, `TimelineCurrentThread`, and the wire mappers `toMillis`, `blockFromServer`, `diffFromServer`, `turnFromServer`, `threadFromServer`, `pageFromServer` (server seconds → client ms; `thread_id | conversation_id | id` accepted as the thread id; stored diffs accepted in both the `pending_diffs` shape `{file_path, edit_blocks[{search,replace}], status}` and the `diff_proposal` event shape).
- `useTimeline` also returns `loading: boolean`, `loadAround(turnId): Promise<void>` (fetches `?around=<turnId>&limit=50`, replaces the page, sets `anchored`, scrolls to `[data-turn-id=<turnId>]` once rendered), `loadLatest(): Promise<void>` (first page again, clears `anchored`) and `anchored: boolean`; `setCurrentThread` is a React `Dispatch<SetStateAction<TimelineCurrentThread | null>>`; exports `TimelineDay`, `dayKeyOf`, `dayLabel`, `groupByDay`.
- `AgentSession.recalled` carries `lastTurnId: string | null` (from the event's `last_turn_id`); a `thread_started` event clears `recalled` and removes any `source: 'thread'` context item (chip expiry on pause).
- `UseAgentStreamReturn.dismissContextItem(id: string)` — removes a context chip locally and clears `session.recalled` when it was the thread chip.
- `FE/lib/api.ts` also exports `redactMessage(messageId: number): Promise<{ ok: boolean }>` → `POST /api/agent/message/{id}/redact`. The legacy `listAgentConversations` / `getAgentConversation` / `deleteAgentConversation` are deleted in A18 (not A14), the commit that removes their last callers.
- `FE/lib/turnFromSession.ts`: `turnFromSession(session, userMessage: {id, content, timestamp}, response, opts?: {cancelled?: boolean}): TimelineTurn` (turnId falls back to `local-${sessionId}`; status `cancelled | interrupted | complete`).
- `FE/components/agent/MessageContent.tsx` (extracted verbatim from AgentChat; exports `MessageContent`, `RunCommand`).
- `FE/components/agent/StaticTerminalChip.tsx`: `StaticTerminalChip({ id, label? })` renders `terminal · ended` with `data-session-id`; used by `Timeline` and `InlineTerminals`.
- `DiffBlock` gains `readOnly?: boolean` (pending diff shows `proposed`, no Apply/Reject).
- `Timeline` props: `{ byDay, hasMore, loading, anchored?, onLoadOlder, onLoadLatest?, onRunCommand? }`; exports `executionFromBlock(block, fallbackId): ToolExecution`, `REDACTED` (`'[redacted by admin]'`) and `redactableIds(turn): number[]`. Each stored turn with a server message id renders a `Forget this` button (`aria-label="Forget this turn"`) that calls `api.redactMessage` for the user and assistant rows and then shows `REDACTED` in place of the words and tool cards (terminal chips stay). A `Back to latest` button renders while `anchored`.
- `FE/lib/announce.ts` exports `announce(text, { assertive? })`, `subscribeAnnouncements((text, options) => …)`, `lastAnnouncement()` (last polite) and `lastAlert()` (last assertive); `FE/components/shell/LiveRegion.tsx` renders both regions — `role="status" aria-live="polite" aria-atomic="true"` and `role="alert" aria-live="assertive" aria-atomic="true"` — mounted first inside HostShell's root. `useAgentStream` announces `Waiting for your approval` assertively on `tool_confirmation_required` (outside the reducer; name-free because the hook has no access to the onboarding `display_name`).
- ContextBar `TYPE_CONFIG` entries gain `noun`; the pill's accessible name is `"<noun>: <label>"` (thread noun: `earlier subject`); `ContextItem.hint?: string` renders as the pill button's `title` (AgentChat sets `matched: <terms>` on the thread chip); the collapse control is labelled `Collapse context` / `Expand context` with `aria-expanded`.
- `CurrentTopicLabel` renders the stored title verbatim — no voice branch (a title has no pronouns; spec §11's "follows the voice setting" is satisfied by the server-rendered continuity text).
- Backend expectation used here: `GET /api/agent/thread/current` may return the raw row (with `conversation_id`); `thread_started` events carry `thread_id` and `title`; `thread_recalled` carry `thread_id`, `title`, `date`, `match_terms` **and `last_turn_id`** (the recalled thread's most recent turn id, or null — the backend planner adds it to `StreamEvent.thread_recalled` and to both emission sites: `ThreadManager.recall()` results and the auto-recall loop in `_begin_turn`); `turn_persisted` carries `turn_id`; `thread_store_error` carries `message` — all at the top level of the SSE JSON like every existing event. New backend route required by A17b: `POST /api/agent/message/{message_id}/redact -> {"ok": true}`, which replaces the row's `content` and `blocks_json` with `[redacted by admin]`, rewrites its `messages_fts` row and regenerates the thread receipt (spec §5); 404 → `{"ok": false}` is acceptable, a 500 is not.
