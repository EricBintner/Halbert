# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for the three-tier sensitivity classifier."""
from __future__ import annotations

import os
import sys
import tempfile

import pytest

# Ensure halbert_core is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from halbert_core.config.sensitivity import (
    classify_sensitivity,
    _host_path,
    DEFAULT_PUBLIC_FILES,
)


class TestTier2ByKey:
    """Tier 2 by key name — _is_secret_key fires."""

    def test_password_key(self):
        assert classify_sensitivity("password", "hunter2") == 2

    def test_api_key(self):
        assert classify_sensitivity("api_key", "abc123") == 2

    def test_token_key(self):
        assert classify_sensitivity("token", "xyz") == 2

    def test_secret_key(self):
        assert classify_sensitivity("secret", "value") == 2

    def test_bearer_key(self):
        assert classify_sensitivity("bearer", "tok") == 2

    def test_passphrase_key(self):
        assert classify_sensitivity("passphrase", "mypass") == 2

    def test_psk_key(self):
        assert classify_sensitivity("psk", "key") == 2

    def test_wpa_psk_key(self):
        assert classify_sensitivity("wpa-psk", "key") == 2

    def test_credential_key(self):
        assert classify_sensitivity("credential", "val") == 2

    def test_authorization_key(self):
        assert classify_sensitivity("authorization", "val") == 2

    def test_password_with_underscore_prefix(self):
        assert classify_sensitivity("db_password", "hunter2") == 2

    def test_pass_suffix(self):
        assert classify_sensitivity("db_pass", "hunter2") == 2


class TestTier2ByContent:
    """Tier 2 by value content — redact_text as detector."""

    def test_pem_block_value(self):
        pem = "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIKB\n-----END RSA PRIVATE KEY-----"
        assert classify_sensitivity("description", pem) == 2

    def test_jwt_value(self):
        jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwp"
        assert classify_sensitivity("note", jwt) == 2

    def test_url_credentials_in_value(self):
        url = "https://admin:secretpass@internal.example.com/api"
        assert classify_sensitivity("endpoint", url) == 2

    def test_routable_ip_in_value(self):
        assert classify_sensitivity("server", "203.0.113.5") == 2

    def test_email_in_value(self):
        assert classify_sensitivity("contact", "admin@example.com") == 2

    def test_key_equals_value_shape(self):
        # redact_text catches embedded key=value
        assert classify_sensitivity("config", "password=hunter2") == 2


class TestTier0ByFile:
    """Tier 0 by file path — floor, not ceiling."""

    def test_public_file_clean_value(self):
        assert classify_sensitivity("hostname", "myhost", "/etc/hostname") == 0

    def test_public_file_structural_key(self):
        assert classify_sensitivity("type", "ext4", "/etc/fstab") == 0

    def test_public_file_with_routable_ip_still_tier1(self):
        # /etc/hosts is public, but a routable IP is still Tier 1
        # because content check fires before file check
        assert classify_sensitivity("server", "203.0.113.5", "/etc/hosts") == 2

    def test_public_file_with_secret_key_still_tier2(self):
        assert classify_sensitivity("password", "hunter2", "/etc/hosts") == 2

    def test_staged_path_maps_to_host_path(self):
        staged = os.path.expanduser(
            "~/.local/share/halbert/sourceprep/host/etc/hosts"
        )
        assert classify_sensitivity("hostname", "myhost", staged) == 0

    def test_non_public_file_is_tier1(self):
        assert classify_sensitivity("port", "2222", "/etc/ssh/sshd_config") == 1

    def test_custom_public_files(self):
        custom = {"/etc/myapp/config.conf"}
        assert classify_sensitivity("port", "8080", "/etc/myapp/config.conf",
                                     public_files=custom) == 0


class TestTier0Structural:
    """Tier 0 for structural values (booleans, structural keys)."""

    def test_boolean_value(self):
        assert classify_sensitivity("enabled", True, "/etc/myapp.conf") == 0

    def test_false_boolean(self):
        assert classify_sensitivity("debug", False, "/etc/myapp.conf") == 0

    def test_include_key(self):
        assert classify_sensitivity("Include", "/etc/myapp.d/*.conf", "/etc/myapp.conf") == 0

    def test_enabled_key(self):
        assert classify_sensitivity("enabled", "yes", "/etc/myapp.conf") == 0

    def test_type_key(self):
        assert classify_sensitivity("type", "ext4", "/etc/myapp.conf") == 0

    def test_kind_key(self):
        assert classify_sensitivity("kind", "Deployment", "/etc/myapp.conf") == 0

    def test_version_key(self):
        assert classify_sensitivity("version", "1.2.3", "/etc/myapp.conf") == 0


class TestTier1Operational:
    """Tier 1 for operational values."""

    def test_port_number(self):
        assert classify_sensitivity("Port", "2222", "/etc/ssh/sshd_config") == 1

    def test_permit_root_login(self):
        assert classify_sensitivity("PermitRootLogin", "no", "/etc/ssh/sshd_config") == 1

    def test_listen_address_private(self):
        # Private IP is not redacted by redact_text, so it's Tier 1
        assert classify_sensitivity("ListenAddress", "192.168.1.1", "/etc/ssh/sshd_config") == 1

    def test_path_value(self):
        assert classify_sensitivity("ExecStart", "/usr/bin/myapp", "/etc/systemd/my.service") == 1

    def test_string_value(self):
        assert classify_sensitivity("ServerName", "myhost.example.com", "/etc/myapp.conf") == 1


class TestExtraSecretKeys:
    """extra_secret_keys from being config."""

    def test_extra_secret_key_matched(self):
        assert classify_sensitivity("serial", "ABC123",
                                     extra_secret_keys=["serial"]) == 2

    def test_extra_secret_key_not_matched(self):
        # "serial" is not in the default _is_secret_key list
        assert classify_sensitivity("serial", "ABC123") == 1

    def test_extra_secret_key_case_insensitive(self):
        assert classify_sensitivity("LICENSE", "XYZ",
                                     extra_secret_keys=["license"]) == 2


class TestHostPathMapping:
    """_host_path maps staged paths back to host paths."""

    def test_staged_path(self):
        staged = os.path.expanduser(
            "~/.local/share/halbert/sourceprep/host/etc/hosts"
        )
        assert _host_path(staged) == "/etc/hosts"

    def test_already_host_path(self):
        assert _host_path("/etc/hosts") == "/etc/hosts"

    def test_nested_staged_path(self):
        staged = os.path.expanduser(
            "~/.local/share/halbert/sourceprep/host/etc/systemd/system/my.service"
        )
        assert _host_path(staged) == "/etc/systemd/system/my.service"


class TestEdgeCases:
    """Edge cases and fail-safe behavior."""

    def test_none_value(self):
        # None value: not Tier 2 (no content), not structural bool,
        # falls to Tier 1
        assert classify_sensitivity("port", None, "/etc/myapp.conf") == 1

    def test_empty_string_value(self):
        assert classify_sensitivity("port", "", "/etc/myapp.conf") == 1

    def test_empty_key(self):
        assert classify_sensitivity("", "value", "/etc/myapp.conf") == 1

    def test_no_file_path(self):
        assert classify_sensitivity("port", "2222") == 1

    def test_int_value(self):
        # An int is not a bool, so not Tier 0 structural
        assert classify_sensitivity("uid", 1000, "/etc/myapp.conf") == 1

    def test_non_secret_key_with_secret_sounding_name(self):
        # keymap is in _NON_SECRET_KEYS
        assert classify_sensitivity("keymap", "us", "/etc/vconsole.conf") == 1
