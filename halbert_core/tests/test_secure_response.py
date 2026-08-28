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
