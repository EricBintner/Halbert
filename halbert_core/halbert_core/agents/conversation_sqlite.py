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

from ..intake.signals import canonical_entities
from .blocks import content_to_text
from .conversation import Conversation, Message

logger = logging.getLogger("halbert.agents.conversation_sqlite")

_DEFAULT_DB = str(Path.home() / ".halbert" / "conversations.db")

#: Bump when a migration step below must run on existing databases.
SCHEMA_VERSION = 4

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
#: Added to ``terminal_blocks`` after the table shipped. ``execution_id`` is
#: the tool call that ran the block: the join the timeline needs to render a
#: stored command the same way the live stream did.
_TERMINAL_BLOCK_ADDITIVE: List[Tuple[str, str]] = [
    ("execution_id", "TEXT"),
    # How many lines fell between output_head and output_tail. Stored so a
    # reloaded turn shows the same elision the live one did; the frontend
    # cannot recompute it from the two halves it receives.
    ("output_elided_lines", "INTEGER"),
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

_THREAD_JSON_LISTS = ("topic_domains", "entities_json", "recalled_json")
_THREAD_FLAGS = ("stale", "ephemeral", "unread")
_THREAD_UPDATABLE = {"title", "updated_at", "user_id", "metadata"} | {
    name for name, _ in _THREAD_COLUMNS
}

# Thread-metadata keys holding entity sets *derived from message text*, which
# is why a redaction has to reach into them (``ThreadManager``'s
# ``_TOPIC_WINDOW_KEY`` / ``_FOUNDING_ENTITIES_KEY``). Spelled out here rather
# than imported because threads.py imports this module and not the other way
# round; ``tests/test_agent_routes_redact.py`` pins the two spellings against
# each other so a rename on either side fails loudly instead of silently
# turning the scrub below into a no-op.
_META_TOPIC_WINDOW = "topic_window"
_META_FOUNDING_ENTITIES = "founding_entities"

#: How much of one row's content the redaction's "does any surviving row still
#: say this?" scan reads. Mirrors ``intake/signals.py::_ENTITY_SCAN_LIMIT``:
#: entities were only ever harvested from that prefix, so reading further
#: could not change the answer.
_ENTITY_SCAN_CHARS = 16 * 1024

#: Total characters that scan may read across the thread before it stops.
#: The pass is a regex sweep (~0.36 ms/KB measured), so an unbounded walk of a
#: long thread of pasted logs is seconds of CPU on the event loop -- the
#: redaction route is ``async``. ~100 ms of work is enough to reach every row
#: of an ordinary thread many times over; see ``_scrub_thread_entities`` for
#: why stopping early errs safely.
_ENTITY_SURVIVOR_BUDGET = 256 * 1024

_THREAD_SELECT = """SELECT c.*,
    (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id) AS message_count,
    (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id AND m.role = 'user') AS turn_count
    FROM conversations c"""

_TURN_KEY = "COALESCE(turn_id, 'm' || id)"
_TURN_KEYS_SQL = (
    f"SELECT {_TURN_KEY} AS turn_key, MIN(id) AS first_id "
    "FROM messages WHERE visible_in_timeline = 1 GROUP BY turn_key"
)
# PERF NOTE (A1b round-3 review, finding 2): this expression can't be served
# by `idx_messages_turn`, so every `list_turns` call does a full GROUP BY
# scan of the whole `messages` table -- and does it three times over (this
# query, `_turn_first_id`, and the final `visible_in_timeline` fetch by key),
# all inside the same `self._lock` RLock `append_message` needs. That is
# O(total messages) on the hot read path of a conversation designed never to
# end, and it blocks concurrent writes for the whole page. Measured on this
# branch: ~20ms/40k messages, ~120-190ms/200k messages. This matches the
# design specified in the Plan A task text, so it is not a deviation -- but
# it should not be assumed to stay flat as the corpus grows. Before A11 (or
# any other paging consumer) leans on this at scale, either bound the GROUP
# BY to an id window (turns have bounded row counts, so
# `id > anchor - limit * K` is safe) or backfill `turn_id` on legacy rows so
# a plain indexed column can be grouped instead.

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


def _term_hits(terms: Sequence[str], haystack: str) -> List[str]:
    """Terms whose crude stem (drop the last letter past 4 chars) starts a word in ``haystack``."""
    out: List[str] = []
    for t in terms:
        stem = t[:-1] if len(t) > 4 else t
        if re.search(r"\b" + re.escape(stem), haystack):
            out.append(t)
    return out


def _receipt_snippet(receipt: str, matched: Sequence[str]) -> str:
    """Line of ``receipt`` most likely to contain a ``matched`` term.

    Literal substring first -- this already covers the common direction,
    where the receipt line holds the longer inflected word and a shorter
    query term/stem is a substring of it (e.g. line "...the resilver has
    not finished..." vs. query term "resilver"). When nothing matches
    literally, a shared-prefix word scan steps in for the *other*
    direction: a query term such as "resilvering" that only matched via
    the porter stemmer's -ing/-ed/-ion suffix stripping, where the shorter
    receipt word ("resilver") is a prefix of the longer query term rather
    than the reverse, so no substring check in either direction finds it
    (A3 review round 2, finding 3). Porter only strips suffixes, so an
    inflected form and its stem always share a prefix -- this is the same
    reason ``match_terms`` above stopped trying to reimplement Porter
    itself, but there it could re-ask the live FTS index per term; there
    is no per-line index here to ask the same question of, so a prefix
    scan over the line's own words is the cheap stand-in.
    """
    lines = [ln for ln in (receipt or "").splitlines() if ln.strip()]
    for ln in lines:
        low = ln.lower()
        if any(t in low for t in matched):
            return ln[:200]
    for ln in lines:
        words = _TOKEN_RE.findall(ln.lower())
        if any(
            len(t) >= 4 and len(w) >= 4 and (t.startswith(w) or w.startswith(t))
            for t in matched
            for w in words
        ):
            return ln[:200]
    return lines[0][:200] if lines else ""


def _loads(text: Any, default: Any) -> Any:
    if not text:
        return default
    try:
        value = json.loads(text)
    except Exception:
        return default
    return value if value is not None else default


class RedactionFailed(RuntimeError):
    """A redaction write did not land: the row's original text is still stored.

    The one place this store raises instead of returning a falsy value. A
    redaction is a privacy promise, and "the write failed" has to be
    distinguishable from "there is no such row" -- otherwise a rolled-back
    redaction (disk full, locked database, an FTS error escaping
    ``_fts_recover``) reaches the caller as a benign 404 "message not found"
    while the original words are still on disk, and the person who asked to
    forget something is told nothing needed forgetting (A11b review finding
    2).
    """


class SqliteConversationStore:
    """SQLite-backed thread/message store with FTS5 search.

    Thread-safe (single connection + re-entrant lock). Best-effort: methods
    log at WARNING and return ``None``/``False``/``[]`` rather than raise --
    with one deliberate exception, ``redact_message``, which raises
    ``RedactionFailed`` when its write does not land.
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
            if name in existing:
                continue
            try:
                cur.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
            except sqlite3.OperationalError as e:
                # A concurrent opener may have added this column between our
                # PRAGMA table_info read and this ALTER (belt-and-suspenders:
                # _ensure_schema also serializes openers with BEGIN IMMEDIATE,
                # but this keeps a single column race from aborting every
                # column after it — see A1 review finding 1).
                if "duplicate column name" in str(e):
                    continue
                raise

    def _ensure_schema(self) -> None:
        with self._lock:
            cur = self._conn.cursor()
            # busy_timeout first: it must be in effect before anything below
            # (the WAL pragma, then BEGIN IMMEDIATE) can hit SQLITE_BUSY.
            try:
                cur.execute("PRAGMA busy_timeout=5000")
            except Exception as e:
                logger.warning(f"SqliteConversationStore schema failed (busy_timeout pragma): {e}")
                self._conn = None
                return
            # A journal-mode change requires SQLite to grab an exclusive lock,
            # and — unlike BEGIN IMMEDIATE below — that lock request does NOT
            # go through the busy handler: SQLite returns SQLITE_BUSY
            # immediately if any other connection currently holds the write
            # lock, busy_timeout or no busy_timeout. Treating that as fatal
            # used to abort the migration before a single CREATE/ALTER TABLE
            # ran while leaving ``self._conn`` set, so the instance silently
            # lost every future write for the rest of its life (A1 review
            # finding 1). WAL is a nice-to-have, not required for
            # correctness, so tolerate the failure and keep going in the
            # connection's default rollback-journal mode — BEGIN IMMEDIATE
            # right below still waits out busy_timeout for the migration
            # itself.
            try:
                cur.execute("PRAGMA journal_mode=WAL")
            except Exception as e:
                logger.warning(f"PRAGMA journal_mode=WAL failed, continuing without WAL: {e}")
            # Serialize schema creation/migration across concurrent openers of
            # the same database file. BEGIN IMMEDIATE claims the write lock
            # up front (busy_timeout above governs how long a racing opener
            # waits here) instead of letting every opener's PRAGMA table_info
            # + ALTER TABLE sequence race one another: the loser used to see
            # a schema missing the exact columns another opener was mid-way
            # through adding, raise, and abort the rest of its own migration
            # (A1 review finding 1).
            try:
                cur.execute("BEGIN IMMEDIATE")
            except Exception as e:
                logger.warning(f"SqliteConversationStore schema failed (lock): {e}")
                self._conn = None
                return
            try:
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
                # v3: terminal_blocks and terminal_sessions (Plan B: B1).
                # Blocks are the persisted shell-command records that back
                # terminal tiles on the timeline; sessions are the PTY
                # sessions (user, agent-pool, oneshot) that produce them.
                cur.execute(
                    """CREATE TABLE IF NOT EXISTS terminal_blocks (
                        block_id    TEXT PRIMARY KEY,
                        session_id  TEXT NOT NULL,
                        thread_id   TEXT,
                        turn_id     TEXT,
                        command     TEXT NOT NULL,
                        cwd         TEXT,
                        owner       TEXT NOT NULL DEFAULT 'agent',
                        interactive INTEGER NOT NULL DEFAULT 0,
                        remote      INTEGER NOT NULL DEFAULT 0,
                        redacted    INTEGER NOT NULL DEFAULT 0,
                        started_at  REAL NOT NULL,
                        ended_at    REAL,
                        exit_code   INTEGER,
                        output_head TEXT NOT NULL DEFAULT '',
                        output_tail TEXT NOT NULL DEFAULT '',
                        execution_id TEXT,
                        output_elided_lines INTEGER
                    )"""
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_tb_session "
                    "ON terminal_blocks(session_id)"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_tb_thread "
                    "ON terminal_blocks(thread_id)"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_tb_turn "
                    "ON terminal_blocks(turn_id)"
                )
                cur.execute(
                    """CREATE TABLE IF NOT EXISTS terminal_sessions (
                        session_id  TEXT PRIMARY KEY,
                        kind        TEXT NOT NULL DEFAULT 'oneshot',
                        owner       TEXT NOT NULL DEFAULT 'agent',
                        watched     INTEGER NOT NULL DEFAULT 1,
                        spawned_at  REAL NOT NULL,
                        ended_at    REAL,
                        last_state  TEXT NOT NULL DEFAULT 'running'
                    )"""
                )
                self._add_missing_columns(cur, "conversations", _THREAD_COLUMNS)
                self._add_missing_columns(cur, "messages", _MESSAGE_COLUMNS)
                self._add_missing_columns(
                    cur, "terminal_blocks", _TERMINAL_BLOCK_ADDITIVE
                )
                # v4: open_loops table (continuity R2-N2).
                cur.execute(
                    """CREATE TABLE IF NOT EXISTS open_loops (
                        id          INTEGER PRIMARY KEY AUTOINCREMENT,
                        thread_id   TEXT NOT NULL,
                        text        TEXT NOT NULL,
                        domain      TEXT,
                        created_at  REAL NOT NULL,
                        closed_at   REAL,
                        source      TEXT
                    )"""
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_open_loops_thread "
                    "ON open_loops(thread_id, closed_at)"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_messages_turn ON messages(turn_id)"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_conversations_status "
                    "ON conversations(status)"
                )
                row = cur.execute("SELECT MAX(version) FROM schema_version").fetchone()
                version = int(row[0]) if row and row[0] is not None else 0
                # Tracked locally and only committed to ``self._fts_ok`` once the
                # whole migration (including the schema_version bump below and
                # the final commit) has actually succeeded — see the comment on
                # the outer ``except`` for why (A1 review finding 2).
                fts_ready = False
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
                        fts_ready = True
                    else:
                        cur.execute(
                            "CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5("
                            "conversation_id UNINDEXED, content, "
                            "tokenize='porter unicode61')"
                        )
                        # Backfill: an already-versioned DB whose messages_fts
                        # table was just (re)created by ``IF NOT EXISTS`` (e.g.
                        # a runtime without FTS5 wrote unindexed rows, and this
                        # runtime has it) would otherwise report ``healthy``
                        # over a permanently empty index (A1 review finding 2).
                        cur.execute(
                            "INSERT INTO messages_fts(rowid, conversation_id, content) "
                            "SELECT id, conversation_id, content FROM messages "
                            "WHERE id NOT IN (SELECT rowid FROM messages_fts)"
                        )
                        fts_ready = True
                    cur.execute(
                        "CREATE VIRTUAL TABLE IF NOT EXISTS receipts_fts USING fts5("
                        "thread_id UNINDEXED, title, receipt, "
                        "tokenize='porter unicode61')"
                    )
                    # Backfill: same rationale as the messages_fts backfill
                    # just above -- a DB that had receipts written while a
                    # runtime without FTS5 was in charge would otherwise
                    # reopen "healthy" over a receipts_fts table missing
                    # those rows forever (mirrors A1 review finding 2, closed
                    # here for receipts_fts per the A3 review).
                    cur.execute(
                        "INSERT INTO receipts_fts(thread_id, title, receipt) "
                        "SELECT id, title, receipt FROM conversations "
                        "WHERE receipt != '' AND id NOT IN "
                        "(SELECT thread_id FROM receipts_fts)"
                    )
                except sqlite3.OperationalError as e:
                    logger.warning(f"FTS5 unavailable, falling back to LIKE: {e}")
                    fts_ready = False
                if version < SCHEMA_VERSION:
                    cur.execute("DELETE FROM schema_version")
                    cur.execute(
                        "INSERT INTO schema_version(version) VALUES (?)", (SCHEMA_VERSION,)
                    )
                self._conn.commit()
                # Only now, after a successful commit, does the flag reflect
                # reality. Setting it earlier (as before) meant a later
                # statement raising would roll back the just-created FTS
                # tables while the flag stayed True, and ``_fts_recover()``
                # short-circuits on a True flag, so it would never have
                # re-verified (A1 review finding 2, the mirror of finding 3's
                # False-latch bug).
                self._fts_ok = fts_ready
            except Exception as e:
                self._conn.rollback()
                logger.warning(f"SqliteConversationStore schema failed: {e}")
                self._fts_ok = False
                # A half-applied migration (e.g. the messages table missing
                # thread columns) must not look like a healthy, usable store:
                # every subsequent method already treats ``self._conn is None``
                # as "fail loudly/return the documented empty result" instead
                # of quietly writing against a schema that doesn't match what
                # the rest of this class assumes (A1 review finding 1).
                self._conn = None

    @property
    def healthy(self) -> bool:
        """``False`` while degraded: no connection, or FTS5 unavailable so
        ``search`` falls back to title-only ``LIKE`` matching. A route can
        poll this to emit ``thread_store_error`` once instead of finding out
        only when a search silently comes back thin."""
        return self._conn is not None and self._fts_ok

    @property
    def connected(self) -> bool:
        """Whether the store has a live connection at all.

        Weaker than ``healthy``, which also demands a working FTS5. A caller
        that must tell "the store is down" from "that row does not exist" --
        the redaction route, which owes those two answers different status
        codes -- wants this one (A11b review finding 2).
        """
        return self._conn is not None

    def _fts_recover(self) -> bool:
        """Return whether FTS5 is currently usable, retrying table creation
        when it previously was not.

        ``_fts_ok`` is not a permanent kill switch: a transient failure at
        connect time (a migration race, a momentarily-unavailable extension)
        should not disable search for the rest of the process's life, so
        every caller that used to gate on ``self._fts_ok`` directly now calls
        this instead (A1 review finding 3). Safe to call from inside an
        already-open write transaction (e.g. from ``append_message``): when
        one is already open (``self._conn.in_transaction``) it leaves the
        commit/rollback to that caller's own ``with self._conn:`` block;
        otherwise (a standalone call, e.g. from ``search``) it commits its
        own work itself so nothing is left dangling uncommitted.

        Recovery also backfills: any ``messages`` row not yet present in
        ``messages_fts`` is indexed, so a table that was just (re)created
        by ``CREATE VIRTUAL TABLE IF NOT EXISTS`` does not report healthy
        over what would otherwise stay a permanently empty index for rows
        written before recovery (A1 review finding 2). ``receipts_fts`` gets
        the identical backfill for the identical reason: ``upsert_receipt``
        writes ``conversations.receipt`` unconditionally but only mirrors it
        into ``receipts_fts`` while ``self._fts_recover()`` reports healthy,
        so any receipt written during a degraded window would otherwise
        never appear in the index, even after recovery (A3 review finding 1).
        """
        if self._fts_ok or self._conn is None:
            return self._fts_ok
        try:
            with self._lock:
                nested = self._conn.in_transaction
                self._conn.execute(
                    "CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5("
                    "conversation_id UNINDEXED, content, "
                    "tokenize='porter unicode61')"
                )
                self._conn.execute(
                    "INSERT INTO messages_fts(rowid, conversation_id, content) "
                    "SELECT id, conversation_id, content FROM messages "
                    "WHERE id NOT IN (SELECT rowid FROM messages_fts)"
                )
                self._conn.execute(
                    "CREATE VIRTUAL TABLE IF NOT EXISTS receipts_fts USING fts5("
                    "thread_id UNINDEXED, title, receipt, "
                    "tokenize='porter unicode61')"
                )
                self._conn.execute(
                    "INSERT INTO receipts_fts(thread_id, title, receipt) "
                    "SELECT id, title, receipt FROM conversations "
                    "WHERE receipt != '' AND id NOT IN "
                    "(SELECT thread_id FROM receipts_fts)"
                )
                if not nested:
                    self._conn.commit()
            self._fts_ok = True
            logger.info("FTS5 recovered; search is no longer degraded to title-only")
        except sqlite3.OperationalError as e:
            logger.warning(f"FTS5 still unavailable, staying in LIKE-only fallback: {e}")
        return self._fts_ok

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
                         updated_at = MAX(conversations.updated_at, excluded.updated_at),
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
        if self._fts_recover() and terms:
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
        failed; nothing is left behind on failure. ``None`` is also returned,
        with no row written, when ``thread_id`` does not name an existing
        conversation (there is no FK, so a typo'd/deleted/merged thread id
        would otherwise write a message no ``get``/``search``/``list_threads``
        call can ever surface again — A1 review finding 4).
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
                if self._conn.execute(
                    "SELECT 1 FROM conversations WHERE id = ?", (thread_id,)
                ).fetchone() is None:
                    raise ValueError(f"no such thread_id {thread_id!r}")
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
                if self._fts_recover():
                    # OR REPLACE: ``_fts_recover()`` may itself have just
                    # backfilled this exact row (it runs its NOT-IN-fts
                    # backfill against ``messages`` as it stands right now,
                    # which already includes the row inserted immediately
                    # above) -- a plain INSERT would then collide on rowid
                    # with what recovery already wrote (same content either
                    # way, so replacing is a no-op in substance).
                    self._conn.execute(
                        "INSERT OR REPLACE INTO messages_fts(rowid, conversation_id, content) "
                        "VALUES (?, ?, ?)",
                        (message_id, thread_id, text),
                    )
                # MAX(...): agrees with save()'s ON CONFLICT clause (A1 review
                # finding 3) so the two write paths can't rewind each other.
                # agents/migrations.py backfills messages with an explicit,
                # often much older, ``timestamp=`` — an unconditional
                # assignment here would otherwise drop a thread's recency
                # below whatever it already was, corrupting ``ORDER BY
                # updated_at DESC`` in list_conversations/list_threads
                # (A1 review finding 3).
                self._conn.execute(
                    "UPDATE conversations SET updated_at = MAX(updated_at, ?) WHERE id = ?",
                    (ts, thread_id),
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
                if "thread_id" in fields:
                    # Same orphaning bug append_message's existence check
                    # closed (A1 review finding 4), left open on this sibling
                    # write path: with no FK on conversation_id, moving a
                    # message to a thread id that doesn't exist would silently
                    # make it invisible to every reader (get/search/list) for
                    # good, and thread_id moves are exactly what merge/split
                    # tasks later in Plan A use this method for.
                    new_thread_id = fields["thread_id"]
                    if self._conn.execute(
                        "SELECT 1 FROM conversations WHERE id = ?", (new_thread_id,)
                    ).fetchone() is None:
                        raise ValueError(f"no such thread_id {new_thread_id!r}")
                cur = self._conn.execute(
                    f"UPDATE messages SET {', '.join(sets)} WHERE id = ?", params
                )
                if cur.rowcount == 0:
                    return False
                if reindex and self._fts_recover():
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
    # Forget / redact (spec §5)
    # ------------------------------------------------------------------

    REDACTED = "[redacted by admin]"

    def redact_message(self, message_id: int) -> Optional[str]:
        """"Forget this" for one row: content and blocks become the
        redaction marker, diff proposals are dropped, metadata gains
        ``redacted``, and every copy the row left elsewhere in the store --
        its FTS index row, the thread title it founded, the thread's derived
        entity sets -- goes with it, so the original words are neither
        searchable nor quotable back into a later prompt. The row itself is
        never deleted. Returns the thread id, or None when the row does not
        exist (or the store has no connection). Raises ``RedactionFailed``
        when any part of that did not land, so a caller never reports a
        privacy action it did not perform. The caller refreshes the thread's
        receipt.

        A redacted *founding* user row takes the thread title down with it.
        Spec §5 defines the provisional title as "first user message
        truncated to 60 characters" and ``ThreadManager._refined_title_fields``
        draws the refined title's verb from that same row, so the title is a
        derived copy of exactly the text a person redacts when they have
        pasted a secret. Leaving it standing kept the words searchable
        (``search``'s ``lower(title) LIKE`` pass, ``search_receipts``' title
        column) and, worse, the receipt refresh that follows a redaction
        re-``INSERT``ed them into ``receipts_fts`` -- the copy recall reads
        back into later prompts as ``retrieved_context`` (A11b review finding
        1). ``title_source`` becomes ``redacted`` so nothing re-derives a
        title from a redacted row later.
        """
        if self._conn is None:
            return None
        try:
            with self._lock, self._conn:
                row = self._conn.execute(
                    "SELECT conversation_id, role, content, blocks_json, metadata "
                    "FROM messages WHERE id = ?",
                    (int(message_id),),
                ).fetchone()
                if row is None:
                    return None
                thread_id = row["conversation_id"]
                original = row["content"] or ""
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
                # `terminal_block_ids` is deliberately left alone: they are
                # opaque session ids, not text the person typed, and the
                # timeline still wants to show that a terminal was involved.
                # Pre-existing metadata keys are kept for the same reason (an
                # A12a-migrated row carries arbitrary JSON metadata from
                # disk); only `redacted` is added.
                self._fts_recover()   # best-effort: flips a stale degraded flag back
                self._scrub_fts_row(int(message_id), thread_id)
                if row["role"] == "user" and self._is_founding_user_row(thread_id, message_id):
                    self._conn.execute(
                        "UPDATE conversations SET title = ?, title_source = 'redacted' "
                        "WHERE id = ?",
                        (self.REDACTED, thread_id),
                    )
                self._scrub_thread_entities(thread_id, original, int(message_id))
            return thread_id
        except Exception as e:
            logger.warning(f"redact_message {message_id} failed: {e}")
            raise RedactionFailed(f"redaction of message {message_id} did not land: {e}") from e

    def _scrub_fts_row(self, message_id: int, thread_id: str) -> None:
        """Rewrite one row's ``messages_fts`` copy to the marker.

        Gating this on ``self._fts_ok`` / ``self._fts_recover()`` -- the way
        every other writer in this class does -- is wrong for a redaction.
        Recovery's backfill only INSERTs rows that are *missing*, so a row
        indexed by an earlier healthy process and skipped here keeps its
        original words in the index verbatim and for good: no later healthy
        process ever rewrites it, ``search`` finds the thread by them and
        ``search_snippets`` hands the whole sentence back (it reads the FTS
        copy, not ``messages.content``), straight into ``recall()`` and the
        next prompt (A11b review finding 2). So the scrub is attempted
        whenever the table exists at all, and if it cannot land the exception
        propagates: ``redact_message``'s transaction rolls back and the caller
        answers 500 rather than reporting a privacy action that only half
        happened. That is a deliberate refusal -- on a runtime whose sqlite
        cannot touch an existing FTS5 table, a redaction fails loudly and can
        be retried on a healthy one, where the partial alternative would have
        left a permanent leak behind a green tick.

        The one benign case is a database with no ``messages_fts`` table:
        nothing is indexed, so there is nothing to leak, and whenever the
        table is created later it is backfilled from ``messages``, which by
        then holds the marker. ``sqlite_master`` answers that question with a
        plain table query, without needing the FTS5 module itself.
        """
        indexed = self._conn.execute(
            "SELECT 1 FROM sqlite_master WHERE name = 'messages_fts'"
        ).fetchone()
        if indexed is None:
            return
        self._conn.execute(
            "DELETE FROM messages_fts WHERE rowid = ?", (message_id,)
        )
        self._conn.execute(
            "INSERT INTO messages_fts(rowid, conversation_id, content) "
            "VALUES (?, ?, ?)",
            (message_id, thread_id, self.REDACTED),
        )

    def _scrub_thread_entities(
        self, thread_id: str, redacted_text: str, message_id: int
    ) -> None:
        """Drop the redacted row's entities from the thread's derived sets.

        ``conversations.entities_json``, ``metadata["topic_window"]["entities"]``
        and ``metadata["founding_entities"]`` are all harvested from message
        *text* by ``intake/signals.py::_scan``, and that harvest keeps **raw
        file paths** (up to 20 a message) beside the alias keywords. Scrubbing
        the row while leaving those standing left the redacted words on the
        thread row, on the ``Entities:`` line of the receipt the caller
        regenerates next and -- through ``upsert_receipt``'s DELETE+INSERT --
        back in ``receipts_fts``, which is the copy ``ThreadManager.recall()``
        feeds into later prompts as ``retrieved_context``: a redacted
        "/srv/clients/acmecorp-payroll-2026.kdbx" was still reachable by
        ``search_receipts("payroll")`` (A11b review finding 1).

        Only entities that *no surviving row of the thread still yields* are
        dropped: these sets describe the thread, not the row, and a path both
        turns mentioned is still the subject of the turn that was not
        redacted. Answering that is a regex sweep per row, so it walks the
        thread newest-first (the sets are a window over the recent turns) and
        stops after ``_ENTITY_SURVIVOR_BUDGET`` characters. An entity the
        budget did not reach is dropped rather than kept: over-dropping costs
        a recall term that ``ThreadManager._topic_sets`` re-adds from the next
        turn that says it, while over-keeping is the leak this exists to
        close. ``topic_domains`` is left alone deliberately: it can only ever
        hold one of the six fixed domain names from ``intake/signals.py``,
        never text a person typed.
        """
        gone = canonical_entities((redacted_text or "")[:_ENTITY_SCAN_CHARS])
        if not gone:
            return
        budget = _ENTITY_SURVIVOR_BUDGET
        for surviving in self._conn.execute(
            "SELECT substr(content, 1, ?) FROM messages "
            "WHERE conversation_id = ? AND id != ? ORDER BY id DESC",
            (_ENTITY_SCAN_CHARS, thread_id, int(message_id)),
        ):
            head = surviving[0] or ""
            gone -= canonical_entities(head)
            if not gone:
                return
            budget -= len(head)
            if budget <= 0:
                break
        thread = self._conn.execute(
            "SELECT entities_json, metadata FROM conversations WHERE id = ?",
            (thread_id,),
        ).fetchone()
        if thread is None:
            return
        entities = [e for e in _loads(thread["entities_json"], []) if e not in gone]
        meta = _loads(thread["metadata"], {})
        if not isinstance(meta, dict):
            meta = {}
        window = meta.get(_META_TOPIC_WINDOW)
        if isinstance(window, dict) and isinstance(window.get("entities"), dict):
            window["entities"] = {
                k: v for k, v in window["entities"].items() if k not in gone
            }
        founding = meta.get(_META_FOUNDING_ENTITIES)
        if isinstance(founding, (list, tuple)):
            meta[_META_FOUNDING_ENTITIES] = [e for e in founding if e not in gone]
        self._conn.execute(
            "UPDATE conversations SET entities_json = ?, metadata = ? WHERE id = ?",
            (json.dumps(entities), json.dumps(meta), thread_id),
        )

    def _is_founding_user_row(self, thread_id: str, message_id: int) -> bool:
        """Whether ``message_id`` is the earliest user row of its thread --
        the one every title in the system is derived from. Called from inside
        ``redact_message``'s open transaction (the lock is re-entrant)."""
        first = self._conn.execute(
            "SELECT id FROM messages WHERE conversation_id = ? AND role = 'user' "
            "ORDER BY id ASC LIMIT 1",
            (thread_id,),
        ).fetchone()
        return first is not None and int(first[0]) == int(message_id)

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

    def last_turn_id(self, thread_id: str) -> Optional[str]:
        """The newest ``turn_id`` in a thread, or None when it has none.

        ``thread_recalled`` carries this one id so the chip click can scroll
        the timeline to where a recalled subject left off (spec §6), and
        A9c's auto-recall asks for it every turn. Reading it with
        ``list_messages`` materialised the whole thread — every row built and
        its four JSON columns decoded, under ``self._lock`` — to look at one
        column of one row: the same ~30 ms/4k-row cost ``pending_notes``
        exists to avoid, paid up to three times per ``recall_thread`` (review:
        Plan A / A9b). ``list_messages(limit=N)`` cannot serve it either —
        that LIMIT takes the OLDEST N rows.

        This walks ``idx_messages_conv`` backwards from the thread's newest
        row and stops at the first row carrying a ``turn_id``; only a tail of
        rows written without one (hidden system notes) is walked past.
        """
        if self._conn is None or not thread_id:
            return None
        try:
            with self._lock:
                row = self._conn.execute(
                    """SELECT turn_id FROM messages
                       WHERE conversation_id = ?
                         AND turn_id IS NOT NULL AND turn_id <> ''
                       ORDER BY id DESC LIMIT 1""",
                    (thread_id,),
                ).fetchone()
            return str(row["turn_id"]) if row is not None else None
        except Exception as e:
            logger.warning(f"last_turn_id {thread_id} failed: {e}")
            return None

    def pending_notes(self, thread_id: str, *, limit: int = 8) -> List[str]:
        """Contents of the ``origin='system'`` rows newer than the thread's
        last human row, oldest-first, at most ``limit`` of them.

        The hidden observations A6d writes (a retracted recall) live as
        ordinary rows at the tail of a thread, and ``ThreadManager.begin_turn``
        asks for them on every turn while holding the manager lock. Reading
        them by materialising the thread (``list_messages``) cost ~30 ms on a
        4k-row thread — every row built, its four JSON columns decoded — to
        look at the 0-1 rows that matter; this tail query costs ~0.003 ms
        because the last human row's id comes straight off ``idx_messages_conv``
        and the outer scan starts there (review: Plan A / A6d).

        The oldest notes are the ones kept when there are more than ``limit``:
        ``build_hint`` renders the head of the list, so a flood of new notes
        must not push the first one out of the hint.
        """
        if self._conn is None or limit <= 0:
            return []
        try:
            with self._lock:
                rows = self._conn.execute(
                    """SELECT content FROM messages
                       WHERE conversation_id = ?
                         AND origin = 'system' AND content <> ''
                         AND id > COALESCE((SELECT MAX(id) FROM messages
                                            WHERE conversation_id = ? AND origin = 'human'), 0)
                       ORDER BY id ASC LIMIT ?""",
                    (thread_id, thread_id, int(limit)),
                ).fetchall()
            return [r["content"] for r in rows]
        except Exception as e:
            logger.warning(f"pending_notes {thread_id} failed: {e}")
            return []

    def _turn_first_id(self, turn_id: str) -> Optional[int]:
        """First *visible* row id for a turn key -- must agree with
        ``_TURN_KEYS_SQL`` (also visible-only) or an anchor computed here
        can sit earlier than a turn's real timeline position when its
        lowest-id row happens to be hidden, silently excluding turns that
        genuinely precede it from a ``before_turn_id``/``around_turn_id``
        page (A1b round-3 review, finding 1)."""
        row = self._conn.execute(
            f"SELECT MIN(id) FROM messages WHERE {_TURN_KEY} = ? AND visible_in_timeline = 1",
            (turn_id,),
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
                    # Fetch up to `limit` on each side so a shortfall on one
                    # side can be topped up from the other -- otherwise a
                    # page anchored near either end of the timeline returns
                    # fewer than `limit` turns with nothing backfilling it.
                    before = self._conn.execute(
                        f"SELECT turn_key FROM ({_TURN_KEYS_SQL}) WHERE first_id < ? "
                        "ORDER BY first_id DESC LIMIT ?",
                        (anchor, limit),
                    ).fetchall()
                    after = self._conn.execute(
                        f"SELECT turn_key FROM ({_TURN_KEYS_SQL}) WHERE first_id >= ? "
                        "ORDER BY first_id ASC LIMIT ?",
                        (anchor, limit),
                    ).fetchall()
                    before_keys = [r["turn_key"] for r in before]  # newest-first
                    after_keys = [r["turn_key"] for r in after]  # oldest-first
                    want_before = limit // 2
                    want_after = limit - want_before
                    if len(before_keys) < want_before:
                        want_after = min(len(after_keys), want_after + (want_before - len(before_keys)))
                        want_before = len(before_keys)
                    elif len(after_keys) < want_after:
                        want_before = min(len(before_keys), want_before + (want_after - len(after_keys)))
                        want_after = len(after_keys)
                    keys = before_keys[:want_before][::-1] + after_keys[:want_after]
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
                # ``_fts_recover()``, not ``self._fts_ok`` directly: a stale
                # degraded flag from a past transient failure must not skip
                # this row forever -- the same rule A1 review finding 3 set
                # for every other FTS-gated caller in this file, which this
                # method (added by A3) had not been following (A3 review
                # finding 1).
                if self._fts_recover():
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

    def _fts_term_hits_map(self, terms: Sequence[str]) -> Dict[str, frozenset]:
        """Which thread_ids the real ``receipts_fts`` index matches, per
        query term, checked against the tokenizer/stemmer the index
        actually runs (``porter unicode61``) -- one MATCH per term, not
        one per candidate row per term.

        PERF NOTE (A3 review round 2, finding 1): the per-row version this
        replaced ran a MATCH scoped by ``thread_id = ?`` for every
        candidate row for every term, and ``thread_id`` is an UNINDEXED FTS
        column, so each of those queries scanned that term's whole posting
        list looking for one thread. With the default ``limit=5`` that was
        up to ``max(limit*4,20)=20`` candidate rows x up to 12 terms = up
        to 240 MATCH queries per ``search_receipts`` call, and
        ``search_receipts`` runs on every user turn (plan-a-contracts.md
        line 89; the plan's ``_gather_candidates``,
        CONTINUOUS-CONVERSATION-PLAN-A-2026-08-26.md:2588) -- i.e. on the
        interactive hot path, with cost growing with the corpus (measured:
        200 threads 10ms, 2 000 threads 51ms, 10 000 threads 267ms; >90%
        of that was the recheck). Running one MATCH per *term* here instead
        -- independent of how many rows are being scored -- cuts that to
        O(terms): measured ~3.5x faster (14.9ms @2k threads, 78.6ms @10k,
        12 queries instead of up to 160). See the PERF NOTE on
        ``_TURN_KEYS_SQL`` above for the same class of issue elsewhere in
        this file.

        A3 review finding 2 (unchanged rationale, now applied per term
        instead of per row): the crude local stem in ``_term_hits`` (drop
        the last letter past 4 chars) only catches suffixes exactly one
        letter long, so a real porter match on an -ing/-ed/-ion form (e.g.
        query "resilvering" against an indexed "resilver") scored zero
        locally even though the row was returned by the very MATCH query
        that used that same term. Re-asking FTS per term instead of
        re-implementing Porter in Python is by construction never out of
        step with what indexed the row: this table's OR-joined MATCH
        (``_fts_query``) guarantees at least one term individually matches
        any row it returns.
        """
        out: Dict[str, frozenset] = {}
        failed: Optional[Exception] = None
        for t in terms:
            try:
                with self._lock:
                    rows = self._conn.execute(
                        "SELECT thread_id FROM receipts_fts WHERE receipts_fts MATCH ?",
                        (_fts_query([t]),),
                    ).fetchall()
                out[t] = frozenset(r["thread_id"] for r in rows)
            except Exception as e:
                failed = e
                out[t] = frozenset()
        if failed is not None:
            # A3 review round 2, finding 2: log once per call, not once per
            # term -- the old per-row helper swallowed every exception with
            # a bare ``except Exception: hit = None`` and never logged at
            # all, contradicting this class's own documented contract
            # (docstring above: "methods log at WARNING ... rather than
            # raise") and every other except block in this file, all of
            # which log. A broken/corrupt receipts_fts fails every term the
            # same way, so one WARNING per call (not N) says the same thing
            # without spamming the log once per query term.
            logger.warning(
                "receipt term recheck against receipts_fts failed for one "
                f"or more terms (falling back to score=0.25 for affected "
                f"rows): {failed}"
            )
        return out

    def _receipt_hit(
        self,
        row: sqlite3.Row,
        terms: Sequence[str],
        *,
        real_fts: bool,
        term_hits: Optional[Dict[str, frozenset]] = None,
    ) -> Dict[str, Any]:
        """``real_fts=True`` for a row the ``receipts_fts`` MATCH query
        itself returned (re-derive matched terms from ``term_hits``, the
        per-term thread_id map from ``_fts_term_hits_map`` -- pass one map
        in once per ``search_receipts`` call rather than recomputing it per
        row; omitted here it is computed for just this one row, e.g. for a
        direct/standalone call); ``real_fts=False`` for a row found only
        via the title LIKE fallback, where there is no live FTS match to
        re-ask and the crude local stem is the best available signal."""
        if real_fts:
            if term_hits is None:
                term_hits = self._fts_term_hits_map(terms)
            matched = [t for t in terms if row["thread_id"] in term_hits.get(t, ())]
        else:
            haystack = f"{row['title'] or ''} {row['receipt'] or ''}".lower()
            matched = _term_hits(terms, haystack)
        # Two topical terms are enough for a full score; a single hit on a
        # one-word query also scores 1.0. Unverifiable FTS hits keep 0.25 --
        # kept as a defensive default (e.g. every per-term recheck above
        # raising); reachable rows can no longer land here empty by
        # construction now that ``matched`` is re-derived from the same
        # index that selected the row (finding 2).
        score = min(1.0, len(matched) / max(1, min(len(terms), 3))) if matched else 0.25
        # Parse topic_domains from the row (stored as JSON or comma-separated)
        raw_domains = row["topic_domains"] if "topic_domains" in row.keys() else None
        if isinstance(raw_domains, str):
            import json as _json
            try:
                topic_domains = _json.loads(raw_domains) if raw_domains else []
            except (ValueError, TypeError):
                topic_domains = []
        elif isinstance(raw_domains, (list, tuple)):
            topic_domains = list(raw_domains)
        else:
            topic_domains = []
        return {
            "thread_id": row["thread_id"],
            "title": row["title"] or "",
            "score": round(score, 3),
            "match_terms": matched,
            "snippet": _receipt_snippet(row["receipt"] or "", matched),
            "last_active": row["last_active"],
            "status": row["status"],
            "topic_domains": topic_domains,
        }

    def search_receipts(
        self, query: str, *, exclude_thread_id: Optional[str] = None,
        limit: int = 5, domains: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Rank threads by receipt/title relevance to ``query``.

        Query terms are quoted and OR-joined; the MATCH runs in its own try so
        an FTS failure degrades to the title LIKE pass instead of aborting.

        ``domains`` (R4): when provided, results whose ``topic_domains``
        overlap the given domains are ranked ahead of non-overlapping ones.
        This is a bleed-prevention ordering, not a hard filter — a
        same-domain hit is preferred but a cross-domain hit is never
        refused, so the user always gets an answer.
        """
        if self._conn is None or not query:
            return []
        terms = _fts_terms(query)
        if not terms:
            return []
        hits: Dict[str, Dict[str, Any]] = {}
        if self._fts_recover():
            try:
                with self._lock:
                    rows = self._conn.execute(
                        """SELECT r.thread_id, r.title, r.receipt,
                                  c.last_active, c.status, c.created_at,
                                  c.topic_domains
                           FROM receipts_fts r JOIN conversations c ON c.id = r.thread_id
                           WHERE receipts_fts MATCH ? AND c.status != 'merged'
                             AND c.ephemeral = 0 AND (? IS NULL OR r.thread_id != ?)
                           ORDER BY bm25(receipts_fts) LIMIT ?""",
                        (_fts_query(terms), exclude_thread_id, exclude_thread_id,
                         max(limit * 4, 20)),
                    ).fetchall()
                if rows:
                    # One term-hit map for every row, not one per row (A3
                    # review round 2, finding 1) -- see the PERF NOTE on
                    # ``_fts_term_hits_map`` above.
                    term_hits = self._fts_term_hits_map(terms)
                    for r in rows:
                        hits[r["thread_id"]] = self._receipt_hit(
                            r, terms, real_fts=True, term_hits=term_hits
                        )
            except Exception as e:
                logger.warning(f"receipt FTS search failed (LIKE fallback only): {e}")
        try:
            like_rows: List[sqlite3.Row] = []
            with self._lock:
                for term in terms[:6]:
                    like_rows.extend(self._conn.execute(
                        """SELECT id AS thread_id, title, receipt, last_active, status, created_at,
                                  topic_domains
                           FROM conversations
                           WHERE lower(title) LIKE ? AND status != 'merged' AND ephemeral = 0
                             AND (? IS NULL OR id != ?)
                           LIMIT ?""",
                        (f"%{term}%", exclude_thread_id, exclude_thread_id, limit),
                    ).fetchall())
            for r in like_rows:
                if r["thread_id"] not in hits:
                    hits[r["thread_id"]] = self._receipt_hit(r, terms, real_fts=False)
        except Exception as e:
            logger.warning(f"receipt title search failed: {e}")
        # R4: domain-aware ordering — prefer same-domain hits, never refuse cross-domain.
        domain_set = set(domains) if domains else set()
        if domain_set:
            for h in hits.values():
                h_domains = set(h.get("topic_domains") or [])
                h["scope_crossed"] = len(h_domains & domain_set) == 0
            ranked = sorted(
                hits.values(),
                key=lambda h: (h.get("scope_crossed", False), -h["score"], -(h["last_active"] or 0.0)),
            )
        else:
            ranked = sorted(
                hits.values(), key=lambda h: (-h["score"], -(h["last_active"] or 0.0))
            )
        return ranked[:limit]

    def search_snippets(self, thread_id: str, query: str, limit: int = 5) -> List[str]:
        """FTS snippets of one thread's messages matching ``query`` (best
        first), excluding hidden (``visible_in_timeline = 0``) rows -- the
        same rule every other reader in this file applies (A3 review finding
        3: internal bookkeeping rows such as A6d's retracted-recall marker
        must not surface as a user-facing recall snippet).
        """
        if self._conn is None or not query:
            return []
        terms = _fts_terms(query)
        if not terms:
            return []
        if not self._fts_recover():
            return []
        try:
            with self._lock:
                rows = self._conn.execute(
                    """SELECT snippet(messages_fts, 1, '', '', '…', 12) AS snip
                       FROM messages_fts
                       WHERE conversation_id = ? AND messages_fts MATCH ?
                         AND EXISTS (
                             SELECT 1 FROM messages m
                             WHERE m.id = messages_fts.rowid AND m.visible_in_timeline = 1
                         )
                       ORDER BY bm25(messages_fts) LIMIT ?""",
                    (thread_id, _fts_query(terms), int(limit)),
                ).fetchall()
            return [r["snip"] for r in rows if r["snip"]]
        except Exception as e:
            logger.warning(f"search_snippets {thread_id} failed: {e}")
            return []

    # ------------------------------------------------------------------
    # Merge-back (spec §5 "Merge")
    # ------------------------------------------------------------------

    def merge_thread(
        self, src_thread_id: str, dst_thread_id: str, *, now: Optional[float] = None
    ) -> Optional[int]:
        """Fold thread ``src`` into thread ``dst`` in one transaction.

        Moves every message row (and its ``messages_fts`` row) of ``src`` onto
        ``dst``, along with every other row keyed by thread (``open_loops``,
        ``terminal_blocks``, ``compact_boundaries``); marks ``src`` ``merged`` (``merged_into = dst``, receipt
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
                # ``_fts_recover()``, not ``self._fts_ok`` directly: a stale
                # flag from a transient connect-time failure would skip the
                # index while the rows move, and the recovery backfill only
                # inserts rows *missing* from ``messages_fts`` -- it can never
                # repair a row left pointing at the merged-away thread, so the
                # merged turns would stop being findable under the thread that
                # now owns them (A6c review finding 2). Safe here: the write
                # transaction is already open and ``_fts_recover`` leaves the
                # commit to this block.
                if self._fts_recover():
                    self._conn.execute(
                        "UPDATE messages_fts SET conversation_id = ? WHERE conversation_id = ?",
                        (dst_thread_id, src_thread_id),
                    )
                    self._conn.execute(
                        "DELETE FROM receipts_fts WHERE thread_id = ?", (src_thread_id,)
                    )
                # Everything else keyed by thread. The source thread is
                # about to be marked ``merged``, so any row left pointing at
                # it is unreachable from the thread that now owns the turns
                # which produced it -- the loops it opened, the shell blocks
                # it ran, the compaction boundaries drawn across it. These
                # move in the same transaction as the messages, so the merge
                # stays all-or-nothing.
                for table in ("open_loops", "terminal_blocks", "compact_boundaries"):
                    self._conn.execute(
                        f"UPDATE {table} SET thread_id = ? WHERE thread_id = ?",
                        (dst_thread_id, src_thread_id),
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

    # ------------------------------------------------------------------
    # terminal_blocks (Plan B: B1)
    # ------------------------------------------------------------------

    _TERMINAL_BLOCK_COLUMNS = (
        "block_id", "session_id", "thread_id", "turn_id", "command",
        "cwd", "owner", "interactive", "remote", "redacted",
        "started_at", "ended_at", "exit_code", "output_head", "output_tail",
        "execution_id", "output_elided_lines",
    )

    def insert_terminal_block(self, block: Dict[str, Any]) -> bool:
        """Insert or replace a terminal block row."""
        if self._conn is None:
            return False
        try:
            with self._lock, self._conn:
                cols = self._TERMINAL_BLOCK_COLUMNS
                placeholders = ", ".join("?" for _ in cols)
                values = tuple(block.get(c) for c in cols)
                self._conn.execute(
                    f"INSERT OR REPLACE INTO terminal_blocks ({', '.join(cols)}) "
                    f"VALUES ({placeholders})",
                    values,
                )
            return True
        except Exception as e:
            logger.warning(f"insert_terminal_block failed: {e}")
            return False

    #: ``thread_id``/``turn_id`` are updatable because a block cannot be born
    #: with them: the turn id is assigned when the turn is persisted, which is
    #: after every command in it has already run. ``end_turn`` stamps them on.
    _TERMINAL_BLOCK_UPDATABLE = frozenset(
        {"ended_at", "exit_code", "output_head", "output_tail",
         "interactive", "remote", "redacted", "thread_id", "turn_id",
         "execution_id", "output_elided_lines"}
    )

    def update_terminal_block(self, block_id: str, **fields: Any) -> bool:
        """Update one or more columns on a terminal block. Returns False if
        the block does not exist or no fields were given. ``last_state`` is
        special-cased: it updates the parent terminal_session's last_state
        and is a no-op if the session has already ended."""
        if self._conn is None:
            return False
        if not fields:
            return False
        # last_state is routed to the session row, not the block row.
        last_state = fields.pop("last_state", None)
        valid = {k: v for k, v in fields.items()
                 if k in self._TERMINAL_BLOCK_UPDATABLE}
        try:
            with self._lock, self._conn:
                updated = False
                if valid:
                    set_clause = ", ".join(f"{k} = ?" for k in valid)
                    row = self._conn.execute(
                        f"UPDATE terminal_blocks SET {set_clause} "
                        f"WHERE block_id = ?",
                        (*valid.values(), block_id),
                    )
                    updated = row.rowcount > 0
                if last_state is not None:
                    # Update the parent session's last_state unless it has
                    # already ended (no-op if session ended).
                    self._conn.execute(
                        "UPDATE terminal_sessions SET last_state = ? "
                        "WHERE session_id = (SELECT session_id FROM "
                        "terminal_blocks WHERE block_id = ?) "
                        "AND last_state NOT IN ('exited', 'killed', 'lost')",
                        (last_state, block_id),
                    )
                    updated = True
                return updated
        except Exception as e:
            logger.warning(f"update_terminal_block failed: {e}")
            return False

    def get_terminal_block(self, block_id: str) -> Optional[Dict[str, Any]]:
        if self._conn is None:
            return None
        try:
            with self._lock:
                row = self._conn.execute(
                    "SELECT * FROM terminal_blocks WHERE block_id = ?",
                    (block_id,),
                ).fetchone()
            if row is None:
                return None
            return dict(row)
        except Exception as e:
            logger.warning(f"get_terminal_block failed: {e}")
            return None

    def threads_with_open_blocks(self) -> set:
        """Thread ids that still have a terminal block running.

        A block is open until ``ended_at`` is written. Returned as one set
        rather than answered per thread so the close sweep, which walks up to
        200 rows, costs one query instead of two hundred.
        """
        if self._conn is None:
            return set()
        try:
            with self._lock:
                rows = self._conn.execute(
                    "SELECT DISTINCT thread_id FROM terminal_blocks "
                    "WHERE ended_at IS NULL AND thread_id IS NOT NULL"
                ).fetchall()
            return {r[0] for r in rows}
        except Exception as e:
            logger.warning(f"threads_with_open_blocks failed: {e}")
            return set()

    def list_terminal_blocks(
        self,
        *,
        session_id: Optional[str] = None,
        thread_id: Optional[str] = None,
        turn_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """List terminal blocks, newest-first by started_at. At most one
        filter is applied; if none, all blocks up to *limit*."""
        if self._conn is None:
            return []
        try:
            with self._lock:
                where = ""
                params: List[Any] = []
                if session_id is not None:
                    where = "WHERE session_id = ?"
                    params.append(session_id)
                elif thread_id is not None:
                    where = "WHERE thread_id = ?"
                    params.append(thread_id)
                elif turn_id is not None:
                    where = "WHERE turn_id = ?"
                    params.append(turn_id)
                params.append(limit)
                rows = self._conn.execute(
                    f"SELECT * FROM terminal_blocks {where} "
                    f"ORDER BY started_at DESC LIMIT ?",
                    params,
                ).fetchall()
            return [dict(r) for r in rows]
        except Exception as e:
            logger.warning(f"list_terminal_blocks failed: {e}")
            return []

    # ------------------------------------------------------------------
    # terminal_sessions (Plan B: B1)
    # ------------------------------------------------------------------

    _TERMINAL_SESSION_COLUMNS = (
        "session_id", "kind", "owner", "watched",
        "spawned_at", "ended_at", "last_state",
    )

    def insert_terminal_session(self, session: Dict[str, Any]) -> bool:
        """Insert or replace a terminal session row."""
        if self._conn is None:
            return False
        try:
            with self._lock, self._conn:
                cols = self._TERMINAL_SESSION_COLUMNS
                placeholders = ", ".join("?" for _ in cols)
                values = tuple(session.get(c) for c in cols)
                self._conn.execute(
                    f"INSERT OR REPLACE INTO terminal_sessions ({', '.join(cols)}) "
                    f"VALUES ({placeholders})",
                    values,
                )
            return True
        except Exception as e:
            logger.warning(f"insert_terminal_session failed: {e}")
            return False

    def update_terminal_session(self, session_id: str, **fields: Any) -> bool:
        """Update one or more columns on a terminal session. Returns False if
        the session does not exist or no fields were given."""
        if self._conn is None:
            return False
        if not fields:
            return False
        valid = {k: v for k, v in fields.items() if k in self._TERMINAL_SESSION_COLUMNS}
        if not valid:
            return False
        try:
            with self._lock, self._conn:
                set_clause = ", ".join(f"{k} = ?" for k in valid)
                row = self._conn.execute(
                    f"UPDATE terminal_sessions SET {set_clause} "
                    f"WHERE session_id = ?",
                    (*valid.values(), session_id),
                )
                return row.rowcount > 0
        except Exception as e:
            logger.warning(f"update_terminal_session failed: {e}")
            return False

    def get_terminal_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        if self._conn is None:
            return None
        try:
            with self._lock:
                row = self._conn.execute(
                    "SELECT * FROM terminal_sessions WHERE session_id = ?",
                    (session_id,),
                ).fetchone()
            if row is None:
                return None
            return dict(row)
        except Exception as e:
            logger.warning(f"get_terminal_session failed: {e}")
            return None

    def list_terminal_sessions(
        self,
        *,
        kind: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """List terminal sessions, newest-first by spawned_at."""
        if self._conn is None:
            return []
        try:
            with self._lock:
                if kind is not None:
                    rows = self._conn.execute(
                        "SELECT * FROM terminal_sessions WHERE kind = ? "
                        "ORDER BY spawned_at DESC LIMIT ?",
                        (kind, limit),
                    ).fetchall()
                else:
                    rows = self._conn.execute(
                        "SELECT * FROM terminal_sessions "
                        "ORDER BY spawned_at DESC LIMIT ?",
                        (limit,),
                    ).fetchall()
            return [dict(r) for r in rows]
        except Exception as e:
            logger.warning(f"list_terminal_sessions failed: {e}")
            return []

    # ------------------------------------------------------------------
    # open_loops (continuity R2-N2)
    # ------------------------------------------------------------------

    def add_open_loop(
        self,
        thread_id: str,
        text: str,
        *,
        domain: Optional[str] = None,
        source: Optional[str] = None,
        created_at: Optional[float] = None,
    ) -> Optional[int]:
        """Record an open loop for a thread. Returns the row id, or None on failure."""
        if self._conn is None:
            return None
        import time as _time
        try:
            with self._lock:
                cur = self._conn.execute(
                    "INSERT INTO open_loops (thread_id, text, domain, created_at, source) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (thread_id, text, domain, created_at or _time.time(), source),
                )
            self._conn.commit()
            return cur.lastrowid
        except Exception as e:
            logger.warning(f"add_open_loop failed: {e}")
            return None

    def list_open_loops(
        self,
        thread_id: str,
        *,
        open_only: bool = True,
    ) -> List[Dict[str, Any]]:
        """List open loops for a thread. By default, only unclosed loops."""
        if self._conn is None:
            return []
        try:
            with self._lock:
                if open_only:
                    rows = self._conn.execute(
                        "SELECT * FROM open_loops WHERE thread_id = ? AND closed_at IS NULL "
                        "ORDER BY created_at ASC",
                        (thread_id,),
                    ).fetchall()
                else:
                    rows = self._conn.execute(
                        "SELECT * FROM open_loops WHERE thread_id = ? "
                        "ORDER BY created_at ASC",
                        (thread_id,),
                    ).fetchall()
            return [dict(r) for r in rows]
        except Exception as e:
            logger.warning(f"list_open_loops failed: {e}")
            return []

    def close_open_loop(self, loop_id: int, *, closed_at: Optional[float] = None) -> bool:
        """Close an open loop by setting closed_at. Returns True on success."""
        if self._conn is None:
            return False
        import time as _time
        try:
            with self._lock:
                self._conn.execute(
                    "UPDATE open_loops SET closed_at = ? WHERE id = ? AND closed_at IS NULL",
                    (closed_at or _time.time(), loop_id),
                )
            self._conn.commit()
            return True
        except Exception as e:
            logger.warning(f"close_open_loop failed: {e}")
            return False

    # ------------------------------------------------------------------
    # Migration (Plan B: B21)
    # ------------------------------------------------------------------

    def migrate_terminal_block_ids_to_blocks(self) -> int:
        """Migrate messages.terminal_block_ids from session ids to block ids.

        For every message with non-empty terminal_block_ids:
          for each session_id in the list, find terminal_blocks rows with
          that session_id, collect their block_ids, and replace the
          session_id with the block_ids.

        Returns the number of messages updated. Idempotent (a session_id
        that has no terminal_blocks rows is left as-is — it was a one-shot
        that never persisted a block). Runs once at boot after schema
        migration.
        """
        if self._conn is None:
            return 0
        try:
            with self._lock:
                rows = self._conn.execute(
                    "SELECT id, terminal_block_ids FROM messages "
                    "WHERE terminal_block_ids IS NOT NULL "
                    "AND terminal_block_ids != '[]'"
                ).fetchall()
            updated = 0
            for row in rows:
                msg_id = row["id"]
                try:
                    ids = json.loads(row["terminal_block_ids"])
                except (json.JSONDecodeError, TypeError):
                    continue
                if not ids:
                    continue
                new_ids: List[str] = []
                changed = False
                for sid in ids:
                    # Check if this id is already a block_id
                    block = self.get_terminal_block(sid)
                    if block is not None:
                        new_ids.append(sid)
                        continue
                    # It's a session_id — find blocks for this session
                    blocks = self.list_terminal_blocks(session_id=sid, limit=100)
                    if blocks:
                        new_ids.extend(b["block_id"] for b in blocks)
                        changed = True
                    else:
                        # No blocks found — leave as-is (one-shot, never persisted)
                        new_ids.append(sid)
                if changed:
                    with self._lock, self._conn:
                        self._conn.execute(
                            "UPDATE messages SET terminal_block_ids = ? "
                            "WHERE id = ?",
                            (json.dumps(new_ids), msg_id),
                        )
                    updated += 1
            if updated:
                logger.info(f"migrate_terminal_block_ids_to_blocks: updated {updated} messages")
            return updated
        except Exception as e:
            logger.warning(f"migrate_terminal_block_ids_to_blocks failed: {e}")
            return 0

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None
