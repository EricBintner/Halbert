# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The five-axis permission evaluator (D-3, packet D3-P1).

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

Every default denies. An unwired axis is a closed axis: nothing is
permitted until every axis is affirmatively wired — the deny-all posture
the wiring packets lift capability by capability.
"""
from __future__ import annotations

from .affordance import (
    EMPTY_AFFORDANCE,
    REGISTRY_BACKED_CAPABILITIES,
    AffordanceTable,
    affords,
)
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
from .consent import (
    ABSENT_DECISION,
    ConsentDecision,
    ConsentRecord,
    FIRST_PARTY_SURFACES,
    Principal,
    consent_state,
    is_affirmative_consent,
    is_valid_grant_record,
    latest_for,
    may_record_grant,
)
from .effective import (
    AXIS_AFFORDANCE,
    AXIS_CEILING,
    AXIS_CONSENT,
    AXIS_HALT,
    AXIS_OS_GRANT,
    AXIS_SCOPE,
    AxisObservation,
    EffectiveDecision,
    REASON_ALLOWED,
    REASON_HALTED,
    REASON_NO_AFFORDANCE,
    REASON_NO_CEILING,
    REASON_NOT_GRANTED,
    REASON_OS_DENIED,
    REASON_OS_UNKNOWN,
    REASON_OUT_OF_SCOPE,
    REASON_QUIET,
    axis_floor,
    effective_capability,
    effective_policy_with_axes,
)
from .halt import HaltReason, HaltState
from .os_grant import (
    DEFAULT_OS_GRANTS,
    OsGrantState,
    OsGrantTable,
    is_os_grant_affirmative,
)
from .channels import (
    CHANNELS,
    DistributionChannel,
    channel_for,
    ceiling_for,
    full_ceiling,
)
from .profiles import (
    ALWAYS_ON_IDS,
    PRESELECTED_PROFILE,
    PROFILE_NAMES,
    PROFILES,
    ProfileDefinition,
    ProfileProposal,
    ProfileRefused,
    VOICEPRINT_DEFAULT_TTL_DAYS,
    accept_profile,
    profile_proposals_for,
)

__all__ = [
    "ABSENT_DECISION",
    "ALWAYS_ON_IDS",
    "AffordanceTable",
    "AXIS_AFFORDANCE",
    "AXIS_CEILING",
    "AXIS_CONSENT",
    "AXIS_HALT",
    "AXIS_OS_GRANT",
    "AXIS_SCOPE",
    "AxisObservation",
    "CHANNELS",
    "CapabilityCeiling",
    "CapabilityKind",
    "CONSENTING_KINDS",
    "ConsentDecision",
    "ConsentRecord",
    "DEFAULT_OS_GRANTS",
    "DistributionChannel",
    "EMPTY_AFFORDANCE",
    "EMPTY_CEILING",
    "EffectiveDecision",
    "FIRST_PARTY_SURFACES",
    "HaltReason",
    "HaltState",
    "PRESELECTED_PROFILE",
    "PROFILE_NAMES",
    "PROFILES",
    "Principal",
    "ProfileDefinition",
    "ProfileProposal",
    "ProfileRefused",
    "REASON_ALLOWED",
    "REASON_HALTED",
    "REASON_NO_AFFORDANCE",
    "REASON_NO_CEILING",
    "REASON_NOT_GRANTED",
    "REASON_OS_DENIED",
    "REASON_OS_UNKNOWN",
    "REASON_OUT_OF_SCOPE",
    "REASON_QUIET",
    "REGISTRY_BACKED_CAPABILITIES",
    "VOICEPRINT_DEFAULT_TTL_DAYS",
    "accept_profile",
    "channel_for",
    "ceiling_for",
    "full_ceiling",
    "is_affirmative_consent",
    "is_os_grant_affirmative",
    "is_valid_grant_record",
    "latest_for",
    "may_record_grant",
    "NEVER_CEILING_IDS",
    "OsGrantState",
    "OsGrantTable",
    "Principal",
    "takes_consent_records",
    "VOCABULARY",
    "affords",
    "axis_floor",
    "ceiling_from_ids",
    "consent_state",
    "effective_capability",
    "effective_policy_with_axes",
    "profile_proposals_for",
]