# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests: ConfigWatcher SourcePrep re-index callback → unified project (T-H1.4).

Verifies the callback invokes SourcePrepSetup.apply(build_fast_sync_only=True)
(re-stage host/, incremental fast_sync, re-push edges) instead of the legacy
HostProjectRegistrar.register("halbert-host"). The detector sweep is
exercised separately.
"""
from __future__ import annotations

import time

import halbert_core.integrations.sourceprep_setup as setup_mod
from halbert_core.config.watcher import create_sourceprep_reindex_callback


def test_reindex_callback_uses_unified_apply(monkeypatch):
    called: dict = {}

    class _FakeSetup:
        def __init__(self, *args, **kwargs):
            called["instantiated"] = True

        def apply(self, build=False, build_fast_sync_only=False, **kwargs):
            called["build"] = build
            called["build_fast_sync_only"] = build_fast_sync_only
            return {
                "project": "halbert",
                "build": {"fast_sync": {"status": "PIPELINE_UP_TO_DATE"}},
            }

    monkeypatch.setattr(setup_mod, "SourcePrepSetup", _FakeSetup)
    # The watcher imports SourcePrepSetup lazily inside _do_reindex, so patch
    # the name the watcher resolves: the module attribute.
    import halbert_core.config.watcher as watcher_mod
    # Force the lazy import to see the fake by patching the source module.
    monkeypatch.setattr(
        "halbert_core.integrations.sourceprep_setup.SourcePrepSetup", _FakeSetup
    )

    cb = create_sourceprep_reindex_callback(debounce_s=0.0)
    cb([])  # schedules a 0s timer
    # Allow the daemon Timer thread to run.
    deadline = time.time() + 2.0
    while time.time() < deadline and "build_fast_sync_only" not in called:
        time.sleep(0.01)

    assert called.get("instantiated") is True
    assert called.get("build_fast_sync_only") is True


def test_reindex_callback_skips_when_daemon_unreachable(monkeypatch, caplog):
    class _FakeSetup:
        def __init__(self, *args, **kwargs):
            pass

        def apply(self, build_fast_sync_only=False, **kwargs):
            return {"status": "skipped", "reason": "daemon unreachable"}

    monkeypatch.setattr(
        "halbert_core.integrations.sourceprep_setup.SourcePrepSetup", _FakeSetup
    )

    cb = create_sourceprep_reindex_callback(debounce_s=0.0)
    cb([])
    # Should not raise; logged as skipped.
    time.sleep(0.2)


def test_reindex_callback_survives_apply_exception(monkeypatch):
    class _FakeSetup:
        def __init__(self, *args, **kwargs):
            pass

        def apply(self, **kwargs):
            raise RuntimeError("boom")

    monkeypatch.setattr(
        "halbert_core.integrations.sourceprep_setup.SourcePrepSetup", _FakeSetup
    )

    cb = create_sourceprep_reindex_callback(debounce_s=0.0)
    cb([])  # must not propagate the exception
    time.sleep(0.2)
