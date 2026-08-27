# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Dashboard startup runs the Plan A conversation hooks exactly once:
migrate the legacy JSON stores, then mark any in-flight turn as interrupted
(spec §12: "interrupted at boot for any in_progress row"). Never fatal."""

import inspect

import pytest

pytest.importorskip("fastapi")

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
