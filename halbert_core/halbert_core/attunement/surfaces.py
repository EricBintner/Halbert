# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Which Halbert surface counts as speech (HB-N4, A-HB-8).

A withdrawal must silence the voice and the panel that opens itself. It must
not empty the bell, and it must never hide a findings row — suppressing a
surface the user navigates to destroys information they asked to be able to
find.

The cut is **push versus pull**, not voice versus text: a line of narration is
text, arrives unbidden, and is push. ``AMBIENT`` is the middle value a strict
binary loses — a bell badge changes without being asked and yet demands
nothing, which is Weiser & Brown's periphery.

Values match ``haloysius.attunement.types.ChannelClass`` exactly; the enum is
declared locally so the taxonomy is testable with the engine absent.
"""

from __future__ import annotations

from enum import Enum
from typing import Mapping


class ChannelClass(str, Enum):
    """Mirror of the engine's ``ChannelClass``. Values must stay identical."""

    PUSH = "push"
    """Arrives unbidden and spends attention. Suppressed by a withdrawal."""

    AMBIENT = "ambient"
    """Changes unbidden, demands nothing. May update; must not escalate."""

    PULL = "pull"
    """Persists where the user navigates to it. Never suppressed."""


class Surface(str, Enum):
    """Every way Halbert can reach a person."""

    VOICE = "voice"
    SATELLITE_AUDIO = "satellite_audio"
    PANEL_AUTO_OPEN = "panel_auto_open"
    BELL_BADGE = "bell_badge"
    PRESENCE_PILL = "presence_pill"
    TRAY_INDICATOR = "tray_indicator"
    FINDINGS_PAGE = "findings_page"
    EVENTS_API = "events_api"
    TIMELINE = "timeline"


SURFACE_CHANNEL: Mapping[Surface, ChannelClass] = {
    # Push — makes a sound, or takes the screen.
    Surface.VOICE: ChannelClass.PUSH,
    Surface.SATELLITE_AUDIO: ChannelClass.PUSH,
    Surface.PANEL_AUTO_OPEN: ChannelClass.PUSH,
    # Ambient — the periphery. `the-being.md` §4's "indicator pulses" lives here.
    Surface.BELL_BADGE: ChannelClass.AMBIENT,
    Surface.PRESENCE_PILL: ChannelClass.AMBIENT,
    Surface.TRAY_INDICATOR: ChannelClass.AMBIENT,
    # Pull — the user goes and looks.
    Surface.FINDINGS_PAGE: ChannelClass.PULL,
    Surface.EVENTS_API: ChannelClass.PULL,
    Surface.TIMELINE: ChannelClass.PULL,
}


def channel_class_for(surface: Surface) -> ChannelClass:
    """The channel class of a surface.

    Raises rather than defaulting: an unmapped surface would silently escape
    the engagement policy, which is the failure this taxonomy exists to stop.
    """
    try:
        return SURFACE_CHANNEL[surface]
    except KeyError:  # pragma: no cover — the guard test makes this unreachable
        raise KeyError(f"surface {surface!r} has no channel class") from None
