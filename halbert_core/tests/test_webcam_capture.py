# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for the webcam capture module."""

import base64
import pytest
import numpy as np
from unittest.mock import MagicMock, patch


def _have_deps() -> bool:
    try:
        import cv2  # noqa: F401
        return True
    except ImportError:
        return False


HAVE_DEPS = _have_deps()


@pytest.mark.skipif(not HAVE_DEPS, reason="opencv not installed")
class TestEncodeJpeg:
    """Test the BGR → JPEG encode pipeline (OpenCV returns BGR, not BGRA)."""

    def test_full_resolution_frame(self):
        from halbert_core.vision.webcam_capture import WebcamCapture
        cap = WebcamCapture(quality=85, max_dim=768)
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        jpeg = cap._encode_jpeg(frame)
        assert len(jpeg) > 0
        assert jpeg[:3] == b'\xff\xd8\xff'  # JPEG magic

    def test_downscale_when_exceeds_max_dim(self):
        from halbert_core.vision.webcam_capture import WebcamCapture
        cap = WebcamCapture(quality=85, max_dim=100, patch_align=False)
        frame = np.zeros((200, 400, 3), dtype=np.uint8)
        jpeg = cap._encode_jpeg(frame)
        import cv2
        decoded = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
        assert decoded.shape[1] == 100
        assert decoded.shape[0] == 50

    def test_no_downscale_when_under_max_dim(self):
        from halbert_core.vision.webcam_capture import WebcamCapture
        cap = WebcamCapture(quality=85, max_dim=1000)
        frame = np.zeros((100, 200, 3), dtype=np.uint8)
        jpeg = cap._encode_jpeg(frame)
        import cv2
        decoded = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
        assert decoded.shape[1] == 200
        assert decoded.shape[0] == 100

    def test_bgr_three_channels(self):
        """OpenCV returns BGR (3 channels), no alpha to strip."""
        from halbert_core.vision.webcam_capture import WebcamCapture
        cap = WebcamCapture(quality=85, max_dim=768)
        frame = np.zeros((10, 10, 3), dtype=np.uint8)
        jpeg = cap._encode_jpeg(frame)
        import cv2
        decoded = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
        assert decoded.shape[2] == 3


class TestErrorHandling:
    def test_webcam_error_has_type(self):
        from halbert_core.vision.webcam_capture import WebcamCaptureError
        err = WebcamCaptureError("Camera in use", error_type="camera_unavailable")
        assert err.error_type == "camera_unavailable"
        assert "Camera in use" in str(err)


@pytest.mark.skipif(not HAVE_DEPS, reason="opencv not installed")
class TestGrabToBase64:
    """Test base64 output with a mocked VideoCapture."""

    def test_returns_valid_base64_jpeg(self):
        from halbert_core.vision import webcam_capture as mod

        fake_frame = np.zeros((100, 200, 3), dtype=np.uint8)
        fake_frame[:, :, 1] = 100  # Green

        class FakeCap:
            def __init__(self, index):
                pass
            def isOpened(self):
                return True
            def read(self):
                # First 5 calls are warmup (discarded), then real frame
                if not hasattr(self, '_count'):
                    self._count = 0
                self._count += 1
                if self._count <= 5:
                    return True, fake_frame
                return True, fake_frame
            def release(self):
                pass

        mod._cv2 = __import__("cv2")
        mod._numpy = np

        with patch.object(mod._cv2, 'VideoCapture', FakeCap):
            cap = mod.WebcamCapture(quality=85, max_dim=768)
            result = cap.grab_to_base64()
            decoded = base64.b64decode(result)
            assert decoded[:3] == b'\xff\xd8\xff'

    def test_camera_unavailable_raises(self):
        from halbert_core.vision import webcam_capture as mod

        class FakeCapClosed:
            def __init__(self, index):
                pass
            def isOpened(self):
                return False
            def release(self):
                pass

        mod._cv2 = __import__("cv2")
        mod._numpy = np

        with patch.object(mod._cv2, 'VideoCapture', FakeCapClosed):
            cap = mod.WebcamCapture()
            with pytest.raises(mod.WebcamCaptureError, match="Cannot open camera"):
                cap.grab_frame()
