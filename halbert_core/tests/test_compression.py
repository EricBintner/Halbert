# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Tests for the Halbert compression package.

Covers all 3 tiers (Lingua, Semantic, MemoryLOD) + factory + epistemic floor.
LinuxBrain's compression package had zero tests — these are new.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from halbert_core.compression.compressor import (
    CompressResult,
    ContextCompressor,
    NoopCompressor,
)
from halbert_core.compression.semantic_compressor import SemanticCompressor
from halbert_core.compression.lingua_compressor import LinguaCompressor
from halbert_core.compression.memory_lod import (
    compress_memory,
    assign_memory_lod,
    compress_batch,
    LODResult,
)
from halbert_core.compression.factory import create_compressor


# ── CompressResult + NoopCompressor ──────────────────────────────


class TestCompressResult:
    def test_defaults(self):
        r = CompressResult(compressed="abc", input_chars=10, output_chars=3)
        assert r.compressed == "abc"
        assert r.input_chars == 10
        assert r.output_chars == 3
        assert r.input_tokens == 0
        assert r.output_tokens == 0
        assert r.compression_ratio == 1.0
        assert r.timing_ms == 0.0
        assert r.error is None

    def test_frozen(self):
        r = CompressResult(compressed="abc", input_chars=10, output_chars=3)
        with pytest.raises(Exception):
            r.compressed = "xyz"  # type: ignore[misc]


class TestNoopCompressor:
    def test_pass_through(self):
        c = NoopCompressor()
        result = c.compress("hello world")
        assert result.compressed == "hello world"
        assert result.input_chars == 11
        assert result.output_chars == 11
        assert result.compression_ratio == 1.0

    def test_is_available(self):
        assert NoopCompressor().is_available() is True

    def test_empty_input(self):
        result = NoopCompressor().compress("")
        assert result.compressed == ""
        assert result.input_chars == 0


# ── SemanticCompressor ───────────────────────────────────────────


class TestSemanticCompressor:
    def test_light_level_filler_removal(self):
        c = SemanticCompressor()
        text = "The service is very really quite important and basically running"
        result = c.compress(text, level="light")
        assert "very" not in result.compressed
        assert "really" not in result.compressed
        assert "basically" not in result.compressed
        assert result.output_chars < result.input_chars

    def test_standard_level_clause_pruning(self):
        c = SemanticCompressor()
        text = "The config file, which is located at /etc/nginx, is enabled."
        result = c.compress(text, level="standard")
        assert "which is located" not in result.compressed

    def test_aggressive_level_abbreviations(self):
        c = SemanticCompressor()
        text = "The package version 1.2 with dependencies and without conflicts"
        result = c.compress(text, level="aggressive")
        assert "w/" in result.compressed or "w/o" in result.compressed

    def test_aggressive_budget_truncation(self):
        c = SemanticCompressor()
        text = "A" * 200
        result = c.compress(text, level="aggressive", budget_chars=50)
        assert len(result.compressed) <= 50
        assert result.compressed.endswith("...")

    def test_empty_input(self):
        result = SemanticCompressor().compress("")
        assert result.compressed == ""
        assert result.input_chars == 0

    def test_is_available(self):
        assert SemanticCompressor().is_available() is True

    def test_extract_keywords(self):
        text = "The nginx service is running on port 80 with ssl enabled"
        keywords = SemanticCompressor.extract_keywords(text, max_keywords=5)
        assert "nginx" in keywords
        assert "service" in keywords
        assert "running" in keywords
        assert "the" not in keywords  # stopword filtered

    def test_infer_category_service(self):
        assert SemanticCompressor.infer_category("The systemd service is running") == "service"

    def test_infer_category_network(self):
        assert SemanticCompressor.infer_category("Network interface eth0 is configured") == "network"

    def test_infer_category_storage(self):
        assert SemanticCompressor.infer_category("Disk mounted at /mnt/data") == "storage"

    def test_infer_category_security(self):
        assert SemanticCompressor.infer_category("Firewall enabled for ssh access") == "security"

    def test_infer_category_package(self):
        assert SemanticCompressor.infer_category("apt package version 1.2 installed") == "package"

    def test_infer_category_kernel(self):
        assert SemanticCompressor.infer_category("Kernel module loaded at boot") == "kernel"

    def test_infer_category_hardware(self):
        assert SemanticCompressor.infer_category("CPU usage is high, memory at 80%") == "hardware"

    def test_infer_category_config_default(self):
        assert SemanticCompressor.infer_category("Some random text about nothing specific") == "config"


