"""
Model provider abstraction for Halbert (Phase 5 M1).

Supports multiple LLM backends:
- Ollama (production-ready)
- llama.cpp (lightweight)
- MLX (Mac Apple Silicon)
"""

from .base import ModelProvider, ModelConfig, ModelResponse, ModelCapability
from .ollama import OllamaProvider
from .llamacpp import LlamaCppProvider
from .mlx import MLXProvider

__all__ = [
    "ModelProvider",
    "ModelConfig",
    "ModelResponse",
    "ModelCapability",
    "OllamaProvider",
    "LlamaCppProvider",
    "MLXProvider",
]
