# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Command injection / danger check for PTY commands (B1d).

A superset of the existing ``dashboard/routes/terminal.py`` safety checks.
The existing ``check_command_safety`` stays; this layer adds patterns the
agent might emit that the route-level check doesn't cover (remote-script
piping, ``eval``/``exec``, command substitution, ZFS/LVM/network
destruction, escalation shells) and a ``uses_elevation`` helper.

Severity ordering: BLOCKED > DANGEROUS > ELEVATION/CAUTION. Callers (B1e)
combine this with the existing ``check_command_safety`` and the ``Sandbox``
wrapper before spawning a PTY. See OPUS-HANDOFF §B1d.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import List


class InjectionSeverity(Enum):
    """Severity of an injection/danger finding."""
    BLOCKED = "blocked"        # never execute
    DANGEROUS = "dangerous"    # require explicit confirmation
    ELEVATION = "elevation"    # privilege escalation present
    CAUTION = "caution"        # show warning but allow


# Severity rank for "worst finding" comparison (higher = worse)
_SEVERITY_RANK = {
    InjectionSeverity.BLOCKED: 4,
    InjectionSeverity.DANGEROUS: 3,
    InjectionSeverity.ELEVATION: 2,
    InjectionSeverity.CAUTION: 1,
}


@dataclass
class InjectionFinding:
    severity: InjectionSeverity
    pattern: str
    reason: str


# (regex, reason, severity) — order matters only for reporting; the worst
# severity is what callers act on.
_PATTERNS = [
    # --- Blocked: never execute ---
    (r"rm\s+-rf\s+/(\s|$|\*)", "Recursive forced delete of root", InjectionSeverity.BLOCKED),
    # rm with any combination of -r/-R/-f flags, split or joined, targeting / or /*
    (r"\brm\s+(?:-\w*[rfRF]\w*\s+)+/\*?(?=\s|$)", "Recursive/forced delete of root (flags reordered or split)", InjectionSeverity.BLOCKED),
    (r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;:", "Fork bomb", InjectionSeverity.BLOCKED),
    (r"mkfs\.", "Filesystem format — erases all data on target", InjectionSeverity.BLOCKED),
    (r">\s*/dev/(sd|nvme|disk)", "Direct write to raw disk device", InjectionSeverity.BLOCKED),
    # dd writing to a block device, regardless of operand order
    (r"\bdd\b[^|;&]*?\bof=/dev/(?:sd|nvme|disk)", "Direct write to raw disk device via dd of=", InjectionSeverity.BLOCKED),
    (r"zpool\s+destroy", "ZFS pool destruction — irreversible data loss", InjectionSeverity.BLOCKED),
    # --- Dangerous: require explicit confirmation ---
    (r"dd\s+if=", "Direct disk read/write — can destroy data", InjectionSeverity.DANGEROUS),
    (r"chmod\s+-R\s+777\s+/", "Recursive world-writable on root filesystem", InjectionSeverity.DANGEROUS),
    (r"curl\s+[^|]*\|\s*(?:bash|sh|zsh|csh|python[0-9.]*|perl|ruby|node)\b", "Piping a remote script into a shell or interpreter", InjectionSeverity.DANGEROUS),
    (r"wget\s+[^|]*\|\s*(?:bash|sh|zsh|csh|python[0-9.]*|perl|ruby|node)\b", "Piping a remote script into a shell or interpreter", InjectionSeverity.DANGEROUS),
    (r"\beval\s+", "eval executes arbitrary code from a string", InjectionSeverity.DANGEROUS),
    (r"\blvremove\b", "LVM logical volume removal", InjectionSeverity.DANGEROUS),
    (r"\bip\s+link\s+delete", "Network interface deletion", InjectionSeverity.DANGEROUS),
    (r"`[^`]+`", "Backtick command substitution (injection vector)", InjectionSeverity.DANGEROUS),
    (r"\$\([^)]+\)", "$(...) command substitution (injection vector)", InjectionSeverity.DANGEROUS),
    # --- Caution ---
    (r"\bexec\s+", "exec replaces the shell process", InjectionSeverity.CAUTION),
    # --- Elevation ---
    (r"\bsudo\s+su\b", "Escalation to a root shell via sudo su", InjectionSeverity.ELEVATION),
    (r"\bsudo\s+-i\b", "Interactive root shell via sudo -i", InjectionSeverity.ELEVATION),
]

_COMPILED = [(re.compile(p), reason, sev) for p, reason, sev in _PATTERNS]

# Privilege-elevation tokens (word-bounded so 'su' doesn't match 'result')
_ELEVATION_RE = re.compile(r"\b(?:sudo|su|doas)\b")


def check_injection(command: str) -> List[InjectionFinding]:
    """Return all injection/danger findings for ``command`` (may be empty).

    Findings are returned in pattern order; use ``worst_severity`` to get the
    single most-severe finding for a decision.
    """
    if not command:
        return []
    findings: List[InjectionFinding] = []
    for regex, reason, sev in _COMPILED:
        if regex.search(command):
            findings.append(InjectionFinding(severity=sev, pattern=regex.pattern, reason=reason))
    return findings


def worst_severity(findings: List[InjectionFinding]) -> InjectionSeverity | None:
    """Return the highest-severity finding, or None if empty."""
    if not findings:
        return None
    return max(findings, key=lambda f: _SEVERITY_RANK[f.severity]).severity


def is_blocked(command: str) -> bool:
    """True if any BLOCKED-severity pattern matches."""
    return any(f.severity is InjectionSeverity.BLOCKED for f in check_injection(command))


def uses_elevation(command: str) -> bool:
    """True if the command uses a privilege-escalation token (sudo/su/doas)."""
    if not command:
        return False
    return bool(_ELEVATION_RE.search(command))


def has_dangerous_substitution(command: str) -> bool:
    """True if the command contains backtick or $(...) command substitution."""
    return any(
        f.reason.startswith("Backtick") or f.reason.startswith("$(...")
        for f in check_injection(command)
    )
