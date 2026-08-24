"""
Permissions hygiene detector.

Checks file and directory permissions for common security violations:
- ~/.ssh/ directory and private key permissions
- World-readable files in /etc/ that may contain secrets

Phase 5 / T5c.3.
"""

from __future__ import annotations

import logging
import os
import stat
from typing import Dict, List

from ..store import Finding

logger = logging.getLogger(__name__)


def _file_mode(path: str) -> int:
    """Get the permission bits of a file."""
    try:
        return os.stat(path).st_mode & 0o777
    except OSError:
        return -1


def _is_world_readable(mode: int) -> bool:
    return bool(mode & stat.S_IROTH)


def _is_group_readable(mode: int) -> bool:
    return bool(mode & stat.S_IRGRP)


class PermissionsHygieneDetector:
    """Detect permission violations on sensitive files."""

    def __init__(self, home_dir: str | None = None, etc_dir: str = "/etc"):
        self.home_dir = home_dir or os.path.expanduser("~")
        self.etc_dir = etc_dir

    def detect(self) -> List[Finding]:
        """Run detection and return a list of findings."""
        findings: List[Finding] = []
        findings.extend(self._check_ssh_permissions())
        findings.extend(self._check_etc_secrets())
        return findings

    def _check_ssh_permissions(self) -> List[Finding]:
        """Check ~/.ssh/ directory and file permissions."""
        findings: List[Finding] = []
        ssh_dir = os.path.join(self.home_dir, ".ssh")

        if not os.path.isdir(ssh_dir):
            return findings

        # Directory should be 700
        mode = _file_mode(ssh_dir)
        if mode != -1 and mode != 0o700:
            severity = "critical" if _is_world_readable(mode) else "warning"
            findings.append(Finding(
                id="",
                detector="permissions_hygiene",
                severity=severity,
                title=f"~/.ssh/ has insecure permissions ({oct(mode)})",
                description=(
                    f"The ~/.ssh/ directory has mode {oct(mode)}. "
                    f"It should be 700 (owner only)."
                ),
                why_now="Permission scan detected insecure mode on ~/.ssh/.",
                why_care=(
                    "Other users on the system can read or traverse the .ssh "
                    "directory, potentially exposing private keys or "
                    "authorized_keys files."
                ),
                why_so=(
                    f"Directory {ssh_dir} has mode {oct(mode)}, but SSH "
                    f"requires 700 for the .ssh directory."
                ),
                why_trust=[ssh_dir],
                affected_paths=[ssh_dir],
                affected_services=["ssh"],
            ))

        # Check specific files. config accepts 600 or 644 (it contains no
        # key material, so world-readable is acceptable — anything more
        # permissive on the write bits or with unexpected group/other
        # access is flagged).
        sensitive_files: Dict[str, tuple] = {
            "id_rsa": (0o600,),
            "id_ed25519": (0o600,),
            "id_ecdsa": (0o600,),
            "id_dsa": (0o600,),
            "authorized_keys": (0o600,),
            "config": (0o600, 0o644),
        }

        for fname, accepted_modes in sensitive_files.items():
            fpath = os.path.join(ssh_dir, fname)
            if not os.path.isfile(fpath):
                continue
            mode = _file_mode(fpath)
            if mode == -1:
                continue

            if mode in accepted_modes:
                continue

            # Private keys must be 600
            if fname.startswith("id_"):
                severity = "critical" if _is_world_readable(mode) else "warning"
                findings.append(Finding(
                    id="",
                    detector="permissions_hygiene",
                    severity=severity,
                    title=f"{fname} has insecure permissions ({oct(mode)})",
                    description=(
                        f"SSH private key {fname} has mode {oct(mode)}. "
                        f"It should be 600 (owner read/write only)."
                    ),
                    why_now="Permission scan detected insecure mode on SSH private key.",
                    why_care=(
                        "Other users can read your private key, allowing them "
                        "to impersonate you on any system that accepts that key. "
                        "SSH may also refuse to use the key."
                    ),
                    why_so=(
                        f"File {fpath} has mode {oct(mode)}, but SSH private "
                        f"keys must be 600."
                    ),
                    why_trust=[fpath],
                    affected_paths=[fpath],
                    affected_services=["ssh"],
                ))

            # authorized_keys should be 600
            elif fname == "authorized_keys":
                severity = "warning" if not _is_world_readable(mode) else "critical"
                findings.append(Finding(
                    id="",
                    detector="permissions_hygiene",
                    severity=severity,
                    title=f"authorized_keys has insecure permissions ({oct(mode)})",
                    description=(
                        f"authorized_keys has mode {oct(mode)}. "
                        f"It should be 600 (owner read/write only)."
                    ),
                    why_now="Permission scan detected insecure mode on authorized_keys.",
                    why_care=(
                        "Other users can read or modify your authorized_keys, "
                        "potentially adding their own keys for access to your account."
                    ),
                    why_so=(
                        f"File {fpath} has mode {oct(mode)}, but authorized_keys "
                        f"should be 600."
                    ),
                    why_trust=[fpath],
                    affected_paths=[fpath],
                    affected_services=["ssh"],
                ))

            # config accepts 600 or 644; anything else is flagged
            elif fname == "config":
                findings.append(Finding(
                    id="",
                    detector="permissions_hygiene",
                    severity="warning",
                    title=f"~/.ssh/config has unexpected permissions ({oct(mode)})",
                    description=(
                        f"SSH client config {fpath} has mode {oct(mode)}. "
                        f"It should be 600 or 644."
                    ),
                    why_now="Permission scan detected unexpected mode on ~/.ssh/config.",
                    why_care=(
                        "Overly permissive or inconsistent modes on the SSH "
                        "client config can allow tampering with host aliases "
                        "and connection settings, or cause SSH to complain."
                    ),
                    why_so=(
                        f"File {fpath} has mode {oct(mode)}, but ~/.ssh/config "
                        f"should be 600 or 644."
                    ),
                    why_trust=[fpath],
                    affected_paths=[fpath],
                    affected_services=["ssh"],
                ))

        return findings

    def _check_etc_secrets(self) -> List[Finding]:
        """Check for world-readable files in /etc/ that may contain secrets."""
        findings: List[Finding] = []

        if not os.path.isdir(self.etc_dir):
            return findings

        # Patterns that suggest secret-containing files
        secret_patterns = (
            "key", "secret", "password", "passwd", "credential",
            ".pem", ".key", ".crt", "token", "auth",
        )

        # Files to explicitly skip (not secrets despite matching patterns)
        skip_files = {
            "keymaps", "keyutils.conf", "passwd-", "group-",
            "passwd", "group", "shadow", "gshadow",  # standard Unix files
            "passwd~orig", "group~orig",
        }

        try:
            for fname in os.listdir(self.etc_dir):
                if fname in skip_files:
                    continue
                if not any(p in fname.lower() for p in secret_patterns):
                    continue

                fpath = os.path.join(self.etc_dir, fname)
                if not os.path.isfile(fpath):
                    continue

                mode = _file_mode(fpath)
                if mode == -1:
                    continue

                # World-readable secret files are a problem
                if _is_world_readable(mode) and (mode & stat.S_IWOTH):
                    # World-writable is critical
                    severity = "critical"
                elif _is_world_readable(mode):
                    severity = "warning"
                else:
                    continue

                findings.append(Finding(
                    id="",
                    detector="permissions_hygiene",
                    severity=severity,
                    title=f"{fname} is world-readable ({oct(mode)})",
                    description=(
                        f"File {fpath} may contain secrets and has mode "
                        f"{oct(mode)} (world-readable)."
                    ),
                    why_now=(
                        f"Permission scan found {fname} matching secret file "
                        f"patterns with world-readable permissions."
                    ),
                    why_care=(
                        "Any user on the system can read this file, potentially "
                        "exposing credentials, API keys, or other secrets."
                    ),
                    why_so=(
                        f"File {fpath} has mode {oct(mode)}, and the filename "
                        f"matches secret file patterns ({secret_patterns})."
                    ),
                    why_trust=[fpath],
                    affected_paths=[fpath],
                    affected_services=[],
                ))
        except OSError as e:
            logger.warning(f"Cannot scan {self.etc_dir}: {e}")

        return findings
