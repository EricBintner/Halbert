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


def test_rungs_are_served_with_copy_and_classifiability(client):
    body = client.get("/api/being/presence/rungs").json()
    assert body["status"] == "ok" and "owner" not in body
    levels = [r["level"] for r in body["rungs"]]
    assert levels == [0, 1, 3, 4, 6, 8, 10]
    by_level = {r["level"]: r for r in body["rungs"]}
    assert by_level[3]["says"].startswith("I") and by_level[3]["why"]
    assert by_level[3]["classifiable"] is True
    assert by_level[6]["classifiable"] is False   # nothing can yet be described as OPEN_LOOP or ABSENCE
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


def test_preview_cuts_items_but_not_counts(client, store):
    for i in range(3):
        _seed(store, "warning", i + 1)
    body = client.get("/api/being/presence/preview", params={"level": 3, "limit": 2}).json()
    assert body["said"] == 3 and len(body["items"]) == 2 and body["truncated"] is False


def test_preview_says_when_the_safety_cap_bound(client, store, monkeypatch):
    from halbert_core.dashboard.routes import being as being_mod
    monkeypatch.setattr(being_mod, "_PREVIEW_ROWS", 2)
    for i in range(3):
        _seed(store, "warning", i + 1)
    assert client.get("/api/being/presence/preview", params={"level": 3}).json()["truncated"] is True


@pytest.mark.parametrize("params", [{"level": 11}, {"level": -1}, {"level": 3, "days": 0}, {"level": 3, "limit": 0}])
def test_preview_validates_its_range(client, params):
    assert client.get("/api/being/presence/preview", params=params).status_code == 422


def test_a_row_the_recorder_writes_is_a_row_the_preview_reads(client, store):
    """The recorder→preview seam: a rename of a row key in either would
    otherwise pass both files' own tests and make every row unclassified."""
    from halbert_core.attunement.shadow import SuppressionRecorder
    from halbert_core.proactive.events import ProactiveEvent
    ev = ProactiveEvent.create(type="finding", severity="critical", title="t", body="b")
    SuppressionRecorder(store=store).record(ev, allowed=False)
    body = client.get("/api/being/presence/preview", params={"level": 0}).json()
    assert body["said"] == 1 and body["unclassified"] == 0


def test_the_preview_says_so_without_the_engine(client, monkeypatch):
    import builtins
    real_import = builtins.__import__

    def no_engine(name, *args, **kwargs):
        if name.startswith("haloysius"):
            raise ImportError("no engine here")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_engine)
    r = client.get("/api/being/presence/preview", params={"level": 3})
    assert r.status_code == 503 and "engine" in r.json()["detail"]


def test_a_config_the_loader_refuses_is_a_400(client, monkeypatch):
    from halbert_core.dashboard.routes import being as being_mod
    monkeypatch.setattr(being_mod, "load_being_config", None, raising=False)
    import halbert_core.config.being_config as bc
    monkeypatch.setattr(bc, "load_being_config", lambda *a, **k: (_ for _ in ()).throw(ValueError("presence must be an integer 0..10, got 11")))
    r = client.get("/api/being/presence/preview", params={"level": 3})
    assert r.status_code == 400 and "presence" in r.json()["detail"]
