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


def list_windows() -> list:
    """List on-screen windows with titles (macOS only).

    Returns a list of dicts with: id, owner, title, bounds, pid,
    is_active. Filters out tiny windows (menu bar items, cursors) and
    windows without names. On non-macOS, returns empty list.

    Uses SCShareableContent (ScreenCaptureKit) when available for
    richer data, falls back to CGWindowListCopyWindowInfo (Quartz).
    """
    import platform
    if platform.system() != "Darwin":
        return []

    # Try ScreenCaptureKit first (richer data, includes process info)
    try:
        return _list_windows_sck()
    except Exception as e:
        logger.debug(f"SCK window listing failed, falling back to CG: {e}")

    # Fall back to CGWindowListCopyWindowInfo
    try:
        return _list_windows_cg()
    except Exception as e:
        logger.warning(f"Failed to list windows: {e}")
        return []


def _list_windows_sck() -> list:
    """List windows using ScreenCaptureKit's SCShareableContent."""
    import time
    from ScreenCaptureKit import SCShareableContent
    from Foundation import NSRunLoop, NSDate, CFRunLoopStop, CFRunLoopGetCurrent

    content = [None]
    def handler(c, err):
        content[0] = c
        CFRunLoopStop(CFRunLoopGetCurrent())

    SCShareableContent.getShareableContentExcludingDesktopWindows_onScreenWindowsOnly_completionHandler_(
        False, True, handler
    )
    rl = NSRunLoop.currentRunLoop()
    deadline = time.time() + 3
    while content[0] is None and time.time() < deadline:
        rl.runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.05))

    if content[0] is None:
        raise RuntimeError("SCK content timeout")

    # Get active window PID for is_active flag
    active_pid = _get_active_pid()

    windows = []
    for w in content[0].windows():
        app = w.owningApplication()
        if not app:
            continue
        owner = app.applicationName() or ""
        pid = app.processID() or 0
        title = w.title() or ""
        rect = w.frame()
        width = int(rect.size.width)
        height = int(rect.size.height)

        if width < 100 or height < 100:
            continue
        if not owner:
            continue

        windows.append({
            "id": w.windowID(),
            "owner": owner,
            "title": title,
            "pid": pid,
            "width": width,
            "height": height,
            "x": int(rect.origin.x),
            "y": int(rect.origin.y),
            "is_active": pid == active_pid,
        })

    return windows


def _list_windows_cg() -> list:
    """List windows using CGWindowListCopyWindowInfo (Quartz fallback)."""
    from Quartz import (
        CGWindowListCopyWindowInfo,
        kCGWindowListOptionOnScreenOnly,
        kCGNullWindowID,
    )

    active_pid = _get_active_pid()

    windows = []
    window_list = CGWindowListCopyWindowInfo(
        kCGWindowListOptionOnScreenOnly, kCGNullWindowID
    )
    for w in window_list:
        name = w.get("kCGWindowName", "") or ""
        owner = w.get("kCGWindowOwnerName", "") or ""
        wid = w.get("kCGWindowNumber", 0)
        pid = w.get("kCGWindowOwnerPID", 0)
        bounds = w.get("kCGWindowBounds", {})
        width = bounds.get("Width", 0)
        height = bounds.get("Height", 0)

        if width < 100 or height < 100:
            continue
        if not owner:
            continue
        if owner == "Window Server":
            continue

        windows.append({
            "id": wid,
            "owner": owner,
            "title": name,
            "pid": pid,
            "width": width,
            "height": height,
            "x": bounds.get("X", 0),
            "y": bounds.get("Y", 0),
            "is_active": pid == active_pid,
        })

    return windows


def _get_active_pid() -> int:
    """Get the PID of the frontmost application (macOS only)."""
    try:
        from AppKit import NSWorkspace
        ws = NSWorkspace.sharedWorkspace()
        app = ws.frontmostApplication()
        return app.processIdentifier() if app else 0
    except Exception:
        return 0


def get_active_window() -> dict:
    """Get info about the frontmost application's main window (macOS only).

    Returns a dict with: id, owner, title, pid, width, height, x, y.
    Returns None on non-macOS or if the active window can't be determined.
    """
    import platform
    if platform.system() != "Darwin":
        return None

    active_pid = _get_active_pid()
    if not active_pid:
        return None

    windows = list_windows()
    # Find the largest window belonging to the active app
    active_windows = [w for w in windows if w.get("pid") == active_pid]
    if not active_windows:
        return None

    # Sort by area (largest first) — the main window is usually the biggest
    active_windows.sort(key=lambda w: w["width"] * w["height"], reverse=True)
    return active_windows[0]


