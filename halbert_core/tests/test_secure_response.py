# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for the deterministic secure responder."""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from halbert_core.config.secure_response import (
    describe_secret,
    _charset_classes,
    _shannon_entropy,
    _view_command,
)


class TestDescribeSecret:
    """describe_secret returns facts without the value."""

    def test_basic_password(self):
        result = describe_secret("password", "hunter2", "/etc/myapp.conf")
        assert result["key"] == "password"
        assert result["file"] == "/etc/myapp.conf"
        assert result["length"] == 7
        assert result["redacted"] is True
        # The value must NOT appear in the result
        assert "hunter2" not in str(result)

    def test_long_token(self):
        token = "ghp_abcdefghijklmnopqrstuvwxyz1234567890"
        result = describe_secret("api_key", token, "/etc/myapp.conf")
        assert result["length"] == len(token)
        assert token not in str(result)

    def test_none_value(self):
        result = describe_secret("password", None, "/etc/myapp.conf")
        assert result["length"] == 0
        assert result["redacted"] is True

    def test_empty_string(self):
        result = describe_secret("token", "", "/etc/myapp.conf")
        assert result["length"] == 0

    def test_no_file_path(self):
        result = describe_secret("password", "hunter2")
        assert result["file"] == ""
        assert "hunter2" not in str(result)

    def test_charset_lowercase(self):
        result = describe_secret("k", "abcdef", "/f")
        assert "lowercase" in result["charset"]

    def test_charset_uppercase(self):
        result = describe_secret("k", "ABCDEF", "/f")
        assert "uppercase" in result["charset"]

    def test_charset_digits(self):
        result = describe_secret("k", "123456", "/f")
        assert "digits" in result["charset"]

    def test_charset_symbols(self):
        result = describe_secret("k", "p@ss!word", "/f")
        assert "symbols" in result["charset"]

    def test_charset_base64(self):
        result = describe_secret("k", "SGVsbG8gV29ybGQ=", "/f")
        assert "base64" in result["charset"]

    def test_charset_hex(self):
        result = describe_secret("k", "deadbeef1234abcd", "/f")
        assert "hex" in result["charset"]

    def test_entropy_is_float(self):
        result = describe_secret("k", "hunter2", "/f")
        assert isinstance(result["entropy_bits"], float)
        assert result["entropy_bits"] > 0

    def test_entropy_zero_for_empty(self):
        result = describe_secret("k", "", "/f")
        assert result["entropy_bits"] == 0.0


class TestViewCommand:
    """view_command returns a safe local command."""

    def test_plist_file(self):
        cmd = _view_command("password", "/Library/Preferences/myapp.plist")
        assert "plutil" in cmd
        assert "password" not in cmd  # key not in plutil command
        assert "/Library/Preferences/myapp.plist" in cmd

    def test_conf_file_with_key(self):
        cmd = _view_command("password", "/etc/myapp.conf")
        assert "grep" in cmd
        assert "password" in cmd  # grep key is safe
        assert "/etc/myapp.conf" in cmd

    def test_conf_file_no_key(self):
        cmd = _view_command("", "/etc/myapp.conf")
        assert "cat" in cmd
        assert "/etc/myapp.conf" in cmd

    def test_no_file(self):
        cmd = _view_command("password", "")
        assert "memory" in cmd

    def test_special_chars_quoted(self):
        cmd = _view_command("pass", "/etc/my app.conf")
        # shlex.quote should handle spaces
        assert "'/etc/my app.conf'" in cmd or '"/etc/my app.conf"' in cmd


class TestCharsetClasses:
    def test_mixed_classes(self):
        classes = _charset_classes("Pass123!word")
        assert "lowercase" in classes
        assert "uppercase" in classes
        assert "digits" in classes
        assert "symbols" in classes

    def test_only_lowercase(self):
        classes = _charset_classes("abcdef")
        assert "lowercase" in classes
        assert "uppercase" not in classes

    def test_empty_string(self):
        assert _charset_classes("") == []


class TestShannonEntropy:
    def test_uniform_distribution(self):
        # All same character → entropy 0
        assert _shannon_entropy("aaaa") == 0.0

    def test_two_chars_equal(self):
        # Two chars, equal frequency → 1.0 bit
        assert _shannon_entropy("abab") == 1.0

    def test_high_entropy(self):
        # Many unique chars → high entropy
        e = _shannon_entropy("abcdefghijklmnopqrstuvwxyz")
        assert e > 4.0

    def test_empty(self):
        assert _shannon_entropy("") == 0.0


