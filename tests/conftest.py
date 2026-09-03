# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Shared fixtures for the top-level suite.

This root had no conftest at all, so nothing isolated it from the
developer's real data directory.
"""
import pytest


@pytest.fixture(autouse=True)
def _isolated_data_and_log_dirs(monkeypatch, tmp_path):
    """No suite writes the real change ledger or the real audit chain.

    ``continuity/state_store.default_state_db_path`` and ``obs/audit``
    resolve through ``utils.paths.data_dir()`` / ``log_dir()`` at call time,
    so without this every test that exercises a write path -- ``write_config``,
    the diff-apply route, an editor save, a chmod by proposal, a thread close
    -- appends to the developer's own ``~/.local/share/halbert/state_ledger.db``
    and to the tamper-evident audit log.

    That is worse than ordinary test pollution. The ledger's whole purpose is
    to be a trustworthy record of why things changed; filling it with pytest
    tmp paths and fixture reasons corrupts exactly the thing the feature
    exists to make trustworthy, and appends to a hash chain that is meant to
    be evidence. The canon-store fixture above exists because the same class
    of bug already happened once to a different store.

    A test wanting a specific layout still overrides these itself: its own
    ``monkeypatch.setenv`` runs after this fixture and wins.
    """
    monkeypatch.setenv("HALBERT_DATA_DIR", str(tmp_path / "_data"))
    monkeypatch.setenv("HALBERT_LOG_DIR", str(tmp_path / "_logs"))
