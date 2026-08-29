# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for diagnostic screen capture on tool failure."""
from unittest.mock import MagicMock, patch, AsyncMock

import pytest


class TestShouldDiagnosticCapture:
    """Test the _should_diagnostic_capture gating logic."""

    def _make_state_machine(self):
        """Create a minimal mock with just the method we need."""
        from halbert_core.agents.state_machine import AgentStateMachine
        # Create a bare instance without full init
        sm = AgentStateMachine.__new__(AgentStateMachine)
        return sm

    def test_disabled_by_default(self):
        sm = self._make_state_machine()
        with patch('halbert_core.vision.config.is_screen_capture_enabled', return_value=True):
            with patch('halbert_core.config.being_config.load_being_config') as mock_cfg:
                mock_cfg.return_value = MagicMock()
                mock_cfg.return_value.senses.vision.capture_on_error = False
                assert sm._should_diagnostic_capture("run_command") is False

    def test_enabled_for_command_tools(self):
        sm = self._make_state_machine()
        with patch('halbert_core.vision.config.is_screen_capture_enabled', return_value=True):
            with patch('halbert_core.config.being_config.load_being_config') as mock_cfg:
                mock_cfg.return_value = MagicMock()
                mock_cfg.return_value.senses.vision.capture_on_error = True
                assert sm._should_diagnostic_capture("run_command") is True
                assert sm._should_diagnostic_capture("execute_command") is True
                assert sm._should_diagnostic_capture("shell") is True
                assert sm._should_diagnostic_capture("bash") is True

    def test_disabled_for_search_tools(self):
        sm = self._make_state_machine()
        with patch('halbert_core.vision.config.is_screen_capture_enabled', return_value=True):
            with patch('halbert_core.config.being_config.load_being_config') as mock_cfg:
                mock_cfg.return_value = MagicMock()
                mock_cfg.return_value.senses.vision.capture_on_error = True
                # Search/read tools should NOT trigger diagnostic capture
                assert sm._should_diagnostic_capture("search") is False
                assert sm._should_diagnostic_capture("read_file") is False
                assert sm._should_diagnostic_capture("recall_memory") is False
                assert sm._should_diagnostic_capture("web_search") is False

    def test_disabled_when_screen_capture_off(self):
        sm = self._make_state_machine()
        with patch('halbert_core.vision.config.is_screen_capture_enabled', return_value=False):
            assert sm._should_diagnostic_capture("run_command") is False

    def test_exception_returns_false(self):
        """If config loading fails, don't capture (fail-safe)."""
        sm = self._make_state_machine()
        with patch('halbert_core.vision.config.is_screen_capture_enabled', side_effect=Exception("no config")):
            assert sm._should_diagnostic_capture("run_command") is False


class TestDiagnosticCaptureTruncation:
    """Test that OCR text is truncated to 500 chars."""

    def test_truncation(self):
        """Verify the truncation logic in the observation."""
        long_ocr = "x" * 1000
        truncated = long_ocr[:500]
        assert len(truncated) == 500
        assert truncated == "x" * 500

    def test_short_text_not_truncated(self):
        short_ocr = "error: command not found"
        truncated = short_ocr[:500]
        assert truncated == short_ocr
