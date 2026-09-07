# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""ERASURE_LIMITS must describe what `forget_request` actually reaches.

It is user-facing text attached to the forget flow, and its whole purpose is
that "everywhere" is a lie when it is two planes of several. A limit that
overstates reach is the same defect pointed the other way: it was amended to
credit `TimelineStore.forget_subject`, which no forget path calls, so a
reader was told their movement history goes when it stays.
"""

import inspect

from halbert_core.continuity import provenance
from halbert_core.continuity.provenance import ERASURE_LIMITS


def test_the_text_does_not_credit_an_uncalled_method():
    credits_subject_erasure = "forget_subject" in ERASURE_LIMITS
    forget_calls_it = "forget_subject" in inspect.getsource(provenance.forget_request)
    assert forget_calls_it or not credits_subject_erasure, (
        "ERASURE_LIMITS credits forget_subject while forget_request never "
        "calls it: the text promises a reach the flow does not have"
    )


def test_it_still_names_the_event_ledger_as_out_of_reach():
    text = ERASURE_LIMITS.lower()
    assert "timeline.db" in text or "event ledger" in text


def test_it_says_erasing_a_subject_is_a_separate_operation():
    # The capability exists and is worth telling the reader about — as a
    # separate thing they can ask for, not as something forget already did.
    assert "separately" in ERASURE_LIMITS.lower()
