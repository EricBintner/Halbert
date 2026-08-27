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
