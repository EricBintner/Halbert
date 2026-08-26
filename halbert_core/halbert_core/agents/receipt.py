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

# Every interpolated field is capped and run through `_clip`, which flattens
# embedded whitespace (including newlines) before truncating. Without this,
# a multi-line title, domain, entity, or file path — any of which may be
# model-authored (diff proposals) or come straight off disk with only
# `.strip()` (A18's JSON migration) — could inject a forged labelled line
# (e.g. a bogus "Open loop: ...") into the middle of the nine-line receipt,
# which is then quoted verbatim into the prompt and the recall hint.
_TITLE_LINE_MAX = 200
_DOMAIN_ITEM_MAX = 60
_ENTITY_ITEM_MAX = 80
_FILE_ITEM_MAX = 80
# entities_json accumulates every turn (A6); cap it so the unbounded field
# can't crowd the fixed max_chars budget and truncate "Open loop" — the
# last, and most operationally important, section — out of the receipt.
_MAX_ENTITIES = 12
_SUPERSEDED = "superseded"
# Bound the per-turn refresh cost: a thread is designed never to end, so
# scanning every stored message on every `end_turn`/redaction is O(n) per
# call and O(n^2) over the thread's life. Only the first message (for
# "Started with") and the most recent `tail` rows are examined.
_DEFAULT_TAIL = 64


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


def _is_superseded(block: Dict[str, Any]) -> bool:
    """A confirmation staged then abandoned when its turn was superseded
    (spec §5): ``{tool, args, result: "not run — superseded", exit: None,
    status: "superseded"}``. Checked on ``status`` first, falling back to
    a string ``result`` in case a caller omits ``status``."""
    if str(block.get("status") or "").strip().lower() == _SUPERSEDED:
        return True
    result = block.get("result")
    return isinstance(result, str) and _SUPERSEDED in result.lower()


def _command_suffix(block: Dict[str, Any]) -> str:
    if _is_superseded(block):
        return "(not run — superseded)"
    return f"(exit {_exit_of(block)})"


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
        lines.append(f"{_clip(cmd, 80)} {_command_suffix(block)}")
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


def build_receipt(
    thread: Dict[str, Any],
    messages: List[Dict[str, Any]],
    *,
    max_chars: int = 1500,
    tail: int = _DEFAULT_TAIL,
) -> str:
    """Render the nine-line receipt for ``thread`` from its stored ``messages``.

    ``messages`` rows are ``SqliteConversationStore.list_messages`` dicts
    (role, content, timestamp, origin, turn_id, blocks, diff_proposals).

    ``messages`` may be the thread's entire history. Only the first row
    (needed for "Started with") and the most recent ``tail`` rows are
    scanned — a per-turn refresh stays O(tail) rather than O(len(history))
    on a conversation designed never to end.
    """
    if len(messages) > tail + 1:
        window = [messages[0], *messages[-tail:]]
    else:
        window = messages
    title = _clip(thread.get("title") or "Untitled", _TITLE_LINE_MAX)
    human = [m for m in window if m.get("role") == "user" and (m.get("origin") or "human") == "human"]
    assistant = [m for m in window if m.get("role") == "assistant"]
    stamps = [float(m["timestamp"]) for m in window if m.get("timestamp") is not None]
    turn_keys = {
        m.get("turn_id") or f"m{m.get('message_id', i)}"
        for i, m in enumerate(window) if m.get("role") == "user"
    }
    # thread.turn_count is the authoritative counter maintained incrementally
    # by the caller (A6); prefer it over counting turn_ids in `window`, which
    # only sees a bounded slice of history once a thread outgrows `tail`.
    n_turns = int(thread.get("turn_count") or 0) or len(turn_keys)
    when = f"{_date(min(stamps))}..{_date(max(stamps))} · {n_turns} turns" if stamps else "unknown"
    domains = ", ".join(_clip(d, _DOMAIN_ITEM_MAX) for d in (thread.get("topic_domains") or [])) or "none"
    entities = ", ".join(
        _clip(e, _ENTITY_ITEM_MAX) for e in (thread.get("entities_json") or [])[:_MAX_ENTITIES]
    ) or "none"
    started = _clip(human[0].get("content"), 160) if human else "none"
    last_said = first_sentence(assistant[-1].get("content") or "", 200) if assistant else "none"
    blocks: List[Dict[str, Any]] = []
    diffs: List[Dict[str, Any]] = []
    for m in window:
        blocks.extend(m.get("blocks") or [])
        diffs.extend(m.get("diff_proposals") or [])
    commands = "; ".join(_command_lines(blocks)[-8:]) or "none"
    files = "; ".join(_clip(p, _FILE_ITEM_MAX) for p in _file_lines(blocks, diffs)[-8:]) or "none"
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
