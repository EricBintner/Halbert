# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The preview: "at this level, here is what I would have said this week,
shown, and held" — admission and channel re-run over stored rows (spec
v2 §15, plan D7). Deterministic; no model, no live context."""

from datetime import datetime, timedelta, timezone

import pytest

engine = pytest.importorskip("haloysius.attunement.types")

from halbert_core.attunement.preview import preview_for_level  # noqa: E402
from halbert_core.config.being_config import BeingConfig  # noqa: E402

NOW = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)


def row(days_ago, impulse_class, channel="push", severity="warning", gate="silent", attempt="a"):
    return {
        "attempt_id": f"{attempt}-{days_ago}-{impulse_class}",
        "ts": (NOW - timedelta(days=days_ago)).isoformat(),
        "source": "finding", "severity": severity,
        "channel_class": channel, "impulse_class": impulse_class,
        "gate_outcome": gate,
    }


ROWS = [
    row(1, "critical"), row(2, "warning"), row(3, "recurrence"),
    row(4, "subject_linked"), row(5, "association"), row(6, "spontaneous"),
    row(9, "warning"),                          # outside a 7-day window
    {"attempt_id": "old", "ts": (NOW - timedelta(days=2)).isoformat(), "gate_outcome": "silent"},  # pre-slice row, no class
]


def test_level_zero_says_only_the_critical():
    p = preview_for_level(ROWS, 0, being_config=BeingConfig(), days=7, now=NOW)
    assert (p["said"], p["shown"], p["held"], p["unclassified"]) == (1, 0, 5, 1)
    assert p["level"] == 0 and p["days"] == 7


def test_level_three_adds_warning_and_recurrence():
    p = preview_for_level(ROWS, 3, being_config=BeingConfig(), days=7, now=NOW)
    assert (p["said"], p["shown"], p["held"]) == (3, 0, 3)


def test_level_four_shows_the_subject_linked_row_ambiently():
    p = preview_for_level(ROWS, 4, being_config=BeingConfig(), days=7, now=NOW)
    assert (p["said"], p["shown"], p["held"]) == (3, 1, 2)
    item = next(i for i in p["items"] if i["impulse_class"] == "subject_linked")
    assert item["verdict"] == "shown" and item["channel"] == "ambient"


def test_level_ten_still_shows_subject_linked_ambiently():
    """Not (6, 0, 0): Halbert's curve (attunement/curve.py) sets
    SUBJECT_LINKED to AMBIENT at rung 4 and never re-admits it at PUSH in a
    later rung, so it stays "shown" rather than "said" at every level from
    4 up to 10 — verified against the curve table, not a preview bug."""
    p = preview_for_level(ROWS, 10, being_config=BeingConfig(), days=7, now=NOW)
    assert (p["said"], p["shown"], p["held"]) == (5, 1, 0)


def test_items_carry_the_live_outcome_beside_the_preview_verdict():
    p = preview_for_level(ROWS, 3, being_config=BeingConfig(), days=7, now=NOW)
    assert all("live_outcome" in i and "verdict" in i for i in p["items"])
    assert len(p["items"]) == 6


def test_overrides_from_the_config_apply():
    cfg = BeingConfig(presence_overrides={"spontaneous": 10})
    p = preview_for_level(ROWS, 0, being_config=cfg, days=7, now=NOW)
    assert p["said"] == 2   # critical + the overridden spontaneous
