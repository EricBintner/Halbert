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
