# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""A15 own-bug 5: the monitor-hash probe for detector_sweep surfaces
``~/.ssh``'s own listing (names, sizes, modes, mtimes) so a permissions
change is caught — but that listing was persisted VERBATIM into
monitor_hashes.json under the scheduler data dir. FD-12: ``~/.ssh`` is
digest-only — a change is still detectable (any name/size/mode/mtime
change moves the digest), but the actual filenames never leave the probe.
"""
import os

import pytest

pytest.importorskip("fastapi")

from halbert_core.dashboard.app import _detector_sweep_probe


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(os.path, "expanduser", lambda p: str(tmp_path) if p == "~" else p)
    return tmp_path


def test_ssh_directory_filenames_never_appear_in_the_probe_text(home):
    ssh = home / ".ssh"
    ssh.mkdir()
    (ssh / "id_ed25519_my_secret_key").write_text("not a real key")
    ok, text = _detector_sweep_probe()
    assert ok
    assert "id_ed25519_my_secret_key" not in text


def test_ssh_directory_is_reduced_to_a_digest(home):
    ssh = home / ".ssh"
    ssh.mkdir()
    (ssh / "config").write_text("Host x")
    ok, text = _detector_sweep_probe()
    assert ok
    ssh_line = next(line for line in text.splitlines() if str(ssh) in line)
    assert "sha256=" in ssh_line
    assert "size=" not in ssh_line and "mode=" not in ssh_line


def test_a_change_under_ssh_still_moves_the_digest(home):
    ssh = home / ".ssh"
    ssh.mkdir()
    (ssh / "config").write_text("Host x")
    _, before = _detector_sweep_probe()

    (ssh / "config").write_text("Host x\nUser someone")
    _, after = _detector_sweep_probe()

    assert before != after


def test_a_missing_ssh_directory_is_reported_absent(home):
    ok, text = _detector_sweep_probe()
    assert ok
    assert f"{home / '.ssh'}: absent" in text
