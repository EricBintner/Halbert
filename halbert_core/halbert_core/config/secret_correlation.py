# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Cross-file secret correlation — find the same secret in multiple files.

The same password or token often appears in several config files:
~/.msmtprc, a Docker compose file, an .env file, and a systemd unit.
Without correlation, the agent thinks there are 4 different secrets
when there's 1 used in 4 places. This matters for rotation advice:
"rotate the password" should identify all locations.

This module builds a correlation index by hashing each secret value
and grouping secrets by hash. The index is built from the canon DB and
stored at ``~/.local/share/halbert/config/secret_correlations.json``.

Security (REV-01 F5): the correlation index stores only hashes, never
raw values — but a bare truncated SHA-256 does not slow a dictionary
attack on human passwords (any candidate is hashed and compared), and
the file enumerates *where every secret on the machine lives*. The
stored hash is therefore HMAC-SHA256 keyed with a locally-generated
random pepper, stored 0600 in a SEPARATE file from the index
(``secret_correlations.pepper``) and generated on first use. An
exfiltrated index alone then verifies nothing: without the pepper,
no candidate can be tested against it. Verification (find_correlated_
secrets) uses the same pepper. If the pepper is lost, the index fails
closed — no matches, never a false positive.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

from ..ingestion.redaction import _is_secret_key, redact_text
from ..utils.paths import data_dir

logger = logging.getLogger(__name__)

_CORRELATION_FILE = os.path.join(data_dir(), "config", "secret_correlations.json")

# The pepper lives in its own file BESIDE the index — never inside it —
# so an exfiltrated or backed-up index alone is useless as a dictionary-
# attack target or a secret-location map.
_PEPPER_FILENAME = "secret_correlations.pepper"

# Per-path pepper cache: keyed by pepper file path so tests (and multi-
# instance setups) with distinct index dirs never share a pepper.
_PEPPER_CACHE: Dict[str, bytes] = {}


def _pepper_path() -> str:
    """Path of the pepper file, beside the current correlation index."""
    return os.path.join(
        os.path.dirname(_CORRELATION_FILE) or ".", _PEPPER_FILENAME
    )


