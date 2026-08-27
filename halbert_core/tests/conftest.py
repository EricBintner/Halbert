# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Shared fixtures."""
import pytest

from halbert_core.model.config_locator import ENV_VAR, WORKSPACE_ENV_VAR


@pytest.fixture(autouse=True)
def _no_declared_workspace_layer(monkeypatch):
    """No suite inherits a workspace layer from the developer's shell.

    Unlike $HALBERT_MODELS_CONFIG this one is *additive*: an exported overlay
    does not have to be the file under test to reach it, it only has to declare
    a pin, and every reader that resolves the layers then sees it. So it is
    cleared for every test, not only the ones that ask for a temp config dir.
    """
    monkeypatch.delenv(WORKSPACE_ENV_VAR, raising=False)


@pytest.fixture
def models_config_dir(monkeypatch, tmp_path):
    """Point every models.yml reader/writer at an empty temp user config dir.

    Nothing under test may touch the developer's real models.yml.
    """
    user = tmp_path / "user"
    monkeypatch.setattr("halbert_core.model.config_locator.get_config_dir", lambda: user)
    monkeypatch.setattr("halbert_core.model.config_locator.repo_root", lambda: tmp_path / "repo")
    monkeypatch.delenv(ENV_VAR, raising=False)
    return user
