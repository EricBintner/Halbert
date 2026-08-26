"""Sidecar parent watchdog: stop the backend when the launching process dies."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time

from halbert_core.dashboard import parent_watchdog as pw


def test_not_configured_returns_none():
    assert pw.start_parent_watchdog(env={}) is None


def test_invalid_pid_is_ignored(caplog):
    assert pw.start_parent_watchdog(env={pw.ENV_VAR: "abc"}) is None
    assert pw.start_parent_watchdog(env={pw.ENV_VAR: "0"}) is None
    assert pw.start_parent_watchdog(env={pw.ENV_VAR: str(os.getpid())}) is None


def test_already_dead_parent_stops_immediately():
    fired = threading.Event()
    # Spawn and reap a child so we hold a pid that is guaranteed dead.
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    assert pw.start_parent_watchdog(env={pw.ENV_VAR: str(proc.pid)}, stop=fired.set) is None
    assert fired.is_set()


def test_stop_fires_when_parent_exits():
    fired = threading.Event()
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        thread = pw.start_parent_watchdog(
            env={pw.ENV_VAR: str(proc.pid)}, interval_s=0.05, stop=fired.set
        )
        assert thread is not None and thread.daemon
        assert not fired.wait(0.3), "must not fire while the parent is alive"
        proc.kill()
        proc.wait()
        assert fired.wait(3.0), "watchdog did not fire after the parent died"
    finally:
        if proc.poll() is None:
            proc.kill()


def test_watch_uses_injected_probe():
    calls = []
    states = iter([True, True, False])
    pw.watch(1234, interval_s=0.01, stop=lambda: calls.append("stop"), alive=lambda _pid: next(states))
    assert calls == ["stop"]
