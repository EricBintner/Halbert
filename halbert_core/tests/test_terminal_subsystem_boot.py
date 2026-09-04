# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Dashboard startup turns the terminal pool on.

Plan B's block machinery — OSC 133 markers, block ids, terminal_blocks rows,
the >2s promotion — all hang off ``terminal_pool_wanted()``, which is False
until something calls ``set_terminal_pool_enabled(True)``. Until this hook
existed the only caller in the repository was a test, so every command in
production took the subprocess fallback and no block was ever produced.

The reaper and the pool are started independently: a reaper that fails to
start must not leave the pool disabled, because that failure mode is silent
and its symptom (no blocks, ever) looks nothing like its cause.
"""

import pytest

pytest.importorskip("fastapi")

from halbert_core.dashboard import app as dashboard_app  # noqa: E402
from halbert_core.streaming import terminal_bridge  # noqa: E402


@pytest.fixture(autouse=True)
def _pool_disabled():
    """Each test starts from the production default and restores it.

    Writes the module global directly rather than calling the setter: one
    test replaces that setter with a raising stub, and a fixture that tore
    down through the thing under test would fail on its own scaffolding.
    """
    terminal_bridge._pool_enabled = False
    yield
    terminal_bridge._pool_enabled = False


class _FakeManager:
    def __init__(self, boom=False):
        self.boom = boom
        self.reaper_started = 0

    def start_reaper(self):
        if self.boom:
            raise RuntimeError("no event loop")
        self.reaper_started += 1


def test_starting_the_subsystem_enables_the_pool(monkeypatch):
    mgr = _FakeManager()
    monkeypatch.setattr(
        "halbert_core.streaming.session_manager.get_terminal_manager", lambda: mgr
    )

    result = dashboard_app.start_terminal_subsystem()

    assert terminal_bridge._pool_enabled is True
    assert mgr.reaper_started == 1
    assert result == {"pool": True, "reaper": True}


def test_a_reaper_failure_does_not_leave_the_pool_disabled(monkeypatch):
    mgr = _FakeManager(boom=True)
    monkeypatch.setattr(
        "halbert_core.streaming.session_manager.get_terminal_manager", lambda: mgr
    )

    result = dashboard_app.start_terminal_subsystem()

    # The pool is the half that matters for blocks; a dead reaper only means
    # exited sessions linger. Coupling them would trade a visible problem for
    # an invisible one.
    assert terminal_bridge._pool_enabled is True
    assert result == {"pool": True, "reaper": False}


def test_it_never_raises_into_startup(monkeypatch):
    def boom():
        raise RuntimeError("import failed")

    monkeypatch.setattr(
        "halbert_core.streaming.session_manager.get_terminal_manager", boom
    )
    monkeypatch.setattr(
        terminal_bridge, "set_terminal_pool_enabled",
        lambda enabled: (_ for _ in ()).throw(RuntimeError("nope")),
    )

    # Startup keeps booting. The dashboard without a terminal pool is a
    # dashboard; the dashboard that refused to start is nothing.
    assert dashboard_app.start_terminal_subsystem() == {"pool": False, "reaper": False}
