# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Vision API routes.

Provides endpoints for screen capture and (future) webcam capture.
All capture is local — frames are processed on the server and returned
as base64 JPEG. Nothing is stored to disk.
"""

import logging
from typing import Optional

try:
    from fastapi import APIRouter, HTTPException, Query
    from fastapi.responses import JSONResponse
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    APIRouter = object

logger = logging.getLogger("halbert.vision.routes")
router = APIRouter(prefix="/vision", tags=["vision"])


if FASTAPI_AVAILABLE:

    @router.get("/screenshot")
    async def capture_screenshot(
        monitor: int = Query(0, description="Monitor index (0=all, 1=primary)"),
        quality: int = Query(85, ge=1, le=100, description="JPEG quality"),
        max_dim: int = Query(1568, ge=256, le=4096, description="Max dimension in pixels"),
    ):
        """Capture the screen and return a base64-encoded JPEG.

        The frontend calls this when the user clicks the camera button
        in the chat composer. The returned image is added to the
        attached images list and sent with the next message to the
        vision model.
        """
        try:
            from ...vision.screen_capture import ScreenCapture, ScreenCaptureError
            cap = ScreenCapture(quality=quality, max_dim=max_dim)
            base64_img = cap.capture_to_base64(monitor_index=monitor)
            return {"image": base64_img, "format": "jpeg"}
        except ScreenCaptureError as e:
            logger.warning(f"Screen capture error: {e}")
            return JSONResponse(
                {"error": str(e), "error_type": e.error_type},
                status_code=500,
            )
        except ImportError as e:
            logger.warning(f"Vision dependency missing: {e}")
            return JSONResponse(
                {"error": str(e), "error_type": "dependency_missing"},
                status_code=503,
            )
        except Exception as e:
            logger.error(f"Unexpected screen capture error: {e}", exc_info=True)
            return JSONResponse(
                {"error": f"Unexpected error: {e}", "error_type": "capture_failed"},
                status_code=500,
            )

    @router.get("/status")
    async def vision_status():
        """Check if vision capture dependencies are available."""
        deps = {}
        for name, module_name in [("mss", "mss"), ("cv2", "cv2"), ("numpy", "numpy")]:
            try:
                __import__(module_name)
                deps[name] = True
            except ImportError:
                deps[name] = False
        return {
            "screen_capture": all(deps.values()),
            "dependencies": deps,
        }

    @router.get("/webcam")
    async def capture_webcam(
        camera: int = Query(0, description="Camera index (0=default)"),
        quality: int = Query(85, ge=1, le=100, description="JPEG quality"),
        max_dim: int = Query(768, ge=256, le=4096, description="Max dimension in pixels"),
    ):
        """Capture a single frame from the webcam and return base64 JPEG.

        The camera is opened per-capture and released immediately — the
        LED lights only momentarily. No continuous streaming.
        """
        try:
            from ...vision.webcam_capture import WebcamCapture, WebcamCaptureError
            cap = WebcamCapture(camera_index=camera, quality=quality, max_dim=max_dim)
            base64_img = cap.grab_to_base64()
            return {"image": base64_img, "format": "jpeg"}
        except WebcamCaptureError as e:
            logger.warning(f"Webcam capture error: {e}")
            return JSONResponse(
                {"error": str(e), "error_type": e.error_type},
                status_code=500,
            )
        except ImportError as e:
            logger.warning(f"Vision dependency missing: {e}")
            return JSONResponse(
                {"error": str(e), "error_type": "dependency_missing"},
                status_code=503,
            )
        except Exception as e:
            logger.error(f"Unexpected webcam capture error: {e}", exc_info=True)
            return JSONResponse(
                {"error": f"Unexpected error: {e}", "error_type": "capture_failed"},
                status_code=500,
            )
