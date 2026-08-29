# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for credential validation — opt-in per-service API checks."""
from __future__ import annotations

import os
import sys
from unittest.mock import patch, MagicMock

def _mock_urlopen(status=200, body=b'{}', headers=None):
    """Create a mock that works as a context manager for urlopen."""
    mock_resp = MagicMock()
    mock_resp.status = status
    mock_resp.read.return_value = body
    mock_resp.headers = headers or {}
    # Make __enter__ return the mock itself so `with urlopen() as resp` works
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = False
    return mock_resp

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from halbert_core.config.credential_validation import (
    validate_credential,
    available_services,
    _is_validation_enabled,
    _hash_token,
    _validation_cache,
)


class TestValidationConfig:
    """Validation gating respects the being config settings."""

    def test_disabled_by_default(self):
        result = validate_credential("ghp_test", "github")
        assert result["status"] == "disabled"

    def test_enabled_but_service_not_listed(self):
        result = validate_credential(
            "ghp_test", "github", enabled=True, services=["openai"]
        )
        assert result["status"] == "disabled"

    def test_enabled_for_all_when_services_none(self):
        """When enabled=True and services=None, all services are enabled."""
        assert _is_validation_enabled("github", enabled=True, services=None)

    def test_enabled_for_specific_service(self):
        assert _is_validation_enabled("github", enabled=True, services=["github"])

    def test_disabled_when_not_enabled(self):
        assert not _is_validation_enabled("github", enabled=False, services=["github"])

    def test_service_match_case_insensitive(self):
        assert _is_validation_enabled("GitHub", enabled=True, services=["github"])

    def test_available_services(self):
        services = available_services()
        assert "github" in services
        assert "openai" in services
        assert "stripe" in services
        assert "slack" in services


class TestHashToken:
    """_hash_token produces a stable cache key without storing the token."""

    def test_stable_hash(self):
        assert _hash_token("ghp_test123") == _hash_token("ghp_test123")

    def test_different_tokens_different_hashes(self):
        assert _hash_token("ghp_test123") != _hash_token("ghp_test456")

    def test_hash_is_short(self):
        assert len(_hash_token("ghp_test123")) == 16


class TestValidateGitHub:
    """GitHub token validation via mocked API calls."""

    def test_valid_github_token(self):
        mock = _mock_urlopen(
            status=200,
            body=b'{"login": "testuser"}',
            headers={"X-OAuth-Scopes": "repo, read:org"},
        )
        with patch("urllib.request.urlopen", return_value=mock):
            result = validate_credential(
                "ghp_validtoken1234567890abcdefghijklmnopqrstuvwxyz",
                "github",
                enabled=True,
            )

        assert result["status"] == "valid"
        assert result["service"] == "GitHub"
        assert result["user"] == "testuser"
        assert "repo" in result["scopes"]

    def test_invalid_github_token(self):
        import urllib.error
        error = urllib.error.HTTPError(
            "https://api.github.com/user", 401, "Unauthorized",
            MagicMock(), None,
        )
        with patch("urllib.request.urlopen", side_effect=error):
            result = validate_credential(
                "ghp_invalidtoken1234567890abcdefghijklmnopqrstuvwxyz",
                "github",
                enabled=True,
            )

        assert result["status"] == "invalid"
        assert result["service"] == "GitHub"

    def test_network_error_returns_error_status(self):
        with patch("urllib.request.urlopen", side_effect=Exception("timeout")):
            result = validate_credential(
                "ghp_networkerrortoken1234567890abcdefghijklmnopqr",
                "github",
                enabled=True,
            )

        assert result["status"] == "error"
        assert "timeout" in result["detail"]


class TestValidateOpenAI:
    """OpenAI key validation via mocked API calls."""

    def test_valid_openai_key(self):
        mock = _mock_urlopen(
            status=200,
            body=b'{"data": [{"id": "gpt-4"}, {"id": "gpt-3.5-turbo"}]}',
        )
        with patch("urllib.request.urlopen", return_value=mock):
            result = validate_credential(
                "sk-validkey1234567890abcdef",
                "openai",
                enabled=True,
            )

        assert result["status"] == "valid"
        assert result["service"] == "OpenAI"
        assert result["models_available"] == 2

    def test_invalid_openai_key(self):
        import urllib.error
        error = urllib.error.HTTPError(
            "https://api.openai.com/v1/models", 401, "Unauthorized",
            MagicMock(), None,
        )
        with patch("urllib.request.urlopen", side_effect=error):
            result = validate_credential(
                "sk-invalidkey1234567890abcdef",
                "openai",
                enabled=True,
            )

        assert result["status"] == "invalid"


class TestValidateStripe:
    """Stripe key validation via mocked API calls."""

    def test_valid_stripe_key(self):
        mock = _mock_urlopen(
            status=200,
            body=b'{"available": [{"amount": 1000}]}',
        )
        with patch("urllib.request.urlopen", return_value=mock):
            result = validate_credential(
                "sk_" + "live_TESTINGONLY00000000000000",
                "stripe",
                enabled=True,
            )

        assert result["status"] == "valid"
        assert result["service"] == "Stripe"


class TestValidateSlack:
    """Slack token validation via mocked API calls."""

    def test_valid_slack_token(self):
        mock = _mock_urlopen(
            status=200,
            body=b'{"ok": true, "team": "myteam", "user": "myuser"}',
        )
        with patch("urllib.request.urlopen", return_value=mock):
            result = validate_credential(
                "xoxb-validtoken1234567890abcdef",
                "slack",
                enabled=True,
            )

        assert result["status"] == "valid"
        assert result["service"] == "Slack"
        assert result["team"] == "myteam"

    def test_invalid_slack_token(self):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b'{"ok": false, "error": "invalid_auth"}'

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = validate_credential(
                "xoxb-invalidtoken1234567890abcdef",
                "slack",
                enabled=True,
            )

        assert result["status"] == "invalid"


class TestValidationCache:
    """Results are cached to avoid repeated API calls."""

    def test_cache_hit_avoids_api_call(self):
        # Clear cache
        _validation_cache.clear()

        mock = _mock_urlopen(
            status=200,
            body=b'{"login": "cacheduser"}',
            headers={"X-OAuth-Scopes": ""},
        )

        token = "ghp_cachetesttoken1234567890abcdefghijklmnopqr"

        with patch("urllib.request.urlopen", return_value=mock) as mock_open:
            # First call hits the API
            r1 = validate_credential(token, "github", enabled=True)
            assert r1["status"] == "valid"
            assert mock_open.call_count == 1

            # Second call should use cache
            r2 = validate_credential(token, "github", enabled=True)
            assert r2["status"] == "valid"
            assert mock_open.call_count == 1  # still 1 — no new API call

    def test_empty_value_returns_error(self):
        result = validate_credential("", "github", enabled=True)
        assert result["status"] == "error"

    def test_unknown_service_returns_error(self):
        result = validate_credential("some_token", "unknown_service", enabled=True)
        assert result["status"] == "error"
        assert "no validator" in result["detail"]
