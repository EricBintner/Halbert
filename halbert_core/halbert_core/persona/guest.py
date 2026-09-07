# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""A guest persona — a borrowed face over Halbert's body.

A paired app can lend Halbert a persona for a session: the name, manner and
directives the user hears. Halbert keeps running underneath exactly as
before — same tools, same memory, same safety gates, same background
observation. The guest is a *costume*, never a tenant: Halbert's agent
answers every turn; the guest supplies the presentation layer only.

Design: ``.handoff/DESIGN-GUEST-PERSONA-2026-09-06.md``. The invariants
this module is responsible for:

- **I1 tighten only.** ``GuestPersona.from_payload`` accepts exactly
  ``GUEST_PERSONA_FIELDS`` — a strict subset of the ratified per-persona
  "Character" fields (MULTI-PERSONA-DESIGN §Q2). Everything else in an
  offer is dropped with its name reported, never merged. The guest cannot
  pick the model, the memory namespace, vision consent, autonomy, or the
  voice mode (a guest is not the machine and never speaks as it).
- **I2 no persistence.** Nothing here reads or writes ``being.yml``, the
  personas directory or ``PersonaManager``. The override is one module-level
  object; revocation is dropping it.
- **I3 no survival.** There is no load path. A restart is always Halbert.
- **I8 guest text is voice, not authority.** Free text is capped
  (``MAX_PROMPT_CHARS`` and friends) so a persona description cannot become
  a second system prompt. Where that text lands, and what comes after it,
  is ``AgentPromptBuilder``'s job.

Lifetime (§7): the offering side must heartbeat. Expiry is evaluated lazily
on every ``current_guest()`` read — there is no timer thread to keep alive,
and a session past its deadline is treated as withdrawn by the next caller
that asks, which announces the ending once through ``on_session_end``.
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, FrozenSet, List, Mapping, Optional, Tuple
from urllib.parse import urlparse

logger = logging.getLogger("halbert.persona.guest")

# ---------------------------------------------------------------------------
# What a guest may supply
# ---------------------------------------------------------------------------

# The accepted subset. Deliberately narrower than the ratified per-persona
# list: ``voice`` (the machine's self-reference mode — a guest is not the
# machine), ``model``/``model_endpoint_id`` (which model Halbert runs is a
# compute decision, not a face), ``persona_id_override`` (the memory
# namespace — private mode is a property of the writers, §6, not of the
# persona layer), ``senses`` (vision consent — the guest gets a narrower view
# in a later phase, never a wider one), and the scheduled-speech fields
# (``proactivity``, ``quiet_hours``, ``morning_report``,
# ``category_overrides`` — open question §12 Q3) are all excluded.
GUEST_PERSONA_FIELDS: FrozenSet[str] = frozenset({
    "name",
    "voice_presentation",
    "archetype_id",
    "personality_profile",
    "tone_descriptors",
    "speech_patterns",
    "directives",
    "custom_personality_prompt",
    "purpose",
    "scene_context",
})

_LIST_FIELDS = ("tone_descriptors", "speech_patterns", "directives")
_TEXT_FIELDS = ("custom_personality_prompt", "purpose", "scene_context")
_TRAITS = ("openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism")

MAX_NAME_CHARS = 80
MAX_PROMPT_CHARS = 4000     # custom_personality_prompt
MAX_TEXT_CHARS = 600        # purpose, scene_context
MAX_LIST_ITEMS = 20
MAX_ITEM_CHARS = 300

# How long an offer stands without a heartbeat. The offering side is expected
# to beat well inside this.
DEFAULT_TTL_SECONDS = 60.0
MAX_TTL_SECONDS = 600.0


class GuestValidationError(ValueError):
    """The offered payload is not a persona Halbert will wear."""


class GuestConflict(RuntimeError):
    """Another peer's session is live, or the caller does not own this one."""


def _one_line(value: Any, field_name: str, limit: int) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise GuestValidationError(f"{field_name} must be a string")
    text = value.strip()
    if "\n" in text or "\r" in text:
        raise GuestValidationError(f"{field_name} must be a single line")
    if len(text) > limit:
        raise GuestValidationError(f"{field_name} is longer than {limit} characters")
    return text


