"""
Compressor factory for Halbert.

Creates the best available compression backend based on installed dependencies.

**Priority:**
  1. LinguaCompressor (if llmlingua installed and model available)
  2. SemanticCompressor (always available, zero deps)
  3. NoopCompressor (pass-through fallback)

Ported from LinuxBrain Phase 72.
"""

from __future__ import annotations

import logging
from typing import Optional

from halbert_core.compression.compressor import ContextCompressor, NoopCompressor
from halbert_core.compression.lingua_compressor import LinguaCompressor
from halbert_core.compression.semantic_compressor import SemanticCompressor

logger = logging.getLogger("halbert.compression.factory")


def create_compressor(
    backend: Optional[str] = None,
    prefer_neural: bool = True,
) -> ContextCompressor:
    """Create the best available compressor.

    Args:
        backend: Force a specific backend: "lingua", "semantic", "noop".
        prefer_neural: If True (default), prefer LinguaCompressor over SemanticCompressor.

    Returns:
        A ContextCompressor instance.
    """
    # ── 1. Explicit backend ────────────────────────────────────
    if backend == "lingua":
        lingua = LinguaCompressor()
        if lingua.is_available():
            logger.info("Using LinguaCompressor (explicit)")
            return lingua
        logger.warning("LinguaCompressor requested but llmlingua not installed")
        return SemanticCompressor()

    if backend == "semantic":
        logger.info("Using SemanticCompressor (explicit)")
        return SemanticCompressor()

    if backend == "noop":
        logger.info("Using NoopCompressor (explicit, no compression)")
        return NoopCompressor()

    # ── 2. Auto-detect ─────────────────────────────────────────
    if prefer_neural:
        lingua = LinguaCompressor()
        if lingua.is_available():
            logger.info("Using LinguaCompressor (auto-detected, LLMLingua-2)")
            return lingua

    # ── 3. Semantic fallback (always available) ────────────────
    logger.info("Using SemanticCompressor (rule-based compression)")
    return SemanticCompressor()
