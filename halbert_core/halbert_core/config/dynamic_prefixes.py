# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Dynamic prefix database — keep credential format detection current.

The bundled credential format database (``credential_formats.py``) is
curated and updated with each Halbert release. New services launch new
token formats constantly, and the bundled list goes stale between
releases. This module fetches an updated list of known credential
prefixes from a maintained source and caches it locally.

Sources (in priority order):
1. A user-configured URL (``security.dynamic_prefix_url``)
2. The Halbert project's maintained list on GitHub
3. The bundled database (fallback, always available)

The fetched list is a JSON file with the same structure as
``_CREDENTIAL_FORMATS`` entries: name, service, pattern, description.

Security: this module fetches PATTERN DEFINITIONS, not secrets. No
credential value is ever sent to the update source. The fetch is a
plain GET request for a public JSON file.

Caching: the fetched list is stored at
``~/.local/share/halbert/config/prefix_cache.json`` and refreshed every
7 days (configurable). On failure, the cache is used until it expires;
after expiry, the bundled database is used.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional

from ..utils.paths import data_dir

logger = logging.getLogger(__name__)

# Default update source — the Halbert project's maintained prefix list.
# This is a public JSON file that contains credential format definitions.
# It sends no secrets; it only fetches pattern definitions.
_DEFAULT_SOURCE_URL = (
    "https://raw.githubusercontent.com/ericbintner/halbert/main/"
    "config/credential_prefixes.json"
)

# Cache location
_CACHE_DIR = os.path.join(data_dir(), "config")
_CACHE_FILE = os.path.join(_CACHE_DIR, "prefix_cache.json")
_CACHE_TTL = 7 * 24 * 3600  # 7 days


def _ensure_cache_dir() -> None:
    """Create the cache directory if it doesn't exist."""
    os.makedirs(_CACHE_DIR, exist_ok=True)


def _load_cache() -> Optional[Dict[str, Any]]:
    """Load the cached prefix database, or None if not present/expired."""
    if not os.path.exists(_CACHE_FILE):
        return None
    try:
        with open(_CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Check age
        fetched_at = data.get("_fetched_at", 0)
        if time.time() - fetched_at > _CACHE_TTL:
            logger.debug("Prefix cache expired, will refresh")
            return None
        return data
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Failed to load prefix cache: {e}")
        return None


def _save_cache(formats: List[Dict[str, Any]]) -> None:
    """Save the fetched prefix database to the cache."""
    _ensure_cache_dir()
    data = {
        "_fetched_at": time.time(),
        "formats": formats,
    }
    try:
        with open(_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except OSError as e:
        logger.warning(f"Failed to save prefix cache: {e}")


def _fetch_prefixes(url: str) -> Optional[List[Dict[str, Any]]]:
    """Fetch the prefix database from a URL.

    Returns a list of format dicts, or None on failure.
    Sends no secrets — this is a plain GET for a public JSON file.
    """
    import urllib.request

    req = urllib.request.Request(url, headers={"User-Agent": "Halbert-MCP/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status != 200:
                logger.warning(f"Prefix fetch returned HTTP {resp.status}")
                return None
            body = resp.read().decode("utf-8")
            data = json.loads(body)
            if isinstance(data, list):
                return data
            if isinstance(data, dict) and "formats" in data:
                return data["formats"]
            logger.warning("Prefix fetch: unexpected JSON structure")
            return None
    except Exception as e:
        logger.warning(f"Failed to fetch prefix database: {e}")
        return None


def _parse_formats(raw_formats: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Parse raw format dicts into a usable structure.

    Validates that each entry has the required fields and compiles the
    regex pattern. Invalid entries are skipped with a warning.
    """
    parsed = []
    for entry in raw_formats:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        service = entry.get("service")
        pattern_str = entry.get("pattern")
        if not name or not service or not pattern_str:
            logger.debug(f"Skipping invalid prefix entry: {entry}")
            continue
        try:
            pattern = re.compile(pattern_str)
        except re.error as e:
            logger.warning(f"Invalid regex in prefix entry '{name}': {e}")
            continue
        parsed.append({
            "name": name,
            "service": service,
            "description": entry.get("description", ""),
            "pattern": pattern,
            "breach_risk": entry.get("breach_risk", "medium"),
            "validation_endpoint": entry.get("validation_endpoint", ""),
        })
    return parsed


def get_dynamic_prefixes(
    *,
    url: Optional[str] = None,
    force_refresh: bool = False,
) -> List[Dict[str, Any]]:
    """Get the credential prefix database, fetching if needed.

    Parameters
    ----------
    url
        Override the source URL. Defaults to the Halbert project's
        maintained list.
    force_refresh
        If True, ignore the cache and fetch fresh.

    Returns
    -------
    List of format dicts with compiled ``pattern`` fields. Empty list
    on failure (the bundled database in ``credential_formats.py`` is
    the fallback).

    No secrets are sent during the fetch — this is a GET for a public
    JSON file containing pattern definitions only.
    """
    source_url = url or _DEFAULT_SOURCE_URL

    # Check cache first (unless force_refresh)
    if not force_refresh:
        cached = _load_cache()
        if cached and "formats" in cached:
            raw = cached["formats"]
            parsed = _parse_formats(raw)
            if parsed:
                logger.debug(f"Using cached prefix database ({len(parsed)} entries)")
                return parsed

    # Fetch fresh
    raw = _fetch_prefixes(source_url)
    if raw:
        _save_cache(raw)
        parsed = _parse_formats(raw)
        if parsed:
            logger.info(f"Fetched {len(parsed)} credential prefix patterns")
            return parsed

    # Fallback: empty list (caller uses bundled database)
    logger.debug("Prefix fetch failed, falling back to bundled database")
    return []


def get_last_fetch_time() -> Optional[float]:
    """Return the timestamp of the last successful cache write, or None."""
    if not os.path.exists(_CACHE_FILE):
        return None
    try:
        with open(_CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("_fetched_at")
    except (json.JSONDecodeError, OSError):
        return None


def clear_cache() -> None:
    """Delete the prefix cache file."""
    if os.path.exists(_CACHE_FILE):
        try:
            os.remove(_CACHE_FILE)
        except OSError as e:
            logger.warning(f"Failed to clear prefix cache: {e}")
