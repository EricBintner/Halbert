# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for vision cognition, disk cache, and episodic memory wiring."""
import base64
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from halbert_core.vision.cache import VisionCache


# ── VisionCache tests ──────────────────────────────────────────────────────

class TestVisionCacheStore:
    def test_store_creates_file(self, tmp_path):
        cache = VisionCache(base_dir=str(tmp_path))
        # 1x1 JPEG
        jpeg_bytes = bytes([0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0xFF, 0xD9])
        b64 = base64.b64encode(jpeg_bytes).decode()
        uri = cache.store(b64)
        assert uri.startswith("file://")
        assert uri.endswith(".jpg")
        assert Path(uri.replace("file://", "")).exists()

    def test_store_dedup_same_image(self, tmp_path):
        cache = VisionCache(base_dir=str(tmp_path))
        b64 = base64.b64encode(b"fake_image_data").decode()
        uri1 = cache.store(b64)
        uri2 = cache.store(b64)
        assert uri1 == uri2
        assert cache.file_count() == 1

    def test_store_different_images(self, tmp_path):
        cache = VisionCache(base_dir=str(tmp_path))
        uri1 = cache.store(base64.b64encode(b"img1").decode())
        uri2 = cache.store(base64.b64encode(b"img2").decode())
        assert uri1 != uri2
        assert cache.file_count() == 2


class TestVisionCacheCleanup:
    def test_cleanup_deletes_expired(self, tmp_path):
        cache = VisionCache(base_dir=str(tmp_path), ttl_days=0)
        # Store a file
        b64 = base64.b64encode(b"old_image").decode()
        cache.store(b64)
        assert cache.file_count() == 1
        # Manually set mtime to 10 days ago
        import time
        for f in tmp_path.glob("*.jpg"):
            old_time = time.time() - (10 * 86400)
            os.utime(f, (old_time, old_time))
        deleted = cache.cleanup()
        assert deleted == 1
        assert cache.file_count() == 0

    def test_cleanup_prunes_to_quota(self, tmp_path):
        # Very small quota — each image is ~50 bytes decoded
        cache = VisionCache(base_dir=str(tmp_path), ttl_days=365, max_bytes=80)
        # Store 3 files
        for i in range(3):
            data = f"img_{i}_" + "x" * 40  # ~50 bytes each
            cache.store(base64.b64encode(data.encode()).decode())
        assert cache.file_count() == 3
        assert cache.total_size() > 80  # over quota
        # Set all mtimes so they're ordered (oldest first)
        import time
        files = sorted(tmp_path.glob("*.jpg"))
        base_time = time.time() - 100
        for i, f in enumerate(files):
            t = base_time + i
            os.utime(f, (t, t))
        deleted = cache.cleanup()
        # Should have deleted at least 1 to get under quota
        assert deleted >= 1
        # Remaining files should be under quota
        assert cache.total_size() <= 80

    def test_cleanup_keeps_fresh_files(self, tmp_path):
        cache = VisionCache(base_dir=str(tmp_path), ttl_days=7, max_bytes=10 * 1024 * 1024)
        cache.store(base64.b64encode(b"fresh").decode())
        deleted = cache.cleanup()
        assert deleted == 0
        assert cache.file_count() == 1


class TestVisionCacheHelpers:
    def test_total_size(self, tmp_path):
        cache = VisionCache(base_dir=str(tmp_path))
        cache.store(base64.b64encode(b"12345678").decode())
        assert cache.total_size() == 8

    def test_file_count(self, tmp_path):
        cache = VisionCache(base_dir=str(tmp_path))
        assert cache.file_count() == 0
        cache.store(base64.b64encode(b"a").decode())
        assert cache.file_count() == 1

    def test_get_uri_existing(self, tmp_path):
        cache = VisionCache(base_dir=str(tmp_path))
        import hashlib
        b64 = base64.b64encode(b"test").decode()
        h = hashlib.md5(b64.encode("ascii", errors="ignore")).hexdigest()
        cache.store(b64)
        uri = cache.get_uri(h)
        assert uri is not None
        assert uri.startswith("file://")

    def test_get_uri_missing(self, tmp_path):
        cache = VisionCache(base_dir=str(tmp_path))
        assert cache.get_uri("nonexistent") is None


# ── System event mapper visual_anomaly tests ──────────────────────────────

