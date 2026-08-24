"""
Precedence resolution engine for host configuration.

Resolves the effective configuration for services that support drop-in
files (sshd_config.d/, systemd unit .d/ directories). Later files
override earlier ones; within a single file, last directive wins.

Phase 5 / T5d.1.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from ..config.parser import parse as parse_config

logger = logging.getLogger(__name__)


def _parse_sshd_directives(path: str) -> List[Tuple[int, str, str]]:
    """Parse sshd_config-style file into a list of (line_no, key, value) tuples.

    sshd_config uses `Key Value` syntax (space-separated, not `=`).
    Comments start with `#`. Includes (`Include`) are expanded.
    """
    directives: List[Tuple[int, str, str]] = []
    if not os.path.isfile(path):
        return directives

    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f, 1):
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                # sshd_config: `Key Value` (space or tab separated)
                parts = re.split(r"[\s=]+", stripped, maxsplit=1)
                if len(parts) >= 2:
                    directives.append((i, parts[0].lower(), parts[1].strip()))
                elif len(parts) == 1:
                    directives.append((i, parts[0].lower(), ""))
    except OSError as e:
        logger.warning(f"Cannot read {path}: {e}")
    return directives


def _parse_systemd_directives(path: str) -> List[Tuple[int, str, str]]:
    """Parse a systemd unit file into a list of (line_no, key, value) tuples.

    systemd uses `Key=Value` syntax. Comments start with `#` or `;`.
    Sections are denoted by [SectionName]. Directives are returned with
    their section prefixed: `Section/Key`.
    """
    directives: List[Tuple[int, str, str]] = []
    if not os.path.isfile(path):
        return directives

    current_section = ""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f, 1):
                stripped = line.strip()
                if not stripped or stripped.startswith(("#", ";")):
                    continue
                if stripped.startswith("[") and stripped.endswith("]"):
                    current_section = stripped[1:-1]
                    continue
                if "=" in stripped:
                    key, _, value = stripped.partition("=")
                    full_key = f"{current_section}/{key.strip().lower()}" if current_section else key.strip().lower()
                    directives.append((i, full_key, value.strip()))
    except OSError as e:
        logger.warning(f"Cannot read {path}: {e}")
    return directives


class PrecedenceEngine:
    """Resolve effective configuration for services with drop-in support.

    Handles:
    - sshd_config + /etc/ssh/sshd_config.d/*.conf (alphabetical, later wins)
    - systemd units + /etc/systemd/system/<unit>.d/*.conf (drop-ins override base)
    """

    def __init__(self, config_dir: str = "/etc"):
        self.config_dir = config_dir
        self.sshd_base = os.path.join(config_dir, "ssh", "sshd_config")
        self.sshd_dropin_dir = os.path.join(config_dir, "ssh", "sshd_config.d")
        self.systemd_dir = os.path.join(config_dir, "systemd", "system")

    def resolve_sshd(self) -> Dict[str, Any]:
        """Resolve effective sshd configuration.

        Reads the base sshd_config and all drop-in files in
        sshd_config.d/ in alphabetical order. Later files override
        earlier ones. Returns a dict with:
          - effective: dict of key -> value (last wins)
          - sources: dict of key -> (file_path, line_no) for provenance
          - conflicts: list of dicts describing conflicting directives
        """
        all_directives: List[Tuple[str, int, str, str]] = []  # (file, line, key, value)

        # Base file
        for line_no, key, value in _parse_sshd_directives(self.sshd_base):
            all_directives.append((self.sshd_base, line_no, key, value))

        # Drop-in files (alphabetical)
        if os.path.isdir(self.sshd_dropin_dir):
            for fname in sorted(os.listdir(self.sshd_dropin_dir)):
                if fname.endswith(".conf"):
                    fpath = os.path.join(self.sshd_dropin_dir, fname)
                    for line_no, key, value in _parse_sshd_directives(fpath):
                        all_directives.append((fpath, line_no, key, value))

        # Build effective config (last wins)
        effective: Dict[str, str] = {}
        sources: Dict[str, Tuple[str, int]] = {}
        # Track all values per key for conflict detection
        all_values: Dict[str, List[Tuple[str, int, str]]] = {}

        for fpath, line_no, key, value in all_directives:
            effective[key] = value
            sources[key] = (fpath, line_no)
            all_values.setdefault(key, []).append((fpath, line_no, value))

        # Detect conflicts (same key, different values across files)
        conflicts: List[Dict[str, Any]] = []
        for key, entries in all_values.items():
            if len(entries) > 1:
                unique_vals = set(v for _, _, v in entries)
                if len(unique_vals) > 1:
                    conflicts.append({
                        "key": key,
                        "values": [
                            {"file": f, "line": l, "value": v}
                            for f, l, v in entries
                        ],
                        "effective": effective[key],
                        "effective_source": sources[key],
                    })

        return {
            "effective": effective,
            "sources": sources,
            "conflicts": conflicts,
        }

    def resolve_systemd_unit(self, unit_name: str) -> Dict[str, Any]:
        """Resolve effective systemd unit configuration.

        Reads the base unit file and all drop-ins in <unit>.d/
        directories. Drop-ins override base; within drop-ins, alphabetical
        order applies. Returns the same structure as resolve_sshd().
        """
        # Find the base unit file
        base_path: Optional[str] = None
        for ext in (".service", ".mount", ".timer", ".socket", ".target"):
            candidate = os.path.join(self.systemd_dir, unit_name + ext)
            if os.path.isfile(candidate):
                base_path = candidate
                break
            # Also check /usr/lib/systemd/system
            candidate2 = os.path.join("/usr/lib/systemd/system", unit_name + ext)
            if os.path.isfile(candidate2):
                base_path = candidate2
                break

        all_directives: List[Tuple[str, int, str, str]] = []

        if base_path:
            for line_no, key, value in _parse_systemd_directives(base_path):
                all_directives.append((base_path, line_no, key, value))

        # Drop-in directories
        # systemd supports <unit>.<ext>.d/ and <unit>.d/
        dropin_dirs: List[str] = []
        for ext in (".service", ".mount", ".timer", ".socket", ".target"):
            d = os.path.join(self.systemd_dir, unit_name + ext + ".d")
            if os.path.isdir(d):
                dropin_dirs.append(d)
        d2 = os.path.join(self.systemd_dir, unit_name + ".d")
        if os.path.isdir(d2):
            dropin_dirs.append(d2)

        for ddir in sorted(dropin_dirs):
            for fname in sorted(os.listdir(ddir)):
                if fname.endswith(".conf"):
                    fpath = os.path.join(ddir, fname)
                    for line_no, key, value in _parse_systemd_directives(fpath):
                        all_directives.append((fpath, line_no, key, value))

        # Build effective config
        effective: Dict[str, str] = {}
        sources: Dict[str, Tuple[str, int]] = {}
        all_values: Dict[str, List[Tuple[str, int, str]]] = {}

        for fpath, line_no, key, value in all_directives:
            effective[key] = value
            sources[key] = (fpath, line_no)
            all_values.setdefault(key, []).append((fpath, line_no, value))

        # Detect conflicts
        conflicts: List[Dict[str, Any]] = []
        for key, entries in all_values.items():
            if len(entries) > 1:
                unique_vals = set(v for _, _, v in entries)
                if len(unique_vals) > 1:
                    conflicts.append({
                        "key": key,
                        "values": [
                            {"file": f, "line": l, "value": v}
                            for f, l, v in entries
                        ],
                        "effective": effective[key],
                        "effective_source": sources[key],
                    })

        return {
            "effective": effective,
            "sources": sources,
            "conflicts": conflicts,
            "base_path": base_path,
        }
