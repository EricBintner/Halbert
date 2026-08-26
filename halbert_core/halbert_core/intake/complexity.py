# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
LLM-based complexity router for incoming messages.

Uses a small guide model to rate query complexity 1-5, with fast paths
for greetings/farewells and a floor for troubleshooting. Includes an LRU
cache and stats tracking for observability.
"""

from __future__ import annotations

import hashlib
import logging
import time
from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Callable, Dict, Optional

from .signals import MessageSignals

logger = logging.getLogger(__name__)


class ComplexityLevel(IntEnum):
    TRIVIAL = 1
    SIMPLE = 2
    MODERATE = 3
    COMPLEX = 4
    VERY_COMPLEX = 5


@dataclass
class ComplexityResult:
    score: int           # 1-5
    level: ComplexityLevel
    reasoning: str = ""
    latency_ms: float = 0.0
    cached: bool = False


# ── Prompt ───────────────────────────────────────────────────────

_COMPLEXITY_PROMPT = (
    "Rate the complexity of this sysadmin query as a single digit 1-5 "
    "(1=trivial, 5=very complex). Query: {message}\nRating:"
)


# ── Router ───────────────────────────────────────────────────────

class ComplexityRouter:
    """Assesses message complexity using an LLM with caching and fast paths."""

    def __init__(
        self,
        llm_caller: Callable,
        guide_model: str,
        endpoint: str,
        cache_size: int = 100,
    ):
        """Args:
            llm_caller: callable wrapping call_llm_chat — signature:
                llm_caller(endpoint, model, messages, options) -> dict
                The response dict must have a "response" key with text.
            guide_model: model name for the complexity assessment LLM call.
            endpoint: LLM endpoint URL.
            cache_size: max LRU cache entries.
        """
        self._llm_caller = llm_caller
        self._guide_model = guide_model
        self._endpoint = endpoint
        self._cache_size = cache_size

        # LRU cache over message hashes (OrderedDict; O(1) hit/evict).
        # Kept manual (not functools.lru_cache) so we can track hits/misses
        # and report cache size in stats.
        self._cache: OrderedDict[str, ComplexityResult] = OrderedDict()

        # Stats
        self._cache_hits = 0
        self._cache_misses = 0
        self._latencies: list[float] = []
        self._score_dist: Dict[int, int] = defaultdict(int)

    def assess(self, message: str, signals: MessageSignals) -> ComplexityResult:
        """Assess the complexity of a message.

        Fast paths (no LLM):
            - Greeting/farewell -> score=1, cached=True
            - Troubleshooting -> minimum score=3

        LLM path:
            - Calls the guide model with a 5-token prompt
            - Parses first digit 1-5 from response
            - Falls back to score=3 on parse failure or timeout
        """
        # ── Fast path: greeting/farewell ─────────────────────────
        if signals.is_greeting or signals.is_farewell:
            result = ComplexityResult(
                score=1,
                level=ComplexityLevel.TRIVIAL,
                reasoning="greeting/farewell fast path",
                latency_ms=0.0,
                cached=True,
            )
            self._score_dist[1] += 1
            return result

        # ── Cache lookup ─────────────────────────────────────────
        cache_key = self._hash_message(message)
        if cache_key in self._cache:
            self._cache_hits += 1
            self._cache.move_to_end(cache_key)
            cached = self._cache[cache_key]
            return ComplexityResult(
                score=cached.score,
                level=cached.level,
                reasoning=cached.reasoning,
                latency_ms=0.0,
                cached=True,
            )

        # ── LLM call ─────────────────────────────────────────────
        self._cache_misses += 1
        start = time.perf_counter()
        score = self._call_llm(message)
        latency_ms = (time.perf_counter() - start) * 1000

        # ── Troubleshooting floor ────────────────────────────────
        if signals.is_troubleshooting and score < 3:
            score = 3

        level = ComplexityLevel(score)
        result = ComplexityResult(
            score=score,
            level=level,
            reasoning="llm assessment",
            latency_ms=latency_ms,
            cached=False,
        )

        # ── Update cache ─────────────────────────────────────────
        self._cache[cache_key] = result
        self._cache.move_to_end(cache_key)
        while len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)

        # ── Update stats ─────────────────────────────────────────
        self._latencies.append(latency_ms)
        if len(self._latencies) > 1000:
            self._latencies = self._latencies[-500:]
        self._score_dist[score] += 1

        return result

    def get_stats(self) -> dict:
        """Return observability stats."""
        avg_latency = (
            sum(self._latencies) / len(self._latencies)
            if self._latencies else 0.0
        )
        return {
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "cache_size": len(self._cache),
            "cache_capacity": self._cache_size,
            "avg_latency_ms": round(avg_latency, 2),
            "score_distribution": dict(self._score_dist),
        }

    # ── Internal ────────────────────────────────────────────────

    def _hash_message(self, message: str) -> str:
        return hashlib.sha256(message.encode()).hexdigest()[:16]

    def _call_llm(self, message: str) -> int:
        """Call the guide model and parse the complexity score."""
        prompt = _COMPLEXITY_PROMPT.format(message=message)
        try:
            response = self._llm_caller(
                self._endpoint,
                self._guide_model,
                [{"role": "user", "content": prompt}],
                {"num_predict": 5, "temperature": 0.1},
            )
            text = response.get("response", "") if isinstance(response, dict) else str(response)
            return self._parse_score(text)
        except Exception as e:
            logger.warning(f"Complexity LLM call failed: {e}")
            return 3  # safe fallback

    @staticmethod
    def _parse_score(text: str) -> int:
        """Extract the first digit 1-5 from the response text."""
        for char in text:
            if char.isdigit() and 1 <= int(char) <= 5:
                return int(char)
        return 3  # fallback
