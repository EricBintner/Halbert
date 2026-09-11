# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The engine's working document, assembled from what Halbert already knows
(HB-D3, plan §4.6).

``decide()`` is pure: it reads no clock, no store and no sensor. Everything
it needs arrives on one :class:`AttunementContext`, and building that is the
consumer's whole job. This module is that build, and nothing else — it takes
a :class:`ProactiveEvent` plus the stores and returns the context, or
``None`` when the engine is not installed.

Three things here are Halbert's judgment rather than the engine's, and each
is marked where it is made:

* **The attachment ceilings are ours** (:func:`halbert_config`). The engine
  ships a companion's numbers and says so; a sysadmin tool that muted itself
  for its first week would be silent exactly when a fresh install has the
  most to say.
* **``life_safety`` is caller-set, never derived from severity** (A-HB-15).
  It comes from the event's *category* and from the acoustic tagger's own
  confirmation, which is what ``ProactiveGate`` already treats as life
  safety.
* **The subject of a proactive push is the primary user, unattributed.**
  Nobody spoke; there is no identity to resolve. UNATTRIBUTED is the honest
  confidence — a channel that implies the trusted default user — and it
  deliberately does not inherit the most-restrictive household request.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from .subject import DEFAULT_SUBJECT_ID
from .surfaces import ChannelClass

logger = logging.getLogger("halbert.attunement.context")

#: Halbert's persona id in the ledger. One machine, one mind.
DEFAULT_PERSONA_ID = "halbert"

#: A runaway guard, not a volume policy — see :func:`halbert_config`.
MAX_PROACTIVE_PER_DAY = 24

#: The channel class every shadow decision is taken at, and a known
#: over-statement. ``ProactiveGate`` makes one decision for the whole event
#: bus, whose subscribers span a bell badge (AMBIENT) and, where it is
#: wired, voice and the auto-opening panel (PUSH). PUSH is the loudest
#: surface an event here can reach, so it is the conservative choice for a
#: suppression system — but the bias has a direction and it is worth
#: knowing: the policy treats AMBIENT more permissively (a quiet dial
#: yields SPEAK_MINIMAL rather than a hold, and the social cost applies to
#: PUSH alone), so the shadow reads **quieter than the product would be**
#: if it decided per surface. ``surfaces.SURFACE_CHANNEL`` is the map to use
#: when a caller can say which surface it is about; none can today.
SHADOW_CHANNEL_CLASS = ChannelClass.PUSH


def engine_available() -> bool:
    """Whether ``haloysius.attunement`` can be imported."""
    try:
        import haloysius.attunement.types  # noqa: F401
    except ImportError:
        return False
    return True


def halbert_config() -> Any:
    """Halbert's ``AttunementConfig``, or None when the engine is absent.

    The engine's ``AttachmentSafety`` defaults are a companion's and the
    engine says so: *"any consumer may set its own numbers in its wiring
    config"*. Two of them are wrong for this product and are set here.

    ``max_proactive_per_day`` — the engine's 3 rations attention to stop a
    companion cultivating attachment. Halbert's failure mode is the
    opposite one: a missed critical. The dial is already the volume policy
    (``off``/``quiet``/``balanced``/``assertive`` with per-category
    overrides), so the cap's remaining job is to catch a detector loop.
    24 is one an hour averaged over a day: a runaway is visible, an ordinary
    day is not rationed.

    ``new_relationship_sessions`` / ``new_relationship_days`` — the engine
    mutes a companion for its first five sessions and seven days so
    intimacy is not manufactured. A machine-minder's first week is when a
    fresh install has the *most* to say — drop-in conflicts, fstab
    phantoms, permissions hygiene are all first-sweep findings. Both are
    zero here.

    ``persona_may_solicit_invitation`` stays False: Halbert never asks to be
    allowed to talk more.

    **Both numbers are pending founder ratification** (`DECISIONS.md`).
    Nothing user-visible turns on them while the decision is in shadow.
    """
    try:
        from haloysius.attunement.types import AttachmentSafety, AttunementConfig
    except ImportError:
        return None
    return AttunementConfig(
        attachment=AttachmentSafety(
            max_proactive_per_day=MAX_PROACTIVE_PER_DAY,
            new_relationship_sessions=0,
            new_relationship_days=0,
        )
    )


def dial_for(being_config: Any) -> Any:
    """``BeingConfig``'s dial and per-category overrides, in engine terms.

    An override this repo accepts but the engine does not is dropped rather
    than raising: a typo in ``being.yml`` must not take the proactive path
    down. ``BeingConfig.validate()`` is the place that rejects one.
    """
    try:
        from haloysius.attunement.types import DialLevel, ProactivityDial
    except ImportError:
        return None

    def _level(value: Any, fallback: Any = None) -> Any:
        try:
            return DialLevel(value)
        except ValueError:
            return fallback

    level = _level(getattr(being_config, "proactivity", None), DialLevel.BALANCED)
    overrides = {}
    for category, value in (getattr(being_config, "category_overrides", None) or {}).items():
        mapped = _level(value)
        if mapped is not None:
            overrides[str(category)] = mapped
    return ProactivityDial(level=level, overrides=overrides)


