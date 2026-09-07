# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The vision side of the ownership seam.

Three background watchers produce observations without going through a tool or
a route — ``VisualWatcher``, ``ZoneWatcher`` and ``AmbientWebcamMonitor``, each
on its own daemon thread — so each needs the gate the Frigate mapper, the
acoustic bridge and the HA mapper already have. Rather than three copies of the
same six lines, they share these two.

Deliberately synchronous. All three call sites build a fresh event loop per
callback (``watcher.py``, ``zone_watcher.py``, ``ambient_webcam.py`` each do
``asyncio.new_event_loop()`` inside a thread), so anything that had to be
awaited could not be dropped in where the decision belongs.

Fails to Halbert. A gate that raised would stop a watcher; a gate that
defaulted to the guest would hand over a camera nobody handed over.
"""
from __future__ import annotations

import logging

from ..continuity.ownership import Owner

logger = logging.getLogger("halbert.vision.gate")

__all__ = ["Owner", "route_vision", "forward_to_guest"]


def route_vision(source_id: str, *, life_safety: bool = False) -> Owner:
    """Who this observation belongs to right now."""
    try:
        from ..continuity.ownership import route_observation
        return route_observation(source_id, life_safety=life_safety)
    except Exception as e:
        logger.debug("Vision ownership lookup failed, keeping it Halbert's: %s", e)
        return Owner.HALBERT


def forward_to_guest(text: str, source_id: str) -> None:
    """Send an observation from a handed-over source to the guest's home.

    Best effort: the guest not hearing about its own camera is a lesser
    failure than a watcher thread dying, and the observation has already been
    withheld from Halbert by the time this is called.
    """
    try:
        from ..persona import sibling
        from ..persona.guest import current_guest
        session = current_guest()
        if session is None:
            return
        sibling.forward_observation(session, f"[{source_id}] {text}", source_id)
    except Exception as e:
        logger.debug("Private-source observation not forwarded: %s", e)
