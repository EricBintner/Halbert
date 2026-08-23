"""
Rule-based semantic compressor for Halbert.

Absorbs the regex-based filler removal and phrase replacement logic into
the unified ContextCompressor ABC.

This is the lightweight, zero-dependency compressor that works everywhere.
For neural compression, use LinguaCompressor instead.

Ported from LinuxBrain Phase 72, adapted for sysadmin context.
"""

from __future__ import annotations

import re
import time
import logging
from typing import Any, Dict, List, Optional

from halbert_core.compression.compressor import CompressResult, ContextCompressor

logger = logging.getLogger("halbert.compression.semantic")

# ── Filler patterns to remove ─────────────────────────────────────

_FILLER_PATTERNS = [
    r"\b(very|really|quite|somewhat|rather|incredibly|absolutely|totally|completely)\s+",
    r"\b(basically|essentially|fundamentally|actually|literally)\s+",
    r"\b(in fact|as a matter of fact|to be honest|honestly speaking)\s*,?\s*",
    r"\b(it is worth noting that|it should be noted that)\s*",
    r"\b(at this point in time|at the present moment)\s*",
    r"\b(due to the fact that)\s*",
    r"\b(in order to)\s+",
    r"\b(a lot of)\s+",
]

# ── Verbose → concise phrase replacements ─────────────────────────

_PHRASE_REPLACEMENTS = [
    (r"\bhas always been\b", "is"),
    (r"\bhas been known to\b", "tends to"),
    (r"\bwas able to\b", "could"),
    (r"\bin the process of\b", ""),
    (r"\bthe reason being that\b", "because"),
    (r"\bwith the exception of\b", "except"),
    (r"\bin the event that\b", "if"),
    (r"\bprior to\b", "before"),
    (r"\bsubsequent to\b", "after"),
    (r"\bat the time when\b", "when"),
    (r"\bin spite of the fact that\b", "although"),
    (r"\bfor the purpose of\b", "to"),
]

# ── Aggressive-mode adjective removal ─────────────────────────────

_DECORATIVE_ADJECTIVES = re.compile(
    r"\b(beautiful|wonderful|amazing|incredible|fantastic|excellent|great|lovely|nice)\s+(\w+)",
    re.IGNORECASE,
)

# ── Abbreviation patterns ─────────────────────────────────────────

_ABBREVIATIONS = [
    (r"\byears old\b", "y/o"),
    (r"\band\b", "&"),
    (r"\bwith\b", "w/"),
    (r"\bwithout\b", "w/o"),
    (r"\bbecause\b", "bc"),
    (r"\bapproximately\b", "~"),
]

# ── Stopwords for keyword extraction ──────────────────────────────

_STOPWORDS = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will",
    "would", "could", "should", "may", "might", "must", "shall",
    "can", "need", "dare", "ought", "used", "to", "of", "in",
    "for", "on", "with", "at", "by", "from", "as", "into",
    "through", "during", "before", "after", "above", "below",
    "between", "under", "again", "further", "then", "once",
    "here", "there", "when", "where", "why", "how", "all",
    "each", "few", "more", "most", "other", "some", "such",
    "no", "nor", "not", "only", "own", "same", "so", "than",
    "too", "very", "just", "and", "but", "if", "or", "because",
    "while", "although", "this", "that", "these", "those",
    "i", "me", "my", "myself", "we", "our", "ours", "you",
    "your", "he", "him", "his", "she", "her", "it", "its",
    "they", "them", "their", "what", "which", "who", "whom",
})


