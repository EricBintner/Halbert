# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The suppression log, and shadow mode (A-HB-25; plan O1 and §4.6).

``the-being.md`` §2 ratifies that nothing appears to the user without a why.
It has a shadow the product cannot answer: **why did I *not* hear about
this?** After attunement, eleven mechanisms can eat a proactive event — the
dial, a category override, quiet hours, safe mode, a snooze, a dismissal, a
withdrawal, a limit floor, a deferred topic, low receptivity, an unreleased
hold — every one of them silent by construction. A warning lost to an
interaction of two is indistinguishable from a warning never generated.

**One recorder, two artifacts, and they must not be confused.** The rows
here answer two different questions and Haloysius was right that one
recorder writing one shape looked like it answered both:

* *What did the product actually do?* — ``gate_outcome`` and
  ``gate_reasons``. ``ProactiveGate`` is still the only thing that decides;
  this is what happened to the user, and it is what
  :meth:`SuppressionRecorder.recent_suppressions` reads.
* *What would the engine have done?* — ``outcome``, ``reasons``,
  ``margin``, by the ``OutcomeEntry`` field names, so Phase C's reader gets
  a standard row. ``decide()`` runs, is written down, and **acts on
  nothing**: that is §4.6 stage one.

``decision_source`` says which produced the top-level fields, and
``margin`` is ``None`` — never ``0.0`` — when no engine decision produced
one. A null margin cannot be mistaken for a decision that landed exactly on
a threshold, which is the distinction A-HB-26's exploration arm is defined
in terms of.

Nothing here may raise into its caller. A suppression log that crashes the
thing it observes is worse than no log.
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any, Dict, List, Optional, Sequence

from .surfaces import ChannelClass

logger = logging.getLogger("halbert.attunement.shadow")

#: Legacy prose from ``ProactiveGate.should_notify`` → stable reason key.
#: The gate's contract is ``(bool, str)`` and is called from several places,
#: so rather than change it we classify what it already says. Keys follow the
#: engine's ``namespace:value[:detail]`` convention so the two logs can be
#: read together.
#:
#: ``ProactiveGate._evaluate`` now emits these keys directly and composed;
#: this mapping remains for any caller that still has only the prose.
_REASON_PATTERNS = (
    (re.compile(r"proactivity dial is '(\w+)'"), lambda m: f"dial:{m.group(1)}"),
    (re.compile(r"quiet hours active"), lambda m: "quiet_hours"),
    (re.compile(r"safe mode active"), lambda m: "incident:safe_mode"),
    (re.compile(r"finding snoozed"), lambda m: "standing:defer_topic:snoozed"),
    (re.compile(r"finding dismissed"), lambda m: "standing:defer_topic:dismissed"),
    # Before this pattern the guest reason fell through to the unmapped slug,
    # which carries the guest's chosen *name* into a durable row that is
    # meant to hold "enums, ids, numbers and timestamps only — never text".
    (re.compile(r"a guest persona is fronting"), lambda m: "guest:fronting"),
)

#: The engine outcomes that reach a person. Taken from ``record_attempt``,
#: which counts exactly these three toward the daily proactive total — the
#: engine's own definition of having spoken, rather than a second one here.
SPEAKING_OUTCOMES = frozenset({"speak", "speak_minimal", "ask_first"})


def reason_key_for(reason: str) -> str:
    """Map the gate's prose to a stable key.

    An unrecognised reason is keyed as ``unmapped:<slug>`` rather than
    dropped — a suppression nobody can name is exactly the failure this log
    exists to expose, so it must be visible rather than silent.
    """
    if not reason:
        return ""
    for pattern, build in _REASON_PATTERNS:
        match = pattern.search(reason)
        if match:
            return build(match)
    slug = re.sub(r"[^a-z0-9]+", "_", reason.lower()).strip("_")[:40]
    logger.debug("attunement: unmapped suppression reason %r", reason)
    return f"unmapped:{slug}"


