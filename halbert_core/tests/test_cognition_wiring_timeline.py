# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""A0: get_timeline_store() and its injection into the HA, Frigate and
system event mappers (DEFECT-3 — the ledger existed and nothing built it).
"""

from __future__ import annotations

import pytest

from halbert_core.continuity.timeline import TimelineStore
from halbert_core.integrations import cognition_wiring


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    """Every cognition_wiring singleton starts unset, and env vars are unset
    unless a test opts in — HALBERT_DATA_DIR in particular must not leak
    between tests since get_timeline_store() reads it at construction."""
    for name in (
        "_timeline_store",
        "_ha_event_mapper",
        "_frigate_event_mapper",
        "_event_mapper",
        "_trackers",
    ):
        monkeypatch.setattr(cognition_wiring, name, None)
    monkeypatch.delenv("HALBERT_DATA_DIR", raising=False)
    monkeypatch.delenv("Halbert_DATA_DIR", raising=False)
    yield


def test_get_timeline_store_is_a_singleton():
    store = cognition_wiring.get_timeline_store()
    assert isinstance(store, TimelineStore)
    assert cognition_wiring.get_timeline_store() is store


def test_get_timeline_store_honours_halbert_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("HALBERT_DATA_DIR", str(tmp_path))
    store = cognition_wiring.get_timeline_store()
    assert store.db_path == str(tmp_path / "timeline.db")
    assert store.stats()["total_events"] == 0


def test_get_ha_event_mapper_injects_timeline_store():
    mapper = cognition_wiring.get_ha_event_mapper()
    assert mapper._timeline is cognition_wiring.get_timeline_store()


def test_get_frigate_event_mapper_injects_timeline_store(monkeypatch):
    import halbert_core.integrations.frigate.frigate_config as frigate_config

    cfg = frigate_config.FrigateConfig(mqtt_enabled=True, mqtt_host="mqtt.local")
    monkeypatch.setattr(frigate_config, "load_frigate_config", lambda: cfg)

    mapper = cognition_wiring.get_frigate_event_mapper()
    assert mapper is not None
    assert mapper._timeline is cognition_wiring.get_timeline_store()


def test_get_frigate_event_mapper_mqtt_only_is_no_longer_none(monkeypatch):
    """A0-code: an MQTT-only install (no REST url) used to make
    get_frigate_event_mapper() return None, forcing dashboard/app.py to
    construct its own uninjected FrigateEventMapper()."""
    import halbert_core.integrations.frigate.frigate_config as frigate_config

    cfg = frigate_config.FrigateConfig(url="", mqtt_enabled=True, mqtt_host="mqtt.local")
    assert not cfg.is_configured()
    assert cfg.is_mqtt_configured()
    monkeypatch.setattr(frigate_config, "load_frigate_config", lambda: cfg)

    assert cognition_wiring.get_frigate_event_mapper() is not None


def test_get_frigate_event_mapper_unconfigured_is_none(monkeypatch):
    import halbert_core.integrations.frigate.frigate_config as frigate_config

    cfg = frigate_config.FrigateConfig()
    monkeypatch.setattr(frigate_config, "load_frigate_config", lambda: cfg)

    assert cognition_wiring.get_frigate_event_mapper() is None


def test_get_event_mapper_injects_timeline_store_into_primary(monkeypatch):
    # Composite wraps the primary SystemEventMapper only when a secondary
    # (HA/Frigate) mapper is available; unconfigure Frigate and stub out
    # HA so the primary is returned directly and its ._timeline is
    # inspectable. register_halbert_state_trackers() touches a real
    # Haloysius continuity ledger — not needed for this assertion, and
    # get_event_mapper() already treats its failure as non-fatal.
    import halbert_core.integrations.frigate.frigate_config as frigate_config
    import halbert_core.integrations.state_trackers as state_trackers

    monkeypatch.setattr(
        frigate_config, "load_frigate_config", lambda: frigate_config.FrigateConfig()
    )
    monkeypatch.setattr(cognition_wiring, "get_ha_event_mapper", lambda: None)

    def _boom():
        raise RuntimeError("no real ledger in this test")

    monkeypatch.setattr(state_trackers, "register_halbert_state_trackers", _boom)

    mapper = cognition_wiring.get_event_mapper()
    assert mapper._timeline is cognition_wiring.get_timeline_store()


def test_shutdown_clears_timeline_store_singleton():
    store = cognition_wiring.get_timeline_store()
    cognition_wiring.shutdown()
    assert cognition_wiring._timeline_store is None
    assert cognition_wiring.get_timeline_store() is not store
