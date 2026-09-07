# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The standing-request store (A-HB-2, A-HB-24, A-HB-25).

The engine's default store is one JSON document per subject. Halbert reaches
its stores from the dashboard, the MCP server (own ``main()``), the scheduler,
the detector runner and the home cognitive loop; ``FindingStore`` is
constructed independently in ten places and survives only because it is
SQLite. A read-modify-write JSON file under that access pattern loses updates,
and the update it loses is a withdrawal.

So Halbert supplies its own store. These tests pin the properties that
motivated it.
"""

import threading
from datetime import datetime, timedelta, timezone

import pytest

from halbert_core.attunement.store import AttunementStore


@pytest.fixture
def store(tmp_path):
    return AttunementStore(db_path=str(tmp_path / "attunement.db"))


def _iso(dt):
    return dt.astimezone(timezone.utc).isoformat()


def test_unknown_subject_reads_as_empty_not_as_an_error():
    """A first-ever turn must not raise."""
    s = AttunementStore(db_path=":memory:")
    record = s.load_subject_raw("halbert", "primary")
    assert record["requests"] == []
    assert record["state"] == {}


def test_subject_round_trips(store):
    record = {
        "requests": [{"id": "r1", "kind": "withdraw", "tone": "irritated"}],
        "state": {"invitation": 1, "accepted_interactions": 4},
    }
    store.save_subject_raw("halbert", "primary", record)
    assert store.load_subject_raw("halbert", "primary") == record


def test_subjects_are_isolated_by_persona_and_by_subject(store):
    store.save_subject_raw("halbert", "eric", {"requests": [{"id": "a"}], "state": {}})
    store.save_subject_raw("halbert", "guest", {"requests": [{"id": "b"}], "state": {}})
    store.save_subject_raw("other", "eric", {"requests": [{"id": "c"}], "state": {}})

    assert store.load_subject_raw("halbert", "eric")["requests"][0]["id"] == "a"
    assert store.load_subject_raw("halbert", "guest")["requests"][0]["id"] == "b"
    assert store.load_subject_raw("other", "eric")["requests"][0]["id"] == "c"


def test_outcomes_append_and_list_newest_first(store):
    for i in range(3):
        store.record_outcome_raw({
            "attempt_id": f"a{i}", "persona_id": "halbert", "subject_id": "primary",
            "source": "consumer_event", "severity": "warning", "channel_class": "push",
            "outcome": "hold", "reasons": ["standing:withdraw"], "margin": -0.2,
        })
    rows = store.list_outcomes_raw("halbert")
    assert [r["attempt_id"] for r in rows] == ["a2", "a1", "a0"]


def test_suppressed_attempts_are_recorded_with_their_reasons(store):
    """A-HB-25: every non-SPEAK decision is written, or 'why did I not hear
    about this' stays unanswerable."""
    store.record_outcome_raw({
        "attempt_id": "sup1", "persona_id": "halbert", "subject_id": "primary",
        "source": "finding", "severity": "warning", "channel_class": "push",
        "outcome": "silent", "reasons": ["dial:balanced:unanchored_info"],
        "margin": -0.4,
    })
    row = store.list_outcomes_raw("halbert")[0]
    assert row["outcome"] == "silent"
    assert row["reasons"] == ["dial:balanced:unanchored_info"]


def test_outcomes_filter_by_subject(store):
    store.record_outcome_raw({"attempt_id": "x", "persona_id": "halbert",
                              "subject_id": "eric", "outcome": "speak"})
    store.record_outcome_raw({"attempt_id": "y", "persona_id": "halbert",
                              "subject_id": "guest", "outcome": "speak"})
    rows = store.list_outcomes_raw("halbert", subject_id="guest")
    assert [r["attempt_id"] for r in rows] == ["y"]


def test_update_reaction_attaches_to_the_attempt(store):
    store.record_outcome_raw({"attempt_id": "a1", "persona_id": "halbert",
                              "subject_id": "primary", "outcome": "speak"})
    assert store.update_reaction("a1", "engaged") is True
    assert store.list_outcomes_raw("halbert")[0]["reaction"] == "engaged"


def test_update_reaction_reports_an_unknown_attempt(store):
    assert store.update_reaction("nope", "engaged") is False


