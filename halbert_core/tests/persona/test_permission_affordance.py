# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Affordance axis: presence, registry-backed for sys.*, deny when missing.

PERMISSION-AND-CONSENT-SYSTEM-2026-09-06.md §1.2: "Is the hardware/software
present?" — unknown is not available; the UI renders "unavailable on this
machine", never "off". A probe is presence, never a grant (§1.1).
"""
from __future__ import annotations

import pytest

from halbert_core.persona.permission.affordance import (
    EMPTY_AFFORDANCE,
    REGISTRY_BACKED_CAPABILITIES,
    AffordanceTable,
    affords,
)


class _FakeRegistry:
    """Stands in for capabilities.CapabilityRegistry — never probe the host."""

    def __init__(self, present: set[str]):
        self._present = set(present)
        self.asked: list[str] = []

    def has(self, name: str) -> bool:
        self.asked.append(name)
        return name in self._present


def test_registry_backed_ids_are_exactly_the_sys_kind():
    for cap_id in REGISTRY_BACKED_CAPABILITIES:
        assert cap_id.startswith("sys.")
    assert set(REGISTRY_BACKED_CAPABILITIES) == {
        "sys.local_llm", "sys.secure_model", "sys.sourceprep", "sys.discovery",
    }


def test_registry_probe_is_delegated_not_duplicated():
    reg = _FakeRegistry({"local_llm"})
    assert affords("sys.local_llm", EMPTY_AFFORDANCE, registry=reg) is True
    assert affords("sys.sourceprep", EMPTY_AFFORDANCE, registry=reg) is False
    assert reg.asked == ["local_llm", "sourceprep"]


def test_unknown_id_is_never_available():
    assert affords("sensor.screenshot", EMPTY_AFFORDANCE) is False
    assert affords("", EMPTY_AFFORDANCE) is False


def test_missing_affordance_denies():
    # in-vocabulary id with no presence evidence anywhere → deny
    assert affords("sensor.camera", EMPTY_AFFORDANCE, registry=_FakeRegistry(set())) is False


def test_explicit_table_beats_the_registry():
    table = AffordanceTable(present=frozenset({"sys.local_llm"}), absent=frozenset({"sys.discovery"}))
    reg = _FakeRegistry(set())  # registry disagrees with both
    assert affords("sys.local_llm", table, registry=reg) is True
    assert affords("sys.discovery", table, registry=reg) is False
    assert reg.asked == []  # the registry was never consulted


def test_table_entries_outside_vocabulary_raise():
    with pytest.raises(ValueError):
        AffordanceTable(present=frozenset({"sensor.screenshot"}))
    with pytest.raises(ValueError):
        AffordanceTable(absent=frozenset({"sensor.hologram"}))


def test_table_present_and_absent_must_be_disjoint():
    with pytest.raises(ValueError):
        AffordanceTable(
            present=frozenset({"sensor.camera"}),
            absent=frozenset({"sensor.camera"}),
        )


def test_hardware_ids_come_from_the_table_not_the_registry():
    # cameras and displays are not registry-probed; presence wiring is D3-P5's
    table = AffordanceTable(present=frozenset({"sensor.camera", "sensor.mic.push_to_talk"}))
    reg = _FakeRegistry({"camera"})  # a trap: a registry hit must not leak in
    assert affords("sensor.camera", table, registry=reg) is True
    assert affords("sensor.mic.continuous", table, registry=reg) is False
    assert reg.asked == []


def test_empty_table_denies_everything_not_registry_backed():
    reg = _FakeRegistry({"local_llm"})
    assert affords("reach.terminal", EMPTY_AFFORDANCE, registry=reg) is False
    assert reg.asked == []