def _load_or_create_pepper() -> bytes:
    """Return the pepper, generating it (0600, O_EXCL) on first use.

    A lost or unreadable pepper is never fabricated from anything
    guessable — on failure a fresh random value is used per call, which
    fails closed (no correlation can verify).
    """
    pepper_file = _pepper_path()
    cached = _PEPPER_CACHE.get(pepper_file)
    if cached is not None:
        return cached

    try:
        with open(pepper_file, "rb") as f:
            key = f.read().strip()
        if key:
            _PEPPER_CACHE[pepper_file] = key
            return key
    except FileNotFoundError:
        pass
    except OSError as e:
        logger.warning(f"Cannot read correlation pepper: {e}")
        return os.urandom(32)  # ephemeral — fails closed

    # Generate on first use. O_CREAT|O_EXCL so two processes racing both
    # end up with the same (first writer's) pepper.
    try:
        os.makedirs(os.path.dirname(pepper_file) or ".", exist_ok=True)
        new_key = os.urandom(32).hex().encode("utf-8")
        fd = os.open(pepper_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            os.write(fd, new_key)
        finally:
            os.close(fd)
        os.chmod(pepper_file, 0o600)
        key = new_key
    except FileExistsError:
        try:
            with open(pepper_file, "rb") as f:
                key = f.read().strip()
        except OSError:
            return os.urandom(32)  # ephemeral — fails closed
    except OSError as e:
        logger.warning(f"Cannot create correlation pepper: {e}")
        return os.urandom(32)  # ephemeral — fails closed

    if not key:
        return os.urandom(32)
    _PEPPER_CACHE[pepper_file] = key
    return key


def _secret_hash(value: str) -> str:
    """Hash a secret value for correlation.

    HMAC-SHA256 keyed with the locally-stored pepper, truncated to 16
    hex chars — enough for collision resistance across a single
    machine's config files, and useless for offline verification
    without the pepper.
    """
    return hmac.new(
        _load_or_create_pepper(), value.encode("utf-8"), hashlib.sha256
    ).hexdigest()[:16]


def _extract_secrets_from_canon(
    canon: Dict[str, Any],
    path: str,
) -> List[Tuple[str, str, str]]:
    """Extract (key, value, section) tuples for all secrets in a canon record.

    Returns only values where the key is a secret key name or the value
    content triggers the redaction detector.
    """
    secrets: List[Tuple[str, str, str]] = []
    kind = canon.get("kind", "text")

    if kind == "ini":
        sections = canon.get("sections", {})
        for section_name, items in sections.items():
            for k, v in items.items():
                if isinstance(v, str) and v:
                    if _is_secret_key(k) or redact_text(v) != v:
                        secrets.append((k, v, section_name))

    elif kind in ("yaml", "json", "plist"):
        tree = canon.get("tree")
        if isinstance(tree, dict):
            _walk_tree(tree, "", secrets)

    return secrets


def _walk_tree(node: Any, prefix: str, secrets: List[Tuple[str, str, str]]) -> None:
    """Recursively walk a tree structure looking for secret key-value pairs."""
    if isinstance(node, dict):
        for k, v in node.items():
            full_key = f"{prefix}.{k}" if prefix else k
            if isinstance(v, str) and v:
                if _is_secret_key(k) or redact_text(v) != v:
                    secrets.append((full_key, v, "tree"))
            elif isinstance(v, (dict, list)):
                _walk_tree(v, full_key, secrets)
    elif isinstance(node, list):
        for i, item in enumerate(node):
            _walk_tree(item, f"{prefix}[{i}]", secrets)


def build_correlation_index(
    canon_entries: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Build a correlation index from canon DB entries.

    Parameters
    ----------
    canon_entries
        List of dicts with ``path`` and ``canon`` keys (the parsed
        canonical record for each file).

    Returns
    -------
    dict mapping secret hashes to lists of locations:
    ``{"<hash>": [{"path": ..., "key": ..., "section": ...}, ...]}``
    """
    index: Dict[str, List[Dict[str, Any]]] = {}

    for entry in canon_entries:
        path = entry.get("path", "")
        canon = entry.get("canon")
        if not canon or not path:
            continue

        secrets = _extract_secrets_from_canon(canon, path)
        for key, value, section in secrets:
            h = _secret_hash(value)
            if h not in index:
                index[h] = []
            index[h].append({
                "path": path,
                "key": key,
                "section": section,
            })

    return index


def save_correlation_index(index: Dict[str, Any]) -> None:
    """Save the correlation index to disk."""
    os.makedirs(os.path.dirname(_CORRELATION_FILE), exist_ok=True)
    try:
        with open(_CORRELATION_FILE, "w", encoding="utf-8") as f:
            json.dump(index, f, indent=2)
    except OSError as e:
        logger.warning(f"Failed to save correlation index: {e}")


def load_correlation_index() -> Dict[str, Any]:
    """Load the correlation index from disk, or empty dict if not present."""
    if not os.path.exists(_CORRELATION_FILE):
        return {}
    try:
        with open(_CORRELATION_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Failed to load correlation index: {e}")
        return {}


def find_correlated_secrets(
    key: str,
    value: str,
    path: str,
) -> List[Dict[str, Any]]:
    """Find all locations where the same secret value appears.

    Parameters
    ----------
    key
        The config key name for the secret.
    value
        The secret value.
    path
        The file the value came from.

    Returns
    -------
    List of locations (excluding the current one) where the same
    secret value appears. Each location is a dict with ``path``,
    ``key``, and ``section``.
    """
    if not value or not isinstance(value, str):
        return []

    index = load_correlation_index()
    if not index:
        # No index on disk — nothing to correlate. (Also keeps the
        # read-only path from creating a pepper when there is no index.)
        return []
    h = _secret_hash(value)
    locations = index.get(h, [])

    # Exclude the current location
    return [
        loc for loc in locations
        if not (loc.get("path") == path and loc.get("key") == key)
    ]


def describe_with_correlations(
    key: str,
    value: Any,
    file_path: str = "",
) -> Dict[str, Any]:
    """Describe a secret including cross-file correlations.

    Wraps ``describe_secret`` and adds a ``correlations`` field listing
    other files where the same secret value appears.
    """
    from .secure_response import describe_secret

    result = describe_secret(key, value, file_path)
    text = "" if value is None else str(value)
    if text:
        correlations = find_correlated_secrets(key, text, file_path)
        if correlations:
            result["correlations"] = correlations
            result["correlation_count"] = len(correlations)

    return result
