# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Dashboard startup runs the Plan A conversation hooks exactly once:
migrate the legacy JSON stores, then mark any in-flight turn as interrupted
(spec §12: "interrupted at boot for any in_progress row"). Never fatal."""

import inspect
import json

import pytest

pytest.importorskip("fastapi")

from halbert_core.agents.conversation import Conversation  # noqa: E402
from halbert_core.agents.conversation_sqlite import SqliteConversationStore  # noqa: E402
from halbert_core.agents.threads import ThreadManager  # noqa: E402
from halbert_core.dashboard import app as dashboard_app  # noqa: E402


class _FakeThreadManager:
    def __init__(self):
        self.store = object()
        self.mark_calls = 0

    def mark_interrupted(self):
        self.mark_calls += 1
        return 2


def test_hooks_migrate_then_mark_interrupted(monkeypatch):
    tm = _FakeThreadManager()
    calls = []
    monkeypatch.setattr("halbert_core.agents.threads.get_thread_manager", lambda: tm)

    def fake_migrate(store):
        calls.append(("migrate", store, tm.mark_calls))
        return {"agent_json": 3, "legacy_json": 1}

    monkeypatch.setattr(
        "halbert_core.agents.migrations.migrate_legacy_conversations", fake_migrate
    )

    result = dashboard_app.run_conversation_boot_hooks()

    # migration ran once, against the manager's store, before mark_interrupted
    assert calls == [("migrate", tm.store, 0)]
    assert tm.mark_calls == 1
    assert result == {"agent_json": 3, "legacy_json": 1, "interrupted": 2}


def test_hooks_never_raise(monkeypatch):
    def boom():
        raise RuntimeError("no database")

    monkeypatch.setattr("halbert_core.agents.threads.get_thread_manager", boom)
    assert dashboard_app.run_conversation_boot_hooks() == {
        "agent_json": 0, "legacy_json": 0, "interrupted": 0,
    }


def test_mark_interrupted_failure_keeps_migration_counts(monkeypatch):
    tm = _FakeThreadManager()

    def bad_mark():
        raise RuntimeError("locked")

    tm.mark_interrupted = bad_mark
    monkeypatch.setattr("halbert_core.agents.threads.get_thread_manager", lambda: tm)
    monkeypatch.setattr(
        "halbert_core.agents.migrations.migrate_legacy_conversations",
        lambda store: {"agent_json": 1, "legacy_json": 0},
    )
    assert dashboard_app.run_conversation_boot_hooks() == {
        "agent_json": 1, "legacy_json": 0, "interrupted": 0,
    }


def test_startup_event_calls_the_hooks():
    src = inspect.getsource(dashboard_app.create_app)
    assert "run_conversation_boot_hooks()" in src
    # it runs before the identity bootstrap and the background starters
    assert src.index("run_conversation_boot_hooks()") < src.index("Bootstrap system identity")


# ---------------------------------------------------------------------------
# The same composition against the real collaborators. The fakes above pin the
# call order; only this pins what the order *means*: mark_interrupted() runs
# in the same boot, immediately after the migration, over the same store — so
# the migration must not leave its historical rows in_progress, or the sweep
# would flip every one of them to "interrupted" and the timeline would render
# "(Halbert restarted here)" on every legacy turn (review: Plan A / A12b).
# ---------------------------------------------------------------------------

_AGENT_CONV = {
    "conversation_id": "agent-1",
    "user_id": "u1",
    "title": "Disk usage on /var",
    "messages": [
        {"role": "user", "content": "why is /var filling up on this box",
         "timestamp": 1720000000.0, "metadata": {}},
        {"role": "assistant",
         "content": "journald is the culprit. Next, run journalctl --vacuum-size=200M.",
         "timestamp": 1720000060.0, "metadata": {}},
    ],
    "created_at": 1720000000.0,
    "updated_at": 1720000060.0,
    "metadata": {},
}


def test_boot_hooks_over_real_store_only_interrupt_the_live_turn(tmp_path, monkeypatch):
    store = SqliteConversationStore(":memory:")
    manager = ThreadManager(store)

    # A turn that was in flight when the previous process died.
    store.save(Conversation(
        conversation_id="live-1", user_id="u1", title="restart nginx",
        created_at=1720000100.0, updated_at=1720000100.0,
    ))
    assert store.append_message(
        "live-1", "user", "restart nginx please",
        origin="human", turn_id="turn-1", status="in_progress",
        timestamp=1720000100.0,
    ) is not None

    agent_dir = tmp_path / "agent-json"
    legacy_dir = tmp_path / "legacy-json"
    agent_dir.mkdir()
    legacy_dir.mkdir()
    (agent_dir / "agent-1.json").write_text(json.dumps(_AGENT_CONV))

    monkeypatch.setattr("halbert_core.agents.threads.get_thread_manager", lambda: manager)
    # Never read the real ~/.halbert and ~/.config/halbert stores from a test.
    monkeypatch.setattr("halbert_core.agents.migrations.AGENT_JSON_DIR", agent_dir)
    monkeypatch.setattr("halbert_core.agents.migrations.LEGACY_JSON_DIR", legacy_dir)

    try:
        result = dashboard_app.run_conversation_boot_hooks()

        # the one legacy file migrated; only the one live row was interrupted
        assert result == {"agent_json": 1, "legacy_json": 0, "interrupted": 1}

        migrated = store.list_messages("agent-1")
        assert [m["role"] for m in migrated] == ["user", "assistant"]
        assert [m["status"] for m in migrated] == ["complete", "complete"]

        assert [m["status"] for m in store.list_messages("live-1")] == ["interrupted"]
    finally:
        store.close()
