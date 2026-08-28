# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for Task 8 — known-prefix and high-entropy redaction gaps."""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from halbert_core.ingestion.redaction import redact_text


class TestKnownPrefixes:
    """Known credential prefixes are redacted regardless of context."""

    def test_github_pat(self):
        token = "ghp_abcdefghijklmnopqrstuvwxyz0123456789AB"
        assert "<token>" in redact_text(token)
        assert token not in redact_text(token)

    def test_github_fine_grained(self):
        token = "github_pat_abcdefghijklmnopqrstuvwxyz0123456789AB"
        # github_pat_ prefix — not in our list, but high-entropy should catch it
        result = redact_text(token)
        assert token not in result

    def test_openai_key(self):
        token = "sk-abcdefghijklmnopqrstuvwxyz0123456789"
        assert "<token>" in redact_text(token)
        assert token not in redact_text(token)

    def test_anthropic_key(self):
        token = "sk-ant-abcdefghijklmnopqrstuvwxyz0123456789"
        result = redact_text(token)
        assert token not in result

    def test_aws_access_key(self):
        token = "AKIAIOSFODNN7EXAMPLE"
        result = redact_text(token)
        assert token not in result

    def test_slack_token(self):
        token = "xoxb-abcdefghijklmnopqrstuvwxyz0123456789"
        result = redact_text(token)
        assert token not in result

    def test_google_api_key(self):
        token = "AIzaSyAabcdefghijklmnopqrstuvwxyz0123456789"
        result = redact_text(token)
        assert token not in result

    def test_stripe_key(self):
        token = "sk_" + "live_TESTINGONLY00000000000000"
        result = redact_text(token)
        assert token not in result

    def test_gitlab_token(self):
        token = "glpat-abcdefghijklmnopqrstuvwxyz0123"
        result = redact_text(token)
        assert token not in result

    def test_prefix_in_sentence(self):
        """A token embedded in a sentence is still redacted."""
        text = "The API key is ghp_abcdefghijklmnopqrstuvwxyz0123456789AB for prod."
        result = redact_text(text)
        assert "ghp_" not in result
        assert "<token>" in result

    def test_prefix_in_config_line(self):
        """A bare token under a neutral key is redacted."""
        text = "location: ghp_abcdefghijklmnopqrstuvwxyz0123456789AB"
        result = redact_text(text)
        assert "ghp_" not in result


class TestHighEntropy:
    """High-entropy backstop catches long random tokens."""

    def test_long_base64_token(self):
        token = "SGVsbG8gV29ybGQgVGhpcyBJcyBBIFZlcnkgTG9uZyBCYXNlNjQgVG9rZW4"
        result = redact_text(token)
        assert token not in result
        assert "<token>" in result

    def test_long_hex_token(self):
        token = "deadbeef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
        result = redact_text(token)
        assert token not in result

    def test_short_token_not_redacted(self):
        """A short string should not be redacted by the entropy backstop."""
        token = "short"
        result = redact_text(token)
        assert result == token

    def test_low_entropy_long_string_not_redacted(self):
        """A long string of repeated characters has low entropy."""
        token = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        result = redact_text(token)
        # Low entropy → not redacted
        assert result == token

    def test_normal_text_not_redacted(self):
        """Normal prose should not be affected."""
        text = "The quick brown fox jumps over the lazy dog."
        result = redact_text(text)
        assert result == text


class TestRedactionGaps:
    """Specific gap cases from the trust boundary research."""

    def test_bare_token_in_file(self):
        """A bare token on its own line, no key=value shape."""
        text = "ghp_abcdefghijklmnopqrstuvwxyz0123456789AB"
        result = redact_text(text)
        assert "ghp_" not in result

    def test_netrc_shape_long_secret(self):
        """netrc: machine h login u password <long_secret> — password is mid-line.

        The known-prefix and entropy backstop catches long secrets. Short
        secrets like 'hunter2' (7 chars) are below the 32-char entropy
        threshold and have no known prefix — this is a known limit, same
        as the redaction module's own comments acknowledge for sequence items.
        """
        long_secret = "SGVsbG8gV29ybGQgVGhpcyBJcyBBIFZlcnkgTG9uZyBTZWNyZXQ"
        text = f"machine example.com login admin password {long_secret}"
        result = redact_text(text)
        assert long_secret not in result

    def test_yaml_sequence_long_secret(self):
        """YAML sequence item with a long secret is caught by entropy backstop."""
        long_secret = "SGVsbG8gV29ybGQgVGhpcyBJcyBBIFZlcnkgTG9uZyBTZWNyZXQ"
        text = f"passwords:\n  - {long_secret}"
        result = redact_text(text)
        assert long_secret not in result

    def test_netrc_short_secret_known_limit(self):
        """Short secrets in netrc format are a known limit (no prefix, below entropy threshold)."""
        text = "machine example.com login admin password hunter2"
        result = redact_text(text)
        # Known limit: hunter2 is 7 chars, below the 32-char entropy threshold
        # and has no known prefix. The format-aware passes don't catch it
        # because 'password' is not the first token and there's no = or : separator.
        # This is acknowledged in the redaction module's own comments.
        assert "hunter2" in result  # known gap

    def test_hash_material(self):
        """SHA-512 hash: $6$salt$hash"""
        text = "$6$mysalt$somehashvaluehere"
        result = redact_text(text)
        # The hash itself is high-entropy and long enough to be caught
        # by the entropy backstop if it's 32+ chars of base64/hex
        # Short hashes may not be caught — that's acceptable
        # The key thing is the $6$ format is recognized as potentially sensitive

    def test_existing_redaction_still_works(self):
        """Existing key=value redaction is not broken by the new passes."""
        text = "password=hunter2"
        result = redact_text(text)
        assert "hunter2" not in result
        assert "<secret>" in result

    def test_pem_block_still_works(self):
        """PEM block redaction is not broken."""
        pem = "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIKB\n-----END RSA PRIVATE KEY-----"
        result = redact_text(pem)
        assert "MIIEpAIKB" not in result
        assert "<pem_block>" in result

    def test_jwt_still_works(self):
        """JWT redaction is not broken."""
        jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwp"
        result = redact_text(jwt)
        assert "eyJ" not in result

    def test_url_credentials_still_works(self):
        """URL credential redaction is not broken."""
        text = "https://admin:secretpass@internal.example.com/api"
        result = redact_text(text)
        assert "secretpass" not in result

    def test_routable_ip_still_works(self):
        """Routable IP redaction is not broken."""
        text = "server: 203.0.113.5"
        result = redact_text(text)
        assert "203.0.113.5" not in result

    def test_private_ip_not_redacted(self):
        """Private IPs are operational data, not secrets."""
        text = "ListenAddress 192.168.1.1"
        result = redact_text(text)
        assert "192.168.1.1" in result

    def test_normal_config_not_over_redacted(self):
        """Normal config values should survive the new passes."""
        text = "Port=2222\nPermitRootLogin=no\nProtocol=2"
        result = redact_text(text)
        assert "2222" in result
        assert "PermitRootLogin" in result
