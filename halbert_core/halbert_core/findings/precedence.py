"""
Precedence resolution engine for host configuration.

Resolves the effective configuration for services that support drop-in
files (sshd_config.d/, systemd unit .d/ directories).

sshd semantics: sshd_config is FIRST-match-wins for most keywords, and
drop-ins are pulled in by an `Include` directive — so a drop-in included
near the top of the base file wins over the base file's own directives.
When no matching `Include` directive is present in the base file, we fall
back to appending drop-ins after the base (last wins) — this assumes the
drop-in directory is pulled in by a mechanism we cannot see from here
(e.g. a distribution-level include in a packaged default file).

systemd semantics: later files override earlier ones; within a single
file, last directive wins. Exception: ADDITIVE directives (e.g.
After=, Environment=, ExecStartPre=, ListenStream=) ACCUMULATE across
files instead of overriding — differing values for those are merged into
lists in the effective config and are NOT reported as conflicts.

Phase 5 / T5d.1.
"""

from __future__ import annotations

import fnmatch
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# Section-aware allowlist of systemd directives that ACCUMULATE across
# files rather than overriding. Values keyed as lowercased
# ("Section/Key") to match parsed directive keys.
_SYSTEMD_ADDITIVE: Dict[str, List[str]] = {
    "Service": [
        "Environment",
        "ExecCondition",
        "ExecStartPre",
        "ExecStartPost",
        "ExecReload",
        "ExecStop",
        "ExecStopPost",
    ],
    "Unit": [
        "After",
        "Before",
        "Wants",
        "Requires",
        "Conflicts",
        "BindsTo",
        "PartOf",
    ],
    "Socket": [
        "ListenStream",
        "ListenDatagram",
        "ListenSequentialPacket",
    ],
}

SYSTEMD_ADDITIVE_KEYS = {
    f"{section.lower()}/{key.lower()}"
    for section, keys in _SYSTEMD_ADDITIVE.items()
    for key in keys
}


