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

# -- The interest candidate rule (RQ-3) ---------------------------------
#
# Deliberately NOT the 7-day / 3-thread rule above. Three threads about
# samba in one evening is a job, not an interest. Distinct *days* are the
# chat analogue of "that grey van, three times this week" -- recurrence
# across time is what separates something a person keeps returning to from
# something they were busy with once.

#: The window a candidate is measured over.
CANDIDATE_WINDOW_DAYS = 30
CANDIDATE_LOOKBACK_SECONDS = CANDIDATE_WINDOW_DAYS * 24 * 3600

#: Distinct days the term must appear on.
CANDIDATE_MIN_DAYS = 3

#: Distinct non-ephemeral closed threads it must appear across.
CANDIDATE_MIN_THREADS = 3

#: What makes a thread non-ephemeral: more than one thing the person said.
#: A single-turn thread is a question answered, not a strand of work, and
#: counting them would let three one-line asks on three days manufacture an
#: interest nobody has.
CANDIDATE_MIN_TURNS = 2


class Consolidator:
    """Cross-thread consolidation into durable preference facts.

    ``store`` is the SqliteConversationStore (for listing threads).
    ``state_store`` is the StateStore (for recording durable facts).
    """

    def __init__(self, store, state_store, memory_store=None):
        self._store = store
        self._state = state_store
        # Optional: the interest candidate rule needs a PersonaMemoryStore,
        # and every existing construction site predates it. None means "ask
        # the wiring at call time", which is also what lets a test inject one
        # without touching the two callers.
        self._memory = memory_store
        #: When the MEM-04 sweep last ran. None means never.
        self._last_sweep: Optional[float] = None

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

    # -- the inferred half of RQ-3 -------------------------------------

    def propose_interests(self, *, now: Optional[float] = None) -> int:
        """Propose interest **candidates** from recurrence. Never raises.

        The arithmetic is the whole method: a term named on at least
        :data:`CANDIDATE_MIN_DAYS` distinct days, in at least
        :data:`CANDIDATE_MIN_THREADS` non-ephemeral closed threads, inside
        :data:`CANDIDATE_WINDOW_DAYS`. No model reads a conversation and
        decides what the person is into; that is the write this whole design
        exists to refuse.

        What it writes is a **candidate**, and a candidate is not a belief.
        ``should_mirror`` keeps it out of the observation index and
        ``_ELIGIBLE_ORIGINS`` keeps it out of the prompt, so nothing derived
        from it can reach a turn until a person says yes. It exists to be
        *asked about*, once, and otherwise to sit in a list.

        The reason is self-naming -- "appeared on 4 days in 30 across 5
        threads" -- which is the only kind of reason ``MEM-06`` accepts
        besides a human utterance. A sentence a model composed about why
        someone might like something is exactly what MEM-06 forbids.

        Returns the number of candidates written.
        """
        ts = time.time() if now is None else now
        try:
            store = self._memory_store()
            if store is None:
                return 0
            threads = self._candidate_threads(ts)
            if not threads:
                return 0
            written = 0
            for topic, days, thread_ids in self._recurring_terms(threads):
                if self._already_known(store, topic, thread_ids):
                    continue
                if self._write_candidate(store, topic, days, thread_ids, ts):
                    written += 1
            if written:
                logger.info(f"consolidation: proposed {written} interest candidates")
            return written
        except Exception:
            logger.warning("proposing interest candidates failed", exc_info=True)
            return 0

    def _memory_store(self):
        """The persona memory store, or ``None``.

        ``MEM-02``: ``StateStore`` never holds a fact about a person -- one
        subject, the machine. An interest is a ``PersonaMemory``, and it is
        reached through the wiring so that under Singular Entity it lands on
        the canonical host rather than in a body-local copy nothing else
        sees.
        """
        if self._memory is not None:
            return self._memory
        try:
            from ..integrations.cognition_wiring import get_persona_memory_store
            return get_persona_memory_store()
        except Exception:
            logger.debug("no persona memory store for candidates", exc_info=True)
            return None

    def _candidate_threads(self, now: float) -> List[Dict[str, Any]]:
        """Closed, inside the window, and more than a single question."""
        try:
            closed = self._store.list_threads(status="closed", limit=500)
        except Exception as e:
            logger.warning(f"candidates: failed to list closed threads: {e}")
            return []
        cutoff = now - CANDIDATE_LOOKBACK_SECONDS
        out = []
        for t in closed:
            try:
                if float(t.get("updated_at") or 0) < cutoff:
                    continue
                if int(t.get("turn_count") or 0) < CANDIDATE_MIN_TURNS:
                    continue
            except (TypeError, ValueError):
                continue
            out.append(t)
        return out

    @staticmethod
    def _day(stamp: Any) -> str:
        """The UTC date a thread was last active, as ``YYYY-MM-DD``.

        UTC rather than local: the rule counts days, and a person working
        across midnight should not have one evening counted as two because
        of where they live.
        """
        from datetime import datetime, timezone

        return datetime.fromtimestamp(
            float(stamp or 0), tz=timezone.utc
        ).strftime("%Y-%m-%d")

    def _recurring_terms(self, threads: List[Dict[str, Any]]):
        """``(topic, distinct_days, thread_ids)`` for every term that clears
        the bar. Entities and domains both count -- a person may return to
        "zfs" (an entity) or to "storage" (a domain), and neither is more
        evidence of interest than the other."""
        days: Dict[str, set] = {}
        seen_in: Dict[str, set] = {}
        for t in threads:
            day = self._day(t.get("updated_at"))
            tid = t.get("thread_id") or t.get("id") or ""
            terms = set()
            for e in (t.get("entities_json") or []):
                if isinstance(e, str) and e.strip():
                    terms.add(e.strip())
            for d in (t.get("topic_domains") or []):
                if isinstance(d, str) and d.strip():
                    terms.add(d.strip())
            for term in terms:
                days.setdefault(term, set()).add(day)
                seen_in.setdefault(term, set()).add(tid)

        out = []
        for term, on_days in days.items():
            threads_for = seen_in.get(term, set())
            if len(on_days) >= CANDIDATE_MIN_DAYS and len(threads_for) >= CANDIDATE_MIN_THREADS:
                out.append((term, len(on_days), sorted(threads_for)))
        # Stable order so a run is reproducible and a test can name a row.
        out.sort(key=lambda r: (-r[1], r[0]))
        return out

    @staticmethod
    def _already_known(store: Any, topic: str, thread_ids: List[str]) -> bool:
        """Whether this topic may not be proposed again.

        Almost always yes, for any existing row in any status. Re-proposing
        something the person stopped using would walk their retraction back
        through the side door; re-proposing an active one would ask them to
        confirm what they already told us; re-proposing a lapsed confirmed
        one would ask again about something they already agreed to and that
        simply ran out of evidence.

        **The one exception is an expired candidate on genuinely new
        evidence.** A candidate that expired was a question nobody answered.
        Asking again off the same threads is nagging, and the spec forbids
        it in those words -- *never re-raised on the same evidence*. But a
        person who ignored it once and then spent a fortnight back in the
        same subject has produced new evidence, and never asking again
        would be a different failure from nagging: the machine noticing and
        saying nothing, forever, because of one shrug months ago.

        Identity is by thread, which is what the candidate stored. Disjoint
        thread sets mean none of the conversations that prompted the first
        question is prompting this one.
        """
        try:
            from .interests import Interest, InterestStatus, Origin, topic_slug

            slug = topic_slug(topic)
            for memory in (getattr(store, "list_memories", list)() or []):
                existing = Interest.from_persona_memory(memory)
                if existing is None or existing.slug != slug:
                    continue
                if (
                    existing.origin is Origin.INFERRED
                    and existing.status is InterestStatus.LAPSED
                ):
                    seen = set(existing.evidence.get("threads") or [])
                    if seen and not (seen & set(thread_ids)):
                        return False
                return True
            # Nothing matching. This is the only path that may write.
            return False
        except Exception:
            # Unreadable is not a licence to write. A store that cannot be
            # searched cannot rule out a retraction, and proposing into that
            # uncertainty is the one error this method must not make.
            logger.debug("could not check for an existing interest", exc_info=True)
            return True

    def _write_candidate(
        self, store: Any, topic: str, days: int, thread_ids: List[str], now: float
    ) -> bool:
        try:
            from datetime import datetime, timezone

            from .interests import Interest, InterestStatus, Origin
            from ..ingestion.redaction import redact_text

            # Scrubbed like anything else that came out of a conversation:
            # an entity is a noun someone typed.
            safe = redact_text(topic, prose=True)
            if safe != topic:
                return False
            stamp = datetime.fromtimestamp(now, tz=timezone.utc).isoformat()
            interest = Interest(
                topic=topic,
                origin=Origin.INFERRED,
                status=InterestStatus.CANDIDATE,
                reason=(
                    f"appeared on {days} days in {CANDIDATE_WINDOW_DAYS} "
                    f"across {len(thread_ids)} threads"
                ),
                evidence={
                    "threads": list(thread_ids),
                    "days": days,
                    "window_days": CANDIDATE_WINDOW_DAYS,
                    "proposed_at": stamp,
                },
                first_seen_at=stamp,
                last_evidenced_at=stamp,
            )
            store.smart_add(interest.to_persona_memory(self._persona_id(store)))
            return True
        except Exception:
            logger.warning(f"could not write the candidate {topic!r}", exc_info=True)
            return False

    @staticmethod
    def _persona_id(store: Any) -> str:
        return str(getattr(store, "persona_id", "") or "halbert")

    # -- MEM-04 --------------------------------------------------------

    #: At most one sweep a day. The clocks it applies are 30 and 90 days;
    #: running it on every idle tick would scan the store hundreds of times
    #: to change nothing.
    SWEEP_INTERVAL_SECONDS = 24 * 3600

    def sweep_interests(self, *, now: Optional[float] = None) -> int:
        """Retire interests that ran out of evidence. Never raises.

        Runs beside the candidate rule rather than on its own scheduler job:
        proposing and retiring are the two halves of one mechanism, and
        keeping them in one place is what stops a later reader finding the
        rule that creates candidates and not the one that clears them.
        """
        ts = time.time() if now is None else now
        last = getattr(self, "_last_sweep", None)
        if last is not None and (ts - last) < self.SWEEP_INTERVAL_SECONDS:
            return 0
        self._last_sweep = ts
        try:
            from .interest_sweep import sweep_interests as _sweep

            report = _sweep(self._memory_store(), None, now=ts)
            return int(report.get("lapsed", 0)) + int(report.get("expired", 0))
        except Exception:
            logger.warning("the interest sweep failed", exc_info=True)
            return 0

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
