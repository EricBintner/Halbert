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


class TestHomeVariant:
    """home is a valid variant for thin clients (N100/Pi)."""

    def test_home_in_valid_variants(self):
        assert "home" in VALID_VARIANTS

    def test_home_variant_validates(self):
        cfg = BeingConfig(variant="home")
        cfg.validate()

    def test_sysadmin_still_valid(self):
        cfg = BeingConfig(variant="sysadmin")
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


class TestSingularEntityFields:
    """body_name, canonical_memory_url, canonical_thread_url for singular entity mode."""

    def test_defaults_are_empty(self):
        cfg = BeingConfig()
        assert cfg.body_name == ""
        assert cfg.canonical_memory_url == ""
        assert cfg.canonical_thread_url == ""

    def test_body_name_set(self):
        cfg = BeingConfig(body_name="desk")
        cfg.validate()
        assert cfg.body_name == "desk"

    def test_canonical_memory_url_valid(self):
        cfg = BeingConfig(canonical_memory_url="http://n150.lan:8001/api/memory")
        cfg.validate()
        assert cfg.canonical_memory_url == "http://n150.lan:8001/api/memory"

    def test_canonical_thread_url_valid(self):
        cfg = BeingConfig(canonical_thread_url="http://n150.lan:8001/api/conversations")
        cfg.validate()
        assert cfg.canonical_thread_url == "http://n150.lan:8001/api/conversations"

    def test_canonical_memory_url_rejects_non_http(self):
        cfg = BeingConfig(canonical_memory_url="ftp://bad")
        with pytest.raises(ValueError, match="canonical_memory_url must be an http"):
            cfg.validate()

    def test_canonical_thread_url_rejects_non_http(self):
        cfg = BeingConfig(canonical_thread_url="ftp://bad")
        with pytest.raises(ValueError, match="canonical_thread_url must be an http"):
            cfg.validate()

    def test_canonical_urls_without_persona_id_warns(self, caplog):
        """Setting canonical URLs without persona_id_override should log a warning."""
        cfg = BeingConfig(canonical_memory_url="http://n150.lan:8001/api/memory")
        with caplog.at_level("WARNING"):
            cfg.validate()
        assert "persona_id_override" in caplog.text

    def test_singular_entity_round_trip(self):
        cfg = BeingConfig(
            persona_id_override="halbert",
            body_name="desk",
            canonical_memory_url="http://n150.lan:8001/api/memory",
            canonical_thread_url="http://n150.lan:8001/api/conversations",
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "being.yml"
            save_being_config(cfg, str(path))
            loaded = load_being_config(str(path))
            assert loaded.persona_id_override == "halbert"
            assert loaded.body_name == "desk"
            assert loaded.canonical_memory_url == "http://n150.lan:8001/api/memory"
            assert loaded.canonical_thread_url == "http://n150.lan:8001/api/conversations"

    def test_independent_mode_round_trip(self):
        """Independent entity mode: no canonical URLs, own persona_id."""
        cfg = BeingConfig(
            persona_id_override="halbert-desk",
            body_name="desk",
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "being.yml"
            save_being_config(cfg, str(path))
            loaded = load_being_config(str(path))
            assert loaded.persona_id_override == "halbert-desk"
            assert loaded.body_name == "desk"
            assert loaded.canonical_memory_url == ""
            assert loaded.canonical_thread_url == ""

    def test_empty_fields_not_written_to_yaml(self):
        """Empty string fields should not appear in YAML output."""
        cfg = BeingConfig()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "being.yml"
            save_being_config(cfg, str(path))
            text = path.read_text()
            assert "body_name" not in text
            assert "canonical_memory_url" not in text
            assert "canonical_thread_url" not in text
