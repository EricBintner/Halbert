# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The surface taxonomy (HB-N4, A-HB-8).

"Leave me alone" is about speech, not about surfaces. These tests pin which
Halbert surface is which class, because the whole point of the amendment is
that a withdrawal silences the voice without emptying the bell or hiding a
findings row.
"""

import pytest

from halbert_core.attunement.surfaces import (
    ChannelClass,
    Surface,
    SURFACE_CHANNEL,
    channel_class_for,
)


def test_every_surface_has_a_channel_class():
    """No surface may be unclassified — an unmapped surface defaults to nothing
    and would silently escape the policy."""
    missing = [s for s in Surface if s not in SURFACE_CHANNEL]
    assert missing == [], f"unclassified surfaces: {missing}"


@pytest.mark.parametrize(
    "surface,expected",
    [
        (Surface.VOICE, ChannelClass.PUSH),
        (Surface.SATELLITE_AUDIO, ChannelClass.PUSH),
        (Surface.PANEL_AUTO_OPEN, ChannelClass.PUSH),
        (Surface.BELL_BADGE, ChannelClass.AMBIENT),
        (Surface.PRESENCE_PILL, ChannelClass.AMBIENT),
        (Surface.TRAY_INDICATOR, ChannelClass.AMBIENT),
        (Surface.FINDINGS_PAGE, ChannelClass.PULL),
        (Surface.EVENTS_API, ChannelClass.PULL),
        (Surface.TIMELINE, ChannelClass.PULL),
    ],
)
def test_surface_classification(surface, expected):
    assert channel_class_for(surface) is expected


def test_the_findings_list_is_never_push():
    """A pull surface suppressed by attunement is a data-integrity failure
    dressed as politeness."""
    for surface in (Surface.FINDINGS_PAGE, Surface.EVENTS_API, Surface.TIMELINE):
        assert channel_class_for(surface) is ChannelClass.PULL


def test_channel_class_values_match_the_engine_contract():
    """The engine's ChannelClass is a str enum with these exact values; ours
    must serialise to the same strings or the Utterance is built wrong."""
    assert ChannelClass.PUSH.value == "push"
    assert ChannelClass.AMBIENT.value == "ambient"
    assert ChannelClass.PULL.value == "pull"
