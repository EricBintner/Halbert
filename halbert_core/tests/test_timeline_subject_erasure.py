# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Occupancy rows are a named person's movement history, and must be erasable.

`timeline_events` has no `request_id`, so `forget_request` cannot reach it the
way it reaches the change ledger -- which is why `ERASURE_LIMITS` currently
names the ledger as out of reach. That sentence is honest, and it is also a
statement that a person's arrivals and departures cannot be removed. This
closes it by subject instead of by request: the id of the entity the rows are
about is the thing a person can actually point at.

Deliberately narrow. It erases occupancy rows and the state rows for the same
entity, not the whole ledger: a disk-health event is machine-state history and
has no person in it.
"""

import time

import pytest

from halbert_core.continuity.timeline import TimelineEvent, TimelineStore


@pytest.fixture
def store(tmp_path):
    s = TimelineStore(db_path=str(tmp_path / "t.db"))
    for et, entity in [
        ("occupancy_change", "person.sarah"),
        ("occupancy_change", "person.sarah"),
        ("ha_state_change", "person.sarah"),
        ("occupancy_change", "person.alex"),
        ("frigate_event", "front_door:person"),
        ("system_event", "disk.sda"),
    ]:
        s.record(TimelineEvent(timestamp=time.time(), event_type=et,
                               source="test", entity_id=entity, title="x"))
    return s


class TestForgetSubject:

    def test_it_removes_that_persons_rows(self, store):
        removed = store.forget_subject("person.sarah")
        assert removed == 3
        assert store.query(entity_id="person.sarah", limit=99) == []

    def test_it_leaves_everyone_else_alone(self, store):
        store.forget_subject("person.sarah")
        assert len(store.query(entity_id="person.alex", limit=99)) == 1

    def test_it_leaves_machine_state_history_alone(self, store):
        store.forget_subject("person.sarah")
        assert len(store.query(entity_id="disk.sda", limit=99)) == 1
        assert len(store.query(entity_id="front_door:person", limit=99)) == 1

    def test_an_unknown_subject_removes_nothing_and_says_so(self, store):
        assert store.forget_subject("person.nobody") == 0

    def test_it_reports_what_it_did_rather_than_claiming_success(self, store):
        # The count is the report: a caller that says "forgotten" without one
        # is the failure mode ERASURE_LIMITS exists to prevent.
        assert isinstance(store.forget_subject("person.sarah"), int)


class TestTheErasureTextTracksTheCode:

    def test_the_limits_no_longer_say_no_erasure_reaches_the_ledger(self):
        from halbert_core.continuity.provenance import ERASURE_LIMITS

        assert "no erasure reaches" not in ERASURE_LIMITS.lower(), (
            "forget_subject reaches it now; a stale limit is a false claim in "
            "the other direction"
        )

    def test_the_limits_still_name_what_subject_erasure_does_not_cover(self):
        from halbert_core.continuity.provenance import ERASURE_LIMITS

        assert "timeline.db" in ERASURE_LIMITS
