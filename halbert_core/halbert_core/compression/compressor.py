"""
Context compression abstraction for Halbert.

Provides a base class and noop implementation for compressing
retrieved context before injecting it into LLM prompts.

Ported from LinuxBrain Phase 72 (originally from CoDRAG's compressor.py).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class CompressResult:
    """Result of a context compression operation."""

    compressed: str
    input_chars: int
    output_chars: int
    input_tokens: int = 0
    output_tokens: int = 0
    compression_ratio: float = 1.0
    timing_ms: float = 0.0
    error: Optional[str] = None


class ContextCompressor(ABC):
    """Abstract base class for context compression providers."""

    @abstractmethod
    def compress(
        self,
        text: str,
        *,
        query: str = "",
        budget_chars: int = 0,
        level: str = "standard",
        timeout_s: float = 30.0,
    ) -> CompressResult:
        """Compress context text.

        Args:
            text: The context string to compress.
            query: The original search query (helps focus compression).
            budget_chars: Target output size in characters. 0 = let compressor decide.
            level: Compression aggressiveness: "light", "standard", "aggressive".
            timeout_s: Hard timeout for the compression call.

        Returns:
            CompressResult with compressed text and metadata.
        """
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the compression backend is ready."""
        ...

    def status(self) -> Dict[str, Any]:
        """Get status info from the compression service."""
        return {"available": self.is_available()}


class NoopCompressor(ContextCompressor):
    """Pass-through compressor that returns text unchanged.

    Used as default when no compression backend is configured.
    """

    def compress(
        self,
        text: str,
        *,
        query: str = "",
        budget_chars: int = 0,
        level: str = "standard",
        timeout_s: float = 30.0,
    ) -> CompressResult:
        return CompressResult(
            compressed=text,
            input_chars=len(text),
            output_chars=len(text),
        )

    def is_available(self) -> bool:
        return True
