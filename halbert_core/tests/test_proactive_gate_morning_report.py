# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The morning report reaches the user at Balanced (HB-N2, ATTN-2 / C2-10).

`morning_report.py` derives the report's severity from the open findings, so a
clean day yields ``info``; ``_PROACTIVITY_THRESHOLD["balanced"] == 1`` then
suppresses it. Three documents disagree with that code:

* ``the-being.md`` §4 — Balanced is "Important findings **and a scheduled
  morning report**".
* ``ROADMAP.md`` ATTN-2 — "morning report on by default at Balanced".
* The engine's §6.1, which models the report as ``user_requested=True``.

A daily brief the user configured is not an unsolicited info notice. It is
something they asked for, and the day being quiet is the report's *content*,
not a reason to withhold it.
"""

import pytest

from halbert_core.config.being_config import BeingConfig
from halbert_core.proactive.events import ProactiveEvent
from halbert_core.proactive.gate import ProactiveGate


def _config(proactivity):
    cfg = BeingConfig()
    cfg.proactivity = proactivity
    cfg.quiet_hours = None
    return cfg


def _report(severity="info"):
    return ProactiveEvent.create(
        type="morning_report", severity=severity, title="Good morning",
        body="Nothing needs you today.", category="reports",
    )


def _finding(severity="info"):
    return ProactiveEvent.create(type="finding", severity=severity,
                                 title="t", body="b")


def test_a_clean_day_report_reaches_the_user_at_balanced():
    allowed, reason = ProactiveGate(_config("balanced")).should_notify(_report())
    assert allowed is True, reason


def test_a_clean_day_report_reaches_the_user_at_assertive():
    assert ProactiveGate(_config("assertive")).should_notify(_report())[0] is True


def test_the_report_is_still_silent_at_quiet():
    """`the-being.md` §4: Quiet is critical findings only."""
    allowed, reason = ProactiveGate(_config("quiet")).should_notify(_report())
    assert allowed is False
    assert "dial" in reason or "proactivity" in reason


def test_the_report_is_still_silent_at_off():
    assert ProactiveGate(_config("off")).should_notify(_report())[0] is False


def test_an_ordinary_info_finding_is_still_suppressed_at_balanced():
    """The exemption is for the thing the user configured, not for info in
    general — otherwise Balanced silently becomes Assertive."""
    assert ProactiveGate(_config("balanced")).should_notify(_finding("info"))[0] is False


def test_a_category_override_can_still_quiet_the_report():
    """An explicit per-category decision outranks the default exemption."""
    cfg = _config("balanced")
    cfg.category_overrides = {"reports": "quiet"}
    assert ProactiveGate(cfg).should_notify(_report())[0] is False


def test_a_warning_report_is_unaffected():
    assert ProactiveGate(_config("balanced")).should_notify(_report("warning"))[0] is True
