# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""One-time migration of the two legacy JSON conversation stores into the
SQLite thread store (spec §8, Plan A).

Two on-disk shapes existed before Plan A:

* ``~/.halbert/conversations/*.json`` — the old ``agents/conversation.py``
  ``ConversationStore`` shape: ``conversation_id``, ``title``, ``messages``
  with float ``timestamp`` values. A message's ``content`` may already be a
  block list (``agents/blocks.py``).
* ``~/.config/halbert/conversations/*.json`` — the old
  ``dashboard/routes/conversations.py`` shape: ``id``, ``name``, ``persona``,
  ``messages`` with ISO-8601 ``timestamp`` strings and a per-message
  ``tool_calls`` list.

Every file becomes one **closed** thread with a deterministic receipt so
recall can find it. Idempotent: each source path is recorded in a
``migrations_done`` table once its thread is fully written and is never read
again. Files that fail to parse are skipped (WARNING), not recorded, and
retried on the next boot. Counts only successful saves.

This is a one-way door — A12c/A12d delete both source stores — so the
message *structure* is carried across too, not just the text: block-typed
content and ``tool_calls`` become ``messages.blocks_json``, which is what
makes the receipt's "Commands" and "Files written" lines (the two a sysadmin
agent is most often asked for) answerable about a migrated thread at all
(review round 2, finding 4).

A thread is written across several store calls, so a run can die between
them (SQLITE_BUSY at boot, a full disk, ``kill -9``). The ``migrations_done``
row is therefore written ``partial`` *before* the thread and flipped to
``done`` only once the thread is complete: a half-written thread is deleted
on the spot when the failure is catchable, and the surviving ``partial`` row
tells the next run to drop whatever that run left behind and import the file
again. Without that marker the next run would find a truncated, still
**open** thread, mistake it for a live conversation, and record the file as
done forever (A12a review finding 1).

Two things make "drop whatever that run left behind" safe to say:

* nothing is deleted unless it can be *shown* to be this migration's own
  half-written import — the thread carries a ``migrated_from`` metadata
  marker naming its source file, and its rows must still be a prefix of what
  that file says (review round 2, finding 1). A live thread that has since
  claimed the same id is left alone;
* the repair does not depend on the source file surviving. Rows still
  ``partial`` whose source is gone are swept at the end of every run, so a
  remnant cannot outlive the store it came from — which A12c/A12d delete on
  purpose (review round 2, finding 2).
"""

from __future__ import annotations

import contextlib
import json
import logging
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from ..intake.signals import analyze_message, canonical_entities
from .blocks import content_to_anthropic, content_to_text
from .conversation import Conversation
from .conversation_sqlite import SqliteConversationStore
from .receipt import build_receipt, provisional_title
from .threads import MAX_THREAD_ENTITIES

logger = logging.getLogger("halbert.agents.migrations")

AGENT_JSON_DIR = Path.home() / ".halbert" / "conversations"
LEGACY_JSON_DIR = Path.home() / ".config" / "halbert" / "conversations"

_ROLE_ORIGIN = {"user": "human", "assistant": "assistant", "system": "system"}

#: ``migrations_done.state`` values. ``_PARTIAL`` is written before the thread
#: exists and means "this file's thread may be half-written, repair it";
#: ``_DONE`` means the file is finished with, forever.
_PARTIAL = "partial"
_DONE = "done"

#: Thread metadata key naming the file a migrated thread was built from. It
#: is the proof of ownership the repair path needs before it deletes
#: anything, and useful provenance afterwards.
_SOURCE_META_KEY = "migrated_from"

#: Same ceiling ``state_machine._tool_block`` puts on a persisted tool
#: result: a legacy ``tool_calls`` entry can carry a whole command's stdout,
#: and ``blocks_json`` is read back on every receipt rebuild.
_MAX_BLOCK_RESULT = 4000


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


def _forget(store: SqliteConversationStore, source_path: str) -> None:
    """Drop a bookkeeping row entirely, so the file starts from scratch if it
    ever comes back."""
    with _lock_of(store):
        with store._conn:
            store._conn.execute(
                "DELETE FROM migrations_done WHERE source_path = ?", (source_path,)
            )


# ---------------------------------------------------------------------------
# Proving a leftover thread is ours before deleting it
# ---------------------------------------------------------------------------

def _is_complete(thread: Dict[str, Any]) -> bool:
    """Did a migration finish this thread? Closed *and* carrying a receipt is
    the last thing ``_build_thread`` does, so both together mean the only
    step left was the bookkeeping flip."""
    return (
        str(thread.get("status") or "") == "closed"
        and bool(str(thread.get("receipt") or "").strip())
    )


def _marks_source(thread: Dict[str, Any], source_path: str) -> bool:
    meta = thread.get("metadata")
    return isinstance(meta, dict) and meta.get(_SOURCE_META_KEY) == source_path


def _rows_match_source(
    store: SqliteConversationStore,
    thread: Dict[str, Any],
    rec: Optional[Dict[str, Any]],
) -> bool:
    """Are this thread's rows still a prefix of what ``rec`` says they should be?

    Second, independent proof of ownership: it holds for a thread written
    before ``migrated_from`` existed, and for one whose metadata a later
    writer replaced. It cannot hold for a live conversation that claimed the
    id, whose rows and title are its own.
    """
    if rec is None or thread.get("title") != rec["title"]:
        return False
    rows = store.list_messages(thread.get("thread_id") or thread.get("id"))
    source = rec["messages"]
    if not rows or len(rows) > len(source):
        return False
    for row, message in zip(rows, source):
        if row.get("role") != message["role"]:
            return False
        if str(row.get("content") or "") != message["content"]:
            return False
        try:
            if float(row.get("timestamp")) != float(message["timestamp"]):
                return False
        except (TypeError, ValueError):
            return False
    return True


def _discard_remnant(
    store: SqliteConversationStore,
    source_path: str,
    thread_id: Optional[str],
    rec: Optional[Dict[str, Any]] = None,
) -> bool:
    """Delete ``thread_id`` iff it is this source file's own half-written import.

    Deleting on the id alone would be a data-loss path the moment anything
    else can create a thread under a caller-supplied id (``save`` /
    ``create`` / ``get_or_create`` all accept one, and A12b/A12c wire legacy
    ids through them): a live thread that had claimed the id would be
    silently replaced by the stale JSON. So a delete needs proof — the
    ``migrated_from`` marker, or rows that are still a prefix of the source —
    and a finished thread is never touched (review round 2, finding 1).
    """
    if not thread_id:
        return False
    thread = store.get_thread(thread_id)
    if thread is None or _is_complete(thread):
        return False
    if not (_marks_source(thread, source_path) or _rows_match_source(store, thread, rec)):
        logger.warning(
            f"migration: thread {thread_id} is recorded partial for {source_path} but "
            "is not that import's own half-written remains; leaving it untouched"
        )
        return False
    logger.warning(
        f"migration: discarding the half-written thread {thread_id} left by an "
        f"interrupted import of {source_path}"
    )
    return store.delete(thread_id)


def _sweep_orphaned_partials(store: SqliteConversationStore) -> int:
    """Drop half-written threads whose source file no longer exists.

    ``_migrate_dir`` can only repair a remnant while the file it came from is
    still there to import again. But A12c/A12d delete both legacy stores on
    purpose, and a user can delete them by hand, so "interrupted, then the
    source went away" is a state to expect rather than an impossibility.
    Left alone the remnant stays **open** for good: ``current_open_thread()``
    hands it to the very next turn as if it were a live conversation, and it
    is truncated and unrecallable (no receipt). Only threads that still prove
    they are ours are dropped; a complete one — the run died on the final
    bookkeeping write — is kept and its row simply flipped to done (review
    round 2, finding 2).
    """
    try:
        with _lock_of(store):
            rows = store._conn.execute(
                "SELECT source_path, thread_id FROM migrations_done WHERE state = ?",
                (_PARTIAL,),
            ).fetchall()
    except Exception as e:
        logger.warning(f"migration: could not read the partial bookkeeping rows: {e}")
        return 0
    dropped = 0
    for row in rows:
        source_path, thread_id = row[0], row[1]
        try:
            if Path(source_path).exists():
                continue  # the file is still there; _migrate_dir repairs it
            thread = store.get_thread(thread_id) if thread_id else None
            if thread is None:
                _forget(store, source_path)
                continue
            if _is_complete(thread) or not _marks_source(thread, source_path):
                _record(store, source_path, thread_id, _DONE)
                continue
            logger.warning(
                f"migration: dropping the half-written thread {thread_id}; the source "
                f"{source_path} it came from is gone, so it can never be completed"
            )
            if store.delete(thread_id):
                _forget(store, source_path)
                dropped += 1
        except Exception as e:
            logger.warning(f"migration: sweeping {source_path} failed: {e}")
    return dropped


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


def _clip_result(value: Any) -> Any:
    if isinstance(value, str) and len(value) > _MAX_BLOCK_RESULT:
        return value[:_MAX_BLOCK_RESULT] + "…"
    if isinstance(value, (str, int, float, bool, dict, list, type(None))):
        return value
    return str(value)


def _tool_call_block(raw: Any) -> Optional[Dict[str, Any]]:
    """One legacy ``tool_calls`` entry as a receipt-readable block.

    ``receipt._tool_name`` / ``_args_of`` / ``_exit_of`` read ``tool``/``name``,
    ``args``/``input`` and ``exit``, so the block only has to name the tool and
    carry its arguments to make the "Commands" and "Files written" lines work.
    Both the Anthropic ``tool_use`` shape and an OpenAI ``function`` entry are
    accepted, because the dashboard's ``tool_calls`` was only ever typed as
    ``List[Dict[str, Any]]`` and never written by one code path.
    """
    if not isinstance(raw, dict):
        return None
    function = raw.get("function") if isinstance(raw.get("function"), dict) else {}
    name = raw.get("tool") or raw.get("name") or function.get("name")
    if not name:
        return None
    args: Any = None
    for key in ("args", "input", "arguments", "parameters"):
        if raw.get(key) is not None:
            args = raw[key]
            break
    if args is None:
        args = function.get("arguments")
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except ValueError:
            args = {"value": args}
    if not isinstance(args, dict):
        args = {} if args is None else {"value": args}
    block: Dict[str, Any] = {"type": "tool_use", "tool": str(name), "args": args}
    for key in ("result", "exit", "status", "error"):
        if raw.get(key) is not None:
            block[key] = _clip_result(raw[key])
    return block


def _message_blocks(raw: Dict[str, Any], content: Any) -> List[Dict[str, Any]]:
    """The structured half of one legacy message.

    Block-typed ``content`` keeps its blocks (exactly what ``append_message``
    would have derived had the content not been stringified first), and the
    dashboard shape's ``tool_calls`` are appended after them.
    """
    blocks: List[Dict[str, Any]] = []
    if isinstance(content, list):
        for block in content_to_anthropic(content):
            if isinstance(block, dict):
                out = dict(block)
                if "content" in out:
                    out["content"] = _clip_result(out["content"])
                blocks.append(out)
    for call in raw.get("tool_calls") or ():
        block = _tool_call_block(call)
        if block is not None:
            blocks.append(block)
    return blocks


def _normalise(data: Any, file_mtime: float) -> Optional[Dict[str, Any]]:
    """Reduce either JSON shape to one record, or None if unrecognised.

    Record: ``{thread_id, title, user_id, created_at, updated_at,
    messages: [{role, content, timestamp, blocks}]}`` — messages in file
    order, timestamps as floats (a missing timestamp inherits the previous
    row's). A message with neither text nor blocks is dropped; one with only
    blocks is kept, because its tool calls are the part of the record the
    receipt is built from.
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
        blocks = _message_blocks(raw, content)
        if isinstance(content, list):
            text = content_to_text(content).strip()
        else:
            text = str(content or "").strip()
        if not text and not blocks:
            continue
        ts = _parse_timestamp(raw.get("timestamp"), last_ts)
        last_ts = ts
        messages.append(
            {"role": role, "content": text, "timestamp": ts, "blocks": blocks}
        )

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
# Topic sets
# ---------------------------------------------------------------------------

def _thread_domains(messages: Sequence[Dict[str, Any]]) -> List[str]:
    """Domains detected across the thread's human messages."""
    domains = set()
    for message in messages:
        if message["role"] != "user" or not message["content"].strip():
            continue
        domains.update(analyze_message(message["content"]).detected_domains)
    return sorted(domains)


def _thread_entities(messages: Sequence[Dict[str, Any]]) -> List[str]:
    """Entities harvested per message, newest-first down to the same ceiling
    a live thread keeps.

    One ``canonical_entities`` call over the concatenated thread stops at
    ``intake.signals._ENTITY_SCAN_LIMIT`` (16 KB), so on a long thread every
    subject raised after the first few turns contributes nothing and the
    thread is unrecallable by entity for good — this migration is the only
    time these rows are ever indexed. Per-message harvesting is what every
    live writer does (``threads._topic_sets``), and its
    ``MAX_THREAD_ENTITIES`` cap matters here too: ``entities_json`` is what
    ``thread_signals._gather_candidates`` overlaps against, so a wide thread
    that kept every entity it ever mentioned becomes a recall magnet
    (review round 2, finding 3).
    """
    last_seen: Dict[str, int] = {}
    for index, message in enumerate(messages):
        for entity in canonical_entities(message["content"]):
            last_seen[str(entity)] = index
    if len(last_seen) > MAX_THREAD_ENTITIES:
        # Same tie-break as `threads._age_topics`: newest first, then name.
        last_seen = dict(
            sorted(last_seen.items(), key=lambda kv: (-kv[1], kv[0]))[:MAX_THREAD_ENTITIES]
        )
    return sorted(last_seen)


# ---------------------------------------------------------------------------
# Writing one thread
# ---------------------------------------------------------------------------

def _write_thread(
    store: SqliteConversationStore, rec: Dict[str, Any], source_path: str
) -> bool:
    """Write one thread, deleting it again if any step refuses.

    Returns False (after a WARNING) if any store call refused or raised. The
    caller proved this id was free immediately before calling, so anything
    written under it here is ours: dropping it keeps a transient failure from
    stranding a truncated, still-open, unrecallable thread — which
    ``current_open_thread()`` would then hand to the very next turn.
    """
    tid = rec["thread_id"]
    try:
        if _build_thread(store, rec, source_path):
            return True
    except Exception as e:
        logger.warning(f"migration: writing thread {tid} raised {e}")
    if store.get_thread(tid) is not None and not store.delete(tid):
        logger.error(
            f"migration: could not remove the half-written thread {tid}; its "
            "source file stays recorded partial so the next run repairs it"
        )
    return False


def _build_thread(
    store: SqliteConversationStore, rec: Dict[str, Any], source_path: str
) -> bool:
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
        metadata={_SOURCE_META_KEY: source_path},
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
            blocks=m["blocks"] or None,
            timestamp=m["timestamp"],
        )
        if message_id is None:
            logger.warning(f"migration: append_message failed for thread {tid}")
            return False
        rows.append({
            "role": role, "content": m["content"], "timestamp": m["timestamp"],
            "origin": origin, "turn_id": turn_id, "blocks": m["blocks"],
        })
        if role == "assistant":
            turn_id = None

    domains = _thread_domains(rec["messages"])
    entities = _thread_entities(rec["messages"])

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
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            rec = _normalise(data, file_path.stat().st_mtime)
            if rec is None:
                logger.warning(f"migration skipped {file_path}: unrecognised shape")
                continue
            if not rec["messages"]:
                _record(store, source, rec["thread_id"], _DONE)
                continue
            if seen is not None:
                # An earlier run died between recording this file and
                # finishing its thread. Clear only what that run itself
                # wrote — under the id the file names now and, if the file
                # has been re-keyed since, under the recorded one — before
                # the "already exists" check below can mistake a remnant for
                # a live thread. Reading the file first is what makes
                # "is this remnant really ours?" answerable at all.
                for candidate in dict.fromkeys((rec["thread_id"], seen["thread_id"])):
                    _discard_remnant(store, source, candidate, rec)
            if store.get_thread(rec["thread_id"]) is not None:
                logger.info(
                    f"migration: thread {rec['thread_id']} already exists, "
                    f"leaving it and recording {file_path.name} as done"
                )
                _record(store, source, rec["thread_id"], _DONE)
                continue
            _record(store, source, rec["thread_id"], _PARTIAL)
            if _write_thread(store, rec, source):
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
    # Anything still recorded partial whose file has gone can never be
    # repaired by re-import; drop it rather than leave an open remnant.
    _sweep_orphaned_partials(store)
    if counts["agent_json"] or counts["legacy_json"]:
        logger.info(
            f"Migrated legacy conversations into threads: "
            f"{counts['agent_json']} agent JSON, {counts['legacy_json']} dashboard JSON"
        )
    return counts
