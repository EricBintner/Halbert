# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The two read-only presence endpoints: the rungs (copy as data, plan D8)
and the preview over the shadow log."""

from datetime import datetime, timedelta, timezone

import pytest

engine = pytest.importorskip("haloysius.attunement.types")

from halbert_core.attunement.store import AttunementStore  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    # The preview route loads being.yml through get_config_dir(); point it at
    # an empty temp dir so the test reads defaults, never the developer's file.
    monkeypatch.setenv("HALBERT_CONFIG_DIR", str(tmp_path))
    from fastapi.testclient import TestClient
    from halbert_core.dashboard.app import create_app
    return TestClient(create_app())


@pytest.fixture
def store(tmp_path, monkeypatch):
    s = AttunementStore(db_path=str(tmp_path / "attunement.db"))
    from halbert_core.dashboard.routes import being as being_mod
    monkeypatch.setattr(being_mod, "_attunement_store", lambda: s)
    return s


def _seed(store, impulse_class, days_ago):
    store.record_outcome_raw({
        "attempt_id": f"{impulse_class}-{days_ago}", "persona_id": "halbert", "subject_id": "primary",
        "outcome": "silent", "ts": (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat(),
        "source": "finding", "severity": "warning", "channel_class": "push",
        "impulse_class": impulse_class, "gate_outcome": "silent",
    })


def test_rungs_are_served_with_copy_and_reachability(client):
    body = client.get("/api/being/presence/rungs").json()
    assert body["status"] == "ok" and body["owner"] == "halbert"
    levels = [r["level"] for r in body["rungs"]]
    assert levels == [0, 1, 3, 4, 6, 8, 10]
    by_level = {r["level"]: r for r in body["rungs"]}
    assert by_level[3]["says"].startswith("I") and by_level[3]["why"]
    assert by_level[3]["reachable"] is True
    assert by_level[6]["reachable"] is False     # OPEN_LOOP has no producer yet
    assert "subject_linked" in by_level[4]["channel"] and by_level[4]["channel"]["subject_linked"] == "ambient"


def test_preview_counts_the_last_week_at_the_hovered_level(client, store):
    _seed(store, "critical", 1)
    _seed(store, "warning", 2)
    _seed(store, "association", 3)
    _seed(store, "warning", 20)
    body = client.get("/api/being/presence/preview", params={"level": 0, "days": 7}).json()
    assert (body["said"], body["held"]) == (1, 2)
    body = client.get("/api/being/presence/preview", params={"level": 8, "days": 7}).json()
    assert body["said"] == 3


def test_preview_validates_its_range(client):
    assert client.get("/api/being/presence/preview", params={"level": 11}).status_code == 422
