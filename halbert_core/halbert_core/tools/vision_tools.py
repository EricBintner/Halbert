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
# Separate hashes per capture type so a full-screen capture doesn't
# suppress a subsequent window capture (or vice versa).
_last_screenshot_hash: str | None = None
_last_window_hash: str | None = None
_last_active_window_hash: str | None = None
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

        # Redaction: if enabled, blur sensitive regions before sending
        from ..vision.redact import should_redact, redact_image, get_blocklist, get_regex_patterns
        if should_redact(cfg):
            jpeg_bytes = redact_image(
                jpeg_bytes,
                blocklist=get_blocklist(cfg),
                patterns=get_regex_patterns(),
            )
            desc += " (redacted)"

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


async def capture_and_ocr(args: Dict) -> Dict[str, Any]:
    """Capture the screen, run OCR, return text instead of an image.

    For terminal output, error dialogs, and code editors, this replaces
    a ~900-token image with a ~50-200-token text observation. The LLM
    gets the same information at 5-15x lower token cost.

    When to use this vs capture_screenshot:
        - Terminal output, command results, logs → capture_and_ocr
        - Error dialogs with text → capture_and_ocr
        - Code in an editor → capture_and_ocr
        - UI layout, charts, photos, diagrams → capture_screenshot
        - "What does this look like?" → capture_screenshot

    If OCR finds no text (empty screen, pure graphics), falls back to
    returning the image so the LLM can still see it.
    """
    from ..vision.config import is_screen_capture_enabled, load_config
    if not is_screen_capture_enabled():
        return {
            "error": "Screen capture is disabled. The user can enable it in Settings > Vision.",
            "error_type": "disabled",
        }

    cfg = load_config()
    region = args.get("region")
    quality = args.get("quality", cfg.screen_capture.quality)
    max_dim = args.get("max_dim", cfg.screen_capture.max_dimension)
    monitor = args.get("monitor", cfg.screen_capture.monitor_index)
    include_image = args.get("include_image", False)

    try:
        from ..vision.screen_capture import ScreenCapture, ScreenCaptureError
        from ..vision.ocr import recognize, is_available as ocr_available

        if not ocr_available():
            return {
                "error": "No OCR backend available. Install pyobjc-framework-Vision (macOS) or tesseract.",
                "error_type": "ocr_unavailable",
            }

        cap = ScreenCapture(
            quality=quality,
            max_dim=max_dim,
            grayscale=cfg.screen_capture.grayscale,
        )

        # Capture as PNG (lossless for OCR — JPEG artifacts hurt accuracy)
        if region and all(k in region for k in ("x", "y", "width", "height")):
            jpeg_bytes = cap.capture_region(
                region["x"], region["y"], region["width"], region["height"]
            )
            desc = f"OCR capture (region {region['width']}x{region['height']})"
        else:
            jpeg_bytes = cap.capture_full(monitor_index=monitor)
            desc = f"OCR capture (monitor {monitor})"

        # Run OCR on the captured frame
        # Re-encode as PNG for better OCR accuracy (JPEG artifacts hurt)
        import cv2
        import numpy as np
        frame = cv2.imdecode(np.frombuffer(jpeg_bytes, np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            # Can't decode — try OCR on the raw JPEG bytes (some backends
            # handle JPEG directly)
            ocr_text = recognize(jpeg_bytes)
        else:
            ok, png_buf = cv2.imencode(".png", frame)
            if not ok:
                return {"error": "Failed to encode frame for OCR", "error_type": "encode_failed"}
            ocr_text = recognize(png_buf.tobytes())

        if ocr_text and ocr_text.strip():
            ocr_text = ocr_text.strip()

            # Redaction: if enabled, mask lines containing sensitive
            # keywords in the OCR text. This prevents passwords/tokens
            # from reaching the LLM via the text path.
            from ..vision.redact import should_redact, get_blocklist, get_regex_patterns, _matches_sensitive
            if should_redact(cfg):
                blocklist = get_blocklist(cfg)
                patterns = get_regex_patterns()
                lines = ocr_text.split("\n")
                redacted_lines = []
                for line in lines:
                    if _matches_sensitive(line, blocklist, patterns):
                        redacted_lines.append("[REDACTED]")
                    else:
                        redacted_lines.append(line)
                ocr_text = "\n".join(redacted_lines)
                desc += " (redacted)"

            result = {
                "ocr_text": ocr_text,
                "description": f"{desc}: {len(ocr_text)} chars of text extracted",
            }
            # Optionally include a small thumbnail for visual context.
            # If redaction is enabled, redact the image too.
            if include_image:
                import base64
                if should_redact(cfg):
                    from ..vision.redact import redact_image
                    jpeg_bytes = redact_image(
                        jpeg_bytes,
                        blocklist=get_blocklist(cfg),
                        patterns=get_regex_patterns(),
                    )
                result["image"] = base64.b64encode(jpeg_bytes).decode("ascii")
            return result
        else:
            # OCR found no text — fall back to sending the image
            import base64
            return {
                "image": base64.b64encode(jpeg_bytes).decode("ascii"),
                "description": f"{desc}: no text found, sending image instead",
            }

    except ScreenCaptureError as e:
        return {"error": str(e), "error_type": e.error_type}
    except ImportError as e:
        return {"error": str(e), "error_type": "dependency_missing"}
    except Exception as e:
        logger.error(f"Unexpected OCR capture error: {e}", exc_info=True)
        return {"error": f"Unexpected error: {e}", "error_type": "capture_failed"}


async def list_windows_tool(args: Dict) -> Dict[str, Any]:
    """List on-screen windows that can be captured individually.

    Returns a list of windows with their IDs, owner app names, and
    titles. The LLM can use a window ID with capture_window to capture
    just that window instead of the full screen — much more efficient
    and avoids capturing sensitive content in other windows.
    """
    from ..vision.screen_capture import list_windows

    try:
        windows = list_windows()
        if not windows:
            return {
                "windows": [],
                "description": "No windows found (per-window capture is macOS-only)",
            }
        return {
            "windows": windows,
            "description": f"Found {len(windows)} capturable windows",
        }
    except Exception as e:
        logger.error(f"Failed to list windows: {e}", exc_info=True)
        return {"error": str(e), "error_type": "list_failed"}


async def capture_window_tool(args: Dict) -> Dict[str, Any]:
    """Capture a specific window by ID (macOS only).

    Use list_windows first to get window IDs. Capturing a single window
    is more efficient than full screen (fewer pixels, fewer tokens) and
    avoids capturing sensitive content in other windows.
    """
    from ..vision.config import is_screen_capture_enabled, load_config

    if not is_screen_capture_enabled():
        return {
            "error": "Screen capture is disabled. The user can enable it in Settings > Vision.",
            "error_type": "disabled",
        }

    window_id = args.get("window_id")
    if window_id is None:
        return {"error": "window_id is required", "error_type": "missing_param"}

    cfg = load_config()
    quality = args.get("quality", cfg.screen_capture.quality)
    max_dim = args.get("max_dim", cfg.screen_capture.max_dimension)

    try:
        from ..vision.screen_capture import ScreenCapture, ScreenCaptureError
        cap = ScreenCapture(
            quality=quality,
            max_dim=max_dim,
            grayscale=cfg.screen_capture.grayscale,
        )
        jpeg_bytes = cap.capture_window(window_id)

        # Dedup (per-tool hash so full-screen captures don't suppress window captures)
        global _last_window_hash
        frame_hash = hashlib.md5(jpeg_bytes).hexdigest()
        if frame_hash == _last_window_hash:
            return {
                "description": "Window unchanged since last capture.",
                "unchanged": True,
            }
        _last_window_hash = frame_hash

        base64_img = base64.b64encode(jpeg_bytes).decode("ascii")
        return {"image": base64_img, "description": f"Window {window_id} captured"}

    except ScreenCaptureError as e:
        return {"error": str(e), "error_type": e.error_type}
    except ImportError as e:
        return {"error": str(e), "error_type": "dependency_missing"}
    except Exception as e:
        logger.error(f"Window capture error: {e}", exc_info=True)
        return {"error": f"Unexpected error: {e}", "error_type": "capture_failed"}


async def capture_active_window_tool(args: Dict) -> Dict[str, Any]:
    """Capture the frontmost application's main window (macOS only).

    Convenience tool — no need to call list_windows first. Finds the
    active app via NSWorkspace.frontmostApplication, then captures its
    largest window. This is the most efficient way to capture "what
    the user is looking at" without capturing other windows.
    """
    from ..vision.config import is_screen_capture_enabled, load_config

    if not is_screen_capture_enabled():
        return {
            "error": "Screen capture is disabled. The user can enable it in Settings > Vision.",
            "error_type": "disabled",
        }

    cfg = load_config()
    quality = args.get("quality", cfg.screen_capture.quality)
    max_dim = args.get("max_dim", cfg.screen_capture.max_dimension)

    try:
        from ..vision.screen_capture import (
            ScreenCapture, ScreenCaptureError, get_active_window,
        )

        active = get_active_window()
        if not active:
            return {
                "error": "Could not determine the active window (macOS only)",
                "error_type": "no_active_window",
            }

        cap = ScreenCapture(
            quality=quality,
            max_dim=max_dim,
            grayscale=cfg.screen_capture.grayscale,
        )
        jpeg_bytes = cap.capture_window(active["id"])

        # Dedup (per-tool hash)
        global _last_active_window_hash
        frame_hash = hashlib.md5(jpeg_bytes).hexdigest()
        if frame_hash == _last_active_window_hash:
            return {
                "description": f"Active window ({active['owner']}) unchanged since last capture.",
                "unchanged": True,
            }
        _last_active_window_hash = frame_hash

        base64_img = base64.b64encode(jpeg_bytes).decode("ascii")
        return {
            "image": base64_img,
            "description": f"Active window captured: {active['owner']} — {active['title']}",
            "window": active,
        }

    except ScreenCaptureError as e:
        return {"error": str(e), "error_type": e.error_type}
    except ImportError as e:
        return {"error": str(e), "error_type": "dependency_missing"}
    except Exception as e:
        logger.error(f"Active window capture error: {e}", exc_info=True)
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
            "Use region to capture a specific area instead of the full screen. "
            "For reading terminal text, prefer capture_and_ocr which returns text "
            "instead of an image (~50-200 tokens vs ~900). "
            "For capturing a specific window, use list_windows + capture_window."
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
    "capture_and_ocr": {
        "name": "capture_and_ocr",
        "description": (
            "Capture the screen and extract text via OCR. Returns text instead of "
            "an image, saving 5-15x on tokens. Use this for terminal output, error "
            "dialogs, code in editors, log files, or any screen that is primarily "
            "text. If no text is found, falls back to sending the image. "
            "Cost: ~50-200 tokens (text) vs ~900 tokens (image). "
            "For visual content (charts, photos, UI layout), use capture_screenshot instead."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "region": {
                    "type": "object",
                    "description": "Optional screen region to capture. Use this to target a specific terminal window or dialog.",
                    "properties": {
                        "x": {"type": "integer"},
                        "y": {"type": "integer"},
                        "width": {"type": "integer"},
                        "height": {"type": "integer"},
                    },
                },
                "max_dim": {
                    "type": "integer",
                    "description": "Max dimension for capture. Higher = better OCR accuracy but slower. 1568 is a good default.",
                    "default": 1568,
                },
                "monitor": {
                    "type": "integer",
                    "description": "Monitor index: 0=all, 1=primary, 2+=secondary.",
                    "default": 1,
                },
                "include_image": {
                    "type": "boolean",
                    "description": "Also include a small image alongside the OCR text. Useful when you need both the text and visual context (e.g. dialog color, icon). Default false.",
                    "default": False,
                },
            },
            "required": [],
        },
    },
    "list_windows": {
        "name": "list_windows",
        "description": (
            "List on-screen windows that can be captured individually (macOS only). "
            "Returns window IDs, owner app names, and titles. Use this before "
            "capture_window to find the right window ID. This is a text-only "
            "result (no image), so it costs very few tokens."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    "capture_window": {
        "name": "capture_window",
        "description": (
            "Capture a specific window by ID (macOS only). Use list_windows first "
            "to get the window ID. Capturing a single window is more efficient "
            "than full screen (fewer pixels, fewer tokens) and avoids capturing "
            "sensitive content in other windows. The image is attached to your "
            "next response automatically."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "window_id": {
                    "type": "integer",
                    "description": "Window ID from list_windows",
                },
                "quality": {
                    "type": "integer",
                    "description": "JPEG quality (1-100, default 85)",
                    "default": 85,
                },
                "max_dim": {
                    "type": "integer",
                    "description": "Max dimension in pixels (default 1568)",
                    "default": 1568,
                },
            },
            "required": ["window_id"],
        },
    },
    "capture_active_window": {
        "name": "capture_active_window",
        "description": (
            "Capture the frontmost application's main window (macOS only). "
            "No need to call list_windows first — this automatically finds "
            "and captures the active window. This is the most efficient way "
            "to capture what the user is looking at. The image is attached "
            "to your next response automatically."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "quality": {
                    "type": "integer",
                    "description": "JPEG quality (1-100, default 85)",
                    "default": 85,
                },
                "max_dim": {
                    "type": "integer",
                    "description": "Max dimension in pixels (default 1568)",
                    "default": 1568,
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
    "capture_and_ocr": capture_and_ocr,
    "list_windows": list_windows_tool,
    "capture_window": capture_window_tool,
    "capture_active_window": capture_active_window_tool,
    "capture_webcam": capture_webcam,
}
