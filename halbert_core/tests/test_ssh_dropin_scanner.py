# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""sshd_config.d drop-in conflict scanner tests (F7 / ATTN-1 proof slice).

Tests mock at the filesystem boundary: a synthetic ``/etc`` tree is built
under ``tmp_path`` and the scanner is pointed at it via its
``config_dir`` constructor argument — the same fixture pattern as
``test_precedence.py``. ``is_available()``/``scan()`` are exercised
through the SSH path only; the other sub-scans are not asserted on.
"""
from __future__ import annotations

import os
from pathlib import Path

from halbert_core.discovery.schema import (
    DiscoverySeverity,
    DiscoveryType,
)
from halbert_core.discovery.scanners.security import SecurityScanner


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _scanner_for(config_dir: Path) -> SecurityScanner:
    return SecurityScanner(config_dir=str(config_dir))


def _ssh_config(config_dir: Path) -> Path:
    return config_dir / "ssh" / "sshd_config"


def _dropin_dir(config_dir: Path) -> Path:
    return config_dir / "ssh" / "sshd_config.d"


def _ssh_findings(config_dir: Path) -> list:
    """Run the scanner and return only the SSH-derived discoveries."""
    scanner = _scanner_for(config_dir)
    return [d for d in scanner.scan() if d.type == DiscoveryType.SECURITY
            and d.name.startswith("ssh")]


def _conflict_of(discoveries: list, directive: str):
    name = f"ssh-dropin-conflict-{directive}"
    for d in discoveries:
        if d.name == name:
            return d
    return None


class TestSshConfigOnly:
    """Hosts with no sshd_config.d directory keep the existing behaviour."""

    def test_no_sshd_config_no_discoveries(self, tmp_path):
        assert _ssh_findings(tmp_path) == []

    def test_main_file_only(self, tmp_path):
        _write(_ssh_config(tmp_path), (
            "Port 22\n"
            "PermitRootLogin no\n"
            "PasswordAuthentication no\n"
            "PubkeyAuthentication yes\n"
        ))

        findings = _ssh_findings(tmp_path)
        assert len(findings) == 1
        assert findings[0].name == "ssh-config"
        assert findings[0].severity == DiscoverySeverity.SUCCESS
        assert findings[0].data["root_login"] == "no"
        assert findings[0].data["password_auth"] == "no"
        assert findings[0].data["pubkey_auth"] == "yes"
        assert findings[0].data["dropins"] == []
        assert not any(f.name.startswith("ssh-dropin-conflict") for f in findings)

    def test_main_file_defaults_when_uncommented_line_absent(self, tmp_path):
        # All-commented sshd_config — the built-in defaults apply.
        _write(_ssh_config(tmp_path), (
            "# This file is managed by the system.\n"
            "# PermitRootLogin prohibit-password\n"
            "#PasswordAuthentication yes\n"
        ))

        findings = _ssh_findings(tmp_path)
        assert len(findings) == 1
        assert findings[0].data["root_login"] == "prohibit-password"
        assert findings[0].data["password_auth"] == "yes"

    def test_main_file_first_match_wins(self, tmp_path):
        # OpenSSH is first-match-wins within a file: the base file says
        # 'no' at line 2, 'yes' at line 3 — effective is 'no'.
        _write(_ssh_config(tmp_path), (
            "Port 22\n"
            "PermitRootLogin no\n"
            "PermitRootLogin yes\n"
        ))

        findings = _ssh_findings(tmp_path)
        assert findings[0].data["root_login"] == "no"

    def test_no_include_fallback_dropin_overrides_base(self, tmp_path):
        # No Include directive in the base file: the engine's documented
        # fallback appends drop-ins after the base, where they override it.
        _write(_ssh_config(tmp_path), "PermitRootLogin no\n")
        _write(_dropin_dir(tmp_path) / "50-cloud.conf", "PermitRootLogin yes\n")

        findings = _ssh_findings(tmp_path)
        base = next(f for f in findings if f.name == "ssh-config")
        conflict = _conflict_of(findings, "PermitRootLogin")

        # Effective value accounts for the drop-in
        assert base.data["root_login"] == "yes"
        assert base.severity == DiscoverySeverity.WARNING
        # PasswordAuthentication is unset: the built-in default 'yes'
        # is still an issue alongside the drop-in-enabled root login.
        assert base.data["issues"] == ["Root login enabled", "Password auth enabled"]
        # Conflict discovery cites the exact drop-in path and line
        assert conflict is not None
        assert conflict.severity == DiscoverySeverity.WARNING
        assert f"{_dropin_dir(tmp_path) / '50-cloud.conf'}:1" in conflict.description
        assert "Effective value is 'yes'" in conflict.description
        assert "across sshd_config and a drop-in" in conflict.description


class TestIncludeAwareResolution:
    """Modern distro layout: Include at top, drop-in wins first-match."""

    def test_include_at_top_dropin_effective_and_conflict_cited(self, tmp_path):
        _write(_ssh_config(tmp_path), (
            f"Include {tmp_path}/ssh/sshd_config.d/*.conf\n"
            "\n"
            "# comments between\n"
            "PermitRootLogin no\n"
            "PasswordAuthentication no\n"
            "PubkeyAuthentication yes\n"
        ))
        # Line 12 of the drop-in, matching the plate's cited line
        pad = "\n".join("# padding line" for _ in range(11))
        _write(_dropin_dir(tmp_path) / "50-cloud.conf", f"{pad}\nPermitRootLogin yes\n")

        findings = _ssh_findings(tmp_path)
        base = next(f for f in findings if f.name == "ssh-config")
        conflict = _conflict_of(findings, "PermitRootLogin")

        assert base.data["root_login"] == "yes"
        assert base.severity == DiscoverySeverity.WARNING
        assert conflict is not None
        assert conflict.id == "security/ssh-dropin-conflict-permitrootlogin"
        assert conflict.title == "sshd config conflict: PermitRootLogin"
        assert "Effective value is 'yes'" in conflict.description
        assert f"{_dropin_dir(tmp_path) / '50-cloud.conf'}:12" in conflict.description
        assert conflict.data["effective_source"] == (
            f"{_dropin_dir(tmp_path) / '50-cloud.conf'}:12"
        )
        assert conflict.data["effective_value"] == "yes"
        assert sorted(conflict.data["affected_paths"]) == [
            str(_ssh_config(tmp_path)),
            str(_dropin_dir(tmp_path) / "50-cloud.conf"),
        ]
        assert conflict.related_to == ["security/ssh-config"]
        assert "first-match-wins" in conflict.chat_context

    def test_matching_value_no_conflict(self, tmp_path):
        # Drop-in sets the same value as the base — no conflict discovery.
        _write(_ssh_config(tmp_path), (
            f"Include {tmp_path}/ssh/sshd_config.d/*.conf\n"
            "PermitRootLogin no\n"
        ))
        _write(_dropin_dir(tmp_path) / "10.conf", "PermitRootLogin no\n")

        findings = _ssh_findings(tmp_path)
        assert not any(f.name.startswith("ssh-dropin-conflict") for f in findings)
        assert next(f for f in findings if f.name == "ssh-config").data["root_login"] == "no"

    def test_base_empty_include_fallback_to_dropin_values(self, tmp_path):
        # Distro default with everything commented: only the drop-in
        # speaks, and it is the effective value.
        _write(_ssh_config(tmp_path), (
            f"Include {tmp_path}/ssh/sshd_config.d/*.conf\n"
            "# PermitRootLogin prohibit-password\n"
        ))
        _write(_dropin_dir(tmp_path) / "60-hardening.conf",
               "PasswordAuthentication no\nPubkeyAuthentication yes\n")

        findings = _ssh_findings(tmp_path)
        base = next(f for f in findings if f.name == "ssh-config")
        assert base.data["password_auth"] == "no"
        assert base.data["pubkey_auth"] == "yes"
        assert base.data["dropins"] == [str(_dropin_dir(tmp_path) / "60-hardening.conf")]
        assert not any(f.name.startswith("ssh-dropin-conflict") for f in findings)

    def test_password_auth_conflict_emitted(self, tmp_path):
        _write(_ssh_config(tmp_path), (
            f"Include {tmp_path}/ssh/sshd_config.d/*.conf\n"
            "PasswordAuthentication no\n"
        ))
        _write(_dropin_dir(tmp_path) / "20-relaxed.conf",
               "PasswordAuthentication yes\n")

        findings = _ssh_findings(tmp_path)
        conflict = _conflict_of(findings, "PasswordAuthentication")
        assert conflict is not None
        assert "Effective value is 'yes'" in conflict.description
        assert "across sshd_config and a drop-in" in conflict.description

    def test_two_dropins_conflict_wording_names_dropins(self, tmp_path):
        # Conflict between two drop-ins (base never sets the directive):
        # the wording must not claim the main file is involved.
        _write(_ssh_config(tmp_path), (
            f"Include {tmp_path}/ssh/sshd_config.d/*.conf\n"
            "# no directive here\n"
        ))
        _write(_dropin_dir(tmp_path) / "10-a.conf", "PubkeyAuthentication yes\n")
        _write(_dropin_dir(tmp_path) / "50-b.conf", "PubkeyAuthentication no\n")

        findings = _ssh_findings(tmp_path)
        conflict = _conflict_of(findings, "PubkeyAuthentication")
        assert conflict is not None
        assert "across drop-in files" in conflict.description
        assert "across sshd_config and a drop-in" not in conflict.description

    def test_two_dropins_effective_from_first_file(self, tmp_path):
        # Two drop-ins disagree: first file in alphabetical order wins.
        _write(_ssh_config(tmp_path),
               f"Include {tmp_path}/ssh/sshd_config.d/*.conf\n")
        _write(_dropin_dir(tmp_path) / "10-a.conf", "PermitRootLogin no\n")
        _write(_dropin_dir(tmp_path) / "50-b.conf", "PermitRootLogin yes\n")

        findings = _ssh_findings(tmp_path)
        base = next(f for f in findings if f.name == "ssh-config")
        conflict = _conflict_of(findings, "PermitRootLogin")
        assert base.data["root_login"] == "no"
        assert conflict.data["effective_source"] == (
            f"{_dropin_dir(tmp_path) / '10-a.conf'}:1"
        )

    def test_non_conf_file_in_dropin_dir_ignored(self, tmp_path):
        # Only *.conf files are drop-ins; a stray README is not.
        _write(_ssh_config(tmp_path),
               "Include /etc/ssh/sshd_config.d/*.conf\nPermitRootLogin no\n")
        _write(_dropin_dir(tmp_path) / "README", "PermitRootLogin yes\n")
        _write(_dropin_dir(tmp_path) / "50-real.conf", "PermitRootLogin no\n")

        findings = _ssh_findings(tmp_path)
        assert not any(f.name.startswith("ssh-dropin-conflict") for f in findings)
        assert next(f for f in findings if f.name == "ssh-config").data["dropins"] == [
            str(_dropin_dir(tmp_path) / "50-real.conf")
        ]

    def test_untracked_directive_conflict_not_emitted_by_scanner(self, tmp_path):
        # The scanner emits conflict discoveries only for the settings it
        # tracks; other directives stay on the findings plane
        # (DropinConflictDetector) — no Port discovery appears here.
        _write(_ssh_config(tmp_path), (
            f"Include {tmp_path}/ssh/sshd_config.d/*.conf\n"
            "Port 22\n"
        ))
        _write(_dropin_dir(tmp_path) / "10.conf", "Port 2222\n")

        findings = _ssh_findings(tmp_path)
        assert not any(f.name.startswith("ssh-dropin-conflict") for f in findings)


class TestSanitization:
    """Config text is untrusted; citations survive sanitization intact."""

    def test_long_tmp_path_citation_not_truncated(self, tmp_path):
        # Sanitized citations keep the full path even under a long
        # tmp_path fixture root (larger cap for paths).
        _write(_ssh_config(tmp_path), (
            f"Include {tmp_path}/ssh/sshd_config.d/*.conf\n"
            "PermitRootLogin no\n"
        ))
        _write(_dropin_dir(tmp_path) / "50-cloud.conf", "PermitRootLogin yes\n")

        findings = _ssh_findings(tmp_path)
        conflict = _conflict_of(findings, "PermitRootLogin")
        assert f"{_dropin_dir(tmp_path) / '50-cloud.conf'}:1" in conflict.description

    def test_hostile_value_is_scrubbed(self, tmp_path):
        # A planted value with control characters / brackets cannot
        # break out of the citation shape or pose as prompt structure.
        _write(_ssh_config(tmp_path), (
            f"Include {tmp_path}/ssh/sshd_config.d/*.conf\n"
            "PermitRootLogin no\n"
        ))
        _write(_dropin_dir(tmp_path) / "50-evil.conf",
               "PermitRootLogin yes<evil>\n")

        findings = _ssh_findings(tmp_path)
        conflict = _conflict_of(findings, "PermitRootLogin")
        assert conflict is not None
        assert "<" not in conflict.description
        assert ">" not in conflict.description
        assert "\n" not in conflict.description


class TestEffectiveValuePropagation:
    """The ssh-config discovery reflects the effective (post-drop-in) state."""

    def test_dropin_hardens_base_issue_disappears(self, tmp_path):
        # Base enables password auth; a drop-in turns it off. The
        # effective state is secure — no issue, no warning.
        _write(_ssh_config(tmp_path), (
            f"Include {tmp_path}/ssh/sshd_config.d/*.conf\n"
            "PasswordAuthentication yes\n"
        ))
        _write(_dropin_dir(tmp_path) / "10-hardening.conf",
               "PasswordAuthentication no\n")

        findings = _ssh_findings(tmp_path)
        base = next(f for f in findings if f.name == "ssh-config")
        conflict = _conflict_of(findings, "PasswordAuthentication")
        assert base.severity == DiscoverySeverity.SUCCESS
        assert base.data["issues"] == []
        assert conflict is not None
        assert conflict.severity == DiscoverySeverity.WARNING

    def test_dropin_hardening_conflict_discovery_has_actions_and_source(self, tmp_path):
        _write(_ssh_config(tmp_path), (
            f"Include {tmp_path}/ssh/sshd_config.d/*.conf\n"
            "PermitRootLogin prohibit-password\n"
        ))
        _write(_dropin_dir(tmp_path) / "50-cloud.conf", "PermitRootLogin yes\n")

        findings = _ssh_findings(tmp_path)
        conflict = _conflict_of(findings, "PermitRootLogin")
        assert [a.id for a in conflict.actions] == ["details", "chat"]
        assert conflict.source == str(_dropin_dir(tmp_path) / "50-cloud.conf")
        assert conflict.status == "Drop-in override"
        assert conflict.type == DiscoveryType.SECURITY


class TestEmptyDropinDirectory:
    def test_empty_dir_no_change_from_main_only(self, tmp_path):
        # An empty sshd_config.d exists: behaviour identical to no dir.
        _write(_ssh_config(tmp_path), (
            f"Include {tmp_path}/ssh/sshd_config.d/*.conf\n"
            "PermitRootLogin no\n"
            "PasswordAuthentication no\n"
        ))
        _dropin_dir(tmp_path).mkdir(parents=True)

        findings = _ssh_findings(tmp_path)
        assert len(findings) == 1
        assert findings[0].name == "ssh-config"
        assert findings[0].data["dropins"] == []
        assert findings[0].severity == DiscoverySeverity.SUCCESS