def _parse_sshd_directives(path: str) -> List[Tuple[int, str, str]]:
    """Parse sshd_config-style file into a list of (line_no, key, value) tuples.

    sshd_config uses `Key Value` syntax (space-separated, not `=`).
    Comments start with `#`.
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
                    full_key = (
                        f"{current_section.lower()}/{key.strip().lower()}"
                        if current_section
                        else key.strip().lower()
                    )
                    directives.append((i, full_key, value.strip()))
    except OSError as e:
        logger.warning(f"Cannot read {path}: {e}")
    return directives


def _include_matches_dropins(include_value: str, dropin_files: List[str]) -> bool:
    """Check whether an sshd Include value matches any drop-in file.

    Include arguments are whitespace-separated glob patterns; relative
    patterns are resolved against /etc/ssh (per sshd_config semantics,
    approximated with the drop-in directory's parent).
    """
    for pattern in include_value.split():
        for fpath in dropin_files:
            if fnmatch.fnmatch(fpath, pattern):
                return True
    return False


class PrecedenceEngine:
    """Resolve effective configuration for services with drop-in support.

    Handles:
    - sshd_config + /etc/ssh/sshd_config.d/*.conf (Include-aware, first
      match wins — see module docstring for the fallback assumption)
    - systemd units + /etc/systemd/system/<unit>.d/*.conf (drop-ins
      override base, EXCEPT additive directives which accumulate)
    """

    def __init__(self, config_dir: str = "/etc"):
        self.config_dir = config_dir
        self.sshd_base = os.path.join(config_dir, "ssh", "sshd_config")
        self.sshd_dropin_dir = os.path.join(config_dir, "ssh", "sshd_config.d")
        self.systemd_dir = os.path.join(config_dir, "systemd", "system")

    def resolve_sshd(self) -> Dict[str, Any]:
        """Resolve effective sshd configuration.

        sshd is first-match-wins. If the base file contains an Include
        directive matching the drop-in directory, drop-in directives are
        inserted into the directive stream at the position of that Include
        (alphabetical file order), and the FIRST occurrence of each key
        wins. When the Include appears at/near the top (the common distro
        default), drop-in values therefore win.

        If no matching Include exists in the base file, drop-ins are
        appended after the base and the LAST occurrence wins (documented
        assumption — see module docstring).

        Returns a dict with:
          - effective: dict of key -> value
          - sources: dict of key -> (file_path, line_no) for provenance
          - conflicts: list of dicts describing conflicting directives
          - include_aware: whether an `Include` for the drop-in dir was
            found (determines the resolution order used)
        """
        base_lines = _parse_sshd_directives(self.sshd_base)

        dropin_files: List[str] = []
        if os.path.isdir(self.sshd_dropin_dir):
            for fname in sorted(os.listdir(self.sshd_dropin_dir)):
                if fname.endswith(".conf"):
                    dropin_files.append(os.path.join(self.sshd_dropin_dir, fname))

        # Locate the Include directive covering our drop-in dir (if any)
        include_line: Optional[int] = None
        for line_no, key, value in base_lines:
            if key == "include" and _include_matches_dropins(value, dropin_files):
                include_line = line_no
                break

        # Build the ordered directive stream: (file, line, key, value)
        stream: List[Tuple[str, int, str, str]] = []
        if include_line is not None:
            dropin_directives: List[Tuple[str, int, str, str]] = []
            for fpath in dropin_files:
                for line_no, key, value in _parse_sshd_directives(fpath):
                    dropin_directives.append((fpath, line_no, key, value))
            for line_no, key, value in base_lines:
                if line_no == include_line:
                    # Expand the drop-ins at the position of the Include
                    stream.extend(dropin_directives)
                    continue  # the Include line itself is not a config value
                stream.append((self.sshd_base, line_no, key, value))
        else:
            # Fallback: drop-ins after the base, last wins (legacy behavior)
            for line_no, key, value in base_lines:
                stream.append((self.sshd_base, line_no, key, value))
            for fpath in dropin_files:
                for line_no, key, value in _parse_sshd_directives(fpath):
                    stream.append((fpath, line_no, key, value))

        first_wins = include_line is not None

        effective: Dict[str, str] = {}
        sources: Dict[str, Tuple[str, int]] = {}
        all_values: Dict[str, List[Tuple[str, int, str]]] = {}

        for fpath, line_no, key, value in stream:
            all_values.setdefault(key, []).append((fpath, line_no, value))
            if first_wins:
                if key not in effective:
                    effective[key] = value
                    sources[key] = (fpath, line_no)
            else:
                effective[key] = value
                sources[key] = (fpath, line_no)

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
            "include_aware": include_line is not None,
        }

    def resolve_systemd_unit(self, unit_name: str) -> Dict[str, Any]:
        """Resolve effective systemd unit configuration.

        Reads the base unit file and all drop-ins in <unit>.d/
        directories. Override-capable directives follow last-wins;
        ADDITIVE directives (see SYSTEMD_ADDITIVE_KEYS) accumulate — their
        effective value is the ordered list of all values, and differing
        accumulated values are NOT conflicts.

        Returns the same structure as resolve_sshd() plus base_path.
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

        # Build effective config; additive keys accumulate into lists
        effective: Dict[str, Any] = {}
        sources: Dict[str, Any] = {}
        all_values: Dict[str, List[Tuple[str, int, str]]] = {}

        for fpath, line_no, key, value in all_directives:
            all_values.setdefault(key, []).append((fpath, line_no, value))
            if key in SYSTEMD_ADDITIVE_KEYS:
                # Accumulate (reset assignments, Key= with empty value,
                # clear previously accumulated values per systemd rules)
                existing = effective.get(key)
                if not isinstance(existing, list) or existing is None:
                    existing = []
                if value == "":
                    existing = []
                else:
                    existing = existing + [value]
                effective[key] = existing
                sources.setdefault(key, []).append((fpath, line_no))
            else:
                effective[key] = value
                sources[key] = (fpath, line_no)

        # Detect conflicts — additive keys never conflict on differing
        # values; accumulation is their defined behavior.
        conflicts: List[Dict[str, Any]] = []
        for key, entries in all_values.items():
            if key in SYSTEMD_ADDITIVE_KEYS:
                continue
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
