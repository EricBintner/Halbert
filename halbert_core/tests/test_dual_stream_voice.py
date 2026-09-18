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
