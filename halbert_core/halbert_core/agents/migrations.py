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

A thread is written across several store calls, so a run can die between
them (SQLITE_BUSY at boot, a full disk, ``kill -9``). The ``migrations_done``
row is therefore written ``partial`` *before* the thread and flipped to
``done`` only once the thread is complete: a half-written thread is deleted
on the spot when the failure is catchable, and the surviving ``partial`` row
tells the next run to drop whatever is left under that id and import the
file again. Without that marker the next run would find a truncated, still
**open** thread, mistake it for a live conversation, and record the file as
done forever (A12a review finding 1).
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

#: ``migrations_done.state`` values. ``_PARTIAL`` is written before the thread
#: exists and means "this file's thread may be half-written, repair it";
#: ``_DONE`` means the file is finished with, forever.
_PARTIAL = "partial"
_DONE = "done"


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
                    "migrated_at REAL NOT NULL, "
                    f"state       TEXT NOT NULL DEFAULT '{_DONE}')"
                )
                # A table written by a build that predates the partial/done
                # marker has no ``state`` column. Every row it holds was
                # written only after a thread was complete, so the column
                # default backfills them all as ``done`` correctly.
                columns = {
                    row[1]
                    for row in conn.execute("PRAGMA table_info(migrations_done)").fetchall()
                }
                if "state" not in columns:
                    conn.execute(
                        "ALTER TABLE migrations_done ADD COLUMN "
                        f"state TEXT NOT NULL DEFAULT '{_DONE}'"
                    )
        return True
    except Exception as e:
        logger.warning(f"migrations_done table unavailable: {e}")
        return False


def _migration_row(
    store: SqliteConversationStore, source_path: str
) -> Optional[Dict[str, Any]]:
    """``{"thread_id", "state"}`` for an already-seen source file, else None."""
    with _lock_of(store):
        row = store._conn.execute(
            "SELECT thread_id, state FROM migrations_done WHERE source_path = ?",
            (source_path,),
        ).fetchone()
    if row is None:
        return None
    return {"thread_id": row[0], "state": row[1] or _DONE}


def _record(
    store: SqliteConversationStore, source_path: str, thread_id: str, state: str
) -> None:
    with _lock_of(store):
        with store._conn:
            store._conn.execute(
                "INSERT OR REPLACE INTO migrations_done "
                "(source_path, thread_id, migrated_at, state) VALUES (?, ?, ?, ?)",
                (source_path, thread_id, time.time(), state),
            )


def _discard_partial(store: SqliteConversationStore, thread_id: Optional[str]) -> None:
    """Drop the thread a previous, interrupted run left half-written.

    Safe to delete: this id is only ever recorded ``partial`` after the run
    that recorded it proved no thread was using it, and new threads take
    ``uuid4().hex`` ids, so nothing else can have claimed it since.
    """
    if not thread_id or store.get_thread(thread_id) is None:
        return
    logger.warning(
        f"migration: discarding the half-written thread {thread_id} left by an "
        "interrupted run and importing its source file again"
    )
    store.delete(thread_id)


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
    """Write one thread, deleting it again if any step refuses.

    Returns False (after a WARNING) if any store call refused or raised. The
    caller proved this id was free immediately before calling, so anything
    written under it here is ours: dropping it keeps a transient failure from
    stranding a truncated, still-open, unrecallable thread — which
    ``current_open_thread()`` would then hand to the very next turn.
    """
    tid = rec["thread_id"]
    try:
        if _build_thread(store, rec):
            return True
    except Exception as e:
        logger.warning(f"migration: writing thread {tid} raised {e}")
    if store.get_thread(tid) is not None and not store.delete(tid):
        logger.error(
            f"migration: could not remove the half-written thread {tid}; its "
            "source file stays recorded partial so the next run repairs it"
        )
    return False


def _build_thread(store: SqliteConversationStore, rec: Dict[str, Any]) -> bool:
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
            seen = _migration_row(store, source)
            if seen is not None and seen["state"] == _DONE:
                continue
            if seen is not None:
                # An earlier run died between recording this file and
                # finishing its thread. Clear what it left before the
                # "already exists" check below can mistake it for a live one.
                _discard_partial(store, seen["thread_id"])
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            rec = _normalise(data, file_path.stat().st_mtime)
            if rec is None:
                logger.warning(f"migration skipped {file_path}: unrecognised shape")
                continue
            if not rec["messages"]:
                _record(store, source, rec["thread_id"], _DONE)
                continue
            if store.get_thread(rec["thread_id"]) is not None:
                logger.info(
                    f"migration: thread {rec['thread_id']} already exists, "
                    f"leaving it and recording {file_path.name} as done"
                )
                _record(store, source, rec["thread_id"], _DONE)
                continue
            _record(store, source, rec["thread_id"], _PARTIAL)
            if _write_thread(store, rec):
                _record(store, source, rec["thread_id"], _DONE)
                migrated += 1
            else:
                logger.warning(
                    f"migration of {file_path} did not complete; it stays "
                    "recorded partial and is imported again on the next run"
                )
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
