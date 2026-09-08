# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Ceiling axis: the design's dotted vocabulary and fail-closed closed sets.

PERMISSION-AND-CONSENT-SYSTEM-2026-09-06.md §1.2/§1.3: the ceiling answers
"can this channel deliver it at all?", unknown channel = empty set = DENY,
and a shipped id is never renamed (a renamed capability is a silently
re-granted capability).
"""
from __future__ import annotations

import pytest

from halbert_core.persona.permission.ceiling import (
    CapabilityCeiling,
    CapabilityKind,
    CONSENTING_KINDS,
    EMPTY_CEILING,
    NEVER_CEILING_IDS,
    VOCABULARY,
    takes_consent_records,
)


def test_vocabulary_is_the_designs_dotted_set():
    """Every id the design's §1.3 declares, verbatim — the shipped namespace."""
    expected = {
        "sensor.screen", "sensor.screen.continuous", "sensor.window_titles",
        "sensor.camera", "sensor.camera.continuous", "sensor.camera.network",
        "sensor.mic.push_to_talk", "sensor.mic.continuous", "sensor.voiceprint",
        "sensor.photos", "sensor.journal", "sensor.hardware", "sensor.config_watch",
        "reach.fs.read", "reach.fs.write", "reach.config.read", "reach.config.write",
        "reach.terminal", "reach.privileged", "reach.service", "reach.package",
        "reach.network", "reach.home", "reach.display_power",
        "egress.cloud_model", "egress.web_search", "egress.web_fetch",
        "egress.peer", "egress.acoustid", "egress.telemetry",
        "auto.scheduler", "auto.observe", "auto.capture_on_intent",
        "auto.capture_on_error", "auto.speak", "auto.act",
        "surface.lan_api", "surface.mcp", "surface.wyoming", "surface.ha_component",
        "sys.local_llm", "sys.secure_model", "sys.sourceprep", "sys.discovery",
    }
    assert expected <= set(VOCABULARY)


def test_every_vocabulary_id_declares_a_known_kind_and_matches_its_prefix():
    kinds = {
        CapabilityKind.SENSOR, CapabilityKind.REACH, CapabilityKind.EGRESS,
        CapabilityKind.AUTO, CapabilityKind.SURFACE, CapabilityKind.SYS,
    }
    for cap_id, kind in VOCABULARY.items():
        assert kind in kinds, cap_id
        assert cap_id.startswith(kind + "."), cap_id


def test_unknown_id_is_not_permitted_even_by_a_ceiling_that_lists_similar():
    ceiling = CapabilityCeiling(frozenset({"sensor.screen", "reach.config.read"}))
    assert ceiling.permits("sensor.screen")
    assert not ceiling.permits("sensor.screen.hologram")   # unknown id
    assert not ceiling.permits("sensor.screenshot")        # plausible rename
    assert not ceiling.permits("")


def test_empty_ceiling_denies_everything():
    assert len(EMPTY_CEILING) == 0
    assert not EMPTY_CEILING.permits("sensor.journal")
    assert not EMPTY_CEILING.permits("sys.local_llm")


def test_ceiling_rejects_ids_outside_the_shipped_vocabulary():
    # a ceiling may not invent ids: construction fails loudly, never grants silently
    with pytest.raises(ValueError):
        CapabilityCeiling(frozenset({"sensor.screenshot"}))


def test_ceiling_rejects_declared_absent_ids():
    # egress.telemetry is declared absent so the privacy label is provable by test
    assert "egress.telemetry" in NEVER_CEILING_IDS
    with pytest.raises(ValueError):
        CapabilityCeiling(frozenset({"egress.telemetry"}))


def test_windows_shaped_empty_set_is_representable():
    # "the Windows ceiling is the empty set until W1–W13 are green"
    assert EMPTY_CEILING.permits("sensor.hardware") is False


def test_consent_record_kinds_per_design_1_3():
    assert takes_consent_records("sensor.screen")
    assert takes_consent_records("reach.terminal")
    assert takes_consent_records("egress.cloud_model")
    assert takes_consent_records("auto.scheduler")
    # sys.* is affordance-only, never consented
    assert not takes_consent_records("sys.local_llm")
    # surface.* is excluded from consent records per §1.3 (the packet series
    # records the tension with the §2.1 grant-table surface rows)
    assert not takes_consent_records("surface.mcp")
    # unknown ids never take consent records
    assert not takes_consent_records("not.a.capability")
    assert CONSENTING_KINDS == frozenset({
        CapabilityKind.SENSOR, CapabilityKind.REACH,
        CapabilityKind.EGRESS, CapabilityKind.AUTO,
    })