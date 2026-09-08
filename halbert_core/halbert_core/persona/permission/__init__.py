# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The five-axis permission evaluator (D-3).

``effective = ceiling ∧ affordance ∧ os_grant ∧ consent ∧ ¬halted``

PERMISSION-AND-CONSENT-SYSTEM-2026-09-06.md, Part 1. This package is the
pure evaluator: closed vocabularies, fail-closed defaults, structured
decisions that name the decisive axis — no LLM, no live wiring (the wiring
packets D3-P5/P6 consume these modules through review-gated passes).

It composes with the persona policy lattice (``halbert_core.persona.policy``):
an axis denial contributes a ``SecurityLevel.DENY`` floor to any
``merge_policies`` fold, so no layer's generosity can loosen what the axes
refuse. It never replaces the lattice, and it never touches the warrant
layer's legitimacy question (composition rule, packet 02).
"""
from __future__ import annotations

from .ceiling import (
    CapabilityCeiling,
    CapabilityKind,
    CONSENTING_KINDS,
    EMPTY_CEILING,
    NEVER_CEILING_IDS,
    VOCABULARY,
    ceiling_from_ids,
    takes_consent_records,
)

__all__ = [
    "CapabilityCeiling", "CapabilityKind", "CONSENTING_KINDS",
    "EMPTY_CEILING", "NEVER_CEILING_IDS", "VOCABULARY",
    "ceiling_from_ids", "takes_consent_records",
]