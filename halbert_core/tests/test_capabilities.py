# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for the capability registry — variant-as-hint refactor (F5)."""
import os
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from halbert_core.capabilities import (
    CapabilityRegistry,
    get_capability_registry,
    has_capability,
    reset_registry,
    ALL_CAPABILITIES,
    CAP_TERMINAL,
    CAP_SOURCEPREP,
    CAP_CONFIG_WATCHER,
    CAP_INGESTION,
    CAP_SCHEDULER,
    CAP_DISCOVERY,
    CAP_HA_CONNECTION,
    CAP_LOCAL_LLM,
    CAP_SECURE_MODEL,
    _variant_preset,
    _PRESET_SYSADMIN,
    _PRESET_HOME,
)


@pytest.fixture(autouse=True)
def _reset():
    """Reset the singleton between tests."""
    reset_registry()
    yield
    reset_registry()


# ---------------------------------------------------------------------------
# Variant presets
# ---------------------------------------------------------------------------

class TestVariantPresets:
    def test_sysadmin_preset_has_sysadmin_caps(self):
        preset = _variant_preset("sysadmin")
        assert preset[CAP_TERMINAL] is True
        assert preset[CAP_SOURCEPREP] is True
        assert preset[CAP_CONFIG_WATCHER] is True
        assert preset[CAP_INGESTION] is True
        assert preset[CAP_SCHEDULER] is True
        assert preset[CAP_DISCOVERY] is True

    def test_sysadmin_preset_ha_off_by_default(self):
        preset = _variant_preset("sysadmin")
        assert preset[CAP_HA_CONNECTION] is False

    def test_home_preset_lacks_sysadmin_caps(self):
        preset = _variant_preset("home")
        assert preset[CAP_TERMINAL] is False
        assert preset[CAP_SOURCEPREP] is False
        assert preset[CAP_CONFIG_WATCHER] is False
        assert preset[CAP_INGESTION] is False
        assert preset[CAP_SCHEDULER] is False
        assert preset[CAP_DISCOVERY] is False

    def test_home_preset_has_ha(self):
        preset = _variant_preset("home")
        assert preset[CAP_HA_CONNECTION] is True

    def test_unknown_variant_uses_sysadmin_preset(self):
        preset = _variant_preset("something_else")
        assert preset[CAP_TERMINAL] is True

    def test_preset_returns_copy_not_reference(self):
        p1 = _variant_preset("sysadmin")
        p1[CAP_TERMINAL] = False
        p2 = _variant_preset("sysadmin")
        assert p2[CAP_TERMINAL] is True


# ---------------------------------------------------------------------------
# CapabilityRegistry — basic mechanics
# ---------------------------------------------------------------------------

