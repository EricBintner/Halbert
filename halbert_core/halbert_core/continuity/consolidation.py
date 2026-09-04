# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""R8: Consolidation at idle — cross-thread abstraction into durable facts.

When the system is idle (no active turn, no live terminal blocks), the
consolidator scans recently-closed threads for recurring patterns and
writes durable preference facts to the state store. These are not
session-scoped — they survive across sessions and inform future turns.

Design constraints (from the handoff):
- Runs in low-load windows only — never blocks a turn.
- Uses the LLM slot (not the chat slot) to abstract patterns.
- Fail-soft: any error is logged and swallowed.
- Measures first (R5 harness), consolidates second.
- Writes to Halbert's own StateStore, not Haloysius (D1).

The consolidator is intentionally simple: it batches closed threads by
domain, extracts recurring entities/commands/files, and records them as
durable facts. An LLM abstraction pass is the natural next step but is
gated behind a flag until the eval harness (R5) confirms the pattern.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from .state_store import ACTOR_SYSTEM

logger = logging.getLogger("halbert.continuity.consolidation")

#: Minimum threads in a domain batch before consolidation runs.
MIN_BATCH = 3

#: How far back to look for closed threads (seconds, default 7 days).
LOOKBACK_SECONDS = 7 * 24 * 3600


class Consolidator:
    """Cross-thread consolidation into durable preference facts.

    ``store`` is the SqliteConversationStore (for listing threads).
    ``state_store`` is the StateStore (for recording durable facts).
    """

    def __init__(self, store, state_store):
        self._store = store
        self._state = state_store

    def consolidate(self, *, now: Optional[float] = None) -> int:
        """Scan closed threads and record durable facts.

        Returns the number of facts recorded. Fail-soft: any error
        returns 0.
        """
        ts = time.time() if now is None else now
        try:
            closed = self._store.list_threads(status="closed", limit=100)
        except Exception as e:
            logger.warning(f"consolidation: failed to list closed threads: {e}")
            return 0

        # Filter to the lookback window
        cutoff = ts - LOOKBACK_SECONDS
        recent = [t for t in closed if float(t.get("updated_at") or 0) >= cutoff]
        if len(recent) < MIN_BATCH:
            return 0

        # Group by domain
        by_domain: Dict[str, List[Dict[str, Any]]] = {}
        for t in recent:
            for d in (t.get("topic_domains") or []):
                by_domain.setdefault(d, []).append(t)

        facts = 0
        for domain, threads in by_domain.items():
            if len(threads) < MIN_BATCH:
                continue
            facts += self._consolidate_domain(domain, threads, ts)

        if facts > 0:
            logger.info(f"consolidation: recorded {facts} durable facts")
        return facts

    def _consolidate_domain(
        self, domain: str, threads: List[Dict[str, Any]], now: float
    ) -> int:
        """Extract recurring patterns from threads in one domain."""
        facts = 0
        # Count entity frequency across threads
        entity_counts: Dict[str, int] = {}
        for t in threads:
            for e in (t.get("entities_json") or []):
                entity_counts[e] = entity_counts.get(e, 0) + 1

        # Entities appearing in >= half the threads are durable preferences
        threshold = max(2, len(threads) // 2)
        for entity, count in entity_counts.items():
            if count >= threshold:
                try:
                    rid = self._state.record_state(
                        f"domain:{domain}", "preferred_entity", entity,
                        "consolidation", confidence=count / len(threads),
                        now=now,
                        reason=(
                            f"consolidation: appeared in {count} of "
                            f"{len(threads)} {domain} threads"
                        ),
                        actor=ACTOR_SYSTEM,
                        # Without a request_id these words are unreachable by
                        # redact_request, which finds rows through it. A reason
                        # that cannot be forgotten should not be recorded.
                        request_id=f"consolidation-{domain}",
                    )
                    if rid is not None:
                        facts += 1
                except Exception as e:
                    logger.warning(f"consolidation: failed to record entity {entity}: {e}")

        # Record the domain's thread count as a durable fact
        try:
            rid = self._state.record_state(
                f"domain:{domain}", "thread_count", str(len(threads)),
                "consolidation", now=now,
                reason="consolidation: closed-thread count for this domain",
                actor=ACTOR_SYSTEM,
                request_id=f"consolidation-{domain}",
            )
            if rid is not None:
                facts += 1
        except Exception as e:
            logger.warning(f"consolidation: failed to record domain count: {e}")

        return facts