def _life_safety(event: Any) -> bool:
    """Whether this event is life safety. Never derived from severity (A-HB-15).

    Two sources, both of which ``ProactiveGate`` already honours: the
    engine's life-safety category set, and a confirmed acoustic anomaly
    (tagger severity >= 2), which the wake chain treats as life safety
    because a glass break at 3am is exactly when it matters.
    """
    category = getattr(event, "category", None) or ""
    try:
        from ..integrations.modality_wiring import is_life_safety_event
        if is_life_safety_event(category):
            return True
    except Exception:
        pass
    if category == "acoustic":
        data = getattr(event, "data", None)
        if isinstance(data, dict) and data.get("anomaly_severity", 0) >= 2:
            return True
    return False


def utterance_for(
    event: Any, *, channel_class: ChannelClass = SHADOW_CHANNEL_CLASS
) -> Any:
    """A ``ProactiveEvent`` as the engine's ``Utterance``, or None.

    ``source`` is the event *type* rather than its title: the engine's
    ledger is "enums, ids, numbers and timestamps only — never text", and
    a finding's title is the user's own filesystem read back.

    ``anchored`` stays False by construction. A proactive event follows up
    on nothing the person said — that is what makes it proactive — and
    claiming otherwise would buy it an exemption it has not earned.
    """
    try:
        from haloysius.attunement.types import Severity, Utterance
        from haloysius.attunement.types import ChannelClass as EngineChannel
    except ImportError:
        return None

    from ..proactive.gate import _USER_REQUESTED_TYPES

    try:
        severity = Severity(getattr(event, "severity", "info") or "info")
    except ValueError:
        severity = Severity.INFO

    return Utterance(
        source=getattr(event, "type", "") or "proactive",
        severity=severity,
        user_requested=getattr(event, "type", None) in _USER_REQUESTED_TYPES,
        category=getattr(event, "category", None) or None,
        life_safety=_life_safety(event),
        channel_class=EngineChannel(channel_class.value),
        id=getattr(event, "id", None),
    )


def build_context(
    event: Any,
    *,
    being_config: Any,
    store: Any,
    persona_id: str = DEFAULT_PERSONA_ID,
    subject_id: str = DEFAULT_SUBJECT_ID,
    channel_class: ChannelClass = SHADOW_CHANNEL_CLASS,
    signals: Any = None,
    quiet_hours_active: bool = False,
    now: Optional[str] = None,
) -> Any:
    """Assemble the context ``decide()`` needs, or None when it cannot be.

    The ledger reads are the only I/O: the subject's active standing
    requests, the invitation level, and four counters. Everything else is
    already in hand.

    ``signals`` is optional and is currently empty on the proactive path —
    nothing along it has a live view of the room. That is honest rather
    than lossy: an absent sensor reads as UNKNOWN activity and the decision
    rests on the dial, the standing requests and the ceilings, which is
    exactly the half of the policy that is wired.
    """
    try:
        from haloysius.attunement.ledger import StandingRequestLedger
        from haloysius.attunement.types import AttunementContext, SituationSignals
        from haloysius.attunement.types import SubjectConfidence as EngineConfidence
    except ImportError:
        return None

    utterance = utterance_for(event, channel_class=channel_class)
    if utterance is None:
        return None

    now = now or datetime.now(timezone.utc).isoformat()
    config = halbert_config()
    dial = dial_for(being_config)
    ledger = StandingRequestLedger(store, persona_id, config)

    state = ledger.state(subject_id)
    personality = getattr(being_config, "personality_profile", None) or {}

    return AttunementContext(
        persona_id=persona_id,
        subject_id=subject_id,
        # Nobody spoke. The primary user is who a push is addressed to, and
        # the channel — this host — is what implies them.
        subject_confidence=EngineConfidence.UNATTRIBUTED,
        now=now,
        utterance=utterance,
        signals=signals if signals is not None else SituationSignals(),
        active_requests=ledger.active(subject_id, now),
        dial=dial,
        invitation=ledger.invitation(subject_id, now, dial),
        config=config,
        quiet_hours_active=bool(quiet_hours_active),
        # Halbert has `extraversion` by that name; it has no trait that
        # means social awareness, so the engine's own default stands.
        persona_extraversion=float(personality.get("extraversion", 0.5)),
        accepted_interactions=state.accepted_interactions,
        sessions_count=state.sessions_count,
        relationship_age_days=ledger.relationship_age_days(subject_id, now),
        proactive_count_today=ledger.proactive_count_today(subject_id, now),
    )
