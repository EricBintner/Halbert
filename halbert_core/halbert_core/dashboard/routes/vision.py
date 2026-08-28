# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Vision API routes.

Provides endpoints for screen capture, webcam capture, and vision
configuration. All capture is local — frames are processed on the
server and returned as base64 JPEG. Nothing is stored to disk.

Capture endpoints check vision_config.yml before capturing. If the
relevant feature (screen_capture.enabled or webcam.enabled) is False,
the endpoint returns a 403 with a clear message instead of capturing.
"""

import logging
from typing import Optional

try:
    from fastapi import APIRouter, HTTPException, Query
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    APIRouter = object

logger = logging.getLogger("halbert.vision.routes")
router = APIRouter(prefix="/vision", tags=["vision"])


if FASTAPI_AVAILABLE:

    class VisionConfigUpdate(BaseModel):
        screen_capture_enabled: Optional[bool] = None
        screen_capture_quality: Optional[int] = None
        screen_capture_max_dim: Optional[int] = None
        screen_capture_monitor_index: Optional[int] = None
        screen_capture_grayscale: Optional[bool] = None
        webcam_enabled: Optional[bool] = None
        webcam_camera_index: Optional[int] = None
        webcam_quality: Optional[int] = None
        webcam_max_dim: Optional[int] = None
        webcam_grayscale: Optional[bool] = None

    @router.get("/config")
    async def get_vision_config():
        """Get the current vision configuration."""
        from ...vision.config import load_config
        cfg = load_config()
        return {
            "screen_capture": {
                "enabled": cfg.screen_capture.enabled,
                "quality": cfg.screen_capture.quality,
                "max_dimension": cfg.screen_capture.max_dimension,
                "monitor_index": cfg.screen_capture.monitor_index,
                "grayscale": cfg.screen_capture.grayscale,
            },
            "webcam": {
                "enabled": cfg.webcam.enabled,
                "camera_index": cfg.webcam.camera_index,
                "quality": cfg.webcam.quality,
                "max_dimension": cfg.webcam.max_dimension,
                "grayscale": cfg.webcam.grayscale,
            },
        }

    @router.put("/config")
    async def update_vision_config(update: VisionConfigUpdate):
        """Update vision configuration fields."""
        from ...vision.config import load_config, save_config
        cfg = load_config()

        if update.screen_capture_enabled is not None:
            cfg.screen_capture.enabled = update.screen_capture_enabled
        if update.screen_capture_quality is not None:
            cfg.screen_capture.quality = update.screen_capture_quality
        if update.screen_capture_max_dim is not None:
            cfg.screen_capture.max_dimension = update.screen_capture_max_dim
        if update.screen_capture_monitor_index is not None:
            cfg.screen_capture.monitor_index = update.screen_capture_monitor_index
        if update.screen_capture_grayscale is not None:
            cfg.screen_capture.grayscale = update.screen_capture_grayscale
        if update.webcam_enabled is not None:
            cfg.webcam.enabled = update.webcam_enabled
        if update.webcam_camera_index is not None:
            cfg.webcam.camera_index = update.webcam_camera_index
        if update.webcam_quality is not None:
            cfg.webcam.quality = update.webcam_quality
        if update.webcam_max_dim is not None:
            cfg.webcam.max_dimension = update.webcam_max_dim
        if update.webcam_grayscale is not None:
            cfg.webcam.grayscale = update.webcam_grayscale

        save_config(cfg)
        return {"status": "ok"}

    @router.get("/screenshot")
    async def capture_screenshot(
        monitor: int = Query(0, description="Monitor index (0=all, 1=primary)"),
        quality: Optional[int] = Query(None, ge=1, le=100, description="JPEG quality (defaults to config)"),
        max_dim: Optional[int] = Query(None, ge=256, le=4096, description="Max dimension in pixels (defaults to config)"),
    ):
        """Capture the screen and return a base64-encoded JPEG.

        Checks vision_config.yml — if screen_capture.enabled is False,
        returns 403 instead of capturing. Quality and max_dim default to
        the config values when not specified in the query.
        """
        from ...vision.config import load_config, is_screen_capture_enabled
        if not is_screen_capture_enabled():
            return JSONResponse(
                {"error": "Screen capture is disabled. Enable it in Settings > Vision.", "error_type": "disabled"},
                status_code=403,
            )

        cfg = load_config()
        eff_quality = quality if quality is not None else cfg.screen_capture.quality
        eff_max_dim = max_dim if max_dim is not None else cfg.screen_capture.max_dimension
        eff_monitor = monitor if monitor != 0 else cfg.screen_capture.monitor_index

        try:
            from ...vision.screen_capture import ScreenCapture, ScreenCaptureError
            cap = ScreenCapture(
                quality=eff_quality,
                max_dim=eff_max_dim,
                grayscale=cfg.screen_capture.grayscale,
            )
            base64_img = cap.capture_to_base64(monitor_index=eff_monitor)
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

    @router.get("/webcam")
    async def capture_webcam(
        camera: Optional[int] = Query(None, description="Camera index (defaults to config)"),
        quality: Optional[int] = Query(None, ge=1, le=100, description="JPEG quality (defaults to config)"),
        max_dim: Optional[int] = Query(None, ge=256, le=4096, description="Max dimension in pixels (defaults to config)"),
    ):
        """Capture a single frame from the webcam and return base64 JPEG.

        Checks vision_config.yml — if webcam.enabled is False, returns
        403 instead of capturing. Camera, quality, and max_dim default
        to the config values when not specified in the query.
        """
        from ...vision.config import load_config, is_webcam_enabled
        if not is_webcam_enabled():
            return JSONResponse(
                {"error": "Webcam capture is disabled. Enable it in Settings > Vision.", "error_type": "disabled"},
                status_code=403,
            )

        cfg = load_config()
        eff_camera = camera if camera is not None else cfg.webcam.camera_index
        eff_quality = quality if quality is not None else cfg.webcam.quality
        eff_max_dim = max_dim if max_dim is not None else cfg.webcam.max_dimension

        try:
            from ...vision.webcam_capture import WebcamCapture, WebcamCaptureError
            cap = WebcamCapture(
                camera_index=eff_camera,
                quality=eff_quality,
                max_dim=eff_max_dim,
                grayscale=cfg.webcam.grayscale,
            )
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
