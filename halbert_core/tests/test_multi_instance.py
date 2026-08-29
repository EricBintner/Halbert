# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Unit tests for Phase 7 multi-instance isolation."""

import os
import importlib
from unittest.mock import patch, MagicMock

import pytest


class TestEnvVarUnification:
    """Test that HALBERT_* env vars take priority over legacy Halbert_* vars."""

    def test_data_dir_halbert_all_caps(self):
        from halbert_core.utils.paths import data_dir
        with patch.dict(os.environ, {"HALBERT_DATA_DIR": "/tmp/hbt-test-data"}, clear=False):
            assert data_dir() == "/tmp/hbt-test-data"

    def test_data_dir_legacy_fallback(self):
        from halbert_core.utils.paths import data_dir
        with patch.dict(os.environ, {"Halbert_DATA_DIR": "/tmp/hbt-legacy-data"}, clear=False):
            if "HALBERT_DATA_DIR" in os.environ:
                del os.environ["HALBERT_DATA_DIR"]
            assert data_dir() == "/tmp/hbt-legacy-data"

    def test_data_dir_all_caps_takes_priority(self):
        from halbert_core.utils.paths import data_dir
        env = {"HALBERT_DATA_DIR": "/tmp/priority", "Halbert_DATA_DIR": "/tmp/legacy"}
        with patch.dict(os.environ, env, clear=False):
            assert data_dir() == "/tmp/priority"

    def test_config_dir_halbert_all_caps(self):
        from halbert_core.utils.paths import config_dir
        with patch.dict(os.environ, {"HALBERT_CONFIG_DIR": "/tmp/hbt-test-config"}, clear=False):
            assert config_dir() == "/tmp/hbt-test-config"

    def test_config_dir_legacy_fallback(self):
        from halbert_core.utils.paths import config_dir
        with patch.dict(os.environ, {"Halbert_CONFIG_DIR": "/tmp/hbt-legacy-config"}, clear=False):
            if "HALBERT_CONFIG_DIR" in os.environ:
                del os.environ["HALBERT_CONFIG_DIR"]
            assert config_dir() == "/tmp/hbt-legacy-config"

    def test_log_dir_halbert_all_caps(self):
        from halbert_core.utils.paths import log_dir
        with patch.dict(os.environ, {"HALBERT_LOG_DIR": "/tmp/hbt-test-log"}, clear=False):
            assert log_dir() == "/tmp/hbt-test-log"


class TestPlatformConfigDirOverride:
    """Test that platform.get_config_dir() honours HALBERT_CONFIG_DIR."""

    def test_config_dir_override(self):
        from halbert_core.utils.platform import get_config_dir
        with patch.dict(os.environ, {"HALBERT_CONFIG_DIR": "/tmp/hbt-platform-config"}, clear=False):
            result = get_config_dir()
            assert str(result) == "/tmp/hbt-platform-config"

    def test_data_dir_override(self):
        from halbert_core.utils.platform import get_data_dir
        with patch.dict(os.environ, {"HALBERT_DATA_DIR": "/tmp/hbt-platform-data"}, clear=False):
            result = get_data_dir()
            assert str(result) == "/tmp/hbt-platform-data"

    def test_config_dir_legacy_fallback(self):
        from halbert_core.utils.platform import get_config_dir
        with patch.dict(os.environ, {"Halbert_CONFIG_DIR": "/tmp/hbt-legacy-platform"}, clear=False):
            if "HALBERT_CONFIG_DIR" in os.environ:
                del os.environ["HALBERT_CONFIG_DIR"]
            result = get_config_dir()
            assert str(result) == "/tmp/hbt-legacy-platform"


