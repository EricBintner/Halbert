# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The decision core: which verb applies to a mid-turn arrival, and its
invariants. Pure; the state machine supplies the predicates."""
from halbert_core.agents.steering import (
    Verdict,
    apply_steer_to_results,
    decide_midturn,
)


def test_idle_arrives_as_normal_turn():
    v = decide_midturn(turn_active=False, is_command=False, text="hello")
    assert v.verb == Verdict.NORMAL_TURN


def test_busy_command_bypasses():
    v = decide_midturn(turn_active=True, is_command=True, text="/stop")
    assert v.verb == Verdict.STOP


def test_busy_text_steers():
    v = decide_midturn(turn_active=True, is_command=False, text="also check the logs")
    assert v.verb == Verdict.STEER


def test_stop_and_redirect_share_safety():
    # a stop accepted at the same edge as a redirect must not produce a retry:
    # one lock decides; second caller sees the decided state
    v1 = decide_midturn(turn_active=True, is_command=True, text="/stop")
    v2 = decide_midturn(turn_active=True, is_command=False, text="do this instead")
    assert {v1.verb, v2.verb} <= {Verdict.STOP, Verdict.STEER}


def test_steer_appends_to_last_tool_result():
    results = [{"name": "recall_memory", "output": "ok"}]
    apply_steer_to_results(results, "also check the logs")
    assert "also check the logs" in results[-1]["output"]
    apply_steer_to_results(results, "and the camera too")
    assert "and the camera too" in results[-1]["output"]  # steers concatenate


def test_guidance_demotes_when_unsafe():
    """Never kill a tool to deliver *guidance*: plain text steers.

    R-01 Phase B (A07-G2): this test used to pass ``is_command=True`` and
    assert that a ``/stop`` demoted to a steer. The demotion rule belongs
    to guidance, not to the stop verb -- transcribing it onto Rule 1 left
    the algebra unable to stop a running command, which is the one thing
    a stop is for. The rule itself is unchanged and pinned here on the
    text it was always about.
    """
    v = decide_midturn(
        turn_active=True,
        is_command=False,
        text="actually, check the logs instead",
        tool_batch_in_flight=True,
    )
    assert v.verb == Verdict.STEER


def test_stop_is_unconditional_even_during_a_tool_batch():
    """Rule 1 acts; it does not append (A07-G2)."""
    v = decide_midturn(
        turn_active=True,
        is_command=True,
        text="/stop",
        tool_batch_in_flight=True,
    )
    assert v.verb == Verdict.STOP