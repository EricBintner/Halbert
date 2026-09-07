# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Private mode is a set of sources handed to the guest.

The user names sources — this webcam, this microphone, that camera — and
for the rest of the guest session those sources are the guest's: their
observations do not enter Halbert's stores (``continuity/ownership.py``
routes them), and the transcript goes to the guest's home. Nothing else
changes. Assigning the first source is what switches private mode on.

Source ids are registry ids (``webcam:0``, ``screen:1``, ``frigate:patio``,
``mic:local:0``); the registry that names local vision sources is VIS-1's
(``DESIGN-VISION-SOURCE-REGISTRY-2026-09-06.md``). This module validates the
shape, not the existence — the picker that lists real sources is the UI's.

Bound to the guest session (D4): a source can only be assigned while a
guest fronts, the map is cleared the moment that session ends however it
ends, and nothing here has a load path across a restart. A private session
that silently resumes recording after a crash is the worst outcome, so it
does not resume at all.
"""
from __future__ import annotations

import logging
import re
import threading
from typing import Dict, Optional

from ..continuity.ownership import Owner

logger = logging.getLogger("halbert.persona.private_sources")

_SOURCE_ID = re.compile(r"^[a-z][a-z0-9_]*:[A-Za-z0-9_.:-]{1,120}$")
MAX_SOURCE_ID_CHARS = 128
_OBSERVER_KEY = "persona.private_sources"


class NoGuestFronting(RuntimeError):
    """A source can only be handed to a guest who is fronting."""


class BadSourceId(ValueError):
    """Not a registry-shaped source id."""


_lock = threading.RLock()
_session_id: Optional[str] = None
_sources: Dict[str, Owner] = {}


def _validate(source_id: str) -> str:
    if not isinstance(source_id, str) or len(source_id) > MAX_SOURCE_ID_CHARS or not _SOURCE_ID.match(source_id):
        raise BadSourceId(f"not a source id: {source_id!r} (expected kind:native, e.g. webcam:0)")
    return source_id


def _live_session():
    from .guest import current_guest
    return current_guest()


def _on_guest_end(session) -> None:
    with _lock:
        if _session_id is not None and session.id == _session_id:
            _clear_locked("guest session ended")


def _clear_locked(why: str) -> None:
    global _session_id
    if _sources:
        logger.info("Private sources released (%s): %s", why, sorted(_sources))
    _sources.clear()
    _session_id = None


def _sync_locked() -> None:
    """Drop the map if the session it was bound to is no longer the one
    fronting. Belt to the observer's braces."""
    if _session_id is None:
        return
    live = _live_session()
    if live is None or live.id != _session_id:
        _clear_locked("session no longer fronting")


def assign(source_id: str, owner: Owner = Owner.GUEST) -> None:
    """Hand ``source_id`` to the fronting guest for the rest of its session."""
    global _session_id
    source_id = _validate(source_id)
    if owner is not Owner.GUEST:
        raise ValueError("a source is handed to the guest; use release() to take it back")
    live = _live_session()
    if live is None:
        raise NoGuestFronting("no guest persona is fronting")
    from .guest import on_session_end
    with _lock:
        if _session_id != live.id:
            _clear_locked("new session")
            _session_id = live.id
        _sources[source_id] = owner
    on_session_end(_on_guest_end, key=_OBSERVER_KEY)
    logger.info("Source %s handed to %s for session %s", source_id, live.persona.name, live.id)


def release(source_id: str) -> None:
    source_id = _validate(source_id)
    with _lock:
        _sync_locked()
        _sources.pop(source_id, None)
        if not _sources:
            _clear_locked("last source released")


def owner_of(source_id: str) -> Owner:
    with _lock:
        _sync_locked()
        return _sources.get(source_id, Owner.HALBERT)


def assigned() -> Dict[str, Owner]:
    with _lock:
        _sync_locked()
        return dict(_sources)


def active() -> bool:
    """Private mode is on exactly when at least one source is the guest's."""
    with _lock:
        _sync_locked()
        return bool(_sources)


def clear() -> None:
    """The user takes every source back; the guest keeps fronting."""
    with _lock:
        _clear_locked("cleared")


def catalogue() -> list:
    """Every source the user could hand over, with the ownership it has now.

    One list across the senses, because the founder's rule is that a private
    mode which gates one sense and not another is worse than none — so the
    picker has to be able to show them together and say which are still
    Halbert's.

    Sources whose subsystem is unavailable are simply absent; this never
    raises, because a picker that cannot render is a worse failure than a
    picker missing a camera.
    """
    out = []
    seen = set()

    machine = _machine_name()

    def add(sid, label, kind):
        if not sid or sid in seen:
            return
        seen.add(sid)
        out.append({
            "id": sid,
            "label": label or sid,
            "kind": kind,
            "owner": owner_of(sid).value,
            # The sentence for THIS source, written once, here. The pill used
            # to carry its own copy and the two had already drifted: ours said
            # "what {label} sees", the pill's said "what it sees" with no
            # label, which reads as every camera — and handing over the desk
            # webcam does not stop the patio camera.
            "statement": statement(label or sid, machine),
        })

    try:
        from ..vision.sources import ACTIVE_WINDOW_SOURCE_ID, list_sources
        for src in list_sources():
            if src.enabled:
                add(src.id, src.label, src.kind)
        add(ACTIVE_WINDOW_SOURCE_ID, "Whatever screen you are looking at", "screen")
    except Exception as e:
        logger.debug("Vision sources unavailable for the picker: %s", e)

    try:
        from ..dashboard.routes.audio import get_audio_pipeline
        pipeline = get_audio_pipeline()
        for adapter in (getattr(pipeline, "_ingress_adapters", None) or []):
            if getattr(adapter, "is_running", False):
                add(getattr(adapter, "source_id", ""), getattr(adapter, "area_id", "") or "Microphone", "mic")
    except Exception as e:
        logger.debug("Audio sources unavailable for the picker: %s", e)

    return out


def _machine_name() -> str:
    try:
        from ..identity import resolve_entity_name
        return resolve_entity_name()
    except Exception:
        return "Halbert"


def statement(label: str, machine: str) -> str:
    """What the user is told the moment they hand over the first source.

    The private-mode review's P6: the line has to be in the interface, not
    only in a design document, because a toggle labelled "private" with no
    stated scope is a promise the system cannot keep — the cameras, the
    microphone and the house sensors do not stop.
    """
    return (
        f"{machine} stops recording what you say and what {label} sees. "
        f"It keeps recording what the machine and the rest of the house are "
        f"doing. Life safety still reaches {machine}."
    )


def reset_for_tests() -> None:
    with _lock:
        _clear_locked("reset")
