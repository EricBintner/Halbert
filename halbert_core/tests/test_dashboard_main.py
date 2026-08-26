"""Tests for the ``python -m halbert_core.dashboard`` entry point (B5)."""
import importlib
import subprocess
import sys

import pytest


def test_main_creates_app_and_runs_uvicorn(monkeypatch):
    import uvicorn

    calls = []

    def fake_run(app, **kwargs):
        calls.append((app, kwargs))

    monkeypatch.setattr(uvicorn, "run", fake_run)
    monkeypatch.setattr(sys, "argv", ["halbert", "--no-ollama-check", "--port", "8999"])

    from halbert_core.dashboard import __main__ as dash_main

    dash_main.main()

    assert len(calls) == 1
    app, kwargs = calls[0]
    assert hasattr(app, "routes")
    assert kwargs["port"] == 8999
    assert "reload" not in kwargs or kwargs["reload"] is False


def test_main_reload_uses_import_string(monkeypatch):
    import uvicorn

    calls = []
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: calls.append((app, kw)))
    monkeypatch.setattr(sys, "argv", ["halbert", "--no-ollama-check", "--reload", "--port", "8998"])

    from halbert_core.dashboard import __main__ as dash_main

    dash_main.main()
    assert calls == [("halbert_core.dashboard.app:app", {"host": "127.0.0.1", "port": 8998, "reload": True, "log_level": "info"})]


def test_module_help_exits_zero():
    result = subprocess.run(
        [sys.executable, "-m", "halbert_core.dashboard", "--help"],
        capture_output=True,
        timeout=60,
    )
    assert result.returncode == 0
    assert b"--port" in result.stdout


def test_env_defaults(monkeypatch):
    monkeypatch.setenv("HALBERT_PORT", "8123")
    monkeypatch.setenv("HALBERT_HOST", "0.0.0.0")
    import uvicorn

    calls = []
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: calls.append(kw))
    monkeypatch.setattr(sys, "argv", ["halbert", "--no-ollama-check"])

    from halbert_core.dashboard import __main__ as dash_main

    dash_main.main()
    assert calls[0]["port"] == 8123
    assert calls[0]["host"] == "0.0.0.0"
