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
