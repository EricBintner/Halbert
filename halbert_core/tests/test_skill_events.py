# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""SK-2: the skill_events table and its two seams (design §6).

Usage telemetry ships with the surface it measures, from day one, because
retrofitting is impossible (OpenClaw §7): every `read_file` of a known
skill path is a consultation receipt (seam 1, the executor's one choke
point), and matcher/explicit activations — today only a debug log line —
are promoted to the same table (seam 2, the state machine). Rows are
keyed by the stable skill id, never the name (the two-sources-of-truth
trap; name is mutable display data and lives in detail_json only).
"""

from __future__ import annotations

import json

import pytest

from halbert_core.agents.conversation_sqlite import SqliteConversationStore
from halbert_core.skills.parser import parse_skill
from halbert_core.skills.registry import SkillRegistry
from halbert_core.skills.telemetry import (
    EVENTS,
    record_skill_event,
    record_skill_read,
    set_active_registry,
    active_registry,
)


@pytest.fixture
def store():
    s = SqliteConversationStore(":memory:")
    yield s
    s.close()


@pytest.fixture
def no_daemon_store(monkeypatch, store):
    """Point telemetry at a throwaway store, never the process manager.

    Production reads `get_thread_manager().store`; the monkeypatch keeps
    these tests from creating (or writing into) the real conversations
    database.
    """
    import halbert_core.skills.telemetry as telemetry

    monkeypatch.setattr(telemetry, "_store", lambda: store)
    return store


def _skill(name, source):
    meta = f"name: {name}\ndescription: d\nhalbert:\n  kind: ops\n"
    return parse_skill(f"---\n{meta}---\nBody.", source_path=source)


@pytest.fixture
def skill_on_disk(tmp_path):
    d = tmp_path / "zfs-rollback"
    d.mkdir()
    src = d / "SKILL.md"
    src.write_text("body")
    refs = d / "references"
    refs.mkdir()
    (refs / "deep.md").write_text("reference")
    reg = SkillRegistry([_skill("zfs-rollback", src)])
    set_active_registry(reg)
    yield reg
    set_active_registry(None)


# ── The table ───────────────────────────────────────────────────────

class TestTheTable:

    def test_the_schema_creates_on_a_fresh_store(self, store):
        cols = {r[1] for r in store._conn.execute(
            "PRAGMA table_info(skill_events)")}
        assert cols >= {"ts", "run_id", "session_id", "skill_id",
                        "persona", "event", "detail_json"}

    def test_the_schema_reconciles_onto_an_old_database(self, tmp_path):
        """A database created before this table existed gains it in place."""
        db = str(tmp_path / "old.db")
        first = SqliteConversationStore(db)
        first._conn.execute("DROP TABLE skill_events")
        first._conn.commit()
        first.close()
        second = SqliteConversationStore(db)
        try:
            cols = {r[1] for r in second._conn.execute(
                "PRAGMA table_info(skill_events)")}
            assert "skill_id" in cols
        finally:
            second.close()

    def test_a_row_round_trips(self, store):
        row_id = store.append_skill_event(
            skill_id="sk_01JZQ0A1B2C3D4E5F6G7H8J9K0", event="read",
            run_id="run-1", session_id="sess-1", persona=None,
            detail={"name": "zfs-rollback"},
        )
        assert row_id is not None
        rows = store.list_skill_events()
        assert len(rows) == 1
        row = rows[0]
        assert row["skill_id"] == "sk_01JZQ0A1B2C3D4E5F6G7H8J9K0"
        assert row["event"] == "read"
        assert row["run_id"] == "run-1"
        assert row["session_id"] == "sess-1"
        assert json.loads(row["detail_json"])["name"] == "zfs-rollback"
        assert row["ts"] > 0

    def test_listing_filters_by_skill_and_recency(self, store):
        sid = "sk_01JZQ0A1B2C3D4E5F6G7H8J9K0"
        store.append_skill_event(skill_id=sid, event="matched")
        store.append_skill_event(skill_id=sid, event="read")
        store.append_skill_event(skill_id="sk_other", event="read")
        mine = store.list_skill_events(skill_id=sid)
        assert [r["event"] for r in mine] == ["read", "matched"]
        assert store.list_skill_events(limit=1)[0]["event"] == "read"

    def test_a_failed_write_returns_none_never_raises(self, store):
        store._conn = None
        assert store.append_skill_event(
            skill_id="sk_x", event="read") is None


class TestTheEventEnum:
    """The design's row names the whole lifecycle; SK-2 emits read,
    matched and explicit — the seams this packet ships. linted,
    verification_run, promoted, archived and absorbed are the later
    packets' to write, and catalog_listed stays unemitted until a
    consumer asks for it (per-skill-per-turn spam with no reader)."""

    def test_the_enum_is_the_designs_own(self):
        assert set(EVENTS) == {
            "catalog_listed", "matched", "explicit", "read", "linted",
            "verification_run", "promoted", "archived", "absorbed",
        }


# ── The telemetry module ─────────────────────────────────────────────

class TestRecordSkillEvent:

    def test_it_writes_through_to_the_store(self, no_daemon_store):
        assert record_skill_event(
            "sk_01JZQ0A1B2C3D4E5F6G7H8J9K0", "matched",
            session_id="s1", run_id="r1",
            detail={"name": "storage-ops", "score": 9},
        )
        rows = no_daemon_store.list_skill_events()
        assert rows[0]["event"] == "matched"
        assert rows[0]["session_id"] == "s1"

    def test_without_a_store_it_is_a_logged_no_op(self, monkeypatch):
        import halbert_core.skills.telemetry as telemetry
        monkeypatch.setattr(telemetry, "_store", lambda: None)
        assert not record_skill_event("sk_x", "read")

    def test_a_broken_store_never_raises(self, monkeypatch):
        import halbert_core.skills.telemetry as telemetry

        def boom():
            raise RuntimeError("store exploded")
        monkeypatch.setattr(telemetry, "_store", boom)
        assert not record_skill_event("sk_x", "read")


class TestSeamOneReads:

    async def test_reading_a_skill_md_is_a_receipt(self, no_daemon_store,
                                                    skill_on_disk):
        skill = skill_on_disk.get("zfs-rollback")
        path = str(skill.source_path)
        assert record_skill_read(path) == skill.id
        rows = no_daemon_store.list_skill_events()
        assert len(rows) == 1
        assert rows[0]["event"] == "read"
        assert rows[0]["skill_id"] == skill.id

    async def test_reading_a_reference_file_is_the_same_receipt(
            self, no_daemon_store, skill_on_disk):
        skill = skill_on_disk.get("zfs-rollback")
        ref = skill.source_path.parent / "references" / "deep.md"
        assert record_skill_read(str(ref)) == skill.id

    async def test_an_unrelated_file_is_no_receipt(self, no_daemon_store,
                                                    skill_on_disk, tmp_path):
        other = tmp_path / "notes.md"
        other.write_text("no skill here")
        assert record_skill_read(str(other)) is None
        assert no_daemon_store.list_skill_events() == []

    async def test_the_executor_records_the_read_at_dispatch(
            self, no_daemon_store, skill_on_disk):
        """The choke point: every surface's consultation passes through
        the executor's read_file, so the receipt catches them all."""
        from halbert_core.tools.executor import ToolExecutor
        from halbert_core.tools.safety import ToolSafetyFramework

        executor = ToolExecutor(safety=ToolSafetyFramework())
        skill = skill_on_disk.get("zfs-rollback")
        result = await executor._read_file({"path": str(skill.source_path)})
        assert "body" in result
        rows = no_daemon_store.list_skill_events()
        assert [r["event"] for r in rows] == ["read"]
        assert rows[0]["skill_id"] == skill.id

    async def test_without_a_registry_the_read_is_just_a_read(
            self, no_daemon_store, tmp_path):
        set_active_registry(None)
        d = tmp_path / "plain"
        d.mkdir()
        f = d / "file.md"
        f.write_text("words")
        from halbert_core.tools.executor import ToolExecutor
        from halbert_core.tools.safety import ToolSafetyFramework

        executor = ToolExecutor(safety=ToolSafetyFramework())
        assert "words" in await executor._read_file({"path": str(f)})
        assert no_daemon_store.list_skill_events() == []


