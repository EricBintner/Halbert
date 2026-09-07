# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""A5: recurrence, counted over the event ledger.

This is the arithmetic CD-3 made the whole of selection: top N by (count,
severity, recency). It is deterministic and it is the reason the ledger
exists — "this van, three times, with timestamps" is a fact, where clustering
chat topics would have produced "docker" and "the thing we tried".

Counts `end` rows, not `new` (DECISIONS.md 2026-09-06). One `end` per tracked
object dedupes exactly as one `new` does, but Frigate assigns `sub_label` —
the plate or the face, the thing that makes it *that* van rather than *a*
van — only after an object is first tracked. Counting `new` grouped
everything as `front_door:person` and made the plan's own motivating example
unreachable.
"""

import pytest

from halbert_core.continuity.timeline import TimelineEvent, TimelineStore


@pytest.fixture
def store(tmp_path):
    return TimelineStore(db_path=str(tmp_path / "t.db"))


def _sighting(store, entity, at, *, sub_label_on_end=None, camera="driveway",
              label="car"):
    """One tracked object's full lifecycle: new, update, end."""
    for kind, offset in (("new", 0), ("update", 1), ("end", 2)):
        eid = entity
        if sub_label_on_end and kind in ("update", "end"):
            eid = f"{camera}:{sub_label_on_end}"
        store.record(TimelineEvent(
            timestamp=at + offset, event_type="frigate_event", source="frigate",
            entity_id=eid, title=f"{label} {kind}",
            data={"type": kind, "frigate_event_id": f"{entity}-{at}"},
        ))


class TestCountByEntity:

    def test_one_object_counts_once_despite_three_rows(self, store):
        _sighting(store, "driveway:car", 100)
        counts = store.count_by_entity(since=0)
        assert counts["driveway:car"][0] == 1, (
            "new + update + end is one object, not three"
        )

    def test_three_sightings_count_three(self, store):
        for day, at in enumerate((100, 200, 300)):
            _sighting(store, "driveway:car", at)
        counts = store.count_by_entity(since=0)
        assert counts["driveway:car"][0] == 3

    def test_it_reports_first_and_last(self, store):
        for at in (100, 200, 300):
            _sighting(store, "driveway:car", at)
        count, first, last = store.count_by_entity(since=0)["driveway:car"]
        assert (count, first, last) == (3, 102, 302)

    def test_the_window_is_respected(self, store):
        _sighting(store, "driveway:car", 100)
        _sighting(store, "driveway:car", 1000)
        assert store.count_by_entity(since=500)["driveway:car"][0] == 1

    def test_until_bounds_the_far_end(self, store):
        _sighting(store, "driveway:car", 100)
        _sighting(store, "driveway:car", 1000)
        assert store.count_by_entity(since=0, until=500)["driveway:car"][0] == 1

    def test_an_empty_window_is_empty_not_an_error(self, store):
        assert store.count_by_entity(since=9999) == {}


class TestTheGreyVan:
    """The motivating example, asserted."""

    def test_a_sub_label_arriving_on_update_groups_by_the_recognised_identity(
        self, store
    ):
        # Frigate sees "a car" first and resolves the plate afterwards. The
        # `end` row carries the resolved identity, which is what makes three
        # visits by the SAME van countable as three.
        for at in (100, 200, 300):
            _sighting(store, "driveway:car", at, sub_label_on_end="grey_van")
        counts = store.count_by_entity(since=0)
        assert counts.get("driveway:grey_van", (0,))[0] == 3
        assert "driveway:car" not in counts, (
            "counting `new` would have grouped these as an anonymous car"
        )

    def test_two_different_vans_do_not_merge(self, store):
        _sighting(store, "driveway:car", 100, sub_label_on_end="grey_van")
        _sighting(store, "driveway:car", 200, sub_label_on_end="white_van")
        counts = store.count_by_entity(since=0)
        assert counts["driveway:grey_van"][0] == 1
        assert counts["driveway:white_van"][0] == 1


class TestFiltering:

    def test_it_can_narrow_to_one_event_type(self, store):
        _sighting(store, "driveway:car", 100)
        store.record(TimelineEvent(timestamp=101, event_type="ha_state_change",
                                   source="ha", entity_id="lock.front_door"))
        counts = store.count_by_entity(since=0, event_type="frigate_event")
        assert set(counts) == {"driveway:car"}

    def test_non_frigate_rows_are_counted_per_row(self, store):
        # Only Frigate has the new/update/end lifecycle. An HA state change is
        # one row per occurrence, and counting only "end" would count none.
        for at in (100, 200):
            store.record(TimelineEvent(
                timestamp=at, event_type="occupancy_change", source="ha",
                entity_id="person.sarah", data={"direction": "arrival"}))
        assert store.count_by_entity(since=0)["person.sarah"][0] == 2

    def test_rows_with_no_entity_are_skipped(self, store):
        store.record(TimelineEvent(timestamp=100, event_type="system_event",
                                   source="sys", entity_id=""))
        assert store.count_by_entity(since=0) == {}
