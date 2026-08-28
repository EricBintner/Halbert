# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Thread segmentation (spec §4.3, §5, §6) and the ``<continuity>`` hint (§7).

``decide`` is pure over its inputs plus two read-only store calls
(``search_receipts``, ``list_threads``); ``build_hint`` renders the
deterministic hint the prompt layer places before the current task.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..intake.signals import MessageSignals
from .receipt import receipt_one_liner

logger = logging.getLogger("halbert.agents.thread_signals")

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

# ── hint field caps ──────────────────────────────────────────────
# The hint is a line-oriented block quoted verbatim into the planning and
# response prompts (contracts §5), i.e. into the prompt of an agent that
# stages shell commands. Every field it interpolates is untrusted or
# model-authored: thread titles come from the model's `new_thread` meta-tool
# or from the first line a human typed, match terms come from the message,
# receipts are extracted from stored content, and notification text carries
# terminal output. Without flattening, any of them can inject a forged
# labelled line ("Open loop: …", "Waiting for you: …") or close and reopen
# the block. `_clip` flattens embedded whitespace, drops the block's own
# delimiters and caps the length — the same defence receipt.py applies to
# every field it renders (see the comment block there).
HEAD_LINE_MAX = 200
RECALL_LINE_MAX = 320
#: Every recalled entry keeps at least this much, so section heads survive.
RECALL_LINE_MIN = 96
WEAK_LINE_MAX = 220
NOTIFICATION_LINE_MAX = 220
NOTIFICATION_ITEM_MAX = 160
#: "Note: …" lines (a retracted recall, A6d). One line each, and a total
#: allowance so a burst of them cannot crowd out the recall section.
NOTE_LINE_MAX = 200
NOTE_ITEM_MAX = 180
NOTES_MAX = 3
NOTES_TOTAL_MAX = 300
TERMINAL_HINT_MAX = 2048  # Plan B: B22 — shell-commands hint (2 KB cap)
TITLE_MAX = 120
DATE_MAX = 24
TERMS_MAX = 96
TERM_ITEM_MAX = 48
ONE_LINER_MAX = 220

#: How much of a field `_clip` looks at before capping it: enough that no
#: renderable content is lost (every cap here is ≤ RECALL_LINE_MAX), little
#: enough that the delimiter fixpoint stays cheap on megabytes of output.
_SCAN_MIN = 1024
_SCAN_FACTOR = 8

_HINT_OPEN = "<continuity>\n"
_HINT_CLOSE = "\n</continuity>"
_RECALL_DISCLAIMER = "Recalled details are past observations with dates. Verify current state before asserting it."
_WS_RE = re.compile(r"\s+")
#: The block's own delimiters, stripped out of interpolated text so it can
#: never look like a close/reopen of the block to whatever reads the prompt.
_DELIM_RE = re.compile(r"</?\s*continuity\s*>", re.IGNORECASE)


def _clip(text: Any, limit: int) -> str:
    """Flatten whitespace, drop hint delimiters, cap at ``limit`` chars."""
    limit = max(1, int(limit))
    flat = _WS_RE.sub(" ", str(text if text is not None else ""))
    # Cut to a bounded window before the loop below. Notification text is
    # unbounded terminal output, and a fixpoint over n characters costs
    # O(n²); everything past this window is discarded by the cap anyway.
    flat = flat[: max(_SCAN_MIN, limit * _SCAN_FACTOR)]
    # Substitute to a fixpoint, not once: a single pass turns the nested
    # payload "</</continuity>continuity>" into "</ continuity>", which is
    # itself a close tag under _DELIM_RE (the pattern tolerates whitespace),
    # so one pass leaves a working delimiter behind. Every pass replaces at
    # least twelve characters with one, so the string strictly shrinks and
    # the loop terminates.
    while _DELIM_RE.search(flat):
        flat = _DELIM_RE.sub(" ", flat)
    flat = _WS_RE.sub(" ", flat).strip()
    if len(flat) <= limit:
        return flat
    return flat[: limit - 1].rstrip() + "…"


