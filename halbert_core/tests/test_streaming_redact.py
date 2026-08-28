# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for streaming/redact.py (Plan B: B2)."""

import pytest

from halbert_core.streaming.redact import redact, redact_bytes, PATTERNS


class TestRedactPassword:
    def test_password_equals(self):
        assert redact("password=secret123")[0] == "password=[redacted]"
        assert redact("password=secret123")[1] is True

    def test_password_with_spaces(self):
        assert redact("password = hunter2")[0] == "password = [redacted]"

    def test_password_quoted(self):
        out, hit = redact('password="my-secret"')
        assert hit is True
        assert "[redacted]" in out
        assert "my-secret" not in out

    def test_password_no_match_in_word(self):
        out, hit = redact("the passwordless login works")
        assert hit is False
        assert out == "the passwordless login works"

    def test_passwd_variant(self):
        out, hit = redact("passwd=abc123")
        assert hit is True
        assert "abc123" not in out


class TestRedactFlag:
    def test_p_flag_space(self):
        out, hit = redact("ssh -pMyToken user@host")
        assert hit is True
        assert "MyToken" not in out

    def test_p_flag_start(self):
        out, hit = redact("-pSecretToken do stuff")
        assert hit is True
        assert "SecretToken" not in out

    def test_p_flag_not_matched_in_word(self):
        out, hit = redact("the -proxy flag")
        assert hit is False


class TestRedactAuthHeader:
    def test_authorization_header(self):
        out, hit = redact("Authorization: Bearer abc.def.ghi")
        assert hit is True
        assert "abc.def.ghi" not in out

    def test_bearer_token(self):
        out, hit = redact("Bearer dGhpcyBpcyBhIHRva2Vu")
        assert hit is True
        assert "dGhpcyBpcyBhIHRva2Vu" not in out

    def test_authorization_basic(self):
        out, hit = redact("Authorization: Basic dXNlcjpwYXNz")
        assert hit is True
        assert "dXNlcjpwYXNz" not in out


class TestRedactCloudKeys:
    def test_aws_key(self):
        out, hit = redact("AKIAIOSFODNN7EXAMPLE")
        assert hit is True
        assert "AKIAIOSFODNN7EXAMPLE" not in out

    def test_huggingface_token(self):
        out, hit = redact("hf_xxxxxxxxxxxxxxxxxxxx")
        assert hit is True
        assert "hf_xxxxxxxxxxxxxxxxxxxx" not in out

    def test_github_pat(self):
        token = "ghp_" + "a" * 36
        out, hit = redact(token)
        assert hit is True
        assert token not in out


class TestRedactPrivateKey:
    def test_rsa_private_key(self):
        key = "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA...\n-----END RSA PRIVATE KEY-----"
        out, hit = redact(key)
        assert hit is True
        assert "MIIEpAIBAAKCAQEA" not in out
        assert "[redacted]" in out

    def test_ec_private_key(self):
        key = "-----BEGIN EC PRIVATE KEY-----\nMHQCAQEE...\n-----END EC PRIVATE KEY-----"
        out, hit = redact(key)
        assert hit is True
        assert "MHQCAQEE" not in out

    def test_private_key_multiline(self):
        key = (
            "-----BEGIN PRIVATE KEY-----\n"
            "line1\nline2\nline3\n"
            "-----END PRIVATE KEY-----"
        )
        out, hit = redact(key)
        assert hit is True
        assert "line1" not in out
        assert "line2" not in out


class TestRedactNoMatch:
    def test_plain_text(self):
        out, hit = redact("ls -la /tmp")
        assert hit is False
        assert out == "ls -la /tmp"

    def test_empty_string(self):
        out, hit = redact("")
        assert hit is False
        assert out == ""

    def test_normal_command_output(self):
        text = "total 0\ndrwxr-xr-x  2 root root 40 Aug 27 12:00 ."
        out, hit = redact(text)
        assert hit is False
        assert out == text


class TestRedactMultiple:
    def test_multiple_secrets_in_one_text(self):
        text = "password=secret AKIAIOSFODNN7EXAMPLE"
        out, hit = redact(text)
        assert hit is True
        assert "secret" not in out
        assert "AKIAIOSFODNN7EXAMPLE" not in out

    def test_redact_replaces_all_occurrences(self):
        text = "password=one password=two"
        out, hit = redact(text)
        assert hit is True
        assert "one" not in out
        assert "two" not in out
        assert out.count("[redacted]") == 2


class TestRedactBytes:
    def test_bytes_redact(self):
        data = b"password=secret123"
        out, hit = redact_bytes(data)
        assert hit is True
        assert b"secret123" not in out
        assert b"[redacted]" in out

    def test_bytes_no_match(self):
        data = b"ls -la"
        out, hit = redact_bytes(data)
        assert hit is False
        assert out == b"ls -la"

    def test_bytes_invalid_utf8(self):
        data = b"password=\xff\xfe secret"
        out, hit = redact_bytes(data)
        # Should not raise; replacement chars are fine
        assert isinstance(out, bytes)

    def test_bytes_empty(self):
        out, hit = redact_bytes(b"")
        assert hit is False
        assert out == b""


class TestRedactNeverRaises:
    def test_none_input(self):
        out, hit = redact(None)  # type: ignore[arg-type]
        assert hit is False
        assert out == ""

    def test_patterns_exist(self):
        assert len(PATTERNS) > 0
        for pattern, replacement in PATTERNS:
            assert hasattr(pattern, "sub")
            assert isinstance(replacement, str)
