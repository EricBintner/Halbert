#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""P-06 — OCR misreads its own synthetic fixture (observational).

The seam (collected empirically 2026-09-07): ``test_ocr.py::
TestRecognize::test_simple_text`` renders "Error: file not found" with
cv2.putText and expects the backend's text to contain "Error"/"not found";
on this box the local OCR backend returned ``"ErFor.' file not found"`` —
the word "Error:" misread, so the assertion fails deterministically on this
machine's backend (tesseract at /usr/local/bin/tesseract).

Cause is recognition quality of the installed backend, not a product
branch — the probe records the observed output and does not judge it.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _env import bootstrap  # noqa: E402

bootstrap()

PROBE_ID = "P-06"


def main() -> int:
    import numpy as np

    try:
        import cv2
    except ImportError:
        print(f"PROBE {PROBE_ID} ocr-simple-text: OBSERVED -- cv2 not installed in this venv")
        return 0

    from halbert_core.vision.ocr import _detect_backend, recognize

    backend = _detect_backend()
    if backend is None:
        print(f"PROBE {PROBE_ID} ocr-simple-text: OBSERVED -- no OCR backend available")
        return 0

    img = np.ones((30 + 30, 600, 3), dtype=np.uint8) * 255
    cv2.putText(img, "Error: file not found", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 1)
    ok, buf = cv2.imencode(".png", img)
    text = recognize(buf.tobytes())
    hit = "error" in text.lower()
    print(
        f"PROBE {PROBE_ID} ocr-simple-text: OBSERVED -- backend={backend}; "
        f"recognize() -> {text!r}; contains 'error': {hit}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:
        print(f"PROBE {PROBE_ID} ocr-simple-text: HARNESS-ERROR -- {exc!r}")
        raise SystemExit(3)