class ShadowDecider:
    """Runs the engine's ``decide()`` beside the gate, and acts on nothing.

    Held by the recorder rather than the gate: shadow mode is the log's
    business, and a gate that imported a policy it does not obey would be
    the confusing arrangement.

    Returns ``None`` for every failure — engine absent, context unbuildable,
    policy raised — and the row then carries the gate's verdict alone.
    """

    def __init__(self, store: Any, being_config: Any = None, *,
                 persona_id: str = "halbert", subject_id: str = "primary"):
        self.store = store
        self.being_config = being_config
        self.persona_id = persona_id
        self.subject_id = subject_id

    def _config(self) -> Any:
        if self.being_config is not None:
            return self.being_config
        try:
            from ..config.being_config import load_being_config
            self.being_config = load_being_config()
        except Exception as exc:
            logger.debug("attunement: no being config for the shadow: %s", exc)
            return None
        return self.being_config

    def decide(self, event: Any, *, channel_class: ChannelClass,
               quiet_hours_active: bool = False) -> Any:
        """The engine's decision for this event, or None."""
        being_config = self._config()
        if being_config is None:
            return None
        try:
            from haloysius.attunement.policy import decide as engine_decide

            from .context import build_context

            ctx = build_context(
                event,
                being_config=being_config,
                store=self.store,
                persona_id=self.persona_id,
                subject_id=self.subject_id,
                channel_class=channel_class,
                quiet_hours_active=quiet_hours_active,
            )
            if ctx is None:
                return None
            return engine_decide(ctx)
        except Exception as exc:
            logger.warning("attunement: shadow decision failed: %s", exc)
            return None


