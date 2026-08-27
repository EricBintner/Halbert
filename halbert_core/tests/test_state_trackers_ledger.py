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
    """Halbert's own StateStore on a temp db (handoff R1)."""
    from halbert_core.continuity import StateStore

    led = StateStore(db_path=str(tmp_path / "state.db"))
    yield led
    led.close()


def _current(ledger):
    return {(t.subject, t.predicate): t.object for t in ledger.current_state()}


class TestDiskHealthTracker:
    def test_update_health_records_a_triple(self, ledger):
        t = DiskHealthTracker(ledger=ledger)
        t.update_health("/dev/sda1", "healthy")
        assert _current(ledger)[("disk:/dev/sda1", "disk_health")] == "healthy"

    def test_new_value_supersedes_the_old_one(self, ledger):
        t = DiskHealthTracker(ledger=ledger)
        t.update_health("/dev/sda1", "healthy")
        t.update_health("/dev/sda1", "failing")
        cur = ledger.current_state()
        assert len(cur) == 1
        assert cur[0].object == "failing"
        hist = ledger.state_history("disk:/dev/sda1", "disk_health")
        assert [h.object for h in hist] == ["healthy", "failing"]
        assert hist[0].valid_to is not None   # old value closed out
        assert hist[1].valid_to is None       # new value is live

    def test_source_carries_provenance(self, ledger):
        t = DiskHealthTracker(ledger=ledger)
        t.update_health("/dev/sda1", "healthy")
        assert ledger.current_state()[0].source == "state_tracker:disk_health"

    def test_no_ledger_is_a_silent_noop(self):
        t = DiskHealthTracker()          # ledger=None
        t.update_health("/dev/sda1", "healthy")   # must not raise

    def test_a_broken_ledger_never_propagates(self, caplog):
        class Boom:
            def record_state(self, *a, **k):
                raise RuntimeError("db gone")

        t = DiskHealthTracker(ledger=Boom())
        t.update_health("/dev/sda1", "healthy")   # must not raise
        assert "disk" in caplog.text.lower()


class TestServiceStatusTracker:
    def test_records_and_supersedes(self, ledger):
        t = ServiceStatusTracker(ledger=ledger)
        t.update_status("nginx", "running")
        t.update_status("nginx", "stopped")
        cur = ledger.current_state()
        assert len(cur) == 1 and cur[0].object == "stopped"
        assert cur[0].subject == "service:nginx"
        assert cur[0].source == "state_tracker:service_status"

    def test_two_services_are_independent(self, ledger):
        t = ServiceStatusTracker(ledger=ledger)
        t.update_status("nginx", "running")
        t.update_status("smbd", "stopped")
        assert _current(ledger) == {
            ("service:nginx", "service_status"): "running",
            ("service:smbd", "service_status"): "stopped",
        }


class TestSystemResourceTracker:
    def test_records_three_predicates(self, ledger):
        t = SystemResourceTracker(ledger=ledger)
        t.update_resources(cpu=42.4, mem=61.6, load=1.234)
        assert _current(ledger) == {
            ("system", "cpu_load"): "42%",
            ("system", "memory_usage"): "62%",
            ("system", "load_average"): "1.23",
        }

    def test_resample_supersedes_each_predicate(self, ledger):
        t = SystemResourceTracker(ledger=ledger)
        t.update_resources(cpu=10.0, mem=20.0, load=0.5)
        t.update_resources(cpu=90.0, mem=80.0, load=4.0)
        assert len(ledger.current_state()) == 3
        assert _current(ledger)[("system", "cpu_load")] == "90%"


class TestAdminPresenceTracker:
    def test_set_and_clear(self, ledger):
        t = AdminPresenceTracker(ledger=ledger)
        t.set_admin("eric")
        assert _current(ledger)[("user", "admin_presence")] == "present"
        t.clear_admin()
        assert _current(ledger)[("user", "admin_presence")] == "absent"
        assert len(ledger.current_state()) == 1

    def test_update_from_turn_marks_present(self, ledger):
        t = AdminPresenceTracker(ledger=ledger)
        t.update_from_turn(persona_id="halbert", user_message="check nginx", ai_response="")
        assert _current(ledger)[("user", "admin_presence")] == "present"


class TestRegistration:
    def test_default_ledger_path_is_halbert_owned(self):
        from halbert_core.integrations.state_trackers import default_ledger_path

        p = str(default_ledger_path())
        assert "halbert" in p and p.endswith("state_ledger.db")
        assert "haloysius" not in p   # Halbert-owned per founder direction D1

    def test_register_wires_a_live_ledger(self, tmp_path, monkeypatch):
        import halbert_core.integrations.state_trackers as st

        monkeypatch.setattr(st, "default_ledger_path", lambda: tmp_path / "l.db")
        trackers = st.register_halbert_state_trackers()
        assert set(trackers) == {
            "disk_health", "service_status", "system_resources", "admin_presence"}
        for t in trackers.values():
            assert t._ledger is not None

        trackers["service_status"].update_status("nginx", "running")
        cur = trackers["service_status"]._ledger.current_state()
        assert [(t.subject, t.object) for t in cur] == [("service:nginx", "running")]

    def test_explicit_ledger_wins(self, ledger):
        import halbert_core.integrations.state_trackers as st

        trackers = st.register_halbert_state_trackers(ledger=ledger)
        assert all(t._ledger is ledger for t in trackers.values())
