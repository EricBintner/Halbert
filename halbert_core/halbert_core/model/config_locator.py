# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Single source of truth for locating models.yml, and for the layer order.

The *global* file — one file, first existing wins:
  1. $HALBERT_MODELS_CONFIG (explicit override; if set but not an existing
     file it is skipped with a WARNING so misconfiguration is loud in logs)
  2. get_config_dir()/models.yml  (user config; every writer targets this)
  3. <repo>/config/models.yml     (dev checkout defaults)
  4. /etc/halbert/models.yml      (system-wide install)

The *layer order* — :func:`resolve_layers`, lowest precedence first — is
``global`` then, only when an operator declared one, ``workspace``. Merging
those layers is :mod:`model.config_layers`; this module only says where they
are. See that module for why there is no discovered project layer.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import List, NamedTuple, Optional

from ..utils.platform import get_config_dir

logger = logging.getLogger("halbert.model.config_locator")

ENV_VAR = "HALBERT_MODELS_CONFIG"
WORKSPACE_ENV_VAR = "HALBERT_WORKSPACE_MODELS_CONFIG"

GLOBAL_LAYER = "global"
WORKSPACE_LAYER = "workspace"


class FileLayer(NamedTuple):
    """One existing config file and the layer it supplies."""

    name: str
    path: Path


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


def workspace_models_config(declared: Optional[str] = None) -> Optional[Path]:
    """The workspace layer's file, or None when no operator declared one.

    Declared by $HALBERT_WORKSPACE_MODELS_CONFIG or by ``declared`` (the
    ``workspace_models_config`` setting, read out of the global file by the
    caller — this module does not parse YAML). Never found by searching:
    Halbert identifies as the host rather than being pointed at a checkout, and
    :func:`repo_root` is *Halbert's own* tree, so a discovered project layer
    would silently scope a user's configuration to Halbert's source.
    """
    raw = os.environ.get(WORKSPACE_ENV_VAR) or declared
    if not raw:
        return None
    path = Path(str(raw)).expanduser()
    if not path.is_file():
        logger.warning(
            "workspace models config %s does not exist; the workspace layer is "
            "not applied", path
        )
        return None
    return path


def resolve_layers(
    declared_workspace: Optional[str] = None, include_repo: bool = False
) -> List[FileLayer]:
    """Every config file that contributes, lowest precedence first.

    Only files that exist are returned, so an empty list means "built-in
    defaults only". This replaces first-existing-wins for readers that layer;
    :func:`find_models_config` still answers "which single file is the global
    one" for the migrating reader and for every writer.

    ``include_repo`` defaults to *off* because the store reads and writes with
    the repo checkout excluded: defaulting it on described a global layer
    nobody reads, so a caller taking the default would report Halbert's own
    packaged template as the file the user's slots came from.
    """
    layers: List[FileLayer] = []
    global_path = find_models_config(include_repo=include_repo)
    if global_path is not None:
        layers.append(FileLayer(GLOBAL_LAYER, global_path))
    workspace_path = workspace_models_config(declared_workspace)
    if workspace_path is not None:
        layers.append(FileLayer(WORKSPACE_LAYER, workspace_path))
    return layers