class TestVisualAnomalyEvent:
    """Test that visual_anomaly events produce cognitive effects."""

    def _make_mock_cognition(self):
        cognition = MagicMock()
        cognition.worries = MagicMock()
        cognition.emotional_state = MagicMock()
        cognition.drives = MagicMock()
        cognition.worries.get_active_worries.return_value = []
        return cognition

    def _make_mapper(self):
        from halbert_core.integrations.system_event_mapper import SystemEventMapper
        mapper = SystemEventMapper()
        # Mock _emotion and _drive to avoid haloysius dependency
        mapper._emotion = MagicMock(return_value=MagicMock())
        mapper._drive = MagicMock(return_value=MagicMock())
        return mapper

    def test_visual_anomaly_adds_worry(self):
        mapper = self._make_mapper()
        cognition = self._make_mock_cognition()
        mapper._apply_event_to_cognition(cognition, {
            "type": "visual_anomaly",
            "severity": "warning",
            "source": "screen:active_window",
            "detail": "error: CUDA out of memory",
            "timestamp": 0,
        })
        assert cognition.worries.add_worry.called
        call_kwargs = cognition.worries.add_worry.call_args
        assert "visual_stability" in str(call_kwargs)
        assert "CUDA" in str(call_kwargs)

    def test_visual_anomaly_critical_higher_intensity(self):
        mapper = self._make_mapper()
        cognition = self._make_mock_cognition()
        mapper._apply_event_to_cognition(cognition, {
            "type": "visual_anomaly",
            "severity": "critical",
            "source": "screen:active_window",
            "detail": "kernel panic",
            "timestamp": 0,
        })
        # Critical should have higher intensity than warning
        worry_call = cognition.worries.add_worry.call_args
        intensity = worry_call[1]["intensity"]
        assert intensity == 0.7

    def test_visual_anomaly_warning_intensity(self):
        mapper = self._make_mapper()
        cognition = self._make_mock_cognition()
        mapper._apply_event_to_cognition(cognition, {
            "type": "visual_anomaly",
            "severity": "warning",
            "source": "screen:active_window",
            "detail": "error occurred",
            "timestamp": 0,
        })
        worry_call = cognition.worries.add_worry.call_args
        intensity = worry_call[1]["intensity"]
        assert intensity == 0.4

    def test_visual_anomaly_adds_vigilance_emotion(self):
        mapper = self._make_mapper()
        cognition = self._make_mock_cognition()
        mapper._apply_event_to_cognition(cognition, {
            "type": "visual_anomaly",
            "severity": "warning",
            "source": "screen:active_window",
            "detail": "error occurred",
            "timestamp": 0,
        })
        assert cognition.emotional_state.add_emotion.called
        # Check VIGILANCE was requested
        emotion_call = mapper._emotion.call_args
        assert emotion_call[0][0] == "VIGILANCE"

    def test_visual_anomaly_adds_competence_drive(self):
        mapper = self._make_mapper()
        cognition = self._make_mock_cognition()
        mapper._apply_event_to_cognition(cognition, {
            "type": "visual_anomaly",
            "severity": "warning",
            "source": "screen:active_window",
            "detail": "error occurred",
            "timestamp": 0,
        })
        assert cognition.drives.add_drive.called
        drive_call = mapper._drive.call_args
        assert drive_call[0][0] == "COMPETENCE"


# ── VisualWatcher memory integration tests ─────────────────────────────────

class TestVisualWatcherMemory:
    def test_memory_stored_on_anomaly(self):
        from halbert_core.config.being_config import BeingConfig
        from halbert_core.vision.watcher import VisualWatcher

        cfg = BeingConfig(senses={"vision": {
            "enabled": True, "proactive_monitoring": True,
            "error_patterns": ["error"],
        }})
        gate = MagicMock()
        gate.should_notify.return_value = (True, "test")
        memory_store = MagicMock()

        w = VisualWatcher(cfg, gate, memory_store=memory_store)

        with patch.object(w, '_capture_active_window', return_value={
            "image": "img_data", "ocr_text": "error occurred"
        }):
            with patch('halbert_core.vision.watcher.get_event_bus') as mock_bus:
                mock_bus_instance = MagicMock()
                mock_bus_instance.publish = AsyncMock()
                mock_bus.return_value = mock_bus_instance
                with patch('halbert_core.vision.cache.VisionCache.store', return_value="file:///tmp/test.jpg"):
                    w._check_screen()

        assert memory_store.store.called
        call_args = memory_store.store.call_args
        # Should store with EPISODIC memory type
        assert "EPISODIC" in str(call_args) or "episodic" in str(call_args).lower()
        # Should have screenshot_uri in metadata, not base64
        metadata = call_args[1].get("metadata", {}) if "metadata" in call_args[1] else {}
        if not metadata:
            # Might be positional
            for arg in call_args[0]:
                if isinstance(arg, dict):
                    metadata = arg
                    break
        assert "screenshot_uri" in str(metadata)

    def test_no_memory_store_no_crash(self):
        from halbert_core.config.being_config import BeingConfig
        from halbert_core.vision.watcher import VisualWatcher

        cfg = BeingConfig(senses={"vision": {
            "enabled": True, "error_patterns": ["error"],
        }})
        gate = MagicMock()
        gate.should_notify.return_value = (True, "test")
        # memory_store=None (default)
        w = VisualWatcher(cfg, gate)

        with patch.object(w, '_capture_active_window', return_value={
            "image": "img", "ocr_text": "error"
        }):
            with patch('halbert_core.vision.watcher.get_event_bus') as mock_bus:
                mock_bus_instance = MagicMock()
                mock_bus_instance.publish = AsyncMock()
                mock_bus.return_value = mock_bus_instance
                w._check_screen()  # should not crash
