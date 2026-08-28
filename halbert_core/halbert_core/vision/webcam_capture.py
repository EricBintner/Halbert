# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Webcam capture via OpenCV.

Single-frame grab, not continuous streaming. The camera is opened
per-capture and released immediately — the LED lights only momentarily,
and the 'Halbert is looking' state is explicit and brief.
"""

from __future__ import annotations

import base64
import logging
from typing import Optional

logger = logging.getLogger("halbert.vision.webcam")

_cv2 = None
_numpy = None


def _ensure_deps() -> None:
    """Import cv2 and numpy on first use."""
    global _cv2, _numpy
    if _cv2 is not None:
        return
    try:
        import cv2 as _cv2_mod
        _cv2 = _cv2_mod
    except ImportError:
        raise ImportError(
            "Webcam capture requires the 'opencv-python' package. "
            "Install with: pip install opencv-python"
        )
    try:
        import numpy as _np_mod
        _numpy = _np_mod
    except ImportError:
        raise ImportError(
            "Webcam capture requires the 'numpy' package. "
            "Install with: pip install numpy"
        )


class WebcamCaptureError(Exception):
    """Raised when webcam capture fails (permission, no camera, etc.)."""

    def __init__(self, message: str, error_type: str = "webcam_failed"):
        super().__init__(message)
        self.error_type = error_type


class WebcamCapture:
    """Webcam capture via OpenCV. Lazy-open, single-frame grab.

    The camera is opened per-capture and released immediately. This:
    - Avoids holding the camera (and its LED) when Halbert isn't looking
    - Makes the 'Halbert is looking' state explicit and momentary
    - Works around macOS camera LED behavior (LED is on while camera is open)

    Patch alignment: same as ScreenCapture — rounds downscale dimensions
    to the nearest 336px multiple to avoid wasted LLaVA patches.
    """

    PATCH_SIZE = 336

    def __init__(
        self,
        camera_index: int = 0,
        quality: int = 85,
        max_dim: int = 768,
        grayscale: bool = False,
        patch_align: bool = True,
    ):
        """
        Args:
            camera_index: OpenCV camera index (0 = default, 1 = second camera).
            quality: JPEG encode quality (1-100).
            max_dim: Downscale target for the longest side (pixels). 768 is
                sufficient for local Ollama vision models.
            grayscale: Convert to grayscale before encoding. Saves ~30%
                on file size. Color matters for webcam (objects, labels),
                so this defaults to False.
            patch_align: Round downscale dimensions to patch multiples.
        """
        self.camera_index = camera_index
        self.quality = quality
        self.max_dim = max_dim
        self.grayscale = grayscale
        self.patch_align = patch_align

    def grab_frame(self) -> bytes:
        """Open camera, grab one frame, close camera. Returns JPEG bytes.

        The camera is opened and closed within this method — no persistent
        handle. On macOS the LED will light briefly during the grab.
        """
        _ensure_deps()
        cap = _cv2.VideoCapture(self.camera_index)
        if not cap.isOpened():
            raise WebcamCaptureError(
                f"Cannot open camera {self.camera_index}. It may be in use "
                "by another application, or camera access was denied.",
                error_type="camera_unavailable",
            )
        try:
            # Warm up: discard first few frames (auto-exposure stabilization)
            for _ in range(5):
                cap.read()
            ret, frame = cap.read()
            if not ret or frame is None:
                raise WebcamCaptureError(
                    "Camera read failed — no frame returned.",
                    error_type="read_failed",
                )
            return self._encode_jpeg(frame)
        finally:
            cap.release()

    def grab_to_base64(self) -> str:
        """Grab frame and return base64-encoded JPEG."""
        jpeg = self.grab_frame()
        return base64.b64encode(jpeg).decode("ascii")

    def _encode_jpeg(self, frame_bgr) -> bytes:
        """Downscale and JPEG encode a BGR frame from OpenCV.

        OpenCV returns BGR (no alpha). We optionally convert to grayscale,
        downscale with patch alignment, and JPEG encode.
        """
        _ensure_deps()
        frame = frame_bgr

        if self.grayscale:
            frame = _cv2.cvtColor(frame, _cv2.COLOR_BGR2GRAY)

        h, w = frame.shape[:2]
        if max(h, w) > self.max_dim:
            scale = self.max_dim / max(h, w)
            new_w = int(w * scale)
            new_h = int(h * scale)

            if self.patch_align:
                new_w = (new_w // self.PATCH_SIZE) * self.PATCH_SIZE
                new_h = (new_h // self.PATCH_SIZE) * self.PATCH_SIZE
                new_w = max(new_w, self.PATCH_SIZE)
                new_h = max(new_h, self.PATCH_SIZE)

            frame = _cv2.resize(frame, (new_w, new_h), interpolation=_cv2.INTER_AREA)

        ok, buf = _cv2.imencode(".jpg", frame, [_cv2.IMWRITE_JPEG_QUALITY, self.quality])
        if not ok:
            raise WebcamCaptureError("JPEG encoding failed")
        return buf.tobytes()
