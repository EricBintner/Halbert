# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Motion detection via frame differencing and MOG2 background subtraction.

Two modes:
  1. Simple frame differencing — compare two frames, threshold the diff.
     Lightweight, no state. Good for "did something change?".
  2. MOG2 background subtraction — adaptive Gaussian mixture model.
     Stateful, learns the background over time. Good for continuous
     monitoring with a webcam or Frigate latest-frame polling.

Usage (frame diff):
    from halbert_core.vision.motion import MotionDetector
    detector = MotionDetector()
    motion = detector.detect(prev_bytes, curr_bytes)

Usage (MOG2):
    from halbert_core.vision.motion import BackgroundSubtractor
    sub = BackgroundSubtractor()
    motion = sub.process(frame_bytes)
    # After N frames, sub.process() returns motion areas that exclude
    # the learned background.
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np

logger = logging.getLogger("halbert.vision.motion")


@dataclass
class MotionResult:
    """Motion detection result."""
    has_motion: bool
    motion_ratio: float  # fraction of pixels that changed (0.0-1.0)
    bounding_boxes: List[Tuple[int, int, int, int]] = field(default_factory=list)
    frame_shape: Tuple[int, int] = (0, 0)  # (height, width)

    def to_dict(self) -> dict:
        return {
            "has_motion": self.has_motion,
            "motion_ratio": round(self.motion_ratio, 4),
            "bounding_boxes": [list(b) for b in self.bounding_boxes],
            "frame_shape": list(self.frame_shape),
        }


