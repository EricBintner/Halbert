# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Halbert state trackers write to the Haloysius TemporalStateLedger (audit F2)."""

import pytest

from halbert_core.integrations.state_trackers import (
    AdminPresenceTracker,
    DiskHealthTracker,
    ServiceStatusTracker,
    SystemResourceTracker,
)


@pytest.fixture
def ledger(tmp_path):
    """A real TemporalStateLedger on a temp db — never the shared default."""
    from haloysius.memory_v2 import get_state_ledger

    led = get_state_ledger(str(tmp_path / "ledger.db"))
    yield led
    led.close()


def _current(ledger, persona_id="halbert"):
    return {(t.subject, t.predicate): t.object for t in ledger.get_current(persona_id)}


class TestDiskHealthTracker:
    def test_update_health_records_a_triple(self, ledger):
        t = DiskHealthTracker(ledger=ledger)
        t.update_health("/dev/sda1", "healthy")
        assert _current(ledger)[("disk:/dev/sda1", "disk_health")] == "healthy"

    def test_new_value_supersedes_the_old_one(self, ledger):
        t = DiskHealthTracker(ledger=ledger)
        t.update_health("/dev/sda1", "healthy")
        t.update_health("/dev/sda1", "failing")
        cur = ledger.get_current("halbert")
        assert len(cur) == 1
        assert cur[0].object == "failing"
        hist = ledger.get_history("halbert", "disk:/dev/sda1", "disk_health")
        assert [h.object for h in hist] == ["healthy", "failing"]
        assert hist[0].valid_to is not None   # old value closed out
        assert hist[1].valid_to is None       # new value is live

    def test_source_carries_provenance(self, ledger):
        t = DiskHealthTracker(ledger=ledger)
        t.update_health("/dev/sda1", "healthy")
        assert ledger.get_current("halbert")[0].source == "state_tracker:disk_health"

    def test_no_ledger_is_a_silent_noop(self):
        t = DiskHealthTracker()          # ledger=None
        t.update_health("/dev/sda1", "healthy")   # must not raise

    def test_a_broken_ledger_never_propagates(self, caplog):
        class Boom:
            def record(self, *a, **k):
                raise RuntimeError("db gone")

        t = DiskHealthTracker(ledger=Boom())
        t.update_health("/dev/sda1", "healthy")   # must not raise
        assert "disk" in caplog.text.lower()
