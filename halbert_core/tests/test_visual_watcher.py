# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for the VisualWatcher proactive screen monitor."""
import hashlib
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from halbert_core.config.being_config import BeingConfig, SensesConfig, SensesVisionConfig
from halbert_core.vision.watcher import VisualWatcher


def _make_config(
    enabled=True,
    proactive=True,
    interval=60,
    patterns=None,
):
    if patterns is None:
        patterns = ["error", "failed", "panic"]
    return BeingConfig(senses={"vision": {
        "enabled": enabled,
        "proactive_monitoring": proactive,
        "interval_seconds": interval,
        "error_patterns": patterns,
    }})


def _make_gate(should_notify=True):
    gate = MagicMock()
    gate.should_notify.return_value = (should_notify, "test")
    return gate


class TestVisualWatcherInit:
    def test_compiles_patterns(self):
        cfg = _make_config(patterns=["error", "failed"])
        w = VisualWatcher(cfg, _make_gate())
        assert len(w._compiled_patterns) == 2

    def test_bad_pattern_skipped(self):
        cfg = _make_config(patterns=["error", "[invalid("])
        w = VisualWatcher(cfg, _make_gate())
        assert len(w._compiled_patterns) == 1  # bad one skipped


class TestVisualWatcherDedup:
    """Stage 1: hash-based dedup skips OCR on unchanged screens."""

    def test_unchanged_screen_skips_publish(self):
        cfg = _make_config()
        w = VisualWatcher(cfg, _make_gate())
        # First capture: new hash
        img = "base64data_v1"
        h = hashlib.md5(img.encode()).hexdigest()
        w._last_hash = h
        w._unchanged_count = 0

        # Same hash → should skip
        with patch.object(w, '_capture_active_window', return_value={"image": img, "ocr_text": "error"}):
            with patch.object(w, '_publish_finding') as mock_pub:
                w._check_screen()
                mock_pub.assert_not_called()
        assert w._unchanged_count == 1

    def test_changed_screen_processes(self):
        cfg = _make_config()
        w = VisualWatcher(cfg, _make_gate())
        w._last_hash = "old_hash"

        with patch.object(w, '_capture_active_window', return_value={"image": "new_img", "ocr_text": "error occurred"}):
            with patch.object(w, '_publish_finding') as mock_pub:
                w._check_screen()
                mock_pub.assert_called_once()
        assert w._unchanged_count == 0


class TestVisualWatcherPatternMatch:
    def test_matches_error_pattern(self):
        cfg = _make_config(patterns=["error", "failed"])
        w = VisualWatcher(cfg, _make_gate())
        assert w._match_patterns("something error happened") == "error"

    def test_matches_failed_pattern(self):
        cfg = _make_config(patterns=["error", "failed"])
        w = VisualWatcher(cfg, _make_gate())
        assert w._match_patterns("operation failed") == "failed"

    def test_no_match(self):
        cfg = _make_config(patterns=["error", "failed"])
        w = VisualWatcher(cfg, _make_gate())
        assert w._match_patterns("all systems normal") is None

    def test_case_insensitive(self):
        cfg = _make_config(patterns=["ERROR"])
        w = VisualWatcher(cfg, _make_gate())
        assert w._match_patterns("error occurred") is not None


class TestVisualWatcherPublish:
    def test_publishes_on_match(self):
        cfg = _make_config()
        gate = _make_gate(should_notify=True)
        w = VisualWatcher(cfg, gate, finding_store=MagicMock())

        with patch.object(w, '_capture_active_window', return_value={
            "image": "img_data", "ocr_text": "CUDA error: out of memory"
        }):
            with patch('halbert_core.vision.watcher.get_event_bus') as mock_bus:
                mock_bus_instance = MagicMock()
                mock_bus_instance.publish = AsyncMock()
                mock_bus.return_value = mock_bus_instance
                w._check_screen()

                # Gate should have been called
                assert gate.should_notify.called
                # Event should have been published
                assert mock_bus_instance.publish.called

    def test_suppressed_by_gate(self):
        cfg = _make_config()
        gate = _make_gate(should_notify=False)
        w = VisualWatcher(cfg, gate, finding_store=MagicMock())

        with patch.object(w, '_capture_active_window', return_value={
            "image": "img_data", "ocr_text": "error occurred"
        }):
            with patch('halbert_core.vision.watcher.get_event_bus') as mock_bus:
                mock_bus_instance = MagicMock()
                mock_bus_instance.publish = AsyncMock()
                mock_bus.return_value = mock_bus_instance
                w._check_screen()

                # Gate called but event NOT published
                assert gate.should_notify.called
                assert not mock_bus_instance.publish.called

    def test_critical_severity_for_panic(self):
        cfg = _make_config(patterns=["kernel panic"])
        gate = _make_gate()
        w = VisualWatcher(cfg, gate, finding_store=MagicMock())

        with patch.object(w, '_capture_active_window', return_value={
            "image": "img", "ocr_text": "kernel panic - not syncing"
        }):
            with patch('halbert_core.vision.watcher.get_event_bus') as mock_bus:
                mock_bus_instance = MagicMock()
                mock_bus_instance.publish = AsyncMock()
                mock_bus.return_value = mock_bus_instance
                w._check_screen()

                # Check the event was published with critical severity
                call_args = mock_bus_instance.publish.call_args
                event = call_args[0][0]
                assert event.severity == "critical"
                assert event.category == "vision"

    def test_warning_severity_for_error(self):
        cfg = _make_config(patterns=["error"])
        gate = _make_gate()
        w = VisualWatcher(cfg, gate, finding_store=MagicMock())

        with patch.object(w, '_capture_active_window', return_value={
            "image": "img", "ocr_text": "error occurred"
        }):
            with patch('halbert_core.vision.watcher.get_event_bus') as mock_bus:
                mock_bus_instance = MagicMock()
                mock_bus_instance.publish = AsyncMock()
                mock_bus.return_value = mock_bus_instance
                w._check_screen()

                call_args = mock_bus_instance.publish.call_args
                event = call_args[0][0]
                assert event.severity == "warning"


class TestVisualWatcherAdaptiveInterval:
    def test_base_interval_when_changing(self):
        cfg = _make_config(interval=30)
        w = VisualWatcher(cfg, _make_gate())
        w._unchanged_count = 0
        assert w._adaptive_interval() == 30

    def test_backoff_when_unchanged(self):
        cfg = _make_config(interval=30)
        w = VisualWatcher(cfg, _make_gate())
        w._unchanged_count = 2
        # factor = min(1 + 2*0.5, 5.0) = 2.0
        assert w._adaptive_interval() == 60

    def test_backoff_capped_at_5x(self):
        cfg = _make_config(interval=30)
        w = VisualWatcher(cfg, _make_gate())
        w._unchanged_count = 100
        assert w._adaptive_interval() == 150  # 30 * 5


class TestVisualWatcherCaptureFailure:
    def test_capture_failure_does_not_crash(self):
        cfg = _make_config()
        w = VisualWatcher(cfg, _make_gate())

        with patch.object(w, '_capture_active_window', return_value=None):
            with patch.object(w, '_publish_finding') as mock_pub:
                w._check_screen()
                mock_pub.assert_not_called()

    def test_no_ocr_text_does_not_publish(self):
        cfg = _make_config()
        w = VisualWatcher(cfg, _make_gate())
        w._last_hash = "old"

        with patch.object(w, '_capture_active_window', return_value={
            "image": "new_img", "ocr_text": ""
        }):
            with patch.object(w, '_publish_finding') as mock_pub:
                w._check_screen()
                mock_pub.assert_not_called()