class ScreenCapture:
    """Cross-platform screen capture. MSS primary, lazy-opened per capture.

    The MSS context is opened per-capture and closed immediately, so we
    don't hold a handle to the display server between captures. This is
    cheap (MSS is ctypes-based, no daemon) and avoids any state drift
    if the display configuration changes between captures.

    Patch alignment: when downscaling, dimensions are rounded down to
    the nearest multiple of patch_size (default 336, LLaVA's patch size).
    This avoids wasted tokens from partially-filled patches — a 1568x1018
    image is 5x4=20 LLaVA patches, but 1344x1008 is 4x3=12 patches (40%
    fewer tokens for negligible resolution loss).
    """

    # LLaVA tiles images into 336x336 patches. Each patch costs ~150
    # tokens. Non-multiple dimensions round up, wasting tokens on
    # partially-filled patches.
    PATCH_SIZE = 336

    def __init__(
        self,
        quality: int = 85,
        max_dim: int = 1568,
        grayscale: bool = False,
        patch_align: bool = True,
    ):
        """
        Args:
            quality: JPEG encode quality (1-100). 85 is visually lossless
                and ~10x smaller than PNG. 70 is sufficient for reading
                terminal text and saves ~40% on file size.
            max_dim: Downscale target for the longest side (pixels). 1568
                matches Claude's max input resolution; 768 is sufficient
                for local Ollama vision models (llava, etc.).
            grayscale: Convert to grayscale before encoding. Saves ~30%
                on file size. Text and UI elements are perfectly readable
                in grayscale — color only matters for photos and charts.
            patch_align: Round downscale dimensions to the nearest patch
                multiple (336px for LLaVA). Saves up to 40% on tokens by
                eliminating partially-filled patches.
        """
        self.quality = quality
        self.max_dim = max_dim
        self.grayscale = grayscale
        self.patch_align = patch_align

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

    def capture_window(self, window_id: int) -> bytes:
        """Capture a specific window by its CGWindowID (macOS only).

        Uses CGWindowListCreateImage (Quartz) for native capture — no
        subprocess, no temp files, ~2x faster than the screencapture CLI.
        On non-macOS platforms, raises ScreenCaptureError.

        Args:
            window_id: The macOS CGWindowNumber (from list_windows or
                get_active_window).

        Returns:
            JPEG-encoded bytes (downscaled and quality-adjusted).
        """
        import platform
        if platform.system() != "Darwin":
            raise ScreenCaptureError(
                "Per-window capture is macOS-only",
                error_type="unsupported_platform",
            )

        try:
            from Quartz import (
                CGWindowListCreateImage, CGRectNull,
                kCGWindowListOptionIncludingWindow,
                kCGWindowImageDefault,
                NSBitmapImageRep, NSJPEGFileType,
                CGImageGetWidth, CGImageGetHeight,
            )
        except ImportError as e:
            raise ScreenCaptureError(
                f"Quartz framework not available: {e}",
                error_type="dependency_missing",
            )

        cg_image = CGWindowListCreateImage(
            CGRectNull,
            kCGWindowListOptionIncludingWindow,
            window_id,
            kCGWindowImageDefault,
        )

        if cg_image is None:
            raise ScreenCaptureError(
                f"Failed to capture window {window_id} (need Screen Recording permission?)",
                error_type="permission_denied",
            )

        # Convert CGImage to JPEG bytes
        rep = NSBitmapImageRep.alloc().initWithCGImage_(cg_image)
        data = rep.representationUsingType_properties_(NSJPEGFileType, None)
        if not data:
            raise ScreenCaptureError(
                "Failed to encode window capture as JPEG",
                error_type="encode_failed",
            )

        jpeg_bytes = bytes(data)

        # Apply our downscale/patch-align/grayscale pipeline
        _ensure_deps()
        frame = _cv2.imdecode(
            _numpy.frombuffer(jpeg_bytes, dtype=_numpy.uint8),
            _cv2.IMREAD_COLOR,
        )
        if frame is None:
            return jpeg_bytes  # Can't decode, return raw JPEG
        return self._encode_jpeg(frame)

    def _encode_jpeg(self, frame_bgra) -> bytes:
        """Convert BGRA frame to BGR, downscale, JPEG encode.

        MSS returns BGRA (Blue, Green, Red, Alpha). OpenCV expects BGR
        (no alpha). We strip the alpha channel, optionally convert to
        grayscale, downscale if the longest side exceeds max_dim (with
        patch alignment to avoid wasted tokens), and JPEG encode.
        """
        _ensure_deps()
        # Strip alpha: BGRA → BGR
        frame = frame_bgra[:, :, :3]

        # Grayscale: text and UI elements are luminance-dominant.
        # Converting before downscale means less data to resize, and
        # grayscale JPEGs are ~30% smaller than color at the same quality.
        if self.grayscale:
            frame = _cv2.cvtColor(frame, _cv2.COLOR_BGR2GRAY)

        h, w = frame.shape[:2]
        if max(h, w) > self.max_dim:
            scale = self.max_dim / max(h, w)
            new_w = int(w * scale)
            new_h = int(h * scale)

            # Patch alignment: round down to the nearest patch multiple.
            # A 1568x1018 image is 5x4=20 LLaVA patches, but 1344x1008
            # is 4x3=12 — 40% fewer tokens for negligible resolution loss.
            if self.patch_align:
                new_w = (new_w // self.PATCH_SIZE) * self.PATCH_SIZE
                new_h = (new_h // self.PATCH_SIZE) * self.PATCH_SIZE
                # Guard against zero (image smaller than one patch)
                new_w = max(new_w, self.PATCH_SIZE)
                new_h = max(new_h, self.PATCH_SIZE)

            frame = _cv2.resize(frame, (new_w, new_h), interpolation=_cv2.INTER_AREA)

        ok, buf = _cv2.imencode(".jpg", frame, [_cv2.IMWRITE_JPEG_QUALITY, self.quality])
        if not ok:
            raise ScreenCaptureError("JPEG encoding failed")
        return buf.tobytes()
