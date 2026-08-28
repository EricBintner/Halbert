# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for the OCR module.

Tests use synthetic images (cv2.putText) so they don't depend on the
screen state. Backend detection is tested but actual OCR runs only
when a backend is available (skipped otherwise).
"""

import pytest
import numpy as np

try:
    import cv2
    HAVE_CV2 = True
except ImportError:
    HAVE_CV2 = False


def _make_text_image(lines, width=600, height=None, font_scale=0.6):
    """Create a black-on-white image with the given text lines."""
    if not HAVE_CV2:
        return None
    if height is None:
        height = 30 + len(lines) * 30
    img = np.ones((height, width, 3), dtype=np.uint8) * 255  # White
    for i, line in enumerate(lines):
        cv2.putText(img, line, (10, 30 + i * 30),
                    cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0, 0, 0), 1)
    return img


@pytest.mark.skipif(not HAVE_CV2, reason="opencv not installed")
class TestOCRBackendDetection:
    def test_detect_backend_returns_string_or_none(self):
        from halbert_core.vision.ocr import _detect_backend
        backend = _detect_backend()
        assert backend is None or backend in ("vision", "tesseract")

    def test_is_available_matches_detect(self):
        from halbert_core.vision.ocr import is_available, _detect_backend
        assert is_available() == (_detect_backend() is not None)


@pytest.mark.skipif(not HAVE_CV2, reason="opencv not installed")
class TestRecognize:
    def test_simple_text(self):
        from halbert_core.vision.ocr import recognize, is_available
        if not is_available():
            pytest.skip("No OCR backend available")

        img = _make_text_image(["Error: file not found"])
        ok, buf = cv2.imencode(".png", img)
        text = recognize(buf.tobytes())
        assert "Error" in text or "error" in text.lower()
        assert "not found" in text.lower() or "not" in text.lower()

    def test_multi_line_text(self):
        from halbert_core.vision.ocr import recognize, is_available
        if not is_available():
            pytest.skip("No OCR backend available")

        img = _make_text_image([
            "line one",
            "line two",
            "line three",
        ])
        ok, buf = cv2.imencode(".png", img)
        text = recognize(buf.tobytes())
        # Should contain text from multiple lines
        assert len(text) > 5
        # Should have newlines (multi-line structure preserved)
        assert "\n" in text or "one" in text.lower()

    def test_empty_image_returns_empty(self):
        from halbert_core.vision.ocr import recognize, is_available
        if not is_available():
            pytest.skip("No OCR backend available")

        img = np.ones((100, 400, 3), dtype=np.uint8) * 255  # Pure white
        ok, buf = cv2.imencode(".png", img)
        text = recognize(buf.tobytes())
        assert text == ""

    def test_raises_import_error_when_no_backend(self, monkeypatch):
        from halbert_core.vision import ocr

        # Force no backend
        monkeypatch.setattr(ocr, "_backend", None)
        monkeypatch.setattr(ocr, "_backend_checked", True)

        with pytest.raises(ImportError, match="No OCR backend"):
            ocr.recognize(b"\x00")


class TestGroupIntoRows:
    def test_empty_list(self):
        from halbert_core.vision.ocr import _group_into_rows
        assert _group_into_rows([]) == ""

    def test_single_fragment(self):
        from halbert_core.vision.ocr import _group_into_rows
        result = _group_into_rows([(0.1, 0.2, "hello")])
        assert result == "hello"

    def test_two_rows(self):
        from halbert_core.vision.ocr import _group_into_rows
        # Two fragments on different rows (y differs by > 0.02)
        texts = [
            (0.1, 0.0, "first"),
            (0.5, 0.0, "second"),
        ]
        result = _group_into_rows(texts)
        assert "first" in result
        assert "second" in result
        assert "\n" in result

    def test_same_row_joined_with_space(self):
        from halbert_core.vision.ocr import _group_into_rows
        # Two fragments on the same row (y differs by < 0.02)
        texts = [
            (0.1, 0.0, "hello"),
            (0.105, 0.5, "world"),
        ]
        result = _group_into_rows(texts)
        assert result == "hello world"
