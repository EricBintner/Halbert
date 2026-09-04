# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""One answer to "where is the config".

There were three resolvers and they disagreed on macOS:

* ``utils/platform.get_config_dir()`` -> ~/Library/Application Support/Halbert
* ``utils/paths.config_dir()``        -> ~/.config/halbert
* ``routes/editor.py:get_config_dir`` -> ~/.config/halbert, hardcoded, and
  honouring no override at all

Both directories were live on the development machine, split by which
resolver a module happened to import: being.yml, models.yml and llm.lock in
one, backups/ and conversations/ in the other -- and being.yml.lock in BOTH,
which is the sharp end of it. The advisory lock is derived from the config
path, so two callers that resolve being.yml differently take out two
different locks and neither sees the other. The one-writer guarantee for the
file that holds the machine's own settings was void.

The platform resolver wins on merit, not seniority: fourteen call sites hold
Halbert's actual config files behind it (being.yml, preferences.yml,
models.yml, gpu_config.yml, web_search.yml, vision_config.yml, the
config-registry probe), while nothing imported paths.config_dir for a config
file at all.
"""

import os
from pathlib import Path

import pytest

from halbert_core.dashboard.routes import editor as editor_routes
from halbert_core.utils import paths as paths_mod
from halbert_core.utils.platform import get_config_dir

RESOLVERS = [
    ("utils.platform.get_config_dir", lambda: Path(get_config_dir())),
    ("utils.paths.config_dir", lambda: Path(paths_mod.config_dir())),
    ("routes.editor.get_config_dir", lambda: Path(editor_routes.get_config_dir())),
]


@pytest.mark.parametrize("name,resolve", RESOLVERS, ids=[r[0] for r in RESOLVERS])
def test_every_resolver_honours_the_override(name, resolve, tmp_path, monkeypatch):
    monkeypatch.setenv("HALBERT_CONFIG_DIR", str(tmp_path / "elsewhere"))
    assert resolve() == tmp_path / "elsewhere", f"{name} ignored HALBERT_CONFIG_DIR"


@pytest.mark.parametrize("name,resolve", RESOLVERS, ids=[r[0] for r in RESOLVERS])
def test_every_resolver_honours_the_legacy_override(name, resolve, tmp_path, monkeypatch):
    monkeypatch.delenv("HALBERT_CONFIG_DIR", raising=False)
    monkeypatch.setenv("Halbert_CONFIG_DIR", str(tmp_path / "legacy"))
    assert resolve() == tmp_path / "legacy", f"{name} ignored the legacy override"


def test_all_three_agree_with_no_override(monkeypatch):
    monkeypatch.delenv("HALBERT_CONFIG_DIR", raising=False)
    monkeypatch.delenv("Halbert_CONFIG_DIR", raising=False)

    answers = {name: resolve() for name, resolve in RESOLVERS}
    assert len(set(answers.values())) == 1, (
        "the resolvers disagree, which is how being.yml and being.yml.lock "
        f"ended up in different directories: {answers}"
    )


def test_the_root_install_location_is_not_lost(monkeypatch):
    """utils/paths had a root branch the platform resolver did not. Folding
    them together must keep it: a root-run Halbert configures the machine,
    not one login account's home."""
    monkeypatch.delenv("HALBERT_CONFIG_DIR", raising=False)
    monkeypatch.delenv("Halbert_CONFIG_DIR", raising=False)
    monkeypatch.setattr(os, "geteuid", lambda: 0, raising=False)

    assert Path(get_config_dir()) == Path("/etc/halbert")


def test_the_editors_backups_live_under_that_one_place(tmp_path, monkeypatch):
    monkeypatch.setenv("HALBERT_CONFIG_DIR", str(tmp_path / "cfg"))

    backup_dir = editor_routes.get_backup_dir("/etc/samba/smb.conf")

    # Not Path.home(): a test that sets the override and still writes into
    # the developer's real home is how ~/.config/halbert/backups filled up
    # with ledger-probe debris in the first place.
    assert str(backup_dir).startswith(str(tmp_path / "cfg"))
