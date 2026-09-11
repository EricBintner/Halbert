# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The interest row -- one shape, written by Halbert, owned by the engine.

``RQ-1``: an interest is a memory_v2 :class:`PersonaMemory`, mirrored as an
``ObservationStore`` ``preference`` row. ``StateStore`` never holds a user
fact (``MEM-02``: one subject, the machine; one open row per key; host-bound),
and ``CD-5`` already put favourites in ``memory_v2``.

**Why a dataclass at all.** ``PersonaMemory.metadata`` is a free dict. The
removed ``MemoryWriter`` failed precisely there -- nothing it wrote could be
read back -- so the pair :meth:`Interest.to_persona_memory` /
:meth:`Interest.from_persona_memory` plus a round-trip test at the boundary is
the whole difference between a shape and a hope.

**A learned interest differs from a stated one in fields, not in store.** Same
row; three explicit fields carry the difference (``origin``, ``evidence``,
``last_confirmed_at``). Confidence is never a number this module chooses --
the engine derives it from provenance, and the UI shows the origin and the
evidence rather than a bare score.

**The confidence trap, measured.** Haloysius's handoff
(``HANDOFF-OBSERVATION-LENSES-UPSTREAM-ASKS-2026-09-06.md``) tells a writer
building its own ``PersonaMemory`` that it "must set ``source="user"``
itself". Measured against the engine as it stands, that alone calibrates at
**0.7** -- the inferred confidence. The 0.9 a stated fact is meant to carry
needs ``Provenance.USER_ORGANIC`` *and* the ``user_stated`` tag, which is what
``teach()`` and ``update_preference()`` both do internally. A stated fact
silently landing at the inferred confidence is the exact defect that fix was
for, so :data:`_USER_STATED_TAG` is applied here and pinned by test.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("halbert.continuity.interests")

__all__ = [
    "Origin",
    "InterestStatus",
    "Interest",
    "topic_slug",
    "INTEREST_TAG",
    "CANONICAL_PREFIX",
]

#: Marks a memory as one of ours. The read path keys off this, so a memory
#: written by any other consumer is not mistaken for an interest.
INTEREST_TAG = "interest"

#: The canonical content. Fixed rather than templated per call, and **without
#: a colon**, which is load-bearing.
#:
#: The engine's ``_extract_subject`` matches ``interested in X`` and returns
#: ``interest in X`` -- the same subject its withdrawal form
#: ("no longer interested in X") returns, which is what makes a withdrawal
#: supersede rather than accumulate beside the interest.
#:
#: A colon defeats it. ``"User is interested in: sailing"`` extracts **None**,
#: and with no subject every interest reads as contradicting every other: six
#: stated interests collapsed to two, and "sailing" replaced "thinkpads".
#: Measured 2026-09-10; the research brief's §5 prescribes the colon form and
#: is wrong about it.
CANONICAL_PREFIX = "User is interested in "

#: The engine calibrates 0.9 on provenance AND this tag. See the module
#: docstring -- the handoff omits the tag, and without it a stated fact is
#: stored at the confidence of an inferred one.
_USER_STATED_TAG = "user_stated"

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


class Origin(str, Enum):
    """How this interest came to be known.

    Carried as a field rather than expressed as a category: ``preference`` is
    the category either way (``pattern`` means a temporal habit in
    ``observation_store.py`` and is a different claim).
    """

    STATED = "stated"
    INFERRED = "inferred"
    INFERRED_CONFIRMED = "inferred_confirmed"


class InterestStatus(str, Enum):
    """Where the row stands.

    ``CANDIDATE`` is the load-bearing one: an inferred interest is **never
    injected into a prompt until a person confirms it**, which is enforced by
    :attr:`Interest.should_mirror` rather than by remembering to check.
    """

    CANDIDATE = "candidate"
    ACTIVE = "active"
    LAPSED = "lapsed"
    FORGET_REQUESTED = "forget_requested"


