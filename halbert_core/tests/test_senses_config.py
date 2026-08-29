# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for SensesConfig / SensesVisionConfig in being_config."""
import tempfile
import os
from pathlib import Path

import pytest

from halbert_core.config.being_config import (
    BeingConfig,
    SensesConfig,
    SensesVisionConfig,
    load_being_config,
    save_being_config,
)


class TestSensesVisionConfig:
    def test_defaults(self):
        cfg = SensesVisionConfig()
        assert cfg.enabled is False
        assert cfg.proactive_monitoring is False
        assert cfg.capture_on_intent is True
        assert cfg.capture_on_error is False
        assert cfg.interval_seconds == 60
        assert "error" in cfg.error_patterns
        assert "failed" in cfg.error_patterns

    def test_custom_values(self):
        cfg = SensesVisionConfig(
            enabled=True,
            proactive_monitoring=True,
            capture_on_intent=False,
            capture_on_error=True,
            interval_seconds=30,
            error_patterns=["kernel panic", "cuda error"],
        )
        assert cfg.enabled is True
        assert cfg.proactive_monitoring is True
        assert cfg.capture_on_intent is False
        assert cfg.capture_on_error is True
        assert cfg.interval_seconds == 30
        assert cfg.error_patterns == ["kernel panic", "cuda error"]


class TestSensesConfig:
    def test_defaults(self):
        cfg = SensesConfig()
        assert isinstance(cfg.vision, SensesVisionConfig)
        assert cfg.vision.enabled is False

    def test_custom_vision(self):
        cfg = SensesConfig(vision=SensesVisionConfig(enabled=True, interval_seconds=15))
        assert cfg.vision.enabled is True
        assert cfg.vision.interval_seconds == 15


class TestBeingConfigSenses:
    def test_default_senses(self):
        cfg = BeingConfig()
        assert isinstance(cfg.senses, SensesConfig)
        assert cfg.senses.vision.enabled is False
        assert cfg.senses.vision.capture_on_intent is True

    def test_senses_via_dict_construction(self):
        """BeingConfig(senses={...}) should coerce dict to SensesConfig."""
        cfg = BeingConfig(senses={"vision": {"enabled": True, "interval_seconds": 30}})
        assert isinstance(cfg.senses, SensesConfig)
        assert cfg.senses.vision.enabled is True
        assert cfg.senses.vision.interval_seconds == 30

    def test_senses_via_from_dict(self):
        """BeingConfig.from_dict should unpack nested senses dict."""
        d = {"senses": {"vision": {"enabled": True, "proactive_monitoring": True}}}
        cfg = BeingConfig.from_dict(d)
        assert isinstance(cfg.senses, SensesConfig)
        assert cfg.senses.vision.enabled is True
        assert cfg.senses.vision.proactive_monitoring is True
        # Defaults preserved for unspecified fields
        assert cfg.senses.vision.capture_on_intent is True
        assert cfg.senses.vision.interval_seconds == 60

    def test_validate_interval_too_low(self):
        cfg = BeingConfig(senses={"vision": {"interval_seconds": 5}})
        with pytest.raises(ValueError, match="interval_seconds must be >= 10"):
            cfg.validate()

    def test_validate_interval_ok(self):
        cfg = BeingConfig(senses={"vision": {"interval_seconds": 10}})
        cfg.validate()  # should not raise

    def test_round_trip_save_load(self):
        cfg = BeingConfig(senses={"vision": {"enabled": True, "interval_seconds": 30}})
        with tempfile.NamedTemporaryFile(suffix=".yml", mode="w", delete=False) as f:
            path = f.name
        try:
            save_being_config(cfg, path)
            loaded = load_being_config(path)
            assert loaded.senses.vision.enabled is True
            assert loaded.senses.vision.interval_seconds == 30
            # Defaults preserved
            assert loaded.senses.vision.capture_on_intent is True
            assert loaded.senses.vision.capture_on_error is False
        finally:
            os.unlink(path)

    def test_round_trip_with_error_patterns(self):
        cfg = BeingConfig(senses={"vision": {
            "enabled": True,
            "error_patterns": ["kernel panic", "cuda error"],
        }})
        with tempfile.NamedTemporaryFile(suffix=".yml", mode="w", delete=False) as f:
            path = f.name
        try:
            save_being_config(cfg, path)
            loaded = load_being_config(path)
            assert loaded.senses.vision.enabled is True
            assert "kernel panic" in loaded.senses.vision.error_patterns
            assert "cuda error" in loaded.senses.vision.error_patterns
        finally:
            os.unlink(path)

    def test_to_dict_contains_senses(self):
        cfg = BeingConfig()
        d = cfg.to_dict()
        assert "senses" in d
        assert "vision" in d["senses"]
        assert d["senses"]["vision"]["enabled"] is False
        assert d["senses"]["vision"]["capture_on_intent"] is True

    def test_from_dict_ignores_unknown_senses_fields(self):
        """Unknown fields in senses.vision should be silently dropped."""
        d = {"senses": {"vision": {"enabled": True, "unknown_field": "ignored"}}}
        cfg = BeingConfig.from_dict(d)
        assert cfg.senses.vision.enabled is True
        # Should not have the unknown field
        assert not hasattr(cfg.senses.vision, "unknown_field")
