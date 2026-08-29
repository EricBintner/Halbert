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
import threading
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

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

# YOLOv8 output has 4 bbox coords + 80 class scores = 84 features per anchor
_NUM_FEATURES = 84


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


# Module-level singleton model (thread-safe)
_model = None
_model_backend: Optional[str] = None
_model_lock = threading.Lock()


def _load_model(model_path: Optional[str] = None, backend: str = "auto"):
    """Load the YOLO model. Lazy, cached, and thread-safe.

    Args:
        model_path: Path to .onnx or .pt file. If None, uses yolov8n default.
        backend: "ultralytics", "onnxruntime", or "auto".
            In "auto" mode, the file extension determines the backend:
            .pt → ultralytics, .onnx → onnxruntime, no extension → ultralytics.
    """
    global _model, _model_backend

    with _model_lock:
        if _model is not None:
            return _model

        if model_path is None:
            model_path = "yolov8n"  # ultralytics auto-downloads nano model

        # Determine backend from file extension in auto mode
        if backend == "auto":
            if model_path.endswith(".onnx"):
                backend = "onnxruntime"
            else:
                backend = "ultralytics"

        # Try ultralytics
        if backend == "ultralytics":
            try:
                from ultralytics import YOLO
                pt_path = model_path if model_path.endswith(".pt") else "yolov8n.pt"
                _model = YOLO(pt_path)
                _model_backend = "ultralytics"
                logger.info(f"Loaded YOLO model via ultralytics: {pt_path}")
                return _model
            except ImportError:
                raise ImportError("ultralytics not installed. Install with: pip install ultralytics")

        # Try onnxruntime
        if backend == "onnxruntime":
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
                    "onnxruntime not installed. Install with: pip install onnxruntime"
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


def _preprocess_onnx(
    img: np.ndarray, input_size: int = 640
) -> Tuple[np.ndarray, float, Tuple[int, int]]:
    """Preprocess image for ONNX YOLO inference (center-padded letterbox).

    Returns:
        (input_tensor, scale, (pad_top, pad_left))
        scale and pad are needed to map boxes back to original image coords.
    """
    import cv2
    h, w = img.shape[:2]
    scale = min(input_size / h, input_size / w)
    new_h, new_w = int(h * scale), int(w * scale)
    resized = cv2.resize(img, (new_w, new_h))

    # Center-pad (matches ultralytics training preprocessing)
    pad_top = (input_size - new_h) // 2
    pad_bottom = input_size - new_h - pad_top
    pad_left = (input_size - new_w) // 2
    pad_right = input_size - new_w - pad_left

    canvas = cv2.copyMakeBorder(
        resized, pad_top, pad_bottom, pad_left, pad_right,
        cv2.BORDER_CONSTANT, value=(114, 114, 114),
    )

    # HWC -> CHW, BGR -> RGB, normalize
    canvas = canvas[:, :, ::-1].transpose(2, 0, 1).astype(np.float32) / 255.0
    return np.expand_dims(canvas, 0), scale, (pad_top, pad_left)


def _postprocess_onnx(
    output: np.ndarray,
    orig_shape: tuple,
    scale: float,
    pad: Tuple[int, int],
    conf_threshold: float = 0.5,
    iou_threshold: float = 0.45,
) -> List[Detection]:
    """Post-process ONNX YOLOv8 output to Detection list.

    Applies confidence filtering and non-maximum suppression (NMS).
    Box coordinates are mapped from the 640x640 letterboxed space back
    to the original image dimensions.
    """
    import cv2

    h, w = orig_shape[:2]

    # YOLOv8 output: (1, 84, N) where 84 = 4 bbox + 80 classes
    output = output[0]  # (84, N) or (N, 84)

    if output.size == 0:
        return []

    # Always transpose so we get (N, 84) — rows are detections
    if output.shape[0] == _NUM_FEATURES:
        output = output.T  # (N, 84)

    pad_top, pad_left = pad

    boxes = []
    scores = []
    class_ids = []

    for row in output:
        bbox = row[:4]  # cx, cy, w, h in 640x640 letterboxed space
        class_scores = row[4:]
        class_id = int(np.argmax(class_scores))
        confidence = float(class_scores[class_id])
        if confidence < conf_threshold:
            continue

        # Convert cx,cy,w,h from letterboxed 640 space to original image pixels
        cx, cy, bw, bh = bbox
        # Remove padding offset, then divide by scale
        x1 = int((cx - bw / 2 - pad_left) / scale)
        y1 = int((cy - bh / 2 - pad_top) / scale)
        x2 = int((cx + bw / 2 - pad_left) / scale)
        y2 = int((cy + bh / 2 - pad_top) / scale)

        # Clamp to image bounds
        x1 = max(0, min(x1, w))
        y1 = max(0, min(y1, h))
        x2 = max(0, min(x2, w))
        y2 = max(0, min(y2, h))

        boxes.append([x1, y1, x2 - x1, y2 - y1])  # NMS wants (x, y, w, h)
        scores.append(confidence)
        class_ids.append(class_id)

    if not boxes:
        return []

    # Non-maximum suppression
    indices = cv2.dnn.NMSBoxes(boxes, scores, conf_threshold, iou_threshold)
    if len(indices) == 0:
        return []

    # NMS returns flat array or nested — flatten
    if isinstance(indices, np.ndarray):
        indices = indices.flatten()

    detections = []
    for i in indices:
        i = int(i)
        x, y, bw, bh = boxes[i]
        label = COCO_LABELS[class_ids[i]] if class_ids[i] < len(COCO_LABELS) else f"class_{class_ids[i]}"
        detections.append(Detection(
            label=label,
            confidence=scores[i],
            bbox=(x, y, x + bw, y + bh),
            class_id=class_ids[i],
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
        input_tensor, scale, pad = _preprocess_onnx(img)
        input_name = model.get_inputs()[0].name
        output = model.run(None, {input_name: input_tensor})[0]
        return _postprocess_onnx(output, img.shape, scale, pad, conf_threshold)

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
    """Check if any object detection backend is available.

    Returns True only if a backend AND a model can be loaded:
    - ultralytics: always can download yolov8n.pt
    - onnxruntime: only if a .onnx model path is provided at call time
    """
    try:
        import ultralytics  # noqa: F401
        return True
    except ImportError:
        pass
    # onnxruntime alone is not sufficient without a model path,
    # but we return True so the tool layer can surface a helpful error
    # when the user tries to use it without specifying a model path.
    try:
        import onnxruntime  # noqa: F401
        return True
    except ImportError:
        pass
    return False