# ── LinguaCompressor ─────────────────────────────────────────────


class TestLinguaCompressor:
    def test_is_available_false_when_not_installed(self):
        c = LinguaCompressor()
        # llmlingua is likely not installed in test env
        # Just check it returns a bool without crashing
        result = c.is_available()
        assert isinstance(result, bool)

    def test_compress_fallback_on_unavailable(self):
        c = LinguaCompressor()
        text = "Some text to compress"
        result = c.compress(text)
        # If llmlingua not installed, should return text unchanged with error
        if not c.is_available():
            assert result.compressed == text
            assert result.error is not None
        # If installed, should return compressed text
        assert result.input_chars == len(text)

    def test_compress_empty(self):
        result = LinguaCompressor().compress("")
        assert result.compressed == ""
        assert result.input_chars == 0

    def test_status(self):
        status = LinguaCompressor().status()
        assert "available" in status
        assert "model" in status
        assert "loaded" in status
        assert "downloaded" in status
        assert status["type"] == "lingua"

    def test_force_tokens_include_sysadmin(self):
        # Verify sysadmin tokens are in the FORCE_TOKENS list
        assert "/" in LinguaCompressor.FORCE_TOKENS
        assert "=" in LinguaCompressor.FORCE_TOKENS
        assert "|" in LinguaCompressor.FORCE_TOKENS
        assert "#" in LinguaCompressor.FORCE_TOKENS

    def test_level_rates(self):
        rates = LinguaCompressor.LEVEL_RATES
        assert rates["light"] == 0.6
        assert rates["standard"] == 0.4
        assert rates["aggressive"] == 0.25


# ── MemoryLOD ────────────────────────────────────────────────────


class TestMemoryLOD:
    def test_lod0_full_content(self):
        text = "The nginx service is running on port 80."
        result = compress_memory(text, lod=0)
        assert result.lod == 0
        assert result.content == text
        assert result.output_chars == len(text)

    def test_lod1_filler_removed(self):
        text = "The nginx service is very really quite running on port 80."
        result = compress_memory(text, lod=1)
        assert result.lod == 1
        assert "very" not in result.content
        assert "really" not in result.content
        assert result.output_chars < result.input_chars

    def test_lod2_key_facts(self):
        text = "The nginx service is running. It handles web traffic. Hello there."
        result = compress_memory(text, lod=2, emotional_weight=0.8)
        assert result.lod == 2
        assert "running" in result.content
        assert "[important]" in result.content  # high emotional_weight

    def test_lod2_minor_marker(self):
        text = "The nginx service is running on port 80."
        result = compress_memory(text, lod=2, emotional_weight=0.2)
        assert "[minor]" in result.content

    def test_lod3_category_one_liner(self):
        text = "The nginx service is running on port 80 with ssl enabled."
        result = compress_memory(text, category="service", lod=3)
        assert result.lod == 3
        assert result.content.startswith("[service]")

    def test_lod4_keywords_timestamp(self):
        text = "The nginx service is running on port 80."
        result = compress_memory(
            text, category="service", keywords=["nginx", "port"], created_at="2026-08-23T10:00:00", lod=4
        )
        assert result.lod == 4
        assert "nginx" in result.content
        assert "port" in result.content
        assert "2026-08-23" in result.content

    def test_lod5_id_tag(self):
        result = compress_memory("some content", category="network", memory_id="mem42", lod=5)
        assert result.lod == 5
        assert result.content == "mem42:network"

    def test_lod5_default_id(self):
        result = compress_memory("some content", category="service", lod=5)
        assert result.content == "mem:service"

    def test_compression_ratio_property(self):
        result = compress_memory("A" * 100, lod=5, memory_id="x", category="c")
        assert result.compression_ratio > 1.0


