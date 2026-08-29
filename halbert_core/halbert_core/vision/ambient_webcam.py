# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Ambient webcam monitor — continuous capture with motion gating.

Opens the webcam on a timer, captures frames, and only processes/
publishes frames where motion is detected. This avoids the cost of
running inference on identical frames (e.g. an empty room).

Pairs with:
  - MotionDetector / BackgroundSubtractor for motion gating
  - inference/detector.py for object detection on motion frames
  - inference/face.py for face detection on motion frames
  - zone_watcher.py for ROI-based monitoring

Usage:
    from halbert_core.vision.ambient_webcam import AmbientWebcamMonitor
    monitor = AmbientWebcamMonitor(
        on_motion=lambda frame: print("Motion!"),
        interval_seconds=10,
    )
    monitor.start()
"""

from __future__ import annotations

import asyncio
import base64
import logging
import threading
import time
from typing import Any, Callable, Optional

from .motion import BackgroundSubtractor, MotionResult

logger = logging.getLogger("halbert.vision.ambient_webcam")


class AmbientWebcamMonitor:
    """Continuous webcam capture with motion gating.

    Captures a frame every `interval_seconds`, runs motion detection,
    and only calls the `on_motion` callback when motion is detected.
    The callback receives the JPEG bytes of the motion frame.

    This is the foundation for always-on webcam perception without
    the cost of continuous inference. The callback can chain to
    detect_objects(), detect_faces(), or any other CV pipeline.
    """

    def __init__(
        self,
        on_motion: Callable[[bytes, MotionResult], Any],
        camera_index: int = 0,
        interval_seconds: float = 10.0,
        warmup_frames: int = 5,
        motion_threshold: int = 25,
        min_motion_ratio: float = 0.01,
        max_dim: int = 640,
    ):
        """
        Args:
            on_motion: Callback(frame_bytes, motion_result) when motion detected.
            camera_index: OpenCV camera index (0 = default webcam).
            interval_seconds: Time between captures.
            warmup_frames: Frames to discard on each capture (auto-exposure settling).
            motion_threshold: Pixel diff threshold for motion detection.
            min_motion_ratio: Minimum changed pixels to trigger callback.
            max_dim: Max dimension for captured frames (downscale for speed).
        """
        self.on_motion = on_motion
        self.camera_index = camera_index
        self.interval = interval_seconds
        self.warmup_frames = warmup_frames
        self.max_dim = max_dim
        self._subtractor = BackgroundSubtractor(
            min_motion_ratio=min_motion_ratio,
            # Use short history for polling-mode webcam — at 10s intervals,
            # 500 frames would take ~83 minutes to learn the background.
            # 30 frames = ~5 minutes, which is reasonable for a webcam.
            history=30,
        )
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._frame_count = 0
        self._motion_count = 0

    def start(self) -> None:
        """Start the ambient monitoring loop."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._monitor_loop, daemon=True,
            name="halbert-ambient-webcam",
        )
        self._thread.start()
        logger.info(f"AmbientWebcamMonitor started (interval={self.interval}s)")

    def stop(self) -> None:
        """Stop the monitoring loop."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        logger.info("AmbientWebcamMonitor stopped")

    def _monitor_loop(self) -> None:
        """Main loop: capture, detect motion, callback."""
        while self._running:
            try:
                self._capture_and_check()
            except Exception as e:
                logger.warning(f"AmbientWebcamMonitor error: {e}")
            time.sleep(self.interval)

    def _capture_and_check(self) -> None:
        """Capture a frame, check for motion, invoke callback if motion."""
        frame_bytes = self._capture_frame()
        if frame_bytes is None:
            return

        self._frame_count += 1
        result = self._subtractor.process(frame_bytes)

        if result.has_motion:
            self._motion_count += 1
            try:
                cb_result = self.on_motion(frame_bytes, result)
                if asyncio.iscoroutine(cb_result):
                    loop = asyncio.new_event_loop()
                    try:
                        loop.run_until_complete(cb_result)
                    finally:
                        loop.close()
            except Exception as e:
                logger.warning(f"AmbientWebcamMonitor callback error: {e}")

    def _capture_frame(self) -> Optional[bytes]:
        """Capture a single frame from the webcam as JPEG bytes."""
        try:
            import cv2
            cap = cv2.VideoCapture(self.camera_index)
            if not cap.isOpened():
                logger.warning(f"AmbientWebcamMonitor: could not open camera {self.camera_index} "
                               f"(may be in use by another process)")
                cap.release()
                return None

            try:
                # Warm up auto-exposure (check each read for failure)
                for _ in range(self.warmup_frames):
                    ok, _ = cap.read()
                    if not ok:
                        break

                ret, frame = cap.read()
                if not ret or frame is None:
                    return None

                # Downscale
                h, w = frame.shape[:2]
                if max(h, w) > self.max_dim:
                    scale = self.max_dim / max(h, w)
                    frame = cv2.resize(frame, (int(w * scale), int(h * scale)),
                                       interpolation=cv2.INTER_AREA)

                # Encode as JPEG (check success)
                success, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                if not success or buf is None:
                    logger.warning("AmbientWebcamMonitor: JPEG encoding failed")
                    return None
                return buf.tobytes()
            finally:
                cap.release()
        except Exception as e:
            logger.debug(f"AmbientWebcamMonitor capture failed: {e}")
            return None

    @property
    def stats(self) -> dict:
        """Return monitoring statistics."""
        return {
            "frames_captured": self._frame_count,
            "motion_events": self._motion_count,
            "motion_rate": (
                self._motion_count / self._frame_count
                if self._frame_count > 0 else 0.0
            ),
        }