def _text(value: Any, field_name: str, limit: int) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise GuestValidationError(f"{field_name} must be a string")
    text = value.strip()
    if len(text) > limit:
        raise GuestValidationError(f"{field_name} is longer than {limit} characters")
    return text


def _string_list(value: Any, field_name: str) -> List[str]:
    if value is None:
        return []
    if not isinstance(value, (list, tuple)):
        raise GuestValidationError(f"{field_name} must be a list of strings")
    if len(value) > MAX_LIST_ITEMS:
        raise GuestValidationError(f"{field_name} has more than {MAX_LIST_ITEMS} items")
    out: List[str] = []
    for item in value:
        if not isinstance(item, str):
            raise GuestValidationError(f"{field_name} must be a list of strings")
        item = " ".join(item.split())
        if len(item) > MAX_ITEM_CHARS:
            raise GuestValidationError(f"{field_name} item is longer than {MAX_ITEM_CHARS} characters")
        if item:
            out.append(item)
    return out


def _profile(value: Any) -> Dict[str, float]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise GuestValidationError("personality_profile must be a mapping of trait to 0..1")
    out: Dict[str, float] = {}
    for trait, score in value.items():
        if trait not in _TRAITS:
            raise GuestValidationError(f"personality_profile has an unknown trait: {trait!r}")
        try:
            score = float(score)
        except (TypeError, ValueError):
            raise GuestValidationError(f"personality_profile[{trait}] must be a number")
        if not 0.0 <= score <= 1.0:
            raise GuestValidationError(f"personality_profile[{trait}] must be within 0..1")
        out[trait] = score
    return out


@dataclass(frozen=True)
class GuestPersona:
    """The persona-scoped fields a guest supplies. Duck-typed for
    ``personality_prompt.generate_personality_section``."""

    name: str
    voice_presentation: str = "not_defined"
    archetype_id: Optional[str] = None
    personality_profile: Dict[str, float] = field(default_factory=dict)
    tone_descriptors: List[str] = field(default_factory=list)
    speech_patterns: List[str] = field(default_factory=list)
    directives: List[str] = field(default_factory=list)
    custom_personality_prompt: str = ""
    purpose: str = ""
    scene_context: str = ""

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> Tuple["GuestPersona", List[str]]:
        """Validate an offer. Returns the persona and the names of the
        fields that were dropped because they are not the guest's to set."""
        if not isinstance(payload, Mapping):
            raise GuestValidationError("persona must be a mapping")
        dropped = sorted(k for k in payload if k not in GUEST_PERSONA_FIELDS)
        for name in dropped:
            logger.info("Guest persona offer: dropped field %r (not a persona field)", name)

        name = _one_line(payload.get("name"), "name", MAX_NAME_CHARS)
        if not name:
            raise GuestValidationError("name is required")

        vp = _one_line(payload.get("voice_presentation"), "voice_presentation", 20) or "not_defined"
        if vp not in ("not_defined", "male", "female"):
            raise GuestValidationError("voice_presentation must be not_defined, male or female")

        archetype = _one_line(payload.get("archetype_id"), "archetype_id", MAX_NAME_CHARS) or None

        return cls(
            name=name,
            voice_presentation=vp,
            archetype_id=archetype,
            personality_profile=_profile(payload.get("personality_profile")),
            tone_descriptors=_string_list(payload.get("tone_descriptors"), "tone_descriptors"),
            speech_patterns=_string_list(payload.get("speech_patterns"), "speech_patterns"),
            directives=_string_list(payload.get("directives"), "directives"),
            custom_personality_prompt=_text(
                payload.get("custom_personality_prompt"), "custom_personality_prompt", MAX_PROMPT_CHARS),
            purpose=_text(payload.get("purpose"), "purpose", MAX_TEXT_CHARS),
            scene_context=_text(payload.get("scene_context"), "scene_context", MAX_TEXT_CHARS),
        ), dropped


