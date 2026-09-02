# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The web-search switch (C3-08): one home for ``web_search.enabled``.

Web search sends the query text off the machine, so it is OFF by default
and only the operator turns it on. The setting is ``web_search.enabled``
in ``web_search.yml`` — the user file (``get_config_dir()/web_search.yml``)
first, then the repo template (``<repo>/config/web_search.yml``), else off.

The capability registry reads this through ``_probe_web`` (CAP_WEB); a
``being.yml capabilities: {web: false}`` override wins over the file the
same way it does for every other capability. Writers only ever touch the
user file, never the git-tracked template.

Only a real YAML boolean ``true`` enables it. A string such as ``'yes'``
is not a switch someone flipped on purpose, so it reads as off.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict

import yaml

logger = logging.getLogger("halbert.web.search_config")

SECTION = "web_search"


def user_config_path() -> Path:
    """The file every writer targets."""
    try:
        from ..utils.platform import get_config_dir
        return get_config_dir() / "web_search.yml"
    except Exception:
        return Path.home() / ".config" / "halbert" / "web_search.yml"


def template_config_path() -> Path:
    """The dev-checkout default (git-tracked, never written)."""
    # this file: <repo>/halbert_core/halbert_core/web/search_config.py
    return Path(__file__).resolve().parents[3] / "config" / "web_search.yml"


def _read(path: Path) -> Dict[str, Any]:
    with open(path, "r") as f:
        raw = yaml.safe_load(f) or {}
    return raw if isinstance(raw, dict) else {}


def load_raw() -> Dict[str, Any]:
    """The raw document the setting is read from: user file, else template, else empty."""
    for path in (user_config_path(), template_config_path()):
        try:
            if path.is_file():
                return _read(path)
        except Exception as e:
            logger.warning("Could not read %s: %s (treating web search as off)", path, e)
            return {}
    return {}


def is_enabled() -> bool:
    """Is web search switched on? Off unless the file says a boolean ``true``."""
    section = load_raw().get(SECTION)
    if not isinstance(section, dict):
        return False
    return section.get("enabled") is True


def set_enabled(enabled: bool) -> Path:
    """Persist the switch to the user file, keeping every other setting.

    A user file that does not exist yet is seeded from the template so the
    instance list and the rest of the tuning travel with the switch.
    """
    path = user_config_path()
    raw = load_raw()
    section = raw.get(SECTION)
    if not isinstance(section, dict):
        section = {}
    section["enabled"] = bool(enabled)
    raw[SECTION] = section
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        f.write("# Halbert web search configuration\n")
        f.write("# web_search.enabled: query text leaves the machine; off by default.\n")
        yaml.safe_dump(raw, f, default_flow_style=False, sort_keys=False)
    logger.info("Web search %s (%s)", "enabled" if enabled else "disabled", path)
    return path
