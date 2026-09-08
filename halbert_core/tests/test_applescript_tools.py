# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""AppleScript tool scaffold (tools/applescript_tools.py, task A1).

Everything is mocked: osascript never runs in these tests, so they pass
on any platform. The platform/capability gates are exercised by mocking
``platform.system`` and ``has_capability``; the config gate goes through
the real loader pointed at a temp file, so the per-call re-read behavior
is tested against actual file contents.
"""
import asyncio
import platform

import pytest

from halbert_core.config import applescript_config
from halbert_core.tools import applescript_tools
from halbert_core.tools.applescript_tools import (
    APPLESCRIPT_TOOL_HANDLERS,
    APPLESCRIPT_TOOL_SCHEMAS,
    MAX_OUTPUT_BYTES,
    register_applescript_tools,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fakes
# ─────────────────────────────────────────────────────────────────────────────

class FakeExecutor:
    """Records register() calls the way ToolExecutor would."""

    def __init__(self):
        self.registered = {}

    def register(self, name, handler, schema):
        self.registered[name] = (handler, schema)


class FakeStream:
    """Stand-in for the StreamReader on a subprocess pipe: hands out the
    canned bytes in chunks; a nonzero delay makes reads block (past any
    test timeout), simulating a process whose pipes never close."""

    def __init__(self, data=b"", chunk_size=64 * 1024, delay=0.0):
        self._data = data
        self._chunk_size = chunk_size
        self._delay = delay

    async def read(self, n):
        if self._delay:
            await asyncio.sleep(self._delay)
        if not self._data:
            return b""
        chunk = self._data[: min(n, self._chunk_size)]
        self._data = self._data[len(chunk):]
        return chunk


class FakeProc:
    """Stand-in for asyncio.subprocess.Process: canned streams, a kill()
    that records (or raises, for the already-exited kill race) and a
    wait() returning the canned exit code."""

    def __init__(self, returncode=0, stdout=b"", stderr=b"",
                 stream_delay=0.0, kill_error=None):
        self.returncode = returncode
        self.stdout = FakeStream(stdout, delay=stream_delay)
        self.stderr = FakeStream(stderr, delay=stream_delay)
        self.killed = False
        self._kill_error = kill_error

    def kill(self):
        if self._kill_error is not None:
            raise self._kill_error
        self.killed = True

    async def wait(self):
        return self.returncode


def _write_config(path, enabled, timeout_seconds=10):
    path.write_text(f"enabled: {str(enabled).lower()}\ntimeout_seconds: {timeout_seconds}\n")
    return path


@pytest.fixture
def isolated_config(tmp_path, monkeypatch):
    """Point the applescript config loader at a temp file (OFF by default)."""
    path = tmp_path / "applescript_config.yml"
    monkeypatch.setattr(applescript_config, "_config_path", lambda: path)
    return path


def _mock_spawn(monkeypatch, procs):
    """Replace asyncio.create_subprocess_exec; records argv, returns procs in order."""
    calls = []

    async def fake_create_subprocess_exec(*argv, **kwargs):
        calls.append(list(argv))
        return procs.pop(0) if len(procs) > 1 else procs[0]

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    return calls


# ─────────────────────────────────────────────────────────────────────────────
# Config (config/applescript_config.py)
# ─────────────────────────────────────────────────────────────────────────────

class TestAppleScriptConfig:
    def test_defaults_are_disabled(self):
        cfg = applescript_config.AppleScriptConfig()
        assert cfg.enabled is False
        assert cfg.timeout_seconds == 10

    def test_load_returns_defaults_when_no_file(self, isolated_config):
        cfg = applescript_config.load_config()
        assert cfg.enabled is False
        assert cfg.timeout_seconds == 10

    def test_load_reads_enabled_and_timeout(self, isolated_config):
        isolated_config.write_text("enabled: true\ntimeout_seconds: 25\n")
        cfg = applescript_config.load_config()
        assert cfg.enabled is True
        assert cfg.timeout_seconds == 25

    def test_quoted_false_string_reads_as_disabled(self, isolated_config):
        """enabled: "false" (a YAML string) must NOT count as enabled."""
        isolated_config.write_text('enabled: "false"\n')
        assert applescript_config.load_config().enabled is False

    def test_corrupt_file_falls_back_to_disabled(self, isolated_config):
        isolated_config.write_text("enabled: [not:: a:: valid:: yaml: dict\n")
        cfg = applescript_config.load_config()
        assert cfg.enabled is False
        assert cfg.timeout_seconds == 10


# ─────────────────────────────────────────────────────────────────────────────
# Registration gating (platform + capability)
# ─────────────────────────────────────────────────────────────────────────────

class TestRegistration:
    def test_registers_both_tools_on_macos_with_capability(self, monkeypatch):
        monkeypatch.setattr(platform, "system", lambda: "Darwin")
        import halbert_core.capabilities as caps
        monkeypatch.setattr(caps, "has_capability", lambda cap: True)

        executor = FakeExecutor()
        register_applescript_tools(executor)
        assert set(executor.registered) == {"run_applescript", "run_jxa"}

    def test_not_registered_on_linux(self, monkeypatch):
        monkeypatch.setattr(platform, "system", lambda: "Linux")
        import halbert_core.capabilities as caps
        monkeypatch.setattr(caps, "has_capability", lambda cap: True)

        executor = FakeExecutor()
        register_applescript_tools(executor)
        assert executor.registered == {}

    def test_not_registered_when_capability_off(self, monkeypatch):
        monkeypatch.setattr(platform, "system", lambda: "Darwin")
        import halbert_core.capabilities as caps
        monkeypatch.setattr(caps, "has_capability", lambda cap: False)

        executor = FakeExecutor()
        register_applescript_tools(executor)
        assert executor.registered == {}

    def test_every_schema_has_a_handler_and_matching_name(self):
        assert set(APPLESCRIPT_TOOL_SCHEMAS) == {"run_applescript", "run_jxa"}
        assert set(APPLESCRIPT_TOOL_HANDLERS) == set(APPLESCRIPT_TOOL_SCHEMAS)
        for name, schema in APPLESCRIPT_TOOL_SCHEMAS.items():
            assert schema["name"] == name
            assert "script" in schema["parameters"]["properties"]

    def test_capability_constant_is_registered(self):
        from halbert_core.capabilities import (
            ALL_CAPABILITIES,
            CAP_APPLESCRIPT,
            _PRESET_HOME,
            _PRESET_SYSADMIN,
        )
        assert CAP_APPLESCRIPT == "applescript"
        assert CAP_APPLESCRIPT in ALL_CAPABILITIES
        assert _PRESET_SYSADMIN[CAP_APPLESCRIPT] is True
        assert _PRESET_HOME[CAP_APPLESCRIPT] is False


# ─────────────────────────────────────────────────────────────────────────────
# Handlers — subprocess mocked
# ─────────────────────────────────────────────────────────────────────────────

class TestHandlers:
    def test_run_applescript_success(self, isolated_config, monkeypatch):
        _write_config(isolated_config, enabled=True)
        calls = _mock_spawn(monkeypatch, [
            FakeProc(returncode=0, stdout=b"Halbert\n"),
        ])

        result = asyncio.run(APPLESCRIPT_TOOL_HANDLERS["run_applescript"](
            {"script": 'tell application "Finder" to name of home'}))

        assert result["success"] is True
        assert result["output"] == "Halbert\n"
        assert result["exit_code"] == 0
        assert calls == [["osascript", "-e",
                          'tell application "Finder" to name of home']]

    def test_run_jxa_uses_javascript_language_flag(self, isolated_config, monkeypatch):
        _write_config(isolated_config, enabled=True)
        calls = _mock_spawn(monkeypatch, [
            FakeProc(returncode=0, stdout=b'"home"\n'),
        ])

        result = asyncio.run(APPLESCRIPT_TOOL_HANDLERS["run_jxa"](
            {"script": "app = Application('Finder'); app.home().name()"}))

        assert result["success"] is True
        assert calls == [["osascript", "-l", "JavaScript", "-e",
                          "app = Application('Finder'); app.home().name()"]]

    def test_invalid_script_returns_structured_error(self, isolated_config, monkeypatch):
        _write_config(isolated_config, enabled=True)
        _mock_spawn(monkeypatch, [
            FakeProc(returncode=1, stderr=b"exec error: Expected end of line but found \n"),
        ])

        result = asyncio.run(APPLESCRIPT_TOOL_HANDLERS["run_applescript"](
            {"script": "tell application"}))

        assert result["success"] is False
        assert result["exit_code"] == 1
        assert "Expected end of line" in result["error"]
        # stderr is surfaced verbatim so the agent can self-correct
        assert result["output"] == ""

    def test_missing_script_arg_is_a_structured_error(self, isolated_config, monkeypatch):
        _write_config(isolated_config, enabled=True)
        calls = _mock_spawn(monkeypatch, [FakeProc()])

        result = asyncio.run(APPLESCRIPT_TOOL_HANDLERS["run_applescript"]({}))

        assert result["success"] is False
        assert calls == []  # nothing was executed

    def test_non_string_script_is_rejected_not_crashed(self, isolated_config, monkeypatch):
        """A list arg must not reach str.strip and raise AttributeError."""
        _write_config(isolated_config, enabled=True)
        calls = _mock_spawn(monkeypatch, [FakeProc()])

        result = asyncio.run(APPLESCRIPT_TOOL_HANDLERS["run_applescript"](
            {"script": ["tell application \"Finder\""]}))

        assert result["success"] is False
        assert "must be a string" in result["error"]
        assert calls == []

    def test_spawn_failure_is_structured_not_a_crash(self, isolated_config, monkeypatch):
        _write_config(isolated_config, enabled=True)

        def fake_create_subprocess_exec(*argv, **kwargs):
            raise FileNotFoundError(2, "No such file or directory", "osascript")

        monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

        result = asyncio.run(APPLESCRIPT_TOOL_HANDLERS["run_applescript"](
            {"script": "return 1"}))

        assert result["success"] is False
        assert "osascript" in result["error"]
        assert result["exit_code"] is None


class TestConfigGate:
    def test_refuses_when_config_off_without_spawning(self, isolated_config, monkeypatch):
        # no config file written — OFF by default
        calls = _mock_spawn(monkeypatch, [FakeProc()])

        result = asyncio.run(APPLESCRIPT_TOOL_HANDLERS["run_applescript"](
            {"script": "return 1"}))

        assert result["success"] is False
        assert result["exit_code"] is None
        assert "disabled" in result["error"].lower()
        # the refusal names the resolved config file so the user can act on it
        assert "applescript_config.yml" in result["error"]
        assert calls == []

    def test_config_is_reread_per_call(self, isolated_config, monkeypatch):
        """Flip the file between two calls in the same process: the second
        call must see the change (no caching)."""
        calls = _mock_spawn(monkeypatch, [FakeProc(returncode=0, stdout=b"ok\n")])

        first = asyncio.run(APPLESCRIPT_TOOL_HANDLERS["run_applescript"](
            {"script": "return 1"}))
        assert first["success"] is False  # off by default

        isolated_config.write_text("enabled: true\n")
        second = asyncio.run(APPLESCRIPT_TOOL_HANDLERS["run_applescript"](
            {"script": "return 1"}))

        assert second["success"] is True
        assert second["output"] == "ok\n"
        assert len(calls) == 1  # spawned exactly once — on the enabled call

    def test_platform_gate_refuses_even_when_config_on(self, isolated_config, monkeypatch):
        """Config ON but not macOS: the in-handler platform gate refuses
        without spawning (defense in depth against a stale registration)."""
        _write_config(isolated_config, enabled=True)
        monkeypatch.setattr(platform, "system", lambda: "Linux")
        calls = _mock_spawn(monkeypatch, [FakeProc()])

        result = asyncio.run(APPLESCRIPT_TOOL_HANDLERS["run_applescript"](
            {"script": "return 1"}))

        assert result["success"] is False
        assert result["exit_code"] is None
        assert "macos" in result["error"].lower()
        assert calls == []


class TestTimeout:
    def test_runaway_script_is_killed_at_configured_timeout(
            self, isolated_config, monkeypatch):
        _write_config(isolated_config, enabled=True, timeout_seconds=1)
        proc = FakeProc(stream_delay=30.0)  # a "delay 30" script
        _mock_spawn(monkeypatch, [proc])

        result = asyncio.run(APPLESCRIPT_TOOL_HANDLERS["run_applescript"](
            {"script": "delay 30"}))

        assert result["success"] is False
        assert result["exit_code"] is None
        assert "timed out" in result["error"].lower()
        assert proc.killed is True

    def test_timeout_config_is_reread_per_call(self, isolated_config, monkeypatch):
        """A timeout change in the file takes effect on the very next call:
        the same script that was killed at 1s completes under the raised
        limit (no caching)."""
        _write_config(isolated_config, enabled=True, timeout_seconds=1)
        slow = FakeProc(stream_delay=2.0, returncode=0, stdout=b"done\n")
        fast = FakeProc(stream_delay=2.0, returncode=0, stdout=b"done\n")
        _mock_spawn(monkeypatch, [slow, fast])
        handler = APPLESCRIPT_TOOL_HANDLERS["run_applescript"]

        killed = asyncio.run(handler({"script": "delay 30"}))
        assert "timed out" in killed["error"].lower()
        assert slow.killed is True

        isolated_config.write_text("enabled: true\ntimeout_seconds: 30\n")
        finished = asyncio.run(handler({"script": "delay 30"}))
        assert finished["success"] is True
        assert finished["output"] == "done\n"
        assert fast.killed is False

    def test_timeout_kill_race_when_child_already_exited(
            self, isolated_config, monkeypatch):
        """A grandchild holding the pipes keeps the reads blocked past the
        timeout while the child itself is gone: kill() raises
        ProcessLookupError, which must not escape the structured contract."""
        _write_config(isolated_config, enabled=True, timeout_seconds=1)
        proc = FakeProc(stream_delay=30.0, kill_error=ProcessLookupError())
        _mock_spawn(monkeypatch, [proc])

        result = asyncio.run(APPLESCRIPT_TOOL_HANDLERS["run_applescript"](
            {"script": "delay 30"}))

        assert result["success"] is False
        assert result["exit_code"] is None
        assert "timed out" in result["error"].lower()


class TestOutputCap:
    def test_stdout_beyond_cap_is_truncated_and_process_stopped(
            self, isolated_config, monkeypatch):
        _write_config(isolated_config, enabled=True)
        proc = FakeProc(stdout=b"x" * (MAX_OUTPUT_BYTES + 1000))
        _mock_spawn(monkeypatch, [proc])

        result = asyncio.run(APPLESCRIPT_TOOL_HANDLERS["run_applescript"](
            {"script": "cat a huge file"}))

        assert len(result["output"]) == MAX_OUTPUT_BYTES
        assert result["success"] is False
        assert "truncat" in result["error"].lower()
        assert "stdout" in result["error"]
        assert proc.killed is True

    def test_stderr_beyond_cap_is_truncated(self, isolated_config, monkeypatch):
        _write_config(isolated_config, enabled=True)
        proc = FakeProc(returncode=1,
                        stderr=b"e" * (MAX_OUTPUT_BYTES + 1000))
        _mock_spawn(monkeypatch, [proc])

        result = asyncio.run(APPLESCRIPT_TOOL_HANDLERS["run_applescript"](
            {"script": "fail loudly"}))

        assert result["success"] is False
        assert "truncat" in result["error"].lower()
        assert "stderr" in result["error"]
        # the notice was appended after the capped stderr text
        assert result["error"].endswith("the process was stopped.")

    def test_output_under_cap_is_untouched(self, isolated_config, monkeypatch):
        _write_config(isolated_config, enabled=True)
        proc = FakeProc(returncode=0, stdout=b"small\n")
        _mock_spawn(monkeypatch, [proc])

        result = asyncio.run(APPLESCRIPT_TOOL_HANDLERS["run_applescript"](
            {"script": "echo small"}))

        assert result["success"] is True
        assert result["output"] == "small\n"
        assert result["error"] == ""
        assert proc.killed is False
