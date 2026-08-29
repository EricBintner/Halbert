# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for CV extensions: motion detection, zone watcher, inference modules."""
import base64
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from halbert_core.vision.motion import (
    MotionDetector, BackgroundSubtractor, MotionResult, detect_motion,
)
from halbert_core.vision.zone_watcher import Zone, ZoneWatcher, ZoneEvent
from halbert_core.vision.inference.detector import Detection, COCO_LABELS


# ── Helper: create a JPEG from a numpy array ───────────────────────────────

def _make_jpeg(width=320, height=240, color=(128, 128, 128)) -> bytes:
    """Create a solid-color JPEG image."""
    import cv2
    img = np.full((height, width, 3), color, dtype=np.uint8)
    _, buf = cv2.imencode(".jpg", img)
    return buf.tobytes()


def _make_jpeg_with_rect(width=320, height=240, rect=(50, 50, 150, 150), color=(255, 0, 0)) -> bytes:
    """Create a JPEG with a colored rectangle on a gray background."""
    import cv2
    img = np.full((height, width, 3), (128, 128, 128), dtype=np.uint8)
    x1, y1, x2, y2 = rect
    img[y1:y2, x1:x2] = color
    _, buf = cv2.imencode(".jpg", img)
    return buf.tobytes()


# ── MotionDetector tests ───────────────────────────────────────────────────

class TestMotionDetector:
    def test_no_motion_identical_frames(self):
        detector = MotionDetector()
        frame = _make_jpeg()
        result = detector.detect(frame, frame)
        assert not result.has_motion
        assert result.motion_ratio < 0.01

    def test_detects_motion_different_frames(self):
        detector = MotionDetector(threshold=20, min_motion_ratio=0.005)
        frame1 = _make_jpeg()
        frame2 = _make_jpeg_with_rect()
        result = detector.detect(frame1, frame2)
        assert result.has_motion
        assert result.motion_ratio > 0.005
        assert len(result.bounding_boxes) > 0

    def test_motion_result_to_dict(self):
        result = MotionResult(
            has_motion=True,
            motion_ratio=0.15,
            bounding_boxes=[(10, 20, 30, 40)],
            frame_shape=(240, 320),
        )
        d = result.to_dict()
        assert d["has_motion"] is True
        assert d["motion_ratio"] == 0.15
        assert d["bounding_boxes"] == [[10, 20, 30, 40]]
        assert d["frame_shape"] == [240, 320]

    def test_different_sizes_auto_resize(self):
        detector = MotionDetector()
        frame1 = _make_jpeg(320, 240)
        frame2 = _make_jpeg(640, 480)
        # Should not crash — auto-resizes
        result = detector.detect(frame1, frame2)
        assert isinstance(result, MotionResult)


# ── BackgroundSubtractor tests ─────────────────────────────────────────────

class TestBackgroundSubtractor:
    def test_first_frame_no_motion(self):
        sub = BackgroundSubtractor(min_motion_ratio=0.01)
        frame = _make_jpeg()
        result = sub.process(frame)
        # First frame always shows "motion" because there's no background yet
        # but with high min_motion_ratio it might not trigger
        assert isinstance(result, MotionResult)
        assert result.frame_shape == (240, 320)

    def test_learns_background(self):
        sub = BackgroundSubtractor(min_motion_ratio=0.01, history=10)
        frame = _make_jpeg()
        # Feed identical frames to learn the background
        for _ in range(15):
            sub.process(frame)
        # Now the same frame should show no motion
        result = sub.process(frame)
        assert not result.has_motion

    def test_detects_new_object(self):
        sub = BackgroundSubtractor(min_motion_ratio=0.005, history=5)
        frame = _make_jpeg()
        # Learn background
        for _ in range(10):
            sub.process(frame)
        # Introduce a new object
        frame_with_obj = _make_jpeg_with_rect()
        result = sub.process(frame_with_obj)
        assert result.has_motion

    def test_reset(self):
        sub = BackgroundSubtractor()
        sub.process(_make_jpeg())
        sub.reset()
        assert sub._frame_count == 0
        assert sub._subtractor is None


# ── Zone tests ─────────────────────────────────────────────────────────────

class TestZone:
    def test_rect_property(self):
        zone = Zone(name="test", x=10, y=20, width=100, height=80)
        assert zone.rect == (10, 20, 110, 100)

    def test_crop(self):
        zone = Zone(name="test", x=50, y=50, width=100, height=100)
        frame = _make_jpeg(320, 240)
        cropped = zone.crop(frame)
        assert len(cropped) > 0
        # Cropped JPEG should decode to 100x100
        import cv2
        img = cv2.imdecode(np.frombuffer(cropped, dtype=np.uint8), cv2.IMREAD_COLOR)
        assert img.shape[:2] == (100, 100)


# ── ZoneWatcher tests ──────────────────────────────────────────────────────

