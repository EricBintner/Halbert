# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Disk cache for screenshots with TTL and quota.

Stores JPEGs in ~/.local/share/halbert/vision_cache/<hash>.jpg.
Rolling cleanup: 7-day TTL, 500MB quota. Oldest files pruned first.

Used by the VisualWatcher to store anomaly screenshots. The episodic
memory system stores the file URI in metadata, not the base64 image,
to avoid bloating the vector store.
"""
from __future__ import annotations

import base64
import hashlib
import logging
import os
import time
from pathlib import Path
from typing import Optional

from ..utils.paths import data_subdir

logger = logging.getLogger(__name__)

_DEFAULT_TTL_DAYS = 7
_DEFAULT_MAX_BYTES = 500 * 1024 * 1024  # 500 MB


class VisionCache:
    """Disk cache for screenshots with TTL and quota."""

    def __init__(
        self,
        base_dir: Optional[str] = None,
        ttl_days: int = _DEFAULT_TTL_DAYS,
        max_bytes: int = _DEFAULT_MAX_BYTES,
    ):
        if base_dir is None:
            base_dir = str(data_subdir("vision_cache"))
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.ttl_days = ttl_days
        self.max_bytes = max_bytes

    def store(self, image_b64: str) -> str:
        """Decode base64 image, save as JPEG, return file URI.

        If the image already exists (same hash), returns the existing URI
        without re-writing.
        """
        # Hash the base64 data to get a stable filename
        h = hashlib.md5(image_b64.encode("ascii", errors="ignore")).hexdigest()
        path = self.base_dir / f"{h}.jpg"

        if path.exists():
            return f"file://{path}"

        try:
            image_data = base64.b64decode(image_b64)
            path.write_bytes(image_data)
            logger.debug(f"VisionCache: stored {h}.jpg ({len(image_data)} bytes)")
        except Exception as e:
            logger.warning(f"VisionCache: failed to store image: {e}")
            return ""

        return f"file://{path}"

    def get_uri(self, hash_hex: str) -> Optional[str]:
        """Return URI if file exists, None otherwise."""
        path = self.base_dir / f"{hash_hex}.jpg"
        if path.exists():
            return f"file://{path}"
        return None

    def cleanup(self) -> int:
        """Delete expired files and prune to quota. Returns deleted count."""
        deleted = 0
        now = time.time()
        ttl_seconds = self.ttl_days * 86400

        # Phase 1: Delete files older than TTL
        files = []
        for f in self.base_dir.glob("*.jpg"):
            try:
                mtime = f.stat().st_mtime
                if now - mtime > ttl_seconds:
                    f.unlink()
                    deleted += 1
                    logger.debug(f"VisionCache: deleted expired {f.name}")
                else:
                    files.append((f, mtime, f.stat().st_size))
            except OSError:
                continue

        # Phase 2: Prune to quota (delete oldest first)
        total_size = sum(size for _, _, size in files)
        if total_size > self.max_bytes:
            # Sort by mtime ascending (oldest first)
            files.sort(key=lambda x: x[1])
            for f, _, size in files:
                if total_size <= self.max_bytes:
                    break
                try:
                    f.unlink()
                    total_size -= size
                    deleted += 1
                    logger.debug(f"VisionCache: pruned {f.name} (quota)")
                except OSError:
                    continue

        if deleted > 0:
            logger.info(f"VisionCache: cleanup deleted {deleted} files")
        return deleted

    def total_size(self) -> int:
        """Return total size of all cached files in bytes."""
        total = 0
        for f in self.base_dir.glob("*.jpg"):
            try:
                total += f.stat().st_size
            except OSError:
                continue
        return total

    def file_count(self) -> int:
        """Return number of cached files."""
        return len(list(self.base_dir.glob("*.jpg")))
