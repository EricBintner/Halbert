# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for BeingConfig home-light variant fields and HA connection."""

import tempfile
from pathlib import Path

from halbert_core.config.being_config import (
    BeingConfig,
    VALID_VARIANTS,
    load_being_config,
    save_being_config,
)


class TestHomeLightVariant:
    """home-light is a valid variant for thin clients (N100/Pi)."""

    def test_home_light_in_valid_variants(self):
        assert "home-light" in VALID_VARIANTS

    def test_home_light_variant_validates(self):
        cfg = BeingConfig(variant="home-light")
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
            variant="home-light",
            ha_url="http://homeassistant.local:8123",
            ha_token="abc123",
        )
        cfg.validate()
        assert cfg.ha_url == "http://homeassistant.local:8123"
        assert cfg.ha_token == "abc123"

    def test_ha_fields_serialize_to_yaml(self):
        cfg = BeingConfig(
            variant="home-light",
            ha_url="http://ha.local:8123",
            ha_token="long-lived-token",
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "being.yml"
            save_being_config(cfg, str(path))
            loaded = load_being_config(str(path))
            assert loaded.variant == "home-light"
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
            variant="home-light",
            ha_url="http://ha:8123",
            ha_token="tok",
            scene_context="smart home automation",
            persona_id_override="home",
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "being.yml"
            save_being_config(cfg, str(path))
            loaded = load_being_config(str(path))
            assert loaded.variant == "home-light"
            assert loaded.ha_url == "http://ha:8123"
            assert loaded.ha_token == "tok"
            assert loaded.scene_context == "smart home automation"
            assert loaded.persona_id_override == "home"
