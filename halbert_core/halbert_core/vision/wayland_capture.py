# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Wayland screen capture via XDG Desktop Portal.

Wayland doesn't allow applications to capture the screen directly
(unlike X11). The XDG Desktop Portal D-Bus API is the standard way
to request screenshots on Wayland compositors (GNOME, KDE, wlroots).

This module provides a WaylandCapture class that mirrors the
ScreenCapture interface, so the agent tools can use either backend
transparently based on the platform.

D-Bus interface:
    org.freedesktop.portal.Desktop
    /org/freedesktop/portal/desktop
    org.freedesktop.portal.Screenshot.Screenshot(options)

The Screenshot method returns a file URI to a temporary PNG file.
We read it, downscale, and JPEG-encode through the same pipeline
as ScreenCapture.

Dependencies:
    - dbus-next (pip install dbus-next) for D-Bus access
    - The compositor must implement the XDG Desktop Portal (most do)

Limitations:
    - The portal may prompt the user for permission on each capture
      (depends on compositor settings). GNOME Shell remembers the
      choice; some compositors prompt every time.
    - No per-window capture yet — the portal's Screenshot method
      captures the full screen. The org.freedesktop.portal.ScreenCast
      interface could be used for window selection, but it's
      significantly more complex.
    - No monitor selection — the portal captures the monitor that
      the compositor chooses (usually the one with pointer focus).
"""

from __future__ import annotations

import base64
import logging
import os
import tempfile
from typing import Optional, Tuple

logger = logging.getLogger("halbert.vision.wayland")

# Lazy imports
_dbus = None
_cv2 = None
_numpy = None


def _ensure_deps() -> None:
    """Import dbus-next, cv2, and numpy on first use."""
    global _dbus, _cv2, _numpy
    if _dbus is not None:
        return
    try:
        from dbus_next import BusType, Message, Variant
        _dbus = {"BusType": BusType, "Message": Message, "Variant": Variant}
    except ImportError:
        raise ImportError(
            "Wayland capture requires the 'dbus-next' package. "
            "Install with: pip install dbus-next"
        )
    _ensure_cv_deps()


def _ensure_cv_deps() -> None:
    """Import only cv2 and numpy (needed for encoding, not D-Bus)."""
    global _cv2, _numpy
    if _cv2 is not None:
        return
    try:
        import cv2 as _cv2_mod
        _cv2 = _cv2_mod
    except ImportError:
        raise ImportError(
            "Wayland capture requires the 'opencv-python' package."
        )
    try:
        import numpy as _np_mod
        _numpy = _np_mod
    except ImportError:
        raise ImportError(
            "Wayland capture requires the 'numpy' package."
        )


def is_wayland() -> bool:
    """Check if we're running on Wayland."""
    return os.environ.get("WAYLAND_DISPLAY") is not None or \
           os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"


class WaylandCaptureError(Exception):
    """Raised when Wayland capture fails."""

    def __init__(self, message: str, error_type: str = "wayland_failed"):
        super().__init__(message)
        self.error_type = error_type


class WaylandCapture:
    """Screen capture via XDG Desktop Portal (Wayland).

    Mirrors the ScreenCapture interface so the agent tools can use
    either backend transparently.
    """

    PORTAL_BUS = "org.freedesktop.portal.Desktop"
    PORTAL_PATH = "/org/freedesktop/portal/desktop"
    PORTAL_IFACE = "org.freedesktop.portal.Screenshot"

    PATCH_SIZE = 336

    def __init__(
        self,
        quality: int = 85,
        max_dim: int = 1568,
        grayscale: bool = False,
        patch_align: bool = True,
    ):
        self.quality = quality
        self.max_dim = max_dim
        self.grayscale = grayscale
        self.patch_align = patch_align

    def capture_full(self) -> bytes:
        """Capture the full screen via XDG Desktop Portal.

        The portal may prompt the user for permission. The screenshot
        is saved to a temporary file by the portal, which we read and
        encode.
        """
        _ensure_deps()

        BusType = _dbus["BusType"]
        Message = _dbus["Message"]
        Variant = _dbus["Variant"]

        import asyncio

        async def _capture():
            bus = BusType.SYSTEM.bus()
            # Request a screenshot
            # options: {"interactive": Variant('b', False)} for non-interactive
            options = {
                "interactive": Variant("b", False),
            }

            # Build the D-Bus method call
            msg = Message.new_method_call(
                self.PORTAL_BUS,
                self.PORTAL_PATH,
                self.PORTAL_IFACE,
                "Screenshot",
            )
            msg.set_signature("a{sv}")
            msg.body = [options]

            reply = await bus.call(msg)
            if reply is None:
                raise WaylandCaptureError("D-Bus call timed out")

            if reply.error_name:
                raise WaylandCaptureError(
                    f"Portal error: {reply.error_name} — {reply.body}",
                    error_type="portal_error",
                )

            # The response is a dict with "uri" key (file:// path)
            result = reply.body[0] if reply.body else {}
            uri = result.get("uri", "") if isinstance(result, dict) else ""

            if not uri:
                raise WaylandCaptureError("No URI in portal response")

            # Convert file:// URI to path
            if uri.startswith("file://"):
                file_path = uri[7:]
            else:
                file_path = uri

            if not os.path.exists(file_path):
                raise WaylandCaptureError(
                    f"Screenshot file not found: {file_path}",
                    error_type="file_missing",
                )

            # Read and encode
            img = _cv2.imread(file_path)
            if img is None:
                raise WaylandCaptureError(
                    "Failed to read screenshot image",
                    error_type="read_failed",
                )

            # Clean up the temp file
            try:
                os.unlink(file_path)
            except OSError:
                pass

            return self._encode_jpeg(img)

        try:
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(_capture())
            finally:
                loop.close()
        except WaylandCaptureError:
            raise
        except Exception as e:
            raise WaylandCaptureError(
                f"Wayland capture failed: {e}",
                error_type="capture_failed",
            ) from e

    def capture_to_base64(self) -> str:
        """Capture and return base64-encoded JPEG."""
        jpeg = self.capture_full()
        return base64.b64encode(jpeg).decode("ascii")

    def _encode_jpeg(self, frame_bgr) -> bytes:
        """Downscale and JPEG encode (same pipeline as ScreenCapture)."""
        _ensure_cv_deps()

        if self.grayscale:
            frame_bgr = _cv2.cvtColor(frame_bgr, _cv2.COLOR_BGR2GRAY)

        h, w = frame_bgr.shape[:2]
        if max(h, w) > self.max_dim:
            scale = self.max_dim / max(h, w)
            new_w = int(w * scale)
            new_h = int(h * scale)

            if self.patch_align:
                new_w = (new_w // self.PATCH_SIZE) * self.PATCH_SIZE
                new_h = (new_h // self.PATCH_SIZE) * self.PATCH_SIZE
                new_w = max(new_w, self.PATCH_SIZE)
                new_h = max(new_h, self.PATCH_SIZE)

            frame_bgr = _cv2.resize(
                frame_bgr, (new_w, new_h),
                interpolation=_cv2.INTER_AREA,
            )

        ok, buf = _cv2.imencode(
            ".jpg", frame_bgr,
            [_cv2.IMWRITE_JPEG_QUALITY, self.quality],
        )
        if not ok:
            raise WaylandCaptureError("JPEG encoding failed")
        return buf.tobytes()
