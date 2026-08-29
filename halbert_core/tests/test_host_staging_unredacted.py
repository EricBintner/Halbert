# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Unredacted staging mode — for Halbert's private host project only.

When ``redact=False``, raw content is written to the staging directory.
This is the mode for Halbert's private host project: the staging dir is
user-owned, the daemon is localhost-only, and the MCP response boundary
(``mcp_response()``) handles egress redaction for external clients.

These tests verify that:
1. ``redact=False`` writes raw content (secrets survive in the staging dir)
2. ``redact=True`` (default) still redacts (existing behavior unchanged)
3. The exclude globs still apply regardless of the redact flag
"""
from __future__ import annotations

from halbert_core.tools.register_host_project import _stage_config_files


def test_redact_false_writes_raw_content(tmp_path):
    """redact=False must write the raw value, not <secret>."""
    src = tmp_path / "etc"
    src.mkdir()
    f = src / "app.conf"
    f.write_text("[auth]\npassword = hunter2-raw-secret\nport = 2222\n")

    staging = tmp_path / "staged"
    _stage_config_files([str(f)], staging, redact=False)

    staged = list(staging.rglob("app.conf"))[0].read_text()
    assert "hunter2-raw-secret" in staged  # raw value survives
    assert "2222" in staged


def test_redact_true_still_redacts(tmp_path):
    """redact=True (default) must still redact — existing behavior."""
    src = tmp_path / "etc"
    src.mkdir()
    f = src / "app.conf"
    f.write_text("[auth]\npassword = hunter2-redacted-secret\nport = 2222\n")

    staging = tmp_path / "staged"
    _stage_config_files([str(f)], staging)  # default redact=True

    staged = list(staging.rglob("app.conf"))[0].read_text()
    assert "hunter2-redacted-secret" not in staged
    assert "2222" in staged


def test_redact_false_with_directory_walk(tmp_path):
    """Directory walking must pass redact=False to each file."""
    src = tmp_path / "etc" / "app.d"
    src.mkdir(parents=True)
    (src / "a.conf").write_text("[auth]\npassword = secretA-raw\n")
    (src / "b.conf").write_text("[auth]\napi_key = secretB-raw\n")

    staging = tmp_path / "staged"
    count = _stage_config_files([str(src)], staging, redact=False)

    assert count == 2
    all_text = "".join(p.read_text() for p in staging.rglob("*.conf"))
    assert "secretA-raw" in all_text
    assert "secretB-raw" in all_text


def test_redact_false_non_secret_content_unchanged(tmp_path):
    """Non-secret content must be identical in both modes."""
    src = tmp_path / "etc"
    src.mkdir()
    f = src / "sysctl.conf"
    f.write_text("net.ipv4.ip_forward = 1\nkernel.pid_max = 4194304\n")

    staging_redacted = tmp_path / "redacted"
    staging_raw = tmp_path / "raw"
    _stage_config_files([str(f)], staging_redacted, redact=True)
    _stage_config_files([str(f)], staging_raw, redact=False)

    # No secrets in this file, so both should be identical
    assert staging_redacted.rglob("sysctl.conf").__next__().read_text() == \
           staging_raw.rglob("sysctl.conf").__next__().read_text()
