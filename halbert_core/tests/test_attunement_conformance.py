# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The engine's policy vectors, run against our wiring (handoff §5).

`check_policy` returns findings rather than raising, because a disagreement
may be one a consumer carries deliberately. The point of running it here is
that we should *decide* a disagreement rather than discover it in
production as a suppression nobody can distinguish from an alert that was
never generated.

Worth running while the policy is in shadow and a disagreement costs
nothing. The suite deliberately carries utterances that must be delivered
as well as ones that must be held — a wiring that passes only the quiet
half is not cautious, it is deaf — so the second assertion below pins that
the run is not trivially green.
"""

import pytest

pytest.importorskip("haloysius.attunement.conformance")


def test_our_policy_agrees_with_the_shared_vectors():
    from haloysius.attunement.conformance import check_policy
    from haloysius.attunement.policy import decide

    failures = check_policy(decide)

    assert failures == [], "\n".join(failures)


def test_the_suite_is_not_only_the_quiet_half():
    """A policy that never speaks must not be able to pass this."""
    from haloysius.attunement.conformance import policy_vectors

    vectors = [
        v for v in policy_vectors()["vectors"] if v.get("class") == "policy"
    ]
    must_speak = [
        v for v in vectors
        if (v.get("expect") or {}).get("outcome") in {"speak", "speak_minimal"}
    ]

    # 25 vectors ship; 23 are the `policy` class `check_policy` runs, the
    # other two are `invariant`. Pinned as a floor so an engine upgrade that
    # quietly ships fewer is visible.
    assert len(vectors) >= 23
    assert must_speak, "every vector expects silence; the suite proves nothing"


def test_halberts_own_ceilings_do_not_break_the_vectors():
    """Our `AttunementConfig` overrides two attachment numbers. The vectors
    build their own contexts, so this asserts the overrides are a valid
    config rather than that they are used."""
    from halbert_core.attunement.context import halbert_config

    config = halbert_config()

    assert config is not None
    assert config.attachment.max_proactive_per_day > 0