# ---------------------------------------------------------------------------
# The guest's home
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GuestHome:
    """Where the guest's own memory lives: a paired sibling's per-persona
    API (``persona/sibling.py``). The guest's words go there and are
    recalled from there, never from a namespace on this disk (design §4.3).
    The token is the credential Halbert presents to the home; it is never
    rendered."""

    base_url: str
    persona_id: str
    token: str = ""
    label: str = ""

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "GuestHome":
        if not isinstance(payload, Mapping):
            raise GuestValidationError("home must be a mapping")
        url = _one_line(payload.get("base_url"), "home.base_url", 300)
        parts = urlparse(url) if url else None
        if not url or parts.scheme not in ("http", "https") or not parts.netloc:
            raise GuestValidationError("home.base_url must be an http(s) URL")
        persona_id = _one_line(payload.get("persona_id"), "home.persona_id", 120)
        if not persona_id:
            raise GuestValidationError("home.persona_id is required")
        return cls(
            base_url=url.rstrip("/"),
            persona_id=persona_id,
            token=_one_line(payload.get("token"), "home.token", 512),
            label=_one_line(payload.get("label"), "home.label", MAX_NAME_CHARS),
        )

    def to_dict(self) -> Dict[str, str]:
        return {"base_url": self.base_url, "persona_id": self.persona_id, "label": self.label}


# ---------------------------------------------------------------------------
# The session
# ---------------------------------------------------------------------------

@dataclass
class GuestSession:
    id: str
    persona: GuestPersona
    offered_by: str            # the peer's node id
    offered_by_name: str
    started_at: str            # ISO-8601 UTC, for display
    started_mono: float        # monotonic clock, for deadlines
    ttl_seconds: float
    deadline: float
    home: Optional[GuestHome] = None
    # A pulled session has nobody on the other side to heartbeat. When the
    # deadline passes, this is asked instead — at most once per window —
    # and a False (or a raise) ends the session as ``home_unreachable``.
    keepalive: Optional[Callable[[], bool]] = field(default=None, repr=False, compare=False)
    ended_mono: Optional[float] = None
    end_reason: Optional[str] = None
    ended_by: str = ""
    _renewing: bool = field(default=False, repr=False, compare=False)

    def active(self, now: Optional[float] = None) -> bool:
        if self.end_reason is not None:
            return False
        return (time.monotonic() if now is None else now) < self.deadline

    def to_dict(self, now: Optional[float] = None) -> Dict[str, Any]:
        now = time.monotonic() if now is None else now
        return {
            "session_id": self.id,
            "name": self.persona.name,
            "offered_by": self.offered_by,
            "offered_by_name": self.offered_by_name,
            "started_at": self.started_at,
            "seconds_until_expiry": max(0.0, self.deadline - now),
            "active": self.active(now),
            "end_reason": self.end_reason,
            "home": self.home.to_dict() if self.home else None,
        }


_lock = threading.RLock()
_session: Optional[GuestSession] = None
_observers: Dict[str, Callable[[GuestSession], None]] = {}


def _now(now: Optional[float]) -> float:
    return time.monotonic() if now is None else now


def _end_locked(session: GuestSession, reason: str, by: str, now: float) -> None:
    """Mark ``session`` ended and clear it if it is the current one. Caller
    holds the lock; observers run after it is released."""
    global _session
    if session.end_reason is not None:
        return
    session.end_reason = reason
    session.ended_by = by
    session.ended_mono = now
    if _session is session:
        _session = None
    logger.info("Guest session %s (%s) ended: %s", session.id, session.persona.name, reason)


def _notify(session: GuestSession) -> None:
    for key, callback in list(_observers.items()):
        try:
            callback(session)
        except Exception as e:  # an observer bug must not keep a face on
            logger.warning("Guest session observer %s failed: %s", key, e)


def current_guest(now: Optional[float] = None) -> Optional[GuestSession]:
    """The session fronting right now, or None. A session past its heartbeat
    deadline is ended here, on the read, and announced once."""
    now = _now(now)
    keep: Optional[Callable[[], bool]] = None
    with _lock:
        session = _session
        if session is None:
            return None
        if session.active(now):
            return session
        if session.keepalive is not None and not session._renewing:
            session._renewing = True
            keep = session.keepalive
    if keep is not None:
        # Outside the lock: this may be a network round trip. Bounded by
        # the transport's timeout and by once-per-window.
        ok = False
        try:
            ok = bool(keep())
        except Exception as e:
            logger.info("Guest session %s keepalive failed: %s", session.id, e)
        with _lock:
            session._renewing = False
            if ok and _session is session and session.end_reason is None:
                session.deadline = now + session.ttl_seconds
                return session
            _end_locked(session, "home_unreachable", "", now)
        _notify(session)
        return None
    with _lock:
        if session.end_reason is not None:
            return None
        _end_locked(session, "heartbeat_missed", "", now)
    _notify(session)
    return None


