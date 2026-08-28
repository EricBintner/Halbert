# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Vision capture tools for the agent.

These tools let the LLM autonomously capture the screen or webcam
when it needs visual context. The tool handler returns a dict with
an "image" key (base64 JPEG) and a "description" key (text). The
state machine detects the "image" key and appends it to ctx.images
so the next LLM call routes through the vision model.
"""

from __future__ import annotations

import base64
import hashlib
import logging
from typing import Dict, Any

logger = logging.getLogger("halbert.tools.vision")

# Dedup state: module-level because tool handlers are stateless functions.
# Vision capture is inherently serial (one user, one screen), so a simple
# last-hash comparison is sufficient — no need for a concurrent map.
_last_screenshot_hash: str | None = None
_last_webcam_hash: str | None = None


async def capture_screenshot(args: Dict) -> Dict[str, Any]:
    """Capture the current screen.

    Returns a dict with:
        - image: base64-encoded JPEG string
        - description: human-readable summary for the observation
        - width, height: original capture dimensions (before downscale)

    The state machine's _handle_executing detects the "image" key and
    appends it to ctx.images, routing the next LLM call through the
    vision model.

    Checks the privacy config (vision_config.yml) before capturing.
    If screen_capture.enabled is False, returns an error dict instead
    of capturing — the user must explicitly opt in via Settings > Vision.
    """
    from ..vision.config import is_screen_capture_enabled, load_config
    if not is_screen_capture_enabled():
        return {
            "error": "Screen capture is disabled. The user can enable it in Settings > Vision.",
            "error_type": "disabled",
        }

    # Fall back to config values when the LLM didn't specify
    cfg = load_config()
    region = args.get("region")
    quality = args.get("quality", cfg.screen_capture.quality)
    max_dim = args.get("max_dim", cfg.screen_capture.max_dimension)
    monitor = args.get("monitor", cfg.screen_capture.monitor_index)

    try:
        from ..vision.screen_capture import ScreenCapture, ScreenCaptureError
        cap = ScreenCapture(
            quality=quality,
            max_dim=max_dim,
            grayscale=cfg.screen_capture.grayscale,
        )

        if region and all(k in region for k in ("x", "y", "width", "height")):
            jpeg_bytes = cap.capture_region(
                region["x"], region["y"], region["width"], region["height"]
            )
            desc = f"Screenshot captured (region {region['width']}x{region['height']})"
        else:
            jpeg_bytes = cap.capture_full(monitor_index=monitor)
            desc = f"Screenshot captured (monitor {monitor})"

        # Dedup: if the screen hasn't changed since the last capture,
        # skip sending the image. The LLM already has it from the
        # previous turn — re-sending wastes ~3000 tokens for nothing.
        global _last_screenshot_hash
        frame_hash = hashlib.md5(jpeg_bytes).hexdigest()
        if frame_hash == _last_screenshot_hash:
            logger.info("Screenshot dedup: screen unchanged since last capture")
            return {
                "description": "Screen unchanged since last capture — the previous screenshot is still current.",
                "unchanged": True,
            }
        _last_screenshot_hash = frame_hash

        base64_img = base64.b64encode(jpeg_bytes).decode("ascii")
        return {"image": base64_img, "description": desc}

    except ScreenCaptureError as e:
        logger.warning(f"Screen capture tool error: {e}")
        return {"error": str(e), "error_type": e.error_type}
    except ImportError as e:
        return {"error": str(e), "error_type": "dependency_missing"}
    except Exception as e:
        logger.error(f"Unexpected screen capture error: {e}", exc_info=True)
        return {"error": f"Unexpected error: {e}", "error_type": "capture_failed"}


async def capture_webcam(args: Dict) -> Dict[str, Any]:
    """Capture a single frame from the webcam.

    Returns a dict with:
        - image: base64-encoded JPEG string
        - description: human-readable summary for the observation

    The camera is opened per-capture and released immediately. The LED
    lights only momentarily.

    Checks the privacy config (vision_config.yml) before capturing.
    If webcam.enabled is False, returns an error dict instead of
    capturing — the user must explicitly opt in via Settings > Vision.
    """
    from ..vision.config import is_webcam_enabled, load_config
    if not is_webcam_enabled():
        return {
            "error": "Webcam capture is disabled. The user can enable it in Settings > Vision.",
            "error_type": "disabled",
        }

    cfg = load_config()
    camera_index = args.get("camera", cfg.webcam.camera_index)
    quality = args.get("quality", cfg.webcam.quality)
    max_dim = args.get("max_dim", cfg.webcam.max_dimension)

    try:
        from ..vision.webcam_capture import WebcamCapture, WebcamCaptureError
        cap = WebcamCapture(
            camera_index=camera_index,
            quality=quality,
            max_dim=max_dim,
            grayscale=cfg.webcam.grayscale,
        )
        jpeg_bytes = cap.grab_frame()

        # Dedup: webcam frames change constantly (noise, lighting), so
        # exact-match dedup is less useful than for screenshots. But it
        # catches the case where the camera pointed at the same static
        # scene (e.g. a label on hardware).
        global _last_webcam_hash
        frame_hash = hashlib.md5(jpeg_bytes).hexdigest()
        if frame_hash == _last_webcam_hash:
            logger.info("Webcam dedup: frame unchanged since last capture")
            return {
                "description": "Webcam frame unchanged since last capture.",
                "unchanged": True,
            }
        _last_webcam_hash = frame_hash

        base64_img = base64.b64encode(jpeg_bytes).decode("ascii")
        return {"image": base64_img, "description": "Webcam frame captured"}

    except WebcamCaptureError as e:
        logger.warning(f"Webcam capture tool error: {e}")
        return {"error": str(e), "error_type": e.error_type}
    except ImportError as e:
        return {"error": str(e), "error_type": "dependency_missing"}
    except Exception as e:
        logger.error(f"Unexpected webcam capture error: {e}", exc_info=True)
        return {"error": f"Unexpected error: {e}", "error_type": "capture_failed"}


# Tool schemas for registration
VISION_TOOL_SCHEMAS = {
    "capture_screenshot": {
        "name": "capture_screenshot",
        "description": (
            "Capture the current screen as an image. Use this when the user asks "
            "about what's on screen, an error dialog, terminal output they can see, "
            "or anything visual on their display. The captured image is attached to "
            "your next response automatically. "
            "Token cost scales with image size: use max_dim=768 for reading text "
            "(~900 tokens), max_dim=512 for quick checks (~450 tokens), "
            "max_dim=1568 only when you need full detail (~3000 tokens). "
            "Use region to capture a specific area instead of the full screen."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "region": {
                    "type": "object",
                    "description": "Optional screen region to capture instead of full screen. Use this when you know where the relevant content is (e.g. the terminal window).",
                    "properties": {
                        "x": {"type": "integer", "description": "Left coordinate (pixels)"},
                        "y": {"type": "integer", "description": "Top coordinate (pixels)"},
                        "width": {"type": "integer", "description": "Region width (pixels)"},
                        "height": {"type": "integer", "description": "Region height (pixels)"},
                    },
                },
                "quality": {
                    "type": "integer",
                    "description": "JPEG quality (1-100). 70 is sufficient for reading text; 85 for photos. Lower = smaller = faster.",
                    "default": 85,
                },
                "max_dim": {
                    "type": "integer",
                    "description": "Max dimension in pixels. 768 for text reading, 512 for quick checks, 1568 for full detail. Lower = fewer tokens.",
                    "default": 1568,
                },
                "monitor": {
                    "type": "integer",
                    "description": "Monitor index: 0=all monitors, 1=primary, 2+=secondary. Default is the configured monitor.",
                    "default": 1,
                },
            },
            "required": [],
        },
    },
    "capture_webcam": {
        "name": "capture_webcam",
        "description": (
            "Capture a single frame from the webcam. Use this when the user asks "
            "you to look at something physical — hardware, a label, a screen on "
            "another device, or anything not on the computer's own display. The "
            "camera LED will light briefly. The captured image is attached to "
            "your next response automatically."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "camera": {
                    "type": "integer",
                    "description": "Camera index (0=default, 1=second camera)",
                    "default": 0,
                },
                "quality": {
                    "type": "integer",
                    "description": "JPEG quality (1-100, default 85)",
                    "default": 85,
                },
                "max_dim": {
                    "type": "integer",
                    "description": "Max dimension in pixels (default 768)",
                    "default": 768,
                },
            },
            "required": [],
        },
    },
}

# Handler mapping
VISION_TOOL_HANDLERS = {
    "capture_screenshot": capture_screenshot,
    "capture_webcam": capture_webcam,
}
