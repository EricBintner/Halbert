# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for the redaction module."""

import pytest
from unittest.mock import patch, MagicMock


class TestBlocklist:
    def test_default_blocklist_has_common_keywords(self):
        from halbert_core.vision.redact import DEFAULT_BLOCKLIST
        assert "password" in DEFAULT_BLOCKLIST
        assert "token" in DEFAULT_BLOCKLIST
        assert "api_key" in DEFAULT_BLOCKLIST
        assert "secret" in DEFAULT_BLOCKLIST

    def test_get_blocklist_returns_defaults_when_no_config(self):
        from halbert_core.vision.redact import get_blocklist, DEFAULT_BLOCKLIST
        assert get_blocklist(None) == DEFAULT_BLOCKLIST

    def test_get_blocklist_uses_config_when_provided(self):
        from halbert_core.vision.redact import get_blocklist
        from halbert_core.vision.config import VisionConfig, RedactionConfig

        cfg = VisionConfig(
            redaction=RedactionConfig(
                enabled=True,
                blocklist=["custom_secret", "my_api_key"],
            )
        )
        result = get_blocklist(cfg)
        assert "custom_secret" in result
        assert "my_api_key" in result

    def test_get_blocklist_falls_to_defaults_when_empty(self):
        from halbert_core.vision.redact import get_blocklist, DEFAULT_BLOCKLIST
        from halbert_core.vision.config import VisionConfig, RedactionConfig

        cfg = VisionConfig(redaction=RedactionConfig(enabled=True, blocklist=[]))
        assert get_blocklist(cfg) == DEFAULT_BLOCKLIST


class TestShouldRedact:
    def test_defaults_to_false(self):
        from halbert_core.vision.redact import should_redact
        assert should_redact(None) is False

    def test_true_when_enabled_in_config(self):
        from halbert_core.vision.redact import should_redact
        from halbert_core.vision.config import VisionConfig, RedactionConfig

        cfg = VisionConfig(redaction=RedactionConfig(enabled=True))
        assert should_redact(cfg) is True

    def test_false_when_disabled_in_config(self):
        from halbert_core.vision.redact import should_redact
        from halbert_core.vision.config import VisionConfig, RedactionConfig

        cfg = VisionConfig(redaction=RedactionConfig(enabled=False))
        assert should_redact(cfg) is False


class TestRedactImage:
    def test_returns_original_when_ocr_unavailable(self):
        from halbert_core.vision.redact import redact_image

        with patch("halbert_core.vision.ocr.is_available", return_value=False):
            result = redact_image(b"fakeimage")

        assert result == b"fakeimage"

    def test_returns_original_when_empty_blocklist(self):
        from halbert_core.vision.redact import redact_image

        result = redact_image(b"fakeimage", blocklist=[])
        assert result == b"fakeimage"

    def test_returns_original_when_no_matches(self):
        from halbert_core.vision.redact import redact_image

        with patch("halbert_core.vision.ocr.is_available", return_value=True), \
             patch("halbert_core.vision.ocr._detect_backend", return_value="vision"), \
             patch("halbert_core.vision.redact._find_sensitive_regions", return_value=[]):
            result = redact_image(b"fakeimage", blocklist=["password"])

        assert result == b"fakeimage"


class TestRedactionConfig:
    def test_redaction_defaults_to_disabled(self):
        from halbert_core.vision.config import VisionConfig
        cfg = VisionConfig()
        assert cfg.redaction.enabled is False
        assert cfg.redaction.blocklist == []

    def test_load_config_includes_redaction_defaults(self, monkeypatch):
        from halbert_core.vision.config import load_config

        # Point to non-existent file
        monkeypatch.setattr("halbert_core.vision.config._config_path",
                            lambda: __import__("pathlib").Path("/nonexistent/vision_config.yml"))
        cfg = load_config()
        assert cfg.redaction.enabled is False
        assert cfg.redaction.blocklist == []