def _terms(terms: Optional[List[str]], fallback: str) -> str:
    """Render match terms as a capped, flattened comma list."""
    items = [_clip(t, TERM_ITEM_MAX) for t in (terms or [])]
    return _clip(", ".join(i for i in items if i), TERMS_MAX) or fallback


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
    except Exception as e:
        # The store logs and returns [] for its own failures, so reaching this
        # means a duck-typed store or a signature drift — recall would go
        # silently dead without a line here (contracts §5 thread_store_error).
        logger.warning(f"search_receipts failed, no recall candidates: {e}")
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
        except Exception as e:
            logger.warning(f"list_threads failed, no entity overlap scoring: {e}")
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


def _is_empty_thread(thread: Optional[Dict[str, Any]]) -> bool:
    """True when nothing has been said in ``thread`` yet."""
    if not thread:
        return True
    try:
        return not int(thread.get("turn_count") or 0) and not int(thread.get("message_count") or 0)
    except (TypeError, ValueError):
        return False


def _anaphora_referent(recent: Dict[str, Any], open_thread: Optional[Dict[str, Any]], now: float) -> bool:
    """May ``recent`` be what a bare "did that work?" points at?

    A bare anaphora carries no topical evidence at all, so the synthetic
    candidate it produces is ``strong`` and can hand the turn to another
    thread (``reopen`` when that thread is paused). Two guards keep filler
    text from doing that:

    * The open thread must not simply be *missing* its ``last_active``.
      A thread that has real turns but no recorded activity — what an
      interrupted ``end_turn`` leaves behind — used to compare as older
      than everything (``float(None or 0)``), so every paused thread won
      and an acknowledgement abandoned the subject in flight. Only a
      thread with nothing said in it yet can be out-ranked that way, and
      then only because there is no other referent for "that".
    * The referent must be within one temporal gate. "did that work?"
      cannot plausibly mean a subject last touched weeks ago.
    """
    last_active = recent.get("last_active")
    if last_active is None:
        return False
    if (float(now) - float(last_active)) > TEMPORAL_GATE_SECONDS:
        return False
    open_last = open_thread.get("last_active") if open_thread else None
    if open_last is None:
        return _is_empty_thread(open_thread)
    return float(last_active) >= float(open_last)


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
        except Exception as e:
            logger.warning(f"list_threads failed, no anaphora referent: {e}")
            recent = []
        if recent and _anaphora_referent(recent[0], open_thread, now):
            r = recent[0]
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

