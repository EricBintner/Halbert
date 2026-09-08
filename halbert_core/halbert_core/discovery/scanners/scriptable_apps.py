# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Scriptable Apps Scanner (A3) - Find scriptable macOS apps and their
AppleScript dictionaries.

For each installed .app bundle the scanner looks for an embedded
scripting definition (``Contents/Resources/*.sdef``) and parses the XML
with stdlib ``xml.etree.ElementTree`` to extract the app's AppleScript
commands, classes, and properties. The result is one Discovery per
scriptable app so the agent can know "Mail is scriptable, here are its
commands" without being told (A4 injects these into the agent prompt).

Documented decisions:

- EMBEDDED .sdef ONLY. The ``sdef`` CLI (which generates a dictionary
  from the app's Cocoa scripting metadata) is deliberately NOT used as
  a fallback: running one subprocess per app across /Applications,
  /System/Applications, and /System/Library/CoreServices is expensive,
  and probing on the reference machine showed every app we care about
  ships an embedded .sdef (Mail, Calendar, Music, Notes, Reminders,
  Messages, Safari, Finder, Keynote, ...). Apps that only expose a
  dictionary via the ``sdef`` tool are missed; that residual gap is a
  known limitation, not a bug.
- Scan roots include /System/Applications and
  /System/Library/CoreServices, where the stock Apple apps live —
  /Applications alone misses most of them.
- SUMMARIZE, not dump: the command list per app is capped
  (``MAX_COMMANDS_PER_APP``); classes and properties are reported as
  counts only. Finder's dictionary alone has 168 properties.
- No caching yet: a full scan is only filesystem globs + reads of the
  .sdef files that exist, cheap enough now. If A4 puts this on the
  prompt path per turn, add change-based caching there (future work).
- Depth-1 globs only: apps nested in subfolders (e.g.
  "/Applications/Adobe Creative Cloud/Adobe Photoshop.app") are a known
  blind spot — accepted scope, revisit alongside A4 if the gap matters.
"""

from __future__ import annotations

import logging
import os
import platform
import re
import shlex
import xml.etree.ElementTree as ET
from pathlib import Path
from plistlib import load as _plist_load
from typing import List, Optional

from .base import BaseScanner
from ..schema import (
    Discovery,
    DiscoveryType,
    DiscoverySeverity,
    DiscoveryAction,
    make_discovery_id,
)

logger = logging.getLogger("halbert.scanner.scriptable_apps")

#: Directories scanned for .app bundles (depth-1 glob per directory).
DEFAULT_APP_DIRS = (
    Path("/Applications"),
    Path("/System/Applications"),
    Path("/System/Library/CoreServices"),
    Path.home() / "Applications",
)


def parse_sdef(path: Path) -> Optional[dict]:
    """
    Parse one .sdef file into name lists.

    Returns:
        Dict with sorted-by-document-order, deduplicated ``commands``,
        ``classes``, and ``properties`` name lists — or None if the
        file is missing, unreadable, or not valid XML.
    """
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError, ValueError) as e:
        logger.debug(f"Cannot parse sdef {path}: {e}")
        return None

    def _names(tag: str) -> List[str]:
        names: List[str] = []
        seen = set()
        for el in root.iter(tag):
            name = el.get("name")
            if name and name not in seen:
                seen.add(name)
                names.append(name)
        return names

    return {
        "commands": _names("command"),
        "classes": _names("class"),
        "properties": _names("property"),
    }


class ScriptableAppsScanner(BaseScanner):
    """
    Scanner for scriptable macOS applications.

    Finds .app bundles with an embedded .sdef dictionary and reports,
    per app: bundle identifier, command names (capped), and class /
    property counts. Apps without an embedded dictionary are ignored
    silently — most third-party apps are not scriptable.
    """

    @property
    def discovery_type(self) -> DiscoveryType:
        return DiscoveryType.APP

    def __init__(self, app_dirs: Optional[List[Path]] = None):
        super().__init__()
        self._app_dirs = list(app_dirs) if app_dirs else list(DEFAULT_APP_DIRS)

    #: Per-app cap on the reported command-name list (see module docstring).
    MAX_COMMANDS_PER_APP = 25

    def is_available(self) -> bool:
        """macOS only — .sdef dictionaries are an Apple-scripting concept."""
        if platform.system() != "Darwin":
            return False
        return any(os.path.isdir(d) for d in self._app_dirs)

    # ─────────────────────────────────────────────────────────────
    # Scanning
    # ─────────────────────────────────────────────────────────────

    def scan(self) -> List[Discovery]:
        """Scan the configured app directories for scriptable apps."""
        discoveries: List[Discovery] = []
        seen: set[str] = set()  # dedupe: bundle_id, then resolved path
        used_ids: set[str] = set()  # id collision suffix (same name, distinct apps)

        for app_dir in self._app_dirs:
            for app_path in self._iter_app_bundles(app_dir):
                sdef_files = self._sdef_files(app_path)
                if not sdef_files:
                    continue

                # One Info.plist read per bundle feeds dedupe + discovery.
                bundle_id, name = self._read_info(app_path)
                key = bundle_id or str(app_path.resolve())
                if key in seen:
                    continue
                seen.add(key)

                discovery = self._discovery_for(app_path, sdef_files, name, bundle_id)
                if discovery:
                    if discovery.id in used_ids:
                        n = 2
                        while f"{discovery.id}-{n}" in used_ids:
                            n += 1
                        discovery.id = f"{discovery.id}-{n}"
                    used_ids.add(discovery.id)
                    discoveries.append(discovery)

        self.logger.info(f"Found {len(discoveries)} scriptable app discoveries")
        return discoveries

    def _iter_app_bundles(self, app_dir: Path) -> List[Path]:
        """Depth-1 listing of .app directories; unreadable/missing dirs skipped."""
        try:
            candidates = sorted(app_dir.glob("*.app"))
        except OSError as e:
            self.logger.debug(f"Cannot list {app_dir}: {e}")
            return []
        bundles = []
        for c in candidates:
            try:
                if (c / "Contents").is_dir():
                    bundles.append(c)
            except OSError as e:
                self.logger.debug(f"Skipping unreadable bundle {c}: {e}")
        return bundles

    def _sdef_files(self, app_path: Path) -> List[Path]:
        """All embedded .sdef files in the bundle, sorted for stability."""
        try:
            return sorted((app_path / "Contents" / "Resources").glob("*.sdef"))
        except OSError:
            return []

    # ─────────────────────────────────────────────────────────────
    # Per-app extraction
    # ─────────────────────────────────────────────────────────────

    def _read_info(self, app_path: Path) -> tuple[Optional[str], str]:
        """
        Read the bundle's Info.plist once.

        Returns:
            (bundle_id, name) — bundle_id is None when the plist is
            missing/unreadable or lacks CFBundleIdentifier; name falls
            back to the .app folder stem when no CFBundleName/Display.
        """
        try:
            with (app_path / "Contents" / "Info.plist").open("rb") as f:
                info = _plist_load(f)
            bundle_id = info.get("CFBundleIdentifier")
            if not isinstance(bundle_id, str):
                bundle_id = None
            name = None
            for key in ("CFBundleName", "CFBundleDisplayName"):
                value = info.get(key)
                if isinstance(value, str) and value:
                    name = value
                    break
        except (OSError, ValueError, AttributeError) as e:
            self.logger.debug(f"No readable Info.plist for {app_path}: {e}")
            bundle_id, name = None, None
        return bundle_id, name or app_path.stem

    def _discovery_for(
        self,
        app_path: Path,
        sdef_files: List[Path],
        name: str,
        bundle_id: Optional[str],
    ) -> Optional[Discovery]:
        """Aggregate the bundle's dictionaries into one Discovery."""
        # Merge all .sdef files of the bundle (some apps ship more than
        # one); document order preserved, duplicates dropped.
        commands: List[str] = []
        seen_commands: set[str] = set()
        class_count = 0
        property_count = 0
        for sdef in sdef_files:
            parsed = parse_sdef(sdef)
            if parsed is None:
                continue  # corrupt/non-XML dictionary — skip it
            for cmd in parsed["commands"]:
                if cmd not in seen_commands:
                    seen_commands.add(cmd)
                    commands.append(cmd)
            class_count += len(parsed["classes"])
            property_count += len(parsed["properties"])

        if not commands and not class_count:
            return None  # nothing usable in any dictionary

        sample = ", ".join(commands[:5])
        more = f" (+{len(commands) - 5} more)" if len(commands) > 5 else ""

        discovery_id = make_discovery_id(
            DiscoveryType.APP, f"scriptable-{_slug(name)}"
        )

        return Discovery(
            id=discovery_id,
            type=DiscoveryType.APP,
            name=name,
            title=f"{name} is scriptable",
            description=(
                f"AppleScript dictionary: {len(commands)} commands ({sample}{more})"
                if commands
                else f"AppleScript dictionary: {class_count} classes, no commands"
            ),
            icon="app-window",
            severity=DiscoverySeverity.INFO,
            source=str(sdef_files[0]),
            status="Available",
            data={
                "app_name": name,
                "bundle_id": bundle_id,
                "app_path": str(app_path),
                "sdef_paths": [str(s) for s in sdef_files],
                "commands": commands[:self.MAX_COMMANDS_PER_APP],
                "command_count": len(commands),
                "classes": class_count,
                "properties": property_count,
            },
            actions=[
                DiscoveryAction(
                    id="open-in-script-editor",
                    label="Open in Script Editor",
                    command=f"open -a 'Script Editor' {shlex.quote(str(app_path))}",
                ),
            ],
            chat_context=(
                f"{name} is scriptable via AppleScript. "
                f"Available commands include: {sample}. "
                f"Drive it with the run_applescript tool "
                f"(e.g. 'tell application \"{name}\" to ...')."
            ),
        )


def _slug(name: str) -> str:
    """Lowercase, alphanumeric+dash slug for a discovery id."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "app"