class TestInstanceInfoEndpoint:
    """Test the /api/instance/info endpoint."""

    def test_instance_info_host(self):
        from halbert_core.dashboard.routes.instance import get_instance_info
        env = {
            "HALBERT_PERSONA_ID": "halbert",
            "HALBERT_SCENE_CONTEXT": "Linux sysadmin",
            "HALBERT_PORT": "8000",
        }
        with patch.dict(os.environ, env, clear=False):
            result = __import__("asyncio").run(get_instance_info())
        assert result["persona_id"] == "halbert"
        assert result["role"] == "host"
        assert result["port"] == 8000
        assert result["features"]["home"] is False
        assert result["features"]["development"] is True

    def test_instance_info_home(self):
        from halbert_core.dashboard.routes.instance import get_instance_info
        env = {
            "HALBERT_PERSONA_ID": "home",
            "HALBERT_SCENE_CONTEXT": "smart home automation",
            "HALBERT_PORT": "8001",
            "WYOMING_PORT": "10401",
        }
        with patch.dict(os.environ, env, clear=False):
            result = __import__("asyncio").run(get_instance_info())
        assert result["persona_id"] == "home"
        assert result["role"] == "home"
        assert result["port"] == 8001
        assert result["features"]["home"] is True
        assert result["features"]["development"] is False
        assert result["features"]["wyoming_port"] == 10401

    def test_instance_info_display_name(self):
        from halbert_core.dashboard.routes.instance import get_instance_info
        env = {
            "HALBERT_PERSONA_ID": "home",
            "HALBERT_DISPLAY_NAME": "Casa Halbert",
        }
        with patch.dict(os.environ, env, clear=False):
            result = __import__("asyncio").run(get_instance_info())
        assert result["display_name"] == "Casa Halbert"

    def test_instance_info_home_tab_override(self):
        from halbert_core.dashboard.routes.instance import get_instance_info
        env = {
            "HALBERT_PERSONA_ID": "halbert",
            "HALBERT_ENABLE_HOME_TAB": "1",
        }
        with patch.dict(os.environ, env, clear=False):
            result = __import__("asyncio").run(get_instance_info())
        assert result["features"]["home"] is True

    def test_instance_info_variant(self):
        from halbert_core.dashboard.routes.instance import get_instance_info
        env = {
            "HALBERT_PERSONA_ID": "home",
            "HALBERT_VARIANT": "home",
        }
        with patch.dict(os.environ, env, clear=False):
            result = __import__("asyncio").run(get_instance_info())
        assert result["variant"] == "home"

    def test_instance_info_default_variant(self):
        from halbert_core.dashboard.routes.instance import get_instance_info
        env = {"HALBERT_PERSONA_ID": "halbert"}
        with patch.dict(os.environ, env, clear=False):
            if "HALBERT_VARIANT" in os.environ:
                del os.environ["HALBERT_VARIANT"]
            result = __import__("asyncio").run(get_instance_info())
        assert result["variant"] == "sysadmin"


class TestCognitionWiringDataSync:
    """Test that HALOYSIUS_DATA_HOME is synced from HALBERT_DATA_DIR."""

    def test_haloysius_data_home_synced(self):
        # Reload the module to trigger the env var sync
        env = {"HALBERT_DATA_DIR": "/tmp/hbt-haloysius-sync"}
        with patch.dict(os.environ, env, clear=False):
            if "HALOYSIUS_DATA_HOME" in os.environ:
                del os.environ["HALOYSIUS_DATA_HOME"]
            import halbert_core.integrations.cognition_wiring as cw
            importlib.reload(cw)
        assert os.environ.get("HALOYSIUS_DATA_HOME") == "/tmp/hbt-haloysius-sync"

    def test_haloysius_data_home_not_overwritten(self):
        env = {
            "HALBERT_DATA_DIR": "/tmp/hbt-should-not-override",
            "HALOYSIUS_DATA_HOME": "/tmp/custom-haloysius",
        }
        with patch.dict(os.environ, env, clear=False):
            import halbert_core.integrations.cognition_wiring as cw
            importlib.reload(cw)
        assert os.environ.get("HALOYSIUS_DATA_HOME") == "/tmp/custom-haloysius"


class TestPersonaIdFromEnv:
    """Test that persona_id is correctly read from env vars."""

    def test_default_persona_id(self):
        from halbert_core.integrations.cognition_wiring import _get_persona_id
        with patch.dict(os.environ, {}, clear=False):
            if "HALBERT_PERSONA_ID" in os.environ:
                del os.environ["HALBERT_PERSONA_ID"]
            assert _get_persona_id() == "halbert"

    def test_custom_persona_id(self):
        from halbert_core.integrations.cognition_wiring import _get_persona_id
        with patch.dict(os.environ, {"HALBERT_PERSONA_ID": "home"}, clear=False):
            assert _get_persona_id() == "home"

    def test_scene_context_from_env(self):
        from halbert_core.integrations.cognition_wiring import _get_scene_context
        with patch.dict(os.environ, {"HALBERT_SCENE_CONTEXT": "smart home"}, clear=False):
            assert _get_scene_context() == "smart home"
