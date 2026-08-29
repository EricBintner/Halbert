# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Face detection via OpenCV DNN or MediaPipe.

Supports two backends:
  1. OpenCV DNN (Caffe SSD) — no extra deps beyond opencv-python
  2. MediaPipe Face Detection — pip install mediapipe

Both return the same FaceDetection dataclass. OpenCV DNN is preferred
because it has no extra dependency (opencv-python is already required
for vision). MediaPipe is faster but adds a heavy dependency.

Usage:
    from halbert_core.vision.inference.face import detect_faces
    faces = detect_faces(image_bytes)
    for f in faces:
        print(f"Face ({f.confidence:.2f}) at {f.bbox}")
"""

from __future__ import annotations

import base64
import logging
import os
from dataclasses import dataclass
from typing import List, Optional

import numpy as np

logger = logging.getLogger("halbert.vision.inference.face")


@dataclass
class FaceDetection:
    """A single face detection result."""
    confidence: float
    bbox: tuple  # (x1, y1, x2, y2) in pixel coords
    backend: str = ""

    def to_dict(self) -> dict:
        return {
            "confidence": round(self.confidence, 3),
            "bbox": list(self.bbox),
            "backend": self.backend,
        }


# Module-level singleton models
_cv2_dnn_net = None
_mediapipe_detector = None
_active_backend: Optional[str] = None


def _decode_image(image_bytes: bytes) -> np.ndarray:
    """Decode JPEG/PNG bytes to BGR numpy array."""
    import cv2
    img_array = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Failed to decode image")
    return img


def _load_cv2_dnn():
    """Load the OpenCV DNN face detector (Caffe SSD).

    Uses the standard res10_300x300_ssd model. The model files are
    downloaded from the OpenCV model zoo if not present locally.
    """
    global _cv2_dnn_net

    if _cv2_dnn_net is not None:
        return _cv2_dnn_net

    import cv2

    # Model files — check common locations
    model_dir = os.path.expanduser("~/.local/share/halbert/models")
    prototxt = os.path.join(model_dir, "deploy.prototxt")
    caffemodel = os.path.join(model_dir, "res10_300x300_ssd_iter_140000.caffemodel")

    if not os.path.exists(prototxt) or not os.path.exists(caffemodel):
        raise FileNotFoundError(
            f"OpenCV DNN face model not found at {model_dir}. "
            "Download deploy.prototxt and res10_300x300_ssd_iter_140000.caffemodel "
            "from the OpenCV model zoo."
        )

    _cv2_dnn_net = cv2.dnn.readNetFromCaffe(prototxt, caffemodel)
    logger.info("Loaded OpenCV DNN face detector")
    return _cv2_dnn_net


def _detect_cv2_dnn(img: np.ndarray, conf_threshold: float = 0.5) -> List[FaceDetection]:
    """Run OpenCV DNN face detection."""
    import cv2

    net = _load_cv2_dnn()
    h, w = img.shape[:2]
    blob = cv2.dnn.blobFromImage(
        cv2.resize(img, (300, 300)), 1.0, (300, 300), (104.0, 177.0, 123.0)
    )
    net.setInput(blob)
    detections = net.forward()

    results = []
    for i in range(detections.shape[2]):
        confidence = float(detections[0, 0, i, 2])
        if confidence < conf_threshold:
            continue
        x1 = int(detections[0, 0, i, 3] * w)
        y1 = int(detections[0, 0, i, 4] * h)
        x2 = int(detections[0, 0, i, 5] * w)
        y2 = int(detections[0, 0, i, 6] * h)
        results.append(FaceDetection(
            confidence=confidence,
            bbox=(x1, y1, x2, y2),
            backend="cv2_dnn",
        ))
    return results


def _load_mediapipe():
    """Load MediaPipe face detector."""
    global _mediapipe_detector

    if _mediapipe_detector is not None:
        return _mediapipe_detector

    import mediapipe as mp

    # Use a low min_detection_confidence so the caller's conf_threshold
    # is the actual filter — MediaPipe's internal threshold doesn't
    # discard low-confidence faces before we can see them.
    _mediapipe_detector = mp.solutions.face_detection.FaceDetection(
        model_selection=0,  # 0=short-range (2m), 1=full-range (5m)
        min_detection_confidence=0.1,
    )
    logger.info("Loaded MediaPipe face detector")
    return _mediapipe_detector


def close_mediapipe() -> None:
    """Release the MediaPipe detector to free GPU/model resources."""
    global _mediapipe_detector
    if _mediapipe_detector is not None:
        try:
            _mediapipe_detector.close()
        except Exception:
            pass
        _mediapipe_detector = None


def _detect_mediapipe(img: np.ndarray, conf_threshold: float = 0.5) -> List[FaceDetection]:
    """Run MediaPipe face detection."""
    import cv2

    detector = _load_mediapipe()
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    results = detector.process(rgb)

    detections = []
    if results.detections:
        h, w = img.shape[:2]
        for d in results.detections:
            conf = d.score[0] if d.score else 0.0
            if conf < conf_threshold:
                continue
            bbox = d.location_data.relative_bounding_box
            x1 = max(0, int(bbox.xmin * w))
            y1 = max(0, int(bbox.ymin * h))
            x2 = min(w, int((bbox.xmin + bbox.width) * w))
            y2 = min(h, int((bbox.ymin + bbox.height) * h))
            detections.append(FaceDetection(
                confidence=float(conf),
                bbox=(x1, y1, x2, y2),
                backend="mediapipe",
            ))
    return detections


def detect_faces(
    image_bytes: bytes,
    conf_threshold: float = 0.5,
    backend: str = "auto",
) -> List[FaceDetection]:
    """Detect faces in an image.

    Args:
        image_bytes: JPEG/PNG encoded image bytes.
        conf_threshold: Minimum confidence (0.0-1.0).
        backend: "cv2_dnn", "mediapipe", or "auto" (try cv2_dnn first).

    Returns:
        List of FaceDetection objects with confidence and bbox.
    """
    global _active_backend
    img = _decode_image(image_bytes)

    # Try OpenCV DNN first (no extra deps)
    if backend in ("auto", "cv2_dnn"):
        try:
            results = _detect_cv2_dnn(img, conf_threshold)
            _active_backend = "cv2_dnn"
            return results
        except FileNotFoundError:
            if backend == "cv2_dnn":
                raise
            logger.debug("cv2_dnn model not available, trying mediapipe")
        except Exception as e:
            if backend == "cv2_dnn":
                raise
            logger.debug(f"cv2_dnn failed ({e}), trying mediapipe")

    # Fall back to MediaPipe
    if backend in ("auto", "mediapipe"):
        try:
            results = _detect_mediapipe(img, conf_threshold)
            _active_backend = "mediapipe"
            return results
        except ImportError:
            raise ImportError(
                "No face detection backend available. Either:\n"
                "  1. Download OpenCV DNN models to ~/.local/share/halbert/models/\n"
                "     See: https://github.com/opencv/opencv/tree/master/samples/dnn/face_detector\n"
                "  2. Install mediapipe: pip install mediapipe"
            )
        except Exception as e:
            raise RuntimeError(
                f"Face detection failed on all backends. Last error: {e}"
            )

    return []


def detect_faces_from_base64(
    image_b64: str,
    conf_threshold: float = 0.5,
    backend: str = "auto",
) -> List[FaceDetection]:
    """Detect faces in a base64-encoded image."""
    if image_b64.startswith("data:"):
        image_b64 = image_b64.split(",", 1)[1]
    image_bytes = base64.b64decode(image_b64)
    return detect_faces(image_bytes, conf_threshold, backend)


def is_available() -> bool:
    """Check if any face detection backend is available."""
    # Check MediaPipe
    try:
        import mediapipe  # noqa: F401
        return True
    except ImportError:
        pass
    # Check OpenCV DNN model files
    model_dir = os.path.expanduser("~/.local/share/halbert/models")
    prototxt = os.path.join(model_dir, "deploy.prototxt")
    caffemodel = os.path.join(model_dir, "res10_300x300_ssd_iter_140000.caffemodel")
    if os.path.exists(prototxt) and os.path.exists(caffemodel):
        return True
    return False
