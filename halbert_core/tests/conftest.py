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


@pytest.fixture
def capability_registry(monkeypatch):
    """Isolated capability registry (F5): probes off, preset-driven.

    The variant gates these suites used to patch
    (``cognition_wiring._get_variant``, ``config_wizard._is_home_variant``)
    became *presets* when F5 converted gating to capability probing: the
    decision now reads this registry, and the registry's probes read the
    developer's real being.yml/models.yml. Tests that pin
    variant-conditional behavior control it here instead — deterministically,
    on any machine.

    Returns a controller: ``set_variant("home" | "sysadmin")`` re-probes
    from that variant's preset; ``set_capability(name, bool)`` pins one
    capability explicitly (the being.yml ``capabilities:`` override path).
    """
    import halbert_core.capabilities as caps

    reg = caps.CapabilityRegistry()
    state = {"variant": "sysadmin", "overrides": {}}
    reg._load_config = lambda: (state["variant"], dict(state["overrides"]))

    monkeypatch.setattr(caps, "_PROBES", {})
    monkeypatch.setattr(caps, "_registry", reg)

    class _Controller:
        def set_variant(self, variant):
            state["variant"] = variant
            self._reprobe()

        def set_capability(self, name, value):
            state["overrides"][name] = value
            self._reprobe()

        @staticmethod
        def _reprobe():
            # Drop the cache so the next has_capability() re-probes with
            # the new preset/override state.
            reg._probed = False
            reg._capabilities.clear()

    return _Controller()