class TestCapabilityRegistry:
    def test_all_capabilities_have_presets(self):
        """Every capability in ALL_CAPABILITIES must have a preset entry."""
        for variant in ("sysadmin", "home"):
            preset = _variant_preset(variant)
            for cap in ALL_CAPABILITIES:
                assert cap in preset, f"{cap} missing from {variant} preset"

    def test_probe_sets_all_capabilities(self):
        reg = CapabilityRegistry()
        reg._load_config = MagicMock(return_value=("sysadmin", {}))
        # Disable all probes so we test preset defaults
        with patch("halbert_core.capabilities._PROBES", {}):
            reg.probe()
        for cap in ALL_CAPABILITIES:
            assert cap in reg._capabilities

    def test_has_returns_false_for_unknown_capability(self):
        reg = CapabilityRegistry()
        reg._load_config = MagicMock(return_value=("sysadmin", {}))
        with patch("halbert_core.capabilities._PROBES", {}):
            reg.probe()
        assert reg.has("nonexistent") is False

    def test_has_all(self):
        reg = CapabilityRegistry()
        reg._load_config = MagicMock(return_value=("sysadmin", {}))
        with patch("halbert_core.capabilities._PROBES", {}):
            reg.probe()
        assert reg.has_all(CAP_TERMINAL, CAP_SOURCEPREP) is True
        assert reg.has_all(CAP_TERMINAL, "nonexistent") is False

    def test_has_any(self):
        reg = CapabilityRegistry()
        reg._load_config = MagicMock(return_value=("sysadmin", {}))
        with patch("halbert_core.capabilities._PROBES", {}):
            reg.probe()
        assert reg.has_any("nonexistent", CAP_TERMINAL) is True
        assert reg.has_any("nonexistent1", "nonexistent2") is False

    def test_enabled_returns_set_of_enabled(self):
        reg = CapabilityRegistry()
        reg._load_config = MagicMock(return_value=("sysadmin", {}))
        with patch("halbert_core.capabilities._PROBES", {}):
            reg.probe()
        enabled = reg.enabled()
        assert isinstance(enabled, set)
        assert CAP_TERMINAL in enabled
        assert CAP_HA_CONNECTION not in enabled  # sysadmin default

    def test_describe_returns_dict(self):
        reg = CapabilityRegistry()
        reg._load_config = MagicMock(return_value=("sysadmin", {}))
        with patch("halbert_core.capabilities._PROBES", {}):
            reg.probe()
        desc = reg.describe()
        assert isinstance(desc, dict)
        assert len(desc) == len(ALL_CAPABILITIES)

    def test_lazy_probe_on_has(self):
        reg = CapabilityRegistry()
        reg._load_config = MagicMock(return_value=("sysadmin", {}))
        with patch("halbert_core.capabilities._PROBES", {}):
            assert reg._probed is False
            reg.has(CAP_TERMINAL)
            assert reg._probed is True


# ---------------------------------------------------------------------------
# Override resolution — being.yml capabilities: section
# ---------------------------------------------------------------------------

class TestOverrideResolution:
    def test_explicit_override_wins_over_preset(self):
        reg = CapabilityRegistry()
        # sysadmin preset has terminal=True, override to False
        reg._load_config = MagicMock(return_value=("sysadmin", {CAP_TERMINAL: False}))
        with patch("halbert_core.capabilities._PROBES", {}):
            reg.probe()
        assert reg.has(CAP_TERMINAL) is False

    def test_override_enables_ha_on_sysadmin(self):
        """The key use case: sysadmin variant + ha_connection override."""
        reg = CapabilityRegistry()
        reg._load_config = MagicMock(return_value=("sysadmin", {CAP_HA_CONNECTION: True}))
        with patch("halbert_core.capabilities._PROBES", {}):
            reg.probe()
        assert reg.has(CAP_HA_CONNECTION) is True

    def test_override_disables_terminal_on_sysadmin(self):
        reg = CapabilityRegistry()
        reg._load_config = MagicMock(return_value=("sysadmin", {CAP_TERMINAL: False}))
        with patch("halbert_core.capabilities._PROBES", {}):
            reg.probe()
        assert reg.has(CAP_TERMINAL) is False

    def test_override_enables_sourceprep_on_home(self):
        """Home variant + sourceprep override = Mac Studio with both."""
        reg = CapabilityRegistry()
        reg._load_config = MagicMock(return_value=("home", {CAP_SOURCEPREP: True}))
        with patch("halbert_core.capabilities._PROBES", {}):
            reg.probe()
        assert reg.has(CAP_SOURCEPREP) is True
        # Other home defaults remain
        assert reg.has(CAP_TERMINAL) is False

    def test_multiple_overrides(self):
        reg = CapabilityRegistry()
        overrides = {CAP_TERMINAL: True, CAP_SOURCEPREP: True, CAP_HA_CONNECTION: True}
        reg._load_config = MagicMock(return_value=("home", overrides))
        with patch("halbert_core.capabilities._PROBES", {}):
            reg.probe()
        assert reg.has(CAP_TERMINAL) is True
        assert reg.has(CAP_SOURCEPREP) is True
        assert reg.has(CAP_HA_CONNECTION) is True
        # Non-overridden home defaults remain
        assert reg.has(CAP_INGESTION) is False


