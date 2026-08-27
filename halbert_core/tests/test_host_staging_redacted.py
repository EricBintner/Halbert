# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Staged host config must be redacted before it becomes searchable.

_stage_config_files writes into the SourcePrep-visible tree. Anything that
lands there is indexed and returned by scoped queries, so a secret reaching
this directory is a secret in the knowledge base.
"""
from __future__ import annotations

from pathlib import Path

from halbert_core.tools.register_host_project import _stage_config_files


def test_staged_nmconnection_has_psk_redacted(tmp_path):
    src_dir = tmp_path / "etc" / "NetworkManager" / "system-connections"
    src_dir.mkdir(parents=True)
    conn = src_dir / "HomeWiFi.nmconnection"
    conn.write_text(
        "[connection]\nid=HomeWiFi\ntype=wifi\n\n"
        "[wifi-security]\nkey-mgmt=wpa-psk\npsk=hunter2supersecret\n"
    )

    staging = tmp_path / "staged"
    count = _stage_config_files([str(conn)], staging)

    assert count == 1
    staged_files = list(staging.rglob("HomeWiFi.nmconnection"))
    assert len(staged_files) == 1
    content = staged_files[0].read_text()
    assert "hunter2supersecret" not in content


def test_staged_wireguard_key_is_redacted(tmp_path):
    src = tmp_path / "etc" / "wireguard"
    src.mkdir(parents=True)
    wg = src / "wg0.conf"
    wg.write_text(
        "[Interface]\nPrivateKey = aGVsbG93b3JsZGJhc2U2NHNlY3JldA=\n"
        "Address = 10.0.0.1/24\nListenPort = 51820\n"
    )

    staging = tmp_path / "staged"
    _stage_config_files([str(wg)], staging)

    staged = list(staging.rglob("wg0.conf"))[0].read_text()
    assert "aGVsbG93b3JsZGJhc2U2NHNlY3JldA=" not in staged
    assert "51820" in staged  # non-secret content survives


def test_staged_directory_tree_is_redacted(tmp_path):
    """Directory staging walks recursively; every file must be redacted."""
    src = tmp_path / "etc" / "NetworkManager" / "system-connections"
    src.mkdir(parents=True)
    (src / "a.nmconnection").write_text("[wifi-security]\npsk=secretAvalue\n")
    (src / "b.nmconnection").write_text("[wifi-security]\npsk=secretBvalue\n")

    staging = tmp_path / "staged"
    count = _stage_config_files([str(src)], staging)

    assert count == 2
    all_text = "".join(p.read_text() for p in staging.rglob("*.nmconnection"))
    assert "secretAvalue" not in all_text
    assert "secretBvalue" not in all_text


def test_binary_plist_is_staged_as_readable_xml(tmp_path):
    """Binary plists must be converted, not copied as unreadable bytes."""
    import plistlib

    src = tmp_path / "Library" / "LaunchDaemons"
    src.mkdir(parents=True)
    p = src / "com.example.daemon.plist"
    p.write_bytes(
        plistlib.dumps({"Label": "com.example.daemon"}, fmt=plistlib.FMT_BINARY)
    )

    staging = tmp_path / "staged"
    _stage_config_files([str(p)], staging)

    staged = list(staging.rglob("com.example.daemon.plist"))[0].read_text()
    assert "com.example.daemon" in staged
    assert "�" not in staged


def test_plist_secret_is_redacted_when_staged(tmp_path):
    """A credential inside a plist must not survive staging."""
    import plistlib

    src = tmp_path / "Library" / "LaunchAgents"
    src.mkdir(parents=True)
    p = src / "com.example.agent.plist"
    p.write_bytes(plistlib.dumps({
        "Label": "com.example.agent",
        "EnvironmentVariables": {"API_TOKEN": "sk-live-shouldnotsurvive"},
    }, fmt=plistlib.FMT_BINARY))

    staging = tmp_path / "staged"
    _stage_config_files([str(p)], staging)

    staged = list(staging.rglob("com.example.agent.plist"))[0].read_text()
    assert "sk-live-shouldnotsurvive" not in staged
    assert "com.example.agent" in staged  # non-secret content survives


def test_unparseable_file_is_still_staged(tmp_path):
    """Parser degrades to text; staging must not silently drop the file."""
    src = tmp_path / "etc"
    src.mkdir()
    f = src / "dispatcher.conf"
    f.write_text("INTERFACE=eth0\nSTATUS=up\n")  # no [section] header

    staging = tmp_path / "staged"
    count = _stage_config_files([str(f)], staging)

    assert count == 1
    assert "INTERFACE=eth0" in list(staging.rglob("dispatcher.conf"))[0].read_text()


def test_missing_source_is_skipped_not_fatal(tmp_path):
    staging = tmp_path / "staged"
    assert _stage_config_files([str(tmp_path / "nope.conf")], staging) == 0


def test_staged_file_keeps_its_trailing_newline(tmp_path):
    """The staged copy is diffed against the live host to spot drift.

    Rebuilding the text from the parser's `lines` loses the final newline —
    `splitlines()` cannot express one — so without a fix every staged file
    would differ from its original by a "\\ No newline at end of file", burying
    the redaction changes that actually matter under noise on every file.
    """
    src = tmp_path / "etc"
    src.mkdir()
    f = src / "sysctl.conf"
    original = "net.ipv4.ip_forward = 1\nkernel.pid_max = 4194304\n"
    f.write_text(original)

    staging = tmp_path / "staged"
    _stage_config_files([str(f)], staging)

    staged = list(staging.rglob("sysctl.conf"))[0].read_text()
    assert staged.endswith("\n")
    assert staged == original  # nothing to redact: byte-identical round-trip


def test_empty_config_file_is_still_staged(tmp_path):
    """An empty drop-in is a fact about the host, not an absence of one.

    Masking a unit or blanking a vendor default is done with an empty file, so
    a staged tree that omits it misreports the machine's config inventory.
    """
    src = tmp_path / "etc" / "sysctl.d"
    src.mkdir(parents=True)
    (src / "99-override.conf").write_text("")

    staging = tmp_path / "staged"
    count = _stage_config_files([str(src)], staging)

    assert count == 1
    staged = list(staging.rglob("99-override.conf"))
    assert len(staged) == 1
    assert staged[0].read_text() == ""


def test_unreadable_file_does_not_abort_the_run(tmp_path):
    """One permission-denied file must not stop the rest from staging."""
    src = tmp_path / "etc"
    src.mkdir()
    good = src / "good.conf"
    good.write_text("[Unit]\nDescription=fine\n")
    bad = src / "bad.conf"
    bad.write_text("[Unit]\nDescription=nope\n")
    bad.chmod(0o000)

    staging = tmp_path / "staged"
    try:
        count = _stage_config_files([str(good), str(bad)], staging)
        assert count >= 1
        assert list(staging.rglob("good.conf"))
    finally:
        bad.chmod(0o644)
