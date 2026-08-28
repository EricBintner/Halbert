# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for the screen capture module.

MSS and OpenCV are mocked — these tests verify the encode pipeline
(BGRA → BGR → downscale → JPEG → base64) and error handling without
requiring a display or the optional dependencies.
"""

import base64
import pytest
import numpy as np


# ─────────────────────────────────────────────────────────────────────────────
# Dependency check
# ─────────────────────────────────────────────────────────────────────────────

def _have_deps() -> bool:
    try:
        import mss  # noqa: F401
        import cv2  # noqa: F401
        return True
    except ImportError:
        return False


HAVE_DEPS = _have_deps()


# ─────────────────────────────────────────────────────────────────────────────
# _encode_jpeg — the core pipeline, testable without a display
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.skipif(not HAVE_DEPS, reason="mss/opencv not installed")
class TestEncodeJpeg:
    """Test the BGRA → JPEG encode pipeline."""

    def test_full_resolution_frame(self):
        from halbert_core.vision.screen_capture import ScreenCapture
        cap = ScreenCapture(quality=85, max_dim=1568)
        # 100x50 BGRA frame
        frame = np.zeros((50, 100, 4), dtype=np.uint8)
        frame[:, :, 1] = 128  # Some green
        jpeg = cap._encode_jpeg(frame)
        assert len(jpeg) > 0
        assert jpeg[:3] == b'\xff\xd8\xff'  # JPEG magic bytes

    def test_downscale_when_exceeds_max_dim(self):
        from halbert_core.vision.screen_capture import ScreenCapture
        cap = ScreenCapture(quality=85, max_dim=100)
        # 200x100 frame, should downscale to 100x50
        frame = np.zeros((100, 200, 4), dtype=np.uint8)
        jpeg = cap._encode_jpeg(frame)
        # Decode and check dimensions
        import cv2
        decoded = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
        assert decoded.shape[1] == 100  # width
        assert decoded.shape[0] == 50   # height

    def test_no_downscale_when_under_max_dim(self):
        from halbert_core.vision.screen_capture import ScreenCapture
        cap = ScreenCapture(quality=85, max_dim=500)
        frame = np.zeros((50, 100, 4), dtype=np.uint8)
        jpeg = cap._encode_jpeg(frame)
        import cv2
        decoded = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
        assert decoded.shape[1] == 100
        assert decoded.shape[0] == 50

    def test_alpha_channel_stripped(self):
        """BGRA input should produce a 3-channel BGR JPEG (no alpha)."""
        from halbert_core.vision.screen_capture import ScreenCapture
        cap = ScreenCapture(quality=85, max_dim=1568)
        frame = np.zeros((10, 10, 4), dtype=np.uint8)
        frame[:, :, 3] = 255  # Full alpha
        jpeg = cap._encode_jpeg(frame)
        import cv2
        decoded = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
        assert decoded.shape[2] == 3  # BGR, not BGRA


# ─────────────────────────────────────────────────────────────────────────────
# capture_to_base64 — end-to-end with mocked MSS
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.skipif(not HAVE_DEPS, reason="mss/opencv not installed")
class TestCaptureToBase64:
    """Test base64 output with a mocked MSS context."""

    def test_returns_valid_base64_jpeg(self, monkeypatch):
        from halbert_core.vision import screen_capture as mod

        # Create a fake frame
        fake_frame = np.zeros((100, 200, 4), dtype=np.uint8)
        fake_frame[:, :, 1] = 100  # Green channel

        class FakeScreenShot:
            """Mimics mss.ScreenShot — supports np.asarray() via __array_interface__."""
            def __init__(self, frame):
                self._frame = frame

            @property
            def __array_interface__(self):
                return {
                    "shape": self._frame.shape,
                    "typestr": f"|u{self._frame.itemsize}",
                    "data": self._frame.tobytes(),
                    "version": 3,
                }

        class FakeMSS:
            monitors = [{"top": 0, "left": 0, "width": 200, "height": 100}]

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def grab(self, monitor):
                return FakeScreenShot(fake_frame)

        # Patch the lazy import
        original_ensure = mod._ensure_deps
        mod._mss = type("FakeMssModule", (), {"mss": FakeMSS})
        mod._cv2 = __import__("cv2")
        mod._numpy = np

        try:
            cap = mod.ScreenCapture(quality=85, max_dim=1568)
            result = cap.capture_to_base64()
            # Verify it's valid base64
            decoded = base64.b64decode(result)
            assert decoded[:3] == b'\xff\xd8\xff'  # JPEG magic
        finally:
            mod._mss = None
            mod._cv2 = None
            mod._numpy = None


# ─────────────────────────────────────────────────────────────────────────────
# Error handling
# ─────────────────────────────────────────────────────────────────────────────

class TestErrorHandling:
    """Test error types and messages."""

    def test_missing_deps_raises_import_error(self):
        from halbert_core.vision import screen_capture as mod
        # Force deps to be "not loaded" and fail the import
        original = mod._mss
        mod._mss = None
        try:
            # Patch _ensure_deps to raise ImportError
            def fake_ensure():
                raise ImportError("Screen capture requires the 'mss' package.")
            mod._ensure_deps = fake_ensure
            cap = mod.ScreenCapture()
            with pytest.raises(ImportError, match="mss"):
                cap.capture_full()
        finally:
            mod._mss = original
            # Restore real _ensure_deps
            import importlib
            importlib.reload(mod)

    def test_screen_capture_error_has_type(self):
        from halbert_core.vision.screen_capture import ScreenCaptureError
        err = ScreenCaptureError("Permission denied", error_type="permission_denied")
        assert err.error_type == "permission_denied"
        assert "Permission denied" in str(err)
