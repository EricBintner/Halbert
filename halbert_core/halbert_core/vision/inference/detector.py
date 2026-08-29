# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Object detection via YOLOv8 ONNX or ultralytics.

Supports two backends:
  1. ultralytics (YOLOv8 native) — pip install ultralytics
  2. onnxruntime (YOLOv8 exported ONNX) — pip install onnxruntime

Both backends return the same Detection dataclass. The module lazy-imports
the backend on first use, so it loads even without the heavy deps.

Usage:
    from halbert_core.vision.inference.detector import detect_objects
    results = detect_objects(image_bytes)
    for d in results:
        print(f"{d.label} ({d.confidence:.2f}) at {d.bbox}")
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np

logger = logging.getLogger("halbert.vision.inference.detector")

# COCO class names (YOLOv8 default 80-class model)
COCO_LABELS = [
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train",
    "truck", "boat", "traffic light", "fire hydrant", "stop sign",
    "parking meter", "bench", "bird", "cat", "dog", "horse", "sheep",
    "cow", "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella",
    "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard",
    "sports ball", "kite", "baseball bat", "baseball glove", "skateboard",
    "surfboard", "tennis racket", "bottle", "wine glass", "cup", "fork",
    "knife", "spoon", "bowl", "banana", "apple", "sandwich", "orange",
    "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair",
    "couch", "potted plant", "bed", "dining table", "toilet", "tv",
    "laptop", "mouse", "remote", "keyboard", "cell phone", "microwave",
    "oven", "toaster", "sink", "refrigerator", "book", "clock", "vase",
    "scissors", "teddy bear", "hair drier", "toothbrush",
]


@dataclass
class Detection:
    """A single object detection result."""
    label: str
    confidence: float
    bbox: tuple  # (x1, y1, x2, y2) in pixel coords
    class_id: int = -1

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "confidence": round(self.confidence, 3),
            "bbox": list(self.bbox),
            "class_id": self.class_id,
        }


# Module-level singleton model
_model = None
_model_backend: Optional[str] = None


def _load_model(model_path: Optional[str] = None, backend: str = "auto"):
    """Load the YOLO model. Lazy and cached.

    Args:
        model_path: Path to .onnx or .pt file. If None, uses yolov8n default.
        backend: "ultralytics", "onnxruntime", or "auto" (try ultralytics first).
    """
    global _model, _model_backend

    if _model is not None:
        return _model

    if model_path is None:
        model_path = "yolov8n"  # ultralytics auto-downloads nano model

    # Try ultralytics first (if "auto" or explicitly requested)
    if backend in ("auto", "ultralytics"):
        try:
            from ultralytics import YOLO
            _model = YOLO(model_path if model_path.endswith(".pt") else "yolov8n.pt")
            _model_backend = "ultralytics"
            logger.info(f"Loaded YOLO model via ultralytics: {model_path}")
            return _model
        except ImportError:
            if backend == "ultralytics":
                raise ImportError("ultralytics not installed. Install with: pip install ultralytics")
            logger.debug("ultralytics not available, trying onnxruntime")

    # Fall back to onnxruntime
    if backend in ("auto", "onnxruntime"):
        try:
            import onnxruntime as ort
            if not model_path.endswith(".onnx"):
                raise ValueError("onnxruntime backend requires a .onnx model path")
            _model = ort.InferenceSession(model_path)
            _model_backend = "onnxruntime"
            logger.info(f"Loaded YOLO model via onnxruntime: {model_path}")
            return _model
        except ImportError:
            raise ImportError(
                "Neither ultralytics nor onnxruntime is installed. "
                "Install with: pip install ultralytics  OR  pip install onnxruntime"
            )

    raise ValueError(f"Unknown backend: {backend}")


def _decode_image(image_bytes: bytes) -> np.ndarray:
    """Decode JPEG/PNG bytes to BGR numpy array (OpenCV convention)."""
    import cv2
    img_array = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Failed to decode image")
    return img


