"""Session affinity router (F2).

3-tier routing that picks which past conversation a new user message most
likely belongs to (so the agent can load the right history):

  1. **Explicit reference** — the message names a session/conversation id
     ("session abc-123", "the conversation about ..."). If the id exists, bind
     to it with high confidence.
  2. **FTS5 search** — search the conversation store for the message's key
     terms (domains + significant words, via intake/signals) and bind to the
     top hit with medium confidence.
  3. **Current session** — fall back to the current conversation id with low
     confidence.

Reuses ``intake/signals.analyze_message`` for entity/domain extraction. Works
with any store exposing ``get(id)`` and ``search(query, user_id, limit)``
(the SqliteConversationStore or the JSON ConversationStore).

See OPUS-HANDOFF §F2.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional

logger = logging.getLogger("halbert.agents.session_affinity")

__all__ = ["SessionAffinity", "SessionAffinityRouter"]


@dataclass
class SessionAffinity:
    """The result of routing a message to a conversation."""
    session_id: Optional[str]
    tier: str  # "explicit" | "fts" | "current"
    confidence: float
    reason: str
    candidates: List[str] = field(default_factory=list)


# "session abc-123", "conversation id: abc-123", "chat abc-123"
_EXPLICIT_RE = re.compile(
    r"(?:session|conversation|chat)\s+(?:id[:\s]*)?([A-Za-z0-9][A-Za-z0-9_\-]{2,})",
    re.IGNORECASE,
)

_STOPWORDS = {
    "the", "a", "an", "is", "was", "my", "our", "i", "to", "do", "about",
    "from", "yesterday", "that", "this", "with", "for", "on", "in", "of",
    "and", "or", "it", "we", "you", "what", "how", "can", "could", "should",
    "tell", "show", "give", "me", "please", "just", "back", "again",
}


class SessionAffinityRouter:
    """3-tier session-affinity router (F2)."""

    def __init__(
        self,
        conversation_store: Any,
        signals_analyzer: Callable[[str], Any] = None,
    ):
        self.store = conversation_store
        if signals_analyzer is None:
            # Late import keeps the module importable without the intake pkg.
            from ..intake.signals import analyze_message
            signals_analyzer = analyze_message
        self.analyze = signals_analyzer

    def route(
        self,
        query: str,
        current_session_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> SessionAffinity:
        """Route ``query`` to the most-likely conversation id."""
        if not query or not query.strip():
            return SessionAffinity(current_session_id, "current", 0.3, "empty query")

        # Tier 1: explicit reference
        hit = self._explicit_reference(query)
        if hit is not None:
            return SessionAffinity(
                session_id=hit, tier="explicit", confidence=0.95,
                reason="explicit session/conversation reference",
            )

        # Tier 2: keyword search. Search per keyword (store-agnostic: a single
        # keyword works for both FTS5 MATCH and the JSON store's literal
        # substring scan) and rank conversations by how many keywords hit.
        keywords = self._extract_keywords(query)
        if keywords:
            scores: dict = {}
            for kw in keywords:
                try:
                    results = self.store.search(kw, user_id=user_id, limit=10)
                except Exception as e:
                    logger.debug(f"affinity search '{kw}' failed: {e}")
                    results = []
                for r in results:
                    if r == current_session_id:
                        continue
                    scores[r] = scores.get(r, 0) + 1
            if scores:
                ranked = sorted(scores, key=lambda k: scores[k], reverse=True)
                best = ranked[0]
                conf = 0.5 + min(0.3, 0.1 * scores[best])
                return SessionAffinity(
                    session_id=best, tier="fts", confidence=conf,
                    reason=f"keyword matches: {dict(sorted(scores.items(), key=lambda x: x[1], reverse=True))}",
                    candidates=ranked[:5],
                )

        # Tier 3: current session
        return SessionAffinity(
            session_id=current_session_id, tier="current", confidence=0.3,
            reason="fallback to current session",
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _explicit_reference(self, query: str) -> Optional[str]:
        """Return a referenced conversation id if the message names one that exists."""
        m = _EXPLICIT_RE.search(query)
        if not m:
            return None
        ref = m.group(1)
        try:
            if self.store.get(ref) is not None:
                return ref
        except Exception:
            pass
        return None

    def _extract_keywords(self, query: str) -> List[str]:
        """Extract search keywords: detected domains + significant words.

        Returns single lowercase tokens (no FTS5 syntax) so the same list
        works for both FTS5 MATCH and literal substring search.
        """
        try:
            signals = self.analyze(query)
        except Exception:
            signals = None
        tokens: List[str] = []
        if signals is not None:
            tokens.extend(getattr(signals, "detected_domains", []) or [])
        for w in re.findall(r"[A-Za-z][A-Za-z0-9_]{2,}", query.lower()):
            if w in _STOPWORDS:
                continue
            tokens.append(w)
        seen = set()
        out: List[str] = []
        for t in tokens:
            if t in seen:
                continue
            seen.add(t)
            out.append(t)
            if len(out) >= 6:
                break
        return out