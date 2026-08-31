# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for BeingConfig home variant fields and HA connection."""

import tempfile
from pathlib import Path

import pytest

from halbert_core.config.being_config import (
    BeingConfig,
    VALID_VARIANTS,
    explicit_variant,
    load_being_config,
    save_being_config,
)


class TestExplicitVariant:
    """explicit_variant: variant only counts when being.yml says so.

    BeingConfig.variant defaults to "sysadmin" and load_being_config returns
    defaults for a missing file, so the dataclass cannot distinguish "being.yml
    says sysadmin" from "being.yml says nothing". Variant resolution
    (cognition_wiring._get_variant) needs that distinction or the
    HALBERT_VARIANT env var is dead on env-only deployments.

    Note: explicit_variant() reads from the default being.yml path and raises
    ValueError on invalid variants (unlike u6's load_explicit_variant which
    accepted a path and returned None). These tests mock the default path.
    """

    def test_missing_file_is_unset(self, monkeypatch):
        import halbert_core.config.being_config as bc
        monkeypatch.setattr(bc, "_default_path", lambda: __import__("pathlib").Path("/nonexistent/being.yml"))
        assert explicit_variant() is None

    def test_explicit_variant_is_returned(self, monkeypatch, tmp_path):
        import halbert_core.config.being_config as bc
        path = tmp_path / "being.yml"
        save_being_config(BeingConfig(variant="home"), str(path))
        monkeypatch.setattr(bc, "_default_path", lambda: path)
        assert explicit_variant() == "home"

    def test_file_without_variant_key_is_unset(self, monkeypatch, tmp_path):
        import halbert_core.config.being_config as bc
        path = tmp_path / "being.yml"
        path.write_text("persona_name: Halbert\n")
        monkeypatch.setattr(bc, "_default_path", lambda: path)
        assert explicit_variant() is None

    def test_invalid_variant_raises_value_error(self, monkeypatch, tmp_path):
        import halbert_core.config.being_config as bc
        path = tmp_path / "being.yml"
        path.write_text("variant: not-a-variant\n")
        monkeypatch.setattr(bc, "_default_path", lambda: path)
        with pytest.raises(ValueError, match="Invalid variant"):
            explicit_variant()

    def test_non_dict_yaml_is_unset(self, monkeypatch, tmp_path):
        import halbert_core.config.being_config as bc
        path = tmp_path / "being.yml"
        path.write_text("- just\n- a\n- list\n")
        monkeypatch.setattr(bc, "_default_path", lambda: path)
        assert explicit_variant() is None


class TestHomeLightVariant:
    """home is a valid variant for thin clients (N100/Pi)."""

    def test_home_light_in_valid_variants(self):
        assert "home" in VALID_VARIANTS

    def test_home_light_variant_validates(self):
        cfg = BeingConfig(variant="home")
        cfg.validate()

    def test_sysadmin_still_valid(self):
        cfg = BeingConfig(variant="sysadmin")
        cfg.validate()

    def test_home_still_valid(self):
        cfg = BeingConfig(variant="home")
        cfg.validate()

    def test_invalid_variant_rejected(self):
        cfg = BeingConfig(variant="bogus")
        try:
            cfg.validate()
            assert False, "Should have raised ValueError"
        except ValueError:
            pass


class TestHAConnectionFields:
    """ha_url and ha_token fields for light variant HA connection."""

    def test_defaults_are_none(self):
        cfg = BeingConfig()
        assert cfg.ha_url is None
        assert cfg.ha_token is None

    def test_set_ha_fields(self):
        cfg = BeingConfig(
            variant="home",
            ha_url="http://homeassistant.local:8123",
            ha_token="abc123",
        )
        cfg.validate()
        assert cfg.ha_url == "http://homeassistant.local:8123"
        assert cfg.ha_token == "abc123"

    def test_ha_fields_serialize_to_yaml(self):
        cfg = BeingConfig(
            variant="home",
            ha_url="http://ha.local:8123",
            ha_token="long-lived-token",
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "being.yml"
            save_being_config(cfg, str(path))
            loaded = load_being_config(str(path))
            assert loaded.variant == "home"
            assert loaded.ha_url == "http://ha.local:8123"
            assert loaded.ha_token == "long-lived-token"

    def test_ha_fields_none_not_written_to_yaml(self):
        """None fields should be stripped from YAML for cleaner output."""
        cfg = BeingConfig()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "being.yml"
            save_being_config(cfg, str(path))
            text = path.read_text()
            assert "ha_url" not in text
            assert "ha_token" not in text

    def test_round_trip_preserves_all_fields(self):
        cfg = BeingConfig(
            variant="home",
            ha_url="http://ha:8123",
            ha_token="tok",
            scene_context="smart home automation",
            persona_id_override="home",
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "being.yml"
            save_being_config(cfg, str(path))
            loaded = load_being_config(str(path))
            assert loaded.variant == "home"
            assert loaded.ha_url == "http://ha:8123"
            assert loaded.ha_token == "tok"
            assert loaded.scene_context == "smart home automation"
            assert loaded.persona_id_override == "home"
