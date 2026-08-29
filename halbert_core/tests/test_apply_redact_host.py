# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for Task 4 — redact_host parameter on SourcePrepSetup.apply."""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from halbert_core.integrations.sourceprep_setup import SourcePrepSetup


class TestRedactHostParam:
    """The apply method passes redact_host through to _stage_host_tree."""

    def test_default_redact_host_is_true(self):
        """Default should be redact=True (backward compat)."""
        setup = SourcePrepSetup.__new__(SourcePrepSetup)
        # Check the default in the signature
        import inspect
        sig = inspect.signature(SourcePrepSetup.apply)
        assert sig.parameters["redact_host"].default is True

    @patch.object(SourcePrepSetup, "_stage_host_tree")
    @patch.object(SourcePrepSetup, "_health_ok", return_value=True)
    @patch.object(SourcePrepSetup, "_find_or_create_project")
    @patch.object(SourcePrepSetup, "_put_config")
    @patch.object(SourcePrepSetup, "_reconcile_scopes")
    def test_apply_passes_redact_host_false(
        self, mock_reconcile, mock_put, mock_find, mock_health, mock_stage
    ):
        """apply(redact_host=False) should pass redact=False to _stage_host_tree."""
        setup = SourcePrepSetup.__new__(SourcePrepSetup)
        setup.template_path = "/dev/null"
        setup.project_root_override = None
        setup.base_url = "http://localhost:1"
        setup.api_key = ""

        mock_stage.return_value = 0
        mock_find.return_value = {"id": "test", "_created": False}
        mock_reconcile.return_value = {}

        # Mock load_template
        with patch("halbert_core.integrations.sourceprep_setup.load_template") as mock_template:
            mock_template.return_value = {
                "project": {
                    "name": "test",
                    "root": "/tmp/test-root",
                    "config": {},
                },
                "scopes": [],
            }
            with patch.object(SourcePrepSetup, "_build_full", return_value={}):
                try:
                    setup.apply(build=True, redact_host=False)
                except Exception:
                    pass  # May fail on missing dirs, that's fine

        # Verify _stage_host_tree was called with redact=False
        assert mock_stage.called
        _, kwargs = mock_stage.call_args
        assert kwargs.get("redact") is False

    @patch.object(SourcePrepSetup, "_stage_host_tree")
    @patch.object(SourcePrepSetup, "_health_ok", return_value=True)
    @patch.object(SourcePrepSetup, "_find_or_create_project")
    @patch.object(SourcePrepSetup, "_put_config")
    @patch.object(SourcePrepSetup, "_reconcile_scopes")
    def test_apply_default_redact_host_true(
        self, mock_reconcile, mock_put, mock_find, mock_health, mock_stage
    ):
        """apply() with no redact_host should pass redact=True (default)."""
        setup = SourcePrepSetup.__new__(SourcePrepSetup)
        setup.template_path = "/dev/null"
        setup.project_root_override = None
        setup.base_url = "http://localhost:1"
        setup.api_key = ""

        mock_stage.return_value = 0
        mock_find.return_value = {"id": "test", "_created": False}
        mock_reconcile.return_value = {}

        with patch("halbert_core.integrations.sourceprep_setup.load_template") as mock_template:
            mock_template.return_value = {
                "project": {
                    "name": "test",
                    "root": "/tmp/test-root",
                    "config": {},
                },
                "scopes": [],
            }
            with patch.object(SourcePrepSetup, "_build_full", return_value={}):
                try:
                    setup.apply(build=True)
                except Exception:
                    pass

        assert mock_stage.called
        _, kwargs = mock_stage.call_args
        assert kwargs.get("redact") is True