# ---------------------------------------------------------------------------
# Probe resolution — active probes override preset defaults
# ---------------------------------------------------------------------------

class TestProbeResolution:
    def test_probe_overrides_preset_default(self):
        """If a probe returns True, it wins over the preset default."""
        reg = CapabilityRegistry()
        reg._load_config = MagicMock(return_value=("sysadmin", {}))
        # CAP_HA_CONNECTION default is False for sysadmin, probe says True
        probes = {CAP_HA_CONNECTION: lambda: True}
        with patch("halbert_core.capabilities._PROBES", probes):
            reg.probe()
        assert reg.has(CAP_HA_CONNECTION) is True

    def test_probe_false_overrides_preset_true(self):
        """If a probe returns False, it wins over the preset default."""
        reg = CapabilityRegistry()
        reg._load_config = MagicMock(return_value=("sysadmin", {}))
        # CAP_TERMINAL default is True for sysadmin, probe says False
        probes = {CAP_TERMINAL: lambda: False}
        with patch("halbert_core.capabilities._PROBES", probes):
            reg.probe()
        assert reg.has(CAP_TERMINAL) is False

    def test_probe_exception_falls_back_to_preset(self):
        """If a probe raises, fall back to the preset default."""
        reg = CapabilityRegistry()
        reg._load_config = MagicMock(return_value=("sysadmin", {}))

        def bad_probe():
            raise RuntimeError("probe failed")

        probes = {CAP_HA_CONNECTION: bad_probe}
        with patch("halbert_core.capabilities._PROBES", probes):
            reg.probe()
        # Falls back to sysadmin preset default (False)
        assert reg.has(CAP_HA_CONNECTION) is False

    def test_explicit_override_wins_over_probe(self):
        """Override > probe > preset."""
        reg = CapabilityRegistry()
        reg._load_config = MagicMock(return_value=("sysadmin", {CAP_HA_CONNECTION: True}))
        # Probe says False, but override says True
        probes = {CAP_HA_CONNECTION: lambda: False}
        with patch("halbert_core.capabilities._PROBES", probes):
            reg.probe()
        assert reg.has(CAP_HA_CONNECTION) is True


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

class TestSingleton:
    def test_get_capability_registry_returns_singleton(self):
        r1 = get_capability_registry()
        r2 = get_capability_registry()
        assert r1 is r2

    def test_reset_registry_clears_singleton(self):
        r1 = get_capability_registry()
        reset_registry()
        r2 = get_capability_registry()
        assert r1 is not r2

    def test_has_capability_convenience(self):
        with patch("halbert_core.capabilities._PROBES", {}):
            with patch.object(
                CapabilityRegistry, "_load_config",
                return_value=("sysadmin", {}),
            ):
                assert has_capability(CAP_TERMINAL) is True


# ---------------------------------------------------------------------------
# Backward compatibility — no overrides = same as variant gate
# ---------------------------------------------------------------------------

class TestBackwardCompatibility:
    def test_sysadmin_no_overrides_matches_old_behavior(self):
        """Without overrides, sysadmin gets all sysadmin services."""
        reg = CapabilityRegistry()
        reg._load_config = MagicMock(return_value=("sysadmin", {}))
        with patch("halbert_core.capabilities._PROBES", {}):
            reg.probe()
        # These were gated by `not _is_home` in the old code
        assert reg.has(CAP_TERMINAL) is True
        assert reg.has(CAP_SOURCEPREP) is True
        assert reg.has(CAP_CONFIG_WATCHER) is True
        assert reg.has(CAP_INGESTION) is True
        assert reg.has(CAP_SCHEDULER) is True
        assert reg.has(CAP_DISCOVERY) is True
        # HA was gated by `_is_home` (only home started it)
        assert reg.has(CAP_HA_CONNECTION) is False

    def test_home_no_overrides_matches_old_behavior(self):
        """Without overrides, home skips all sysadmin services."""
        reg = CapabilityRegistry()
        reg._load_config = MagicMock(return_value=("home", {}))
        with patch("halbert_core.capabilities._PROBES", {}):
            reg.probe()
        # These were gated by `not _is_home` in the old code
        assert reg.has(CAP_TERMINAL) is False
        assert reg.has(CAP_SOURCEPREP) is False
        assert reg.has(CAP_CONFIG_WATCHER) is False
        assert reg.has(CAP_INGESTION) is False
        assert reg.has(CAP_SCHEDULER) is False
        assert reg.has(CAP_DISCOVERY) is False
        # HA was gated by `_is_home` (only home started it)
        assert reg.has(CAP_HA_CONNECTION) is True


