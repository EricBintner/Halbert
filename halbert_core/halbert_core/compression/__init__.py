"""
Halbert Compression Package

Unified context compression for Halbert's memory and conversation systems.

3-tier context compression system:
  - LinguaCompressor: LLMLingua-2 token pruning (178MB, neural, lazy-loaded)
  - SemanticCompressor: Rule-based regex compression (zero deps, always works)
  - MemoryLOD: 6-level structural compression for memories (budget-aware)

Ported from LinuxBrain Phase 72, adapted for sysadmin context.

Usage:
    from halbert_core.compression import create_compressor, compress_memory

    # Prose compression
    compressor = create_compressor()
    result = compressor.compress("Long memory text...", level="standard")

    # Memory LOD compression
    from halbert_core.compression.memory_lod import compress_memory, assign_memory_lod
    lod = assign_memory_lod(relevance=0.6, epistemic=0.8)
    compressed = compress_memory(memory, lod=lod)
"""

from halbert_core.compression.compressor import (
    ContextCompressor,
    CompressResult,
    NoopCompressor,
)
from halbert_core.compression.lingua_compressor import LinguaCompressor
from halbert_core.compression.semantic_compressor import SemanticCompressor
from halbert_core.compression.factory import create_compressor

__all__ = [
    "ContextCompressor",
    "CompressResult",
    "NoopCompressor",
    "LinguaCompressor",
    "SemanticCompressor",
    "create_compressor",
]
