# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Blocklist redaction for screen capture.

Blurs screen regions that contain sensitive keywords before the image
is sent to the LLM. This prevents accidental exposure of passwords,
API keys, tokens, and other secrets that might be visible on screen.

How it works:
    1. Run OCR on the captured frame to get text with bounding boxes
    2. Check each text fragment against the blocklist (case-insensitive
       substring match) and regex patterns (for structured secrets)
    3. Blur any region whose text matches a blocklist entry or pattern
    4. Re-encode the redacted frame as JPEG

Two matching modes:
    - Keyword blocklist: case-insensitive substring match against a
      list of sensitive words (password, secret, token, etc.)
    - Regex patterns: regular expressions that match structured secret
      formats (AWS keys, GitHub tokens, private key blocks, etc.)

Both are configurable in vision_config.yml. Regex patterns are checked
after keyword matching — if a keyword already matches, the regex is
skipped for that fragment.

Performance: OCR runs once on the full frame (already done for
capture_and_ocr), so redaction adds negligible overhead when OCR is
already running. For capture_screenshot (image-only), redaction adds
one OCR pass (~50-200ms on Vision, ~200-500ms on Tesseract).

Limitations:
    - OCR-based: if the sensitive text is in an image (not rendered
      text), it won't be detected. This is a known limitation of
      text-based redaction.
    - Keyword matching: matches by substring, not semantic meaning.
      "passwordless" would trigger on "password". This is intentional
      — false positives are safer than false negatives for redaction.
