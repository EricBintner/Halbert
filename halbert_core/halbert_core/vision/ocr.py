# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""OCR pre-processing for screen capture.

Turns a screenshot into text before sending it to the LLM. For terminal
output, error dialogs, and code editors, this replaces a ~900-token
image with a ~50-200-token text observation — a 5-15x reduction.

Backend selection (automatic, best-available):
    1. macOS Vision framework (VNRecognizeTextRequest)
       - Best accuracy, fastest (Neural Engine on Apple Silicon)
       - Returns text with bounding boxes and confidence scores
       - macOS only, requires pyobjc-framework-Vision
    2. Tesseract (via subprocess)
       - Cross-platform, decent accuracy
       - Returns plain text or TSV with bounding boxes
       - Requires tesseract binary in PATH

The module degrades gracefully: if no backend is available, the caller
gets an ImportError and falls back to sending the raw image.

Design decisions:
    - No pytesseract dependency: the subprocess interface avoids a
      Python wrapper that adds its own error handling and version
      coupling. Tesseract's CLI is stable across versions.
    - Vision results are sorted top-to-bottom, left-to-right to
      preserve reading order. Terminal output and code have strict
      vertical structure; jumbled text would be useless to the LLM.
    - Confidence filtering: Vision returns low-confidence results for
      UI chrome (icons, buttons). We filter below 0.3 to keep only
      real text, but the threshold is configurable.
    - Layout preservation: we group text by approximate rows (y
      coordinate clustering) and join with newlines, so multi-line
      terminal output stays multi-line.
"""

from __future__ import annotations

import logging
import subprocess
import tempfile
from typing import List, Optional, Tuple

logger = logging.getLogger("halbert.vision.ocr")

# Lazy-loaded backend detection
_backend: Optional[str] = None
_backend_checked = False


def _detect_backend() -> Optional[str]:
    """Detect the best available OCR backend. Cached after first call."""
    global _backend, _backend_checked
    if _backend_checked:
        return _backend
    _backend_checked = True

    # 1. macOS Vision framework
    try:
        from Vision import VNRecognizeTextRequest  # noqa: F401
        _backend = "vision"
        logger.info("OCR backend: macOS Vision framework")
        return _backend
    except ImportError:
        pass

    # 2. Tesseract binary
    import shutil
    if shutil.which("tesseract"):
        _backend = "tesseract"
        logger.info("OCR backend: Tesseract (subprocess)")
        return _backend

    _backend = None
    logger.warning("No OCR backend available (need pyobjc-framework-Vision or tesseract)")
    return _backend


def is_available() -> bool:
    """Check if any OCR backend is available."""
    return _detect_backend() is not None


def recognize(image_bytes: bytes, min_confidence: float = 0.3) -> str:
    """Run OCR on a PNG/JPEG image, return extracted text.

    Args:
        image_bytes: PNG or JPEG encoded image bytes.
        min_confidence: Minimum confidence threshold (0-1). Results
            below this are filtered out. 0.3 filters UI chrome while
            keeping real text. Lower to 0.1 for aggressive capture.

    Returns:
        Extracted text, with rows separated by newlines. Empty string
        if no text was found or no backend is available.

    Raises:
        ImportError: If no OCR backend is available.
    """
    backend = _detect_backend()
    if backend is None:
        raise ImportError(
            "No OCR backend available. Install one of:\n"
            "  macOS: pip install pyobjc-framework-Vision\n"
            "  Cross-platform: install tesseract binary"
        )

    if backend == "vision":
        return _recognize_vision(image_bytes, min_confidence)
    elif backend == "tesseract":
        return _recognize_tesseract(image_bytes)
    return ""


def _recognize_vision(image_bytes: bytes, min_confidence: float) -> str:
    """OCR using macOS Vision framework.

    VNRecognizeTextRequest returns text observations with bounding
    boxes. We sort by position (top-to-bottom, left-to-right) and
    group into rows to preserve terminal/code layout.
    """
    from Foundation import NSData
    from Vision import VNRecognizeTextRequest, VNImageRequestHandler

    ns_data = NSData.dataWithBytes_length_(image_bytes, len(image_bytes))
    request = VNRecognizeTextRequest.alloc().init()
    request.setRecognitionLanguages_(["en"])
    request.setRecognitionLevel_(1)  # accurate

    handler = VNImageRequestHandler.alloc().initWithData_options_(ns_data, None)
    success, error = handler.performRequests_error_([request], None)

    if not success:
        logger.warning(f"Vision OCR failed: {error}")
        return ""

    results = request.results()
    if not results:
        return ""

    # Extract text with confidence filtering and bounding boxes
    texts: List[Tuple[float, float, str]] = []  # (y, x, text)
    for r in results:
        candidates = r.topCandidates_(1)
        if not candidates:
            continue
        candidate = candidates[0]
        if candidate.confidence() < min_confidence:
            continue
        # Vision bounding box is normalized (0-1), origin bottom-left
        # We want top-to-bottom, so invert y
        bbox = r.boundingBox()
        y = 1.0 - bbox.origin.y  # top-to-bottom
        x = bbox.origin.x
        texts.append((y, x, candidate.string()))

    if not texts:
        return ""

    # Group into rows by y-coordinate clustering
    texts.sort(key=lambda t: (t[0], t[1]))
    return _group_into_rows(texts)


def _recognize_tesseract(image_bytes: bytes) -> str:
    """OCR using Tesseract via subprocess.

    Uses stdin/stdout to avoid temp file path issues. PSM 6 (uniform
    block of text) works well for terminal output and code.
    """
    try:
        result = subprocess.run(
            ["tesseract", "stdin", "stdout", "--psm", "6"],
            input=image_bytes,
            capture_output=True,
            timeout=10,
        )
        text = result.stdout.decode("utf-8", errors="replace").strip()
        if result.returncode != 0 and not text:
            stderr = result.stderr.decode("utf-8", errors="replace")
            logger.warning(f"Tesseract error: {stderr[:200]}")
        return text
    except subprocess.TimeoutExpired:
        logger.warning("Tesseract timed out")
        return ""
    except FileNotFoundError:
        raise ImportError("Tesseract binary not found in PATH")
    except Exception as e:
        logger.warning(f"Tesseract failed: {e}")
        return ""


def _group_into_rows(texts: List[Tuple[float, float, str]]) -> str:
    """Group OCR results into rows by y-coordinate proximity.

    Vision returns individual text fragments. Terminal output has
    strict horizontal rows, so we cluster by y-coordinate and join
    fragments on the same row with spaces.
    """
    if not texts:
        return ""

    # Cluster by y: two fragments are on the same row if their y
    # coordinates are within 0.02 (2% of image height) of each other.
    ROW_THRESHOLD = 0.02

    rows: List[List[Tuple[float, float, str]]] = []
    for y, x, text in texts:
        placed = False
        for row in rows:
            if abs(row[0][0] - y) < ROW_THRESHOLD:
                row.append((y, x, text))
                placed = True
                break
        if not placed:
            rows.append([(y, x, text)])

    # Sort each row by x, join with spaces
    lines = []
    for row in rows:
        row.sort(key=lambda t: t[1])
        lines.append(" ".join(t[2] for t in row))

    return "\n".join(lines)
