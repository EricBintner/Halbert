# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for compromise detection — HIBP and GitHub secret scanning."""
from __future__ import annotations

import os
import sys
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from halbert_core.cli.compromise_detection import (
    check_compromised,
    _sha1_upper,
    _check_hibp,
    _check_github_scanning,
)


def _mock_urlopen(status=200, body=b"", headers=None):
    """Create a mock that works as a context manager for urlopen."""
    mock_resp = MagicMock()
    mock_resp.status = status
    mock_resp.read.return_value = body
    mock_resp.headers = headers or {}
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = False
    return mock_resp


class TestSha1Hash:
    """_sha1_upper produces the format HIBP expects."""

    def test_known_value(self):
        # SHA-1 of "password" is 5BAA61E4C9B93F3F0682250B6CF8331B7EE68FD8
        result = _sha1_upper("password")
        assert result == "5BAA61E4C9B93F3F0682250B6CF8331B7EE68FD8"

    def test_uppercase(self):
        result = _sha1_upper("test")
        assert result == result.upper()

    def test_stable(self):
        assert _sha1_upper("abc") == _sha1_upper("abc")


class TestHibpCheck:
    """HIBP password check via k-anonymity model."""

    def test_compromised_password(self):
        # SHA-1 of "password" = 5BAA61E4C9B93F3F0682250B6CF8331B7EE68FD8
        # prefix = 5BAA6, suffix = 1E4C9B93F3F0682250B6CF8331B7EE68FD8
        hibp_response = (
            "1E4C9B93F3F0682250B6CF8331B7EE68FD8:3303003\n"
            "001E4C9B93F3F0682250B6CF8331B7EE68FD:5\n"
        ).encode()
        mock = _mock_urlopen(status=200, body=hibp_response)
        with patch("urllib.request.urlopen", return_value=mock):
            result = _check_hibp("password")

        assert result["status"] == "compromised"
        assert result["breach_count"] == 3303003
        assert "Rotate" in result["detail"]

    def test_safe_password(self):
        # SHA-1 of a random string that won't be in the response
        hibp_response = "AAAAABBBBCCCCDDDDEEEEFFFF111122223333:5\n".encode()
        mock = _mock_urlopen(status=200, body=hibp_response)
        with patch("urllib.request.urlopen", return_value=mock):
            result = _check_hibp("xJ7#kL9$mN2pQ4rT")

        assert result["status"] == "safe"
        assert result["breach_count"] == 0

    def test_network_error(self):
        with patch("urllib.request.urlopen", side_effect=Exception("timeout")):
            result = _check_hibp("password")

        assert result["status"] == "error"
        assert "timeout" in result["detail"]


class TestGitHubScanning:
    """GitHub token exposure check."""

    def test_valid_github_token(self):
        mock = _mock_urlopen(
            status=200,
            body=b'{"login": "testuser"}',
        )
        with patch("urllib.request.urlopen", return_value=mock):
            result = _check_github_scanning("ghp_validtoken1234567890abcdefghijklmnopqrstuvwxyz")

        assert result["status"] == "active"

    def test_revoked_token(self):
        import urllib.error
        error = urllib.error.HTTPError(
            "https://api.github.com/user", 401, "Unauthorized",
            MagicMock(), None,
        )
        with patch("urllib.request.urlopen", side_effect=error):
            result = _check_github_scanning("ghp_revokedtoken1234567890abcdefghijklmnopqrstuvwxyz")

        assert result["status"] == "invalid_or_revoked"
        assert "revoked" in result["detail"].lower() or "invalid" in result["detail"].lower()

    def test_non_github_token_skipped(self):
        result = _check_github_scanning("sk-openaikey1234567890abcdef")
        assert result["status"] == "skipped"


class TestCheckCompromised:
    """check_compromised orchestrates the checks."""

    def test_disabled_by_default(self):
        result = check_compromised("password123")
        assert result["status"] == "disabled"

    def test_empty_value(self):
        result = check_compromised("", enabled=True)
        assert result["status"] == "error"

    def test_password_hibp_check(self):
        hibp_response = b"1E4C9B93F3F0682250B6CF8331B7EE68FD8:1\n"
        mock = _mock_urlopen(status=200, body=hibp_response)
        with patch("urllib.request.urlopen", return_value=mock):
            result = check_compromised(
                "password", enabled=True, hibp=True
            )

        assert result["status"] == "compromised"

    def test_safe_password(self):
        hibp_response = b"AAAAABBBBCCCCDDDDEEEEFFFF111122223333:5\n"
        mock = _mock_urlopen(status=200, body=hibp_response)
        with patch("urllib.request.urlopen", return_value=mock):
            result = check_compromised(
                "xJ7#kL9$mN2pQ4rT", enabled=True, hibp=True
            )

        assert result["status"] == "safe"

    def test_github_token_check(self):
        mock = _mock_urlopen(status=200, body=b'{"login": "user"}')
        with patch("urllib.request.urlopen", return_value=mock):
            result = check_compromised(
                "ghp_validtoken1234567890abcdefghijklmnopqrstuvwxyz",
                enabled=True, github_scanning=True,
                credential_type={"service": "GitHub", "type": "github_pat_classic"},
            )

        assert result["status"] == "active"

    def test_no_applicable_check(self):
        result = check_compromised(
            "sk-openaikey1234567890abcdef",
            enabled=True, hibp=True, github_scanning=True,
            credential_type={"service": "OpenAI", "type": "openai_api_key"},
        )
        # OpenAI key: not a password (hibp skipped), not a GitHub token (gh skipped)
        assert result["status"] == "skipped"

    def test_password_with_credential_type(self):
        """When credential_type says it's a password, hibp fires."""
        hibp_response = b"1E4C9B93F3F0682250B6CF8331B7EE68FD8:1\n"
        mock = _mock_urlopen(status=200, body=hibp_response)
        with patch("urllib.request.urlopen", return_value=mock):
            result = check_compromised(
                "password", enabled=True, hibp=True,
                credential_type={"service": "Unknown", "type": "password"},
            )

        assert result["status"] == "compromised"