class SemanticCompressor(ContextCompressor):
    """Rule-based semantic compressor using regex patterns.

    Zero external dependencies.  Works everywhere.

    Levels:
    - "light": filler removal + phrase replacement only
    - "standard": + adjective trimming + subordinate clause removal
    - "aggressive": + abbreviations + truncation
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
        input_chars = len(text)
        if input_chars == 0:
            return CompressResult(compressed="", input_chars=0, output_chars=0)

        t0 = time.perf_counter()

        # ── Light: filler + verbose phrase removal ──
        compressed = text
        for pattern in _FILLER_PATTERNS:
            compressed = re.sub(pattern, "", compressed, flags=re.IGNORECASE)
        for pattern, replacement in _PHRASE_REPLACEMENTS:
            compressed = re.sub(pattern, replacement, compressed, flags=re.IGNORECASE)
        # Remove redundant articles in lists
        compressed = re.sub(r"\b(the|a|an)\s+(\w+),\s+\1\s+", r"\2, ", compressed)
        # Collapse whitespace
        compressed = re.sub(r"\s+", " ", compressed).strip()

        if level == "light":
            return self._result(text, compressed, t0)

        # ── Standard: + adjective trimming + clause pruning ──
        compressed = _DECORATIVE_ADJECTIVES.sub(r"\2", compressed)
        sentences = compressed.split(". ")
        shortened = []
        for sent in sentences:
            sent = re.sub(r",\s*which\s+[^,]+", "", sent)
            sent = re.sub(r",\s*who\s+[^,]+", "", sent)
            stripped = sent.strip()
            if stripped:
                shortened.append(stripped)
        compressed = ". ".join(shortened)

        if level == "standard":
            return self._result(text, compressed, t0)

        # ── Aggressive: + abbreviations ──
        for pattern, replacement in _ABBREVIATIONS:
            compressed = re.sub(pattern, replacement, compressed, flags=re.IGNORECASE)

        # Budget-based truncation
        if budget_chars > 0 and len(compressed) > budget_chars:
            compressed = compressed[:budget_chars - 3] + "..."

        return self._result(text, compressed, t0)

    def is_available(self) -> bool:
        return True  # Zero deps

    @staticmethod
    def _result(original: str, compressed: str, t0: float) -> CompressResult:
        input_chars = len(original)
        output_chars = len(compressed)
        ratio = input_chars / output_chars if output_chars > 0 else 1.0
        return CompressResult(
            compressed=compressed,
            input_chars=input_chars,
            output_chars=output_chars,
            compression_ratio=round(ratio, 2),
            timing_ms=round((time.perf_counter() - t0) * 1000, 1),
        )

    # ── Utility methods (reusable by other components) ─────────

    @staticmethod
    def extract_keywords(text: str, max_keywords: int = 10) -> List[str]:
        """Extract keywords from text (stopword-filtered, deduplicated)."""
        words = text.lower().split()
        seen: set = set()
        keywords: List[str] = []
        for word in words:
            clean = re.sub(r"[^\w]", "", word)
            if clean and clean not in _STOPWORDS and len(clean) > 2 and clean not in seen:
                seen.add(clean)
                keywords.append(clean)
        return keywords[:max_keywords]

    @staticmethod
    def infer_category(text: str) -> str:
        """Infer memory category from content text.

        Sysadmin categories for Halbert (replaces LinuxBrain's persona categories).
        """
        t = text.lower()
        if any(w in t for w in ["service", "daemon", "systemd", "running", "stopped", "started"]):
            return "service"
        if any(w in t for w in ["network", "interface", "ip", "dns", "routing", "ethernet", "wifi"]):
            return "network"
        if any(w in t for w in ["disk", "mount", "partition", "filesystem", "lvm", "storage", "nvme"]):
            return "storage"
        if any(w in t for w in ["firewall", "ssh", "cert", "ssl", "permissions", "sudo", "auth"]):
            return "security"
        if any(w in t for w in ["package", "apt", "dpkg", "rpm", "installed", "version", "update"]):
            return "package"
        if any(w in t for w in ["kernel", "module", "driver", "boot", "grub", "initramfs"]):
            return "kernel"
        if any(w in t for w in ["cpu", "memory", "ram", "gpu", "hardware", "device"]):
            return "hardware"
        return "config"
