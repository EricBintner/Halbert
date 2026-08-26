# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Halbert-owned cross-session continuity.

Founder direction 2026-08-26 (D1): Haloysius has no cross-session understanding.
It owns the mind's *present* state — cognition, drives, worries, persona, the
state-tracker protocol. Halbert owns memory *across time*: threads, receipts,
recall, open loops and machine-state history. This package is that second half.

See ``.handoff/HANDOFF-CONTINUITY-AFTER-PLAN-A-2026-08-26.md``.
"""

from .state_store import StateStore, StateTriple

__all__ = ["StateStore", "StateTriple"]
