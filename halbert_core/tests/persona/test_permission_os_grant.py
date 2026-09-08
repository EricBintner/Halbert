# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""OS-grant axis: the four states, because three would force a lie.

PERMISSION-AND-CONSENT-SYSTEM-2026-09-06.md §1.2: "Has the operating system
agreed?" — GRANTED / DENIED / UNDETERMINED / UNQUERYABLE. UNQUERYABLE is the
honest state for Full Disk Access (no API exists) and for every macOS sensor
row until the signing chain lands ("can't tell — this build isn't signed").
The audit found zero hits for any authorization-status API in the tree, so
the default table is empty: nothing reads GRANTED until a preflight is wired
(deliberately — D3-P5's wiring decides, and absence of a query is never a
grant).
"""
from __future__ import annotations

import pytest

from halbert_core.persona.permission.os_grant import (
    DEFAULT_OS_GRANTS,
    OsGrantState,
    OsGrantTable,
    is_os_grant_affirmative,
)


def test_four_states_exist_and_are_distinct():
    states = {
        OsGrantState.GRANTED, OsGrantState.DENIED,
        OsGrantState.UNDETERMINED, OsGrantState.UNQUERYABLE,
    }
    assert len(states) == 4
    assert len({s.value for s in states}) == 4


def test_only_granted_is_affirmative():
    for state in (
        OsGrantState.DENIED,
        OsGrantState.UNDETERMINED,
        OsGrantState.UNQUERYABLE,
    ):
        assert is_os_grant_affirmative(state) is False
    assert is_os_grant_affirmative(OsGrantState.GRANTED) is True


def test_default_table_is_empty_so_nothing_is_os_granted():
    # no preflight is wired anywhere in the tree; absence of a query is
    # never a grant — everything reads UNDETERMINED, sensors included
    assert DEFAULT_OS_GRANTS.state_for("sensor.camera") is OsGrantState.UNDETERMINED
    assert DEFAULT_OS_GRANTS.state_for("reach.terminal") is OsGrantState.UNDETERMINED
    assert DEFAULT_OS_GRANTS.state_for("not.a.capability") is OsGrantState.UNDETERMINED


def test_table_states_are_read_as_written():
    table = OsGrantTable({
        "sensor.camera": OsGrantState.GRANTED,
        "sensor.mic.continuous": OsGrantState.DENIED,       # a detected revocation
        "sensor.screen": OsGrantState.UNQUERYABLE,          # unsigned build
        "reach.privileged": OsGrantState.UNDETERMINED,      # preflight failed once
    })
    assert table.state_for("sensor.camera") is OsGrantState.GRANTED
    assert table.state_for("sensor.mic.continuous") is OsGrantState.DENIED
    assert table.state_for("sensor.screen") is OsGrantState.UNQUERYABLE
    assert table.state_for("reach.privileged") is OsGrantState.UNDETERMINED


def test_table_rejects_ids_outside_the_vocabulary():
    with pytest.raises(ValueError):
        OsGrantTable({"sensor.screenshot": OsGrantState.GRANTED})


def test_table_rejects_invalid_states():
    with pytest.raises(ValueError):
        OsGrantTable({"sensor.camera": "probably fine"})
    with pytest.raises(ValueError):
        OsGrantTable({"sensor.camera": None})


def test_unqueryable_and_undetermined_are_both_non_grants():
    # the two "can't tell" states must never be read as yes — the UI says
    # "can't tell", the gate says no
    for state in (OsGrantState.UNQUERYABLE, OsGrantState.UNDETERMINED):
        table = OsGrantTable({"sensor.screen": state})
        assert is_os_grant_affirmative(table.state_for("sensor.screen")) is False


def test_probe_registry_is_never_consulted_for_os_grants():
    # a probe is not a grant (§1.1): the os_grant module must not even import
    # the registry's probe names
    import halbert_core.persona.permission.os_grant as os_grant_mod

    assert not hasattr(os_grant_mod, "REGISTRY_BACKED_CAPABILITIES")
    assert not any(
        name.startswith("CAP_")
        for name in dir(os_grant_mod)
    )