def _decode_image(image_bytes: bytes) -> np.ndarray:
    """Decode JPEG/PNG bytes to grayscale numpy array."""
    import cv2
    img_array = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(img_array, cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise ValueError("Failed to decode image")
    return img


def _decode_image_color(image_bytes: bytes) -> np.ndarray:
    """Decode JPEG/PNG bytes to BGR numpy array."""
    import cv2
    img_array = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Failed to decode image")
    return img


class MotionDetector:
    """Simple frame-differencing motion detector.

    Compares two consecutive frames. No state between calls —
    each detect() is independent.
    """

    def __init__(
        self,
        threshold: int = 25,
        min_motion_ratio: float = 0.01,
        blur_size: Tuple[int, int] = (21, 21),
        dilate_iterations: int = 2,
    ):
        """
        Args:
            threshold: Pixel diff threshold (0-255). Higher = less sensitive.
            min_motion_ratio: Minimum fraction of changed pixels to report motion.
            blur_size: Gaussian blur kernel size for noise reduction.
            dilate_iterations: Number of dilation passes to connect motion regions.
        """
        self.threshold = threshold
        self.min_motion_ratio = min_motion_ratio
        self.blur_size = blur_size
        self.dilate_iterations = dilate_iterations

    def detect(
        self,
        prev_frame: bytes,
        curr_frame: bytes,
    ) -> MotionResult:
        """Detect motion between two JPEG-encoded frames.

        Args:
            prev_frame: Previous frame as JPEG/PNG bytes.
            curr_frame: Current frame as JPEG/PNG bytes.

        Returns:
            MotionResult with has_motion, motion_ratio, and bounding boxes.
        """
        import cv2

        prev = _decode_image(prev_frame)
        curr = _decode_image(curr_frame)

        # Resize to match if needed
        if prev.shape != curr.shape:
            curr = cv2.resize(curr, (prev.shape[1], prev.shape[0]))

        # Frame difference
        diff = cv2.absdiff(prev, curr)

        # Threshold
        _, thresh = cv2.threshold(diff, self.threshold, 255, cv2.THRESH_BINARY)

        # Blur to reduce noise
        thresh = cv2.GaussianBlur(thresh, self.blur_size, 0)
        _, thresh = cv2.threshold(thresh, self.threshold, 255, cv2.THRESH_BINARY)

        # Dilate to connect regions
        thresh = cv2.dilate(thresh, None, iterations=self.dilate_iterations)

        # Find contours (motion regions)
        contours, _ = cv2.findContours(
            thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        h, w = curr.shape
        motion_pixels = int(np.count_nonzero(thresh))
        motion_ratio = motion_pixels / (h * w) if h * w > 0 else 0.0

        # Extract bounding boxes (filter small noise)
        min_area = (h * w) * 0.001  # 0.1% of frame
        bboxes = []
        for c in contours:
            area = cv2.contourArea(c)
            if area < min_area:
                continue
            x, y, cw, ch = cv2.boundingRect(c)
            bboxes.append((x, y, x + cw, y + ch))

        has_motion = motion_ratio >= self.min_motion_ratio and len(bboxes) > 0

        return MotionResult(
            has_motion=has_motion,
            motion_ratio=motion_ratio,
            bounding_boxes=bboxes,
            frame_shape=(h, w),
        )


class BackgroundSubtractor:
    """MOG2 adaptive background subtraction.

    Learns the background over time. Better than frame differencing
    for continuous monitoring because it adapts to lighting changes
    and ignores stationary objects.

    Usage:
        sub = BackgroundSubtractor()
        for frame in video_stream:
            result = sub.process(frame)
            if result.has_motion:
                print("Motion detected!")
    """

    def __init__(
        self,
        history: int = 500,
        var_threshold: int = 16,
        min_motion_ratio: float = 0.01,
        detect_shadows: bool = False,
    ):
        """
        Args:
            history: Number of frames to learn background (default 500).
            var_threshold: MOG2 variance threshold (higher = less sensitive).
            min_motion_ratio: Minimum fraction of foreground pixels to report motion.
            detect_shadows: Whether to detect and exclude shadows.
        """
        self.history = history
        self.var_threshold = var_threshold
        self.min_motion_ratio = min_motion_ratio
        self.detect_shadows = detect_shadows
        self._subtractor = None
        self._frame_count = 0

    def _get_subtractor(self):
        """Lazy-init the MOG2 subtractor."""
        if self._subtractor is None:
            import cv2
            self._subtractor = cv2.createBackgroundSubtractorMOG2(
                history=self.history,
                varThreshold=self.var_threshold,
                detectShadows=self.detect_shadows,
            )
        return self._subtractor

    def process(self, frame_bytes: bytes) -> MotionResult:
        """Process a single frame and return motion detection result.

        Args:
            frame_bytes: JPEG/PNG encoded frame.

        Returns:
            MotionResult with has_motion, motion_ratio, and bounding boxes.
        """
        import cv2

        img = _decode_image(frame_bytes)
        sub = self._get_subtractor()

        # Apply background subtraction
        fg_mask = sub.apply(img)

        # Remove shadows (gray pixels) if shadow detection is on
        if self.detect_shadows:
            _, fg_mask = cv2.threshold(fg_mask, 200, 255, cv2.THRESH_BINARY)

        # Noise reduction
        fg_mask = cv2.GaussianBlur(fg_mask, (21, 21), 0)
        _, fg_mask = cv2.threshold(fg_mask, 200, 255, cv2.THRESH_BINARY)
        fg_mask = cv2.dilate(fg_mask, None, iterations=2)

        h, w = img.shape
        motion_pixels = int(np.count_nonzero(fg_mask))
        motion_ratio = motion_pixels / (h * w) if h * w > 0 else 0.0

        # Find contours
        contours, _ = cv2.findContours(
            fg_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        min_area = (h * w) * 0.001
        bboxes = []
        for c in contours:
            area = cv2.contourArea(c)
            if area < min_area:
                continue
            x, y, cw, ch = cv2.boundingRect(c)
            bboxes.append((x, y, x + cw, y + ch))

        has_motion = motion_ratio >= self.min_motion_ratio and len(bboxes) > 0

        self._frame_count += 1
        return MotionResult(
            has_motion=has_motion,
            motion_ratio=motion_ratio,
            bounding_boxes=bboxes,
            frame_shape=(h, w),
        )

    def reset(self) -> None:
        """Reset the background model."""
        self._subtractor = None
        self._frame_count = 0


def detect_motion(
    prev_frame: bytes,
    curr_frame: bytes,
    threshold: int = 25,
    min_motion_ratio: float = 0.01,
) -> MotionResult:
    """One-shot motion detection between two frames.

    Convenience function that creates a MotionDetector, calls detect(),
    and returns the result. For continuous monitoring, use
    BackgroundSubtractor instead.
    """
    detector = MotionDetector(threshold=threshold, min_motion_ratio=min_motion_ratio)
    return detector.detect(prev_frame, curr_frame)


def detect_motion_from_base64(
    prev_b64: str,
    curr_b64: str,
    threshold: int = 25,
    min_motion_ratio: float = 0.01,
) -> MotionResult:
    """Motion detection between two base64-encoded frames."""
    for b64 in (prev_b64, curr_b64):
        if b64.startswith("data:"):
            # Strip in-place
            if b64 is prev_b64:
                prev_b64 = prev_b64.split(",", 1)[1]
            else:
                curr_b64 = curr_b64.split(",", 1)[1]
    return detect_motion(
        base64.b64decode(prev_b64),
        base64.b64decode(curr_b64),
        threshold,
        min_motion_ratio,
    )
