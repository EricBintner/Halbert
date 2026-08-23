"""
Memory Level of Detail (LOD) compression for Halbert.

Adapted from CoDRAG's lod_extractor.py for conversational memories
instead of source code.  Each LOD level produces progressively smaller
representations of a memory, enabling budget-aware context packing.

LOD Levels:
  0 — Full memory content + metadata               (1:1)
  1 — Content with filler words removed             (~1.3:1)
  2 — Key facts + importance markers                (~3:1)
  3 — Category + one-line summary                   (~5:1)
  4 — Keywords + timestamp                          (~8:1)
  5 — ID + category tag only                        (~20:1)

Ported from LinuxBrain Phase 72, adapted with sysadmin fact indicators
and an epistemic floor to prevent "lost along the way" compression
failures (from ACL 2025 gist token study).

Usage:
    from halbert_core.compression.memory_lod import compress_memory, assign_memory_lod

    # Determine LOD based on relevance + epistemic confidence
    lod = assign_memory_lod(relevance=0.6, epistemic=0.8)

    # Compress to that LOD
    compressed = compress_memory(memory_content, category="service",
                                 keywords=["nginx", "systemd"], lod=lod)

    # Budget-aware batch compression
    texts = compress_batch(memories, query="nginx status",
                           target_chars=2000)
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("halbert.compression.memory_lod")


# ── Filler words for LOD 1 removal ────────────────────────────────

_FILLER_RE = re.compile(
    r"\b(very|really|quite|somewhat|rather|incredibly|absolutely|totally|"
    r"completely|basically|essentially|fundamentally|actually|literally)\s+",
    re.IGNORECASE,
)

# ── Sentence-level fact extraction heuristics ─────────────────────
# Includes sysadmin fact verbs (configured, enabled, installed, etc.)
# alongside general prose fact verbs from LinuxBrain.

_FACT_INDICATORS = re.compile(
    r"\b(is|are|was|were|lives?|works?|grew up|born|from|named?|called|"
    # Sysadmin facts (NEW for Halbert)
    r"configured|enabled|disabled|installed|running|failed|"
    r"error|version|path|mounted|loaded|started|stopped|"
    r"set to|defined as|located at|points to)\b",
    re.IGNORECASE,
)


@dataclass
class LODResult:
    """Result of a memory LOD compression."""
    content: str
    lod: int
    input_chars: int
    output_chars: int

    @property
    def compression_ratio(self) -> float:
        return round(self.input_chars / max(self.output_chars, 1), 2)


# ── LOD compression functions ─────────────────────────────────────

def _remove_filler(text: str) -> str:
    """LOD 1: Remove filler/intensifier words."""
    cleaned = _FILLER_RE.sub("", text)
    return re.sub(r"\s+", " ", cleaned).strip()


def _extract_key_facts(text: str) -> str:
    """LOD 2: Extract sentences containing factual indicators."""
    sentences = re.split(r"[.!?]+", text)
    facts = []
    for sent in sentences:
        sent = sent.strip()
        if not sent:
            continue
        if _FACT_INDICATORS.search(sent):
            # Compress the fact sentence
            compressed = _FILLER_RE.sub("", sent)
            compressed = re.sub(r"\s+", " ", compressed).strip()
            if compressed:
                facts.append(compressed)
    if not facts:
        # Fallback: first sentence
        first = sentences[0].strip() if sentences else text[:100]
        return _remove_filler(first)
    return ". ".join(facts)


def _one_liner(text: str) -> str:
    """Extract a one-line summary from text (first sentence, compressed)."""
    first_sent = re.split(r"[.!?]", text)[0].strip()
    compressed = _FILLER_RE.sub("", first_sent)
    compressed = re.sub(r"\s+", " ", compressed).strip()
    if len(compressed) > 80:
        compressed = compressed[:77] + "..."
    return compressed


# ── Public API ────────────────────────────────────────────────────

def compress_memory(
    content: str,
    category: str = "general",
    keywords: Optional[List[str]] = None,
    memory_id: str = "",
    created_at: str = "",
    emotional_weight: float = 0.5,
    lod: int = 0,
) -> LODResult:
    """Compress a memory to the specified LOD level.

    Args:
        content: Full memory content text.
        category: Memory category (service, network, storage, etc.).
        keywords: Extracted keywords for LOD 4.
        memory_id: Memory ID for LOD 5.
        created_at: ISO timestamp for LOD 4.
        emotional_weight: 0.0-1.0 for LOD 2 importance markers.
        lod: Target LOD level (0-5).

    Returns:
        LODResult with compressed content and metadata.
    """
    input_chars = len(content)

    if lod <= 0:
        # LOD 0: Full content
        return LODResult(content=content, lod=0, input_chars=input_chars, output_chars=input_chars)

    if lod == 1:
        # LOD 1: Filler words removed
        compressed = _remove_filler(content)
        return LODResult(content=compressed, lod=1, input_chars=input_chars, output_chars=len(compressed))

    if lod == 2:
        # LOD 2: Key facts + importance marker
        facts = _extract_key_facts(content)
        if emotional_weight >= 0.7:
            facts += " [important]"
        elif emotional_weight <= 0.3:
            facts += " [minor]"
        return LODResult(content=facts, lod=2, input_chars=input_chars, output_chars=len(facts))

    if lod == 3:
        # LOD 3: Category + one-liner
        summary = f"[{category}] {_one_liner(content)}"
        return LODResult(content=summary, lod=3, input_chars=input_chars, output_chars=len(summary))

    if lod == 4:
        # LOD 4: Keywords + timestamp
        kw = keywords or []
        date_str = created_at[:10] if created_at else ""
        parts = [", ".join(kw)] if kw else [_one_liner(content)[:30]]
        if date_str:
            parts.append(f"({date_str})")
        compressed = " ".join(parts)
        return LODResult(content=compressed, lod=4, input_chars=input_chars, output_chars=len(compressed))

    # LOD 5: ID + category tag only
    tag = f"{memory_id or 'mem'}:{category}"
    return LODResult(content=tag, lod=5, input_chars=input_chars, output_chars=len(tag))


def assign_memory_lod(relevance: float, epistemic: float = 1.0) -> int:
    """Assign a LOD level based on relevance and epistemic confidence.

    Higher combined scores → lower LOD (more detail).
    Lower combined scores → higher LOD (more compression).

    Epistemic floor: if epistemic >= 0.8, never return LOD > 2.
    This prevents the "lost along the way" failure mode identified in
    the ACL 2025 gist token compression study, where high-confidence
    information degrades through multiple compression levels.

    Args:
        relevance: Cosine similarity or search relevance (0.0-1.0).
        epistemic: Epistemic confidence score (0.0-1.0).

    Returns:
        LOD level 0-5.
    """
    combined = 0.6 * relevance + 0.4 * epistemic
    if combined >= 0.70:
        return 0
    if combined >= 0.50:
        return 1
    if combined >= 0.35:
        return 2
    # Epistemic floor: high-confidence memories stay at LOD 2
    if epistemic >= 0.8:
        return 2
    if combined >= 0.20:
        return 3
    if combined >= 0.10:
        return 4
    return 5


def compress_batch(
    memories: List[Dict[str, Any]],
    query: str = "",
    target_chars: int = 4000,
) -> str:
    """Compress a batch of memories to fit within a character budget.

    Assigns LOD levels dynamically based on relevance scores, compressing
    less-relevant memories more aggressively to maximize context breadth
    within the token budget.

    Args:
        memories: List of memory dicts with keys:
            content, category, keywords, id, created_at,
            emotional_weight, relevance, epistemic_score
        query: Search query for context.
        target_chars: Target character budget for all memories combined.

    Returns:
        Combined compressed text ready for prompt injection.
    """
    if not memories:
        return ""

    # Sort by relevance (highest first)
    sorted_mems = sorted(memories, key=lambda m: m.get("relevance", 0.0), reverse=True)

    # First pass: assign LODs and estimate sizes
    entries: List[Tuple[Dict[str, Any], int]] = []
    for mem in sorted_mems:
        rel = mem.get("relevance", 0.5)
        epi = mem.get("epistemic_score", 0.5)
        lod = assign_memory_lod(rel, epi)
        entries.append((mem, lod))

    # Render and check budget
    parts: List[str] = []
    total_chars = 0

    for mem, lod in entries:
        result = compress_memory(
            content=mem.get("content", ""),
            category=mem.get("category", "general"),
            keywords=mem.get("keywords"),
            memory_id=mem.get("id", ""),
            created_at=mem.get("created_at", ""),
            emotional_weight=mem.get("emotional_weight", 0.5),
            lod=lod,
        )

        # If adding this memory would exceed budget, try higher LOD
        while total_chars + result.output_chars > target_chars and lod < 5:
            lod += 1
            result = compress_memory(
                content=mem.get("content", ""),
                category=mem.get("category", "general"),
                keywords=mem.get("keywords"),
                memory_id=mem.get("id", ""),
                created_at=mem.get("created_at", ""),
                emotional_weight=mem.get("emotional_weight", 0.5),
                lod=lod,
            )

        if total_chars + result.output_chars > target_chars:
            break  # Budget exhausted

        parts.append(result.content)
        total_chars += result.output_chars

    return "\n".join(parts)
