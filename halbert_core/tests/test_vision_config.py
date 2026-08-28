# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for the vision config module."""

import pytest
import tempfile
import os
from pathlib import Path


class TestVisionConfigDefaults:
    def test_defaults_are_disabled(self):
        from halbert_core.vision.config import VisionConfig
        cfg = VisionConfig()
        assert cfg.screen_capture.enabled is False
        assert cfg.webcam.enabled is False

    def test_default_quality_and_dims(self):
        from halbert_core.vision.config import VisionConfig
        cfg = VisionConfig()
        assert cfg.screen_capture.quality == 85
        assert cfg.screen_capture.max_dimension == 1568
        assert cfg.webcam.quality == 85
        assert cfg.webcam.max_dimension == 768


class TestLoadSaveConfig:
    def test_load_returns_defaults_when_no_file(self, tmp_path, monkeypatch):
        from halbert_core.vision import config as mod
        monkeypatch.setattr(mod, '_config_path', lambda: tmp_path / "nonexistent.yml")
        cfg = mod.load_config()
        assert cfg.screen_capture.enabled is False
        assert cfg.webcam.enabled is False

    def test_save_then_load_roundtrip(self, tmp_path, monkeypatch):
        from halbert_core.vision import config as mod
        path = tmp_path / "vision_config.yml"
        monkeypatch.setattr(mod, '_config_path', lambda: path)

        cfg = mod.VisionConfig(
            screen_capture=mod.ScreenCaptureConfig(enabled=True, quality=90, max_dimension=1024),
            webcam=mod.WebcamConfig(enabled=True, camera_index=1, quality=75, max_dimension=512),
        )
        mod.save_config(cfg)
        assert path.exists()

        loaded = mod.load_config()
        assert loaded.screen_capture.enabled is True
        assert loaded.screen_capture.quality == 90
        assert loaded.screen_capture.max_dimension == 1024
        assert loaded.webcam.enabled is True
        assert loaded.webcam.camera_index == 1
        assert loaded.webcam.quality == 75
        assert loaded.webcam.max_dimension == 512

    def test_load_partial_config(self, tmp_path, monkeypatch):
        """A config file with only some fields should fill defaults for the rest."""
        from halbert_core.vision import config as mod
        path = tmp_path / "vision_config.yml"
        path.write_text("screen_capture:\n  enabled: true\n")
        monkeypatch.setattr(mod, '_config_path', lambda: path)

        cfg = mod.load_config()
        assert cfg.screen_capture.enabled is True
        assert cfg.screen_capture.quality == 85  # Default
        assert cfg.webcam.enabled is False  # Default

    def test_load_corrupt_file_returns_defaults(self, tmp_path, monkeypatch):
        from halbert_core.vision import config as mod
        path = tmp_path / "vision_config.yml"
        path.write_text("::: invalid yaml :::")
        monkeypatch.setattr(mod, '_config_path', lambda: path)

        cfg = mod.load_config()
        assert cfg.screen_capture.enabled is False
        assert cfg.webcam.enabled is False


class TestEnabledChecks:
    def test_is_screen_capture_enabled_false_by_default(self, tmp_path, monkeypatch):
        from halbert_core.vision import config as mod
        monkeypatch.setattr(mod, '_config_path', lambda: tmp_path / "nonexistent.yml")
        assert mod.is_screen_capture_enabled() is False

    def test_is_webcam_enabled_false_by_default(self, tmp_path, monkeypatch):
        from halbert_core.vision import config as mod
        monkeypatch.setattr(mod, '_config_path', lambda: tmp_path / "nonexistent.yml")
        assert mod.is_webcam_enabled() is False

    def test_is_screen_capture_enabled_true_after_save(self, tmp_path, monkeypatch):
        from halbert_core.vision import config as mod
        path = tmp_path / "vision_config.yml"
        monkeypatch.setattr(mod, '_config_path', lambda: path)
        cfg = mod.VisionConfig(
            screen_capture=mod.ScreenCaptureConfig(enabled=True)
        )
        mod.save_config(cfg)
        assert mod.is_screen_capture_enabled() is True
