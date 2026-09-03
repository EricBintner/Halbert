# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import os

import pytest

from halbert_core.utils.paths import config_dir, data_dir, log_dir, data_subdir, log_subdir, state_subdir


@pytest.fixture(autouse=True)
def _see_the_legacy_names(monkeypatch):
    """This module tests the LEGACY ``Halbert_*`` env names.

    The suite-wide isolation fixture sets the modern ``HALBERT_*`` names, and
    the resolvers check those first, so without clearing them these tests
    would assert about a variable they never set.
    """
    for modern in ("HALBERT_CONFIG_DIR", "HALBERT_DATA_DIR", "HALBERT_LOG_DIR"):
        monkeypatch.delenv(modern, raising=False)

def test_env_overrides_take_precedence(tmp_path, monkeypatch):
    c = tmp_path / "cfg"
    d = tmp_path / "dat"
    l = tmp_path / "log"
    c.mkdir()
    d.mkdir()
    l.mkdir()
    monkeypatch.setenv("Halbert_CONFIG_DIR", str(c))
    monkeypatch.setenv("Halbert_DATA_DIR", str(d))
    monkeypatch.setenv("Halbert_LOG_DIR", str(l))
    assert config_dir() == str(c)
    assert data_dir() == str(d)
    assert log_dir() == str(l)


def test_subdir_creates_directories(tmp_path, monkeypatch):
    monkeypatch.setenv("Halbert_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("Halbert_LOG_DIR", str(tmp_path / "logs"))
    p1 = data_subdir("raw", "journald")
    p2 = log_subdir("audit", "2025")
    p3 = state_subdir("journald")
    assert os.path.isdir(p1)
    assert os.path.isdir(p2)
    assert os.path.isdir(p3)
