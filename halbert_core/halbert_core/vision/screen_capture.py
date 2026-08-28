# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Screen capture via MSS.

Cross-platform (macOS CoreGraphics, Linux XShm, Windows GDI).
Returns JPEG-encoded bytes or base64 strings, downscaled to a
model-optimal resolution before encoding.

The module is deliberately thin: capture, downscale, encode. No
annotation, no region-selection overlay, no continuous streaming.
Every capture is a single frame, explicitly triggered.
"""

from __future__ import annotations

import base64
import logging
from typing import Optional, Tuple

logger = logging.getLogger("halbert.vision.screen")

# Lazy imports — mss and cv2 are optional dependencies. The module
# imports cleanly without them; capture attempts raise with a clear
# message if they are missing.
_mss = None
_cv2 = None
_numpy = None


def _ensure_deps() -> None:
    """Import mss, cv2, and numpy on first use. Raises ImportError with context."""
    global _mss, _cv2, _numpy
    if _mss is not None:
        return
    try:
        import mss as _mss_mod
        _mss = _mss_mod
    except ImportError:
        raise ImportError(
            "Screen capture requires the 'mss' package. "
            "Install with: pip install mss"
        )
    try:
        import cv2 as _cv2_mod
        _cv2 = _cv2_mod
    except ImportError:
        raise ImportError(
            "Screen capture requires the 'opencv-python' package. "
            "Install with: pip install opencv-python"
        )
    try:
        import numpy as _np_mod
        _numpy = _np_mod
    except ImportError:
        raise ImportError(
            "Screen capture requires the 'numpy' package. "
            "Install with: pip install numpy"
        )


class ScreenCaptureError(Exception):
    """Raised when screen capture fails (permission, display, etc.)."""

    def __init__(self, message: str, error_type: str = "capture_failed"):
        super().__init__(message)
        self.error_type = error_type


class ScreenCapture:
    """Cross-platform screen capture. MSS primary, lazy-opened per capture.

    The MSS context is opened per-capture and closed immediately, so we
    don't hold a handle to the display server between captures. This is
    cheap (MSS is ctypes-based, no daemon) and avoids any state drift
    if the display configuration changes between captures.
    """

    def __init__(self, quality: int = 85, max_dim: int = 1568):
        """
        Args:
            quality: JPEG encode quality (1-100). 85 is visually lossless
                and ~10x smaller than PNG.
            max_dim: Downscale target for the longest side (pixels). 1568
                matches Claude's max input resolution; 768 is sufficient
                for local Ollama vision models (llava, etc.).
        """
        self.quality = quality
        self.max_dim = max_dim

    def capture_full(self, monitor_index: int = 0) -> bytes:
        """Capture the full primary monitor (or a specific monitor).

        Args:
            monitor_index: 0 = all monitors combined, 1 = primary,
                2+ = secondary. Defaults to 0 (everything).

        Returns:
            JPEG-encoded bytes.

        Raises:
            ScreenCaptureError: On capture or encoding failure.
            ImportError: If mss/opencv/numpy are not installed.
        """
        _ensure_deps()
        try:
            with _mss.mss() as sct:
                if monitor_index >= len(sct.monitors):
                    monitor_index = 0
                monitor = sct.monitors[monitor_index]
                frame = _numpy.asarray(sct.grab(monitor))
        except Exception as e:
            err = str(e).lower()
            if "permission" in err or "not authorized" in err:
                raise ScreenCaptureError(
                    "Screen capture permission denied. Grant Screen Recording "
                    "access in System Settings > Privacy & Security > Screen Recording.",
                    error_type="permission_denied",
                ) from e
            raise ScreenCaptureError(f"Screen capture failed: {e}") from e

        return self._encode_jpeg(frame)

    def capture_region(self, x: int, y: int, width: int, height: int) -> bytes:
        """Capture a specific screen region.

        Args:
            x: Left coordinate (pixels).
            y: Top coordinate (pixels).
            width: Region width.
            height: Region height.

        Returns:
            JPEG-encoded bytes.
        """
        _ensure_deps()
        region = {"top": y, "left": x, "width": width, "height": height}
        try:
            with _mss.mss() as sct:
                frame = _numpy.asarray(sct.grab(region))
        except Exception as e:
            raise ScreenCaptureError(f"Region capture failed: {e}") from e

        return self._encode_jpeg(frame)

    def capture_to_base64(
        self,
        region: Optional[Tuple[int, int, int, int]] = None,
        monitor_index: int = 0,
    ) -> str:
        """Capture and return base64-encoded JPEG.

        Args:
            region: Optional (x, y, width, height) tuple. If None,
                captures the full monitor.
            monitor_index: Which monitor to capture (0 = all).

        Returns:
            Base64-encoded JPEG string (no data: prefix).
        """
        if region is not None:
            jpeg = self.capture_region(*region)
        else:
            jpeg = self.capture_full(monitor_index=monitor_index)
        return base64.b64encode(jpeg).decode("ascii")

    def _encode_jpeg(self, frame_bgra) -> bytes:
        """Convert BGRA frame to BGR, downscale, JPEG encode.

        MSS returns BGRA (Blue, Green, Red, Alpha). OpenCV expects BGR
        (no alpha). We strip the alpha channel, downscale if the longest
        side exceeds max_dim, and JPEG encode.
        """
        _ensure_deps()
        # Strip alpha: BGRA → BGR
        frame = frame_bgra[:, :, :3]

        h, w = frame.shape[:2]
        if max(h, w) > self.max_dim:
            scale = self.max_dim / max(h, w)
            new_w = int(w * scale)
            new_h = int(h * scale)
            frame = _cv2.resize(frame, (new_w, new_h), interpolation=_cv2.INTER_AREA)

        ok, buf = _cv2.imencode(".jpg", frame, [_cv2.IMWRITE_JPEG_QUALITY, self.quality])
        if not ok:
            raise ScreenCaptureError("JPEG encoding failed")
        return buf.tobytes()
