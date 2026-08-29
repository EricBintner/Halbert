# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for credential format identification — the safe internet lookup."""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from halbert_core.config.credential_formats import (
    identify_credential,
    list_known_formats,
)
from halbert_core.config.secure_response import describe_secret


class TestIdentifyCredential:
    """identify_credential matches known credential formats."""

    def test_github_pat_classic(self):
        result = identify_credential("ghp_abcdefghijklmnopqrstuvwxyz0123456789AB")
        assert result is not None
        assert result["service"] == "GitHub"
        assert result["confidence"] == "high"
        assert result["breach_risk"] == "high"

    def test_openai_key(self):
        result = identify_credential("sk-abcdefghijklmnopqrstuvwxyz0123456789")
        assert result is not None
        assert result["service"] == "OpenAI"
        assert result["confidence"] == "high"

    def test_anthropic_key(self):
        result = identify_credential("sk-ant-abcdefghijklmnopqrstuvwxyz0123456789")
        assert result is not None
        assert result["service"] == "Anthropic"

    def test_aws_access_key_id(self):
        result = identify_credential("AKIAIOSFODNN7EXAMPLE")
        assert result is not None
        assert result["service"] == "AWS"
        assert result["type"] == "aws_access_key_id"

    def test_slack_bot_token(self):
        result = identify_credential("xoxb-abcdefghijklmnopqrstuvwxyz0123456789")
        assert result is not None
        assert result["service"] == "Slack"

    def test_google_api_key(self):
        # Google API key: AIza + exactly 35 chars
        result = identify_credential("AIza" + "b" * 35)
        assert result is not None
        assert result["service"] == "Google Cloud"

    def test_stripe_secret_key(self):
        result = identify_credential("sk_" + "live_TESTINGONLY00000000000000")
        assert result is not None
        assert result["service"] == "Stripe"

    def test_gitlab_token(self):
        result = identify_credential("glpat-abcdefghijklmnopqrstuvwxyz0123")
        assert result is not None
        assert result["service"] == "GitLab"

    def test_jwt(self):
        jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwpMeKKF2QT4fwp"
        result = identify_credential(jwt)
        assert result is not None
        assert result["service"] == "JWT"

    def test_pem_block(self):
        pem = "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIKB\n-----END RSA PRIVATE KEY-----"
        result = identify_credential(pem)
        assert result is not None
        assert result["service"] == "PKI"
        assert result["type"] == "pem_private_key"

    def test_unknown_format_returns_none(self):
        result = identify_credential("just-a-random-string")
        assert result is None

    def test_empty_string_returns_none(self):
        result = identify_credential("")
        assert result is None

    def test_none_returns_none(self):
        result = identify_credential(None)  # type: ignore
        assert result is None

    def test_sendgrid_key(self):
        # SendGrid: SG. + 22 chars + . + 43 chars
        key = "SG." + "a" * 22 + "." + "b" * 43
        result = identify_credential(key)
        assert result is not None
        assert result["service"] == "SendGrid"

    def test_linear_api_key(self):
        key = "lin_api_" + "a" * 40
        result = identify_credential(key)
        assert result is not None
        assert result["service"] == "Linear"

    def test_notion_api_key(self):
        key = "secret_" + "a" * 43
        result = identify_credential(key)
        assert result is not None
        assert result["service"] == "Notion"

    def test_pulumi_token(self):
        key = "pul-" + "a" * 40
        result = identify_credential(key)
        assert result is not None
        assert result["service"] == "Pulumi"


class TestDescribeSecretWithIdentification:
    """describe_secret includes credential type when identified."""

    def test_describe_secret_includes_credential_type(self):
        result = describe_secret("api_key", "ghp_abcdefghijklmnopqrstuvwxyz0123456789AB")
        assert "credential_type" in result
        assert result["credential_type"]["service"] == "GitHub"
        assert result["redacted"] is True
        # The raw value must NOT appear in the result
        assert "ghp_" not in str(result)

    def test_describe_secret_without_identify_flag(self):
        result = describe_secret(
            "api_key", "ghp_abcdefghijklmnopqrstuvwxyz0123456789AB",
            identify=False,
        )
        assert "credential_type" not in result
        assert result["redacted"] is True

    def test_describe_secret_unknown_credential(self):
        result = describe_secret("password", "hunter2")
        assert "credential_type" not in result
        assert result["length"] == 7
        assert result["redacted"] is True

    def test_describe_secret_aws_key(self):
        result = describe_secret("aws_access_key_id", "AKIAIOSFODNN7EXAMPLE")
        assert "credential_type" in result
        assert result["credential_type"]["service"] == "AWS"
        assert "AKIAIOSFODNN7EXAMPLE" not in str(result)

    def test_describe_secret_includes_breach_risk(self):
        result = describe_secret("token", "ghp_abcdefghijklmnopqrstuvwxyz0123456789AB")
        assert "credential_type" in result
        assert "breach_risk" in result["credential_type"]

    def test_describe_secret_includes_validation_available(self):
        result = describe_secret("token", "ghp_abcdefghijklmnopqrstuvwxyz0123456789AB")
        assert "credential_type" in result
        assert result["credential_type"]["validation_available"] is True


class TestListKnownFormats:
    """list_known_formats returns the database for inspection."""

    def test_returns_list(self):
        formats = list_known_formats()
        assert isinstance(formats, list)
        assert len(formats) > 10

    def test_each_format_has_required_fields(self):
        formats = list_known_formats()
        for fmt in formats:
            assert "name" in fmt
            assert "service" in fmt
            assert "description" in fmt
            assert "breach_risk" in fmt
            assert "validation_available" in fmt

    def test_includes_github(self):
        formats = list_known_formats()
        services = {f["service"] for f in formats}
        assert "GitHub" in services

    def test_includes_aws(self):
        formats = list_known_formats()
        services = {f["service"] for f in formats}
        assert "AWS" in services
