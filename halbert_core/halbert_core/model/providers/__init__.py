# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Model providers package (Phase 5 M1, Phase 38).

Provides abstraction layer for different model backends.
Supports: Ollama (local), Anthropic (API), OpenAI (API)
"""

from .base import (
    ModelProvider, ModelConfig, ModelResponse, ModelCapability,
    ModelLoadError, ModelNotLoadedError, ModelNotFoundError, GenerationError
)
from .ollama import OllamaProvider
from .llamacpp import LlamaCppProvider
from .mlx import MLXProvider

# Phase 38: API providers (optional dependencies)
try:
    from .anthropic import AnthropicProvider, ANTHROPIC_AVAILABLE
except ImportError:
    AnthropicProvider = None
    ANTHROPIC_AVAILABLE = False

__all__ = [
    "ModelProvider",
    "ModelConfig",
    "ModelResponse",
    "ModelCapability",
    "OllamaProvider",
    "LlamaCppProvider",
    "MLXProvider",
    "AnthropicProvider",
    "ANTHROPIC_AVAILABLE",
]
