# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for the Wayland capture module.

These tests verify the module structure and encoding pipeline without
requiring an actual Wayland session or D-Bus connection.
"""

import pytest
import numpy as np

try:
    import cv2
    HAVE_CV2 = True
except ImportError:
    HAVE_CV2 = False


class TestIsWayland:
    def test_returns_false_when_no_wayland_env(self, monkeypatch):
        from halbert_core.vision.wayland_capture import is_wayland
        monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
        monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
        assert is_wayland() is False

    def test_returns_true_when_wayland_display_set(self, monkeypatch):
        from halbert_core.vision.wayland_capture import is_wayland
        monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
        assert is_wayland() is True

    def test_returns_true_when_session_type_wayland(self, monkeypatch):
        from halbert_core.vision.wayland_capture import is_wayland
        monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
        monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
        assert is_wayland() is True


class TestWaylandCaptureError:
    def test_has_error_type(self):
        from halbert_core.vision.wayland_capture import WaylandCaptureError
        err = WaylandCaptureError("test", error_type="portal_error")
        assert err.error_type == "portal_error"


@pytest.mark.skipif(not HAVE_CV2, reason="opencv not installed")
class TestWaylandEncodeJpeg:
    def test_full_resolution_frame(self):
        from halbert_core.vision.wayland_capture import WaylandCapture
        cap = WaylandCapture(quality=85, max_dim=768, patch_align=False)
        frame = np.zeros((100, 200, 3), dtype=np.uint8)
        jpeg = cap._encode_jpeg(frame)
        assert len(jpeg) > 0

    def test_downscale_when_exceeds_max_dim(self):
        from halbert_core.vision.wayland_capture import WaylandCapture
        cap = WaylandCapture(quality=85, max_dim=100, patch_align=False)
        frame = np.zeros((200, 400, 3), dtype=np.uint8)
        jpeg = cap._encode_jpeg(frame)
        decoded = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
        assert decoded.shape[1] == 100
        assert decoded.shape[0] == 50

    def test_patch_alignment(self):
        from halbert_core.vision.wayland_capture import WaylandCapture
        cap = WaylandCapture(quality=85, max_dim=1568, patch_align=True)
        # 6048x3928 -> 1568x1018 -> align to 1344x1008
        frame = np.zeros((3928, 6048, 3), dtype=np.uint8)
        jpeg = cap._encode_jpeg(frame)
        decoded = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
        assert decoded.shape[1] == 1344
        assert decoded.shape[0] == 1008

    def test_grayscale(self):
        from halbert_core.vision.wayland_capture import WaylandCapture
        cap = WaylandCapture(quality=85, max_dim=768, grayscale=True)
        frame = np.zeros((100, 200, 3), dtype=np.uint8)
        jpeg = cap._encode_jpeg(frame)
        decoded = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_UNCHANGED)
        assert len(decoded.shape) == 2  # Grayscale
