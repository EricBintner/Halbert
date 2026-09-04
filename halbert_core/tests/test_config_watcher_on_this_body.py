# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The watcher runs on the body it is installed on.

The config watcher is the only thing that fills the change ledger without
somebody acting: it notices a file changing on disk and records what, when
and -- as a deterministic rule naming itself -- why. Without it, "what has
changed on this machine" is answerable only about changes Halbert made
itself, which is the smaller and less interesting half.

It did not run here. Two independent reasons, and the second was invisible:

* ``start_config_watcher`` returned early on ``not is_linux()``;
* ``_probe_config_watcher`` looked for config-registry.yml in the config
  directory and /etc/halbert, while ``_find_config_registry`` -- the loader
  that actually opens it -- walks up from the module and finds the one in
  the repo. The capability said no while the manifest sat where the loader
  would have found it.

The gate reads as vestigial rather than considered: config/parser.py has
native plist support, binary and XML, with a comment about why plists must be
checked before the text read -- nobody writes that for Linux. The watcher
uses watchdog, which is cross-platform. capabilities.py names this machine in
its own docstring ("the Mac Studio with both sysadmin and home duties").
"""

from pathlib import Path

import pytest

from halbert_core.dashboard import app as dashboard_app


class TestTheProbeAndTheLoaderAgree:
    def test_the_probe_finds_a_registry_the_loader_would_open(self, monkeypatch, tmp_path):
        """Two answers to "is there something to watch" is how the watcher
        stayed off with its manifest in place."""
        monkeypatch.setenv("HALBERT_CONFIG_DIR", str(tmp_path / "cfg"))
        from halbert_core import capabilities

        found = dashboard_app._find_config_registry()
        assert found is not None, "the loader cannot find the repo's registry"
        assert capabilities._probe_config_watcher() is True

    def test_no_registry_anywhere_means_no_capability(self, monkeypatch, tmp_path):
        from halbert_core import capabilities

        monkeypatch.setenv("HALBERT_CONFIG_DIR", str(tmp_path / "cfg"))
        from halbert_core.config import manifest

        monkeypatch.setattr(manifest, "find_registry", lambda: None)
        assert capabilities._probe_config_watcher() is False


class TestTheRegistryIsChosenByPlatform:
    def test_a_mac_gets_the_mac_registry(self, monkeypatch):
        monkeypatch.setattr(
            "halbert_core.utils.platform.is_macos", lambda: True
        )
        found = dashboard_app._find_config_registry()
        assert found is not None
        assert found.name == "config-registry.macos.yml", (
            "a Mac watching /etc/systemd/*.service watches nothing"
        )

    def test_everything_else_gets_the_generic_one(self, monkeypatch):
        monkeypatch.setattr(
            "halbert_core.utils.platform.is_macos", lambda: False
        )
        found = dashboard_app._find_config_registry()
        assert found is not None
        assert found.name == "config-registry.yml"


class TestTheMacRegistryDescribesThisMachine:
    @pytest.fixture
    def registry(self):
        import yaml

        path = Path(dashboard_app.__file__).resolve()
        for parent in path.parents:
            candidate = parent / "config" / "config-registry.macos.yml"
            if candidate.is_file():
                return yaml.safe_load(candidate.read_text())
        pytest.fail("no macOS registry found")

    def test_it_watches_places_that_exist_on_a_mac(self, registry):
        includes = " ".join(registry["include"])
        assert "/Library/LaunchDaemons" in includes
        assert "/etc/" in includes
        # systemd is Linux. A registry that lists it on a Mac is a registry
        # nobody checked against a Mac.
        assert "systemd" not in includes

    def test_it_does_not_watch_secrets(self, registry):
        excludes = " ".join(registry["exclude"])
        for secret in ("/etc/ssl", "master.passwd", "/etc/sudoers"):
            assert secret in excludes, f"{secret} is watched"

    def test_it_leaves_the_persons_own_login_items_alone(self, registry):
        """~/Library/LaunchAgents is what the person chose to run at login.
        It is theirs, it changes for reasons that are not administration, and
        recording it would make the change ledger a log of somebody's day."""
        includes = " ".join(registry["include"])
        assert "~" not in includes
        assert "/Users/" not in includes

    def test_it_ignores_the_backup_files_the_os_leaves_behind(self, registry):
        # /etc is full of foo~orig and foo~previous from OS upgrades. Each is
        # a "change" that nobody made.
        excludes = " ".join(registry["exclude"])
        assert "~orig" in excludes and "~previous" in excludes
