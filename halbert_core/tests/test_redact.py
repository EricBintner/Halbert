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


class TestRegexPatterns:
    def test_default_patterns_have_common_secret_formats(self):
        from halbert_core.vision.redact import DEFAULT_REGEX_PATTERNS
        # Should have patterns for AWS, GitHub, Slack, Stripe, etc.
        pattern_strings = [p.pattern for p in DEFAULT_REGEX_PATTERNS]
        assert any("AKIA" in p for p in pattern_strings)  # AWS
        assert any("ghp_" in p for p in pattern_strings)  # GitHub
        assert any("xox" in p for p in pattern_strings)   # Slack
        assert any("sk_" in p for p in pattern_strings)   # Stripe

    def test_aws_key_matches(self):
        from halbert_core.vision.redact import _matches_sensitive, DEFAULT_REGEX_PATTERNS
        assert _matches_sensitive("AKIAIOSFODNN7EXAMPLE", [], DEFAULT_REGEX_PATTERNS)

    def test_github_token_matches(self):
        from halbert_core.vision.redact import _matches_sensitive, DEFAULT_REGEX_PATTERNS
        token = "ghp_" + "A" * 36
        assert _matches_sensitive(token, [], DEFAULT_REGEX_PATTERNS)

    def test_jwt_matches(self):
        from halbert_core.vision.redact import _matches_sensitive, DEFAULT_REGEX_PATTERNS
        jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        assert _matches_sensitive(jwt, [], DEFAULT_REGEX_PATTERNS)

    def test_pem_key_block_matches(self):
        from halbert_core.vision.redact import _matches_sensitive, DEFAULT_REGEX_PATTERNS
        pem = "-----BEGIN RSA PRIVATE KEY-----"
        assert _matches_sensitive(pem, [], DEFAULT_REGEX_PATTERNS)

    def test_non_secret_text_does_not_match_regex(self):
        from halbert_core.vision.redact import _matches_sensitive, DEFAULT_REGEX_PATTERNS
        assert not _matches_sensitive("Hello World 12345", [], DEFAULT_REGEX_PATTERNS)
        assert not _matches_sensitive("ls -la /tmp", [], DEFAULT_REGEX_PATTERNS)

    def test_keyword_takes_priority_over_regex(self):
        from halbert_core.vision.redact import _matches_sensitive, DEFAULT_REGEX_PATTERNS
        # "password" keyword matches, no need for regex
        assert _matches_sensitive("password: hunter2", ["password"], DEFAULT_REGEX_PATTERNS)

    def test_regex_catches_what_keywords_miss(self):
        from halbert_core.vision.redact import _matches_sensitive, DEFAULT_REGEX_PATTERNS
        # AWS key has no keyword, only regex catches it
        assert _matches_sensitive("AKIAIOSFODNN7EXAMPLE", [], DEFAULT_REGEX_PATTERNS)
        # But with keywords only, it's missed
        assert not _matches_sensitive("AKIAIOSFODNN7EXAMPLE", ["password", "secret"], [])

    def test_get_regex_patterns_returns_compiled(self):
        from halbert_core.vision.redact import get_regex_patterns
        import re
        patterns = get_regex_patterns()
        assert all(isinstance(p, re.Pattern) for p in patterns)
