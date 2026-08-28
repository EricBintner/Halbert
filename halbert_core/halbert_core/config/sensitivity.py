# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Three-tier sensitivity classifier for config values.

Tiers
-----
0 — Public
    Machine structure with no secrets and no exploitable identifying values.
    Service names, booleans, structural keys (``include``, ``enabled``).

1 — Operational
    Config values that could identify the machine or reveal security-relevant
    settings, but are not credentials.  SSH port, routable IPs, firewall rules.

2 — Secrets
    Credentials, keys, tokens, passwords — anything ``_is_secret_key`` or
    ``redact_text`` identifies.

The classifier is the single decision point that the config query layer
(``queries.py``), the MCP server, and the agent context assembler all consult.
It reuses the same two detectors the rest of the trust boundary uses:
``_is_secret_key`` (key-name predicate) and ``redact_text`` (content detector).

Design notes
------------
File-level Tier 0 is a **floor**, not a ceiling.  It is placed *after* the
content checks so that ``/etc/hosts`` with a routable IP still gets Tier 1
for that value, and ``/etc/fstab`` with cifs credentials still gets Tier 2.
A path can confirm clean content is public; it can never certify content it
has not looked at.

Known limit (shared with Task 8): ``redact_text`` is keyword-driven with no
entropy or known-prefix detection, so a bare context-free secret (``ghp_…``
under a neutral key) is classified Tier 1, not Tier 2.  Closing that gap in
Task 8 closes it here too — both share one detector.
"""
from __future__ import annotations

import os
from typing import Any, Optional, Sequence, Set

from ..ingestion.redaction import _is_secret_key, redact_text

# Default set of host paths whose *structure* is public.  A value drawn from
# one of these files is Tier 0 only if the content checks above did not fire.
DEFAULT_PUBLIC_FILES: Set[str] = {
    "/etc/hosts",
    "/etc/hostname",
    "/etc/fstab",
    "/etc/machine-id",
    "/etc/os-release",
}

# Structural config keys whose values are shape, not data.
_STRUCTURAL_KEYS = frozenset({"include", "enabled", "type", "kind", "version"})

# The staging directory prefix.  Staged paths look like
# ``~/.local/share/halbert/sourceprep/host/etc/hosts``; the original host
# path is ``/etc/hosts``.  _host_path() strips the prefix so PUBLIC_FILES
# can be matched by their real host paths.
_STAGING_PREFIX_SEGMENTS = (
    "sourceprep",
    "host",
)


def _host_path(staged_or_host_path: str) -> str:
    """Map a staged path back to its original host path.

    ``~/.local/share/halbert/sourceprep/host/etc/hosts`` → ``/etc/hosts``.
    If the path is already a host path (no staging prefix), it is returned
    unchanged.
    """
    # Normalise to forward slashes for matching.
    p = staged_or_host_path.replace("\\", "/")
    # Find the full ``sourceprep/host/`` prefix and take everything after it.
    marker = "/" + "/".join(_STAGING_PREFIX_SEGMENTS) + "/"
    idx = p.find(marker)
    if idx != -1:
        remainder = p[idx + len(marker):]
        if remainder:
            return "/" + remainder
    return staged_or_host_path


def classify_sensitivity(
    key: str,
    value: Any,
    file_path: str = "",
    *,
    public_files: Optional[Set[str]] = None,
    extra_secret_keys: Optional[Sequence[str]] = None,
) -> int:
    """Return sensitivity tier: 0 (public), 1 (operational), 2 (secret).

    Parameters
    ----------
    key
        The config key name (e.g. ``"password"``, ``"Port"``, ``"Include"``).
    value
        The config value.  May be any type — str, int, float, bool, None, dict, list.
    file_path
        The file the value came from.  May be a staged path or a host path.
    public_files
        Override for the set of Tier-0 host paths.  Defaults to
        ``DEFAULT_PUBLIC_FILES``.
    extra_secret_keys
        Additional key names to treat as Tier 2 (from being config
        ``security.extra_secret_keys``).  Compared by whole-key equality
        after normalisation, same as ``_NON_SECRET_KEYS``.
    """
    pub = public_files if public_files is not None else DEFAULT_PUBLIC_FILES
    text = "" if value is None else str(value)

    # --- Tier 2: by key name ---
    if _is_secret_key(key):
        return 2
    if extra_secret_keys:
        norm_key = _normalize_for_compare(key)
        for extra in extra_secret_keys:
            if _normalize_for_compare(extra) == norm_key:
                return 2

    # --- Tier 2: by value content ---
    # redact_text as a detector: if it would have changed the value, the
    # value contains a credential (key=value shape, PEM, JWT, URL creds, etc).
    if text and redact_text(text) != text:
        return 2

    # --- Tier 0: by file (floor, not ceiling — AFTER content checks) ---
    if file_path and _host_path(file_path) in pub:
        return 0

    # --- Tier 0: structural values ---
    if isinstance(value, bool):
        return 0
    if key and key.lower() in _STRUCTURAL_KEYS:
        return 0

    # --- Tier 1: everything else with a real value ---
    return 1


def _normalize_for_compare(key: str) -> str:
    """Normalise a key for whole-key comparison (lowercase, stripped)."""
    return key.strip().lower().replace("-", "").replace("_", "")