def build_hint(open_thread: Dict[str, Any], decision: ThreadDecision, recalled: List[Dict[str, Any]], notifications: List[Dict[str, Any]], voice: str = "first_person", *, now: Optional[float] = None, notes: Optional[List[str]] = None, terminal_hint: Optional[str] = None) -> str:
    """Render the ``<continuity>`` block (≤ 900 chars); '' when there is nothing to say.

    ``voice`` is accepted for the prompt layer, which wraps the block through
    the voice renderer; the facts inside are voice-neutral. ``notes`` are
    system-origin observations (a retracted recall, spec §6) rendered as
    ``Note:`` lines after the recall lines and before ``Waiting for you``;
    at most ``NOTES_MAX`` are rendered, within ``NOTES_TOTAL_MAX`` chars.
    ``terminal_hint`` (Plan B: B22) is the shell-commands hint from
    ``WatchedShellProcessor.build_hint_text``, rendered after notes and
    before ``Waiting for you``.
    """
    now = time.time() if now is None else now
    if not open_thread:
        return ""
    title = _clip(open_thread.get("title"), TITLE_MAX) or "Untitled"
    turns = int(open_thread.get("turn_count") or 0)
    weak: List[Candidate] = []
    if not recalled and decision.strong is None:
        weak = [c for c in decision.candidates if not c.strong][:WEAK_CANDIDATES_MAX]

    notif_line = ""
    if notifications:
        items = [_clip(n.get("text") or n.get("title"), NOTIFICATION_ITEM_MAX) for n in notifications]
        joined = "; ".join(i for i in items if i)
        if joined:
            notif_line = _clip("Waiting for you: " + joined, NOTIFICATION_LINE_MAX)
    note_lines: List[str] = []
    for note in (notes or [])[:NOTES_MAX]:
        text = _clip(note, NOTE_ITEM_MAX)
        if text:
            note_lines.append(_clip(f"Note: {text}", NOTE_LINE_MAX))
    if turns == 0 and not recalled and not weak and not notif_line and not note_lines:
        return ""

    if turns == 0:
        head = f'Thread: "{title}" · opened just now.'
    else:
        head = (f'Thread: "{title}" · {turns} turns · last active '
                f'{relative_time(open_thread.get("last_active"), now)}.')
    if decision.stale:
        head += " (resuming after a gap)"
    head_line = _clip(head, HEAD_LINE_MAX)

    recall_lines = [
        f'Pulled in: "{_clip(r.get("title"), TITLE_MAX)}" '
        f'({_clip(r.get("date"), DATE_MAX) or "unknown date"}, '
        f'{relative_time(r.get("last_active"), now)}; matched {_terms(r.get("match_terms"), "recall")}) — '
        f'{_clip(receipt_one_liner(r.get("receipt") or ""), ONE_LINER_MAX)}'
        for r in recalled
    ]
    weak_line = ""
    if weak:
        weak_line = "Earlier work that may matter: " + "; ".join(
            f'"{_clip(c.title, TITLE_MAX)}" ({format_date(c.last_active, now)}; '
            f'matched {_terms(c.match_terms, "title")})'
            for c in weak
        )

    # Budget by priority rather than truncating the joined body as one string:
    # a single long receipt one-liner would otherwise eat the whole budget and
    # drop "Waiting for you" — the most time-critical line — entirely. The head
    # and the notifications survive whole; the notes take a bounded slice next;
    # the recalled lines (or, when there are none, the weak-candidate line)
    # share what is left, never below RECALL_LINE_MIN so every section keeps at
    # least its head. Reserving RECALL_LINE_MIN per recall line before the notes
    # are admitted is what keeps that floor affordable — without the reserve a
    # long note run would push the body past the budget and back into the
    # tail truncation this ordering exists to avoid.
    body_budget = HINT_MAX_CHARS - len(_HINT_OPEN) - len(_HINT_CLOSE)
    has_disclaimer = bool(recall_lines or weak_line)
    disclaimer_cost = (len(_RECALL_DISCLAIMER) + 1) if has_disclaimer else 0
    free = body_budget - len(head_line) - (len(notif_line) + 1 if notif_line else 0) - disclaimer_cost
    if note_lines:
        reserved_lines = len(recall_lines) or (1 if weak_line else 0)
        reserve = reserved_lines * (RECALL_LINE_MIN + 1)
        allowance = min(NOTES_TOTAL_MAX, max(0, free - reserve))
        kept: List[str] = []
        for line in note_lines:
            if len(line) + 1 > allowance:
                break  # a note that does not fit drops rather than truncating the block
            allowance -= len(line) + 1
            kept.append(line)
        note_lines = kept
        free -= sum(len(line) + 1 for line in note_lines)
    if recall_lines:
        per = min(RECALL_LINE_MAX, max(RECALL_LINE_MIN, (free - len(recall_lines)) // len(recall_lines)))
        recall_lines = [_clip(line, per) for line in recall_lines]
    elif weak_line:
        weak_line = _clip(weak_line, min(WEAK_LINE_MAX, max(RECALL_LINE_MIN, free - 1)))

    lines: List[str] = [head_line] + recall_lines
    if weak_line:
        lines.append(weak_line)
    if recall_lines or weak_line:
        lines.append(_RECALL_DISCLAIMER)
    lines.extend(note_lines)
    if terminal_hint:
        lines.append(_clip(terminal_hint, TERMINAL_HINT_MAX))
    if notif_line:
        lines.append(notif_line)
    body = "\n".join(lines)
    if len(body) > body_budget:  # only reachable with more recalled entries than A6 sends
        body = body[: body_budget - 1].rstrip() + "…"
    return f"{_HINT_OPEN}{body}{_HINT_CLOSE}"
