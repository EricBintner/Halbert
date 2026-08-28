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

import logging
from typing import Dict, Any

logger = logging.getLogger("halbert.tools.vision")


async def capture_screenshot(args: Dict) -> Dict[str, Any]:
    """Capture the current screen.

    Returns a dict with:
        - image: base64-encoded JPEG string
        - description: human-readable summary for the observation
        - width, height: original capture dimensions (before downscale)

    The state machine's _handle_executing detects the "image" key and
    appends it to ctx.images, routing the next LLM call through the
    vision model.
    """
    region = args.get("region")
    quality = args.get("quality", 85)
    max_dim = args.get("max_dim", 1568)

    try:
        from ..vision.screen_capture import ScreenCapture, ScreenCaptureError
        cap = ScreenCapture(quality=quality, max_dim=max_dim)

        if region and all(k in region for k in ("x", "y", "width", "height")):
            base64_img = cap.capture_to_base64(
                region=(region["x"], region["y"], region["width"], region["height"])
            )
            desc = f"Screenshot captured (region {region['width']}x{region['height']})"
        else:
            base64_img = cap.capture_to_base64()
            desc = "Screenshot captured (full screen)"

        return {"image": base64_img, "description": desc}

    except ScreenCaptureError as e:
        logger.warning(f"Screen capture tool error: {e}")
        return {"error": str(e), "error_type": e.error_type}
    except ImportError as e:
        return {"error": str(e), "error_type": "dependency_missing"}
    except Exception as e:
        logger.error(f"Unexpected screen capture error: {e}", exc_info=True)
        return {"error": f"Unexpected error: {e}", "error_type": "capture_failed"}


# Tool schemas for registration
VISION_TOOL_SCHEMAS = {
    "capture_screenshot": {
        "name": "capture_screenshot",
        "description": (
            "Capture the current screen as an image. Use this when the user asks "
            "about what's on screen, an error dialog, terminal output they can see, "
            "or anything visual on their display. The captured image is attached to "
            "your next response automatically — you will be able to see it."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "region": {
                    "type": "object",
                    "description": "Optional screen region to capture instead of full screen",
                    "properties": {
                        "x": {"type": "integer", "description": "Left coordinate (pixels)"},
                        "y": {"type": "integer", "description": "Top coordinate (pixels)"},
                        "width": {"type": "integer", "description": "Region width (pixels)"},
                        "height": {"type": "integer", "description": "Region height (pixels)"},
                    },
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
            "required": [],
        },
    },
}

# Handler mapping
VISION_TOOL_HANDLERS = {
    "capture_screenshot": capture_screenshot,
}
