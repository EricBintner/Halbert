# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for the SecurityConfig dataclass and being config integration."""
from __future__ import annotations

import os
import sys
import tempfile

import pytest
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from halbert_core.config.being_config import (
    BeingConfig,
    SecurityConfig,
    load_being_config,
    save_being_config,
    VALID_OPERATIONAL_TIERS,
    VALID_SECRET_TIERS,
)


class TestSecurityConfigDefaults:
    def test_defaults(self):
        s = SecurityConfig()
        assert s.operational_tier == "cloud_ok"
        assert s.secret_tier == "local_only"
        assert "/etc/hosts" in s.public_files
        assert s.extra_secret_keys == []

    def test_validate_ok(self):
        s = SecurityConfig()
        s.validate()  # should not raise

    def test_validate_bad_operational_tier(self):
        s = SecurityConfig(operational_tier="bogus")
        with pytest.raises(ValueError, match="operational_tier"):
            s.validate()

    def test_validate_bad_secret_tier(self):
        s = SecurityConfig(secret_tier="bogus")
        with pytest.raises(ValueError, match="secret_tier"):
            s.validate()

    def test_to_dict(self):
        s = SecurityConfig(operational_tier="local_only", extra_secret_keys=["serial"])
        d = s.to_dict()
        assert d["operational_tier"] == "local_only"
        assert d["extra_secret_keys"] == ["serial"]

    def test_from_dict(self):
        d = {
            "operational_tier": "redact",
            "secret_tier": "cloud_ok_acknowledged",
            "public_files": ["/etc/myapp"],
            "extra_secret_keys": ["license"],
        }
        s = SecurityConfig.from_dict(d)
        assert s.operational_tier == "redact"
        assert s.secret_tier == "cloud_ok_acknowledged"
        assert s.public_files == ["/etc/myapp"]
        assert s.extra_secret_keys == ["license"]

    def test_from_dict_ignores_unknown_keys(self):
        d = {"operational_tier": "local_only", "bogus": "value"}
        s = SecurityConfig.from_dict(d)
        assert s.operational_tier == "local_only"


class TestBeingConfigIntegration:
    def test_default_security(self):
        bc = BeingConfig()
        assert isinstance(bc.security, SecurityConfig)
        assert bc.security.operational_tier == "cloud_ok"

    def test_from_dict_with_security(self):
        d = {
            "voice": "first_person",
            "security": {
                "operational_tier": "local_only",
                "secret_tier": "cloud_ok_acknowledged",
                "public_files": ["/etc/myapp"],
                "extra_secret_keys": ["serial"],
            },
        }
        bc = BeingConfig.from_dict(d)
        assert bc.security.operational_tier == "local_only"
        assert bc.security.secret_tier == "cloud_ok_acknowledged"
        assert bc.security.public_files == ["/etc/myapp"]
        assert bc.security.extra_secret_keys == ["serial"]

    def test_from_dict_without_security(self):
        d = {"voice": "hybrid"}
        bc = BeingConfig.from_dict(d)
        assert bc.security.operational_tier == "cloud_ok"  # default

    def test_to_dict_includes_security(self):
        bc = BeingConfig()
        bc.security.operational_tier = "redact"
        d = bc.to_dict()
        assert "security" in d
        assert d["security"]["operational_tier"] == "redact"

    def test_validate_propagates_to_security(self):
        bc = BeingConfig()
        bc.security.operational_tier = "bogus"
        with pytest.raises(ValueError, match="operational_tier"):
            bc.validate()

    def test_valid_security_passes_validation(self):
        bc = BeingConfig()
        bc.security.operational_tier = "local_only"
        bc.security.secret_tier = "cloud_ok_acknowledged"
        bc.validate()  # should not raise


class TestLoadSaveWithSecurity:
    def test_save_and_load_security(self, tmp_path):
        bc = BeingConfig()
        bc.security.operational_tier = "local_only"
        bc.security.secret_tier = "cloud_ok_acknowledged"
        bc.security.extra_secret_keys = ["serial", "license"]

        path = str(tmp_path / "being.yml")
        save_being_config(bc, path)

        # Verify the YAML has the security section
        with open(path) as f:
            raw = yaml.safe_load(f)
        assert "security" in raw
        assert raw["security"]["operational_tier"] == "local_only"
        assert raw["security"]["secret_tier"] == "cloud_ok_acknowledged"
        assert "serial" in raw["security"]["extra_secret_keys"]

        # Load it back
        loaded = load_being_config(path)
        assert loaded.security.operational_tier == "local_only"
        assert loaded.security.secret_tier == "cloud_ok_acknowledged"
        assert loaded.security.extra_secret_keys == ["serial", "license"]

    def test_load_without_security_section(self, tmp_path):
        """A being.yml without a security section should use defaults."""
        path = str(tmp_path / "being.yml")
        with open(path, "w") as f:
            yaml.dump({"voice": "hybrid", "proactivity": "balanced"}, f)

        loaded = load_being_config(path)
        assert loaded.security.operational_tier == "cloud_ok"
        assert loaded.security.secret_tier == "local_only"
