# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Dual-stream voice turns: a digest for the ear, a body for the screen.

A voice turn used to produce ONE stream. `build_response_prompt`'s voice
branch asked for short plain text with no markdown, capped at the engine's
12-35 word risk budget, and the demuxer set `display_text` to that same
line -- so there was no technical body to stage on a screen, write to a
note, or page through. The four-layer progressive-disclosure design was
describing a system that did not exist.

The engine was always ready: `split_channels` maps `<speech>` to PERSONA
(spoken) and `<text>` to SILENT (screen-only). Only the producer was
missing.

These tests pin the five things that had to be true before the prompt
could be flipped:

- a screen being PRESENT is not the same as it being PRIVATE (a wall
  kiosk answers True to `has_screen`);
- the display copy takes the engine's shape-based redaction when the
  screen is shared, because a bystander reading the wall is the
  bystander the speech redaction exists for;
- control tags never reach the screen, because `display_text` is
  deliberately verbatim;
- the spoken budget is soft only where it is an attention budget, and
  hard wherever `must_defer_details` makes it a disclosure boundary;
- a screenless satellite never hears "I've put it on screen".
"""

import pytest

from halbert_core.integrations.channel_capability import HalbertChannelCapability


# ---------------------------------------------------------------------------
# Task 1: present vs private
# ---------------------------------------------------------------------------

def test_desktop_screen_is_both_present_and_private():
    cap = HalbertChannelCapability(is_desktop=True)
    assert cap.has_screen() is True
    assert cap.has_private_screen() is True


def test_kiosk_has_a_screen_but_it_is_not_private():
    cap = HalbertChannelCapability(is_desktop=True, kiosk=True)
    assert cap.has_screen() is True
    assert cap.has_private_screen() is False


def test_satellite_has_neither():
    cap = HalbertChannelCapability(is_desktop=False, wyoming_active=True)
    assert cap.has_screen() is False
    assert cap.has_private_screen() is False


def test_screen_is_private_degrades_closed_without_a_seam(monkeypatch):
    """No engine, no seam, no answer -- so the answer is 'not private'."""
    from halbert_core.integrations import modality_wiring

    monkeypatch.setattr(modality_wiring, "_engine_available", lambda: False)
    assert modality_wiring.screen_is_private() is False


def test_a_satellite_turn_is_not_a_private_screen():
    """The one non-private body production can actually produce.

    ``is_desktop`` has no caller outside tests and ``kiosk`` needs an env
    flag on the backend unit, so both stay at their defaults on a running
    host. ``set_wyoming_active`` is different: ``wyoming_agent`` calls it
    around every satellite turn (``wyoming_agent.py:381`` / ``:482``).
    Until it was checked here, a turn spoken into a room with no screen in
    it still answered True.
    """
    cap = HalbertChannelCapability(is_desktop=True)
    assert cap.has_private_screen() is True
    cap.set_wyoming_active(True)
    assert cap.has_private_screen() is False
    cap.set_wyoming_active(False)
    assert cap.has_private_screen() is True


@pytest.mark.parametrize(
    "value", ["1", "true", "TRUE", " True ", "yes", "on", "y", "enable", "enabled"]
)
def test_every_accepted_kiosk_spelling_reaches_the_backend(monkeypatch, value):
    """An unrecognised spelling here does not cost a feature, it leaves a
    wall panel reporting a private screen. So the accepted set is wider
    than the repo's usual three."""
    from halbert_core.integrations.app_seam import HalbertAppSeam

    monkeypatch.setenv("HALBERT_KIOSK", value)
    cap = HalbertAppSeam().get_channel_capability()
    assert cap.has_private_screen() is False


@pytest.mark.parametrize("value", ["", "0", "false", "no", "off"])
def test_kiosk_unset_or_false_keeps_the_desk_default(monkeypatch, value):
    from halbert_core.integrations.app_seam import HalbertAppSeam

    monkeypatch.setenv("HALBERT_KIOSK", value)
    cap = HalbertAppSeam().get_channel_capability()
    assert cap.has_private_screen() is True


# --- screen_is_private: every branch that has to fail closed ---------------

class _PrivateCap:
    def has_private_screen(self):
        return True


class _RaisingCap:
    def has_private_screen(self):
        raise RuntimeError("capability blew up")


class _OldCap:
    """A capability from before this accessor existed."""


def _wire_resolver(monkeypatch, resolver):
    """Point `screen_is_private` at a resolver of our choosing."""
    pytest.importorskip("haloysius.seam")
    import haloysius.seam as seam

    from halbert_core.integrations import modality_wiring

    monkeypatch.setattr(modality_wiring, "_engine_available", lambda: True)
    monkeypatch.setattr(seam, "resolve_channel_capability", resolver)
    return modality_wiring


def test_screen_is_private_says_yes_when_the_capability_does(monkeypatch):
    """The positive control. Without it the four tests below would pass
    just as well against a function that returned False unconditionally."""
    wiring = _wire_resolver(monkeypatch, lambda: _PrivateCap())
    assert wiring.screen_is_private() is True


def test_screen_is_private_fails_closed_when_there_is_no_capability(monkeypatch):
    wiring = _wire_resolver(monkeypatch, lambda: None)
    assert wiring.screen_is_private() is False


def test_screen_is_private_fails_closed_on_a_capability_too_old_to_answer(monkeypatch):
    wiring = _wire_resolver(monkeypatch, lambda: _OldCap())
    assert wiring.screen_is_private() is False


def test_screen_is_private_fails_closed_when_resolution_raises(monkeypatch):
    def _boom():
        raise RuntimeError("seam blew up")

    wiring = _wire_resolver(monkeypatch, _boom)
    assert wiring.screen_is_private() is False


def test_screen_is_private_fails_closed_when_the_getter_raises(monkeypatch):
    wiring = _wire_resolver(monkeypatch, lambda: _RaisingCap())
    assert wiring.screen_is_private() is False