# ---------------------------------------------------------------------------
# Probe implementation — verify the real probe functions use correct APIs
# ---------------------------------------------------------------------------

class TestProbeImplementations:
    """Verify the probes call the real APIs, not the non-existent get_model_config."""

    def test_probe_local_llm_uses_llm_config_resolve(self):
        """_probe_local_llm should use llm_config.resolve(), not get_model_config."""
        from halbert_core.capabilities import _probe_local_llm
        # Should not raise ImportError — the function must use the real API
        result = _probe_local_llm()
        assert isinstance(result, bool)

    def test_probe_secure_model_uses_llm_config_resolve(self):
        """_probe_secure_model should use llm_config.resolve(), not get_model_config."""
        from halbert_core.capabilities import _probe_secure_model
        result = _probe_secure_model()
        assert isinstance(result, bool)

    def test_probe_local_llm_returns_true_when_local_model_configured(self):
        """With a local model configured, _probe_local_llm should detect it."""
        from halbert_core.capabilities import _probe_local_llm
        from halbert_core.model.llm_config import ResolvedModel

        mock_model = ResolvedModel(
            model="test", url="http://localhost:11434", provider="ollama", api_key=""
        )
        with patch("halbert_core.model.llm_config.resolve", return_value=mock_model):
            assert _probe_local_llm() is True

    def test_probe_local_llm_returns_false_for_remote_only(self):
        """With only remote models, _probe_local_llm should return False."""
        from halbert_core.capabilities import _probe_local_llm
        from halbert_core.model.llm_config import ResolvedModel

        mock_model = ResolvedModel(
            model="test", url="https://api.openai.com", provider="openai", api_key=""
        )
        with patch("halbert_core.model.llm_config.resolve", return_value=mock_model):
            assert _probe_local_llm() is False

    def test_probe_local_llm_returns_false_when_no_model(self):
        """With no model configured, _probe_local_llm should return False."""
        from halbert_core.capabilities import _probe_local_llm
        with patch("halbert_core.model.llm_config.resolve", return_value=None):
            assert _probe_local_llm() is False

    def test_probe_secure_model_returns_true_when_local_secure_configured(self):
        """With a local secure model, _probe_secure_model should detect it."""
        from halbert_core.capabilities import _probe_secure_model
        from halbert_core.model.llm_config import ResolvedModel

        mock_model = ResolvedModel(
            model="secure", url="http://localhost:11434", provider="ollama", api_key=""
        )
        with patch("halbert_core.model.llm_config.resolve", return_value=mock_model):
            with patch("halbert_core.model.llm_config._is_local_url", return_value=True):
                assert _probe_secure_model() is True

    def test_probe_secure_model_returns_false_for_remote_url(self):
        """A secure model pointing at a remote URL should not count."""
        from halbert_core.capabilities import _probe_secure_model
        from halbert_core.model.llm_config import ResolvedModel

        mock_model = ResolvedModel(
            model="secure", url="https://api.openai.com", provider="openai", api_key=""
        )
        with patch("halbert_core.model.llm_config.resolve", return_value=mock_model):
            with patch("halbert_core.model.llm_config._is_local_url", return_value=False):
                assert _probe_secure_model() is False

    def test_probe_secure_model_returns_false_when_not_configured(self):
        """No secure_model slot configured → False."""
        from halbert_core.capabilities import _probe_secure_model
        with patch("halbert_core.model.llm_config.resolve", return_value=None):
            assert _probe_secure_model() is False