def topic_slug(topic: str) -> str:
    """A deterministic dedup key for a topic.

    Replaces content-hash dedup, so the same topic typed with different case,
    spacing or punctuation is one interest rather than several.

    It does **not** join near misses: ``thinkpads`` and ``vintage thinkpads``
    remain two slugs. The design doc lists those as topics that should not
    fragment, and joining them is fuzzy *correspondence* -- rung 0 of the
    disagreement meter -- which is a separate decision with its own tolerance.
    A substring rule here would look like it worked and would also join
    ``zfs`` to ``zfs send``, which are not the same interest.
    """
    return _SLUG_STRIP.sub("-", (topic or "").strip().lower()).strip("-")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Interest:
    """One thing the person is interested in, and how we know.

    ``reason`` is mandatory (``MEM-06``): a stored fact about a person needs a
    reason that is a human utterance or a self-naming rule, never model text.
    """

    topic: str
    origin: Origin
    reason: str
    status: InterestStatus = InterestStatus.ACTIVE
    actor: str = ""
    speaker_role: str = ""
    body_id: str = ""
    evidence: Dict[str, Any] = field(default_factory=dict)
    first_seen_at: str = ""
    last_evidenced_at: str = ""
    last_confirmed_at: str = ""

    def __post_init__(self) -> None:
        self.topic = (self.topic or "").strip()
        if not self.topic:
            raise ValueError("an interest needs a topic")
        if not (self.reason or "").strip():
            raise ValueError(
                "an interest needs a reason: a human utterance or a "
                "self-naming rule (MEM-06)"
            )
        if self.origin is Origin.STATED and not (self.actor or "").strip():
            raise ValueError("a stated interest needs the actor who stated it")
        if not self.first_seen_at:
            self.first_seen_at = _now()

    # -- derived ---------------------------------------------------------

    @property
    def slug(self) -> str:
        return topic_slug(self.topic)

    @property
    def content(self) -> str:
        return f"{CANONICAL_PREFIX}{self.topic}"

    @property
    def observation_category(self) -> str:
        """Always ``preference``, set explicitly.

        The keyword classifier files "interested in" as ``fact``; naming the
        category here is what stops an interest becoming a fact in the index.
        """
        return "preference"

    @property
    def should_mirror(self) -> bool:
        """Whether the derived ``ObservationStore`` row may exist.

        Only for an active interest. The observation row is the index recall
        reads, so mirroring a candidate would inject a belief nobody
        confirmed, and mirroring a lapsed or forget-requested one would keep
        answering with something the person retired.
        """
        return self.status is InterestStatus.ACTIVE

    # -- the boundary ----------------------------------------------------

    def to_persona_memory(self, persona_id: str) -> Any:
        """Build the engine row. Import is local so ``continuity`` stays
        importable on a install without the engine's optional extras."""
        from haloysius.memory_v2.types import MemoryType, PersonaMemory, Provenance

        stated = self.origin is Origin.STATED
        tags: List[str] = [INTEREST_TAG, self.origin.value, self.slug]
        if stated:
            tags.append(_USER_STATED_TAG)

        return PersonaMemory(
            id=f"interest_{self.slug}",
            persona_id=persona_id,
            memory_type=MemoryType.SEMANTIC,
            content=self.content,
            # A stated interest is the person's own words; an inferred one is
            # derived by our arithmetic and says so.
            source=Provenance.USER_ORGANIC if stated else Provenance.CONSOLIDATION,
            tags=tags,
            # The deterministic retrieval anchor: recall must not depend on an
            # embedder agreeing with itself.
            keywords=[t for t in self.topic.lower().split() if t],
            metadata=self._metadata(),
        )

    def _metadata(self) -> Dict[str, Any]:
        return {
            "halbert_interest": True,
            "topic": self.topic,
            "origin": self.origin.value,
            "status": self.status.value,
            "reason": self.reason,
            "actor": self.actor,
            "speaker_role": self.speaker_role,
            "body_id": self.body_id,
            "evidence": dict(self.evidence),
            "first_seen_at": self.first_seen_at,
            "last_evidenced_at": self.last_evidenced_at,
            "last_confirmed_at": self.last_confirmed_at,
        }

    @classmethod
    def from_persona_memory(cls, memory: Any) -> Optional["Interest"]:
        """Read one back, or ``None`` when it is not ours or is malformed.

        Never raises. ``metadata`` is a free dict that any consumer may write
        into, and a reader that raises here takes down whatever was iterating
        the store.
        """
        try:
            tags = list(getattr(memory, "tags", None) or [])
            meta = dict(getattr(memory, "metadata", None) or {})
            if INTEREST_TAG not in tags:
                return None
            topic = meta.get("topic")
            if not isinstance(topic, str) or not topic.strip():
                return None
            return cls(
                topic=topic,
                origin=Origin(meta["origin"]),
                reason=meta.get("reason") or "",
                status=InterestStatus(meta.get("status", InterestStatus.ACTIVE.value)),
                actor=meta.get("actor") or "",
                speaker_role=meta.get("speaker_role") or "",
                body_id=meta.get("body_id") or "",
                evidence=dict(meta.get("evidence") or {}),
                first_seen_at=meta.get("first_seen_at") or "",
                last_evidenced_at=meta.get("last_evidenced_at") or "",
                last_confirmed_at=meta.get("last_confirmed_at") or "",
            )
        except Exception:
            logger.debug("not a readable interest row", exc_info=True)
            return None