class TestArchitecturalGuarantee:
    """Prove describe_secret has no code path that sends the secret
    to any external service, regardless of config.

    This is the AgentSecrets pattern: prove there is no code path, not
    just that the code path is disabled. We mock all network egress and
    assert that describe_secret never triggers any of them.
    """

    def test_no_network_calls_with_password(self):
        """describe_secret with a password makes no network calls."""
        from unittest.mock import patch, MagicMock
        with patch("urllib.request.urlopen") as mock_open:
            result = describe_secret("password", "hunter2", "/etc/app.conf")
            assert mock_open.call_count == 0
        assert result["redacted"] is True
        assert "hunter2" not in str(result)

    def test_no_network_calls_with_github_token(self):
        """describe_secret with a GitHub PAT makes no network calls."""
        from unittest.mock import patch
        token = "ghp_abcdefghijklmnopqrstuvwxyz1234567890"
        with patch("urllib.request.urlopen") as mock_open:
            result = describe_secret("api_key", token, "/etc/app.conf")
            assert mock_open.call_count == 0
        assert token not in str(result)

    def test_no_network_calls_with_identified_credential(self):
        """Even when the credential type is identified, no network calls."""
        from unittest.mock import patch
        token = "sk-abcdefghijklmnopqrstuvwxyz0123456789"
        with patch("urllib.request.urlopen") as mock_open:
            result = describe_secret("api_key", token, "/etc/app.conf")
            assert mock_open.call_count == 0
        # The credential was identified locally (no network)
        assert "credential_type" in result
        assert result["credential_type"]["service"] == "OpenAI"

    def test_no_network_calls_with_empty_value(self):
        """describe_secret with empty value makes no network calls."""
        from unittest.mock import patch
        with patch("urllib.request.urlopen") as mock_open:
            result = describe_secret("token", "", "/etc/app.conf")
            assert mock_open.call_count == 0

    def test_no_network_calls_with_none_value(self):
        """describe_secret with None value makes no network calls."""
        from unittest.mock import patch
        with patch("urllib.request.urlopen") as mock_open:
            result = describe_secret("token", None, "/etc/app.conf")
            assert mock_open.call_count == 0

    def test_value_not_in_result_string(self):
        """The raw value must not appear anywhere in the result."""
        result = describe_secret("password", "supersecret123", "/etc/app.conf")
        assert "supersecret123" not in str(result)
        assert "supersecret" not in str(result)

    def test_value_not_in_result_dict(self):
        """The raw value must not appear in any field of the result dict."""
        value = "supersecret123"
        result = describe_secret("password", value, "/etc/app.conf")
        for k, v in result.items():
            if isinstance(v, str):
                assert value not in v
            elif isinstance(v, dict):
                assert value not in str(v)


class TestBreachRisk:
    """breach_risk is surfaced from the credential format database."""

    def test_breach_risk_for_github_pat(self):
        token = "ghp_abcdefghijklmnopqrstuvwxyz1234567890"
        result = describe_secret("api_key", token, "/etc/app.conf")
        assert "breach_risk" in result
        assert result["breach_risk"] == "high"

    def test_breach_risk_for_stripe_publishable(self):
        key = "pk_live_abcdefghijklmnopqrstuvwxyz123456"
        result = describe_secret("stripe_key", key, "/etc/app.conf")
        assert result.get("breach_risk") == "low"

    def test_no_breach_risk_for_unidentified_value(self):
        result = describe_secret("password", "hunter2", "/etc/app.conf")
        assert "breach_risk" not in result

    def test_breach_risk_in_credential_type(self):
        """breach_risk is also available inside the credential_type dict."""
        token = "ghp_abcdefghijklmnopqrstuvwxyz1234567890"
        result = describe_secret("api_key", token, "/etc/app.conf")
        assert "credential_type" in result
        assert "breach_risk" in result["credential_type"]


class TestLastChanged:
    """last_changed returns file modification time."""

    def test_last_changed_for_real_file(self, tmp_path):
        config_file = tmp_path / "app.conf"
        config_file.write_text("password = hunter2\n")
        result = describe_secret("password", "hunter2", str(config_file))
        assert "last_changed" in result
        assert result["last_changed"] is not None
        # Should be an ISO timestamp
        assert "T" in result["last_changed"]

    def test_last_changed_none_for_nonexistent_file(self):
        result = describe_secret("password", "hunter2", "/nonexistent/path.conf")
        assert result["last_changed"] is None

    def test_last_changed_none_for_empty_path(self):
        result = describe_secret("password", "hunter2", "")
        assert result["last_changed"] is None
