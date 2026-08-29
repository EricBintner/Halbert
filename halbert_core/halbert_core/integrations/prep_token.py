# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""PREP_DAEMON_TOKEN management for SourcePrep API authentication.

The SourcePrep daemon supports bearer token auth via the
``PREP_DAEMON_TOKEN`` env var on the server side.  This module provides
the client-side counterpart: generate, persist, and retrieve a token so
Halbert's API calls authenticate against the daemon.

Token storage: ``~/.config/halbert/prep_token`` (or platform equivalent
via ``config_dir()``).  The file is created with mode 0600.

Scope note (from the plan's review): the token blocks unauthenticated
localhost callers — other users' processes, stray browser fetches,
mis-scoped containers.  It does NOT provide same-user isolation: any
process running as the same user can read the token file and the index
files directly off disk.  Same-user isolation requires OS-level controls
(encryption at rest, Task 5).
"""
from __future__ import annotations

import logging
import os
import secrets
from pathlib import Path
from typing import Optional

from ..utils.paths import config_dir

logger = logging.getLogger(__name__)

_TOKEN_FILENAME = "prep_token"
_ENV_VAR = "PREP_DAEMON_TOKEN"


def _token_path() -> Path:
    return Path(config_dir()) / _TOKEN_FILENAME


def get_token() -> Optional[str]:
    """Retrieve the daemon token.

    Resolution order:
    1. ``PREP_DAEMON_TOKEN`` env var (set by the daemon or user)
    2. ``~/.config/halbert/prep_token`` file (persisted by ``ensure_token``)

    Returns None if no token is configured — callers should pass None to
    the daemon, which will treat the request as unauthenticated.  If the
    daemon has ``PREP_DAEMON_TOKEN`` set, unauthenticated requests get 403.
    """
    env_token = os.environ.get(_ENV_VAR, "").strip()
    if env_token:
        return env_token

    path = _token_path()
    try:
        token = path.read_text(encoding="utf-8").strip()
        if token:
            return token
    except (OSError, ValueError):
        pass
    return None


def ensure_token() -> str:
    """Get the existing token, or generate and persist a new one.

    If ``PREP_DAEMON_TOKEN`` is set in the env, it is returned as-is
    without writing to disk (the daemon is the source of truth in that
    case).

    Otherwise, if the token file exists, its contents are returned.
    If not, a new 32-byte hex token is generated, written to
    ``~/.config/halbert/prep_token`` with mode 0600, and returned.

    The generated token must also be set as ``PREP_DAEMON_TOKEN`` on the
    daemon side — either by exporting it in the daemon's environment or
    by having the daemon read the same file.  Halbert's startup sequence
    should call ``ensure_token()`` and export the result to the daemon's
    environment.
    """
    env_token = os.environ.get(_ENV_VAR, "").strip()
    if env_token:
        return env_token

    path = _token_path()
    try:
        token = path.read_text(encoding="utf-8").strip()
        if token:
            return token
    except (OSError, ValueError):
        pass

    # Generate a new token
    path.parent.mkdir(parents=True, exist_ok=True)
    token = secrets.token_hex(32)
    # Write with mode 0600 — only the owner can read it
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, token.encode("utf-8"))
    finally:
        os.close(fd)
    logger.info("Generated new PREP_DAEMON_TOKEN at %s", path)
    return token


def auth_headers() -> dict:
    """Return an Authorization header dict, or an empty dict if no token.

    Usage::

        headers = auth_headers()
        resp = requests.post(url, json=body, headers=headers, timeout=30)
    """
    token = get_token()
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}