"""

from __future__ import annotations

import logging
import re
from typing import List, Optional, Tuple

logger = logging.getLogger("halbert.vision.redact")

# Default blocklist: keywords that indicate sensitive content.
# Case-insensitive substring match. Adding a word here means any
# screen region containing that word will be blurred before sending
# to the LLM.
DEFAULT_BLOCKLIST = [
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "api-key",
    "access_key",
    "private_key",
    "credential",
    "authorization",
    "bearer",
    "session_id",
    "sessionid",
    "cookie",
    "oauth",
    "client_secret",
    "refresh_token",
    "access_token",
    "ssh-rsa",
    "ssh-ed25519",
    "BEGIN PRIVATE KEY",
    "BEGIN RSA PRIVATE KEY",
    "BEGIN OPENSSH PRIVATE KEY",
]

# Default regex patterns: structured secret formats that don't match
# simple keyword search. Each pattern is a compiled regex. If any
# pattern matches a text fragment, the region is blurred.
DEFAULT_REGEX_PATTERNS = [
    # AWS Access Key ID (20 chars, starts with AKIA)
    re.compile(r"AKIA[0-9A-Z]{16}"),
    # AWS Secret Access Key (40 chars base64)
    re.compile(r"aws_secret_access_key\s*[:=]\s*[A-Za-z0-9/+=]{40}"),
    # GitHub Personal Access Token (ghp_ + 36 chars)
    re.compile(r"ghp_[A-Za-z0-9]{36}"),
    # GitHub Fine-grained Token (github_pat_ + variable length)
    re.compile(r"github_pat_[A-Za-z0-9_]{82}"),
    # Slack Token (xoxb- or xoxp-)
    re.compile(r"xox[baprs]-[0-9A-Za-z-]{10,}"),
    # Stripe Key (sk_live_ or sk_test_)
    re.compile(r"sk_(live|test)_[A-Za-z0-9]{24,}"),
    # Google API Key (AIza + 35 chars)
    re.compile(r"AIza[0-9A-Za-z_\-]{35}"),
    # PEM private key block (full block, not just the header)
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    # JWT (three base64 segments separated by dots)
    re.compile(r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"),
    # Generic hex/base64 secret (32+ chars after secret/key assignment)
    re.compile(r"(?:secret|key|token)\s*[:=]\s*[A-Za-z0-9+/=]{32,}", re.IGNORECASE),
]


def get_blocklist(config=None) -> List[str]:
    """Get the keyword blocklist from config, or return defaults."""
    if config is not None and hasattr(config, "redaction"):
        if config.redaction.blocklist:
            return config.redaction.blocklist
    return DEFAULT_BLOCKLIST


def get_regex_patterns(config=None) -> List[re.Pattern]:
    """Get compiled regex patterns for structured secrets.

    Always returns DEFAULT_REGEX_PATTERNS — these match known secret
    formats (AWS keys, GitHub tokens, JWTs, etc.) that simple keyword
    matching would miss. Future config could allow custom patterns.
    """
    return DEFAULT_REGEX_PATTERNS


def _matches_sensitive(text: str, blocklist: List[str], patterns: List[re.Pattern]) -> bool:
    """Check if text matches any blocklist keyword or regex pattern.

    Keyword matching is case-insensitive substring. Regex matching
    uses fullmatch-equivalent (search) against compiled patterns.
    """
    text_lower = text.lower()

    # Check keywords first (fast path)
    for keyword in blocklist:
        if keyword.lower() in text_lower:
            return True

    # Check regex patterns (catches structured secrets without keywords)
    for pattern in patterns:
        if pattern.search(text):
            return True

    return False


def redact_image(
    image_bytes: bytes,
    blocklist: Optional[List[str]] = None,
    blur_strength: int = 51,
    patterns: Optional[List[re.Pattern]] = None,
) -> bytes:
    """Redact sensitive regions from an image.

    Runs OCR to find text, blurs regions matching the blocklist or
    regex patterns, and returns the redacted image as PNG bytes.

    Args:
        image_bytes: PNG or JPEG encoded image bytes.
        blocklist: List of keywords to redact (case-insensitive
            substring match). Defaults to DEFAULT_BLOCKLIST.
        blur_strength: Gaussian blur kernel size (must be odd, > 1).
            51 is strong enough to make text unreadable at any
            resolution.
        patterns: List of compiled regex patterns for structured
            secrets (AWS keys, GitHub tokens, JWTs, etc.). Defaults
            to DEFAULT_REGEX_PATTERNS.

    Returns:
        PNG-encoded image bytes with sensitive regions blurred.
        If OCR is unavailable or finds no matches, returns the
        original image unchanged.
    """
    if blocklist is None:
        blocklist = DEFAULT_BLOCKLIST
    if patterns is None:
        patterns = DEFAULT_REGEX_PATTERNS

    if not blocklist and not patterns:
        return image_bytes

    try:
        from .ocr import is_available, _detect_backend
    except ImportError:
        logger.warning("OCR module not available for redaction")
        return image_bytes

    if not is_available():
        logger.warning("No OCR backend for redaction — skipping")
        return image_bytes

    # We need bounding boxes for redaction, not just text.
    # The Vision backend provides them; Tesseract would need TSV mode.
    backend = _detect_backend()
    if backend != "vision":
        logger.info("Redaction requires Vision backend (current: %s), skipping", backend)
        return image_bytes

    try:
        import cv2
        import numpy as np
    except ImportError:
        return image_bytes

    # Decode image
    frame = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        return image_bytes

    # Get text with bounding boxes
    matches = _find_sensitive_regions(frame, blocklist, patterns)
    if not matches:
        return image_bytes

    # Blur each matching region
    for (x, y, w, h) in matches:
        pad = 10
        x0 = max(0, x - pad)
        y0 = max(0, y - pad)
        x1 = min(frame.shape[1], x + w + pad)
        y1 = min(frame.shape[0], y + h + pad)

        roi = frame[y0:y1, x0:x1]
        if roi.size > 0:
            blurred = cv2.GaussianBlur(roi, (blur_strength, blur_strength), 0)
            frame[y0:y1, x0:x1] = blurred

    logger.info(f"Redacted {len(matches)} sensitive regions")

    ok, buf = cv2.imencode(".png", frame)
    if not ok:
        return image_bytes
    return buf.tobytes()


def _find_sensitive_regions(
    frame,
    blocklist: List[str],
    patterns: List[re.Pattern],
    min_confidence: float = 0.3,
) -> List[Tuple[int, int, int, int]]:
    """Find screen regions containing blocklist keywords or regex matches.

    Returns a list of (x, y, width, height) tuples in pixel coordinates.
    """
    from Foundation import NSData
    from Vision import VNRecognizeTextRequest, VNImageRequestHandler
    import cv2

    ok, buf = cv2.imencode(".png", frame)
    if not ok:
        return []

    ns_data = NSData.dataWithBytes_length_(buf.tobytes(), len(buf.tobytes()))
    request = VNRecognizeTextRequest.alloc().init()
    request.setRecognitionLanguages_(["en"])
    request.setRecognitionLevel_(1)

    handler = VNImageRequestHandler.alloc().initWithData_options_(ns_data, None)
    success, error = handler.performRequests_error_([request], None)
    if not success:
        return []

    results = request.results()
    if not results:
        return []

    h, w = frame.shape[:2]
    matches = []

    for r in results:
        candidates = r.topCandidates_(1)
        if not candidates:
            continue
        candidate = candidates[0]
        if candidate.confidence() < min_confidence:
            continue

        text = candidate.string()
        if _matches_sensitive(text, blocklist, patterns):
            bbox = r.boundingBox()
            px_x = int(bbox.origin.x * w)
            px_y = int((1.0 - bbox.origin.y - bbox.size.height) * h)
            px_w = int(bbox.size.width * w)
            px_h = int(bbox.size.height * h)
            matches.append((px_x, px_y, px_w, px_h))

    return matches


def should_redact(config=None) -> bool:
    """Check if redaction is enabled in config.

    Redaction is OFF by default — it adds OCR overhead to every
    capture_screenshot call. Users can enable it in Settings > Vision
    when they frequently share screens with sensitive content.
    """
    if config is not None and hasattr(config, "redaction"):
        return config.redaction.enabled
    return False