class SuppressionRecorder:
    """Writes one row per proactive decision, allowed or suppressed."""

    def __init__(self, store: Any = None, *, persona_id: str = "halbert",
                 subject_id: str = "primary", decider: Optional[ShadowDecider] = None):
        self.store = store
        self.persona_id = persona_id
        self.subject_id = subject_id
        #: Optional :class:`ShadowDecider`. None → the row carries the
        #: gate's verdict alone, with a null margin saying so.
        self.decider = decider

    def record(
        self,
        event: Any,
        *,
        allowed: bool,
        reason: str = "",
        reason_keys: Optional[Sequence[str]] = None,
        channel_class: ChannelClass = ChannelClass.PUSH,
        quiet_hours_active: bool = False,
        decision: Any = None,
    ) -> Optional[str]:
        """Record one decision. Returns the attempt id, or None.

        ``reason_keys`` is the full composition — every mechanism that ate
        this event, not the first one that fired. A caller with only the
        prose may pass ``reason`` instead and get a single mapped key.

        ``decision`` is the engine's ``EngagementDecision`` when the caller
        already has one; otherwise the attached :class:`ShadowDecider`
        produces it, and if there is none the row says so.

        Never raises: every failure is logged and swallowed.
        """
        if self.store is None:
            return None
        try:
            gate_keys = self._gate_keys(allowed, reason, reason_keys)
            if decision is None and self.decider is not None:
                # Its own guard, inside the recorder's. The shadow is the
                # speculative half of this row and the gate's verdict is the
                # half that describes what happened, so a policy that blows
                # up must cost its own opinion and nothing else.
                try:
                    decision = self.decider.decide(
                        event,
                        channel_class=channel_class,
                        quiet_hours_active=quiet_hours_active,
                    )
                except Exception as exc:
                    logger.warning("attunement: shadow decision failed: %s", exc)
                    decision = None

            attempt_id = str(uuid.uuid4())
            gate_outcome = "speak" if allowed else "silent"
            entry: Dict[str, Any] = {
                "attempt_id": attempt_id,
                "persona_id": self.persona_id,
                "subject_id": self.subject_id,
                "source": getattr(event, "type", "") or "",
                "severity": getattr(event, "severity", "") or "",
                "channel_class": channel_class.value,
                "context_key": getattr(event, "finding_id", None),
                # What actually happened to the user.
                "gate_outcome": gate_outcome,
                "gate_reasons": gate_keys,
            }
            entry.update(self._verdict(decision, gate_outcome, gate_keys))
            self.store.record_outcome_raw(entry)
            return attempt_id
        except Exception as exc:
            logger.warning("attunement: could not record decision: %s", exc)
            return None

    @staticmethod
    def _gate_keys(allowed: bool, reason: str,
                   reason_keys: Optional[Sequence[str]]) -> List[str]:
        if reason_keys is not None:
            return [str(k) for k in reason_keys if k]
        key = reason_key_for("" if allowed else reason)
        return [key] if key else []

    def _verdict(self, decision: Any, gate_outcome: str,
                 gate_keys: List[str]) -> Dict[str, Any]:
        """The top-level ``OutcomeEntry`` fields, and who produced them."""
        if decision is None:
            return {
                "decision_source": "gate",
                "outcome": gate_outcome,
                "reasons": gate_keys,
                # Not 0.0. A zero margin means the engine computed one and it
                # landed on a threshold; this means no margin was computed.
                "margin": None,
                "receptivity_level": None,
                "activity": None,
                "shadow_agrees": None,
            }

        outcome = getattr(decision.outcome, "value", decision.outcome)
        receptivity = getattr(decision, "receptivity", None)
        return {
            "decision_source": "engine",
            "outcome": outcome,
            "reasons": [str(r) for r in (decision.reasons or ())],
            "margin": float(getattr(decision, "margin", 0.0)),
            "receptivity_level": (
                getattr(receptivity.level, "value", receptivity.level)
                if receptivity is not None else None
            ),
            "activity": self._persistable_activity(decision),
            "shadow_agrees": (outcome in SPEAKING_OUTCOMES) == (gate_outcome == "speak"),
        }

    @staticmethod
    def _persistable_activity(decision: Any) -> Optional[str]:
        """The activity label, if its provenance may be persisted (A-HB-19).

        An activity enum at a timestamp is still a fact about a person's
        home, so a vision- or audio-derived label never reaches the durable
        row. Read off the decision's receptivity rather than the raw
        signals, because that is what the decision was actually taken on.
        """
        receptivity = getattr(decision, "receptivity", None)
        activity = getattr(receptivity, "activity", None) if receptivity else None
        if activity is None:
            return None
        provenance = getattr(receptivity, "activity_provenance", None)
        provenance = getattr(provenance, "value", provenance)
        if provenance in ("vision", "audio"):
            return None
        return getattr(activity, "value", activity)

    def recent_suppressions(self, limit: int = 50) -> List[Dict[str, Any]]:
        """The rows behind "what haven't you told me?".

        Read off ``gate_outcome``: the question is about what the product
        withheld, and the engine's opinion is not acted on.
        """
        if self.store is None:
            return []
        try:
            rows = self.store.list_outcomes_raw(
                self.persona_id, subject_id=self.subject_id, limit=limit * 4
            )
        except Exception as exc:
            logger.warning("attunement: could not read suppressions: %s", exc)
            return []
        return [
            r for r in rows
            if r.get("gate_outcome", r.get("outcome")) != "speak"
        ][:limit]


def default_recorder(being_config: Any = None, *, store: Any = None) -> Optional[SuppressionRecorder]:
    """The recorder production wires into ``ProactiveGate``, or None.

    Returns None rather than raising: a proactive path that cannot start
    because its *log* could not start would be the log making things worse.

    The store is deliberately constructed per call rather than shared.
    ``AttunementStore`` is SQLite in WAL mode precisely because it is
    reached from the dashboard, the MCP server, the scheduler, the detector
    runner and the cognitive loop at once, and ``FindingStore`` is already
    built independently in ten places on the same reasoning.
    """
    try:
        from .store import AttunementStore

        store = store if store is not None else AttunementStore()
        return SuppressionRecorder(
            store=store,
            decider=ShadowDecider(store, being_config),
        )
    except Exception as exc:
        logger.warning("attunement: could not build the suppression log: %s", exc)
        return None
