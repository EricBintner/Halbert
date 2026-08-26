# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for the Sandbox wrapper (B1c)."""

import pytest

from halbert_core.streaming.sandbox import Sandbox


# ---------------------------------------------------------------------------
# validate_path
# ---------------------------------------------------------------------------

class TestValidatePath:
    def setup_method(self):
        self.s = Sandbox()

    def test_absolute_path_valid(self):
        assert self.s.validate_path("/etc/halbert") is True
        assert self.s.validate_path("/var/log") is True
        assert self.s.validate_path("/") is True

    def test_relative_path_invalid(self):
        assert self.s.validate_path("relative/path") is False
        assert self.s.validate_path("./foo") is False
        assert self.s.validate_path("~/foo") is False

    def test_empty_invalid(self):
        assert self.s.validate_path("") is False
        assert self.s.validate_path(None) is False

    def test_null_byte_invalid(self):
        assert self.s.validate_path("/etc/foo\x00bar") is False

    def test_traversal_component_invalid(self):
        assert self.s.validate_path("/etc/../etc/shadow") is False
        assert self.s.validate_path("/a/b/../../c") is False

    def test_dotdot_in_filename_allowed(self):
        # '..' inside a filename (not a path component) is allowed
        assert self.s.validate_path("/home/user/my..file") is True
        assert self.s.validate_path("/var/data/v2..0") is True


# ---------------------------------------------------------------------------
# wrap_command platform dispatch
# ---------------------------------------------------------------------------

@pytest.fixture
def sandbox():
    return Sandbox()


def test_wrap_linux_bwrap(monkeypatch, sandbox):
    monkeypatch.setattr("halbert_core.streaming.sandbox.platform.system", lambda: "Linux")
    monkeypatch.setattr("halbert_core.streaming.sandbox.shutil.which", lambda b: "/usr/bin/bwrap" if b == "bwrap" else None)
    wrapped = sandbox.wrap_command("ls /", writable_paths=["/var/log/halbert"])
    assert wrapped.startswith("bwrap ")
    assert "--ro-bind / /" in wrapped
    assert "--bind /var/log/halbert /var/log/halbert" in wrapped
    assert wrapped.endswith("-- /bin/sh -c 'ls /'" or "/bin/sh -c 'ls /'" in wrapped)


def test_wrap_macos_seatbelt(monkeypatch, sandbox):
    monkeypatch.setattr("halbert_core.streaming.sandbox.platform.system", lambda: "Darwin")
    monkeypatch.setattr("halbert_core.streaming.sandbox.shutil.which", lambda b: "/usr/bin/sandbox-exec" if b == "sandbox-exec" else None)
    wrapped = sandbox.wrap_command("ls /", writable_paths=["/tmp/halbert"])
    assert wrapped.startswith("sandbox-exec -p ")
    assert "/bin/sh -c " in wrapped
    # Permissive v1 profile carries system-dir write denies
    assert "/etc" in wrapped


def test_wrap_unsupported_platform_returns_command(monkeypatch, sandbox):
    monkeypatch.setattr("halbert_core.streaming.sandbox.platform.system", lambda: "Windows")
    # is_available returns False on Windows anyway
    wrapped = sandbox.wrap_command("ls /", writable_paths=["/tmp"])
    assert wrapped == "ls /"


def test_wrap_unavailable_binary_returns_command(monkeypatch, sandbox):
    # On Linux but bwrap not installed
    monkeypatch.setattr("halbert_core.streaming.sandbox.platform.system", lambda: "Linux")
    monkeypatch.setattr("halbert_core.streaming.sandbox.shutil.which", lambda b: None)
    wrapped = sandbox.wrap_command("ls /", writable_paths=["/tmp"])
    assert wrapped == "ls /"


def test_invalid_writable_paths_filtered(monkeypatch, sandbox):
    monkeypatch.setattr("halbert_core.streaming.sandbox.platform.system", lambda: "Linux")
    monkeypatch.setattr("halbert_core.streaming.sandbox.shutil.which", lambda b: "/usr/bin/bwrap" if b == "bwrap" else None)
    wrapped = sandbox.wrap_command(
        "ls /",
        writable_paths=["/var/log", "relative/bad", "/etc/../etc/shadow", "/tmp/ok"],
    )
    # Valid paths bound, invalid ones dropped
    assert "--bind /var/log /var/log" in wrapped
    assert "--bind /tmp/ok /tmp/ok" in wrapped
    assert "relative/bad" not in wrapped
    assert "--bind /etc/../etc/shadow" not in wrapped


# ---------------------------------------------------------------------------
# is_available
# ---------------------------------------------------------------------------

def test_is_available_macos(monkeypatch, sandbox):
    monkeypatch.setattr("halbert_core.streaming.sandbox.platform.system", lambda: "Darwin")
    monkeypatch.setattr("halbert_core.streaming.sandbox.shutil.which", lambda b: "/usr/bin/sandbox-exec" if b == "sandbox-exec" else None)
    assert sandbox.is_available() is True


def test_is_available_linux_no_bwrap(monkeypatch, sandbox):
    monkeypatch.setattr("halbert_core.streaming.sandbox.platform.system", lambda: "Linux")
    monkeypatch.setattr("halbert_core.streaming.sandbox.shutil.which", lambda b: None)
    assert sandbox.is_available() is False


def test_seatbelt_profile_contains_system_dir_denies(monkeypatch, sandbox):
    monkeypatch.setattr("halbert_core.streaming.sandbox.platform.system", lambda: "Darwin")
    profile = sandbox._seatbelt_profile(["/tmp/halbert"])
    # Permissive v1: deny writes to system dirs, deny reads to sensitive paths.
    # Paths are seatbelt double-quoted strings (json.dumps), e.g. (subpath "/etc")
    assert '(deny file-write* (subpath "/etc"))' in profile
    assert '(deny file-write* (subpath "/System"))' in profile
    assert '/etc/ssh' in profile  # sensitive read deny present