def _preprocess_onnx(img: np.ndarray, input_size: int = 640) -> np.ndarray:
    """Preprocess image for ONNX YOLO inference (letterbox + normalize)."""
    import cv2
    h, w = img.shape[:2]
    scale = min(input_size / h, input_size / w)
    new_h, new_w = int(h * scale), int(w * scale)
    resized = cv2.resize(img, (new_w, new_h))
    canvas = np.full((input_size, input_size, 3), 114, dtype=np.uint8)
    canvas[:new_h, :new_w] = resized
    # HWC -> CHW, BGR -> RGB, normalize
    canvas = canvas[:, :, ::-1].transpose(2, 0, 1).astype(np.float32) / 255.0
    return np.expand_dims(canvas, 0)


def _postprocess_onnx(output: np.ndarray, orig_shape: tuple, conf_threshold: float = 0.5) -> List[Detection]:
    """Post-process ONNX YOLO output to Detection list."""
    h, w = orig_shape[:2]
    detections = []
    # YOLOv8 output shape: (1, 84, N) where 84 = 4 bbox + 80 classes
    output = output[0]  # (84, N)
    if output.shape[0] > output.shape[1]:
        output = output.T  # transpose to (N, 84)

    for row in output:
        bbox = row[:4]  # cx, cy, w, h (normalized)
        class_scores = row[4:]
        class_id = int(np.argmax(class_scores))
        confidence = float(class_scores[class_id])
        if confidence < conf_threshold:
            continue

        # Convert normalized cx,cy,w,h to pixel x1,y1,x2,y2
        cx, cy, bw, bh = bbox
        x1 = int((cx - bw / 2) * w)
        y1 = int((cy - bh / 2) * h)
        x2 = int((cx + bw / 2) * w)
        y2 = int((cy + bh / 2) * h)

        label = COCO_LABELS[class_id] if class_id < len(COCO_LABELS) else f"class_{class_id}"
        detections.append(Detection(
            label=label, confidence=confidence,
            bbox=(x1, y1, x2, y2), class_id=class_id,
        ))

    return detections


def detect_objects(
    image_bytes: bytes,
    model_path: Optional[str] = None,
    conf_threshold: float = 0.5,
    backend: str = "auto",
) -> List[Detection]:
    """Detect objects in an image using YOLOv8.

    Args:
        image_bytes: JPEG/PNG encoded image bytes.
        model_path: Path to model file. None = default yolov8n.
        conf_threshold: Minimum confidence (0.0-1.0).
        backend: "ultralytics", "onnxruntime", or "auto".

    Returns:
        List of Detection objects with label, confidence, and bbox.
    """
    model = _load_model(model_path, backend)
    img = _decode_image(image_bytes)

    if _model_backend == "ultralytics":
        results = model(img, conf=conf_threshold, verbose=False)
        detections = []
        for r in results:
            for box in r.boxes:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                class_id = int(box.cls[0])
                conf = float(box.conf[0])
                label = COCO_LABELS[class_id] if class_id < len(COCO_LABELS) else f"class_{class_id}"
                detections.append(Detection(
                    label=label, confidence=conf,
                    bbox=(int(x1), int(y1), int(x2), int(y2)),
                    class_id=class_id,
                ))
        return detections

    elif _model_backend == "onnxruntime":
        input_tensor = _preprocess_onnx(img)
        input_name = model.get_inputs()[0].name
        output = model.run(None, {input_name: input_tensor})[0]
        return _postprocess_onnx(output, img.shape, conf_threshold)

    return []


def detect_objects_from_base64(
    image_b64: str,
    model_path: Optional[str] = None,
    conf_threshold: float = 0.5,
    backend: str = "auto",
) -> List[Detection]:
    """Detect objects in a base64-encoded image.

    Convenience wrapper for detect_objects that accepts the base64
    format used by Halbert's vision tools.
    """
    # Strip data URI prefix if present
    if image_b64.startswith("data:"):
        image_b64 = image_b64.split(",", 1)[1]
    image_bytes = base64.b64decode(image_b64)
    return detect_objects(image_bytes, model_path, conf_threshold, backend)


def is_available() -> bool:
    """Check if any object detection backend is available."""
    try:
        import ultralytics  # noqa: F401
        return True
    except ImportError:
        pass
    try:
        import onnxruntime  # noqa: F401
        return True
    except ImportError:
        pass
    return False