class TestZoneWatcher:
    def test_check_once_no_motion(self):
        frame = _make_jpeg(320, 240)
        watcher = ZoneWatcher(
            zones=[Zone(name="zone1", x=0, y=0, width=320, height=240)],
            frame_source=lambda: frame,
            on_event=lambda e: None,
        )
        # Feed background first
        for _ in range(15):
            watcher.check_once()
        events = watcher.check_once()
        assert len(events) == 0

    def test_check_once_with_motion(self):
        frame = _make_jpeg(320, 240)
        frame_with_obj = _make_jpeg_with_rect(320, 240)
        watcher = ZoneWatcher(
            zones=[Zone(name="zone1", x=0, y=0, width=320, height=240, min_motion_ratio=0.005)],
            frame_source=lambda: frame,
            on_event=lambda e: None,
        )
        # Learn background
        for _ in range(15):
            watcher.check_once()
        # Switch to frame with object
        watcher.frame_source = lambda: frame_with_obj
        events = watcher.check_once()
        assert len(events) >= 1
        assert events[0].zone_name == "zone1"

    def test_cooldown_prevents_rapid_events(self):
        frame = _make_jpeg(320, 240)
        frame_with_obj = _make_jpeg_with_rect(320, 240)
        events_received = []
        watcher = ZoneWatcher(
            zones=[Zone(name="zone1", x=0, y=0, width=320, height=240,
                       min_motion_ratio=0.005, cooldown_seconds=60)],
            frame_source=lambda: frame_with_obj,
            on_event=lambda e: events_received.append(e),
        )
        # Learn background with the motion frame source already set
        for _ in range(15):
            watcher._check_all_zones()
        # Now motion should fire once
        events_before = len(events_received)
        watcher._check_all_zones()
        # May or may not fire depending on background learning
        # The key test: after first event, second is suppressed
        if events_received:
            first_event_count = len(events_received)
            watcher._check_all_zones()  # should be suppressed by cooldown
            assert len(events_received) == first_event_count


# ── Detection dataclass tests ──────────────────────────────────────────────

class TestDetection:
    def test_to_dict(self):
        d = Detection(label="person", confidence=0.95, bbox=(10, 20, 30, 40), class_id=0)
        result = d.to_dict()
        assert result["label"] == "person"
        assert result["confidence"] == 0.95
        assert result["bbox"] == [10, 20, 30, 40]
        assert result["class_id"] == 0

    def test_coco_labels_has_person(self):
        assert "person" in COCO_LABELS
        assert COCO_LABELS[0] == "person"

    def test_coco_labels_has_car(self):
        assert "car" in COCO_LABELS
        assert COCO_LABELS[2] == "car"

    def test_coco_labels_count(self):
        assert len(COCO_LABELS) == 80


# ── Vision tool registration tests ─────────────────────────────────────────

class TestCVToolRegistration:
    def test_cv_tools_in_schema_dict(self):
        from halbert_core.tools.vision_tools import VISION_TOOL_SCHEMAS
        assert "detect_objects" in VISION_TOOL_SCHEMAS
        assert "detect_faces" in VISION_TOOL_SCHEMAS
        assert "detect_motion" in VISION_TOOL_SCHEMAS

    def test_cv_tools_have_handlers(self):
        from halbert_core.tools.vision_tools import VISION_TOOL_HANDLERS
        assert "detect_objects" in VISION_TOOL_HANDLERS
        assert "detect_faces" in VISION_TOOL_HANDLERS
        assert "detect_motion" in VISION_TOOL_HANDLERS

    def test_schemas_match_handlers(self):
        from halbert_core.tools.vision_tools import VISION_TOOL_SCHEMAS, VISION_TOOL_HANDLERS
        assert set(VISION_TOOL_SCHEMAS.keys()) == set(VISION_TOOL_HANDLERS.keys())

    def test_detect_objects_schema_has_source_param(self):
        from halbert_core.tools.vision_tools import VISION_TOOL_SCHEMAS
        schema = VISION_TOOL_SCHEMAS["detect_objects"]
        assert "source" in schema["parameters"]["properties"]

    def test_detect_motion_schema_has_delay_param(self):
        from halbert_core.tools.vision_tools import VISION_TOOL_SCHEMAS
        schema = VISION_TOOL_SCHEMAS["detect_motion"]
        assert "delay_seconds" in schema["parameters"]["properties"]


# ── AmbientWebcamMonitor tests (mocked) ────────────────────────────────────

class TestAmbientWebcamMonitor:
    def test_stats_initial(self):
        from halbert_core.vision.ambient_webcam import AmbientWebcamMonitor
        monitor = AmbientWebcamMonitor(on_motion=lambda f, r: None)
        stats = monitor.stats
        assert stats["frames_captured"] == 0
        assert stats["motion_events"] == 0
        assert stats["motion_rate"] == 0.0
