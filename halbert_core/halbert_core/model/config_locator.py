# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Single source of truth for locating models.yml.

Candidate order (first existing wins):
  1. $HALBERT_MODELS_CONFIG (explicit override; if set but not an existing
     file it is skipped with a WARNING so misconfiguration is loud in logs)
  2. get_config_dir()/models.yml  (user config; every writer targets this)
  3. <repo>/config/models.yml     (dev checkout defaults)
  4. /etc/halbert/models.yml      (system-wide install)
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import List, Optional

from ..utils.platform import get_config_dir

logger = logging.getLogger("halbert.model.config_locator")

ENV_VAR = "HALBERT_MODELS_CONFIG"


def repo_root() -> Path:
    # this file: <repo>/halbert_core/halbert_core/model/config_locator.py
    # parents[0]=model, [1]=halbert_core (pkg), [2]=halbert_core (dist), [3]=<repo>
    return Path(__file__).resolve().parents[3]


def user_models_config() -> Path:
    return get_config_dir() / "models.yml"


def repo_models_config() -> Path:
    return repo_root() / "config" / "models.yml"


def write_models_config() -> Path:
    """Where writers must persist models.yml.

    $HALBERT_MODELS_CONFIG when set, else the user config file. Never the
    git-tracked repo config and never /etc/halbert/models.yml (a system
    install with no user file must not have its packaged config edited).
    """
    env = os.environ.get(ENV_VAR)
    if env:
        return Path(env).expanduser()
    return user_models_config()


def models_config_candidates(include_repo: bool = True) -> List[Path]:
    cands: List[Path] = []
    env = os.environ.get(ENV_VAR)
    if env:
        cands.append(Path(env).expanduser())
    cands.append(user_models_config())
    if include_repo:
        cands.append(repo_models_config())
    cands.append(Path("/etc/halbert/models.yml"))
    return cands


def find_models_config(include_repo: bool = True) -> Optional[Path]:
    """Return the first existing models.yml, or None."""
    env = os.environ.get(ENV_VAR)
    for c in models_config_candidates(include_repo=include_repo):
        if c.is_file():
            return c
        if env and c == Path(env).expanduser():
            logger.warning(
                "%s=%s is set but is not a file; ignoring it and falling back "
                "to the standard candidates", ENV_VAR, c
            )
    return None