def offer(
    persona: GuestPersona,
    offered_by: str,
    offered_by_name: str = "",
    ttl_seconds: float = DEFAULT_TTL_SECONDS,
    now: Optional[float] = None,
    home: Optional[GuestHome] = None,
    keepalive: Optional[Callable[[], bool]] = None,
) -> GuestSession:
    """Install ``persona`` as the face for a session.

    One face at a time: a live session from another peer refuses the offer
    (``GuestConflict``); the same peer re-offering replaces its own.
    ``home`` is where the guest's words go; ``keepalive`` replaces the
    heartbeat for a session Halbert pulled itself.
    """
    if not offered_by:
        raise GuestValidationError("offered_by is required")
    ttl = float(ttl_seconds)
    if not 1.0 <= ttl <= MAX_TTL_SECONDS:
        raise GuestValidationError(f"ttl_seconds must be within 1..{MAX_TTL_SECONDS:g}")
    now = _now(now)
    replaced: Optional[GuestSession] = None
    with _lock:
        live = current_guest(now)
        if live is not None:
            if live.offered_by != offered_by:
                raise GuestConflict(
                    f"{live.offered_by_name or live.offered_by} already has a persona fronting")
            _end_locked(live, "replaced", offered_by, now)
            replaced = live
        session = GuestSession(
            id=uuid.uuid4().hex,
            persona=persona,
            offered_by=offered_by,
            offered_by_name=offered_by_name or "",
            started_at=datetime.now(timezone.utc).isoformat(),
            started_mono=now,
            ttl_seconds=ttl,
            deadline=now + ttl,
            home=home,
            keepalive=keepalive,
        )
        global _session
        _session = session
    if replaced is not None:
        _notify(replaced)
    logger.info("Guest session %s: %s fronting, offered by %s", session.id, persona.name, offered_by)
    return session


def heartbeat(session_id: str, offered_by: str, now: Optional[float] = None) -> GuestSession:
    """Keep a session alive. Only the peer that offered it may."""
    now = _now(now)
    with _lock:
        live = current_guest(now)
        if live is None or live.id != session_id:
            raise LookupError("no live guest session with that id")
        if live.offered_by != offered_by:
            raise GuestConflict("that session was offered by another peer")
        live.deadline = now + live.ttl_seconds
        return live


def withdraw(reason: str = "withdrawn", by: str = "", now: Optional[float] = None) -> Optional[GuestSession]:
    """End the current session, whoever asks: the offering peer, the user
    from the Presence Pill, or the guest's own handback. Returns the ended
    session, or None when nothing was fronting."""
    now = _now(now)
    with _lock:
        live = current_guest(now)
        if live is None:
            return None
        _end_locked(live, reason, by, now)
    _notify(live)
    return live


def handback(now: Optional[float] = None) -> Optional[GuestSession]:
    """The guest hands the conversation back to Halbert."""
    return withdraw(reason="handback", by="guest", now=now)


def on_session_end(
    callback: Callable[[GuestSession], None],
    key: Optional[str] = None,
) -> Callable[[], None]:
    """Hear every ending once (withdrawn, handback, replaced,
    heartbeat_missed). Returns an unsubscribe function.

    ``key`` makes a subscription idempotent: subscribing again under the
    same key replaces the earlier callback instead of adding a second."""
    key = key or uuid.uuid4().hex
    with _lock:
        _observers[key] = callback

    def unsubscribe() -> None:
        with _lock:
            _observers.pop(key, None)

    return unsubscribe


def reset_for_tests() -> None:
    """Drop the session and every observer. What a process restart amounts
    to — there is no load path (I3)."""
    global _session
    with _lock:
        _session = None
        _observers.clear()
