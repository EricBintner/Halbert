# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Parser must degrade, never drop.

snapshot.py wraps parse + raw-text write in one try block, so any exception
escaping parse() means the file never reaches the knowledge base at all.
Config formats the role manifests harvest routinely violate strict ini rules.
"""
from __future__ import annotations

from halbert_core.config.parser import parse


def test_duplicate_keys_fall_back_to_text(tmp_path):
    """systemd drop-ins legitimately repeat directives."""
    p = tmp_path / "override.conf"
    p.write_text(
        "[Service]\n"
        "Environment=FOO=1\n"
        "Environment=BAR=2\n"
        "ExecStartPre=/bin/true\n"
        "ExecStartPre=/bin/echo hi\n"
    )
    result = parse(str(p))
    assert result["kind"] == "text"
    assert result["hash"]
    assert any("BAR=2" in line["text"] for line in result["lines"])


def test_missing_section_header_falls_back_to_text(tmp_path):
    """NetworkManager dispatcher scripts and bare KEY=value .conf files."""
    p = tmp_path / "dispatcher.conf"
    p.write_text("INTERFACE=eth0\nSTATUS=up\n")
    result = parse(str(p))
    assert result["kind"] == "text"
    assert any("INTERFACE=eth0" in line["text"] for line in result["lines"])


def test_valid_ini_still_parses_as_ini(tmp_path):
    """The fallback must not swallow files that parse cleanly."""
    p = tmp_path / "good.conf"
    p.write_text("[Unit]\nDescription=Test unit\n")
    result = parse(str(p))
    assert result["kind"] == "ini"
    assert result["sections"]["Unit"]["description"] == "Test unit"


import plistlib


def test_binary_plist_is_parsed_not_mangled(tmp_path):
    """Binary plists must not flow through the errors='replace' text path."""
    p = tmp_path / "com.example.daemon.plist"
    payload = {"Label": "com.example.daemon", "RunAtLoad": True, "KeepAlive": False}
    p.write_bytes(plistlib.dumps(payload, fmt=plistlib.FMT_BINARY))

    result = parse(str(p))
    assert result["kind"] == "plist"
    assert result["tree"]["Label"] == "com.example.daemon"
    assert result["tree"]["RunAtLoad"] is True
    assert "�" not in "".join(line["text"] for line in result["lines"])


def test_xml_plist_is_parsed(tmp_path):
    """LaunchAgents/LaunchDaemons are XML; they must parse the same way."""
    p = tmp_path / "com.example.agent.plist"
    payload = {"Label": "com.example.agent", "ProgramArguments": ["/bin/echo", "hi"]}
    p.write_bytes(plistlib.dumps(payload, fmt=plistlib.FMT_XML))

    result = parse(str(p))
    assert result["kind"] == "plist"
    assert result["tree"]["ProgramArguments"] == ["/bin/echo", "hi"]


def test_plists_with_different_content_hash_differently(tmp_path):
    """Hash must be computed over parsed content, so it is real and stable.

    Two plists with different content must hash differently — proving the
    hash is not being taken over identical U+FFFD replacement soup.
    """
    a = tmp_path / "a.plist"
    b = tmp_path / "b.plist"
    a.write_bytes(plistlib.dumps({"Label": "alpha"}, fmt=plistlib.FMT_BINARY))
    b.write_bytes(plistlib.dumps({"Label": "beta"}, fmt=plistlib.FMT_BINARY))
    assert parse(str(a))["hash"] != parse(str(b))["hash"]


def test_unreadable_plist_falls_back_to_text(tmp_path):
    """A corrupt or non-plist file named .plist must not raise."""
    p = tmp_path / "broken.plist"
    p.write_bytes(b"this is not a plist at all")
    result = parse(str(p))
    assert result["kind"] == "text"
