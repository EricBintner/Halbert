# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Skills usage telemetry — the `skill_events` table and its seams (SK-2).

Design DESIGN-SKILLS-SYSTEM-2026-09-07 §6: usage telemetry ships with the
surface it measures, from day one, because retrofitting is impossible
(OpenClaw §7: "every tool call is matched against known SKILL.md paths →
per-run skill-activation receipts"). Two seams write rows:

* **reads (seam 1)** — `tools/executor.py`'s `_read_file` resolves each
  path against the registry's known skill paths before dispatch; a hit
  appends a `read` receipt. This single choke point catches every Track-B
  consultation regardless of which surface asked.
* **activations (seam 2)** — matcher and explicit activations, today only
  a debug log line, are promoted to the same table by the state machine
  at the point the turn's skills are first known.

Rows are keyed by the **stable skill id**, never the name — the same
identity discipline as provenance (§5.4): name is mutable display data,
and a rename or a colliding pack name must not smear one skill's history
over another's. The name rides in `detail_json` as display context only.

Telemetry is a reportability feature, never a gate (the turn-digest
rule): every function here fails soft — a missing store, a broken
registry or an unwritable row costs nothing but a log line.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

#: The design's event vocabulary (§6). SK-2 emits `read`, `matched` and
#: `explicit` — the two seams this packet ships. `linted` is SK-5's,
#: `promoted`/`archived`/`absorbed`/`verification_run` are SK-6/SK-7's,
#: and `catalog_listed` stays unemitted until a consumer asks for it:
#: a row per skill per turn with no reader is spam, and the design names
#: the consumers (curator, learning loop, dashboard) as future packets.
EVENTS = (
    "catalog_listed",
    "matched",
    "explicit",
    "read",
    "linted",
    "verification_run",
    "promoted",
    "archived",
    "absorbed",
)

#: The registry whose skill paths seam 1 resolves against. Set once at
#: wiring (dashboard/routes/agent.py), read on every read_file dispatch.
#: A process holds one live registry; the catalog renderer keys its memo
#: on the registry's snapshot_version, and that version never repeats,
#: so a re-wire cannot hand stale entries to either consumer.
_active_registry = None


def set_active_registry(registry) -> None:
    """Point the process's read seam at *registry* (None to disarm)."""
    global _active_registry
    _active_registry = registry


def active_registry():
    """The registry wired at daemon startup, or None."""
    return _active_registry


def _store():
    """The conversation store the events table lives alongside.

    Lazy and tolerant: threads owns the process-wide manager, and a
    daemon without one (or a satellite whose store proxies to the
    canonical host and does not carry this table) simply writes nothing.
    """
    try:
        from ..agents.threads import get_thread_manager

        manager = get_thread_manager()
        return getattr(manager, "store", None)
    except Exception:
        logger.debug("skill telemetry has no conversation store", exc_info=True)
        return None


def current_persona() -> Optional[str]:
    """The persona fronting this turn, or None when the machine itself is.

    The row records whose turn produced the event (a guest's consultation
    is the guest's, on the machine's record); persona-dimensioned
    *catalogs* are SK-3's, and this column is deliberately just a fact.
    """
    try:
        from ..persona.guest import current_guest

        guest = current_guest()
        return getattr(guest.persona, "name", None) if guest else None
    except Exception:
        return None


def _turn_ids() -> Dict[str, Optional[str]]:
    """run_id/session_id from the turn scope, where the seams run.

    `read` rows are written from inside tool handlers, which take only
    their args dict — the ids ride ContextVars (the same pattern as
    provenance.current_turn and the terminal bridge's session var).
    Activation rows run inside the turn lock, where the same ContextVars
    are already set, so both seams stamp identical ids without threading
    a parameter through every handler.
    """
    out: Dict[str, Optional[str]] = {"run_id": None, "session_id": None}
    try:
        from ..continuity.provenance import current_turn

        out["run_id"] = current_turn.get()
    except Exception:
        pass
    try:
        from ..streaming.terminal_bridge import current_agent_session

        out["session_id"] = current_agent_session.get()
    except Exception:
        pass
    return out


def _telemetry_permitted() -> bool:
    """Whether this turn's conversation may leave telemetry (FD-19).

    Fails CLOSED: a predicate that cannot be read is not permission. The
    thread manager owns the question -- the same one it already asks
    before recording promotion evidence -- so there is one answer rather
    than two that can disagree.
    """
    try:
        from ..agents.threads import _conversation_is_halberts
        return bool(_conversation_is_halberts())
    except Exception as e:
        logger.debug("skill telemetry suppressed (cannot tell whose "
                     "conversation this is): %s", e)
        return False


def record_skill_event(skill_id: str, event: str, *,
                       session_id: Optional[str] = None,
                       run_id: Optional[str] = None,
                       persona: Optional[str] = None,
                       detail: Optional[dict] = None) -> bool:
    """Append one row. True when a row landed; never raises.

    `persona` defaults to the fronting guest when the caller does not
    know better — one place computes it so the rows stay consistent.
    """
    if event not in EVENTS:
        logger.warning("refusing unknown skill event %r (not one of EVENTS)",
                       event)
        return False
    if not skill_id:
        return False
    # A13-G7 (FD-19): telemetry is suppressed entirely when the
    # conversation is not Halbert's. A guest fronting, or a private-mode
    # turn, would otherwise leave a durable record of which skills their
    # words matched -- evidence about a person who never agreed to be
    # measured, in a table their "forget me" did not reach.
    if not _telemetry_permitted():
        logger.debug(
            "skill event %s for %s suppressed: this conversation is not "
            "Halbert's", event, skill_id)
        return False
    try:
        store = _store()
        if store is None:
            logger.debug("skill event %s for %s dropped: no store",
                         event, skill_id)
            return False
        return store.append_skill_event(
            skill_id=skill_id,
            event=event,
            run_id=run_id,
            session_id=session_id,
            persona=persona if persona is not None else current_persona(),
            detail=detail,
        ) is not None
    except Exception:
        logger.warning("recording skill event %s failed; continuing",
                       event, exc_info=True)
        return False


def record_skill_read(path: Any, *,
                      session_id: Optional[str] = None,
                      run_id: Optional[str] = None) -> Optional[str]:
    """Resolve *path* against the known skill paths; a hit appends a
    `read` receipt and returns the skill's stable id, else None.

    Seam 1's half that lives here: the executor hands over the already-
    normalized path, this resolves it (the SKILL.md itself, or anything
    under the skill's own directory — its references/ and scripts/) and
    writes the row with the turn's ContextVar ids. Never raises: a
    receipt that cannot be written costs the log line, never the read.
    """
    try:
        registry = active_registry()
        if registry is None:
            return None
        skill = registry.skill_for_path(path)
        if skill is None or not getattr(skill, "id", None):
            return None
        ids = _turn_ids()
        record_skill_event(
            skill.id, "read",
            session_id=session_id if session_id is not None else ids["session_id"],
            run_id=run_id if run_id is not None else ids["run_id"],
            detail={"name": skill.name, "path": str(path)},
        )
        return skill.id
    except Exception:
        logger.warning("recording a skill read failed; continuing",
                       exc_info=True)
        return None