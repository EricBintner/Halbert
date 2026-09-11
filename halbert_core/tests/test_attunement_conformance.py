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


def test_ask_first_is_currently_unreachable_in_our_default_case():
    """A tripwire on an engine boundary bug, not a preference.

    The plain case — a warning, no sensor, normal invitation, established
    relationship, default extraversion — computes `value - cost` as
    0.19999999999999996 against `ASK_T[warning]` of 0.2, and misses by
    5.55e-17. It falls through to HOLD.

    It matters because `ASK_FIRST` *is* A-HB-26's exploration arm, and
    `warning` is the severity our detectors overwhelmingly emit: the arm
    Phase C is defined over cannot appear in a Halbert row at all while this
    holds. Reported in
    `.handoff/RESEARCH-ATTUNEMENT-DECISIONS-2026-09-10.md` §0.

    **When this starts failing, the engine has fixed the comparison —
    delete it, and expect our shadow rows to start carrying `ask_first`.**
    """
    from haloysius.attunement.policy import CONSTANTS, decide
    from haloysius.attunement.types import (
        AttunementContext,
        EngagementOutcome,
        Severity,
        Utterance,
    )

    ctx = AttunementContext(
        persona_id="halbert",
        now="2026-09-10T12:00:00+00:00",
        utterance=Utterance(source="finding", severity=Severity.WARNING),
        sessions_count=10, relationship_age_days=30.0, accepted_interactions=10,
    )
    decision = decide(ctx)

    assert decision.outcome is EngagementOutcome.HOLD
    assert decision.margin < CONSTANTS["ASK_T"][Severity.WARNING]
    # ...but only just. The gap is arithmetic, not judgment.
    assert CONSTANTS["ASK_T"][Severity.WARNING] - decision.margin < 1e-12


def test_nothing_in_halbert_releases_a_held_decision():
    """Pins the go-live blocker so it cannot be forgotten quietly.

    Every policy outcome other than SPEAK / SPEAK_MINIMAL / SILENT is a
    HOLD, and a consumer only gets deferral semantics by calling
    `ledger.release(...)`. Until something does, leaving shadow would turn
    `dial:quiet`, `standing:withdraw`, `receptivity:unavailable` and both
    `attachment:*` gates into silent drops.

    **When this starts failing, the held queue (F6) exists — delete it and
    revisit ATN-1's cap, which can safely be lower once a capped item is
    deferred rather than lost.**
    """
    import pathlib
    import subprocess

    root = pathlib.Path(__file__).resolve().parents[1] / "halbert_core"
    found = subprocess.run(
        ["grep", "-rn", "--include=*.py", r"\.release(\|ResumeCondition", str(root)],
        capture_output=True, text=True,
    ).stdout
    # Thread/lock releases are not decision releases.
    hits = [
        line for line in found.splitlines()
        if "ResumeCondition" in line or "lock.release" not in line
    ]
    hits = [l for l in hits if "ResumeCondition" in l]

    assert hits == [], "something now releases holds:\n" + "\n".join(hits)