class TestSeamTwoActivations:

    def _machine(self, matches, session_id="sess-1"):
        from halbert_core.agents.state_machine import AgentStateMachine

        m = AgentStateMachine.__new__(AgentStateMachine)
        m.ctx = type("C", (), {
            "intake": type("I", (), {"active_skills": matches})(),
            "session_id": session_id,
            "request_id": "req-1",
        })()
        return m

    def _match(self, skill, explicit=False):
        from halbert_core.skills.matcher import SkillMatch
        return SkillMatch(skill=skill, score=9, explicit=explicit)

    def test_a_matched_skill_gets_a_matched_row(self, no_daemon_store,
                                                 skill_on_disk):
        skill = skill_on_disk.get("zfs-rollback")
        self._machine([self._match(skill)])._record_skill_activation()
        rows = no_daemon_store.list_skill_events()
        assert [r["event"] for r in rows] == ["matched"]
        assert rows[0]["skill_id"] == skill.id
        assert rows[0]["session_id"] == "sess-1"

    def test_an_explicit_invocation_gets_an_explicit_row(self, no_daemon_store,
                                                         skill_on_disk):
        skill = skill_on_disk.get("zfs-rollback")
        self._machine([self._match(skill, explicit=True)])._record_skill_activation()
        rows = no_daemon_store.list_skill_events()
        assert [r["event"] for r in rows] == ["explicit"]

    def test_a_turn_without_skills_writes_nothing(self, no_daemon_store):
        self._machine([])._record_skill_activation()
        assert no_daemon_store.list_skill_events() == []

    def test_telemetry_never_costs_the_turn(self, monkeypatch, skill_on_disk):
        import halbert_core.skills.telemetry as telemetry

        def boom():
            raise RuntimeError("store exploded")
        monkeypatch.setattr(telemetry, "_store", boom)
        skill = skill_on_disk.get("zfs-rollback")
        m = self._machine([self._match(skill)])
        m._record_skill_activation()   # must not raise

    def test_a_skill_without_an_id_is_skipped_not_named(self, no_daemon_store,
                                                        tmp_path):
        """The row keys on identity, never name: a match whose skill never
        got an id writes nothing rather than a name-keyed row."""
        d = tmp_path / "no-id"
        d.mkdir()
        src = d / "SKILL.md"
        src.write_text("body")
        bare = _skill("no-id", src)
        assert bare.id is None
        self._machine([self._match(bare)])._record_skill_activation()
        assert no_daemon_store.list_skill_events() == []


class TestTheRegistryHolder:

    def test_the_holder_round_trips(self, skill_on_disk):
        assert active_registry() is skill_on_disk

    def test_the_default_is_none(self):
        set_active_registry(None)
        assert active_registry() is None