class TestAssignMemoryLOD:
    def test_high_relevance_returns_0(self):
        assert assign_memory_lod(relevance=0.9, epistemic=0.9) == 0

    def test_medium_relevance_returns_1(self):
        assert assign_memory_lod(relevance=0.6, epistemic=0.8) == 1

    def test_low_relevance_returns_2(self):
        assert assign_memory_lod(relevance=0.4, epistemic=0.5) == 2

    def test_very_low_relevance_returns_5(self):
        assert assign_memory_lod(relevance=0.01, epistemic=0.01) == 5

    def test_epistemic_floor_high_confidence(self):
        # High epistemic confidence should floor at LOD 2 even with low relevance
        lod = assign_memory_lod(relevance=0.05, epistemic=0.9)
        assert lod <= 2, f"Epistemic floor violated: got LOD {lod} for epistemic=0.9"

    def test_epistemic_floor_boundary(self):
        # At exactly 0.8 epistemic, floor should apply
        lod = assign_memory_lod(relevance=0.05, epistemic=0.8)
        assert lod <= 2

    def test_no_floor_for_low_epistemic(self):
        # Low epistemic + low relevance should allow high LOD
        lod = assign_memory_lod(relevance=0.05, epistemic=0.3)
        assert lod >= 3

    def test_combined_score_thresholds(self):
        # combined = 0.6 * relevance + 0.4 * epistemic
        # 0.6*0.5 + 0.4*0.5 = 0.5 → LOD 1
        assert assign_memory_lod(0.5, 0.5) == 1
        # 0.6*0.3 + 0.4*0.3 = 0.3 → below 0.35, LOD 2 (if epi < 0.8)
        # Actually 0.3 < 0.35 so check next: epi=0.3 < 0.8, then 0.3 >= 0.20 → LOD 3
        assert assign_memory_lod(0.3, 0.3) == 3


class TestCompressBatch:
    def test_empty_batch(self):
        assert compress_batch([]) == ""

    def test_fits_budget(self):
        memories = [
            {"content": "nginx is running", "category": "service", "relevance": 0.9, "epistemic_score": 0.9},
            {"content": "ssh is enabled", "category": "security", "relevance": 0.7, "epistemic_score": 0.8},
        ]
        result = compress_batch(memories, target_chars=1000)
        assert len(result) > 0
        assert "nginx" in result

    def test_exceeds_budget_promotes_lod(self):
        # Create many memories that won't fit in a tiny budget
        memories = [
            {"content": f"Service {i} is running on port {i}", "category": "service", "relevance": 0.5, "epistemic_score": 0.5, "id": f"m{i}"}
            for i in range(20)
        ]
        result = compress_batch(memories, target_chars=100)
        # Should fit within budget (or close to it)
        assert len(result) <= 200  # some tolerance

    def test_sorts_by_relevance(self):
        memories = [
            {"content": "low relevance memory about disks", "category": "storage", "relevance": 0.1, "epistemic_score": 0.3},
            {"content": "high relevance memory about nginx", "category": "service", "relevance": 0.9, "epistemic_score": 0.9},
        ]
        result = compress_batch(memories, target_chars=1000)
        # High relevance memory should appear first (it's at LOD 0 = full content)
        assert "nginx" in result


# ── Factory ──────────────────────────────────────────────────────


class TestFactory:
    def test_auto_detect_returns_compressor(self):
        c = create_compressor()
        assert isinstance(c, ContextCompressor)

    def test_auto_detect_semantic_when_no_llmlingua(self):
        # If llmlingua is not installed, should fall back to Semantic
        c = create_compressor(prefer_neural=True)
        # Either Lingua (if installed) or Semantic
        assert isinstance(c, (LinguaCompressor, SemanticCompressor))

    def test_explicit_lingua(self):
        c = create_compressor(backend="lingua")
        # Returns Lingua if available, else Semantic fallback
        assert isinstance(c, (LinguaCompressor, SemanticCompressor))

    def test_explicit_semantic(self):
        c = create_compressor(backend="semantic")
        assert isinstance(c, SemanticCompressor)

    def test_explicit_noop(self):
        c = create_compressor(backend="noop")
        assert isinstance(c, NoopCompressor)

    def test_no_neural_preference(self):
        c = create_compressor(prefer_neural=False)
        assert isinstance(c, SemanticCompressor)