def test_purge_removes_one_subject_and_its_outcomes_only(store):
    store.save_subject_raw("halbert", "eric", {"requests": [{"id": "a"}], "state": {}})
    store.save_subject_raw("halbert", "guest", {"requests": [{"id": "b"}], "state": {}})
    store.record_outcome_raw({"attempt_id": "e1", "persona_id": "halbert",
                              "subject_id": "eric", "outcome": "speak"})
    store.record_outcome_raw({"attempt_id": "g1", "persona_id": "halbert",
                              "subject_id": "guest", "outcome": "speak"})

    store.purge("halbert", "eric")

    assert store.load_subject_raw("halbert", "eric")["requests"] == []
    assert store.load_subject_raw("halbert", "guest")["requests"][0]["id"] == "b"
    assert [r["attempt_id"] for r in store.list_outcomes_raw("halbert")] == ["g1"]


def test_purge_all_clears_one_persona_and_leaves_the_others(store):
    store.save_subject_raw("halbert", "eric", {"requests": [{"id": "a"}], "state": {}})
    store.save_subject_raw("other", "eric", {"requests": [{"id": "c"}], "state": {}})
    store.record_outcome_raw({"attempt_id": "h", "persona_id": "halbert",
                              "subject_id": "eric", "outcome": "speak"})
    store.record_outcome_raw({"attempt_id": "o", "persona_id": "other",
                              "subject_id": "eric", "outcome": "speak"})

    store.purge_all("halbert")

    assert store.load_subject_raw("halbert", "eric")["requests"] == []
    assert store.list_outcomes_raw("halbert") == []
    assert store.load_subject_raw("other", "eric")["requests"][0]["id"] == "c"
    assert len(store.list_outcomes_raw("other")) == 1


def test_retention_trims_rows_past_the_horizon(store):
    old = _iso(datetime.now(timezone.utc) - timedelta(days=120))
    recent = _iso(datetime.now(timezone.utc) - timedelta(days=1))
    store.record_outcome_raw({"attempt_id": "old", "persona_id": "halbert",
                              "subject_id": "primary", "outcome": "speak", "ts": old})
    store.record_outcome_raw({"attempt_id": "new", "persona_id": "halbert",
                              "subject_id": "primary", "outcome": "speak", "ts": recent})

    removed = store.trim_outcomes(retention_days=90)

    assert removed == 1
    assert [r["attempt_id"] for r in store.list_outcomes_raw("halbert")] == ["new"]


def test_concurrent_writers_do_not_lose_outcomes(tmp_path):
    """The property the whole module exists for. Separate store instances mean
    separate connections, which is how the real entry points reach it."""
    db = str(tmp_path / "attunement.db")
    AttunementStore(db_path=db)  # create the schema once

    errors = []

    def write(worker):
        try:
            s = AttunementStore(db_path=db)
            for i in range(20):
                s.record_outcome_raw({
                    "attempt_id": f"w{worker}-{i}", "persona_id": "halbert",
                    "subject_id": "primary", "outcome": "hold",
                })
        except Exception as exc:  # pragma: no cover - surfaced by the assert
            errors.append(exc)

    threads = [threading.Thread(target=write, args=(w,)) for w in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert len(AttunementStore(db_path=db).list_outcomes_raw("halbert", limit=1000)) == 120


def test_concurrent_subject_writes_do_not_lose_the_last_writer(tmp_path):
    db = str(tmp_path / "attunement.db")
    AttunementStore(db_path=db)

    def write(worker):
        s = AttunementStore(db_path=db)
        s.save_subject_raw("halbert", f"s{worker}",
                           {"requests": [{"id": str(worker)}], "state": {}})

    threads = [threading.Thread(target=write, args=(w,)) for w in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    s = AttunementStore(db_path=db)
    for w in range(8):
        assert s.load_subject_raw("halbert", f"s{w}")["requests"][0]["id"] == str(w)


def test_default_path_sits_beside_the_findings_database(tmp_path, monkeypatch):
    monkeypatch.setenv("HALBERT_DATA_DIR", str(tmp_path))
    s = AttunementStore()
    assert s.db_path.endswith("attunement.db")
    assert str(tmp_path) in s.db_path
