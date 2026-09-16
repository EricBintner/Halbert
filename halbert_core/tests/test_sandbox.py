# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for the Sandbox wrapper (B1c).

Fail direction: ``wrap_command`` raises ``SandboxUnavailable`` when no
sandbox can be built. It used to return the bare command, which a caller
had no way to detect — that inversion is tested, not assumed.
"""

import os

import pytest

from halbert_core.streaming.sandbox import Sandbox, SandboxUnavailable


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
    writable_real = os.path.realpath("/var/log/halbert")
    wrapped = sandbox.wrap_command("ls /", writable_paths=["/var/log/halbert"])
    assert wrapped.startswith("bwrap ")
    assert "--ro-bind / /" in wrapped
    assert f"--bind {writable_real} {writable_real}" in wrapped
    assert wrapped.endswith("-- /bin/sh -c 'ls /'" or "/bin/sh -c 'ls /'" in wrapped)


def test_wrap_macos_seatbelt(monkeypatch, sandbox):
    monkeypatch.setattr("halbert_core.streaming.sandbox.platform.system", lambda: "Darwin")
    monkeypatch.setattr("halbert_core.streaming.sandbox.shutil.which", lambda b: "/usr/bin/sandbox-exec" if b == "sandbox-exec" else None)
    wrapped = sandbox.wrap_command("ls /", writable_paths=["/tmp/halbert"])
    assert wrapped.startswith("sandbox-exec -p ")
    assert "/bin/sh -c " in wrapped
    # Permissive v1 profile carries system-dir write denies
    assert "/etc" in wrapped


def test_wrap_unsupported_platform_raises(monkeypatch, sandbox):
    monkeypatch.setattr("halbert_core.streaming.sandbox.platform.system", lambda: "Windows")
    with pytest.raises(SandboxUnavailable) as exc:
        sandbox.wrap_command("ls /", writable_paths=["/tmp"])
    assert exc.value.error_type == "unsupported_platform"


def test_wrap_unavailable_binary_raises(monkeypatch, sandbox):
    # On Linux but bwrap not installed
    monkeypatch.setattr("halbert_core.streaming.sandbox.platform.system", lambda: "Linux")
    monkeypatch.setattr("halbert_core.streaming.sandbox.shutil.which", lambda b: None)
    with pytest.raises(SandboxUnavailable) as exc:
        sandbox.wrap_command("ls /", writable_paths=["/tmp"])
    assert exc.value.error_type == "missing_binary"


def test_invalid_writable_paths_filtered(monkeypatch, sandbox):
    monkeypatch.setattr("halbert_core.streaming.sandbox.platform.system", lambda: "Linux")
    monkeypatch.setattr("halbert_core.streaming.sandbox.shutil.which", lambda b: "/usr/bin/bwrap" if b == "bwrap" else None)
    wrapped = sandbox.wrap_command(
        "ls /",
        writable_paths=["/var/log", "relative/bad", "/etc/../etc/shadow", "/tmp/ok"],
    )
    # Valid paths bound — by their RESOLVED spelling, because the kernel only
    # ever sees the resolved vnode (macOS: /tmp is /private/tmp; realpath on
    # Linux is the identity).
    log_real, ok_real = os.path.realpath("/var/log"), os.path.realpath("/tmp/ok")
    assert f"--bind {log_real} {log_real}" in wrapped
    assert f"--bind {ok_real} {ok_real}" in wrapped
    assert "relative/bad" not in wrapped
    assert "--bind /etc/../etc/shadow" not in wrapped


def test_never_writable_paths_refused(monkeypatch, sandbox):
    """`--bind / /` used to pass validate_path and re-bind the whole root
    read-write over the read-only profile — the caller named its own
    containment. The dangerous set is refused outright now."""
    monkeypatch.setattr("halbert_core.streaming.sandbox.platform.system", lambda: "Linux")
    monkeypatch.setattr("halbert_core.streaming.sandbox.shutil.which", lambda b: "/usr/bin/bwrap" if b == "bwrap" else None)
    wrapped = sandbox.wrap_command("ls /", writable_paths=["/", "/etc", "/proc/1"])
    assert "--bind / /" not in wrapped
    etc_real = os.path.realpath("/etc")
    assert f"--bind {etc_real}" not in wrapped
    assert "--bind /proc/1 /proc/1" not in wrapped


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
    # Paths are seatbelt double-quoted strings (json.dumps), and every one is
    # realpath'd first: on macOS the kernel sees /private/etc, so a rule
    # naming /etc literally protects nothing (verified dead before the fix).
    etc_real = os.path.realpath("/etc")
    assert f'(deny file-write* (subpath "{etc_real}"))' in profile
    assert '(deny file-write* (subpath "/System"))' in profile
    ssh_real = os.path.realpath("/etc/ssh")
    assert f'(deny file-read* (subpath "{ssh_real}"))' in profile


def test_seatbelt_profile_allows_network_explicitly(monkeypatch, sandbox):
    """Regression: a bare (version 1) profile denies network, so the shipped
    profile silently broke curl/brew/git fetch under /exec. Network policy is
    the classifier's layer; this profile must say so, not lie about it."""
    monkeypatch.setattr("halbert_core.streaming.sandbox.platform.system", lambda: "Darwin")
    profile = sandbox._seatbelt_profile([])
    assert "(allow network*)" in profile
